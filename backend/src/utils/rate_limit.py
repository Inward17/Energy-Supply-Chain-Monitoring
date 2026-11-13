"""
src/utils/rate_limit.py
───────────────────────
In-memory sliding-window rate limiter for the endpoints that spend metered
quota (Gemini, GDELT) or heavy CPU.

The API is unauthenticated and CORS only restrains browsers, so without this a
script could loop `POST /api/orchestrator/war-room` and drain the daily Gemini
quota that live news scoring depends on.

Two windows per route:
  * per client  — stops one caller hogging the service.
  * global      — caps total spend even if client IPs are spoofed or rotated.

ponytail: per-process memory, so limits reset on restart and are not shared
across instances. Fine for a single Render instance; move to Redis or Postgres
if the API is ever scaled horizontally.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request


def client_ip(request: Request) -> str:
    """Best-effort caller identity.

    Production sits behind Cloudflare (in front of Render), which overwrites
    CF-Connecting-IP with the real client address, so it cannot be forged by
    the caller. X-Forwarded-For's first hop can be, which is why the global
    window exists as a backstop.
    """
    cf = request.headers.get("cf-connecting-ip")
    if cf:
        return cf.strip()
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


class RateLimiter:
    def __init__(self, name: str, per_client: int, global_limit: int, window_s: float) -> None:
        self.name = name
        self.per_client = per_client
        self.global_limit = global_limit
        self.window_s = window_s
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._all: deque[float] = deque()
        self._lock = threading.Lock()

    def _prune(self, q: deque[float], now: float) -> None:
        while q and now - q[0] > self.window_s:
            q.popleft()

    def check(self, request: Request) -> None:
        """Raise 429 when either window is full; otherwise record the hit."""
        key = client_ip(request)
        now = time.monotonic()
        with self._lock:
            q = self._hits[key]
            self._prune(q, now)
            self._prune(self._all, now)
            if len(q) >= self.per_client or len(self._all) >= self.global_limit:
                oldest = q[0] if len(q) >= self.per_client else self._all[0]
                retry = max(1, int(self.window_s - (now - oldest)) + 1)
                raise HTTPException(
                    status_code=429,
                    detail="Too many requests. Try again shortly.",
                    headers={"Retry-After": str(retry)},
                )
            q.append(now)
            self._all.append(now)
            # Drop idle clients so the map cannot grow without bound.
            if len(self._hits) > 10_000:
                for k in [k for k, v in self._hits.items() if not v]:
                    del self._hits[k]

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()
            self._all.clear()
