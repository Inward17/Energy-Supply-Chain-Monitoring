"""
src/database/postgres_db.py
────────────────────────────
Local PostgreSQL abstraction layer using SQLAlchemy connection pooling.

All operations are wrapped in context managers to prevent zombie connections
during the persistent cron_worker scheduled loop.

Connection pool is initialised once at module level via `get_engine()`.
"""

from __future__ import annotations

import os
import logging
import urllib.parse
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Generator

from sqlalchemy import create_engine, text, Engine
from sqlalchemy.pool import QueuePool
from dotenv import load_dotenv
load_dotenv(override=True)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Engine Singleton
# ---------------------------------------------------------------------------

_engine: Engine | None = None


def get_engine() -> Engine:
    """Return (or lazily create) the shared SQLAlchemy connection pool engine."""
    global _engine
    if _engine is None:
        db_pass = os.getenv('DB_PASSWORD', '')
        encoded_pass = urllib.parse.quote_plus(db_pass) if db_pass else ''
        dsn = (
            f"postgresql+psycopg2://{os.getenv('DB_USER', 'postgres')}"
            f":{encoded_pass}"
            f"@{os.getenv('DB_HOST', 'localhost')}"
            f":{os.getenv('DB_PORT', '5432')}"
            f"/{os.getenv('DB_NAME', 'energy_resilience')}"
        )
        _engine = create_engine(
            dsn,
            poolclass=QueuePool,
            pool_size=5,
            max_overflow=10,
            pool_pre_ping=True,       # Validate connections before checkout
            pool_recycle=1800,        # Recycle connections every 30 minutes
            echo=False,
        )
        logger.info("PostgreSQL connection pool initialised.")
    return _engine


@contextmanager
def get_conn() -> Generator:
    """Context manager that yields a database connection and handles rollback on error."""
    engine = get_engine()
    conn = engine.connect()
    try:
        yield conn
        conn.commit()
    except Exception as exc:
        conn.rollback()
        logger.error("DB operation failed: %s", exc)
        raise
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Schema Initialisation (idempotent)
# ---------------------------------------------------------------------------

