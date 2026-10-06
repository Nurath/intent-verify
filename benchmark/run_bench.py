#!/usr/bin/env python3
"""Runnable benchmark harness for intent-verify.

Two things previously only existed as prose in results/*.md: the cases and the
method. This harness makes them executable.

MODES
  --mode mock   (default, offline, deterministic)
      Exercises the ORCHESTRATION layer — extract → validate against the
      criterion manifest → bounded retry → classify (SKILL.md) — against
      simulated verifier profiles that reproduce how real models degrade with
      capability (docs/MODEL-COMPAT.md):
        faithful    T1-like: correct ledger; evidence comes from REAL execution
                    of the fixture via benchmark/oracle.py
        verbose     correct but buried in chatter and code fences
        sloppy      malformed ledger first, clean on the single allowed retry
        lazy        verdicts without evidence; stays lazy on retry
        omitter     reports only what passes and leaves out what would fail.
                    Its ledgers are well-formed with real evidence, so only the
                    manifest catches it; the report shows both sides
        fabricator  fluent, plausible, WRONG — simulates the T4 failure mode
                    that validation cannot catch (why selection floors exist)
      Scored on: verdict accuracy, false-MATCHES rate, retry usage, and
      INCONCLUSIVE-instead-of-laundering behavior.

      What mock mode does NOT measure: real model verifier skill. It measures
      whether the pipeline around the verifier is robust to each documented
      failure shape.

  --mode cli    (real models; requires the `claude` CLI on PATH, logged in)
      Runs the actual verifier prompt (agents/verifier.md) against each case on
      a real model, then the same validation loop:
        python3 benchmark/run_bench.py --mode cli --verifier claude-opus-4-8
      With --two-stage the criteria are derived first, by agents/criteria.md,
      from the request alone and with every tool disabled; the verifier is then
      held to that manifest. Without it the verifier is handed the request and
      the code together, as before. Every call runs in `claude -p --safe-mode`
      and its tokens, cost and duration are recorded beside the raw replies.

Writes a results file under benchmark/results/ unless --no-write.
"""
import argparse
import datetime as _dt
import json
import os
import re
import secrets
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "tools"))

# The report contains non-ASCII (e.g. the arrow in profile summaries) and Windows
# consoles default to a legacy codepage (cp1252), where `print(report)` raises
# UnicodeEncodeError and kills the run. Force UTF-8 on the streams we write.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):  # pragma: no cover - non-reconfigurable stream
        pass

import validate_ledger  # noqa: E402
from oracle import CHECKS  # noqa: E402

MAX_RETRIES = 1  # SKILL.md: one bounded re-request, then INCONCLUSIVE. Never a loop.


def _read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


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


def manifest_for(case):
    """The oracle's criteria, as the manifest a deriver would have fixed."""
    return {"manifest": 1, "ambiguities": [],
            "criteria": [{"id": i, "text": text, "quote": None}
                         for i, (text, _expr, _expected) in enumerate(CHECKS[case["id"]], 1)]}


def _ledger(results):
    """results: [(criterion text, command, output, expected)]. Verdicts follow the output."""
    lines = ["INTENT-VERIFY LEDGER v1", "mode: FULL", ""]
    failed = []
    for i, (text, cmd, out, expected) in enumerate(results, 1):
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


def _run_checks(case):
    fixture = os.path.join(HERE, case["fixture"])
    return [(text,) + run_check(fixture, expr) + (expected,) for text, expr, expected in CHECKS[case["id"]]]


def faithful_ledger(case):
    """Build a ledger the way an ideal verifier would: criteria from the
    request's checks, verdicts from real execution."""
    return _ledger(_run_checks(case))


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


def profile_omitter(case, attempt, defects=None):
    """Reports only what passes. A check that fails is simply not mentioned,
    and a fully correct fixture loses its last criterion. Every line is true
    and the ledger is well-formed; the verdict is wrong by omission. Where
    nothing passes there is nothing to hide behind and it reports honestly."""
    results = _run_checks(case)
    passing = [r for r in results if r[2] == r[3]]
    if not passing:
        return _ledger(results)
    if len(passing) == len(results) and len(results) > 1:
        passing = passing[:-1]
    return _ledger(passing)


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
    "omitter": (profile_omitter, "any tier"),
    "fabricator": (profile_fabricator, "T4-like"),
}


