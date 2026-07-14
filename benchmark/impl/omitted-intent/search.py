def search(items, q):
    """Return items whose text contains the query."""
    return [x for x in items if q in x]
