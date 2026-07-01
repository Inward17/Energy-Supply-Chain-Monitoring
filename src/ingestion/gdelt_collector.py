"""
src/ingestion/gdelt_collector.py
─────────────────────────────────
Queries the GDELT Doc 2.0 API (no auth required) for energy-supply-chain
relevant news and persists headlines to the local news_cache table.

API endpoint: https://api.gdeltproject.org/api/v2/doc/doc
Free, no key, no registration. Throttled to 1 req/sec by the service.

Strategy:
  - Filter by energy transit keywords (chokepoints, crude, LNG, tanker)
  - Deduplicate by URL before any DB insert
  - Token-efficient: we only send titles to the LLM, not full article text
"""

from __future__ import annotations

import logging
import time
import json
from typing import Any

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from src.database.postgres_db import upsert_news

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# GDELT API Config
# ---------------------------------------------------------------------------

GDELT_DOC_URL = "https://api.gdeltproject.org/api/v2/doc/doc"

# Energy chokepoint + supply chain keyword filter
# Grouped with OR to maximise relevant article capture
ENERGY_QUERY = (
    '("Strait of Hormuz" OR "Suez Canal" OR "Bab-el-Mandeb" OR '
    '"Red Sea" OR "Persian Gulf" OR "Strait of Malacca" OR '
    '"crude oil" OR "oil tanker" OR "LNG carrier" OR '
    '"oil supply disruption" OR "oil sanctions" OR '
    '"refinery attack" OR "pipeline explosion")'
)

GDELT_PARAMS = {
    "query":     ENERGY_QUERY,
    "mode":      "ArtList",
    "format":    "json",
    "maxrecords": "50",   # Keep well within free tier
    "timespan":  "3d",    # Expand window to 3 days to guarantee news and survive rate limits
    "sort":      "DateDesc",
}


# ---------------------------------------------------------------------------
# Fetch
# ---------------------------------------------------------------------------

class RateLimitError(Exception):
    pass

@retry(
    retry=retry_if_exception_type((httpx.HTTPError, RateLimitError)),
    wait=wait_exponential(multiplier=2, min=2, max=30),
    stop=stop_after_attempt(5),
    reraise=False,
)
def _query_gdelt(params: dict) -> list[dict[str, Any]]:
    """Execute a single GDELT Doc 2.0 API request and parse article list."""
    with httpx.Client(timeout=20.0) as client:
        resp = client.get(GDELT_DOC_URL, params=params)
        if resp.status_code == 429:
            logger.warning("GDELT Rate Limit hit (429). Backing off...")
            raise RateLimitError("429 Too Many Requests")
        resp.raise_for_status()

    if not resp.text.strip():
        logger.info("GDELT returned an empty response (likely no articles found).")
        return []

    try:
        data = resp.json()
    except json.JSONDecodeError:
        logger.warning("GDELT returned invalid JSON: %s", resp.text[:200])
        return []

    articles = data.get("articles", [])
    logger.info("GDELT returned %d articles.", len(articles))
    return articles


def _parse_articles(raw: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Extract only the fields we need from raw GDELT article records."""
    parsed = []
    for item in raw:
        url = item.get("url", "").strip()
        if not url:
            continue
        parsed.append({
            "url":    url,
            "title":  item.get("title", "")[:500],   # Cap length
            "source": item.get("domain", item.get("sourcecountry", "")),
        })
    return parsed


# ---------------------------------------------------------------------------
# Public Interface
# ---------------------------------------------------------------------------

def fetch_and_store(timespan: str | None = None) -> int:
    """
    Fetch latest energy-relevant news from GDELT and persist to news_cache.

    Args:
        timespan: GDELT timespan filter (e.g. '15min', '1h', '24h').
                  Use '24h' on first run to backfill the last 24 hours.

    Returns:
        Number of new rows inserted into news_cache.
    """
    if timespan:
        params = {**GDELT_PARAMS, "timespan": timespan}
    else:
        params = GDELT_PARAMS
        timespan = params.get("timespan", "15min")
    logger.info("gdelt_collector: querying GDELT (timespan=%s) ...", timespan)

    try:
        raw = _query_gdelt(params)
    except Exception as exc:
        logger.error("gdelt_collector: query failed — %s", exc)
        return 0

    if not raw:
        logger.info("gdelt_collector: no new articles in timespan.")
        return 0

    records = _parse_articles(raw)
    if not records:
        return 0

    count = upsert_news(records)
    logger.info("gdelt_collector: %d new records stored.", count)
    return count


def backfill(timespan: str = "24h") -> int:
    """Backfill the news_cache with the last 24 hours of articles. Call once at setup."""
    logger.info("gdelt_collector: backfilling with timespan=%s", timespan)
    return fetch_and_store(timespan=timespan)


# ---------------------------------------------------------------------------
# CLI test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    n = fetch_and_store(timespan="1h")
    print(f"Stored {n} new articles.")
