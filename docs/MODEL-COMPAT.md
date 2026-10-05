# Model compatibility: making cross-model verification survive weak verifiers

`intent-verify` asks for **a different model for the verifier** (see SKILL.md;
that lever is a design argument and has not been ablated in the benchmark). But
"different" spans a huge capability range — on the
[Artificial Analysis Intelligence Index](https://artificialanalysis.ai/evaluations/artificial-analysis-intelligence-index)
the gap between the strongest and weakest listed models is ~60 points. A
verifier that is *different but far weaker* does not give you an independent
second opinion; it gives you a new, worse set of failure modes. This document
is the design for handling that — how the tool stays compatible with a wide
range of models with varying intelligence, instead of silently assuming a
frontier verifier.

## How verification degrades as verifier capability drops

Observed/expected failure modes, in the order they appear as models get weaker:

| Capability drop | What breaks first | Consequence if unhandled |
|---|---|---|
| mild | Criteria get shallow (restate the request instead of decomposing it) | subtle drift (tiebreaks, direction, case rules) slips through |
| moderate | Procedure order violated — reads the code before deriving criteria | confirmation bias returns; criteria mirror the code |
| moderate | Output format drifts (prose instead of ledger) | orchestrator can't parse → verdict lost or mis-read |
| severe | Evidence discipline collapses: PASS with no run, or "evidence" paraphrased from reading the code | the lenient-judge failure the tool exists to prevent |
| severe | Fabricated command output (fluent, plausible, never executed) | worse than no verification: false confidence with a paper trail |
| any | Budget blindness: retries a broken build forever, boots servers, waits on interactive input | verification hangs — the practical "infinite loop" in this pipeline |

Three code-level mechanisms + one policy mechanism absorb these:

1. **Protocol adaptation (`mode: STRUCTURED`)** — for T3 verifiers the skill
   dispatches a simplified protocol: at most 5 criteria exercised per run, one
   decisive execution per criterion, fill-in ledger template, no prose. Every
   requirement is still listed; those beyond the budget are `NOT-EXERCISED`,
   which makes the run `INCONCLUSIVE` and tells the orchestrator to send
   another batch. Weak models follow templates far more reliably than open
   procedures.
2. **Mechanical ledger validation** (`tools/validate_ledger.py`) — the
   orchestrator validates structure (numbering without gaps, one verdict per
   criterion, values on their own line) + evidence presence + verdict
   consistency. One bounded re-request on defects, then `INCONCLUSIVE`. Never
   loops, never launders an unverifiable answer into `MATCHES INTENT`.
3. **Execution budget** (`agents/verifier.md`) — ≤3 attempts per criterion,
   ~15 commands total, non-interactive, nothing installed, timeouts on anything
   that can block. Budget exhaustion → `NOT-EXERCISED`, honestly.
4. **Selection floors** (`models/registry.json` + `tools/select_verifier.py`) —
   below-floor models are excluded *by policy*, because fabricated evidence
   (T4's signature failure) cannot be caught by output validation.

## Tiers

Derived from the AA Intelligence Index snapshot in `models/registry.json`
(`as_of: 2026-08-02` — scores drift, refresh the snapshot):

| Tier | Index | Example models (score) | Verifier role |
|---|---|---|---|
| T1 | ≥ 50 | Claude Opus 5 (60.7), GPT-5.6 Sol (58.9), Kimi K3 (57.1), Claude Opus 4.8 (55.7), Claude Sonnet 5 (53.4), GPT-5.4 (51.4) | Preferred. FULL protocol. |
| T2 | 35–49.9 | Gemini 3.1 Pro (46.5), DeepSeek V4 Pro (44.3), GPT-5.4 mini (40.0), Claude Sonnet 4.6 (35.9) | Fine for single-file / bounded diffs. FULL protocol. |
| T3 | 20–34.9 | Gemini 3 Flash (27.4), GPT-5 mini (25.3), DeepSeek V3.2 (24.7) | Simple single-behavior changes only. STRUCTURED protocol. |
| T4 | < 20 | GPT-5 nano (19.9), Llama 4 Maverick (14.3), GPT-4o mini (6.9) | Never. Excluded by selection. |

Floors by change complexity: `simple → T3+`, `standard → T2+`,
`complex → T1 preferred`. Plus a **gap cap**: a verifier more than 25 index
points below the implementer triggers a `weak-verifier` warning on the report —
it will tend to miss whatever the implementer missed, and more.

Why exclusion instead of harder validation for T4: `validate_ledger.py` can
prove evidence is *present and well-formed*, not that it is *real*. A model
that fabricates output produces valid-looking ledgers. The only sound defense
is not asking it to verify.

## Fallback order when the ideal verifier isn't available

1. Different family, at/above floor (the design case).
2. Same family, different model, at/above floor — cross-model lever weakened;
   note it in the report.
3. Same model, fresh context — cross-model lever lost; say so explicitly. A
   capable same-model check still beats an incapable cross-model one.
4. No capable model at all → don't verify; tell the user verification was
   skipped rather than emitting a low-trust verdict.

## Keeping the snapshot honest

`models/registry.json` pins `as_of`. When the index shifts (new releases,
score updates), update the snapshot in one commit — don't hand-edit individual
scores over time, or the tiers stop being comparable. Models not in the
snapshot: either add them with a score from the source, or pass
`--assume-tier` explicitly. `select_verifier.py` deliberately refuses to guess.

## Measuring this (instead of asserting it)

`benchmark/run_bench.py --mode mock` simulates the tier failure modes above
(faithful / verbose / sloppy-format / lazy-no-evidence / fabricator) against
the 16 controlled cases and scores what the *orchestration layer* does with
each — parse tolerance, bounded retry, INCONCLUSIVE instead of false MATCHES,
floor exclusion. `--mode cli` runs the same cases through real models via the
`claude` CLI (e.g. verifier on Opus 4.8 or Haiku) for actual verifier-skill
measurement. See the Reproduce section of the top-level README.
