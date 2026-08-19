import json
import os
import sys
import unittest

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE, "tools"))
import select_verifier as sv

REG, INDEX = sv.load_registry(os.path.join(BASE, "models", "registry.json"))


def pick(implementer, candidates, complexity="standard", assume=None):
    return sv.select(implementer, candidates, complexity, REG, INDEX, assume)


class TestSelectVerifier(unittest.TestCase):
    def test_prefers_different_family_even_if_slightly_weaker(self):
        r = pick("claude-opus-4-8", ["claude-sonnet-5", "gpt-5.4"])
        self.assertEqual(r["verifier"], "gpt-5.4")
        self.assertEqual(r["mode"], "FULL")

    def test_same_model_excluded(self):
        r = pick("claude-opus-4-8", ["opus 4.8", "gpt-5.4"])
        self.assertEqual(r["verifier"], "gpt-5.4")
        excluded = [e for e in r["ranked"] if e.get("excluded")]
        self.assertTrue(any("same model" in e["excluded"] for e in excluded))

    def test_floor_excludes_t3_for_standard_changes(self):
        r = pick("claude-opus-5", ["gemini-3-flash", "gpt-5.4"])
        self.assertEqual(r["verifier"], "gpt-5.4")

    def test_t3_allowed_for_simple_changes_in_structured_mode(self):
        r = pick("claude-opus-5", ["gemini-3-flash"], complexity="simple")
        self.assertEqual(r["verifier"], "gemini-3-flash")
        self.assertEqual(r["mode"], "STRUCTURED")

    def test_t4_never_eligible(self):
        r = pick("claude-opus-5", ["gpt-4o-mini", "llama-4-maverick"], complexity="simple")
        self.assertIsNone(r["verifier"])
        self.assertIn("same-model", r["reason"])

    def test_gap_warning(self):
        r = pick("claude-opus-5", ["gemini-3-flash"], complexity="simple")
        self.assertTrue(any("weak-verifier" in w for w in r["warnings"]))

    def test_unknown_candidate_excluded_without_assume(self):
        r = pick("claude-opus-5", ["totally-new-model-9000", "gpt-5.4"])
        self.assertEqual(r["verifier"], "gpt-5.4")
        self.assertTrue(any("not in registry" in w for w in r["warnings"]))

    def test_unknown_candidate_with_assume_tier(self):
        r = pick("claude-opus-5", ["totally-new-model-9000"], assume="T2")
        self.assertEqual(r["verifier"], "totally-new-model-9000")

    def test_alias_and_dot_normalization(self):
        self.assertIsNotNone(sv.resolve("Opus 4.8", INDEX))
        self.assertIsNotNone(sv.resolve("claude-opus-4-8", INDEX))
        self.assertIsNotNone(sv.resolve("gpt-5-4-mini", INDEX))

    def test_haiku_explicit_tier_without_score(self):
        m = sv.resolve("haiku 4.5", INDEX)
        self.assertEqual(sv.tier_of(m, REG["tier_bounds"]), "T3")

    def test_same_family_fallback_warns(self):
        r = pick("claude-opus-4-8", ["claude-sonnet-5"])
        self.assertEqual(r["verifier"], "claude-sonnet-5")
        self.assertTrue(any("family" in w for w in r["warnings"]))


if __name__ == "__main__":
    unittest.main()
