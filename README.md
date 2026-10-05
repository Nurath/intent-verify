# intent-verify

**An independent second-opinion check that an AI-written change did what you *actually asked* — not just what the diff claims, and not just "tests pass."**

`intent-verify` is a Claude Code plugin (a skill, two subagents and a capture
hook) that catches
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
                 ┌────────────────────────────────────────────────┐
   your request  │  1. FREEZE    what you asked, verbatim: the    │
   ───────────▶  │               prompt, later corrections, and   │
                 │               the questions you answered       │
                 └────────────────────────┬───────────────────────┘
                                          ▼
                 ┌────────────────────────────────────────────────┐
                 │  2. CRITERIA  an agent that is given only the  │
                 │               request, and has no tool to read │
                 │               the project, lists what must be  │
                 │               true                             │
                 └────────────────────────┬───────────────────────┘
                                          ▼
                 ┌────────────────────────────────────────────────┐
   agent's diff  │  3. VERIFY    a fresh-context subagent, on a   │
   ───────────▶  │               DIFFERENT model, RUNS the code   │
                 │               against each criterion and keeps │
                 │               the evidence                     │
                 └────────────────────────┬───────────────────────┘
                                          ▼
                 ┌────────────────────────────────────────────────┐
                 │  4. LEDGER    PASS / FAIL / NOT-EXERCISED per  │
                 │               criterion, checked by machine    │
                 │               against the list from step 2:    │
                 │               MATCHES INTENT / DRIFTED /       │
                 │               INCONCLUSIVE                     │
                 └────────────────────────────────────────────────┘
