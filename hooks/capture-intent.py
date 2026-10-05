#!/usr/bin/env python3
"""intent-verify UserPromptSubmit hook — Python alternate.

Reads the hook JSON payload on stdin and appends the prompt to the intent
ledger (.intent/log.jsonl + log.md). Mirrors capture-intent.js (canonical):
redaction, truncation, rotation, verify-invocation tagging, a ledger directory
that ignores itself, and an explicit marker when the input was too large to
read. The reader commands (--list / --freeze) exist only in the canonical script.

Contract: side-effect only; always exits 0; never writes stdout.
Invoked by capture-intent.sh when node is unavailable, or directly:
  { "type": "command", "command": "python3", "args": ["${CLAUDE_PLUGIN_ROOT}/hooks/capture-intent.py"] }
"""
import json
import os
import re
import sys
import time

MAX_STDIN = 10 * 1024 * 1024

# Keep in sync with capture-intent.js (canonical); the reasoning lives there.
REDACT = [
    (r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z0-9 ]*PRIVATE KEY-----", "[REDACTED:private-key]"),
    (r"\bgithub_pat_[A-Za-z0-9_]{22,}\b", "[REDACTED:github-pat]"),
    (r"\bgh[pousr]_[A-Za-z0-9]{36,}\b", "[REDACTED:github-token]"),
    (r"\bsk-(?:(?:proj|svcacct|admin|ant-[a-z]+[0-9]*)-(?=[A-Za-z0-9_-]*[0-9])(?=[A-Za-z0-9_-]*[A-Z])[A-Za-z0-9_-]{20,}"
     r"|(?:ant-)?[A-Za-z0-9]{20,}\b)", "[REDACTED:api-key]"),
    (r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b", "[REDACTED:slack-token]"),
    (r"\bAKIA[0-9A-Z]{16}\b", "[REDACTED:aws-key-id]"),
    (r"(?i)\b(aws_secret_access_key|api[_-]?key|auth[_-]?token|password)\s*[=:]\s*['\"]?[A-Za-z0-9+/=_-]{16,}['\"]?", r"\1=[REDACTED:assigned-secret]"),
    (r"\bBearer\s+[A-Za-z0-9._~+/=-]{20,}", "Bearer [REDACTED:bearer]"),
]
VERIFY_INVOCATION = re.compile(
    r"^\s*(?:/\s*intent-verify(?=[:\s]|$)|intent-verify[\s.!?]*$"
    r"|verify\s+(?:this|that|it)(?:\s+\w+){0,2}\s+(?:did|does|do)\s+what\s+i\s+(?:asked|wanted)\b"
    r"|did\s+(?:it|this|that)\s+(?:actually\s+)?do\s+what\s+i\s+(?:asked|wanted)\b"
    r"|check\s+(?:it|this|that)\s+(?:actually\s+)?did\s+what\s+i\s+(?:asked|wanted)\b"
    r"|verify\s+(?:this|that|it)[\s.!?]*$)", re.I)


def int_env(name, default):
    try:
        v = int(os.environ.get(name, ""))
    except ValueError:
        return default
    return v if v > 0 else default


def rotate(path, cap):
    try:
        if os.path.getsize(path) > cap:
            stamp = time.strftime("%Y-%m-%dT%H-%M-%SZ", time.gmtime())
            os.replace(path, "%s.%s.old" % (path, stamp))
            d, base = os.path.dirname(path), os.path.basename(path)
            old = sorted(f for f in os.listdir(d) if f.startswith(base + ".") and f.endswith(".old"))
            while len(old) > 3:
                os.unlink(os.path.join(d, old.pop(0)))
    except OSError:
        pass


def ledger_dir():
    d = os.path.join(os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd(), ".intent")
    os.makedirs(d, exist_ok=True)
    # Raw prompts live inside the user's project. A .gitignore holding "*" makes
    # the directory ignore itself in any repository or worktree, so a broad
    # `git add .` cannot stage it. Written once; never overwritten.
    ignore = os.path.join(d, ".gitignore")
    if not os.path.exists(ignore):
        try:
            with open(ignore, "w", encoding="utf-8", newline="\n") as f:
                f.write("*\n")
        except OSError:
            pass
    return d


def new_entry(kind, payload):
    entry = {
        "id": "%x-%04x" % (int(time.time() * 1000), os.getpid() % 0xFFFF),
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "kind": kind,
        "prompt": "",
    }
    for k in ("session_id", "cwd", "transcript_path"):
        if payload.get(k):
            entry[k] = str(payload[k])
    return entry


def append(entry, body):
    d = ledger_dir()
    cap = int_env("INTENT_VERIFY_MAX_LOG", 1024 * 1024)
    jsonl, md = os.path.join(d, "log.jsonl"), os.path.join(d, "log.md")
    rotate(jsonl, cap)
    rotate(md, cap)
    with open(jsonl, "a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    runs = re.findall(r"`+", body)
    fence = "`" * max(3, (max(len(r) for r in runs) + 1) if runs else 3)
    with open(md, "a", encoding="utf-8", newline="\n") as f:
        f.write("## %s · #%s · %s\n\n%stext\n%s\n%s\n\n" % (entry["ts"], entry["id"], entry["kind"], fence, body, fence))


def main():
    # Bytes, decoded as UTF-8: text-mode stdin uses the locale codepage on
    # Windows and would mangle every non-ASCII prompt.
    data = sys.stdin.buffer.read(MAX_STDIN + 1)
    while len(data) > MAX_STDIN and sys.stdin.buffer.read(1 << 20):
        pass  # drain: closing early would break the writer's pipe mid-prompt
    raw = data.decode("utf-8", "replace")
    try:
        payload = json.loads(raw)
    except ValueError:
        if len(data) > MAX_STDIN:
            # Too large to read in full, so this prompt is NOT in the ledger. Say
            # so: a silent gap lets the freeze step fall back to an older task.
            sid = re.search(r'"session_id"\s*:\s*"([^"]{1,200})"', raw[:65536])
            entry = new_entry("capture-incomplete", {"session_id": sid.group(1)} if sid else {})
            entry["reason"] = "hook input exceeded %d bytes" % MAX_STDIN
            append(entry, "(prompt not captured: %s)" % entry["reason"])
        return
    if not isinstance(payload, dict):
        return
    prompt = payload.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip():
        return

    redactions = 0
    for pat, sub in REDACT:
        prompt, k = re.subn(pat, sub, prompt)
        redactions += k

    max_len = int_env("INTENT_VERIFY_MAX_PROMPT", 64000)
    truncated = len(prompt) > max_len
    if truncated:
        dropped = len(prompt) - max_len
        prompt = prompt[:max_len] + "\n…[truncated %d chars]" % dropped

    entry = new_entry("verify-invocation" if VERIFY_INVOCATION.match(prompt) else "task", payload)
    entry["prompt"] = prompt
    if truncated:
        entry["truncated"] = True
    if redactions:
        entry["redactions"] = redactions
    append(entry, prompt)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
