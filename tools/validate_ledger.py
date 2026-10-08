#!/usr/bin/env python3
"""Machine validation for intent-verify: verifier ledgers and criterion manifests.

A LEDGER is the verifier's reply (agents/verifier.md). It is only trustworthy
if it kept the evidence contract, so this enforces, mechanically, the
properties that a lenient or weak verifier breaks first:

  - a mode line and at least one criterion
  - criteria are numbered 1..N in order, with no gaps or repeats
  - every verdict is PASS | FAIL | NOT-EXERCISED
  - PASS and FAIL carry both the command and its output, and output that shows
    nothing (spaces, a zero-width character) is not evidence
  - NOT-EXERCISED carries a reason
  - the final line is present and CONSISTENT with the per-criterion verdicts:
      any FAIL            => DRIFTED, listing every failed criterion
      all PASS            => MATCHES INTENT, and exactly those words
      no FAIL, some N-E   => INCONCLUSIVE
  - STRUCTURED mode: at most 5 criteria exercised (PASS/FAIL); requirements
    beyond that budget must be listed as NOT-EXERCISED, never dropped
  - with --manifest: every criterion of the manifest is in the ledger under the
    same number with the same text, letter for letter (spacing aside). A
    requirement the verifier left out, or a reply cut off before its last
    criteria, is then a defect instead of something a reader has to notice.
    The verifier may append further criteria.

Since 0.4.0 the ledger is ONE JSON OBJECT bound to its run (--run, --nonce):

    {"ledger": 2, "nonce": "<run nonce>", "mode": "FULL" | "STRUCTURED",
     "criteria": [{"id": 1, "text": "...", "verdict": "PASS", "cmd": "...", "out": "..."},
                  {"id": 2, "text": "...", "verdict": "NOT-EXERCISED", "reason": "..."}],
     "final": "MATCHES INTENT", "observations": "<optional>", "seal": "<run nonce>"}

  - the reply is that object: its first "{" opens the ledger and nothing
    follows the closing brace. A second ledger, a correction or a remark after
    it would make the reply ambiguous, and an ambiguous reply is invalid
    whichever version was meant
  - no key is written twice (a decoder keeps the last one without a word) and
    no key is unknown, at the top or in a criterion, so a second verdict cannot
    sit beside the first under another name
  - "nonce" is the run's nonce, which the code under test cannot know. "seal",
    the last key, repeats it: output pasted with its quotes unescaped can close
    the object early, but cannot complete it. The nonce occurs nowhere else:
    not around the ledger, and not in its other strings as they decode, in
    either letter case; the two that hold it write it out character for
    character
  Captured output is a string there and never structure. --unsealed accepts the
  version 1 object that 0.4.0 and 0.4.1 wrote (no seal, text around it), so
  that records made then can still be checked.

Without a run the older TEXT ledger is checked (header INTENT-VERIFY LEDGER
v1): manual use, and the simulated verifiers of the benchmark. There:
  - a single-line field holds its value on its own line (an empty field can
    never borrow the next line's text)
  - the LAST FINAL line is the conclusion, and every CRITERION block after the
    header is parsed wherever it sits, so a "FINAL:" line inside captured
    program output can neither end the ledger nor hide a criterion
  - every VERDICT line belongs to exactly one criterion and each criterion has
    exactly one. A second one is ambiguous (usually captured output that starts
    with a ledger keyword and was not indented). Together with the rule above
    this gives the property the tests pin down: a reply holding any VERDICT
    line that is not PASS can never validate as MATCHES INTENT.
  It cannot tell a ledger the verifier wrote from one the program printed.

A MANIFEST is the list of criteria fixed before anyone looked at the code
(agents/criteria.md, or criteria the user supplied):
    {"manifest": 1,
     "criteria": [{"id": 1, "text": "...", "quote": "..." | null}, ...],
     "ambiguities": [{"question": "...", "assumed": "...", "criteria": [1]}, ...]}
(an ambiguity may also carry "whether": true)
--check-manifest validates a deriver's reply, which is that object and nothing
after it: ids run 1..N, each text is one line, no key is unknown or written
twice, and every quote really occurs in the request as whole words, so a
criterion cannot be invented and attributed to the user. An ambiguity must name
existing criteria and the reading they assume; one that names none is dropped
and counted, since no answer to it could change the verdict. At most one may be
marked "whether": true, meaning that on the other reading the request asked for
no change at all. It is printed as ASK FIRST, because it is put to the user
before anything is verified. The check also lists the parts of the request no
criterion quotes; that is a hint, since it may be context or a missed
requirement.

What it cannot do:
  - detect *forged* output -- that is why below-floor models are excluded by
    selection rather than "validated harder" (see docs/MODEL-COMPAT.md);
  - read prose. A ledger whose "observations" or "reason" contradicts its own
    verdicts is still a well-formed ledger, and "." is still output;
  - prove that the nonce stayed secret. It is found in a command or in output
    however JSON spells it and in either letter case. A verifier that reversed
    it, split it or regrouped it before passing it on would not be noticed;
  - know whether a manifest is COMPLETE, or whether a quote has anything to do
    with the criterion it is attached to. What a request demands is still a
    model's judgement; the manifest only makes that judgement explicit, early
    and checkable.

Usage (use `python` where `python3` is not installed, e.g. stock Windows):
  validate_ledger.py --run DIR [--manifest MANIFEST]     # the reply the hook captured
  validate_ledger.py REPLY --nonce HEX [--manifest MANIFEST]   # a reply you saved yourself
  validate_ledger.py LEDGER [--manifest MANIFEST]        # a text ledger; - for stdin
  validate_ledger.py --check-manifest REPLY [--request FILE] [--out MANIFEST]
  validate_ledger.py --manifest-from FILE [--out MANIFEST]
Exit codes: 0 valid; 1 invalid (defects on stdout, one per line, so they can be
quoted in the single bounded re-request; a valid ledger is printed criterion
by criterion after the VALID line); 2 usage error or unreadable file;
4 --run holds no captured reply; 3 the validator itself failed, which says
nothing about what it was given.
"""
import argparse
import json
import os
import re
import sys
import textwrap
import traceback
import unicodedata