def init_schema() -> None:
    """
    Create all required tables if they do not already exist.
    Safe to call on every startup — uses IF NOT EXISTS.
    """
    ddl_statements = [
        """
        CREATE TABLE IF NOT EXISTS news_cache (
            id         SERIAL PRIMARY KEY,
            url        TEXT UNIQUE NOT NULL,
            title      TEXT,
            source     TEXT,
            fetched_at TIMESTAMPTZ DEFAULT NOW(),
            processed  BOOLEAN DEFAULT FALSE
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS vessel_telemetry (
            id          SERIAL PRIMARY KEY,
            mmsi        BIGINT,
            vessel_name TEXT,
            lat         DOUBLE PRECISION,
            lon         DOUBLE PRECISION,
            speed       REAL,
            heading     INTEGER,
            region      TEXT,
            recorded_at TIMESTAMPTZ DEFAULT NOW(),
            UNIQUE (mmsi, recorded_at)
        )
        """,
        "ALTER TABLE vessel_telemetry ADD COLUMN IF NOT EXISTS ship_type INTEGER;",
        """
        CREATE TABLE IF NOT EXISTS vessel_type_registry (
            mmsi        BIGINT PRIMARY KEY,
            ship_type   INTEGER,
            first_seen  TIMESTAMPTZ DEFAULT NOW()
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS market_prices (
            id          SERIAL PRIMARY KEY,
            ticker      TEXT NOT NULL,
            price_open  DOUBLE PRECISION,
            price_close DOUBLE PRECISION,
            price_high  DOUBLE PRECISION,
            price_low   DOUBLE PRECISION,
            volume      BIGINT,
            trade_date  DATE NOT NULL,
            UNIQUE (ticker, trade_date)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS risk_events (
            id                   SERIAL PRIMARY KEY,
            region               TEXT,
            disruption_type      TEXT,
            severity             DOUBLE PRECISION,
            affected_chokepoints TEXT[],
            confidence           DOUBLE PRECISION,
            summary              TEXT,
            sdi_score            DOUBLE PRECISION,
            created_at           TIMESTAMPTZ DEFAULT NOW()
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS risk_events_backtest (
            id                   SERIAL PRIMARY KEY,
            event_name           TEXT,
            region               TEXT,
            disruption_type      TEXT,
            severity             DOUBLE PRECISION,
            affected_chokepoints TEXT[],
            confidence           DOUBLE PRECISION,
            summary              TEXT,
            sdi_score            DOUBLE PRECISION,
            created_at           TIMESTAMPTZ DEFAULT NOW()
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS backtest_jobs (
            id          SERIAL PRIMARY KEY,
            event_name  TEXT NOT NULL,
            status      TEXT DEFAULT 'pending',
            start_time  TIMESTAMPTZ,
            end_time    TIMESTAMPTZ,
            created_at  TIMESTAMPTZ DEFAULT NOW(),
            error_log   TEXT
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_news_processed ON news_cache (processed, fetched_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx_vessel_region  ON vessel_telemetry (region, recorded_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx_prices_ticker  ON market_prices (ticker, trade_date DESC)",
        "CREATE INDEX IF NOT EXISTS idx_risk_severity  ON risk_events (severity DESC, created_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx_risk_bt_event  ON risk_events_backtest (event_name, created_at DESC)",
    ]
    try:
        with get_conn() as conn:
            for stmt in ddl_statements:
                conn.execute(text(stmt))
        logger.info("Schema initialised / verified OK.")
    except Exception as exc:
        logger.error("Schema init failed: %s", exc)


# ---------------------------------------------------------------------------
# news_cache
# ---------------------------------------------------------------------------

def upsert_news(records: list[dict[str, Any]]) -> int:
    """
    Insert news records; skip duplicates (conflict on url).

    Args:
        records: List of dicts with keys: url, title, source.

    Returns:
        Number of rows actually inserted.
    """
    if not records:
        return 0
    inserted = 0
    stmt = text(
        """
        INSERT INTO news_cache (url, title, source, fetched_at, processed)
        VALUES (:url, :title, :source, :fetched_at, FALSE)
        ON CONFLICT (url) DO NOTHING
        """
    )
    try:
        with get_conn() as conn:
            for rec in records:
                result = conn.execute(
                    stmt,
                    {
                        "url": rec.get("url"),
                        "title": rec.get("title", ""),
                        "source": rec.get("source", ""),
                        "fetched_at": datetime.now(timezone.utc),
                    },
                )
                inserted += result.rowcount
    except Exception as exc:
        logger.error("upsert_news failed: %s", exc)
    return inserted


def fetch_unprocessed_news(limit: int = 10) -> list[dict[str, Any]]:
    """Return unprocessed news_cache rows for the Sentinel Agent."""
    try:
        with get_conn() as conn:
            rows = conn.execute(
                text(
                    "SELECT id, url, title, source FROM news_cache "
                    "WHERE processed = FALSE ORDER BY fetched_at DESC LIMIT :lim"
                ),
                {"lim": limit},
            ).mappings().all()
            return [dict(r) for r in rows]
    except Exception as exc:
        logger.error("fetch_unprocessed_news failed: %s", exc)
        return []


def mark_news_processed(ids: list[int]) -> None:
    """Mark news_cache rows as processed after Sentinel scoring."""
    if not ids:
        return
    try:
        with get_conn() as conn:
            conn.execute(
                text("UPDATE news_cache SET processed = TRUE WHERE id = ANY(:ids)"),
                {"ids": ids},
            )
    except Exception as exc:
        logger.error("mark_news_processed failed: %s", exc)


# ---------------------------------------------------------------------------
# vessel_telemetry
# ---------------------------------------------------------------------------

def upsert_vessel(records: list[dict[str, Any]]) -> int:
    """Insert vessel position snapshots; skip exact duplicates (mmsi + timestamp)."""
    if not records:
        return 0
    stmt = text(
        """
        INSERT INTO vessel_telemetry
            (mmsi, vessel_name, ship_type, lat, lon, speed, heading, region, recorded_at)
        VALUES
            (:mmsi, :vessel_name, :ship_type, :lat, :lon, :speed, :heading, :region, :recorded_at)
        ON CONFLICT (mmsi, recorded_at) DO NOTHING
        """
    )
    inserted = 0
    try:
        with get_conn() as conn:
            for rec in records:
                result = conn.execute(
                    stmt,
                    {
                        "mmsi":        rec.get("mmsi"),
                        "vessel_name": rec.get("vessel_name", ""),
                        "ship_type":   rec.get("ship_type"),
                        "lat":         rec.get("lat"),
                        "lon":         rec.get("lon"),
                        "speed":       rec.get("speed", 0),
                        "heading":     rec.get("heading", 0),
                        "region":      rec.get("region", "Unknown"),
                        "recorded_at": rec.get("recorded_at", datetime.now(timezone.utc)),
                    },
                )
                inserted += result.rowcount
    except Exception as exc:
        logger.error("upsert_vessel failed: %s", exc)
    return inserted


def fetch_vessels(region: str | None = None, limit: int = 500) -> list[dict[str, Any]]:
    """Fetch the most recent vessel positions, optionally filtered by region."""
    try:
        with get_conn() as conn:
            if region:
                rows = conn.execute(
                    text(
                        "SELECT DISTINCT ON (mmsi) mmsi, vessel_name, ship_type, lat, lon, "
                        "speed, heading, region, recorded_at "
                        "FROM vessel_telemetry WHERE region = :region "
                        "AND recorded_at >= NOW() - INTERVAL '24 hours' "
                        "ORDER BY mmsi, recorded_at DESC LIMIT :lim"
                    ),
                    {"region": region, "lim": limit},
                ).mappings().all()
            else:
                rows = conn.execute(
                    text(
                        "SELECT DISTINCT ON (mmsi) mmsi, vessel_name, ship_type, lat, lon, "
                        "speed, heading, region, recorded_at "
                        "FROM vessel_telemetry "
                        "WHERE recorded_at >= NOW() - INTERVAL '24 hours' "
                        "ORDER BY mmsi, recorded_at DESC LIMIT :lim"
                    ),
                    {"lim": limit},
                ).mappings().all()
            return [dict(r) for r in rows]
    except Exception as exc:
        logger.error("fetch_vessels failed: %s", exc)
        return []


def upsert_vessel_types(records: list[dict[str, Any]]) -> None:
    """Insert or update ship types in the persistent registry."""
    if not records:
        return
    stmt = text(
        """
        INSERT INTO vessel_type_registry (mmsi, ship_type, first_seen)
        VALUES (:mmsi, :ship_type, :first_seen)
        ON CONFLICT (mmsi) DO UPDATE SET
            ship_type = EXCLUDED.ship_type
        """
    )
    try:
        with get_conn() as conn:
            for rec in records:
                conn.execute(stmt, rec)
    except Exception as exc:
        logger.error("upsert_vessel_types failed: %s", exc)


def fetch_vessel_types() -> dict[int, int]:
    """Fetch all known MMSI -> ship_type mappings."""
    try:
        with get_conn() as conn:
            rows = conn.execute(
                text("SELECT mmsi, ship_type FROM vessel_type_registry")
            ).mappings().all()
            return {r["mmsi"]: r["ship_type"] for r in rows if r["ship_type"] is not None}
    except Exception as exc:
        logger.error("fetch_vessel_types failed: %s", exc)
        return {}


# ---------------------------------------------------------------------------
# market_prices
# ---------------------------------------------------------------------------

def upsert_price(records: list[dict[str, Any]]) -> int:
    """Insert market price rows; update close/open/high/low if the date already exists."""
    if not records:
        return 0
    stmt = text(
        """
        INSERT INTO market_prices
            (ticker, price_open, price_close, price_high, price_low, volume, trade_date)
        VALUES
            (:ticker, :price_open, :price_close, :price_high, :price_low, :volume, :trade_date)
        ON CONFLICT (ticker, trade_date) DO UPDATE SET
            price_open  = EXCLUDED.price_open,
            price_close = EXCLUDED.price_close,
            price_high  = EXCLUDED.price_high,
            price_low   = EXCLUDED.price_low,
            volume      = EXCLUDED.volume
        """
    )
    inserted = 0
    try:
        with get_conn() as conn:
            for rec in records:
                result = conn.execute(stmt, rec)
                inserted += result.rowcount
    except Exception as exc:
        logger.error("upsert_price failed: %s", exc)
    return inserted


def fetch_latest_prices(
    tickers: list[str] | None = None, days: int = 60
) -> list[dict[str, Any]]:
    """Fetch recent price rows for given tickers (default: all)."""
    try:
        with get_conn() as conn:
            if tickers:
                rows = conn.execute(
                    text(
                        "SELECT ticker, price_open, price_close, price_high, price_low, volume, trade_date "
                        "FROM market_prices WHERE ticker = ANY(:tickers) "
                        f"AND trade_date >= CURRENT_DATE - INTERVAL '{days} days' "
                        "ORDER BY trade_date DESC"
                    ),
                    {"tickers": tickers},
                ).mappings().all()
            else:
                rows = conn.execute(
                    text(
                        "SELECT ticker, price_open, price_close, price_high, price_low, volume, trade_date "
                        f"FROM market_prices WHERE trade_date >= CURRENT_DATE - INTERVAL '{days} days' "
                        "ORDER BY ticker, trade_date DESC"
                    )
                ).mappings().all()
            return [dict(r) for r in rows]
    except Exception as exc:
        logger.error("fetch_latest_prices failed: %s", exc)
        return []


# ---------------------------------------------------------------------------
# risk_events
# ---------------------------------------------------------------------------

def upsert_risk_event(event: dict[str, Any]) -> None:
    """Insert a scored risk event from the Sentinel Agent."""
    stmt = text(
        """
        INSERT INTO risk_events
            (region, disruption_type, severity, affected_chokepoints,
             confidence, summary, sdi_score, created_at)
        VALUES
            (:region, :disruption_type, :severity, :affected_chokepoints,
             :confidence, :summary, :sdi_score, :created_at)
        """
    )
    try:
        with get_conn() as conn:
            conn.execute(
                stmt,
                {
                    "region":               event.get("region", "Unknown"),
                    "disruption_type":      event.get("disruption_type", "unknown"),
                    "severity":             event.get("severity", 0.0),
                    "affected_chokepoints": event.get("affected_chokepoints", []),
                    "confidence":           event.get("confidence", 0.0),
                    "summary":              event.get("summary", ""),
                    "sdi_score":            event.get("sdi_score", 0.0),
                    "created_at":           datetime.now(timezone.utc),
                },
            )
    except Exception as exc:
        logger.error("upsert_risk_event failed: %s", exc)


def fetch_risk_events(limit: int = 50) -> list[dict[str, Any]]:
    """Return most recent risk events sorted by severity."""
    try:
        with get_conn() as conn:
            rows = conn.execute(
                text(
                    "SELECT id, region, disruption_type, severity, affected_chokepoints, "
                    "confidence, summary, sdi_score, created_at "
                    "FROM risk_events ORDER BY created_at DESC LIMIT :lim"
                ),
                {"lim": limit},
            ).mappings().all()
            return [dict(r) for r in rows]
    except Exception as exc:
        logger.error("fetch_risk_events failed: %s", exc)
        return []


def fetch_latest_sdi() -> float:
    """Return the most recent SDI score for the dashboard summary metric."""
    try:
        with get_conn() as conn:
            row = conn.execute(
                text("SELECT sdi_score FROM risk_events ORDER BY created_at DESC LIMIT 1")
            ).mappings().first()
            if row and row["sdi_score"] is not None:
                return float(row["sdi_score"])
    except Exception as exc:
        logger.error("fetch_latest_sdi failed: %s", exc)
    return 0.0

# ---------------------------------------------------------------------------
# risk_events_backtest
# ---------------------------------------------------------------------------

def upsert_risk_event_backtest(event: dict[str, Any]) -> None:
    """Insert a scored risk event from the backtest runner."""
    stmt = text(
        """
        INSERT INTO risk_events_backtest
            (event_name, region, disruption_type, severity, affected_chokepoints,
             confidence, summary, sdi_score, created_at)
        VALUES
            (:event_name, :region, :disruption_type, :severity, :affected_chokepoints,
             :confidence, :summary, :sdi_score, :created_at)
        """
    )
    try:
        with get_conn() as conn:
            conn.execute(
                stmt,
                {
                    "event_name":           event.get("event_name", "unknown"),
                    "region":               event.get("region", "Unknown"),
                    "disruption_type":      event.get("disruption_type", "unknown"),
                    "severity":             event.get("severity", 0.0),
                    "affected_chokepoints": event.get("affected_chokepoints", []),
                    "confidence":           event.get("confidence", 0.0),
                    "summary":              event.get("summary", ""),
                    "sdi_score":            event.get("sdi_score", 0.0),
                    "created_at":           event.get("created_at", datetime.now(timezone.utc)),
                },
            )
    except Exception as exc:
        logger.error("upsert_risk_event_backtest failed: %s", exc)


def fetch_risk_events_backtest(event_name: str) -> list[dict[str, Any]]:
    """Return all risk events for a given backtest event name, sorted chronologically."""
    try:
        with get_conn() as conn:
            rows = conn.execute(
                text(
                    "SELECT id, event_name, region, disruption_type, severity, affected_chokepoints, "
                    "confidence, summary, sdi_score, created_at "
                    "FROM risk_events_backtest WHERE event_name = :event_name ORDER BY created_at ASC"
                ),
                {"event_name": event_name},
            ).mappings().all()
            return [dict(r) for r in rows]
    except Exception as exc:
        logger.error("fetch_risk_events_backtest failed: %s", exc)
        return []


# ---------------------------------------------------------------------------
# backtest_jobs
# ---------------------------------------------------------------------------

def create_backtest_job(event_name: str) -> int | None:
    """Create a new backtest job and return its ID."""
    try:
        with get_conn() as conn:
            result = conn.execute(
                text("INSERT INTO backtest_jobs (event_name, status) VALUES (:event_name, 'pending') RETURNING id"),
                {"event_name": event_name}
            )
            return result.scalar()
    except Exception as exc:
        logger.error("create_backtest_job failed: %s", exc)
        return None

def update_backtest_job(job_id: int, status: str, error_log: str | None = None) -> None:
    """Update status (and optionally error_log/timestamps) for a backtest job."""
    try:
        with get_conn() as conn:
            if status == 'running':
                conn.execute(
                    text("UPDATE backtest_jobs SET status = :status, start_time = NOW() WHERE id = :id"),
                    {"status": status, "id": job_id}
                )
            elif status in ('completed', 'failed'):
                conn.execute(
                    text("UPDATE backtest_jobs SET status = :status, end_time = NOW(), error_log = :error_log WHERE id = :id"),
                    {"status": status, "error_log": error_log, "id": job_id}
                )
            else:
                conn.execute(
                    text("UPDATE backtest_jobs SET status = :status WHERE id = :id"),
                    {"status": status, "id": job_id}
                )
    except Exception as exc:
        logger.error("update_backtest_job failed: %s", exc)

def fetch_pending_backtest_jobs() -> list[dict[str, Any]]:
    """Fetch all pending backtest jobs."""
    try:
        with get_conn() as conn:
            rows = conn.execute(
                text("SELECT id, event_name, status, start_time, end_time, created_at, error_log FROM backtest_jobs WHERE status = 'pending' ORDER BY created_at ASC")
            ).mappings().all()
            return [dict(r) for r in rows]
    except Exception as exc:
        logger.error("fetch_pending_backtest_jobs failed: %s", exc)
        return []

def fetch_all_backtest_jobs() -> list[dict[str, Any]]:
    """Fetch all backtest jobs."""
    try:
        with get_conn() as conn:
            rows = conn.execute(
                text("SELECT id, event_name, status, start_time, end_time, created_at, error_log FROM backtest_jobs ORDER BY created_at DESC LIMIT 50")
            ).mappings().all()
            return [dict(r) for r in rows]
    except Exception as exc:
        logger.error("fetch_all_backtest_jobs failed: %s", exc)
        return []
