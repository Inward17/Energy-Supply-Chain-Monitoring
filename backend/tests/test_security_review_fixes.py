"""
tests/test_security_review_fixes.py
───────────────────────────────────
Regressions for the second security review: spend controls, key leakage,
error-text leakage, input bounds and the backtest list contract.
"""
from __future__ import annotations

import logging

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

import api
from run_backtest import pick_day_event
from src.database.postgres_db import DatabaseUnavailable
from src.utils.rate_limit import RateLimiter
from src.utils.schemas import BacktestRequest


@pytest.fixture
def client():
    return TestClient(api.app)


# ── Input bounds ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize("limit", ["0", "-1", "201", "100000000"])
def test_risk_events_limit_is_bounded(client, limit):
    assert client.get(f"/api/risk/events?limit={limit}").status_code == 422


def test_backtest_event_is_a_closed_set():
    with pytest.raises(ValidationError):
        BacktestRequest(event_name="anything_else")
    assert BacktestRequest(event_name="red_sea_attacks").event_name == "red_sea_attacks"


# ── Spend controls ────────────────────────────────────────────────────────────

class _Req:
    def __init__(self, ip: str):
        self.headers = {"cf-connecting-ip": ip}
        self.client = None


def test_rate_limiter_per_client_and_global():
    rl = RateLimiter("t", per_client=2, global_limit=3, window_s=60)
    rl.check(_Req("a"))
    rl.check(_Req("a"))
    with pytest.raises(Exception) as e:
        rl.check(_Req("a"))
    assert e.value.status_code == 429
    rl.check(_Req("b"))                       # 3rd hit overall
    with pytest.raises(Exception) as e:       # global cap holds even for a new IP
        rl.check(_Req("c"))
    assert e.value.status_code == 429


def test_war_room_is_rate_limited(client, monkeypatch):
    api._war_room_limit.reset()
    monkeypatch.setattr(api, "find_alternatives", lambda **_: {"procurement_matrix": [], "diagnostic": {"reason": "x"}})
    body = {"scenario_name": "S", "blocked_chokepoint": "Strait of Hormuz", "disrupted_volume_mbpd": 1.0}
    codes = [client.post("/api/orchestrator/war-room", json=body).status_code for _ in range(6)]
    assert codes[:5] == [200] * 5 and codes[5] == 429
    api._war_room_limit.reset()


def test_war_room_brief_is_cached():
    calls = []
    build = lambda: calls.append(1) or "Brief text"
    key = ("cache-test",)
    assert api._cached_brief(key, build) == "Brief text"
    assert api._cached_brief(key, build) == "Brief text"
    assert len(calls) == 1


# ── Error-text leakage ────────────────────────────────────────────────────────

def test_backtest_errors_are_reduced_to_fixed_messages():
    assert api._public_backtest_error("'list' object has no attribute 'get'") == api._BACKTEST_ERRORS["internal"]
    assert api._public_backtest_error("Gemini API daily quota likely exhausted.") == api._BACKTEST_ERRORS["quota"]
    assert api._public_backtest_error(None) is None


def test_database_outage_is_503_not_empty_data(client, monkeypatch):
    def down(**_):
        raise DatabaseUnavailable("fetch_risk_events")
    monkeypatch.setattr(api, "fetch_risk_events", down)
    r = client.get("/api/risk/events")
    assert r.status_code == 503
    assert "fetch_risk_events" not in r.text


# ── Key leakage ───────────────────────────────────────────────────────────────

def test_httpx_request_urls_are_not_logged():
    assert logging.getLogger("httpx").getEffectiveLevel() >= logging.WARNING


def test_provider_failure_log_omits_url(monkeypatch, caplog):
    from src.ingestion import news_providers as np_

    secret = "sekret-key-123"

    def boom():
        req = httpx.Request("GET", f"https://newsdata.io/api/1/latest?apikey={secret}")
        raise httpx.HTTPStatusError("bad", request=req, response=httpx.Response(429, request=req))

    provider = np_.Provider("newsdata", boom, daily_limit=10, delay_hours=0)
    monkeypatch.setattr(provider, "budget_remaining", lambda: 10)
    monkeypatch.setattr(np_, "PROVIDERS", [provider])
    monkeypatch.setattr(np_, "record_provider_call", lambda _: None)
    with caplog.at_level(logging.WARNING):
        np_.fetch_from_fallbacks()
    assert secret not in caplog.text
    assert "HTTP 429" in caplog.text


# ── Backtest list contract ────────────────────────────────────────────────────

def test_pick_day_event_takes_most_severe():
    events = [{"severity": 0.2, "region": "A"}, {"severity": 0.9, "region": "B"}]
    assert pick_day_event(events)["region"] == "B"
    assert pick_day_event([]) is None
    assert pick_day_event(None) is None
    assert pick_day_event({"severity": 0.5}) == {"severity": 0.5}
