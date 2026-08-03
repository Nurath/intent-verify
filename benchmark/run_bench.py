#!/usr/bin/env python3
"""Runnable benchmark harness for intent-verify.

Two things previously only existed as prose in results/*.md: the cases and the
method. This harness makes them executable.

MODES
  --mode mock   (default, offline, deterministic)
      Exercises the ORCHESTRATION layer — extract → validate → bounded retry →
      classify (SKILL.md step 6) — against simulated verifier profiles that
      reproduce how real models degrade with capability (docs/MODEL-COMPAT.md):
        faithful    T1-like: correct ledger; evidence comes from REAL execution
                    of the fixture via benchmark/oracle.py
        verbose     correct but buried in chatter and code fences
        sloppy      malformed ledger first, clean on the single allowed retry
        lazy        verdicts without evidence; stays lazy on retry
        fabricator  fluent, plausible, WRONG — simulates the T4 failure mode
                    that validation cannot catch (why selection floors exist)
      Scored on: verdict accuracy, false-MATCHES rate, retry usage, and
      INCONCLUSIVE-instead-of-laundering behavior.

      What mock mode does NOT measure: real model verifier skill. It measures
      whether the pipeline around the verifier is robust to each documented
      failure shape.

  --mode cli    (real models; requires the `claude` CLI on PATH)
      Runs the actual verifier prompt (agents/verifier.md) against each case on
      a real model, then the same validation loop:
        python3 benchmark/run_bench.py --mode cli --verifier claude-opus-4-8
      Records the model, tier (models/registry.json), and per-case verdicts.

Writes a results file under benchmark/results/ unless --no-write.
"""
import argparse
import datetime as _dt
import json
import os
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "tools"))

import validate_ledger  # noqa: E402
from oracle import CHECKS  # noqa: E402

MAX_RETRIES = 1  # SKILL.md: one bounded re-request, then INCONCLUSIVE. Never a loop.


# ---------------------------------------------------------------- oracle runs
def run_check(fixture_path, expr):
    code = (
        "import importlib.util as u; spec=u.spec_from_file_location('m', %r); "
        "m=u.module_from_spec(spec); spec.loader.exec_module(m); print(%s)" % (fixture_path, expr)
    )
    cmd = [sys.executable, "-c", code]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=15,
                           env={**os.environ, "PYTHONHASHSEED": "0"})
        out = (r.stdout or r.stderr).strip()
    except subprocess.TimeoutExpired:
        out = "<timeout after 15s>"
    return "python3 -c \"...%s...\"" % expr.replace('"', "'"), out


def faithful_ledger(case):
    """Build a ledger the way an ideal verifier would: criteria from the
    request's checks, verdicts from real execution."""
    checks = CHECKS[case["id"]]
    fixture = os.path.join(HERE, case["fixture"])
    lines = ["INTENT-VERIFY LEDGER v1", "mode: FULL", ""]
    failed = []
    for i, (text, expr, expected) in enumerate(checks, 1):
        cmd, out = run_check(fixture, expr)
        ok = out == expected
        if not ok:
            failed.append(i)
        lines += [
            "CRITERION %d: %s" % (i, text),
            "VERDICT: %s" % ("PASS" if ok else "FAIL"),
            "EVIDENCE-CMD: %s" % cmd,
            "EVIDENCE-OUT: %s (expected %s)" % (out, expected),
            "",
        ]
    final = ("DRIFTED — criteria %s failed" % ", ".join(map(str, failed))) if failed else "MATCHES INTENT"
    lines.append("FINAL: %s" % final)
    return "\n".join(lines)


# ------------------------------------------------------------- mock profiles
def profile_faithful(case, attempt, defects=None):
    return faithful_ledger(case)


def profile_verbose(case, attempt, defects=None):
    core = faithful_ledger(case)
    return (
        "Great question! I carefully verified the change as an independent reviewer.\n"
        "Let me walk you through my thinking first...\n\n"
        "After deriving criteria from the original request alone, I ran the code.\n"
        "Here are my results:\n\n```\n" + core + "\n```\n\n"
        "I hope this helps! Let me know if you need anything else.\n"
    )


def profile_sloppy(case, attempt, defects=None):
    core = faithful_ledger(case)
    if attempt == 0:
        # lowercase field names, missing FINAL — a typical weak-model rendition
        mangled = core.replace("VERDICT:", "verdict:").replace("INTENT-VERIFY LEDGER v1", "my verification notes")
        return "\n".join(l for l in mangled.splitlines() if not l.startswith("FINAL:"))
    return core  # a named-defect re-request straightens it out