HEADER = "INTENT-VERIFY LEDGER v1"
VERDICTS = {"PASS", "FAIL", "NOT-EXERCISED"}
STRUCTURED_BUDGET = 5
NOTES_SHOWN = 10
MIN_QUOTE = 4
REPORT_FINAL, REPORT_CMD, REPORT_OUT, REPORT_NOTE = 120, 200, 300, 800  # characters of each value that are printed
# The verifier's remarks are where a caveat to a verdict goes, so they are
# printed nearly whole. The two verifications kept from real sessions wrote 939
# and 4,536 characters of them; the limit for other notes cut both, the second
# one in the middle of the caveat that mattered.
REPORT_OBSERVATIONS = 6000
DEFECTS_SHOWN, IDS_SHOWN = 50, 30  # lines of defects printed; ids of one ambiguity printed
MAX_FAILED_SCANS = 200
# capture-intent.js --begin-run makes 32 characters; the M4 runs of 2026-10-05 used 16.
NONCE = re.compile(r"[0-9a-f]{16,64}\Z")
LEDGER_KEYS = ("ledger", "nonce", "mode", "criteria", "final", "observations", "seal")
ENTRY_KEYS = ("id", "text", "verdict", "cmd", "out", "reason")
MANIFEST_KEYS = ("manifest", "criteria", "ambiguities", "unlinked_ambiguities")

# Horizontal whitespace only. A single-line field's value must sit on the
# field's own line: with \s here an empty "EVIDENCE-CMD:" swallowed the line
# below it and the ledger validated.
_VALUE = r"[ \t]*(\S[^\n]*)$"
# A criterion number has at most six digits. Python refuses to convert a run of
# several thousand, and a line of 4,301 nines in captured output used to raise.
_NUMBER = r"\d{1,6}(?!\d)"
_CRIT_HEAD = r"CRITERION[ \t]+" + _NUMBER + r"[ \t]*:"
_FIELD_START = r"^(?:VERDICT:|EVIDENCE-CMD:|REASON:|" + _CRIT_HEAD + r"|FINAL:|OBSERVATIONS:)"
_QUOTE_MARKS = {0x2018: "'", 0x2019: "'", 0x201C: '"', 0x201D: '"'}


def _squash(s):
    """A text with its spacing evened out. Two criterion texts are the same when
    they agree after this and in nothing less: "copy its text exactly" covers
    case too, since MAX_RETRIES and max_retries are different names."""
    return " ".join(unicodedata.normalize("NFC", s).split())


def _norm(s):
    """For finding a quote in a request, where typography is beside the point:
    case and curly or straight quote marks do not matter either."""
    return _squash(s.translate(_QUOTE_MARKS)).casefold()


# Printable as far as Python knows, not marks, and blank to a reader: the Hangul
# fillers, the empty Braille cell, the hieroglyphic blanks and the null notehead.
_BLANK_GLYPHS = frozenset(map(chr, (0x115F, 0x1160, 0x2800, 0x3164, 0xFFA0, 0x13441, 0x13442, 0x1D159)))
# Marks that draw nothing even on a letter: the grapheme joiner, the Khmer
# inherent vowels, the variation selectors of Mongolian and of everything else,
# the Khitan filler, and the joiners and selectors of single scripts. Python
# calls them printable.
_UNSEEN_MARKS = frozenset(chr(c) for lo, hi in ((0x034F, 0x034F), (0x17B4, 0x17B5), (0x180B, 0x180D), (0x180F, 0x180F),
                                               (0x2D7F, 0x2D7F), (0xFE00, 0xFE0F), (0x1107F, 0x1107F),
                                               (0x113D0, 0x113D0), (0x11A47, 0x11A47), (0x11A99, 0x11A99),
                                               (0x11F42, 0x11F42), (0x13440, 0x13440), (0x16FE4, 0x16FE4),
                                               (0x1BC9D, 0x1BC9D), (0xE0100, 0xE01EF))
                          for c in range(lo, hi + 1))


def _shows(ch):
    """Whether a character puts something on the page by itself. A combining
    mark does not: it needs a letter to sit on. That one rule covers every
    invisible mark without a list of them: the grapheme joiner, the variation
    selectors and the script fillers are all marks, and Python calls them
    printable."""
    return (ch.isprintable() and not ch.isspace() and unicodedata.category(ch)[0] != "M"
            and ch not in _BLANK_GLYPHS)


def _blank(s):
    """True for a string that shows nothing: empty, or only spaces, marks and
    characters without a glyph. A zero-width space is not evidence, and
    neither is a grapheme joiner."""
    return not any(_shows(ch) for ch in s or "")


def _seen_length(s, enough):
    """How much of a string a reader sees, counted as far as `enough`: each
    character that shows, one for a gap between two of them, and up to two
    marks on a letter, which is as many as are printed. What draws nothing is
    not counted, and neither is a mark with no letter under it or a third
    accent on one."""
    n, marks, gap = 0, None, False
    for ch in s:
        if _shows(ch):
            n += 2 if gap and n else 1
            marks, gap = 0, False
        elif ch.isspace():
            marks, gap = None, True
        elif marks is not None and marks < 2 and unicodedata.category(ch)[0] == "M" and ch not in _UNSEEN_MARKS:
            n, marks = n + 1, marks + 1
        if n >= enough:
            break
    return n


def _too_short(quote):
    """Whether a quote is under MIN_QUOTE characters to a reader. Measured as
    written and as composed, and the smaller taken: composing turns a letter
    and its accent into one character, and takes a few single characters
    apart into three."""
    return min(_seen_length(quote, MIN_QUOTE), _seen_length(unicodedata.normalize("NFC", quote), MIN_QUOTE)) < MIN_QUOTE


def extract_ledger(text):
    """Tolerate chatter/code-fences around the ledger (weak models love wrapping
    output in prose): everything from the header on is the ledger. It is not
    cut at a FINAL line. Cutting at the first one let a later FAIL go unparsed
    and validate as MATCHES INTENT; cutting at the last one still did whenever
    the only FINAL was a line of captured program output."""
    i = text.find(HEADER)
    return None if i == -1 else text[i:]


