# Platform spikes for 0.3 (2026-10-05)

0.3 leans on Claude Code behaviours that its documentation describes. This is
what has, and has not, been observed on a real installation (Windows 11, Claude
Code 2.1.287). The numbering follows `docs/DESIGN-v0.3.md`.

Most of the spikes need a model call from a fresh session that has the new
plugin loaded. On the day, the `claude` CLI on the machine was logged out, and a
running session does not pick up newly added agents or hooks, so several could
not be run. They are marked as such and not assumed.

| Spike | Question | Result |
|---|---|---|
| S5, hook half | Does a plugin hook receive the data directory, and what does `UserPromptSubmit` carry? | **Seen.** A probe plugin loaded with `--plugin-dir` got `CLAUDE_PLUGIN_ROOT`, `CLAUDE_PLUGIN_DATA` (`~/.claude/plugins/data/<id>`) and `CLAUDE_PROJECT_DIR` in its environment, and `${CLAUDE_PLUGIN_DATA}` in the hook's `args` was substituted. Payload keys: `cwd`, `hook_event_name`, `permission_mode`, `prompt`, `prompt_id`, `session_id`, `transcript_path`. A slash command arrives as typed (`/plugin:skill`). The session id is not in the hook's environment, only in the payload. |
| S5, skill half | Is `${CLAUDE_PLUGIN_DATA}` substituted in skill text? | **Seen** (later run, below). Invoking the installed skill from the desktop app rendered `${CLAUDE_PLUGIN_ROOT}`, `${CLAUDE_PLUGIN_DATA}`, `${CLAUDE_PROJECT_DIR}` and `${CLAUDE_SESSION_ID}` as real absolute paths and ids, with forward slashes on Windows. The project directory is the one the session started in. The reader's fallback for an empty `--data` stays. |
| S1 | Does an agent whose allowlist names only inert tools launch, with no way to read files? | **Seen** (later run, below). The installed `intent-criteria` agent launched and returned a manifest. Asked to list its tools, it named `TaskStop` and `SubagentHandback` (which the harness gives every subagent) and said none could read a file or run a command. `TodoWrite`, the other tool in its allowlist, does not exist in this version; the agent launches while at least one listed tool does. The run used about 14k tokens. |
| S4 | Does `PostToolUse` fire for `AskUserQuestion`, carrying the answer? | **Seen** (later run, below). Two questions answered in one call in the desktop app produced one `decision` entry holding both questions, every option with its description, and both answers. The answer's shape had first been taken from a real session transcript, `{questions, answers: {<question>: <label>}}`; the hook keeps an answer in any other shape as text. |
| S7 | Can prompts the harness submits be told from typed ones? | **Seen in our own ledgers.** Of 706 captured entries, 85 began `<task-notification>`, 16 `<agent-message>`, 2 `<system-reminder>` and 1 `<scheduled-task>`; a later session also showed `<ci-monitor-event>`. |
| S2, S3 | `SubagentStop` payload, and block-to-retry | Not run. Nothing in 0.3.0 depends on them; they gate Change C. |
| S6 | Can a subagent read a file under the data directory without a prompt? | Not needed. The request is handed to subagents inline. |

One more thing was observed that no spike asked about: the harness delivers a
background subagent's report with two spaces in front of every line. A valid
ledger copied from that message was rejected by the 0.2.1 validator ("no
CRITERION blocks found"). 0.3.0 removes an indent shared by every line.

## Later the same day

After a restart with 0.3.1 installed (Claude Code 2.1.289), S1, S4 and the
skill half of S5 were run from the desktop app; the table above has the
results. The restarted session's hook was already writing to the plugin data
directory. All three were seen once, on one Windows machine.
