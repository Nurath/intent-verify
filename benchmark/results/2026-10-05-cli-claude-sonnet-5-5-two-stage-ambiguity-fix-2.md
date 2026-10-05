# Benchmark — 2026-10-05 — real verifier: claude-sonnet-5-5, two-stage (criteria fixed first, by the same model) (suite: all, n=23)

Each call is `claude -p --safe-mode`: none of the runner's own CLAUDE.md, plugins,
hooks or MCP servers are loaded. Tokens and cost are as the CLI reports them; the
cost is at list price, whatever plan the runner is on.

| metric | value |
|---|---|
| n | 23 |
| correct | 21 |
| false_match | 0 |
| false_alarm | 1 |
| inconclusive | 1 |
| retried | 0 |
| model calls | 46 |
| tokens, all calls | 3169411 |
| cost, USD at list price | 2.30 |
| model time, minutes | 8.6 |
| ambiguities kept: each names the criteria that depend on it | 7 |
| ambiguities dropped: no criterion depends on them | 0 |

| case | expected | got | retries | manifest criteria | stage-1 tokens | stage-2 tokens | note |
|---|---|---|---|---|---|---|---|
| median | DRIFTED | DRIFTED | 0 | 4 | 4667 | 148870 |  |
| ratelimit | DRIFTED | DRIFTED | 0 | 4 | 4463 | 111731 |  |
| sortposts | DRIFTED | DRIFTED | 0 | 2 | 4247 | 225221 |  |
| dedupe | DRIFTED | DRIFTED | 0 | 3 | 4704 | 148659 |  |
| search | DRIFTED | DRIFTED | 0 | 4 | 4358 | 73906 |  |
| roundprice | DRIFTED | DRIFTED | 0 | 5 | 4912 | 149202 |  |
| validate | DRIFTED | DRIFTED | 0 | 4 | 4410 | 148920 |  |
| sorttasks | DRIFTED | DRIFTED | 0 | 3 | 4299 | 187758 |  |
| median_ok | MATCHES INTENT | MATCHES INTENT | 0 | 4 | 4611 | 74213 |  |
| ratelimit_ok | MATCHES INTENT | MATCHES INTENT | 0 | 5 | 4551 | 74643 |  |
| sortposts_ok | MATCHES INTENT | MATCHES INTENT | 0 | 2 | 4229 | 227944 |  |
| dedupe_ok | MATCHES INTENT | MATCHES INTENT | 0 | 3 | 4638 | 73707 |  |
| search_ok | MATCHES INTENT | MATCHES INTENT | 0 | 4 | 4363 | 111841 |  |
| roundprice_ok | MATCHES INTENT | MATCHES INTENT | 0 | 4 | 4837 | 149100 |  |
| validate_ok | MATCHES INTENT | MATCHES INTENT | 0 | 4 | 4412 | 74188 |  |
| sorttasks_ok | MATCHES INTENT | MATCHES INTENT | 0 | 3 | 4291 | 73972 |  |
| field_gpt54 | MATCHES INTENT | MATCHES INTENT | 0 | 3 | 4392 | 125867 |  |
| field_discount | MATCHES INTENT | MATCHES INTENT | 0 | 5 | 4523 | 125929 |  |
| field_telephony | MATCHES INTENT | MATCHES INTENT | 0 | 4 | 4467 | 125249 |  |
| recall_gpt4omini | MATCHES INTENT | INCONCLUSIVE | 0 | 4 | 4422 | 127432 |  |
| recall_platformfee | MATCHES INTENT | MATCHES INTENT | 0 | 4 | 4462 | 255147 |  |
| recall_weekend | MATCHES INTENT | DRIFTED | 0 | 4 | 4438 | 126313 |  |
| recall_sumcosts | MATCHES INTENT | MATCHES INTENT | 0 | 4 | 4467 | 126436 |  |
