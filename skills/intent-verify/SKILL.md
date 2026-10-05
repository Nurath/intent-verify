---
name: intent-verify
description: >
  Independent second-opinion check that an AI-written change did what the USER
  ORIGINALLY ASKED — not just "tests pass" and not what the diff claims. Freezes
  the original request, has acceptance criteria fixed by an agent that cannot
  see the code, then dispatches a fresh-context verifier (ideally a different
  model) that exercises the running code per criterion and requires captured
  evidence. Catches "confidently built the wrong thing" / intent drift that
  diff-anchored review misses. Use after an agent completes a non-trivial
  change, before commit, or when the user says "verify this did what I asked",
  "intent-verify", "did it actually do what I wanted".
argument-hint: "[file with your own acceptance criteria]"
license: MIT
---

# intent-verify

A change can pass tests, typecheck, and a diff review and still be **the wrong
thing built correctly.** Diff-anchored review inherits the implementer's
misunderstanding: it reads the code plus the code's own description, so a mean
labelled "central value" reads fine. This skill checks the change against the
**user's original words**, with fresh eyes.

## The three design decisions (each survives a specific failure mode)

Each one answers a specific way a reviewer ends up agreeing with the author:

1. **Different model for the verifier.** A blind spot in the weights survives a
   fresh context, so a same-model judge can share the author's misreading.
   Dispatch the verifier on a different model than the implementer whenever one
   at or above the capability floor exists; step 3 covers the fallback. (A
   design argument: the benchmark never compared it with a same-model check.)
2. **Criteria before code.** The acceptance criteria are fixed by an agent that
   is given the request and has no tool to read the project. Whoever has seen
   the code — you, or a verifier with a shell — tends to write criteria the
   code already satisfies. The verifier is then held to that list mechanically.
3. **Evidence required for every PASS.** No criterion is PASS without captured
   runtime evidence (the command run + its actual output). "Looks right" is the
   exact failure we're catching; a judge that rationalizes is worthless.

"Different model" alone is not enough: a verifier far below the implementer's
capability fails in its own ways (skipped steps, fabricated evidence, broken
ledger format). Capability-aware dispatch below closes that gap.

## Procedure

The bundled helpers live in the plugin, not in the project being verified, so
call them by absolute path: `${CLAUDE_PLUGIN_ROOT}` is this plugin's install
directory. The Python helpers need `python3`, or `python` where `python3` is not
installed (stock Windows).

**Nothing in this procedure is written inside the project.** Keep a run's
working files — the frozen request, the manifest, the replies — in a scratch
directory of your own: your session's scratchpad directory if you have one,
otherwise a new directory under the system temp directory. It is `<scratch>`
below.

1. **Freeze intent.** The ground truth is what the user asked for, verbatim —
   trust it over the diff, comments, or the commit message.
   - List what this session's user asked for. The output is one compact line
     per entry, so long prompts are not loaded into your context:

     `node "${CLAUDE_PLUGIN_ROOT}/hooks/capture-intent.js" --list --data "${CLAUDE_PLUGIN_DATA}" --project "${CLAUDE_PROJECT_DIR}" --session "${CLAUDE_SESSION_ID}"`

     The ledger lives outside the project, one file per session; `--limit N`
     shows more. A ledger that 0.2.x left inside the project is read as well.
   - **Selection rule:** pick the entries that *define* the work under
     verification. That is the `task` that started it — often not the newest
     entry — plus anything later that narrowed or changed it: a follow-up
     prompt, or a `decision` (a multiple-choice question the user answered).
     Leave out `verify-invocation` entries; they ask for this skill to run.
     Entries labelled `agent-message`, `scheduled-task` or `ci-monitor-event`
     were submitted by the harness, not typed. One of them can still be the
     request (a scheduled task, an instruction relayed from another session, a
     CI event that asked for a fix), so they are labelled, not hidden.
     Background-agent reports are never requests and are left out; `--all`
     shows them.
   - If you had to choose between plausible candidates, or the listing reports
     NO entries for this session, show the candidates (id + first line) and ask
     the user to pick. Otherwise just say which entries you used.
   - A `capture-incomplete` entry is a prompt that was too large to record. If
     one is newer than your candidate, the real request may be the missing one:
     ask the user instead of silently verifying against an older task.
   - Freeze the chosen entries into one file:

     `node "${CLAUDE_PLUGIN_ROOT}/hooks/capture-intent.js" --freeze <id>[,<id>...] --out "<scratch>/request.md" --data "${CLAUDE_PLUGIN_DATA}" --project "${CLAUDE_PROJECT_DIR}"`

     One id gives that prompt verbatim; several are joined oldest first. **Exit
     code 3 (`"truncated": true`) means the stored text is incomplete** — a
     part was longer than the capture cap. Recover the full text (ask the user
     to paste it; `transcript_path` in the metadata names the session
     transcript that holds it) and overwrite the frozen file. If you cannot,
     the verdict is capped at `INCONCLUSIVE — original request was truncated
     at capture`: a change cannot be shown to match a request nobody has in
     full.
   - No ledger, or no `node`? Ask the user to paste the original request and
     save it as `<scratch>/request.md`. Do not reconstruct it from memory or
     from the diff — that reintroduces the blind spot.