def parse(text):
    ledger = {"mode": None, "criteria": [], "final": None, "stray_verdicts": 0}
    # A harness that relays a subagent's reply may indent every line of it. No
    # keyword then sits at column 0 and a perfectly good ledger had "no
    # CRITERION blocks". Only an indent shared by EVERY non-blank line is
    # removed, so a ledger quoted inside a prose reply stays quoted.
    #
    # A carriage return on its own does not end a line. It used to: output
    # holding "\r" and a forged ledger then became ledger lines of its own, and
    # in an indented copy they stood at column 0 while the verifier's did not.
    body = extract_ledger(textwrap.dedent(text.replace("\r\n", "\n")))
    if body is None:
        return None, ["missing header line 'INTENT-VERIFY LEDGER v1'"]

    blocks = re.split(r"^(?=" + _CRIT_HEAD + ")", body, flags=re.M)
    # Only the preamble sets the mode: a "mode:" line in captured output does not.
    m = re.search(r"^mode:[ \t]*(FULL|STRUCTURED)[ \t]*$", blocks[0], re.M)
    if m:
        ledger["mode"] = m.group(1)
    ledger["stray_verdicts"] = len(re.findall(r"^VERDICT:", blocks[0], re.M))

    for block in blocks[1:]:
        head = re.match(r"CRITERION[ \t]+(" + _NUMBER + r")[ \t]*:[ \t]*([^\n]*)", block)
        crit = {
            "n": int(head.group(1)),
            "text": head.group(2).strip(),
            "verdict": None,
            "verdicts": len(re.findall(r"^VERDICT:", block, re.M)),
            "cmd": None,
            "out": None,
            "reason": None,
        }
        vm = re.search(r"^VERDICT:" + _VALUE, block, re.M)
        if vm:
            crit["verdict"] = vm.group(1).strip()
        cm = re.search(r"^EVIDENCE-CMD:" + _VALUE, block, re.M)
        if cm:
            crit["cmd"] = cm.group(1).strip()
        # Multi-line by design: runs until the next field line.
        om = re.search(r"^EVIDENCE-OUT:\s*(.*?)(?=" + _FIELD_START + r"|\Z)", block, re.M | re.S)
        if om:
            crit["out"] = om.group(1).strip()
        rm = re.search(r"^REASON:" + _VALUE, block, re.M)
        if rm:
            crit["reason"] = rm.group(1).strip()
        ledger["criteria"].append(crit)

    finals = re.findall(r"^FINAL:" + _VALUE, body, re.M)
    if finals:
        ledger["final"] = finals[-1].strip()
    return ledger, []


def validate(text, manifest=None):
    ledger, defects = parse(text)
    if ledger is None:
        return None, defects
    if not ledger["criteria"]:
        defects.append("no CRITERION blocks found")
        return ledger, defects
    return ledger, defects + _check(ledger, manifest, _TEXT_NAMES, True)


# How each encoding spells a field, so a defect names what the verifier wrote.
_TEXT_NAMES = {"no_mode": "missing 'mode: FULL' or 'mode: STRUCTURED' line", "no_final": "missing FINAL line",
               "verdict": "VERDICT", "cmd": "EVIDENCE-CMD", "out": "EVIDENCE-OUT", "reason": "REASON", "final": "FINAL"}
_JSON_NAMES = {"no_mode": 'missing "mode": it must be "FULL" or "STRUCTURED"', "no_final": 'missing "final"',
               "verdict": '"verdict"', "cmd": '"cmd"', "out": '"out"', "reason": '"reason"', "final": '"final"'}


def _check(ledger, manifest, names, text_grammar):
    """The rules both encodings share, applied to a parsed ledger. Returns the
    defects. `text_grammar` adds the three that only the line-oriented grammar
    needs, where captured output and ledger fields share one stream of lines."""
    defects = []
    crits = ledger["criteria"]
    if ledger["mode"] is None:
        defects.append(names["no_mode"])
    if text_grammar and ledger["stray_verdicts"]:
        defects.append("VERDICT line before the first CRITERION (every verdict must sit inside its criterion)")

    # Without this a ledger holding only "CRITERION 3" validated: a dropped
    # criterion was indistinguishable from a requirement nobody checked.
    nums = [c["n"] for c in crits]
    if nums != list(range(1, len(nums) + 1)):
        # A long list is not printed whole: the line is cut where the report
        # cuts every line, and the entry that is wrong may be past the cut.
        first = next(i for i, n in enumerate(nums, 1) if n != i)
        defects.append("criteria must be numbered 1..N in order with no gaps or repeats, "
                       + (f"found {nums}" if len(nums) <= 20 else
                          f"and entry {first} of {len(nums)} is numbered {nums[first - 1]}"))

    # The manifest was fixed before the code was read. Each of its criteria must
    # come back under the same number, word for word; what the verifier adds
    # goes after them.
    if manifest is not None:
        by_n = {c["n"]: c for c in crits}
        for want in manifest["criteria"]:
            got = by_n.get(want["id"])
            if got is None:
                defects.append(f"criterion {want['id']} of the manifest is missing from the ledger: {want['text']!r}")
            elif _squash(got["text"]) != _squash(want["text"]):
                defects.append(f"criterion {want['id']} does not match the manifest; copy its text exactly: {want['text']!r}")

    exercised = [c for c in crits if c["verdict"] in ("PASS", "FAIL")]
    if ledger["mode"] == "STRUCTURED" and len(exercised) > STRUCTURED_BUDGET:
        defects.append(
            f"STRUCTURED mode allows at most {STRUCTURED_BUDGET} exercised criteria, found {len(exercised)} "
            "(list requirements beyond the budget as NOT-EXERCISED)")

    for c in crits:
        n = c["n"]
        if _blank(c["text"]):
            defects.append(f"criterion {n}: empty criterion text")
        if text_grammar and c["verdicts"] > 1:
            defects.append(
                f"criterion {n}: {c['verdicts']} VERDICT lines, exactly one is allowed "
                "(indent any captured output line that starts with a ledger keyword)")
        if c["verdict"] not in VERDICTS:
            defects.append(f"criterion {n}: {names['verdict']} must be PASS|FAIL|NOT-EXERCISED, got {c['verdict']!r}")
            continue
        if c["verdict"] in ("PASS", "FAIL"):
            if _blank(c["cmd"]):
                defects.append(f"criterion {n}: {c['verdict']} without {names['cmd']}")
            out = c["out"] or ""
            # Text grammar only. There, output runs up to the next field line, so
            # "output" made of nothing but field-looking lines is how an empty
            # EVIDENCE-OUT followed by more fields parses. In a JSON ledger the
            # output is a string of its own: a program that prints only
            # "FINAL: MATCHES INTENT" has printed exactly that, and it is evidence.
            only_fields = text_grammar and out and all(
                re.match(r"^(VERDICT|EVIDENCE-CMD|EVIDENCE-OUT|REASON|CRITERION\s+\d+|FINAL|OBSERVATIONS)\b", l.strip())
                for l in out.splitlines() if l.strip())
            if _blank(out) or only_fields:
                defects.append(f"criterion {n}: {c['verdict']} without {names['out']} "
                               "(evidence is required, 'looks right' is not evidence)")
        elif _blank(c["reason"]):
            defects.append(f"criterion {n}: NOT-EXERCISED without {names['reason']}")

    final = ledger["final"]
    if not final:
        defects.append(names["no_final"])
        return defects

    name, said = names["final"], verdict_of(ledger)
    failed = sorted(c["n"] for c in crits if c["verdict"] == "FAIL")
    unexercised = sorted(c["n"] for c in crits if c["verdict"] == "NOT-EXERCISED")
    if all(c["verdict"] in VERDICTS for c in crits):
        if failed:
            if said != "DRIFTED":
                defects.append(f"{name} must be DRIFTED (criteria {failed} failed), got {final!r}")
            else:
                listed = {int(x) for x in re.findall(r"(?<!\d)" + _NUMBER, final)}
                missing = [n for n in failed if n not in listed]
                if missing:
                    defects.append(f"{name} DRIFTED must list every failed criterion; missing {missing}")
        elif unexercised:
            if said != "INCONCLUSIVE":
                defects.append(
                    f"{name} must be INCONCLUSIVE (criteria {unexercised} not exercised, none failed) — "
                    f"a criterion nobody exercised cannot be laundered into MATCHES INTENT; got {final!r}")
        elif said != "MATCHES INTENT":
            defects.append(f"all criteria PASS but {name} is {final!r}; expected MATCHES INTENT and nothing after it")
    return defects


