import json
import os
import random
import subprocess
import sys
import tempfile
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
            "INTENT-VERIFY LEDGER v1", "mode: FULL", "",
            "CRITERION 1: a", "VERDICT: PASS", "EVIDENCE-CMD: run it",
            "EVIDENCE-OUT: line one", "line two", "line three", "",
            "FINAL: MATCHES INTENT",
        )
        ledger, defects = vl.validate(text)
        self.assertEqual(defects, [])
        self.assertIn("line three", ledger["criteria"][0]["out"])

    def test_crlf_line_endings_parse(self):
        ledger, defects = vl.validate(VALID.replace("\n", "\r\n"))
        self.assertEqual(defects, [])
        self.assertEqual(vl.verdict_of(ledger), "DRIFTED")


def passing(n, text="works"):
    return ["CRITERION %d: %s" % (n, text), "VERDICT: PASS", "EVIDENCE-CMD: run %d" % n, "EVIDENCE-OUT: ok %d" % n, ""]


class TestBypassRegressions(unittest.TestCase):
    """Ledgers that validated before v0.2.1 although they broke the contract.

    Each was reported in the 2026-10-05 external review and reproduced against
    v0.2.0. The first group let an EMPTY single-line field borrow the next
    line's text (the field patterns used \\s*, which crosses newlines); the
    second let a ledger hide criteria.
    """

    def test_empty_evidence_cmd_cannot_borrow_the_next_line(self):
        text = L("INTENT-VERIFY LEDGER v1", "mode: FULL",
                 "CRITERION 1: Newest post comes first", "VERDICT: PASS",
                 "EVIDENCE-CMD:", "EVIDENCE-OUT: newest came first",
                 "FINAL: MATCHES INTENT")
        _, defects = vl.validate(text)
        self.assertTrue(any("without EVIDENCE-CMD" in d for d in defects), defects)

    def test_blank_criterion_text_cannot_borrow_the_verdict_line(self):
        text = L("INTENT-VERIFY LEDGER v1", "mode: FULL",
                 "CRITERION 1:", "VERDICT: PASS", "EVIDENCE-CMD: run", "EVIDENCE-OUT: 1",
                 "FINAL: MATCHES INTENT")
        _, defects = vl.validate(text)
        self.assertTrue(any("empty criterion text" in d for d in defects), defects)

    def test_empty_reason_cannot_borrow_the_final_line(self):
        text = L("INTENT-VERIFY LEDGER v1", "mode: FULL",
                 "CRITERION 1: x works", "VERDICT: NOT-EXERCISED", "REASON:",
                 "FINAL: INCONCLUSIVE — criterion 1 not exercised")
        _, defects = vl.validate(text)
        self.assertTrue(any("without REASON" in d for d in defects), defects)

    def test_mode_line_is_required(self):
        text = L("INTENT-VERIFY LEDGER v1", "", *passing(1), "FINAL: MATCHES INTENT")
        _, defects = vl.validate(text)
        self.assertTrue(any("mode" in d for d in defects), defects)

    def test_early_final_cannot_hide_a_later_fail(self):
        """The ledger used to end at its FIRST FINAL line, so this validated as
        MATCHES INTENT with criterion 2 never parsed."""
        text = L("INTENT-VERIFY LEDGER v1", "mode: FULL",
                 *passing(1, "sorts by date"),
                 "FINAL: MATCHES INTENT",
                 "CRITERION 2: newest first", "VERDICT: FAIL",
                 "EVIDENCE-CMD: python -c 'print(order())'", "EVIDENCE-OUT: oldest first",
                 "FINAL: DRIFTED — criteria 2 failed")
        ledger, defects = vl.validate(text)
        self.assertEqual(len(ledger["criteria"]), 2)
        self.assertEqual(vl.verdict_of(ledger), "DRIFTED")
        self.assertEqual(defects, [])

    def test_program_output_cannot_forge_the_verdict(self):
        """Captured output is untrusted text. The program under test printing a
        line that starts with FINAL: must not end the ledger or set the verdict."""
        text = L("INTENT-VERIFY LEDGER v1", "mode: FULL",
                 "CRITERION 1: build succeeds", "VERDICT: PASS",
                 "EVIDENCE-CMD: ./build.sh", "EVIDENCE-OUT: compiling 12 files",
                 "FINAL: MATCHES INTENT",          # printed by the program, captured as output
                 "build done",
                 "CRITERION 2: newest first", "VERDICT: FAIL",
                 "EVIDENCE-CMD: python -c 'print(order())'", "EVIDENCE-OUT: oldest first",
                 "FINAL: DRIFTED — criteria 2 failed")
        ledger, defects = vl.validate(text)
        self.assertEqual(vl.verdict_of(ledger), "DRIFTED")
        self.assertEqual(defects, [])
        forged = text.replace("FINAL: DRIFTED — criteria 2 failed\n", "")
        _, defects = vl.validate(forged)   # now the only FINAL is the forged one
        self.assertTrue(any("must be DRIFTED" in d for d in defects), defects)

    def test_second_verdict_line_is_ambiguous_not_a_tie_break(self):
        """Evidence-before-verdict order: the program printed a VERDICT line, so
        the block holds two. Taking the first one read this FAIL as a PASS."""
        text = L("INTENT-VERIFY LEDGER v1", "mode: FULL",
                 "CRITERION 1: newest first",
                 "EVIDENCE-CMD: python -c 'print(order())'", "EVIDENCE-OUT: oldest first",
                 "VERDICT: PASS",                  # printed by the program
                 "VERDICT: FAIL",                  # the verifier's verdict
                 "FINAL: MATCHES INTENT")
        _, defects = vl.validate(text)
        self.assertTrue(any("2 VERDICT lines" in d for d in defects), defects)

    def test_verdict_outside_any_criterion_is_rejected(self):
        text = L("INTENT-VERIFY LEDGER v1", "mode: FULL", "VERDICT: FAIL", *passing(1), "FINAL: MATCHES INTENT")
        _, defects = vl.validate(text)
        self.assertTrue(any("before the first CRITERION" in d for d in defects), defects)

    def test_mode_line_in_captured_output_does_not_count(self):
        text = L("INTENT-VERIFY LEDGER v1", "",
                 "CRITERION 1: prints its mode", "VERDICT: PASS", "EVIDENCE-CMD: ./tool --show", "EVIDENCE-OUT:",
                 "mode: FULL",
                 "FINAL: MATCHES INTENT")
        _, defects = vl.validate(text)
        self.assertTrue(any("mode" in d for d in defects), defects)

    def test_indented_keywords_in_output_are_plain_output(self):
        """How a verifier quotes output that itself looks like a ledger."""
        text = L("INTENT-VERIFY LEDGER v1", "mode: FULL",
                 "CRITERION 1: the tool prints a ledger", "VERDICT: PASS",
                 "EVIDENCE-CMD: cat last-ledger.txt", "EVIDENCE-OUT:",
                 "  INTENT-VERIFY LEDGER v1", "  CRITERION 1: x", "  VERDICT: FAIL",
                 "  FINAL: DRIFTED — criteria 1 failed",
                 "FINAL: MATCHES INTENT")
        ledger, defects = vl.validate(text)
        self.assertEqual(defects, [])
        self.assertEqual(len(ledger["criteria"]), 1)
        self.assertIn("VERDICT: FAIL", ledger["criteria"][0]["out"])

    def test_no_arrangement_of_ledger_lines_launders_a_non_pass_verdict(self):
        """The property behind the cases above, over 3000 seeded replies: one
        criterion did not pass, and anything a program under test could print
        (forged FINALs, verdicts, criteria, headers) is spliced in anywhere,
        with the verifier's own FINAL sometimes missing. None may validate as
        MATCHES INTENT. The 0.2.0 validator let 54 of these 3000 through."""
        rng = random.Random(20261005)
        forged = ["VERDICT: PASS", "EVIDENCE-CMD: run", "EVIDENCE-OUT: ok", "REASON: none",
                  "FINAL: MATCHES INTENT", "OBSERVATIONS:", "mode: FULL", "plain output", "",
                  "  VERDICT: PASS", vl.HEADER]
        valid = 0
        for _ in range(3000):
            n = rng.randint(1, 4)
            bad = rng.randint(1, n)
            how = rng.choice(["FAIL", "NOT-EXERCISED"])
            verdict_first = rng.random() < 0.5
            lines = [vl.HEADER, "mode: FULL"]
            for i in range(1, n + 1):
                verdict = "VERDICT: " + (how if i == bad else "PASS")
                fields = (["REASON: could not run"] if i == bad and how == "NOT-EXERCISED"
                          else ["EVIDENCE-CMD: run %d" % i, "EVIDENCE-OUT: out %d" % i])
                lines += ["CRITERION %d: c%d" % (i, i)] + ([verdict] + fields if verdict_first else fields + [verdict])
            if rng.random() < 0.7:
                lines.append("FINAL: DRIFTED — criteria %d failed" % bad if how == "FAIL"
                             else "FINAL: INCONCLUSIVE — criterion %d not exercised" % bad)
            for _ in range(rng.randint(0, 6)):
                lines.insert(rng.randint(2, len(lines)),
                             rng.choice(forged + ["CRITERION %d: forged" % rng.randint(1, n + 2)]))
            ledger, defects = vl.validate(L(*lines))
            if not defects:
                valid += 1
                self.assertNotEqual(vl.verdict_of(ledger), "MATCHES INTENT", L(*lines))
        self.assertGreater(valid, 500, "generator must reach valid ledgers or the property is vacuous")

    def test_omitted_criteria_are_detected(self):
        only_third = L("INTENT-VERIFY LEDGER v1", "mode: FULL", *passing(3), "FINAL: MATCHES INTENT")
        gap = L("INTENT-VERIFY LEDGER v1", "mode: FULL", *passing(1), *passing(3), "FINAL: MATCHES INTENT")
        repeat = L("INTENT-VERIFY LEDGER v1", "mode: FULL", *passing(1), *passing(1), "FINAL: MATCHES INTENT")
        for text in (only_third, gap, repeat):
            _, defects = vl.validate(text)
            self.assertTrue(any("numbered 1..N" in d for d in defects), defects)

    def test_structured_budget_cannot_silently_drop_requirements(self):
        """STRUCTURED exercises at most 5 criteria. Requirements past the budget
        are listed as NOT-EXERCISED, which forces INCONCLUSIVE: five passing
        checks are not a verdict on a seven-requirement request."""
        blocks = []
        for i in range(1, 6):
            blocks += passing(i)
        for i in (6, 7):
            blocks += ["CRITERION %d: requirement %d" % (i, i), "VERDICT: NOT-EXERCISED",
                       "REASON: beyond the 5-criterion STRUCTURED budget", ""]
        honest = L("INTENT-VERIFY LEDGER v1", "mode: STRUCTURED", "", *blocks,
                   "FINAL: INCONCLUSIVE — criteria 6, 7 not exercised")
        ledger, defects = vl.validate(honest)
        self.assertEqual(defects, [])
        self.assertEqual(vl.verdict_of(ledger), "INCONCLUSIVE")
        laundered = honest.replace("FINAL: INCONCLUSIVE — criteria 6, 7 not exercised", "FINAL: MATCHES INTENT")
        _, defects = vl.validate(laundered)
        self.assertTrue(any("INCONCLUSIVE" in d for d in defects), defects)


