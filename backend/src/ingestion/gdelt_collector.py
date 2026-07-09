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
import urllib.parse

from src.database.postgres_db import upsert_news
from src.database.neo4j_graph import get_driver

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# GDELT API Config
# ---------------------------------------------------------------------------

GDELT_DOC_URL = "https://api.gdeltproject.org/api/v2/doc/doc"

# Energy chokepoint + supply chain keyword filter
# Grouped with OR to maximise relevant article capture
# Includes producer-nation disruption terms (sanctions, export ban, troop buildup)
ENERGY_QUERY = (
    '("Strait of Hormuz" OR "Suez Canal" OR "Bab-el-Mandeb" OR '
    '"Red Sea" OR "Persian Gulf" OR "Strait of Malacca" OR '
    '"crude oil" OR "oil tanker" OR "LNG carrier" OR '
    '"oil supply disruption" OR "oil sanctions" OR '
    '"refinery attack" OR "pipeline explosion" OR '
    '"production cut" OR "export ban" OR "troop buildup" OR '
    '"military drill" OR "invasion")'
)

GDELT_PARAMS = {
    "query":     ENERGY_QUERY,
    "mode":      "ArtList",
    "format":    "json",
    "maxrecords": "100",  # Increased to capture broader producer-nation news before Python pre-filter
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


# ---------------------------------------------------------------------------
# Python Pre-Filter Logic
# ---------------------------------------------------------------------------

_CHOKEPOINTS = {
    "Strait of Hormuz", "Suez Canal", "Bab-el-Mandeb",
    "Strait of Malacca", "Turkish Straits", "Cape of Good Hope",
    "Strait of Gibraltar", "Panama Canal", "Red Sea", "Persian Gulf"
}

def _get_producer_countries() -> list[str]:
    """Dynamically fetch distinct producer countries from Neo4j ExportPorts."""
    driver = get_driver()
    countries = ["Saudi Arabia", "Kuwait", "Iran", "Iraq", "UAE", "Russia", "Nigeria", "Venezuela", "USA", "Canada"] # Fallback
    if not driver:
        return countries
        
    try:
        with driver.session() as session:
            res = session.run("MATCH (p:ExportPort) RETURN DISTINCT p.country AS c")
            db_countries = [r["c"] for r in res if r["c"]]
            if db_countries:
                countries = db_countries
    except Exception as exc:
        logger.warning("Failed to fetch producer countries from Neo4j, using fallback: %s", exc)
        
    return countries

def _prefilter_articles(articles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Coarse pre-filter to drop noise before Gemini scoring.
    Keeps articles whose title contains known chokepoints, producer countries, 
    or major conflict/supply-chain keywords.
    """
    countries = [c.lower() for c in _get_producer_countries()]
    chokepoints = [c.lower() for c in _CHOKEPOINTS]
    broad_keywords = [
        "crude oil", "oil tanker", "lng carrier", "oil supply", "sanctions", 
        "refinery", "pipeline", "production cut", "export ban", "troop buildup", 
        "military drill", "invasion", "war", "conflict"
    ]
    
    TIER_1_GLOBAL = {
        "reuters.com", "bloomberg.com", "ft.com", "wsj.com", "cnbc.com", 
        "bbc.com", "cnn.com", "apnews.com", "aljazeera.com", "nytimes.com", 
        "theguardian.com", "dw.com", "france24.com", "washingtonpost.com"
    }
    
    TIER_2_INDUSTRY = {
        "oilprice.com", "spglobal.com", "argusmedia.com", "platts.com", 
        "eia.gov", "iea.org", "rigzone.com", "upstreamonline.com", 
        "arabnews.com", "alarabiya.net", "jpost.com", "haaretz.com",
        "worldoil.com", "energyintel.com"
    }

    global_arts = []
    industry_arts = []
    other_arts = []

    for art in articles:
        title = art.get("title", "").lower()
        domain = art.get("domain", "").lower()
        if (any(c in title for c in countries) or 
            any(cp in title for cp in chokepoints) or
            any(k in title for k in broad_keywords)):
            
            if domain in TIER_1_GLOBAL:
                global_arts.append(art)
            elif domain in TIER_2_INDUSTRY:
                industry_arts.append(art)
            else:
                other_arts.append(art)
    
    # Enforce 60 / 20 / 20 split for max 10 articles
    max_total = 10
    target_global = 6
    target_industry = 2
    target_other = 2

    # Fill quotas, reallocating unused slots to others if necessary
    kept_global = global_arts[:target_global]
    rem_global_slots = target_global - len(kept_global)

    target_industry += rem_global_slots
    kept_industry = industry_arts[:target_industry]
    rem_ind_slots = target_industry - len(kept_industry)

    target_other += rem_ind_slots
    kept_other = other_arts[:target_other]
    rem_other_slots = target_other - len(kept_other)

    # If we still have slots left from 'other', we can backfill global/industry
    if rem_other_slots > 0:
        extra_global = global_arts[len(kept_global):len(kept_global) + rem_other_slots]
        kept_global.extend(extra_global)
        rem_other_slots -= len(extra_global)

    if rem_other_slots > 0:
        extra_industry = industry_arts[len(kept_industry):len(kept_industry) + rem_other_slots]
        kept_industry.extend(extra_industry)

    filtered = kept_global + kept_industry + kept_other
    logger.info("[GDELT] Python pre-filter kept %d articles (Global: %d, Industry: %d, Other: %d).", 
                len(filtered), len(kept_global), len(kept_industry), len(kept_other))
    return filtered


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

    raw = _prefilter_articles(raw)
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


def fetch_historical(startdatetime: str, enddatetime: str) -> list[dict[str, str]]:
    """
    Fetch news from GDELT for a specific historical window without persisting to news_cache.
    Used for the backtest script.
    
    Args:
        startdatetime: YYYYMMDDHHMMSS
        enddatetime: YYYYMMDDHHMMSS
        
    Returns:
        List of parsed article dictionaries.
    """
    params = {
        **GDELT_PARAMS, 
        "startdatetime": startdatetime, 
        "enddatetime": enddatetime
    }
    # timespan conflicts with start/end datetimes
    if "timespan" in params:
        del params["timespan"]
        
    logger.info("gdelt_collector: querying GDELT historical (%s to %s) ...", startdatetime, enddatetime)

    try:
        raw = _query_gdelt(params)
    except Exception as exc:
        logger.error("gdelt_collector: historical query failed — %s", exc)
        return []

    raw = _prefilter_articles(raw)
    return _parse_articles(raw)


# ---------------------------------------------------------------------------
# CLI test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    n = fetch_and_store(timespan="1h")
    print(f"Stored {n} new articles.")
