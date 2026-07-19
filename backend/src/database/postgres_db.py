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
        # Daily call counters for the news providers. Their free tiers are
        # capped per calendar day, so the budget has to survive a worker
        # restart — an in-memory counter would silently reset and overrun.
        """
        CREATE TABLE IF NOT EXISTS provider_quota (
            provider    TEXT NOT NULL,
            usage_date  DATE NOT NULL,
            calls       INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (provider, usage_date)
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
            affected_producer_countries TEXT[],
            directly_affected_producer_countries TEXT[],
            confidence           DOUBLE PRECISION,
            summary              TEXT,
            sdi_score            DOUBLE PRECISION,
            source_urls          TEXT[],
            source_fetched_at    TIMESTAMPTZ,
            created_at           TIMESTAMPTZ DEFAULT NOW()
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS sdi_snapshots (
            id                 SERIAL PRIMARY KEY,
            sdi_score          DOUBLE PRECISION NOT NULL,
            p_risk             DOUBLE PRECISION NOT NULL,
            delta_d            DOUBLE PRECISION NOT NULL,
            delta_p            DOUBLE PRECISION NOT NULL,
            delta_f            DOUBLE PRECISION NOT NULL,
            confidence_low     DOUBLE PRECISION,
            confidence_high    DOUBLE PRECISION,
            top_region         TEXT,
            top_chokepoints    TEXT[],
            event_source_at    TIMESTAMPTZ,
            vessel_source_at   TIMESTAMPTZ,
            market_source_date DATE,
            ais_status         TEXT,
            market_status      TEXT,
            computed_at        TIMESTAMPTZ DEFAULT NOW()
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
            affected_producer_countries TEXT[],
            confidence           DOUBLE PRECISION,
            summary              TEXT,
            sdi_score            DOUBLE PRECISION,
            created_at           TIMESTAMPTZ DEFAULT NOW()
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS backtest_jobs (
            id            SERIAL PRIMARY KEY,
            event_name    TEXT NOT NULL,
            status        TEXT DEFAULT 'pending',
            progress_pct  INT DEFAULT 0,
            progress_note TEXT,
            start_time    TIMESTAMPTZ,
            end_time      TIMESTAMPTZ,
            created_at    TIMESTAMPTZ DEFAULT NOW(),
            error_log     TEXT
        )
        """,
        # Safely add progress columns to existing DBs that predate this migration
        "ALTER TABLE backtest_jobs ADD COLUMN IF NOT EXISTS progress_pct INT DEFAULT 0",
        "ALTER TABLE backtest_jobs ADD COLUMN IF NOT EXISTS progress_note TEXT",
        # Safely add source_urls column to existing DBs
        "ALTER TABLE risk_events ADD COLUMN IF NOT EXISTS source_urls TEXT[]",
        # Safely add producer countries to existing DBs
        "ALTER TABLE risk_events ADD COLUMN IF NOT EXISTS affected_producer_countries TEXT[]",
        "ALTER TABLE risk_events_backtest ADD COLUMN IF NOT EXISTS affected_producer_countries TEXT[]",
        "ALTER TABLE risk_events ADD COLUMN IF NOT EXISTS directly_affected_producer_countries TEXT[]",
        "ALTER TABLE risk_events ADD COLUMN IF NOT EXISTS source_fetched_at TIMESTAMPTZ",
        # Safely add severity reasoning to existing DBs
        "ALTER TABLE risk_events ADD COLUMN IF NOT EXISTS severity_reasoning TEXT",
        "ALTER TABLE risk_events_backtest ADD COLUMN IF NOT EXISTS severity_reasoning TEXT",
        "ALTER TABLE news_cache ADD COLUMN IF NOT EXISTS article_category TEXT DEFAULT 'general'",
        "ALTER TABLE risk_events ADD COLUMN IF NOT EXISTS article_category TEXT DEFAULT 'general'",
        """
        UPDATE risk_events AS r
        SET source_fetched_at = COALESCE(
            (
                SELECT MAX(n.fetched_at)
                FROM news_cache AS n
                WHERE n.url = ANY(COALESCE(r.source_urls, ARRAY[]::TEXT[]))
            ),
            r.created_at
        )
        WHERE r.source_fetched_at IS NULL
        """,
        "CREATE INDEX IF NOT EXISTS idx_news_processed ON news_cache (processed, fetched_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx_vessel_region  ON vessel_telemetry (region, recorded_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx_prices_ticker  ON market_prices (ticker, trade_date DESC)",
        "CREATE INDEX IF NOT EXISTS idx_risk_severity  ON risk_events (severity DESC, created_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx_risk_source    ON risk_events (source_fetched_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx_sdi_computed   ON sdi_snapshots (computed_at DESC)",
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
        INSERT INTO news_cache (url, title, source, fetched_at, processed, article_category)
        VALUES (:url, :title, :source, :fetched_at, FALSE, :article_category)
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
                        # Prefer the article's own publication time. Risk decay
                        # runs from this timestamp, so stamping a provider's
                        # delayed article (GNews ~12h, NewsAPI ~24h) as "now"
                        # would score day-old news as if it were breaking.
                        "fetched_at": rec.get("published_at") or datetime.now(timezone.utc),
                        "article_category": rec.get("article_category", "general"),
                    },
                )
                inserted += result.rowcount
    except Exception as exc:
        logger.error("upsert_news failed: %s", exc)
    return inserted


