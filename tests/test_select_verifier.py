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


class TestScoresFromDifferentIndexVersions(unittest.TestCase):
    """Review of 0.5.0. The rows added for the current models carry scores from
    a newer version of the index, and their note says to compare tiers with
    the older rows, not scores. The ranking compared the numbers anyway."""

    MIXED = "scores from different versions of the index are not compared"
    UNMEASURED = "the gap between them is not measured"

    def test_the_reviews_case(self):
        """claude-opus-5 was picked over claude-opus-5-5 for a complex change
        because 60.7 on the old index is more than 58 on the new one."""
        r = pick("sonnet", ["claude-opus-5", "opus"], complexity="complex")
        self.assertEqual(r["verifier"], "claude-opus-5-5")
        self.assertTrue(any(self.MIXED in w and "claude-opus-5-5 (v4.3.2)" in w and "claude-opus-5 " in w
                            for w in r["warnings"]), r["warnings"])
        scales = {e["id"]: e.get("scale") for e in r["ranked"]}
        self.assertEqual(scales, {"claude-opus-5": "2026-08-02", "claude-opus-5-5": "v4.3.2"})

    def test_the_order_of_the_candidates_does_not_matter(self):
        for candidates in (["claude-opus-5", "opus"], ["opus", "claude-opus-5"]):
            self.assertEqual(pick("sonnet", candidates, complexity="complex")["verifier"], "claude-opus-5-5")
            self.assertEqual(pick("sonnet", candidates, prefer="capable")["verifier"], "claude-opus-5-5")

    def test_a_model_placed_by_assumption_is_on_the_scale_of_the_model_it_is_placed_above(self):
        r = pick("opus", ["claude-sonnet-5", "claude-fable-5", "fable"], complexity="complex")
        self.assertEqual(r["verifier"], "claude-fable-5-1")
        self.assertTrue(any(self.MIXED in w for w in r["warnings"]), r["warnings"])

    def test_within_one_version_the_scores_still_decide_and_nothing_is_said(self):
        r = pick("claude-opus-5", ["claude-sonnet-5", "claude-fable-5"], complexity="complex")
        self.assertEqual(r["verifier"], "claude-fable-5")
        self.assertFalse(any(self.MIXED in w or self.UNMEASURED in w for w in r["warnings"]), r["warnings"])
        r = pick("claude-opus-5-5", ["sonnet", "opus", "fable", "haiku"], complexity="complex")
        self.assertFalse(any(self.MIXED in w or self.UNMEASURED in w for w in r["warnings"]), r["warnings"])

    def test_a_higher_tier_on_the_old_index_stays_ahead_of_a_lower_tier_on_the_new_one(self):
        index = dict(INDEX)
        index["new-mid"] = {"id": "new-mid", "family": "claude", "aa_intelligence": 49, "scale": "v4.3.2"}
        r = sv.select("sonnet", ["new-mid", "claude-opus-5"], "standard", REG, index, prefer="capable")
        self.assertEqual((r["verifier"], r["tier"]), ("claude-opus-5", "T1"))
        self.assertFalse(any(self.MIXED in w for w in r["warnings"]), "tiers were compared, which the registry allows")

    def test_the_gap_to_the_implementer_is_not_subtracted_across_versions(self):
        """58 on the new index minus a score on the old one is not a gap."""
        r = pick("opus", ["sonnet", "gemini-3-flash"], complexity="simple")
        self.assertEqual((r["verifier"], r["tier"]), ("gemini-3-flash", "T3"))
        self.assertTrue(any(self.UNMEASURED in w and "v4.3.2" in w and "2026-08-02" in w for w in r["warnings"]), r["warnings"])
        self.assertTrue(any(w.startswith("weak-verifier: verifier is in T3, the implementer in T1") for w in r["warnings"]))
        self.assertFalse(any("points below" in w for w in r["warnings"]), r["warnings"])
        near = pick("opus", ["sonnet", "gpt-5.4"])
        self.assertEqual(near["verifier"], "gpt-5.4")
        self.assertTrue(any(self.UNMEASURED in w for w in near["warnings"]))
        self.assertFalse(any(w.startswith("weak-verifier") for w in near["warnings"]), near["warnings"])

    def test_the_gap_within_one_version_is_measured_as_before(self):
        r = pick("claude-opus-5", ["gemini-3-flash"], complexity="simple")
        self.assertTrue(any("points below the implementer" in w for w in r["warnings"]), r["warnings"])

    def test_a_timed_pick_is_not_a_comparison_of_scores(self):
        r = pick("claude-opus-5", ["sonnet", "claude-fable-5"])
        self.assertEqual(r["verifier"], "claude-sonnet-5-5")
        self.assertIn("fastest eligible candidate", r["reason"])
        self.assertFalse(any(self.MIXED in w for w in r["warnings"]), r["warnings"])

    def test_what_was_measured_still_outranks_what_was_assumed(self):
        """Found by attacking the fix. Putting the tier first let a candidate known
        only by --assume-tier T1 outrank a measured T2 model, which it never did."""
        r = pick("gemini-3-pro", ["gemini-3.1-pro", "mystery-x"], complexity="simple", assume="T1")
        self.assertEqual(r["verifier"], "gemini-3.1-pro")
        r = pick("gemini-3-pro", ["mystery-x", "gemini-3.1-pro"], complexity="simple", assume="T1", prefer="capable")
        self.assertEqual(r["verifier"], "gemini-3.1-pro")

    def test_a_verifier_two_tiers_down_is_weak_whether_or_not_it_has_a_score(self):
        """Found by attacking the fix: the warning needed two scores, so Opus 5.5
        with Haiku 4.5, T1 to T3, got none."""
        for implementer, candidate in (("opus", "haiku"), ("fable", "gemini-3-flash"), ("fable", "haiku")):
            r = pick(implementer, [candidate], complexity="simple")
            self.assertTrue(any(w.startswith("weak-verifier: verifier is in T3, the implementer in T1") for w in r["warnings"]),
                            (implementer, candidate, r["warnings"]))
        r = pick("fable", ["sonnet"])
        self.assertFalse(any(w.startswith("weak-verifier") for w in r["warnings"]), r["warnings"])

    def test_a_scale_the_registry_does_not_list_is_not_compared_and_says_so(self):
        index = dict(INDEX)
        index["a"] = {"id": "a", "family": "claude", "aa_intelligence": 60, "scale": "zzz"}
        index["b"] = {"id": "b", "family": "claude", "aa_intelligence": 70, "scale": "yyy"}
        for candidates in (["a", "b"], ["b", "a"]):
            r = sv.select("claude-opus-5", candidates, "complex", REG, index)
            self.assertEqual(r["verifier"], candidates[0], "neither score is used, so neither decides")
            self.assertEqual(len([w for w in r["warnings"] if "a scale the registry does not list" in w]), 2, r["warnings"])
            self.assertFalse(any(self.MIXED in w for w in r["warnings"]), r["warnings"])
        r = sv.select("claude-opus-5", ["a", "claude-fable-5"], "complex", REG, index)
        self.assertEqual(r["verifier"], "claude-fable-5", "a score that can be placed comes first")

    def test_a_place_that_was_not_given_is_not_claimed(self):
        index = dict(INDEX)
        index["u"] = {"id": "u", "family": "claude", "aa_intelligence": None, "tier": "T1"}
        index["x"] = {"id": "x", "family": "claude", "aa_intelligence": None, "tier": "T1", "ranks_above": "u"}
        r = sv.select("claude-opus-5-5", ["x"], "complex", REG, index)
        self.assertEqual(r["verifier"], "x")
        self.assertFalse(any("by the registry's assumption" in w for w in r["warnings"]), r["warnings"])

    def test_a_tie_on_time_that_the_scale_decided_is_said(self):
        index = dict(INDEX)
        index["old-quick"] = {"id": "old-quick", "family": "claude", "aa_intelligence": 61, "verify_seconds": 9.0}
        index["new-quick"] = {"id": "new-quick", "family": "claude", "aa_intelligence": 52, "scale": "v4.3.2",
                              "verify_seconds": 9.0}
        for candidates in (["old-quick", "new-quick"], ["new-quick", "old-quick"]):
            r = sv.select("claude-opus-5-5", candidates, "standard", REG, index)
            self.assertEqual(r["verifier"], "new-quick")
            self.assertTrue(any(self.MIXED in w for w in r["warnings"]), r["warnings"])

    def test_every_scale_a_row_names_is_one_the_registry_lists(self):
        self.assertEqual(REG["scales"], ["v4.3.2", "2026-08-02"])
        for m in REG["models"]:
            self.assertIn(m.get("scale", REG["scales"][-1]), REG["scales"], m["id"])
        noted = [m["id"] for m in REG["models"] if "v4.3.2" in (m.get("note") or "") and m.get("aa_intelligence") is not None]
        self.assertEqual(sorted(noted), sorted(m["id"] for m in REG["models"] if m.get("scale") == "v4.3.2"))


if __name__ == "__main__":
    unittest.main()
