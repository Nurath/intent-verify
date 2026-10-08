# Handoff — intent-verify

The small file to read first when picking this repository up. It points at
everything else; it should stay under a few pages.

## Reading order

1. The newest file in `logs/` — what was done last, what is open.
2. This file.
3. The section of `docs/architecture.md` you need (parts, flow, storage,
   contracts, runbook). Grep for it; do not read the whole file by default.
4. The top entry of `CHANGELOG.md`.

`README.md` is the case for the tool and its evidence. `docs/DESIGN-v0.3.md` is
the reasoning behind 0.3, including what was proposed and not built.

## What this is

A Claude Code plugin that checks whether an AI-written change did what the user
asked, as opposed to what the diff says it does. A hook records what the user
asks. On request, a skill freezes that request, has acceptance criteria written
by a subagent that cannot read the project, has a second subagent on a
different model run the code against each criterion, and validates the
resulting ledger mechanically: the copy a `SubagentStop` hook captured, bound
to its run by a nonce, not one the implementing session relayed. The verdict is
`MATCHES INTENT`, `DRIFTED` or `INCONCLUSIVE`.

## Where things live

| You want | Look at |
|---|---|
| The procedure the orchestrating session follows | `skills/intent-verify/SKILL.md` |
| What the two subagents are told | `agents/criteria.md`, `agents/verifier.md` |
| Capture, and the `--list` / `--show` / `--freeze` reader | `hooks/capture-intent.js` |
| Manifest and ledger validation | `tools/validate_ledger.py` |
| Verifier model policy | `tools/select_verifier.py`, `models/registry.json`, `docs/MODEL-COMPAT.md` |
| The benchmark and every recorded run | `benchmark/`, `benchmark/results/` |
| Whether the question before verifying is asked where it should be | `benchmark/ask_first.py`, `benchmark/ask_first_cases.json` |
| Tests, including the ones on prose and config | `tests/` |

## What is released — check, do not trust this file

```bash
git log --oneline -3 origin/main
```

```bash
claude plugin list
```

The version is `version` in `.claude-plugin/plugin.json`; the top heading of
`CHANGELOG.md` must match it (a test enforces that). An installed copy changes
only when someone runs the two update commands in the runbook and restarts.

## Test baseline (0.5.3)

- `python3 -m unittest discover -s tests`: 331 tests. On Windows 18 skip (POSIX
  shell tests and one layout-specific test); on Linux and macOS the PowerShell
  classes skip instead.
- `node hooks/capture-intent.js --selftest`: 35 of 35.
- `python3 benchmark/run_bench.py --mode mock --no-write`: exit 0.
- CI: four checks (`ubuntu-latest`, `macos-latest`, `windows (powershell)`,
  `windows (pwsh)`), all required to be green before a merge.

## Gotchas

- **A running Claude Code session does not pick up a new plugin version**, new
  agents or new hooks. Anything that needs the new code loaded needs a restart.
- **The `claude` CLI has its own login.** A logged-out CLI blocks
  `run_bench.py --mode cli` and any headless check, even while the desktop app
  works.
- **Windows:** there is no `python3`, only `python`. Tracked files check out
  with CRLF while the index stays LF. The POSIX shell tests cannot run locally;
  CI is where they execute.
- **Rules that exist in four runtimes** (redaction, invocation tagging) must be
  changed in all four; see the runbook in `docs/architecture.md`.
- **Files in this repository ship to everyone who installs the plugin.** Keep
  logs and docs free of anything private.
- **A parser or validator is not sound because its author tested it.** Two
  independent reviews each found false-pass paths in one that had been called
  sound (0.2.0, 0.4.1), and the first fix for the second review was itself
  broken by the first model set on it. Before releasing a change to
  `validate_ledger.py`, have a different model attack it, with the code and the
  rules and without your conclusions, and attack again after fixing what it
  finds.
- **A property test has to be able to fail.** A seeded fuzz of ledger syntax
  found nothing even with every protection switched off. Its replacement
  enumerates a grammar that contains the known attack and counts the payloads
  only the new rules stop.
- **A check on what a reply contains has two readings: as written and as
  decoded.** A JSON escape for one character hid the nonce from a rule that
  read the raw text (0.4.3).
- **Locate, do not count.** Two counts can be balanced: an escape takes an
  occurrence out of one place and a copy puts it back elsewhere. A rule about
  where something may be has to look at each place separately.
- **The agents pin their own model and effort** (0.5.0). A session's own
  setting no longer makes them faster or slower, and the skill must not pass a
  model to the criteria agent. The benchmark harness passes `--effort high` to
  match. Seen working headless only; the documentation says the
  `CLAUDE_CODE_EFFORT_LEVEL` environment variable still overrides the pin.
