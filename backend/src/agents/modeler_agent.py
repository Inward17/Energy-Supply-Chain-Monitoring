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
from datetime import datetime, timezone
from typing import Any

from src.database.postgres_db import (
    fetch_risk_events,
    fetch_vessels,
    fetch_latest_prices,
    fetch_latest_sdi,
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
from src.utils.constants import MODELER_BASELINE_RISK, TANKER_SHIP_TYPES

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


# ---------------------------------------------------------------------------
# Current SDI Snapshot
# ---------------------------------------------------------------------------

def compute_current_sdi() -> dict[str, Any]:
    """
    Compute the current global Supply Disruption Index from live cache data.

    Returns:
        Dict with: sdi_score, p_risk, delta_d, delta_p, current_brent,
                   price_impact_usd, top_region, top_chokepoints.
    """
    # P_risk — latest from risk_events table
    events = fetch_risk_events(limit=5)
    max_event = max(events, key=lambda e: float(e.get("severity", 0)), default=None)
    p_risk = float(max_event.get("severity", 0)) if max_event else 0.0
    confidence_for_band = float(max_event.get("confidence", 0.5)) if max_event else 0.3
    updated_at = max_event.get("created_at") if max_event and max_event.get("created_at") else datetime.now(timezone.utc)
    if not isinstance(updated_at, str):
        updated_at = updated_at.isoformat()

    top_event = events[0] if events else {}
    top_region = top_event.get("region", "—")
    top_chokepoints = top_event.get("affected_chokepoints", []) or []

    # ΔD_vessel — aggregate vessel count vs baselines (tankers only)
    vessels = fetch_vessels()
    region_counts_tanker: dict[str, int] = {}
    for v in vessels:
        region = v.get("region", "Unknown")
        if v.get("ship_type") in TANKER_SHIP_TYPES:
            region_counts_tanker[region] = region_counts_tanker.get(region, 0) + 1

    delta_d_values = []
    for region, baseline in _VESSEL_BASELINES.items():
        current = region_counts_tanker.get(region, 0)
        delta_d_values.append(normalise_vessel_density_delta(current, baseline))
    delta_d = sum(delta_d_values) / len(delta_d_values) if delta_d_values else 0.0

    # ΔP_price — Brent vs 30-day mean
    brent = get_brent_rolling_stats()
    delta_p = normalise_price_delta(
        current_price=brent["current_price"],
        rolling_mean=brent["rolling_mean"],
        rolling_std=brent["rolling_std"],
    )

    # ΔP_freight — BOAT vs 35-day mean
    freight = get_freight_rolling_stats()
    delta_f = normalise_freight_delta(
        current_freight=freight["current_price"],
        rolling_mean=freight["rolling_mean"],
        rolling_std=freight["rolling_std"],
    )

    sdi = supply_disruption_index(p_risk=p_risk, delta_d_vessel=delta_d, delta_p_price=delta_p, delta_p_freight=delta_f)

    # Confidence band derived from geopolitical signal reliability.
    # The margin is scaled only against the P_risk (Gemini) component's contribution.
    sdi_component = p_risk * 50.0
    margin = sdi_component * (1.0 - confidence_for_band)
    confidence_low = max(0.0, sdi - margin)
    confidence_high = min(100.0, sdi + margin)

    # Price impact: use highest-risk chokepoint flow
    flow = max((_CHOKEPOINT_FLOWS.get(cp, 1.0) for cp in top_chokepoints), default=1.0)
    price_impact = estimate_price_impact(
        disruption_probability=p_risk,
        chokepoint_flow_mb_per_day=flow,
    )

    return {
        "sdi_score":        sdi,
        "confidence_low":   round(confidence_low, 1),
        "confidence_high":  round(confidence_high, 1),
        "p_risk":           round(p_risk, 3),
        "delta_d":          round(delta_d, 3),
        "delta_p":          round(delta_p, 3),
        "delta_f":          round(delta_f, 3),
        "current_brent":    brent["current_price"],
        "current_freight":  freight["current_price"],
        "price_impact_usd": price_impact,
        "top_region":       top_region,
        "top_chokepoints":  top_chokepoints,
        "vessel_count":     len(vessels),
        "tanker_count":     sum(region_counts_tanker.values()),
        "active_alerts":    len([e for e in events if float(e.get("severity", 0)) > 0.5]),
        "gemini_configured": bool(os.getenv("GEMINI_API_KEY", "")),
        "ais_configured":    bool(os.getenv("AISSTREAM_API_KEY", "")),
        "w1":               _W1,
        "w2":               _W2,
        "w3":               _W3,
        "w4":               _W4,
        "confidence":       confidence_for_band,
        "updated_at":       updated_at,
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

    # Count vessels per region (tankers only for SDI)
    region_counts_tanker: dict[str, int] = {}
    for v in vessels:
        region = v.get("region", "Unknown")
        if v.get("ship_type") in TANKER_SHIP_TYPES:
            region_counts_tanker[region] = region_counts_tanker.get(region, 0) + 1

    # Map event severity to chokepoints
    chokepoint_risk: dict[str, float] = {}
    for event in events:
        cps = event.get("affected_chokepoints") or []
        sev = float(event.get("severity", 0))
        for cp in cps:
            chokepoint_risk[cp] = max(chokepoint_risk.get(cp, 0.0), sev)

    matrix = []
    for cp_name, flow_mb in _CHOKEPOINT_FLOWS.items():
        risk = chokepoint_risk.get(cp_name, MODELER_BASELINE_RISK)
        baseline = _VESSEL_BASELINES.get(cp_name, 10)
        current  = region_counts_tanker.get(cp_name, baseline)
        delta_d  = normalise_vessel_density_delta(current, baseline)
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
            "sdi_contribution": sdi_contrib,
            "vessels_current":  current,
            "vessels_baseline": baseline,
            "price_impact_usd": estimate_price_impact(risk, flow_mb),
        })

    return sorted(matrix, key=lambda x: (x["risk_score"], x["flow_mb_day"]), reverse=True)


