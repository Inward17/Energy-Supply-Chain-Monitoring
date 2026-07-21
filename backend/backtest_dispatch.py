"""
backtest_dispatch.py
─────────────────────
In-process dispatch for user-triggered backtest jobs.

Replaces a queue the API wrote to and the cron worker polled every 30 seconds.
That poll issued a Postgres query twice a minute forever, which on a
serverless database is the difference between "idle most of the time" and
"never idle at all" — it could never reach the inactivity window needed to
scale to zero, so a metered compute allowance drained continuously whether or
not anyone ran a backtest. Dispatching directly removes the query entirely,
and a job now starts immediately instead of up to 30 s later.

Jobs run in threads rather than the previous `subprocess.Popen`, which paid a
fresh interpreter's imports (~190 MB of pandas/numpy/searoute) per job on top
of this process's own. Threads share what is already loaded.

Concurrency is capped for the same reason: each backtest builds frames over
the full event window, and the small instances this deploys to have 512 MB
total. The old code spawned one subprocess per pending job with no limit, so
two clicks could take the service down with an out-of-memory kill.
"""

from __future__ import annotations

import logging
import os
import threading

logger = logging.getLogger("backtest_dispatch")

# One at a time by default — enough for a dashboard whose backtests are
# occasional and user-initiated, and the only setting that reliably fits the
# 512 MB tiers. Raise it where memory allows.
MAX_CONCURRENT = max(1, int(os.getenv("BACKTEST_MAX_CONCURRENT", "1")))

_slots = threading.BoundedSemaphore(MAX_CONCURRENT)


def active_jobs() -> int:
    """Best-effort count of running jobs, for logging and health output."""
    # BoundedSemaphore exposes no public counter; the private one is stable and
    # this is advisory only, so a wrong read is harmless.
    return MAX_CONCURRENT - getattr(_slots, "_value", MAX_CONCURRENT)


def _run(job_id: int, event_name: str) -> None:
    try:
        # Imported here, not at module scope: this module is pulled in by the
        # API at startup, and run_backtest drags in the full modelling stack.
        # Deferring it keeps that cost on the first backtest rather than on
        # every boot, which matters when the platform times out slow starts.
        from run_backtest import run_backtest

        run_backtest(job_id, event_name)
    except Exception:
        # run_backtest marks its own job failed; this only covers a raise
        # before it got that far, so the thread ends with a logged reason
        # instead of an unhandled traceback in the platform's log.
        logger.exception("Backtest job %s (%s) crashed", job_id, event_name)
    finally:
        _slots.release()


def dispatch(job_id: int, event_name: str) -> bool:
    """Start a backtest in a background thread.

    Returns False when every slot is busy so the caller can say so, rather
    than accepting the job and silently never running it.
    """
    if not _slots.acquire(blocking=False):
        logger.warning(
            "Backtest %s rejected — %d job(s) already running.", job_id, MAX_CONCURRENT
        )
        return False

    threading.Thread(
        target=_run,
        args=(job_id, event_name),
        name=f"backtest-{job_id}",
        daemon=True,
    ).start()
    logger.info("Backtest job %s (%s) started in-process.", job_id, event_name)
    return True
