# Changelog

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