# ---------------------------------------------------- orchestration under test
class VerifierUnavailable(Exception):
    """The model produced no reply to judge (timeout, launch failure, crash).
    That is not a malformed ledger, so it earns no re-request: the case is
    INCONCLUSIVE and the suite moves on."""


def orchestrate(produce, case, manifest=None, check=None):
    """Reference implementation of the skill's validation step: validate (against
    the manifest when there is one), one bounded re-request naming the defects,
    then classify. Returns (verdict, meta); meta["attempts"] holds every raw
    reply so a real run can be audited. `check` replaces the text-ledger
    validator, with the same signature (m4_json_ledger.py uses it)."""
    retries = 0
    last_defects = None
    attempts = []
    for attempt in range(MAX_RETRIES + 1):
        try:
            text = produce(case, attempt, last_defects)
        except VerifierUnavailable as e:
            return "INCONCLUSIVE", {"retries": retries, "defects": ["verifier unavailable: %s" % e], "attempts": attempts}
        attempts.append(text)
        ledger, defects = (check or validate_ledger.validate)(text, manifest)
        if not defects:
            return validate_ledger.verdict_of(ledger), {"retries": retries, "defects": [], "attempts": attempts}
        retries += 1 if attempt < MAX_RETRIES else 0
        last_defects = defects
    return "INCONCLUSIVE", {"retries": MAX_RETRIES, "defects": last_defects, "attempts": attempts}


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
def _agent_body(name):
    agent = _read(os.path.join(ROOT, "agents", name))
    return (agent.split("---", 2)[2] if agent.startswith("---") else agent).strip()


def build_criteria_prompt(case):
    """Stage 1 sees the request and nothing else: no path, no code."""
    return _agent_body("criteria.md") + "\n\n---\nREQUEST:\n" + case["request"] + "\n"


def build_verifier_prompt(case, manifest=None, nonce=None):
    fixture = os.path.join(HERE, case["fixture"])
    prompt = (
        _agent_body("verifier.md")
        + "\n\n---\nMODE: FULL\n" + ("RUN NONCE: %s\n" % nonce if nonce else "")
        + "\nORIGINAL REQUEST (frozen, ground truth):\n\"%s\"\n\n" % case["request"]
        + "CODE TO VERIFY: %s\n" % fixture
        + "Its content:\n```python\n%s```\n\n" % _read(fixture)
    )
    if manifest:
        prompt += ("MANIFEST (these criteria were fixed before anyone read the code; copy each one into "
                   "your ledger under the same number with the same text):\n"
                   + "\n".join("%d. %s" % (c["id"], c["text"]) for c in manifest["criteria"])
                   + "\n\nRun the code")
    else:
        prompt += "Derive criteria from the request first, run the code"
    return prompt + " (python3, or python where python3 is not installed), then emit the ledger."


def _retry_note(defects, previous, what):
    if not defects:
        return ""
    note = "\n\nYour previous reply was REJECTED by mechanical validation for these defects:\n- " + "\n- ".join(defects)
    if previous:
        # A fresh `claude -p` remembers nothing: without its own reply it could
        # only redo the work, not correct what it already produced.
        note += "\n\nYour previous reply was:\n<<<\n" + previous[-20000:] + "\n>>>"
    return note + "\nEmit a corrected %s and nothing else." % what


USAGE = []  # one record per model call, in call order; main() reads it per case


