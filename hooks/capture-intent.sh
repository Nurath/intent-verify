#!/bin/sh
# intent-verify UserPromptSubmit hook — POSIX alternate.
#
# The plugin's default hook is hooks/capture-intent.js invoked in exec form
# ("command": "node", "args": [...]) because that is the documented
# cross-platform pattern. Use THIS script only if you wire hooks manually in
# settings.json on macOS/Linux/Git-Bash and prefer a shell entry point:
#   { "type": "command", "command": "sh \"$CLAUDE_PLUGIN_ROOT/hooks/capture-intent.sh\"" }
#
# Contract: side-effect only. ALWAYS exits 0 (non-zero would surface an error
# notice on every prompt; exit 2 would REJECT the prompt). Never writes stdout
# (UserPromptSubmit stdout is injected into Claude's context).
#
# Delegation order: node (canonical implementation — single source of truth for
# redaction/truncation/rotation) -> python3 -> python -> jq (extract+encode)
# -> markdown-only last resort. The old script hard-required a bare `python`,
# which no longer exists on stock Ubuntu/Debian/macOS, so capture silently
# failed on the most common dev platforms.

input=$(cat 2>/dev/null) || exit 0
[ -n "$input" ] || exit 0
self_dir=$(dirname "$0")

# 1) Canonical path: reuse the js implementation verbatim.
if command -v node >/dev/null 2>&1; then
    printf '%s' "$input" | node "$self_dir/capture-intent.js" 2>/dev/null
    exit 0
fi

root="${CLAUDE_PROJECT_DIR:-.}"
dir="$root/.intent"
mkdir -p "$dir" 2>/dev/null || exit 0
max_prompt="${INTENT_VERIFY_MAX_PROMPT:-16000}"
ts=$(date -u +%Y-%m-%dT%H:%M:%SZ 2>/dev/null)
id="$(date +%s 2>/dev/null)-$$"

# 2) Python path (python3 first — bare `python` is legacy-only).
PY=""
if command -v python3 >/dev/null 2>&1; then PY=python3
elif command -v python >/dev/null 2>&1; then PY=python
fi
if [ -n "$PY" ] && [ -f "$self_dir/capture-intent.py" ]; then
    printf '%s' "$input" | "$PY" "$self_dir/capture-intent.py" 2>/dev/null
    exit 0
fi

# Shared degraded-path helpers: redact the highest-risk shapes with sed,
# truncate the WHOLE prompt with head -c, rotate at the size cap. Degraded
# paths keep the bounded-ledger guarantees; only the redaction list is shorter.
max_log="${INTENT_VERIFY_MAX_LOG:-1048576}"
redact_sed() {
    sed -E \
        -e 's/\bgithub_pat_[A-Za-z0-9_]{22,}/[REDACTED:github-pat]/g' \
        -e 's/\bgh[pousr]_[A-Za-z0-9]{36,}/[REDACTED:github-token]/g' \
        -e 's/\bsk-(ant-)?[A-Za-z0-9]{20,}/[REDACTED:api-key]/g' \
        -e 's/\bxox[baprs]-[A-Za-z0-9-]{10,}/[REDACTED:slack-token]/g' \
        -e 's/\bAKIA[0-9A-Z]{16}/[REDACTED:aws-key-id]/g' 2>/dev/null || cat
}
rotate_at_cap() {
    for f in "$dir/log.jsonl" "$dir/log.md"; do
        [ -f "$f" ] || continue
        sz=$(wc -c < "$f" 2>/dev/null || echo 0)
        [ "$sz" -gt "$max_log" ] 2>/dev/null && mv -f "$f" "$f.$(printf '%s' "$ts" | tr ':' '-').old" 2>/dev/null
    done
    return 0
}

# 3) jq path: extract AND JSON-encode safely (no hand-rolled escaping).
if command -v jq >/dev/null 2>&1; then
    prompt=$(printf '%s' "$input" | jq -r '.prompt // empty | if type == "string" then . else empty end' 2>/dev/null)
    [ -n "$prompt" ] || exit 0
    prompt=$(printf '%s' "$prompt" | redact_sed | head -c "$max_prompt")
    rotate_at_cap
    enc=$(printf '%s' "$prompt" | jq -Rs .) || exit 0
    printf '{"id":"%s","ts":"%s","kind":"task","prompt":%s}\n' "$id" "$ts" "$enc" >> "$dir/log.jsonl" 2>/dev/null
    # shellcheck disable=SC2016  # literal backtick fence, not an expansion
    printf '## %s · #%s · task\n\n````text\n%s\n````\n\n' "$ts" "$id" "$prompt" >> "$dir/log.md" 2>/dev/null
    exit 0
fi

# 4) Last resort: markdown-only, fenced (no JSON tooling available).
input=$(printf '%s' "$input" | redact_sed | head -c "$max_prompt")
rotate_at_cap
# shellcheck disable=SC2016  # literal backtick fence, not an expansion
printf '## %s · #%s · task (raw hook payload; no JSON parser on PATH)\n\n````text\n%s\n````\n\n' "$ts" "$id" "$input" >> "$dir/log.md" 2>/dev/null
exit 0
