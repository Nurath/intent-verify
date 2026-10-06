"""Checks on the parts of the plugin that are prose or configuration.

The skill, the agent definitions and the hook registration are instructions and
JSON, not code, so nothing else exercises them. Each test here pins a promise
that one of those files makes and that a later edit could quietly break.
"""
import json
import os
import re
import sys
import unittest

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE, "tools"))
import validate_ledger  # noqa: E402


def read(*parts):
    with open(os.path.join(BASE, *parts), encoding="utf-8") as f:
        return f.read()


def frontmatter(*parts):
    block = read(*parts).split("---", 2)[1]
    return dict(line.split(":", 1) for line in block.strip().splitlines() if ":" in line and not line.startswith(" "))


class TestSkillText(unittest.TestCase):
    SKILL = read("skills", "intent-verify", "SKILL.md")

    def test_every_bundled_helper_is_called_through_the_plugin_root(self):
        """The skill runs inside the user's project. 0.2.0 called its helpers by
        a path relative to this repository, which does not exist there."""
        for helper, folder in (("capture-intent.js", "hooks"), ("validate_ledger.py", "tools"),
                               ("select_verifier.py", "tools")):
            prefix = "${CLAUDE_PLUGIN_ROOT}/%s/" % folder
            hits = [m.start() for m in re.finditer(re.escape(helper), self.SKILL)]
            self.assertTrue(hits, "%s is never mentioned" % helper)
            for at in hits:
                self.assertEqual(self.SKILL[at - len(prefix):at], prefix, "%s at offset %d" % (helper, at))

    def test_reader_commands_say_where_the_ledger_is(self):
        commands = [l for l in self.SKILL.splitlines() if "capture-intent.js" in l]
        self.assertEqual([("--list" in l, "--freeze" in l, "--begin-run" in l) for l in commands],
                         [(True, False, False), (False, True, False), (False, False, True)])
        for line in commands:
            self.assertIn('--data "${CLAUDE_PLUGIN_DATA}"', line)
            self.assertIn('--project "${CLAUDE_PROJECT_DIR}"', line)
        for line in (commands[0], commands[2]):
            self.assertIn('--session "${CLAUDE_SESSION_ID}"', line)

    def test_the_verdict_comes_from_the_reply_the_hook_captured(self):
        """0.4.0: the session that wrote the code no longer relays the evidence."""
        step6 = self.SKILL[self.SKILL.index("**Validate the ledger before trusting it.**"):self.SKILL.index("**Report the ledger**")]
        commands = [l.strip() for l in step6.splitlines() if "validate_ledger.py" in l]
        self.assertEqual(len(commands), 2)
        self.assertIn('--run "<run dir>" --manifest "<scratch>/manifest.json"', commands[0])
        self.assertIn('--nonce <nonce> --manifest "<scratch>/manifest.json"', commands[1])
        self.assertIn("relayed by you and not\n   captured", step6)
        self.assertIn("RUN NONCE:", self.SKILL[self.SKILL.index("**Dispatch the verifier (stage 2).**"):])

    def test_the_procedure_writes_nothing_inside_the_project(self):
        self.assertNotIn(".intent/frozen", self.SKILL)
        targets = re.findall(r'--out "([^"]+)"', self.SKILL)
        self.assertTrue(targets)
        for target in targets:
            self.assertTrue(target.startswith("<scratch>/"), target)

    def test_the_ledger_is_validated_against_the_manifest(self):
        validations = [l for l in self.SKILL.splitlines() if '"<scratch>/ledger.txt"' in l and "validate_ledger.py" in l]
        self.assertEqual(len(validations), 1)
        self.assertIn('--manifest "<scratch>/manifest.json"', validations[0])

    def test_ambiguities_are_not_asked_before_verifying(self):
        """0.3.1 put every ambiguity to the user before the check ran: 2 to 4
        questions on each one-line request, none of which changed a verdict.
        A question now comes after the evidence, and only when it matters."""
        step2 = self.SKILL[self.SKILL.index("**Fix the criteria (stage 1).**"):self.SKILL.index("**Select the verifier model**")]
        self.assertIn("Do not stop to ask", step2)
        self.assertNotIn("before going further", step2)
        report = self.SKILL[self.SKILL.index("**Report the ledger**"):]
        self.assertIn("FAILED or was NOT-EXERCISED", report)
        self.assertIn("One clarification only", report)


