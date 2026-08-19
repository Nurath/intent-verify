#!/usr/bin/env node
/**
 * intent-verify UserPromptSubmit hook (canonical, cross-platform).
 *
 * Freezes the user's request verbatim to the intent ledger so verification can
 * check work against the ORIGINAL ask, not the diff's self-description.
 *
 * Invoked in exec form from hooks/hooks.json:
 *   { "command": "node", "args": ["${CLAUDE_PLUGIN_ROOT}/hooks/capture-intent.js"] }
 * This is the documented cross-platform pattern (node is a real executable on
 * every platform; no shell is involved, so no sh-on-Windows breakage).
 *
 * Contract (do not violate):
 *   - NEVER exit non-zero: on UserPromptSubmit, exit 2 would REJECT the user's
 *     prompt, and any other non-zero shows an error notice on every prompt.
 *   - NEVER print to stdout on success: UserPromptSubmit stdout is injected
 *     into Claude's context.
 *   - Side-effect only. Failures are silent (set INTENT_VERIFY_DEBUG=1 for stderr).
 *
 * Ledger layout (under <project>/.intent/):
 *   log.jsonl  — canonical machine ledger, one JSON object per line:
 *                {id, ts, session_id?, cwd?, kind, prompt, truncated?, redactions?}
 *   log.md     — human-readable mirror (fenced, collision-safe)
 * Entries are capped (INTENT_VERIFY_MAX_PROMPT, default 16000 chars) and files
 * rotate at INTENT_VERIFY_MAX_LOG bytes (default 1 MiB, keep 3 archives), so the
 * ledger can never grow without bound or blow up a verifier's context window.
 */
'use strict';

const fs = require('fs');
const path = require('path');

const MAX_PROMPT = intEnv('INTENT_VERIFY_MAX_PROMPT', 16000);
const MAX_LOG = intEnv('INTENT_VERIFY_MAX_LOG', 1024 * 1024);
const KEEP_ARCHIVES = 3;

