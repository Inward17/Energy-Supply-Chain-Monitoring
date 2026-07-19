"""
src/agents/modeler_agent.py
────────────────────────────
Deterministic impact evaluation layer — zero LLM calls.

Reads pre-cached data from local Postgres and applies algebraic
formulas to produce the composite Supply Disruption Index (SDI)
and supporting impact metrics.

SDI = w1·P_risk + w2·ΔD_vessel + w3·ΔP_price + w4·ΔP_freight

All outputs are structured dicts consumed directly by app.py.
"""

from __future__ import annotations

import logging
import os
import re
from datetime import datetime, timezone
from statistics import median
from typing import Any

from src.database.postgres_db import (
    fetch_risk_events,
    fetch_vessels,
    fetch_region_tanker_buckets,
)
from src.ingestion.market_trawler import get_brent_rolling_stats
from src.ingestion.freight_trawler import get_freight_rolling_stats
from src.utils.metrics import (
    supply_disruption_index,
    normalise_price_delta,
    normalise_freight_delta,
    normalise_vessel_density_delta,
    estimate_price_impact,
    compute_resilience_score,
    flow_weighted_risk,
    _W1, _W2, _W3, _W4,
)
from src.utils.constants import (
    ELEVATED_RISK_THRESHOLD,
    sdi_band,
    FIXER_BRENT_FALLBACK_USD,
    MODELER_BASELINE_RISK,
    PRODUCER_CHOKEPOINT_INFER_DISCOUNT,
    CHOKEPOINT_INDIRECT_MENTION_DISCOUNT,
    PRODUCER_NATIONS,
    PRODUCER_TO_CHOKEPOINTS,
    RISK_EVENT_HALF_LIFE_DAYS_BY_TYPE,
    TANKER_SHIP_TYPES,
    canonical_country_name,
    canonical_chokepoint_name,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Baseline vessel counts per region (rolling 7-day reference)
# Updated manually; in a production setup, computed nightly from DB aggregates
# ---------------------------------------------------------------------------
_VESSEL_BASELINES: dict[str, int] = {
    "Strait of Hormuz":  45,
    "Bab-el-Mandeb":     30,
    "Suez Canal":        28,
    "Strait of Malacca": 60,
    "Turkish Straits":   18,
    "Cape of Good Hope": 12,
}

# Chokepoint daily oil flow (million barrels/day) for price impact calculation
_CHOKEPOINT_FLOWS: dict[str, float] = {
    "Strait of Hormuz":    21.0,
    "Strait of Malacca":   16.0,
    "Suez Canal":           9.5,
    "Bab-el-Mandeb":        8.8,
    "Cape of Good Hope":    5.0,
    "Turkish Straits":      2.9,
    "Strait of Gibraltar":  1.5,
    "Panama Canal":         0.8,
}

_MARKET_MAX_AGE_DAYS = int(os.getenv("MARKET_MAX_AGE_DAYS", "5"))
_AIS_MIN_TYPE_COVERAGE = float(os.getenv("AIS_MIN_TYPE_COVERAGE", "0.70"))
_AIS_MIN_TANKERS = int(os.getenv("AIS_MIN_TANKERS", "10"))
_AIS_MIN_REGIONS = int(os.getenv("AIS_MIN_REGIONS", "3"))
_MAX_RISK_SCORE = 0.95

# ---------------------------------------------------------------------------
# Self-calibrated vessel-density baselines
# ---------------------------------------------------------------------------
# The legacy path compared a partially-typed live snapshot against the
# hand-maintained `_VESSEL_BASELINES` above. Because AIS types only a fraction
# of vessels — and that fraction is not stable over time — the two sides were
# measured differently and the 70% coverage gate had to disable the signal
# outright. These settings drive the replacement: baselines are the median of a
# region's own recent coverage-corrected readings, so the bias cancels and only
# a noise floor is needed rather than a high coverage bar.
_AIS_BASELINE_DAYS = int(os.getenv("AIS_BASELINE_DAYS", "7"))
#: Ignore buckets thinner than this — too few sightings to estimate from.
_AIS_MIN_BUCKET_SAMPLE = int(os.getenv("AIS_MIN_BUCKET_SAMPLE", "15"))
#: The share's precision depends on how many vessels were *classified*, not how
#: many were seen: a bucket with 3 typed vessels yields shares of 0.00 or 1.00
#: and would poison the baseline median. Gate on the classified count.
_AIS_MIN_TYPED_SAMPLE = int(os.getenv("AIS_MIN_TYPED_SAMPLE", "12"))
#: Below this coverage, the 1/coverage correction amplifies noise faster than
#: it removes bias, so the bucket is discarded rather than trusted.
_AIS_COVERAGE_FLOOR = float(os.getenv("AIS_COVERAGE_FLOOR", "0.15"))
#: Minimum prior buckets before a region's median is treated as a baseline.
_AIS_MIN_BASELINE_BUCKETS = int(os.getenv("AIS_MIN_BASELINE_BUCKETS", "6"))
#: A live reading older than this is stale, not current traffic.
_AIS_MAX_BUCKET_AGE_SECONDS = int(os.getenv("AIS_MAX_BUCKET_AGE_SECONDS", "10800"))


def _as_utc_datetime(value: Any) -> datetime | None:
    """Normalise DB/JSON timestamps without treating processing time as source time."""
    if value is None:
        return None
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _event_timestamp(event: dict[str, Any]) -> datetime | None:
    """Prefer article fetch time; created_at may only be delayed processing time."""
    return _as_utc_datetime(event.get("source_fetched_at") or event.get("created_at"))


def _decayed_risk(
    raw_risk: float,
    event_time: datetime | None,
    now: datetime,
    disruption_type: str | None = None,
) -> float:
    """Decay excess risk toward baseline rather than cancelling decay in an average."""
    bounded = max(MODELER_BASELINE_RISK, min(_MAX_RISK_SCORE, raw_risk))
    age_days = (
        max(0.0, (now - event_time).total_seconds() / 86400.0)
        if event_time
        else 3.0
    )
    event_type = str(disruption_type or "unknown").strip().lower()
    half_life_days = RISK_EVENT_HALF_LIFE_DAYS_BY_TYPE.get(
        event_type,
        RISK_EVENT_HALF_LIFE_DAYS_BY_TYPE["default"],
    )
    decay = 0.5 ** (age_days / half_life_days)
    return MODELER_BASELINE_RISK + (bounded - MODELER_BASELINE_RISK) * decay


def _event_risk(
    event: dict[str, Any],
    now: datetime,
    multiplier: float = 1.0,
) -> float:
    severity = float(event.get("severity", 0.0) or 0.0)
    return _decayed_risk(
        severity * multiplier,
        _event_timestamp(event),
        now,
        event.get("disruption_type"),
    )


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _market_feed_is_fresh(stats: dict[str, Any], now: datetime) -> bool:
    if (
        stats.get("status") != "available"
        or float(stats.get("current_price", 0.0) or 0.0) <= 0
        or not stats.get("latest_date")
    ):
        return False
    try:
        latest = datetime.fromisoformat(str(stats["latest_date"])[:10]).date()
    except ValueError:
        return False
    age_days = (now.date() - latest).days
    return 0 <= age_days <= _MARKET_MAX_AGE_DAYS


def get_current_freight_index(
    now: datetime | None = None,
    stats: dict[str, Any] | None = None,
) -> float:
    """Return the cache-backed freight stress index, or neutral when unavailable.

    Fixer consumes this narrow helper so procurement freight pricing uses the
    same normalised BOAT signal as the SDI without rebuilding the full score.
    """
    current_time = now or datetime.now(timezone.utc)
    freight = stats if stats is not None else get_freight_rolling_stats()
    if not _market_feed_is_fresh(freight, current_time):
        return 0.5
    return normalise_freight_delta(
        current_freight=float(freight["current_price"]),
        rolling_mean=float(freight["rolling_mean"]),
        rolling_std=float(freight["rolling_std"]),
    )


def _known_producer_countries() -> set[str]:
    """Read the matrix population from the graph, with a deterministic fallback."""
    countries: set[str] = set()
    try:
        from src.database.neo4j_graph import get_driver

        driver = get_driver()
        if driver:
            with driver.session() as session:
                result = session.run(
                    "MATCH (p:ExportPort) RETURN DISTINCT p.country AS c"
                )
                countries = {
                    canonical_country_name(row["c"])
                    for row in result
                    if row["c"]
                }
    except Exception as exc:
        logger.warning("Producer graph unavailable; using registry fallback: %s", exc)

    if not countries:
        countries = {
            canonical_country_name(country)
            for country in PRODUCER_NATIONS
        }
    return {country for country in countries if country}


def _producer_transit_map() -> dict[str, set[str]]:
    result: dict[str, set[str]] = {}
    for country, chokepoints in PRODUCER_TO_CHOKEPOINTS.items():
        canonical = canonical_country_name(country)
        result.setdefault(canonical, set()).update(chokepoints)
    return result


def _bucket_tanker_share(bucket: dict[str, Any]) -> float | None:
    """Tanker share of classified traffic for one time bucket, or None if thin.

    Deliberately a *share* (tankers / typed) rather than a corrected count.
    A raw count depends on both AIS type coverage and how long the collector
    ran, and neither is stable — coverage moves with reception, and the
    snapshot window is a tunable. A share cancels both: it is coverage-invariant
    (the corrected count `tankers/coverage` divided by `total` reduces exactly
    to `tankers/typed`) and window-invariant, because a longer window scales
    numerator and denominator alike.

    Measured on live data, share was the more stable baseline in every region
    (e.g. Malacca CV 0.76 -> 0.42), which is what governs how small a real drop
    the signal can resolve.

    Trade-off: a uniform collapse of *all* traffic leaves the share unchanged.
    This detects the realistic case — tankers rerouting while other shipping
    continues — not a total port shutdown.
    """
    total = int(bucket.get("total") or 0)
    typed = int(bucket.get("typed") or 0)
    tankers = int(bucket.get("tankers") or 0)
    if total < _AIS_MIN_BUCKET_SAMPLE or typed < _AIS_MIN_TYPED_SAMPLE:
        return None
    if typed / total < _AIS_COVERAGE_FLOOR:
        # Classified too small a fraction of what passed through to represent it.
        return None
    return tankers / typed


def _self_calibrated_density(now: datetime) -> tuple[float, str, dict[str, Any]]:
    """Vessel-density divergence against rolling, self-calibrated baselines.

    Replaces the hand-maintained `_VESSEL_BASELINES` table. The baseline for a
    region is the median of its own recent coverage-corrected readings, so the
    live value and the baseline are produced by exactly the same measurement
    path and any residual sampling bias cancels between them.

    Returns (delta_d, status, diagnostics).
    """
    buckets = fetch_region_tanker_buckets(days=_AIS_BASELINE_DAYS)
    if not buckets:
        return 0.0, "unavailable", {"reason": "no telemetry buckets"}

    by_region: dict[str, list[dict[str, Any]]] = {}
    for row in buckets:
        by_region.setdefault(str(row.get("region")), []).append(row)

    regions: list[str] = []
    deltas: list[float] = []
    flows: list[float] = []
    detail: dict[str, Any] = {}

    for region, rows in by_region.items():
        rows.sort(key=lambda r: _as_utc_datetime(r.get("bucket")) or now)
        usable = [(r, _bucket_tanker_share(r)) for r in rows]
        usable = [(r, share) for r, share in usable if share is not None]
        if len(usable) < _AIS_MIN_BASELINE_BUCKETS + 1:
            continue

        latest_row, latest_share = usable[-1]
        latest_at = _as_utc_datetime(latest_row.get("bucket"))
        if not latest_at or (now - latest_at).total_seconds() > _AIS_MAX_BUCKET_AGE_SECONDS:
            continue

        history = [share for _, share in usable[:-1]]
        baseline = median(history)
        if baseline <= 0:
            continue

        delta = normalise_vessel_density_delta(latest_share, baseline)
        regions.append(region)
        deltas.append(delta)
        flows.append(_CHOKEPOINT_FLOWS.get(region, 1.0))
        detail[region] = {
            "live_share": round(latest_share, 3),
            "baseline_share": round(baseline, 3),
            "delta": round(delta, 3),
            "history_buckets": len(history),
        }

    if len(regions) < _AIS_MIN_REGIONS:
        return 0.0, "partial", {
            "reason": f"only {len(regions)} region(s) with a usable baseline",
            "regions": detail,
        }

    # Flow-weighted so a drop at Hormuz outweighs one at a minor passage.
    delta_d = flow_weighted_risk(flows, deltas)
    return delta_d, "available", {"regions": detail}


def _ais_tanker_snapshot(
    vessels: list[dict[str, Any]],
    now: datetime,
) -> tuple[list[dict[str, Any]], dict[str, int], float, bool]:
    """Filter to fresh positions and judge whether the snapshot is dense enough.

    Returns (fresh_vessels, region_counts_tanker, type_coverage,
    coverage_sufficient). The same gate protects both the global SDI and the
    per-chokepoint matrix, so a sparse 120-second snapshot is never compared
    against full-density baselines on either path.
    """
    fresh_vessels = []
    for vessel in vessels:
        recorded_at = _as_utc_datetime(vessel.get("recorded_at"))
        if recorded_at and (now - recorded_at).total_seconds() > 86400:
            continue
        fresh_vessels.append(vessel)

    region_counts_tanker: dict[str, int] = {}
    for vessel in fresh_vessels:
        region = vessel.get("region", "Unknown")
        if vessel.get("ship_type") in TANKER_SHIP_TYPES:
            region_counts_tanker[region] = region_counts_tanker.get(region, 0) + 1

    typed_vessel_count = sum(
        vessel.get("ship_type") is not None for vessel in fresh_vessels
    )
    type_coverage = (
        typed_vessel_count / len(fresh_vessels) if fresh_vessels else 0.0
    )
    eligible_regions = [
        region for region in region_counts_tanker if region in _VESSEL_BASELINES
    ]
    coverage_sufficient = (
        type_coverage >= _AIS_MIN_TYPE_COVERAGE
        and sum(region_counts_tanker.values()) >= _AIS_MIN_TANKERS
        and len(eligible_regions) >= _AIS_MIN_REGIONS
    )
    return fresh_vessels, region_counts_tanker, type_coverage, coverage_sufficient


def _active_chokepoint_risks(
    events: list[dict[str, Any]],
    now: datetime,
) -> tuple[dict[str, float], dict[str, str]]:
    """Return the strongest active risk and provenance for each chokepoint."""
    chokepoint_risk: dict[str, float] = {}
    inference_source: dict[str, str] = {}
    for event in events:
        affected = set(event.get("affected_chokepoints") or [])
        direct_field = event.get("directly_affected_chokepoints")
        if direct_field is None:
            # Legacy rows (SQL NULL) predate the direct/indirect split: their
            # chokepoint attributions were written at full severity, so
            # discounting them retroactively would understate known incidents.
            # An explicit empty list means the scorer judged every mention
            # indirect and keeps the discount.
            direct = affected
        else:
            direct = set(direct_field)
        indirect = affected - direct
        
        # Apply full risk to directly affected chokepoints
        direct_risk = _event_risk(event, now)
        for chokepoint in direct:
            if direct_risk > chokepoint_risk.get(chokepoint, MODELER_BASELINE_RISK):
                chokepoint_risk[chokepoint] = direct_risk
                
        # Apply discounted risk to indirectly affected (regional mention) chokepoints
        indirect_risk = _event_risk(event, now, CHOKEPOINT_INDIRECT_MENTION_DISCOUNT)
        for chokepoint in indirect:
            if indirect_risk > chokepoint_risk.get(chokepoint, MODELER_BASELINE_RISK):
                chokepoint_risk[chokepoint] = indirect_risk

    transit_map = _producer_transit_map()
    for event in events:
        if event.get("affected_chokepoints"):
            continue
        for country in event.get("affected_producer_countries") or []:
            canonical = canonical_country_name(country)
            inferred_risk = _event_risk(
                event,
                now,
                PRODUCER_CHOKEPOINT_INFER_DISCOUNT,
            )
            for chokepoint in transit_map.get(canonical, set()):
                if inferred_risk > chokepoint_risk.get(
                    chokepoint,
                    MODELER_BASELINE_RISK,
                ):
                    chokepoint_risk[chokepoint] = inferred_risk
                    inference_source[chokepoint] = f"inferred from {canonical}"
    return chokepoint_risk, inference_source


# ---------------------------------------------------------------------------
# Current SDI Snapshot
# ---------------------------------------------------------------------------

def compute_current_sdi() -> dict[str, Any]:
    """
    Compute the current global Supply Disruption Index from local cache data.

    No network calls are allowed here. Missing feeds contribute zero and are
    surfaced through status fields instead of being interpreted as disruption.
    """
    now = datetime.now(timezone.utc)

    # Decay each event's severity from the article timestamp. Confidence is
    # not folded into the risk itself; it only widens the confidence band.
    # Max aggregation models the worst active incident without letting repeated
    # headlines inflate the result.
    events = fetch_risk_events(limit=50)
    ranked_events = [(_event_risk(event, now), event) for event in events]
    p_risk, max_event = max(
        ranked_events,
        key=lambda item: item[0],
        default=(MODELER_BASELINE_RISK, None),
    )
    confidence_for_band = (
        (
            0.5
            if max_event.get("confidence") is None
            else float(max_event["confidence"])
        )
        if max_event
        else 0.3
    )
    event_source_at = _event_timestamp(max_event) if max_event else None
    top_region = max_event.get("region", "-") if max_event else "-"
    top_chokepoints = (
        (max_event.get("affected_chokepoints", []) or []) if max_event else []
    )

    # Compare only observed tanker regions. An empty or untyped snapshot is
    # unavailable data, not proof that every chokepoint is empty.
    vessels = fetch_vessels()
    fresh_vessels, region_counts_tanker, type_coverage, coverage_sufficient = (
        _ais_tanker_snapshot(vessels, now)
    )

    # Preferred path: each region measured against its own rolling median, so
    # partial AIS type coverage biases both sides equally and cancels.
    delta_d, ais_status, density_detail = _self_calibrated_density(now)

    if ais_status != "available":
        # Fallback to the legacy hand-set baselines, which demand high coverage
        # precisely because the two sides are measured differently.
        eligible_vessel_risks = [
            (region, normalise_vessel_density_delta(current, _VESSEL_BASELINES[region]))
            for region, current in region_counts_tanker.items()
            if region in _VESSEL_BASELINES
        ]
        if not fresh_vessels:
            delta_d = 0.0
            ais_status = "unavailable"
        elif coverage_sufficient:
            delta_d = flow_weighted_risk(
                [_CHOKEPOINT_FLOWS.get(region, 1.0) for region, _ in eligible_vessel_risks],
                [risk for _, risk in eligible_vessel_risks],
            )
            ais_status = "available"
        else:
            delta_d = 0.0
            ais_status = "partial"
        density_detail = {**density_detail, "source": "static-baseline fallback"}
    else:
        density_detail = {**density_detail, "source": "self-calibrated"}
    vessel_times = [
        timestamp
        for timestamp in (
            _as_utc_datetime(vessel.get("recorded_at"))
            for vessel in fresh_vessels
        )
        if timestamp
    ]
    vessel_source_at = max(vessel_times, default=None)

    # Market statistics are cache-backed. A missing feed contributes zero and
    # is exposed as unavailable rather than silently receiving a neutral score.
    brent = get_brent_rolling_stats()
    freight = get_freight_rolling_stats()
    brent_present = brent.get("status") == "available"
    freight_present = freight.get("status") == "available"
    brent_available = _market_feed_is_fresh(brent, now)
    freight_available = _market_feed_is_fresh(freight, now)
    delta_p = (
        normalise_price_delta(
            current_price=brent["current_price"],
            rolling_mean=brent["rolling_mean"],
            rolling_std=brent["rolling_std"],
        )
        if brent_available
        else 0.0
    )
    delta_f = get_current_freight_index(now=now, stats=freight) if freight_available else 0.0
    if brent_available and freight_available:
        market_status = "available"
    elif brent_available or freight_available:
        market_status = "partial"
    elif brent_present or freight_present:
        market_status = "stale"
    else:
        market_status = "unavailable"

    market_dates = [
        str(value)
        for value in (brent.get("latest_date"), freight.get("latest_date"))
        if value
    ]
    market_source_date = min(market_dates) if market_dates else None

    sdi = supply_disruption_index(
        p_risk=p_risk,
        delta_d_vessel=delta_d,
        delta_p_price=delta_p,
        delta_p_freight=delta_f,
    )

    # Apply uncertainty only to the geopolitical component's actual weight.
    sdi_component = p_risk * _W1 * 100.0
    margin = sdi_component * (1.0 - confidence_for_band)
    confidence_low = max(0.0, sdi - margin)
    confidence_high = min(100.0, sdi + margin)

    chokepoint_risks, _ = _active_chokepoint_risks(events, now)
    risk_weighted_affected_flow = sum(
        _CHOKEPOINT_FLOWS[chokepoint] * risk
        for chokepoint, risk in chokepoint_risks.items()
        if chokepoint in _CHOKEPOINT_FLOWS and risk > ELEVATED_RISK_THRESHOLD
    )
    price_impact = estimate_price_impact(
        disruption_probability=1.0,
        chokepoint_flow_mb_per_day=risk_weighted_affected_flow,
    ) if risk_weighted_affected_flow else 0.0

    return {
        "sdi_score": sdi,
        "sdi_band": sdi_band(sdi),
        "confidence_low": round(confidence_low, 1),
        "confidence_high": round(confidence_high, 1),
        "p_risk": round(p_risk, 3),
        "delta_d": round(delta_d, 3),
        "delta_p": round(delta_p, 3),
        "delta_f": round(delta_f, 3),
        "current_brent": brent.get("current_price", 0.0),
        "current_freight": freight.get("current_price", 0.0),
        "price_impact_usd": price_impact,
        "top_region": top_region,
        "top_chokepoints": top_chokepoints,
        "vessel_count": len(fresh_vessels),
        "tanker_count": sum(region_counts_tanker.values()),
        "ais_type_coverage": round(type_coverage, 3),
        "vessel_density_detail": density_detail,
        "active_alerts": sum(risk > ELEVATED_RISK_THRESHOLD for risk, _ in ranked_events),
        "gemini_configured": bool(os.getenv("GEMINI_API_KEY", "")),
        "ais_configured": bool(os.getenv("AISSTREAM_API_KEY", "")),
        "ais_status": ais_status,
        "market_status": market_status,
        "event_source_at": _iso(event_source_at),
        "vessel_source_at": _iso(vessel_source_at),
        "market_source_date": market_source_date,
        "computed_at": now.isoformat(),
        "updated_at": _iso(event_source_at) or now.isoformat(),
        "w1": _W1,
        "w2": _W2,
        "w3": _W3,
        "w4": _W4,
        "confidence": confidence_for_band,
    }


# ---------------------------------------------------------------------------
# Per-Chokepoint Risk Summary
# ---------------------------------------------------------------------------
def compute_chokepoint_risk_matrix() -> list[dict[str, Any]]:
    """
    Build a per-chokepoint risk matrix for the Reroute Matrix tab.

    Returns:
        List of dicts: name, flow_mb_day, risk_score, sdi_contribution,
        vessels_current, vessels_baseline, price_impact_usd.
    """
    events = fetch_risk_events(limit=20)
    vessels = fetch_vessels()
    now = datetime.now(timezone.utc)

    # Same freshness filter and density gate as the global SDI: a sparse
    # 120-second snapshot must not be read as route avoidance here either.
    _, region_counts_tanker, _, coverage_sufficient = _ais_tanker_snapshot(
        vessels,
        now,
    )

    chokepoint_risk, chokepoint_inference_source = _active_chokepoint_risks(
        events,
        now,
    )

    matrix = []
    for cp_name, flow_mb in _CHOKEPOINT_FLOWS.items():
        risk = chokepoint_risk.get(cp_name, MODELER_BASELINE_RISK)
        baseline = _VESSEL_BASELINES.get(cp_name, 10)
        current  = region_counts_tanker.get(cp_name, baseline)
        delta_d  = (
            normalise_vessel_density_delta(current, baseline)
            if coverage_sufficient
            else 0.0
        )
        sdi_contrib = supply_disruption_index(
            p_risk=risk,
            delta_d_vessel=delta_d,
            delta_p_price=0.0,
            delta_p_freight=0.0,
        )
        matrix.append({
            "name":             cp_name,
            "flow_mb_day":      flow_mb,
            "risk_score":       round(risk, 3),
            "inference_source": chokepoint_inference_source.get(cp_name),
            "sdi_contribution": sdi_contrib,
            "vessels_current":  current,
            "vessels_baseline": baseline,
            "ais_signal_used":  coverage_sufficient,
            "price_impact_usd": estimate_price_impact(risk, flow_mb),
        })

    return sorted(matrix, key=lambda x: (x["risk_score"], x["flow_mb_day"]), reverse=True)


# ---------------------------------------------------------------------------
# Score Attribution (drill-down)
# ---------------------------------------------------------------------------

def _event_stub(event: dict[str, Any], now: datetime) -> dict[str, Any]:
    """Compact event record for a drill-down list."""
    ts = _event_timestamp(event)
    return {
        "id": event.get("id"),
        "region": event.get("region"),
        "disruption_type": event.get("disruption_type"),
        "severity": round(float(event.get("severity") or 0.0), 3),
        "confidence": event.get("confidence"),
        "summary": event.get("summary"),
        "source_urls": event.get("source_urls") or [],
        "source_fetched_at": _iso(ts),
        "age_hours": round((now - ts).total_seconds() / 3600.0, 1) if ts else None,
    }


def explain_chokepoint_risk(name: str) -> dict[str, Any] | None:
    """Break down how a chokepoint's risk score was produced.

    Risk is a max, not a sum, so exactly one event sets the score. This returns
    that event plus every other contender and the multiplier each received, so
    the number can be audited rather than trusted.
    """
    canonical = canonical_chokepoint_name(name)
    if canonical not in _CHOKEPOINT_FLOWS:
        return None

    now = datetime.now(timezone.utc)
    events = fetch_risk_events(limit=50)
    transit_map = _producer_transit_map()

    contributors: list[dict[str, Any]] = []
    for event in events:
        direct_field = event.get("directly_affected_chokepoints")
        affected = set(event.get("affected_chokepoints") or [])
        direct = affected if direct_field is None else set(direct_field)

        contribution: float | None = None
        basis = ""
        multiplier = 1.0

        if canonical in direct:
            contribution = _event_risk(event, now)
            basis = "directly named as affected"
        elif canonical in affected:
            multiplier = CHOKEPOINT_INDIRECT_MENTION_DISCOUNT
            contribution = _event_risk(event, now, multiplier)
            basis = "mentioned regionally, not directly targeted"
        elif not affected:
            for raw_country in event.get("affected_producer_countries") or []:
                country = canonical_country_name(raw_country)
                if canonical in transit_map.get(country, set()):
                    multiplier = PRODUCER_CHOKEPOINT_INFER_DISCOUNT
                    contribution = _event_risk(event, now, multiplier)
                    basis = f"inferred from {country} export routing"
                    break

        if contribution is None:
            continue
        contributors.append({
            **_event_stub(event, now),
            "contribution": round(contribution, 3),
            "multiplier": multiplier,
            "basis": basis,
        })

    contributors.sort(key=lambda c: c["contribution"], reverse=True)
    risk = contributors[0]["contribution"] if contributors else MODELER_BASELINE_RISK
    flow = _CHOKEPOINT_FLOWS[canonical]

    return {
        "name": canonical,
        "risk_score": round(risk, 3),
        "flow_mb_day": flow,
        "price_impact_usd": estimate_price_impact(risk, flow),
        "is_baseline": not contributors,
        "baseline_risk": MODELER_BASELINE_RISK,
        "elevated_threshold": ELEVATED_RISK_THRESHOLD,
        "driver": contributors[0] if contributors else None,
        "contributors": contributors[:8],
        "dependent_producers": sorted(
            country for country, cps in transit_map.items() if canonical in cps
        ),
        "explanation": (
            f"Score is the highest single active event contribution. "
            f"Aggregation is max, not sum, so repeated coverage of one incident "
            f"cannot inflate it."
            if contributors
            else "No active event references this chokepoint; it sits at the baseline floor."
        ),
    }


def explain_producer_risk(name: str) -> dict[str, Any] | None:
    """Break down how a producer country's risk score was produced."""
    canonical = canonical_country_name(name)
    known = _known_producer_countries()
    if canonical not in known:
        return None

    now = datetime.now(timezone.utc)
    events = fetch_risk_events(limit=50)
    transit_map = _producer_transit_map()
    own_chokepoints = sorted(transit_map.get(canonical, set()))

    contributors: list[dict[str, Any]] = []
    for event in events:
        chokepoints = set(event.get("affected_chokepoints") or [])
        explicit_direct = event.get("directly_affected_producer_countries") or []
        if not explicit_direct and not chokepoints:
            explicit_direct = event.get("affected_producer_countries") or []
        if not explicit_direct and not chokepoints:
            explicit_direct = _producers_named_in_region(
                str(event.get("region") or ""), known
            )
        named = {canonical_country_name(c) for c in explicit_direct}

        if canonical in named:
            contributors.append({
                **_event_stub(event, now),
                "contribution": round(_event_risk(event, now), 3),
                "multiplier": 1.0,
                "exposure_type": "direct",
                "basis": "country named as directly impacted",
            })
            continue

        exposed = set(own_chokepoints).intersection(chokepoints)
        if exposed:
            contributors.append({
                **_event_stub(event, now),
                "contribution": round(
                    _event_risk(event, now, PRODUCER_CHOKEPOINT_INFER_DISCOUNT), 3
                ),
                "multiplier": PRODUCER_CHOKEPOINT_INFER_DISCOUNT,
                "exposure_type": "transit",
                "basis": "export routes cross " + ", ".join(sorted(exposed)),
            })

    contributors.sort(key=lambda c: c["contribution"], reverse=True)
    top = contributors[0] if contributors else None

    return {
        "name": canonical,
        "risk_score": round(top["contribution"], 3) if top else MODELER_BASELINE_RISK,
        "exposure_type": top["exposure_type"] if top else "baseline",
        "is_baseline": not contributors,
        "baseline_risk": MODELER_BASELINE_RISK,
        "transit_chokepoints": own_chokepoints,
        "transit_discount": PRODUCER_CHOKEPOINT_INFER_DISCOUNT,
        "driver": top,
        "contributors": contributors[:8],
        "explanation": (
            "Direct impairment scores at full severity; exposure that is only "
            f"via a transiting chokepoint is discounted to "
            f"{PRODUCER_CHOKEPOINT_INFER_DISCOUNT:.0%}. The score is the highest "
            "single contribution, not a sum."
            if contributors
            else "No active event names this producer or its transit routes."
        ),
    }


# ---------------------------------------------------------------------------
# Per-Producer Risk Summary
# ---------------------------------------------------------------------------

def _producers_named_in_region(region: str, known: set[str]) -> list[str]:
    """Producer countries named in a free-text region label.

    Matches on word boundaries so "Russia, Central Asia" resolves to Russia
    while a substring collision (e.g. "Oman" inside "Romania") does not.
    """
    if not region:
        return []
    found = []
    for country in known:
        if not country:
            continue
        if re.search(rf"\b{re.escape(country)}\b", region, flags=re.IGNORECASE):
            found.append(country)
    return found


def compute_producer_country_risk_matrix() -> list[dict[str, Any]]:
    """
    Build producer risk from direct impairment and discounted transit exposure.

    Countries are canonicalised against the Neo4j export-port population. A
    chokepoint incident raises only producers whose export routes use that
    chokepoint, at a documented discount. Country names merely mentioned as
    actors do not receive the incident's full severity.
    """
    events = fetch_risk_events(limit=50)
    now = datetime.now(timezone.utc)
    known_countries = _known_producer_countries()
    transit_map = _producer_transit_map()

    state: dict[str, dict[str, Any]] = {
        country: {
            "risk_score": MODELER_BASELINE_RISK,
            "exposure_type": "baseline",
            "risk_driver": None,
            "source_event_id": None,
        }
        for country in known_countries
    }

    def apply_candidate(
        country: str,
        candidate: float,
        exposure_type: str,
        driver: str,
        event_id: Any,
    ) -> None:
        if country not in state:
            return
        if candidate > float(state[country]["risk_score"]):
            state[country] = {
                "risk_score": candidate,
                "exposure_type": exposure_type,
                "risk_driver": driver,
                "source_event_id": event_id,
            }

    for event in events:
        chokepoints = set(event.get("affected_chokepoints") or [])
        explicit_direct = (
            event.get("directly_affected_producer_countries") or []
        )

        # Older producer-only rows predate the explicit direct-impact field.
        # They are safe to interpret as direct only when no chokepoint was
        # attached; mixed/chokepoint rows remain transit exposure.
        if not explicit_direct and not chokepoints:
            explicit_direct = event.get("affected_producer_countries") or []

        # Last resort: the scorer sometimes names the country only in `region`
        # ("Russia", "Russia, Central Asia") and leaves both producer arrays
        # empty. Those events previously scored nothing at all, leaving a
        # producer at baseline while its own disruption sat in the feed.
        if not explicit_direct and not chokepoints:
            explicit_direct = _producers_named_in_region(
                str(event.get("region") or ""),
                known_countries,
            )

        for raw_country in explicit_direct:
            country = canonical_country_name(raw_country)
            apply_candidate(
                country,
                _event_risk(event, now),
                "direct",
                str(event.get("summary") or event.get("disruption_type") or ""),
                event.get("id"),
            )

        if chokepoints:
            for country in known_countries:
                exposed = transit_map.get(country, set()).intersection(chokepoints)
                if not exposed:
                    continue
                apply_candidate(
                    country,
                    _event_risk(
                        event,
                        now,
                        PRODUCER_CHOKEPOINT_INFER_DISCOUNT,
                    ),
                    "transit",
                    ", ".join(sorted(exposed)),
                    event.get("id"),
                )

    matrix = [
        {
            "name": country,
            "risk_score": round(float(values["risk_score"]), 3),
            "exposure_type": values["exposure_type"],
            "risk_driver": values["risk_driver"],
            "source_event_id": values["source_event_id"],
        }
        for country, values in state.items()
    ]
    return sorted(
        matrix,
        key=lambda row: (-row["risk_score"], row["name"]),
    )


# ---------------------------------------------------------------------------
# Resilience Score for a Set of Alternatives
# ---------------------------------------------------------------------------
def score_alternatives(alternatives: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Compute a resilience score and enriched metadata for a list of route alternatives.

    Args:
        alternatives: Output from neo4j find_alternative_routes() (legacy route list).

    Returns:
        Dict with resilience_score and annotated alternatives list.
    """
    if not alternatives:
        return {"resilience_score": 0.0, "alternatives": []}

    avg_detour = sum(a.get("detour_days", 0) for a in alternatives) / len(alternatives)
    avg_cost   = sum(a.get("cost_premium_pct", 0) for a in alternatives) / len(alternatives)

    resilience = compute_resilience_score(
        num_alternatives=len(alternatives),
        avg_detour_days=avg_detour,
        avg_cost_premium_pct=avg_cost,
    )

    # Rank alternatives by composite score.
    # If landed_cost_usd is present (full procurement matrix), incorporate it.
    for alt in alternatives:
        landed   = alt.get("landed_cost_usd", 0.0)
        has_cost = landed > 0

        cost_comp   = (1 - min(landed / (FIXER_BRENT_FALLBACK_USD * 1.5), 1)) * 0.15 if has_cost else 0.0
        route_comp  = (1 - alt.get("risk_score", 0.5)) * (0.40 if has_cost else 0.50)
        detour_comp = (1 - min(alt.get("detour_days", 10) / 30, 1)) * (0.25 if has_cost else 0.30)
        prem_comp   = (1 - min(alt.get("cost_premium_pct", 20) / 50, 1)) * 0.20

        alt["composite_score"] = round(route_comp + detour_comp + prem_comp + cost_comp, 3)

    ranked = sorted(alternatives, key=lambda x: x["composite_score"], reverse=True)

    return {"resilience_score": resilience, "alternatives": ranked}