2. **Fix the criteria (stage 1).** Do this before anyone exercises the code,
   and do not write them yourself unless you have to.
   - **The user already has acceptance criteria** (a file, a spec section, a
     list in the request): those win. Put them one per line in a file and run

     `python3 "${CLAUDE_PLUGIN_ROOT}/tools/validate_ledger.py" --manifest-from <file> --out "<scratch>/manifest.json"`

   - **Otherwise** dispatch the `intent-criteria` subagent, on a model chosen
     as in step 3, with the frozen request text inline and nothing else: no
     path, no diff, no description of the change. Save its reply exactly as
     returned to `<scratch>/criteria-reply.txt` and check it:

     `python3 "${CLAUDE_PLUGIN_ROOT}/tools/validate_ledger.py" --check-manifest "<scratch>/criteria-reply.txt" --request "<scratch>/request.md" --out "<scratch>/manifest.json"`

     Exit 1 lists defects (an invented quote, a skipped number): re-request
     **once** naming them.
   - **`AMBIGUITY:` lines** name a point where the request has two readings,
     the reading the criteria were written for, and the criteria that depend on
     it. Do not stop to ask: verify against the assumed readings, and settle
     them in the report (step 7). The check has already dropped every ambiguity
     that no criterion depends on (`DROPPED:`), since no answer to it could
     change the verdict.
   - **`NOTE:` lines** are parts of the request that no criterion quotes. They
     may be context or a requirement the deriver skipped; carry them into your
     report so the user can tell.
   - **Fallback.** If the subagent cannot be dispatched, or there is still no
     valid manifest after the one re-request, write the criteria yourself, one
     per line, and build the manifest with `--manifest-from`. Say in the report
     that the criteria were *not* fixed independently: you wrote them knowing
     what was built.
3. **Select the verifier model** (capability-aware — see the table below):
   different model than the implementer, at or above the capability floor for
   the change, preferably a different vendor family. Record the choice. If only
   below-floor models are available, say so and fall back to same-model
   fresh-context verification with a stated caveat — a capable same-model check
   beats an incapable cross-model one, but note that the cross-model lever was
   lost. `python3 "${CLAUDE_PLUGIN_ROOT}/tools/select_verifier.py"` automates
   this against the bundled `models/registry.json`.
4. **Dispatch the verifier (stage 2)** — the `intent-verifier` subagent, on the
   selected model — handing it only `{the frozen request text, the manifest's
   criteria as MANIFEST, the code/app, mode}` and NOT the implementer's
   reasoning. Set `mode: FULL` for tier T1/T2 verifiers, `mode: STRUCTURED` for
   T3 (simpler protocol, fill-in template).
   - **More than 5 criteria and only a T3 verifier?** STRUCTURED mode exercises
     at most 5. Use a T1/T2 verifier, or dispatch one batch per 5 criteria,
     each time naming which to exercise, and combine: any FAIL ⇒ `DRIFTED`;
     every criterion PASS in some batch ⇒ `MATCHES INTENT`; otherwise
     `INCONCLUSIVE`.
