# Jarvis AI Agent

**A daily AI brief, written by AI agents, checked by an independent AI model, and verified by plain code before anything is published.** It runs every morning at 10:00 IST on Zoho Catalyst and publishes to a website.

- **Website (daily reports):** https://bsaiprasad13-main.github.io/jarvis-ai-agent/
- **Runs on:** Zoho Catalyst: a Job function started by Job Scheduling, with reports and memory in Stratus
- **Code:** this repository

---

## 1. What it is

Every morning Jarvis reads seven sources (Product Hunt, Hacker News, TechCrunch, VentureBeat, YourStory, Inc42, Business Standard) and writes a short brief in three sections for an engineer who builds with AI:

- **AI & developer tools** worth trying
- **AI industry news**: models, platforms, funding and research that change how AI is built
- **India tech & startups**

Each pick has a one- or two-line "why it matters", written from the article itself, plus background from [Edgepedia](https://www.edgepedia.org) where a name needs explaining.

## 2. How it helps

- **For the reader:** about ten minutes of reading replaces an hour of scrolling, and nothing in the brief is made up. Every link was fetched that morning, and every explanation was checked against its article.
- **As engineering:** it is a working answer to the hardest problem with AI agents. Agents sound confident, say they're done when they aren't, and quietly make things up. Jarvis is built so that it can't publish work that hasn't been checked, and when something breaks it recovers or tells me exactly what went wrong.

## 3. How it works

```
 10:00 IST  Zoho Catalyst Job Scheduling starts the Job function
                         │
            ┌──────── Harness (plain code) ─────────┐
            │ contracts · time budgets · routing ·  │
            │ done-checks · final checks · alerts   │
            └─────┬─────────────────────────┬───────┘
                  ▼                         ▼
          Global desk (AI agent)     India desk (AI agent)          run in parallel
          fetch · read articles · search · Edgepedia background · draft
                  │                         │
                  ▼                         ▼
          Checker (a different AI model): scores 1–5 on 5 points, sends back exact fixes
                  │ accepted
                  ▼
          Done-check (code) ── fails ──► backup model ──► backup model ──► original pipeline (that desk only)
                  │ passes
                  ▼
          Final checks (code) ──► report + memory saved to Stratus and read back ──► website
                                   └─ anything wrong ──► alert email saying where
```

| Part | What it does | Where |
|---|---|---|
| **Desk agents** | Gemini with function calling and 7 tools. Each desk owns its own sources and sections and decides what to fetch, what to read in full, what to look up, and when its draft is ready. | `jarvis_agent/agent.py`, `tools.py` |
| **Checker** | A *different* model in a fresh context scores each draft on grounded, specific, relevant, best picks and honest, with evidence, and returns exact fixes. Grounding must score 4 or more out of 5. | `jarvis_agent/evaluator.py` |
| **Harness** | Plain code. Gives each desk a contract, refuses `finish` until it's met, routes failures, enforces time budgets, and runs final checks. | `jarvis_agent/harness.py` |
| **Memory** | Links already published (no repeats for 14 days), feed addresses that worked, and one lesson per desk per day, read at the start of the next run. | `jarvis_agent/store.py` (Stratus `state/memory.json`) |
| **Agent spec** | Reader, sections and desks in one file. A new audience or new sources is a config change, not a code change. | `jarvis.config.json` |
| **Website** | Daily reports, how each one was made, every check, a monitoring view, and an optional on-device chat. | `site/index.html` (GitHub Pages; reads reports from Stratus) |

## 4. Why it is reliable

Every rule below is enforced in code, not by asking the model nicely.

- **The agent can't decide it's done.** `finish` is refused until code confirms the desk's contract: every source tried, enough articles read, every section filled (or honestly marked quiet when there really is little news), and the checker's approval. The refusal lists exactly what's missing.
- **The writer never grades itself.** The checker runs on a different model. If every independent model is unavailable, it falls back to the writer's model, and the report says so openly.
- **It can't invent links.** Models only see story IDs like `g14`; code maps them back to the addresses it actually fetched, and a final check confirms every link was fetched that day. Background links must come from a real Edgepedia lookup.
- **Failures follow fixed routes, decided by code.** A writer that crashes, runs out of steps or stops half way is replaced by a backup model, then another, then the original one-call pipeline for that desk only. If the thing deciding what to do after a failure were itself a model, its own failure would go unnoticed.
- **It always finishes inside Catalyst's 15-minute job limit.** Writers get 5 minutes, backups 2.5 each, model retries stop when time is up, and time is always kept back for the fallback, publishing and the alert.
- **Nothing counts as published until it's read back.** After saving the report, the job reads it from Stratus and compares the links.
- **Web text is data, never instructions.** Article text is labelled as information, no tool can act on it, and the website escapes all text.

## 5. How it was tested

- **50 offline checks** (`python tests/test_agent.py`, with fake models and fake sources, run on every push). They cover:
  - a desk calling `finish` early, crashing, or stopping half done
  - every agent writer failing
  - the checker going down or returning broken JSON (this never costs the writer a draft)
  - weak grounding, invented IDs and background links
  - desks staying inside their contract
  - the time budget
  - the alert rules
  - the **Catalyst Job function end to end**, with a fake SDK and an in-memory bucket: clean run, degraded run, and crash
- **Real runs with real models and sources**, including **fault injection** (`fault=india:writer`). In one test the India writer was crashed on purpose, both backup models then genuinely hit their quota (HTTP 429), and the original pipeline wrote the section. All final checks still passed.

## 6. How we know it works every day

- **A report card for every run**, published on the website: each check marked PASS, FAIL or RETRIED (failed, then recovered automatically), with its evidence.
- **Alert emails, only when they matter:**
  - **FAILED:** the run crashed or a final check failed. The email names the failing check, what was recovered on the way, each desk's attempts, and the last lines of the error.
  - **Needs attention:** the brief went out, but the original pipeline had to write a section because every agent writer failed.
  - **No email** when a backup model quietly took over. That's normal operation, and it's visible on the report card.
- **Monitoring on the website:** for each model, the number of calls, success rate, median and p95 response time, and failure codes. It also shows how often the checker accepts a first draft, and what the system caught: drafts written from headlines alone, made-up IDs, claims the article didn't support, and early `finish` calls.

## 7. What changed, and what the logs taught us

| Version | What changed | Why |
|---|---|---|
| v1 (Sep 2026) | One-call pipeline on Catalyst: fetch, one Gemini call, email at 10:00. Ran daily. | It worked, but it wrote from headlines, repeated stories (5 repeats in 3 days despite a no-repeat rule), and nothing noticed a wrong answer. |
| v2 | One agent with tools, plus a checker model. | Give the model choices (what to read) and an independent check. |
| v3 | Two desk agents, a harness with contracts and fallbacks, a report card. | Specialised, parallel work, and code (not the model) decides when it's done. |
| v4 | Spec file, Edgepedia background, per-call latency, monitoring, on-device chat. | Make it configurable, grounded and observable. |
| v5 (now) | Runs on Zoho Catalyst (Job function, Job Scheduling, Stratus), with alert emails. | GitHub's scheduler starts late or skips runs, and failures need to reach me. |

Fixes found by reading real run logs, each covered by a test:

- An accepted draft contained details the checker itself had flagged as invented, because grounding scored 3. **Grounding now needs 4.**
- A draft that used up its tries could still ship with weak grounding. **It now ships only with grounding of 4 or more.**
- The checker penalised the Global desk for "missing India news", which is the other desk's job. **It's now told which sections each desk owns.**
- A broken reply from the checker counted against the writer. **It now falls through to the next checker model and costs no draft.**
- A desk handed in an empty "quiet" section when it had plenty of stories. **That's now refused.**
- Test runs were reading production memory. **They now use their own.**
- Two of the system's own checks were wrong (counting recovered failures as run failures, and missing HTML-escaped links). The report card exposed both.

## 8. Decisions and why

| Decision | Why |
|---|---|
| **Zoho Catalyst instead of GitHub Actions** to run it | Catalyst Job Scheduling starts on time; GitHub's scheduled runs are often late. The code stays on GitHub. |
| **Job function, not a Basic I/O function** | Basic I/O stops at 30 seconds; a run takes 1–5 minutes. Job functions allow 15. |
| **Stratus for reports and memory** | Simple file storage. The bucket is public read-only, so the website reads reports directly and nobody can change them. Memory holds nothing secret. |
| **Website, not a daily email** | Reports should be readable by anyone, with their evidence. Email is kept for alerts only. |
| **Code decides "done" and routes failures** | Models are confident even when wrong, and the router must not fail with the thing it routes around. |
| **Checker on a different model** | A model grading its own work is generous with itself. |
| **Grounding must score 4 of 5** | Made-up details are the costliest mistake, so they get the strictest bar. |
| **Keep the original pipeline as the last fallback** | A simple, proven path means a bad day still produces a brief. |
| **Gemini model chains** (Flash Lite writes; Flash and 3 Flash Preview back up and check) | Cheap for the bulk of the work, with different models for independence and for outages or quota limits. |
| **Edgepedia for background** | A free, citable source, so background facts can be checked rather than generated. |
| **Optional on-device chat** (WebLLM, Qwen2.5 1.5B on WebGPU) | Answers questions about the reports privately on the visitor's own device. It answers only from the reports and code rejects answers without a source. Without WebGPU it shows matching stories. |

## 9. Skills this project demonstrates

- **Building AI agents and conversational flows:** function-calling agents with tools, contracts and edge-case handlers (early finish, crashes, half-done work, outages), plus a chat that cites its sources and declines honestly.
- **Prompt engineering and context management:** system prompts built from a spec, scoped checker prompts, a rubric with evidence, lessons carried between runs, and retrieval (RAG) over every report for the chat.
- **End-to-end delivery:** spec, then prompts and tools, then offline tests, then staging runs with fault injection, then production on Zoho Catalyst, then monitoring and alerts.
- **Integrations:** Gemini, Product Hunt GraphQL, the Hacker News API, five RSS feeds with self-healing fallbacks, the Edgepedia API, Resend, Zoho Catalyst (Job Scheduling, Stratus) and GitHub Pages.
- **Optimisation from logs:** every fix in section 7 came from reading run traces and report cards; latency and failure rates are tracked per model.
- **Low-latency and on-device AI:** a 1.5B model running in the browser on WebGPU, with time to first token and tokens per second shown for each answer.

## 10. Run it yourself

```
pip install -r requirements.txt
python tests/test_agent.py               # 50 offline checks
copy .env.example .env                   # GEMINI_API_KEY, PRODUCT_HUNT_DEVELOPER_TOKEN
python run.py --dry-run                  # a real run; report saved to site/data
```

**Deploy to Zoho Catalyst:**

```
python scripts/build_catalyst.py         # bundles code + Linux/Python 3.12 libraries
catalyst deploy --only functions:jarvis_agent
```

In the Catalyst console:
1. Create a Stratus bucket (Public template) and allow the website's domain in Bucket CORS.
2. Create a Function job pool.
3. Add the environment variables to `jarvis_agent`.
4. Create a daily 10:00 IST cron that runs the job function.

Environment variables:
- **Needed:** `GEMINI_API_KEY`, `PRODUCT_HUNT_DEVELOPER_TOKEN`, `JARVIS_BUCKET`
- **For alert emails:** `RESEND_API_KEY`, `ALERT_TO_EMAIL`, `ALERT_FROM_EMAIL`
- **Optional model chains:** `DESK_MODEL`, `RESERVE_MODELS`, `EVALUATOR_MODELS`

## 11. Files

| File | What |
|---|---|
| `jarvis.config.json` | The agent spec: reader, sections, desks |
| `jarvis_agent/harness.py` | Runs the desks in parallel, routes failures, time budgets, final checks, report card |
| `jarvis_agent/agent.py` | One desk's agent loop and instructions |
| `jarvis_agent/tools.py` | Desk tools and the definition of done |
| `jarvis_agent/evaluator.py` | Code rules + rubric review by a different model |
| `jarvis_agent/alerts.py` | When to email, and what the email says |
| `jarvis_agent/storage.py`, `store.py` | Local folder or Stratus bucket; memory across runs |
| `jarvis_agent/gemini.py` | Gemini REST client: function calling, retries, time limits, per-call timing |
| `functions/jarvis_agent/main.py` | The Zoho Catalyst Job function entry point |
| `run.py` | One run: harness → publish and read back → memory → alert |
| `scripts/build_catalyst.py` | Builds the Catalyst function folder |
| `site/index.html` | The website |
| `tests/test_agent.py` | The 50 offline checks |
