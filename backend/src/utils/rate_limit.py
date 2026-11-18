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

import os
import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request


def client_ip(request: Request) -> str:
    """Caller identity for per-client limits.

    Proxy headers are trusted only when TRUSTED_PROXY says what sits in front:

    * ``cloudflare`` (default, the production setup): CF-Connecting-IP. Render
      is fronted by Cloudflare, which sets this header itself and answers 403
      to any request that tries to supply it (verified against production).
    * ``none``: the TCP peer address only, for deployments reached directly.

    X-Forwarded-For is never trusted: its first hop is whatever the client
    sent. The global window remains the backstop either way.
    """
    if os.getenv("TRUSTED_PROXY", "cloudflare").strip().lower() == "cloudflare":
        cf = request.headers.get("cf-connecting-ip")
        if cf:
            return cf.strip()
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
