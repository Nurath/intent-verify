# Benchmark run 4 — 2026-07-14 — field trial (real code, natural tasks)

## Purpose

Rounds 1–3 used hand-crafted fixtures. This round removes that bias: a **real,
runnable module** as substrate, **realistic tasks**, and **natural** (unplanted)
implementation outcomes — to see if the tool holds on messy real code.

## Setup

- **Substrate:** `dispatch-agent/core/cost.py` (175 lines, real per-call cost
  logic, stdlib-only, runnable). Copied to sandboxes — production untouched.
  Field fixtures: [`../field/`](../field/).
- **3 realistic tasks**, each with natural drift potential (not planted):
  1. Add `gpt-5.4` (full) model rates. *Trap:* prefix ordering vs `gpt-5.4-mini`.
  2. Add `discount_pct` param — discount LLM cost only.
  3. Telephony bills per whole minute, rounding partial minutes up.
- **Implementer:** Opus 4.8, given each task plainly (no hint of traps).
- **Ground truth:** established independently by running each result before verifying.
- **Verifier:** Sonnet (cross-model), blind, evidence required.

## Result

| Task | Ground truth | Blind verifier | Verdict correct? |
|------|-------------|----------------|------------------|
| gpt-5.4 model | CORRECT (7.25 full; mini still 5.25) | MATCHES INTENT | ✅ |
| discount_pct | CORRECT (llm-only, total reflects) | MATCHES INTENT | ✅ |
| telephony ceil | CORRECT (`math.ceil`, 61s→2min) | MATCHES INTENT | ✅ |

**3/3 correct verdicts. 0 false positives on real code.**

## Quality signals

- **Task 1 verifier independently rediscovered the trap.** From the request's
  emphasis "the full model, NOT the mini," it derived a criterion and tested that
  `gpt-5.4-mini` still routes to mini rates (5.25, not 7.25) — confirming the
  prefix ordering. It was never told about the trap. This is intent-anchoring
  working on real code: the *request wording* drove a test the code alone wouldn't.
- **Correct scoping.** Task-1 and task-3 verifiers flagged real incompleteness
  (`rates_from_settings()` not wired for gpt-5.4; 0-second edge bills $0) as
  **observations, not failures** — because the request didn't ask for them. It did
  not cry wolf on out-of-scope gaps. Good precision calibration on messy code.

## What this round measured — and did NOT

- **Measured: field precision.** On real, messy, correct implementations, the
  verifier passed 3/3 with runtime evidence and zero false alarms. This was the
  biggest real-world risk (false positives on real code) — and it held.
- **NOT measured: field recall on natural drift.** All 3 natural implementations
  were correct (a strong implementer didn't drift), so there was no natural drift
  to catch. Field recall remains unproven.

## Next to close the gap

To measure field recall honestly, natural drift must occur. Options: a weaker/
faster implementer model, more or harder tasks (until some drift), or a larger
sample. Until then, the honest claim is: **field precision demonstrated (3/3 real
correct impls passed); field recall on natural drift still open.**
