import json
import os
import subprocess
import sys
import unittest
from unittest import mock

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE, "benchmark"))
sys.path.insert(0, os.path.join(BASE, "tools"))

import run_bench  # noqa: E402
from oracle import CHECKS  # noqa: E402

with open(os.path.join(BASE, "benchmark", "cases.json"), encoding="utf-8") as _f:
    CASES = {c["id"]: c for c in json.load(_f)["cases"]}


class TestOracle(unittest.TestCase):
    def test_every_controlled_case_has_checks_and_fixture(self):
        controlled = [c for c in CASES.values() if c["suite"] == "controlled"]
        self.assertEqual(len(controlled), 16)
        for c in controlled:
            self.assertIn(c["id"], CHECKS)
            self.assertTrue(os.path.exists(os.path.join(BASE, "benchmark", c["fixture"])), c["fixture"])

    def test_oracle_separates_drifted_from_correct(self):
        for cid, checks in CHECKS.items():
            case = CASES[cid]
            fixture = os.path.join(BASE, "benchmark", case["fixture"])
            outcomes = []
            for _text, expr, expected in checks:
                _cmd, out = run_bench.run_check(fixture, expr)
                outcomes.append(out == expected)
            if case["expected"] == "MATCHES INTENT":
                self.assertTrue(all(outcomes), "%s: correct fixture failed a check" % cid)
            else:
                self.assertFalse(all(outcomes), "%s: drifted fixture passed every check" % cid)


class TestOrchestration(unittest.TestCase):
    def _case(self, cid):
        return CASES[cid]

    def test_faithful_reaches_expected_verdict(self):
        for cid in ("sortposts", "sortposts_ok", "median", "validate_ok"):
            got, meta = run_bench.orchestrate(run_bench.profile_faithful, self._case(cid))
            self.assertEqual(got, self._case(cid)["expected"], cid)
            self.assertEqual(meta["retries"], 0)

    def test_verbose_wrapper_still_parses(self):
        got, meta = run_bench.orchestrate(run_bench.profile_verbose, self._case("search"))
        self.assertEqual(got, "DRIFTED")

    def test_sloppy_recovers_via_single_retry(self):
        got, meta = run_bench.orchestrate(run_bench.profile_sloppy, self._case("dedupe"))
        self.assertEqual(got, "DRIFTED")
        self.assertEqual(meta["retries"], 1)

    def test_lazy_yields_inconclusive_never_matches(self):
        for cid in ("median", "median_ok"):
            got, _ = run_bench.orchestrate(run_bench.profile_lazy, self._case(cid))
            self.assertEqual(got, "INCONCLUSIVE", cid)

    def test_retry_is_bounded(self):
        calls = []
        def always_garbage(case, attempt, defects=None):
            calls.append(attempt)
            return "no ledger here"
        got, meta = run_bench.orchestrate(always_garbage, self._case("median"))
        self.assertEqual(got, "INCONCLUSIVE")
        self.assertEqual(len(calls), run_bench.MAX_RETRIES + 1, "must never loop beyond the single bounded retry")


class TestValidatorBypassRegression(unittest.TestCase):
    def test_field_order_cannot_launder_empty_evidence(self):
        import validate_ledger as vl
        text = (
            "INTENT-VERIFY LEDGER v1\n\n"
            "CRITERION 1: sorts newest first\n"
            "EVIDENCE-CMD: python3 -c 'x'\n"
            "EVIDENCE-OUT:\n"
            "VERDICT: PASS\n\n"
            "FINAL: MATCHES INTENT\n"
        )
        _, defects = vl.validate(text)
        self.assertTrue(any("EVIDENCE-OUT" in d for d in defects))

    def test_retry_receives_named_defects(self):
        seen = {}
        case = CASES["median"]
        def produce(case, attempt, defects):
            if attempt == 0:
                return "INTENT-VERIFY LEDGER v1\n\nCRITERION 1: x\nVERDICT: PASS\n\nFINAL: MATCHES INTENT\n"
            seen["defects"] = defects
            return run_bench.profile_faithful(case, attempt)
        got, meta = run_bench.orchestrate(produce, case)
        self.assertEqual(got, case["expected"])
        self.assertTrue(seen["defects"], "retry must be told why the first ledger was rejected")


class TestRealVerifierRunner(unittest.TestCase):
    """--mode cli. Before v0.2.1 a timeout aborted the whole run with a
    traceback, the exit status was ignored, and the retry was a fresh process
    that never saw the reply it was asked to correct."""

    def test_unavailable_verifier_is_inconclusive_and_not_retried(self):
        calls = []
        def produce(case, attempt, defects):
            calls.append(attempt)
            raise run_bench.VerifierUnavailable("timed out after 5s")
        got, meta = run_bench.orchestrate(produce, CASES["median"])
        self.assertEqual(got, "INCONCLUSIVE")
        self.assertEqual(calls, [0], "nothing came back, so there is no ledger to correct")
        self.assertIn("timed out", meta["defects"][0])

    def test_timeout_launch_failure_and_silent_crash_are_unavailable(self):
        outcomes = [subprocess.TimeoutExpired("claude", 5), FileNotFoundError("claude"),
                    subprocess.CompletedProcess([], 1, stdout="", stderr="API error")]
        for outcome in outcomes:
            effect = outcome if isinstance(outcome, Exception) else None
            with mock.patch.object(run_bench.subprocess, "run", side_effect=effect, return_value=outcome):
                with self.assertRaises(run_bench.VerifierUnavailable, msg=repr(outcome)):
                    run_bench.run_cli_verifier(CASES["median"], "some-model", 5)

    def test_a_reply_is_judged_even_if_the_exit_status_is_nonzero(self):
        done = subprocess.CompletedProcess([], 1, stdout="partial reply", stderr="")
        with mock.patch.object(run_bench.subprocess, "run", return_value=done):
            self.assertEqual(run_bench.run_cli_verifier(CASES["median"], "some-model", 5), "partial reply")

    def test_retry_prompt_carries_the_defects_and_the_rejected_reply(self):
        done = subprocess.CompletedProcess([], 0, stdout="ok", stderr="")
        with mock.patch.object(run_bench.subprocess, "run", return_value=done) as run:
            run_bench.run_cli_verifier(CASES["median"], "some-model", 5,
                                       defects=["missing FINAL line"], previous="my earlier ledger")
        prompt = run.call_args.kwargs["input"]
        self.assertIn("missing FINAL line", prompt)
        self.assertIn("my earlier ledger", prompt)

    @mock.patch("builtins.print")
    @mock.patch.object(run_bench.shutil, "which", return_value="claude")
    def test_cli_run_feeds_each_rejected_reply_into_its_retry(self, _which, _print):
        seen = []
        def fake(case, model, timeout, defects=None, previous=None):
            seen.append((case["id"], bool(defects), previous))
            return "not a ledger" if previous is None else run_bench.faithful_ledger(case)
        with mock.patch.object(run_bench, "run_cli_verifier", side_effect=fake):
            code = run_bench.main(["--mode", "cli", "--verifier", "some-model", "--no-write"])
        self.assertEqual(code, 0, "faithful retries reach every expected verdict")
        first = [s for s in seen if s[0] == "median"]
        self.assertEqual(first, [("median", False, None), ("median", True, "not a ledger")])


if __name__ == "__main__":
    unittest.main()
