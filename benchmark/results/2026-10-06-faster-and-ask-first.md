# Faster, and one question first, checked (2026-10-06)

0.5.0 comes from the plugin's first use on real work, in another project, the
same day as 0.4.2. That run went as designed: the hook captured the sealed
ledger and it was valid on the first reply. Three things about it were not good
enough. It took fourteen minutes, 2 min 44 s for the criteria and 9 min 12 s
for the verifier. Its report said that all four criteria had passed and did not
show them. And it verified under a reading of the request in which one sentence
was the user's decision, when on the other reading no change had been asked
for yet; that point was recorded as an ordinary ambiguity, and since every
criterion passed it was never put to the user.

The release changes five things. The criteria agent may mark one ambiguity to
be asked before verifying. The validator prints the ledger. Both agents pin
their effort, and the criteria agent its model. The selector prefers the
fastest model the benchmark has timed. And the selector answers in one call.

Five questions had to be answered before release. Is a run faster and cheaper?
Does Claude Code honour the pin at all? Are the verdicts the same? Is the
question asked where it should be, and only there? Can the printed ledger be
made to say something the verifier did not?

All model calls are Sonnet 5.5 unless a table says otherwise; cost is at list
price, as the CLI reports it. The benchmark runs and the stage-1 runs keep
every reply beside their report. The two timing checks of section 1 do not:
their numbers were read from the sessions' result envelopes, which were in a
temporary directory and are gone.

## 1. Time and cost

### One task, before and after

A headless session on Opus 5.5 at maximum effort (`claude -p --plugin-dir DIR
--setting-sources local --model opus --effort max`) dispatched one plugin agent
in the foreground and waited for it. "Before" loads 0.4.3 and names the model
for both agents the way its skill did in the first real run: the most capable
candidate, Fable 5.1, with the agents inheriting the session's effort. "After"
loads this release, names no model for the criteria agent, and names the
selector's choice for the verifier. The task is the `ratelimit` fixture, with
the manifest of four criteria kept from 0.4.2's run, so both verifiers were
held to the same list. One run each.

| agent | | model | seconds | agent's tokens | of which output | agent's cost |
|---|---|---|---|---|---|---|
| criteria | before | Fable 5.1 | 104 | 10,601 | 7,147 | $0.401 |
| criteria | after | Sonnet 5.5 | 14 | 4,278 | 409 | $0.014 |
| verifier | before | Fable 5.1 | 176 | 62,038 | 9,155 | $0.683 |
| verifier | after | Sonnet 5.5 | 27 | 32,439 | 1,200 | $0.044 |
| both | before | | 281 | 72,639 | 16,302 | $1.08 |
| both | after | | 40 | 36,717 | 1,609 | $0.06 |

Seconds are the wall time of the session that dispatches the agent, so they
include that session's own two turns. Both verifiers' replies were captured by
the hook and validated from that copy, with the same result: `VALID: 4 criteria
(all 4 manifest criteria covered), final = DRIFTED — criteria 4 failed`.

This is the three changes together. "Before" ran on a more capable and more
expensive model as well as at a higher effort, and the table does not say how
much of the difference each accounts for. The next check does, for one of them.

### The effort pin by itself

`effort` in an agent's frontmatter is documented, but a field Claude Code does
not recognise there is ignored without a word, so the pin had to be seen
working. Two copies of this release's plugin were made that differ in one
line: `agents/criteria.md` with and without `effort: high`. Both keep `model:
sonnet`. The same maximum-effort session on Opus dispatched the criteria agent
from each, with the same one-line request (`ratelimit`). Claude Code 2.1.292,
one run each.

| copy | agent's model, as billed | session seconds | agent's tokens | of which output | agent's cost |
|---|---|---|---|---|---|
| with `effort: high` | Sonnet 5.5 | 13.6 | 3,932 | 437 | $0.013 |
| without the line | Sonnet 5.5 | 130.0 | 19,361 | 15,863 | $0.162 |

The field is honoured for a plugin's agent, and so is `model`: the session ran
on Opus and the agent's usage was billed to Sonnet in both copies. Effort alone
is a factor of 36 in output and 12 in cost on stage 1, with no change of model.

