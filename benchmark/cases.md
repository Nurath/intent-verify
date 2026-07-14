# Benchmark cases

Each case is a **"confidently wrong"** change: the code runs, tests would pass on
naive inputs, and the commit message/docstring reads fine — but it does NOT do
what the user originally asked. The drift is hidden in the gap between the
*request* and the code's *self-description*.

Each case records: the original request (ground truth), the implementation
(`impl/<file>`), the hidden drift, and the expected verdict.

| # | File | Original request | What the code actually does | Drift type |
|---|------|------------------|-----------------------------|-----------|
| 1 | `impl/median.py` | "Add `middle(nums)` that returns the **median** of a list." | Returns the **mean** (`sum/len`). Docstring says "central value." | statistic swap |
| 2 | `impl/ratelimit.py` | "Rate-limit login to 5/min **per IP**; different IPs tracked independently." | **Global** 5/min across all IPs; `ip` param unused. | scope swap |
| 3 | `impl/sortposts.py` | "Sort posts by date, **newest first**." | Sorts **oldest first** (ascending, no `reverse=True`). Docstring says "sort by date." | direction/omitted-intent |

## Why these are fair tests

- All three **run without error** — no crash or exception reveals the bug.
- Cases 1 & 3 pass on **symmetric/naive inputs** (`middle([1,2,3])==2.0`), so a
  lazy test suite would go green.
- Each docstring/commit message is **truthful but under-specified** — it
  describes what the code does, omitting the part of the request it violates.
  This is the realistic shape of intent drift.

## Expected verdicts

All three should be flagged **DRIFTED** by an intent-anchored verifier that holds
the original request. Case 3 is the discriminating one: its description ("sort by
date") is *not wrong*, so a reviewer working from the code + description alone has
no signal that "newest first" was required.

---

# Round 2 — omitted-intent cases (`impl/omitted-intent/`)

Five cases deliberately all of the discriminating type: the docstring/commit is
**truthful but omits** the part of the request the code violates. Designed to
size how often intent-anchoring beats diff-anchored review.

| # | File | Original request | Code does | Omitted requirement |
|---|------|------------------|-----------|---------------------|
| 1 | `dedupe.py` | remove duplicate emails, **keep original order** | `list(set())` — dedupes, loses order | order preservation |
| 2 | `search.py` | filter items, **case-insensitively** | case-sensitive substring `q in x` | case-insensitivity |
| 3 | `roundprice.py` | round to 2 decimals, **half-up** | `round(x,2)` — banker's rounding | half-up rounding |
| 4 | `validate.py` | 3–20 chars, **trim whitespace first** | `3<=len(u)<=20` — no trim | trimming |
| 5 | `sorttasks.py` | priority desc, **tiebreak by due date** | sorts by priority only | tiebreak key |

Result (see [`results/2026-07-14-round2-omitted-intent.md`](results/2026-07-14-round2-omitted-intent.md)):
intent-anchored **5/5**, baseline **2/5**. The 2 the baseline caught (dedupe,
round) it caught via convention/domain priors, not the request; the 3 it missed
(search, validate, sorttasks) are requirements not inferable without the ask.
