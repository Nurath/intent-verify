# intent-verify UserPromptSubmit hook - Windows PowerShell alternate.
#
# The plugin's default hook is hooks/capture-intent.js invoked in exec form
# ("command": "node", "args": [...]), which works on every platform. Use THIS
# script only if you wire hooks manually on Windows without Node, e.g.:
#   { "type": "command", "command": "powershell.exe",
#     "args": ["-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
#              "${CLAUDE_PLUGIN_ROOT}\\hooks\\capture-intent.ps1"] }
#
# Compatible with Windows PowerShell 5.1 (preinstalled everywhere) AND pwsh 7+.
# stdin is decoded as UTF-8 explicitly ([Console]::In on 5.1 would use the OEM
# codepage and mangle non-ASCII prompts) and the ledger is written as UTF-8.
#
# Writes the 0.2 layout inside the project (<project>/.intent/), a directory
# that ignores itself in git. The plugin's own hook has written outside the
# project since 0.3. This alternate was not moved, and the reader in
# capture-intent.js still reads what it writes.
#
# Contract: side-effect only; ALWAYS exits 0; never writes stdout.
$ErrorActionPreference = 'SilentlyContinue'
try {
    $utf8 = New-Object System.Text.UTF8Encoding($false)
    $reader = New-Object System.IO.StreamReader([Console]::OpenStandardInput(), $utf8)
    $raw = $reader.ReadToEnd()
    if ([string]::IsNullOrEmpty($raw)) { exit 0 }
    try { $payload = $raw | ConvertFrom-Json } catch { exit 0 }
    $prompt = $payload.prompt
    if ($null -eq $prompt -or -not ($prompt -is [string]) -or [string]::IsNullOrWhiteSpace($prompt)) { exit 0 }

    # Redact obvious credential shapes (precision over recall). Keep in sync
    # with capture-intent.js (canonical).
    $redactions = 0
    $rules = @(
        @('-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z0-9 ]*PRIVATE KEY-----', '[REDACTED:private-key]'),
        @('\bgithub_pat_[A-Za-z0-9_]{22,}\b', '[REDACTED:github-pat]'),
        @('\bgh[pousr]_[A-Za-z0-9]{36,}\b', '[REDACTED:github-token]'),
        @('\bsk-(?:(?:proj|svcacct|admin|ant-[a-z]+[0-9]*)-(?=[A-Za-z0-9_-]*[0-9])(?=[A-Za-z0-9_-]*[A-Z])[A-Za-z0-9_-]{20,}|(?:ant-)?[A-Za-z0-9]{20,}\b)', '[REDACTED:api-key]'),
        @('\bxox[baprs]-[A-Za-z0-9-]{10,}\b', '[REDACTED:slack-token]'),
        @('\bAKIA[0-9A-Z]{16}\b', '[REDACTED:aws-key-id]'),
        @('(?i)\b(aws_secret_access_key|api[_-]?key|auth[_-]?token|password)\s*[=:]\s*[''"]?[A-Za-z0-9+/=_-]{16,}[''"]?', '$1=[REDACTED:assigned-secret]'),
        @('\bBearer\s+[A-Za-z0-9._~+/=-]{20,}', 'Bearer [REDACTED:bearer]')
    )
    foreach ($rule in $rules) {
        $rx = [regex]$rule[0]
        $m = $rx.Matches($prompt)
        if ($m.Count -gt 0) { $redactions += $m.Count; $prompt = $rx.Replace($prompt, $rule[1]) }
    }

    # Truncate oversized prompts so the ledger cannot blow up a context window.
    $maxLen = 64000
    if ($env:INTENT_VERIFY_MAX_PROMPT -match '^\d{1,9}$') { $maxLen = [int]$env:INTENT_VERIFY_MAX_PROMPT }
    $truncated = $false
    if ($prompt.Length -gt $maxLen) {
        $dropped = $prompt.Length - $maxLen
        $prompt = $prompt.Substring(0, $maxLen) + "`n...[truncated $dropped chars]"
        $truncated = $true
    }

    $root = if ($env:CLAUDE_PROJECT_DIR) { $env:CLAUDE_PROJECT_DIR } else { (Get-Location).Path }
    $dir = Join-Path $root '.intent'
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
    # Raw prompts live inside the user's project. A .gitignore holding "*" makes
    # the directory ignore itself in any repository or worktree, so a broad
    # 'git add .' cannot stage it. Written once; never overwritten.
    $ignore = Join-Path $dir '.gitignore'
    if (-not (Test-Path $ignore)) { [System.IO.File]::WriteAllText($ignore, "*`n", $utf8) }

    $ts = (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')
    $id = '{0:x}-{1:x4}' -f [int64]((Get-Date).ToUniversalTime() - (Get-Date '1970-01-01')).TotalMilliseconds, ($PID -band 0xFFFF)
    $kind = 'task'
    # Only an unmistakable request to RUN verification is tagged; a task that merely
    # starts with "verify this ..." stays a task. Keep in sync with capture-intent.js.
    if ($prompt -match '^\s*(?:/\s*intent-verify(?=[:\s]|$)|intent-verify[\s.!?]*$|verify\s+(?:this|that|it)(?:\s+\w+){0,2}\s+(?:did|does|do)\s+what\s+i\s+(?:asked|wanted)\b|did\s+(?:it|this|that)\s+(?:actually\s+)?do\s+what\s+i\s+(?:asked|wanted)\b|check\s+(?:it|this|that)\s+(?:actually\s+)?did\s+what\s+i\s+(?:asked|wanted)\b|verify\s+(?:this|that|it)[\s.!?]*$)') { $kind = 'verify-invocation' }

    $entry = [ordered]@{ id = $id; ts = $ts; kind = $kind; prompt = $prompt }
    if ($payload.session_id) { $entry.session_id = [string]$payload.session_id }
    if ($payload.cwd) { $entry.cwd = [string]$payload.cwd }
    if ($payload.transcript_path) { $entry.transcript_path = [string]$payload.transcript_path }
    if ($truncated) { $entry.truncated = $true }
    if ($redactions -gt 0) { $entry.redactions = $redactions }

    $cap = [int64]1048576
    if ($env:INTENT_VERIFY_MAX_LOG -match '^\d{1,15}$') { $cap = [int64]$env:INTENT_VERIFY_MAX_LOG }
    $jsonl = Join-Path $dir 'log.jsonl'
    $md = Join-Path $dir 'log.md'
    foreach ($f in @($jsonl, $md)) {
        if ((Test-Path $f) -and ((Get-Item $f).Length -gt $cap)) {
            $stamp = $ts -replace ':', '-'
            Move-Item -Force $f "$f.$stamp.old"
        }
        # keep at most 3 rotation archives per file
        $base = Split-Path $f -Leaf
        $old = @(Get-ChildItem -Path $dir -Filter "$base.*.old" | Sort-Object Name)
        while ($old.Count -gt 3) { Remove-Item -Force $old[0].FullName; $old = $old[1..($old.Count - 1)] }
    }

    $dot = [string][char]0xB7
    [System.IO.File]::AppendAllText($jsonl, (($entry | ConvertTo-Json -Compress -Depth 4) + "`n"), $utf8)
    $fenceLen = 3
    $runs = [regex]::Matches($prompt, '`+')
    foreach ($r in $runs) { if ($r.Length + 1 -gt $fenceLen) { $fenceLen = $r.Length + 1 } }
    $fence = '`' * $fenceLen
    [System.IO.File]::AppendAllText($md, "## $ts $dot #$id $dot $kind`n`n${fence}text`n$prompt`n$fence`n`n", $utf8)
}
catch { }
exit 0
