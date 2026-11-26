"""Measure the checker: does it catch invented details, and does it pass faithful drafts?

    python evals/checker_eval.py [label]    # real model calls (needs GEMINI_API_KEY), about 20 calls

Each case is a two-pick draft for the desk that would write it: the case pick plus a fixed, faithful control pick. Both picks
count as read in full, so the checker sees each article excerpt exactly as it does in a real run. A
draft is rejected for grounding when the checker scores "grounded" below 4, the same bar used in
production (evaluator.PASS_MIN_GROUNDED).

Writes evals/results.md (summary and per-case table) and evals/results.json.
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


def main():
    data = load_cases()
    rows = []
    for case in data["cases"]:
        state, digest = draft_for(case, data)
        started = time.time()
        r = evaluator.review(state, digest)
        grounded = (r.get("rubric") or {}).get("grounded", {}).get("score")
        rows.append({"id": case["id"], "label": case["label"], "change": case.get("change", ""),
                     "grounded": grounded, "accepted": r.get("accepted"), "score": r.get("score"),
                     "model": r.get("evaluator_model"), "seconds": round(time.time() - started, 1),
                     "rule_errors": r.get("rule_errors"), "unavailable": bool(r.get("unavailable")),
                     "evidence": (r.get("rubric") or {}).get("grounded", {}).get("evidence", "")[:200]})
        print(f"{case['id']:>4} {case['label']:<9} grounded={grounded} accepted={r.get('accepted')}")

    done = [x for x in rows if not x["unavailable"]]
    bad = [x for x in done if x["label"] == "invented"]
    good = [x for x in done if x["label"] == "faithful"]
    caught = [x for x in bad if x["grounded"] is not None and x["grounded"] < evaluator.PASS_MIN_GROUNDED]
    passed = [x for x in good if x["grounded"] is not None and x["grounded"] >= evaluator.PASS_MIN_GROUNDED]
    oks = sorted(c["ms"] for c in gemini.CALLS if c.get("ok"))

    def pct(q):
        return round(oks[min(len(oks) - 1, int(q * len(oks)))] / 1000, 1) if oks else None
    summary = {
        "invented_caught": f"{len(caught)}/{len(bad)}",
        "faithful_passed": f"{len(passed)}/{len(good)}",
        "unavailable": len(rows) - len(done),
        "checker_models": sorted({x["model"] for x in done if x["model"]}),
        "latency_p50_s": pct(0.5), "latency_p95_s": pct(0.95),
        "model_calls": len(gemini.CALLS), "failed_calls": sum(1 for c in gemini.CALLS if not c.get("ok")),
    }
    label = sys.argv[1] if len(sys.argv) > 1 else "results"
    with open(os.path.join(HERE, f"{label}.json"), "w", encoding="utf-8") as f:
        json.dump({"summary": summary, "cases": rows}, f, indent=1)
    lines = ["# Checker evaluation", "",
             "20 labelled drafts (`checker_cases.json`): 10 faithful, 10 with one invented detail. "
             "Run with `python evals/checker_eval.py`.", "",
             f"- **Invented details caught:** {summary['invented_caught']}",
             f"- **Faithful drafts passed:** {summary['faithful_passed']}",
             f"- **Checker model(s):** {', '.join(summary['checker_models'])}",
             f"- **Checker latency:** p50 {summary['latency_p50_s']} s, p95 {summary['latency_p95_s']} s "
             f"({summary['model_calls']} calls, {summary['failed_calls']} retried or failed)", "",
             "This test measures grounding only (are the facts in the article?). The other rubric points, such as "
             "story selection, are not part of it. A draft fails grounding below 4 of 5.", "",
             "| Case | Label | What was changed | Grounded (1-5) | Grounding verdict |", "|---|---|---|---|---|"]
    lines += [f"| {x['id']} | {x['label']} | {x['change'] or '-'} | {x['grounded']} | {verdict(x['grounded'])} |" for x in rows]
    with open(os.path.join(HERE, f"{label}.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
