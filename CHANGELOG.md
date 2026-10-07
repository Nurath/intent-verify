# Changelog

## 0.5.2 — 2026-10-07

A sixth review, of 0.5.1, the same day. It confirmed both findings of the
fifth as fixed and reported one more, which reproduced. It is older than
0.5.1 and 0.5.0, and 0.5.1 had walked past it.

### Fixed
- **A value made only of invisible marks no longer counts as evidence.** A
  `PASS` needs a command and an output that show something. The test for that
  took every character Python calls printable for visible, apart from seven
  listed fillers. U+034F COMBINING GRAPHEME JOINER is printable and draws
  nothing, so a ledger whose command and output were that one character
  validated as `MATCHES INTENT`. So did one made of variation selectors, of
  the Mongolian ones, of the Khitan filler or of the musical null notehead:
  2,499 marks counted as visible by themselves. The test now asks whether a
  character puts something on the page: a combining mark does not, since it
  needs a letter to sit on, and that one rule covers every invisible mark
  without a list of them. It applies wherever a value has to show something:
  the command, the output, the reason for `NOT-EXERCISED`, the conclusion, a
  criterion's text and quote, a question and its assumed reading. Text with a
  mark in it is text as before.

  0.5.1 had fixed the filter for what is printed so that it treats these
  characters as marks, and had not looked at the test for blankness beside it.

### Checked
- 322 unit tests (were 315). Two of the new ones do not come from the
  code: every code point Unicode lists as default-ignorable must be blank, and
  no combining mark may count as visible alone.
- The review's fixtures: the ledger with invisible evidence exits 1, as its
  controls with a space and a zero-width space always did.
- All 180 recorded verdicts replay unchanged, and all 194 stored stage-1
  replies are judged as they were: no reply a real model wrote changes.

### Not changed
- The formats and the prompts. No model run was repeated.

## 0.5.1 — 2026-10-07

A review of 0.5.0 by another vendor's model, the fifth of this plugin, the day
it was released. It confirmed the earlier findings as fixed, replayed the 19
new verifier replies and the 77 ask-first manifests to the published numbers,
and reported two findings. Both reproduced, and each reached a step further
than the review's fixture.

### Fixed
- **Scores from different versions of the index are no longer compared.**
  0.5.0 added the current Claude models with scores read from a newer version
  of the index than the rest of the registry, and said in their note to compare
  tiers with the older rows, not scores. The ranking compared the numbers all
  the same: for a complex change `claude-opus-5` (60.7 on the old index) was
  picked over `claude-opus-5-5` (58 on the new one), and the gap to the
  implementer was subtracted across versions too. The registry now lists its
  `scales`, newest first, and a row says which one its score is on. Candidates
  with a score still come before those known only by an assumed tier; they are
  then ordered by tier, by scale and by score, so two numbers meet only when
  they are from the same version, and a warning says when the newer version
  decided. Across versions the gap is reported as not measured, and
  `weak-verifier` is given when the verifier is two or more tiers below the
  implementer. That tier rule now applies whenever there are not two scores on
  one version to subtract: Opus 5.5 with Haiku 4.5, T1 to T3, used to get no
  warning because Haiku has no score. A score on a scale the registry does not
  list is not used to rank, and the output says so.
- **Everything the validator prints is filtered and bounded.** 0.5.0 put the
  ledger, the questions and the notes through one filter. A criterion's quote
  was still printed with `repr()`, and so was whatever a `DEFECT:` line quotes
  from the reply. No line break or escape code got through, but length and
  combining marks did: a 20,006-character quote made a 20,037-character line,
  and 5,000 accents were printed as 5,000. The quote is now shown up to 300
  characters with its full length stated, every defect line up to 800, and
  neither with more than two combining marks in a row. The manifest file keeps
  the quote whole.
