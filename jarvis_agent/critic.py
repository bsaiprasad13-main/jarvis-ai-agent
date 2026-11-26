"""The editor that reviews each draft before anything is sent.

Two layers:
1. Rules checked by code (cannot be talked around): every item id is real,
   nothing repeats, sections fit, explanations aren't one-liners.
2. A separate Gemini call acting as a strict editor: scores the draft 1-10 for
   usefulness to the reader and lists concrete fixes.
A draft is accepted only if it breaks no rule AND scores >= PASS_SCORE.
"""
from . import gemini
from .config import CRITIC_MODEL, PASS_SCORE
from .tools import DIGEST_KEYS, SECTION_NAMES

READER = ("a final-year engineering student moving into product management, "
          "looking for Associate PM / PM roles as a fresher")
MIN_WORDS, MAX_WORDS, MAX_PER_SECTION = 12, 70, 8


def check_rules(state, digest):
    errors, seen = [], set()
    for key in DIGEST_KEYS:
        entries = digest.get(key) or []
        if len(entries) > MAX_PER_SECTION:
            errors.append(f"{key}: {len(entries)} items, max is {MAX_PER_SECTION}")
        for e in entries:
            iid = str(e.get("item_id", ""))
            item = state.items.get(iid)
            if not item:
                errors.append(f"{key}: item id '{iid}' does not exist. Use only ids you fetched.")
                continue
            if iid in seen:
                errors.append(f"{iid} is used more than once")
            seen.add(iid)
            home = SECTION_NAMES.get(item["section"])
            if home and home != key:
                errors.append(f"{iid} ({item['source']}) belongs in {home}, not {key}")
            words = len(str(e.get("why_it_matters", "")).split())
            if words < MIN_WORDS:
                errors.append(f"{iid}: why_it_matters is too short ({words} words). Be specific.")
            elif words > MAX_WORDS:
                errors.append(f"{iid}: why_it_matters is too long ({words} words). Keep it to 1-2 sentences.")
    notes = digest.get("notes") or {}
    for key in DIGEST_KEYS:
        if not digest.get(key) and (notes.get(key) or {}).get("status") == "normal":
            errors.append(f"{key} is empty but its note says 'normal'. Mark it quiet or source_issue and explain.")
    return errors


def _draft_text(state, digest):
    lines = []
    for key in DIGEST_KEYS:
        lines.append(f"## {key}")
        for e in digest.get(key) or []:
            item = state.items.get(str(e.get("item_id")), {})
            read = "full article read" if item.get("article") else "title only"
            lines.append(f"- [{e.get('item_id')}] {e.get('title')} ({item.get('source', '?')}, {read})\n"
                         f"  why: {e.get('why_it_matters')}")
        note = (digest.get("notes") or {}).get(key) or {}
        if note.get("status") and note["status"] != "normal":
            lines.append(f"  note: {note['status']} - {note.get('message', '')}")
    return "\n".join(lines)


def _unused(state, digest, limit=20):
    used = {str(e.get("item_id")) for k in DIGEST_KEYS for e in (digest.get(k) or [])}
    out = []
    for key in DIGEST_KEYS:
        pool = [i for i in state.items.values()
                if i["id"] not in used and SECTION_NAMES.get(i["section"], key) == key][:limit]
        out.append(f"## unused {key}\n" + "\n".join(f"- [{i['id']}] {i['title'][:120]} ({i['source']})" for i in pool))
    return "\n".join(out)


def llm_review(state, digest):
    failed = [n for n, s in state.sources.items() if not s["ok"]]
    prompt = f"""You are a strict editor reviewing a daily email digest written for {READER}.

Score the draft from 1 to 10 for how genuinely useful it is to this reader today.
Judge:
- Is each "why" specific to this item and to breaking into product management? Generic lines like
  "this shows AI is growing" or "PMs should keep an eye on this" are weak.
- Are the picks important and credible, or did the writer skip clearly better stories (see unused list)?
- Is anything irrelevant, low-effort, clickbait, or just a minor update?
- Are section notes honest (failed sources today: {failed or "none"})?

Return JSON: {{"score": <1-10>, "issues": [{{"item_id": "<id or null>", "problem": "...", "fix": "..."}}]}}
List at most 6 issues, most important first. If the draft is good, return few or no issues.

DRAFT:
{_draft_text(state, digest)}

CANDIDATES NOT USED:
{_unused(state, digest)}
"""
    res = gemini.ask_json(CRITIC_MODEL, prompt)
    score = int(res.get("score", 0))
    issues = [i for i in res.get("issues", []) if isinstance(i, dict)][:6]
    return max(1, min(score, 10)), issues


def review(state, digest):
    errors = check_rules(state, digest)
    try:
        score, issues = llm_review(state, digest)
    except Exception as e:                 # editor unavailable: rules alone decide
        score, issues = (PASS_SCORE if not errors else 1), [{"item_id": None, "problem": f"editor unavailable ({e})", "fix": ""}]
    return {"accepted": not errors and score >= PASS_SCORE, "score": score,
            "rule_errors": errors, "issues": issues}
