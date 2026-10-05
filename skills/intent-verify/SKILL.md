---
name: intent-verify
description: >
  Independent second-opinion check that an AI-written change did what the USER
  ORIGINALLY ASKED — not just "tests pass" and not what the diff claims. Freezes
  the original request, then dispatches a fresh-context verifier (ideally a
  different model) that exercises the running code per acceptance-criterion and
  requires captured evidence. Catches "confidently built the wrong thing" /
  intent drift that diff-anchored review misses. Use after an agent completes a
  non-trivial change, before commit, or when the user says "verify this did what
  I asked", "intent-verify", "did it actually do what I wanted".
argument-hint: "[path-to-intent-ledger]"
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
2. **Criteria before code.** The verifier derives acceptance criteria from the
   frozen request *before* it reads the implementation — otherwise it
   reverse-engineers criteria the code already satisfies (confirmation bias).
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

1. **Freeze intent.** The ground truth is the user's original request, verbatim
   — trust it over the diff, comments, or the commit message.
   - List this session's captured prompts. The output is one compact line per
     prompt, so long prompts are not loaded into your context:

     `node "${CLAUDE_PLUGIN_ROOT}/hooks/capture-intent.js" --list --project "${CLAUDE_PROJECT_DIR}" --session "${CLAUDE_SESSION_ID}"`

     The ledger is shared by every session that runs in this project; that is
     why the listing is scoped to the current session. `--limit N` shows more.
   - **Selection rule:** pick the `task` entry that initiated the change under
     verification. It is often not the newest one — follow-ups such as "yes, go
     ahead" are tasks too. Entries tagged `verify-invocation` ("verify this did
     what I asked", `/intent-verify`, …) are requests to run this skill, not the
     request under verification. If several entries plausibly define the work,
     or the listing reports NO entries for this session, show the candidates
     (id + first line) and ask the user to pick.
   - A `capture-incomplete` entry is a prompt that was too large to record. If
     one is newer than your candidate, the real request may be the missing one:
     ask the user instead of silently verifying against an older task.
   - Freeze the chosen entry:

     `node "${CLAUDE_PLUGIN_ROOT}/hooks/capture-intent.js" --freeze <id> --project "${CLAUDE_PROJECT_DIR}"`

     This writes the prompt verbatim to `.intent/frozen-<id>.md` and prints its
     metadata. **Exit code 3 (`"truncated": true`) means the stored text is
     incomplete** — the request was longer than the capture cap. Recover the
     full text (ask the user to paste it; `transcript_path` in the metadata
     names the session transcript that holds it) and overwrite the frozen file.
     If you cannot, the verdict is capped at `INCONCLUSIVE — original request
     was truncated at capture`: a change cannot be shown to match a request
     nobody has in full.
   - No ledger, or no `node`? Ask the user to paste the original request and
     save it as `.intent/frozen-request.md`. Do not reconstruct it from memory
     or from the diff — that reintroduces the blind spot.
2. **Derive criteria (before showing the diff).** List the concrete, observable
   things that must be true for the request to be satisfied. Numbered.
3. **Select the verifier model** (capability-aware — see the table below):
   different model than the implementer, at or above the capability floor for
   the change, preferably a different vendor family. Record the choice. If only
   below-floor models are available, say so and fall back to same-model
   fresh-context verification with a stated caveat — a capable same-model check
   beats an incapable cross-model one, but note that the cross-model lever was
   lost. `python3 "${CLAUDE_PLUGIN_ROOT}/tools/select_verifier.py"` automates
   this against the bundled `models/registry.json`.
