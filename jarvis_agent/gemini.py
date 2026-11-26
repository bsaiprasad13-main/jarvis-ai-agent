"""Small Gemini REST client: plain JSON answers and function calling, with retry."""
import json
import os
import threading
import time

import requests

BASE = "https://generativelanguage.googleapis.com/v1beta/models"


class GeminiError(Exception):
    pass


CALLS = []                      # every model call this process made: model, ms, ok, status (for monitoring)
_lock = threading.Lock()


def _record(model, started, status):
    with _lock:
        CALLS.append({"model": model, "ms": round((time.time() - started) * 1000), "ok": status == 200, "status": status})


def _post(model, payload, tries=5, deadline=None):
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        raise GeminiError("GEMINI_API_KEY is not set (put it in .env)")
    url = f"{BASE}/{model}:generateContent"
    wait = 8
    for attempt in range(tries):
        timeout = 60
        if deadline:                                          # never wait past the run's time budget
            timeout = min(60, deadline - time.time())
            if timeout < 5:
                last = "time budget used up"
                break
        started = time.time()
        try:
            # key in a header, never in the URL, so it can't appear in error messages
            resp = requests.post(url, headers={"x-goog-api-key": key}, json=payload, timeout=timeout)
        except requests.RequestException as e:
            last = f"network error: {type(e).__name__}"
            _record(model, started, 0)
        else:
            _record(model, started, resp.status_code)
            if resp.status_code == 200:
                return resp.json()
            last = f"HTTP {resp.status_code}: {resp.text[:300]}"
            if resp.status_code not in (429, 500, 502, 503, 504):
                raise GeminiError(last)
        if deadline and time.time() + wait > deadline:      # out of time: stop retrying
            break
        if attempt < tries - 1:
            time.sleep(wait)
            wait = min(wait * 2, 60)
    raise GeminiError(f"gave up after {tries} tries ({last})")


def _content(res):
    try:
        return res["candidates"][0]["content"]
    except (KeyError, IndexError):
        raise GeminiError(f"no answer from model: {json.dumps(res)[:300]}")


def ask_json(model, prompt, system=None, tries=5):
    """One call that must return JSON. Used by the checker and the fallback pipeline.
    Temperature 0: a judge should give the same verdict for the same draft."""
    payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"responseMimeType": "application/json", "temperature": 0},
    }
    if system:
        payload["systemInstruction"] = {"parts": [{"text": system}]}
    parts = _content(_post(model, payload, tries)).get("parts", [])
    text = "".join(p.get("text", "") for p in parts).strip()
    if text.startswith("```"):
        text = text.strip("`").removeprefix("json").strip()
    return json.loads(text)


def step(model, system, contents, declarations, tries=5, deadline=None):
    """One agent step. Returns the model's content (kept as-is, so any
    thought signatures go back unchanged) and the function calls in it."""
    payload = {
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": contents,
        "tools": [{"functionDeclarations": declarations}],
        # ANY = the model must always answer with a tool call. It ends the
        # run by calling `finish`, never with loose text.
        "toolConfig": {"functionCallingConfig": {"mode": "ANY"}},
    }
    content = _content(_post(model, payload, tries, deadline))
    content.setdefault("role", "model")
    calls = [p["functionCall"] for p in content.get("parts", []) if "functionCall" in p]
    return content, calls
