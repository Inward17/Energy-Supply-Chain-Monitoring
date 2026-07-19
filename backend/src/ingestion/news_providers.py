"""
src/ingestion/news_providers.py
────────────────────────────────
Fallback news sources for when GDELT is rate-limited.

GDELT is the primary collector — it is unauthenticated and unmetered — but it
throttles aggressively per IP, and a sustained block starves the Sentinel of
headlines entirely. These providers cover that gap.

Each provider is wrapped to a common record shape so the collector and the
Sentinel do not care which one supplied a headline:

    {url, title, source, published_at, article_category}

`published_at` is the article's own publication time, never ingestion time.
Risk decay in modeler_agent runs from that timestamp, so a provider that serves
delayed articles must not have them recorded as breaking news.

Free-tier characteristics that shape the ordering below:

    NewsData.io   200 req/day   real-time
    GNews         100 req/day   ~12h delay,  10 articles/request
    NewsAPI.org   100 req/day   ~24h delay,  non-commercial use only

Providers are therefore tried freshest-first: a 24h-delayed headline is close
to worthless for a live disruption index and is only worth having when nothing
else responded.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any, Callable

import httpx
from dotenv import load_dotenv

from src.database.postgres_db import provider_calls_today, record_provider_call

load_dotenv()
logger = logging.getLogger(__name__)

_TIMEOUT = 25.0

#: Query terms shared across providers. Deliberately broader than the GDELT
#: chokepoint query: these providers are the fallback when GDELT is blocked, so
#: they need to cover producer-nation supply events too (the gap that left
#: Russia unscored while its refinery outages sat unreported).
SEARCH_TERMS = (
    "crude oil OR oil exports OR oil pipeline OR oil refinery OR "
    "LNG OR tanker OR Strait of Hormuz OR Suez Canal OR OPEC"
)

#: NewsData.io rejects a long `q` with HTTP 422 (its free tier caps query
#: length), so it gets a trimmed variant of the same intent.
SEARCH_TERMS_SHORT = "crude oil OR oil exports OR oil pipeline OR tanker"


def _iso(value: str | None) -> datetime | None:
    """Parse a provider timestamp into an aware UTC datetime."""
    if not value:
        return None
    text = str(value).strip().replace("Z", "+00:00")
    for candidate in (text, text.replace(" ", "T")):
        try:
            parsed = datetime.fromisoformat(candidate)
        except ValueError:
            continue
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    logger.debug("news_providers: unparseable timestamp %r", value)
    return None


def _record(url: str, title: str, source: str, published: str | None) -> dict[str, Any] | None:
    url = (url or "").strip()
    title = (title or "").strip()
    if not url or not title:
        return None
    return {
        "url": url,
        "title": title[:500],
        "source": (source or "").strip()[:120],
        "published_at": _iso(published),
        # Categorised downstream by the collector's existing pre-filter.
        "article_category": "general",
    }


# ---------------------------------------------------------------------------
# Individual providers
# ---------------------------------------------------------------------------

def fetch_newsdata() -> list[dict[str, Any]]:
    """NewsData.io — real-time, 200 requests/day."""
    key = os.getenv("NEWSDATA_API_KEY", "").strip()
    if not key:
        return []
    response = httpx.get(
        "https://newsdata.io/api/1/latest",
        params={"apikey": key, "q": SEARCH_TERMS_SHORT, "language": "en"},
        timeout=_TIMEOUT,
    )
    response.raise_for_status()
    payload = response.json()
    out = []
    for item in payload.get("results") or []:
        record = _record(
            item.get("link", ""),
            item.get("title", ""),
            item.get("source_id", "newsdata"),
            item.get("pubDate"),
        )
        if record:
            out.append(record)
    return out


def fetch_gnews() -> list[dict[str, Any]]:
    """GNews — ~12h delayed on the free tier, 100 requests/day."""
    key = os.getenv("GNEWS_API_KEY", "").strip()
    if not key:
        return []
    response = httpx.get(
        "https://gnews.io/api/v4/search",
        params={"q": SEARCH_TERMS, "apikey": key, "lang": "en", "max": 10},
        timeout=_TIMEOUT,
    )
    response.raise_for_status()
    payload = response.json()
    out = []
    for item in payload.get("articles") or []:
        record = _record(
            item.get("url", ""),
            item.get("title", ""),
            (item.get("source") or {}).get("name", "gnews"),
            item.get("publishedAt"),
        )
        if record:
            out.append(record)
    return out


def fetch_newsapi() -> list[dict[str, Any]]:
    """NewsAPI.org — ~24h delayed on the free tier, 100 requests/day."""
    key = os.getenv("NEWSAPI_API_KEY", "").strip()
    if not key:
        return []
    response = httpx.get(
        "https://newsapi.org/v2/everything",
        params={
            "q": SEARCH_TERMS,
            "apiKey": key,
            "language": "en",
            "pageSize": 20,
            "sortBy": "publishedAt",
        },
        timeout=_TIMEOUT,
    )
    response.raise_for_status()
    payload = response.json()
    out = []
    for item in payload.get("articles") or []:
        record = _record(
            item.get("url", ""),
            item.get("title", ""),
            (item.get("source") or {}).get("name", "newsapi"),
            item.get("publishedAt"),
        )
        if record:
            out.append(record)
    return out


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

class Provider:
    def __init__(self, name: str, fetch: Callable[[], list[dict[str, Any]]], daily_limit: int, delay_hours: int):
        self.name = name
        self.fetch = fetch
        self.daily_limit = daily_limit
        self.delay_hours = delay_hours

    def budget_remaining(self) -> int:
        return self.daily_limit - provider_calls_today(self.name)


#: Freshest first — see the module docstring.
PROVIDERS: list[Provider] = [
    Provider("newsdata", fetch_newsdata, daily_limit=200, delay_hours=0),
    Provider("gnews", fetch_gnews, daily_limit=100, delay_hours=12),
    Provider("newsapi", fetch_newsapi, daily_limit=100, delay_hours=24),
]


def fetch_from_fallbacks() -> tuple[list[dict[str, Any]], str | None]:
    """Try each provider in freshness order until one returns articles.

    Stops at the first success rather than querying them all, so a sustained
    GDELT outage consumes one provider's budget instead of three.

    Returns (records, provider_name).
    """
    for provider in PROVIDERS:
        remaining = provider.budget_remaining()
        if remaining <= 0:
            logger.info("news_providers: %s daily budget spent, skipping.", provider.name)
            continue
        try:
            record_provider_call(provider.name)
            records = provider.fetch()
        except Exception as exc:
            logger.warning("news_providers: %s failed - %s", provider.name, exc)
            continue
        if records:
            logger.info(
                "news_providers: %s returned %d articles (%d calls left today).",
                provider.name,
                len(records),
                remaining - 1,
            )
            return records, provider.name
        logger.info("news_providers: %s returned nothing.", provider.name)
    return [], None
