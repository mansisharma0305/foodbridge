"""Minimal in-memory rate limiter for POST endpoints (login, register, report).

Good enough for a demo / single process. For public deployment use Flask-Limiter with a
shared store (Redis) and configure the proxy so request.remote_addr is the real client IP.
"""
import threading
import time
from collections import defaultdict, deque
from functools import wraps

from flask import abort, current_app, request

_hits = defaultdict(deque)
_lock = threading.Lock()


def reset_rate_limits():
    with _lock:
        _hits.clear()


def rate_limit(limit, window_seconds):
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if request.method == "POST" and current_app.config.get("RATELIMIT_ENABLED", True):
                key = (request.endpoint, request.remote_addr)
                now = time.monotonic()
                with _lock:
                    hits = _hits[key]
                    while hits and now - hits[0] > window_seconds:
                        hits.popleft()
                    if len(hits) >= limit:
                        abort(429)
                    hits.append(now)
            return view(*args, **kwargs)

        return wrapped

    return decorator
