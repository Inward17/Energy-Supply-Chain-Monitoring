"""
src/ingestion/gdelt_collector.py
─────────────────────────────────
Queries the GDELT Doc 2.0 API (no auth required) for energy-supply-chain
relevant news and persists headlines to the local news_cache table.

API endpoint: https://api.gdeltproject.org/api/v2/doc/doc
Free, no key, no registration. Throttled to one request per 5 seconds.

Strategy:
  - Filter by energy transit keywords (chokepoints, crude, LNG, tanker)
  - Secondary filter for producer nation signals (sanctions, war, etc.)
  - Alternate maritime/producer live queries across cycles to avoid 429 bursts
  - Deduplicate by URL before any DB insert
  - Token-efficient: we only send titles to the LLM, not full article text
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from src.database.postgres_db import upsert_news
from src.database.neo4j_graph import get_driver

from src.utils.constants import (
    GDELT_PRODUCER_MAXRECORDS,
    GDELT_SLOTS_MARITIME,
    GDELT_SLOTS_PRODUCER,
    PRODUCER_NATIONS,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# GDELT API Config
# ---------------------------------------------------------------------------

GDELT_DOC_URL = "https://api.gdeltproject.org/api/v2/doc/doc"

# GDELT currently returns a plain-text query-length error for the previous
# 337/516-byte expressions. Keep a conservative byte cap so future vocabulary
# additions fail locally instead of silently starving the news cache.
GDELT_QUERY_MAX_BYTES = 200
GDELT_QUERY_MIN_BYTES = 3

_MARITIME_QUERY_TERMS = (
    "Strait of Hormuz",
    "Suez Canal",
    "Bab-el-Mandeb",
    "Red Sea",
    "Persian Gulf",
    "Strait of Malacca",
    "oil tanker",
    "LNG carrier",
)
_PRODUCER_ENERGY_TERMS = (
    "oil production",
    "oil exports",
    "oil refinery",
    "oil pipeline",
)
_PRODUCER_DISRUPTION_TERMS = (
    "attack",
    "shutdown",
    "sanctions",
    "embargo",
    "war",
)

#: Queries A and B between them only match conflict and policy vocabulary, so
#: weather, accident, piracy and protest disruptions were never ingested at all
#: — leaving four of the Sentinel's nine disruption types unreachable and their
#: tuned decay half-lives dead code. This third query covers them. It is a
#: separate rotation slot rather than an extension of Query B because the API
#: rejects expressions over GDELT_QUERY_MAX_BYTES.
_PHYSICAL_ASSET_TERMS = (
    "oil tanker",
    "oil terminal",
    "refinery",
    "pipeline",
)
_PHYSICAL_DISRUPTION_TERMS = (
    "storm",
    "fire",
    "explosion",
    "piracy",
    "strike",
)


def _quote_query_term(term: str) -> str:
    return term if term.isalnum() else f'"{term}"'


def _or_clause(terms: tuple[str, ...]) -> str:
    return "(" + " OR ".join(_quote_query_term(term) for term in terms) + ")"


def _validate_query(query: str, *, label: str) -> str:
    """Return a normalized query or reject it before consuming an API call."""
    if not isinstance(query, str):
        raise ValueError(f"{label} query must be a string")
    normalized = " ".join(query.split())
    query_bytes = len(normalized.encode("utf-8"))
    if not GDELT_QUERY_MIN_BYTES <= query_bytes <= GDELT_QUERY_MAX_BYTES:
        raise ValueError(
            f"{label} query is {query_bytes} bytes; expected "
            f"{GDELT_QUERY_MIN_BYTES}-{GDELT_QUERY_MAX_BYTES}"
        )
    return normalized


def _build_maritime_query() -> str:
    return _validate_query(_or_clause(_MARITIME_QUERY_TERMS), label="maritime")


def _build_producer_query() -> str:
    """Build one compact producer-risk query; country matching stays local."""
    query = (
        f"{_or_clause(_PRODUCER_ENERGY_TERMS)} AND "
        f"{_or_clause(_PRODUCER_DISRUPTION_TERMS)}"
    )
    return _validate_query(query, label="producer")


def _build_physical_query() -> str:
    """Storm / fire / piracy / labour disruptions to energy infrastructure."""
    query = (
        f"{_or_clause(_PHYSICAL_ASSET_TERMS)} AND "
        f"{_or_clause(_PHYSICAL_DISRUPTION_TERMS)}"
    )
    return _validate_query(query, label="physical")


ENERGY_QUERY = _build_maritime_query()
PRODUCER_QUERY = _build_producer_query()
PHYSICAL_QUERY = _build_physical_query()

#: A 3-day window mostly re-returned articles already held in news_cache, so
#: each successful call spent its payload on duplicates that ON CONFLICT then
#: discarded. 12h keeps the yield fresh and raises the share of genuinely new
#: rows per call — which matters when successful calls are the scarce resource.
GDELT_TIMESPAN = os.getenv("GDELT_TIMESPAN", "12h")

GDELT_PARAMS = {
    "query": ENERGY_QUERY,
    "mode": "ArtList",
    "format": "json",
    "maxrecords": "100",
    "timespan": GDELT_TIMESPAN,
    "sort": "DateDesc",
}

GDELT_PARAMS_PRODUCER = {
    "query": PRODUCER_QUERY,
    "mode": "ArtList",
    "format": "json",
    "maxrecords": str(GDELT_PRODUCER_MAXRECORDS),
    "timespan": GDELT_TIMESPAN,
    "sort": "DateDesc",
}

GDELT_PARAMS_PHYSICAL = {
    "query": PHYSICAL_QUERY,
    "mode": "ArtList",
    "format": "json",
    "maxrecords": str(GDELT_PRODUCER_MAXRECORDS),
    "timespan": GDELT_TIMESPAN,
    "sort": "DateDesc",
}

# ---------------------------------------------------------------------------
# Fetch
# ---------------------------------------------------------------------------

class RateLimitError(Exception):
    pass

@retry(
    # Do not retry 429s inside the same cycle. Repeated immediate requests
    # extend GDELT's per-IP throttle; the next scheduled cycle is the retry.
    retry=retry_if_exception_type(httpx.HTTPError),
    wait=wait_exponential(multiplier=2, min=6, max=60),
    stop=stop_after_attempt(5),
    reraise=False,
)
def _query_gdelt(params: dict[str, Any]) -> list[dict[str, Any]]:
    """Execute a single GDELT Doc 2.0 API request and parse article list."""
    request_params = dict(params)
    request_params["query"] = _validate_query(
        request_params.get("query", ""),
        label="request",
    )
    with httpx.Client(timeout=20.0) as client:
        resp = client.get(GDELT_DOC_URL, params=request_params)
        if resp.status_code == 429:
            # Deliberately not retried in-cycle (RateLimitError is outside the
            # tenacity predicate): hammering GDELT extends the per-IP throttle.
            logger.warning(
                "GDELT rate limit (429); skipping this cycle, next scheduled "
                "cycle is the retry."
            )
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
    logger.info("GDELT returned %d articles for query pattern.", len(articles))
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
    """Return canonical producers plus any additional Neo4j export nations."""
    countries = set(PRODUCER_NATIONS)
    driver = get_driver()
    if not driver:
        return sorted(countries)

    try:
        with driver.session() as session:
            result = session.run("MATCH (p:ExportPort) RETURN DISTINCT p.country AS c")
            countries.update(row["c"] for row in result if row["c"])
    except Exception as exc:
        logger.warning("Failed to fetch producer countries from Neo4j, using registry: %s", exc)

    return sorted(countries)

def _apply_tier_split(articles: list[dict[str, Any]], target_slots: int) -> list[dict[str, Any]]:
    """Applies a 60/20/20 tier split up to target_slots."""
    if target_slots <= 0:
        return []

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
        domain = art.get("domain", "").lower()
        if domain in TIER_1_GLOBAL:
            global_arts.append(art)
        elif domain in TIER_2_INDUSTRY:
            industry_arts.append(art)
        else:
            other_arts.append(art)

    # 60/20/20 target sizes
    target_global = int(target_slots * 0.6)
    target_industry = max(1, int(target_slots * 0.2)) if target_slots >= 2 else 0
    target_other = target_slots - target_global - target_industry

    kept_global = global_arts[:target_global]
    rem_global_slots = target_global - len(kept_global)

    target_industry += rem_global_slots
    kept_industry = industry_arts[:target_industry]
    rem_ind_slots = target_industry - len(kept_industry)

    target_other += rem_ind_slots
    kept_other = other_arts[:target_other]
    rem_other_slots = target_other - len(kept_other)

    if rem_other_slots > 0:
        extra_global = global_arts[len(kept_global):len(kept_global) + rem_other_slots]
        kept_global.extend(extra_global)
        rem_other_slots -= len(extra_global)

    if rem_other_slots > 0:
        extra_industry = industry_arts[len(kept_industry):len(kept_industry) + rem_other_slots]
        kept_industry.extend(extra_industry)

    return kept_global + kept_industry + kept_other


def _prefilter_articles(articles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Coarse pre-filter to drop noise before Gemini scoring.
    Splits by category and applies tier splitting within each category.
    """
    countries = [c.lower() for c in _get_producer_countries()]
    chokepoints = [c.lower() for c in _CHOKEPOINTS]
    broad_keywords = [
        "crude oil", "oil tanker", "lng carrier", "oil supply", "sanctions",
        "refinery", "pipeline", "production cut", "export ban", "troop buildup",
        "military drill", "invasion", "war", "conflict",
        # Physical-disruption vocabulary, so Query C's results survive relevance
        # filtering rather than being dropped for lacking conflict language.
        "storm", "hurricane", "cyclone", "typhoon", "fire", "explosion",
        "spill", "aground", "collision", "piracy", "hijack", "strike",
        "protest", "blockade", "shutdown", "outage",
    ]

    valid_articles = []
    for art in articles:
        title = art.get("title", "").lower()
        country_match = any(country in title for country in countries)
        chokepoint_match = any(chokepoint in title for chokepoint in chokepoints)
        keyword_match = any(keyword in title for keyword in broad_keywords)

        # Query B intentionally stays compact and searches all energy crises;
        # require a producer name in the title before assigning that category.
        if art.get("_category") == "producer_nation":
            if country_match:
                valid_articles.append(art)
        elif country_match or chokepoint_match or keyword_match:
            valid_articles.append(art)

    maritime_arts = [a for a in valid_articles if a.get("_category") == "chokepoint"]
    producer_arts = [a for a in valid_articles if a.get("_category") == "producer_nation"]
    physical_arts = [a for a in valid_articles if a.get("_category") == "physical"]

    target_maritime = GDELT_SLOTS_MARITIME
    target_producer = GDELT_SLOTS_PRODUCER

    # Reallocate if one category is short
    if len(maritime_arts) < target_maritime:
        target_producer += (target_maritime - len(maritime_arts))
    elif len(producer_arts) < target_producer:
        target_maritime += (target_producer - len(producer_arts))

    kept_maritime = _apply_tier_split(maritime_arts, target_maritime)
    kept_producer = _apply_tier_split(producer_arts, target_producer)
    # Only one query runs per cycle, so a physical batch never competes with the
    # other two for slots — but it must have its own bucket, or every article
    # from Query C would pass relevance and then be silently discarded here.
    kept_physical = _apply_tier_split(
        physical_arts, GDELT_SLOTS_MARITIME + GDELT_SLOTS_PRODUCER
    )

    filtered = kept_maritime + kept_producer + kept_physical

    logger.info(
        "[GDELT] Python pre-filter kept %d articles (Maritime: %d, Producer: %d, Physical: %d).",
        len(filtered), len(kept_maritime), len(kept_producer), len(kept_physical),
    )
    return filtered


