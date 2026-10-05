# Changelog

## 0.2.1 — 2026-10-05

Correctness release. An independent review of 0.2.0 found ways to get a wrong
verdict and gaps in capture; every finding was reproduced before it was fixed
and each bypass is now a regression test. The ledger a well-formed verifier
emits is unchanged — it is validated more strictly — and so are the hook wiring
and the three verdicts.

### Fixed — verdicts that could be wrong
- **A malformed ledger could validate as `MATCHES INTENT`.**
  - Single-line fields matched across newlines, so an empty `EVIDENCE-CMD:`,
    `REASON:` or criterion text borrowed the next line and passed. A value must
    now sit on its field's own line.
  - The ledger was cut at its first `FINAL:` line, so a `FAIL` after it was
    never parsed — including when that "FINAL" was a line of captured program
    output. Every criterion block is now parsed wherever it sits, the last
    `FINAL` is the conclusion, each criterion carries exactly one `VERDICT`,
    and the `mode:` line is required. A seeded property test splices forged
    ledger lines into 3,000 replies that each hold one verdict other than PASS;
    none validates as `MATCHES INTENT` (54 of the same 3,000 got past the 0.2.0
    validator).
- **Requirements could vanish from a ledger unnoticed.** Criteria must be
  numbered 1..N with no gaps. STRUCTURED mode now lists every requirement and
  marks those beyond its 5-criterion budget `NOT-EXERCISED` (so the run is
  `INCONCLUSIVE`) instead of dropping them. The skill hands its own criteria to
  the verifier as a floor and checks they all came back, and round 2 re-verifies
  everything rather than only what failed.
- **Verification could run against the wrong request, or half of one.**
  - The capture cap is 64k characters, up from 16k, which long task prompts
    exceeded in ordinary use. A request that is still cut caps the verdict at
    `INCONCLUSIVE` unless the full text is recovered.
  - Freezing the request is now a command, `capture-intent.js --list` /
    `--freeze <id>`, scoped to the current session. The project ledger is
    shared by every session; the old step was prose around `tail`.
  - Only unmistakable invocations ("verify this did what I asked",
    `/intent-verify`) are tagged `verify-invocation`. Tasks that merely began
    with "verify this …", or with the tool's own name, were being hidden from
    the freeze step.
  - Hook input over 10 MiB was dropped silently. It now leaves a
    `capture-incomplete` marker.
- **The validator crashed on non-ASCII ledgers under Windows codepages**, with
  the same exit code as "invalid". Its streams are UTF-8 now, and the skill
  treats any exit code other than 0 or 1 as a validator failure.
- **The skill called its helpers by repository-relative path**, which does not
  resolve from an installed plugin. They are addressed through
  `${CLAUDE_PLUGIN_ROOT}`.

### Fixed — privacy
- **`.intent/` was not ignored in the projects it is written to.** 0.2.0's note
  that it "remains gitignored" was true only inside this repository. The hook
  now writes `.intent/.gitignore` containing `*`, so the ledger ignores itself
  wherever it lands; existing ledgers are covered on the next prompt.
- **Prefixed API keys were stored verbatim** (`sk-proj-…`, `sk-svcacct-…`,
  `sk-admin-…`, `sk-ant-api03-…`): the pattern required an unbroken
  alphanumeric run.

### Fixed — benchmark runner (`--mode cli`)
- A verifier timeout aborted the whole run, and a failed launch or silent crash
  was scored as a malformed ledger. Each now makes that case `INCONCLUSIVE` and
  the run continues.
- The single retry was a fresh process that never saw the reply it was asked
  to correct. It now receives it.
- The CLI is launched through its resolved path; a `.cmd` shim could not be
  started by bare name on Windows.
- Raw verifier replies are saved beside the report so verdicts can be audited.

### Changed
- `capture-intent.sh` fallbacks: rotation archives are pruned to 3 (they grew
  without bound) and the jq path tags verification requests. They are now
  described as best-effort, not as equivalent to the Node script.
- Docs no longer state what was not measured: the cross-model lever was never
  ablated, and "harmless to run always" rested on seven tasks.
- Tests: the hook contract also runs against the PowerShell alternate (5.1 and
  7) and against the sh fallbacks with neither node nor python on PATH. CI adds
  macOS.

