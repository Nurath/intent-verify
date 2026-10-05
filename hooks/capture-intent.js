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
 * Hook contract (do not violate):
 *   - NEVER exit non-zero: on UserPromptSubmit, exit 2 would REJECT the user's
 *     prompt, and any other non-zero shows an error notice on every prompt.
 *   - NEVER print to stdout: UserPromptSubmit stdout is injected into Claude's
 *     context.
 *   - Side-effect only. Failures are silent (set INTENT_VERIFY_DEBUG=1 for stderr).
 *
 * Ledger layout (under <project>/.intent/):
 *   log.jsonl   canonical machine ledger, one JSON object per line:
 *               {id, ts, kind, prompt, session_id?, cwd?, transcript_path?,
 *                truncated?, redactions?, reason?}
 *               kind: task | verify-invocation | capture-incomplete
 *   log.md      human-readable mirror (fenced, collision-safe)
 *   .gitignore  "*" -- the directory ignores itself in any repository/worktree
 * Entries are capped (INTENT_VERIFY_MAX_PROMPT, default 64000 chars) and files
 * rotate at INTENT_VERIFY_MAX_LOG bytes (default 1 MiB, keep 3 archives), so the
 * ledger can never grow without bound.
 *
 * Reader commands for the skill's freeze step (these DO print to stdout):
 *   capture-intent.js --list   [--project DIR] [--session ID] [--limit N]
 *   capture-intent.js --freeze ID [--project DIR]
 */
'use strict';

const fs = require('fs');
const path = require('path');

const MAX_PROMPT = intEnv('INTENT_VERIFY_MAX_PROMPT', 64000);
const MAX_LOG = intEnv('INTENT_VERIFY_MAX_LOG', 1024 * 1024);
const MAX_STDIN = 10 * 1024 * 1024;
const KEEP_ARCHIVES = 3;

