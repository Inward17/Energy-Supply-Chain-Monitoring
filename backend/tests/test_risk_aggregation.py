"""
tests/test_risk_aggregation.py
──────────────────────────────
Regression tests for the additive-accumulator-instead-of-max() risk scoring
bug discovered during code review (Issue #2).

The bug: fixer_agent used `risk_score = min(0.95, risk_score + severity*confidence)`
so any country appearing in 2+ moderate-severity events would always be pushed
to exactly 0.95 — producing the identical-score bucketing visible in the
Producer Risk Matrix screenshots.

The fix: `risk_score = max(risk_score, severity * confidence)` followed by
a single `min(0.95, risk_score)` clamp.

These tests ensure this regression never silently re-enters the codebase.
"""
from __future__ import annotations

import pytest
from unittest.mock import patch


def _make_port(name: str, country: str, api: float = 33.4, sulphur: float = 1.77) -> dict:
    return {
        "name": name,
        "country": country,
        "grade": "Test Grade",
        "api_gravity": api,
        "sulphur_pct": sulphur,
        "baseline_days_to_india": 15,
        "lat": 25.0,
        "lon": 55.0,
        "congestion_score": 0.3,
        "transit_chokepoints": [],
    }


def _make_event(region: str, severity: float, confidence: float = 1.0) -> dict:
    return {
        "region": region,
        "summary": f"Event in {region}",
        "severity": severity,
        "confidence": confidence,
        "affected_chokepoints": [],
        "created_at": "2026-07-10T12:00:00+00:00",
    }


def _run_with_mocks(viable_ports, all_events, brent=75.0):
    """Run find_alternatives with all external I/O mocked out."""
    from src.agents.fixer_agent import find_alternatives

    with (
        patch("src.agents.fixer_agent.find_export_ports_bypassing", return_value=viable_ports),
        patch("src.agents.fixer_agent.find_alternative_routes", return_value=[]),
        patch("src.agents.fixer_agent.score_alternatives", return_value={"resilience_score": 0.5, "alternatives": []}),
        patch("src.agents.fixer_agent.fetch_risk_events", return_value=all_events),
        patch("src.agents.fixer_agent.fetch_latest_prices", return_value=[{"price_close": brent, "trade_date": "2026-07-10"}]),
        patch("src.agents.fixer_agent.get_refinery_coords", return_value={"lat": 22.3, "lon": 69.85}),
        patch("src.agents.fixer_agent.match_refineries_to_crude", return_value=[]),
        patch("src.agents.fixer_agent.get_grade_suppliers", return_value=[]),
        patch("src.agents.fixer_agent.get_crude_specs", return_value=None),
        patch("src.agents.fixer_agent._compute_lead_time", return_value=15.0),
    ):
        return find_alternatives(blocked_chokepoint="Suez Canal")


# ---------------------------------------------------------------------------
# Regression tests
# ---------------------------------------------------------------------------

def test_single_event_risk_equals_severity_times_confidence():
    """Single event: risk_score should equal severity * confidence (above 0.05 baseline)."""
    ports  = [_make_port("Port Alpha", "TestCountry")]
    events = [_make_event("TestCountry region", severity=0.7, confidence=0.8)]

    result = _run_with_mocks(ports, events)
    pm = result["procurement_matrix"]
    assert len(pm) == 1

    expected = 0.7 * 0.8  # 0.56
    assert pm[0]["risk_score"] == pytest.approx(expected, abs=0.01), (
        f"Expected risk={expected:.3f}, got {pm[0]['risk_score']:.3f}"
    )


def test_multiple_events_same_country_risk_is_max_not_sum():
    """
    Country in 3 events: score must equal max(sev*conf), NOT sum(sev*conf).

    Under old additive bug:  0.05 + 0.36 + 0.45 + 0.54 = 1.4  → capped to 0.95
    Under correct max() fix: max(0.05, 0.36, 0.45, 0.54)       = 0.54
    """
    ports  = [_make_port("Port Gulf", "GulfCountry")]
    events = [
        _make_event("GulfCountry region", severity=0.4, confidence=0.9),
        _make_event("GulfCountry region", severity=0.5, confidence=0.9),
        _make_event("GulfCountry region", severity=0.6, confidence=0.9),
    ]

    result = _run_with_mocks(ports, events)
    pm = result["procurement_matrix"]
    assert len(pm) == 1

    actual = pm[0]["risk_score"]
    assert actual < 0.95, (
        f"risk_score={actual} — if 0.95, the additive accumulator bug has returned. "
        "Expected max(sev*conf)=0.54, not sum capped at 0.95."
    )
    assert actual == pytest.approx(0.6 * 0.9, abs=0.01), (
        f"Expected {0.6*0.9:.3f} (worst event), got {actual:.3f}"
    )


def test_two_countries_have_different_risk_scores():
    """
    Two countries with different worst events must receive different scores.
    Under the old bug, both would land at 0.95 if each had 2+ events.
    """
    ports = [
        _make_port("Port High", "HighRisk"),
        _make_port("Port Low",  "LowRisk"),
    ]
    events = [
        _make_event("HighRisk region", severity=0.85, confidence=0.9),  # worst: 0.765
        _make_event("HighRisk region", severity=0.60, confidence=0.9),
        _make_event("LowRisk region",  severity=0.35, confidence=0.9),  # worst: 0.315
        _make_event("LowRisk region",  severity=0.20, confidence=0.9),
    ]

    result = _run_with_mocks(ports, events)
    pm = {row["country"]: row["risk_score"] for row in result["procurement_matrix"]}

    high = pm["HighRisk"]
    low  = pm["LowRisk"]

    assert high != low, (
        f"Both countries returned identical risk_score={high:.3f} — "
        "this is the bucketing bug. Scores must differ when worst events differ."
    )
    assert high > low
    assert high == pytest.approx(0.85 * 0.9, abs=0.01), f"HighRisk: expected {0.85*0.9:.3f}, got {high}"
    assert low  == pytest.approx(0.35 * 0.9, abs=0.01), f"LowRisk:  expected {0.35*0.9:.3f}, got {low}"


def test_no_matching_events_returns_baseline():
    """Port with no matching events stays at the 0.05 baseline."""
    ports  = [_make_port("Quiet Port", "QuietCountry")]
    events = [_make_event("SomeOtherRegion entirely", severity=0.9, confidence=0.9)]

    result = _run_with_mocks(ports, events)
    pm = result["procurement_matrix"]
    assert pm[0]["risk_score"] == pytest.approx(0.05, abs=0.001)


def test_extreme_severity_clamped_to_0_95():
    """Even with severity=1.0 / confidence=1.0, risk must not exceed 0.95."""
    ports  = [_make_port("Extreme Port", "ExtremeCountry")]
    events = [_make_event("ExtremeCountry region", severity=1.0, confidence=1.0)]

    result = _run_with_mocks(ports, events)
    pm = result["procurement_matrix"]
    assert pm[0]["risk_score"] <= 0.95