class TestPluginFiles(unittest.TestCase):
    READS_OR_RUNS = {"Read", "Grep", "Glob", "Bash", "PowerShell", "Edit", "Write", "NotebookEdit", "WebFetch",
                     "WebSearch", "Agent", "Skill", "LSP", "Monitor", "ToolSearch", "Artifact", "SendMessage"}

    def tools(self, name):
        return {t.strip() for t in frontmatter("agents", name)["tools"].split(",")}

    def test_the_criteria_agent_has_no_tool_that_reads_or_runs(self):
        """'Criteria before code' rests on this list. It is an allowlist, so a
        tool added to Claude Code later is not granted by default."""
        front = frontmatter("agents", "criteria.md")
        self.assertNotIn("disallowedTools", front)
        self.assertTrue(self.tools("criteria.md"))
        self.assertEqual(self.tools("criteria.md") & self.READS_OR_RUNS, set())
        self.assertEqual(front["omitClaudeMd"].strip(), "true")

    def test_the_verifier_agent_cannot_edit(self):
        self.assertEqual(self.tools("verifier.md"), {"Read", "Grep", "Glob", "Bash"})

    def test_the_verifier_writes_a_ledger_bound_to_its_run(self):
        body = read("agents", "verifier.md")
        self.assertIn("RUN NONCE", body)
        self.assertIn('"nonce": "<the RUN NONCE, copied exactly>"', body)
        self.assertNotIn("INTENT-VERIFY LEDGER v1", body)

    def test_the_verifiers_template_is_the_ledger_the_validator_accepts(self):
        """The prompt and the validator are two descriptions of one format."""
        body = read("agents", "verifier.md")
        template = body[body.index('{"ledger": 2,'):body.index("Format rules the validator enforces")]
        entry = template[template.index('{"id": 1'):template.index("...")]
        top = template.replace(entry, "")
        self.assertEqual(tuple(re.findall(r'"(\w+)":', top)), validate_ledger.LEDGER_KEYS, "the seal comes last")
        self.assertEqual(tuple(re.findall(r'"(\w+)":', entry)), validate_ledger.ENTRY_KEYS)
        self.assertNotIn("OBSERVATIONS:", body, "remarks go inside the object now")

    def test_hooks_register_every_capture_event_in_exec_form(self):
        hooks = json.loads(read("hooks", "hooks.json"))["hooks"]
        self.assertEqual(sorted(hooks), ["PostToolUse", "SubagentStop", "UserPromptSubmit"])
        self.assertEqual(hooks["PostToolUse"][0]["matcher"], "AskUserQuestion")
        # Plugin agents are matched by their qualified name; the bare name never fires.
        self.assertEqual(hooks["SubagentStop"][0]["matcher"], "intent-verify:intent-verifier")
        qualified = json.loads(read(".claude-plugin", "plugin.json"))["name"] + ":" + frontmatter("agents", "verifier.md")["name"].strip()
        self.assertEqual(hooks["SubagentStop"][0]["matcher"], qualified)
        self.assertIn("const VERIFIER_AGENT = '%s';" % qualified, read("hooks", "capture-intent.js"))
        for entries in hooks.values():
            for hook in entries[0]["hooks"]:
                self.assertEqual((hook["command"], hook["args"]), ("node", ["${CLAUDE_PLUGIN_ROOT}/hooks/capture-intent.js"]))

    def test_the_version_matches_the_changelog(self):
        version = json.loads(read(".claude-plugin", "plugin.json"))["version"]
        latest = re.search(r"^## (\d+\.\d+\.\d+)", read("CHANGELOG.md"), re.M).group(1)
        self.assertEqual(version, latest)


if __name__ == "__main__":
    unittest.main()
