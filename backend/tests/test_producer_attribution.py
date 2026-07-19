"""
tests/test_producer_attribution.py
──────────────────────────────────
Regressions for producer-country attribution and SDI severity banding.

Both fixes came from the same observation: Russia sat at baseline 0.05 while
four scored Russian disruption events were sitting in the feed, and the
dashboard rendered a 55 as reassuring green.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from src.agents.modeler_agent import (
    _producers_named_in_region,
    compute_producer_country_risk_matrix,
)
from src.utils.constants import canonical_country_name, sdi_band

NOW = datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Country canonicalisation
# ---------------------------------------------------------------------------

def test_long_form_country_names_canonicalise():
    """An unmapped long form is dropped by the producer validator, silently
    costing that producer its score."""
    assert canonical_country_name("Russian Federation") == "Russia"
    assert canonical_country_name("Islamic Republic of Iran") == "Iran"
    assert canonical_country_name("KSA") == "Saudi Arabia"
    assert canonical_country_name("U.A.E.") == "United Arab Emirates"


def test_canonicalisation_is_case_insensitive():
    assert canonical_country_name("russian federation") == "Russia"
    assert canonical_country_name("RUSSIAN FEDERATION") == "Russia"


def test_unknown_names_pass_through_unchanged():
    assert canonical_country_name("Norway") == "Norway"
    assert canonical_country_name("") == ""


# ---------------------------------------------------------------------------
# Region -> producer fallback
# ---------------------------------------------------------------------------

def test_region_label_resolves_to_producer():
    known = {"Russia", "Iran", "Saudi Arabia"}
    assert _producers_named_in_region("Russia", known) == ["Russia"]
    assert _producers_named_in_region("Russia, Central Asia", known) == ["Russia"]


def test_region_matching_does_not_fire_on_substrings():
    """Word boundaries: 'Oman' must not match inside 'Romania'."""
    assert _producers_named_in_region("Romania coast", {"Oman"}) == []
    assert _producers_named_in_region("Persian Gulf", {"Russia", "Iran"}) == []


def test_event_naming_country_only_in_region_still_scores_it():
    """The Russia case: region says Russia, both producer arrays are empty.

    Previously scored nothing, leaving the producer at baseline while its own
    disruption sat in the feed.
    """
    event = {
        "id": 1,
        "region": "Russia",
        "disruption_type": "military_conflict",
        "severity": 0.7,
        "confidence": 0.9,
        "summary": "Refinery outages disrupt Russian fuel supply",
        "affected_chokepoints": [],
        "affected_producer_countries": None,
        "directly_affected_producer_countries": None,
        "source_fetched_at": (NOW - timedelta(hours=2)).isoformat(),
    }

    with (
        patch("src.agents.modeler_agent.fetch_risk_events", return_value=[event]),
        patch("src.agents.modeler_agent._known_producer_countries", return_value={"Russia", "Iran"}),
        patch("src.agents.modeler_agent._producer_transit_map", return_value={}),
    ):
        matrix = compute_producer_country_risk_matrix()

    russia = next(row for row in matrix if row["name"] == "Russia")
    assert russia["risk_score"] > 0.5, f"expected Russia to score, got {russia}"
    assert russia["exposure_type"] == "direct"


def test_region_fallback_does_not_override_explicit_attribution():
    """An event that already names producers must not also pick up its region."""
    event = {
        "id": 2,
        "region": "Russia",
        "disruption_type": "military_conflict",
        "severity": 0.8,
        "confidence": 0.9,
        "summary": "Attack on Iranian export terminal",
        "affected_chokepoints": [],
        "affected_producer_countries": ["Iran"],
        "directly_affected_producer_countries": ["Iran"],
        "source_fetched_at": NOW.isoformat(),
    }

    with (
        patch("src.agents.modeler_agent.fetch_risk_events", return_value=[event]),
        patch("src.agents.modeler_agent._known_producer_countries", return_value={"Russia", "Iran"}),
        patch("src.agents.modeler_agent._producer_transit_map", return_value={}),
    ):
        matrix = compute_producer_country_risk_matrix()

    by_name = {row["name"]: row for row in matrix}
    assert by_name["Iran"]["risk_score"] > 0.5
    assert by_name["Russia"]["exposure_type"] == "baseline"


# ---------------------------------------------------------------------------
# SDI banding
# ---------------------------------------------------------------------------

def test_sdi_bands_are_graduated():
    assert sdi_band(10) == "LOW"
    assert sdi_band(35) == "MODERATE"
    assert sdi_band(55.8) == "ELEVATED"
    assert sdi_band(70) == "SEVERE"
    assert sdi_band(85) == "CRITICAL"


def test_mid_fifties_is_not_reassuring():
    """The specific regression: a 55 used to render as 'safe' green because the
    dashboard thresholded on `score > 60`."""
    assert sdi_band(55.7) not in ("LOW", "MODERATE")
