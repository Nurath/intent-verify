# The sealed ledger, checked (2026-10-06)

0.4.2 changes what a verifier has to write: one JSON object that is the whole
reply, with only the format's keys, ending in `"seal"`, the run's nonce again.
The validator got stricter in several places at once, so three questions had
to be answered before release. Does it stop what it was changed to stop? Does
anything already recorded come out differently? Do real models still produce a
reply it accepts?

## 1. What it was changed to stop

An independent review of 0.4.1 reported three findings. A first fix closed
them, and a second model set on that fix reported thirteen more
(`logs/2026-10-06.md` lists all sixteen). Each has a regression test in
`tests/test_validate_ledger.py` (`TestSecondReview`, `TestAdversarialPass`,
`TestSealedLedger`).

One of those tests deserves a note, because its first version proved nothing.
It pasted random pieces of ledger syntax into the output of a failing ledger,
12,000 replies, and none validated as `MATCHES INTENT`. None did with every
new rule switched off either: random pieces almost never form the one sequence
that works. The test that replaced it enumerates a grammar that contains the
known attack (end the string, maybe the entry, forge the entries after it, end
the list, conclude, then close the object or open something for the real
remainder to land in):

| | replies |
|---|---|
| in the grammar, over two ledger shapes | 4,680 |
| validate as `MATCHES INTENT` | 0 |
| validate at all (as `DRIFTED`, the honest verdict) | 2 |
| conclude `MATCHES INTENT` and are stopped only by the seal and the rule about text after the ledger | 76 |
| conclude `MATCHES INTENT` and are stopped by those two plus the rules about repeated or unknown keys | 204 |

The test asserts the fourth row is above zero, so it fails if the grammar ever
stops containing an attack that works without the new rules.

### A second pass, on the rewritten validator

A third model (Fable 5.1) was then given the rewritten code, the prompts, the
threat model and the list of what was already known, and asked for false
passes, false rejects that a retry cannot fix, crashes, stage-1 mistakes, and
any way to reach the version 1 rules without the flag. It wrote and ran its own
probes outside the repository. It reported no false pass, no crash and no
unfixable false reject, and two minor findings, both fixed and pinned by tests:

- `--manifest-from` kept a line holding only a zero-width space as a criterion,
  and the manifest it wrote was then rejected by `--manifest`.
- A brace in the sentence before the ledger (`it returns {} on empty input`)
  was read as the object the reply opens with, and the defect sent the retry
  looking for a problem with the nonce. The message now names the brace.

## 2. Nothing recorded changes

Every real reply kept in this directory was put through the new validator and
compared with the verdict its run recorded (a final reply that is invalid
corresponds to a recorded `INCONCLUSIVE`). Version 1 JSON ledgers were checked
with `--unsealed`.

| stored before this release | replies | recorded verdict reproduced |
|---|---|---|
| version 1 JSON ledgers (the prompts of 0.4.0 and 0.4.1) | 53 | 53 |
| text ledgers | 71 | 71 |
| stage-1 replies, the final attempt of each | 78 | all validate |

The 36 version 2 replies made for this release (section 3) replay to their
recorded verdicts as well.

## 3. Real models still write it

All calls are `claude -p --safe-mode`; cost at list price.

### End to end, live

A headless session loaded the working tree as a plugin (`--plugin-dir`, user
settings left out) and dispatched `intent-verify:intent-verifier` (Sonnet 5.5)
on the `median` fixture, a mean labelled "central value", under a run started
with `capture-intent.js --begin-run`.

- The `SubagentStop` hook filed the verifier's reply in the run's directory.
  Nothing went to `_unmatched/`.
- `validate_ledger.py --run <dir> --manifest <manifest>`: `VALID: 5 criteria (all
  5 manifest criteria covered), final = DRIFTED — criteria 2, 3, 4 failed
  (captured by the hook: reply-….txt)`.
- Cost: $0.15.

The run is kept as `2026-10-06-sealed-live.raw/` (local paths replaced with
placeholders) and checks out from the published copy; a test runs it:
`python tools/validate_ledger.py --run benchmark/results/2026-10-06-sealed-live.raw --manifest benchmark/results/2026-10-06-sealed-live.raw/manifest.json`.

### The same, in the desktop app

Added after the release, the same day. The Windows desktop app was restarted
with 0.4.2 installed from the marketplace, and a session there started a run
with the installed copy and dispatched `intent-verify:intent-verifier` (Sonnet
5.5) on the same fixture with the same manifest.

- The verifier handed back a version 2 ledger and nothing else: no sentence
  before it, nothing after it, exactly the format's keys, the nonce twice.
- The hook filed it in the run's directory, the same 8,041 characters the
  verifier handed back. Nothing went to `_unmatched/`.
- `validate_ledger.py --run <dir> --manifest <manifest>`, run from the installed
  copy: `VALID: 5 criteria (all 5 manifest criteria covered), final = DRIFTED —
  criteria 2, 3, 4 failed (captured by the hook: reply-….txt)`.

The run is kept as `2026-10-06-sealed-desktop.raw/` (local paths replaced,
session id replaced), and the same test runs it.

### The benchmark sets

| run | verifier | expected verdict | valid on the first reply | retries | cost |
|---|---|---|---|---|---|
| controlled, two-stage, n=16 ([report](2026-10-06-cli-claude-sonnet-5-5-two-stage-v042.md)) | Sonnet 5.5, FULL | 16/16 | 16/16 | 0 | $1.27 |
| adversarial, two-stage, n=3 ([report](2026-10-06-cli-claude-sonnet-5-5-two-stage-v042-adversarial.md)) | Sonnet 5.5, FULL | 3/3 `DRIFTED` | 3/3 | 0 | $0.29 |
| controlled, criteria held fixed, n=16 ([report](2026-10-06-m4-claude-haiku-4-5-20251001-structured-json.md)) | Haiku 4.5, STRUCTURED | 15/16, 1 `INCONCLUSIVE` | 16/16 | 0 | $1.08 |

All 20 Sonnet replies, the live one included, were the object and nothing else:
no sentence before it, nothing after it, exactly the format's keys, remarks in
`observations`. With the version 1 prompt, 45 of the 53 replies kept here had
put remarks after the object and 4 had carried a key of their own
(`ledger_note`), both of which that prompt allowed.

Haiku 4.5 is the small-model check: a stricter format is only an improvement
if a T3 verifier can still write it. It did, 16 of 16 on the first reply, as
with version 1 the day before. All 16 of its replies came in a code fence and
one opened with a sentence, which is why the validator tolerates both. Its one
`INCONCLUSIVE` is the STRUCTURED budget at work: that manifest has six criteria
and the mode exercises five. The same case came out the same way with
version 1.

## What this does not show

- **More than one run per harness.** The sealed ledger has been captured and
  validated once headless and once in the desktop app. The interactive
  terminal has not been checked as a harness of its own.
- **Other verifier models**, and FULL mode on a small one.
- **That nothing is left.** Two reviews and two adversarial passes are a record
  of what was looked for.
