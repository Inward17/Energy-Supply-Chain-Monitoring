"""
src/agents/spr_agent.py
────────────────────────
Strategic Petroleum Reserve (SPR) Optimisation Agent

Calculates India's SPR burn-down trajectory during a supply disruption,
quantifies the "Survival Gap", and generates policy-level demand management
recommendations to ensure continuity before rerouted shipments arrive.

All calculations are deterministic maths — zero external API calls.
"""

from __future__ import annotations

import logging
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# India Macro Constants  (2024/2025 data)
# ---------------------------------------------------------------------------

INDIA_CONSUMPTION_MBPD   = 5.4    # Million barrels per day — total consumption
SPR_CAPACITY_MB          = 39.0   # Total SPR capacity in million barrels
SPR_SITES = {
    "Visakhapatnam": 13.33,
    "Mangaluru":     9.75,
    "Padur":         18.33,
}

# Chokepoint → fraction of India's imports that transit it (2024 data)
_CHOKEPOINT_IMPORT_SHARE: dict[str, float] = {
    "Strait of Hormuz":      0.40,   # ~40% of India's crude via Hormuz
    "Suez Canal":            0.15,
    "Bab-el-Mandeb":         0.12,
    "Strait of Malacca":     0.05,
    "Cape of Good Hope":     0.02,
    "Turkish Straits":       0.01,
    "LOOP (Louisiana)":      0.00,
    "Bab el-Mandeb Strait":  0.12,   # alias
}

# GDP / inflation impact per day of zero-oil (World Bank / McKinsey estimates)
_GDP_LOSS_PER_DAY_PCT  = 0.035  # 0.035% GDP per day of supply zero-out
_INFL_RISE_PER_DAY_PCT = 0.07   # 0.07% inflation per day of oil scarcity

# Demand management levers (each reduces daily consumption by a fraction)
_DEMAND_LEVERS = [
    {"name": "Refinery Run-Rate Cut (15%)", "reduction_pct": 0.15, "cost": "Low"},
    {"name": "Industrial Priority Scheme",  "reduction_pct": 0.08, "cost": "Low"},
    {"name": "Transport Fuel Rationing",    "reduction_pct": 0.10, "cost": "Medium"},
    {"name": "Strategic Import Acceleration","reduction_pct": 0.00, "cost": "Medium"},
]


# ---------------------------------------------------------------------------
# Core Calculation
# ---------------------------------------------------------------------------

