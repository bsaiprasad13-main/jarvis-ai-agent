# Checker evaluation

Does the checker catch made-up details? This folder measures it on labelled drafts, using real model calls.

- [`checker_cases.json`](checker_cases.json): **20 main cases** (10 faithful; 10 that each add or change one detail the article doesn't support: a wrong amount, an invented investor, a false "beats every model", a removed safety step...), plus **6 held-out cases** written after the fix and never used to tune it. The held-out articles are long, with the key fact late in the text. Companies are invented, so the model can't answer from memory.
- [`checker_eval.py`](checker_eval.py): runs each case through the real checker exactly like a production draft, by the desk that would write it. `python evals/checker_eval.py after 3` runs every case 3 times.

All runs use `gemini-3.5-flash-lite`, the weakest model in the checker chain.

## Result

| | Before | After (3 runs) |
|---|---|---|
| Invented details caught (main) | **4/10** | **30/30** |
| Faithful drafts passed (main) | 10/10 | 29/29 |
| Held-out: invented caught | - | **9/9** |
| Held-out: faithful passed | - | 9/9 |
| Checks with no answer (model error even after one retry) | 0 | 1 |
| Checker latency p50 / p95 | 2.0 s / 2.3 s | 2.4 s / 2.8 s |

## What changed

**Before** (one run, default temperature): the checker gave one overall "grounded" score. On 6 of 10 made-up details it still scored grounding 4 or 5, a pass. Examples: "cut derailments by half" and "backed by a fresh Google investment", neither of which the article says.

**After**, three changes:
1. The checker lists every factual claim in a read pick (numbers, names, investors, results, "first" or "beats", "all" or "permanently") and marks whether the article supports it. **Code** caps grounding at 2 if any claim is unsupported, whatever score the model gave. See `llm_review` in [`jarvis_agent/evaluator.py`](../jarvis_agent/evaluator.py).
2. The checker sees the full text the writer read (up to 2,500 characters), not just the first 500, so true facts from later in an article aren't rejected. The held-out cases test exactly this.
3. Checker calls use temperature 0: in one run at the default temperature, one invented claim slipped through, so a judge should not be random.

## Per case (main set)

| Case | What was changed | Before | After: correct verdicts |
|---|---|---|---|
| f1 | faithful | pass (5) | 3/3 |
| f2 | faithful | pass (5) | 3/3 |
| f3 | faithful | pass (5) | 2/2 |
| f4 | faithful | pass (5) | 3/3 |
| f5 | faithful | pass (5) | 3/3 |
| f6 | faithful | pass (5) | 3/3 |
| f7 | faithful | pass (5) | 3/3 |
| f8 | faithful | pass (5) | 3/3 |
| f9 | faithful | pass (5) | 3/3 |
| f10 | faithful | pass (5) | 3/3 |
| b1 | wrong amount | fail (2) | 3/3 |
| b2 | invented feature | pass (5) | 3/3 |
| b3 | wrong number | fail (3) | 3/3 |
| b4 | false claim of first | pass (5) | 3/3 |
| b5 | removed the safety step | fail (2) | 3/3 |
| b6 | invented outcome | pass (5) | 3/3 |
| b7 | wrong speed | pass (4) | 3/3 |
| b8 | invented investor | pass (5) | 3/3 |
| b9 | wrong scope | pass (4) | 3/3 |
| b10 | wrong vendor list | fail (2) | 3/3 |

## Held-out set

| Case | What was changed | After: correct verdicts |
|---|---|---|
| h1 | faithful | 3/3 |
| h2 | faithful | 3/3 |
| h3 | faithful | 3/3 |
| h4 | wrong investor (late fact) | 3/3 |
| h5 | invented capability (late fact) | 3/3 |
| h6 | wrong numbers (late fact) | 3/3 |

A correct verdict means invented cases fail grounding (below 4 of 5) and faithful cases pass it. Raw results: [`before.json`](before.json), [`after.json`](after.json).
