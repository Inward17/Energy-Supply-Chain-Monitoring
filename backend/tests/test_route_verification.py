"""Reroute must prove the actual voyage avoids the blocked passage."""
from unittest.mock import patch

from src.agents import fixer_agent as fixer
from src.database.neo4j_graph import _fallback_export_ports


def test_restriction_is_applied_even_when_static_detour_is_zero():
    calls = []

    def fake_sea_km(*args):
        restriction = args[4] if len(args) > 4 else None
        calls.append(restriction)
        return 5000.0

    with patch.object(fixer, "_sea_km", side_effect=fake_sea_km):
        _, basis = fixer._route_lead_time(50.0, 26.0, 69.85, 22.3, extra_detour_days=0,
                                          blocked_chokepoint="Strait of Hormuz")
    assert calls == ["ormuz"]
    assert basis == "verified"


def test_restricted_route_replaces_unrestricted_one():
    """Ras Tanura -> Rotterdam with Suez blocked must go around the Cape."""
    open_days, _ = fixer._route_lead_time(50.16, 26.65, 4.3, 51.95)
    blocked_days, basis = fixer._route_lead_time(50.16, 26.65, 4.3, 51.95, blocked_chokepoint="Suez Canal")
    assert basis == "verified"
    assert blocked_days > open_days + 10


def test_unsupported_restriction_is_labelled_unverified():
    with patch.object(fixer, "_sea_km", return_value=5000.0):
        days, basis = fixer._route_lead_time(50.0, 26.0, 129.3, 35.5, extra_detour_days=4,
                                             blocked_chokepoint="Strait of Malacca")
    assert basis == "unverified"
    assert days > 4  # static detour still added


def test_failed_restriction_falls_back_to_unverified():
    def fake_sea_km(*args):
        restriction = args[4] if len(args) > 4 else None
        if restriction:
            raise ValueError("no route")
        return 5000.0

    with patch.object(fixer, "_sea_km", side_effect=fake_sea_km):
        _, basis = fixer._route_lead_time(50.0, 26.0, 4.3, 51.9, blocked_chokepoint="Suez Canal")
    assert basis == "unverified"


def test_zero_coordinates_are_routed_not_estimated():
    from tests.test_risk_aggregation import _make_port, _run_with_mocks

    port = {**_make_port("Equator Terminal", "Gabon"), "lat": 0.0, "lon": 9.0}
    row = _run_with_mocks([port], [])["procurement_matrix"][0]
    assert row["route_basis"] == "verified"  # went through the (mocked) route engine
    assert row["lead_time_days"] == 15.0


def test_fallback_ports_have_coordinates_and_respect_blockade():
    rows = _fallback_export_ports("Strait of Hormuz")
    assert rows
    assert all(r["lat"] is not None and r["lon"] is not None for r in rows)
    assert all("Strait of Hormuz" not in r["transit_chokepoints"] for r in rows)
    assert all(r["grade"] == "Brent" for r in _fallback_export_ports("Strait of Hormuz", "Brent"))


def test_estimated_lead_time_uses_port_baseline_for_india():
    port = {"baseline_days_to_india": 22}
    assert fixer._estimated_lead_time(port, "India", 2) == 24.0
    assert fixer._estimated_lead_time(port, "Netherlands", 0) != 22.0
