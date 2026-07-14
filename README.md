# intent-verify

**An independent second-opinion check that an AI-written change did what you *actually asked* — not just what the diff claims, and not just "tests pass."**

`intent-verify` is a Claude Code skill (packageable as a plugin) that catches
**intent drift**: the failure where an AI coding agent confidently builds the
*wrong thing correctly*. The code runs, tests go green, the diff reads fine — but
it isn't what you asked for, and ordinary review can't see the gap because it
checks the code against the code's *own* description.

---

## The problem, in one example

> **You ask:** "Return the posts sorted by date, **newest first**."
> **The agent writes:** `sorted(posts, key=lambda p: p["date"])` — and commits it as *"sort posts by date."*
> **A normal reviewer** reads "sort posts by date," sees code that sorts posts by date, and says **LGTM.**
> It ships oldest-first. Users notice. You don't, until they do.

The bug isn't in the code — the code is clean and correct *against its own
description*. The bug is that the description silently dropped "newest first."
Diff-anchored review inherits that omission. Only something holding your **original
request** can catch it.

That's the entire job of this tool.

---

## How it works

```
                 ┌──────────────────────────────────────────────┐
   your request  │  1. FREEZE  the original request verbatim     │
   ───────────▶  │            (a UserPromptSubmit hook, or       │
                 │             a pasted intent ledger)           │
                 └──────────────────────┬───────────────────────┘
                                        ▼
                 ┌──────────────────────────────────────────────┐
   agent's diff  │  2. VERIFY  a fresh-context subagent, on a    │
   ───────────▶  │            DIFFERENT model, derives criteria  │
                 │            from the request BEFORE reading the │
                 │            code, then RUNS the app to exercise │
                 │            each one, capturing evidence.       │
                 └──────────────────────┬───────────────────────┘
                                        ▼
                 ┌──────────────────────────────────────────────┐
                 │  3. LEDGER  per-criterion PASS / FAIL /       │
                 │            NOT-EXERCISED (+ evidence), and     │
                 │            a verdict: MATCHES INTENT / DRIFTED │
                 └──────────────────────────────────────────────┘
```

### The three design decisions (each defends a specific failure mode)

These are load-bearing, not stylistic — remove any one and the check collapses
into the blind spot it exists to catch:

| Lever | Defends against | Why |
|-------|-----------------|-----|
| **Different model** for the verifier | Shared blind spot | Same-model judging correlates with the author — the blind spot lives in the weights, not just the transcript. Cross-model is the single most important lever. |
| **Criteria before code** | Confirmation bias | If the verifier reads the diff first, it reverse-engineers criteria the code already satisfies. Derive criteria from the request *first*. |
| **Evidence required for PASS** | Lenient judge | "Looks right" is the exact failure. No criterion passes without captured runtime output. |

Full skill text: [`SKILL.md`](SKILL.md). Verifier subagent: [`agents/verifier.md`](agents/verifier.md).

---

## Does it work? — measured, not asserted

Everything below is reproducible from [`benchmark/`](benchmark/): the cases, the
method, and the captured verifier output are all on disk.

### Controlled benchmark (n=16, cross-model, evidence-required)

**Confusion matrix**

|  | Actually WRONG (8) | Actually CORRECT (8) |
|---|---|---|
| **Flagged DRIFTED** | 8 ✅ caught | 0 ✅ no false alarm |
| **Passed MATCHES INTENT** | 0 missed | 8 ✅ correct pass |

- **Recall 8/8** — caught every drift, including subtle omitted-intent ones.
- **Precision 8/8** — zero false positives; correct code passed with rigorous
  runtime evidence (not rubber-stamped).
- **Differential 4/8** — drift caught *only* by intent-anchoring, that ordinary
  diff-anchored review **missed**: newest-first sort, case-insensitive search,
  trim-first validation, tiebreak-by-due-date. All are requirements you **cannot
  infer** from code + commit message + convention. That is the seam this tool
  occupies. (The other 4, review also caught — because they were blatant in the
  code or flagged by domain convention.)

### Field trial (n=7, real code, natural tasks)

Substrate: a real module (`dispatch-agent/core/cost.py`), realistic tasks,
implementations produced *naturally* by Opus (×3) and Haiku (×4) with no trap hints.

- **Precision 7/7, zero false positives** on real, messy code — including a weaker
  model's output.
- The verifier **independently rediscovered a prefix-ordering trap** from a
  request's "the full model, NOT the mini" wording, and correctly scoped
  out-of-request gaps as *observations*, not failures.
- **Field recall could not be measured**: all 7 natural implementations came out
  *correct* — natural drift barely occurs on well-specified tasks, even for a
  weaker model.

---

## When to use it (and when not to)

The field trial taught us something sharper than a number: **drift lives in
ambiguity, not in clear specs.**

