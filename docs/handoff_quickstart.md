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

## Test baseline (0.4.1)

- `python3 -m unittest discover -s tests`: 209 tests. On Windows 18 skip (POSIX
  shell tests and one layout-specific test); on Linux and macOS the PowerShell
  classes skip instead.
- `node hooks/capture-intent.js --selftest`: 34 of 34.
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
- **The harness indents a background subagent's report.** Take a verifier's
  reply from the subagent's own output where possible; the validator tolerates a
  uniform indent but not a tidied-up copy.

## Open items (2026-10-05)

Done later on 2026-10-05: the three platform checks passed, and the two-stage
flow scored 16 of 16 on the controlled set
(`benchmark/results/2026-10-05-cli-claude-sonnet-5-5-two-stage.md`).

1. **Stage-1 questions: fixed in 0.3.2, with one cost to watch.** 41 up-front
   questions on the 16 controlled requests became 3, none asked before
   verifying. The cost: a second reading the criteria agent does not record
   gets no question at all. In the field set that produced one false DRIFTED
   (`recall_weekend`: a flag from the caller versus recognising a weekend date).
   If it recurs, the candidate fix is a question after any FAIL whose evidence
   shows the code doing what the words say by another route. That question
   would come from the session that wrote the code, so it needs care.
2. **Change C1: works headless, unproven in the desktop app. First thing to
   check.** 0.4.0 captured nothing in the desktop app, because a subagent
   there hands its report back through a `SubagentHandback` tool call and the
   hook read only `last_assistant_message`. 0.4.1 reads the subagent's
   transcript and handles the real transcript of that failure, but nobody has
   yet seen `SubagentStop` fire for a plugin's agent in the desktop app. Check:
   run one verification in a desktop session on 0.4.1 and read step 6. "Captured
   by the hook" means it works. Exit 4 now says whether the hook left a trace;
   "no sign that the hook ran" means the desktop app always relays, and the
   README must say so. Also open: long or backslash-heavy evidence in a JSON
   ledger (M4), and C2, which needs S3 first.
3. **Cross-model ablation** not run. On the controlled set the drift is planted
   and both arms would likely sit at the ceiling. A fair test needs drift a
   model produced itself, which is the field-recall work.
4. **`models/registry.json` predates the current models.** The selector
   excludes unknown models unless `--assume-tier` is passed.
5. **The alternate hooks** still use the in-project layout. Port them or retire
   them; today they cannot serve the skill without Node either way.
6. **The verifier's command budget** ("about 15") is exceeded in practice.
   Pick a number from the recorded runs and enforce it with `maxTurns`.
