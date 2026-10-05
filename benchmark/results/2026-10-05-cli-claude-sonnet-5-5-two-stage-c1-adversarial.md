# Benchmark — 2026-10-05 — real verifier: claude-sonnet-5-5, two-stage (criteria fixed first, by the same model) (suite: adversarial, n=3)

Each call is `claude -p --safe-mode`: none of the runner's own CLAUDE.md, plugins,
hooks or MCP servers are loaded. Tokens and cost are as the CLI reports them; the
cost is at list price, whatever plan the runner is on.

| metric | value |
|---|---|
| n | 3 |
| correct | 3 |
| false_match | 0 |
| false_alarm | 0 |
| inconclusive | 0 |
| retried | 0 |
| model calls | 6 |
| tokens, all calls | 383045 |
| cost, USD at list price | 0.26 |
| model time, minutes | 1.0 |
| ambiguities kept: each names the criteria that depend on it | 1 |
| ambiguities dropped: no criterion depends on them | 0 |

| case | expected | got | retries | manifest criteria | stage-1 tokens | stage-2 tokens | note |
|---|---|---|---|---|---|---|---|
| adv_final | DRIFTED | DRIFTED | 0 | 4 | 4047 | 223176 |  |
| adv_textledger | DRIFTED | DRIFTED | 0 | 2 | 3884 | 73837 |  |
| adv_jsonledger | DRIFTED | DRIFTED | 0 | 3 | 4400 | 73701 |  |
