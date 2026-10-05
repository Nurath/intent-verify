#!/usr/bin/env python3
"""Machine validation for intent-verify: verifier ledgers and criterion manifests.

A LEDGER is the verifier's reply (agents/verifier.md). It is only trustworthy
if it kept the evidence contract, so this enforces, mechanically, the
properties that a lenient or weak verifier breaks first:

  - header present (INTENT-VERIFY LEDGER v1), a mode line, at least one criterion
  - criteria are numbered 1..N in order, with no gaps or repeats
  - every VERDICT is PASS | FAIL | NOT-EXERCISED
  - PASS and FAIL carry both EVIDENCE-CMD and non-empty EVIDENCE-OUT
  - NOT-EXERCISED carries a REASON
  - a single-line field holds its value on its own line (an empty field can
    never borrow the next line's text)
  - FINAL is present and CONSISTENT with the per-criterion verdicts:
      any FAIL            => DRIFTED, listing every failed criterion
      all PASS            => MATCHES INTENT
      no FAIL, some N-E   => INCONCLUSIVE
    The LAST FINAL line is the conclusion, and every CRITERION block after the
    header is parsed wherever it sits, so a "FINAL:" line inside captured
    program output can neither end the ledger nor hide a criterion.
  - every VERDICT line belongs to exactly one criterion and each criterion has
    exactly one. A second one is ambiguous (usually captured output that starts
    with a ledger keyword and was not indented). Together with the rule above
    this gives the property the tests pin down: a reply holding any VERDICT
    line that is not PASS can never validate as MATCHES INTENT.
  - STRUCTURED mode: at most 5 criteria exercised (PASS/FAIL); requirements
    beyond that budget must be listed as NOT-EXERCISED, never dropped
  - with --manifest: every criterion of the manifest is in the ledger under the
    same number with the same text. A requirement the verifier left out, or a
    reply cut off before its last criteria, is then a defect instead of
    something a reader has to notice. The verifier may append further criteria.

A MANIFEST is the list of criteria fixed before anyone looked at the code
(agents/criteria.md, or criteria the user supplied):
    {"manifest": 1,
     "criteria": [{"id": 1, "text": "...", "quote": "..." | null}, ...],
     "ambiguities": ["..."]}
--check-manifest validates a deriver's reply: ids run 1..N, each text is one
line, and every quote really occurs in the request, so a criterion cannot be
invented and attributed to the user. It also lists the parts of the request no
criterion quotes; that is a hint, since it may be context or a missed
requirement.

What it cannot do:
  - detect *forged* output -- that is why below-floor models are excluded by
    selection rather than "validated harder" (see docs/MODEL-COMPAT.md);
  - know whether a manifest is COMPLETE. What a request demands is still a
    model's judgement; the manifest only makes that judgement explicit, early
    and checkable.

Usage (use `python` where `python3` is not installed, e.g. stock Windows):
  validate_ledger.py LEDGER [--manifest MANIFEST]        # LEDGER may be - for stdin
  validate_ledger.py --check-manifest REPLY [--request FILE] [--out MANIFEST]
  validate_ledger.py --manifest-from FILE [--out MANIFEST]
Exit codes: 0 valid; 1 invalid (defects on stdout, one per line, so they can be
quoted in the single bounded re-request); 2 usage error or unreadable file.
Any other outcome means the validator itself failed, not what it was given.
"""
import argparse
import json
import re
import sys
import textwrap

HEADER = "INTENT-VERIFY LEDGER v1"
VERDICTS = {"PASS", "FAIL", "NOT-EXERCISED"}
STRUCTURED_BUDGET = 5

# Horizontal whitespace only. A single-line field's value must sit on the
# field's own line: with \s here an empty "EVIDENCE-CMD:" swallowed the line
# below it and the ledger validated.
_VALUE = r"[ \t]*(\S[^\n]*)$"
_CRIT_HEAD = r"CRITERION[ \t]+\d+[ \t]*:"
_FIELD_START = r"^(?:VERDICT:|EVIDENCE-CMD:|REASON:|" + _CRIT_HEAD + r"|FINAL:|OBSERVATIONS:)"


