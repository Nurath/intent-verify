import glob
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOOKS = os.path.join(BASE, "hooks")
MIB = 1024 * 1024


def data_dir(project_dir):
    """Where the Node hook is told to keep its ledger in tests: beside the project."""
    return project_dir + ".data"


def run_hook(cmd, payload, project_dir, extra_env=None):
    """payload: str (sent as text) or bytes (sent verbatim)."""
    env = {**os.environ, "CLAUDE_PROJECT_DIR": project_dir, "INTENT_VERIFY_DATA": data_dir(project_dir),
           **(extra_env or {})}
    if isinstance(payload, bytes):
        return subprocess.run(cmd, input=payload, capture_output=True, timeout=60, env=env)
    return subprocess.run(cmd, input=payload, capture_output=True, text=True, timeout=60, env=env)


def read_jsonl(project_dir):
    """Every captured entry, oldest first, wherever the runtime keeps it: the Node
    hook writes one file per session under the data directory, the alternates
    write <project>/.intent/log.jsonl."""
    files = sorted(glob.glob(os.path.join(data_dir(project_dir), "projects", "*", "sessions", "*.jsonl")))
    files.append(os.path.join(project_dir, ".intent", "log.jsonl"))
    entries = []
    for p in files:
        if os.path.exists(p):
            with open(p, encoding="utf-8") as f:
                entries += [json.loads(l) for l in f if l.strip()]
    return sorted(entries, key=lambda e: e.get("ts", ""))