def verdict_of(ledger):
    """What a final line concludes. MATCHES INTENT only when it is exactly those
    words: 'MATCHES INTENT — DRIFTED: criterion 1 failed' used to count as a
    match by the way it starts."""
    final = " ".join((ledger.get("final") or "").split())
    if final == "MATCHES INTENT":
        return final
    other = re.match(r"(DRIFTED|INCONCLUSIVE)\b", final)
    return other.group(1) if other else None


# ------------------------------------------------------- run-bound JSON ledger
def _decode(text, at):
    """The JSON value starting at text[at], as (value, where it ends, the keys
    that any of its objects repeats). Python's decoder keeps the last of two
    equal keys without a word, so '"verdict": "FAIL", "verdict": "PASS"' used to
    read as PASS; the repeats are returned, and every caller treats one as a
    defect."""
    repeated = []

    def pairs(items):
        seen = {}
        for key, value in items:
            if key in seen:
                repeated.append(key)
            seen[key] = value
        return seen

    value, end = json.JSONDecoder(object_pairs_hook=pairs).raw_decode(text, at)
    return value, end, repeated


def _repeats(what, repeated):
    keys = ", ".join(sorted({repr(k) for k in repeated}))
    return f"the {what} repeats the key(s) {keys}: a key may appear once in an object, and repeating one is not a correction"


def _unknown(obj, allowed, where):
    """A key nobody asked for is a defect. Beside "verdict": "PASS" it could
    read "Verdict": "FAIL" or "verdict_corrected": "FAIL", and only one of the
    two would ever be looked at."""
    extra = ", ".join(sorted(repr(k) for k in obj if k not in allowed))
    keys = ", ".join(f'"{k}"' for k in allowed)
    return [f"{where}: unknown key(s) {extra}; the keys are {keys} and no others"] if extra else []


def _strings(value):
    """Every string in a decoded JSON value, keys included. A loop and not a
    recursion: a reply decides how deep the value goes."""
    todo = [value]
    while todo:
        item = todo.pop()
        if isinstance(item, str):
            yield item
        elif isinstance(item, dict):
            todo.extend(item)
            todo.extend(item.values())
        elif isinstance(item, list):
            todo.extend(item)


def _only_object(text, what, remarks=""):
    """The JSON object a reply consists of, as (object, defects, where it stands
    in the text: a start and an end). Its first "{"
    opens the object and nothing may follow the closing brace but the end of a
    code fence. A sentence before it is tolerated if it holds no brace (3 of
    the 53 real version 1 replies had one). Text after it is where a second,
    contradicting conclusion went, parsed or not: a draft and its correction,
    the correction cut off halfway, or one with a trailing comma, all used to
    validate as the draft. One attempt at decoding also means a hostile reply
    costs its length and no more."""
    start = text.find("{")
    if start == -1:
        return None, [f"no JSON object found: the reply must be the {what}"], None
    try:
        obj, end, repeated = _decode(text, start)
    except RecursionError:
        return None, [f"the {what} is nested too deeply to read"], None
    except ValueError as e:  # JSONDecodeError, or a number too long for Python to convert
        return None, [f"the {what} does not parse as JSON: {e}. The reply's first '{{' must open the {what}, "
                      'and inside a string a line break is written \\n, a tab \\t, a double quote \\" '
                      "and a backslash \\\\"], None
    defects = []
    # Stripped before it is matched: with the white space in the pattern, a long
    # run of it in front of one stray character took time quadratic in its length.
    after = text[end:].strip()
    if not re.fullmatch(r"(?:`{3,})?", after):
        defects.append(f"text after the {what}: nothing may follow its closing brace, and a correction replaces the "
                       f"{what}, it does not follow it.{remarks} Found: {' '.join(after[:400].split())[:60]!r}")
    if repeated:
        defects.append(_repeats(what, repeated))
    try:
        json.dumps(obj, ensure_ascii=False).encode("utf-8")
    except UnicodeEncodeError:
        defects.append(f"the {what} holds half of a surrogate pair (an escape like \\ud83d with no partner): "
                       "write the character itself")
    except RecursionError:
        return None, [f"the {what} is nested too deeply to read"], None
    return obj, defects, (start, end)


def _json_objects(text):
    """Every top-level JSON object in a reply, as (object, repeated keys, start,
    end). Only
    a version 1 ledger is looked for this way: it could stand anywhere in a
    reply. The search gives up after MAX_FAILED_SCANS braces that open nothing."""
    found, at, failed = [], 0, 0
    while failed < MAX_FAILED_SCANS:
        at = text.find("{", at)
        if at == -1:
            break
        try:
            obj, end, repeated = _decode(text, at)
        except (ValueError, RecursionError):
            at, failed = at + 1, failed + 1
            continue
        found.append((obj, repeated, at, end))
        at = end
    return found