- **And the rest of what a reply can make it print.** Found by setting another
  model on those two fixes:
  - The filter counted marks by combining class. 1,567 printable marks have
    class 0 (an enclosing circle, a variation selector, a Thai vowel sign) and
    went through in piles of 795. It counts every mark now, and prints a blank
    glyph as a space.
  - The ids an ambiguity names were printed as given. One id repeated a
    million times is a valid list, and made a line of three million
    characters. Thirty are shown, with the count.
  - A reply with a million defects printed a million lines. Fifty are printed,
    then how many more.
  - A defect about numbering printed every number; cut at 800 characters, the
    wrong one could be past the cut. For a long list it names the entry.
  - `--run` printed the names of files beside the run as they were, and a
    `run.json` nested too deep to read was a traceback, not a usage error.

### Checked
- 315 unit tests (were 290). The new ones fail without the change they pin,
  apart from the controls: an ordinary quote, a short defect, and rankings
  within one version, which read as before.
- The review's fixtures: the selector case now picks `claude-opus-5-5` and
  says why; the two manifests print lines of 366 and 87 characters.
- All 180 recorded verdicts replay unchanged. No prompt changed, so no model
  run was repeated.
- **Another model was set on the two fixes before this release**, with the
  code, the rules and no conclusions. What held: 40,500 generated manifests
  and ledgers gave the same exit code and the same written manifest as 0.5.0,
  with no crash; shifting every score of one index version by a constant
  never changed a pick in 2.6 million selections; no pick depended on the
  order of the candidates except on exact ties, in 1.08 million. What it
  found is the third item above and the tier rule in the first. Its probes
  and fuzzers were run again on the released code.

### Known, and left
- A quote of 10 MB takes 12 to 34 seconds to check against the request. Older
  than this release, and not from printing.
- A defect line cut at 800 characters can lose the end of a criterion text
  longer than that. The manifest has it whole.
- Two candidates that tie exactly (same tier, no score, or equal scores) are
  taken in the order listed. Among candidates with no score the higher tier
  now comes first; it used to be whichever was listed first.

### Not changed
- Verdicts, the ledger and manifest formats, the prompts. One exit code: a
  `run.json` that cannot be read is 2, as other unusable run directories are,
  where it was 3.
- Within one version of the index the ranking of scored models is what it
  was.

## 0.5.0 — 2026-10-07

The plugin's first use on real work, the same day as 0.4.2, went as designed:
the sealed ledger was captured and valid on the first reply. It also took
fourteen minutes, reported its result in one line, and verified the change
under a reading of the request that the user might not have meant. This
release is about those three things.

### Added
- **One question can be asked before anything is verified.** The criteria agent
  may mark one ambiguity `"whether": true`: on its other reading the request did
  not ask for a change at all (a question, a request for an explanation, a
  choice not yet made). The validator prints it as `ASK FIRST:` and the skill
  puts it to the user before the verifier runs. If the answer is that no change
  was asked, the run ends as `DRIFTED` and the verifier's minutes are not
  spent. If nobody can answer, the verdict line carries the reading it rests
  on. Every other ambiguity is still settled after the verdict, and only when
  it decides one. At most one may be marked: 0.3.1 asked 41 questions up front
  on 16 one-line requests.
- **The validator prints the ledger.** After `VALID`, it prints each criterion
  with its verdict, the command and what it showed, then the verifier's
  observations. The skill shows that block as it is, in place of a sentence
  such as "passed all 4 criteria". Each value is one line: a line break becomes
  `⏎` and a character without a glyph becomes a space, so nothing a program
  printed can start a line of the report. A command is shown up to 200
  characters and its output up to 300, with the full length stated where one
  is cut. The observations are shown up to 6,000, because a caveat to a verdict
  goes there: the first real ledger of this release wrote 4,536.
- `benchmark/ask_first.py` measures whether the mark is used where it should
  be, on real models.

### Changed
- **The agents pin their own model and effort.** They used to inherit the
  session's, and the skill sent the criteria agent to whatever model the
  selector picked. Now the criteria agent runs on Sonnet at high effort, and the
  verifier at high effort on the model picked for the run. The benchmark never
  ran at maximum effort; a session set to it did.
