# Checker evaluation

Does the checker catch made-up details? 20 labelled drafts in [`checker_cases.json`](checker_cases.json): 10 faithful, and 10 that each add or change one detail the article doesn't support (a wrong amount, an invented investor, a false "beat every model", a removed safety step...). The companies are invented, so the model can't answer from memory.

Run it: `python evals/checker_eval.py after` (about 20 Gemini calls). Each case is checked exactly like a real draft, by the desk that would write it. Both runs below used the same model, `gemini-3.5-flash-lite`, the weakest model in the checker chain.

## Result

| | Before | After |
|---|---|---|
| Invented details caught | **4/10** | **10/10** |
| Faithful drafts passed | 10/10 | 10/10 |
| Checker latency (p50 / p95) | 2.0 s / 2.3 s | 3.0 s / 3.7 s |

## What changed

**Before:** the checker gave one overall "grounded" score. On 6 of 10 made-up details it still scored grounding 4 or 5, a pass (for example "cut derailments by half" and "backed by a fresh Google investment", neither of which the article says).

**After:** the checker must also list every factual claim in a read pick (numbers, names, investors, results, "first" or "beats", "all" or "permanently") and mark whether the article supports it. **Code** then caps grounding at 2 if any claim is unsupported, whatever score the model gave. The model judges; code decides. See `llm_review` in [`jarvis_agent/evaluator.py`](../jarvis_agent/evaluator.py).

The extra step costs about 1 second per check. The 10 faithful drafts still pass.

## Per case

| Case | What was changed | Before | After |
|---|---|---|---|
| f1 | faithful | pass (5) | pass (5) |
| f2 | faithful | pass (5) | pass (5) |
| f3 | faithful | pass (5) | pass (5) |
| f4 | faithful | pass (5) | pass (5) |
| f5 | faithful | pass (5) | pass (5) |
| f6 | faithful | pass (5) | pass (5) |
| f7 | faithful | pass (5) | pass (5) |
| f8 | faithful | pass (5) | pass (5) |
| f9 | faithful | pass (5) | pass (5) |
| f10 | faithful | pass (5) | pass (5) |
| b1 | wrong amount | **fail** (2) | **fail** (2) |
| b2 | invented feature | pass (5) | **fail** (2) |
| b3 | wrong number | **fail** (3) | **fail** (2) |
| b4 | false claim of first | pass (5) | **fail** (2) |
| b5 | removed the safety step | **fail** (2) | **fail** (2) |
| b6 | invented outcome | pass (5) | **fail** (2) |
| b7 | wrong speed | pass (4) | **fail** (2) |
| b8 | invented investor | pass (5) | **fail** (2) |
| b9 | wrong scope | pass (4) | **fail** (2) |
| b10 | wrong vendor list | **fail** (2) | **fail** (2) |

Grounding verdict: pass means the checker scored grounding 4 or 5; fail means below 4, so the draft goes back to the desk. Raw results: [`before.json`](before.json), [`after.json`](after.json).