def _version_1(text, nonce):
    """The ledger that 0.4.0 and 0.4.1 wrote: the one top-level object in the
    reply that has a "ledger" key and the run's nonce, with remarks allowed
    around it and no seal. Kept so that records made then can be checked
    (--unsealed); the plugin itself no longer accepts it."""
    found = _json_objects(text)
    mine = [f for f in found if "ledger" in f[0] and f[0].get("nonce") == nonce]
    if len(mine) != 1:
        return (None, [f"{len(mine)} version 1 ledgers in the reply carry this run's nonce: there must be exactly one"],
                None, 0)
    obj, repeated, start, end = mine[0]
    # What the reply's other objects hold of the nonce once decoded: remarks
    # were allowed around a version 1 ledger, objects among them.
    elsewhere = sum(s.lower().count(nonce) for other in found if other[0] is not obj for s in _strings(other[0]))
    return obj, ([_repeats("ledger", repeated)] if repeated else []), (start, end), elsewhere


def validate_json(text, manifest, nonce, unsealed=False):
    """The verifier's JSON ledger for one run. Returns (ledger, defects), as
    validate() does, with the same rules applied to the object itself.

    The reply is the ledger, carries the run's nonce and ends with it again as
    its seal. A ledger printed by the code under test cannot carry the nonce,
    so quoting one, whole or in part, proves nothing; inside the object,
    captured output is a string and is never structure. If it is pasted with a
    double quote left unescaped it can end its string and even close the
    object, but what it closes has no seal."""
    if not isinstance(nonce, str) or not NONCE.match(nonce):
        raise ValueError("a run nonce is 16 to 64 hexadecimal characters")
    if unsealed:
        obj, defects, span, elsewhere = _version_1(text, nonce)
    else:
        obj, defects, span = _only_object(text, "ledger", ' Remarks go in its "observations".')
        elsewhere = 0
    if obj is None:
        return None, defects
    if obj.get("nonce") != nonce:
        if nonce not in text:
            return None, defects + ["no JSON ledger in the reply carries this run's nonce"]
        # The nonce is there, so a ledger probably is too, behind a brace in the
        # opening sentence or inside a wrapper. Say that, or the one retry goes
        # looking for a problem with the nonce.
        opened = json.dumps(obj, ensure_ascii=False)[:40]
        return None, defects + [f"the reply's first '{{' opens {opened!r}, which does not carry this run's nonce as its "
                                '"nonce", though the nonce is in the reply. The ledger must be that first object: write '
                                "no brace before it and do not wrap it in another object"]

    # Where the nonce is, as against where it belongs, in either letter case.
    # Three places are counted and kept apart: around the ledger as the reply
    # writes it, inside the ledger as the reply writes it, and in the ledger's
    # strings once decoded, where an escape for one character no longer hides
    # it. Added into one count they cancelled out: an escaped "seal" took an
    # occurrence away and a copy in the sentence before the ledger put it back.
    version, legit = (1, 1) if unsealed else (2, 1 + (obj.get("seal") == nonce))
    start, end = span
    outside = text[:start].lower().count(nonce) + text[end:].lower().count(nonce) + elsewhere
    written = text[start:end].lower().count(nonce)
    held = sum(s.lower().count(nonce) for s in _strings(obj))
    places = '"nonce"' if unsealed else '"nonce" and "seal"'
    if type(obj.get("ledger")) is not int or obj["ledger"] != version:
        older = (" (a version 1 ledger, as 0.4.0 and 0.4.1 wrote it, is checked with --unsealed)"
                 if type(obj.get("ledger")) is int and obj["ledger"] == 1 else "")
        defects.append(f'"ledger" must be {version}, the version of this format, found {obj.get("ledger")!r}{older}')
    if not unsealed:
        defects += _unknown(obj, LEDGER_KEYS, "the ledger")
        if obj.get("seal") != nonce or list(obj)[-1] != "seal":
            defects.append('the ledger is not sealed: its last key must be "seal", holding the run nonce again. A ledger '
                           "that closes before its seal is what pasted output with an unescaped double quote produces: "
                           'inside a string a double quote is written \\"')
        if obj.get("observations") is not None and not isinstance(obj["observations"], str):
            defects.append('"observations" must be a string')
    if outside:
        defects.append(f"the run nonce occurs {outside} time(s) outside the ledger: it belongs in {places} and nowhere "
                       "else in the reply, not in a sentence before the ledger and not in a second one")
    if held > legit:
        defects.append(f"the run nonce occurs {held - legit} time(s) in the ledger besides {places}: it does not belong "
                       "in a command, in output, in a reason, in a remark or in a criterion, however it is spelled "
                       '(an escape such as \\u0061 for "a", or upper case, is still the nonce)')
    if written != held:
        defects.append(f"the run nonce must be written out character for character: the ledger spells it {written} "
                       f"time(s) and holds it {held} time(s) once decoded")

    entries = obj.get("criteria")
    if not isinstance(entries, list) or not entries:
        return None, defects + ['"criteria" must be a non-empty list']

    def said(entry, key):
        value = entry.get(key)
        return value if isinstance(value, str) and not _blank(value) else None

    final = obj.get("final")
    if final is not None and not isinstance(final, str):
        defects.append('"final" must be a string')
    ledger = {"mode": obj.get("mode") if obj.get("mode") in ("FULL", "STRUCTURED") else None,
              "criteria": [], "stray_verdicts": 0,
              "observations": obj.get("observations") if isinstance(obj.get("observations"), str) else None,
              "final": " ".join(final.split()) if isinstance(final, str) and not _blank(final) else None}
    for position, entry in enumerate(entries, 1):
        if not isinstance(entry, dict):
            defects.append(f'entry {position} of "criteria" must be an object')
            continue
        if not unsealed:
            defects += _unknown(entry, ENTRY_KEYS, f'entry {position} of "criteria"')
        wrong = [k for k in ("text", "verdict", "cmd", "out", "reason") if k in entry and not isinstance(entry[k], str)]
        if wrong:
            fields = ", ".join(wrong)
            defects.append(f'entry {position} of "criteria": {fields} must be strings')
        number = entry.get("id")
        if type(number) is not int:
            defects.append(f'entry {position} of "criteria": "id" must be a whole number, found {number!r}')
            number = position
        ledger["criteria"].append({
            "n": number, "text": " ".join((said(entry, "text") or "").split()), "verdicts": 1,
            "verdict": (said(entry, "verdict") or "").strip() or None,
            # Kept exactly as written: a command may span lines, and output is data.
            "cmd": said(entry, "cmd"), "out": said(entry, "out"), "reason": said(entry, "reason")})
    return ledger, defects + _check(ledger, manifest, _JSON_NAMES, False)