```

### The three design decisions (each defends a specific failure mode)

Each one answers a specific way a reviewer ends up agreeing with the author:

| Lever | Defends against | Why |
|-------|-----------------|-----|
| **Different model** for the verifier | Shared blind spot | A blind spot in the weights survives a fresh context, so a same-model judge can share the author's misreading. This is a design argument: it was on in every benchmark run and never ablated (see [Honest limitations](#honest-limitations)). |
| **Criteria before code** | Confirmation bias | Whoever has seen the code writes criteria the code already satisfies. So the criteria are fixed first, by an agent that is given the request and has no tool to read the project, and the verifier is then held to that list by the validator. |
| **Evidence required for PASS** | Lenient judge | "Looks right" is the exact failure. No criterion passes without captured runtime output. |

Skill: [`skills/intent-verify/SKILL.md`](skills/intent-verify/SKILL.md).
Subagents: [`agents/criteria.md`](agents/criteria.md),
[`agents/verifier.md`](agents/verifier.md). How the parts fit:
[`docs/architecture.md`](docs/architecture.md).

---

## Does it work? — measured, not asserted

Everything below is reproducible from [`benchmark/`](benchmark/): the cases, the
method, and the captured verifier output are all on disk.

The two July results were produced by the single-stage flow, in which the
verifier was *told* to derive criteria before reading the code. The two-stage
flow that 0.3 ships was run on the same controlled set in October; see the end
of this section.

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

### The two-stage flow (0.3) on the controlled set

October 2026: the 16 July fixtures, one run each, Sonnet 5.5 deriving the
criteria (with every tool disabled) and verifying, each call in
`claude -p --safe-mode`.

|  | Actually WRONG (8) | Actually CORRECT (8) |
|---|---|---|
| **Flagged DRIFTED** | 8 ✅ caught | 0 ✅ no false alarm |
| **Passed MATCHES INTENT** | 0 missed | 8 ✅ correct pass |

- **No `INCONCLUSIVE`.** Criteria written without sight of the code asked for
  nothing the correct code could not show.
- **Right for the right reason.** Every planted drift had its own criterion in
  the manifest, quoted from the request, and that criterion is the one that
  failed. No other criterion failed on correct code.
- **One retry in 16.** A verifier paraphrased a manifest criterion; the
  validator rejected the ledger, and the retry copied the text exactly.
- **Cost.** 33 model calls, 1.79M tokens, $1.33 at list price. Deriving the
  criteria cost about 3.6k tokens a case; verifying cost 73k to 222k.
- **Questions on every request.** Stage 1 raised 2 to 4 ambiguities on each of
  the 16 one-line requests, 41 in all. None was about a planted drift and the
  verdicts did not need them, because the harness asks no one. The 0.3.1 skill
  put every one of them to the user before verifying; 0.3.2 does not.

**0.3.2, re-run the same way.** Ambiguities are now recorded only when a
criterion depends on them, and asked only after the verdict, when it rests on
one. On the 16 requests: 3 questions instead of 41, 13 requests with none, none
asked before verifying, verdicts 16 of 16. On the 7 field requests, run
two-stage for the first time: 4 questions, 5 of 7 expected verdicts. One is a
false `DRIFTED` (`recall_weekend`: the criterion expects the code to recognise a
weekend date, the code takes a flag from the caller), a second reading that
nobody recorded and that an up-front question might have caught. The other is
`INCONCLUSIVE` because the fixture has no earlier version to compare against.
[`benchmark/results/2026-10-05-cli-claude-sonnet-5-5-two-stage-ambiguity-fix-2.md`](benchmark/results/2026-10-05-cli-claude-sonnet-5-5-two-stage-ambiguity-fix-2.md).

What this does not show is that two-stage beats single-stage: single-stage was
also 16 of 16 in July, so the set is at its ceiling for both. It shows that 0.3
keeps that result while adding the mechanical coverage check. Report and every
raw reply:
[`benchmark/results/2026-10-05-cli-claude-sonnet-5-5-two-stage.md`](benchmark/results/2026-10-05-cli-claude-sonnet-5-5-two-stage.md).

The same mechanism offline: a simulated verifier that reports only what passes,
and never mentions the criterion that would fail, gets 2 false
`MATCHES INTENT` on the 8 drifted cases when its ledger is validated alone, and
0 when it is held to a manifest. An earlier eight-run first look is in
[`benchmark/results/2026-10-05-two-stage-smoke.md`](benchmark/results/2026-10-05-two-stage-smoke.md).

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
  two subagent passes, one of which executes your code.
- ⚠️ **Its own limit** (failure mode #1): on *genuinely* ambiguous requests there
  is often no single ground truth. The criteria agent lists the places a
  request can be read two ways and the skill asks you about them once; if you
  are not there to answer, it can only check what the words committed to.

---

## Usage

Invoke `intent-verify` after an agent completes a non-trivial change, or say
*"verify this did what I asked."* The skill:

1. **Freezes what you asked.** It lists what was captured for the current
   session — your prompts, and the multiple-choice questions you answered —
   picks the entries that define the work, and writes them to one file. A
   request that was cut at the capture cap, or never captured, is reported
   rather than guessed at. With no ledger it asks you to paste the request.
2. **Gets the criteria fixed.** If you already have acceptance criteria, those
   are used. Otherwise the criteria agent derives them from the request alone;
   each one has to quote the words it rests on, and the quote is checked. Where
   the request can be read two ways, you are asked, once.
3. **Dispatches the verifier** on a different model, with the request, the
   criteria and the code.
4. **Validates the ledger mechanically** — evidence for every PASS, a consistent
   verdict, every criterion from step 2 present — and returns it with a verdict:
   `MATCHES INTENT` / `DRIFTED` / `INCONCLUSIVE` (when the change couldn't
   honestly be exercised, or the request itself was incomplete — never
   laundered into a pass).

Nothing in that procedure writes inside your project.

### Install as a plugin

This repo is its own Claude Code marketplace. From Claude Code:

```
/plugin marketplace add Nurath/intent-verify
/plugin install intent-verify
```

Two hooks then record what you ask for — each prompt (`UserPromptSubmit`) and
each multiple-choice question you answer (`PostToolUse` on `AskUserQuestion`).
The skill runs on request, and the two subagents are bundled. No manual wiring.

To update an existing install from a shell, then restart Claude Code:

```bash
claude plugin marketplace update intent-verify
```

```bash
claude plugin update intent-verify@intent-verify
```

The hooks run via `node` in exec form — the documented cross-platform pattern —
so they behave the same on macOS, Linux, and Windows (no Git Bash required).
They do require `node` on PATH (present for every npm-based Claude Code
install).

### Where your prompts are kept

- **Outside your project.** The hook writes under the plugin's data directory
  (Claude Code's `${CLAUDE_PLUGIN_DATA}`, `~/.claude/plugins/data/<plugin>/`),
  in `projects/<key>/sessions/<session>.jsonl`. Set `INTENT_VERIFY_DATA` to put
  it somewhere else.
- **One file per session.** Several sessions working in the same project no
  longer share a ledger.
- **For 30 days.** A session file nobody has written to for that long is
  deleted (`INTENT_VERIFY_RETENTION_DAYS`; `0` keeps everything). Claude Code
  removes a plugin's data directory when the plugin is uninstalled.
- **In plaintext.** Common credential shapes (GitHub, `sk-` API keys including
  the `sk-proj-`/`sk-ant-api03-` forms, Slack, AWS, private keys) are redacted
  on the way in. Redaction is partial by nature: treat the ledger as sensitive.
- **Capped at 256,000 characters per entry** (`INTENT_VERIFY_MAX_PROMPT`). A
  longer prompt keeps its start and its end and is flagged `truncated`, and the
  skill will not return `MATCHES INTENT` against a request it does not have in
  full. Hook input too large to read at all (over 10 MiB) leaves a
  `capture-incomplete` marker instead of a silent gap.
- **Labelled.** Entries are a `task`, a `verify-invocation` ("verify this did
  what I asked", `/intent-verify`), a `decision` (a question you answered) or
  a `capture-incomplete` marker. Prompts the harness submits by itself — a
  background agent reporting back, a message from another session, a scheduled
  task, a CI event — are marked when the ledger is listed, and background-agent
  reports are left out unless you ask for them.

A ledger that 0.2.x left in `<project>/.intent/` is not touched and is still
read. Delete that directory once its requests no longer matter.

To look at your own ledger, from the plugin's directory:
`node hooks/capture-intent.js --list --project <dir>` and `--show <id>`.

### Without Node

`capture-intent.py`, `capture-intent.ps1` and `capture-intent.sh` are alternates
for wiring a prompt hook by hand, e.g. `{"type": "command", "command":
"python3", "args": ["${CLAUDE_PLUGIN_ROOT}/hooks/capture-intent.py"]}`. They are
as they were in 0.2.1: they write `<project>/.intent/`, which ignores itself in
git, they record prompts only, and the reader still picks their entries up.
They were not moved to the new layout because the reader the skill uses is the
Node script: on a machine without Node the alternates can record a request but
nothing can freeze it, so you would be pasting the request by hand either way.

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
The snapshot is from 2026-08-02 and does not know models released since; the
selector refuses to guess a tier for those unless you pass `--assume-tier`.
Full rationale: [`docs/MODEL-COMPAT.md`](docs/MODEL-COMPAT.md).

## Bounded by design (no verify↔fix loops)

Everything that could loop is capped: re-verification stops after 2 rounds
(the second re-runs every criterion against the same manifest, then the skill
reports the persistent divergence instead of ping-ponging with a
non-deterministic verifier), a malformed manifest or ledger gets exactly one
re-request (then `INCONCLUSIVE`), a question about an ambiguity comes at most
once, after the verdict, and only when the verdict rests on it, the verifier
has an execution budget (attempts per criterion, total commands,
non-interactive, installs nothing) and is read-only — it can never "fix" the
code it is judging. Verifier depth is always exactly one: no verifying the
verifier.

---

## How it compares

| | Anchors on | OSS? | Catches "wrong thing built correctly"? |
|---|---|---|---|
| Ordinary diff review | code + its description | — | ✗ (inherits the omission) |
| Native `verify` skill | **the diff** as ground truth | yes | ✗ structurally (trusts the diff) |
| Spec-first harness, e.g. [Claude Code Harness](https://github.com/Chachamaru127/claude-code-harness) | acceptance criteria you approve before the work | yes | by design, for work planned through it (not evaluated here) |
| Aviator Verify (commercial) | original intent + criteria | **no** (proprietary/hosted) | ✓ |
| **intent-verify** | **the prompt as you typed it** | **yes** | ✓ (on ambiguous requests) |

Fixing acceptance criteria before the work and checking results criterion by
criterion is established practice, and a spec-first harness does it properly:
per its README, Claude Code Harness has you approve the criteria before any
work and reviews separately against them. If you plan through one, its criteria
are better ground truth than anything derived afterwards — hand them to
intent-verify, or use the harness's own review.

intent-verify is for the change that was *not* planned that way: an ordinary
prompt, an agent that went and built something, and the question of whether it
built what the prompt said.

---

## Repository layout

```
.claude-plugin/
  plugin.json                plugin manifest (name, version, hooks)
  marketplace.json           marketplace listing (one-command install)
