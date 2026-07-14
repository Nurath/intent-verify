import time
_attempts = []
WINDOW, LIMIT = 60, 5
def allow_login(ip):
    """Block after 5 login attempts per minute."""
    now = time.time()
    global _attempts
    _attempts = [t for t in _attempts if now - t < WINDOW]
    if len(_attempts) >= LIMIT:
        return False
    _attempts.append(now)
    return True
