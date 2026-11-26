"""Paths and settings. API keys come from .env (never from code)."""
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT, "data")
RUNS_DIR = os.path.join(ROOT, "runs")

try:
    from dotenv import load_dotenv
    # Keys come from .env in this folder, or from the file JARVIS_ENV_FILE points to
    # (e.g. the production News Reporter's .env), so keys never need copying.
    _env = os.path.join(ROOT, ".env")
    load_dotenv(_env if os.path.exists(_env) else os.environ.get("JARVIS_ENV_FILE", _env))
except ImportError:
    pass

# Model used by the agent and by the critic. Same family as production.
AGENT_MODEL = os.environ.get("AGENT_MODEL", "gemini-3.5-flash-lite")
CRITIC_MODEL = os.environ.get("CRITIC_MODEL", AGENT_MODEL)
# If the agent's model is overloaded, the run switches to this one and carries on.
BACKUP_MODEL = os.environ.get("BACKUP_MODEL", "gemini-3.5-flash-lite")

# Guardrails: hard limits enforced in code, not by the AI.
MAX_STEPS = int(os.environ.get("AGENT_MAX_STEPS", "30"))      # model calls in one run
MAX_ARTICLE_READS = 12                                         # full articles per run
MAX_SEARCHES = 4                                               # extra searches per run
MAX_DRAFTS = 3                                                 # drafts the critic will review
PASS_SCORE = 7                                                 # critic score (1-10) needed to accept
LESSONS_KEPT = 15                                              # notes remembered across runs
