"""Rate-limiter memory, backtest lead-time semantics, War Room brief evidence."""
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

import api
from src.agents import briefing_agent
from src.utils import rate_limit
from src.utils.rate_limit import RateLimiter


def _req(ip):
    r = MagicMock()
    r.headers = {"cf-connecting-ip": ip}
    r.client.host = ip
    return r


# ── rate limiter ─────────────────────────────────────────────────────────────

def test_idle_clients_are_forgotten(monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr(rate_limit.time, "monotonic", lambda: clock[0])
    rl = RateLimiter("t", per_client=5, global_limit=10_000, window_s=60)
    for i in range(500):
        rl.check(_req(f"10.0.{i // 250}.{i % 250}"))
    assert rl.tracked_clients() == 500
    clock[0] += 120  # every client idle for two windows
    rl.check(_req("10.9.9.9"))
    assert rl.tracked_clients() == 1


def test_rejected_requests_allocate_nothing(monkeypatch):
    monkeypatch.setattr(rate_limit.time, "monotonic", lambda: 5.0)
    rl = RateLimiter("t", per_client=5, global_limit=2, window_s=60)
    rl.check(_req("1.1.1.1"))
    rl.check(_req("1.1.1.2"))
    for i in range(100):
        with pytest.raises(HTTPException):
            rl.check(_req(f"2.2.2.{i}"))
    assert rl.tracked_clients() == 2


# ── backtest lead time ──────────────────────────────────────────────────────

def _bt(sdi_by_day, prices_by_day):
    events = [{"created_at": datetime(2024, 1, d, tzinfo=timezone.utc), "sdi_score": s,
               "severity": 0.8, "confidence": 1.0} for d, s in sdi_by_day.items()]
    prices = [{"ticker": "BZ=F", "trade_date": f"2024-01-{d:02d}", "price_close": p}
              for d, p in prices_by_day.items()]
    with (
        patch.object(api, "fetch_risk_events_backtest", return_value=events),
        patch.object(api, "fetch_latest_prices", return_value=prices),
    ):
        return TestClient(api.app).get("/api/backtest/red_sea_attacks?sdi_threshold=65").json()


FLAT = {d: 75.0 for d in range(1, 21)}


def test_missing_breakout_is_null_not_zero():
    body = _bt({d: (80.0 if d == 18 else 20.0) for d in range(1, 21)}, FLAT)
    assert body["lead_time_days"] is None
    assert body["missing_observations"] == ["market_reaction"]
    assert "never broke out" in body["verdict"]


def test_nothing_observed_names_both():
    body = _bt({d: 20.0 for d in range(1, 21)}, FLAT)
    assert body["lead_time_days"] is None
    assert body["missing_observations"] == ["alert", "market_reaction"]
    assert all(s["lead_time_days"] is None for s in body["threshold_sensitivity"])


def test_methodology_states_three_signals():
    body = _bt({d: 20.0 for d in range(1, 21)}, FLAT)
    assert body["signals"] == 3 and "3-signal" in body["methodology"]


# ── brief evidence ──────────────────────────────────────────────────────────

def test_brief_prompt_carries_freshness_graph_route_and_assumptions():
    captured = {}

    def fake(client, prompt, *, temperature):
        captured["prompt"] = prompt
        return MagicMock(text="brief")

    import pandas as pd
    spr = {"survival_days": 18, "supply_gap_days": 12, "recommendation": "r",
           "macro_infl_impact": "+1%", "macro_gdp_impact_pct": "-1%"}
    evidence = {"newest_event_at": "2026-10-24", "market_close": "2026-11-13", "ais_status": "unavailable",
                "graph_status": "seed", "route_basis": "verified", "spr_assumptions": ["Reserve starts full"]}
    with (
        patch.dict("os.environ", {"GEMINI_API_KEY": "k"}),
        patch.object(briefing_agent, "genai"),
        patch.object(briefing_agent, "generate_with_fallback", side_effect=fake),
    ):
        briefing_agent.generate_emergency_brief("S", "Jamnagar", spr, pd.DataFrame(), evidence=evidence)
    p = captured["prompt"]
    for needle in ("2026-10-24", "2026-11-13", "seed data (not live)", "verified", "Reserve starts full",
                   "do not invent numbers"):
        assert needle in p