def profile_lazy(case, attempt, defects=None):
    checks = CHECKS[case["id"]]
    lines = ["INTENT-VERIFY LEDGER v1", "mode: STRUCTURED", ""]
    for i, (text, _e, _x) in enumerate(checks, 1):
        lines += ["CRITERION %d: %s" % (i, text), "VERDICT: PASS", ""]  # no evidence, any attempt
    lines.append("FINAL: MATCHES INTENT")
    return "\n".join(lines)


def profile_fabricator(case, attempt, defects=None):
    checks = CHECKS[case["id"]]
    lines = ["INTENT-VERIFY LEDGER v1", "mode: FULL", ""]
    for i, (text, expr, expected) in enumerate(checks, 1):
        lines += [
            "CRITERION %d: %s" % (i, text),
            "VERDICT: PASS",
            "EVIDENCE-CMD: python3 -c \"...%s...\"" % expr.replace('"', "'"),
            "EVIDENCE-OUT: %s (expected %s)" % (expected, expected),  # never executed
            "",
        ]
    lines.append("FINAL: MATCHES INTENT")
    return "\n".join(lines)


PROFILES = {
    "faithful": (profile_faithful, "T1-like"),
    "verbose": (profile_verbose, "T2-like"),
    "sloppy": (profile_sloppy, "T3-like"),
    "lazy": (profile_lazy, "T3/T4-like"),
    "fabricator": (profile_fabricator, "T4-like"),
}


# ---------------------------------------------------- orchestration under test
def orchestrate(produce, case):
    """Reference implementation of SKILL.md step 6: validate, one bounded
    re-request naming the defects, then classify. Returns (verdict, meta)."""
    retries = 0
    last_defects = None
    for attempt in range(MAX_RETRIES + 1):
        text = produce(case, attempt, last_defects)
        ledger, defects = validate_ledger.validate(text)
        if not defects:
            return validate_ledger.verdict_of(ledger), {"retries": retries, "defects": []}
        retries += 1 if attempt < MAX_RETRIES else 0
        last_defects = defects
    return "INCONCLUSIVE", {"retries": MAX_RETRIES, "defects": last_defects}


def score(rows):
    n = len(rows)
    correct = sum(1 for r in rows if r["got"] == r["expected"])
    false_match = sum(1 for r in rows if r["got"] == "MATCHES INTENT" and r["expected"] == "DRIFTED")
    missed_ok = sum(1 for r in rows if r["got"] == "DRIFTED" and r["expected"] == "MATCHES INTENT")
    inconclusive = sum(1 for r in rows if r["got"] == "INCONCLUSIVE")
    retried = sum(1 for r in rows if r["meta"]["retries"] > 0)
    return {
        "n": n, "correct": correct, "false_match": false_match,
        "false_alarm": missed_ok, "inconclusive": inconclusive, "retried": retried,
    }


# ----------------------------------------------------------------- cli mode
def build_verifier_prompt(case):
    agent = open(os.path.join(ROOT, "agents", "verifier.md"), encoding="utf-8").read()
    body = agent.split("---", 2)[2] if agent.startswith("---") else agent
    fixture = os.path.join(HERE, case["fixture"])
    return (
        body.strip()
        + "\n\n---\nMODE: FULL\n\nORIGINAL REQUEST (frozen, ground truth):\n\"%s\"\n\n" % case["request"]
        + "CODE TO VERIFY: %s\n" % fixture
        + "Its content:\n```python\n%s```\n\n" % open(fixture, encoding="utf-8").read()
        + "Derive criteria from the request first, run the code (python3 is available), then emit the ledger."
    )


def run_cli_verifier(case, model, timeout, defects=None):
    prompt = build_verifier_prompt(case)
    if defects:
        prompt += ("\n\nYour previous ledger was REJECTED by mechanical validation for these defects:\n- "
                   + "\n- ".join(defects)
                   + "\nEmit a corrected INTENT-VERIFY LEDGER v1 and nothing else.")
    cmd = ["claude", "-p", "--model", model, "--max-turns", "15",
           "--allowedTools", "Bash,Read,Grep,Glob"]
    r = subprocess.run(cmd, input=prompt, capture_output=True, text=True, timeout=timeout)
    return r.stdout