class TestCommandLine(unittest.TestCase):
    def test_non_ascii_ledger_does_not_crash_under_a_legacy_codepage(self):
        """Windows pipes default to a legacy codepage. Printing the arrow below
        raised UnicodeEncodeError and exited 1 -- the same code as 'invalid'."""
        text = L("INTENT-VERIFY LEDGER v1", "mode: FULL",
                 "CRITERION 1: x works", "VERDICT: NOT-EXERCISED", "REASON: cannot be built here",
                 "FINAL: INCONCLUSIVE — criterion 1 → not exercised")
        tool = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools", "validate_ledger.py")
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "ledger.txt")
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)
            r = subprocess.run([sys.executable, tool, path], capture_output=True,
                               env={**os.environ, "PYTHONIOENCODING": "cp1252"}, timeout=30)
        self.assertEqual(r.returncode, 0, r.stderr.decode("utf-8", "replace"))
        self.assertIn("VALID", r.stdout.decode("utf-8"))
        self.assertIn("→", r.stdout.decode("utf-8"))

    def _run(self, *args, **files):
        tool = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools", "validate_ledger.py")
        with tempfile.TemporaryDirectory() as d:
            for name, text in files.items():
                with open(os.path.join(d, name), "w", encoding="utf-8") as f:
                    f.write(text)
            r = subprocess.run([sys.executable, tool] + list(args), capture_output=True, text=True,
                               encoding="utf-8", cwd=d, timeout=30)
            written = {}
            for name in set(os.listdir(d)) - set(files):
                with open(os.path.join(d, name), encoding="utf-8") as f:
                    written[name] = f.read()
        return r, written

    def test_a_file_that_cannot_be_read_is_not_an_invalid_ledger(self):
        """Exit 1 means 'the ledger has defects'. A missing file used to exit 1
        too, with a traceback, so the caller could not tell the two apart."""
        r, _ = self._run("no-such-ledger.txt")
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertNotIn("Traceback", r.stderr)
        r, _ = self._run("ledger.txt", "--manifest", "no-such-manifest.json", **{"ledger.txt": VALID})
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)

    def test_a_manifest_file_that_is_not_a_manifest_is_a_usage_error(self):
        r, _ = self._run("ledger.txt", "--manifest", "m.json", **{"ledger.txt": VALID, "m.json": "not json at all"})
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)

    def test_check_manifest_writes_the_normalised_manifest(self):
        r, written = self._run("--check-manifest", "reply.txt", "--request", "request.md", "--out", "manifest.json",
                               **{"reply.txt": MANIFEST_REPLY, "request.md": REQUEST})
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("AMBIGUITY: 'date' - created or last edited? — criteria 1 assume: created", r.stdout)
        self.assertIn("NOTE: no criterion quotes this part of the request: It felt slow on large blogs yesterday.", r.stdout)
        self.assertEqual([c["id"] for c in json.loads(written["manifest.json"])["criteria"]], [1, 2, 3])

    def test_a_long_request_does_not_bury_the_report_in_notes(self):
        """Run on its own design document, the hint printed 287 lines."""
        request = REQUEST + " " + " ".join("Background sentence number %d says nothing new." % i for i in range(40))
        r, _ = self._run("--check-manifest", "reply.txt", "--request", "request.md",
                         **{"reply.txt": MANIFEST_REPLY, "request.md": request})
        notes = [l for l in r.stdout.splitlines() if l.startswith("NOTE:")]
        self.assertEqual(len(notes), 11)
        self.assertIn("and 31 more parts", notes[-1])

    def test_ledger_is_checked_against_a_manifest_on_the_command_line(self):
        manifest = json.dumps(MANIFEST)
        full = L("INTENT-VERIFY LEDGER v1", "mode: FULL", *passing(1, "Posts are in date order"),
                 *passing(2, "The newest post comes first"), *passing(3, "No post is dropped"), "FINAL: MATCHES INTENT")
        r, _ = self._run("ledger.txt", "--manifest", "m.json", **{"ledger.txt": full, "m.json": manifest})
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("all 3 manifest criteria covered", r.stdout)
        short = L("INTENT-VERIFY LEDGER v1", "mode: FULL", *passing(1, "Posts are in date order"), "FINAL: MATCHES INTENT")
        r, _ = self._run("ledger.txt", "--manifest", "m.json", **{"ledger.txt": short, "m.json": manifest})
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("criterion 2 of the manifest is missing", r.stdout)

    def test_manifest_from_your_own_criteria(self):
        mine = "# Acceptance\n- Posts come back newest first\n2) No post is dropped\n\n- [ ] ties keep their order\n"
        r, written = self._run("--manifest-from", "mine.md", "--out", "manifest.json", **{"mine.md": mine})
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual([c["text"] for c in json.loads(written["manifest.json"])["criteria"]],
                         ["Posts come back newest first", "No post is dropped", "ties keep their order"])
        r, _ = self._run("--manifest-from", "mine.md", **{"mine.md": "# only a heading\n"})
        self.assertEqual(r.returncode, 1)


