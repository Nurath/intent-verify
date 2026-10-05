# intent-verify

**An independent second-opinion check that an AI-written change did what you *actually asked* — not just what the diff claims, and not just "tests pass."**

`intent-verify` is a Claude Code plugin (a skill, a verifier subagent and a
capture hook) that catches
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

Each one answers a specific way a reviewer ends up agreeing with the author:

| Lever | Defends against | Why |
|-------|-----------------|-----|
| **Different model** for the verifier | Shared blind spot | A blind spot in the weights survives a fresh context, so a same-model judge can share the author's misreading. This is a design argument: it was on in every benchmark run and never ablated (see [Honest limitations](#honest-limitations)). |
| **Criteria before code** | Confirmation bias | If the verifier reads the diff first, it reverse-engineers criteria the code already satisfies. Derive criteria from the request *first*. |
| **Evidence required for PASS** | Lenient judge | "Looks right" is the exact failure. No criterion passes without captured runtime output. |

Full skill text: [`skills/intent-verify/SKILL.md`](skills/intent-verify/SKILL.md). Verifier subagent: [`agents/verifier.md`](agents/verifier.md).

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

**What this isolates.** Both arms ran on the same reviewer model (Sonnet,
reviewing Opus-written code) and differed only in what they were given: the
original request, or the code plus its commit message. The differential
therefore measures the *anchor*. It says nothing about the cross-model lever,
which was on in both arms.

### Field trial (n=7, real code, natural tasks)

Substrate: a real module (`dispatch-agent/core/cost.py`), realistic tasks,
implementations produced *naturally* by Opus (×3) and Haiku (×4) with no trap hints.

- **Precision 7/7, zero false positives** on real, messy code — including a weaker
  model's output.
- The verifier **independently rediscovered a prefix-ordering trap** from a
  request's "the full model, NOT the mini" wording, and correctly scoped
  out-of-request gaps as *observations*, not failures.
- **Field recall could not be measured**: all 7 natural implementations came out
  *correct*, so there was no drift to catch.

---

## When to use it (and when not to)

The field trial points one way (seven tasks, so a direction rather than a
finding): **drift shows up where the request leaves room for a wrong reading.**

- ✅ **Use it when the request was ambiguous or under-specified** — when a
  plausible-but-wrong interpretation exists. That's where "confidently wrong"
  happens, and where this tool earns its keep.
- ➖ **On crisp, example-rich specs it had nothing to catch in our trial.** All 7
  natural implementations were already correct and it raised no false alarm.
  Seven tasks cannot show that it never will, and a run is not free: it spends
  a verifier pass that executes your code.
- ⚠️ **Its own limit** (failure mode #1): on *genuinely* ambiguous requests there
  is often no single ground truth, so the verifier — like any reviewer — can only
  check what the words actually committed to. Freezing a vague ask does not
  manufacture intent.

---

## Usage

Invoke `intent-verify` after an agent completes a non-trivial change, or say
*"verify this did what I asked."* The skill:

1. Freezes your original request: it lists the prompts captured for the current
   session, picks the one that started the change, and writes it out verbatim
   (`capture-intent.js --list` / `--freeze`). A request that was cut at the
   capture cap, or never captured, is reported rather than guessed at. With no
   ledger it asks you to paste the request.
2. Derives acceptance criteria from the request.
3. Dispatches the verifier subagent **on a different model**, handing it those
   criteria as a floor; the verifier still derives its own before reading code.
4. Validates the verifier's ledger mechanically (evidence-required PASS,
   consistent verdict, no skipped criterion numbers), checks that every
   criterion from step 2 is in it, then returns it + a verdict: `MATCHES INTENT`
   / `DRIFTED` / `INCONCLUSIVE` (when the change couldn't honestly be exercised,
   or the request itself was incomplete — never laundered into a pass).

### Install as a plugin

This repo is its own Claude Code marketplace. From Claude Code:

