import json
import os
import sys
import unittest

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE, "tools"))
import select_verifier as sv

REG, INDEX = sv.load_registry(os.path.join(BASE, "models", "registry.json"))


def pick(implementer, candidates, complexity="standard", assume=None, prefer=None):
    return sv.select(implementer, candidates, complexity, REG, INDEX, assume, prefer)


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


class TestCurrentModelsAndSpeed(unittest.TestCase):
    """0.5.0. In the plugin's first real run the session needed three calls to
    get a selection (the registry did not know the current model names), and
    the most capable candidate then verified for nine minutes."""

    def test_claude_codes_own_names_resolve_in_one_call(self):
        for name, model in (("sonnet", "claude-sonnet-5-5"), ("claude-sonnet-5-5", "claude-sonnet-5-5"),
                            ("opus", "claude-opus-5-5"), ("Opus 5.5", "claude-opus-5-5"), ("fable", "claude-fable-5-1"),
                            ("claude-fable-5-1", "claude-fable-5-1"), ("haiku", "claude-haiku-4-5"),
                            ("claude-haiku-4-5-20251001", "claude-haiku-4-5")):
            self.assertEqual((sv.resolve(name, INDEX) or {}).get("id"), model, name)
        r = pick("claude-opus-5-5", ["sonnet", "opus", "fable", "haiku"])
        self.assertEqual(r["warnings"], ["no different-family candidate was eligible; verifier shares the implementer's "
                                         "family (cross-model lever weakened)"])

    def test_the_fastest_timed_model_that_clears_the_floor_is_chosen(self):
        r = pick("claude-opus-5-5", ["sonnet", "opus", "fable", "haiku"])
        self.assertEqual((r["verifier"], r["mode"], r["tier"]), ("claude-sonnet-5-5", "FULL", "T1"))
        timed = sv.resolve("sonnet", INDEX)["verify_seconds"]
        self.assertIn("fastest eligible candidate the benchmark has timed (%.1f s" % timed, r["reason"])
        self.assertEqual(pick("claude-fable-5-1", ["sonnet", "opus"])["verifier"], "claude-sonnet-5-5")

    def test_cheaper_per_token_is_not_faster(self):
        """Haiku in STRUCTURED mode took 40 s a verification against Sonnet's 12, at the same cost."""
        r = pick("claude-opus-5-5", ["haiku", "sonnet"], complexity="simple")
        self.assertEqual((r["verifier"], r["mode"]), ("claude-sonnet-5-5", "FULL"))
        self.assertEqual(pick("claude-sonnet-5-5", ["haiku"], complexity="simple")["mode"], "STRUCTURED")

    def test_a_complex_change_goes_to_the_most_capable(self):
        self.assertEqual(pick("claude-fable-5-1", ["sonnet", "opus"], complexity="complex")["verifier"], "claude-opus-5-5")
        self.assertIn("highest-capability", pick("claude-fable-5-1", ["sonnet", "opus"], complexity="complex")["reason"])

    def test_the_preference_can_be_set_either_way(self):
        self.assertEqual(pick("claude-fable-5-1", ["sonnet", "opus"], prefer="capable")["verifier"], "claude-opus-5-5")
        self.assertEqual(pick("claude-fable-5-1", ["sonnet", "opus"], complexity="complex", prefer="fast")["verifier"],
                         "claude-sonnet-5-5")

    def test_a_different_family_still_comes_before_speed(self):
        self.assertEqual(pick("claude-opus-5-5", ["sonnet", "gpt-5.4"])["verifier"], "gpt-5.4")

    def test_untimed_candidates_are_ranked_by_capability(self):
        r = pick("claude-sonnet-5-5", ["fable", "opus"])
        self.assertEqual(r["verifier"], "claude-opus-5-5")
        self.assertIn("highest-capability", r["reason"])

    def test_the_command_line_takes_the_preference(self):
        import subprocess
        tool = os.path.join(BASE, "tools", "select_verifier.py")
        args = [sys.executable, tool, "--implementer", "claude-fable-5-1", "--candidates", "sonnet", "opus", "fable", "haiku"]
        fast = json.loads(subprocess.run(args, capture_output=True, text=True, timeout=30).stdout)
        capable = json.loads(subprocess.run(args + ["--prefer", "capable"], capture_output=True, text=True, timeout=30).stdout)
        self.assertEqual((fast["verifier"], capable["verifier"]), ("claude-sonnet-5-5", "claude-opus-5-5"))

    def test_a_model_the_index_does_not_list_is_not_called_the_most_capable(self):
        """A model known only by an assumed tier has no score to rank by, and no
        place is invented for it."""
        r = pick("claude-opus-5-5", ["sonnet", "claude-next-9"], assume="T1", prefer="capable")
        self.assertEqual(r["verifier"], "claude-sonnet-5-5")
        self.assertEqual([e["score"] for e in r["ranked"] if e["id"] == "claude-next-9"], [None])

    def test_a_complex_change_by_opus_goes_to_fable_and_says_on_what_ground(self):
        """Found by running the release on itself. The option the maintainer chose
        read "Sonnet instead of Fable when Opus wrote the change ... Complex
        changes still require the top tier". Fable 5.1 has no score, so a complex
        change written by Opus went to Sonnet all the same, and asking for the
        most capable model changed nothing in the commonest case. Its registry
        row now places it where its predecessor stood: above Sonnet, below Opus."""
        r = pick("claude-opus-5-5", ["sonnet", "opus", "fable", "haiku"], complexity="complex")
        self.assertEqual((r["verifier"], r["mode"], r["tier"]), ("claude-fable-5-1", "FULL", "T1"))
        self.assertIn("highest-capability", r["reason"])
        self.assertTrue(any("no published score" in w and "ranked above claude-sonnet-5-5 by the registry's assumption" in w
                            for w in r["warnings"]), r["warnings"])
        fable = [e for e in r["ranked"] if e["id"] == "claude-fable-5-1"][0]
        self.assertEqual((fable["score"], fable["ranks_above"]), (None, "claude-sonnet-5-5"), "no score is invented for it")
        self.assertEqual(pick("claude-opus-5-5", ["sonnet", "opus", "fable", "haiku"], prefer="capable")["verifier"],
                         "claude-fable-5-1")

    def test_the_assumed_place_is_below_a_higher_score_and_never_the_fast_pick(self):
        self.assertEqual(pick("claude-sonnet-5-5", ["fable", "opus"], complexity="complex")["verifier"], "claude-opus-5-5")
        for complexity in ("simple", "standard"):
            self.assertEqual(pick("claude-opus-5-5", ["sonnet", "opus", "fable", "haiku"], complexity=complexity)["verifier"],
                             "claude-sonnet-5-5", complexity)
        self.assertEqual(pick("claude-opus-5-5", ["sonnet", "opus", "fable", "haiku"], complexity="complex",
                              prefer="fast")["verifier"], "claude-sonnet-5-5")
        self.assertEqual(pick("gpt-5.6-sol", ["sonnet", "opus", "fable"], complexity="complex")["verifier"], "claude-opus-5-5")

    def test_a_place_above_a_model_the_registry_does_not_score_is_no_place(self):
        index = dict(INDEX)
        index["x-new"] = {"id": "x-new", "family": "claude", "aa_intelligence": None, "tier": "T1", "ranks_above": "nobody"}
        r = sv.select("claude-opus-5-5", ["sonnet", "x-new"], "complex", REG, index)
        self.assertEqual(r["verifier"], "claude-sonnet-5-5")

    def test_an_unlisted_candidate_is_not_taken_for_another_vendor(self):
        """Its family is unknown, and unknown was counted as different. With
        --assume-tier it was preferred over every listed model of the
        implementer's family, and the reason said a different family had been
        preferred. Found when a test of the ranking named a model nobody lists."""
        for prefer in ("fast", "capable"):
            r = pick("claude-opus-5-5", ["claude-next-9", "sonnet"], assume="T1", prefer=prefer)
            self.assertEqual(r["verifier"], "claude-sonnet-5-5", prefer)
        alone = pick("claude-opus-5-5", ["claude-next-9"], assume="T1")
        self.assertEqual(alone["verifier"], "claude-next-9")
        self.assertIn("(same/unknown family)", alone["reason"])
        self.assertEqual(pick("claude-opus-5-5", ["claude-next-9", "sonnet", "gpt-5.4"], assume="T1")["verifier"], "gpt-5.4")


if __name__ == "__main__":
    unittest.main()
