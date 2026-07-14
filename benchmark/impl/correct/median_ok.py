def middle(nums):
    """Return the median of a list of numbers."""
    s = sorted(nums); n = len(s); m = n // 2
    return s[m] if n % 2 else (s[m-1] + s[m]) / 2
