---
name: intent-verify
description: >
  Independent second-opinion check that an AI-written change did what the USER
  ORIGINALLY ASKED — not just "tests pass" and not what the diff claims. Freezes
  the original request, then dispatches a fresh-context verifier (ideally a
  different model) that exercises the running code per acceptance-criterion and
  requires captured evidence. Catches "confidently built the wrong thing" /
  intent drift that diff-anchored review misses. Use after an agent completes a
  non-trivial change, before commit, or when the user says "verify this did what
  I asked", "intent-verify", "did it actually do what I wanted".
argument-hint: "[path-to-intent-ledger]"
license: MIT
---

# intent-verify

A change can pass tests, typecheck, and a diff review and still be **the wrong
thing built correctly.** Diff-anchored review inherits the implementer's
misunderstanding: it reads the code plus the code's own description, so a mean
labelled "central value" reads fine. This skill checks the change against the
**user's original words**, with fresh eyes.

## The three design decisions (each survives a specific failure mode)

These are not stylistic — remove any one and the check collapses into the same
blind spot it exists to catch. Grilled against the failure modes:

1. **Different model for the verifier.** Same-model judging correlates with the
   author — the blind spot lives in the weights, not just the transcript. The
   verifier MUST run on a different model than the implementer. This is the
   single most important lever; without it "fresh context" is cosmetic.
2. **Criteria before code.** The verifier derives acceptance criteria from the
   frozen request *before* it reads the implementation — otherwise it
   reverse-engineers criteria the code already satisfies (confirmation bias).
3. **Evidence required for every PASS.** No criterion is PASS without captured
   runtime evidence (the command run + its actual output). "Looks right" is the
   exact failure we're catching; a judge that rationalizes is worthless.

"Different model" alone is not enough: a verifier far below the implementer's
capability fails in its own ways (skipped steps, fabricated evidence, broken
ledger format). Capability-aware dispatch below closes that gap.

## Procedure

