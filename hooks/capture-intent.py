#!/usr/bin/env python3
"""intent-verify UserPromptSubmit hook — Python alternate.

Reads the hook JSON payload on stdin, appends the prompt to the intent ledger
(.intent/log.jsonl + log.md). Same behavior as capture-intent.js (canonical):
redaction, truncation, rotation, verify-invocation tagging.

Contract: side-effect only; always exits 0; never writes stdout.
Invoked by capture-intent.sh when node is unavailable, or directly:
  { "type": "command", "command": "python3", "args": ["${CLAUDE_PLUGIN_ROOT}/hooks/capture-intent.py"] }
"""
import json
import os
import re
import sys
import time

REDACT = [
    (r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z0-9 ]*PRIVATE KEY-----", "[REDACTED:private-key]"),
    (r"\bgithub_pat_[A-Za-z0-9_]{22,}\b", "[REDACTED:github-pat]"),
    (r"\bgh[pousr]_[A-Za-z0-9]{36,}\b", "[REDACTED:github-token]"),
    (r"\bsk-(?:ant-)?[A-Za-z0-9]{20,}\b", "[REDACTED:api-key]"),
    (r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b", "[REDACTED:slack-token]"),
    (r"\bAKIA[0-9A-Z]{16}\b", "[REDACTED:aws-key-id]"),
    (r"(?i)\b(aws_secret_access_key|api[_-]?key|auth[_-]?token|password)\s*[=:]\s*['\"]?[A-Za-z0-9+/=_-]{16,}['\"]?", r"\1=[REDACTED:assigned-secret]"),
    (r"\bBearer\s+[A-Za-z0-9._~+/=-]{20,}", "Bearer [REDACTED:bearer]"),
]
VERIFY_INVOCATION = re.compile(
    r"^\s*(/?\s*intent-verify\b|verify\s+(this|that|it)\b|"
    r"did\s+(it|this|that)\s+(actually\s+)?do\s+what\s+i\s+(asked|wanted)|"
    r"check\s+(it|this)\s+did\s+what\s+i\s+asked)", re.I)


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


def main():
    try:
        raw = sys.stdin.read(10 * 1024 * 1024)
        payload = json.loads(raw)
    except Exception:
        return
    prompt = payload.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip():
        return

    redactions = 0
    for pat, sub in REDACT:
        prompt, k = re.subn(pat, sub, prompt)
        redactions += k

    try:
        max_len = int(os.environ.get("INTENT_VERIFY_MAX_PROMPT", "16000"))
    except ValueError:
        max_len = 16000
    truncated = len(prompt) > max_len
    if truncated:
        dropped = len(prompt) - max_len
        prompt = prompt[:max_len] + "\n…[truncated %d chars]" % dropped

    root = os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    d = os.path.join(root, ".intent")
    os.makedirs(d, exist_ok=True)

    entry = {
        "id": "%x-%04x" % (int(time.time() * 1000), os.getpid() % 0xFFFF),
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "kind": "verify-invocation" if VERIFY_INVOCATION.match(prompt) else "task",
        "prompt": prompt,
    }
    if payload.get("session_id"):
        entry["session_id"] = str(payload["session_id"])
    if payload.get("cwd"):
        entry["cwd"] = str(payload["cwd"])
    if truncated:
        entry["truncated"] = True
    if redactions:
        entry["redactions"] = redactions

    try:
        cap = int(os.environ.get("INTENT_VERIFY_MAX_LOG", str(1024 * 1024)))
    except ValueError:
        cap = 1024 * 1024
    jsonl, md = os.path.join(d, "log.jsonl"), os.path.join(d, "log.md")
    rotate(jsonl, cap)
    rotate(md, cap)
    with open(jsonl, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    runs = re.findall(r"`+", prompt)
    fence = "`" * max(3, (max(len(r) for r in runs) + 1) if runs else 3)
    with open(md, "a", encoding="utf-8") as f:
        f.write("## %s · #%s · %s\n\n%stext\n%s\n%s\n\n" % (entry["ts"], entry["id"], entry["kind"], fence, prompt, fence))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