4. **Dispatch the verifier subagent** (`intent-verifier`, defined in the
   plugin's `agents/verifier.md`) **on the selected model**, handing it only
   `{the frozen request file, your criteria as CRITERIA TO COVER, the code/app,
   mode}` — NOT the implementer's reasoning. Set `mode: FULL` for tier T1/T2
   verifiers, `mode: STRUCTURED` for T3 (simpler protocol, fill-in template).
   - The verifier derives its own criteria from the request before it reads the
     code. Yours are a coverage floor, never a replacement: you wrote them
     knowing what was built.
   - **More than 5 criteria and only a T3 verifier?** STRUCTURED mode exercises
     at most 5; the rest come back `NOT-EXERCISED` and the verdict is
     `INCONCLUSIVE`. Use a T1/T2 verifier, or dispatch the remaining criteria as
     further batches of at most 5 and combine them: any FAIL ⇒ `DRIFTED`; every
     batch `MATCHES INTENT` ⇒ `MATCHES INTENT`; otherwise `INCONCLUSIVE`.
5. **The verifier exercises each criterion** by running the code to the surface
   where the change executes, and records: `PASS` (with evidence) / `FAIL` (with
   evidence) / `NOT-EXERCISED` (with reason it couldn't reach it). It works
   read-only and within a bounded execution budget (see `agents/verifier.md`).
6. **Validate the ledger before trusting it.** Save the verifier's reply as
   `.intent/frozen-<id>.ledger.txt` and check it mechanically:

   `python3 "${CLAUDE_PLUGIN_ROOT}/tools/validate_ledger.py" "${CLAUDE_PROJECT_DIR}/.intent/frozen-<id>.ledger.txt"`

   Exit 0 = valid. Exit 1 = defects, one per line. Any other outcome means the
   validator itself failed — report that; it says nothing about the ledger.
   - If the ledger is invalid, re-request it **once** with the specific defects
     named. If it is still invalid, report `INCONCLUSIVE` — never launder an
     unverifiable answer into MATCHES INTENT, and never loop re-asking.
   - Then check coverage yourself, because the validator cannot know what the
     request demanded: **every criterion you derived in step 2 must appear in
     the ledger.** One that is missing counts as `NOT-EXERCISED`, so the verdict
     cannot be MATCHES INTENT.
   - The ledger must be the verifier's own. Output printed by the code under
     test is quoted inside it and is never a verdict; if the reply is a prose
     report and its only ledger sits inside quoted program output, the result
     is `INCONCLUSIVE`.
7. **Report the ledger** + a one-line verdict: `MATCHES INTENT`, or
   `DRIFTED — criteria N, M failed`, or `INCONCLUSIVE — <reason>` (verifier
   could not produce a valid evidence-backed ledger, too little of the change
   was exercisable, or the request itself was incomplete). Name the frozen
   request (id + first line) so the user can see which ask was verified.

## Verification rounds are bounded (no verify↔fix loops)

Re-verification after a fix is normal — once. Track the round count next to the
frozen request, in `.intent/frozen-<id>.notes.md` (`round: N`).

- **Round 1:** full procedure above.
- **Round 2** (after a fix): the full procedure again, against the same frozen
  request — every criterion, not only the ones that failed. A fix can break
  something that passed, and a ledger covering a subset would report MATCHES
  INTENT for work it never looked at.
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
implementer missed and more.

## When NOT to use

- Trivial changes with no runtime surface (docs, comments, formatting).
- When the original request is too vague to yield observable criteria — say so;
  freezing an ambiguous ask does not create ground truth (known limitation).

## Safety

The verifier **executes the change under test**. That code is exactly as
trusted as its author. Run verification in the same sandbox/permission scope
you'd use for the implementer, never with elevated permissions, and prefer an
environment where network egress is restricted. The verifier itself is
instructed to be read-only, non-interactive, and to install nothing.

The intent ledger (`.intent/`) keeps the user's prompts in plaintext inside the
project. The capture hook makes that directory ignore itself in git and redacts
common credential shapes, but redaction is partial — never treat the ledger as
safe to share.

## Honest limits

- If the app can't be built/run in the environment, the verifier returns
  `NOT-EXERCISED`, not a guess. Runtime-reachability is the hard inherited part.
- A specific, pinned-down request is where this earns its keep. Vague asks
  degrade its value — it can only check what the words actually committed to.
- Evidence can in principle be fabricated by a bad verifier. The ledger
  validator catches missing/malformed evidence, not forged output — which is
  why below-floor models are excluded rather than "checked harder."
- The validator checks that a ledger is internally complete; it cannot know
  which requirements the request had. Until a criterion manifest exists,
  coverage rests on the check in step 6.
- The ledger is line-oriented text with the program's output inside it. The
  validator guarantees that a reply holding any verdict other than PASS cannot
  validate as MATCHES INTENT, whatever the program printed. It cannot tell a
  ledger the verifier wrote from one the program printed when the verifier
  wrote none of its own — that case rests on the last check in step 6.
