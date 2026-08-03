import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))
import validate_ledger as vl


def L(*lines):
    return "\n".join(lines) + "\n"


VALID = L(
    "INTENT-VERIFY LEDGER v1", "mode: FULL", "",
    "CRITERION 1: newest post first", "VERDICT: FAIL",
    "EVIDENCE-CMD: python3 -c '...'", "EVIDENCE-OUT: oldest came first", "",
    "CRITERION 2: all posts kept", "VERDICT: PASS",
    "EVIDENCE-CMD: python3 -c '...'", "EVIDENCE-OUT: both present", "",
    "FINAL: DRIFTED — criteria 1 failed",
)


class TestValidateLedger(unittest.TestCase):
    def test_valid_ledger_passes(self):
        ledger, defects = vl.validate(VALID)
        self.assertEqual(defects, [])
        self.assertEqual(vl.verdict_of(ledger), "DRIFTED")

    def test_extracts_from_chatter_and_fences(self):
        wrapped = "Sure! Here you go:\n\n```\n" + VALID + "```\nHope that helps!"
        ledger, defects = vl.validate(wrapped)
        self.assertEqual(defects, [])
        self.assertEqual(len(ledger["criteria"]), 2)

    def test_missing_header_is_defect(self):
        _, defects = vl.validate("just some prose, no ledger at all")
        self.assertTrue(any("header" in d for d in defects))

    def test_pass_without_evidence_rejected(self):
        text = L("INTENT-VERIFY LEDGER v1", "", "CRITERION 1: works", "VERDICT: PASS", "", "FINAL: MATCHES INTENT")
        _, defects = vl.validate(text)
        self.assertTrue(any("without EVIDENCE-CMD" in d for d in defects))
        self.assertTrue(any("without EVIDENCE-OUT" in d for d in defects))

    def test_not_exercised_needs_reason(self):
        text = L("INTENT-VERIFY LEDGER v1", "", "CRITERION 1: x", "VERDICT: NOT-EXERCISED", "", "FINAL: INCONCLUSIVE — 1 not exercised")
        _, defects = vl.validate(text)
        self.assertTrue(any("without REASON" in d for d in defects))

    def test_unexercised_cannot_become_matches(self):
        text = L(
            "INTENT-VERIFY LEDGER v1", "",
            "CRITERION 1: x", "VERDICT: PASS", "EVIDENCE-CMD: c", "EVIDENCE-OUT: o", "",
            "CRITERION 2: y", "VERDICT: NOT-EXERCISED", "REASON: no runtime here", "",
            "FINAL: MATCHES INTENT",
        )
        _, defects = vl.validate(text)
        self.assertTrue(any("INCONCLUSIVE" in d for d in defects))

    def test_fail_forces_drifted_listing_all(self):
        text = VALID.replace("FINAL: DRIFTED — criteria 1 failed", "FINAL: MATCHES INTENT")
        _, defects = vl.validate(text)
        self.assertTrue(any("must be DRIFTED" in d for d in defects))
        partial = L(
            "INTENT-VERIFY LEDGER v1", "",
            "CRITERION 1: a", "VERDICT: FAIL", "EVIDENCE-CMD: c", "EVIDENCE-OUT: o", "",
            "CRITERION 2: b", "VERDICT: FAIL", "EVIDENCE-CMD: c", "EVIDENCE-OUT: o", "",
            "FINAL: DRIFTED — criteria 1 failed",
        )
        _, defects = vl.validate(partial)
        self.assertTrue(any("missing [2]" in d for d in defects))

    def test_structured_mode_caps_criteria(self):
        blocks = []
        for i in range(1, 7):
            blocks += ["CRITERION %d: c%d" % (i, i), "VERDICT: PASS", "EVIDENCE-CMD: c", "EVIDENCE-OUT: o", ""]
        text = L("INTENT-VERIFY LEDGER v1", "mode: STRUCTURED", "", *blocks, "FINAL: MATCHES INTENT")
        _, defects = vl.validate(text)
        self.assertTrue(any("at most 5" in d for d in defects))

    def test_all_pass_must_be_matches(self):
        text = L(
            "INTENT-VERIFY LEDGER v1", "",
            "CRITERION 1: a", "VERDICT: PASS", "EVIDENCE-CMD: c", "EVIDENCE-OUT: o", "",
            "FINAL: DRIFTED — criteria 1 failed",
        )
        _, defects = vl.validate(text)
        self.assertTrue(any("expected MATCHES INTENT" in d for d in defects))

    def test_multiline_evidence_out(self):
        text = L(
            "INTENT-VERIFY LEDGER v1", "",
            "CRITERION 1: a", "VERDICT: PASS", "EVIDENCE-CMD: run it",
            "EVIDENCE-OUT: line one", "line two", "line three", "",
            "FINAL: MATCHES INTENT",
        )
        ledger, defects = vl.validate(text)
        self.assertEqual(defects, [])
        self.assertIn("line three", ledger["criteria"][0]["out"])


if __name__ == "__main__":
    unittest.main()
