"""
src/ingestion/market_trawler.py
────────────────────────────────
Fetches energy market price data from yfinance — no API key required.

Tickers tracked:
  BZ=F  — Brent Crude Futures (primary energy price signal)
  NG=F  — Henry Hub Natural Gas Futures
  USO   — United States Oil Fund ETF (spot proxy)
  XLE   — Energy Select Sector SPDR Fund (sector proxy)
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

ENERGY_TICKERS = ["BZ=F", "NG=F", "USO", "XLE"]


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
    """
    Fetch OHLCV data for a single ticker via yfinance.

    Args:
        ticker: Yahoo Finance ticker symbol.
        period: Lookback period string (e.g. '60d').

    Returns:
        List of price dicts ready for upsert_price().
    """
    logger.info("Fetching %s ...", ticker)
    df = yf.download(ticker, period=period, progress=False, auto_adjust=True)

    if df.empty:
        logger.warning("No data returned for ticker: %s", ticker)
        return []

    # Flatten multi-level columns (yfinance sometimes returns MultiIndex)
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

def fetch_and_store(tickers: list[str] = ENERGY_TICKERS) -> dict[str, int]:
    """
    Fetch 60-day OHLCV history for all tracked tickers and persist to Postgres.

    Args:
        tickers: List of Yahoo Finance tickers to pull.

    Returns:
        Dict mapping ticker → number of new rows inserted.
    """
    results: dict[str, int] = {}

    for ticker in tickers:
        try:
            records = _fetch_ticker(ticker)
            if records:
                count = upsert_price(records)
                results[ticker] = count
                logger.info("market_trawler: %s → %d rows stored.", ticker, count)
            else:
                results[ticker] = 0
        except Exception as exc:
            logger.error("market_trawler: failed for %s — %s", ticker, exc)
            results[ticker] = 0

    return results


def get_brent_rolling_stats() -> dict[str, float]:
    """
    Return the current Brent Crude price, 30-day mean, and std deviation.
    Used by modeler_agent for ΔP_price normalisation.

    Returns:
        Dict with keys: current_price, rolling_mean, rolling_std.
    """
    try:
        df = yf.download("BZ=F", period=BRENT_STATS_PERIOD, progress=False, auto_adjust=True)
        if df.empty:
            return {"current_price": 0.0, "rolling_mean": 0.0, "rolling_std": 1.0}

        if hasattr(df.columns, "levels"):
            df.columns = df.columns.get_level_values(0)

        closes = df["Close"].dropna().astype(float)
        return {
            "current_price": round(float(closes.iloc[-1]), 2),
            "rolling_mean":  round(float(closes.rolling(30).mean().iloc[-1]), 2),
            "rolling_std":   round(float(closes.rolling(30).std().iloc[-1]), 2),
        }
    except Exception as exc:
        logger.error("get_brent_rolling_stats failed: %s", exc)
        return {"current_price": 0.0, "rolling_mean": 0.0, "rolling_std": 1.0}


# ---------------------------------------------------------------------------
# CLI test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    result = fetch_and_store()
    print("Fetch results:", result)
    stats = get_brent_rolling_stats()
    print("Brent stats:", stats)
