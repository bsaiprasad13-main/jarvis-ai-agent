"""Zoho Catalyst Job function: runs Jarvis once. Triggered daily at 10:00 IST by Catalyst Job Scheduling.

Reports and memory live in a Stratus bucket (JARVIS_BUCKET). The website reads reports/index.json from it.
If the run fails or needs the backup pipeline, an alert email says where (see jarvis_agent/alerts.py).
Job parameters (optional, for tests from the console):
    mode=test           run and publish a report labelled "test", without changing memory
    fault=india:writer  crash that writer on purpose to watch the recovery
    test_alert=1        only send a test alert email (checks the Resend settings), no run
    watchdog=1          only check that today's daily report exists; alert if it doesn't (run by a 10:30 cron)
"""
import logging
import os
import sys
import time
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)          # the jarvis_agent package and its libraries are bundled here

BUCKET = os.environ.get("JARVIS_BUCKET", "jarvis-reports-66495")


def handler(job_request, context):
    logger = logging.getLogger()
    log = logger.info
    stamp, status = "unknown", "failed"
    try:
        import zcatalyst_sdk
        from jarvis_agent import alerts
        from jarvis_agent.storage import StratusStorage
        from jarvis_agent.store import Memory
        import run as runner

        params = job_request.get_all_job_params() or {}
        log(alerts.settings_report())                       # names only, so a wiped setting is obvious in the logs
        if params.get("test_alert"):
            sent = alerts.send("failed", ["This is a test alert sent from the Catalyst console (test_alert=1). "
                                          "Nothing is wrong."], [], None, None, "test-alert", log=log)
            status = "ok" if sent else "failed"
            raise SystemExit
        if params.get("watchdog"):
            ok, reason = runner.check_today(StratusStorage(zcatalyst_sdk.initialize(req=context), BUCKET), "reports/")
            log(f"watchdog: {reason}")
            if not ok:
                alerts.send("failed", [reason], [], None, None, "watchdog", log=log)
            status = "ok"
            raise SystemExit
        if params.get("fault"):
            os.environ["JARVIS_FAULT"] = str(params["fault"])          # fault-injection test
        mode = "test" if params.get("mode") == "test" else "daily"
        remaining = int(context.get_remaining_execution_time_ms()) / 1000   # Catalyst returns a string
        deadline = time.time() + remaining - 120                           # keep 2 minutes to publish and alert

        app = zcatalyst_sdk.initialize(req=context)
        store = StratusStorage(app, BUCKET)
        memory = Memory(storage=store, key="state/memory.json")
        status, reasons, checks, trace, error, stamp = runner.run_once(
            memory, store, "reports/", "", mode, save_memory=(mode == "daily"), deadline=deadline, log=log)
        if status != "ok":
            alerts.send(status, reasons, checks, trace, error, stamp, log=log)
    except SystemExit:
        pass
    except Exception:
        err = traceback.format_exc()
        logger.error(err)
        try:
            from jarvis_agent import alerts
            alerts.send("failed", ["The job crashed before the harness could report"], [], None, err, stamp, log=log)
        except Exception:
            logger.error("could not send alert:\n" + traceback.format_exc())
    if status == "failed":
        context.close_with_failure()
    else:
        context.close_with_success()