```
/plugin marketplace add Nurath/intent-verify
/plugin install intent-verify
```

Then the `UserPromptSubmit` hook auto-captures each request to the intent
ledger, the skill invokes on change-verification, and the verifier runs as a
bundled subagent — no manual wiring.

The capture hook runs via `node` in exec form — the documented cross-platform
pattern — so it behaves the same on macOS, Linux, and Windows (no Git Bash
required). It does require `node` on PATH (present for every npm-based Claude
Code install); without Node, wire one of the alternates in your settings
instead, e.g. `{"type": "command", "command": "python3", "args":
["${CLAUDE_PLUGIN_ROOT}/hooks/capture-intent.py"]}`.

The alternates are not all equal:

- `capture-intent.py` and `capture-intent.ps1` pass the same capture contract as
  the Node script in CI (redaction, caps, tagging, self-ignoring ledger). Two
  differences: only the Node script has the `--list`/`--freeze` reader the skill
  uses, and a prompt too large to read is stored truncated by the `.ps1` but
  recorded as a `capture-incomplete` marker by Node and Python.
- `capture-intent.sh` is a dispatcher: it runs the Node script when `node`
  exists, then Python. With neither it falls back to `jq`, then to a raw
  markdown-only entry. Those two fallbacks are best-effort: a shorter redaction
  list, no session id, and the raw path cannot tag verification requests.

Capture details, all bounded by design:

- Canonical ledger is `.intent/log.jsonl` (one JSON entry per prompt, with
  `id`/`ts`/`kind`/`session_id`), plus a human-readable `log.md` mirror. JSONL
  means prompts containing `---`/`##`/code fences can't corrupt entry
  boundaries.
- Entries are capped at 64k characters (`INTENT_VERIFY_MAX_PROMPT`) and files
  rotate at 1 MiB (`INTENT_VERIFY_MAX_LOG`, 3 archives kept). A capped entry is
  flagged `truncated`, and the skill will not return `MATCHES INTENT` against a
  request it does not have in full.
- **The ledger holds your prompts in plaintext inside the project.** The hook
  writes `.intent/.gitignore` (`*`) so the directory ignores itself in whatever
  repository it lands in, and redacts common credential shapes (GitHub, `sk-`
  API keys including the `sk-proj-`/`sk-ant-api03-` forms, Slack, AWS, private
  keys) before writing. Redaction is partial by nature: treat `.intent/` as
  sensitive.
- Prompts that only *invoke* verification ("verify this did what I asked",
  `/intent-verify`) are tagged `verify-invocation`, so the freeze step skips
  them. A task that merely begins with "verify this …" stays a task.
- Hook input too large to read (over 10 MiB) leaves a `capture-incomplete`
  marker instead of a silent gap.

---

## Model compatibility (varying verifier intelligence)