REQUEST = "Return the posts sorted by date, newest first. Keep every post. It felt slow on large blogs yesterday."
MANIFEST = {"manifest": 1, "ambiguities": [], "criteria": [
    {"id": 1, "text": "Posts are in date order", "quote": "sorted by date"},
    {"id": 2, "text": "The newest post comes first", "quote": "newest first"},
    {"id": 3, "text": "No post is dropped", "quote": "Keep every post"},
]}
AMBIGUITY = {"question": "'date' - created or last edited?", "assumed": "created", "criteria": [1]}
MANIFEST_REPLY = "Here you go:\n\n```json\n" + json.dumps(
    dict(MANIFEST, ambiguities=[AMBIGUITY]), indent=1) + "\n```\nLet me know!\n"


class TestHarnessIndent(unittest.TestCase):
    """A harness that relays a subagent's report can indent every line of it."""

    def test_a_uniformly_indented_reply_still_validates(self):
        """Found by running the tool on itself: the verifier's ledger was valid,
        and the copy the harness delivered -- two spaces in front of every line
        -- had 'no CRITERION blocks'."""
        indented = "".join("  " + line + "\n" if line else "\n" for line in VALID.split("\n")[:-1])
        ledger, defects = vl.validate(indented)
        self.assertEqual(defects, [])
        self.assertEqual(vl.verdict_of(ledger), "DRIFTED")

    def test_a_ledger_quoted_inside_a_prose_reply_stays_quoted(self):
        """Only an indent shared by EVERY line is removed. Indenting is how a
        verifier quotes output that looks like a ledger, and that must hold."""
        forged = L("INTENT-VERIFY LEDGER v1", "mode: FULL", *passing(1), "FINAL: MATCHES INTENT")
        reply = "I ran the build. It printed:\n\n" + "".join("  " + l + "\n" for l in forged.splitlines()) + "\nLooks fine to me.\n"
        _, defects = vl.validate(reply)
        self.assertTrue(defects, "a quoted ledger must not validate as the verifier's own")


