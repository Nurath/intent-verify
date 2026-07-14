def sort_tasks(tasks):
    """Sort tasks by priority, highest first. Each task: {'priority': int, 'due': 'YYYY-MM-DD'}."""
    return sorted(tasks, key=lambda t: -t["priority"])