// Conservative, high-precision credential shapes. Precision over recall: we must
// never mangle ordinary prose, but pasted tokens must not land in a plaintext ledger.
const REDACTIONS = [
  [/-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z0-9 ]*PRIVATE KEY-----/g, '[REDACTED:private-key]'],
  [/\bgithub_pat_[A-Za-z0-9_]{22,}\b/g, '[REDACTED:github-pat]'],
  [/\bgh[pousr]_[A-Za-z0-9]{36,}\b/g, '[REDACTED:github-token]'],
  // sk- family. Prefixed keys (sk-proj-, sk-svcacct-, sk-admin-, sk-ant-api03-,
  // sk-ant-admin01-, ...) have URL-safe bodies that contain "-" and "_"; the
  // bare legacy shape is alphanumeric only. Prefixes are enumerated and a
  // prefixed body must hold a digit AND an uppercase letter, so hyphenated
  // prose ("sk-admin-panel-redesign-with-new-layout") is never touched.
  [/\bsk-(?:(?:proj|svcacct|admin|ant-[a-z]+[0-9]*)-(?=[A-Za-z0-9_-]*[0-9])(?=[A-Za-z0-9_-]*[A-Z])[A-Za-z0-9_-]{20,}|(?:ant-)?[A-Za-z0-9]{20,}\b)/g, '[REDACTED:api-key]'],
  [/\bxox[baprs]-[A-Za-z0-9-]{10,}\b/g, '[REDACTED:slack-token]'],
  [/\bAKIA[0-9A-Z]{16}\b/g, '[REDACTED:aws-key-id]'],
  [/\b(aws_secret_access_key|api[_-]?key|auth[_-]?token|password)\s*[=:]\s*['"]?[A-Za-z0-9+/=_-]{16,}['"]?/gi, '$1=[REDACTED:assigned-secret]'],
  [/\bBearer\s+[A-Za-z0-9._~+/=-]{20,}/g, 'Bearer [REDACTED:bearer]'],
];

// A prompt is tagged verify-invocation only when it is unmistakably a request to
// RUN verification: the slash command, the skill's bare name as the whole prompt,
// or a phrase asking whether the work "did what I asked/wanted". A task that
// merely STARTS like one ("verify this endpoint returns 404", "intent-verify
// should also handle ...") defines work and stays a task. The two mistakes
// are not symmetric: excluding a real request makes the freeze step fall back
// to an older one silently, while keeping an invocation is visible and harmless.
const VERIFY_INVOCATION = /^\s*(?:\/\s*intent-verify(?=[:\s]|$)|intent-verify[\s.!?]*$|verify\s+(?:this|that|it)(?:\s+\w+){0,2}\s+(?:did|does|do)\s+what\s+i\s+(?:asked|wanted)\b|did\s+(?:it|this|that)\s+(?:actually\s+)?do\s+what\s+i\s+(?:asked|wanted)\b|check\s+(?:it|this|that)\s+(?:actually\s+)?did\s+what\s+i\s+(?:asked|wanted)\b|verify\s+(?:this|that|it)[\s.!?]*$)/i;

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
  // collide -- prompts containing ``` or `## `/`---` cannot corrupt entry boundaries.
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

function projectRoot(env, cwdOverride) {
  return env.CLAUDE_PROJECT_DIR || cwdOverride || process.cwd();
}

function ledgerDir(root) {
  const dir = path.join(root, '.intent');
  fs.mkdirSync(dir, { recursive: true });
  // The ledger holds raw prompts and lives inside the user's project. A
  // .gitignore containing "*" makes the directory ignore itself in whatever
  // repository or linked worktree it lands in, so a broad `git add .` cannot
  // stage it. Written once; an existing file is never overwritten.
  const ignore = path.join(dir, '.gitignore');
  if (!fs.existsSync(ignore)) {
    try { fs.writeFileSync(ignore, '*\n', 'utf8'); } catch (e) { debug(`gitignore: ${e.message}`); }
  }
  return dir;
}

function newEntry(kind, payload) {
  const entry = {
    id: `${Date.now().toString(36)}-${Math.random().toString(16).slice(2, 6)}`,
    ts: new Date().toISOString(),
    kind,
    prompt: '',
  };
  for (const k of ['session_id', 'cwd', 'transcript_path']) {
    if (payload && payload[k]) entry[k] = String(payload[k]);
  }
  return entry;
}

function append(root, entry, mdBody) {
  const dir = ledgerDir(root);
  const jsonl = path.join(dir, 'log.jsonl');
  const md = path.join(dir, 'log.md');
  rotate(jsonl);
  rotate(md);
  fs.appendFileSync(jsonl, JSON.stringify(entry) + '\n', 'utf8');
  const fence = fenceFor(mdBody);
  fs.appendFileSync(
    md,
    `## ${entry.ts} · #${entry.id} · ${entry.kind}\n\n${fence}text\n${mdBody}\n${fence}\n\n`,
    'utf8'
  );
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

  const entry = newEntry(VERIFY_INVOCATION.test(prompt) ? 'verify-invocation' : 'task', payload);
  entry.prompt = prompt;
  if (truncated) entry.truncated = true;
  if (count > 0) entry.redactions = count;
  append(projectRoot(env, cwdOverride), entry, prompt);
  return { entry };
}

// The hook input was too large to read in full, so this prompt is NOT in the
// ledger. Say so explicitly: a silent gap would let the freeze step fall back
// to an older task and verify the change against the wrong request.
function markIncomplete(rawInput, env, reason, cwdOverride) {
  const sid = /"session_id"\s*:\s*"([^"]{1,200})"/.exec(rawInput.slice(0, 65536));
  const entry = newEntry('capture-incomplete', sid ? { session_id: sid[1] } : null);
  entry.reason = reason;
  append(projectRoot(env, cwdOverride), entry, `(prompt not captured: ${reason})`);
  return { entry };
}

// ---------------------------------------------------------------- reader side
function readLedger(root) {
  let text;
  try { text = fs.readFileSync(path.join(root, '.intent', 'log.jsonl'), 'utf8'); } catch { return []; }
  const entries = [];
  for (const line of text.split('\n')) {
    if (!line.trim()) continue;
    try { entries.push(JSON.parse(line)); } catch { /* torn line: skip it */ }
  }
  return entries;
}

// One compact line per entry, so a ledger of very long prompts can be scanned
// without loading them. A project ledger is shared by every session that runs
// in that directory; --session narrows it to the caller's own prompts. An empty
// session ('') means the caller asked for scoping but had no id to give: that
// is said out loud, because an unscoped listing looks exactly like a scoped one.
function list(root, session, limit) {
  const all = readLedger(root);
  let rows = all;
  let scope = `${all.length} entries`;
  if (session === '') {
    scope = `session id unavailable -- showing EVERY session (${all.length} total); confirm with the user before using one`;
  } else if (session) {
    const mine = all.filter((e) => e.session_id === session);
    if (mine.length) {
      rows = mine;
      scope = `${mine.length} entries for this session (${all.length} total)`;
    } else {
      scope = `NO entries for session ${session} -- showing other sessions (${all.length} total); confirm with the user before using one`;
    }
  }
  const lines = [`# intent ledger: ${scope}; newest last`];
  for (const e of rows.slice(-limit)) {
    const text = typeof e.prompt === 'string' ? e.prompt : '';
    const flags = [];
    if (e.truncated) flags.push('TRUNCATED');
    if (e.redactions) flags.push(`redactions=${e.redactions}`);
    if (session && e.session_id !== session) flags.push('other-session');
    const head = e.kind === 'capture-incomplete'
      ? `(prompt not captured: ${e.reason || 'unknown'})`
      : JSON.stringify(text.replace(/\s+/g, ' ').trim().slice(0, 100));
    lines.push([e.id, e.ts, e.kind, `${text.length} chars`, flags.join(' '), head].filter(Boolean).join('  '));
  }
  return lines.join('\n') + '\n';
}

