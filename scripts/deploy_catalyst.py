"""One command to deploy Jarvis to Zoho Catalyst without losing its settings.

    python scripts/deploy_catalyst.py [--env-file other.env ...] [--no-alerts]

Why: `catalyst deploy` replaces the function's environment variables with whatever
catalyst-config.json lists, so settings typed only in the console are wiped by the next deploy.
This script:
  1. builds the function folder (scripts/build_catalyst.py),
  2. puts the settings into catalyst-config.json for this deploy only,
  3. runs `catalyst deploy --only functions:jarvis_agent`,
  4. restores the clean catalyst-config.json (secrets never stay in the repo folder or reach git).

Settings: any --env-file files (later ones win), then catalyst.env in the repo root (gitignored) on top.
Old-style TO_EMAIL / FROM_EMAIL are accepted for ALERT_TO_EMAIL / ALERT_FROM_EMAIL. Only names are
printed. It refuses to deploy when a needed setting is missing, because the deploy would wipe it.
"""
import json
import os
import subprocess
import sys

from dotenv import dotenv_values

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG = os.path.join(ROOT, "functions", "jarvis_agent", "catalyst-config.json")
REQUIRED = ["GEMINI_API_KEY", "PRODUCT_HUNT_DEVELOPER_TOKEN", "JARVIS_BUCKET"]
ALERTS = ["RESEND_API_KEY", "ALERT_TO_EMAIL", "ALERT_FROM_EMAIL"]
ALIASES = {"ALERT_TO_EMAIL": "TO_EMAIL", "ALERT_FROM_EMAIL": "FROM_EMAIL"}
OPTIONAL = ["DESK_MODEL", "RESERVE_MODELS", "EVALUATOR_MODELS"]
DEFAULTS = {"JARVIS_BUCKET": "jarvis-reports-66495"}


def clean(v):
    return (v or "").strip().strip('"').strip("'").strip()


def load_settings(files):
    raw = {}
    for f in files:
        raw.update({k: clean(v) for k, v in dotenv_values(f).items() if clean(v)})
    out = dict(DEFAULTS)
    for name in REQUIRED + ALERTS + OPTIONAL:
        v = raw.get(name) or raw.get(ALIASES.get(name, ""), "")
        if v:
            out[name] = v
    return out


def main():
    files = [sys.argv[i + 1] for i, a in enumerate(sys.argv) if a == "--env-file"]
    local = os.path.join(ROOT, "catalyst.env")
    if os.path.exists(local):
        files.append(local)
    if not files or not all(os.path.exists(f) for f in files):
        sys.exit("Settings file not found. Create catalyst.env from catalyst.env.example, or pass --env-file.")
    settings = load_settings(files)
    needed = REQUIRED + ([] if "--no-alerts" in sys.argv else ALERTS)
    missing = [n for n in needed if n not in settings]
    if missing:
        sys.exit(f"Not deploying: missing {', '.join(missing)} (the deploy would wipe them on the function). "
                 "Add them to catalyst.env.")
    print("Deploying with settings:", ", ".join(sorted(settings)))

    subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "build_catalyst.py")], check=True)
    with open(CONFIG, encoding="utf-8", newline="") as f:
        original = f.read()
    try:
        cfg = json.loads(original)
        cfg["deployment"]["env_variables"] = settings
        with open(CONFIG, "w", encoding="utf-8", newline="") as f:
            json.dump(cfg, f, indent="\t")
        result = subprocess.run("catalyst deploy --only functions:jarvis_agent -ni", shell=True, cwd=ROOT,
                                capture_output=True, text=True, encoding="utf-8", errors="replace")
        out = (result.stdout or "") + (result.stderr or "")
        ok = "DEPLOYMENT SUCCESSFUL" in out
        print("Deploy:", "successful" if ok else "FAILED")
        if not ok:
            print("\n".join(l for l in out.splitlines() if "rror" in l)[:2000])
            sys.exit(1)
    finally:
        with open(CONFIG, "w", encoding="utf-8", newline="") as f:     # never leave secrets in the repo folder
            f.write(original)


if __name__ == "__main__":
    main()
