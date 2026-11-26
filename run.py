"""Run Jarvis once.

    python run.py --dry-run                 # everything, but save the email to runs/ instead of sending; memory unchanged
    python run.py --dry-run --save-memory   # same, but remember sent stories and lessons (for back-to-back test runs)
    python run.py --no-email                # daily website run: everything except the email; memory updated
    python run.py                           # live: send the email, update memory and the website data
"""
import datetime
import html
import json
import os
import sys
import traceback

for _stream in (sys.stdout, sys.stderr):      # Windows consoles can't print every symbol in news titles
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass

from jarvis_agent import harness  # noqa: E402
from jarvis_agent.config import RUNS_DIR, SITE_DATA_DIR  # noqa: E402
from jarvis_agent.email_sender import render_email_html, send_alert_email, send_daily_digest  # noqa: E402
from jarvis_agent.store import Memory  # noqa: E402


def publish_site_data(stamp, email, trace, mode):
    """Write this run to site/data and read it back, so 'published' is checked, not assumed."""
    os.makedirs(SITE_DATA_DIR, exist_ok=True)
    run_file = os.path.join(SITE_DATA_DIR, f"{stamp}.json")
    record = {"id": stamp, "kind": "agent", "mode": mode, "email": email, "trace": trace}
    with open(run_file, "w", encoding="utf-8") as f:
        json.dump(record, f, ensure_ascii=False, indent=1, default=str)
    index_file = os.path.join(SITE_DATA_DIR, "index.json")
    index = []
    if os.path.exists(index_file):
        with open(index_file, encoding="utf-8") as f:
            index = json.load(f)
    index = [r for r in index if r["id"] != stamp] + [{
        "id": stamp, "kind": "agent", "mode": mode, "file": f"data/{stamp}.json",
        "stories": sum(len(email.get(k, [])) for k in ("section_1_tools", "section_2_ai_news", "section_3_india_news")),
        "checks_passed": sum(c["passed"] for c in trace["report_card"] if c.get("final", True)),
        "checks": sum(1 for c in trace["report_card"] if c.get("final", True)),
        "recoveries": sum(1 for c in trace["report_card"] if not c.get("final", True) and not c["passed"])}]
    with open(index_file, "w", encoding="utf-8") as f:
        json.dump(sorted(index, key=lambda r: r["id"]), f, indent=1)
    with open(run_file, encoding="utf-8") as f:          # read back
        back = json.load(f)
    links = [r["link"] for k in ("section_1_tools", "section_2_ai_news", "section_3_india_news") for r in back["email"].get(k, [])]
    return links


def main(dry_run, save_memory, no_email=False):
    os.makedirs(RUNS_DIR, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y-%m-%d_%H%M")
    # test runs keep their own memory, so they never shift production's "last run" or sent-story list
    memory = Memory(os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "test_memory.json")) if dry_run else Memory()
    memory.prune_sent()
    mode = "dry run" if dry_run else ("daily" if no_email else "live")
    print(f"=== Jarvis run {stamp} ({mode}) ===")

    email, urls, trace, report = harness.run(memory)

    html_out = render_email_html(email, trace)
    in_email = [u for u in urls if html.escape(u) in html_out or u in html_out]   # links are HTML-escaped (& -> &amp;)
    report.add("Email rendered with every story link", len(in_email) == len(urls), f"{len(in_email)}/{len(urls)} links in the email")
    if dry_run:
        path = os.path.join(RUNS_DIR, f"{stamp}_email.html")
        with open(path, "w", encoding="utf-8") as f:
            f.write(html_out)
        report.add("Email saved (dry run, not sent)", os.path.getsize(path) > 0, path)
    elif not no_email:
        report.add("Email sent", send_daily_digest(email, trace), "Resend accepted the message")

    published = publish_site_data(stamp, email, trace, mode)
    report.add("Website data written and read back", sorted(published) == sorted(urls), f"{len(published)} stories in site/data/{stamp}.json")
    # write again so the final report card (with the publish checks) is what's saved
    trace["report_card"] = report.checks
    publish_site_data(stamp, email, trace, mode)
    with open(os.path.join(RUNS_DIR, f"{stamp}_trace.json"), "w", encoding="utf-8") as f:
        json.dump(trace, f, indent=1, default=str, ensure_ascii=False)

    if not dry_run or save_memory:
        memory.mark_sent(urls)
        for d in trace["desks"]:
            for a in d["attempts"]:
                if a["met_contract"]:
                    for lesson in a["lessons"]:
                        memory.add_lesson(lesson, d["desk"])
        if not dry_run:
            memory.set_last_run()
        memory.save()

    print("\nReport card:")
    for c in report.checks:
        tag = "PASS" if c["passed"] else ("FAIL" if c.get("final", True) else "RETRIED")
        print(f"  {tag:7} {c['check']}  ({c['evidence'][:110]})")
    for d in trace["desks"]:
        for a in d["attempts"]:
            scores = " -> ".join(f"{x['score']}/10" for x in a["drafts"])
            print(f"  {d['title']} {a['role']} [{a['model']}]: drafts {scores or 'none'}; read {len(a['read'])}; "
                  f"finish refused {a['finish_refusals']}x; lesson: {a['lessons'][:1]}")
    if not report.passed:
        raise RuntimeError("report card has failing checks")


if __name__ == "__main__":
    dry = "--dry-run" in sys.argv
    try:
        main(dry, "--save-memory" in sys.argv, "--no-email" in sys.argv)
    except Exception:
        err = traceback.format_exc()
        print("!!! RUN FAILED !!!\n" + err)
        if not dry and "--no-email" not in sys.argv:
            send_alert_email(err)
        sys.exit(1)
