"""The harness: runs the desks, routes failures, and decides when the run is done.

Routing lives in code on purpose. If the thing deciding "what happens when
something fails" were a model, its own failure would go unnoticed.

    Global desk ─┐                        ┌─ pass ─────────────────────────┐
                 ├─ done-check (code) ────┤                                ├─> assemble ─> final checks ─> publish
    India desk ──┘                        └─ fail ─> reserve (other model) ┤
                                                      └─ fail ─> old pipeline for that desk only
"""
import time
from concurrent.futures import ThreadPoolExecutor

import os

from . import fetchers, gemini, legacy
from .agent import run_desk
from .config import DESK_MODEL, RESERVE_MODELS
from .desks import DESKS, SECTION_TITLES
from .tools import DIGEST_KEYS, LEGACY_SECTION, SOURCES, done_check

EMAIL_KEYS = {"tools": "section_1_tools", "ai_news": "section_2_ai_news", "india_news": "section_3_india_news"}


class ReportCard:
    """Every check the harness ran, with its evidence. Saved with each run."""

    def __init__(self):
        self.checks = []

    def add(self, name, passed, evidence="", final=True):
        """final=False marks an attempt the harness can still recover from (shown as RETRIED if it failed)."""
        self.checks.append({"check": name, "passed": bool(passed), "final": final, "evidence": str(evidence)[:400]})
        return passed

    @property
    def passed(self):
        return all(c["passed"] for c in self.checks if c.get("final", True))


def _legacy_for_desk(desk, memory, state, deadline=None):
    """The original one-call pipeline, limited to this desk's sources and sections."""
    if state and state.items:
        items = [dict(i, section=LEGACY_SECTION.get(i["section"], "section_1")) for i in state.items.values()
                 if i["section"] != "search"]
        failed = [n for n, s in state.sources.items() if not s["ok"]]
    else:
        sources = [{"name": n, "method": SOURCES[n]["method"], "section": LEGACY_SECTION[SOURCES[n]["section"]],
                    "url": memory.source_url(n, SOURCES[n]["url"])} for n in desk.sources]
        raw, failed, _ = fetchers.fetch_all_data(sources, memory.last_run())
        items = [i for i in raw if not memory.was_sent(i["url"])]
    fetched = [i["url"] for i in items]
    data = None
    for _ in range(3):
        data = legacy.write_brief(items, failed)
        if data or (deadline and time.time() + 75 > deadline):     # no time left for a wait and another call
            break
        time.sleep(15)
    if not data:
        return None
    out = {"notes": {}, "fetched": fetched if not (state and state.items) else []}
    for k in desk.sections:
        out[k] = data.get(EMAIL_KEYS[k], [])
        n = LEGACY_SECTION[k][-1]
        out["notes"][k] = {"status": data.get("section_notes", {}).get(f"section_{n}_status", "normal"),
                           "message": data.get("section_notes", {}).get(f"section_{n}_message", "")}
    return out


def _rows_from_state(state, digest):
    """Agent digest (ids) -> email rows (real links)."""
    rows = {}
    for k in state.desk.sections:
        rows[k] = []
        for e in digest.get(k) or []:
            item = state.items.get(str(e.get("item_id")))
            if item:
                rows[k].append({"title": e.get("title") or item["title"], "source": item["source"], "link": item["url"],
                                "why_it_matters": e.get("why_it_matters", ""), "item_id": item["id"],
                                "read": bool(item.get("article")),
                                "background": ({"title": state.lookups[e["background"]]["title"], "url": e["background"],
                                                "source": "Edgepedia"} if e.get("background") in state.lookups else None)})
    return rows


WRITER_BUDGET, RESERVE_BUDGET, PIPELINE_RESERVE = 300, 150, 90     # seconds


def run_desk_with_backups(desk, memory, report, log, deadline=None):
    """Writer -> (done-check) -> reserve -> (done-check) -> old pipeline. Returns the desk's outcome.
    Each attempt gets a time budget, and time is always kept back for the old pipeline."""
    attempts = []
    for role, model in [("writer", DESK_MODEL)] + [("reserve", m) for m in RESERVE_MODELS if m != DESK_MODEL]:
        budget = WRITER_BUDGET if role == "writer" else RESERVE_BUDGET
        until = time.time() + budget
        if deadline:
            until = min(until, deadline - PIPELINE_RESERVE)
            if until - time.time() < 45:
                report.add(f"{desk.title}: {role} ({model}) skipped", False, "not enough time left in the run", final=False)
                continue
        state = run_desk(desk, memory, model, log, role=role, tries=5 if role == "writer" else 2, deadline=until)
        missing = done_check(state)
        if state.error:
            missing = [f"crashed: {state.error}"] + missing
        attempts.append({"role": role, "state": state, "missing": missing})
        if report.add(f"{desk.title}: {role} ({model}) met its contract", not missing,
                      "all conditions met" if not missing else "; ".join(missing), final=False):
            digest = state.final_digest()
            report.add(f"{desk.title} delivered its sections", True, f"written by the {role} ({model})")
            return {"desk": desk, "source": role, "state": state, "attempts": attempts,
                    "rows": _rows_from_state(state, digest), "notes": digest.get("notes") or {}}
        log(f"  [{desk.key}] {role} did not meet its contract: {missing[:2]}")
    log(f"  [{desk.key}] all writers failed; running the old pipeline for this desk")
    best = max((a["state"] for a in attempts), key=lambda s: len(s.items)) if attempts else None
    data = _legacy_for_desk(desk, memory, best, deadline)
    report.add(f"{desk.title} delivered its sections", data is not None,
               "written by the old pipeline (all agent writers failed)" if data else "old pipeline also failed")
    if not data:
        return {"desk": desk, "source": "failed", "state": best, "attempts": attempts,
                "rows": {k: [] for k in desk.sections},
                "notes": {k: {"status": "source_issue", "message": "This section could not be written today."} for k in desk.sections}}
    rows = {k: [dict(r, read=False) for r in data[k]] for k in desk.sections}
    return {"desk": desk, "source": "pipeline", "state": best, "attempts": attempts, "rows": rows, "notes": data["notes"],
            "fetched": data["fetched"]}