def _one_line(value, limit):
    """A value as one line of what the validator prints, cut to `limit`
    characters. Every kind of line break becomes a visible mark and a character
    without a glyph becomes a space, so nothing a program printed can start a
    line of its own, or wipe one on a terminal, and pass for the validator's.
    Everything printed that a reply or a request supplied goes through here."""
    value = value or ""
    # Only the start is worked on: a 9 MB value used to be flattened whole to
    # show 300 characters of it.
    head = value[:limit * 4 + 64]
    more = len(head) < len(value)
    # What draws nothing goes first, so that it leaves no gap, no line of its
    # own and no place in a pile of marks: an unseen mark is dropped, and a
    # character without a glyph becomes a space unless it breaks the line.
    head = "".join(ch if ch.isspace() or (ch.isprintable() and ch not in _BLANK_GLYPHS) else " "
                   for ch in head if ch not in _UNSEEN_MARKS)
    flat = " \u23ce ".join(" ".join(part.split()) for part in head.splitlines() if part.strip())
    shown, stacked = [], 0
    for ch in flat:
        # Every mark, not only those with a combining class: an enclosing
        # circle has class 0 and stacks like the rest.
        stacked = stacked + 1 if unicodedata.category(ch)[0] == "M" else 0
        if stacked <= 2:  # a pile of combining marks is drawn over the lines around it
            shown.append(ch)
    flat = "".join(shown)
    if len(flat) > limit or more:
        return f"{flat[:limit]} \u2026 [cut: {len(value)} characters in all]"
    return flat


def ledger_lines(ledger):
    """A valid ledger as a report shows it: a line per criterion with its
    evidence beneath, then the verifier's observations. It is printed so that
    showing the ledger is a paste; the first real run reported "passed all 4
    criteria" and showed none of them."""
    lines = ["LEDGER"]
    for c in ledger["criteria"]:
        lines.append(f"  {c['n']} {c['verdict']}  {_one_line(c['text'], REPORT_OUT)}")
        if c["verdict"] == "NOT-EXERCISED":
            lines.append("      why: " + _one_line(c["reason"], REPORT_OUT))
        else:
            lines.append("      ran: " + _one_line(c["cmd"], REPORT_CMD))
            lines.append("      saw: " + _one_line(c["out"], REPORT_OUT))
    if not _blank(ledger.get("observations")):
        lines.append("OBSERVATIONS: " + _one_line(ledger["observations"], REPORT_OBSERVATIONS))
    return lines


def captured_reply(run_dir):
    """(nonce, newest reply file or None) of a run made by capture-intent.js
    --begin-run. The SubagentStop hook files each verifier reply there."""
    with open(os.path.join(run_dir, "run.json"), encoding="utf-8") as f:
        nonce = json.load(f)["nonce"]
    if not isinstance(nonce, str) or not NONCE.match(nonce):
        raise ValueError("its nonce is not 16 to 64 hexadecimal characters")
    replies = sorted(n for n in os.listdir(run_dir) if n.startswith("reply-") and n.endswith(".txt"))
    return nonce, (os.path.join(run_dir, replies[-1]) if replies else None)


def hook_traces(run_dir):
    """What the hook left beside this run since it began: replies carrying no
    known nonce, and notes that it ran and found no reply. Any of them means
    the hook ran; none means there is no sign that it did."""
    try:
        began = os.path.getmtime(os.path.join(run_dir, "run.json"))
        apart = os.path.join(os.path.dirname(os.path.abspath(run_dir)), "_unmatched")
        return sorted(n for n in os.listdir(apart) if os.path.getmtime(os.path.join(apart, n)) >= began)
    except OSError:
        return []


# ------------------------------------------------------------------ manifests
def _occurs(quote, wanted):
    """Whether a quote is in the (normalised) request as whole words. 'ort' is
    inside 'sorted', and it is not a piece of what the user wrote."""
    return re.search(r"(?<!\w)" + re.escape(_norm(quote)) + r"(?!\w)", wanted) is not None


