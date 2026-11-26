# Jarvis AI Agent

A multi-agent AI system that writes a daily brief for engineers who build with AI: new AI and developer tools, AI industry news, and India tech and startup news. Two desk agents decide what to read and write; an evaluator on a different model checks every draft; a harness written in plain code decides when the work is actually done. Anyone can then chat with the briefs on the website, using a small model that runs on their own device.

**Live:** [website](https://bsaiprasad13-main.github.io/jarvis-ai-agent/) (every run with its evidence, a chat, and monitoring) · runs daily at 10:00 IST on GitHub Actions.

It grew out of a fixed pipeline that has emailed me a daily brief in production on Zoho Catalyst. This version turns it into agents, and keeps the old pipeline as the last fallback.

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
                         │  fetch · read articles · search · Edgepedia background · draft
                         ▼
                 Evaluator (a different model) ── rubric score + exact fixes ──► back to that desk
                         │ accepted
                         ▼
          done-check (code) ── fail ──► reserve models redo the desk ── fail ──► old pipeline, that desk only
                         │ pass
                         ▼
          final checks (code) ──► email + website data (read back) + report card + per-call latency
```

- **Desks are agents with function calling.** Each decides which of its sources to fetch, which articles to read in full, when to search for more, which companies or concepts to look up on [Edgepedia](https://www.edgepedia.org) for background, and when its draft is ready. It can only touch its own sources and sections.
- **The evaluator is a separate model in a fresh context**, so no model grades its own work. It scores each draft 1–5 on grounded, specific, relevant, selection and honest, with evidence and exact fixes. Malformed or missing reviews fall through to the next evaluator model and never cost the writer a draft.
- **Done is decided by code.** `finish` is refused until the desk's contract is met: sources fetched, enough articles read, sections filled (an empty "quiet" section is refused when there were enough stories), and the evaluator's approval.
- **Failures are routed by code.** A desk that crashes, runs out of steps or stops half done goes to a reserve model, then the next, then the old pipeline for that desk only. Every run ends with a report card: PASS, FAIL, or RETRIED when the harness recovered.

## The agent is a spec

The reader, the sections and the desks live in [`jarvis.config.json`](jarvis.config.json). A different audience, different sections or different sources is a config change, not a code change: the prompts, the evaluator's rubric and the fallback pipeline all read the same spec.

## Hallucination controls

- **No invented links.** Models only see story ids like `g14`; code maps them back to fetched URLs, and a final check confirms every link was fetched that day.
- **Grounding.** At least 2–3 picks per desk must be read in full; the evaluator checks each explanation against the article excerpt. Background lines come only from real Edgepedia lookups (code-checked).
- **Web text is data.** Article text is labelled as information; no tool can act on it.
- **Chat answers are checked too.** The on-device chat answers only from retrieved stories and must cite them; code replaces an answer that cites nothing with "that isn't in my briefs".

## Ask Jarvis: chat that runs on your device

The website retrieves the stories that match a question (BM25 over every run) and, if you load it, runs Qwen2.5 1.5B in your browser with WebGPU ([WebLLM](https://github.com/mlc-ai/web-llm)). After a one-time download nothing you type leaves the page. It shows time to first token and tokens per second for each answer.

## Monitoring

Every model call is timed and saved with the run. The website computes, across runs: calls, success rate, median and p95 latency per model, failure codes, first-draft acceptance, recoveries, and what the harness and evaluator caught (headline-only drafts, made-up ids, ungrounded claims, early `finish` calls).

## Lifecycle

| Stage | How |
|---|---|
| Spec | `jarvis.config.json`: reader, sections, desks |
| Tests | `python tests/test_agent.py`: 38 offline checks (fake models and sources), run in CI before every daily run |
| Staging | `python run.py --dry-run`: real models and sources, separate test memory, email saved not sent |
| Fault test | `JARVIS_FAULT=india:writer python run.py --dry-run`: crash a writer on purpose and watch the recovery |
| Production | GitHub Actions daily at 10:00 IST: `python run.py --no-email`, publishes to the website |
| Monitoring | Report card per run + latency and failure stats on the website |

## Run it

```
pip install -r requirements.txt
copy .env.example .env        # GEMINI_API_KEY, PRODUCT_HUNT_DEVELOPER_TOKEN (+ RESEND_API_KEY, TO_EMAIL, FROM_EMAIL to email)
python run.py --dry-run
python tests/test_agent.py
```

Models (optional): `DESK_MODEL`, `RESERVE_MODELS`, `EVALUATOR_MODELS` (comma-separated, tried in order).

## Files

| File | What |
|---|---|
| `jarvis.config.json` | The agent spec |
| `jarvis_agent/harness.py` | Runs desks in parallel, routes failures, final checks, report card |
| `jarvis_agent/agent.py` | One desk's agent loop and instructions |
| `jarvis_agent/tools.py` | Desk tools (fetch, read, search, Edgepedia, submit, lesson, finish) and the definition of done |
| `jarvis_agent/evaluator.py` | Code rules + rubric review by a different model |
| `jarvis_agent/gemini.py` | Gemini REST client: function calling, retry, per-call timing |
| `jarvis_agent/store.py` | Memory across runs: sent links, feed URLs, lessons per desk |
| `site/index.html` | Website: runs, on-device chat, monitoring |
| `run.py` | One run: harness → email → website data → memory |
