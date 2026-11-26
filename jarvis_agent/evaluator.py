"""The evaluator: reviews each desk's draft before anything is published.

Worker and checker are kept apart: the evaluator runs on a different model
from the desks, in a fresh context, so it isn't grading its own work.

Two layers:
1. Rules checked by code (cannot be argued with): real item ids, no repeats,
   the right section, enough articles read, explanations of sane length.
2. A rubric scored by the evaluator model, 1-5 on each dimension, each with
   evidence. A draft passes only with no rule broken, no dimension below 3,
   and an average of at least 3.5 (shown as 7/10).
"""
from . import gemini
from .config import EVALUATOR_BACKUP, EVALUATOR_MODEL
from .desks import SECTION_BRIEFS

READER = ("a final-year engineering student moving into product management, "
          "looking for Associate PM / PM roles as a fresher")
MIN_WORDS, MAX_WORDS = 12, 70
RUBRIC = {
    "grounded": "Every 'why' is supported by the article excerpt (where given) or the title. Nothing invented.",
    "specific": "Each 'why' names something concrete from the story (a feature, number, decision) and what the reader can learn from it. No generic lines.",
    "relevant": "Picks genuinely help someone breaking into product management right now.",
    "selection": "The strongest available stories were picked; no clearly better unused candidate was skipped; no filler.",
    "honest": "Section notes are truthful about quiet days and failed sources.",
}
PASS_MIN_DIM, PASS_AVG = 3, 3.5


def check_rules(state, digest):
    desk, errors, seen = state.desk, [], set()
    picks = [str(e.get("item_id")) for k in desk.sections for e in (digest.get(k) or [])]
    read = [i for i in picks if state.items.get(i, {}).get("read_attempted")]
    need = min(desk.min_read, len(picks))
    if len(read) < need:
        errors.append(f"Only {len(read)} of your picks were read in full. Use read_article on at least {need} picks "
                      "(start with the ones whose value is least clear) and base why_it_matters on what they say.")
    for key in desk.sections:
        entries = digest.get(key) or []
        if len(entries) > desk.max_items:
            errors.append(f"{key}: {len(entries)} items, max is {desk.max_items}")
        for e in entries:
            iid = str(e.get("item_id", ""))
            item = state.items.get(iid)
            if not item:
                errors.append(f"{key}: item id '{iid}' does not exist. Use only ids your tools returned.")
                continue
            if iid in seen:
                errors.append(f"{iid} is used more than once")
            seen.add(iid)
            if item["section"] != "search" and item["section"] != key:
                errors.append(f"{iid} ({item['source']}) belongs in {item['section']}, not {key}")
            words = len(str(e.get("why_it_matters", "")).split())
            if words < MIN_WORDS:
                errors.append(f"{iid}: why_it_matters is too short ({words} words). Be specific.")
            elif words > MAX_WORDS:
                errors.append(f"{iid}: why_it_matters is too long ({words} words). Keep it to 1-2 sentences.")
    notes = digest.get("notes") or {}
    for key in desk.sections:
        if not digest.get(key) and (notes.get(key) or {}).get("status") == "normal":
            errors.append(f"{key} is empty but its note says 'normal'. Mark it quiet or source_issue and explain.")
    return errors


def _draft_text(state, digest):
    lines = []
    for key in state.desk.sections:
        lines.append(f"## {key}: {SECTION_BRIEFS[key]}")
        for e in digest.get(key) or []:
            item = state.items.get(str(e.get("item_id")), {})
            read = "full article read" if item.get("article") else "title only"
            lines.append(f"- [{e.get('item_id')}] {e.get('title')} ({item.get('source', '?')}, {read})\n"
                         f"  why: {e.get('why_it_matters')}")
            if item.get("article"):
                lines.append(f"  article excerpt: {item['article'][:500]}")
        note = (digest.get("notes") or {}).get(key) or {}
        if note.get("status") and note["status"] != "normal":
            lines.append(f"  note: {note['status']} - {note.get('message', '')}")
    return "\n".join(lines)


def _unused(state, digest, limit=20):
    used = {str(e.get("item_id")) for k in state.desk.sections for e in (digest.get(k) or [])}
    out = []
    for key in state.desk.sections:
        pool = [i for i in state.items.values() if i["id"] not in used and i["section"] in (key, "search")][:limit]
        out.append(f"## unused for {key}\n" + "\n".join(f"- [{i['id']}] {i['title'][:120]} ({i['source']})" for i in pool))
    return "\n".join(out)


def _prompt(state, digest):
    failed = [n for n, s in state.sources.items() if not s["ok"]]
    dims = "\n".join(f'- "{k}": {v}' for k, v in RUBRIC.items())
    return f"""You are a strict, independent evaluator. A writer drafted part of a daily email digest for {READER}.
You did not write it. Judge it against this rubric, scoring each dimension 1-5 (5 = excellent, 3 = acceptable,
1 = poor). Be demanding: most first drafts land at 3 on at least one dimension. Cite evidence for each score.
{dims}
Failed sources today: {failed or "none"}.

Return JSON:
{{"rubric": {{"grounded": {{"score": 1-5, "evidence": "..."}}, "specific": {{...}}, "relevant": {{...}},
  "selection": {{...}}, "honest": {{...}}}},
 "issues": [{{"item_id": "<id or null>", "problem": "...", "fix": "..."}}]}}
List at most 6 issues, most important first. Each fix must say exactly what to change.

DRAFT:
{_draft_text(state, digest)}

CANDIDATES NOT USED:
{_unused(state, digest)}
"""


def llm_review(state, digest):
    prompt = _prompt(state, digest)
    try:
        res, model = gemini.ask_json(EVALUATOR_MODEL, prompt, tries=2), EVALUATOR_MODEL
    except gemini.GeminiError:
        res, model = gemini.ask_json(EVALUATOR_BACKUP, prompt), EVALUATOR_BACKUP
    rubric = {}
    for k in RUBRIC:
        d = (res.get("rubric") or {}).get(k) or {}
        try:
            score = max(1, min(5, int(d.get("score", 1))))
        except (TypeError, ValueError):
            score = 1
        rubric[k] = {"score": score, "evidence": str(d.get("evidence", ""))[:400]}
    issues = [i for i in res.get("issues", []) if isinstance(i, dict)][:6]
    return rubric, issues, model


def review(state, digest):
    errors = check_rules(state, digest)
    try:
        rubric, issues, model = llm_review(state, digest)
    except Exception as e:                       # evaluator unavailable: nothing passes on rules alone
        rubric = {k: {"score": 1, "evidence": "evaluator unavailable"} for k in RUBRIC}
        issues, model = [{"item_id": None, "problem": f"evaluator unavailable ({type(e).__name__})", "fix": "resubmit"}], None
    scores = [d["score"] for d in rubric.values()]
    avg = sum(scores) / len(scores)
    passed = not errors and min(scores) >= PASS_MIN_DIM and avg >= PASS_AVG
    return {"accepted": passed, "score": round(avg * 2, 1), "rubric": rubric, "rule_errors": errors,
            "issues": issues, "evaluator_model": model,
            "independent": model is not None and model != state.model}
