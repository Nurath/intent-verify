# Benchmark — 2026-10-06 — real verifier: claude-sonnet-5-5, two-stage (criteria fixed first, by the same model) (suite: controlled, n=16)

Each call is `claude -p --safe-mode`: none of the runner's own CLAUDE.md, plugins,
hooks or MCP servers are loaded. Tokens and cost are as the CLI reports them; the
cost is at list price, whatever plan the runner is on.

| metric | value |
|---|---|
| n | 16 |
| correct | 16 |
| false_match | 0 |
| false_alarm | 0 |
| inconclusive | 0 |
| retried | 0 |
| model calls | 32 |
| tokens, all calls | 1530204 |
| cost, USD at list price | 1.27 |
| model time, minutes | 4.7 |
| ambiguities kept: each names the criteria that depend on it | 8 |
| ambiguities dropped: no criterion depends on them | 0 |

| case | expected | got | retries | manifest criteria | stage-1 tokens | stage-2 tokens | note |
|---|---|---|---|---|---|---|---|
| median | DRIFTED | DRIFTED | 0 | 4 | 4427 | 74356 |  |
| ratelimit | DRIFTED | DRIFTED | 0 | 4 | 4221 | 75383 |  |
| sortposts | DRIFTED | DRIFTED | 0 | 2 | 4015 | 74364 |  |
| dedupe | DRIFTED | DRIFTED | 0 | 3 | 4602 | 74874 |  |
| search | DRIFTED | DRIFTED | 0 | 4 | 4136 | 74359 |  |
| roundprice | DRIFTED | DRIFTED | 0 | 5 | 4686 | 75290 |  |
| validate | DRIFTED | DRIFTED | 0 | 5 | 4295 | 74697 |  |
| sorttasks | DRIFTED | DRIFTED | 0 | 3 | 4070 | 74671 |  |
| median_ok | MATCHES INTENT | MATCHES INTENT | 0 | 4 | 4182 | 74627 |  |
| ratelimit_ok | MATCHES INTENT | MATCHES INTENT | 0 | 5 | 4310 | 75316 |  |
| sortposts_ok | MATCHES INTENT | MATCHES INTENT | 0 | 3 | 4043 | 74767 |  |
| dedupe_ok | MATCHES INTENT | MATCHES INTENT | 0 | 3 | 4224 | 74422 |  |
| search_ok | MATCHES INTENT | MATCHES INTENT | 0 | 3 | 4161 | 74489 |  |
| roundprice_ok | MATCHES INTENT | MATCHES INTENT | 0 | 4 | 4592 | 265706 |  |
| validate_ok | MATCHES INTENT | MATCHES INTENT | 0 | 4 | 4257 | 149974 |  |
| sorttasks_ok | MATCHES INTENT | MATCHES INTENT | 0 | 3 | 4073 | 74615 |  |
