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
| tokens, all calls | 1696161 |
| cost, USD at list price | 1.28 |
| model time, minutes | 4.9 |
| ambiguities kept: each names the criteria that depend on it | 8 |
| ambiguities dropped: no criterion depends on them | 0 |

| case | expected | got | retries | manifest criteria | stage-1 tokens | stage-2 tokens | note |
|---|---|---|---|---|---|---|---|
| median | DRIFTED | DRIFTED | 0 | 3 | 4246 | 109914 |  |
| ratelimit | DRIFTED | DRIFTED | 0 | 5 | 4241 | 110792 |  |
| sortposts | DRIFTED | DRIFTED | 0 | 2 | 3884 | 73128 |  |
| dedupe | DRIFTED | DRIFTED | 0 | 3 | 4075 | 222860 |  |
| search | DRIFTED | DRIFTED | 0 | 4 | 4094 | 147829 |  |
| roundprice | DRIFTED | DRIFTED | 0 | 4 | 4611 | 74068 |  |
| validate | DRIFTED | DRIFTED | 0 | 4 | 4198 | 73753 |  |
| sorttasks | DRIFTED | DRIFTED | 0 | 3 | 4109 | 73795 |  |
| median_ok | MATCHES INTENT | MATCHES INTENT | 0 | 4 | 4224 | 149933 |  |
| ratelimit_ok | MATCHES INTENT | MATCHES INTENT | 0 | 5 | 4481 | 74564 |  |
| sortposts_ok | MATCHES INTENT | MATCHES INTENT | 0 | 2 | 4122 | 73688 |  |
| dedupe_ok | MATCHES INTENT | MATCHES INTENT | 0 | 3 | 4776 | 73737 |  |
| search_ok | MATCHES INTENT | MATCHES INTENT | 0 | 3 | 4187 | 148100 |  |
| roundprice_ok | MATCHES INTENT | MATCHES INTENT | 0 | 3 | 4575 | 73824 |  |
| validate_ok | MATCHES INTENT | MATCHES INTENT | 0 | 4 | 4388 | 73867 |  |
| sorttasks_ok | MATCHES INTENT | MATCHES INTENT | 0 | 3 | 4189 | 73909 |  |
