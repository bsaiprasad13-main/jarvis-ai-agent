"""Paths and settings. API keys come from .env (never from code)."""
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT, "data")

try:
    from dotenv import load_dotenv
    # Keys come from .env in this folder, or from the file JARVIS_ENV_FILE points to
    # (e.g. a shared .env elsewhere), so keys never need copying.
    _env = os.path.join(ROOT, ".env")
    load_dotenv(_env if os.path.exists(_env) else os.environ.get("JARVIS_ENV_FILE", _env))
except ImportError:
    pass

# Who does what. The evaluator and the reserve run on a different model from
# the desks, so one model never grades its own work and one outage can't stop a run.
def _models(name, default):
    return [m.strip() for m in os.environ.get(name, default).split(",") if m.strip()]


DESK_MODEL = os.environ.get("DESK_MODEL", "gemini-3.5-flash-lite")
# Tried in order; the next one is used when one is overloaded or out of quota.
RESERVE_MODELS = _models("RESERVE_MODELS", "gemini-3.5-flash,gemini-3-flash-preview")
EVALUATOR_MODELS = _models("EVALUATOR_MODELS", "gemini-3.5-flash,gemini-3-flash-preview")
RESERVE_MODEL, EVALUATOR_MODEL = RESERVE_MODELS[0], EVALUATOR_MODELS[0]
EVALUATOR_BACKUP = os.environ.get("EVALUATOR_BACKUP", "gemini-3.5-flash-lite")   # last resort; flagged as not independent

# Guardrails: hard limits enforced in code, not by the AI. Per desk.
MAX_STEPS = int(os.environ.get("AGENT_MAX_STEPS", "20"))
MAX_ARTICLE_READS = 8
MAX_SEARCHES = 3
MAX_LOOKUPS = 4               # Edgepedia background lookups
MAX_DRAFTS = 3
LESSONS_KEPT = 15
