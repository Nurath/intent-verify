#!/usr/bin/env node
/**
 * intent-verify capture hook and ledger reader (canonical, cross-platform).
 *
 * Records what the user asked for, verbatim, so verification can check work
 * against the ORIGINAL ask and not the diff's description of itself.
 *
 * Hook mode. Registered in hooks/hooks.json in exec form
 *   { "command": "node", "args": ["${CLAUDE_PLUGIN_ROOT}/hooks/capture-intent.js"] }
 * (node is a real executable on every platform; no shell is involved) for:
 *   UserPromptSubmit              the prompt, before any work happens
 *   PostToolUse AskUserQuestion   the question and the user's answer: a scope
 *                                 decision that is not a prompt and would
 *                                 otherwise be missing from the record
 *
 * Hook contract (do not violate):
 *   - NEVER exit non-zero: on UserPromptSubmit, exit 2 would REJECT the user's
 *     prompt, and any other non-zero shows an error notice on every prompt.
 *   - NEVER print to stdout: UserPromptSubmit stdout is injected into Claude's
 *     context.
 *   - Side-effect only. Failures are silent (set INTENT_VERIFY_DEBUG=1 for stderr).
 *
 * Where it writes: OUTSIDE the project, so prompts never sit in a repository.
 *   <data>/projects/<key>/project.json             {"path": "<project dir>"}
 *   <data>/projects/<key>/sessions/<session>.jsonl one JSON object per line:
 *       {id, ts, kind, prompt, session_id?, prompt_id?, cwd?, transcript_path?,
 *        truncated?, redactions?, reason?}
 *       kind: task | verify-invocation | decision | capture-incomplete
 *   <data> = $INTENT_VERIFY_DATA, else $CLAUDE_PLUGIN_DATA (Claude Code sets it
 *            for plugin hooks), else ~/.claude/intent-verify
 *   <key>  = first 16 hex digits of sha256(normalised project path)
 * One file per session, so "this session's requests" is a file and not a filter.
 * Session files untouched for INTENT_VERIFY_RETENTION_DAYS (default 30; 0 keeps
 * everything) are deleted. An entry is capped at INTENT_VERIFY_MAX_PROMPT
 * characters (default 256000); a longer prompt keeps its start and its end.
 *
 * Reader commands for the skill's freeze step (these DO print to stdout):
 *   capture-intent.js --list   [--session ID] [--limit N] [--all]
 *   capture-intent.js --show ID
 *   capture-intent.js --freeze ID[,ID...] [--out FILE]
 * each with [--project DIR] [--data DIR]. The reader also reads a ledger left
 * in <project>/.intent/ by 0.2.x or by one of the alternate hooks.
 */
'use strict';

const crypto = require('crypto');
const fs = require('fs');
const os = require('os');
const path = require('path');

const MAX_PROMPT = intEnv('INTENT_VERIFY_MAX_PROMPT', 256000);
const RETENTION_DAYS = intEnv('INTENT_VERIFY_RETENTION_DAYS', 30, true);
const MAX_STDIN = 10 * 1024 * 1024;
const DAY_MS = 24 * 60 * 60 * 1000;

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

// Prompts the harness submits by itself: a background agent reporting back, a
// message from another session or agent, a scheduled task firing, a CI event
// from the desktop app. Recognised when the ledger is READ, so entries written
// by any version or runtime are covered.
const HARNESS_SOURCE = /^\s*<(task-notification|agent-message|scheduled-task|ci-monitor-event)[\s>]/;

