def valid_username(u):
    """Valid if 3-20 chars after trimming whitespace."""
    return 3 <= len(u.strip()) <= 20