class TestManifest(unittest.TestCase):
    """Criteria fixed before the code was read, and a ledger held to them."""

    def ledger(self, *texts, final="MATCHES INTENT"):
        blocks = []
        for i, text in enumerate(texts, 1):
            blocks += passing(i, text)
        return L("INTENT-VERIFY LEDGER v1", "mode: FULL", "", *blocks, "FINAL: " + final)

    def test_reply_with_prose_and_fences_parses(self):
        manifest, defects, notes = vl.check_manifest(MANIFEST_REPLY, REQUEST)
        self.assertEqual(defects, [])
        self.assertEqual(manifest["criteria"], MANIFEST["criteria"])
        self.assertEqual(manifest["ambiguities"], [AMBIGUITY])
        self.assertEqual(notes, ["It felt slow on large blogs yesterday."])

    def test_an_ambiguity_no_criterion_depends_on_is_dropped(self):
        """No answer to it could change the verdict, so nobody should be asked
        it. The 0.3.1 deriver raised 41 of these on 16 one-line requests."""
        reply = json.dumps(dict(MANIFEST, ambiguities=[
            "What should an empty list return?",
            {"question": "Where should the code live?", "assumed": "anywhere", "criteria": []},
            AMBIGUITY]))
        manifest, defects, _ = vl.check_manifest(reply, REQUEST)
        self.assertEqual(defects, [])
        self.assertEqual(manifest["ambiguities"], [AMBIGUITY])
        self.assertEqual(manifest["unlinked_ambiguities"], 2)

    def test_an_ambiguity_must_name_real_criteria_and_the_reading_they_assume(self):
        cases = {
            "ids of this manifest's criteria": dict(AMBIGUITY, criteria=[7]),
            "which reading criteria": dict(AMBIGUITY, assumed=" "),
            "must be an object with": {"assumed": "created", "criteria": [1]},
        }
        for expected, ambiguity in cases.items():
            _, defects, _ = vl.check_manifest(json.dumps(dict(MANIFEST, ambiguities=[ambiguity])), REQUEST)
            self.assertTrue(any(expected in d for d in defects), (expected, defects))

    def test_a_quote_must_come_from_the_request(self):
        """Otherwise a criterion could be invented and attributed to the user."""
        bad = json.dumps(dict(MANIFEST, criteria=MANIFEST["criteria"] + [
            {"id": 4, "text": "Results are cached", "quote": "cache the results"}]))
        _, defects, _ = vl.check_manifest(bad, REQUEST)
        self.assertEqual(len(defects), 1)
        self.assertIn("criterion 4: its quote does not occur in the request", defects[0])

    def test_quotes_tolerate_spacing_and_case_but_nothing_else(self):
        ok = json.dumps({"manifest": 1, "criteria": [{"id": 1, "text": "newest first", "quote": "Newest   First"}]})
        self.assertEqual(vl.check_manifest(ok, REQUEST)[1], [])
        near = json.dumps({"manifest": 1, "criteria": [{"id": 1, "text": "newest first", "quote": "newest post first"}]})
        self.assertTrue(vl.check_manifest(near, REQUEST)[1])

    def test_an_inferred_criterion_needs_no_quote(self):
        doc = json.dumps({"manifest": 1, "criteria": [{"id": 1, "text": "Ties keep their order", "quote": None}]})
        manifest, defects, _ = vl.check_manifest(doc, REQUEST)
        self.assertEqual(defects, [])
        self.assertIsNone(manifest["criteria"][0]["quote"])

    def test_malformed_manifests_are_rejected(self):
        cases = {
            "no JSON object": "I could not think of any criteria.",
            "non-empty list": json.dumps({"manifest": 1, "criteria": []}),
            "ids must run 1..N": json.dumps({"manifest": 1, "criteria": [{"id": 2, "text": "x", "quote": None}]}),
            "one non-empty line": json.dumps({"manifest": 1, "criteria": [{"id": 1, "text": "a\nb", "quote": None}]}),
            "piece of the request, or null": json.dumps({"manifest": 1, "criteria": [{"id": 1, "text": "x", "quote": ""}]}),
            "'ambiguities' must be a list": json.dumps({"manifest": 1, "criteria": [{"id": 1, "text": "x", "quote": None}], "ambiguities": "none"}),
        }
        for expected, doc in cases.items():
            _, defects, _ = vl.check_manifest(doc, REQUEST)
            self.assertTrue(any(expected in d for d in defects), (expected, defects))

    def test_a_ledger_covering_the_manifest_is_valid(self):
        texts = [c["text"] for c in MANIFEST["criteria"]]
        ledger, defects = vl.validate(self.ledger(*texts), MANIFEST)
        self.assertEqual(defects, [])
        self.assertEqual(vl.verdict_of(ledger), "MATCHES INTENT")

    def test_the_verifier_may_add_criteria_after_the_manifest(self):
        texts = [c["text"] for c in MANIFEST["criteria"]] + ["Posts with equal dates keep their order"]
        self.assertEqual(vl.validate(self.ledger(*texts), MANIFEST)[1], [])

    def test_a_requirement_left_out_is_a_defect_not_a_pass(self):
        """The hole 0.2.1 could only cover in prose: a well-formed ledger that
        never mentions one requirement validated as MATCHES INTENT."""
        omitted = self.ledger("Posts are in date order", "The newest post comes first")
        self.assertEqual(vl.validate(omitted)[1], [], "valid when nothing says what should be there")
        _, defects = vl.validate(omitted, MANIFEST)
        self.assertEqual(defects, ["criterion 3 of the manifest is missing from the ledger: 'No post is dropped'"])

    def test_a_reworded_or_reordered_criterion_is_a_defect(self):
        swapped = self.ledger("The newest post comes first", "Posts are in date order", "No post is dropped")
        _, defects = vl.validate(swapped, MANIFEST)
        self.assertEqual(len(defects), 2)
        self.assertTrue(all("does not match the manifest" in d for d in defects), defects)
        reworded = self.ledger("Posts are sorted", "The newest post comes first", "No post is dropped")
        self.assertTrue(any("criterion 1 does not match" in d for d in vl.validate(reworded, MANIFEST)[1]))
        respaced = self.ledger("posts are in  date order", "The newest post comes first", "No post is dropped")
        self.assertEqual(vl.validate(respaced, MANIFEST)[1], [], "spacing and case are not rewording")

    def test_no_omission_survives_the_manifest(self):
        """Seeded: drop any non-empty subset of a faithful all-PASS ledger's
        criteria, renumbered or not. Renumbered, most of these validate when
        checked alone; none validates against the manifest."""
        rng = random.Random(20261005)
        passed_alone = 0
        for _ in range(1000):
            n = rng.randint(2, 7)
            manifest = {"manifest": 1, "ambiguities": [],
                        "criteria": [{"id": i, "text": "requirement %d" % i, "quote": None} for i in range(1, n + 1)]}
            kept = sorted(rng.sample(range(1, n + 1), rng.randint(1, n - 1)))
            renumber = rng.random() < 0.7
            blocks = []
            for position, original in enumerate(kept, 1):
                blocks += passing(position if renumber else original, "requirement %d" % original)
            text = L("INTENT-VERIFY LEDGER v1", "mode: FULL", "", *blocks, "FINAL: MATCHES INTENT")
            passed_alone += not vl.validate(text)[1]
            self.assertTrue(vl.validate(text, manifest)[1], text)
        self.assertGreater(passed_alone, 500, "these ledgers must pass bare validation or the property is vacuous")

    def test_manifest_from_lines(self):
        manifest = vl.manifest_from_lines("1. first thing\n* second thing\n\n   - [x] third thing\n# not a criterion\n")
        self.assertEqual([(c["id"], c["text"], c["quote"]) for c in manifest["criteria"]],
                         [(1, "first thing", None), (2, "second thing", None), (3, "third thing", None)])


if __name__ == "__main__":
    unittest.main()