function intEnv(name, dflt, allowZero) {
  const v = parseInt(process.env[name], 10);
  return Number.isFinite(v) && (v > 0 || (allowZero && v === 0)) ? v : dflt;
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

// A prompt over the cap keeps its start AND its end: with a long paste the
// instruction sits at one end, and cutting only the tail could remove it.
function capLength(text) {
  if (text.length <= MAX_PROMPT) return { text, truncated: false };
  const half = Math.max(1, Math.floor(MAX_PROMPT / 2));
  const dropped = text.length - 2 * half;
  return {
    text: `${text.slice(0, half)}\n…[truncated ${dropped} chars from the middle]…\n${text.slice(-half)}`,
    truncated: true,
  };
}

// ------------------------------------------------------------------- storage
function projectRoot(env, cwdOverride) {
  return env.CLAUDE_PROJECT_DIR || cwdOverride || process.cwd();
}

function writeRoot(env) {
  return env.INTENT_VERIFY_DATA || env.CLAUDE_PLUGIN_DATA || path.join(os.homedir(), '.claude', 'intent-verify');
}

function normalizeProject(dir) {
  const p = path.resolve(dir).replace(/\\/g, '/').replace(/\/+$/, '') || '/';
  return process.platform === 'win32' ? p.toLowerCase() : p;
}

function projectKey(dir) {
  return crypto.createHash('sha256').update(normalizeProject(dir)).digest('hex').slice(0, 16);
}

function sessionFile(root, project, sessionId) {
  const name = String(sessionId || '_nosession').replace(/[^A-Za-z0-9_-]/g, '_').slice(0, 80);
  return path.join(root, 'projects', projectKey(project), 'sessions', `${name}.jsonl`);
}

function append(root, project, entry) {
  const file = sessionFile(root, project, entry.session_id);
  fs.mkdirSync(path.dirname(file), { recursive: true });
  const meta = path.join(path.dirname(path.dirname(file)), 'project.json');
  if (!fs.existsSync(meta)) {
    try { fs.writeFileSync(meta, JSON.stringify({ path: normalizeProject(project) }) + '\n', 'utf8'); } catch (e) { debug(`project.json: ${e.message}`); }
  }
  fs.appendFileSync(file, JSON.stringify(entry) + '\n', 'utf8');
  prune(root);
}

// Retention replaces rotation. At most once a day, delete session files nobody
// has written to for RETENTION_DAYS. Only *.jsonl files directly inside the
// sessions directory of a project this hook created (it has our project.json)
// are ever removed.
function prune(root, now) {
  if (!RETENTION_DAYS) return 0;
  now = now || Date.now();
  const stamp = path.join(root, '.pruned');
  try { if (now - fs.statSync(stamp).mtimeMs < DAY_MS) return 0; } catch { /* never pruned */ }
  let removed = 0;
  try {
    fs.writeFileSync(stamp, new Date(now).toISOString() + '\n', 'utf8');
    for (const key of fs.readdirSync(path.join(root, 'projects'))) {
      if (!fs.existsSync(path.join(root, 'projects', key, 'project.json'))) continue;
      const sessions = path.join(root, 'projects', key, 'sessions');
      let names = [];
      try { names = fs.readdirSync(sessions); } catch { continue; }
      for (const name of names) {
        if (!name.endsWith('.jsonl')) continue;
        const file = path.join(sessions, name);
        try {
          if (now - fs.statSync(file).mtimeMs > RETENTION_DAYS * DAY_MS) { fs.unlinkSync(file); removed++; }
        } catch (e) { debug(`prune: ${e.message}`); }
      }
    }
  } catch (e) { debug(`prune: ${e.message}`); }
  return removed;
}

// -------------------------------------------------------------------- capture
function newEntry(kind, payload) {
  const entry = {
    id: `${Date.now().toString(36)}-${Math.random().toString(16).slice(2, 6)}`,
    ts: new Date().toISOString(),
    kind,
    prompt: '',
  };
  for (const k of ['session_id', 'prompt_id', 'cwd', 'transcript_path']) {
    if (payload && payload[k]) entry[k] = String(payload[k]);
  }
  return entry;
}

function store(kind, payload, text, env, cwdOverride) {
  const red = applyRedactions(text);
  const cut = capLength(red.text);
  const entry = newEntry(kind || (VERIFY_INVOCATION.test(cut.text) ? 'verify-invocation' : 'task'), payload);
  entry.prompt = cut.text;
  if (cut.truncated) entry.truncated = true;
  if (red.count > 0) entry.redactions = red.count;
  append(writeRoot(env), projectRoot(env, cwdOverride), entry);
  return { entry };
}

function capture(rawInput, env, cwdOverride) {
  let payload;
  try { payload = JSON.parse(rawInput); } catch { return { skipped: 'unparseable-input' }; }
  if (payload && payload.hook_event_name === 'PostToolUse') return captureDecision(payload, env, cwdOverride);
  const prompt = payload && payload.prompt;
  if (typeof prompt !== 'string' || prompt.trim() === '') return { skipped: 'no-prompt' };
  return store(null, payload, prompt, env, cwdOverride);
}

// AskUserQuestion. Its result is {questions, answers: {<question text>: <chosen
// label>}} -- the shape recorded in session transcripts -- and the documented
// tool input may carry the same `answers` map. Anything else is kept as text.
function captureDecision(payload, env, cwdOverride) {
  if (payload.tool_name !== 'AskUserQuestion') return { skipped: 'not-a-decision' };
  const input = payload.tool_input && typeof payload.tool_input === 'object' ? payload.tool_input : {};
  const resp = payload.tool_response;
  const obj = resp && typeof resp === 'object' ? resp : {};
  const answers = [obj.answers, input.answers].find((a) => a && typeof a === 'object') || null;
  const questions = [input.questions, obj.questions].find(Array.isArray) || [];
  const blocks = [];
  for (const q of questions) {
    if (!q || typeof q.question !== 'string') continue;
    const lines = [`Q: ${q.question}`];
    for (const o of Array.isArray(q.options) ? q.options : []) {
      if (o && o.label) lines.push(`  - ${o.label}${o.description ? `: ${o.description}` : ''}`);
    }
    lines.push(`A: ${answers && answers[q.question] !== undefined ? String(answers[q.question]) : '(not recorded)'}`);
    blocks.push(lines.join('\n'));
  }
  if (!blocks.length) return { skipped: 'no-questions' };
  if (!answers && resp !== undefined && resp !== null) {
    blocks.push(`Result as returned: ${(typeof resp === 'string' ? resp : JSON.stringify(resp)).slice(0, 2000)}`);
  }
  return store('decision', payload, blocks.join('\n\n'), env, cwdOverride);
}

// The hook input was too large to read in full, so this prompt is NOT in the
// ledger. Say so explicitly: a silent gap would let the freeze step fall back
// to an older task and verify the change against the wrong request.
function markIncomplete(rawInput, env, reason, cwdOverride) {
  const sid = /"session_id"\s*:\s*"([^"]{1,200})"/.exec(rawInput.slice(0, 65536));
  const entry = newEntry('capture-incomplete', sid ? { session_id: sid[1] } : null);
  entry.reason = reason;
  append(writeRoot(env), projectRoot(env, cwdOverride), entry);
  return { entry };
}

