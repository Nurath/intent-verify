import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOOKS = os.path.join(BASE, "hooks")
MIB = 1024 * 1024


def run_hook(cmd, payload, project_dir, extra_env=None):
    """payload: str (sent as text) or bytes (sent verbatim)."""
    env = {**os.environ, "CLAUDE_PROJECT_DIR": project_dir, **(extra_env or {})}
    if isinstance(payload, bytes):
        return subprocess.run(cmd, input=payload, capture_output=True, timeout=60, env=env)
    return subprocess.run(cmd, input=payload, capture_output=True, text=True, timeout=60, env=env)


def read_jsonl(project_dir):
    p = os.path.join(project_dir, ".intent", "log.jsonl")
    if not os.path.exists(p):
        return []
    with open(p, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


class HookContract:
    """Shared contract every runtime implementation must satisfy."""
    CMD = None

    # Only an unmistakable request to RUN verification is tagged. A task that
    # merely starts with "verify this ..." defines work: tagging it would hide
    # it from the freeze step, which then verifies against an older request.
    KINDS = {
        "verify this did what I asked": "verify-invocation",
        "verify that it did what I wanted": "verify-invocation",
        "did it actually do what I wanted?": "verify-invocation",
        "check this did what I asked": "verify-invocation",
        "/intent-verify": "verify-invocation",
        "/intent-verify:intent-verify focus on sorting": "verify-invocation",
        "verify this.": "verify-invocation",
        "intent-verify": "verify-invocation",
        "intent-verify should also handle multi-turn requests": "task",
        "intent-verify-review.md can you check this review": "task",
        "verify this endpoint returns 404 for missing users": "task",
        "verify that the cache invalidates on logout": "task",
        "add a 404 handler": "task",
    }

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

    def test_only_unmistakable_invocations_are_tagged(self):
        for prompt, kind in self.KINDS.items():
            run_hook(self.CMD, json.dumps({"prompt": prompt}), self.dir)
            self.assertEqual(read_jsonl(self.dir)[-1]["kind"], kind, prompt)

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
        with open(os.path.join(self.dir, ".intent", "log.md"), encoding="utf-8") as f:
            self.assertNotIn(secret, f.read())

    def test_redacts_prefixed_api_keys(self):
        """sk-proj-... and sk-ant-api03-... bodies contain '-' and '_'; the old
        pattern required an unbroken alphanumeric run and stored both verbatim."""
        shapes = {
            "legacy": "sk-" + "A1b2" * 8,
            "project": "sk-proj-" + "Ab1_" * 12,
            "anthropic": "sk-ant-api03-" + "Ab1-" * 20 + "AA",
        }
        for name, key in shapes.items():
            run_hook(self.CMD, json.dumps({"prompt": "use %s for auth" % key}), self.dir)
            e = read_jsonl(self.dir)[-1]
            self.assertNotIn(key, e["prompt"], name)
            self.assertIn("[REDACTED:api-key]", e["prompt"], name)

    def test_hyphenated_prose_is_not_redacted(self):
        prose = "rename sk-admin-panel-redesign-with-new-layout and the sk-learn-compatible-estimator"
        run_hook(self.CMD, json.dumps({"prompt": prose}), self.dir)
        e = read_jsonl(self.dir)[0]
        self.assertEqual(e["prompt"], prose)
        self.assertNotIn("redactions", e)

    def test_truncates_and_marks(self):
        run_hook(self.CMD, json.dumps({"prompt": "y" * 9000}), self.dir,
                 extra_env={"INTENT_VERIFY_MAX_PROMPT": "1000"})
        e = read_jsonl(self.dir)[0]
        self.assertTrue(e.get("truncated"))
        self.assertLess(len(e["prompt"]), 1200)

    def test_unicode_survives(self):
        run_hook(self.CMD, json.dumps({"prompt": "préférence — 中文 — emoji ✅"}), self.dir)
        self.assertIn("中文", read_jsonl(self.dir)[0]["prompt"])

    def test_raw_utf8_bytes_survive(self):
        """The payload arrives as UTF-8 bytes, not ASCII escapes. A runtime that
        decodes stdin with the locale codepage mangles every non-ASCII prompt."""
        text = "préférence — 中文 — emoji ✅"
        r = run_hook(self.CMD, json.dumps({"prompt": text}, ensure_ascii=False).encode("utf-8"), self.dir)
        self.assertEqual(r.returncode, 0)
        self.assertEqual(read_jsonl(self.dir)[0]["prompt"], text)

    def test_keeps_session_and_transcript_path(self):
        run_hook(self.CMD, json.dumps({"prompt": "p", "session_id": "s-1", "transcript_path": "/t/s-1.jsonl"}), self.dir)
        e = read_jsonl(self.dir)[0]
        self.assertEqual((e["session_id"], e["transcript_path"]), ("s-1", "/t/s-1.jsonl"))

    def test_md_fences_never_collide(self):
        run_hook(self.CMD, json.dumps({"prompt": "look:\n```py\nx=1\n```\n---\n## fake"}), self.dir)
        with open(os.path.join(self.dir, ".intent", "log.md"), encoding="utf-8") as f:
            md = f.read()
        self.assertIn("````", md)

    @unittest.skipUnless(shutil.which("git"), "git not available")
    def test_ledger_dir_ignores_itself(self):
        """The ledger holds raw prompts inside the USER's repository, where this
        plugin's own .gitignore does not apply. A broad `git add .` must not be
        able to stage it."""
        subprocess.run(["git", "init", "-q", self.dir], check=True, capture_output=True)
        run_hook(self.CMD, json.dumps({"prompt": "add a dark mode toggle"}), self.dir)
        self.assertTrue(read_jsonl(self.dir), "nothing was captured")
        st = subprocess.run(["git", "-C", self.dir, "status", "--porcelain"], capture_output=True, text=True)
        self.assertEqual(st.stdout.strip(), "")

    # What a 12 MiB prompt leaves behind. node and python stop reading at
    # 10 MiB, so the JSON never parses and they record that a prompt was lost.
    OVERSIZED = "capture-incomplete"

    def test_oversized_input_is_never_dropped_silently(self):
        """A silent gap lets the freeze step fall back to an older task and
        verify the wrong request, so the ledger must show that a prompt arrived:
        a capture-incomplete marker, or the capped text flagged as truncated."""
        payload = json.dumps({"session_id": "s-big", "prompt": "x" * (12 * MIB)})
        r = run_hook(self.CMD, payload, self.dir)
        self.assertEqual(r.returncode, 0, "hook must always exit 0")
        self.assertEqual(r.stdout, "", "hook stdout is injected as context; must stay silent")
        entries = read_jsonl(self.dir)
        self.assertEqual([e["kind"] for e in entries], [self.OVERSIZED])
        self.assertEqual(entries[0].get("session_id"), "s-big")
        if self.OVERSIZED == "task":
            self.assertTrue(entries[0].get("truncated"))
        else:
            self.assertEqual(entries[0]["prompt"], "")


@unittest.skipUnless(shutil.which("node"), "node not available")
class TestNodeHook(HookContract, unittest.TestCase):
    CMD = ["node", os.path.join(HOOKS, "capture-intent.js")]

    def _cli(self, *args):
        return subprocess.run(self.CMD + list(args) + ["--project", self.dir],
                              capture_output=True, text=True, encoding="utf-8", timeout=30)

    def _from_file(self, payload):
        src = os.path.join(self.dir, "payload.json")
        with open(src, "w", encoding="utf-8") as f:
            f.write(payload)
        env = {**os.environ, "CLAUDE_PROJECT_DIR": self.dir}
        with open(src, "rb") as fh:
            return subprocess.run(self.CMD, stdin=fh, capture_output=True, text=True, timeout=60, env=env)

    def test_selftest_green(self):
        r = subprocess.run(self.CMD + ["--selftest"], capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_stdin_cap_does_not_break_the_stream_lifecycle(self):
        """Regression: the >10MiB memory guard used process.stdin.pause().

        A paused stream never emits 'end', so the capture+exit path never ran and
        the prompt was silently DROPPED. stdin is a redirected file here, not a
        pipe: the drop was chunk-timing dependent and reproduced on this
        transport. Sized just past the cap so the JSON still closes -- the
        prompt is captured (truncated), not lost.
        """
        r = self._from_file(json.dumps({"prompt": "x" * (10 * MIB + 20000)}))
        self.assertEqual(r.returncode, 0, "hook must always exit 0")
        self.assertEqual(r.stdout, "", "hook stdout is injected as context; must stay silent")
        entries = read_jsonl(self.dir)
        self.assertEqual(len(entries), 1, "oversized prompt must still reach the ledger")
        self.assertTrue(entries[0]["truncated"])

    def test_unreadable_input_leaves_a_marker_on_a_file_transport_too(self):
        r = self._from_file(json.dumps({"session_id": "s-big", "prompt": "x" * (12 * MIB)}))
        self.assertEqual(r.returncode, 0)
        self.assertEqual([e["kind"] for e in read_jsonl(self.dir)], ["capture-incomplete"])

    def test_list_is_scoped_to_the_session(self):
        """Every session in a project writes to one ledger, so 'the newest task'
        is often somebody else's prompt."""
        run_hook(self.CMD, json.dumps({"prompt": "mine: sort newest first", "session_id": "A"}), self.dir)
        run_hook(self.CMD, json.dumps({"prompt": "theirs: unrelated work", "session_id": "B"}), self.dir)
        out = self._cli("--list", "--session", "A").stdout
        self.assertIn("mine: sort newest first", out)
        self.assertNotIn("theirs", out)
        out = self._cli("--list", "--session", "nobody").stdout
        self.assertIn("NO entries for session nobody", out)
        self.assertIn("other-session", out)
        # Scoping requested, but the caller had no id to pass: say so, because an
        # unscoped listing is otherwise indistinguishable from a scoped one.
        self.assertIn("session id unavailable", self._cli("--list", "--session", "").stdout)

    def test_freeze_writes_the_request_verbatim(self):
        text = "line one\n```py\nx = 1\n```\n  two trailing spaces  "
        run_hook(self.CMD, json.dumps({"prompt": text, "session_id": "A"}), self.dir)
        r = self._cli("--freeze", read_jsonl(self.dir)[0]["id"])
        self.assertEqual(r.returncode, 0, r.stderr)
        meta = json.loads(r.stdout)
        self.assertFalse(meta["truncated"])
        with open(meta["file"], encoding="utf-8", newline="") as f:
            self.assertEqual(f.read(), text)

    def test_freeze_exits_3_for_a_truncated_request(self):
        """An incomplete request must be impossible to miss: verifying against
        it can pass a change that violates the part that was cut off."""
        run_hook(self.CMD, json.dumps({"prompt": "y" * 5000}), self.dir,
                 extra_env={"INTENT_VERIFY_MAX_PROMPT": "1000"})
        r = self._cli("--freeze", read_jsonl(self.dir)[0]["id"])
        self.assertEqual(r.returncode, 3)
        self.assertTrue(json.loads(r.stdout)["truncated"])

    def test_freeze_rejects_unknown_ids(self):
        self.assertEqual(self._cli("--freeze", "nope").returncode, 2)
        self.assertEqual(self._cli("--freeze", "../escape").returncode, 2)


class TestPythonHook(HookContract, unittest.TestCase):
    CMD = [sys.executable, os.path.join(HOOKS, "capture-intent.py")]


def _ps_hook(exe):
    return [exe, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", os.path.join(HOOKS, "capture-intent.ps1")]


@unittest.skipUnless(os.name == "nt" and shutil.which("powershell"), "Windows PowerShell 5.1 not available")
class TestWindowsPowerShellHook(HookContract, unittest.TestCase):
    CMD = _ps_hook("powershell")
    OVERSIZED = "task"  # reads all of stdin, then stores the capped prompt as truncated


@unittest.skipUnless(os.name == "nt" and shutil.which("pwsh"), "PowerShell 7 not available")
class TestPwshHook(HookContract, unittest.TestCase):
    CMD = _ps_hook("pwsh")
    OVERSIZED = "task"


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


@unittest.skipUnless(os.name == "posix", "sh dispatcher is POSIX-only")
class TestShDegradedPaths(unittest.TestCase):
    """The dispatcher's fallbacks for a machine with neither node nor python.

    The contract suite above never reaches them: with node on PATH the
    dispatcher delegates at its first branch. Here PATH holds only the tools
    those fallbacks are allowed to use, so the branches actually run.
    """
    TOOLS = ["cat", "sed", "head", "wc", "mv", "date", "mkdir", "tr", "dirname", "rm", "grep"]

    def setUp(self):
        if not all(shutil.which(t) for t in self.TOOLS + ["sh"]):
            self.skipTest("coreutils not available")
        self.dir = tempfile.mkdtemp(prefix="intent-verify-test-")
        self.farm = tempfile.mkdtemp(prefix="intent-verify-path-")
        for tool in self.TOOLS:
            os.symlink(shutil.which(tool), os.path.join(self.farm, tool))

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)
        shutil.rmtree(self.farm, ignore_errors=True)

    def run_sh(self, payload, **env):
        full = {"PATH": self.farm, "CLAUDE_PROJECT_DIR": self.dir, **env}
        return subprocess.run([shutil.which("sh"), os.path.join(HOOKS, "capture-intent.sh")],
                              input=payload, capture_output=True, text=True, timeout=30, env=full)

    def test_last_resort_path_is_bounded_and_self_ignoring(self):
        d = os.path.join(self.dir, ".intent")
        os.makedirs(d)
        for day in range(1, 6):
            open(os.path.join(d, "log.md.2020-01-0%dT00-00-00Z.old" % day), "w").close()
        with open(os.path.join(d, "log.md"), "w") as f:
            f.write("z" * 500)
        r = self.run_sh(json.dumps({"prompt": "add a 404 handler"}), INTENT_VERIFY_MAX_LOG="100")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout, "")
        archives = sorted(f for f in os.listdir(d) if f.endswith(".old"))
        self.assertEqual(len(archives), 3, "rotation must keep 3 archives, not grow forever: %s" % archives)
        self.assertNotIn("log.md.2020-01-01T00-00-00Z.old", archives, "the oldest archive goes first")
        with open(os.path.join(d, ".gitignore")) as f:
            self.assertEqual(f.read(), "*\n")
        with open(os.path.join(d, "log.md"), encoding="utf-8") as f:
            self.assertIn("404 handler", f.read())

    @unittest.skipUnless(shutil.which("jq"), "jq not available")
    def test_jq_path_tags_and_redacts(self):
        os.symlink(shutil.which("jq"), os.path.join(self.farm, "jq"))
        key = "sk-proj-" + "Ab1_" * 12
        self.run_sh(json.dumps({"prompt": "verify this did what I asked"}))
        r = self.run_sh(json.dumps({"prompt": "verify this endpoint returns 404 using %s" % key}))
        self.assertEqual(r.returncode, 0, r.stderr)
        entries = read_jsonl(self.dir)
        self.assertEqual([e["kind"] for e in entries], ["verify-invocation", "task"])
        self.assertNotIn(key, entries[1]["prompt"])
        self.assertIn("[REDACTED:api-key]", entries[1]["prompt"])


if __name__ == "__main__":
    unittest.main()
