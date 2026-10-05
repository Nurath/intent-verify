import json
import os
import sys
import unittest

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE, "benchmark"))
sys.path.insert(0, os.path.join(BASE, "tools"))

import m4_json_ledger as m4  # noqa: E402
import validate_ledger  # noqa: E402

with open(os.path.join(BASE, "benchmark", "cases.json"), encoding="utf-8") as _f:
    CASES = {c["id"]: c for c in json.load(_f)["cases"]}

MANIFEST = {"manifest": 1, "ambiguities": [], "criteria": [
    {"id": 1, "text": "returns the median", "quote": "median"}]}


class TestM4Prompts(unittest.TestCase):
    """M4 varies only the ledger's encoding; everything else in the prompt is the same."""

    def test_the_json_arm_is_the_shipped_prompt_with_a_nonce(self):
        prompt = m4.build_prompt(CASES["median"], MANIFEST, "STRUCTURED", "json", "a" * 32)
        self.assertIn("MODE: STRUCTURED\nRUN NONCE: %s\n" % ("a" * 32), prompt)
        self.assertIn(m4.JSON_SECTION, prompt)
        self.assertNotIn(validate_ledger.HEADER, prompt)

    def test_the_text_arm_swaps_in_the_text_ledger_and_has_no_nonce(self):
        prompt = m4.build_prompt(CASES["median"], MANIFEST, "STRUCTURED", "text", "a" * 32)
        self.assertIn(validate_ledger.HEADER, prompt)
        self.assertNotIn(m4.JSON_SECTION, prompt)
        self.assertNotIn("RUN NONCE", prompt, "a text-ledger verifier is never told to copy a nonce")
        self.assertIn("- MODE — `FULL` (default) or `STRUCTURED` (simplified protocol, defined below).\n- MANIFEST", prompt)
        json_arm = m4.build_prompt(CASES["median"], MANIFEST, "STRUCTURED", "json", "a" * 32)
        procedure = json_arm[json_arm.index("Hard rules"):json_arm.index(m4.JSON_SECTION)]
        self.assertIn(procedure, prompt, "the rules and procedure are the same in both arms")


if __name__ == "__main__":
    unittest.main()