1. **Freeze intent.** Take the user's original request verbatim and write it to
   `.intent/<task>.md`. This is ground truth — trust it over the diff, comments,
   or the commit message.
   - Preferred source: the hook ledger `.intent/log.jsonl` (one JSON entry per
     prompt, each with an `id`, `ts`, and `kind`). **Selection rule:** pick the
     most recent entry with `kind: "task"` that initiated the change under
     verification. Entries with `kind: "verify-invocation"` ("verify this did
     what I asked", `/intent-verify`, …) are *never* the frozen request — they
     are requests to run this skill. If several task entries plausibly define
     the work, show the candidates (id + first line) and ask the user to pick.
     Read only what you need (last ~20 entries), not the whole ledger.
   - No ledger? Ask the user to paste the original request. Do not reconstruct
     it from memory or from the diff — that reintroduces the blind spot.
2. **Derive criteria (before showing the diff).** List the concrete, observable
   things that must be true for the request to be satisfied. Numbered.
3. **Select the verifier model** (capability-aware — see the table below):
   different model than the implementer, at or above the capability floor for
   the change, preferably a different vendor family. Record the choice. If only
   below-floor models are available, say so and fall back to same-model
   fresh-context verification with a stated caveat — a capable same-model check
   beats an incapable cross-model one, but note that the cross-model lever was
   lost. `tools/select_verifier.py` automates this against
   `models/registry.json`.
4. **Dispatch the verifier subagent** (`agents/verifier.md`) **on the selected
   model**, handing it only `{frozen request, criteria, the code/app, mode}` —
   NOT the implementer's reasoning. Set `mode: FULL` for tier T1/T2 verifiers,
   `mode: STRUCTURED` for T3 (simpler protocol, ≤5 criteria, fill-in template).
5. **The verifier exercises each criterion** by running the code to the surface
   where the change executes, and records: `PASS` (with evidence) / `FAIL` (with
   evidence) / `NOT-EXERCISED` (with reason it couldn't reach it). It works
   read-only and within a bounded execution budget (see `agents/verifier.md`).
6. **Validate the ledger before trusting it.** The verifier's output must match
   the ledger format in `agents/verifier.md` (`python3 tools/validate_ledger.py
   <file>` checks it mechanically). If it is malformed, or contains a PASS
   without both command and output evidence, re-request the ledger **once** with
   the specific defect named. If it is still invalid, report `INCONCLUSIVE` —
   never launder an unverifiable answer into MATCHES INTENT, and never loop
   re-asking.
7. **Report the ledger** + a one-line verdict: `MATCHES INTENT`, or
   `DRIFTED — criteria N, M failed`, or `INCONCLUSIVE — <reason>` (verifier
   could not produce a valid evidence-backed ledger, or too little of the
   change was exercisable).

## Verification rounds are bounded (no verify↔fix loops)

Re-verification after a fix is normal — once. Track the round count in
`.intent/<task>.md` (`round: N`).

- **Round 1:** full procedure above.
- **Round 2** (after a fix): verify only the previously-failed criteria, plus a
  quick regression glance at the rest.
- **After round 2, stop.** If criteria still fail, do NOT fix-and-re-verify
  again. Report the persistent divergence (criterion, what the request says,
  what the code does, evidence) and hand the decision to the user. A
  criterion that keeps failing across two rounds usually means the request is
  ambiguous or the criterion is wrong — more loops burn tokens without adding
  signal, and verifiers are non-deterministic enough that a flaky criterion can
  ping-pong forever.
- Never invoke intent-verify on its own verification output, and never dispatch
  a verifier from inside a verifier. Depth is always exactly one.

## Model compatibility (capability-aware dispatch)

Verifier quality degrades in *specific* ways as models get weaker — this skill
degrades the protocol instead of silently degrading the verdict. Tiers follow
the Artificial Analysis Intelligence Index snapshot in `models/registry.json`
(see `docs/MODEL-COMPAT.md` for the full rationale):

| Tier | AA intelligence | Verifier role | Protocol |
|------|-----------------|---------------|----------|
| T1 | ≥ 50 (e.g. Opus 5, GPT-5.6 Sol, Kimi K3, Opus 4.8, Sonnet 5) | Preferred | FULL |
| T2 | 35–49.9 (e.g. Gemini 3.1 Pro, DeepSeek V4 Pro, GPT-5.4 mini) | Fine for single-file / small-diff changes | FULL |
| T3 | 20–34.9 (e.g. GPT-5 mini, Gemini 3 Flash, DeepSeek V3.2) | Simple, single-behavior changes only | STRUCTURED |
| T4 | < 20 | Never use as verifier | — |

Floors: simple single-behavior change → T3+; typical change → T2+; multi-file
or subtle-semantics change → T1 preferred. Also keep the *gap* bounded: a
verifier more than ~25 points below the implementer gets a
`weak-verifier` warning attached to the report, because it will miss what the
implementer missed and more.

## When NOT to use

- Trivial changes with no runtime surface (docs, comments, formatting).
- When the original request is too vague to yield observable criteria — say so;
  freezing an ambiguous ask does not create ground truth (known limitation).

## Safety

The verifier **executes the change under test**. That code is exactly as
trusted as its author. Run verification in the same sandbox/permission scope
you'd use for the implementer, never with elevated permissions, and prefer an
environment where network egress is restricted. The verifier itself is
instructed to be read-only, non-interactive, and to install nothing.

## Honest limits

- If the app can't be built/run in the environment, the verifier returns
  `NOT-EXERCISED`, not a guess. Runtime-reachability is the hard inherited part.
- A specific, pinned-down request is where this earns its keep. Vague asks
  degrade its value — it can only check what the words actually committed to.
- Evidence can in principle be fabricated by a bad verifier. The ledger
  validator catches missing/malformed evidence, not forged output — which is
  why below-floor models are excluded rather than "checked harder."
