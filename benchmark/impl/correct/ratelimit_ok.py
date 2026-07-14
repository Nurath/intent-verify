import time
from collections import defaultdict
_a = defaultdict(list); WINDOW, LIMIT = 60, 5
def allow_login(ip):
    now = time.time()
    _a[ip] = [t for t in _a[ip] if now - t < WINDOW]
    if len(_a[ip]) >= LIMIT: return False
    _a[ip].append(now); return True