skills/intent-verify/
  SKILL.md                   the orchestration skill (two stages, bounded rounds, model floors)
agents/
  criteria.md                stage 1: criteria from the request alone (no file or shell tools)
  verifier.md                stage 2: the independent verifier (budget, ledger grammar)
hooks/
  hooks.json                 registers the two capture hooks (node, exec form)
  capture-intent.js          capture + the --list / --show / --freeze reader
  capture-intent.py/.ps1/.sh alternates for manual wiring (0.2 in-project layout)
models/
  registry.json              AA Intelligence Index snapshot -> tiers, floors
tools/
  select_verifier.py         capability-aware verifier selection (policy as code)
  validate_ledger.py         validates ledgers and criterion manifests
docs/
  architecture.md            how the parts fit, contracts, storage, how to release
  handoff_quickstart.md      where to start when picking this repo up
  DESIGN-v0.3.md             the 0.3 proposal, and what was and was not built from it
  MODEL-COMPAT.md            design: surviving weak verifier models
benchmark/
  cases.md / cases.json      every case documented / machine-readable
  oracle.py                  real discriminating executions for the 16 controlled cases
  run_bench.py               runnable harness: --mode mock (orchestration) / cli (real models)
  impl/                      "confidently wrong" + correct fixtures (rounds 1-3)
  field/ field-recall/       rounds 4-5 — real cost.py implementations
  results/                   dated records of every run, with raw replies where kept