def fetch_unprocessed_news(
    limit: int = 10, max_age_hours: int = 72
) -> list[dict[str, Any]]:
    """Return recent unprocessed rows, excluding stale backlog from scoring."""
    try:
        l_cp = int(limit * 0.4)
        l_prod = int(limit * 0.3)
        l_gen = limit - l_cp - l_prod
        
        with get_conn() as conn:
            rows = conn.execute(
                text(
                    """
                    (
                        SELECT id, url, title, source, article_category, fetched_at 
                        FROM news_cache 
                        WHERE processed = FALSE AND article_category = 'chokepoint'
                        AND fetched_at >= NOW() - make_interval(hours => :max_age_hours)
                        ORDER BY fetched_at DESC LIMIT :l_cp
                    )
                    UNION ALL
                    (
                        SELECT id, url, title, source, article_category, fetched_at 
                        FROM news_cache 
                        WHERE processed = FALSE AND article_category = 'producer_nation'
                        AND fetched_at >= NOW() - make_interval(hours => :max_age_hours)
                        ORDER BY fetched_at DESC LIMIT :l_prod
                    )
                    UNION ALL
                    (
                        SELECT id, url, title, source, article_category, fetched_at 
                        FROM news_cache 
                        WHERE processed = FALSE AND article_category NOT IN ('chokepoint', 'producer_nation')
                        AND fetched_at >= NOW() - make_interval(hours => :max_age_hours)
                        ORDER BY fetched_at DESC LIMIT :l_gen
                    )
                    ORDER BY fetched_at DESC
                    """
                ),
                {
                    "l_cp": l_cp, 
                    "l_prod": l_prod, 
                    "l_gen": l_gen, 
                    "max_age_hours": max(1, max_age_hours)
                },
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


def record_provider_call(provider: str) -> None:
    """Count one outbound call against a provider's daily free-tier budget."""
    try:
        with get_conn() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO provider_quota (provider, usage_date, calls)
                    VALUES (:provider, CURRENT_DATE, 1)
                    ON CONFLICT (provider, usage_date)
                    DO UPDATE SET calls = provider_quota.calls + 1
                    """
                ),
                {"provider": provider},
            )
    except Exception as exc:
        logger.error("record_provider_call failed: %s", exc)


def provider_calls_today(provider: str) -> int:
    """Calls already spent against a provider today."""
    try:
        with get_conn() as conn:
            return int(
                conn.execute(
                    text(
                        "SELECT calls FROM provider_quota "
                        "WHERE provider = :provider AND usage_date = CURRENT_DATE"
                    ),
                    {"provider": provider},
                ).scalar()
                or 0
            )
    except Exception as exc:
        logger.error("provider_calls_today failed: %s", exc)
        # Fail closed: an unknown spend is treated as exhausted rather than
        # risking an overrun of a hard daily cap.
        return 10**6


def fetch_region_tanker_buckets(
    days: int = 7,
    bucket_minutes: int = 60,
) -> list[dict[str, Any]]:
    """Per-region, per-time-bucket tanker counts with their AIS type coverage.

    Both the live reading and the rolling baseline are derived from this one
    query so they share an identical measurement method. That matters because
    AIS ship-type coverage is only partial and *not* stationary — comparing a
    live count against a differently-measured baseline would read pure sampling
    drift as a traffic anomaly.

    Returns rows of: region, bucket, total (distinct MMSI), typed (distinct
    MMSI with a known ship_type), tankers (distinct MMSI typed as a tanker).
    """
    try:
        with get_conn() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT
                        region,
                        to_timestamp(
                            floor(extract(epoch FROM recorded_at) / (:bucket_seconds))
                            * (:bucket_seconds)
                        ) AS bucket,
                        COUNT(DISTINCT mmsi) AS total,
                        COUNT(DISTINCT mmsi) FILTER (WHERE ship_type IS NOT NULL) AS typed,
                        COUNT(DISTINCT mmsi) FILTER (
                            WHERE ship_type >= 80 AND ship_type < 90
                        ) AS tankers
                    FROM vessel_telemetry
                    WHERE recorded_at >= NOW() - make_interval(days => :days)
                      AND region IS NOT NULL
                      AND region <> 'Unknown'
                    GROUP BY region, bucket
                    ORDER BY region, bucket
                    """
                ),
                {"days": days, "bucket_seconds": bucket_minutes * 60},
            ).mappings().all()
            return [dict(r) for r in rows]
    except Exception as exc:
        logger.error("fetch_region_tanker_buckets failed: %s", exc)
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
    """Store a Gemini-scored risk event, inserting array parameters via dictionaries."""
    try:
        with get_conn() as conn:
            stmt = text("""
                INSERT INTO risk_events
                    (region, disruption_type, severity, affected_chokepoints, directly_affected_chokepoints, affected_producer_countries,
                     directly_affected_producer_countries, confidence, summary, sdi_score, source_urls,
                     source_fetched_at, severity_reasoning, article_category)
                VALUES
                    (:region, :disruption_type, :severity, :affected_chokepoints, :directly_affected_chokepoints, :affected_producer_countries,
                     :directly_affected_producer_countries, :confidence, :summary, :sdi_score, :source_urls,
                     :source_fetched_at, :severity_reasoning, :article_category)
            """)
            conn.execute(
                stmt,
                {
                    "region":               event.get("region", "Unknown"),
                    "disruption_type":      event.get("disruption_type", "unknown"),
                    "severity":             event.get("severity", 0.1),
                    "affected_chokepoints": event.get("affected_chokepoints", []),
                    "directly_affected_chokepoints": event.get("directly_affected_chokepoints", []),
                    "affected_producer_countries": event.get("affected_producer_countries", []),
                    "directly_affected_producer_countries": event.get(
                        "directly_affected_producer_countries", []
                    ),
                    "confidence":           event.get("confidence", 0.5),
                    "summary":              event.get("summary", ""),
                    "sdi_score":            event.get("sdi_score", 0.0),
                    "source_urls":          event.get("source_urls", []),
                    "source_fetched_at":    event.get("source_fetched_at"),
                    "severity_reasoning":   event.get("severity_reasoning", ""),
                    "article_category":     event.get("article_category", "general"),
                }
            )
    except Exception as exc:
        logger.error("upsert_risk_event failed: %s", exc)


