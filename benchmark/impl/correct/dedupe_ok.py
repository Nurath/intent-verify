def dedupe(emails):
    """Remove duplicate emails, preserving first-seen order."""
    return list(dict.fromkeys(emails))