def _norm(s):
    return " ".join(s.split()).casefold()


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
    body = extract_ledger(textwrap.dedent(text.replace("\r\n", "\n").replace("\r", "\n")))
    if body is None:
        return None, ["missing header line 'INTENT-VERIFY LEDGER v1'"]

    blocks = re.split(r"^(?=" + _CRIT_HEAD + ")", body, flags=re.M)
    # Only the preamble sets the mode: a "mode:" line in captured output does not.
    m = re.search(r"^mode:[ \t]*(FULL|STRUCTURED)[ \t]*$", blocks[0], re.M)
    if m:
        ledger["mode"] = m.group(1)
    ledger["stray_verdicts"] = len(re.findall(r"^VERDICT:", blocks[0], re.M))

    for block in blocks[1:]:
        head = re.match(r"CRITERION[ \t]+(\d+)[ \t]*:[ \t]*([^\n]*)", block)
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

    crits = ledger["criteria"]
    if not crits:
        defects.append("no CRITERION blocks found")
        return ledger, defects
    if ledger["mode"] is None:
        defects.append("missing 'mode: FULL' or 'mode: STRUCTURED' line")
    if ledger["stray_verdicts"]:
        defects.append("VERDICT line before the first CRITERION (every verdict must sit inside its criterion)")

    # Without this a ledger holding only "CRITERION 3" validated: a dropped
    # criterion was indistinguishable from a requirement nobody checked.
    nums = [c["n"] for c in crits]
    if nums != list(range(1, len(nums) + 1)):
        defects.append(f"criteria must be numbered 1..N in order with no gaps or repeats, found {nums}")

    # The manifest was fixed before the code was read. Each of its criteria must
    # come back under the same number, word for word; what the verifier adds
    # goes after them.
    if manifest is not None:
        by_n = {c["n"]: c for c in crits}
        for want in manifest["criteria"]:
            got = by_n.get(want["id"])
            if got is None:
                defects.append(f"criterion {want['id']} of the manifest is missing from the ledger: {want['text']!r}")
            elif _norm(got["text"]) != _norm(want["text"]):
                defects.append(f"criterion {want['id']} does not match the manifest; copy its text exactly: {want['text']!r}")

    exercised = [c for c in crits if c["verdict"] in ("PASS", "FAIL")]
    if ledger["mode"] == "STRUCTURED" and len(exercised) > STRUCTURED_BUDGET:
        defects.append(
            f"STRUCTURED mode allows at most {STRUCTURED_BUDGET} exercised criteria, found {len(exercised)} "
            "(list requirements beyond the budget as NOT-EXERCISED)")

    for c in crits:
        n = c["n"]
        if not c["text"]:
            defects.append(f"criterion {n}: empty criterion text")
        if c["verdicts"] > 1:
            defects.append(
                f"criterion {n}: {c['verdicts']} VERDICT lines, exactly one is allowed "
                "(indent any captured output line that starts with a ledger keyword)")
        if c["verdict"] not in VERDICTS:
            defects.append(f"criterion {n}: VERDICT must be PASS|FAIL|NOT-EXERCISED, got {c['verdict']!r}")
            continue
        if c["verdict"] in ("PASS", "FAIL"):
            if not c["cmd"]:
                defects.append(f"criterion {n}: {c['verdict']} without EVIDENCE-CMD")
            out = c["out"] or ""
            only_fields = out and all(
                re.match(r"^(VERDICT|EVIDENCE-CMD|EVIDENCE-OUT|REASON|CRITERION\s+\d+|FINAL|OBSERVATIONS)\b", l.strip())
                for l in out.splitlines() if l.strip())
            if not out or only_fields:
                defects.append(f"criterion {n}: {c['verdict']} without EVIDENCE-OUT (evidence is required, 'looks right' is not evidence)")
        else:
            if not c["reason"]:
                defects.append(f"criterion {n}: NOT-EXERCISED without REASON")

    final = ledger["final"]
    if not final:
        defects.append("missing FINAL line")
        return ledger, defects

    failed = sorted(c["n"] for c in crits if c["verdict"] == "FAIL")
    unexercised = sorted(c["n"] for c in crits if c["verdict"] == "NOT-EXERCISED")
    judged = all(c["verdict"] in VERDICTS for c in crits)
    if judged:
        if failed:
            if not final.startswith("DRIFTED"):
                defects.append(f"FINAL must be DRIFTED (criteria {failed} failed), got {final!r}")
            else:
                listed = {int(x) for x in re.findall(r"\d+", final)}
                missing = [n for n in failed if n not in listed]
                if missing:
                    defects.append(f"FINAL DRIFTED must list every failed criterion; missing {missing}")
        elif unexercised:
            if not final.startswith("INCONCLUSIVE"):
                defects.append(
                    f"FINAL must be INCONCLUSIVE (criteria {unexercised} not exercised, none failed) — "
                    f"a criterion nobody exercised cannot be laundered into MATCHES INTENT; got {final!r}")
        else:
            if not final.startswith("MATCHES INTENT"):
                defects.append(f"all criteria PASS but FINAL is {final!r}; expected MATCHES INTENT")
    return ledger, defects


def verdict_of(ledger):
    f = ledger.get("final") or ""
    for v in ("MATCHES INTENT", "DRIFTED", "INCONCLUSIVE"):
        if f.startswith(v):
            return v
    return None


# ------------------------------------------------------------------ manifests
def _find_json_object(text, key):
    """The first JSON object in a model's reply that has `key`; prose and code
    fences around it are ignored."""
    decoder = json.JSONDecoder()
    for m in re.finditer(r"\{", text):
        try:
            obj, _end = decoder.raw_decode(text, m.start())
        except ValueError:
            continue
        if isinstance(obj, dict) and key in obj:
            return obj
    return None


