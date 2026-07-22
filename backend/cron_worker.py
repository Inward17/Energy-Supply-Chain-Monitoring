"""
cron_worker.py
───────────────
Background orchestration engine — the Shadow Cache heartbeat.

Each pipeline step runs on its own independent schedule:
  - market / freight / GDELT / sentinel / SDI — every CRON_INTERVAL_MINUTES
  - ais_streamer — immediately, then every AIS_INTERVAL_MINUTES
  - portwatch    — every 12 hours (slow-moving port traffic data)
  - retention    — every 24 hours (bounds vessel_telemetry growth)

Backtests are not scheduled here. They are user-triggered and now start
directly in the API process (see backtest_dispatch.py); this file used to
poll Postgres for them every 30 seconds, which kept a serverless database
permanently awake.

Runs either as its own process or inside the API process — see
``start_background_scheduler`` and RUN_WORKER in api.py. Both paths build the
same schedule, so the two deployment shapes cannot drift apart.

Usage:
  python cron_worker.py            # Normal background run
  python cron_worker.py --once     # Single-pass validation run
  python cron_worker.py --backfill # Backfill 24h of news on first run
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import BinaryIO, Callable

import schedule
from dotenv import load_dotenv

load_dotenv(override=True)

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

# stdout is the only handler a container platform needs — it captures and
# rotates for you. The local file is a convenience for bare-metal runs and is
# skipped when the filesystem is read-only or the log is unwanted, so a
# container never dies over a logging path it cannot write.
_LOG_HANDLERS: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]
if os.getenv("LOG_TO_FILE", "1") != "0":
    try:
        _LOG_HANDLERS.append(logging.FileHandler("cron_worker.log", encoding="utf-8"))
    except OSError:
        pass

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    handlers=_LOG_HANDLERS,
)
logger = logging.getLogger("cron_worker")

# ---------------------------------------------------------------------------
# Worker/process locks
# ---------------------------------------------------------------------------

_LOCK_FILE = Path(__file__).resolve().with_suffix(".lock")
_cycle_lock = threading.Lock()


class _ProcessSingleton:
    """Hold an operating-system file lock for the lifetime of one worker.

    The lock is attached to the open file handle rather than the presence of the
    lock file, so an unclean process exit cannot leave a permanently stale lock.
    ``msvcrt.locking`` provides the required cross-process exclusion on Windows;
    ``flock`` keeps development and CI behaviour equivalent on POSIX systems.
    """

    def __init__(self, path: Path) -> None:
        self.path = path
        self._handle: BinaryIO | None = None
        self.owner_pid: str | None = None

    def acquire(self) -> bool:
        if self._handle is not None:
            return True

        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            handle = self.path.open("x+b")
        except FileExistsError:
            handle = self.path.open("r+b")

        # msvcrt locks a byte range and therefore needs at least one byte.
        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b"\0")
            handle.flush()
        handle.seek(0)

        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (OSError, IOError):
            try:
                # PID metadata starts after the locked sentinel byte, so it
                # remains readable while another Windows process owns byte 0.
                handle.seek(1)
                owner = handle.read().decode("ascii", errors="ignore")
                self.owner_pid = owner.strip("\0\r\n ") or None
            except OSError:
                # A Windows byte-range lock can also deny reads. Exclusion still
                # succeeded even when the diagnostic owner PID is unavailable.
                self.owner_pid = None
            finally:
                handle.close()
            return False

        handle.seek(1)
        handle.write(str(os.getpid()).encode("ascii"))
        handle.truncate()
        handle.flush()
        self._handle = handle
        self.owner_pid = str(os.getpid())
        return True

    def release(self) -> None:
        handle = self._handle
        if handle is None:
            return

        try:
            # Keep the sentinel byte but remove diagnostic metadata while this
            # process still owns the lock. The file itself can safely persist.
            handle.seek(1)
            handle.truncate()
            handle.flush()
            handle.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()
            self._handle = None
            self.owner_pid = None


_WORKER_LOCK = _ProcessSingleton(_LOCK_FILE)


def _acquire_lock() -> bool:
    """Prevent overlapping cycles inside the singleton worker process."""
    if not _cycle_lock.acquire(blocking=False):
        logger.warning("Previous cron cycle still running — skipping this tick.")
        return False
    return True


def _release_lock() -> None:
    if _cycle_lock.locked():
        _cycle_lock.release()


# ---------------------------------------------------------------------------
# Pipeline Steps
# ---------------------------------------------------------------------------

def step_market() -> None:
    """Fetch energy market prices from yfinance."""
    from src.ingestion.market_trawler import fetch_and_store
    results = fetch_and_store()
    logger.info("MARKET  ✓  %s", results)


def step_freight() -> None:
    """Fetch freight cost proxy prices from yfinance."""
    from src.ingestion.freight_trawler import fetch_and_store
    results = fetch_and_store()
    logger.info("FREIGHT ✓  %s", results)


def step_gdelt() -> None:
    """Fetch latest GDELT energy news headlines."""
    from src.ingestion.gdelt_collector import fetch_and_store
    n = fetch_and_store()
    logger.info("GDELT   ✓  %d new articles", n)


def step_ais() -> None:
    """Collect AIS vessel snapshot from strategic chokepoint regions."""
    from src.ingestion.ais_streamer import snapshot_vessels
    n = snapshot_vessels()
    logger.info("AIS     ✓  %d vessel records stored", n)


def step_sentinel() -> None:
    """Run Gemini Sentinel Agent on unprocessed news batch."""
    from src.agents.sentinel_agent import process_unprocessed_batch
    n = process_unprocessed_batch(batch_size=10)
    logger.info("SENTINEL✓  %d risk event(s) written", n)


def step_sdi_snapshot() -> None:
    """Persist one canonical SDI point from the refreshed local caches."""
    from src.agents.modeler_agent import compute_current_sdi
    from src.database.postgres_db import upsert_sdi_snapshot

    snapshot = compute_current_sdi()
    upsert_sdi_snapshot(snapshot)
    logger.info("SDI     snapshot persisted: %.1f", snapshot["sdi_score"])


def step_retention() -> None:
    """Trim telemetry past the analysis window so storage stays bounded."""
    from src.database.postgres_db import purge_old_telemetry

    days = int(os.getenv("TELEMETRY_RETENTION_DAYS", "14"))
    removed = purge_old_telemetry(days)
    logger.info("RETENTION✓  %d vessel row(s) older than %dd removed", removed, days)


def step_portwatch() -> None:
    """Fetch daily port traffic from IMF PortWatch."""
    from src.ingestion.portwatch_trawler import trawl_portwatch
    trawl_portwatch()
    logger.info("PORTWATCH✓  Congestion scores updated")


def step_ais_and_snapshot() -> None:
    """Refresh AIS and immediately persist the SDI that uses that snapshot."""
    step_ais()
    step_sdi_snapshot()


def _run_step_safely(name: str, fn: Callable[[], None]) -> None:
    """Keep a failed standalone scheduled job from terminating the worker."""
    try:
        fn()
    except Exception as exc:
        logger.error("Scheduled step failed: %s - %s", name, exc, exc_info=True)


# A step is not killed for exceeding this — a thread cannot be safely
# interrupted from outside, and the underlying HTTP/WebSocket calls own their
# own timeouts. It exists so a stall is visible in the platform's logs rather
# than looking like a service that quietly stopped updating.
_SLOW_STEP_SECONDS = int(os.getenv("SLOW_STEP_WARN_SECONDS", "900"))

_step_locks: dict[str, threading.Lock] = {}
_step_locks_guard = threading.Lock()


def _lock_for(name: str) -> threading.Lock:
    with _step_locks_guard:
        return _step_locks.setdefault(name, threading.Lock())


def _dispatch(name: str, fn: Callable[[], None]) -> None:
    """Run a scheduled step in its own thread, skipping overlapping runs.

    ``schedule`` executes jobs inline on its polling loop, so a slow step
    holds up every step queued behind it — an AIS window is 10 minutes by
    default, and a stalled HTTP call is unbounded. Historical logs show
    cycles that ran for hours, during which nothing else could have run.
    Threading each step contains a stall to the step that caused it.

    The per-name lock keeps a step from overlapping itself, which is the
    behaviour the inline loop gave for free.
    """
    lock = _lock_for(name)
    if not lock.acquire(blocking=False):
        logger.warning("Skipping %s — its previous run is still in progress.", name)
        return

    def runner() -> None:
        started = time.monotonic()
        try:
            fn()
        except Exception as exc:
            logger.error("Scheduled step failed: %s - %s", name, exc, exc_info=True)
        finally:
            elapsed = time.monotonic() - started
            if elapsed > _SLOW_STEP_SECONDS:
                logger.warning(
                    "%s took %.0fs (over the %ds warning threshold) — possible stall.",
                    name,
                    elapsed,
                    _SLOW_STEP_SECONDS,
                )
            lock.release()

    threading.Thread(target=runner, name=f"job-{name}", daemon=True).start()


# ---------------------------------------------------------------------------
# Full Cycle
# ---------------------------------------------------------------------------

def run_cycle() -> None:
    """Execute one complete Shadow Cache refresh cycle."""
    if not _acquire_lock():
        return
    try:
        _run_cycle_unlocked()
    finally:
        _release_lock()


def _run_cycle_unlocked() -> None:
    start = datetime.now(timezone.utc)
    logger.info("=" * 60)
    logger.info("CRON CYCLE START  %s", start.strftime("%Y-%m-%d %H:%M UTC"))
    logger.info("=" * 60)

    steps = [
        ("Market Trawler",  step_market),
        ("Freight Trawler", step_freight),
        # GDELT runs before Sentinel so fresh articles are always available in the same cycle.
        # Previously on a separate 30-min schedule which meant Sentinel could fire on an empty queue.
        ("GDELT Collector", step_gdelt),
        ("Sentinel Agent",  step_sentinel),
        ("SDI Snapshot",    step_sdi_snapshot),
    ]

    for name, fn in steps:
        try:
            logger.info("── Running: %s", name)
            fn()
        except Exception as exc:
            logger.error("── FAILED:  %s — %s", name, exc, exc_info=True)

    elapsed = (datetime.now(timezone.utc) - start).total_seconds()
    logger.info("CRON CYCLE DONE   %.1fs elapsed", elapsed)
    logger.info("=" * 60)


# ---------------------------------------------------------------------------
# Scheduling
# ---------------------------------------------------------------------------

def build_schedule() -> None:
    """Register every recurring step. Shared by both deployment shapes.

    Intervals default high because each wake-up costs more than the work
    itself on a serverless database: it cannot scale to zero until several
    idle minutes have passed, so frequent short jobs bill almost as much as
    running continuously. Both are env-tunable for a host without that
    constraint.
    """
    interval = int(os.getenv("CRON_INTERVAL_MINUTES", "60"))
    ais_interval = int(os.getenv("AIS_INTERVAL_MINUTES", "60"))

    logger.info(
        "Scheduling — cycle every %dm, AIS every %dm, PortWatch 12h, retention 24h.",
        interval,
        ais_interval,
    )

    schedule.every(interval).minutes.do(_dispatch, "Cron Cycle", run_cycle)
    schedule.every(ais_interval).minutes.do(
        _dispatch, "AIS + SDI Refresh", step_ais_and_snapshot
    )

    # Port traffic is slow-moving — once every 12 hours is plenty
    schedule.every(12).hours.do(_dispatch, "PortWatch", step_portwatch)

    # Storage housekeeping — cheap, and the only thing stopping vessel_telemetry
    # growing past a managed free tier's cap.
    schedule.every(24).hours.do(_dispatch, "Retention", step_retention)


def run_startup_steps() -> None:
    """One-off steps that must not wait for their first scheduled tick.

    AIS runs hourly and PortWatch twice a day. A process that only ever starts
    those from the schedule serves stale vessel and port data for that whole
    interval — and on a host that restarts on every config change, or idles the
    instance out, the interval can reset before it ever elapses. Vessel
    telemetry went a full day without a single new row that way while every
    other feed kept writing normally.

    Shared with the standalone worker so the two deployment shapes start from
    the same state.
    """
    for name, fn in (
        ("Initial AIS Snapshot", step_ais),
        ("Post-AIS SDI Snapshot", step_sdi_snapshot),
        ("Initial PortWatch", step_portwatch),
    ):
        logger.info("Running startup step: %s", name)
        _run_step_safely(name, fn)


def run_scheduler_loop(stop: threading.Event | None = None) -> None:
    """Poll the schedule until stopped. Blocks; see start_background_scheduler."""
    while stop is None or not stop.is_set():
        schedule.run_pending()
        time.sleep(10)


def start_background_scheduler() -> threading.Thread | None:
    """Run the pipeline inside the caller's process.

    Used when the API and worker share one process — the shape a host bills
    per service, or one whose free tier covers a web service but not a
    separate worker.

    Takes the same cross-process lock as standalone mode, so starting the API
    with RUN_WORKER=1 while `python cron_worker.py` is already running leaves
    scheduling to the existing worker instead of doubling every job and every
    metered API call. Returns None in that case.
    """
    if not _WORKER_LOCK.acquire():
        owner = f" (PID {_WORKER_LOCK.owner_pid})" if _WORKER_LOCK.owner_pid else ""
        logger.warning(
            "A cron worker is already running%s — not scheduling in this process.",
            owner,
        )
        return None

    build_schedule()
    thread = threading.Thread(
        target=run_scheduler_loop, name="cron-scheduler", daemon=True
    )
    thread.start()
    logger.info("In-process cron scheduler started.")
    return thread


# ---------------------------------------------------------------------------
# Entry Point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Energy Resilience OS — Cron Worker")
    parser.add_argument("--once",     action="store_true", help="Run one cycle then exit")
    parser.add_argument("--backfill", action="store_true", help="Backfill 24h GDELT news then exit")
    args = parser.parse_args()

    if not _WORKER_LOCK.acquire():
        owner = f" (PID {_WORKER_LOCK.owner_pid})" if _WORKER_LOCK.owner_pid else ""
        logger.error("Another cron worker is already running%s; exiting.", owner)
        return

    try:
        _run_worker(args)
    finally:
        _WORKER_LOCK.release()


def _run_worker(args: argparse.Namespace) -> None:
    # Ensure DB schema exists before any cycle runs
    from src.database.postgres_db import init_schema
    from src.database.neo4j_graph import seed_graph

    logger.info("Initialising local PostgreSQL schema ...")
    init_schema()

    logger.info("Seeding Neo4j knowledge graph (no-op if already seeded) ...")
    seed_graph()

    if args.backfill:
        logger.info("Backfilling GDELT 24h news ...")
        from src.ingestion.gdelt_collector import backfill
        try:
            backfill(timespan="24h")
        except Exception as exc:
            logger.error("Backfill failed: %s", exc)
            raise SystemExit(1)
        logger.info("Backfill complete. Exiting.")
        return

    if args.once:
        logger.info("Single-pass mode — running one full cycle ...")
        run_cycle()
        logger.info("Done. Exiting.")
        return

    # Scheduled mode
    logger.info("Press Ctrl+C to stop.")

    # Run immediately on startup so the dashboard has current inputs.
    run_cycle()
    run_startup_steps()

    build_schedule()

    try:
        run_scheduler_loop()
    except KeyboardInterrupt:
        logger.info("Cron worker stopped by user.")


if __name__ == "__main__":
    main()