// Conservative, high-precision credential shapes. Precision over recall: we must
// never mangle ordinary prose, but pasted tokens must not land in a plaintext ledger.
const REDACTIONS = [
  [/-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z0-9 ]*PRIVATE KEY-----/g, '[REDACTED:private-key]'],
  [/\bgithub_pat_[A-Za-z0-9_]{22,}\b/g, '[REDACTED:github-pat]'],
  [/\bgh[pousr]_[A-Za-z0-9]{36,}\b/g, '[REDACTED:github-token]'],
  [/\bsk-(?:ant-)?[A-Za-z0-9]{20,}\b/g, '[REDACTED:api-key]'],
  [/\bxox[baprs]-[A-Za-z0-9-]{10,}\b/g, '[REDACTED:slack-token]'],
  [/\bAKIA[0-9A-Z]{16}\b/g, '[REDACTED:aws-key-id]'],
  [/\b(aws_secret_access_key|api[_-]?key|auth[_-]?token|password)\s*[=:]\s*['"]?[A-Za-z0-9+/=_-]{16,}['"]?/gi, '$1=[REDACTED:assigned-secret]'],
  [/\bBearer\s+[A-Za-z0-9._~+/=-]{20,}/g, 'Bearer [REDACTED:bearer]'],
];

// Prompts that INVOKE verification are captured but tagged, so the freeze step
// can tell the task-defining ask apart from "verify this did what I asked".
const VERIFY_INVOCATION = /^\s*(\/?\s*intent-verify\b|verify\s+(this|that|it)\b|did\s+(it|this|that)\s+(actually\s+)?do\s+what\s+i\s+(asked|wanted)|check\s+(it|this)\s+did\s+what\s+i\s+asked)/i;

function intEnv(name, dflt) {
  const v = parseInt(process.env[name], 10);
  return Number.isFinite(v) && v > 0 ? v : dflt;
}

function debug(msg) {
  if (process.env.INTENT_VERIFY_DEBUG === '1') process.stderr.write(`capture-intent: ${msg}\n`);
}

function applyRedactions(text) {
  let count = 0;
  for (const [re, sub] of REDACTIONS) {
    text = text.replace(re, (...m) => {
      count++;
      return sub.includes('$1') ? sub.replace('$1', m[1]) : sub;
    });
  }
  return { text, count };
}

function fenceFor(text) {
  // A fence one backtick longer than the longest run inside the prompt can never
  // collide — prompts containing ``` or `## `/`---` cannot corrupt entry boundaries.
  const runs = text.match(/`+/g) || [];
  const longest = runs.reduce((a, r) => Math.max(a, r.length), 0);
  return '`'.repeat(Math.max(3, longest + 1));
}

function rotate(file) {
  try {
    const st = fs.statSync(file);
    if (st.size <= MAX_LOG) return;
    const stamp = new Date().toISOString().replace(/[:.]/g, '-');
    fs.renameSync(file, `${file}.${stamp}.old`);
    const dir = path.dirname(file);
    const base = path.basename(file);
    const archives = fs.readdirSync(dir)
      .filter((f) => f.startsWith(base + '.') && f.endsWith('.old'))
      .sort();
    while (archives.length > KEEP_ARCHIVES) {
      fs.unlinkSync(path.join(dir, archives.shift()));
    }
  } catch (e) { debug(`rotate: ${e.message}`); }
}

function capture(rawInput, env, cwdOverride) {
  let payload;
  try { payload = JSON.parse(rawInput); } catch { return { skipped: 'unparseable-input' }; }
  let prompt = payload && payload.prompt;
  if (typeof prompt !== 'string' || prompt.trim() === '') return { skipped: 'no-prompt' };

  const { text, count } = applyRedactions(prompt);
  prompt = text;

  let truncated = false;
  if (prompt.length > MAX_PROMPT) {
    const dropped = prompt.length - MAX_PROMPT;
    prompt = prompt.slice(0, MAX_PROMPT) + `\n…[truncated ${dropped} chars]`;
    truncated = true;
  }

  const root = env.CLAUDE_PROJECT_DIR || cwdOverride || process.cwd();
  const dir = path.join(root, '.intent');
  fs.mkdirSync(dir, { recursive: true });

  const entry = {
    id: `${Date.now().toString(36)}-${Math.random().toString(16).slice(2, 6)}`,
    ts: new Date().toISOString(),
    kind: VERIFY_INVOCATION.test(prompt) ? 'verify-invocation' : 'task',
    prompt,
  };
  if (payload.session_id) entry.session_id = String(payload.session_id);
  if (payload.cwd) entry.cwd = String(payload.cwd);
  if (truncated) entry.truncated = true;
  if (count > 0) entry.redactions = count;

  const jsonl = path.join(dir, 'log.jsonl');
  const md = path.join(dir, 'log.md');
  rotate(jsonl);
  rotate(md);
  fs.appendFileSync(jsonl, JSON.stringify(entry) + '\n', 'utf8');
  const fence = fenceFor(prompt);
  fs.appendFileSync(
    md,
    `## ${entry.ts} · #${entry.id} · ${entry.kind}\n\n${fence}text\n${prompt}\n${fence}\n\n`,
    'utf8'
  );
  return { entry };
}

function selftest() {
  const os = require('os');
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'intent-verify-selftest-'));
  const env = { CLAUDE_PROJECT_DIR: tmp };
  const results = [];
  const ok = (name, cond) => results.push([name, !!cond]);

  // 1. Normal capture.
  let r = capture(JSON.stringify({ prompt: 'sort posts by date, newest first', session_id: 's1' }), env);
  ok('captures-task', r.entry && r.entry.kind === 'task');
  // 2. Verify-invocation tagging.
  r = capture(JSON.stringify({ prompt: 'verify this did what I asked' }), env);
  ok('tags-verify-invocation', r.entry && r.entry.kind === 'verify-invocation');
  // 3. Malformed JSON never throws.
  r = capture('{nope', env);
  ok('survives-bad-json', r.skipped === 'unparseable-input');
  // 4. Non-string prompt (null) is skipped — not logged as "None"/"null".
  r = capture(JSON.stringify({ prompt: null }), env);
  ok('skips-null-prompt', r.skipped === 'no-prompt');
  // 5. Redaction.
  r = capture(JSON.stringify({ prompt: 'use token ghp_' + 'a'.repeat(36) + ' for auth' }), env);
  ok('redacts-github-token', r.entry && r.entry.prompt.includes('[REDACTED:github-token]') && r.entry.redactions === 1);
  // 6. Truncation.
  r = capture(JSON.stringify({ prompt: 'x'.repeat(MAX_PROMPT + 500) }), env);
  ok('truncates-huge-prompt', r.entry && r.entry.truncated === true && r.entry.prompt.length < MAX_PROMPT + 100);
  // 7. Fence collision safety.
  r = capture(JSON.stringify({ prompt: 'code:\n```py\nprint(1)\n```\n---\n## fake heading' }), env);
  ok('fence-collision-safe', r.entry && fenceFor(r.entry.prompt).length >= 4);
  // 8. JSONL parses back.
  const lines = fs.readFileSync(path.join(tmp, '.intent', 'log.jsonl'), 'utf8').trim().split('\n');
  ok('jsonl-roundtrips', lines.every((l) => { try { JSON.parse(l); return true; } catch { return false; } }));
  ok('jsonl-count', lines.length === 5); // entries 1,2,5,6,7 (3,4 skipped)

  let pass = 0;
  for (const [name, good] of results) {
    process.stdout.write(`${good ? 'PASS' : 'FAIL'} ${name}\n`);
    if (good) pass++;
  }
  try { fs.rmSync(tmp, { recursive: true, force: true }); } catch {}
  process.stdout.write(`${pass}/${results.length} selftests passed\n`);
  process.exit(pass === results.length ? 0 : 1);
}

if (require.main === module) {
  if (process.argv.includes('--selftest')) {
    selftest();
  } else {
    const MAX_STDIN = 10 * 1024 * 1024;
    let raw = '';
    process.stdin.setEncoding('utf8');
    // Bound memory WITHOUT pausing: a paused stream never emits 'end', so the
    // capture+exit path would never run and we'd depend on the event loop
    // happening to drain (silently dropping the prompt, or hanging if anything
    // else kept the loop alive). Stop accumulating but keep draining to EOF.
    process.stdin.on('data', (c) => { if (raw.length <= MAX_STDIN) raw += c; });
    process.stdin.on('end', () => {
      try { capture(raw, process.env); } catch (e) { debug(e.message); }
      process.exit(0);
    });
    process.stdin.on('error', () => process.exit(0));
  }
}

module.exports = { capture, applyRedactions, fenceFor };