def _parse_articles(raw: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Extract only the fields we need from raw GDELT article records."""
    parsed = []
    for item in raw:
        url = item.get("url", "").strip()
        if not url:
            continue
        parsed.append({
            "url":              url,
            "title":            item.get("title", "")[:500],   # Cap length
            "source":           item.get("domain", item.get("sourcecountry", "")),
            "article_category": item.get("_category", "general"),
        })
    return parsed

def _fetch_dual_query(timespan: str) -> list[dict[str, Any]]:
    """Fetch both Query A and Query B from GDELT, deduplicate by URL."""
    params_a = {**GDELT_PARAMS, "timespan": timespan}
    logger.info("gdelt_collector: querying GDELT Query A (Maritime) ...")
    raw_a = []
    try:
        raw_a = _query_gdelt(params_a)
        for art in raw_a:
            art["_category"] = "chokepoint"
    except Exception as exc:
        logger.error("gdelt_collector: Query A failed — %s", exc)

    time.sleep(5.5)  # GDELT asks high-traffic clients for >=5 seconds

    params_b = {
        **GDELT_PARAMS_PRODUCER,
        "query": _build_producer_query(),
        "timespan": timespan
    }
    logger.info("gdelt_collector: querying GDELT Query B (Producer) ...")
    raw_b = []
    try:
        raw_b = _query_gdelt(params_b)
        for art in raw_b:
            art["_category"] = "producer_nation"
    except Exception as exc:
        logger.error("gdelt_collector: Query B failed — %s", exc)

    # Explicit two-pass merge: producer_nation articles seed the dict first (lower priority),
    # then chokepoint articles overwrite on URL collision (higher priority).
    # This guarantees "chokepoint wins" structurally, not just by iteration-order accident.
    seen_urls: dict[str, dict] = {}
    for art in raw_b:  # producer_nation — lower priority
        if url := art.get("url", ""):
            seen_urls[url] = art
    for art in raw_a:  # chokepoint — higher priority, overwrites collisions
        if url := art.get("url", ""):
            seen_urls[url] = art

    return list(seen_urls.values())


def _fetch_live_query(
    timespan: str,
    category: str | None = None,
) -> list[dict[str, Any]]:
    """Run one alternating live query so GDELT's per-IP limit is respected."""
    if category is None:
        interval_seconds = max(
            60,
            int(os.getenv("CRON_INTERVAL_MINUTES", "15")) * 60,
        )
        slot = int(time.time() // interval_seconds)
        # Three-way rotation: one query per cycle keeps within GDELT's per-IP
        # limit, and the physical slot is what makes weather/accident/piracy/
        # protest incidents reachable at all.
        category = ("chokepoint", "producer_nation", "physical")[slot % 3]

    if category == "chokepoint":
        params = {**GDELT_PARAMS, "timespan": timespan}
        label = "A (Maritime)"
    elif category == "producer_nation":
        params = {**GDELT_PARAMS_PRODUCER, "timespan": timespan}
        label = "B (Producer)"
    elif category == "physical":
        params = {**GDELT_PARAMS_PHYSICAL, "timespan": timespan}
        label = "C (Physical)"
    else:
        raise ValueError(f"Unknown GDELT live category: {category}")

    logger.info("gdelt_collector: querying GDELT Query %s ...", label)
    articles = _query_gdelt(params)
    for article in articles:
        article["_category"] = category
    return articles

# ---------------------------------------------------------------------------
# Public Interface
# ---------------------------------------------------------------------------

def _classify_article(title: str) -> str | None:
    """Assign a fallback article to one of GDELT's two query categories.

    GDELT tags articles by *which query* returned them. The fallback providers
    run a single blended query, so the category has to be derived from the
    headline instead — without it the pre-filter's chokepoint/producer bucket
    split drops every fallback article on the floor.
    """
    lowered = (title or "").lower()
    if any(cp.lower() in lowered for cp in _CHOKEPOINTS):
        return "chokepoint"
    if any(country.lower() in lowered for country in _get_producer_countries()):
        return "producer_nation"
    return None


def _fetch_and_store_fallback() -> int:
    """Pull from the keyed providers and persist, reusing GDELT's pre-filter.

    Records carry the article's own `published_at`, so a delayed provider's
    headlines decay from when they were published rather than when we happened
    to ingest them.
    """
    from src.ingestion.news_providers import fetch_from_fallbacks

    records, provider = fetch_from_fallbacks()
    if not records:
        logger.warning("gdelt_collector: no fallback provider returned articles.")
        return 0

    # The pre-filter expects GDELT's field names; map onto them so relevance
    # scoring and the chokepoint/producer categorisation stay identical
    # regardless of which provider supplied the headline.
    as_gdelt = []
    for rec in records:
        category = _classify_article(rec["title"])
        if not category:
            continue          # Neither a chokepoint nor a producer story.
        as_gdelt.append({
            "url": rec["url"],
            "title": rec["title"],
            "domain": rec["source"],
            "_category": category,
            "_published_at": rec.get("published_at"),
        })

    if not as_gdelt:
        logger.info("gdelt_collector: no fallback article matched a tracked region.")
        return 0

    kept = _prefilter_articles(as_gdelt)
    parsed = _parse_articles(kept)
    for rec, original in zip(parsed, kept):
        rec["published_at"] = original.get("_published_at")

    if not parsed:
        logger.info("gdelt_collector: fallback articles all filtered out as irrelevant.")
        return 0

    count = upsert_news(parsed)
    logger.info("gdelt_collector: %d new records stored via %s.", count, provider)
    return count


def fetch_and_store(
    timespan: str | None = None,
    category: str | None = None,
    allow_fallback: bool = True,
) -> int:
    """
    Fetch latest energy-relevant news and persist to news_cache.

    GDELT is tried first — it is unauthenticated and unmetered. When it is
    rate-limited (its dominant failure mode), the keyed providers in
    news_providers take over rather than leaving the Sentinel with no input.
    """
    actual_timespan = timespan or GDELT_PARAMS.get("timespan", "15min")

    # A fetch failure propagates to the caller: returning 0 here made outages
    # indistinguishable from "no news", so the cron worker logged hours of
    # 429 rate-limit errors as "GDELT ✓ 0 new articles".
    try:
        merged = _fetch_live_query(actual_timespan, category=category)
    except Exception as exc:
        if not allow_fallback:
            raise
        logger.warning("gdelt_collector: GDELT unavailable (%s) - trying fallbacks.", exc)
        return _fetch_and_store_fallback()

    if not merged:
        logger.info("gdelt_collector: no new articles in selected live query.")
        return _fetch_and_store_fallback() if allow_fallback else 0

    merged = _prefilter_articles(merged)
    records = _parse_articles(merged)
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
    """
    params_a = {
        **GDELT_PARAMS,
        "startdatetime": startdatetime,
        "enddatetime": enddatetime
    }
    if "timespan" in params_a:
        del params_a["timespan"]

    logger.info("gdelt_collector: querying GDELT historical Query A (%s to %s) ...", startdatetime, enddatetime)
    raw_a = []
    try:
        raw_a = _query_gdelt(params_a)
        for art in raw_a:
            art["_category"] = "chokepoint"
    except Exception as exc:
        logger.error("gdelt_collector: historical Query A failed — %s", exc)

    time.sleep(5.5)

    params_b = {
        **GDELT_PARAMS_PRODUCER,
        "query": _build_producer_query(),
        "startdatetime": startdatetime,
        "enddatetime": enddatetime
    }
    if "timespan" in params_b:
        del params_b["timespan"]

    logger.info("gdelt_collector: querying GDELT historical Query B (%s to %s) ...", startdatetime, enddatetime)
    raw_b = []
    try:
        raw_b = _query_gdelt(params_b)
        for art in raw_b:
            art["_category"] = "producer_nation"
    except Exception as exc:
        logger.error("gdelt_collector: historical Query B failed — %s", exc)

    seen_urls: dict[str, dict] = {}
    for art in raw_a + raw_b:
        url = art.get("url", "")
        if url and url not in seen_urls:
            seen_urls[url] = art

    merged = list(seen_urls.values())
    filtered = _prefilter_articles(merged)
    return _parse_articles(filtered)


# ---------------------------------------------------------------------------
# CLI test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    n = fetch_and_store(timespan="1h")
    print(f"Stored {n} new articles.")
