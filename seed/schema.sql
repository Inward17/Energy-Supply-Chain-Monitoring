-- Schema for Energy Supply Chain Resilience OS
-- Run this BEFORE restoring seed/postgres_dump.sql
-- This is identical to what init_schema() creates in postgres_db.py

CREATE TABLE IF NOT EXISTS news_cache (
    id         SERIAL PRIMARY KEY,
    url        TEXT UNIQUE NOT NULL,
    title      TEXT,
    source     TEXT,
    fetched_at TIMESTAMPTZ DEFAULT NOW(),
    processed  BOOLEAN DEFAULT FALSE
);

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
);

ALTER TABLE vessel_telemetry ADD COLUMN IF NOT EXISTS ship_type INTEGER;

CREATE TABLE IF NOT EXISTS vessel_type_registry (
    mmsi        BIGINT PRIMARY KEY,
    ship_type   INTEGER,
    first_seen  TIMESTAMPTZ DEFAULT NOW()
);

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
);

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
);

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
);

CREATE TABLE IF NOT EXISTS backtest_jobs (
    id          SERIAL PRIMARY KEY,
    event_name  TEXT NOT NULL,
    status      TEXT DEFAULT 'pending',
    start_time  TIMESTAMPTZ,
    end_time    TIMESTAMPTZ,
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    error_log   TEXT
);

CREATE INDEX IF NOT EXISTS idx_news_processed ON news_cache (processed, fetched_at DESC);
CREATE INDEX IF NOT EXISTS idx_vessel_region  ON vessel_telemetry (region, recorded_at DESC);
CREATE INDEX IF NOT EXISTS idx_prices_ticker  ON market_prices (ticker, trade_date DESC);
CREATE INDEX IF NOT EXISTS idx_risk_severity  ON risk_events (severity DESC, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_risk_bt_event  ON risk_events_backtest (event_name, created_at DESC);
