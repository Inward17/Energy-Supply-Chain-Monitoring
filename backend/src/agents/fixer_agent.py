"""
src/agents/fixer_agent.py
──────────────────────────
Adaptive Procurement Orchestrator — the 5-step rerouting engine.

Given a blocked chokepoint + optional crude grade, executes:
  Step 1: Chemical Constraint  — grade-compatible refinery matching
  Step 2: Spatial Traversal    — export ports that bypass the blockade
  Step 3: Financial Math       — landed cost = Brent spot + VLCC freight premium
  Step 4: Lead Time            — distance / VLCC speed formula
  Step 5: Ranking              — sort by landed cost or lead time; composite score

All data comes from local PostgreSQL (prices) and local Neo4j (graph).
Zero external API calls are made at query time.
"""

from __future__ import annotations

import logging
from typing import Any

import searoute as sr

from src.database.neo4j_graph import (
    find_export_ports_bypassing,
    find_alternative_routes,
    match_refineries_to_crude,
    get_all_chokepoints,
    get_all_refineries,
    get_refinery_coords,
    get_crude_specs,
    get_grade_suppliers,
    get_driver,
)
from src.database.postgres_db import fetch_latest_prices, fetch_risk_events
from src.agents.modeler_agent import get_current_freight_index, score_alternatives
from src.utils.constants import (
    CHOKEPOINTS,
    FIXER_BRENT_FALLBACK_USD,
    FIXER_FALLBACK_DISTANCE_NM,
    FIXER_WORST_CASE_LEAD_DAYS,
    FIXER_WEIGHT_COST,
    FIXER_WEIGHT_TIME,
    FIXER_WEIGHT_RISK,
    FIXER_WEIGHT_CONGESTION,
    VLCC_DAILY_CHARTER_USD,
    VLCC_CARGO_BARRELS,
    VLCC_SPEED_KNOTS,
    FREIGHT_RATE_SENSITIVITY,
    SANCTIONED_SOURCE_COUNTRIES,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Financial Constants
# ---------------------------------------------------------------------------

# VLCC (Very Large Crude Carrier) economic parameters
# (Imported from constants.py)
NAUTICAL_MILES_PER_DAY   = VLCC_SPEED_KNOTS * 24  # ~312 NM/day

# Kilometres per nautical mile (for searoute output conversion)
_KM_PER_NM = 1.852

# Default destination used when no refinery is selected
_DEFAULT_DESTINATION = "Jamnagar"  # Largest import refinery — India west coast

# ── Conditional Detour Map ────────────────────────────────────────────────
# For each blocked chokepoint, defines which transit chokepoints in the
# export port's SHIPS_THROUGH list would be affected.
# A detour only applies if the port's natural route would cross the blockade.
#
# Format: blocked_chokepoint -> {detour_days, affected_transit_markers}
# affected_transit_markers: strings that, if present in port's transit
# chokepoints, indicate this port WOULD normally use the blocked route.
_CHOKEPOINT_DETOUR: dict[str, dict] = {
    "Strait of Hormuz":    {"detour_days": 0,  "triggers": ["Strait of Hormuz"]},
    "Suez Canal":          {"detour_days": 14, "triggers": ["Suez Canal", "Bab-el-Mandeb"]},
    "Bab-el-Mandeb":       {"detour_days": 14, "triggers": ["Bab-el-Mandeb", "Suez Canal"]},
    "Strait of Malacca":   {"detour_days": 4,  "triggers": ["Strait of Malacca"]},
    "Turkish Straits":     {"detour_days": 5,  "triggers": ["Turkish Straits"]},
    "Strait of Gibraltar": {"detour_days": 3,  "triggers": ["Strait of Gibraltar"]},
    "Panama Canal":        {"detour_days": 10, "triggers": ["Panama Canal"]},
}

# ``searoute`` can explicitly avoid these named passages. Where the library
# has coverage, a route-specific detour replaces the old fixed-day heuristic.
_SEAROUTE_RESTRICTIONS: dict[str, str] = {
    "Suez Canal": "suez",
    "Bab-el-Mandeb": "babalmandab",
    "Turkish Straits": "bosporus",
    "Strait of Gibraltar": "gibraltar",
    "Panama Canal": "panama",
    "Strait of Hormuz": "ormuz",
}


# ---------------------------------------------------------------------------
# Step 3 Helper: Freight Premium Calculation
# ---------------------------------------------------------------------------

def _compute_freight_premium(
    voyage_days: float,
    freight_index: float = 0.5,
) -> float:
    """
    Calculate freight cost per barrel from total voyage days.

    The live freight index is neutral at 0.50. Above-neutral freight raises
    the effective charter rate, while a calm market lowers it symmetrically.

    Formula:
      effective_rate = base_rate × (1 + (index - 0.5) × sensitivity)
      premium = effective_rate × voyage_days / cargo_barrels
    """
    index = max(0.0, min(1.0, float(freight_index)))
    effective_daily_rate = VLCC_DAILY_CHARTER_USD * (
        1.0 + (index - 0.5) * FREIGHT_RATE_SENSITIVITY
    )
    return round((effective_daily_rate * voyage_days) / VLCC_CARGO_BARRELS, 2)


def _worst_blend_congestion(congestion_scores: list[float]) -> float:
    """A blend is constrained by its most congested required supply leg."""
    return max(congestion_scores, default=0.5)


# ---------------------------------------------------------------------------
# Conditional Detour — Bug Fix #2
# ---------------------------------------------------------------------------

def get_conditional_detour(blocked_chokepoint: str, port_transit_chokepoints: list[str]) -> int:
    """
    Return detour penalty days ONLY if this port's natural route would
    actually cross the blocked chokepoint.

    Bug fixed: previously ALL ports received the same flat detour, making
    nearby ports (e.g. UK -> Rotterdam) artificially expensive.

    Args:
        blocked_chokepoint:      The chokepoint declared as blocked.
        port_transit_chokepoints: List of chokepoints this port normally
                                  SHIPS_THROUGH on its natural route.

    Returns:
        Detour days (int). 0 if this port's route never crosses the blockade.
    """
    config = _CHOKEPOINT_DETOUR.get(blocked_chokepoint)
    if not config:
        return 0

    triggers = config["triggers"]
    # If the port's natural route shares any trigger with the blockade, apply detour
    if any(t in port_transit_chokepoints for t in triggers):
        return config["detour_days"]

    return 0  # Port's route does NOT cross the blockade — no penalty


# ---------------------------------------------------------------------------
# Step 4 Helper: Lead Time via Marine Routing — Bug Fix #1
# ---------------------------------------------------------------------------

def _compute_lead_time(
    port_lon: float,
    port_lat: float,
    dest_lon: float,
    dest_lat: float,
    extra_detour_days: float = 0,
    blocked_chokepoint: str | None = None,
) -> float:
    """
    Calculate total voyage lead time using searoute marine routing.

    searoute traces actual sea lanes (avoids land), preventing the
    'Flying Ship Bug' where geopy would route Novorossiysk → Rotterdam
    straight over Ukraine. IMPORTANT: searoute takes [lon, lat] order.

    When supported by ``searoute``, an affected passage is restricted and the
    actual additional nautical miles are used. Static detour days remain a
    fallback for passages the route engine cannot restrict.
    """
    try:
        route = sr.searoute([port_lon, port_lat], [dest_lon, dest_lat], units="km")
        dist_km = route["properties"]["length"]
    except Exception as exc:
        # Graceful fallback to straight-line if searoute fails (e.g. same port as dest)
        logger.debug("searoute failed (%s) — using haversine fallback", exc)
        from math import radians, cos, sin, asin, sqrt
        lat1, lat2 = radians(port_lat), radians(dest_lat)
        dlon = radians(dest_lon - port_lon)
        dlat = radians(dest_lat - port_lat)
        a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
        dist_km = 2 * 6371 * asin(sqrt(a))
    fallback_detour_days = extra_detour_days

    restriction = _SEAROUTE_RESTRICTIONS.get(blocked_chokepoint or "")
    if dist_km and extra_detour_days > 0 and restriction:
        try:
            detour_route = sr.searoute(
                [port_lon, port_lat],
                [dest_lon, dest_lat],
                units="km",
                restrictions=["northwest", restriction],
            )
            detour_km = detour_route["properties"]["length"]
            if detour_km > dist_km:
                dist_km = detour_km
                fallback_detour_days = 0
        except Exception as exc:
            logger.debug(
                "searoute restriction '%s' failed (%s) — using static detour fallback",
                restriction,
                exc,
            )

    dist_nm = dist_km / _KM_PER_NM
    base_days = dist_nm / NAUTICAL_MILES_PER_DAY
    return round(base_days + fallback_detour_days, 1)


# ---------------------------------------------------------------------------
# Step 5 Helper: Composite Score
# ---------------------------------------------------------------------------

def _composite_score(
    landed_cost: float,
    lead_time: float,
    risk_score: float,
    brent_price: float,
    congestion_score: float = 0.5,
) -> float:
    """
    Compute a normalised composite procurement score (0–1, higher = better).

    Weights:
      cost       (inverse, cheaper = better)
      lead time  (inverse, faster = better)
      route risk (inverse, safer = better)
      congestion (inverse, less congested = better)
    """
    max_cost      = brent_price * 1.5 if brent_price > 0 else 120.0
    cost_score    = 1 - min(landed_cost / max_cost, 1)
    time_score    = 1 - min(lead_time / FIXER_WORST_CASE_LEAD_DAYS, 1)
    risk_score_n  = 1 - min(risk_score, 1)
    congestion_factor = 1.0 - min(congestion_score, 1.0)

    return round(
        cost_score * FIXER_WEIGHT_COST +
        time_score * FIXER_WEIGHT_TIME +
        risk_score_n * FIXER_WEIGHT_RISK +
        congestion_factor * FIXER_WEIGHT_CONGESTION,
        3
    )


# ---------------------------------------------------------------------------
# Main Public Interface
# ---------------------------------------------------------------------------

def find_alternatives(
    blocked_chokepoint: str,
    crude_grade: str | None = None,
    ranking_mode: str = "cost",
    destination_refinery: str | None = None,
    excluded_countries: list[str] | None = None,
    strict_grade_match: bool = False,
) -> dict[str, Any]:
    """
    Full 5-step Adaptive Procurement Orchestrator.

    Args:
        blocked_chokepoint:   Chokepoint name, e.g. "Strait of Hormuz".
        crude_grade:          Optional crude grade to filter (e.g. "Arab Light").
        ranking_mode:         "cost" (cheapest first) or "speed" (fastest first).
        destination_refinery: Name of the destination refinery. Defaults to Jamnagar.
        excluded_countries:   List of countries to remove from results.
    """
    dest_name = destination_refinery or _DEFAULT_DESTINATION
    dest_coords = get_refinery_coords(dest_name)
    if dest_coords is None:
        logger.warning("fixer_agent: unknown destination '%s', falling back to Jamnagar.", dest_name)
        dest_name = _DEFAULT_DESTINATION
        dest_coords = get_refinery_coords(_DEFAULT_DESTINATION)
    dest_lat = dest_coords["lat"]
    dest_lon = dest_coords["lon"]

    logger.info(
        "fixer_agent: START — chokepoint='%s'  grade='%s'  mode='%s'  dest='%s' (%.2f, %.2f)",
        blocked_chokepoint, crude_grade or "any", ranking_mode, dest_name, dest_lat, dest_lon,
    )

    # ─── Step 3 prep: Fetch live Brent price from Postgres ──────────────────
    prices = fetch_latest_prices(tickers=["BZ=F"], days=7)
    current_brent = 0.0
    if prices:
        latest = sorted(prices, key=lambda p: str(p.get("trade_date", "")), reverse=True)
        current_brent = float(latest[0].get("price_close", 0.0))

    # Fallback Brent estimate if DB is empty
    if current_brent <= 0:
        current_brent = FIXER_BRENT_FALLBACK_USD
        logger.warning("fixer_agent: No Brent price in DB — using fallback $%.2f/bbl", current_brent)

    # Cache-backed BOAT stress signal shared with the SDI. If its feed is
    # unavailable, the Modeler helper returns 0.50 so existing base pricing is
    # preserved rather than fabricating a stressed freight rate.
    freight_index = get_current_freight_index()

    # ─── Step 1: Chemical Constraint — refinery matching ────────────────────
    refinery_options: list[dict] = []
    grade_suppliers: list[str] = []
    stage_a_count = 1
    if crude_grade:
        refinery_options = match_refineries_to_crude(crude_grade)
        grade_suppliers = get_grade_suppliers(crude_grade)
        stage_a_count = len(grade_suppliers)

    # ─── Step 2: Spatial Graph Traversal — find unblocked export ports ──────
    viable_ports = find_export_ports_bypassing(blocked_chokepoint, crude_grade)
    grade_filtered = crude_grade is not None

    if not viable_ports and crude_grade:
        if strict_grade_match:
            logger.info("fixer_agent: No exact match for grade '%s', strict mode enabled. Returning empty.", crude_grade)
            # DO NOT widen. viable_ports remains empty.
        else:
            logger.info("fixer_agent: No ports for grade '%s', widening to compatible grades.", crude_grade)
            all_ports = find_export_ports_bypassing(blocked_chokepoint, None)
            req_specs = get_crude_specs(crude_grade)

            if req_specs:
                req_api = req_specs["api_gravity"]
                req_sul = req_specs["sulphur_pct"]
                compatible_ports = []
                for p in all_ports:
                    p_api = p.get("api_gravity")
                    p_sul = p.get("sulphur_pct")
                    # If we have specs, apply a basic compatibility filter (e.g., API +/- 4, Sulphur +/- 1.0)
                    if p_api is not None and p_sul is not None:
                        if abs(p_api - req_api) <= 4.0 and abs(p_sul - req_sul) <= 1.0:
                            p["match_type"] = "substitute"
                            p["match_reason"] = f"Similar API gravity ({p_api}° vs {crude_grade}'s {req_api}°)"
                            compatible_ports.append(p)
                    else:
                        # Fallback for ports/grades lacking specs in DB
                        p["match_type"] = "substitute"
                        p["match_reason"] = "Fallback substitute (specs missing)"
                        compatible_ports.append(p)

                # Binary Blending
                blended_ports = []
                seen_pairs = set()

                for i in range(len(all_ports)):
                    for j in range(i + 1, len(all_ports)):
                        p1 = all_ports[i]
                        p2 = all_ports[j]

                        grade1 = p1.get("grade")
                        grade2 = p2.get("grade")
                        port1_name = p1.get("name")
                        port2_name = p2.get("name")

                        # Dedup: same grade, same port, or same country (correlated risk — no diversification)
                        if grade1 == grade2 or port1_name == port2_name:
                            continue
                        if p1.get("country") == p2.get("country"):
                            continue  # same-country blends violate independence assumption

                        # Unordered pair dedup
                        pair_key = tuple(sorted([grade1, grade2]))
                        if pair_key in seen_pairs:
                            continue

                        api1 = p1.get("api_gravity")
                        api2 = p2.get("api_gravity")
                        s1 = p1.get("sulphur_pct")
                        s2 = p2.get("sulphur_pct")

                        if api1 is not None and api2 is not None and s1 is not None and s2 is not None:
                            if api1 == api2:
                                continue

                            w = (req_api - api2) / (api1 - api2)

                            # Explicit bracketing/bounds check
                            if 0.1 <= w <= 0.9:
                                # Sulphur tolerance check
                                blend_s = (w * s1) + ((1 - w) * s2)
                                if abs(blend_s - req_sul) <= 1.0:
                                    seen_pairs.add(pair_key)
                                    w_pct = int(w * 100)
                                    p2_pct = 100 - w_pct

                                    blend_p = {
                                        "name": f"{port1_name} ({w_pct}%) + {port2_name} ({p2_pct}%)",
                                        "country": f"{p1.get('country')} + {p2.get('country')}",
                                        "grade": f"{grade1} + {grade2}",
                                        "match_type": "blend",
                                        "match_reason": f"Blend ratio estimated via linear API gravity interpolation — a simplified model; actual refinery blending may vary.",
                                        "is_blend": True,
                                        "blend_components": [
                                            {"port": p1, "weight": w},
                                            {"port": p2, "weight": 1 - w}
                                        ]
                                    }
                                    blended_ports.append(blend_p)

                viable_ports = compatible_ports + blended_ports
            else:
                # If requested grade lacks specs, just accept all as substitutes
                for p in all_ports:
                    p["match_type"] = "substitute"
                    p["match_reason"] = "Substitute (specs missing for requested grade)"
                viable_ports = all_ports

            # Note: We keep grade_filtered = True because we are still technically filtering by grade (compatibility)
            # but we're widening the net. The UI relies on this flag for some things, but maybe it's fine.
            grade_filtered = True

    stage_b_count = len(viable_ports)

    # ─── Prep for dynamic risk scoring ─────────────────────────────────────
    all_events = fetch_risk_events(limit=50)
    context_events = [
        e for e in all_events
        if blocked_chokepoint in (e.get("affected_chokepoints") or [])
        or blocked_chokepoint.lower() in (e.get("region") or "").lower()
    ][:5]

    # ─── Steps 3, 4, 5: Cost + lead time + ranking ─────────────────────────
    procurement_matrix: list[dict] = []

    for port in viable_ports:
        port_name    = port.get("name", "Unknown Port")
        country      = port.get("country", "Unknown")
        grade        = port.get("grade", crude_grade or "Mixed")
        match_type   = port.get("match_type", "exact")
        match_reason = port.get("match_reason", "")
        port_transits = port.get("transit_chokepoints") or []
        if port.get("is_blend"):
            components = port.get("blend_components", [])
            blend_landed_cost = 0.0
            blend_lead_time = 0.0
            blend_risk_score = 0.0
            blend_extra_detour = 0.0
            blend_congestion_scores: list[float] = []

            for comp in components:
                c_port = comp["port"]
                w = comp["weight"]

                c_transits = c_port.get("transit_chokepoints") or []
                c_detour = get_conditional_detour(blocked_chokepoint, c_transits)

                c_lat = c_port.get("lat") or 0.0
                c_lon = c_port.get("lon") or 0.0
                if c_lat and c_lon:
                    c_time = _compute_lead_time(
                        port_lon=c_lon, port_lat=c_lat,
                        dest_lon=dest_lon, dest_lat=dest_lat,
                        extra_detour_days=c_detour,
                        blocked_chokepoint=blocked_chokepoint,
                    )
                else:
                    c_time = round(FIXER_FALLBACK_DISTANCE_NM / NAUTICAL_MILES_PER_DAY + c_detour, 1)

                c_freight = _compute_freight_premium(
                    voyage_days=c_time,
                    freight_index=freight_index,
                )
                c_cost = current_brent + c_freight

                c_risk = 0.05
                c_country = c_port.get("country", "")
                for ev in all_events:
                    region_str = (ev.get("region") or "").lower()
                    summary_str = (ev.get("summary") or "").lower()
                    if c_country.lower() in region_str or c_country.lower() in summary_str:
                        severity = float(ev.get("severity", 0.0))
                        confidence = float(ev.get("confidence", 0.5))
                        # Use max(), not +=: risk reflects the worst single event,
                        # not an accumulation that trivially caps every multi-event country at 0.95
                        c_risk = max(c_risk, severity * confidence)
                c_risk = min(0.95, c_risk)

                c_cong_raw = c_port.get("congestion_score")
                c_cong = float(c_cong_raw) if c_cong_raw is not None else 0.5

                # Cost is proportional to blend volume; congestion is gated
                # by the most constrained leg below.
                blend_landed_cost += c_cost * w
                blend_congestion_scores.append(c_cong)

                # Max for risk, lead time, extra detour
                blend_lead_time = max(blend_lead_time, c_time)
                blend_risk_score = max(blend_risk_score, c_risk)
                blend_extra_detour = max(blend_extra_detour, c_detour)

            landed_cost = round(blend_landed_cost, 2)
            lead_time = blend_lead_time
            risk_score = blend_risk_score
            congestion_score = _worst_blend_congestion(blend_congestion_scores)
            extra_detour = blend_extra_detour
            freight_prem = round(landed_cost - current_brent, 2)
        else:
            # Missing or unmapped congestion data defaults to 0.5 (neutral)
            raw_congestion = port.get("congestion_score")
            congestion_score = float(raw_congestion) if raw_congestion is not None else 0.5

            # Step 3a — Conditional Detour Penalty
            extra_detour = get_conditional_detour(blocked_chokepoint, port_transits)

            # Step 4 — Lead time (searoute marine distance port -> destination)
            port_lat = port.get("lat") or 0.0
            port_lon = port.get("lon") or 0.0
            if port_lat and port_lon:
                lead_time = _compute_lead_time(
                    port_lon=port_lon, port_lat=port_lat,
                    dest_lon=dest_lon, dest_lat=dest_lat,
                    extra_detour_days=extra_detour,
                    blocked_chokepoint=blocked_chokepoint,
                )
            else:
                # Fallback for ports without coordinates
                lead_time = round(FIXER_FALLBACK_DISTANCE_NM / NAUTICAL_MILES_PER_DAY + extra_detour, 1)

            # Step 3b — Financial math (freight premium based on total lead time)
            freight_prem = _compute_freight_premium(
                voyage_days=lead_time,
                freight_index=freight_index,
            )
            landed_cost  = round(current_brent + freight_prem, 2)

            # Dynamic risk score based on Intelligence pipeline.
            # Baseline is 5%; we take the MAX severity*confidence across all matching events.
            # Using += here would trivially push any country in 2+ moderate events to 0.95,
            # producing the identical-score bucketing bug visible in the Producer Risk Matrix.
            risk_score = 0.05
            for ev in all_events:
                region_str = (ev.get("region") or "").lower()
                summary_str = (ev.get("summary") or "").lower()
                if country.lower() in region_str or country.lower() in summary_str:
                    severity = float(ev.get("severity", 0.0))
                    confidence = float(ev.get("confidence", 0.5))
                    risk_score = max(risk_score, severity * confidence)
            risk_score = min(0.95, risk_score)

        # Step 5 — Composite score
        comp = _composite_score(
            landed_cost=landed_cost,
            lead_time=lead_time,
            risk_score=risk_score,
            brent_price=current_brent,
            congestion_score=congestion_score,
        )

        procurement_matrix.append({
            "export_port":        port_name,
            "country":            country,
            "crude_grade":        grade,
            "brent_spot_usd":     current_brent,
            "freight_premium":    freight_prem,
            "landed_cost_usd":    landed_cost,
            "lead_time_days":     lead_time,
            "risk_score":         risk_score,
            "congestion_score":   congestion_score,
            "composite_score":    comp,
            "extra_detour_days":  extra_detour,
            "recommended":        False,
            "match_type":         match_type,
            "match_reason":       match_reason,
        })

    # Rank
    if ranking_mode == "speed":
        procurement_matrix.sort(key=lambda x: x["lead_time_days"])
    else:  # default: cost
        procurement_matrix.sort(key=lambda x: x["landed_cost_usd"])

    # ─── Step 5: Country filter (optional) ─────────────────────────────────
    stage_b_countries = list({r.get("country", "") for r in procurement_matrix if r.get("country")})

    if excluded_countries:
        banned = {c.lower() for c in excluded_countries}
        before = len(procurement_matrix)
        procurement_matrix = [
            r for r in procurement_matrix
            if r.get("country", "").lower() not in banned
        ]
        removed = before - len(procurement_matrix)
        if removed:
            logger.info(
                "fixer_agent: filter removed %d rows (excluded: %s)",
                removed,
                excluded_countries,
            )

    stage_c_count = len(procurement_matrix)
    diagnostic = None
    if stage_c_count == 0:
        if stage_a_count == 0:
            diagnostic = {
                "reason": "no_data_for_grade",
                "requested_grade": crude_grade or "Any",
                "excluding": excluded_countries or [],
                "grade_suppliers": [],
                "message": f"The crude grade '{crude_grade}' is not recognized in our database."
            }
        elif stage_b_count == 0:
            diagnostic = {
                "reason": "chokepoint_bypass_eliminates_all_grade_sources",
                "requested_grade": crude_grade or "Any",
                "excluding": excluded_countries or [],
                "grade_suppliers": grade_suppliers,
                "message": f"All export sources for {crude_grade or 'your request'} route through {blocked_chokepoint}, which is currently blocked. No bypass route exists for this specific grade."
            }
        else:
            conflicts = [c for c in (excluded_countries or []) if c.lower() in {bc.lower() for bc in stage_b_countries}]
            diagnostic = {
                "reason": "grade_only_available_from_excluded_countries",
                "requested_grade": crude_grade or "Any",
                "excluding": excluded_countries or [],
                "grade_suppliers": conflicts,
                "message": f"{crude_grade or 'Your requested grade'} is supplied almost exclusively by {', '.join(conflicts) if conflicts else 'your excluded countries'}, which is in your excluded countries list. No alternative source exists under these constraints."
            }

    # Mark the top recommendation
    if procurement_matrix:
        procurement_matrix[0]["recommended"] = True

    # Resilience score via modeler (still used for the sidebar gauge)
    legacy_routes = find_alternative_routes(blocked_chokepoint)
    scored        = score_alternatives(legacy_routes)

    logger.info(
        "fixer_agent: DONE — %d viable sources found for %s (Brent=$%.2f)",
        len(procurement_matrix), blocked_chokepoint, current_brent,
    )

    return {
        "blocked_chokepoint":  blocked_chokepoint,
        "crude_grade":         crude_grade,
        "destination_refinery": dest_name,
        "dest_coords":         dest_coords,
        "resilience_score":    scored["resilience_score"],
        "procurement_matrix":  procurement_matrix,
        "diagnostic":          diagnostic,
        # legacy key kept for backward compat
        "alternatives":        scored["alternatives"],
        "refinery_options":    refinery_options,
        "current_brent_usd":   current_brent,
        "freight_params": {
            "vlcc_daily_charter_usd": VLCC_DAILY_CHARTER_USD,
            "freight_index": round(freight_index, 4),
            "effective_daily_charter_usd": round(
                VLCC_DAILY_CHARTER_USD
                * (1.0 + (freight_index - 0.5) * FREIGHT_RATE_SENSITIVITY),
                2,
            ),
            "vlcc_cargo_barrels":     VLCC_CARGO_BARRELS,
            "vlcc_speed_knots":       VLCC_SPEED_KNOTS,
            # We no longer export a single extra_detour_days because it varies per port,
            # but we keep the key at 0 to avoid breaking app.py layout blindly.
            # Real detour is stored per row in procurement_matrix.
            "extra_detour_days":      0,
        },
        "context_events":  context_events,
        "ranking_mode":    ranking_mode,
        "grade_filtered":  grade_filtered,
    }


# ---------------------------------------------------------------------------
# Dropdown Helpers
# ---------------------------------------------------------------------------

def get_chokepoint_list() -> list[str]:
    """Return list of chokepoint names for the dashboard dropdown."""
    try:
        chokepoints = get_all_chokepoints()
        return [cp["name"] for cp in chokepoints]
    except Exception as exc:
        logger.error("get_chokepoint_list failed: %s", exc)
        return CHOKEPOINTS


def get_crude_grade_list() -> list[str]:
    """Return list of supported crude grades sourced from Neo4j (with static fallback).

    Querying the graph ensures this list stays in sync with seeded data —
    adding a new CrudeGrade node will immediately appear in the UI dropdown
    without requiring a code change.
    """
    driver = get_driver()
    if driver:
        try:
            with driver.session() as session:
                result = session.run("MATCH (g:CrudeGrade) RETURN g.name AS name ORDER BY g.name")
                grades = [r["name"] for r in result]
                if grades:
                    return grades
        except Exception as exc:
            logger.warning("get_crude_grade_list: Neo4j query failed (%s), falling back to seed list.", exc)
    # Fallback: derive from seed data so the list is always consistent with _CRUDE_GRADES
    from src.database.neo4j_graph import _CRUDE_GRADES
    return sorted(g["name"] for g in _CRUDE_GRADES)



def get_refinery_list() -> list[str]:
    """Return list of destination refinery names for the dashboard dropdown (sorted by capacity)."""
    try:
        refs = get_all_refineries()
        return [f"{r['name']} ({r['country']})" for r in refs]
    except Exception as exc:
        logger.error("get_refinery_list failed: %s", exc)
        return [f"{r['name']} ({r['country']})" for r in [
            {"name": "Jamnagar",             "country": "India"},
            {"name": "Rotterdam",            "country": "Netherlands"},
            {"name": "Houston Ship Channel", "country": "USA"},
            {"name": "Singapore Jurong",     "country": "Singapore"},
            {"name": "Ulsan",                "country": "South Korea"},
        ]]
