import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOOKS = os.path.join(BASE, "hooks")


def run_hook(cmd, payload, project_dir, extra_env=None):
    env = {**os.environ, "CLAUDE_PROJECT_DIR": project_dir, **(extra_env or {})}
    return subprocess.run(cmd, input=payload, capture_output=True, text=True, timeout=30, env=env)


def read_jsonl(project_dir):
    p = os.path.join(project_dir, ".intent", "log.jsonl")
    if not os.path.exists(p):
        return []
    with open(p, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


class HookContract:
    """Shared contract every runtime implementation must satisfy."""
    CMD = None

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="intent-verify-test-")

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_captures_prompt(self):
        r = run_hook(self.CMD, json.dumps({"prompt": "sort by date, newest first"}), self.dir)
        self.assertEqual(r.returncode, 0)
        self.assertEqual(r.stdout, "", "hook stdout is injected as context; must stay silent")
        entries = read_jsonl(self.dir)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["kind"], "task")
        self.assertIn("newest first", entries[0]["prompt"])

    def test_tags_verify_invocations(self):
        run_hook(self.CMD, json.dumps({"prompt": "verify this did what I asked"}), self.dir)
        self.assertEqual(read_jsonl(self.dir)[0]["kind"], "verify-invocation")

    def test_malformed_json_exits_zero_writes_nothing(self):
        r = run_hook(self.CMD, "{definitely not json", self.dir)
        self.assertEqual(r.returncode, 0)
        self.assertEqual(read_jsonl(self.dir), [])

    def test_null_prompt_skipped_not_logged_as_none(self):
        r = run_hook(self.CMD, json.dumps({"prompt": None}), self.dir)
        self.assertEqual(r.returncode, 0)
        self.assertEqual(read_jsonl(self.dir), [])

    def test_redacts_tokens(self):
        secret = "ghp_" + "a" * 36
        run_hook(self.CMD, json.dumps({"prompt": "use %s please" % secret}), self.dir)
        entries = read_jsonl(self.dir)
        self.assertNotIn(secret, entries[0]["prompt"])
        self.assertIn("[REDACTED:github-token]", entries[0]["prompt"])
        raw = open(os.path.join(self.dir, ".intent", "log.md"), encoding="utf-8").read()
        self.assertNotIn(secret, raw)

    def test_truncates_and_marks(self):
        run_hook(self.CMD, json.dumps({"prompt": "y" * 9000}), self.dir,
                 extra_env={"INTENT_VERIFY_MAX_PROMPT": "1000"})
        e = read_jsonl(self.dir)[0]
        self.assertTrue(e.get("truncated"))
        self.assertLess(len(e["prompt"]), 1200)

    def test_unicode_survives(self):
        run_hook(self.CMD, json.dumps({"prompt": "préférence — 中文 — emoji ✅"}), self.dir)
        self.assertIn("中文", read_jsonl(self.dir)[0]["prompt"])

    def test_md_fences_never_collide(self):
        run_hook(self.CMD, json.dumps({"prompt": "look:\n```py\nx=1\n```\n---\n## fake"}), self.dir)
        md = open(os.path.join(self.dir, ".intent", "log.md"), encoding="utf-8").read()
        self.assertIn("````", md)


@unittest.skipUnless(shutil.which("node"), "node not available")
class TestNodeHook(HookContract, unittest.TestCase):
    CMD = ["node", os.path.join(HOOKS, "capture-intent.js")]

    def test_selftest_green(self):
        r = subprocess.run(self.CMD + ["--selftest"], capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


class TestPythonHook(HookContract, unittest.TestCase):
    CMD = [sys.executable, os.path.join(HOOKS, "capture-intent.py")]


@unittest.skipUnless(os.name == "posix", "sh dispatcher is POSIX-only")
class TestShDispatcher(HookContract, unittest.TestCase):
    CMD = ["sh", os.path.join(HOOKS, "capture-intent.sh")]

    def test_rotation(self):
        for i in range(4):
            run_hook(self.CMD, json.dumps({"prompt": "p%d " % i + "z" * 400}), self.dir,
                     extra_env={"INTENT_VERIFY_MAX_LOG": "600"})
        d = os.path.join(self.dir, ".intent")
        rotated = [f for f in os.listdir(d) if f.endswith(".old")]
        self.assertTrue(rotated, "expected rotation archives at tiny INTENT_VERIFY_MAX_LOG")


if __name__ == "__main__":
    unittest.main()
