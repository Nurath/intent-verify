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
| S5, skill half | Is `${CLAUDE_PLUGIN_DATA}` substituted in skill text? | **Not run.** The reader therefore does not depend on it: with an empty `--data` it looks where Claude Code keeps this plugin's data. |
| S1 | Does an agent whose allowlist names only inert tools launch, with no way to read files? | **Not run.** If `intent-criteria` cannot be dispatched, the skill writes the criteria itself and has to say so in its report. |
| S4 | Does `PostToolUse` fire for `AskUserQuestion`, carrying the answer? | **Not run live.** The answer's shape was taken from a real session transcript — `{questions, answers: {<question>: <label>}}` — and from the documented tool input. The hook keeps an answer in any other shape as text. |
| S7 | Can prompts the harness submits be told from typed ones? | **Seen in our own ledgers.** Of 706 captured entries, 85 began `<task-notification>`, 16 `<agent-message>`, 2 `<system-reminder>` and 1 `<scheduled-task>`; a later session also showed `<ci-monitor-event>`. |
| S2, S3 | `SubagentStop` payload, and block-to-retry | Not run. Nothing in 0.3.0 depends on them; they gate Change C. |
| S6 | Can a subagent read a file under the data directory without a prompt? | Not needed. The request is handed to subagents inline. |

One more thing was observed that no spike asked about: the harness delivers a
background subagent's report with two spaces in front of every line. A valid
ledger copied from that message was rejected by the 0.2.1 validator ("no
CRITERION blocks found"). 0.3.0 removes an indent shared by every line.

## Finishing the three that are open

Each takes a minute in the first session started after 0.3.0 is installed:

- **S1:** ask for the `intent-verify:intent-criteria` agent to be run on any
  one-line request. It should start, and when asked it should report no tool
  that reads files or runs commands.
- **S4:** answer any multiple-choice question in a session, then run the
  skill's `--list` command. A `decision` entry with the question and the answer
  should be there.
- **S5, skill half:** invoke the skill and look at the first command it runs.
  `--data` should be followed by a real path.
