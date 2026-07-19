"""Regression coverage for SDI freshness and producer-risk attribution.

These tests deliberately replace the integration fixtures from ``conftest.py``:
the modeler is a deterministic cache consumer, so none of these cases should
need a running PostgreSQL or Neo4j service (or make a yfinance request).
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from src.agents import modeler_agent
from src.utils.constants import MODELER_BASELINE_RISK, PRODUCER_CHOKEPOINT_INFER_DISCOUNT


NOW = datetime(2026, 7, 14, 12, 0, tzinfo=timezone.utc)


class _FixedDateTime(datetime):
    @classmethod
    def now(cls, tz=None):
        if tz is None:
            return NOW.replace(tzinfo=None)
        return NOW.astimezone(tz)


class _GraphSession:
    def __init__(self, countries: list[str]):
        self._countries = countries

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def run(self, _query: str):
        return [{"c": country} for country in self._countries]


class _GraphDriver:
    def __init__(self, countries: list[str]):
        self._countries = countries

    def session(self):
        return _GraphSession(self._countries)


# Override conftest's service-backed autouse fixtures for this unit-test module.
@pytest.fixture(scope="session", autouse=True)
def setup_test_db():
    yield


@pytest.fixture(autouse=True)
def db_transaction():
    yield None


@pytest.fixture(autouse=True)
def clean_neo4j():
    yield


@pytest.fixture(autouse=True)
def fixed_now():
    with patch.object(modeler_agent, "datetime", _FixedDateTime):
        yield


def _cached_market_rows() -> list[dict]:
    """Return a complete, newest-first rolling window for both SDI tickers."""
    rows = []
    for days_old in range(35):
        trade_day: date = (NOW - timedelta(days=days_old)).date()
        rows.extend(
            [
                {
                    "ticker": "BZ=F",
                    "price_close": 101.0 if days_old == 0 else 100.0,
                    "trade_date": trade_day,
                },
                {
                    "ticker": "BOAT",
                    "price_close": 51.0 if days_old == 0 else 50.0,
                    "trade_date": trade_day,
                },
            ]
        )
    return rows


def _compute_sdi(*, events: list[dict], vessels: list[dict]):
    with (
        patch.object(modeler_agent, "fetch_risk_events", return_value=events),
        patch.object(modeler_agent, "fetch_vessels", return_value=vessels),
        patch.object(
            modeler_agent,
            "get_brent_rolling_stats",
            return_value={
                "current_price": 101.0,
                "rolling_mean": 100.0,
                "rolling_std": 1.0,
                "latest_date": "2026-07-14",
                "status": "available",
            },
        ),
        patch.object(
            modeler_agent,
            "get_freight_rolling_stats",
            return_value={
                "current_price": 51.0,
                "rolling_mean": 50.0,
                "rolling_std": 1.0,
                "latest_date": "2026-07-14",
                "status": "available",
            },
        ),
        patch(
            "yfinance.download",
            side_effect=AssertionError("request-path modeler called yfinance"),
        ) as live_download,
    ):
        result = modeler_agent.compute_current_sdi()

    live_download.assert_not_called()
    return result


@pytest.mark.parametrize(
    "vessels",
    [
        [],
        [
            {
                "mmsi": 123456789,
                "ship_type": 80,
                "region": "Strait of Hormuz",
                "recorded_at": (NOW - timedelta(hours=25)).isoformat(),
            }
        ],
    ],
    ids=["empty", "stale"],
)
def test_missing_or_stale_ais_is_unavailable_not_total_disruption(vessels):
    result = _compute_sdi(events=[], vessels=vessels)

    assert result["delta_d"] == 0.0
    assert result["ais_status"] == "unavailable"


def test_low_ship_type_coverage_is_partial_and_excluded():
    vessels = [
        {
            "mmsi": index,
            "ship_type": 80 if index < 2 else None,
            "region": "Strait of Hormuz" if index % 2 else "Suez Canal",
            "recorded_at": NOW.isoformat(),
        }
        for index in range(20)
    ]

    result = _compute_sdi(events=[], vessels=vessels)

    assert result["ais_status"] == "partial"
    assert result["ais_type_coverage"] == pytest.approx(0.1)
    assert result["delta_d"] == 0.0


def test_vessel_deviation_is_weighted_by_chokepoint_flow():
    vessels = [
        {
            "mmsi": index,
            "ship_type": 80,
            "region": "Strait of Hormuz",
            "recorded_at": NOW.isoformat(),
        }
        for index in range(1)
    ]
    vessels += [
        {
            "mmsi": 100 + index,
            "ship_type": 80,
            "region": "Suez Canal",
            "recorded_at": NOW.isoformat(),
        }
        for index in range(28)
    ]
    vessels += [
        {
            "mmsi": 200 + index,
            "ship_type": 80,
            "region": "Strait of Malacca",
            "recorded_at": NOW.isoformat(),
        }
        for index in range(60)
    ]

    result = _compute_sdi(events=[], vessels=vessels)

    # Hormuz has the largest flow and is nearly empty, so the aggregate must
    # lean above the unweighted one-in-three-region average.
    assert result["ais_status"] == "available"
    assert result["delta_d"] > 0.4


def test_current_sdi_uses_cached_market_rows_only():
    result = _compute_sdi(events=[], vessels=[])

    assert result["current_brent"] == 101.0
    assert result["current_freight"] == 51.0


def test_price_impact_aggregates_all_elevated_chokepoints():
    events = [
        {
            "severity": 0.80,
            "confidence": 1.0,
            "source_fetched_at": NOW.isoformat(),
            "affected_chokepoints": ["Strait of Hormuz"],
            "directly_affected_chokepoints": ["Strait of Hormuz"],
        },
        {
            "severity": 0.60,
            "confidence": 1.0,
            "source_fetched_at": NOW.isoformat(),
            "affected_chokepoints": ["Strait of Malacca"],
            "directly_affected_chokepoints": ["Strait of Malacca"],
        },
    ]

    result = _compute_sdi(events=events, vessels=[])

    # (21 × .8 + 16 × .6) / (100 × .05) = $5.28/bbl.
    assert result["price_impact_usd"] == pytest.approx(5.28)


def test_geopolitical_risk_uses_source_time_and_decays_to_baseline():
    event = {
        "severity": 0.95,
        "confidence": 0.80,
        # Processing is current, but the underlying article is four weeks old.
        "created_at": NOW.isoformat(),
        "source_fetched_at": (NOW - timedelta(days=28)).isoformat(),
        "region": "Persian Gulf",
        "affected_chokepoints": ["Strait of Hormuz"],
    }

    result = _compute_sdi(events=[event], vessels=[])

    expected = MODELER_BASELINE_RISK + (
        event["severity"] - MODELER_BASELINE_RISK
    ) * 0.25
    assert result["p_risk"] == pytest.approx(expected, abs=0.001)
    assert result["updated_at"].startswith("2026-06-16")


def test_confidence_widens_the_band_without_suppressing_early_severity():
    event = {
        "severity": 0.80,
        "confidence": 0.20,
        "source_fetched_at": NOW.isoformat(),
        "created_at": NOW.isoformat(),
        "disruption_type": "unknown",
        "region": "Persian Gulf",
        "affected_chokepoints": ["Strait of Hormuz"],
    }

    result = _compute_sdi(events=[event], vessels=[])

    assert result["p_risk"] == pytest.approx(0.80, abs=0.001)
    assert result["confidence_high"] - result["confidence_low"] > 20


def test_event_type_half_lives_distinguish_persistent_from_fast_incidents():
    base_event = {
        "severity": 0.90,
        "source_fetched_at": (NOW - timedelta(days=10)).isoformat(),
    }
    military = modeler_agent._event_risk(
        {**base_event, "disruption_type": "military_conflict"}, NOW
    )
    sanctions = modeler_agent._event_risk(
        {**base_event, "disruption_type": "sanctions"}, NOW
    )

    assert sanctions > military


def _producer_scores(events: list[dict], graph_countries: list[str]) -> dict[str, float]:
    with (
        patch.object(modeler_agent, "fetch_risk_events", return_value=events),
        patch(
            "src.database.neo4j_graph.get_driver",
            return_value=_GraphDriver(graph_countries),
        ),
    ):
        matrix = modeler_agent.compute_producer_country_risk_matrix()
    return {row["name"]: row["risk_score"] for row in matrix}


def test_producer_matrix_normalizes_aliases_and_excludes_event_only_countries():
    events = [
        {
            "severity": 0.60,
            "confidence": 1.0,
            "source_fetched_at": NOW.isoformat(),
            "created_at": NOW.isoformat(),
            "affected_chokepoints": [],
            "affected_producer_countries": ["United Arab Emirates", "Bahrain"],
        }
    ]

    scores = _producer_scores(
        events,
        graph_countries=["USA", "United States", "UAE", "United Arab Emirates", "Kuwait"],
    )

    assert set(scores) == {"United States", "United Arab Emirates", "Kuwait"}
    assert scores["United Arab Emirates"] == pytest.approx(0.60)
    assert scores["United States"] == pytest.approx(MODELER_BASELINE_RISK)
    assert "Bahrain" not in scores


def test_hormuz_event_discounts_exposed_producers_and_leaves_us_at_baseline():
    event = {
        "severity": 0.95,
        "confidence": 1.0,
        "source_fetched_at": NOW.isoformat(),
        "created_at": NOW.isoformat(),
        "affected_chokepoints": ["Strait of Hormuz"],
        # The model may list geopolitical actors here. Chokepoint attribution
        # must instead follow graph-backed transit exposure.
        "affected_producer_countries": ["USA", "Bahrain", "Kuwait"],
    }

    scores = _producer_scores(
        [event],
        graph_countries=["Kuwait", "United Arab Emirates", "United States"],
    )

    discounted = event["severity"] * event["confidence"] * PRODUCER_CHOKEPOINT_INFER_DISCOUNT
    assert scores["Kuwait"] == pytest.approx(discounted, abs=0.001)
    assert scores["United Arab Emirates"] == pytest.approx(discounted, abs=0.001)
    assert scores["Kuwait"] < event["severity"]
    assert scores["United States"] == pytest.approx(MODELER_BASELINE_RISK)


def test_single_old_direct_producer_event_decays_toward_baseline():
    event = {
        "severity": 0.95,
        "confidence": 1.0,
        "source_fetched_at": (NOW - timedelta(days=28)).isoformat(),
        "created_at": NOW.isoformat(),
        "affected_chokepoints": [],
        "affected_producer_countries": ["Kuwait"],
    }

    scores = _producer_scores([event], graph_countries=["Kuwait"])

    expected = MODELER_BASELINE_RISK + (
        event["severity"] - MODELER_BASELINE_RISK
    ) * 0.25
    assert scores["Kuwait"] == pytest.approx(expected, abs=0.001)
    assert MODELER_BASELINE_RISK < scores["Kuwait"] < event["severity"]
