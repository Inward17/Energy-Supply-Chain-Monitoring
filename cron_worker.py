"""
cron_worker.py
───────────────
Background orchestration engine — the Shadow Cache heartbeat.

Runs a sequential pipeline every CRON_INTERVAL_MINUTES (default: 15 min):
  1. market_trawler  — yfinance price fetch
  2. gdelt_collector — GDELT news headlines
  3. ais_streamer    — AIS vessel snapshot
  4. sentinel_agent  — Gemini batch scoring

Designed to run in a dedicated terminal alongside `streamlit run app.py`.
Uses the `schedule` library for a simple, dependency-free loop.

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
import time
from datetime import datetime, timezone
from pathlib import Path

import schedule
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("cron_worker.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("cron_worker")

# ---------------------------------------------------------------------------
# File Lock (prevent overlapping runs on Windows)
# ---------------------------------------------------------------------------

_LOCK_FILE = Path("cron_worker.lock")
_running = False  # Simple in-process guard (used instead of fcntl on Windows)


def _acquire_lock() -> bool:
    """Return True if no other cycle is already running."""
    global _running
    if _running:
        logger.warning("Previous cron cycle still running — skipping this tick.")
        return False
    _running = True
    return True


def _release_lock() -> None:
    global _running
    _running = False


# ---------------------------------------------------------------------------
# Pipeline Steps
# ---------------------------------------------------------------------------

def step_market() -> None:
    """Fetch energy market prices from yfinance."""
    from src.ingestion.market_trawler import fetch_and_store
    results = fetch_and_store()
    logger.info("MARKET  ✓  %s", results)


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
    n = process_unprocessed_batch(batch_size=5)
    logger.info("SENTINEL✓  %d risk event(s) written", n)


# ---------------------------------------------------------------------------
# Full Cycle
# ---------------------------------------------------------------------------

def run_cycle() -> None:
    """Execute one complete Shadow Cache refresh cycle."""
    if not _acquire_lock():
        return

    start = datetime.now(timezone.utc)
    logger.info("=" * 60)
    logger.info("CRON CYCLE START  %s", start.strftime("%Y-%m-%d %H:%M UTC"))
    logger.info("=" * 60)

    steps = [
        ("Market Trawler", step_market),
        ("GDELT Collector", step_gdelt),
        ("AIS Streamer",    step_ais),
        ("Sentinel Agent",  step_sentinel),
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

    _release_lock()


# ---------------------------------------------------------------------------
# Entry Point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Energy Resilience OS — Cron Worker")
    parser.add_argument("--once",     action="store_true", help="Run one cycle then exit")
    parser.add_argument("--backfill", action="store_true", help="Backfill 24h GDELT news then exit")
    args = parser.parse_args()

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
        backfill(timespan="24h")
        logger.info("Backfill complete. Exiting.")
        return

    if args.once:
        logger.info("Single-pass mode — running one full cycle ...")
        run_cycle()
        logger.info("Done. Exiting.")
        return

    # Scheduled mode
    interval = int(os.getenv("CRON_INTERVAL_MINUTES", "15"))
    logger.info("Starting scheduled cron loop — every %d minutes.", interval)
    logger.info("Press Ctrl+C to stop.")

    # Run immediately on startup so dashboard has data right away
    run_cycle()

    schedule.every(interval).minutes.do(run_cycle)

    try:
        while True:
            schedule.run_pending()
            time.sleep(30)
    except KeyboardInterrupt:
        logger.info("Cron worker stopped by user.")


if __name__ == "__main__":
    main()
