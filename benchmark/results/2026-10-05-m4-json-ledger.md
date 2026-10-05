# M4 — JSON ledger against text ledger (2026-10-05)

**Question** (`docs/DESIGN-v0.3.md`, measurement M4): can a verifier, and a T3
model above all, write its ledger as one JSON object as reliably as it writes the
text ledger? Change C would make the ledger a JSON object carrying a per-run
nonce, so output printed by the code under test is a JSON string and can never be
read as ledger structure. The design named the risk: escaping is where weak
models slip.

**Method.** The 16 controlled cases, criteria held fixed (the manifests derived
in the two-stage run, `2026-10-05-cli-claude-sonnet-5-5-two-stage.raw/`), one
run per case, every call in `claude -p --safe-mode`, one retry on an invalid
ledger. A JSON ledger is rewritten as the text ledger and checked by the same
validator, so both encodings face the same rules; JSON adds only that the object
must parse, carry the run's nonce and hold strings. Script:
`benchmark/m4_json_ledger.py`. Per-arm reports and every raw reply sit beside
this file (`2026-10-05-m4-*.md` and `.raw/`); local paths in the stored replies
were replaced with `<repo>`, `<tmp>` and `<home>` before publishing.

| Verifier | Mode | Ledger | Valid on first reply | Expected verdict | Tokens | Cost, list price |
|---|---|---|---|---|---|---|
| Haiku 4.5 (T3) | STRUCTURED | text | 15/16 | 15/16 | 4.34M | $1.15 |
| Haiku 4.5 (T3) | STRUCTURED | JSON | 16/16 | 15/16 | 3.21M | $0.92 |
| Sonnet 5.5 (T1) | FULL | text, from the two-stage run | 15/16 | 16/16 | 1.73M | $1.14 |
| Sonnet 5.5 (T1) | FULL | JSON | 16/16 | 16/16 | 1.79M | $1.10 |

- **Haiku's one miss is the same case in both arms.** `validate_ok` is the only
  case with six criteria, and STRUCTURED mode exercises at most five, so the
  right outcome is INCONCLUSIVE with the sixth marked NOT-EXERCISED. The JSON
  ledger did exactly that. The text ledger exercised all six, broke the
  five-criterion rule, and was rejected on the retry as well.
- **Sonnet's text retry** was a paraphrased manifest criterion, rejected and
  then copied exactly.
- **Every JSON reply parsed and carried its run's nonce.** Across the 32 JSON
  ledgers, 250 evidence fields: 72 multi-line, 52 holding double quotes, 2
  holding backslashes. The longest captured output was 421 characters.

**What this does not show.** These are one-function fixtures with short output.
Long captured output, and output full of backslashes (Windows paths), were
barely exercised, and that is where the design expected escaping to fail. One
run per cell, one T3 model (Haiku 4.5, whose tier was assigned by hand in
`models/registry.json`), no non-Anthropic verifier.

**Reading.** On this set the JSON ledger was at least as reliable as the text
one for both tiers, and for the T3 model it held the STRUCTURED budget where the
text ledger did not. Nothing here argues against Change C's ledger format; the
long-output case is the one still open.
