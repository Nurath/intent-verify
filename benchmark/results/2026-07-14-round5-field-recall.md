# Benchmark run 5 — 2026-07-14 — field-recall attempt (weaker implementer)

## Purpose

Round 4 measured field precision but not field recall (no natural drift occurred).
This round tried to *induce* natural drift: a **weaker implementer (Haiku 4.5)** on
**4 trickier tasks** against the real `cost.py`, expecting some to drift so the
verifier could be tested on catching real, unplanted drift.

## Setup

- Substrate: same real `dispatch-agent/core/cost.py`. Fixtures: [`../field-recall/`](../field-recall/).
- Implementer: **Haiku 4.5** (weaker → drift-prone), tasks given plainly, no trap hints.
- 4 tasks: add `gpt-4o-mini` model; add `platform_fee_pct` (fee = % of total, new
  line item); add `weekend_surcharge` (telephony ×1.5 only); add `sum_costs()`
  aggregator (sum 5 fields, round, empty→zeros).
- Ground truth established independently by running each. Verifier: Sonnet, blind.

## Result — no drift induced

| Task | Ground truth | Blind verifier | Correct? |
|------|-------------|----------------|----------|
| gpt-4o-mini | CORRECT (0.75; plain gpt-4o still 2.50) | MATCHES INTENT | ✅ |
| platform_fee_pct | CORRECT (0.125 fee, total 2.625) | MATCHES INTENT | ✅ |
| weekend_surcharge | CORRECT (telephony 0.018→0.027) | MATCHES INTENT | ✅ |
| sum_costs | CORRECT (sums, rounds, empty→zeros) | MATCHES INTENT | ✅ |

**Haiku produced 4/4 correct implementations. Verifier: 4/4 correct verdicts, 0
false positives on weaker-model output.**

## The honest finding

We tried to force natural drift — weaker model, trickier tasks — and **still got
4/4 correct.** Across both field rounds (Opus 3 + Haiku 4) that is **7/7 correct
natural implementations** on real code, and **7/7 correct verifier verdicts, 0
false positives** across two model tiers.

**Field recall on natural drift could not be measured — because natural drift
barely happens on well-specified tasks with examples, even for a weaker model,
against clean well-documented code.**

## What this actually tells us (sharper than a number)

- **Drift lives in ambiguity, not in clear specs.** When the request is specific
  and gives examples, capable models — even Haiku — implement it correctly. The
  "confidently wrong" failure the tool targets arises from **under-specified /
  omitted-intent** requests, which is exactly what the controlled benchmark
  deliberately constructed and measured (recall 8/8 on omitted-intent).
- **So the recall payoff is conditional on request ambiguity.** intent-verify
  earns its keep when the ask is vague and a plausible-but-wrong reading exists —
  not on crisp specs where models rarely drift.
- **On crisp specs it's cheap and harmless:** it reliably passes correct work
  (7/7 field precision, 0 false alarms), so running it always is safe; it just
  won't fire much when the spec is clear.
- **The unmeasurable half is a real limit** (failure mode #1): on genuinely
  ambiguous requests, drift is likelier *but there's often no single ground truth*
  to score against — so both "did the model drift?" and "did the verifier catch
  it?" become judgment calls. Honest field recall would need real
  under-specified tasks with a known intended answer.

## Bottom line

- **Field precision: 7/7 (Opus + Haiku), 0 false positives.** Strong.
- **Field recall: unmeasured** — natural drift not inducible on clear specs; best
  recall evidence remains the controlled omitted-intent benchmark (8/8).
- **Refined product thesis:** *use intent-verify when the request was ambiguous or
  under-specified.* On clear specs it's a safe no-op; on vague ones it's where the
  value is — and also where its own ground-truth limit bites.
