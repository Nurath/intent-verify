# Benchmark — 2026-10-06 — real verifier: claude-sonnet-5-5, two-stage (criteria fixed first, by the same model) (suite: controlled, n=16)

Each call is `claude -p --safe-mode --effort high`: none of the runner's own CLAUDE.md, plugins,
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
| tokens, all calls | 1512258 |
| cost, USD at list price | 1.46 |
| model time, minutes | 5.4 |
| ambiguities kept: each names the criteria that depend on it | 3 |
| ambiguities dropped: no criterion depends on them | 0 |
| of those kept, asked before verifying: the request may not ask for a change | 0 |

| case | expected | got | retries | manifest criteria | stage-1 tokens | stage-2 tokens | note |
|---|---|---|---|---|---|---|---|
| median | DRIFTED | DRIFTED | 0 | 3 | 5022 | 112468 |  |
| ratelimit | DRIFTED | DRIFTED | 0 | 5 | 5333 | 76064 |  |
| sortposts | DRIFTED | DRIFTED | 0 | 3 | 4531 | 74968 |  |
| dedupe | DRIFTED | DRIFTED | 0 | 3 | 4984 | 113799 |  |
| search | DRIFTED | DRIFTED | 0 | 4 | 4888 | 75072 |  |
| roundprice | DRIFTED | DRIFTED | 0 | 2 | 5433 | 74598 |  |
| validate | DRIFTED | DRIFTED | 0 | 5 | 5248 | 113652 |  |
| sorttasks | DRIFTED | DRIFTED | 0 | 3 | 4861 | 75689 |  |
| median_ok | MATCHES INTENT | MATCHES INTENT | 0 | 4 | 4974 | 75123 |  |
| ratelimit_ok | MATCHES INTENT | MATCHES INTENT | 0 | 5 | 5280 | 76439 |  |
| sortposts_ok | MATCHES INTENT | MATCHES INTENT | 0 | 2 | 4763 | 112263 |  |
| dedupe_ok | MATCHES INTENT | MATCHES INTENT | 0 | 3 | 4805 | 74937 |  |
| search_ok | MATCHES INTENT | MATCHES INTENT | 0 | 4 | 4620 | 75659 |  |
| roundprice_ok | MATCHES INTENT | MATCHES INTENT | 0 | 4 | 5186 | 113214 |  |
| validate_ok | MATCHES INTENT | MATCHES INTENT | 0 | 4 | 4976 | 75441 |  |
| sorttasks_ok | MATCHES INTENT | MATCHES INTENT | 0 | 3 | 4853 | 113115 |  |
