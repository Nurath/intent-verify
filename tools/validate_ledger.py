#!/usr/bin/env python3
"""Machine validation of an intent-verify verifier ledger.

The verifier's output (agents/verifier.md) is only trustworthy if it kept the
evidence contract. This validator enforces, mechanically, the properties that a
lenient or weak verifier breaks first:

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

What it cannot do:
  - detect *forged* output -- that is why below-floor models are excluded by
    selection rather than "validated harder" (see docs/MODEL-COMPAT.md);
  - know which requirements the request actually had. It checks that the ledger
    is internally complete, not that the verifier derived every criterion or
    that its reply was not cut off before later ones.

Usage:
  python3 tools/validate_ledger.py <ledger-file>     # or - for stdin
  (use `python` where `python3` is not installed, e.g. stock Windows)
Exit codes: 0 valid; 1 invalid (defects listed on stdout, one per line, so the
orchestrator can quote them in its single bounded re-request); 2 usage error.
Any other outcome means the validator itself failed, not the ledger.
"""
import re
import sys

HEADER = "INTENT-VERIFY LEDGER v1"
VERDICTS = {"PASS", "FAIL", "NOT-EXERCISED"}
STRUCTURED_BUDGET = 5

# Horizontal whitespace only. A single-line field's value must sit on the
# field's own line: with \s here an empty "EVIDENCE-CMD:" swallowed the line
# below it and the ledger validated.
_VALUE = r"[ \t]*(\S[^\n]*)$"
_CRIT_HEAD = r"CRITERION[ \t]+\d+[ \t]*:"
_FIELD_START = r"^(?:VERDICT:|EVIDENCE-CMD:|REASON:|" + _CRIT_HEAD + r"|FINAL:|OBSERVATIONS:)"


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
    body = extract_ledger(text.replace("\r\n", "\n").replace("\r", "\n"))
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


def validate(text):
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
    if len(argv) != 2:
        print(__doc__)
        return 2
    if argv[1] == "-":
        text = sys.stdin.read()
    else:
        with open(argv[1], encoding="utf-8", errors="replace") as f:
            text = f.read()
    ledger, defects = validate(text)
    if defects:
        for d in defects:
            print(f"DEFECT: {d}")
        print(f"INVALID ({len(defects)} defect(s))")
        return 1
    n = len(ledger["criteria"])
    print(f"VALID: {n} criteria, final = {ledger['final']}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