// ---------------------------------------------------------------- reader side
// Where a ledger can be. The skill passes --data; the rest is for a caller
// that could not (its skill text arrived without the path substituted), so it
// also looks where Claude Code keeps this plugin's data.
function readRoots(explicit, env) {
  if (explicit) return [explicit];
  if (env.INTENT_VERIFY_DATA) return [env.INTENT_VERIFY_DATA];
  const roots = env.CLAUDE_PLUGIN_DATA ? [env.CLAUDE_PLUGIN_DATA] : [];
  const pluginData = path.join(os.homedir(), '.claude', 'plugins', 'data');
  try {
    for (const name of fs.readdirSync(pluginData)) {
      if (name.startsWith('intent-verify')) roots.push(path.join(pluginData, name));
    }
  } catch { /* no plugin data directory */ }
  roots.push(path.join(os.homedir(), '.claude', 'intent-verify'));
  return [...new Set(roots)];
}

function readJsonl(file) {
  let text;
  try { text = fs.readFileSync(file, 'utf8'); } catch { return []; }
  const entries = [];
  for (const line of text.split('\n')) {
    if (!line.trim()) continue;
    try { entries.push(JSON.parse(line)); } catch { /* torn line: skip it */ }
  }
  return entries;
}

// Every entry recorded for this project, oldest first: one file per session
// under each data root, plus a ledger still sitting in the project itself.
function readProject(roots, project) {
  const entries = [];
  const seen = new Set();
  const take = (e, legacy) => {
    if (!e || typeof e.id !== 'string' || seen.has(e.id)) return;
    seen.add(e.id);
    entries.push(legacy ? Object.assign({ legacy: true }, e) : e);
  };
  for (const root of roots) {
    const dir = path.join(root, 'projects', projectKey(project), 'sessions');
    let names = [];
    try { names = fs.readdirSync(dir).filter((n) => n.endsWith('.jsonl')).sort(); } catch { continue; }
    for (const name of names) readJsonl(path.join(dir, name)).forEach((e) => take(e, false));
  }
  readJsonl(path.join(project, '.intent', 'log.jsonl')).forEach((e) => take(e, true));
  return entries.sort((a, b) => (String(a.ts) < String(b.ts) ? -1 : String(a.ts) > String(b.ts) ? 1 : 0));
}

function sourceOf(entry) {
  const m = HARNESS_SOURCE.exec(typeof entry.prompt === 'string' ? entry.prompt : '');
  return m ? m[1] : null;
}