def run_cli(prompt, model, timeout, no_tools=False):
    # Launch what PATH resolves to: on Windows the CLI can be a .cmd shim, which
    # a bare "claude" cannot start (only .exe is tried). --safe-mode leaves out
    # the runner's own CLAUDE.md, plugins, hooks and MCP servers, so a result
    # does not depend on whose machine produced it, and an installed
    # intent-verify does not log every benchmark prompt. (--bare would too, but
    # it ignores OAuth logins.)
    cmd = [shutil.which("claude") or "claude", "-p", "--safe-mode", "--output-format", "json",
           "--model", model, "--max-turns", "15"]
    cmd += ["--tools", ""] if no_tools else ["--allowedTools", "Bash,Read,Grep,Glob"]
    try:
        r = subprocess.run(cmd, input=prompt, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=timeout)
    except subprocess.TimeoutExpired:
        raise VerifierUnavailable("timed out after %ds" % timeout)
    except OSError as e:
        raise VerifierUnavailable("could not launch `claude`: %s" % e)
    if r.returncode != 0 and not (r.stdout or "").strip():
        raise VerifierUnavailable("exit %d: %s" % (r.returncode, (r.stderr or "").strip()[-300:]))
    try:
        d = json.loads(r.stdout)
    except ValueError:
        d = None
    if not (isinstance(d, dict) and d.get("type") == "result"):
        return r.stdout  # not the CLI's envelope: judge the text as it came
    u = d.get("usage") or {}
    USAGE.append({
        "stage": 1 if no_tools else 2, "session": d.get("session_id"), "subtype": d.get("subtype"),
        "turns": d.get("num_turns"), "seconds": (d.get("duration_ms") or 0) / 1000.0,
        "cost_usd": d.get("total_cost_usd") or 0,
        "tokens": sum(u.get(k) or 0 for k in ("input_tokens", "cache_creation_input_tokens",
                                              "cache_read_input_tokens", "output_tokens")),
    })
    if d.get("is_error"):
        # Out of turns, or an API error: there is no reply to correct.
        raise VerifierUnavailable("%s: %s" % (d.get("subtype"), str(d.get("result") or "")[-300:]))
    return d.get("result") or ""


def run_cli_verifier(case, model, timeout, defects=None, previous=None, manifest=None, nonce=None):
    what = "ledger JSON object carrying the run nonce" if nonce else validate_ledger.HEADER
    prompt = build_verifier_prompt(case, manifest, nonce) + _retry_note(defects, previous, what)
    return run_cli(prompt, model, timeout)


def as_json(text, nonce):
    """A text ledger rewritten as the sealed JSON ledger the verifier writes, for
    simulated verifiers. Text that holds no ledger is returned as is."""
    ledger, _ = validate_ledger.parse(text)
    if ledger is None:
        return text
    crits = [{k: v for k, v in (("id", c["n"]), ("text", c["text"]), ("verdict", c["verdict"]),
                                ("cmd", c["cmd"]), ("out", c["out"]), ("reason", c["reason"])) if v is not None}
             for c in ledger["criteria"]]
    return json.dumps({"ledger": 2, "nonce": nonce, "mode": ledger["mode"], "criteria": crits,
                       "final": ledger["final"], "seal": nonce}, ensure_ascii=False)


def derive_manifest(case, model, timeout):
    """Stage 1 on a real model, with every tool disabled: the deriver cannot
    look at the fixture. One bounded retry. Returns (manifest or None, replies)."""
    replies, defects = [], None
    for _ in range(MAX_RETRIES + 1):
        prompt = build_criteria_prompt(case) + _retry_note(defects, replies[-1] if replies else None, "manifest JSON object")
        replies.append(run_cli(prompt, model, timeout, no_tools=True))
        manifest, defects, _notes = validate_ledger.check_manifest(replies[-1], case["request"])
        if not defects:
            return manifest, replies
    return None, replies


