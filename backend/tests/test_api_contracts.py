"""Failures are HTTP errors, not rows in a 200 array; missing prices are null."""
from unittest.mock import patch

from fastapi.testclient import TestClient

import api

client = TestClient(api.app)


def test_degraded_chokepoint_matrix_is_503():
    with patch.object(api, "compute_chokepoint_risk_matrix", side_effect=ValueError("no data")):
        r = client.get("/api/risk/chokepoints")
    assert r.status_code == 503


def test_degraded_producer_matrix_is_503():
    with patch.object(api, "compute_producer_country_risk_matrix", side_effect=ValueError("no data")):
        r = client.get("/api/risk/producers")
    assert r.status_code == 503


def test_degraded_live_metrics_is_503():
    with patch.object(api, "compute_current_sdi", side_effect=ValueError("no data")):
        r = client.get("/api/metrics/live")
    assert r.status_code == 503


def test_instrument_without_observations_is_unavailable_not_zero():
    stats = {"current_price": None, "rolling_mean": None, "rolling_std": None}
    with (
        patch.object(api, "fetch_latest_prices", return_value=[]),
        patch.object(api, "get_brent_rolling_stats", return_value=stats),
    ):
        r = client.get("/api/market/prices")
    assert r.status_code == 200
    for inst in r.json()["instruments"]:
        assert inst["available"] is False
        assert inst["price"] is None
