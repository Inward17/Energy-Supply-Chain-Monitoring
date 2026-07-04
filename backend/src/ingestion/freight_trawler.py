"""
src/ingestion/freight_trawler.py
────────────────────────────────
Fetches shipping freight cost proxy data from yfinance.

We use the Breakwave Dry Bulk Shipping ETF (BOAT) as a proxy for freight
stress. While not exactly VLCC crude rates, it serves as a leading
macro indicator for global shipping costs.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any

import yfinance as yf
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from src.database.postgres_db import upsert_price
from src.utils.constants import MARKET_HISTORY_PERIOD, BRENT_STATS_PERIOD

logger = logging.getLogger(__name__)

FREIGHT_TICKER = "BOAT"


# ---------------------------------------------------------------------------
# Fetch with retry
# ---------------------------------------------------------------------------

@retry(
    retry=retry_if_exception_type(Exception),
    wait=wait_exponential(multiplier=2, min=4, max=30),
    stop=stop_after_attempt(3),
    reraise=False,
)
def _fetch_ticker(ticker: str, period: str = MARKET_HISTORY_PERIOD) -> list[dict[str, Any]]:
    """Fetch OHLCV data for a single ticker via yfinance."""
    logger.info("Fetching %s ...", ticker)
    df = yf.download(ticker, period=period, progress=False, auto_adjust=True)

    if df.empty:
        logger.warning("No data returned for ticker: %s", ticker)
        return []

    # Flatten multi-level columns
    if hasattr(df.columns, "levels"):
        df.columns = df.columns.get_level_values(0)

    records = []
    for idx, row in df.iterrows():
        trade_date = idx.date() if hasattr(idx, "date") else idx
        records.append({
            "ticker":      ticker,
            "price_open":  round(float(row.get("Open",  0) or 0), 4),
            "price_close": round(float(row.get("Close", 0) or 0), 4),
            "price_high":  round(float(row.get("High",  0) or 0), 4),
            "price_low":   round(float(row.get("Low",   0) or 0), 4),
            "volume":      int(row.get("Volume", 0) or 0),
            "trade_date":  trade_date,
        })
    return records


# ---------------------------------------------------------------------------
# Public Interface
# ---------------------------------------------------------------------------

def fetch_and_store() -> dict[str, int]:
    """Fetch history for the freight ticker and persist to Postgres."""
    results: dict[str, int] = {}
    try:
        records = _fetch_ticker(FREIGHT_TICKER)
        if records:
            count = upsert_price(records)
            results[FREIGHT_TICKER] = count
            logger.info("freight_trawler: %s → %d rows stored.", FREIGHT_TICKER, count)
        else:
            results[FREIGHT_TICKER] = 0
    except Exception as exc:
        logger.error("freight_trawler: failed for %s — %s", FREIGHT_TICKER, exc)
        results[FREIGHT_TICKER] = 0

    return results


def fetch_historical_prices(start_date: str, end_date: str) -> dict[str, int]:
    """Fetch historical prices for a specific date window using yfinance."""
    results: dict[str, int] = {}
    try:
        logger.info("Fetching historical %s from %s to %s...", FREIGHT_TICKER, start_date, end_date)
        df = yf.download(FREIGHT_TICKER, start=start_date, end=end_date, progress=False, auto_adjust=True)
        
        if df.empty:
            logger.warning("No historical data returned for ticker: %s", FREIGHT_TICKER)
            results[FREIGHT_TICKER] = 0
            return results

        if hasattr(df.columns, "levels"):
            df.columns = df.columns.get_level_values(0)

        records = []
        for idx, row in df.iterrows():
            trade_date = idx.date() if hasattr(idx, "date") else idx
            records.append({
                "ticker":      FREIGHT_TICKER,
                "price_open":  round(float(row.get("Open",  0) or 0), 4),
                "price_close": round(float(row.get("Close", 0) or 0), 4),
                "price_high":  round(float(row.get("High",  0) or 0), 4),
                "price_low":   round(float(row.get("Low",   0) or 0), 4),
                "volume":      int(row.get("Volume", 0) or 0),
                "trade_date":  trade_date,
            })
            
        if records:
            count = upsert_price(records)
            results[FREIGHT_TICKER] = count
            logger.info("freight_trawler: %s → %d historical rows stored.", FREIGHT_TICKER, count)
        else:
            results[FREIGHT_TICKER] = 0
    except Exception as exc:
        logger.error("freight_trawler: failed to process historical %s — %s", FREIGHT_TICKER, exc)
        results[FREIGHT_TICKER] = 0

    return results


def get_freight_rolling_stats() -> dict[str, float]:
    """
    Return the current freight price, rolling mean, and std deviation.
    Used by modeler_agent for ΔP_freight normalisation.
    """
    try:
        df = yf.download(FREIGHT_TICKER, period=BRENT_STATS_PERIOD, progress=False, auto_adjust=True)
        if df.empty:
            return {"current_price": 0.0, "rolling_mean": 0.0, "rolling_std": 0.0}

        if hasattr(df.columns, "levels"):
            df.columns = df.columns.get_level_values(0)

        closes = df["Close"].dropna().astype(float)
        if closes.empty:
            return {"current_price": 0.0, "rolling_mean": 0.0, "rolling_std": 0.0}

        return {
            "current_price": round(float(closes.iloc[-1]), 2),
            "rolling_mean":  round(float(closes.rolling(30).mean().iloc[-1]), 2) if len(closes) >= 30 else round(float(closes.mean()), 2),
            "rolling_std":   round(float(closes.rolling(30).std().iloc[-1]), 2) if len(closes) >= 30 else (round(float(closes.std()), 2) if len(closes) > 1 else 0.0),
        }
    except Exception as exc:
        logger.error("Failed to fetch freight stats: %s", exc)
        return {"current_price": 0.0, "rolling_mean": 0.0, "rolling_std": 0.0}