- ✅ **Use it when the request was ambiguous or under-specified** — when a
  plausible-but-wrong interpretation exists. That's where "confidently wrong"
  happens, and where this tool earns its keep.
- ➖ **On crisp, example-rich specs it's a safe near-no-op** — capable models
  rarely drift there (7/7 correct in the field), and the tool won't false-alarm
  (0 FPs), so running it always is harmless. It just won't fire much.
- ⚠️ **Its own limit** (failure mode #1): on *genuinely* ambiguous requests there
  is often no single ground truth, so the verifier — like any reviewer — can only
  check what the words actually committed to. Freezing a vague ask does not
  manufacture intent.

---

## Usage

As a skill (v1): invoke `intent-verify` after an agent completes a non-trivial
change, or say *"verify this did what I asked."* The skill:

1. Reads your frozen original request (from a `UserPromptSubmit` hook ledger, or
   asks you to paste it).
2. Derives acceptance criteria from the request.
3. Dispatches the verifier subagent **on a different model**.
4. Returns a per-criterion ledger + `MATCHES INTENT` / `DRIFTED` verdict.

Packaged as a plugin (v2, planned): a `UserPromptSubmit` hook captures intent
automatically, and one `plugin.json` install wires up the skill + verifier +
hook. See [Roadmap](#roadmap).

---

## How it compares

| | Anchors on | OSS? | Catches "wrong thing built correctly"? |
|---|---|---|---|
| Ordinary diff review | code + its description | — | ✗ (inherits the omission) |
| Native `verify` skill | **the diff** as ground truth | yes | ✗ structurally (trusts the diff) |
| Aviator Verify (commercial) | original intent + criteria | **no** (proprietary/hosted) | ✓ |
| **intent-verify** | **the original request** | **yes** | ✓ (on ambiguous requests) |

The concept is validated to the point of having a funded commercial product
(Aviator). The open-source, local, request-anchored slice is what this fills.

---

## Repository layout

```
SKILL.md                     the orchestration skill (v1)
agents/verifier.md           the independent verifier subagent prompt
benchmark/
  cases.md                   every case documented (request, drift, expected verdict)
  impl/                      "confidently wrong" fixtures
    median.py ratelimit.py sortposts.py          (round 1)
    omitted-intent/          5 description-truthful-but-omits-requirement cases (round 2)
    correct/                 8 correct implementations for the precision test (round 3)
  field/                     round 4 — real cost.py, Opus implementations
  field-recall/              round 5 — real cost.py, Haiku implementations
  results/
    2026-07-14.md                          round 1 — mechanism validation
    2026-07-14-round2-omitted-intent.md    round 2 — the differential edge
    2026-07-14-round3-precision.md         round 3 — false-positive test (n=16 matrix)
    2026-07-14-round4-field-trial.md       round 4 — field precision (real code)
    2026-07-14-round5-field-recall.md      round 5 — field-recall attempt + thesis
```

---

## Reproduce

Point [`agents/verifier.md`](agents/verifier.md) at each fixture in `benchmark/impl/`,
supplying the matching original request from [`benchmark/cases.md`](benchmark/cases.md),
running the verifier on a **model different from whatever wrote the code**. Compare
to a baseline reviewer given only the code + commit message. Verifiers are
non-deterministic; expect the omitted-intent cases (sort, search, validate,
sorttasks, tiebreak) to be the discriminators.

---

## Honest limitations

- **Small, hand-crafted controlled fixtures.** 16/16 there does not imply field
  accuracy.
- **Field recall unproven.** Natural drift didn't occur on clear specs; the best
  recall evidence is the controlled omitted-intent set.
- **Non-deterministic.** Re-runs may vary; treat verdicts as strong signal, not proof.
- **Ground-truth limit.** On genuinely ambiguous requests there may be no single
  right answer to check against.
- **Thin moat.** If a first-party `verify` starts reading the task prompt, the edge
  narrows. Acceptable for an OSS "help now" tool — stated openly.

---

## Roadmap

- [x] **v1** — skill + verifier subagent + intent ledger (this repo)
- [x] Controlled benchmark (recall, precision, differential)
- [x] Field trial (precision on real code)
- [ ] **v2 plugin** — `plugin.json` + `marketplace.json` + `UserPromptSubmit`
      hook (auto-capture intent) + one-command install
- [ ] Field recall on real *under-specified* tasks with a known intended answer

## Status

v1 prototype. Controlled benchmark n=16 (recall 8/8, precision 8/8, differential
4/8). Field trial n=7 (Opus + Haiku, real code): precision 7/7, 0 false positives;
field recall unmeasurable on clear specs. Refined thesis: the value is on
ambiguous / under-specified requests.

## License

[MIT](LICENSE).