### The controlled set, at the effort the agents now pin

The harness passes `--effort high` from this release on, to match the agents.
The 0.4.2 run of the same set, earlier the same day, passed no effort and so
ran at the CLI's default for the model.

| run | effort | expected verdict | valid on the first reply | asked before verifying | median seconds, stage 1 / stage 2 | cost |
|---|---|---|---|---|---|---|
| controlled, two-stage, n=16 ([report](2026-10-06-cli-claude-sonnet-5-5-two-stage-v050.md)) | high | 16/16 | 16/16 | 0 | 6.8 / 12.5 | $1.46 |
| adversarial, two-stage, n=3 ([report](2026-10-06-cli-claude-sonnet-5-5-two-stage-v050-adversarial.md)) | high | 3/3 `DRIFTED` | 3/3 | 0 | 5.5 / 16.9 | $0.27 |
| 0.4.2, controlled ([report](2026-10-06-cli-claude-sonnet-5-5-two-stage-v042.md)) | CLI default | 16/16 | 16/16 | | 4.0 / 11.6 | $1.27 |
| 0.4.2, adversarial ([report](2026-10-06-cli-claude-sonnet-5-5-two-stage-v042-adversarial.md)) | CLI default | 3/3 `DRIFTED` | 3/3 | | 5.3 / 14.7 | $0.29 |

Two things follow. The verdicts are unchanged with the new rules for the
criteria agent, and none of the 19 requests got a question before verifying.
And the pin is a ceiling and a floor, not a speed-up for everyone: a session
that was not set above the default now gets agents that are a little slower,
and on the controlled set 15% dearer, than before. The registry's `verify_seconds` for Sonnet
5.5 is the 12.5 s measured here.

### The request this release was built from

The release's own request is the plugin's second real one: a paragraph of
context and three parts, 3,446 characters. It was put through stage 1 twice.

| | model | effort | seconds | tokens | criteria |
|---|---|---|---|---|---|
| the agent of 0.4.2, dispatched in a desktop session at maximum effort | Sonnet 5.5 | inherited: maximum | 307 | 50,293 | 15 |
| this release's rules, `claude -p --safe-mode --effort high`, three runs | Sonnet 5.5 | high | 16 to 18 | 7,698 to 8,181 | 9 to 11 |

The two rows are not one experiment: the first ran inside the desktop app with
that session's instructions loaded, the second headless with none. They agree
with the table above about where the minutes go.

## 2. Is the question asked where it should be?

Stage 1 alone, no code and no verifier
([report](2026-10-06-ask-first-claude-sonnet-5-5.md), every reply kept beside
it). `benchmark/ask_first_cases.json` holds 17 requests written for this
release, each run three times because the same request does not always get the
same answer, and the benchmark's own 26 requests were each run once.

| requests | runs in which the question was marked | wanted |
|---|---|---|
| may not ask for a change at all: a question, a request for an explanation, a choice not yet made (7) | 21/21 | all |
| ask for a change in the form of a question, a wish or a stated rule (9) | 0/27 | none |
| a careful reader could take either way (1) | 1/3 | not scored |
| the benchmark's own, plainly asking for a change (26) | 0/26 | none |
| no valid manifest after the one retry | 0 | 0 |

78 calls, $1.43, 6.3 s a call at the median.

**This is a fit, not a held-out score.** The 17 requests were written by the
author of the rules, and the rules were revised twice after seeing misses on
them:

| rules | may not ask | ask as a question, wish or rule | either way | benchmark's own |
|---|---|---|---|---|
| first | 17/18 | 0/18 | 0/3 | 2/26 |
| second: a requirement stated as a rule or a fact is a request | 16/18 | 0/24 | 0/3 | 0/26 |
| third, released: the point hides in a request of several parts | 21/21 | 0/27 | 1/3 | 0/26 |

- The first rules marked two of the benchmark's own requests, the ones that
  state a rule as a fact ("A username is valid if ..."). Asking "did you want
  this built?" about those would bring back a question before every run. A
  sentence and two requests of that kind were added.
