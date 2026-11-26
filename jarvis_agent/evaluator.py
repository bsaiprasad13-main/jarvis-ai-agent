"""The evaluator: reviews each desk's draft before anything is published.

Worker and checker are kept apart: the evaluator runs on a different model
from the desks, in a fresh context, so it isn't grading its own work.

Two layers:
1. Rules checked by code (cannot be argued with): real item ids, no repeats,
   the right section, enough articles read, explanations of sane length.
2. A rubric scored by the evaluator model, 1-5 on each dimension, each with
   evidence. A draft passes only with no rule broken, no dimension below 3,
   grounding at 4 or more, and an average of at least 3.5 (shown as 7/10).
3. A fact check: the model lists each factual claim in a read pick's "why" and
   says whether the article text supports it. If any claim is unsupported,
   code caps grounding at 2, whatever score the model gave (measured in evals/).
"""
from . import gemini, tools
from .config import EVALUATOR_BACKUP, EVALUATOR_MODELS
from .desks import READER, SECTION_BRIEFS, TEST_QUESTION


MIN_WORDS, MAX_WORDS = 12, 70
RUBRIC = {
    "grounded": "Facts only: every 'why' is supported by the article text (where given) or the title. Nothing invented. Relevance and section fit are judged elsewhere, not here.",
    "specific": "Each 'why' names something concrete from the story (a feature, number, decision) and what the reader can learn from it. No generic lines.",
    "relevant": f"Picks pass the reader's test: {TEST_QUESTION}",
    "selection": "The strongest available stories were picked; no clearly better unused candidate was skipped; no filler.",
    "honest": "Section notes are truthful about quiet days and failed sources.",
}
PASS_MIN_DIM, PASS_AVG = 3, 3.5
PASS_MIN_GROUNDED = 4      # made-up details are the costliest failure, so grounding has a higher bar


def check_rules(state, digest):
    desk, errors, seen = state.desk, [], set()
    picks = [str(e.get("item_id")) for k in desk.sections for e in (digest.get(k) or [])]
    read = tools.read_picks(state, picks)
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
            if e.get("background") and e["background"] not in state.lookups:
                errors.append(f"{iid}: background must be a background_url returned by lookup_background")
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
                lines.append(f"  article text: {item['article']}")   # everything the desk read (up to 2,500 characters)
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
    owned = ", ".join(state.desk.sections)
    return f"""You are a strict, independent evaluator. A writer drafted part of a daily brief for {READER}.
You did not write it. This writer is the {state.desk.title} and owns ONLY these sections: {owned}. Other sections
are written by another desk, so never penalize their absence; judge only what this desk is responsible for. Judge it against this rubric, scoring each dimension 1-5 (5 = excellent, 3 = acceptable,
1 = poor). Be demanding: most first drafts land at 3 on at least one dimension. Cite evidence for each score.
{dims}
Failed sources today: {failed or "none"}.

Return JSON:
{{"rubric": {{"grounded": {{"score": 1-5, "evidence": "..."}}, "specific": {{...}}, "relevant": {{...}},
  "selection": {{...}}, "honest": {{...}}}},
 "issues": [{{"item_id": "<id or null>", "problem": "...", "fix": "..."}}]}}
List at most 6 issues, most important first. Each fix must say exactly what to change.

FACT CHECK (fill "claims"): for every pick that has an article text, list each specific claim in its
"why": numbers, amounts, names, investors, customers, results, comparisons ("first", "beats", "only") and
scope ("all", "permanently", "already"). Set "supported" to true only if the article text or title states it;
a claim that goes beyond the text is false. Judge facts only here, not relevance.
Add to the JSON: "claims": [{{"item_id": "...", "claim": "...", "supported": true or false}}]

DRAFT:
{_draft_text(state, digest)}

CANDIDATES NOT USED:
{_unused(state, digest)}
"""


def llm_review(state, digest):
    prompt = _prompt(state, digest)
    res = model = None
    for candidate in [m for m in EVALUATOR_MODELS if m != state.model] + [EVALUATOR_BACKUP]:   # writer's own model last
        try:
            res, model = gemini.ask_json(candidate, prompt, tries=2), candidate
            if isinstance(res, dict) and isinstance(res.get("rubric"), dict):
                break
            res = None                                   # malformed answer: try the next evaluator
        except (gemini.GeminiError, ValueError):         # ValueError covers bad JSON
            continue
    if res is None:
        raise gemini.GeminiError("no evaluator returned a usable review")
    rubric = {}
    for k in RUBRIC:
        d = (res.get("rubric") or {}).get(k) or {}
        try:
            score = max(1, min(5, int(d.get("score", 1))))
        except (TypeError, ValueError):
            score = 1
        rubric[k] = {"score": score, "evidence": str(d.get("evidence", ""))[:400]}
    issues = [i for i in res.get("issues", []) if isinstance(i, dict)][:6]
    # code decides grounding: any unsupported claim in a pick whose article was read caps it at 2
    read_ids = {iid for iid, it in state.items.items() if it.get("article")}
    unsupported = [c for c in res.get("claims") or [] if isinstance(c, dict) and c.get("supported") is False
                   and str(c.get("item_id")) in read_ids]
    if unsupported:
        rubric["grounded"] = {"score": min(rubric["grounded"]["score"], 2),
                              "evidence": "Not in the article: " + "; ".join(f"{c.get('item_id')}: {c.get('claim')}" for c in unsupported)[:380]}
        issues = [{"item_id": c.get("item_id"), "problem": f"not supported by the article: {c.get('claim')}",
                   "fix": "remove it or replace it with what the article says"} for c in unsupported][:3] + issues
        issues = issues[:6]
    return rubric, issues, model


def review(state, digest):
    errors = check_rules(state, digest)
    try:
        rubric, issues, model = llm_review(state, digest)
    except Exception as e:                       # evaluator unavailable: nothing passes on rules alone
        return {"accepted": False, "unavailable": True, "score": None, "rubric": {}, "rule_errors": errors,
                "issues": [], "evaluator_model": None, "independent": False, "error": type(e).__name__}
    scores = [d["score"] for d in rubric.values()]
    avg = sum(scores) / len(scores)
    passed = (not errors and min(scores) >= PASS_MIN_DIM and avg >= PASS_AVG
              and rubric["grounded"]["score"] >= PASS_MIN_GROUNDED)
    return {"accepted": passed, "score": round(avg * 2, 1), "rubric": rubric, "rule_errors": errors,
            "issues": issues, "evaluator_model": model,
            "independent": model is not None and model != state.model}
