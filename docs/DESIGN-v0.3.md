# intent-verify v0.3 — design proposal

**Status:** Changes A and B and the smaller fixes were built in 0.3.0. Change C
was not. The proposal below is kept as it was reviewed; this box records what
came of it.
**Baseline:** v0.2.1 (PR #2). **Written:** 2026-10-05.

## What was built from this, and where it departs

| Part | 0.3.0 |
|---|---|
| **A** criterion manifest, two-stage dispatch | Built: `agents/criteria.md`, `validate_ledger.py --check-manifest / --manifest / --manifest-from`, the skill's stage 1 and ambiguity question, `run_bench.py --two-stage`, the `omitter` mock profile. |
| **B** ledger outside the project | Built for the plugin's hook: per-session files under the data directory, retention, legacy `.intent/` read as a fallback, `--show`. |
| **C** verdict path without the implementer | Not built. C1 still needs spikes S2 and S3 and measurements M3 and M4. |
| Smaller fixes | 1 to 4 built. 5 (`maxTurns`) not: it needs a number from real runs. |
| Measurements M1–M5 | None run. Eight real-model runs as a smoke test instead: `benchmark/results/2026-10-05-two-stage-smoke.md`. |
| Spikes | S5 (hook half) and S7 seen. S1, S4 and the skill half of S5 not run: `benchmark/results/2026-10-05-platform-spikes.md`. |

Departures from the text below, each deliberate:

- **Only the Node hook moved (B).** "One rule for every runtime" was not
  followed. The `.py`, `.ps1` and `.sh` alternates still write
  `<project>/.intent/`. The skill's reader is the Node script, so a machine
  without Node cannot freeze a request whatever layout the alternate wrote;
  porting the layout to three more runtimes would have bought nothing and
  added three places for it to go wrong.
- **No `runs/` directory (B).** A run's working files live in a scratch
  directory the orchestrator chooses. Nothing needs them kept until a hook
  writes them, which is Change C.
- **No `request_sha256` in the manifest (A).** Nothing would have read it.
- **`--criteria` is spelled `--manifest-from` (A).**
- **`--list` does not print a command that deletes a legacy ledger (B).** It
  names the directory and says it can be deleted once its requests are no
  longer needed. That output is read by an agent, and a ready-made delete
  command for a user's files does not belong in front of one.
- **The deriver's allowlist names two inert tools**, not one, so that it
  resolves both where `TodoWrite` exists and where it does not.
- **Harness events are labelled when the ledger is read**, not when it is
  written, so entries captured by any version are covered.
- **The cap went to 256,000 characters** as well as keeping both ends.

What the work showed that this document got wrong or did not foresee:

- **Stage 1 is not "small next to the verifier run"** (Change A, Cost). In the
  session it was tried in, a criteria run was reported at 95k–106k tokens,
  mostly standing context, against 57k–140k for a verifier run on a
  one-function fixture.
- **Criteria written without sight of the code can ask for something the code
  cannot show**, which would turn a correct change into INCONCLUSIVE. The
  criteria prompt now tells the deriver to say only what the request commits
  to. How often this happens is unmeasured.
- **The deriver over-produces ambiguities** (2, 4 and 5 on three requests). It
  is now limited to four, most consequential first.
- **The harness indents a background subagent's report**, and the 0.2.1
  validator rejected a valid ledger copied from it. This strengthens the case
  for C: a reply captured by a hook is never reformatted on the way.
- **The verifier's command budget is exceeded in practice**: 8 to 13 shell
  commands on one-function fixtures and 18 on the 0.2.1 release, against a
  stated budget of about 15.

---

## The short version

v0.2.1 fixed every wrong-verdict path that could be fixed without changing a
contract. Three limits are left, and each needs one:

| | Limit after 0.2.1 | Proposed change | What becomes mechanical |
|---|---|---|---|
| **A** | Nobody who has not seen the code fixes the criteria, and the validator cannot tell when a requirement is missing | **Criterion manifest, two-stage dispatch** | "Every criterion fixed before the code was seen has a verdict, or the result is not MATCHES INTENT" |
| **B** | Your prompts sit in plaintext inside each project, in one file shared by every session | **Ledger outside the project tree**, one file per session | Session scoping, and "nothing of mine is in the repo" |
| **C** | The verifier's reply is free text, and the session that wrote the code is the one that saves and validates it | **Structured ledger bound to the run, captured by a hook** | "The ledger the validator saw is the one the verifier wrote" |

You asked for A and B. C came out of the 0.2.1 work; I recommend deciding it
together with them because it shares their plumbing, but it can wait.

Separately, three small capture fixes need none of the above and could ship as
0.2.2 (see [Smaller fixes](#smaller-fixes-that-need-none-of-this)).

The decisions I need from you are listed [at the end](#decisions-for-you).

## What the design rests on

Measured or observed during the 0.2.1 work, not assumed:

- **The validator's guarantee is narrow and now exact.** A reply holding any
  verdict other than PASS cannot validate as MATCHES INTENT (property test,
  3,000 seeded replies; 54 of them got past 0.2.0). What it cannot do: know
  which requirements a request had, or tell a ledger the verifier wrote from
  one the program printed when the verifier wrote none.
- **One in seven captured "tasks" is not something you typed.** Across our own
  ledgers (7 ledgers, 706 entries), 104 entries are harness events: 85
  `<task-notification>` (a background subagent reporting back), 16
  `<agent-message>`, 2 `<system-reminder>`, 1 `<scheduled-task>`. The Claude
  Code docs confirm `UserPromptSubmit` also fires for scheduled tasks,
  background-subagent reports and messages from other sessions.
- **A scope decision can be missing from the ledger entirely.** The request
  behind 0.2.1 was one captured prompt plus your answer to a multiple-choice
  question ("Patch + design v0.3"). The answer is not a prompt, so it was never
  captured. I recovered it from the session transcript with a short script.
- **Ledgers are shared.** The ledger this session wrote to holds 14 entries
  from 5 sessions; one of them is ours.
- **Long prompts are real.** Five of our prompts had been cut at the old 16k
  cap; in the transcripts they ran 18k to 44k characters. The docs note that
  pasted content arrives expanded inside `prompt`, which is where the length
  comes from.
- **Untested platform claims were wrong.** The first macOS CI run showed the sh
  fallback's redaction had matched nothing on macOS since 0.2.0. Every
  mechanism below therefore comes with a spike and a CI leg before it is relied
  on.

Platform facts below are from the Claude Code docs as fetched on 2026-10-05
(plugins reference: environment variables; subagents: frontmatter and tools;
hooks reference: common input, UserPromptSubmit, PostToolUse, SubagentStart,
SubagentStop). I read those sections, not the whole pages. Each one the design
depends on is listed again under [Spikes](#spikes-before-building), because the
docs describing a behaviour is not the same as having seen it work here.

---

## Change A — criterion manifest, two-stage dispatch

### The problem

Today the criteria come from two places, and both are compromised:

1. The **orchestrator** derives them in step 2 of the skill. It is usually the
   session that wrote the code, so it derives them knowing what was built.
   0.2.1 demotes these to a floor for exactly that reason.
2. The **verifier** is told to derive its own "before studying the
   implementation". That is an instruction. The verifier has file and shell
   tools from its first turn, and our own benchmark harness hands it the
   request and the code in one prompt.

So "criteria before code" — one of the three design decisions the README is
built on — is a request we make of a model, not a property of the system. And
because the validator has no list to check against, a verifier that never
mentions a requirement produces a ledger that validates. 0.2.1 covers that with
a prose check carried out by the orchestrator.

### The proposal

Split verification into two dispatches with different capabilities.

**Stage 1 — derive.** A new plugin subagent, `intent-criteria`:

- Receives the frozen request, inline. Nothing else.
- Cannot read files or run commands. The docs say an agent whose tool list
  resolves to nothing does not launch, so the allowlist would name a single
  inert tool. `omitClaudeMd: true` keeps the project's CLAUDE.md, which often
  describes the implementation, out of its context.
- Runs on a different model from the implementer, by the existing selection
  policy.
- Emits a manifest:

  ```json
  {
    "manifest": 1,
    "request_sha256": "…",
    "criteria": [
      {"id": 1, "text": "Posts are returned newest first", "quote": "newest first"},
      {"id": 2, "text": "No post is dropped", "quote": null}
    ],
    "ambiguities": ["'by date' — created or last edited?"]
  }
  ```

  `quote` is the exact piece of the request that commits to the criterion. A
  quote that does not occur in the request is a defect, so a criterion cannot be
  invented and attributed to you. Criteria with no quote are allowed and are
  reported to you separately as inferred. Sentences of the request that no
  quote touches are listed as a hint that something may have been skipped.

**Stage 2 — exercise.** The existing verifier receives request, manifest and
code. Its ledger must carry one criterion per manifest id, same number, same
text. It may append more. `validate_ledger.py --manifest` enforces this: a
manifest criterion that is absent is a defect, not something a reader has to
notice.

Three things follow without extra machinery:

- **Rounds become comparable.** Round 2 reuses the manifest, so a verdict that
  flips is about the code, not about criteria that were re-derived differently.
- **Your own criteria win.** `--criteria FILE` skips stage 1. If acceptance
  criteria were agreed before the work — an issue, a spec, a plan file — they
  are better ground truth than anything derived afterwards.
- **Ambiguity gets a place to go.** The README's stated limit is that an
  ambiguous request has no single ground truth. `ambiguities` turns that into a
  question to you before stage 2; your answer joins the frozen request. This is
  the case the tool is meant for, so I would spend the one interaction here.

### What it guarantees, and what it does not

Guaranteed, mechanically: every manifest criterion is in the ledger with a
verdict, or the verdict is not MATCHES INTENT; a reply cut off before its last
criteria is detected; the manifest was written by an agent with no access to
the code (pending spike S1).

Not guaranteed: that the manifest is *complete*. Deciding what a request
demands is still a model's judgement. The quotes, the uncovered-sentence hint
and showing you the manifest are aids, not proof.

### Cost

One more subagent call per verification, on the request alone, with no tools:
small next to the verifier run. A new agent file, one file format, a validator
flag, a changed skill procedure, and a two-stage mode in the benchmark.

### Alternatives considered

- **Keep the prose check.** Free, and it is what a reviewer already showed to
  be the weak point.
- **One verifier, two messages** (criteria first, then send it the code). Tools
  cannot be withheld from an agent mid-run, so this is still an instruction.
- **You write the criteria, always.** Most accurate, too much friction as the
  default. Kept as the `--criteria` override.
- **Derive at capture time**, in the prompt hook, before any code exists. The
  strongest guarantee of all, but it costs a model call on every prompt and
  most prompts are never verified.

---

## Change B — ledger outside the project tree

### The problem

`.intent/` holds your prompts in plaintext inside each project. 0.2.1 makes the
directory ignore itself, which stops `git add .` and nothing else: the files are
still there for code search, indexers, backups, another agent's grep, or a
zipped copy of the folder. One file is shared by every session in the project,
which is why 0.2.1 had to add session scoping. `log.md` duplicates all of it.
Uninstalling the plugin leaves all of it behind.

### The proposal

Store the ledger under the plugin's data directory. Per the docs,
`${CLAUDE_PLUGIN_DATA}` resolves to `~/.claude/plugins/data/<id>/`, survives
plugin updates, is deleted on uninstall unless `--keep-data` is passed, is
exported to hook processes, and is substituted in skill and agent Markdown. It
is *not* in the environment of commands run through the Bash tool, so the skill
must pass it to the reader explicitly.

```
<data>/projects/<key>/project.json             the project path this key stands for
<data>/projects/<key>/sessions/<session>.jsonl one file per session, append-only
<data>/projects/<key>/runs/<run>/              request, manifest, ledger, verdict
```

`<key>` is a hash of the normalised project path.

- **One file per session** makes scoping a property of the layout. The
  `--session` filter and its failure modes go away.
- **Retention replaces rotation.** Session files older than a set age are
  deleted (I would default to 30 days). A size cap per entry stays only to
  bound disk use and can be far higher than 64k.
- **`log.md` is dropped.** `--list` and a `--show <id>` are the readable view.
- **The verifier gets the request inline**, not as a path. The file now lives
  outside the project, where a subagent's read may need a permission prompt,
  and inline removes the wrong-file failure as well.
- **Manually wired alternates** have no plugin environment. One rule for every
  runtime: `INTENT_VERIFY_DATA` if set, else `CLAUDE_PLUGIN_DATA`, else
  `~/.claude/intent-verify/`.

### Migration

0.3 stops writing `.intent/`. The reader looks in the data directory first and
falls back to a legacy `.intent/log.jsonl`, read-only, so a verification run
straight after upgrading still finds its request. Legacy ledgers are never
deleted automatically — they are your files — but while one exists `--list`
says so and prints the command that removes it.

### The trade

Prompts move from many project folders to one tree in your home directory.
That is easier to wipe and is out of every repository. It is also one place
that now holds prompts from all your projects, which matters if the home
directory is synced or backed up. Redaction is unchanged and still partial.

### Alternatives considered

- **Stay in `.intent/`** with the self-ignore. Zero migration; leaves every
  problem above except accidental staging.
- **The session scratchpad directory** (a hook input field). Perfectly scoped,
  but its lifetime is the session's, and a request must outlive that.
- **Store pointers, not text.** Claude Code already keeps every prompt in the
  session transcript; the ledger could hold only an id and a hash and read the
  text from the transcript at freeze time. No duplicate copy at all. I would
  not make it the default: the transcript format is internal, the docs warn it
  is written asynchronously and can lag, and transcripts get cleaned up. It is
  the right recovery source, and could be an opt-in mode.

---

## Change C — the verdict path without the implementer

### The problem

Two things, both found while fixing 0.2.1.

1. The ledger is line-oriented text with the program's output inside it. 0.2.1
   closes every case where the verifier wrote a ledger. If it writes a prose
   report and quotes a ledger printed by the code under test, that quoted
   ledger is what validates. The skill now tells the orchestrator to check for
   this; nothing enforces it.
2. The orchestrator relays the evidence. It saves the verifier's reply to a
   file and runs the validator on it, and it is usually the session that wrote
   the code being judged. Nothing detects a ledger that was tidied, trimmed or
   summarised on the way.

### The proposal

- **A run has an identity.** `capture-intent.js --begin-run` creates the run
  directory and a random nonce, and prints the dispatch block for the verifier.
- **The ledger is a JSON object carrying that nonce.** Captured output is a
  JSON string, so it cannot be read as structure. A ledger printed by the
  program under test cannot carry the nonce unless the verifier leaked it.
- **A `SubagentStop` hook captures the reply.** Per the docs it receives the
  subagent's final text as `last_assistant_message` and can be matched to the
  plugin's verifier. It writes that text into the run directory. The
  orchestrator validates the file the hook wrote, not a copy it made.

That is **C1**, and it is what I would build. **C2** goes further: the hook
validates too and, on defects, returns `decision: "block"`, which the docs say
keeps the subagent running with the reason as its next instruction. That makes
the single bounded retry mechanical. It also requires the validator to run
inside a hook, which means porting it from Python to Node — the plugin's only
guaranteed runtime — and keeping the property test against the port. I would
not pay that until a measurement shows the prose retry failing.

### The risk

JSON-escaping long multi-line output is exactly where weak models slip.
STRUCTURED mode exists because T3 verifiers follow templates better than open
formats. This needs a measurement (M4) before the text grammar is retired, and
v1 text ledgers stay accepted for at least one minor version either way.

---

## Smaller fixes that need none of this

Additive, no contract change, each backed by something observed. They could
ship as 0.2.2.

1. **Label harness events.** Tag entries that open with a harness envelope
   (`task-notification`, `agent-message`, `scheduled-task`) and leave
   task-notifications out of `--list` by default. A subagent's report is never
   your request; a scheduled task or a message from another session might be,
   so those are labelled, not hidden.
2. **Record decisions.** A `PostToolUse` hook on `AskUserQuestion` receives the
   question and the answer (docs). Store them as `kind: decision`, linked to the
   prompt in flight by `prompt_id`.
3. **Freeze a set, not an entry.** `--freeze id1,id2` writes one request from
   the task, its follow-ups and its decisions, and the skill shows you the set
   before verifying. This is the fix for "one prompt is one request".
4. **Keep both ends of a cut prompt.** With a long paste the instruction sits
   at the start or the end; cutting only the tail can remove the instruction.
5. **Make the execution budget mechanical** with `maxTurns` on the verifier.
   The number has to come from measuring real runs first.

---

## Prior art, and where not to go

No part of this is a novelty claim. Fixing acceptance criteria before the work
and checking results criterion by criterion is established practice.

- **Spec-first harnesses.** [Claude Code Harness](https://github.com/Chachamaru127/claude-code-harness)
  (MIT) runs plan → work → review as one loop: per its README, planning writes
  `spec.md` and `Plans.md` with acceptance criteria that you approve before any
  work, review runs separately from implementation and returns criterion-level
  results, and a sync step reports drift between plan and implementation. I
  read its README; I have not run it.

  If you already plan through a harness like that, its approved criteria are
  better ground truth than a manifest derived after the fact, which is why
  `--criteria` is in Change A. And if what you want is the whole disciplined
  loop, adopt one rather than growing intent-verify into one.

  intent-verify's remaining place is narrower than the README's comparison
  table suggests: checking work that was *not* planned through a spec, against
  the prompt as you typed it. The table should gain a row for this category
  (decision D6).
- **Not read yet**, surfaced by the same search and worth reading before A is
  built: Stanford's "LLM-as-a-Verifier" paper, an arXiv paper on static
  verification of code against natural-language requirements, and Augment's
  coordinator/implementor/verifier guide. I have seen search excerpts only.
- **Commercial:** Aviator Verify, already in the README.

Out of scope on purpose: re-running the verifier's commands to check its
evidence (that is executing model-written commands from a hook); a planning or
task-tracking layer; anything hosted.

---

## Measuring it

0.2.1 removed claims that were never measured. 0.3 should not add new ones.

| | Question | Method |
|---|---|---|
| **M1** | Does a different-model verifier beat a same-model one? | 16 controlled cases × both arms × 3 repeats, everything else equal |
| **M2** | Does two-stage beat single-stage? | Manifest recall against the oracle's criteria, verdict accuracy, tokens and latency |
| **M3** | Do forged ledgers get through? | New adversarial fixtures: code that prints FINAL lines, a whole ledger, a whole ledger plus "stop here"; text v1 against JSON + nonce |
| **M4** | Can T3 models emit the JSON ledger? | Validity rate, STRUCTURED text against JSON |
| **M5** | Field recall | Under-specified tasks with a known intended answer (already on the roadmap) |

Also a new mock profile, `omitter`, which drops a criterion: undetectable
today, and it must be INVALID once `--manifest` exists.

These cost real model runs. M1 alone is 96 verifier runs. If M1 shows no
difference at this size, the honest outcome is to say so and demote the
cross-model lever from a design decision to a preference.

---

## Order of work

| Phase | Contents | Gate |
|---|---|---|
| **0.2.2** | Smaller fixes 1–4 | Spikes S4, S7 |
| **0.3.0** | B, then A with `--criteria` and ambiguity prompts; benchmark two-stage mode; M1 and M2 | Spikes S1, S5, S6 |
| **0.3.x** | C1; M3 and M4 | Spikes S2, S3 |
| later | C2, only if the prose retry is shown to fail | M-data |

**What breaks for whom.** Existing `.intent/` directories are left in place and
read as a fallback. Manually wired alternates need `INTENT_VERIFY_DATA` or get
the home-directory default. Anything outside the plugin that reads
`.intent/log.jsonl` would need the new path; I know of nothing that does. v1
text ledgers keep validating through 0.3.x.

## Spikes before building

Each is under an hour, has a pass/fail outcome, and should run on the Windows
desktop app and the CLI, with the result recorded under `benchmark/results/`.

- **S1** An agent whose allowlist is one inert tool launches, and cannot read
  files or run commands. `omitClaudeMd` is honoured for a plugin agent.
- **S2** A plugin `SubagentStop` hook fires for the plugin's verifier, in
  foreground and background, with the complete final text.
- **S3** `decision: "block"` re-prompts the subagent once, and
  `stop_hook_active` is true on the second stop.
- **S4** `PostToolUse` fires for `AskUserQuestion` in the desktop app with the
  answer in `tool_response`, and `prompt_id` matches the prompt in flight.
- **S5** `${CLAUDE_PLUGIN_DATA}` is substituted in the skill body on Windows
  (backslashes, spaces), is present in the hook's environment, and the
  directory survives a version bump.
- **S6** Whether a subagent reading a file under the data directory triggers a
  permission prompt, per permission mode.
- **S7** The envelope tags on harness-generated prompts are stable prefixes.

## Decisions for you

1. **A — build the two-stage manifest?** I recommend yes, with the `--criteria`
   override and the ambiguity question.
2. **B — move the ledger to the plugin data directory?** I recommend yes: one
   file per session, drop `log.md`, 30-day retention. Tell me if you want a
   different retention, or the pointer-only mode.
3. **C — now or later?** I recommend C1 in a 0.3.x release after its spikes,
   and C2 only on evidence.
4. **0.2.2 first?** I recommend yes. The harness-event and decision fixes are
   small and the need is measured.
5. **Measurement budget.** M1 is about 96 verifier runs. Run it, and on which
   pair of models?
6. **README comparison table.** Add the spec-first category? Proposed row:
   *Spec-first harness (e.g. Claude Code Harness) · anchors on acceptance
   criteria you approve before work · OSS · catches it when the work was
   planned through the harness.*
7. **This document.** Keep it local, commit it under `docs/`, or open it as a
   GitHub issue for outside comment?