# ---------------------------------------------------------------------------
# Per-Producer Risk Summary
# ---------------------------------------------------------------------------

def compute_producer_country_risk_matrix() -> list[dict[str, Any]]:
    """
    Build a per-producer risk matrix for the Reroute Matrix tab.
    Aggregates risk score for producer nations using the same max-severity logic as chokepoints.

    Returns:
        List of dicts: name, risk_score.
    """
    events = fetch_risk_events(limit=20)
    
    producer_risk: dict[str, float] = {}
    for event in events:
        countries = event.get("affected_producer_countries") or []
        sev = float(event.get("severity", 0))
        for country in countries:
            producer_risk[country] = max(producer_risk.get(country, 0.0), sev)
            
    # Fetch baseline of all known producers from the knowledge graph
    common_producers = []
    try:
        from src.database.neo4j_graph import get_driver
        driver = get_driver()
        if driver:
            with driver.session() as session:
                res = session.run("MATCH (p:ExportPort) RETURN DISTINCT p.country AS c")
                common_producers = [r["c"] for r in res if r["c"]]
    except Exception:
        pass
        
    if not common_producers:
        common_producers = ["Russia", "Saudi Arabia", "Iran", "Iraq", "UAE", "Kuwait", "Nigeria", "Venezuela"]
    for cp in common_producers:
        if cp not in producer_risk:
            producer_risk[cp] = MODELER_BASELINE_RISK

    matrix = []
    for country, risk in producer_risk.items():
        matrix.append({
            "name": country,
            "risk_score": round(risk, 3)
        })
        
    return sorted(matrix, key=lambda x: x["risk_score"], reverse=True)


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

        cost_comp   = (1 - min(landed / 120.0, 1)) * 0.15 if has_cost else 0.0
        route_comp  = (1 - alt.get("risk_score", 0.5)) * (0.40 if has_cost else 0.50)
        detour_comp = (1 - min(alt.get("detour_days", 10) / 30, 1)) * (0.25 if has_cost else 0.30)
        prem_comp   = (1 - min(alt.get("cost_premium_pct", 20) / 50, 1)) * 0.20

        alt["composite_score"] = round(route_comp + detour_comp + prem_comp + cost_comp, 3)

    ranked = sorted(alternatives, key=lambda x: x["composite_score"], reverse=True)

    return {"resilience_score": resilience, "alternatives": ranked}

