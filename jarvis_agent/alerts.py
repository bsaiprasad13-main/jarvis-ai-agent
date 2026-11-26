"""Email me when a run needs attention, and say exactly where it went wrong.

When an email goes out:
- FAILED: the run crashed, or a final check failed (the website may not have today's report).
- DEGRADED: the brief went out, but every agent writer on a desk failed and the old pipeline
  wrote that desk's section.
No email when the harness quietly recovered (a reserve model took over): that is normal
operation and is visible on the website's report card instead.

Uses Resend. Needs RESEND_API_KEY, ALERT_TO_EMAIL and ALERT_FROM_EMAIL (falls back to TO_EMAIL /
FROM_EMAIL). If they're missing, the alert is only logged.
"""
import os

import requests

SITE = "https://bsaiprasad13-main.github.io/jarvis-ai-agent/"


def classify(report_checks, trace, error):
    """Returns ('failed' | 'degraded' | 'ok', reasons)."""
    if error:
        return "failed", [f"The run stopped with an error: {error.splitlines()[-1][:300] if error else ''}"]
    failed = [c for c in report_checks if c.get("final", True) and not c.get("warning") and not c["passed"]]
    if failed:
        return "failed", [f"{c['check']}: {c['evidence']}" for c in failed]
    reasons = [f"{d['title']}: every agent writer failed, so the old pipeline wrote this section"
               for d in (trace or {}).get("desks", []) if d.get("written_by") in ("pipeline", "failed")]
    reasons += [f"{c['check']}: {c['evidence']}" for c in report_checks if c.get("warning") and not c["passed"]]
    return ("degraded", reasons) if reasons else ("ok", [])


def build_message(status, reasons, report_checks, trace, error, run_id):
    retried = [c for c in report_checks if c.get("final") is False and not c["passed"]]
    lines = [f"Jarvis run {run_id}: {status.upper()}", ""]
    lines += ["What went wrong:"] + [f"  - {r}" for r in reasons] + [""]
    if retried:
        lines += ["What the harness recovered from on the way:"]
        lines += [f"  - {c['check']}: {c['evidence'].splitlines()[0][:200]}" for c in retried] + [""]
    if report_checks:
        lines += ["Full report card:"]
        for c in report_checks:
            tag = "PASS" if c["passed"] else ("WARN" if c.get("warning") else ("FAIL" if c.get("final", True) else "RETRIED"))
            lines.append(f"  {tag:7} {c['check']}")
        lines.append("")
    if trace:
        for d in trace.get("desks", []):
            for a in d.get("attempts", []):
                lines.append(f"  {d['title']} {a['role']} [{a['model']}]: steps {a['steps']}, "
                             f"drafts {[x['score'] for x in a['drafts']]}, error: {(a.get('error') or 'none')[:150]}")
        lines.append("")
    if error:
        lines += ["Error details (last lines):", "\n".join(error.strip().splitlines()[-12:]), ""]
    lines += [f"Website: {SITE}", "Logs: Catalyst console > Functions > jarvis_agent > Logs"]
    return "\n".join(lines)


SETTINGS = ("GEMINI_API_KEY", "PRODUCT_HUNT_DEVELOPER_TOKEN", "JARVIS_BUCKET",
            "RESEND_API_KEY", "ALERT_TO_EMAIL", "ALERT_FROM_EMAIL")


def setting(name, *fallbacks):
    """An environment value with stray spaces and wrapping quotes removed (common copy-paste mistakes)."""
    for n in (name, *fallbacks):
        v = (os.environ.get(n) or "").strip().strip('"').strip("'").strip()
        if v:
            return v
    return ""


def settings_report():
    """Which settings this function can see. Names only, never values."""
    present = [n for n in SETTINGS if setting(n)]
    missing = [n for n in SETTINGS if not setting(n)]
    return f"settings present: {', '.join(present) or 'none'} | missing: {', '.join(missing) or 'none'}"


def send(status, reasons, report_checks, trace, error, run_id, log=print):
    if status == "ok":
        return False
    body = build_message(status, reasons, report_checks, trace, error, run_id)
    key = setting("RESEND_API_KEY")
    to = setting("ALERT_TO_EMAIL", "TO_EMAIL")
    sender = setting("ALERT_FROM_EMAIL", "FROM_EMAIL")
    subject = (f"Jarvis FAILED: {reasons[0][:90]}" if status == "failed"
               else "Jarvis needs attention: backup pipeline used")
    missing = [n for n, v in (("RESEND_API_KEY", key), ("ALERT_TO_EMAIL", to), ("ALERT_FROM_EMAIL", sender)) if not v]
    if missing:
        log(f"ALERT NOT EMAILED: missing setting(s) {', '.join(missing)} on this function.\n" + body)
        return False
    try:
        resp = requests.post("https://api.resend.com/emails", timeout=20,
                             headers={"Authorization": f"Bearer {key}"},
                             json={"from": sender, "to": [to], "subject": subject, "text": body})
    except Exception as e:
        log(f"ALERT NOT EMAILED: could not reach Resend ({type(e).__name__}).\n{body}")
        return False
    if resp.status_code in (200, 201):
        log("alert email sent")
        return True
    log(f"ALERT NOT EMAILED: Resend rejected it (HTTP {resp.status_code}): {resp.text[:300]}\n"
        f"Check ALERT_FROM_EMAIL uses your verified Resend domain and RESEND_API_KEY can send.\n{body}")
    return False

