# Benchmark run 2 — 2026-07-14 — omitted-intent cases

## Purpose

Round 1 (n=3) validated the mechanism but had only **one** discriminating
(omitted-intent) case. This round is **5 cases deliberately all of the
omitted-intent type** — where the commit message/docstring is truthful but omits
the part of the request the code violates — to size the differential edge.

## Setup

Same as round 1. Implementer: Opus 4.8. Verifier: Sonnet (cross-model).
Two conditions: **intent-anchored** (given original request, runs code, evidence
required) vs **diff-anchored baseline** (given only code + commit message, may run).
Fixtures: [`../impl/omitted-intent/`](../impl/omitted-intent/).

## Result

| Case | Omitted requirement | Intent-anchored (ours) | Diff-anchored baseline |
|------|---------------------|------------------------|------------------------|
| dedupe | keep original order | DRIFTED ✅ | ISSUE ✅ |
| search | case-insensitive | DRIFTED ✅ | **LGTM ❌** |
| roundprice | round half-up | DRIFTED ✅ | ISSUE ✅ |
| validate | trim whitespace first | DRIFTED ✅ | **LGTM ❌** |
| sorttasks | tiebreak by due date | DRIFTED ✅ | **LGTM ❌** |

**Ours: 5/5. Baseline: 2/5. Ours-unique catches: 3 (search, validate, sorttasks).**

## Why the baseline caught 2 (this is the important nuance)

- **dedupe** — the baseline flagged `list(set())` because "remove duplicates"
  *conventionally* implies preserving order, and `set()` losing order is a
  reflexive reviewer red flag. Convention carried it.
- **roundprice** — the baseline flagged `round(x, 2)` because rounding a **price**
  with float `round()` is a known money-rounding smell. Domain knowledge carried it.

Both catches came from **priors** (convention/domain), *not* from knowing the
request. The three it MISSED — case-insensitive search, trim-before-validate,
tiebreak-by-due — are requirements you **cannot infer** from the code + commit
message + convention. Only holding the original request reveals them. That is
precisely the seam intent-anchoring occupies.

## Captured evidence (intent-anchored, abbreviated)

- **search:** `search(['Apple','APPLE PIE',...], 'apple')` → `[]` (case-sensitive). The request's own example fails. DRIFTED.
- **validate:** `valid_username('  ab  ')` → `True` (no trim; trimmed = 2 chars, should be False). Request's own example fails. DRIFTED.
- **sorttasks:** three priority-5 tasks came out `08-01, 01-01, 05-01` (input order) instead of due-ascending. DRIFTED.
- **dedupe:** output order non-deterministic across runs, never first-seen order. DRIFTED. (Baseline also caught.)
- **roundprice:** `round_price(2.675)` → `2.67` not `2.68`; `1.005`→`1.0`. DRIFTED. (Baseline also caught.)

## Combined result (rounds 1 + 2, n=8)

| | Caught | Rate |
|---|---|---|
| Intent-anchored (ours) | 8/8 | **100%** |
| Diff-anchored baseline | 4/8 | 50% |
| **Unique to intent-anchoring** | **4/8** | drift the baseline missed |

The 4 unique catches — newest-first sort, case-insensitive search, trim-first
validation, tiebreak-by-due — are all **arbitrary requirements not inferable from
code + convention.** The 4 the baseline also caught were either blatant in the
code (mean, unused `ip` param) or flagged by convention/domain (dedupe order,
price rounding).

## Honest interpretation

- **Mechanism: robust.** 8/8 across two rounds, cross-model, evidence-based, zero
  false PASS.
- **Edge is real and now sized:** intent-anchoring uniquely catches drift on
  **~50% of these "confidently wrong" cases**, and on the pure omitted-intent
  subset it caught 3/5 the baseline missed.
- **Where it wins is now precise:** when the violated requirement is *specific to
  the request* and not recoverable from code, description, or convention. A strong
  reviewer with good domain priors closes part of the gap (dedupe, round).
- **Selection caveat (important):** these cases were *deliberately chosen* to be
  omitted-intent. Real-world change mixes include many blatant bugs a normal
  review catches, so the field-wide unique-catch rate is **lower than 50%.** The
  honest claim is *"on drift where the code looks right against its own
  description, intent-anchoring catches what review misses,"* not a blanket 50%.

## Limitations

- Still hand-crafted fixtures, single verifier model, non-deterministic.
- No measure yet of **false positives** (does it wrongly flag *correct* code as
  drifted?) — the next needed round is correct implementations, to check it
  doesn't cry wolf.
