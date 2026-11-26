"""Small Gemini REST client: plain JSON answers and function calling, with retry."""
import json
import os
import time

import requests

BASE = "https://generativelanguage.googleapis.com/v1beta/models"


class GeminiError(Exception):
    pass


def _post(model, payload, tries=5):
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        raise GeminiError("GEMINI_API_KEY is not set (put it in .env)")
    url = f"{BASE}/{model}:generateContent"
    wait = 8
    for attempt in range(tries):
        try:
            resp = requests.post(url, params={"key": key}, json=payload, timeout=90)
        except requests.RequestException as e:
            last = f"network error: {e}"
        else:
            if resp.status_code == 200:
                return resp.json()
            last = f"HTTP {resp.status_code}: {resp.text[:300]}"
            if resp.status_code not in (429, 500, 502, 503, 504):
                raise GeminiError(last)
        if attempt < tries - 1:
            time.sleep(wait)
            wait = min(wait * 2, 60)
    raise GeminiError(f"gave up after {tries} tries ({last})")


def _content(res):
    try:
        return res["candidates"][0]["content"]
    except (KeyError, IndexError):
        raise GeminiError(f"no answer from model: {json.dumps(res)[:300]}")


def ask_json(model, prompt, system=None):
    """One call that must return JSON. Used by the critic and the fallback."""
    payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"responseMimeType": "application/json"},
    }
    if system:
        payload["systemInstruction"] = {"parts": [{"text": system}]}
    parts = _content(_post(model, payload)).get("parts", [])
    text = "".join(p.get("text", "") for p in parts).strip()
    if text.startswith("```"):
        text = text.strip("`").removeprefix("json").strip()
    return json.loads(text)


def step(model, system, contents, declarations):
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
    content = _content(_post(model, payload))
    content.setdefault("role", "model")
    calls = [p["functionCall"] for p in content.get("parts", []) if "functionCall" in p]
    return content, calls
