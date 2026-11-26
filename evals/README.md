# Checker evaluation

Does the checker catch made-up details? Labelled drafts, real model calls.

- [`checker_cases.json`](checker_cases.json): **20 main cases** (10 faithful, 10 that each add or change one detail the article doesn't support) and **6 held-out cases**: long articles with the key fact late in the text, written after the fix and never used to tune it. Companies are invented, so the model can't answer from memory.
- [`checker_eval.py`](checker_eval.py): runs each case through the checker exactly like a production draft. `python evals/checker_eval.py after 3` runs every case 3 times.

**Same conditions for both:** `gemini-3.5-flash-lite` (the weakest model in the checker chain), temperature 0, 3 runs, same cases.

## Result

Counted by **unique case**: a case counts only if the checker got it right in all 3 runs. Totals over every run are in brackets.

| | Original checker | Current checker |
|---|---|---|
| Invented details caught: main (10 cases) | 4/10 (17/30) | **10/10** (30/30) |
| Faithful drafts passed: main (10 cases) | 9/10 (29/30) | 10/10 (29/29) |
| Invented details caught: held-out (3 cases) | 0/3 (1/9) | **3/3** (9/9) |
| Faithful drafts passed: held-out (3 cases) | 2/3 (7/9) | 3/3 (9/9) |
| Checker latency p50 / p95 | 1.7 s / 2.3 s | 2.4 s / 2.8 s |

## What changed

1. **Claim-by-claim fact check, decided by code.** The checker lists every factual claim in a read pick and marks whether the article supports it. Code caps grounding at 2 if any claim isn't clearly supported, whatever score the model gave. See `_parse` in [`jarvis_agent/evaluator.py`](../jarvis_agent/evaluator.py).
2. **The checker sees the full text the writer read** (up to 2,500 characters), not the first 500. The original checker missed almost every late-in-the-article fact on the held-out set, and wrongly rejected some true ones.
3. **Temperature 0**, so the same draft gets the same verdict.

## Limits of this test

- **Small and author-written:** 26 cases, and I wrote them. The prompt names common kinds of claims (numbers, investors, "first"), and the invented cases use those same kinds. A blind set built from real run traces is the next step.
- **Measured before the article fence:** the run above was made before article text was fenced as data in the prompt (a prompt-injection fix). It will be re-run once the API quota allows.
- **One model only:** the test uses the weakest checker model; production tries stronger ones first.

## Per case

| Case | What was changed | Original: right / runs | Current: right / runs |
|---|---|---|---|
| f1 | faithful | 3/3 | 3/3 |
| f2 | faithful | 2/3 | 3/3 |
| f3 | faithful | 3/3 | 2/2 |
| f4 | faithful | 3/3 | 3/3 |
| f5 | faithful | 3/3 | 3/3 |
| f6 | faithful | 3/3 | 3/3 |
| f7 | faithful | 3/3 | 3/3 |
| f8 | faithful | 3/3 | 3/3 |
| f9 | faithful | 3/3 | 3/3 |
| f10 | faithful | 3/3 | 3/3 |
| b1 | wrong amount | 3/3 | 3/3 |
| b2 | invented feature | 1/3 | 3/3 |
| b3 | wrong number | 3/3 | 3/3 |
| b4 | false claim of first | 0/3 | 3/3 |
| b5 | removed the safety step | 3/3 | 3/3 |
| b6 | invented outcome | 0/3 | 3/3 |
| b7 | wrong speed | 2/3 | 3/3 |
| b8 | invented investor | 0/3 | 3/3 |
| b9 | wrong scope | 2/3 | 3/3 |
| b10 | wrong vendor list | 3/3 | 3/3 |
| h1 | faithful | 3/3 | 3/3 |
| h2 | faithful | 1/3 | 3/3 |
| h3 | faithful | 3/3 | 3/3 |
| h4 | wrong investor (late fact) | 0/3 | 3/3 |
| h5 | invented capability (late fact) | 1/3 | 3/3 |
| h6 | wrong numbers (late fact) | 0/3 | 3/3 |

Right means an invented case fails grounding (below 4 of 5) and a faithful case passes it. Raw results: [`before.json`](before.json), [`after.json`](after.json).