- **A label written after seeing the answer is not a measurement.** The first
  ask-first run missed one of six cases, and the case turned out to be
  mislabelled; a second run of the same request then gave the other answer.
  Cases a careful reader could take either way are now labelled so and not
  scored, and every case is run three times. And rules revised after misses
  on a set are fitted to that set: keep requests they never saw, and write
  down the expected answer before running them.
- **When one rule is fixed, look at the rule beside it, and at what else
  reads the same list.** 0.5.1 taught the print filter about marks with no
  glyph and left `_blank` calling them evidence (0.5.2); 0.5.2 then took two
  characters off a list the print filter also read (0.5.3).
- **Version 1 ledgers need `--unsealed`.** The runs kept from 0.4.0 and 0.4.1
  are version 1 objects. The default path rejects them and says so.
- **A harness is a thing to test.** The verifier-capture hook worked headless
  and captured nothing in the desktop app (0.4.0). Check hook behaviour where
  users run it.
- **The harness indents a background subagent's report.** Take a verifier's
  reply from the subagent's own output where possible; the validator tolerates a
  uniform indent but not a tidied-up copy.

## Open items (2026-10-07)

Done: the sealed ledger captured and validated headless and in the desktop app
(`benchmark/results/2026-10-06-sealed-ledger.md`). If a reply is ever rejected
for "text after the ledger", look at what the harness appended to the
hand-back before suspecting the verifier.

1. **Stage-1 questions: fixed in 0.3.2, with one cost to watch.** 41 up-front
   questions on the 16 controlled requests became 3, none asked before
   verifying. The cost: a second reading the criteria agent does not record
   gets no question at all. In the field set that produced one false DRIFTED
   (`recall_weekend`: a flag from the caller versus recognising a weekend date).
   If it recurs, the candidate fix is a question after any FAIL whose evidence
   shows the code doing what the words say by another route. That question
   would come from the session that wrote the code, so it needs care.
2. **Change C1 works headless and, from 0.4.1, in the desktop app; each seen
   once.** 0.4.0 captured nothing in the desktop app, because a subagent there
   hands its report back through a `SubagentHandback` tool call and the hook
   read only `last_assistant_message`. 0.4.1 reads the subagent's transcript,
   and the desktop check then passed: the hook's copy matched the report byte
   for byte (`benchmark/results/2026-10-05-c1-run-bound-ledger.md`). A harness
   is a separate thing to test: check hook behaviour in the one users run, not
   only headless. Not checked: the interactive terminal. Still open: long or
   backslash-heavy evidence in a JSON ledger (M4), and C2, which needs S3
   first.
3. **Cross-model ablation** not run. On the controlled set the drift is planted
   and both arms would likely sit at the ceiling. A fair test needs drift a
   model produced itself, which is the field-recall work.
4. **`models/registry.json` holds scores from two versions of the index**
   (`scales`): the current Claude models on the newer one, every other row on
   the August snapshot. Scores are compared only within a scale (0.5.1). A
   whole refresh would end that. Fable 5.1 has an assumed tier, no score, and
   `ranks_above` Sonnet 5.5: drop that field when the index lists it. Only
   Sonnet 5.5 and Haiku 4.5 are timed.
5. **The alternate hooks** still use the in-project layout. Port them or retire
   them; today they cannot serve the skill without Node either way.
6. **The verifier's command budget** ("about 15") is exceeded in practice.
   Pick a number from the recorded runs and enforce it with `maxTurns`.
7. **The question before verifying (0.5.0) is measured on requests written
   here**, 17 of them, plus one real one
   (`benchmark/results/2026-10-06-faster-and-ask-first.md`). In real runs,
   note when it is asked and what the answer was. If it is asked about plain
   requests, the rules in `agents/criteria.md` need a case, not a rewrite.
8. **Speed (0.5.0) is measured on one small task.** Not measured: a real run
   end to end, the pin in the desktop app, whether `high` is the right
   effort (the CLI's default gave the same 19 verdicts), and what a stronger
   verifier catches that Sonnet does not. Not built, by the maintainer's
   choice: the verifier skipping CLAUDE.md.
9. **A request whose subject is in the assistant's previous message** ("ok
   lets work on it") cannot be frozen from the user's prompts alone. The
   0.5.0 check of itself added that paragraph by hand, labelled. The skill
   does not say what to do; the hook does not capture assistant text.
10. **The printed ledger shows the start of a long output only.** The last line
    of a test log, where the result is, can be cut. Candidate: head and tail.
    It touches the filter every printed value goes through, so attack it.