def fetch_risk_events(limit: int = 50) -> list[dict[str, Any]]:
    """Return most recent risk events sorted by severity."""
    try:
        with get_conn() as conn:
            rows = conn.execute(
                text(
                    "SELECT id, region, disruption_type, severity, affected_chokepoints, directly_affected_chokepoints, affected_producer_countries, "
                    "directly_affected_producer_countries, confidence, summary, sdi_score, source_urls, "
                    "source_fetched_at, severity_reasoning, created_at "
                    "FROM risk_events ORDER BY created_at DESC LIMIT :lim"
                ),
                {"lim": limit},
            ).mappings().all()
            return [dict(r) for r in rows]
    except Exception as exc:
        logger.error("fetch_risk_events failed: %s", exc)
        return []

def fetch_risk_event(event_id: int) -> dict[str, Any] | None:
    """Return a single risk event by ID."""
    try:
        with get_conn() as conn:
            row = conn.execute(
                text(
                    "SELECT id, region, disruption_type, severity, affected_chokepoints, directly_affected_chokepoints, "
                    "affected_producer_countries, directly_affected_producer_countries, confidence, summary, "
                    "sdi_score, source_urls, source_fetched_at, severity_reasoning, created_at "
                    "FROM risk_events WHERE id = :event_id"
                ),
                {"event_id": event_id},
            ).mappings().first()
            return dict(row) if row else None
    except Exception as exc:
        logger.error("fetch_risk_event failed: %s", exc)
        return None

