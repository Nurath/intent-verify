# intent-verify UserPromptSubmit hook (Windows).
# Freezes the user's request verbatim to .intent/log.md so verification can check
# work against the ORIGINAL ask. Side-effect only; must never block or error.
$ErrorActionPreference = 'SilentlyContinue'
try {
    $raw = [Console]::In.ReadToEnd()
    $prompt = ($raw | ConvertFrom-Json).prompt
    if ([string]::IsNullOrWhiteSpace($prompt)) { exit 0 }

    $root = if ($env:CLAUDE_PROJECT_DIR) { $env:CLAUDE_PROJECT_DIR } else { '.' }
    $dir = Join-Path $root '.intent'
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
    $ts = (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')
    Add-Content -Path (Join-Path $dir 'log.md') -Value "## $ts`n`n$prompt`n`n---`n"
}
catch { }
exit 0