class HookContract:
    """Shared contract every runtime implementation must satisfy."""
    CMD = None
    IN_PROJECT = True  # the runtime writes <project>/.intent/ (everything except the Node hook)

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
        shutil.rmtree(data_dir(self.dir), ignore_errors=True)

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
        for root in (self.dir, data_dir(self.dir)):  # no file the hook wrote may hold it
            for d, _dirs, names in os.walk(root):
                for name in names:
                    with open(os.path.join(d, name), encoding="utf-8", errors="replace") as f:
                        self.assertNotIn(secret, f.read(), name)

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
        if not self.IN_PROJECT:
            self.skipTest("only the in-project layout keeps a markdown mirror")
        run_hook(self.CMD, json.dumps({"prompt": "look:\n```py\nx=1\n```\n---\n## fake"}), self.dir)
        with open(os.path.join(self.dir, ".intent", "log.md"), encoding="utf-8") as f:
            md = f.read()
        self.assertIn("````", md)

    @unittest.skipUnless(shutil.which("git"), "git not available")
    def test_capture_leaves_nothing_git_would_stage(self):
        """Raw prompts must never be something a broad `git add .` can pick up in
        the USER's repository, where this plugin's own .gitignore does not
        apply. The Node hook writes outside the project; the alternates write a
        .intent/ directory that ignores itself."""
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
    IN_PROJECT = False

    QUESTION = {"question": "Ship now or later?", "header": "Ship", "multiSelect": False,
                "options": [{"label": "Now", "description": "today"}, {"label": "Later", "description": "next week"}]}

    def _cli(self, *args):
        return subprocess.run(self.CMD + list(args) + ["--project", self.dir, "--data", data_dir(self.dir)],
                              capture_output=True, text=True, encoding="utf-8", timeout=30)

    def _from_file(self, payload):
        src = os.path.join(self.dir, "payload.json")
        with open(src, "w", encoding="utf-8") as f:
            f.write(payload)
        env = {**os.environ, "CLAUDE_PROJECT_DIR": self.dir, "INTENT_VERIFY_DATA": data_dir(self.dir)}
        with open(src, "rb") as fh:
            return subprocess.run(self.CMD, stdin=fh, capture_output=True, text=True, timeout=60, env=env)

    def _answered(self, response):
        return json.dumps({"hook_event_name": "PostToolUse", "tool_name": "AskUserQuestion", "session_id": "A",
                           "prompt_id": "p-1", "tool_input": {"questions": [self.QUESTION]}, "tool_response": response})

    def _stale_and_fresh(self):
        """An old and a recent session file plus a stray note in a project the
        hook created, and an old file in a directory it did not create."""
        projects = os.path.join(data_dir(self.dir), "projects")
        ours = os.path.join(projects, "0123456789abcdef", "sessions")
        foreign = os.path.join(projects, "someone-elses", "sessions")
        os.makedirs(ours)
        os.makedirs(foreign)
        with open(os.path.join(projects, "0123456789abcdef", "project.json"), "w") as f:
            json.dump({"path": "/somewhere"}, f)
        paths = [os.path.join(ours, n) for n in ("old.jsonl", "recent.jsonl", "notes.txt")]
        paths.append(os.path.join(foreign, "old.jsonl"))
        long_ago = time.time() - 40 * 86400
        for p in paths:
            open(p, "w").close()
            if "recent" not in p:
                os.utime(p, (long_ago, long_ago))
        return paths

    def test_selftest_green(self):
        r = subprocess.run(self.CMD + ["--selftest"], capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_writes_one_file_per_session_and_nothing_in_the_project(self):
        run_hook(self.CMD, json.dumps({"prompt": "add a 404 handler", "session_id": "A", "prompt_id": "p-1"}), self.dir)
        run_hook(self.CMD, json.dumps({"prompt": "unrelated", "session_id": "B"}), self.dir)
        self.assertEqual(os.listdir(self.dir), [], "the plugin hook must not write inside the project")
        files = glob.glob(os.path.join(data_dir(self.dir), "projects", "*", "sessions", "*.jsonl"))
        self.assertEqual(sorted(os.path.basename(f) for f in files), ["A.jsonl", "B.jsonl"])
        self.assertEqual(read_jsonl(self.dir)[0]["prompt_id"], "p-1")
        with open(os.path.join(os.path.dirname(os.path.dirname(files[0])), "project.json"), encoding="utf-8") as f:
            self.assertTrue(json.load(f)["path"])

    def test_truncation_keeps_both_ends(self):
        """With a long paste the instruction sits at one end; cutting only the
        tail could remove the instruction itself."""
        run_hook(self.CMD, json.dumps({"prompt": "START " + "y" * 9000 + " fix the bug above"}), self.dir,
                 extra_env={"INTENT_VERIFY_MAX_PROMPT": "1000"})
        e = read_jsonl(self.dir)[0]
        self.assertTrue(e["truncated"])
        self.assertTrue(e["prompt"].startswith("START "))
        self.assertTrue(e["prompt"].endswith(" fix the bug above"))

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

    def test_records_an_answered_question_as_a_decision(self):
        """An answer to a multiple-choice question is not a prompt, so it was
        missing from the ledger even when it decided the scope of the work."""
        r = run_hook(self.CMD, self._answered({"questions": [self.QUESTION], "answers": {"Ship now or later?": "Later"}}), self.dir)
        self.assertEqual((r.returncode, r.stdout), (0, ""))
        e = read_jsonl(self.dir)[0]
        self.assertEqual((e["kind"], e["session_id"], e["prompt_id"]), ("decision", "A", "p-1"))
        self.assertIn("Q: Ship now or later?", e["prompt"])
        self.assertIn("- Later: next week", e["prompt"])
        self.assertTrue(e["prompt"].endswith("A: Later"))

    def test_an_answer_in_an_unknown_shape_is_kept_as_text(self):
        run_hook(self.CMD, self._answered('Your questions have been answered: "Ship now or later?"="Later"'), self.dir)
        e = read_jsonl(self.dir)[0]
        self.assertEqual(e["kind"], "decision")
        self.assertIn('"Ship now or later?"="Later"', e["prompt"])

    def test_other_tool_results_are_not_recorded(self):
        payload = json.dumps({"hook_event_name": "PostToolUse", "tool_name": "Write", "session_id": "A",
                              "tool_input": {"file_path": "x"}, "tool_response": {}})
        r = run_hook(self.CMD, payload, self.dir)
        self.assertEqual((r.returncode, r.stdout), (0, ""))
        self.assertEqual(read_jsonl(self.dir), [])

    def test_list_is_scoped_to_the_session(self):
        """Several sessions work in one project, so 'the newest task' is often
        somebody else's prompt."""
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

    def test_list_hides_background_agent_reports_and_labels_other_harness_prompts(self):
        """The harness submits prompts of its own. An agent's report is never the
        user's request, in either form it arrives in. A message from another
        session, a scheduled task or a CI event can be what started the work.

        In the session that built 0.3.0, ten of fifteen captured entries were
        subagent hand-backs; listed, they pushed the real request out of view."""
        prompts = ["sort newest first",
                   "<task-notification>\n<task-id>x1</task-id> agent finished",
                   "<agent-message from=\"a1b2\">\n[Subagent hand-back] The text below is the final report\n  hand-back body",
                   "<agent-message from=\"other\">please also add tests",
                   "<ci-monitor-event>1 CI check failed"]
        for p in prompts:
            run_hook(self.CMD, json.dumps({"prompt": p, "session_id": "A"}), self.dir)
        out = self._cli("--list", "--session", "A").stdout
        self.assertNotIn("agent finished", out)
        self.assertNotIn("hand-back body", out)
        self.assertIn("2 background-agent reports hidden", out)
        self.assertIn("please also add tests", out)
        self.assertIn("  agent-message  ", out)
        self.assertIn("  ci-monitor-event  ", out)
        everything = self._cli("--list", "--session", "A", "--all").stdout
        self.assertIn("agent finished", everything)
        self.assertIn("hand-back body", everything)
        self.assertIn("  agent-report  ", everything)

    def test_list_says_where_it_looked_when_it_finds_nothing(self):
        out = self._cli("--list").stdout
        self.assertIn("0 entries", out)
        self.assertIn(data_dir(self.dir), out)

    def test_show_prints_one_request_in_full(self):
        text = "line one\nline two"
        run_hook(self.CMD, json.dumps({"prompt": text, "session_id": "A"}), self.dir)
        r = self._cli("--show", read_jsonl(self.dir)[0]["id"])
        self.assertEqual((r.returncode, r.stdout), (0, text + "\n"))
        self.assertEqual(self._cli("--show", "nope").returncode, 2)

    def test_freeze_writes_the_request_verbatim(self):
        text = "line one\n```py\nx = 1\n```\n  two trailing spaces  "
        run_hook(self.CMD, json.dumps({"prompt": text, "session_id": "A"}), self.dir)
        out = os.path.join(data_dir(self.dir), "frozen", "request.md")
        r = self._cli("--freeze", read_jsonl(self.dir)[0]["id"], "--out", out)
        self.assertEqual(r.returncode, 0, r.stderr)
        meta = json.loads(r.stdout)
        self.assertEqual((meta["file"], meta["truncated"], len(meta["parts"])), (out, False, 1))
        with open(out, encoding="utf-8", newline="") as f:
            self.assertEqual(f.read(), text)
        self.assertEqual(os.listdir(self.dir), [], "freezing must not write inside the project either")

    def test_freeze_joins_a_task_and_the_decision_that_scoped_it(self):
        """One prompt is often not the whole request."""
        run_hook(self.CMD, json.dumps({"prompt": "fix what the review found", "session_id": "A"}), self.dir)
        run_hook(self.CMD, self._answered({"questions": [self.QUESTION], "answers": {"Ship now or later?": "Later"}}), self.dir)
        ids = [e["id"] for e in read_jsonl(self.dir)]
        out = os.path.join(data_dir(self.dir), "request.md")
        r = self._cli("--freeze", ",".join(reversed(ids)), "--out", out)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual([p["kind"] for p in json.loads(r.stdout)["parts"]], ["task", "decision"])
        with open(out, encoding="utf-8") as f:
            text = f.read()
        self.assertLess(text.index("fix what the review found"), text.index("A: Later"))

    def test_freeze_exits_3_for_a_truncated_request(self):
        """An incomplete request must be impossible to miss: verifying against
        it can pass a change that violates the part that was cut off."""
        run_hook(self.CMD, json.dumps({"prompt": "y" * 5000}), self.dir,
                 extra_env={"INTENT_VERIFY_MAX_PROMPT": "1000"})
        r = self._cli("--freeze", read_jsonl(self.dir)[0]["id"], "--out", os.path.join(data_dir(self.dir), "r.md"))
        self.assertEqual(r.returncode, 3)
        self.assertTrue(json.loads(r.stdout)["truncated"])

    def test_freeze_rejects_unknown_ids(self):
        run_hook(self.CMD, json.dumps({"prompt": "a real one"}), self.dir)
        real = read_jsonl(self.dir)[0]["id"]
        for ids in ("nope", "../escape", real + ",nope"):
            self.assertEqual(self._cli("--freeze", ids).returncode, 2, ids)

    def test_reads_a_ledger_left_inside_the_project(self):
        """Requests captured by 0.2.x, or by an alternate hook, stay where they
        are. The reader still finds them and the hook no longer adds to them."""
        legacy = os.path.join(self.dir, ".intent")
        os.makedirs(legacy)
        with open(os.path.join(legacy, "log.jsonl"), "w", encoding="utf-8") as f:
            f.write(json.dumps({"id": "old-1", "ts": "2026-01-01T00:00:00Z", "kind": "task",
                                "prompt": "an older request", "session_id": "A"}) + "\n")
        run_hook(self.CMD, json.dumps({"prompt": "a newer request", "session_id": "A"}), self.dir)
        out = self._cli("--list", "--session", "A").stdout
        self.assertLess(out.index("an older request"), out.index("a newer request"))
        self.assertIn("ledger inside the project", out)
        self.assertEqual(os.listdir(legacy), ["log.jsonl"])
        frozen = os.path.join(data_dir(self.dir), "old.md")
        self.assertEqual(self._cli("--freeze", "old-1", "--out", frozen).returncode, 0)

    def test_stale_session_files_are_deleted(self):
        """Retention replaces rotation: per-session files would otherwise pile up
        for good. Only session files are ever removed."""
        old, recent, note, foreign = self._stale_and_fresh()
        run_hook(self.CMD, json.dumps({"prompt": "anything"}), self.dir)
        self.assertEqual([os.path.exists(p) for p in (old, recent, note, foreign)], [False, True, True, True])

    def test_retention_can_be_switched_off(self):
        old = self._stale_and_fresh()[0]
        run_hook(self.CMD, json.dumps({"prompt": "anything"}), self.dir, extra_env={"INTENT_VERIFY_RETENTION_DAYS": "0"})
        self.assertTrue(os.path.exists(old))

    def _stop(self, agent_type, reply):
        return run_hook(self.CMD, json.dumps({"hook_event_name": "SubagentStop", "agent_type": agent_type,
                                              "agent_id": "a1", "session_id": "A", "last_assistant_message": reply}),
                        self.dir)

    def test_the_verifiers_reply_is_filed_under_its_run_byte_for_byte(self):
        """0.4.0: the hook, not the session that wrote the code, keeps the ledger."""
        r = self._cli("--begin-run", "--session", "A")
        self.assertEqual(r.returncode, 0, r.stderr)
        run = json.loads(r.stdout)
        reply = 'I ran it.\n  {"ledger": 1, "nonce": "%s", "criteria": []}\r\nend — ok\n' % run["nonce"]
        h = self._stop("intent-verify:intent-verifier", reply)
        self.assertEqual((h.returncode, h.stdout), (0, ""), "a SubagentStop hook that prints or fails can keep the verifier running")
        files = glob.glob(os.path.join(run["run"], "reply-*.txt"))
        self.assertEqual(len(files), 1)
        with open(files[0], encoding="utf-8", newline="") as f:
            self.assertEqual(f.read(), reply)

    def test_a_report_handed_back_through_a_tool_call_is_captured(self):
        """The desktop app ends a subagent with a SubagentHandback tool call and
        no final text. 0.4.0 read only last_assistant_message and filed nothing."""
        run = json.loads(self._cli("--begin-run").stdout)
        report = 'checked\n{"ledger": 1, "nonce": "%s", "criteria": []}\n' % run["nonce"]
        transcript = os.path.join(self.dir, "session", "subagents", "agent-a1.jsonl")
        os.makedirs(os.path.dirname(transcript))
        said = lambda content: {"type": "assistant", "message": {"role": "assistant", "content": content}}  # noqa: E731
        with open(transcript, "w", encoding="utf-8") as f:
            for entry in (said([{"type": "text", "text": "Running it."}]),
                          said([{"type": "tool_use", "name": "SubagentHandback", "input": {"message": report}}]),
                          {"type": "user", "message": {"role": "user", "content": [{"type": "tool_result", "content": "ok"}]}}):
                f.write(json.dumps(entry) + "\n")
        named = {"agent_transcript_path": transcript, "last_assistant_message": ""}
        beside_the_session = {"transcript_path": os.path.join(self.dir, "session.jsonl")}
        for where in (named, beside_the_session):
            h = run_hook(self.CMD, json.dumps({"hook_event_name": "SubagentStop", "agent_id": "a1",
                                               "agent_type": "intent-verify:intent-verifier", **where}), self.dir)
            self.assertEqual((h.returncode, h.stdout), (0, ""))
        files = glob.glob(os.path.join(run["run"], "reply-*.txt"))
        self.assertEqual(len(files), 2)
        for path in files:
            with open(path, encoding="utf-8", newline="") as f:
                self.assertEqual(f.read(), report)

    def test_a_stop_with_no_reply_anywhere_leaves_a_note(self):
        """So 'the hook ran and found nothing' can be told from 'it never ran'."""
        h = self._stop("intent-verify:intent-verifier", "")
        self.assertEqual((h.returncode, h.stdout), (0, ""))
        notes = glob.glob(os.path.join(data_dir(self.dir), "projects", "*", "runs", "_unmatched", "empty-*.json"))
        self.assertEqual(len(notes), 1)

    def test_no_other_subagents_reply_is_kept(self):
        run = json.loads(self._cli("--begin-run").stdout)
        for agent in ("intent-verifier", "general-purpose", "other-plugin:intent-verifier"):
            self.assertEqual(self._stop(agent, '{"nonce": "%s"}' % run["nonce"]).returncode, 0)
        self.assertEqual(glob.glob(os.path.join(data_dir(self.dir), "projects", "*", "runs", "*", "reply-*")), [])


class TestPythonHook(HookContract, unittest.TestCase):
    CMD = [sys.executable, os.path.join(HOOKS, "capture-intent.py")]

    def test_rotation(self):
        for i in range(4):
            run_hook(self.CMD, json.dumps({"prompt": "p%d " % i + "z" * 400}), self.dir,
                     extra_env={"INTENT_VERIFY_MAX_LOG": "600"})
        d = os.path.join(self.dir, ".intent")
        rotated = [f for f in os.listdir(d) if f.endswith(".old")]
        self.assertTrue(rotated, "expected rotation archives at tiny INTENT_VERIFY_MAX_LOG")


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
    """With node on PATH the dispatcher hands over to the Node hook, so this is
    the Node hook's behaviour reached through sh."""
    CMD = ["sh", os.path.join(HOOKS, "capture-intent.sh")]
    IN_PROJECT = not shutil.which("node")


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
        key, token = "sk-proj-" + "Ab1_" * 12, "ghp_" + "a" * 36
        self.run_sh(json.dumps({"prompt": "verify this did what I asked"}))
        r = self.run_sh(json.dumps({"prompt": "verify this endpoint returns 404 using %s then %s" % (key, token)}))
        self.assertEqual(r.returncode, 0, r.stderr)
        entries = read_jsonl(self.dir)
        self.assertEqual([e["kind"] for e in entries], ["verify-invocation", "task"])
        # sed here is whatever the platform ships: GNU on Linux, BSD on macOS.
        self.assertEqual(entries[1]["prompt"],
                         "verify this endpoint returns 404 using [REDACTED:api-key] then [REDACTED:github-token]")


if __name__ == "__main__":
    unittest.main()
