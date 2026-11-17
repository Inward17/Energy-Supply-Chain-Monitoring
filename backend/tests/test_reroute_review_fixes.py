"""Reroute fixes from the external review: refinery labels, decayed supplier
risk, and the balanced (composite) ranking mode."""
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

import api
from src.agents import fixer_agent as fixer
from src.utils.schemas import RerouteRequest

NOW = datetime.now(timezone.utc)


def test_dropdown_labels_resolve_to_graph_names():
    assert fixer.canonical_refinery("Rotterdam (Netherlands)") == "Rotterdam"
    assert fixer.canonical_refinery("Houston Ship Channel (USA)") == "Houston Ship Channel"
    assert fixer.canonical_refinery("Jamnagar") == "Jamnagar"


def test_unknown_refinery_raises_instead_of_rerouting_to_jamnagar():
    with patch.object(fixer, "get_refinery_coords", return_value=None):
        with pytest.raises(fixer.UnknownRefinery):
            fixer.find_alternatives(blocked_chokepoint="Strait of Hormuz", destination_refinery="Nowhere")


def test_unknown_refinery_is_a_422():
    with patch.object(fixer, "get_refinery_coords", return_value=None):
        r = TestClient(api.app).post(
            "/api/orchestrator/reroute",
            json={"blocked_chokepoint": "Strait of Hormuz", "destination_refinery": "Nowhere"},
        )
    assert r.status_code == 422
    assert r.json()["detail"] == "Unknown destination refinery"


def _event(days_old: float) -> dict:
    return {
        "region": "Iraq", "summary": "", "severity": 0.9, "confidence": 1.0,
        "disruption_type": "military_conflict",
        "source_fetched_at": (NOW - timedelta(days=days_old)).isoformat(),
    }


def test_supplier_risk_decays_with_event_age():
    fresh = fixer._country_risk("Iraq", [_event(0)], NOW)
    old = fixer._country_risk("Iraq", [_event(120)], NOW)
    assert fresh > 0.85
    assert old < 0.06


def test_empty_country_does_not_match_every_event():
    assert fixer._country_risk("", [_event(0)], NOW) == 0.05


def test_balanced_ranking_mode_is_accepted():
    assert RerouteRequest(blocked_chokepoint="Strait of Hormuz", ranking_mode="balanced").ranking_mode == "balanced"
