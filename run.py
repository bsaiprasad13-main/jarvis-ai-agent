"""Run Jarvis once.

    python run.py --dry-run   # do everything, but save the email to runs/ instead of sending
    python run.py             # real run: send the email and update memory
"""
import datetime
import json
import os
import sys
import traceback

from jarvis_agent.agent import run_with_fallback
from jarvis_agent.config import RUNS_DIR
from jarvis_agent.email_sender import render_email_html, send_alert_email, send_daily_digest
from jarvis_agent.store import Memory


def main(dry_run):
    os.makedirs(RUNS_DIR, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y-%m-%d_%H%M")
    memory = Memory()
    memory.prune_sent()
    print(f"=== Jarvis agent run {stamp} ({'dry run' if dry_run else 'live'}) ===")

    email, urls, trace = run_with_fallback(memory)

    with open(os.path.join(RUNS_DIR, f"{stamp}_trace.json"), "w", encoding="utf-8") as f:
        json.dump(trace, f, indent=2, default=str)

    if dry_run:
        path = os.path.join(RUNS_DIR, f"{stamp}_email.html")
        with open(path, "w", encoding="utf-8") as f:
            f.write(render_email_html(email, trace))
        print(f"Dry run: email saved to {path} (not sent, memory unchanged)")
    else:
        if not send_daily_digest(email, trace):
            raise RuntimeError("email failed to send via Resend")
        memory.mark_sent(urls)
        for lesson in trace.get("lessons_saved") or []:
            memory.add_lesson(lesson)
        memory.set_last_run()
        memory.save()
        print(f"Sent. {len(urls)} stories logged as sent.")

    drafts = trace.get("drafts") or []
    print(f"Mode: {trace['mode']}" + (f" ({trace['fallback_reason']})" if trace.get("fallback_reason") else ""))
    if drafts:
        print("Drafts: " + ", ".join(f"{d['score']}/10{' accepted' if d['accepted'] else ''}" for d in drafts))
    for lesson in trace.get("lessons_saved") or []:
        print(f"Lesson: {lesson}")


if __name__ == "__main__":
    dry = "--dry-run" in sys.argv
    try:
        main(dry)
    except Exception:
        err = traceback.format_exc()
        print("!!! RUN FAILED !!!\n" + err)
        if not dry:
            send_alert_email(err)
        sys.exit(1)