// Write one entry's prompt verbatim to .intent/frozen-<id>.md -- the ground
// truth the verifier reads -- and return its metadata, or null if no entry
// with a captured prompt has that id.
function freeze(root, id) {
  if (!/^[A-Za-z0-9_-]{1,64}$/.test(id || '')) return null;  // id becomes a file name
  const e = readLedger(root).find((x) => x.id === id);
  if (!e || typeof e.prompt !== 'string' || e.prompt === '') return null;
  const file = path.join(ledgerDir(root), `frozen-${id}.md`);
  fs.writeFileSync(file, e.prompt, 'utf8');
  return {
    id: e.id,
    ts: e.ts,
    kind: e.kind,
    session_id: e.session_id || null,
    chars: e.prompt.length,
    truncated: !!e.truncated,
    redactions: e.redactions || 0,
    transcript_path: e.transcript_path || null,
    file,
  };
}

function selftest() {
  const os = require('os');
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'intent-verify-selftest-'));
  const env = { CLAUDE_PROJECT_DIR: tmp };
  const results = [];
  const ok = (name, cond) => results.push([name, !!cond]);
  const cap = (prompt, extra) => capture(JSON.stringify(Object.assign({ prompt }, extra)), env);
  let written = 0;

  // Normal capture, with the payload fields the freeze step relies on.
  let r = cap('sort posts by date, newest first', { session_id: 's1', transcript_path: '/t/s1.jsonl' });
  written++;
  const first = r.entry;
  ok('captures-task', first && first.kind === 'task');
  ok('keeps-session-and-transcript', first && first.session_id === 's1' && first.transcript_path === '/t/s1.jsonl');
  ok('ledger-dir-ignores-itself', fs.readFileSync(path.join(tmp, '.intent', '.gitignore'), 'utf8') === '*\n');

  // Classification: only unmistakable requests to RUN verification are tagged.
  const kinds = {
    'verify this did what I asked': 'verify-invocation',
    'verify that it did what I wanted': 'verify-invocation',
    'did it actually do what I wanted?': 'verify-invocation',
    'check this did what I asked': 'verify-invocation',
    '/intent-verify': 'verify-invocation',
    '/intent-verify:intent-verify focus on sorting': 'verify-invocation',
    'verify this.': 'verify-invocation',
    'intent-verify': 'verify-invocation',
    'intent-verify should also handle multi-turn requests': 'task',
    'intent-verify-review.md can you check this review': 'task',
    'verify this endpoint returns 404 for missing users': 'task',
    'verify that the cache invalidates on logout': 'task',
    'add a 404 handler': 'task',
  };
  const wrong = Object.keys(kinds).filter((p) => { written++; return cap(p, { session_id: 's2' }).entry.kind !== kinds[p]; });
  ok('classifies-invocations-narrowly', wrong.length === 0);
  if (wrong.length) process.stdout.write(`  misclassified: ${JSON.stringify(wrong)}\n`);

  // Malformed JSON never throws; a non-string prompt is skipped, not logged.
  ok('survives-bad-json', capture('{nope', env).skipped === 'unparseable-input');
  ok('skips-null-prompt', capture(JSON.stringify({ prompt: null }), env).skipped === 'no-prompt');

  // Redaction: token shapes go, hyphenated prose stays.
  const shapes = {
    github: 'ghp_' + 'a'.repeat(36),
    legacy: 'sk-' + 'A1b2'.repeat(8),
    project: 'sk-proj-' + 'Ab1_'.repeat(12),
    anthropic: 'sk-ant-api03-' + 'Ab1-'.repeat(20) + 'AA',
  };
  const leaked = Object.keys(shapes).filter((k) => {
    written++;
    const e = cap(`use ${shapes[k]} for auth`).entry;
    return e.prompt.includes(shapes[k]) || e.redactions !== 1;
  });
  ok('redacts-token-shapes', leaked.length === 0);
  if (leaked.length) process.stdout.write(`  not redacted: ${JSON.stringify(leaked)}\n`);
  written++;
  const prose = 'rename sk-admin-panel-redesign-with-new-layout and the sk-learn-compatible-estimator';
  r = cap(prose);
  ok('leaves-hyphenated-prose-alone', r.entry.prompt === prose && !r.entry.redactions);

  // Truncation is recorded on the entry.
  r = cap('x'.repeat(MAX_PROMPT + 500), { session_id: 's1' });
  written++;
  const big = r.entry;
  ok('truncates-huge-prompt', big && big.truncated === true && big.prompt.length < MAX_PROMPT + 100);

  // Fence collision safety.
  r = cap('code:\n```py\nprint(1)\n```\n---\n## fake heading');
  written++;
  ok('fence-collision-safe', r.entry && fenceFor(r.entry.prompt).length >= 4);

  // An unreadable oversized input leaves an explicit marker, never a silent gap.
  r = markIncomplete('{"session_id":"s1","prompt":"xxxx', env, 'hook input exceeded the size cap');
  written++;
  ok('marks-incomplete-capture', r.entry.kind === 'capture-incomplete' && r.entry.session_id === 's1' && r.entry.prompt === '');

  // JSONL parses back, and nothing skipped was logged.
  const lines = fs.readFileSync(path.join(tmp, '.intent', 'log.jsonl'), 'utf8').trim().split('\n');
  ok('jsonl-roundtrips', lines.every((l) => { try { JSON.parse(l); return true; } catch { return false; } }));
  ok('jsonl-count', lines.length === written);

  // Reader side: session-scoped listing, and freeze writes the prompt verbatim.
  const listing = list(tmp, 's1', 10);
  ok('list-scopes-to-session', listing.includes(first.id) && listing.includes('TRUNCATED') &&
     listing.includes('capture-incomplete') && !listing.includes('404 handler'));
  ok('list-flags-unknown-session', list(tmp, 'nope', 3).includes('NO entries for session nope'));
  ok('list-flags-missing-session-id', list(tmp, '', 3).includes('session id unavailable'));
  let meta = freeze(tmp, first.id);
  ok('freeze-writes-verbatim', meta && !meta.truncated && fs.readFileSync(meta.file, 'utf8') === first.prompt);
  meta = freeze(tmp, big.id);
  ok('freeze-reports-truncation', meta && meta.truncated === true);
  ok('freeze-rejects-unknown-or-unsafe-id', freeze(tmp, 'nope') === null && freeze(tmp, '../x') === null);

  let pass = 0;
  for (const [name, good] of results) {
    process.stdout.write(`${good ? 'PASS' : 'FAIL'} ${name}\n`);
    if (good) pass++;
  }
  try { fs.rmSync(tmp, { recursive: true, force: true }); } catch {}
  process.stdout.write(`${pass}/${results.length} selftests passed\n`);
  process.exit(pass === results.length ? 0 : 1);
}