// One compact line per entry, so long prompts can be scanned without loading
// them. session: an id narrows the listing to that session; '' means the
// caller asked for scoping but had no id to give, which is said out loud
// because an unscoped listing looks exactly like a scoped one.
function list(roots, project, session, limit, all) {
  const everything = readProject(roots, project);
  let rows = everything;
  let scope = `${everything.length} entries`;
  if (session === '') {
    scope = `session id unavailable -- showing EVERY session (${everything.length} total); confirm with the user before using one`;
  } else if (session) {
    const mine = everything.filter((e) => e.session_id === session);
    if (mine.length) {
      rows = mine;
      scope = `${mine.length} entries for this session (${everything.length} total)`;
    } else {
      scope = `NO entries for session ${session} -- showing other sessions (${everything.length} total); confirm with the user before using one`;
    }
  }
  // A background agent reporting back is submitted as a prompt too. It is never
  // the user's request, so it is left out unless asked for.
  const reports = rows.filter((e) => sourceOf(e) === 'task-notification').length;
  if (!all) rows = rows.filter((e) => sourceOf(e) !== 'task-notification');
  const lines = [`# intent ledger: ${scope}; newest last` +
    (reports && !all ? `; ${reports} background-agent reports hidden (--all shows them)` : '')];
  if (!everything.length) {
    lines.push(`# looked in: ${roots.concat(path.join(project, '.intent')).join(' ; ')}`);
  }
  if (everything.some((e) => e.legacy)) {
    lines.push(`# includes a ledger inside the project (${path.join(project, '.intent')}), written by 0.2.x or an alternate hook; ` +
      'the plugin hook no longer writes there. Delete that directory once its requests are no longer needed.');
  }
  for (const e of rows.slice(-limit)) {
    const text = typeof e.prompt === 'string' ? e.prompt : '';
    const flags = [];
    if (e.truncated) flags.push('TRUNCATED');
    if (e.redactions) flags.push(`redactions=${e.redactions}`);
    if (session && e.session_id !== session) flags.push('other-session');
    if (sourceOf(e)) flags.push(sourceOf(e));
    const head = e.kind === 'capture-incomplete'
      ? `(prompt not captured: ${e.reason || 'unknown'})`
      : JSON.stringify(text.replace(/\s+/g, ' ').trim().slice(0, 100));
    lines.push([e.id, e.ts, e.kind, `${text.length} chars`, flags.join(' '), head].filter(Boolean).join('  '));
  }
  return lines.join('\n') + '\n';
}

const SAFE_ID = /^[A-Za-z0-9_-]{1,64}$/;

// Write the chosen entries to one file -- the ground truth handed to the
// verifier -- and describe it. One id gives that prompt verbatim. Several are
// joined oldest first, each under a line saying what it is: a request is often
// a task plus a later answer or correction. Returns null for an unknown id.
function freeze(roots, project, ids, out) {
  if (!ids.length || !ids.every((id) => SAFE_ID.test(id))) return null;
  const parts = readProject(roots, project).filter((e) => ids.includes(e.id));
  if (parts.length !== new Set(ids).size || parts.some((e) => typeof e.prompt !== 'string' || e.prompt === '')) return null;
  const text = parts.length === 1
    ? parts[0].prompt
    : parts.map((e, i) => `===== part ${i + 1} of ${parts.length}: ${e.kind}, ${e.ts} =====\n${e.prompt}`).join('\n\n') + '\n';
  const file = out || path.join(fs.mkdtempSync(path.join(os.tmpdir(), 'intent-verify-')), 'request.md');
  fs.mkdirSync(path.dirname(path.resolve(file)), { recursive: true });
  fs.writeFileSync(file, text, 'utf8');
  return {
    file,
    chars: text.length,
    truncated: parts.some((e) => !!e.truncated),
    parts: parts.map((e) => ({
      id: e.id,
      ts: e.ts,
      kind: e.kind,
      session_id: e.session_id || null,
      chars: e.prompt.length,
      truncated: !!e.truncated,
      redactions: e.redactions || 0,
      transcript_path: e.transcript_path || null,
    })),
  };
}

