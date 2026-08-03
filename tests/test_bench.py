import json
import os
import subprocess
import sys
import unittest

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE, "benchmark"))
sys.path.insert(0, os.path.join(BASE, "tools"))

import run_bench  # noqa: E402
from oracle import CHECKS  # noqa: E402

CASES = {c["id"]: c for c in json.load(open(os.path.join(BASE, "benchmark", "cases.json"), encoding="utf-8"))["cases"]}


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


if __name__ == "__main__":
    unittest.main()