# ----------------------------------------------------------------------- main
def main(argv=None):
    ap = argparse.ArgumentParser(description="intent-verify benchmark harness")
    ap.add_argument("--mode", choices=["mock", "cli"], default="mock")
    ap.add_argument("--suite", default="controlled", choices=["controlled", "field", "field-recall", "all"])
    ap.add_argument("--profiles", nargs="+", default=list(PROFILES), choices=list(PROFILES))
    ap.add_argument("--verifier", help="[cli] model to run the verifier on, e.g. claude-opus-4-8")
    ap.add_argument("--timeout", type=int, default=600, help="[cli] per-case seconds")
    ap.add_argument("--no-write", action="store_true", help="don't write a results file")
    a = ap.parse_args(argv)

    cases = json.load(open(os.path.join(HERE, "cases.json"), encoding="utf-8"))["cases"]
    if a.suite != "all":
        cases = [c for c in cases if c["suite"] == a.suite]
    if a.mode == "mock":
        cases = [c for c in cases if c["id"] in CHECKS]  # oracle-backed only

    stamp = _dt.date.today().isoformat()
    out = []

    if a.mode == "mock":
        out.append("# Benchmark — %s — mock orchestration robustness (suite: %s, n=%d)\n" % (stamp, a.suite, len(cases)))
        out.append("Generated by `python3 benchmark/run_bench.py --mode mock`. Measures the pipeline")
        out.append("(extract → validate → one bounded retry → classify), NOT real model skill.")
        out.append("Verifier profiles simulate the capability-degradation failure modes in docs/MODEL-COMPAT.md.\n")
        exit_bad = False
        for name in a.profiles:
            fn, tier = PROFILES[name]
            rows = [{"id": c["id"], "expected": c["expected"], **dict(zip(("got", "meta"), orchestrate(fn, c)))} for c in cases]
            s = score(rows)
            out.append("## profile: %s (%s)\n" % (name, tier))
            out.append("| metric | value |\n|---|---|")
            out.append("| correct verdicts | %d/%d |" % (s["correct"], s["n"]))
            out.append("| false MATCHES on drifted code | %d |" % s["false_match"])
            out.append("| false alarms on correct code | %d |" % s["false_alarm"])
            out.append("| INCONCLUSIVE (honest refusals) | %d |" % s["inconclusive"])
            out.append("| cases needing the single retry | %d |" % s["retried"])
            if name == "fabricator":
                caught = s["false_match"] == 0
                out.append("| fabricated evidence caught by validation | %s |" %
                           ("yes" if caught else "**no — this is exactly why T4 models are excluded by selection, not validated harder**"))
            out.append("")
            # Pipeline robustness assertions (what this mode actually tests):
            if name in ("faithful", "verbose", "sloppy") and s["correct"] != s["n"]:
                exit_bad = True
                out.append("**REGRESSION: %s profile should reach %d/%d.**\n" % (name, s["n"], s["n"]))
            if name == "lazy" and (s["false_match"] > 0 or s["inconclusive"] != s["n"]):
                exit_bad = True
                out.append("**REGRESSION: lazy profile must yield INCONCLUSIVE everywhere, never MATCHES.**\n")
        out.append("## Reading the fabricator row\n")
        out.append("The fabricator writes well-formed ledgers with invented output. Validation is")
        out.append("structural, so it cannot catch this — by design the defense is `models/registry.json`")
        out.append("floors + `tools/select_verifier.py` refusing below-floor verifiers. The row is kept")
        out.append("in the report to make that boundary measurable and visible, not to celebrate it.\n")
    else:
        if not a.verifier:
            ap.error("--mode cli requires --verifier")
        if not shutil.which("claude"):
            print("ERROR: `claude` CLI not found on PATH; cli mode needs it (or use --mode mock).", file=sys.stderr)
            return 2
        out.append("# Benchmark — %s — real verifier: %s (suite: %s, n=%d)\n" % (stamp, a.verifier, a.suite, len(cases)))
        rows = []
        for c in cases:
            def produce(case, attempt, defects, _c=c):
                return run_cli_verifier(_c, a.verifier, a.timeout, defects)
            got, meta = orchestrate(produce, c)
            rows.append({"id": c["id"], "expected": c["expected"], "got": got, "meta": meta})
            print("%-18s expected=%-14s got=%-14s retries=%d" % (c["id"], c["expected"], got, meta["retries"]))
        s = score(rows)
        out.append("| metric | value |\n|---|---|")
        for k, v in s.items():
            out.append("| %s | %s |" % (k, v))
        out.append("\n| case | expected | got | retries |\n|---|---|---|---|")
        for r in rows:
            out.append("| %s | %s | %s | %d |" % (r["id"], r["expected"], r["got"], r["meta"]["retries"]))
        exit_bad = s["false_match"] > 0

    report = "\n".join(out) + "\n"
    print(report)
    if not a.no_write:
        dest = os.path.join(HERE, "results", "%s-%s.md" % (stamp, "mock-orchestration" if a.mode == "mock" else "cli-" + a.verifier))
        with open(dest, "w", encoding="utf-8") as f:
            f.write(report)
        print("written: %s" % os.path.relpath(dest, ROOT), file=sys.stderr)
    return 1 if exit_bad else 0


if __name__ == "__main__":
    sys.exit(main())
