def sort_tasks(tasks):
    """Priority highest first; ties by due date earliest first."""
    return sorted(tasks, key=lambda t: (-t["priority"], t["due"]))
