"""Backtest endpoint contract. Replaces a script that ran a real backtest at
import time and only printed the result."""
from datetime import datetime, timezone
from unittest.mock import patch

from fastapi.testclient import TestClient

import api

client = TestClient(api.app)


def _event(day: int, sdi: float) -> dict:
    return {"created_at": datetime(2024, 1, day, tzinfo=timezone.utc), "sdi_score": sdi,
            "severity": 0.8, "region": "Red Sea", "disruption_type": "military_conflict", "summary": "s"}


def test_backtest_returns_a_series():
    events = [_event(d, 40 + d) for d in range(1, 6)]
    prices = [{"ticker": "BZ=F", "trade_date": f"2024-01-{d:02d}", "price_close": 75 + d} for d in range(1, 6)]
    with (
        patch.object(api, "fetch_risk_events_backtest", return_value=events),
        patch.object(api, "fetch_latest_prices", return_value=prices),
    ):
        r = client.get("/api/backtest/red_sea_attacks")
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body["series"], list) and body["series"]


def test_backtest_without_data_is_404():
    with patch.object(api, "fetch_risk_events_backtest", return_value=[]):
        r = client.get("/api/backtest/red_sea_attacks")
    assert r.status_code == 404