def calculate_spr_impact(
    lead_time_days: float,
    blocked_chokepoint: str,
    disrupted_volume_mbpd: float | None = None,
    gdp_impact_rate: float = 0.035,
    run_rate_cut: float = 0.15,
    industrial_cut: float = 0.08,
    transport_cut: float = 0.10,
) -> dict[str, Any]:
    """
    Simulate India's SPR burn-down during a supply disruption.

    Args:
        lead_time_days:       Days until rerouted tanker arrives (from Fixer Agent).
        blocked_chokepoint:   Which chokepoint is blocked (maps to import share).
        disrupted_volume_mbpd: Daily volume lost in mbpd. If None, calculated from
                               chokepoint import share × India daily consumption.

    Returns:
        Dict containing survival_days, supply_gap_days, burndown_df,
        recommendation, macro figures, and demand management actions.
    """
    # ── Step 1: Compute daily shortfall ─────────────────────────────────────
    if disrupted_volume_mbpd is None:
        share = _CHOKEPOINT_IMPORT_SHARE.get(blocked_chokepoint, 0.10)
        disrupted_volume_mbpd = INDIA_CONSUMPTION_MBPD * share

    daily_shortfall = disrupted_volume_mbpd

    logger.info(
        "spr_agent: chokepoint='%s'  daily_shortfall=%.2f mbpd  lead_time=%.1f days",
        blocked_chokepoint, daily_shortfall, lead_time_days,
    )

    # ── Step 2: SPR survival days ────────────────────────────────────────────
    if daily_shortfall > 0:
        actual_spr_survival_days = SPR_CAPACITY_MB / daily_shortfall
    else:
        actual_spr_survival_days = 999.0  # No shortfall

    supply_gap_days = max(0.0, lead_time_days - actual_spr_survival_days)

    # ── Step 3: Demand Management — can we close the gap? ───────────────────
    demand_actions: list[dict] = []
    adjusted_shortfall = daily_shortfall

    cumulative_reduction = 0.0
    demand_levers = [
        {"name": f"Refinery Run-Rate Cut ({int(run_rate_cut * 100)}%)", "reduction_pct": run_rate_cut, "cost": "Low"},
        {"name": f"Industrial Priority Scheme ({int(industrial_cut * 100)}%)",  "reduction_pct": industrial_cut, "cost": "Low"},
        {"name": f"Transport Fuel Rationing ({int(transport_cut * 100)}%)",    "reduction_pct": transport_cut, "cost": "Medium"},
        {"name": "Strategic Import Acceleration","reduction_pct": 0.00, "cost": "Medium"},
    ]
    for lever in demand_levers:
        if lever["reduction_pct"] > 0:
            reduced_mbpd = INDIA_CONSUMPTION_MBPD * lever["reduction_pct"]
            cumulative_reduction += reduced_mbpd
            demand_actions.append({
                "action":      lever["name"],
                "reduction":   f"{lever['reduction_pct']:.0%} of daily demand",
                "saves_mbpd":  round(reduced_mbpd, 2),
                "cost":        lever["cost"],
            })
        else:
            demand_actions.append({
                "action":      lever["name"],
                "reduction":   "Logistics speed-up",
                "saves_mbpd":  0.0,
                "cost":        lever["cost"],
            })

    adjusted_shortfall = max(0.0, daily_shortfall - cumulative_reduction)
    if adjusted_shortfall > 0 and adjusted_shortfall < daily_shortfall:
        adjusted_survival = SPR_CAPACITY_MB / adjusted_shortfall
        adjusted_gap = max(0.0, lead_time_days - adjusted_survival)
    elif adjusted_shortfall == 0:
        adjusted_survival = 999.0
        adjusted_gap = 0.0
    else:
        adjusted_survival = actual_spr_survival_days
        adjusted_gap = max(0.0, lead_time_days - adjusted_survival)

    # ── Step 4: Burn-Down Time-Series ────────────────────────────────────────
    horizon = int(lead_time_days) + 5
    burn_down_data = []
    current_spr     = SPR_CAPACITY_MB
    current_spr_adj = SPR_CAPACITY_MB

    for day in range(horizon):
        # Baseline burn (no demand management)
        if day < lead_time_days:
            current_spr = max(0.0, current_spr - daily_shortfall)
            status_base = "Critical" if current_spr == 0.0 else "Depleting"
        else:
            current_spr = min(SPR_CAPACITY_MB, current_spr + daily_shortfall * 0.5)
            status_base = "Replenishing"

        # Adjusted burn (with demand management levers applied)
        if day < lead_time_days:
            current_spr_adj = max(0.0, current_spr_adj - adjusted_shortfall)
            status_adj = "Managed" if current_spr_adj > 0.0 else "Critical"
        else:
            current_spr_adj = min(SPR_CAPACITY_MB, current_spr_adj + adjusted_shortfall * 0.5)
            status_adj = "Replenishing"

        burn_down_data.append({
            "Day":                      day,
            "SPR Level (MB)":          round(current_spr, 2),
            "SPR Managed (MB)":        round(current_spr_adj, 2),
            "SPR Capacity (MB)":       SPR_CAPACITY_MB,
            "Safe Floor (MB)":         SPR_CAPACITY_MB * 0.10,  # 10% emergency buffer
            "Status":                  status_base,
            "Ships Arrive":            day == int(lead_time_days),
        })

    df_burndown = pd.DataFrame(burn_down_data)

    # ── Step 5: Macro-Economic Impact ────────────────────────────────────────
    gap_days = supply_gap_days
    gdp_hit  = round(gap_days * gdp_impact_rate, 3)
    infl_hit = round(gap_days * _INFL_RISE_PER_DAY_PCT, 3)
    gdp_hit_adj  = round(adjusted_gap * gdp_impact_rate, 3)
    infl_hit_adj = round(adjusted_gap * _INFL_RISE_PER_DAY_PCT, 3)

    # Estimate GDP value of the gap (India GDP ≈ $3.7T, 1% ≈ $37B)
    gdp_usd_loss = round(gdp_hit * 37_000, 0)   # in million USD

    # ── Step 6: Summary ──────────────────────────────────────────────────────
    if supply_gap_days <= 0:
        recommendation = "✅ SPR Sufficient — No intervention required."
        status_color   = "green"
    elif adjusted_gap <= 0:
        recommendation = "⚠️ Demand Management Required — Levers can close the gap."
        status_color   = "orange"
    else:
        recommendation = "🚨 CRITICAL — Gap remains even with full demand management. Emergency imports required."
        status_color   = "red"

    return {
        "blocked_chokepoint":       blocked_chokepoint,
        "daily_shortfall_mbpd":     round(daily_shortfall, 2),
        "lead_time_days":           lead_time_days,
        "spr_capacity_mb":          SPR_CAPACITY_MB,
        "spr_sites":                SPR_SITES,
        "survival_days":            round(actual_spr_survival_days, 1),
        "supply_gap_days":          round(supply_gap_days, 1),
        "adjusted_gap_days":        round(adjusted_gap, 1),
        "adjusted_survival_days":   round(adjusted_survival, 1),
        "burndown_df":              df_burndown,
        "demand_actions":           demand_actions,
        "recommendation":           recommendation,
        "status_color":             status_color,
        "macro_gdp_impact_pct":     f"-{gdp_hit:.3f}%" if gdp_hit > 0 else "0.000%",
        "macro_gdp_impact_usd":     f"~${gdp_usd_loss:,.0f}M loss" if gdp_usd_loss > 0 else "$0 loss",
        "macro_infl_impact":        f"+{infl_hit:.3f}%" if infl_hit > 0 else "0.000%",
        "macro_gdp_adj":            f"-{gdp_hit_adj:.3f}%" if adjusted_gap > 0 else "Negligible",
        "macro_infl_adj":           f"+{infl_hit_adj:.3f}%" if adjusted_gap > 0 else "Negligible",
        "india_consumption_mbpd":   INDIA_CONSUMPTION_MBPD,
    }