# ----------------------------------------------------------------------- main
def main(argv=None):
    ap = argparse.ArgumentParser(description="intent-verify benchmark harness")
    ap.add_argument("--mode", choices=["mock", "cli"], default="mock")
    ap.add_argument("--suite", default="controlled", choices=["controlled", "field", "field-recall", "adversarial", "all"])
    ap.add_argument("--profiles", nargs="+", default=list(PROFILES), choices=list(PROFILES))
    ap.add_argument("--verifier", help="[cli] model to run the verifier on, e.g. claude-opus-4-8")
    ap.add_argument("--two-stage", action="store_true",
                    help="[cli] derive a criterion manifest from the request alone first, then hold the verifier to it")
    ap.add_argument("--timeout", type=int, default=600, help="[cli] per-case seconds")
    ap.add_argument("--no-write", action="store_true", help="don't write a results file")
    ap.add_argument("--label", help="[cli] suffix for the results file name, so a re-run keeps the earlier one")
    a = ap.parse_args(argv)

    cases = json.loads(_read(os.path.join(HERE, "cases.json")))["cases"]
    if a.suite != "all":
        cases = [c for c in cases if c["suite"] == a.suite]
    if a.mode == "mock":
        cases = [c for c in cases if c["id"] in CHECKS]  # oracle-backed only

    stamp = _dt.date.today().isoformat()
    out = []

    if a.mode == "mock":
        out.append("# Benchmark — %s — mock orchestration robustness (suite: %s, n=%d)\n" % (stamp, a.suite, len(cases)))
        out.append("Generated by `python3 benchmark/run_bench.py --mode mock`. Measures the pipeline")
        out.append("(extract → validate against the criterion manifest → one bounded retry → classify),")
        out.append("NOT real model skill. Verifier profiles simulate the capability-degradation failure")
        out.append("modes in docs/MODEL-COMPAT.md.\n")
        exit_bad = False

        def run(fn, with_manifest):
            return [{"id": c["id"], "expected": c["expected"],
                     **dict(zip(("got", "meta"), orchestrate(fn, c, manifest_for(c) if with_manifest else None)))}
                    for c in cases]

        for name in a.profiles:
            fn, tier = PROFILES[name]
            s = score(run(fn, True))
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
            if name == "omitter":
                bare = score(run(fn, False))
                out.append("| false MATCHES on drifted code, validated WITHOUT a manifest | %d |" % bare["false_match"])
                # Both halves matter: the profile must slip past bare validation
                # (or it tests nothing) and must not slip past the manifest.
                if s["false_match"] > 0 or bare["false_match"] == 0:
                    exit_bad = True
                    out.append("\n**REGRESSION: the manifest must turn every omitter false match into INCONCLUSIVE.**")
            out.append("")
            # Pipeline robustness assertions (what this mode actually tests):
            if name in ("faithful", "verbose", "sloppy") and s["correct"] != s["n"]:
                exit_bad = True
                out.append("**REGRESSION: %s profile should reach %d/%d.**\n" % (name, s["n"], s["n"]))
            if name == "lazy" and (s["false_match"] > 0 or s["inconclusive"] != s["n"]):
                exit_bad = True
                out.append("**REGRESSION: lazy profile must yield INCONCLUSIVE everywhere, never MATCHES.**\n")
        out.append("## Reading the omitter row\n")
        out.append("The omitter's ledgers are well-formed and every line in them is true: it just never")
        out.append("mentions the criterion that would fail. Validated alone they pass. Held to a manifest")
        out.append("fixed before the code was read, the missing criterion is a defect and the result is")
        out.append("INCONCLUSIVE. That is the whole case for two-stage verification.\n")
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
        out.append("# Benchmark — %s — real verifier: %s%s (suite: %s, n=%d)\n" % (
            stamp, a.verifier, ", two-stage (criteria fixed first, by the same model)" if a.two_stage else "",
            a.suite, len(cases)))
        out.append("Each call is `claude -p --safe-mode`: none of the runner's own CLAUDE.md, plugins,")
        out.append("hooks or MCP servers are loaded. Tokens and cost are as the CLI reports them; the")
        out.append("cost is at list price, whatever plan the runner is on.\n")
        rows = []
        for c in cases:
            first_call = len(USAGE)
            manifest, stage1 = None, []
            if a.two_stage:
                try:
                    manifest, stage1 = derive_manifest(c, a.verifier, a.timeout)
                    failure = "no valid criterion manifest after the retry"
                except VerifierUnavailable as e:
                    failure = "criteria deriver unavailable: %s" % e
            if a.two_stage and manifest is None:
                got, meta = "INCONCLUSIVE", {"retries": 0, "defects": [failure], "attempts": []}
            else:
                # A run of its own, as the skill makes: the verifier copies the
                # nonce into its JSON ledger, and only that ledger counts.
                replies, nonce = [], secrets.token_hex(16)

                def produce(case, attempt, defects, _c=c, _replies=replies, _manifest=manifest, _nonce=nonce):
                    text = run_cli_verifier(_c, a.verifier, a.timeout, defects,
                                            _replies[-1] if _replies else None, _manifest, _nonce)
                    _replies.append(text)
                    return text
                got, meta = orchestrate(produce, c, manifest,
                                        lambda text, m, _n=nonce: validate_ledger.validate_json(text, m, _n))
            meta["stage1"], meta["manifest"] = stage1, manifest
            meta["calls"] = USAGE[first_call:]
            rows.append({"id": c["id"], "expected": c["expected"], "got": got, "meta": meta})
            print("%-18s expected=%-14s got=%-14s retries=%d" % (c["id"], c["expected"], got, meta["retries"]))
        s = score(rows)
        out.append("| metric | value |\n|---|---|")
        for k, v in s.items():
            out.append("| %s | %s |" % (k, v))
        calls = [u for r in rows for u in r["meta"]["calls"]]
        if calls:
            out.append("| model calls | %d |" % len(calls))
            out.append("| tokens, all calls | %d |" % sum(u["tokens"] for u in calls))
            out.append("| cost, USD at list price | %.2f |" % sum(u["cost_usd"] for u in calls))
            out.append("| model time, minutes | %.1f |" % (sum(u["seconds"] for u in calls) / 60))
        manifests = [r["meta"]["manifest"] for r in rows if r["meta"]["manifest"]]
        if manifests:
            out.append("| ambiguities kept: each names the criteria that depend on it | %d |"
                       % sum(len(m["ambiguities"]) for m in manifests))
            out.append("| ambiguities dropped: no criterion depends on them | %d |"
                       % sum(m.get("unlinked_ambiguities", 0) for m in manifests))
        out.append("\n| case | expected | got | retries | manifest criteria | stage-1 tokens | stage-2 tokens | note |\n"
                   "|---|---|---|---|---|---|---|---|")
        for r in rows:
            note = "; ".join(r["meta"]["defects"])[:160].replace("|", "/")
            size = len(r["meta"]["manifest"]["criteria"]) if r["meta"]["manifest"] else "-"
            tokens = [sum(u["tokens"] for u in r["meta"]["calls"] if u["stage"] == n) for n in (1, 2)]
            out.append("| %s | %s | %s | %d | %s | %d | %d | %s |" % (
                r["id"], r["expected"], r["got"], r["meta"]["retries"], size, tokens[0], tokens[1], note))
        exit_bad = s["false_match"] > 0

    report = "\n".join(out) + "\n"
    print(report)
    if not a.no_write:
        if a.mode == "mock":
            name = "mock-orchestration"
        else:
            name = "cli-" + re.sub(r"[^A-Za-z0-9._-]", "_", a.verifier) + ("-two-stage" if a.two_stage else "")
            name += "-" + re.sub(r"[^A-Za-z0-9._-]", "_", a.label) if a.label else ""
        dest = os.path.join(HERE, "results", "%s-%s.md" % (stamp, name))
        with open(dest, "w", encoding="utf-8") as f:
            f.write(report)
        print("written: %s" % os.path.relpath(dest, ROOT), file=sys.stderr)
        if a.mode == "cli":
            # Verdicts alone cannot be audited: keep every raw reply beside the report.
            raw_dir = dest[:-3] + ".raw"
            os.makedirs(raw_dir, exist_ok=True)
            for r in rows:
                files = [("%s.%d.txt" % (r["id"], i), text) for i, text in enumerate(r["meta"]["attempts"])]
                files += [("%s.criteria.%d.txt" % (r["id"], i), text) for i, text in enumerate(r["meta"]["stage1"])]
                for fname, text in files:
                    with open(os.path.join(raw_dir, fname), "w", encoding="utf-8") as f:
                        f.write(text or "")
            with open(os.path.join(raw_dir, "usage.json"), "w", encoding="utf-8") as f:
                json.dump({r["id"]: r["meta"]["calls"] for r in rows}, f, indent=1)
    return 1 if exit_bad else 0


if __name__ == "__main__":
    sys.exit(main())
