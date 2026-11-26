"""Measure the checker: does it catch invented details, and does it pass faithful drafts?

    python evals/checker_eval.py [label] [runs]   # real model calls (needs GEMINI_API_KEY), 26 per run

Each case is a two-pick draft for the desk that would write it: the case pick plus a fixed, faithful control pick. Both picks
count as read in full, so the checker sees each article excerpt exactly as it does in a real run. A
draft is rejected for grounding when the checker scores "grounded" below 4, the same bar used in
production (evaluator.PASS_MIN_GROUNDED).

Writes evals/<label>.json. Held-out cases (long articles, key fact late in the text) are scored separately.
"""
import json
import os
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from jarvis_agent import evaluator, gemini, tools  # noqa: E402
from jarvis_agent.config import DESK_MODEL  # noqa: E402
from jarvis_agent.desks import GLOBAL, INDIA  # noqa: E402
from jarvis_agent.store import Memory  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
# each case is checked by the desk that would really have written it
SECTION_FOR_SOURCE = {"Product Hunt": "tools", "Hacker News": "tools", "TechCrunch": "ai_news"}


def load_cases():
    with open(os.path.join(HERE, "checker_cases.json"), encoding="utf-8") as f:
        return json.load(f)


def draft_for(case, data):
    """A RunState and digest for one case, set up exactly like a real desk draft: the case pick plus a faithful control."""
    section = SECTION_FOR_SOURCE.get(case["source"], "india_news")
    desk, control = (INDIA, data["control"]) if section == "india_news" else (GLOBAL, data["control_global"])
    state = tools.RunState(Memory(os.path.join(tempfile.mkdtemp(), "m.json")), evaluator.review, desk, model=DESK_MODEL)
    for iid, c in (("i1", case), ("i2", control)):
        state.items[iid] = {"id": iid, "title": c["title"], "source": c["source"], "section": section,
                            "url": f"https://example.test/{iid}", "article": c["article"]}
        state.reads.append(iid)
    digest = {section: [{"item_id": "i1", "title": case["title"], "why_it_matters": case["why"]},
                        {"item_id": "i2", "title": control["title"], "why_it_matters": control["why"]}],
              "notes": {}}
    return state, digest


def verdict(grounded):
    if grounded is None:
        return "no answer"
    return "pass" if grounded >= evaluator.PASS_MIN_GROUNDED else "fail"


def run_case(case, data, case_set):
    state, digest = draft_for(case, data)
    started = time.time()
    r = evaluator.review(state, digest)
    if r.get("unavailable"):                       # a temporary model error (503/429): wait and ask once more
        time.sleep(15)
        r = evaluator.review(state, digest)
    grounded = (r.get("rubric") or {}).get("grounded", {}).get("score")
    print(f"{case['id']:>4} {case['label']:<9} grounded={grounded} -> {verdict(grounded)}")
    return {"set": case_set, "id": case["id"], "label": case["label"], "change": case.get("change", ""),
            "grounded": grounded, "verdict": verdict(grounded), "model": r.get("evaluator_model"),
            "seconds": round(time.time() - started, 1), "unavailable": bool(r.get("unavailable")),
            "evidence": (r.get("rubric") or {}).get("grounded", {}).get("evidence", "")[:200]}


def score(rows):
    done = [x for x in rows if not x["unavailable"]]
    bad = [x for x in done if x["label"] == "invented"]
    good = [x for x in done if x["label"] == "faithful"]
    return {"invented_caught": f"{sum(x['verdict'] == 'fail' for x in bad)}/{len(bad)}",
            "faithful_passed": f"{sum(x['verdict'] == 'pass' for x in good)}/{len(good)}",
            "no_answer": len(rows) - len(done)}


def main():
    data = load_cases()
    runs = int(sys.argv[2]) if len(sys.argv) > 2 else 1        # repeat to see how stable the verdicts are
    rows = []
    for n in range(runs):
        rows += [dict(run_case(c, data, "main"), run=n + 1) for c in data["cases"]]
        rows += [dict(run_case(c, data, "held_out"), run=n + 1) for c in data.get("held_out", [])]
    oks = sorted(c["ms"] for c in gemini.CALLS if c.get("ok"))

    def pct(q):
        return round(oks[min(len(oks) - 1, int(q * len(oks)))] / 1000, 1) if oks else None
    summary = {"runs": runs, "main": score([x for x in rows if x["set"] == "main"]),
               "held_out": score([x for x in rows if x["set"] == "held_out"]),
               "checker_models": sorted({x["model"] for x in rows if x["model"]}),
               "latency_p50_s": pct(0.5), "latency_p95_s": pct(0.95),
               "model_calls": len(gemini.CALLS), "failed_calls": sum(1 for c in gemini.CALLS if not c.get("ok"))}
    label = sys.argv[1] if len(sys.argv) > 1 else "results"
    with open(os.path.join(HERE, f"{label}.json"), "w", encoding="utf-8") as f:
        json.dump({"summary": summary, "cases": rows}, f, indent=1)
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
