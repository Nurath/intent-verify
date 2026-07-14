#!/bin/sh
# intent-verify UserPromptSubmit hook.
# Freezes the user's request verbatim to .intent/log.md so verification can check
# work against the ORIGINAL ask, not the diff's self-description. Side-effect only;
# never blocks or errors the prompt.
input=$(cat 2>/dev/null)
root="${CLAUDE_PROJECT_DIR:-.}"
dir="$root/.intent"
mkdir -p "$dir" 2>/dev/null || exit 0

# Extract the prompt from the hook JSON (python is ubiquitous; fall back to raw).
prompt=$(printf '%s' "$input" | python -c "import sys,json
try: print(json.load(sys.stdin).get('prompt',''))
except Exception: pass" 2>/dev/null)
[ -z "$prompt" ] && exit 0

ts=$(date -u +%Y-%m-%dT%H:%M:%SZ 2>/dev/null)
printf '## %s\n\n%s\n\n---\n\n' "$ts" "$prompt" >> "$dir/log.md" 2>/dev/null
exit 0
