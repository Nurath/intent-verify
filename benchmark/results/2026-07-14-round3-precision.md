# Benchmark run 3 — 2026-07-14 — precision (false-positive) test

## Purpose

Rounds 1–2 measured **recall** (does it catch drift?). A verifier that flags
everything would score perfectly on recall and be useless. This round measures
**precision**: given **correct** implementations of the same requirements, does it
correctly return `MATCHES INTENT`, or does it cry wolf?

## Setup

Same as prior rounds. Verifier: Sonnet (cross-model), evidence required, same
procedure. Fixtures: [`../impl/correct/`](../impl/correct/) — correct
implementations of all 8 requirements from rounds 1 and 2. The verifier was told
NOT to presume the code correct or wrong.

## Result

| Case | Correct implementation | Verdict |
|------|------------------------|---------|
| median | `sorted` + middle/avg-of-two | MATCHES INTENT ✅ |
| rate-limit | per-IP `defaultdict` | MATCHES INTENT ✅ |
| sort | `reverse=True` | MATCHES INTENT ✅ |
| dedupe | `dict.fromkeys` (order-preserving) | MATCHES INTENT ✅ |
| search | `.lower()` both sides | MATCHES INTENT ✅ |
| roundprice | `Decimal(str(x))` + `ROUND_HALF_UP` | MATCHES INTENT ✅ |
| validate | `.strip()` then length | MATCHES INTENT ✅ |
| sorttasks | `(-priority, due)` key | MATCHES INTENT ✅ |

**8/8 correctly passed. 0 false positives.**

## The passes were rigorous, not lazy

The verifiers actively tried to break the correct code before passing it:
- **median:** 10 inputs incl. skewed, negative, float, even/odd, reverse-sorted.
- **rate-limit:** monkey-patched `time.time()` to deterministically test 60s
  window expiry AND cross-IP independence (one IP exhausted, another still allowed).
- **roundprice:** explicitly confirmed `Decimal(str(x))` avoids the binary-float
  artifact that makes naive `round(2.675,2)` return the wrong `2.67`.
- **validate:** tab/newline whitespace, both boundaries (3/20/2/21 post-trim).

This is evidence that the "evidence-required" design lever works: passes come with
captured runtime proof, not assertions.

## Full confusion matrix (rounds 1–3, n=16)

|  | Actually WRONG (8) | Actually CORRECT (8) |
|---|---|---|
| **Flagged DRIFTED** | 8 (true positive) | 0 (false positive) |
| **Passed MATCHES INTENT** | 0 (false negative) | 8 (true negative) |

- **Recall: 8/8 (100%)** — caught every drift.
- **Precision: 8/8 (100%)** — no false alarms.
- **Differential over baseline review: 4/8** — drift only intent-anchoring caught.

## Honest caveats (unchanged and important)

- **Small, hand-crafted, clean fixtures.** Real code is messier; real requests are
  vaguer. A perfect 16/16 here does NOT mean 100% in the field.
- **Single verifier model, non-deterministic.** Re-runs may vary.
- **The wrong-case set was chosen to be omitted-intent**, inflating the
  differential vs a random change mix.
- **What this DOES establish:** the mechanism is sound in both directions (catches
  drift, doesn't cry wolf) on controlled cases — enough to justify packaging and a
  field trial, not enough to advertise a field accuracy number.
