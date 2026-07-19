"""
tests/test_news_fallback.py
───────────────────────────
Covers the fallback news providers that take over when GDELT is rate-limited.

GDELT is unauthenticated and unmetered but throttles hard per IP; a sustained
block previously left the Sentinel with no headlines at all. These tests pin
the behaviours that make the fallback safe rather than merely present.

No test performs a live HTTP request.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from src.ingestion import gdelt_collector as collector
from src.ingestion import news_providers as providers

NOW = datetime.now(timezone.utc)


def _article(url, title, published=None):
    return {
        "url": url,
        "title": title,
        "source": "example.com",
        "published_at": published,
        "article_category": "general",
    }


# ---------------------------------------------------------------------------
# Timestamp integrity — the correctness risk of a delayed provider
# ---------------------------------------------------------------------------

def test_publication_time_is_preserved_not_ingestion_time():
    """GNews lags ~12h and NewsAPI ~24h. Risk decay runs from this timestamp,
    so stamping a delayed article as "now" would score day-old news as
    breaking and inflate the index."""
    published = NOW - timedelta(hours=20)
    stored: list[dict] = []

    with (
        patch.object(collector, "_fetch_live_query", side_effect=collector.RateLimitError("429")),
        patch.object(
            providers, "fetch_from_fallbacks",
            return_value=([_article("https://x.test/1", "Strait of Hormuz tanker attack", published)], "gnews"),
        ),
        patch.object(collector, "upsert_news", side_effect=lambda recs: stored.extend(recs) or len(recs)),
    ):
        collector.fetch_and_store()

    assert stored, "article should have been stored"
    assert stored[0]["published_at"] == published


def test_iso_parser_normalises_provider_timestamp_formats():
    """NewsData returns 'YYYY-MM-DD HH:MM:SS', GNews/NewsAPI return ISO-Z."""
    from src.ingestion.news_providers import _iso

    spaced = _iso("2026-07-18 21:00:00")
    zulu = _iso("2026-07-18T21:00:00Z")
    assert spaced is not None and zulu is not None
    assert spaced.tzinfo is not None and zulu.tzinfo is not None
    assert spaced == zulu
    assert _iso(None) is None
    assert _iso("not a date") is None


# ---------------------------------------------------------------------------
# Fallback triggering
# ---------------------------------------------------------------------------

def test_gdelt_failure_triggers_fallback():
    with (
        patch.object(collector, "_fetch_live_query", side_effect=collector.RateLimitError("429")),
        patch.object(
            providers, "fetch_from_fallbacks",
            return_value=([_article("https://x.test/2", "Suez Canal convoy halted", NOW)], "newsdata"),
        ),
        patch.object(collector, "upsert_news", return_value=1),
    ):
        assert collector.fetch_and_store() == 1


def test_fallback_can_be_disabled_so_failures_stay_visible():
    """run_backtest and probes need the raw error, not a silent substitution."""
    with patch.object(collector, "_fetch_live_query", side_effect=collector.RateLimitError("429")):
        try:
            collector.fetch_and_store(allow_fallback=False)
        except collector.RateLimitError:
            return
    raise AssertionError("expected RateLimitError to propagate")


# ---------------------------------------------------------------------------
# Categorisation — fallback articles must land in GDELT's buckets
# ---------------------------------------------------------------------------

def test_articles_are_classified_into_gdelt_buckets():
    """GDELT tags by *which query* matched; the blended fallback query has no
    such tag, and an unclassified article is silently dropped by the
    pre-filter's chokepoint/producer split."""
    assert collector._classify_article("Tanker held at Strait of Hormuz") == "chokepoint"
    assert collector._classify_article("Russia halts crude oil exports") == "producer_nation"
    assert collector._classify_article("Local council debates parking") is None


def test_unclassifiable_fallback_articles_are_skipped_not_stored():
    with (
        patch.object(collector, "_fetch_live_query", side_effect=collector.RateLimitError("429")),
        patch.object(
            providers, "fetch_from_fallbacks",
            return_value=([_article("https://x.test/3", "Celebrity wedding photos", NOW)], "newsapi"),
        ),
        patch.object(collector, "upsert_news", return_value=99) as mock_upsert,
    ):
        assert collector.fetch_and_store() == 0
        mock_upsert.assert_not_called()


# ---------------------------------------------------------------------------
# Quota discipline
# ---------------------------------------------------------------------------

def test_providers_are_tried_freshest_first():
    """A 24h-delayed headline is near-worthless for a live index, so it is only
    reached when fresher sources returned nothing."""
    assert [p.name for p in providers.PROVIDERS] == ["newsdata", "gnews", "newsapi"]
    assert [p.delay_hours for p in providers.PROVIDERS] == [0, 12, 24]


def test_first_success_stops_the_chain():
    """A sustained GDELT outage should consume one provider's budget, not three."""
    calls: list[str] = []

    def track(name):
        def _fetch():
            calls.append(name)
            return [_article(f"https://x.test/{name}", "Suez Canal blocked", NOW)]
        return _fetch

    pool = [
        providers.Provider("newsdata", track("newsdata"), 200, 0),
        providers.Provider("gnews", track("gnews"), 100, 12),
    ]
    with (
        patch.object(providers, "PROVIDERS", pool),
        patch.object(providers, "provider_calls_today", return_value=0),
        patch.object(providers, "record_provider_call", lambda name: None),
    ):
        records, used = providers.fetch_from_fallbacks()

    assert used == "newsdata"
    assert calls == ["newsdata"], "should not have queried the second provider"
    assert len(records) == 1


def test_exhausted_provider_is_skipped():
    def boom():
        raise AssertionError("must not call a provider with no budget left")

    pool = [providers.Provider("newsdata", boom, daily_limit=200, delay_hours=0)]
    with (
        patch.object(providers, "PROVIDERS", pool),
        patch.object(providers, "provider_calls_today", return_value=200),
    ):
        records, used = providers.fetch_from_fallbacks()

    assert records == [] and used is None


def test_unknown_spend_fails_closed():
    """If the quota table cannot be read, treat the budget as gone rather than
    risk overrunning a hard daily cap."""
    from src.database import postgres_db

    with patch.object(postgres_db, "get_conn", side_effect=Exception("db down")):
        assert postgres_db.provider_calls_today("newsdata") > 1000
