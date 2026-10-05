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
| retried | 1 |
| model calls | 33 |
| tokens, all calls | 1786711 |
| cost, USD at list price | 1.33 |
| model time, minutes | 5.6 |

| case | expected | got | retries | manifest criteria | stage-1 tokens | stage-2 tokens | note |
|---|---|---|---|---|---|---|---|
| median | DRIFTED | DRIFTED | 0 | 5 | 3615 | 109460 |  |
| ratelimit | DRIFTED | DRIFTED | 0 | 5 | 3817 | 111886 |  |
| sortposts | DRIFTED | DRIFTED | 0 | 2 | 3486 | 72583 |  |
| dedupe | DRIFTED | DRIFTED | 0 | 3 | 3570 | 109579 |  |
| search | DRIFTED | DRIFTED | 0 | 3 | 3577 | 145991 |  |
| roundprice | DRIFTED | DRIFTED | 0 | 4 | 3787 | 184646 |  |
| validate | DRIFTED | DRIFTED | 0 | 5 | 3815 | 73663 |  |
| sorttasks | DRIFTED | DRIFTED | 0 | 3 | 3610 | 110669 |  |
| median_ok | MATCHES INTENT | MATCHES INTENT | 1 | 5 | 3639 | 110627 |  |
| ratelimit_ok | MATCHES INTENT | MATCHES INTENT | 0 | 5 | 3752 | 73506 |  |
| sortposts_ok | MATCHES INTENT | MATCHES INTENT | 0 | 2 | 3527 | 72809 |  |
| dedupe_ok | MATCHES INTENT | MATCHES INTENT | 0 | 3 | 3589 | 72657 |  |
| search_ok | MATCHES INTENT | MATCHES INTENT | 0 | 5 | 3683 | 222293 |  |
| roundprice_ok | MATCHES INTENT | MATCHES INTENT | 0 | 4 | 3757 | 73530 |  |
| validate_ok | MATCHES INTENT | MATCHES INTENT | 0 | 6 | 3802 | 73418 |  |
| sorttasks_ok | MATCHES INTENT | MATCHES INTENT | 0 | 3 | 3594 | 110774 |  |