def run(memory, log=print, deadline=None):
    """Returns (brief, sent_urls, trace, report_card). Raises only if no section could be produced at all."""
    report, started = ReportCard(), time.time()
    gemini.CALLS.clear()
    with ThreadPoolExecutor(max_workers=len(DESKS)) as pool:            # desks work in parallel
        outcomes = list(pool.map(lambda d: run_desk_with_backups(d, memory, report, log, deadline), DESKS))

    # --- assemble ---------------------------------------------------------
    email, all_rows = {"section_notes": {}}, []
    for oc in outcomes:
        for k in oc["desk"].sections:
            email[EMAIL_KEYS[k]] = oc["rows"][k]
            all_rows += oc["rows"][k]
            n = LEGACY_SECTION[k][-1]
            note = oc["notes"].get(k) or {}
            status = note.get("status") or ("normal" if oc["rows"][k] else "quiet")
            email["section_notes"][f"section_{n}_status"] = "quiet" if status == "normal" and not oc["rows"][k] else status
            email["section_notes"][f"section_{n}_message"] = note.get("message", "")

    # --- final checks on the whole digest (code) ---------------------------
    fetched = {i["url"] for oc in outcomes for a in oc["attempts"] for i in a["state"].items.values()}
    fetched |= {u for oc in outcomes for u in oc.get("fetched", [])}
    urls = [r["link"] for r in all_rows if r.get("link")]
    report.add("Every section is filled or honestly explained",
               all(email.get(EMAIL_KEYS[k]) or email["section_notes"].get(f"section_{LEGACY_SECTION[k][-1]}_message")
                   for k in DIGEST_KEYS),
               {SECTION_TITLES[k]: len(email.get(EMAIL_KEYS[k], [])) for k in DIGEST_KEYS})
    report.add("No story appears twice", len(urls) == len(set(urls)), f"{len(urls)} links, {len(set(urls))} unique")
    report.add("Every link came from today's feeds", all(u in fetched for u in urls),
               f"{sum(u in fetched for u in urls)}/{len(urls)} links found in today's fetched stories")
    report.add("The digest has stories", len(urls) > 0, f"{len(urls)} stories")
    if not urls:
        raise RuntimeError("no section could be produced")

    trace = {"seconds": round(time.time() - started), "desks": [_desk_trace(oc) for oc in outcomes],
             "report_card": report.checks, "models": {"desk": DESK_MODEL, "reserve": RESERVE_MODELS},
             "model_calls": list(gemini.CALLS), "fault_injected": os.environ.get("JARVIS_FAULT") or None}
    return email, urls, trace, report


def _desk_trace(oc):
    def attempt(a):
        s = a["state"]
        return {"role": a["role"], "model": s.model, "met_contract": not a["missing"], "missing": a["missing"],
                "error": s.error, "steps": s.steps, "seconds": s.seconds,
                "sources": s.sources, "stories_considered": len(s.items),
                "read": {i: s.items[i]["title"] for i in s.reads if i in s.items and s.items[i].get("article")},
                "searches": s.searches, "lookups": [{"term": v["term"], "title": v["title"], "url": u} for u, v in s.lookups.items()],
                "finish_refusals": s.finish_refusals, "lessons": s.lessons, "summary": s.summary,
                "drafts": [{"score": d["review"]["score"], "accepted": d["review"]["accepted"],
                            "rubric": d["review"]["rubric"], "rule_errors": d["review"]["rule_errors"],
                            "issues": d["review"]["issues"], "evaluator_model": d["review"]["evaluator_model"],
                            "independent": d["review"]["independent"],
                            "picks": [{"section": k, "item_id": e.get("item_id"), "title": e.get("title"),
                                       "why_it_matters": e.get("why_it_matters"),
                                       "read": str(e.get("item_id")) in d["read_ids"]}
                                      for k in s.desk.sections for e in (d["digest"].get(k) or [])]}
                           for d in s.drafts],
                "events": s.events}
    return {"desk": oc["desk"].key, "title": oc["desk"].title, "written_by": oc["source"],
            "sections": {k: oc["rows"][k] for k in oc["desk"].sections},
            "attempts": [attempt(a) for a in oc["attempts"]]}
