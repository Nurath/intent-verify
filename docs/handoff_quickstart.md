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
resulting ledger mechanically. The verdict is `MATCHES INTENT`, `DRIFTED` or
`INCONCLUSIVE`.

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

## Test baseline (0.3.1)

- `python3 -m unittest discover -s tests`: 183 tests. On Windows 18 skip (POSIX
  shell tests and one layout-specific test); on Linux and macOS the PowerShell
  classes skip instead.
- `node hooks/capture-intent.js --selftest`: 26 of 26.
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

1. **Stage 1 asks too many questions.** In that run it raised 2 to 4
   ambiguities on every one-line request, 41 over 16, and the verdicts needed
   none of them. The skill puts each one to the user. Decide a rule before
   more people hit it.
2. **Change C: checks first, then decide** (decided 2026-10-05). Run spike S2
   (does `SubagentStop` fire for the plugin's verifier with the complete
   reply?) and measurement M4 (can verifiers write the JSON ledger reliably?).
   Build C1 only if both hold. The design also lists S3, which matters only
   for C2, and M3, which sizes the threat C1 removes.
3. **Cross-model ablation** not run. On the controlled set the drift is planted
   and both arms would likely sit at the ceiling. A fair test needs drift a
   model produced itself, which is the field-recall work.
4. **`models/registry.json` predates the current models.** The selector
   excludes unknown models unless `--assume-tier` is passed.
5. **The alternate hooks** still use the in-project layout. Port them or retire
   them; today they cannot serve the skill without Node either way.
6. **The verifier's command budget** ("about 15") is exceeded in practice.
   Pick a number from the recorded runs and enforce it with `maxTurns`.