"Different model for the verifier" spans a ~60-point range on the
[Artificial Analysis Intelligence Index](https://artificialanalysis.ai/evaluations/artificial-analysis-intelligence-index)
— and verifier failure modes change with capability: shallow criteria, then
format drift, then evidence-free verdicts, then fluent fabrication. v0.2 makes
that explicit instead of assuming a frontier verifier:

| Tier | AA index | Verifier role | Protocol |
|---|---|---|---|
| T1 ≥ 50 | Opus 5 · GPT-5.6 Sol · Kimi K3 · Opus 4.8 · Sonnet 5 | preferred | FULL |
| T2 35–49.9 | Gemini 3.1 Pro · DeepSeek V4 Pro · GPT-5.4 mini | bounded diffs | FULL |
| T3 20–34.9 | GPT-5 mini · Gemini 3 Flash · DeepSeek V3.2 | simple changes only | STRUCTURED (≤5 criteria exercised per run, template ledger) |
| T4 < 20 | — | never (fabrication risk is unvalidatable) | excluded by selection |

`tools/select_verifier.py` implements the policy against
`models/registry.json` (pinned snapshot, `as_of` dated): different model
required, different family preferred, floor by change complexity, and a
`weak-verifier` warning when the verifier trails the implementer by >25 points.
Full rationale: [`docs/MODEL-COMPAT.md`](docs/MODEL-COMPAT.md).

## Bounded by design (no verify↔fix loops)

Everything that could loop is capped: re-verification stops after 2 rounds
(the second re-runs every criterion, then the skill reports the persistent
divergence instead of ping-ponging with a non-deterministic verifier), a
malformed ledger gets exactly one re-request
(then `INCONCLUSIVE`), the verifier has an execution budget (attempts per
criterion, total commands, non-interactive, installs nothing) and is read-only
— it can never "fix" the code it is judging. Verifier depth is always exactly
one: no verifying the verifier.

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
.claude-plugin/
  plugin.json                plugin manifest (name, version, hooks)
  marketplace.json           marketplace listing (one-command install)
skills/intent-verify/
  SKILL.md                   the orchestration skill (bounded rounds, model floors)
agents/
  verifier.md                the independent verifier subagent (budget, ledger grammar)
hooks/
  hooks.json                 registers the UserPromptSubmit hook (node, exec form)
  capture-intent.js          canonical capture (redact/cap/rotate) + --list/--freeze reader
  capture-intent.py/.ps1     capture-only alternates for manual wiring
  capture-intent.sh          POSIX dispatcher: node -> python -> jq -> raw
models/
  registry.json              AA Intelligence Index snapshot -> tiers, floors
tools/
  select_verifier.py         capability-aware verifier selection (policy as code)
  validate_ledger.py         mechanical ledger/evidence/verdict validation
docs/
  MODEL-COMPAT.md            design: surviving weak verifier models
benchmark/
  cases.md / cases.json      every case documented / machine-readable
  oracle.py                  real discriminating executions for the 16 controlled cases
  run_bench.py               runnable harness: --mode mock (orchestration) / cli (real models)
  impl/                      "confidently wrong" + correct fixtures (rounds 1-3)
  field/ field-recall/       rounds 4-5 — real cost.py implementations
  results/                   captured runs (2026-07-14 rounds 1-5, + generated)
tests/                       hook contract per runtime, validator, selector, oracle, orchestration
.github/workflows/ci.yml     Linux + macOS + Windows (PS 5.1 & 7) CI, shellcheck, mock bench
```

---

## Reproduce

Two runnable paths (plus the original manual one):

```bash
# Orchestration robustness, offline + deterministic: simulated verifier
# profiles (faithful/verbose/sloppy/lazy/fabricator) against all 16 controlled
# cases, evidence backed by real fixture execution via benchmark/oracle.py.
python3 benchmark/run_bench.py --mode mock

# Real verifier skill, any model the `claude` CLI can reach — e.g. a smaller
# model, to see where capability floors actually bite:
python3 benchmark/run_bench.py --mode cli --verifier claude-opus-4-8
python3 benchmark/run_bench.py --mode cli --verifier claude-haiku-4-5 --suite controlled
```

cli mode grants the verifier `Bash,Read,Grep,Glob` (it must run the fixtures to
gather evidence) — that means executing the benchmark's deliberately-wrong but
benign code; run it where you'd run any untrusted test suite.

Both write a dated report under `benchmark/results/`; cli mode also keeps every
raw verifier reply beside it, so a verdict can be audited. A verifier that
times out or cannot be launched scores that case `INCONCLUSIVE` and the run
continues. Note that this harness hands the verifier the request and the code
in one prompt, so it measures the verifier's skill, not whether criteria were
fixed before the code was seen. Manual reproduction still
works: point [`agents/verifier.md`](agents/verifier.md) at each fixture in
`benchmark/impl/`, supplying the matching original request from
[`benchmark/cases.md`](benchmark/cases.md), running the verifier on a **model
different from whatever wrote the code**. Verifiers are non-deterministic;
expect the omitted-intent cases (sort, search, validate, sorttasks, tiebreak)
to be the discriminators.

---

## Honest limitations

- **Small, hand-crafted controlled fixtures.** 16/16 there does not imply field
  accuracy.
- **Field recall unproven.** Natural drift didn't occur on clear specs; the best
  recall evidence is the controlled omitted-intent set.
- **Non-deterministic.** Re-runs may vary; treat verdicts as strong signal, not proof.
- **The cross-model lever is unmeasured.** Every benchmark run used a verifier
  on a different model from the implementer; none compared that with a
  same-model verifier. The differential above isolates request-anchoring only.
- **Coverage is checked by the orchestrator, not the validator.** The validator
  proves a ledger is internally complete and consistent. It cannot know which
  requirements the request had, so a requirement the verifier never listed is
  caught only by the skill's own criteria. Both are written by a model.
- **The ledger is text with program output inside it.** A reply holding any
  verdict other than PASS cannot validate as `MATCHES INTENT`, whatever the
  program printed. A verifier that writes no ledger of its own and quotes one
  printed by the code under test is caught only by the skill reading the reply.
- **One prompt is one request.** A task refined over several messages is
  verified against the single entry that was frozen; say which one you mean.
- **Prompts are stored in your project**, in plaintext, partly redacted.
- **Ground-truth limit.** On genuinely ambiguous requests there may be no single
  right answer to check against.
- **Thin moat.** If a first-party `verify` starts reading the task prompt, the edge
  narrows. Acceptable for an OSS "help now" tool — stated openly.

---

## Roadmap

- [x] **v1** — skill + verifier subagent + intent ledger (this repo)
- [x] Controlled benchmark (recall, precision, differential)
- [x] Field trial (precision on real code)
- [x] **v2 plugin** — `plugin.json` + `marketplace.json` + `UserPromptSubmit`
      hook (auto-capture intent) + one-command install
- [x] **v0.2 hardening** — cross-platform capture (node exec form; stock
      Windows works), bounded ledger (JSONL, caps, rotation, redaction),
      bounded verification (rounds, retries, verifier budget, read-only)
- [x] **Capability-aware dispatch** — AA-index tiers/floors, STRUCTURED mode
      for smaller models, machine-validated ledger + `INCONCLUSIVE`
- [x] **Runnable benchmark + CI** — `run_bench.py` mock/cli modes, execution
      oracle, Linux + macOS + Windows workflows
- [x] **v0.2.1** — closes the false-pass paths in the ledger validator and the
      capture gaps found by an independent review (see [CHANGELOG](CHANGELOG.md))
- [ ] **Criterion manifest** — criteria fixed before the verifier sees code and
      enforced by the validator, instead of checked in prose
- [ ] **Ledger outside the project tree**, and a structured ledger bound to the
      run that produced it
- [ ] Cross-model ablation (same-model vs cross-model verifier, controlled set)
- [ ] Field recall on real *under-specified* tasks with a known intended answer
- [ ] Registry refresh automation (pull the AA snapshot instead of hand-pinning)

## Status

v1 prototype. Controlled benchmark n=16 (recall 8/8, precision 8/8, differential
4/8). Field trial n=7 (Opus + Haiku, real code): precision 7/7, 0 false positives;
field recall unmeasurable on clear specs. Refined thesis: the value is on
ambiguous / under-specified requests.

v0.2 hardens the prototype for real environments: capture works on stock
Windows/macOS/Linux, every loop surface is bounded, verifier dispatch is
capability-aware (AA-index tiers), the ledger contract is machine-validated
with an honest `INCONCLUSIVE`, and the benchmark is runnable
(`benchmark/run_bench.py`) with CI.

v0.2.1 is a correctness release. An independent review of 0.2.0 found ledgers
that validated as `MATCHES INTENT` when they should not have, requests verified
after being cut at capture, and a ledger directory that was not ignored in the
projects it was written to. Each finding was reproduced, fixed, and kept as a
regression test.

## License

[MIT](LICENSE).