def fetch_latest_sdi() -> float:
    """Return the most recent SDI score for the dashboard summary metric."""
    try:
        with get_conn() as conn:
            row = conn.execute(
                text("SELECT sdi_score FROM sdi_snapshots ORDER BY computed_at DESC LIMIT 1")
            ).mappings().first()
            if row and row["sdi_score"] is not None:
                return float(row["sdi_score"])
    except Exception as exc:
        logger.error("fetch_latest_sdi failed: %s", exc)
    return 0.0


# ---------------------------------------------------------------------------
# sdi_snapshots
# ---------------------------------------------------------------------------

def upsert_sdi_snapshot(snapshot: dict[str, Any]) -> None:
    """Persist one canonical SDI computation for the dashboard timeline."""
    try:
        with get_conn() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO sdi_snapshots
                        (sdi_score, p_risk, delta_d, delta_p, delta_f,
                         confidence_low, confidence_high, top_region, top_chokepoints,
                         event_source_at, vessel_source_at, market_source_date,
                         ais_status, market_status, computed_at)
                    VALUES
                        (:sdi_score, :p_risk, :delta_d, :delta_p, :delta_f,
                         :confidence_low, :confidence_high, :top_region, :top_chokepoints,
                         :event_source_at, :vessel_source_at, :market_source_date,
                         :ais_status, :market_status, COALESCE(:computed_at, NOW()))
                    """
                ),
                {
                    "sdi_score": snapshot.get("sdi_score", 0.0),
                    "p_risk": snapshot.get("p_risk", 0.0),
                    "delta_d": snapshot.get("delta_d", 0.0),
                    "delta_p": snapshot.get("delta_p", 0.0),
                    "delta_f": snapshot.get("delta_f", 0.0),
                    "confidence_low": snapshot.get("confidence_low"),
                    "confidence_high": snapshot.get("confidence_high"),
                    "top_region": snapshot.get("top_region"),
                    "top_chokepoints": snapshot.get("top_chokepoints", []),
                    "event_source_at": snapshot.get("event_source_at"),
                    "vessel_source_at": snapshot.get("vessel_source_at"),
                    "market_source_date": snapshot.get("market_source_date"),
                    "ais_status": snapshot.get("ais_status", "unavailable"),
                    "market_status": snapshot.get("market_status", "unavailable"),
                    "computed_at": snapshot.get("computed_at"),
                },
            )
    except Exception as exc:
        logger.error("upsert_sdi_snapshot failed: %s", exc)
        raise


def fetch_sdi_snapshots(limit: int = 50) -> list[dict[str, Any]]:
    """Return persisted SDI points, newest first."""
    try:
        with get_conn() as conn:
            rows = conn.execute(
                text(
                    "SELECT id, sdi_score, p_risk, delta_d, delta_p, delta_f, "
                    "confidence_low, confidence_high, top_region, top_chokepoints, "
                    "event_source_at, vessel_source_at, market_source_date, "
                    "ais_status, market_status, computed_at "
                    "FROM sdi_snapshots ORDER BY computed_at DESC LIMIT :lim"
                ),
                {"lim": limit},
            ).mappings().all()
            return [dict(row) for row in rows]
    except Exception as exc:
        logger.error("fetch_sdi_snapshots failed: %s", exc)
        return []

# ---------------------------------------------------------------------------
# risk_events_backtest
# ---------------------------------------------------------------------------

def upsert_risk_event_backtest(event: dict[str, Any]) -> None:
    """Insert a scored risk event from the backtest runner."""
    stmt = text(
        """
        INSERT INTO risk_events_backtest
            (event_name, region, disruption_type, severity, affected_chokepoints, affected_producer_countries,
             confidence, summary, sdi_score, severity_reasoning, created_at)
        VALUES
            (:event_name, :region, :disruption_type, :severity, :affected_chokepoints, :affected_producer_countries,
             :confidence, :summary, :sdi_score, :severity_reasoning, :created_at)
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
                    "affected_producer_countries": event.get("affected_producer_countries", []),
                    "confidence":           event.get("confidence", 0.0),
                    "summary":              event.get("summary", ""),
                    "sdi_score":            event.get("sdi_score", 0.0),
                    "severity_reasoning":   event.get("severity_reasoning", ""),
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
                    "SELECT id, event_name, region, disruption_type, severity, affected_chokepoints, affected_producer_countries, "
                    "confidence, summary, sdi_score, severity_reasoning, created_at "
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
    """Create a new backtest job only if one doesn't already exist for this event_name.
    Returns the existing job ID if one exists, or the new one if created.
    """
    try:
        with get_conn() as conn:
            # Return existing job if already present (avoid duplicates)
            existing = conn.execute(
                text("SELECT id FROM backtest_jobs WHERE event_name = :event_name ORDER BY id DESC LIMIT 1"),
                {"event_name": event_name}
            ).fetchone()
            if existing:
                return existing[0]
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

def update_backtest_job_progress(job_id: int, progress_pct: int, current_date_str: str) -> None:
    """Update the progress percentage and current date being processed for a running backtest job."""
    try:
        with get_conn() as conn:
            conn.execute(
                text("UPDATE backtest_jobs SET progress_pct = :pct, progress_note = :note WHERE id = :id"),
                {"pct": progress_pct, "note": current_date_str, "id": job_id}
            )
    except Exception as exc:
        logger.error("update_backtest_job_progress failed: %s", exc)

def fetch_pending_backtest_jobs() -> list[dict[str, Any]]:
    """Fetch all pending backtest jobs."""
    try:
        with get_conn() as conn:
            rows = conn.execute(
                text("SELECT id, event_name, status, progress_pct, progress_note, start_time, end_time, created_at, error_log FROM backtest_jobs WHERE status = 'pending' ORDER BY created_at ASC")
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
                text("SELECT id, event_name, status, progress_pct, progress_note, start_time, end_time, created_at, error_log FROM backtest_jobs ORDER BY created_at DESC LIMIT 50")
            ).mappings().all()
            return [dict(r) for r in rows]
    except Exception as exc:
        logger.error("fetch_all_backtest_jobs failed: %s", exc)
        return []