function selftest() {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'intent-verify-selftest-'));
  const project = path.join(tmp, 'project');
  const data = path.join(tmp, 'data');
  fs.mkdirSync(project);
  const env = { CLAUDE_PROJECT_DIR: project, INTENT_VERIFY_DATA: data };
  const roots = [data];
  const results = [];
  const ok = (name, cond) => results.push([name, !!cond]);
  const cap = (prompt, extra) => capture(JSON.stringify(Object.assign({ prompt }, extra)), env);

  // Normal capture, with the payload fields the freeze step relies on.
  let r = cap('sort posts by date, newest first', { session_id: 's1', prompt_id: 'p1', transcript_path: '/t/s1.jsonl' });
  const first = r.entry;
  ok('captures-task', first && first.kind === 'task');
  ok('keeps-session-prompt-id-and-transcript', first && first.session_id === 's1' && first.prompt_id === 'p1' && first.transcript_path === '/t/s1.jsonl');
  ok('writes-one-file-per-session-outside-the-project',
    fs.existsSync(sessionFile(data, project, 's1')) && fs.readdirSync(project).length === 0);

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
  const wrong = Object.keys(kinds).filter((p) => cap(p, { session_id: 's2' }).entry.kind !== kinds[p]);
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
    const e = cap(`use ${shapes[k]} for auth`).entry;
    return e.prompt.includes(shapes[k]) || e.redactions !== 1;
  });
  ok('redacts-token-shapes', leaked.length === 0);
  if (leaked.length) process.stdout.write(`  not redacted: ${JSON.stringify(leaked)}\n`);
  const prose = 'rename sk-admin-panel-redesign-with-new-layout and the sk-learn-compatible-estimator';
  r = cap(prose);
  ok('leaves-hyphenated-prose-alone', r.entry.prompt === prose && !r.entry.redactions);

  // A prompt over the cap is flagged and keeps both ends.
  const big = cap('HEAD' + 'x'.repeat(MAX_PROMPT + 500) + 'TAIL', { session_id: 's1' }).entry;
  ok('truncation-keeps-both-ends', big.truncated === true && big.prompt.startsWith('HEAD') &&
     big.prompt.endsWith('TAIL') && big.prompt.length < MAX_PROMPT + 100);

  // An unreadable oversized input leaves an explicit marker, never a silent gap.
  r = markIncomplete('{"session_id":"s1","prompt":"xxxx', env, 'hook input exceeded the size cap');
  ok('marks-incomplete-capture', r.entry.kind === 'capture-incomplete' && r.entry.session_id === 's1' && r.entry.prompt === '');

  // An answered question is a decision; other tool results are not recorded.
  const question = { question: 'Ship now or later?', header: 'Ship', options: [{ label: 'Now', description: 'today' }, { label: 'Later', description: 'next week' }] };
  const asked = { hook_event_name: 'PostToolUse', tool_name: 'AskUserQuestion', session_id: 's1', prompt_id: 'p1', tool_input: { questions: [question] } };
  const decision = capture(JSON.stringify(Object.assign({ tool_response: { questions: [question], answers: { 'Ship now or later?': 'Later' } } }, asked)), env).entry;
  ok('records-an-answered-question', decision && decision.kind === 'decision' && decision.prompt_id === 'p1' &&
     decision.prompt.includes('Q: Ship now or later?') && decision.prompt.includes('- Later: next week') && decision.prompt.endsWith('A: Later'));
  r = capture(JSON.stringify(Object.assign({ tool_response: 'answered: Later' }, asked)), env);
  ok('keeps-an-unrecognised-answer-as-text', r.entry.prompt.includes('A: (not recorded)') && r.entry.prompt.includes('Result as returned: answered: Later'));
  ok('ignores-other-tools', capture(JSON.stringify({ hook_event_name: 'PostToolUse', tool_name: 'Write', tool_input: {} }), env).skipped === 'not-a-decision');

  // Reader: session scoping, hidden agent reports, a ledger left in the project.
  cap('<task-notification>\n<task-id>abc</task-id> agent finished', { session_id: 's1' });
  let listing = list(roots, project, 's1', 20, false);
  ok('list-scopes-to-session', listing.includes(first.id) && listing.includes('TRUNCATED') &&
     listing.includes('capture-incomplete') && listing.includes('decision') && !listing.includes('404 handler'));
  ok('list-hides-agent-reports', !listing.includes('agent finished') && listing.includes('1 background-agent reports hidden') &&
     list(roots, project, 's1', 20, true).includes('agent finished'));
  ok('list-flags-unknown-session', list(roots, project, 'nope', 3, false).includes('NO entries for session nope'));
  ok('list-flags-missing-session-id', list(roots, project, '', 3, false).includes('session id unavailable'));
  ok('list-says-where-it-looked', list(roots, path.join(tmp, 'elsewhere'), 's1', 3, false).includes('# looked in: '));
  fs.mkdirSync(path.join(project, '.intent'));
  fs.writeFileSync(path.join(project, '.intent', 'log.jsonl'),
    JSON.stringify({ id: 'old-1', ts: '2026-01-01T00:00:00Z', kind: 'task', prompt: 'an older request', session_id: 's1' }) + '\n');
  listing = list(roots, project, 's1', 20, false);
  ok('list-reads-a-ledger-left-in-the-project', listing.includes('an older request') && listing.includes('includes a ledger inside the project'));

  // Freeze: one entry verbatim, several joined oldest first, problems reported.
  let meta = freeze(roots, project, [first.id], path.join(tmp, 'one.md'));
  ok('freeze-writes-verbatim', meta && !meta.truncated && fs.readFileSync(meta.file, 'utf8') === first.prompt);
  meta = freeze(roots, project, [decision.id, first.id], path.join(tmp, 'set.md'));
  const joined = meta ? fs.readFileSync(meta.file, 'utf8') : '';
  ok('freeze-joins-a-set-oldest-first', meta && meta.parts.length === 2 && meta.parts[0].id === first.id &&
     joined.indexOf(first.prompt) !== -1 && joined.indexOf(first.prompt) < joined.indexOf('Q: Ship now or later?'));
  meta = freeze(roots, project, [first.id, big.id], path.join(tmp, 'cut.md'));
  ok('freeze-reports-truncation', meta && meta.truncated === true);
  ok('freeze-rejects-unknown-or-unsafe-id', freeze(roots, project, ['nope']) === null && freeze(roots, project, ['../x']) === null &&
     freeze(roots, project, [first.id, 'nope']) === null);
  ok('freeze-leaves-the-project-alone', JSON.stringify(fs.readdirSync(project)) === '[".intent"]' &&
     fs.readdirSync(path.join(project, '.intent')).length === 1);

  // Retention: only stale session files go.
  const sessions = path.dirname(sessionFile(data, project, 's1'));
  const stale = path.join(sessions, 'stale.jsonl');
  const keepMe = path.join(sessions, 'notes.txt');
  const foreign = path.join(data, 'projects', 'not-ours', 'sessions', 'old.jsonl');
  fs.mkdirSync(path.dirname(foreign), { recursive: true });
  for (const f of [stale, foreign]) fs.writeFileSync(f, '{}\n');
  fs.writeFileSync(keepMe, 'not a session file\n');
  const longAgo = new Date(Date.now() - 40 * DAY_MS);
  for (const f of [stale, keepMe, foreign]) fs.utimesSync(f, longAgo, longAgo);
  fs.rmSync(path.join(data, '.pruned'), { force: true });
  const removed = prune(data);
  ok('prune-removes-only-stale-session-files-of-its-own-projects', removed === 1 && !fs.existsSync(stale) &&
     fs.existsSync(keepMe) && fs.existsSync(foreign) && fs.existsSync(sessionFile(data, project, 's1')) && prune(data) === 0);

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
  const reading = ['--list', '--show', '--freeze'].some((flag) => argv.includes(flag));
  const project = reading ? arg('--project') || projectRoot(process.env) : null;
  const roots = reading ? readRoots(arg('--data'), process.env) : null;
  if (argv.includes('--selftest')) {
    selftest();
  } else if (argv.includes('--list')) {
    const limit = parseInt(arg('--limit'), 10);
    const session = argv.includes('--session') ? (arg('--session') || '') : null;
    process.stdout.write(list(roots, project, session, Number.isFinite(limit) && limit > 0 ? limit : 10, argv.includes('--all')));
    process.exit(0);
  } else if (argv.includes('--show')) {
    const id = arg('--show');
    const entry = readProject(roots, project).find((e) => e.id === id);
    if (!entry) {
      process.stderr.write(`capture-intent: no ledger entry has id "${id}"\n`);
      process.exit(2);
    }
    process.stdout.write((typeof entry.prompt === 'string' ? entry.prompt : '') + '\n');
    process.exit(0);
  } else if (argv.includes('--freeze')) {
    const ids = (arg('--freeze') || '').split(',').map((s) => s.trim()).filter(Boolean);
    const meta = freeze(roots, project, ids, arg('--out'));
    if (!meta) {
      process.stderr.write(`capture-intent: not every id in "${ids.join(',')}" names a ledger entry with a captured prompt\n`);
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

module.exports = { capture, markIncomplete, applyRedactions, list, freeze, prune, readProject, readRoots, sessionFile, projectKey, VERIFY_INVOCATION };