function arg(name) {
  const i = process.argv.indexOf(name);
  return i !== -1 && i + 1 < process.argv.length ? process.argv[i + 1] : null;
}

if (require.main === module) {
  const argv = process.argv;
  if (argv.includes('--selftest')) {
    selftest();
  } else if (argv.includes('--list')) {
    const limit = parseInt(arg('--limit'), 10);
    const root = arg('--project') || projectRoot(process.env);
    const session = argv.includes('--session') ? (arg('--session') || '') : null;
    process.stdout.write(list(root, session, Number.isFinite(limit) && limit > 0 ? limit : 10));
    process.exit(0);
  } else if (argv.includes('--freeze')) {
    const id = arg('--freeze');
    const meta = freeze(arg('--project') || projectRoot(process.env), id);
    if (!meta) {
      process.stderr.write(`capture-intent: no ledger entry with a captured prompt has id "${id}"\n`);
      process.exit(2);
    }
    process.stdout.write(JSON.stringify(meta, null, 2) + '\n');
    if (meta.truncated) {
      process.stderr.write('capture-intent: this request was TRUNCATED at capture; the frozen file is incomplete. ' +
        'Recover the full text before any MATCHES INTENT verdict.\n');
    }
    process.exit(meta.truncated ? 3 : 0);
  } else {
    // Hook mode. Bound memory WITHOUT pausing the stream: a paused stream never
    // emits 'end', so the capture+exit path would never run. Stop accumulating
    // but keep draining to EOF, and remember that input was dropped.
    let raw = '';
    let overflow = false;
    process.stdin.setEncoding('utf8');
    process.stdin.on('data', (c) => { if (raw.length <= MAX_STDIN) raw += c; else overflow = true; });
    process.stdin.on('end', () => {
      try {
        const r = capture(raw, process.env);
        if (overflow && r.skipped === 'unparseable-input') {
          markIncomplete(raw, process.env, `hook input exceeded ${MAX_STDIN} characters`);
        }
      } catch (e) { debug(e.message); }
      process.exit(0);
    });
    process.stdin.on('error', () => process.exit(0));
  }
}

module.exports = { capture, markIncomplete, applyRedactions, fenceFor, list, freeze, VERIFY_INVOCATION };