def check_manifest(text, request=None):
    """Validate a criterion manifest. Returns (manifest, defects, notes): the
    manifest in normalised form, and as notes the parts of the request that no
    criterion quotes."""
    obj = _find_json_object(text, "criteria")
    if obj is None:
        return None, ["no JSON object with a 'criteria' list found"], []
    raw = obj.get("criteria")
    if not isinstance(raw, list) or not raw:
        return None, ["'criteria' must be a non-empty list"], []

    defects, criteria = [], []
    wanted = _norm(request) if request is not None else None
    for i, c in enumerate(raw, 1):
        if not isinstance(c, dict):
            defects.append(f"criterion {i}: must be an object with id, text and quote")
            continue
        if c.get("id") != i:
            defects.append(f"criterion {i}: ids must run 1..N in order, found id {c.get('id')!r}")
        body, quote = c.get("text"), c.get("quote")
        if not isinstance(body, str) or not body.strip() or "\n" in body.strip():
            defects.append(f"criterion {i}: 'text' must be one non-empty line")
            body = ""
        if quote is not None and (not isinstance(quote, str) or not quote.strip()):
            defects.append(f"criterion {i}: 'quote' must be a piece of the request, or null")
            quote = None
        elif quote is not None and wanted is not None and _norm(quote) not in wanted:
            defects.append(f"criterion {i}: its quote does not occur in the request: {quote!r}")
        criteria.append({"id": i, "text": " ".join(body.split()), "quote": quote})

    ambiguities = obj.get("ambiguities") or []
    if not isinstance(ambiguities, list) or not all(isinstance(a, str) for a in ambiguities):
        defects.append("'ambiguities' must be a list of strings")
        ambiguities = []
    manifest = {"manifest": 1, "criteria": criteria, "ambiguities": [a.strip() for a in ambiguities if a.strip()]}
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
        s = re.sub(r"^\s*(?:[-*+]|\d+[.)])\s+", "", line).strip()
        s = re.sub(r"^\[[ xX]\]\s+", "", s)
        if s and not s.startswith("#"):
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
    for d in defects:
        print(f"DEFECT: {d}")
    print(f"INVALID ({len(defects)} defect(s))")
    return 1


def _emit_manifest(manifest, notes, out):
    print(f"VALID: {len(manifest['criteria'])} criteria")
    for c in manifest["criteria"]:
        print(f"  {c['id']}. {c['text']}  " + (f"[quote: {c['quote']!r}]" if c["quote"] else "[no quote]"))
    for a in manifest["ambiguities"]:
        print(f"AMBIGUITY: {a}")
    for n in notes:
        print(f"NOTE: no criterion quotes this part of the request: {n}")
    if out:
        with open(out, "w", encoding="utf-8", newline="\n") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)
            f.write("\n")
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
        epilog="Exit codes: 0 valid, 1 invalid (defects listed), 2 usage error or unreadable file.")
    ap.add_argument("ledger", nargs="?", help="a verifier's reply, or - for stdin")
    ap.add_argument("--manifest", metavar="FILE", help="criteria the ledger must cover")
    ap.add_argument("--check-manifest", metavar="REPLY", help="validate a criteria deriver's reply instead of a ledger")
    ap.add_argument("--request", metavar="FILE", help="with --check-manifest: the frozen request each quote must occur in")
    ap.add_argument("--manifest-from", metavar="FILE", help="build a manifest from criteria you already have, one per line")
    ap.add_argument("--out", metavar="FILE", help="with --check-manifest or --manifest-from: write the manifest here")
    a = ap.parse_args(argv[1:])
    if sum(x is not None for x in (a.ledger, a.check_manifest, a.manifest_from)) != 1:
        ap.print_usage(sys.stderr)
        print("validate_ledger.py: give a ledger, or --check-manifest, or --manifest-from", file=sys.stderr)
        return 2

    try:
        if a.manifest_from is not None:
            manifest = manifest_from_lines(_read(a.manifest_from))
            if not manifest["criteria"]:
                return _report(["no criteria found (one per line)"])
            return _emit_manifest(manifest, [], a.out)
        if a.check_manifest is not None:
            request = _read(a.request) if a.request else None
            manifest, defects, notes = check_manifest(_read(a.check_manifest), request)
            return _report(defects) if defects else _emit_manifest(manifest, notes, a.out)

        manifest = None
        if a.manifest:
            manifest, defects, _notes = check_manifest(_read(a.manifest))
            if defects:
                print(f"validate_ledger.py: {a.manifest} is not a valid manifest: {defects[0]}", file=sys.stderr)
                return 2
        text = _read(a.ledger)
    except OSError as e:
        # Exit 1 means "invalid". A file that is not there is a different problem.
        print(f"validate_ledger.py: cannot read or write {e.filename}: {e.strerror}", file=sys.stderr)
        return 2

    ledger, defects = validate(text, manifest)
    if defects:
        return _report(defects)
    covered = f" (all {len(manifest['criteria'])} manifest criteria covered)" if manifest else ""
    print(f"VALID: {len(ledger['criteria'])} criteria{covered}, final = {ledger['final']}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
