# Two-stage verification — first real-model run (2026-10-05)

A smoke test, not a benchmark: eight model runs to see whether the 0.3 flow
holds together on real output before it shipped. Read the caveats before the
tables.

## Setup

- **Stage 1 (criteria):** Claude Sonnet 5.5, given the text of
  `agents/criteria.md` and the request. No path, no code.
- **Stage 2 (verifier):** Claude Sonnet 5.5 through the `intent-verifier`
  agent, given the request, the stage-1 manifest and one fixture.
- **Fixtures:** `benchmark/impl/` — `sorttasks` and `ratelimit`, each in its
  drifted and its correct form. They were written in July by a different model
  (Opus 4.8).
- **Validation:** `tools/validate_ledger.py` at 0.3.0, `--check-manifest` for
  stage 1 and `--manifest` for stage 2.

## Caveats

- It was run from inside a Claude Code desktop session, through that session's
  subagent tool, because the `claude` CLI on the machine was logged out. Two
  things follow:
  - The deriver was a general-purpose agent *told* not to use tools. It made no
    tool call other than handing back its reply, but nothing enforced that. The
    tool restriction in `agents/criteria.md` has not been seen working.
  - The verifier ran the 0.2.0 agent prompt, since the session predated the
    update, with the manifest rules given in the dispatch message.
- One run per cell. Verifiers are non-deterministic.
- Two requests and one invented one. Nothing below is a rate.

## Stage 1 — manifests

| Request | Criteria | Quoted | Inferred | Ambiguities raised | Valid on first reply |
|---|---|---|---|---|---|
| `sorttasks`: "Sort tasks by priority, highest first; break ties by earliest due date." | 3 | 2 | 1 | 2 | yes |
| `ratelimit`: "Rate-limit login to 5 attempts per minute per IP; different IPs are tracked independently." | 7 | 6 | 1 | 4 | yes |
| Invented, deliberately vague: "The blog index is slow and the posts are in a weird order. Sort the posts by date and make it fast. Don't break the RSS feed." | 6 | 5 | 1 | 5 | yes |

- The `sorttasks` manifest contains the tie-break ("break ties by earliest due
  date"). That is the requirement the drifted fixture omits, and one of the four
  that diff-anchored review missed in July.
- For the vague request the first ambiguity raised was the sort direction:
  newest first or oldest first. The one sentence no criterion quoted was the
  opening complaint, which the validator listed as a note.
- Every quote was found in its request by the mechanical check.

## Stage 2 — verdicts

| Fixture | Expected | Verdict | Manifest criteria | Added by verifier | PASS / FAIL / not exercised | Defects |
|---|---|---|---|---|---|---|
| `sorttasks` | DRIFTED | DRIFTED — criteria 2 failed | 3 | 0 | 2 / 1 / 0 | 0 |
| `ratelimit` | DRIFTED | DRIFTED — criteria 5, 6 failed | 7 | 0 | 4 / 2 / 1 | 0 |
| `sorttasks_ok` | MATCHES INTENT | MATCHES INTENT | 3 | 2 | 5 / 0 / 0 | 0 |
| `ratelimit_ok` | MATCHES INTENT | MATCHES INTENT | 7 | 3 | 10 / 0 / 0 | 0 |

Four of four expected verdicts. Every ledger was valid against its manifest on
the first reply, and also in the form the harness delivers a background
subagent's report, with two spaces in front of every line. As a control, each
ledger is invalid against the other request's manifest.

## What it showed that the design had not

1. **A criterion the code cannot show.** The `ratelimit` manifest's one inferred
   criterion was "Requests to endpoints other than login are not blocked by, or
   counted toward, this limit." The fixture is a single function. One verifier
   marked it NOT-EXERCISED; the other wrote a shim around the function and
   passed it. Had the first one been looking at the correct fixture, a correct
   change would have come back INCONCLUSIVE. Criteria written without sight of
   the code can outrun the code's surface.
2. **Eager ambiguities:** 2, 4 and 5 questions. Put to a user one by one, that
   is a lot of friction for a check that was supposed to be quiet.
3. **Cost.** Each stage-1 run was reported at 95k–106k tokens, most of it the
   session's standing context, against 57k–140k for a verifier run on these
   one-function fixtures. In a session with a large standing context, stage 1
   is not small next to stage 2.

The criteria prompt was tightened after these replies: say only what the
request commits to, include an implied criterion only when breaking it would
defeat the request, raise at most four ambiguities. One re-run on the
`ratelimit` request then gave 5 criteria, all quoted, and 3 ambiguities. That is
one run and stage 2 was not repeated with it.

## Files

`2026-10-05-two-stage-smoke.raw/` holds the raw replies: four stage-1 replies
and four ledgers. Local paths are shortened to `<repo>` and `<scratch>`; nothing
else is changed.
