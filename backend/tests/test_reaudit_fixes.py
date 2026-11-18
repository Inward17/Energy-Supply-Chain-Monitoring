"""Re-audit fixes: route eligibility, no-path handling, Malacca/Cape geometry,
blend exclusions, War Room route choice, client IP trust, test-DB guard."""
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

import api
from src.agents import fixer_agent as fixer
from src.utils import rate_limit


def _port(name, country, lat=25.0, lon=55.0):
    return {"name": name, "country": country, "grade": "Test Grade", "api_gravity": 33.4,
            "sulphur_pct": 1.77, "baseline_days_to_india": 15, "lat": lat, "lon": lon,
            "congestion_score": 0.3, "transit_chokepoints": []}


def _run(ports, route_by_port, *, excluded=None, mode="cost"):
    """find_alternatives with I/O mocked; route_by_port maps port name -> (days, basis)."""
    by_lat_lon = {(p["lon"], p["lat"]): route_by_port[p["name"]] for p in ports}

    def route(port_lon, port_lat, *_a, **_k):
        return by_lat_lon[(port_lon, port_lat)]

    with (
        patch.object(fixer, "find_export_ports_bypassing", return_value=ports),
        patch.object(fixer, "find_alternative_routes", return_value=[]),
        patch.object(fixer, "score_alternatives", return_value={"resilience_score": 0.5, "alternatives": []}),
        patch.object(fixer, "fetch_risk_events", return_value=[]),
        patch.object(fixer, "fetch_latest_prices", return_value=[{"price_close": 75.0, "trade_date": "2026-11-01"}]),
        patch.object(fixer, "get_refinery_coords", return_value={"lat": 22.3, "lon": 69.85, "country": "India"}),
        patch.object(fixer, "match_refineries_to_crude", return_value=[]),
        patch.object(fixer, "get_grade_suppliers", return_value=[]),
        patch.object(fixer, "get_crude_specs", return_value=None),
        patch.object(fixer, "_route_lead_time", side_effect=route),
    ):
        return fixer.find_alternatives(blocked_chokepoint="Suez Canal", excluded_countries=excluded,
                                       ranking_mode=mode)


# ── route eligibility ─────────────────────────────────────────────────────────

def test_unverified_route_is_never_recommended_even_if_faster():
    ports = [_port("Fast", "Norway", 1, 1), _port("Slow", "Brazil", 2, 2)]
    res = _run(ports, {"Fast": (5.0, "unverified"), "Slow": (30.0, "verified")}, mode="speed")
    pm = res["procurement_matrix"]
    assert [r["export_port"] for r in pm] == ["Slow", "Fast"]  # verified tier first
    assert pm[0]["recommended"] is True and pm[1]["recommended"] is False


def test_no_verified_route_means_no_recommendation():
    ports = [_port("A", "Norway", 1, 1), _port("B", "Brazil", 2, 2)]
    res = _run(ports, {"A": (5.0, "unverified"), "B": (9.0, "estimated")})
    assert not any(r["recommended"] for r in res["procurement_matrix"])
    assert res["diagnostic"]["reason"] == "no_verified_route"


def test_no_path_around_blockade_is_not_a_zero_day_verified_route():
    no_path = {"properties": {"length": 0.0}, "geometry": {"coordinates": []}}
    open_route = {"properties": {"length": 1000.0}, "geometry": {"coordinates": [[50, 26], [69, 22]]}}

    def fake(*_a, restrictions=None, **_k):
        return no_path if restrictions and "ormuz" in restrictions else open_route

    with patch.object(fixer.sr, "searoute", side_effect=fake):
        days, basis = fixer._route_lead_time(50.16, 26.65, 69.85, 22.3, blocked_chokepoint="Strait of Hormuz")
    assert basis == "unverified"
    assert days > 0


