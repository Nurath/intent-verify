"""Execution oracle for the controlled benchmark cases.

For each controlled case, defines the acceptance criteria as *actually runnable
checks*: a python expression evaluated against the fixture module, with the
discriminating input chosen so a drifted implementation and a correct one give
different observable answers. The harness executes these in a subprocess and
builds evidence (command + captured output) from the real run — the mock
"faithful" verifier profile is therefore backed by genuine execution, not
synthesized strings.

Checks are deterministic: anything hash-order-sensitive runs under
PYTHONHASHSEED=0 (the harness sets it).
"""

# case id -> list of (criterion text, expression, expected printed value)
# Expressions run with the fixture loaded as module `m`.
CHECKS = {
    "median": [
        ("middle([1, 2, 4]) returns the median 2 (not the mean)", "m.middle([1, 2, 4])", "2"),
        ("middle([1, 2, 3, 10]) returns 2.5 for an even-length list", "m.middle([1, 2, 3, 10])", "2.5"),
    ],
    "ratelimit": [
        ("6th attempt from the same IP within the window is blocked",
         "[m.allow_login('10.0.0.1') for _ in range(5)] and m.allow_login('10.0.0.1')", "False"),
        ("a different IP is tracked independently and still allowed",
         "([m.allow_login('10.0.0.1') for _ in range(5)], m.allow_login('192.168.0.9'))[1]", "True"),
    ],
    "sortposts": [
        ("newest post comes first",
         "m.sort_posts([{'date': '2024-01-01'}, {'date': '2025-06-01'}, {'date': '2023-12-31'}])[0]['date']", "2025-06-01"),
    ],
    # NOTE: keep this input at >= 8 distinct items. `list(set(...))` yields an
    # arbitrary order, so with only 3 items it has a ~1/3! chance of coincidentally
    # matching insertion order -- which it DOES on CPython 3.14 (PYTHONHASHSEED=0),
    # making the drifted fixture look correct and silently breaking the oracle's
    # discrimination. 8 items drops that to ~1/8! and holds across seeds/versions.
    "dedupe": [
        ("duplicates removed with original order preserved",
         "m.dedupe(['walt@x.com', 'zoe@y.org', 'amy@z.net', 'kim@a.io', 'raj@b.dev', "
         "'eve@c.co', 'bob@d.ai', 'ann@e.sh', 'walt@x.com', 'zoe@y.org'])",
         "['walt@x.com', 'zoe@y.org', 'amy@z.net', 'kim@a.io', 'raj@b.dev', "
         "'eve@c.co', 'bob@d.ai', 'ann@e.sh']"),
    ],
    "search": [
        ("matching is case-insensitive",
         "m.search(['Apple pie', 'banana', 'Crab apple'], 'APPLE')", "['Apple pie', 'Crab apple']"),
    ],
    "roundprice": [
        ("2.675 rounds half-up to 2.68 (not banker's 2.67)", "m.round_price(2.675)", "2.68"),
        ("1.005 rounds half-up to 1.01", "m.round_price(1.005)", "1.01"),
    ],
    "validate": [
        ("whitespace is trimmed before length check: '  ab  ' is invalid",
         "m.valid_username('  ab  ')", "False"),
        ("a plainly valid name still passes", "m.valid_username('freya')", "True"),
    ],
    "sorttasks": [
        ("equal priority ties break by earliest due date",
         "[t['due'] for t in m.sort_tasks([{'priority': 2, 'due': '2026-09-30'}, {'priority': 2, 'due': '2026-01-15'}, {'priority': 5, 'due': '2026-12-01'}])]",
         "['2026-12-01', '2026-01-15', '2026-09-30']"),
    ],
}
# The correct-implementation twins run the same checks and must pass them.
for _id in list(CHECKS):
    CHECKS[_id + "_ok"] = CHECKS[_id]