logs/                        one file per working day: what was done, what is open
tests/                       hook contract per runtime, validator, manifests, selector,
                             oracle, orchestration, and the plugin's prose and config
.github/workflows/ci.yml     Linux + macOS + Windows (PS 5.1 & 7) CI, shellcheck, mock bench
```

---

## Reproduce

Two runnable paths (plus the original manual one):

```bash
# Orchestration robustness, offline + deterministic: simulated verifier
# profiles (faithful/verbose/sloppy/lazy/omitter/fabricator) against all 16
# controlled cases, evidence backed by real fixture execution.
python3 benchmark/run_bench.py --mode mock
```

```bash
# Real verifier, any model the `claude` CLI can reach (the CLI must be logged in):
python3 benchmark/run_bench.py --mode cli --verifier claude-opus-4-8
```

```bash
# The same, two-stage: criteria first, from the request alone and with every
# tool disabled, then a verifier held to them.
python3 benchmark/run_bench.py --mode cli --verifier claude-opus-4-8 --two-stage
```

cli mode grants the verifier `Bash,Read,Grep,Glob` (it must run the fixtures to
gather evidence) — that means executing the benchmark's deliberately-wrong but
benign code; run it where you'd run any untrusted test suite.

Each writes a dated report under `benchmark/results/`; cli mode also keeps every
raw reply beside it, so a verdict can be audited. A model that times out or
cannot be launched scores that case `INCONCLUSIVE` and the run continues.
Without `--two-stage` the harness hands the verifier the request and the code
in one prompt, so it measures the verifier's skill, not whether criteria were
fixed before the code was seen. Manual reproduction still works: point
[`agents/verifier.md`](agents/verifier.md) at each fixture in
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
- **The two-stage flow is measured once.** 16 cases, one run each, one model for
  both stages, on fixtures where single-stage was already perfect. It matched
  July's result; it has not been shown to beat it.
- **Fewer questions has a price.** 0.3.2 asks nothing before verifying, and a
  question comes afterwards only for a reading the criteria agent recorded. When
  it misses the real second reading, the verdict arrives without one: in the
  field set that was one false `DRIFTED` in 7. The evidence in the ledger shows
  what the code does, so you can still tell, but the tool does not ask.
- **The platform behaviour 0.3 relies on was seen once, on one machine:** the
  criteria agent launching without file access, a `decision` recorded from an
  answered question, and the data directory filled into the skill's commands,
  in the Windows desktop app on Claude Code 2.1.289
  ([record](benchmark/results/2026-10-05-platform-spikes.md)). If a later
  version changes any of them, it fails safe: the skill falls back and says so,
  nothing is recorded, or the reader looks in the usual place.
- **A manifest makes coverage checkable, not complete.** Whether the criteria
  capture everything the request demands is still a model's judgement. The
  report shows the criteria and the parts of the request none of them quotes.
- **Criteria can outrun the code.** Written without sight of the code, a
  criterion may ask for something the changed code has no way to show, and a
  correct change would then come back `INCONCLUSIVE`. In the eight-run first
  look one criterion went unexercised for this reason; the code in that run was
  wrong on other criteria, so the verdict did not turn on it. In the 16-case
  run it did not happen.
- **The ledger is text with program output inside it.** A reply holding any
  verdict other than PASS cannot validate as `MATCHES INTENT`, whatever the
  program printed. A verifier that writes no ledger of its own and quotes one
  printed by the code under test is caught only by the skill reading the reply.
- **The session that wrote the code still handles the evidence.** It saves the
  verifier's reply and runs the validator on it. Nothing detects a ledger that
  was tidied on the way.
- **Prompts are stored in plaintext**, partly redacted: in your home directory
  with the plugin's hook, inside the project with the alternates.
- **Ground-truth limit.** On genuinely ambiguous requests there may be no single
  right answer to check against.
- **Thin moat.** A spec-first harness already covers planned work, and if a
  first-party `verify` starts reading the task prompt the remaining edge
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
- [x] **v0.3.0** — criterion manifest with two-stage dispatch; ledger outside
      the project, one file per session; answered questions recorded
- [x] The three platform checks (October 2026, one machine)
- [x] Measure the two-stage flow on the controlled set: 16 of 16, no
      `INCONCLUSIVE`
- [x] **v0.3.2** — ambiguities recorded only when a criterion depends on them,
      asked only after the verdict: 3 questions on the controlled set instead
      of 41
- [ ] Cross-model ablation, on drift a model produced itself (the controlled
      set's drift is planted, and both arms would likely sit at its ceiling)
- [ ] A structured ledger bound to its run and captured by a hook, so the
      implementing session no longer handles the evidence
      ([design](docs/DESIGN-v0.3.md), Change C). Its two gating checks passed
      in October: [hook spike](benchmark/results/2026-10-05-platform-spikes.md),
      [JSON ledger](benchmark/results/2026-10-05-m4-json-ledger.md)
- [ ] Field recall on real *under-specified* tasks with a known intended answer
- [ ] Registry refresh (the snapshot predates current models)

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

v0.3.0 makes two of the tool's promises mechanical. "Criteria before code" was
an instruction to the verifier; the criteria are now fixed by an agent that
cannot read the project, and a ledger that leaves one out is invalid. "Your
prompts stay out of git" was a self-ignoring directory inside the project; the
ledger is now outside it. The mechanisms are tested, and in its first full run
the two-stage flow reached the expected verdict on all 16 controlled cases.

## License

[MIT](LICENSE).
