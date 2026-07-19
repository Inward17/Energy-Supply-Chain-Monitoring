"""
tests/test_vessel_density_baseline.py
─────────────────────────────────────
Covers the self-calibrated vessel-density signal that replaced the
hand-maintained `_VESSEL_BASELINES` table.

The property that matters: the live reading and the baseline must be produced
by the same measurement path, so that partial AIS type coverage and changes to
the collector's snapshot window cancel between them instead of masquerading as
a traffic anomaly.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from src.agents.modeler_agent import _bucket_tanker_share, _self_calibrated_density

NOW = datetime(2026, 7, 19, 12, 0, tzinfo=timezone.utc)


def _bucket(region, hours_ago, total, typed, tankers):
    return {
        "region": region,
        "bucket": NOW - timedelta(hours=hours_ago),
        "total": total,
        "typed": typed,
        "tankers": tankers,
    }


def _steady_history(region, hours, total=100, typed=50, tankers=20):
    """Baseline history at a constant 40% tanker share."""
    return [_bucket(region, h, total, typed, tankers) for h in range(hours, 0, -1)]


def _three_regions(latest_by_region):
    """Three regions of steady history plus a caller-supplied latest bucket."""
    rows = []
    for region in ("Suez Canal", "Strait of Malacca", "Turkish Straits"):
        rows += _steady_history(region, 10)
        rows.append(latest_by_region[region])
    return rows


# ---------------------------------------------------------------------------
# Share metric invariants
# ---------------------------------------------------------------------------

def test_share_is_invariant_to_snapshot_window_length():
    """A longer collector window sees proportionally more of everything.

    This is the regression that motivated the metric: raising
    AIS_SNAPSHOT_SECONDS 120 -> 600 multiplied raw counts ~6x, which made live
    readings tower over a baseline gathered under the old window.
    """
    short_window = _bucket("Suez Canal", 1, total=100, typed=50, tankers=20)
    long_window = _bucket("Suez Canal", 1, total=600, typed=300, tankers=120)

    assert _bucket_tanker_share(short_window) == _bucket_tanker_share(long_window)


def test_share_is_invariant_to_type_coverage():
    """Typing 30% vs 70% of the same traffic must not move the signal."""
    low_coverage = _bucket("Suez Canal", 1, total=100, typed=30, tankers=12)
    high_coverage = _bucket("Suez Canal", 1, total=100, typed=70, tankers=28)

    assert _bucket_tanker_share(low_coverage) == _bucket_tanker_share(high_coverage)


def test_thin_and_poorly_typed_buckets_are_rejected():
    # Barely any traffic seen at all.
    assert _bucket_tanker_share(_bucket("Suez Canal", 1, total=5, typed=4, tankers=2)) is None

    # Plenty of traffic, but too few of it classified: a share off 4 vessels is
    # noise. This is the case that was poisoning baselines with 0.0/1.0 medians.
    assert _bucket_tanker_share(_bucket("Suez Canal", 1, total=100, typed=4, tankers=2)) is None

    # Well-sampled in absolute terms, but classified too small a fraction of
    # what passed through (10% < the 15% floor) to represent it.
    assert _bucket_tanker_share(_bucket("Suez Canal", 1, total=200, typed=20, tankers=8)) is None

    # Sufficient on both counts.
    assert _bucket_tanker_share(_bucket("Suez Canal", 1, total=100, typed=40, tankers=16)) == 0.4


# ---------------------------------------------------------------------------
# Signal behaviour
# ---------------------------------------------------------------------------

def test_tanker_exodus_raises_delta():
    """Tanker share halving across every region must register as disruption."""
    latest = {
        r: _bucket(r, 0, total=100, typed=50, tankers=10)  # 20% vs 40% baseline
        for r in ("Suez Canal", "Strait of Malacca", "Turkish Straits")
    }
    with patch(
        "src.agents.modeler_agent.fetch_region_tanker_buckets",
        return_value=_three_regions(latest),
    ):
        delta, status, _ = _self_calibrated_density(NOW)

    assert status == "available"
    assert delta > 0.4, f"a halved tanker share should read as disruption, got {delta}"


def test_traffic_above_baseline_is_not_disruption():
    latest = {
        r: _bucket(r, 0, total=100, typed=50, tankers=35)  # 70% vs 40% baseline
        for r in ("Suez Canal", "Strait of Malacca", "Turkish Straits")
    }
    with patch(
        "src.agents.modeler_agent.fetch_region_tanker_buckets",
        return_value=_three_regions(latest),
    ):
        delta, status, _ = _self_calibrated_density(NOW)

    assert status == "available"
    assert delta == 0.0


def test_window_change_alone_does_not_fabricate_a_signal():
    """History collected on a short window, live on a long one: same share."""
    rows = []
    for region in ("Suez Canal", "Strait of Malacca", "Turkish Straits"):
        rows += _steady_history(region, 10, total=100, typed=50, tankers=20)
        rows.append(_bucket(region, 0, total=600, typed=300, tankers=120))

    with patch("src.agents.modeler_agent.fetch_region_tanker_buckets", return_value=rows):
        delta, status, _ = _self_calibrated_density(NOW)

    assert status == "available"
    assert delta == 0.0, "a collector-window change must not look like traffic change"


# ---------------------------------------------------------------------------
# Guards
# ---------------------------------------------------------------------------

def test_insufficient_history_reports_partial_not_zero_signal():
    rows = []
    for region in ("Suez Canal", "Strait of Malacca", "Turkish Straits"):
        rows += _steady_history(region, 2)  # below the minimum baseline buckets
        rows.append(_bucket(region, 0, total=100, typed=50, tankers=10))

    with patch("src.agents.modeler_agent.fetch_region_tanker_buckets", return_value=rows):
        delta, status, _ = _self_calibrated_density(NOW)

    assert status == "partial"
    assert delta == 0.0


def test_stale_latest_bucket_is_not_treated_as_live():
    """Collection stopped 12h ago; the last reading is history, not "now"."""
    rows = []
    for region in ("Suez Canal", "Strait of Malacca", "Turkish Straits"):
        # Everything predates the staleness cut-off, newest bucket 12h old.
        rows += [_bucket(region, h, 100, 50, 20) for h in range(24, 12, -1)]
        rows.append(_bucket(region, 12, total=100, typed=50, tankers=10))

    with patch("src.agents.modeler_agent.fetch_region_tanker_buckets", return_value=rows):
        delta, status, _ = _self_calibrated_density(NOW)

    assert status == "partial"
    assert delta == 0.0


def test_no_telemetry_reports_unavailable():
    with patch("src.agents.modeler_agent.fetch_region_tanker_buckets", return_value=[]):
        delta, status, _ = _self_calibrated_density(NOW)

    assert status == "unavailable"
    assert delta == 0.0