def check_manifest(text, request=None):
    """Validate a criterion manifest. Returns (manifest, defects, notes): the
    manifest in normalised form, and as notes the parts of the request that no
    criterion quotes."""
    obj, defects, _span = _only_object(text, "manifest")
    if obj is None:
        return None, defects, []
    raw = obj.get("criteria")
    if not isinstance(raw, list) or not raw:
        return None, defects + ["'criteria' must be a non-empty list"], []

    defects, criteria = defects + _unknown(obj, MANIFEST_KEYS, "the manifest"), []
    wanted = _norm(request) if request is not None else None
    for i, c in enumerate(raw, 1):
        if not isinstance(c, dict):
            defects.append(f"criterion {i}: must be an object with id, text and quote")
            continue
        defects += _unknown(c, ("id", "text", "quote"), f"criterion {i}")
        if type(c.get("id")) is not int or c["id"] != i:
            defects.append(f"criterion {i}: ids must run 1..N in order, found id {c.get('id')!r}")
        body, quote = c.get("text"), c.get("quote")
        if not isinstance(body, str) or _blank(body) or "\n" in body.strip():
            defects.append(f"criterion {i}: 'text' must be one non-empty line")
            body = ""
        if quote is not None and (not isinstance(quote, str) or _blank(quote)):
            defects.append(f"criterion {i}: 'quote' must be a piece of the request, or null")
            quote = None
        elif quote is not None and _too_short(quote):
            # "a" and "the" occur in any request and tie a criterion to nothing.
            # Nor does "a" followed by three characters nobody sees.
            defects.append(f"criterion {i}: its quote {quote!r} is too short to tie the criterion to the request; "
                           f"quote {MIN_QUOTE} characters of it or more, or use null")
        elif quote is not None and wanted is not None and not _occurs(quote, wanted):
            defects.append(f"criterion {i}: its quote does not occur in the request: {quote!r}")
        criteria.append({"id": i, "text": " ".join(body.split()), "quote": quote})

    # An ambiguity counts only through the criteria whose check depends on it.
    # One that names none cannot change the verdict, so nobody should be asked
    # it: in the 0.3.1 controlled run the deriver raised 41 such questions on 16
    # one-line requests, and the verdicts needed none of them.
    ambiguities, unlinked, asked_first = [], 0, 0
    raw_amb = obj.get("ambiguities") or []
    if not isinstance(raw_amb, list):
        defects.append("'ambiguities' must be a list")
        raw_amb = []
    ids = {c["id"] for c in criteria}
    for j, a in enumerate(raw_amb, 1):
        whether = False
        if isinstance(a, dict):
            defects += _unknown(a, ("question", "assumed", "criteria", "whether"), f"ambiguity {j}")
            if "whether" in a and type(a["whether"]) is not bool:
                defects.append(f"ambiguity {j}: 'whether' must be true or false")
            whether = a.get("whether") is True
        if isinstance(a, str) or (isinstance(a, dict) and not a.get("criteria")):
            if whether:
                # Not dropped like any other that names no criterion: this one
                # decides whether there is anything to verify.
                defects.append(f"ambiguity {j}: one marked 'whether' must name the criteria that take the request to "
                               "ask for this change (usually all of them)")
            else:
                unlinked += 1
            continue
        question, assumed, linked = (a.get(k) for k in ("question", "assumed", "criteria")) if isinstance(a, dict) else (None,) * 3
        if not isinstance(question, str) or _blank(question):
            defects.append(f"ambiguity {j}: must be an object with 'question', 'assumed' and 'criteria'")
        elif not isinstance(linked, list) or any(type(n) is not int or n not in ids for n in linked):
            defects.append(f"ambiguity {j}: 'criteria' must list ids of this manifest's criteria, found {linked!r}")
        elif not isinstance(assumed, str) or _blank(assumed):
            defects.append(f"ambiguity {j}: 'assumed' must say which reading criteria {linked} were written for")
        else:
            ambiguities.append({"question": " ".join(question.split()), "assumed": " ".join(assumed.split()),
                                "criteria": linked})
            if whether:
                ambiguities[-1]["whether"] = True
                asked_first += 1
    if asked_first > 1:
        # 0.3.1 put 41 questions to the user before checking 16 one-line requests.
        defects.append("only one ambiguity may be marked 'whether': it is put to the user before anything is verified")
    manifest = {"manifest": 1, "criteria": criteria, "ambiguities": ambiguities}
    if unlinked:
        manifest["unlinked_ambiguities"] = unlinked
    notes = _uncovered(manifest, request) if request is not None and not defects else []
    return manifest, defects, notes


def _uncovered(manifest, request):
    quotes = [_norm(c["quote"]) for c in manifest["criteria"] if c["quote"]]
    notes = []
    for sentence in re.split(r"(?<=[.!?])\s+|\n+", request):
        words = _norm(sentence).split()
        if len(words) < 4:
            continue
        flat = " ".join(words)
        grams = {" ".join(words[i:i + 3]) for i in range(len(words) - 2)}
        if not any(q in flat or any(g in q for g in grams) for q in quotes):
            notes.append(" ".join(sentence.split()))
    return notes


def manifest_from_lines(text):
    """A manifest from criteria somebody already wrote down, one per line.
    Bullets, numbering and checkboxes are dropped; headings are skipped."""
    items = []
    for line in text.splitlines():
        # A heading is "#" and a space. "- #tags are lowercased" is a criterion.
        if re.match(r"\s*#{1,6}(?:\s|$)", line):
            continue
        s = re.sub(r"^\s*(?:[-*+]|\d+[.)])\s+", "", line).strip()
        s = re.sub(r"^\[[ xX]\]\s+", "", s)
        if not _blank(s):  # the test check_manifest applies, so what this writes it also accepts
            items.append(s)
    return {"manifest": 1, "criteria": [{"id": i, "text": t, "quote": None} for i, t in enumerate(items, 1)],
            "ambiguities": []}


# ------------------------------------------------------------------------ cli
def _read(path):
    if path == "-":
        return sys.stdin.read()
    with open(path, encoding="utf-8", errors="replace") as f:
        return f.read()


def _report(defects):
    # A defect quotes what it found, and what it found is the reply's. Every
    # line goes through the filter of the report: repr() had kept line breaks
    # and escape codes out, and let a 20,000-character quote or a pile of
    # combining marks through whole.
    for d in defects[:DEFECTS_SHOWN]:
        print("DEFECT: " + _one_line(d, REPORT_NOTE))
    if len(defects) > DEFECTS_SHOWN:
        print(f"DEFECT: ... and {len(defects) - DEFECTS_SHOWN} more")
    print(f"INVALID ({len(defects)} defect(s))")
    return 1


def _emit_manifest(manifest, notes, out):
    # Serialised before the file is opened, so nothing that fails here can
    # leave half a manifest behind.
    data = json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
    print(f"VALID: {len(manifest['criteria'])} criteria")
    for c in manifest["criteria"]:
        # The manifest file keeps the quote whole; this line shows the start of it.
        print(f"  {c['id']}. {_one_line(c['text'], REPORT_NOTE)}  "
              + (f"[quote: {_one_line(c['quote'], REPORT_OUT)!r}]" if c["quote"] else "[no quote]"))
    for a in manifest["ambiguities"]:
        label = "ASK FIRST" if a.get("whether") else "AMBIGUITY"
        # The ids are the reply's as well: a list may repeat one a million times.
        ids = ", ".join(map(str, a["criteria"][:IDS_SHOWN])) + (
            f" … [{len(a['criteria'])} in all]" if len(a["criteria"]) > IDS_SHOWN else "")
        print(f"{label}: {_one_line(a['question'], REPORT_NOTE)} — criteria {ids} "
              f"assume: {_one_line(a['assumed'], REPORT_NOTE)}")
    if manifest.get("unlinked_ambiguities"):
        print(f"DROPPED: {manifest['unlinked_ambiguities']} ambiguity question(s) that no criterion depends on; "
              "no answer to them could change the verdict")
    # A hint, so it must stay readable: a long request has hundreds of sentences
    # that are context and not requirements.
    for n in notes[:NOTES_SHOWN]:
        print(f"NOTE: no criterion quotes this part of the request: {_one_line(n, REPORT_NOTE)}")
    if len(notes) > NOTES_SHOWN:
        print(f"NOTE: ... and {len(notes) - NOTES_SHOWN} more parts of the request that no criterion quotes")
    if out:
        with open(out, "w", encoding="utf-8", newline="\n") as f:
            f.write(data)
    return 0


