"""Run Jarvis once.

On Zoho Catalyst, the Job function (functions/jarvis_agent/main.py) calls run_once() every day at 10:00 IST
and keeps reports and memory in a Stratus bucket. On a laptop:

    python run.py --dry-run     # real models and sources; report saved to site/data, separate test memory
    python run.py               # same, but updates the local memory (data/memory.json)

Either way, a failed or degraded run produces an alert (emailed when Resend is configured, otherwise printed).
"""
import datetime
import json
import os
import sys
import time
import traceback

for _stream in (sys.stdout, sys.stderr):      # Windows consoles can't print every symbol in news titles
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass

from jarvis_agent import alerts, harness  # noqa: E402
from jarvis_agent.config import ROOT  # noqa: E402
from jarvis_agent.storage import LocalStorage  # noqa: E402
from jarvis_agent.store import Memory  # noqa: E402

SECTION_KEYS = ("section_1_tools", "section_2_ai_news", "section_3_india_news")
IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))     # run ids are India time, wherever the code runs


def publish_report(store, prefix, file_prefix, stamp, brief, trace, mode):
    """Write this run's report and update the index, then read the report back to prove it landed."""
    record = {"id": stamp, "kind": "agent", "mode": mode, "email": brief, "trace": trace}
    store.write_text(f"{prefix}{stamp}.json", json.dumps(record, ensure_ascii=False, indent=1, default=str))
    index = json.loads(store.read_text(f"{prefix}index.json") or "[]")
    index = [r for r in index if r["id"] != stamp] + [{
        "id": stamp, "tz": "IST", "kind": "agent", "mode": mode, "file": f"{file_prefix}{stamp}.json",
        "stories": sum(len(brief.get(k, [])) for k in SECTION_KEYS),
        "checks_passed": sum(c["passed"] for c in trace["report_card"] if c.get("final", True)),
        "checks": sum(1 for c in trace["report_card"] if c.get("final", True)),
        "recoveries": sum(1 for c in trace["report_card"] if not c.get("final", True) and not c["passed"])}]
    store.write_text(f"{prefix}index.json", json.dumps(sorted(index, key=lambda r: r["id"]), indent=1))
    back = json.loads(store.read_text(f"{prefix}{stamp}.json") or "{}")
    return [r["link"] for k in SECTION_KEYS for r in (back.get("email") or {}).get(k, [])]


def check_today(store, prefix):
    """Watchdog: was today's daily report published? Returns (ok, reason)."""
    today = datetime.datetime.now(IST).strftime("%Y-%m-%d")
    index = json.loads(store.read_text(f"{prefix}index.json") or "[]")
    todays = [r for r in index if r.get("mode") == "daily" and r["id"].startswith(today)]
    if not todays:
        return False, (f"No daily report was published today ({today}). The 10:00 run may not have started, "
                       "or Catalyst stopped it before it could report. Check Job Scheduling > Jobs and the function logs.")
    last = todays[-1]
    if last.get("checks") and last.get("checks_passed", 0) < last["checks"]:
        return False, f"Today's report ({last['id']}) was published with failed checks. See it on the website."
    return True, f"today's report {last['id']} is published"


def run_once(memory, store, prefix, file_prefix, mode, save_memory, deadline=None, log=print):
    """One full run. Returns (status, reasons, report_checks, trace, error)."""
    stamp = datetime.datetime.now(IST).strftime("%Y-%m-%d_%H%M")
    report_checks, trace, error = [], None, None
    log(f"=== Jarvis run {stamp} ({mode}) ===")
    try:
        memory.prune_sent()
        brief, urls, trace, report = harness.run(memory, log=log, deadline=deadline)
        published = publish_report(store, prefix, file_prefix, stamp, brief, trace, mode)
        report.add("Report published and read back", sorted(published) == sorted(urls),
                   f"{len(published)} stories in {prefix}{stamp}.json")
        trace["report_card"] = report.checks
        publish_report(store, prefix, file_prefix, stamp, brief, trace, mode)   # save the final report card
        report_checks = report.checks
        if save_memory:
            memory.mark_sent(urls)
            for d in trace["desks"]:
                for a in d["attempts"]:
                    if a["met_contract"]:
                        for lesson in a["lessons"]:
                            memory.add_lesson(lesson, d["desk"])
            memory.set_last_run()
            memory.save()
    except Exception:
        error = traceback.format_exc()
        log("!!! RUN FAILED !!!\n" + error)
    status, reasons = alerts.classify(report_checks, trace, error)
    for c in report_checks:
        tag = "PASS" if c["passed"] else ("FAIL" if c.get("final", True) else "RETRIED")
        log(f"  {tag:7} {c['check']}  ({c['evidence'].splitlines()[0][:110] if c['evidence'] else ''})")
    log(f"Run status: {status}")
    return status, reasons, report_checks, trace, error, stamp


def main():
    dry = "--dry-run" in sys.argv
    site_store = LocalStorage(os.path.join(ROOT, "site"))
    memory_path = os.path.join(ROOT, "data", "test_memory.json" if dry else "memory.json")
    status, reasons, checks, trace, error, stamp = run_once(
        Memory(memory_path), site_store, "data/", "data/", "test run" if dry else "local", save_memory=not dry,
        deadline=time.time() + 12 * 60)
    if status != "ok":
        alerts.send(status, reasons, checks, trace, error, stamp)
    sys.exit(0 if status != "failed" else 1)


if __name__ == "__main__":
    main()