### Known limits, unchanged by this release
- The validator cannot know which requirements a request had; coverage rests on
  the skill's own criteria until a criterion manifest exists.
- A verifier that writes no ledger of its own and quotes one printed by the
  code under test is caught only by the skill reading the reply.
- `.intent/` still lives inside the project.

## 0.2.0 — 2026-08-03

Hardening + capability-aware verification. No behavior of the core thesis
changed: request-anchored, cross-model, evidence-required. What changed is that
the tool now survives hostile runtime conditions (stock Windows, no `python`,
huge ledgers, weak verifier models, flaky re-verification) instead of assuming
a frontier verifier on a POSIX box.

### Fixed
- **Intent capture broke silently on the most common platforms.**
  - `hooks.json` used a `commandWindows` key that does not exist in the Claude
    Code hooks schema, so on Windows without Git Bash the `sh` command ran
    under PowerShell and errored on every prompt. Hooks now use the documented
    cross-platform exec form: `"command": "node", "args": [...]`.
  - `capture-intent.sh` required a bare `python`, which modern Ubuntu/Debian/
    macOS don't ship — the ledger silently never populated. The dispatcher now
    falls back node → python3 → python → jq → markdown-only, and never fails
    the prompt.
  - The old config invoked `pwsh` (PowerShell 7), which stock Windows lacks,
    and `capture-intent.ps1` wrote ASCII under 5.1 defaults while stdin decoded
    via the OEM codepage — both mangled non-ASCII prompts. The script now
    decodes stdin as UTF-8 explicitly and writes UTF-8 on 5.1 and 7+.
  - Hook JSON payloads with a null/non-string `prompt` were logged as the
    string "None"; now skipped.
- **Ledger could grow without bound and corrupt its own entries.** Prompts are
  redacted (common credential shapes), capped (16k chars/entry, configurable),
  rotated (1 MiB, 3 archives); canonical storage is `.intent/log.jsonl` (one
  JSON object per line — no more `---`/`##` delimiter collisions with prompt
  content), with a fence-collision-safe `log.md` mirror.
- **Verification could loop.** SKILL.md now bounds re-verification (2 rounds,
  then report divergence and stop), bounds ledger re-requests (exactly one,
  then INCONCLUSIVE), forbids verifier recursion, and gives the verifier an
  explicit execution budget (attempts per criterion, total commands,
  non-interactive, install-nothing) so it cannot thrash on an unrunnable app.
- **The verifier could "helpfully" modify code.** Now explicitly read+run only,
  with a restricted tool list in `agents/verifier.md` frontmatter.

### Added
- **Capability-aware dispatch** (the model-intelligence gap): tier system on
  the Artificial Analysis Intelligence Index (`models/registry.json`, snapshot
  2026-08-02), floors per change complexity, different-family preference,
  weak-verifier gap warnings, STRUCTURED protocol for smaller models, and
  `tools/select_verifier.py` implementing the policy. Design rationale in
  `docs/MODEL-COMPAT.md`.
- **Machine-validated ledger contract**: exact output grammar in
  `agents/verifier.md`; `tools/validate_ledger.py` enforces evidence-required
  PASS/FAIL, reason-required NOT-EXERCISED, verdict/criteria consistency, and
  the new honest third verdict `INCONCLUSIVE` (unexercised work can no longer
  be laundered into MATCHES INTENT).
- **Runnable benchmark**: `benchmark/cases.json` (machine-readable cases),
  `benchmark/oracle.py` (real discriminating executions for all 16 controlled
  cases), `benchmark/run_bench.py` with mock mode (orchestration robustness
  across simulated verifier-degradation profiles, offline, deterministic) and
  cli mode (real models via the `claude` CLI).
- **Tests + CI**: 54 unit tests across hooks (node/python/sh contract parity),
  validator, selector, oracle, and orchestration; GitHub Actions on Linux +
  Windows (PowerShell 5.1 and 7) with shellcheck and the mock benchmark as a
  regression gate.

### Notes
- `.intent/` remains gitignored; redaction is defense-in-depth, not a promise.
- Registry scores drift; refresh the snapshot in one commit rather than
  hand-editing single entries (see docs/MODEL-COMPAT.md).

## 0.1.0 — 2026-07-14

Initial release: skill + verifier subagent + intent ledger + controlled
benchmark (n=16) + field trials (n=7).
