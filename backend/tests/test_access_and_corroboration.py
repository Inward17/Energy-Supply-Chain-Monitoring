"""Admin key on backtests, shared daily Gemini budget, corroboration rule."""
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

import api
from src.agents import sentinel_agent as sentinel
from src.database.postgres_db import try_consume_daily_quota

client = TestClient(api.app)


# ── admin key ────────────────────────────────────────────────────────────────

def _trigger(headers=None):
    api._backtest_limit.reset()
    with (
        patch.object(api, "create_backtest_job", return_value=7),
        patch.object(api, "dispatch_backtest", return_value=True),
    ):
        return client.post("/api/backtest/trigger", json={"event_name": "red_sea_attacks"}, headers=headers or {})


def test_backtests_disabled_without_configured_key(monkeypatch):
    monkeypatch.setattr(api, "ADMIN_API_KEY", "")
    assert _trigger({"X-Admin-Key": "anything"}).status_code == 403


def test_backtest_requires_matching_key(monkeypatch):
    monkeypatch.setattr(api, "ADMIN_API_KEY", "s3cret-key")
    assert _trigger().status_code == 401
    assert _trigger({"X-Admin-Key": "wrong"}).status_code == 401
    assert _trigger({"X-Admin-Key": "s3cret-key"}).status_code == 200


# ── shared daily budget ──────────────────────────────────────────────────────

def test_daily_quota_is_atomic_and_capped():
    name = "test:quota-cap"
    assert [try_consume_daily_quota(name, 2) for _ in range(4)] == [True, True, False, False]
    assert try_consume_daily_quota("test:zero", 0) is False


def test_brief_budget_spent_skips_gemini(monkeypatch):
    build = MagicMock(return_value="brief")
    monkeypatch.setattr(api, "try_consume_daily_quota", lambda *_: False)
    api._brief_cache.clear()
    text = api._cached_brief(("k-budget",), build)
    build.assert_not_called()
    assert "budget" in text


def test_cache_hit_spends_nothing(monkeypatch):
    spend = MagicMock(return_value=True)
    monkeypatch.setattr(api, "try_consume_daily_quota", spend)
    api._brief_cache.clear()
    api._cached_brief(("k-cache",), lambda: "brief")
    api._cached_brief(("k-cache",), lambda: "brief")
    assert spend.call_count == 1


# ── corroboration ────────────────────────────────────────────────────────────

def _rows(*urls):
    return [{"url": u} for u in urls]


@pytest.mark.parametrize("severity,rows,verified,expected", [
    (0.5, _rows("https://a.com/1"), True, (0.5, None)),                                   # below threshold
    (0.9, _rows("https://a.com/1"), True, (0.6, False)),                                  # one site
    (0.9, _rows("https://www.a.com/1", "https://a.com/2"), True, (0.6, False)),           # same site twice
    (0.9, _rows("https://a.com/1", "https://b.org/2"), True, (0.9, True)),                # two sites
    (0.9, _rows("https://a.com/1", "https://b.org/2", "https://c.net/3"), False, (0.6, False)),  # batch context
])
def test_corroboration_rule(severity, rows, verified, expected):
    assert sentinel.corroborate(severity, rows, verified) == expected


def test_sentinel_caps_uncorroborated_event():
    batch = [{"id": 1, "title": "Tanker hit near Hormuz", "url": "https://one.example/a",
              "fetched_at": datetime.now(timezone.utc), "article_category": "chokepoint"}]
    scored = [{"region": "Persian Gulf", "disruption_type": "military_conflict", "severity": 0.92,
               "confidence": 0.9, "summary": "s", "severity_reasoning": "r", "headline_indices": [1]}]
    written = []
    with (
        patch.object(sentinel, "fetch_unprocessed_news", return_value=batch),
        patch.object(sentinel, "_select_balanced_batch", return_value=batch),
        patch.object(sentinel, "_call_gemini", return_value=scored),
        patch.object(sentinel, "upsert_risk_event", side_effect=written.append),
        patch.object(sentinel, "mark_news_processed", lambda ids: None),
        patch.dict("os.environ", {"GEMINI_API_KEY": "k"}),
    ):
        sentinel.process_unprocessed_batch()
    assert written[0]["severity"] == 0.6
    assert written[0]["corroborated"] is False
    assert written[0]["severity_reasoning"].startswith("[Uncorroborated: model scored 0.92")
