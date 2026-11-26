# Jarvis AI Agent

An autonomous news agent that writes me a daily email digest of the AI tools, AI industry news and Indian startup news worth knowing as someone breaking into product management.

It grew out of Jarvis AI News Reporter, a fixed pipeline that has emailed me every morning in production on Zoho Catalyst. This version turns that pipeline into an **agent**: it decides what to read, checks its own work, fixes it, and learns between runs.

## Workflow vs agent

| | News Reporter (pipeline) | Jarvis AI Agent |
|---|---|---|
| Who decides the steps | Code: fetch → dedupe → one LLM call → send | Gemini, using tools, in a loop |
| What the LLM sees | Headlines only | Headlines, plus full articles it chooses to read |
| Quality check | None: the first answer is sent | An independent editor scores each draft; rejected drafts come back with fixes |
| Failed source | Fixed list of fallback URLs | Also decides whether to search for the story elsewhere |
| Memory | Sent links only | Sent links + lessons it writes for its future self |
| If the AI breaks | Alert email, no digest | Falls back to the old pipeline, so the digest still goes out |

## How a run works

```
           ┌──────────────── Gemini (agent) ────────────────┐
           │  decides the next step from what it has seen   │
           └───────┬───────────────┬───────────────┬────────┘
     fetch_source  │  read_article │  search_hn    │  submit_digest
                   ▼               ▼               ▼
            7 news sources    full page text   Hacker News     ┌─ Editor (critic.py) ─┐
            (sent + dupes                                      │ 1. rules in code     │
             removed by code)                                  │ 2. Gemini as editor, │
                                                               │    score 1–10        │
                                                               └──────┬───────────────┘
                                         rejected: feedback goes back │ accepted (≥7, no rule breaks)
                                                                      ▼
                                                save_lesson → finish → email (+ "how it was made" footer)
```

1. **Gather.** The agent fetches sources. Code removes stories already sent in the last 14 days and near-duplicates.
2. **Investigate.** For stories whose value isn't clear from the title, it reads the full article (up to 12 per run). If a source is down, it can search Hacker News to fill the gap.
3. **Draft and review.** It submits a draft. The editor is two layers:
   - **Rules in code**, which the model can't talk its way around: every story must be one it actually fetched, nothing repeats, items sit in the right section, explanations aren't one-liners, empty sections say why.
   - **Gemini as a strict editor**, a separate call that scores usefulness for the reader 1–10 and lists concrete fixes, including better stories the draft skipped.
4. **Fix.** A rejected draft goes back with the feedback. The agent reads more or swaps stories, then resubmits (3 drafts max).
5. **Reflect.** It saves a short lesson ("VentureBeat failed 3 days running; search for AI news on HN instead"). Tomorrow's run starts by reading its lessons.

## Guardrails (enforced in code, not by the prompt)

- **No made-up links.** The model only sees item ids like `s14`. Code maps them back to real URLs, so every link in the email was fetched that day.
- **Web text is data.** Article text is labelled as information, and the agent has no tool that can act on it. The only outside action is the final email to one fixed address. Titles are HTML-escaped in the email.
- **Budgets.** At most 30 model steps, 12 article reads, 4 searches and 3 drafts per run.
- **Always delivers.** If the agent errors or runs out of steps without a usable draft, the original pipeline writes the digest.
- **Visible trace.** Each email ends with how it was made: sources checked, stories considered, articles read, each draft's score. The full step-by-step log is saved in `runs/`.

## Run it

```
pip install -r requirements.txt
copy .env.example .env        # then fill in your keys
python run.py --dry-run       # full run, email saved to runs/ instead of sent
python run.py                 # live: sends the email and updates memory
python tests/test_agent.py    # 23 offline checks, no keys or internet needed
```

Keys (`.env`): `GEMINI_API_KEY`, `RESEND_API_KEY`, `PRODUCT_HUNT_DEVELOPER_TOKEN`, `TO_EMAIL`, `FROM_EMAIL`. Optional: `AGENT_MODEL` (default `gemini-3.5-flash-lite`).

## Files

| File | What |
|---|---|
| `jarvis_agent/agent.py` | The loop, the agent's instructions, fallback to the old pipeline |
| `jarvis_agent/tools.py` | The 6 tools and the run's shared state |
| `jarvis_agent/critic.py` | The editor: code rules + Gemini review |
| `jarvis_agent/store.py` | Memory across runs (sent links, feed URLs, lessons) |
| `jarvis_agent/gemini.py` | Gemini REST client with function calling and retry |
| `jarvis_agent/fetchers.py`, `vector_store.py`, `email_sender.py`, `legacy.py` | Reused from the production pipeline |

## Next

- Deploy on Zoho Catalyst as a Job function (agent runs take minutes, longer than a basic function allows), with memory in the Data Store.
- Let me reply to the email ("more like this", "skip these") and turn replies into lessons.