def main(argv):
    # The report echoes ledger text, which can hold any character. On Windows
    # the default console/pipe encoding is a legacy codepage, where printing an
    # arrow raised UnicodeEncodeError and exited 1 -- indistinguishable from
    # "ledger invalid". Speak UTF-8 on every stream.
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    ap = argparse.ArgumentParser(
        prog="validate_ledger.py", description="Validate an intent-verify ledger or criterion manifest.",
        epilog="Exit codes: 0 valid, 1 invalid (defects listed), 2 usage error or unreadable file, "
               "3 the validator itself failed, 4 --run holds no captured reply.")
    ap.add_argument("ledger", nargs="?", help="a verifier's reply, or - for stdin")
    ap.add_argument("--run", metavar="DIR", help="validate the reply the SubagentStop hook captured for this run "
                                                 "(a directory made by capture-intent.js --begin-run)")
    ap.add_argument("--nonce", metavar="HEX", help="with a ledger file: the run's nonce, for a reply the session saved itself")
    ap.add_argument("--unsealed", action="store_true", help="with --run or --nonce: accept the version 1 ledger of 0.4.0 "
                                                            "and 0.4.1, which has no seal; for records made then")
    ap.add_argument("--manifest", metavar="FILE", help="criteria the ledger must cover")
    ap.add_argument("--check-manifest", metavar="REPLY", help="validate a criteria deriver's reply instead of a ledger")
    ap.add_argument("--request", metavar="FILE", help="with --check-manifest: the frozen request each quote must occur in")
    ap.add_argument("--manifest-from", metavar="FILE", help="build a manifest from criteria you already have, one per line")
    ap.add_argument("--out", metavar="FILE", help="with --check-manifest or --manifest-from: write the manifest here")
    a = ap.parse_args(argv[1:])

    def usage(problem):
        ap.print_usage(sys.stderr)
        print(f"validate_ledger.py: {problem}", file=sys.stderr)
        return 2

    if sum(x is not None for x in (a.ledger, a.run, a.check_manifest, a.manifest_from)) != 1:
        return usage("give a ledger, or --run, or --check-manifest, or --manifest-from")
    # An option that is there but empty is a mistake in the caller, and reading
    # it as "not given" skipped the very check it asked for: --manifest "" let
    # a ledger through without its manifest.
    if "" in (a.ledger, a.run, a.nonce, a.manifest, a.check_manifest, a.request, a.manifest_from, a.out):
        return usage("an argument is empty")
    if a.nonce is not None and not NONCE.match(a.nonce):
        return usage("--nonce is the run nonce that --begin-run printed: 16 to 64 hexadecimal characters")
    if a.unsealed and a.run is None and a.nonce is None:
        return usage("--unsealed goes with --run or --nonce")

    try:
        if a.manifest_from is not None:
            manifest = manifest_from_lines(_read(a.manifest_from))
            if not manifest["criteria"]:
                return _report(["no criteria found (one per line)"])
            return _emit_manifest(manifest, [], a.out)
        if a.check_manifest is not None:
            request = _read(a.request) if a.request is not None else None
            manifest, defects, notes = check_manifest(_read(a.check_manifest), request)
            return _report(defects) if defects else _emit_manifest(manifest, notes, a.out)

        manifest = None
        if a.manifest is not None:
            manifest, defects, _notes = check_manifest(_read(a.manifest))
            if defects:
                print(f"validate_ledger.py: {a.manifest} is not a valid manifest: {_one_line(defects[0], REPORT_NOTE)}",
                      file=sys.stderr)
                return 2
        source = None
        if a.run is not None:
            try:
                nonce, reply = captured_reply(a.run)
            except (KeyError, TypeError, ValueError, RecursionError) as e:
                print(f"validate_ledger.py: {a.run} is not a run directory (no usable run.json): "
                      f"{_one_line(str(e), REPORT_OUT)}", file=sys.stderr)
                return 2
            if reply is None:
                # The hook names these files itself. Anything else that can write
                # beside the run could name one anything.
                traces = [_one_line(n, REPORT_FINAL) for n in hook_traces(a.run)]
                why = (f"The hook ran since this run began ({', '.join(traces[:3])} in _unmatched), "
                       "but nothing it saw carried this run's nonce." if traces else
                       "There is no sign that the hook ran.")
                print(f"NO REPLY CAPTURED: the SubagentStop hook filed nothing under {a.run}. {why}")
                return 4
            text, source = _read(reply), f"captured by the hook: {_one_line(os.path.basename(reply), REPORT_FINAL)}"
        else:
            text, nonce = _read(a.ledger), a.nonce
            if nonce is not None:
                source = "relayed by the session, not captured by the hook"
    except OSError as e:
        # Exit 1 means "invalid". A file that is not there is a different problem.
        print(f"validate_ledger.py: cannot read or write {e.filename}: {e.strerror}", file=sys.stderr)
        return 2

    if nonce is not None:
        ledger, defects = validate_json(text, manifest, nonce, a.unsealed)
        if a.unsealed:
            source += "; a version 1 ledger, which has no seal"
    elif HEADER not in text and re.search(r'"ledger"\s*:', text):
        ledger, defects = None, ["this is a JSON ledger: check it with --run, or with --nonce if you saved the reply yourself"]
    else:
        ledger, defects = validate(text, manifest)
    if defects:
        return _report(defects)
    covered = f" (all {len(manifest['criteria'])} manifest criteria covered)" if manifest else ""
    # The conclusion is the verifier's own text and goes through the same filter
    # as its evidence: escape codes in it used to redraw this line as a match.
    print(f"VALID: {len(ledger['criteria'])} criteria{covered}, final = {_one_line(ledger['final'], REPORT_FINAL)}"
          + (f" ({source})" if source else ""))
    print("\n".join(ledger_lines(ledger)))
    return 0


def run(argv):
    """main(), with a failure of the validator itself kept apart from its
    answers: an uncaught exception exits 1, and 1 means "the ledger has defects"."""
    try:
        return main(argv)
    except Exception:  # noqa: BLE001
        traceback.print_exc()
        return 3


if __name__ == "__main__":
    sys.exit(run(sys.argv))
