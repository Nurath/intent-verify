def search(items, q):
    """Return items containing the query, case-insensitively."""
    ql = q.lower()
    return [x for x in items if ql in x.lower()]
