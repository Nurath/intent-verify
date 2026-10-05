# Benchmark — 2026-10-05 — real verifier: claude-sonnet-5-5, two-stage (criteria fixed first, by the same model) (suite: controlled, n=16)

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
| tokens, all calls | 1476685 |
| cost, USD at list price | 1.23 |
| model time, minutes | 4.3 |
| ambiguities kept: each names the criteria that depend on it | 12 |
| ambiguities dropped: no criterion depends on them | 0 |

| case | expected | got | retries | manifest criteria | stage-1 tokens | stage-2 tokens | note |
|---|---|---|---|---|---|---|---|
| median | DRIFTED | DRIFTED | 0 | 4 | 4094 | 73832 |  |
| ratelimit | DRIFTED | DRIFTED | 0 | 5 | 4318 | 74580 |  |
| sortposts | DRIFTED | DRIFTED | 0 | 2 | 4001 | 73422 |  |
| dedupe | DRIFTED | DRIFTED | 0 | 3 | 4218 | 110810 |  |
| search | DRIFTED | DRIFTED | 0 | 4 | 4212 | 73591 |  |
| roundprice | DRIFTED | DRIFTED | 0 | 5 | 4835 | 186160 |  |
| validate | DRIFTED | DRIFTED | 0 | 4 | 4262 | 73834 |  |
| sorttasks | DRIFTED | DRIFTED | 0 | 3 | 4081 | 74178 |  |
| median_ok | MATCHES INTENT | MATCHES INTENT | 0 | 5 | 4159 | 150078 |  |
| ratelimit_ok | MATCHES INTENT | MATCHES INTENT | 0 | 5 | 4380 | 74440 |  |
| sortposts_ok | MATCHES INTENT | MATCHES INTENT | 0 | 2 | 4024 | 73751 |  |
| dedupe_ok | MATCHES INTENT | MATCHES INTENT | 0 | 3 | 4144 | 73730 |  |
| search_ok | MATCHES INTENT | MATCHES INTENT | 0 | 3 | 4102 | 74139 |  |
| roundprice_ok | MATCHES INTENT | MATCHES INTENT | 0 | 5 | 4461 | 74399 |  |
| validate_ok | MATCHES INTENT | MATCHES INTENT | 0 | 4 | 4256 | 74051 |  |
| sorttasks_ok | MATCHES INTENT | MATCHES INTENT | 0 | 3 | 4078 | 74065 |  |