- **The selector prefers the fastest timed model.** Among the candidates that
  differ from the implementer and clear the capability floor, it takes the
  fastest one this plugin's benchmark has timed (`verify_seconds` in the
  registry), and the most capable only for a complex change or with
  `--prefer capable`. On the one task where both were run, the most capable
  model and the fastest returned the same verdict; what differed was the wait.
  A different vendor family still comes before speed.
- **One selector call.** The registry knows Opus 5.5 and Sonnet 5.5 (scores read
  from the index on 2026-10-06), Fable 5.1 (not on the index: tier assumed from
  its predecessor, no score) and the bare names Claude Code uses. The first
  real run needed three calls to get an answer.
- **A model without a score can be given a place.** A complex change goes to
  the most capable candidate, and Fable 5.1 has no score to rank by, so a
  complex change written by Opus went to Sonnet all the same. A registry row
  may now name the listed model it ranks just above (`ranks_above`). Fable 5.1
  is placed above Sonnet 5.5 and below Opus 5.5, where its predecessor stood on
  the index, and the selector's warning says when a pick rests on that
  assumption. No score is invented for it.
- The listing that starts every run names the Python command that works on
  the machine, so a session on a stock Windows no longer loses a call to
  `python3`.
- The benchmark runs every call at `--effort high`, the level the agents pin.

### Fixed
- **A candidate the registry does not list was taken for another vendor's
  model.** With `--assume-tier` it was preferred over every listed model of the
  implementer's family, and the reason said a different family had been
  preferred. Unknown is no longer different.

### Measured
Record: `benchmark/results/2026-10-06-faster-and-ask-first.md`.