- One request, the shape of the first real run (asked to choose a fix, the
  user answers "first explain what is going wrong", then writes a sentence
  that may be the decision), was marked in 2 runs of 3 and then 1 of 3. A
  sentence about requests of several parts was added, with two new requests to
  see whether it carries: the same shape with different words (marked 3 of 3)
  and the same shape with the choice made (0 of 3).
- No change was made after the third run. Whatever it showed was going to be
  reported.

The raw replies of the first two runs were not kept; their reports gave the
numbers above. Three checks were not fitted: the two requests added with the
last revision, the benchmark's own 26, and the request this release was built
from. That last one has a question back in place of a choice ("what would
effective changes") and then a plain choice, and its expected answer, not
marked, was written down before it was run. It was not marked in 3 runs of 3.

**A label written after seeing the answer is not a measurement.** The first
look, one run of six requests, missed one. The request was the one a careful
reader could take either way: it had been labelled "must ask", and a second
run of it gave the other answer. It is now labelled as what it is, reported
and not scored.

## 3. Can the printed ledger be made to lie?

The validator now prints what the session is told to show the user, so
whatever reaches that block reaches the user as the validator's word. A model
other than the one that wrote the code (Sonnet 5.5; the code is by Opus 5.5)
was given the two additions, the threat and what was already known, and asked
for a line of the report that a program's output or a verifier's text could
forge, and for a marked ambiguity that gets through when it should not. It
wrote and ran its own probes outside the repository.

What held:

- The body of the printed ledger: 12,876 systematic and 9,000 random replies,
  with line breaks of every kind, escape codes and the validator's own labels
  in every field. No line of the body started with anything but what the
  validator put there, and none held a character without a glyph.
- The rule for the marked ambiguity (at most one, it must name criteria, and it
  survives the round trip into the manifest and back): 471 cases.
- No crash, including values nested thousands deep.

What it found, all fixed and each pinned by a test:

| | Finding | Now |
|---|---|---|
| 1 | The conclusion on the `VALID:` line was printed as the verifier wrote it. Escape codes in it wiped the line on a terminal and drew `final = MATCHES INTENT` above a ledger that said `FAIL`; in a text ledger a Unicode line separator did the same for a reader that splits on it | the conclusion goes through the same filter as the evidence |
| 2 | `--check-manifest` printed questions and assumed readings as written, so an `AMBIGUITY:` could be redrawn as `ASK FIRST:` and the other way round | filtered |
| 3 | A marked ambiguity whose question showed nothing (a zero-width space, a NUL, a filler character) was accepted | a defect |
| 4 | Combining marks were printed however many there were; a pile of them is drawn over the neighbouring lines | two at most |
| 5 | A value of megabytes was flattened whole in order to show 300 characters of it | only the start is worked on: 9 MB in 0.16 s |

Its reproductions and both of its fuzzers were run again on the final code: the
reproductions are all neutralised and the fuzzers report no problem.

## 4. The release, checked against its own request

`/intent-verify` was run on this change in the session that made it, with the
installed plugin. The request has no subject of its own ("ok lets work on
it ..."): "it" is an offer in the assistant's previous message. The frozen
request therefore carries that paragraph, copied from the transcript and
labelled as not the user's words, ahead of the three captured parts.

| | round 1, 2026-10-06 | round 2, 2026-10-07 |
|---|---|---|
| criteria | 15 from the criteria agent, each with a quote, no ambiguity | the same manifest |
| verifier | Sonnet 5.5, FULL | Sonnet 5.5, FULL |
| ledger | captured by the hook, valid on the first reply | captured by the hook, valid on the first reply |
| verdict | `MATCHES INTENT`, 15 of 15 | `MATCHES INTENT`, 15 of 15 |
| the verifier's work | 36 tool calls, 176,220 tokens, 12 min 18 s | 40 tool calls, 220,832 tokens, 15 min 23 s |

Both rounds ran with the agents of the installed release, which inherit the
session's effort, here the maximum. The quarter of an hour is the cost this
release removes, not one it has.

### What round 1's observations said that its verdict did not

- **Criterion 14, "for complex changes the selector still picks the top-tier
  model", passed on one reading only.** Read as "T1", it held. But a complex
  change written by Opus got Sonnet 5.5 like any other, because Fable 5.1 has
  no score to rank by, and `--prefer capable` changed nothing. The option the
  maintainer had chosen said "Sonnet instead of Fable when Opus wrote the
  change ... Complex changes still require the top tier". A registry row may
  now name the listed model an unscored one ranks just above; Fable 5.1 is
  placed above Sonnet 5.5 and below Opus 5.5, where its predecessor stood, and
  the selector says when a pick rests on that. Both readings now hold.
- **The printed ledger cut those observations at 800 characters.** They were
  4,536 long and the cut fell inside the caveat above. Of the 57 version 2
  ledgers kept, only the two from real sessions exceed 800 (939 and 4,536);
  no benchmark ledger exceeds 530, which is how the limit had looked right.
  Observations are now printed up to 6,000 characters.
- Rewriting a test for the first of these showed that a candidate the registry
  does not list was counted as another vendor's model and preferred over
  every listed one. Fixed.

Round 2 ran on the tree with those three changes, against the same request
and the same 15 criteria. Its ledger printed with 3,476 characters of
observations, whole.

### What both rounds say, and no change answers

- **Criteria 1 to 5 and 8 are about what a session does when it follows the
  skill.** The verifier was told to start no session, since each is a paid
  model run. Those criteria rest on the skill's text, quoted with line
  numbers, and on what was run: the validator prints `ASK FIRST` for a marked
  ambiguity and rejects a second one, one that names no criterion, and a mark
  that is not a boolean. The second verifier put it plainly: if an observed
  session is required, those criteria are `NOT-EXERCISED` and the verdict is
  `INCONCLUSIVE`.
- **Criterion 15 says more than the request did.** It reads "neither agent is
  set to skip" CLAUDE.md. The criteria agent has skipped it since 0.3.0 and
  this change does not touch that. Both verifiers judged the criterion against
  the user's words, "leaves CLAUDE.md loading as it is", passed it, and said
  that read literally it fails because of the criterion and not the change.
  A criteria agent that cannot see the code assumed a starting state.
- **A long output is cut from its start.** In round 2's own test a
  1,197-character test log was shown as far as its eighth test, and the
  closing `OK` was cut. The reply file has it whole; the printed block does
  not show the end. Not changed in this release.
- **Only the `MATCHES INTENT` form of "the verdict states the reading" is
  spelled out** in the skill. For the other two verdicts the report is told to
  say that the question could not be asked.

The frozen request and the manifest were rebuilt on the second day, after a
restart emptied the directory they were in: the same three captured entries,
the same context paragraph and the criteria agent's reply. Round 1's ledger,
which the hook had filed elsewhere, validates against the rebuilt manifest
with all 15 criteria covered.

## What this does not show

- **How much faster a real run is.** The before-and-after is one run of one
  small module. The first real run took fourteen minutes; nothing here repeats
  that run with this release.
- **That the fastest model is as good as the most capable one.** Both returned
  the same verdict on the one task where both ran. The benchmark's sets are at
  their ceiling for Sonnet 5.5, so they cannot show what a stronger verifier
  would catch on a harder change. `--prefer capable`, or calling the change
  complex, selects the most capable; for a change written by Opus that is
  Fable 5.1, on the registry's assumption about a model with no published
  score, and nothing here ran it as a verifier with the effort pinned.
- **That high is the right effort.** The CLI's default and high gave the same
  19 verdicts. Maximum was never run on the sets, and nothing compares a lower
  pin on harder work.
- **The pin in the desktop app, and the environment variable.** The pin was
  seen headless. The documentation says `CLAUDE_CODE_EFFORT_LEVEL` overrides
  an agent's own effort; that was not tried.
- **The question on requests nobody here wrote.** One real request, and 17
  written by the author of the rules. How often real users write something that
  may not ask for a change, and how often the agent marks it, is not known.
- **Other models for stage 1.** The criteria agent is pinned to Sonnet, and
  only Sonnet 5.5 was run.
- **That a session follows the new step.** The skill tells the session to ask
  before dispatching the verifier and to show the printed ledger as it is.
  Tests pin the text; no session was run to see it obeyed.