@pytest.mark.parametrize("coords,expected", [
    ([[60.0, 20.0], [80.0, 5.0], [110.0, 10.0]], "verified"),      # stays out of the Malacca box
    ([[60.0, 20.0], [100.5, 3.0], [110.0, 10.0]], "unverified"),   # passes through it
])
def test_malacca_is_checked_by_route_geometry(coords, expected):
    with patch.object(fixer, "_sea_route", return_value=(5000.0, coords)):
        _, basis = fixer._route_lead_time(60, 20, 110, 10, extra_detour_days=4,
                                          blocked_chokepoint="Strait of Malacca")
    assert basis == expected


def test_cape_crossing_route_is_unverified():
    coords = [[5.0, 4.0], [18.5, -34.8], [70.0, 22.0]]
    with patch.object(fixer, "_sea_route", return_value=(15000.0, coords)):
        _, basis = fixer._route_lead_time(5, 4, 70, 22, blocked_chokepoint="Cape of Good Hope")
    assert basis == "unverified"


# ── blend exclusions ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("excluded,kept", [
    (["Iran"], []),
    (["Iraq"], []),
    (["Iran", "Iraq"], []),
    (["iran "], []),           # case and whitespace normalised
    (["Kuwait"], ["Iran + Iraq"]),
])
def test_blend_is_excluded_if_any_leg_is_excluded(excluded, kept):
    ports = [_port("Blend", "Iran + Iraq", 1, 1)]
    res = _run(ports, {"Blend": (10.0, "verified")}, excluded=excluded)
    assert [r["country"] for r in res["procurement_matrix"]] == kept


def test_unrelated_blend_survives():
    res = _run([_port("Blend", "Iraq + UAE", 1, 1)], {"Blend": (10.0, "verified")}, excluded=["Iran"])
    assert [r["country"] for r in res["procurement_matrix"]] == ["Iraq + UAE"]


# ── War Room picks a verified route or none ──────────────────────────────────

def test_war_room_skips_spr_without_a_verified_route():
    result = {"procurement_matrix": [{"export_port": "X", "lead_time_days": 3.0, "route_basis": "unverified"}],
              "diagnostic": {"reason": "no_verified_route", "message": "m"}}
    spr = MagicMock()
    with (
        patch.object(api, "find_alternatives", return_value=result),
        patch.object(api, "calculate_spr_impact", spr),
    ):
        api._war_room_limit.reset()
        r = TestClient(api.app).post("/api/orchestrator/war-room", json={
            "scenario_name": "S", "blocked_chokepoint": "Strait of Hormuz", "disrupted_volume_mbpd": 1.0})
    assert r.status_code == 200
    assert r.json()["diagnostic"]["reason"] == "no_verified_route"
    spr.assert_not_called()


# ── client IP trust ───────────────────────────────────────────────────────────

def _request(headers, peer="10.0.0.5"):
    req = MagicMock()
    req.headers = {k.lower(): v for k, v in headers.items()}
    req.client.host = peer
    return req


def test_forwarded_for_is_never_trusted(monkeypatch):
    monkeypatch.delenv("TRUSTED_PROXY", raising=False)
    assert rate_limit.client_ip(_request({"X-Forwarded-For": "1.2.3.4"})) == "10.0.0.5"


def test_cf_header_only_behind_cloudflare(monkeypatch):
    req = _request({"CF-Connecting-IP": "9.9.9.9"})
    monkeypatch.setenv("TRUSTED_PROXY", "cloudflare")
    assert rate_limit.client_ip(req) == "9.9.9.9"
    monkeypatch.setenv("TRUSTED_PROXY", "none")
    assert rate_limit.client_ip(req) == "10.0.0.5"


# ── test database guard ──────────────────────────────────────────────────────

def test_remote_database_is_refused_without_opt_in(monkeypatch):
    from tests import conftest

    monkeypatch.setenv("DB_HOST", "ep-prod-123.eu-central-1.aws.neon.tech")
    monkeypatch.delenv("TEST_DB_ALLOW_REMOTE", raising=False)
    with pytest.raises(pytest.exit.Exception):
        conftest._check_postgres_target()
    monkeypatch.setenv("TEST_DB_ALLOW_REMOTE", "1")
    conftest._check_postgres_target()  # explicit opt-in passes
