"""Paths and settings. API keys come from .env (never from code)."""
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT, "data")
RUNS_DIR = os.path.join(ROOT, "runs")
SITE_DATA_DIR = os.path.join(ROOT, "site", "data")

try:
    from dotenv import load_dotenv
    # Keys come from .env in this folder, or from the file JARVIS_ENV_FILE points to
    # (e.g. the production News Reporter's .env), so keys never need copying.
    _env = os.path.join(ROOT, ".env")
    load_dotenv(_env if os.path.exists(_env) else os.environ.get("JARVIS_ENV_FILE", _env))
except ImportError:
    pass

# Who does what. The evaluator and the reserve run on a different model from
# the desks, so one model never grades its own work and one outage can't stop a run.
DESK_MODEL = os.environ.get("DESK_MODEL", "gemini-3.5-flash-lite")
RESERVE_MODEL = os.environ.get("RESERVE_MODEL", "gemini-3.5-flash")
EVALUATOR_MODEL = os.environ.get("EVALUATOR_MODEL", "gemini-3.5-flash")
EVALUATOR_BACKUP = os.environ.get("EVALUATOR_BACKUP", "gemini-3.5-flash-lite")   # used (and flagged) only if the evaluator is down

# Guardrails: hard limits enforced in code, not by the AI. Per desk.
MAX_STEPS = int(os.environ.get("AGENT_MAX_STEPS", "20"))
MAX_ARTICLE_READS = 8
MAX_SEARCHES = 3
MAX_DRAFTS = 3
LESSONS_KEPT = 15