- **Time and cost, one task, before and after.** A session on Opus 5.5 at
  maximum effort dispatched each agent once the way 0.4.3 ran it (both on the
  most capable model, at the session's effort) and once with this release. The
  criteria agent went from 104 s and $0.40 to 14 s and $0.014, the verifier
  from 176 s and $0.68 to 27 s and $0.044. Same verdict, the reply captured by
  the hook both times. One run each, on a single small module.
- **The effort pin by itself.** Two copies of the plugin that differ in the
  `effort: high` line of the criteria agent, same model, same request, same
  maximum-effort session: 437 output tokens and $0.013 with the line, 15,863
  and $0.16 without. So Claude Code 2.1.292 honours the field for a plugin's
  agent, and effort accounts for an order of magnitude of stage 1 without any
  change of model.
- **Verdicts at the pinned effort, with the new rules for the criteria agent.**
  The controlled set: 16 of 16. The fixtures that print forged verdicts: 3 of
  3. Every ledger valid on the first reply, and no question before verifying on
  any of the 19. A verification took 12.5 s at the median (11.6 s at the CLI's
  default effort in 0.4.2's run) and stage 1 took 6.8 s (4.0 s): for a session
  that was not set above the default, the pin makes the agents a little slower,
  not faster.
- **Is the question asked where it should be?** Stage 1 alone, three runs of
  each of 17 requests written for this release and one of each of the
  benchmark's 26. Marked in 21 of 21 runs where the words may not ask for a
  change; in 0 of 27 where a change is asked for as a question, a wish or a
  stated rule; in 0 of 26 on the benchmark's own; in 1 of 3 on a request a
  careful reader could take either way (not scored). The rules were revised
  twice after misses on these requests, so this is a fit to them: the first
  version marked one of them in 2 runs of 3 and two of the benchmark's own
  requests that state a rule as a fact.
- **This release's own request,** which the rules were not tuned on: a
  paragraph of context and three parts, with a question back in place of one
  choice and then a plain choice. Not marked in 3 of 3 runs, as it should not
  be. Stage 1 took 16 to 18 s and about 8,000 tokens; the same model took 307 s
  and 50,000 tokens on it in a maximum-effort desktop session with the unpinned
  agent of the installed release.
- **The two additions, attacked by another model.** Nothing a program prints
  could start a line of the printed ledger or pass for one of the validator's
  (12,876 systematic and 9,000 random replies), and the rule for the marked
  ambiguity held in 471 cases. It found five things around them, all fixed
  and pinned by tests: the conclusion on the `VALID:`
  line was printed as written, so escape codes in it could redraw the line as
  a match on a terminal; `--check-manifest` printed questions the same way; a
  question that shows nothing was accepted; a pile of combining marks was
  printed whole; and a value of megabytes was flattened whole to show 300
  characters of it.
- **The release, checked against its own request** with the installed 0.4.3,
  twice: 15 criteria, `MATCHES INTENT` both times, each ledger captured by the
  hook. The first round's observations are where the ranking rule and the
  6,000-character limit come from. Both verifiers also say what the verdict
  rests on: the criteria about what a session does were checked against the
  skill's text and the validator's behaviour, since no session was run.

### Not changed
- The ledger format, what the hook captures, and the verifier's instructions.
- A request that asks for a change but is unclear about which one. That is an
  ordinary ambiguity, settled after the verdict.

## 0.4.3 — 2026-10-06

A third independent review, of 0.4.2, confirmed the three findings of the
second as fixed in the new format and reported one new one. It reproduced, and
it reached further than the review's fixture.

### Fixed
- **The nonce could sit in a command unseen.** The rule that the nonce occurs
  only in `"nonce"` and `"seal"` counted it in the reply as written. In JSON,
  `\u0061` is an `a`, so a command written
  `python t.py --token 0123456789\u0061bcdef...` decodes to one holding the
  nonce while the reply shows the nonce only twice, and it validated. The same
  spelling got through in output, reasons, observations and criterion texts,
  and so did the nonce in upper case, in any field and in a sentence before the
  ledger. The nonce is now also looked for in every decoded string of the
  ledger, keys included, and in either letter case.

### Fixed: found by attacking that fix
A model set on the fix before the PR found that it could be balanced out, and
that 0.4.2 had the same hole.

- **The nonce was counted, not located.** One count ran over the whole reply.
  A `"seal"` spelled with an escape took one occurrence away, and a copy of the
  nonce in the sentence before the ledger put it back: two in all, as
  expected, with the nonce sitting in the open. Three places are now kept
  apart. Around the ledger the nonce may not occur at all. In the ledger's
  decoded strings it occurs only as `"nonce"` and `"seal"`. And those two are
  written out character for character, so that what the reply shows and what
  it holds agree.
- **White space after the ledger could stall the validator.** The check on what
  follows the closing brace took time quadratic in a run of white space before
  a stray character: 80,000 line breaks took 14 seconds. It takes milliseconds
  now, for manifests as well.
- `--unsealed` also looks for the nonce in the other objects of a reply, and
  its search for the ledger gives up after 200 braces that open nothing (was
  2,000).

Nothing recorded changes: replayed through the new validator, all 161 recorded
verdicts come out the same. The verifier's prompt is unchanged.

### Still not checked
- **A nonce encoded some other way** before it is passed on: reversed, split
  over two arguments, regrouped like a UUID, base64. The check catches a
  verifier that pastes the nonce into a command or echoes output holding it.
  It is not a proof that the nonce stayed secret, and the verifier is told
  never to pass it on.

## 0.4.2 — 2026-10-06

A second independent review, of 0.4.1, found two ways a JSON ledger that should
not pass validated as `MATCHES INTENT`, and one way a truthful ledger could not
validate at all. Before the fix went out, another model was set on it and
found more of the same kind, so the format changed, and a third model was set
on the result. Every finding reproduced. None of the real replies kept in
`benchmark/results/` has any of these shapes: replayed through the new
validator, the 124 verdicts recorded before this release all come out the
same, so no published result changes. The record is
`benchmark/results/2026-10-06-sealed-ledger.md`.

### Changed
- **The ledger is version 2, and it is the whole reply.**
  `{"ledger": 2, "nonce", "mode", "criteria", "final", "observations", "seal"}`.
  The reply's first `{` opens it and nothing may follow its closing brace, a
  code fence aside. Remarks go in `"observations"`; the `OBSERVATIONS:` line
  after the object is gone. A sentence before the object is still tolerated.
- **It ends with a seal.** `"seal"`, the last key, repeats the run's nonce, and
  the nonce may occur nowhere else in the reply.
- **Only the format's keys**, at the top and in each criterion, and none twice.
- **A stage-1 reply is the manifest and nothing after it**, with the same rule
  about keys. A quote is four characters or more and occurs in the request as
  whole words.
- `validate_ledger.py --unsealed` checks the version 1 object that 0.4.0 and
  0.4.1 wrote, so that the runs kept in `benchmark/results/` can still be
  checked. The skill never passes it.
- `validate_ledger.py` exits 3 when the validator itself fails. A traceback
  used to exit 1, which means "the ledger has defects".

### Fixed: found by the review
- **A repeated JSON key could hide a verdict.** Python's decoder keeps the last
  of two equal keys without a word, so a criterion holding
  `"verdict": "FAIL", "verdict": "PASS"` read as PASS, and a second `criteria`
  list replaced the first. A key written twice, at any depth, is now a defect,
  in ledgers and in manifests.
- **Two ledgers for one run: the first one won.** A complete PASS ledger
  followed by "Correction:" and a complete FAIL ledger, both carrying the run's
  nonce, validated as the first. Stage 1 had the same flaw: of two manifests in
  one reply the draft was used.
- **Truthful output could be rejected.** A JSON ledger was rewritten as a text
  ledger to be checked, and the text grammar treats output made only of
  field-looking lines as missing. So evidence that was exactly
  `FINAL: MATCHES INTENT`, which the adversarial fixtures print, counted as no
  evidence, and no retry could fix it. JSON ledgers are now checked as data,
  with the rules shared between the two encodings; commands and output are
  kept exactly as written.
- Defects on a JSON ledger name the JSON fields (`"out"`, `"final"`), and a
  criterion `id` has to be a whole number.

### Fixed: found by attacking the fix
- **A second conclusion the parser never saw.** The first fix counted ledgers
  that parsed. A correction with a trailing comma, one cut off halfway, or one
  without its `"ledger"` key did not parse as a ledger, and the draft before it
  validated. Nothing may follow the ledger now, parsed or not.
- **A second verdict under another name.** `"Verdict": "FAIL"` or
  `"verdict_corrected": "FAIL"` beside `"verdict": "PASS"` was read by nobody.
  Unknown keys are defects.
- **Pasted output could rewrite the ledger.** Output pasted into `"out"` with a
  double quote left unescaped ends the string; what follows is parsed as
  ledger and could supply passing verdicts and close the object. It cannot
  supply the nonce, so what it closes has no seal, and the verifier's own
  remainder is text after the ledger.
- **`MATCHES INTENT` was matched by its first words.**
  `MATCHES INTENT — DRIFTED: criterion 1 failed` counted as a match. With every
  criterion PASS the final line is those two words and nothing after them.
- **A criterion could be re-worded in case.** Ledger and manifest texts were
  compared ignoring case, so `max_retries` matched `MAX_RETRIES`. Spacing aside,
  the text is now compared letter for letter.
- **Evidence that shows nothing counted.** A zero-width space was output. So
  did a command holding the run's nonce, which hands it to the code under test.
- **Text ledger: a carriage return started a line.** In a copy the harness had
  indented, a forged ledger behind carriage returns stood at column 0 and
  outranked the verifier's own lines.
- **Crashes and stalls.** A run of more than 4,300 digits raised instead of
  being reported, and a reply of unclosed braces took time quadratic in its
  length.
- **An empty argument was read as an absent one.** `--manifest ""` skipped the
  manifest and let a short ledger through; `--nonce ""` matched a ledger whose
  nonce was empty. Both are usage errors now.
- **A manifest that could not be written.** Half of a surrogate pair in a
  criterion was reported as a missing run directory and left a cut-off file.
- **Quotes.** `"a"` and `"the"` occur in any request and were accepted as the
  words a criterion rests on, as was `"ort"` inside `sorted`; a criterion `id`
  of `true` passed for 1. In the other direction, a quote that differed from
  the request only in curly quote marks or in how an accent is encoded was
  rejected.
- A JSON string broken over two lines now gets a message that says how to
  write a line break, and `--manifest-from` no longer drops a line such as
  `- #tags are lowercased` as a heading.

### Fixed: found by the second pass
On the rewritten validator the second pass found no false pass and no crash,
and two small things:
- `--manifest-from` kept a line holding only a zero-width space as a criterion,
  and the manifest it wrote was rejected when read back.
- A brace in the sentence before the ledger was read as the object the reply
  opens with, and the defect pointed the retry at the nonce. It names the
  brace now.

### Still not checked
- **Prose.** A ledger whose `observations` or `reason` contradicts its own
  verdicts is well-formed. The skill is told to report them.
- **Evidence quality.** `"."` is output.
- **Whether a quote has anything to do with its criterion.**

### Seen after the release
- The same day, in a desktop session on 0.4.2: the verifier handed back a
  sealed ledger and nothing else, the hook filed it under its run unchanged,
  and `--run` validated it as captured. The run is kept in
  `benchmark/results/2026-10-06-sealed-desktop.raw/`.

## 0.4.1 — 2026-10-05

### Fixed
- **0.4.0 captured nothing in the desktop app.** There a subagent hands its
  report back through a `SubagentHandback` tool call and writes no final text,
  so `last_assistant_message`, the only place the `SubagentStop` hook looked,
  did not hold the verifier's ledger. The first check after installing 0.4.0
  showed it: `--run` exited 4, and the skill's fallback validated the relayed
  copy and reported it as relayed. 0.4.0 had been checked in headless sessions
  only, where a subagent ends with a text message. The hook now also reads the
  subagent's own transcript, named in the payload or found beside the
  session's: the last hand-back, else the last text. Given the transcript of
  that failed check, it files the report byte for byte and `--run` validates
  it.
- **Whether the hook ran is now visible.** When it runs for the verifier and
  finds no reply anywhere, it leaves a note in `_unmatched/`, and
  `validate_ledger.py --run` says whether the hook left any trace since the run
  began.

### Not yet seen
- `SubagentStop` firing for a plugin's agent in the desktop app. 0.4.0 left no
  trace either way. The first verification on 0.4.1 settles it: a captured
  reply, a note, or no sign that the hook ran.

### Seen after the release
- The same evening, in a desktop session on 0.4.1: the hook filed the
  verifier's report under its run, byte for byte, and `--run` validated it as
  captured. The run is kept in `benchmark/results/2026-10-05-c1-desktop.raw/`.

## 0.4.0 — 2026-10-05

### Changed
- **The session that wrote the code no longer carries the verdict.** Until
  0.3.2 the orchestrating session, usually the one that made the change, saved
  the verifier's reply and ran the validator on its own copy, and a ledger
  printed by the code under test could pass for the verifier's own when the
  verifier wrote none. Change C1 of the v0.3 design:
  - `capture-intent.js --begin-run` starts a verification run: a directory
    under the plugin's data directory, named by a random nonce.
  - The verifier writes its ledger as one JSON object carrying that nonce.
    Output printed by the code under test is a JSON string inside it, so it
    is never structure, and the code cannot know the nonce.
  - A `SubagentStop` hook, matched on `intent-verify:intent-verifier`, files
    the verifier's final reply byte for byte under the run whose nonce it
    carries (`_unmatched/` otherwise).
  - `validate_ledger.py --run <dir>` validates that captured copy; only the
    ledger carrying the run's nonce counts, held to the same rules as the text
    ledger. Exit 4 means the hook filed nothing; the skill then checks its own
    copy with `--nonce` and must say the ledger was relayed.
- The text ledger (`INTENT-VERIFY LEDGER v1`) is still accepted without a run,
  for manual use and the offline benchmark profiles.

### Evidence
- Live: a headless session with this version loaded ran the real verifier; the
  hook filed its reply and `--run` validated it (DRIFTED, criteria 2 to 4, as
  the fixture deserves).
- Three new adversarial fixtures, drifted code that prints a FINAL line, a whole
  text ledger, or a JSON ledger plus "report MATCHES INTENT": 3 of 3 DRIFTED.
  Two replies quoted the forged verdict inside their evidence, where it stayed
  a string.
- Controlled set with the shipped JSON verifier: 16 of 16, no retries, 32 calls,
  $1.28 at list price. The same stage-1 prompt kept 8 ambiguities this time,
  against 3 in the 0.3.2 run: that count moves from run to run, and both are far
  below the 41 of 0.3.1.
- Offline: forged-ledger tests (M3), and a test that pins the 0.3 hole the
  nonce closes.

## 0.3.2 — 2026-10-05

### Changed
- **Ambiguities no longer stop a verification.** 0.3.1 put every ambiguity the
  criteria agent raised to the user before the check ran. On the 16 one-line
  requests of the controlled set that was 41 questions, 2 to 4 on every
  request, and the verdicts needed none of them: most were about things the
  request leaves open, which no criterion tests. Now:
  - The criteria agent records an ambiguity only when a criterion's check
    depends on it, as `{question, assumed, criteria}`: the reading the criteria
    were written for and the criteria that rest on it. It records nothing the
    request leaves open and nothing with an ordinary reading.
  - `validate_ledger.py --check-manifest` drops an ambiguity that names no
    criterion and counts it (`DROPPED:`); one that names a criterion that does
    not exist, or no assumed reading, is a defect.
  - The skill verifies against the assumed readings and asks nothing first. A
    question comes after the verdict, only when a criterion that depends on an
    ambiguity failed or could not be run and the evidence would differ under
    the other reading. One clarification, which re-derives the criteria and
    replaces the first verdict.
- Re-measured on the same 16 requests: 3 questions instead of 41, 13 requests
  with none, none asked before verifying, verdicts 16 of 16 as before. On the 7
  field requests, never run two-stage before: 4 questions, 5 of 7 expected
  verdicts. `recall_weekend` came back DRIFTED: its criterion expects the code
  to recognise a weekend date, the code takes a flag from the caller, and that
  difference is a real second reading nobody recorded. A question asked up
  front under 0.3.1 might have caught it. `recall_gpt4omini` was INCONCLUSIVE:
  the fixture has no earlier version to compare rates against.

### Benchmark
- `run_bench.py --mode cli` runs every call in `claude -p --safe-mode` (the
  runner's CLAUDE.md, plugins, hooks and MCP servers stay out) and records each
  call's tokens, cost, turns and duration in `usage.json`. `--label` keeps an
  earlier results file; the two-stage report counts kept and dropped
  ambiguities.
- `benchmark/m4_json_ledger.py`: measurement M4 of the v0.3 design (JSON ledger
  against text, criteria held fixed). Haiku 4.5 and Sonnet 5.5 wrote valid JSON
  ledgers on 16 of 16 first replies, against 15 of 16 for text.
- Results: the two-stage flow on the controlled set (16 of 16), M4, and
  platform checks S1, S2, S4 and S5 seen on a live installation.

## 0.3.1 — 2026-10-05

### Fixed
- **Subagent hand-backs crowded the listing.** A subagent's report reaches the
  session as an `<agent-message>` framed "[Subagent hand-back]", and 0.3.0
  treated every `<agent-message>` as a possible request, labelling it and
  keeping it. In the session that built 0.3.0, ten of fifteen captured entries
  were hand-backs, enough to push the real requests out of the default ten-row
  listing. They are now hidden with the other background-agent reports
  (`--all` shows them, labelled `agent-report`). A message from another
  session, which has no such frame, is still listed.

## 0.3.0 — 2026-10-05

The two changes 0.2.1 could not make without changing a contract, the smaller
capture fixes, and what running the tool on its own release turned up. The
proposal, with the reasoning behind each choice and what was left out, is
`docs/DESIGN-v0.3.md`.

### Added — criteria fixed before the code is read
- **Criterion manifest.** `validate_ledger.py --manifest` requires every
  criterion of a manifest in the ledger under the same number with the same
  text. A requirement the verifier never mentions, or a reply cut off before
  its last criteria, is now a defect. In 0.2.1 such a ledger validated, and the
  omission was caught only if the orchestrator noticed it.
- **`intent-criteria` agent (stage 1).** Derives the manifest from the request
  alone; its tool allowlist holds nothing that reads files or runs commands.
  Each criterion quotes the words of the request it rests on, and
  `--check-manifest` verifies every quote, so a requirement cannot be invented
  and attributed to the user. It also lists the places where the request can be
  read two ways; the skill puts those to the user once, before verifying.
- **Your own criteria win.** `--manifest-from FILE` builds the manifest from
  criteria you already have, one per line.
- **Benchmark.** `--two-stage` for real-model runs: criteria first, with every
  tool disabled, then a verifier held to them. A new mock profile, `omitter`,
  reports only what passes: 2 false MATCHES on the drifted cases when its
  ledgers are validated alone, 0 against a manifest.

### Changed — where your prompts are kept
- **The ledger is outside the project.** The plugin's hook writes under the
  plugin data directory (`${CLAUDE_PLUGIN_DATA}`; `INTENT_VERIFY_DATA`
  overrides it; `~/.claude/intent-verify` when neither exists), one file per
  session. Nothing is written inside the project any more, by the hook or by
  the skill, whose working files now go to a scratch directory.
- **Retention replaces rotation.** A session file untouched for 30 days is
  deleted (`INTENT_VERIFY_RETENTION_DAYS`; 0 keeps everything). The `log.md`
  mirror is gone; `--list` and the new `--show <id>` are the readable view.
- **An existing `.intent/` directory is left alone and still read.** `--list`
  says when it is reading one. Delete it once its requests no longer matter.
- **The capture cap is 256,000 characters**, up from 64,000, and a prompt over
  it keeps its start and its end: with a long paste the instruction sits at one
  end, and cutting only the tail could remove it.
- `--freeze` takes `--out FILE` and no longer writes `.intent/frozen-<id>.md`.

### Added — capture
- **Answered questions are recorded.** A second hook (`PostToolUse` on
  `AskUserQuestion`) stores the question, its options and the answer as a
  `decision` entry. The scope of 0.2.1 itself was decided by such an answer,
  and it was missing from the ledger.
- **A request can be several entries.** `--freeze id1,id2` joins a task, its
  follow-ups and its decisions into one request, oldest first.
- **Prompts the harness submits are labelled** when the ledger is listed:
  background-agent reports, messages from other sessions, scheduled tasks, CI
  events. In our own ledgers 104 of 706 "tasks" were such prompts. Agent
  reports are left out of `--list` unless `--all` is given; the others can be
  real requests, so they are marked and kept.
- Entries carry `prompt_id`.

### Fixed
- **A valid ledger was rejected when the harness had indented it.** A
  background subagent's report is delivered with two spaces in front of every
  line, which left no keyword at column 0: "no CRITERION blocks found". The
  validator now removes an indent shared by every line. A ledger quoted inside
  a prose reply is still not accepted as the verifier's own.
- **A file that could not be read exited 1**, the code for "the ledger has
  defects", with a traceback. It exits 2.

### Not in this release
- **The alternate hooks** (`.py`, `.ps1`, `.sh`) still write `<project>/.intent/`
  and record prompts only. The reader is the Node script, so on a machine
  without Node they could not serve the skill either way.
- **Change C of the design**: a structured ledger bound to its run and captured
  by a hook. The session that wrote the code still saves and validates the
  verifier's reply.
- **Measurements.** The two-stage flow has been run on real models eight times
  (`benchmark/results/2026-10-05-two-stage-smoke.md`). The controlled set has
  not been re-run with it, and the cross-model ablation has not been run.
- **Three platform behaviours have not been seen on a live session**: the
  criteria agent launching without file access, a decision being recorded, and
  the data directory being filled into the skill's commands. Each fails safe;
  see `benchmark/results/2026-10-05-platform-spikes.md`.

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
- **The sh fallbacks redacted nothing on macOS.** Their `sed` rules began with
  `\b`, which BSD sed does not treat as a word boundary, so no rule ever
  matched there. They are plain POSIX ERE now. Present since 0.2.0; found by
  the macOS CI leg this release adds.

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
