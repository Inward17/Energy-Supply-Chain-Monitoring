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
from collections import deque

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
        self._hits: dict[str, deque[float]] = {}
        self._all: deque[float] = deque()
        self._lock = threading.Lock()
        self._last_sweep = time.monotonic()

    def _prune(self, q: deque[float], now: float) -> None:
        while q and now - q[0] > self.window_s:
            q.popleft()

    def _sweep(self, now: float) -> None:
        """Forget clients whose newest hit has left the window.

        A client's timestamps are otherwise pruned only when it returns, so an
        idle client kept its entry forever. Runs at most once a minute (or once
        per window, if shorter), O(clients).
        """
        if now - self._last_sweep < min(self.window_s, 60.0):
            return
        self._last_sweep = now
        stale = [k for k, q in self._hits.items() if not q or now - q[-1] > self.window_s]
        for k in stale:
            del self._hits[k]

    def check(self, request: Request) -> None:
        """Raise 429 when either window is full; otherwise record the hit.

        Nothing is allocated for a request that is rejected, so a flood of
        new client keys cannot grow memory once the global window is full.
        """
        key = client_ip(request)
        now = time.monotonic()
        with self._lock:
            self._sweep(now)
            self._prune(self._all, now)
            q = self._hits.get(key)
            if q is not None:
                self._prune(q, now)
            client_full = q is not None and len(q) >= self.per_client
            if client_full or len(self._all) >= self.global_limit:
                oldest = q[0] if client_full else self._all[0]
                retry = max(1, int(self.window_s - (now - oldest)) + 1)
                raise HTTPException(
                    status_code=429,
                    detail="Too many requests. Try again shortly.",
                    headers={"Retry-After": str(retry)},
                )
            if q is None:
                q = self._hits[key] = deque()
            q.append(now)
            self._all.append(now)

    def tracked_clients(self) -> int:
        with self._lock:
            return len(self._hits)

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()
            self._all.clear()
