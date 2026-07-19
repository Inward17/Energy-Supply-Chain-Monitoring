"""
tests/test_dedup_repeated_coverage.py
──────────────────────────────────────
Explicit regression test: 3 near-duplicate headlines about the same incident
must NOT inflate the risk score vs a single article. Structural dedup via max().
"""
from __future__ import annotations
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch


def _make_event(event_id, country, severity=0.7, confidence=0.9, hours_old=2.0):
    ts = (datetime.now(timezone.utc) - timedelta(hours=hours_old)).isoformat()
    return {
        "id": event_id, "severity": severity, "confidence": confidence,
        "disruption_type": "military_conflict",
        "region": f"{country} region",
        "summary": f"Attack in {country}",
        "affected_chokepoints": [],
        "affected_producer_countries": [country],
        "directly_affected_producer_countries": [country],
        "source_fetched_at": ts, "created_at": ts,
    }


def _get_producer_risk(events, country):
    from src.agents.modeler_agent import compute_producer_country_risk_matrix
    with (
        patch("src.agents.modeler_agent.fetch_risk_events", return_value=events),
        patch("src.agents.modeler_agent._known_producer_countries", return_value={country}),
        patch("src.agents.modeler_agent._producer_transit_map", return_value={}),
    ):
        matrix = compute_producer_country_risk_matrix()
        row = next((r for r in matrix if r["name"] == country), None)
        return row["risk_score"] if row else 0.0


def test_single_event_gives_nonbaseline_score():
    events = [_make_event(1, "TestCountry", severity=0.7, confidence=0.9, hours_old=2)]
    score = _get_producer_risk(events, "TestCountry")
    assert 0.1 < score < 0.95, f"Expected non-trivial score for sev=0.7, got {score}"


def test_three_duplicates_equal_single_event():
    """3 near-duplicate events must not significantly inflate the score vs 1 event."""
    single = [_make_event(1, "TestCountry", severity=0.70, confidence=0.9, hours_old=2.0)]
    triple = [
        _make_event(1, "TestCountry", severity=0.70, confidence=0.90, hours_old=2.0),
        _make_event(2, "TestCountry", severity=0.68, confidence=0.89, hours_old=2.5),
        _make_event(3, "TestCountry", severity=0.72, confidence=0.88, hours_old=3.0),
    ]
    single_score = _get_producer_risk(single, "TestCountry")
    triple_score = _get_producer_risk(triple, "TestCountry")

    assert triple_score < 0.95, (
        f"triple_score={triple_score:.3f} hit 0.95 ceiling — additive accumulation detected."
    )
    ratio = triple_score / single_score if single_score > 0 else 999
    assert ratio < 1.5, (
        f"triple={triple_score:.3f} is {ratio:.1f}x single={single_score:.3f}. "
        "Repeated coverage inflated by >50% — dedup not effective."
    )


def test_ten_duplicates_bounded():
    """10 events for the same incident must not push score to 0.95 ceiling."""
    events = [
        _make_event(i, "IranianOilfields", severity=0.65, confidence=0.85, hours_old=float(i))
        for i in range(1, 11)
    ]
    score = _get_producer_risk(events, "IranianOilfields")
    assert score < 0.95, (
        f"10 duplicate events pushed score to {score:.3f}. Additive accumulation bug."
    )
    assert score > 0.1, "Score should not be at baseline with sev=0.65 events"


def test_highest_severity_duplicate_wins():
    """When 3 duplicates vary in severity, the highest should dominate (not the sum)."""
    events = [
        _make_event(1, "RussiaOil", severity=0.50, confidence=0.9, hours_old=6),
        _make_event(2, "RussiaOil", severity=0.85, confidence=0.9, hours_old=2),
        _make_event(3, "RussiaOil", severity=0.40, confidence=0.9, hours_old=10),
    ]
    single_high = [_make_event(10, "RussiaOil", severity=0.85, confidence=0.9, hours_old=2)]
    mixed_score = _get_producer_risk(events, "RussiaOil")
    high_score   = _get_producer_risk(single_high, "RussiaOil")

    assert mixed_score < 0.95, f"mixed_score={mixed_score:.3f} hit ceiling"
    assert abs(mixed_score - high_score) < 0.10, (
        f"mixed={mixed_score:.3f} should ≈ high-severity single={high_score:.3f}."
    )
