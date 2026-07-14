def sort_posts(posts):
    """Sort posts by date, newest first."""
    return sorted(posts, key=lambda p: p["date"], reverse=True)
