#!/usr/bin/env python3
"""Machine validation of an intent-verify verifier ledger.

The verifier's output (agents/verifier.md) is only trustworthy if it kept the
evidence contract. This validator enforces, mechanically, the properties that a
lenient or weak verifier breaks first:

  - header present (INTENT-VERIFY LEDGER v1) and at least one criterion
  - every VERDICT is PASS | FAIL | NOT-EXERCISED
  - PASS and FAIL carry both EVIDENCE-CMD and non-empty EVIDENCE-OUT
  - NOT-EXERCISED carries a REASON
  - FINAL is present and CONSISTENT with the per-criterion verdicts:
      any FAIL            => DRIFTED, listing every failed criterion
      all PASS            => MATCHES INTENT
      no FAIL, some N-E   => INCONCLUSIVE
  - STRUCTURED mode: at most 5 criteria

It cannot detect *forged* output — that is why below-floor models are excluded
by selection rather than "validated harder" (see docs/MODEL-COMPAT.md).

Usage:
  python3 tools/validate_ledger.py <ledger-file>     # or - for stdin
Exit codes: 0 valid; 1 invalid (defects listed on stdout, one per line, so the
orchestrator can quote them in its single bounded re-request).
"""
import re
import sys

HEADER = "INTENT-VERIFY LEDGER v1"
VERDICTS = {"PASS", "FAIL", "NOT-EXERCISED"}


def extract_ledger(text):
    """Tolerate chatter/code-fences around the ledger: slice from the header to
    the end of the FINAL line (weak models love wrapping output in prose)."""
    i = text.find(HEADER)
    if i == -1:
        return None
    tail = text[i:]
    m = re.search(r"^FINAL:.*$", tail, re.M)
    return tail[: m.end()] if m else tail


def parse(text):
    ledger = {"mode": None, "criteria": [], "final": None}
    body = extract_ledger(text)
    if body is None:
        return None, ["missing header line 'INTENT-VERIFY LEDGER v1'"]

    m = re.search(r"^mode:\s*(FULL|STRUCTURED)\s*$", body, re.M)
    if m:
        ledger["mode"] = m.group(1)

    blocks = re.split(r"^(?=CRITERION\s+\d+\s*:)", body, flags=re.M)
    for block in blocks[1:]:
        head = re.match(r"CRITERION\s+(\d+)\s*:\s*(.*)", block)
        crit = {
            "n": int(head.group(1)),
            "text": head.group(2).strip(),
            "verdict": None,
            "cmd": None,
            "out": None,
            "reason": None,
        }
        vm = re.search(r"^VERDICT:\s*(\S[^\n]*)$", block, re.M)
        if vm:
            crit["verdict"] = vm.group(1).strip()
        cm = re.search(r"^EVIDENCE-CMD:\s*(.+)$", block, re.M)
        if cm:
            crit["cmd"] = cm.group(1).strip()
        om = re.search(r"^EVIDENCE-OUT:\s*(.*?)(?=^(?:VERDICT:|EVIDENCE-CMD:|REASON:|CRITERION\s+\d+\s*:|FINAL:|OBSERVATIONS:)|\Z)", block, re.M | re.S)
        if om:
            crit["out"] = om.group(1).strip()
        rm = re.search(r"^REASON:\s*(.+)$", block, re.M)
        if rm:
            crit["reason"] = rm.group(1).strip()
        ledger["criteria"].append(crit)

    fm = re.search(r"^FINAL:\s*(.+)$", body, re.M)
    if fm:
        ledger["final"] = fm.group(1).strip()
    return ledger, []


def validate(text):
    ledger, defects = parse(text)
    if ledger is None:
        return None, defects

    crits = ledger["criteria"]
    if not crits:
        defects.append("no CRITERION blocks found")
        return ledger, defects
    if ledger["mode"] == "STRUCTURED" and len(crits) > 5:
        defects.append(f"STRUCTURED mode allows at most 5 criteria, found {len(crits)}")

    seen = set()
    for c in crits:
        n = c["n"]
        if n in seen:
            defects.append(f"criterion {n}: duplicate number")
        seen.add(n)
        if not c["text"]:
            defects.append(f"criterion {n}: empty criterion text")
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
    if len(argv) != 2:
        print(__doc__)
        return 2
    text = sys.stdin.read() if argv[1] == "-" else open(argv[1], encoding="utf-8").read()
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
