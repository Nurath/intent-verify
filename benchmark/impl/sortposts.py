def sort_posts(posts):
    """Sort posts by date."""
    return sorted(posts, key=lambda p: p["date"])