5. **The verifier exercises each criterion** by running the code to the surface
   where the change executes, and records: `PASS` (with evidence) / `FAIL` (with
   evidence) / `NOT-EXERCISED` (with reason it couldn't reach it). It works
   read-only and within a bounded execution budget.
6. **Validate the ledger before trusting it.** Save the verifier's reply exactly
   as returned to `<scratch>/ledger.txt` — without any frame the harness put
   around a subagent's report, and without tidying; a uniform indent is fine —
   and check it against the manifest:

   `python3 "${CLAUDE_PLUGIN_ROOT}/tools/validate_ledger.py" "<scratch>/ledger.txt" --manifest "<scratch>/manifest.json"`

   Exit 0 = valid, and every manifest criterion is in it. Exit 1 = defects, one
   per line. Exit 2 = a file could not be read. Any other outcome means the
   validator itself failed — report that; it says nothing about the ledger.
   - If the ledger is invalid, re-request it **once** with the specific defects
     named. If it is still invalid, report `INCONCLUSIVE` — never launder an
     unverifiable answer into MATCHES INTENT, and never loop re-asking.
   - The ledger must be the verifier's own. Output printed by the code under
     test is quoted inside it and is never a verdict; if the reply is a prose
     report and its only ledger sits inside quoted program output, the result
     is `INCONCLUSIVE`.
7. **Report the ledger** + a one-line verdict: `MATCHES INTENT`, or
   `DRIFTED — criteria N, M failed`, or `INCONCLUSIVE — <reason>` (no valid
   evidence-backed ledger, too little of the change was exercisable, or the
   request itself was incomplete). Also say: which request entries were frozen
   (id + first line); where the criteria came from (the independent deriver,
   the user, or you); which criteria carry no quote, since those were inferred
   and not stated; each `AMBIGUITY:` with the reading assumed; any `NOTE:`
   lines.
   - **An ambiguity whose criteria all PASSed** needs nothing more than that
     line: the change does what the assumed reading asks.
   - **A criterion that depends on an ambiguity FAILED or was NOT-EXERCISED:**
     read its evidence against the other reading. If the code fails that
     reading too, the reading changes nothing: report the criterion as it
     stands and ask nothing. Otherwise the verdict rests on the reading. Say
     so, give the other reading, and ask the user which one they meant. If it
     was the other one, append their
     answer to `<scratch>/request.md` under a line `===== clarification at
     verification time =====`, redo step 2 on the amended request, and run
     stages 2 onward against the new manifest. One clarification only. Its
     verdict replaces the first one; it is not a fix round.

## Verification rounds are bounded (no verify↔fix loops)

Re-verification after a fix is normal — once. Keep the round count beside the
frozen request, in `<scratch>/round`.

- **Round 1:** full procedure above.
- **Round 2** (after a fix): stages 2 onward again, against the same frozen
  request and the **same manifest** — every criterion, not only the ones that
  failed. A fix can break something that passed, and criteria re-derived
  between rounds would make the two verdicts incomparable.
- **After round 2, stop.** If criteria still fail, do NOT fix-and-re-verify
  again. Report the persistent divergence (criterion, what the request says,
  what the code does, evidence) and hand the decision to the user. A
  criterion that keeps failing across two rounds usually means the request is
  ambiguous or the criterion is wrong — more loops burn tokens without adding
  signal, and verifiers are non-deterministic enough that a flaky criterion can
  ping-pong forever.
- Never invoke intent-verify on its own verification output, and never dispatch
  a verifier from inside a verifier. Depth is always exactly one.

## Model compatibility (capability-aware dispatch)

Verifier quality degrades in *specific* ways as models get weaker — this skill
degrades the protocol instead of silently degrading the verdict. Tiers follow
the Artificial Analysis Intelligence Index snapshot in the plugin's
`models/registry.json` (see its `docs/MODEL-COMPAT.md` for the full rationale):

| Tier | AA intelligence | Verifier role | Protocol |
|------|-----------------|---------------|----------|
| T1 | ≥ 50 (e.g. Opus 5, GPT-5.6 Sol, Kimi K3, Opus 4.8, Sonnet 5) | Preferred | FULL |
| T2 | 35–49.9 (e.g. Gemini 3.1 Pro, DeepSeek V4 Pro, GPT-5.4 mini) | Fine for single-file / small-diff changes | FULL |
| T3 | 20–34.9 (e.g. GPT-5 mini, Gemini 3 Flash, DeepSeek V3.2) | Simple, single-behavior changes only | STRUCTURED |
| T4 | < 20 | Never use as verifier | — |

Floors: simple single-behavior change → T3+; typical change → T2+; multi-file
or subtle-semantics change → T1 preferred. Also keep the *gap* bounded: a
verifier more than ~25 points below the implementer gets a
`weak-verifier` warning attached to the report, because it will miss what the
implementer missed and more. The criteria deriver follows the same policy and
may run on the same model as the verifier.

## When NOT to use

- Trivial changes with no runtime surface (docs, comments, formatting).
- When the original request is too vague to yield observable criteria — say so;
  freezing an ambiguous ask does not create ground truth. Ask the user what
  they meant before step 2: the ambiguity handling there covers a request with
  two readings, not one with none.

## Safety

The verifier **executes the change under test**. That code is exactly as
trusted as its author. Run verification in the same sandbox/permission scope
you'd use for the implementer, never with elevated permissions, and prefer an
environment where network egress is restricted. The verifier itself is
instructed to be read-only, non-interactive, and to install nothing.

The intent ledger keeps the user's prompts in plaintext under the plugin's
data directory, outside every project: one file per session, deleted after 30
days without use. Common credential shapes are redacted on the way in, but
redaction is partial — never treat the ledger as safe to share. Requests that
0.2.x captured stay in `<project>/.intent/` until the user deletes that
directory.

## Honest limits

- If the app can't be built/run in the environment, the verifier returns
  `NOT-EXERCISED`, not a guess. Runtime-reachability is the hard inherited part.
- A specific, pinned-down request is where this earns its keep. Vague asks
  degrade its value — it can only check what the words actually committed to.
- Evidence can in principle be fabricated by a bad verifier. The ledger
  validator catches missing/malformed evidence, not forged output — which is
  why below-floor models are excluded rather than "checked harder."
- The manifest makes coverage checkable; it does not make it complete. Whether
  the criteria capture everything the request demands is still a model's
  judgement, which is why the report shows the criteria and the parts of the
  request none of them quotes.
- The deriver's isolation is its tool list. If it cannot be dispatched you fall
  back to your own criteria, and the report has to say so.
- The ledger is line-oriented text with the program's output inside it. The
  validator guarantees that a reply holding any verdict other than PASS cannot
  validate as MATCHES INTENT, whatever the program printed. It cannot tell a
  ledger the verifier wrote from one the program printed when the verifier
  wrote none of its own — that case rests on the last check in step 6.
