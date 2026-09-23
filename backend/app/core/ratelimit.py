"""Per-user rate limiting for endpoints that do real work per call (/ai/ask).
In-process sliding window keyed by a hash of the session token — never the
raw token. One API instance runs today (render.yaml); if it ever scales out,
this becomes per-instance, which is still a sensible ceiling but not a
global one.
"""

from __future__ import annotations

import hashlib
import threading
import time
from collections import deque

from fastapi import HTTPException, Request

from .cookies import read_access_token


class RateLimiter:
    def __init__(self, limit: int, window_seconds: float) -> None:
        self.limit = limit
        self.window = window_seconds
        self._hits: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def check(self, key: str) -> None:
        now = time.monotonic()
        with self._lock:
            hits = self._hits.setdefault(key, deque())
            while hits and now - hits[0] > self.window:
                hits.popleft()
            if len(hits) >= self.limit:
                retry = int(self.window - (now - hits[0])) + 1
                raise HTTPException(
                    status_code=429,
                    detail="You're sending requests too quickly. Please wait a moment and try again.",
                    headers={"Retry-After": str(retry)},
                )
            hits.append(now)
            if len(self._hits) > 5000:  # bound memory: drop idle callers
                for k in [k for k, v in self._hits.items() if not v or now - v[-1] > self.window]:
                    del self._hits[k]

    def check_request(self, request: Request) -> None:
        token = read_access_token(request) or (request.client.host if request.client else "anonymous")
        self.check(hashlib.sha256(token.encode()).hexdigest())


# A person asks at most a few questions a minute.
ASK_LIMITER = RateLimiter(limit=20, window_seconds=60)
