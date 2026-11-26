# Jarvis AI Agent

A multi-agent news system that writes me a daily email digest of the AI tools, AI industry news and Indian startup news worth knowing as someone breaking into product management.

It grew out of Jarvis AI News Reporter, a fixed pipeline that emails me every morning in production on Zoho Catalyst. This version turns that pipeline into agents that decide what to read, get their drafts checked by an independent evaluator, fix what it rejects, and learn between runs. A harness written in plain code decides when the work is actually done.

## How a run works

```
                  ┌──────────── Harness (code, not a model) ─────────────┐
                  │ gives each desk a contract · enforces budgets ·      │
                  │ checks "done" · routes failures · final checks       │
                  └──────┬───────────────────────────────┬───────────────┘
                         ▼                               ▼
                 Global desk (agent)              India desk (agent)        run in parallel
                 Product Hunt, Hacker News,       YourStory, Inc42,
                 TechCrunch, VentureBeat          Business Standard
                 → AI tools, AI news              → India startup news
                         │  fetch · read articles · search · draft
                         ▼
                 Evaluator (a different model) ── rubric score + fixes ──► back to that desk
                         │ accepted
                         ▼
          done-check (code) ── fail ──► reserve model redoes the desk ── fail ──► old pipeline, that desk only
                         │ pass
                         ▼
          final checks (code) ──► email + website data (read back to confirm) + report card
```

- **Desks are agents.** Each one decides which of its sources to fetch, which articles to read in full, when to search for more, and when its draft is ready. It can only touch its own sources and sections.
- **The evaluator is a separate model in a fresh context**, so no model grades its own work. It scores each draft 1–5 on five points (grounded in the article, specific, relevant to a future PM, best stories picked, honest about gaps), with evidence for each score and exact fixes. A draft passes with no rule broken, no point below 3, and an average of at least 3.5 (shown as 7/10).
- **Done is decided by code, not by the model.** A desk's `finish` call is refused until its contract is met: every source fetched or its failure reported, enough articles read, every section filled or honestly marked quiet, and the evaluator's approval. The refusal lists exactly what is missing.
- **Failures are routed by code.** A desk that crashes, runs out of steps, or stops with the job half done is handed to a reserve model, and then to the next one. If every model fails, the original pipeline writes that desk's sections, so the email still goes out.
- **Every run ends with a report card.** Each check gets PASS or FAIL with its evidence. A failure the harness recovered from shows as RETRIED.

## Guardrails (in code, not in the prompt)

- **No invented links.** Models only see story ids like `g14`. Code maps them back to the URLs it fetched, and a final check confirms every link in the email was fetched that day.
- **Web text is data.** Article text is labelled as information, no tool can act on it, and the only outside action is one email to a fixed address. Titles are HTML-escaped.
- **Budgets per desk.** 20 model steps, 8 article reads, 3 searches, 3 drafts.
- **Visible evidence.** The email footer and the website show how each desk worked, the evaluator's scores, and the harness checks.

## Run it

```
pip install -r requirements.txt
copy .env.example .env        # then fill in your keys
python run.py --dry-run       # full run; email saved to runs/ instead of sent
python run.py                 # live: sends the email, updates memory and site/data
python tests/test_agent.py    # 29 offline checks, no keys or internet needed
```

Keys (`.env`): `GEMINI_API_KEY`, `RESEND_API_KEY`, `PRODUCT_HUNT_DEVELOPER_TOKEN`, `TO_EMAIL`, `FROM_EMAIL`.
Models (optional): `DESK_MODEL`, `RESERVE_MODELS`, `EVALUATOR_MODELS` (comma-separated, tried in order).

The offline tests cover a desk trying to finish early, a desk crashing, a desk stopping half done, both writers failing, desks staying inside their contract, and the evaluator going down.

## Files

| File | What |
|---|---|
| `jarvis_agent/harness.py` | Runs the desks in parallel, routes failures, final checks, report card |
| `jarvis_agent/desks.py` | The two desks and their contracts |
| `jarvis_agent/agent.py` | One desk's agent loop and instructions |
| `jarvis_agent/tools.py` | The desk tools and the definition of done |
| `jarvis_agent/evaluator.py` | Code rules + rubric review by a different model |
| `jarvis_agent/store.py` | Memory across runs: sent links, feed URLs, lessons per desk |
| `jarvis_agent/gemini.py` | Gemini REST client with function calling and retry |
| `jarvis_agent/fetchers.py`, `vector_store.py`, `email_sender.py`, `legacy.py` | Reused from the production pipeline |
| `run.py` | One run: harness → email → website data → memory |

## Next

- Run it daily on a schedule and publish each run to the website.
- Use an evaluator from a different provider for stronger independence.
- Replay saved days as a regression test whenever a prompt or model changes.
