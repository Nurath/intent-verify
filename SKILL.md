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

## Procedure

1. **Freeze intent.** Take the user's original request verbatim (from the
   `UserPromptSubmit` hook ledger if present, else ask the user to paste it).
   Write it to `.intent/<task>.md`. This is ground truth — trust it over the
   diff, comments, or commit message.
2. **Derive criteria (before showing the diff).** List the concrete, observable
   things that must be true for the request to be satisfied. Numbered.
3. **Dispatch the verifier subagent** (`agents/verifier.md`) **on a different
   model**, handing it only `{frozen request, criteria, the code/app}` — NOT the
   implementer's reasoning.
4. **The verifier exercises each criterion** by running the code to the surface
   where the change executes, and records: `PASS` (with evidence) / `FAIL` (with
   evidence) / `NOT-EXERCISED` (with reason it couldn't reach it).
5. **Report the ledger** + a one-line verdict: `MATCHES INTENT` or
   `DRIFTED — criteria N, M failed`.

## When NOT to use

- Trivial changes with no runtime surface (docs, comments, formatting).
- When the original request is too vague to yield observable criteria — say so;
  freezing an ambiguous ask does not create ground truth (known limitation).

## Honest limits

- If the app can't be built/run in the environment, the verifier returns
  `NOT-EXERCISED`, not a guess. Runtime-reachability is the hard inherited part.
- A specific, pinned-down request is where this earns its keep. Vague asks
  degrade its value — it can only check what the words actually committed to.
