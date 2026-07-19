-- Schema for Energy Supply Chain Resilience OS
-- Run this BEFORE restoring seed/postgres_dump.sql
-- This is identical to what init_schema() creates in postgres_db.py

CREATE TABLE IF NOT EXISTS news_cache (
    id         SERIAL PRIMARY KEY,
    url        TEXT UNIQUE NOT NULL,
    title      TEXT,
    source     TEXT,
    fetched_at TIMESTAMPTZ DEFAULT NOW(),
    processed  BOOLEAN DEFAULT FALSE,
    article_category TEXT DEFAULT 'general'
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
    directly_affected_chokepoints TEXT[],
    affected_producer_countries TEXT[],
    directly_affected_producer_countries TEXT[],
    confidence           DOUBLE PRECISION,
    summary              TEXT,
    sdi_score            DOUBLE PRECISION,
    source_urls          TEXT[],
    source_fetched_at    TIMESTAMPTZ,
    severity_reasoning   TEXT,
    article_category     TEXT DEFAULT 'general',
    created_at           TIMESTAMPTZ DEFAULT NOW()
);

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
);

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
    severity_reasoning   TEXT,
    created_at           TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS backtest_jobs (
    id          SERIAL PRIMARY KEY,
    event_name  TEXT NOT NULL,
    status      TEXT DEFAULT 'pending',
    start_time   TIMESTAMPTZ,
    end_time     TIMESTAMPTZ,
    progress_pct INT DEFAULT 0,
    progress_note TEXT,
    created_at   TIMESTAMPTZ DEFAULT NOW(),
    error_log    TEXT
);

CREATE INDEX IF NOT EXISTS idx_news_processed ON news_cache (processed, fetched_at DESC);
CREATE INDEX IF NOT EXISTS idx_vessel_region  ON vessel_telemetry (region, recorded_at DESC);
CREATE INDEX IF NOT EXISTS idx_prices_ticker  ON market_prices (ticker, trade_date DESC);
CREATE INDEX IF NOT EXISTS idx_risk_severity  ON risk_events (severity DESC, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_risk_source    ON risk_events (source_fetched_at DESC);
CREATE INDEX IF NOT EXISTS idx_sdi_computed   ON sdi_snapshots (computed_at DESC);
CREATE INDEX IF NOT EXISTS idx_risk_bt_event  ON risk_events_backtest (event_name, created_at DESC);
