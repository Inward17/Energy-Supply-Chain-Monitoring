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

# Source: PPAC Industry Consumption Report, September 2024 (FY 2024-25).
# Rounded model input, expressed as crude-equivalent million barrels/day.
INDIA_CONSUMPTION_MBPD   = 5.4
# Source: MoPNG/ISPRL capacity statement, 20 March 2025 (Phase I, 5.33 MMT).
# Site figures are the single source of truth; the total is derived from them.
BBL_PER_TONNE = 7.33
SPR_SITES_MMT = {
    "Visakhapatnam": 1.33,
    "Mangaluru":     1.50,
    "Padur":         2.50,
}
SPR_SITES = {site: round(mmt * BBL_PER_TONNE, 2) for site, mmt in SPR_SITES_MMT.items()}
SPR_CAPACITY_MB = round(sum(SPR_SITES.values()), 1)  # ≈ 39.1 MB

# Days for each demand lever to reach full effect (linear ramp). Rationing
# needs notification and enforcement; refiners can cut runs within days.
LEVER_RAMP_DAYS = {"run_rate": 3, "industrial": 7, "transport": 14}
# After replacement cargoes arrive, the reserve refills at this share of the
# disrupted daily volume. A modelling assumption, not a cargo schedule.
DEFAULT_REPLENISH_SHARE = 0.5
# Pessimistic case: levers deliver only this share of their target.
PESSIMISTIC_LEVER_EFFECTIVENESS = 0.5

# Chokepoint → fraction of India's imports that transit it (2024 data)
_CHOKEPOINT_IMPORT_SHARE: dict[str, float] = {
    "Strait of Hormuz":      0.40,   # ~40% of India's crude via Hormuz
    "Suez Canal":            0.15,
    "Bab-el-Mandeb":         0.12,
    "Strait of Malacca":     0.05,
    "Cape of Good Hope":     0.02,
    "Turkish Straits":       0.01,
    "LOOP (Louisiana)":      0.00,
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

Lever = tuple[float, int]  # (full-effect saving in mbpd, ramp days)


def _managed_draw(day: int, shortfall: float, levers: list[Lever], effectiveness: float = 1.0) -> float:
    """Reserve draw on `day` with each lever ramping linearly to full effect."""
    saved = sum(mbpd * min(1.0, (day + 1) / ramp) for mbpd, ramp in levers)
    return max(0.0, shortfall - effectiveness * saved)


def _days_until_empty(
    shortfall: float, levers: list[Lever], effectiveness: float = 1.0, cap_days: int = 3650
) -> float | None:
    """Fractional day the reserve runs dry, or None if the levers close the gap first.

    Savings only grow with time, so once the draw reaches zero it stays there.
    """
    level = SPR_CAPACITY_MB
    for day in range(cap_days):
        draw = _managed_draw(day, shortfall, levers, effectiveness)
        if draw <= 0:
            return None
        if level <= draw:
            return day + level / draw
        level -= draw
    return None


def calculate_spr_impact(
    lead_time_days: float,
    blocked_chokepoint: str,
    disrupted_volume_mbpd: float | None = None,
    gdp_impact_rate: float = 0.035,
    run_rate_cut: float = 0.15,
    industrial_cut: float = 0.08,
    transport_cut: float = 0.10,
    replenish_share: float = DEFAULT_REPLENISH_SHARE,
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
    survival_days_is_unlimited = daily_shortfall <= 0
    if daily_shortfall > 0:
        actual_spr_survival_days = SPR_CAPACITY_MB / daily_shortfall
    else:
        # Retain a JSON-safe finite value for existing clients. The explicit
        # flag prevents any future cross-scenario aggregation from treating
        # this sentinel as an observed number of survival days.
        actual_spr_survival_days = 999.0

    supply_gap_days = max(0.0, lead_time_days - actual_spr_survival_days)

    # ── Step 3: Demand Management — can we close the gap? ───────────────────
    demand_actions: list[dict] = []
    demand_levers = [
        {"name": f"Refinery Run-Rate Cut ({int(run_rate_cut * 100)}%)", "reduction_pct": run_rate_cut, "cost": "Low"},
        {"name": f"Industrial Priority Scheme ({int(industrial_cut * 100)}%)",  "reduction_pct": industrial_cut, "cost": "Low"},
        {"name": f"Transport Fuel Rationing ({int(transport_cut * 100)}%)",    "reduction_pct": transport_cut, "cost": "Medium"},
        {"name": "Strategic Import Acceleration","reduction_pct": 0.00, "cost": "Medium"},
    ]
    ramps = [LEVER_RAMP_DAYS["run_rate"], LEVER_RAMP_DAYS["industrial"], LEVER_RAMP_DAYS["transport"], 0]
    levers: list[Lever] = []
    for lever, ramp in zip(demand_levers, ramps):
        if lever["reduction_pct"] > 0:
            reduced_mbpd = INDIA_CONSUMPTION_MBPD * lever["reduction_pct"]
            levers.append((reduced_mbpd, ramp))
            demand_actions.append({
                "action":      lever["name"],
                "reduction":   f"{lever['reduction_pct']:.0%} of daily demand",
                "saves_mbpd":  round(reduced_mbpd, 2),
                "ramp_days":   ramp,
                "cost":        lever["cost"],
            })
        else:
            demand_actions.append({
                "action":      lever["name"],
                "reduction":   "Logistics speed-up",
                "saves_mbpd":  0.0,
                "ramp_days":   0,
                "cost":        lever["cost"],
            })


    # Survival with levers ramping in, not switched on at day 0.
    if daily_shortfall <= 0:
        adjusted_survival = 999.0
    else:
        empty_at = _days_until_empty(daily_shortfall, levers)
        adjusted_survival = 999.0 if empty_at is None else empty_at
    adjusted_gap = max(0.0, lead_time_days - adjusted_survival)

    if daily_shortfall <= 0:
        pessimistic_survival = 999.0
    else:
        empty_at = _days_until_empty(daily_shortfall, levers, PESSIMISTIC_LEVER_EFFECTIVENESS)
        pessimistic_survival = 999.0 if empty_at is None else empty_at
    pessimistic_gap = max(0.0, lead_time_days - pessimistic_survival)

    # ── Step 4: Burn-Down Time-Series ────────────────────────────────────────
    horizon = int(lead_time_days) + 5
    burn_down_data = []
    current_spr     = SPR_CAPACITY_MB
    current_spr_adj = SPR_CAPACITY_MB

    refill = daily_shortfall * replenish_share
    arrival_day = int(lead_time_days)  # the day in which cargoes land
    for day in range(horizon):
        # Share of this day before arrival: 1 before, 0 after, fractional on
        # the arrival day itself (lead 2.5 → day 2 is half drawn, half refilled).
        before = min(1.0, max(0.0, lead_time_days - day))

        current_spr = max(0.0, current_spr - daily_shortfall * before)
        current_spr = min(SPR_CAPACITY_MB, current_spr + refill * (1 - before))
        if before > 0:
            status_base = "Critical" if current_spr == 0.0 else "Depleting"
        else:
            status_base = "Replenishing"

        draw = _managed_draw(day, daily_shortfall, levers)
        current_spr_adj = max(0.0, current_spr_adj - draw * before)
        current_spr_adj = min(SPR_CAPACITY_MB, current_spr_adj + refill * (1 - before))

        burn_down_data.append({
            "Day":                      day,
            "SPR Level (MB)":          round(current_spr, 2),
            "SPR Managed (MB)":        round(current_spr_adj, 2),
            "SPR Capacity (MB)":       SPR_CAPACITY_MB,
            "Safe Floor (MB)":         SPR_CAPACITY_MB * 0.10,  # 10% emergency buffer
            "Status":                  status_base,
            "Ships Arrive":            day == arrival_day,
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
    elif adjusted_gap <= 0 and pessimistic_gap <= 0:
        recommendation = "⚠️ Demand Management Required — Levers can close the gap."
        status_color   = "orange"
    elif adjusted_gap <= 0:
        recommendation = (
            "⚠️ Demand Management Required — Levers close the gap only near full effect; "
            f"at {PESSIMISTIC_LEVER_EFFECTIVENESS:.0%} delivery the reserve runs "
            f"{pessimistic_gap:.1f} days short."
        )
        status_color   = "orange"
    else:
        recommendation = "🚨 CRITICAL — Gap remains even with full demand management. Emergency imports required."
        status_color   = "red"

    ramp_text = ", ".join(
        f"{a['action'].split(' (')[0].lower()} {a['ramp_days']} d"
        for a in demand_actions if a["saves_mbpd"] > 0
    )
    assumptions = [
        f"Reserve starts full ({SPR_CAPACITY_MB} MB across 3 sites); real fill is usually lower, so survival days are an upper bound.",
        f"Levers ramp linearly to full effect: {ramp_text or 'none active'}.",
        "Lever savings are shares of total national demand and can overlap (a refinery run cut and fuel rationing may remove the same barrels).",
        f"Pessimistic case assumes levers deliver {PESSIMISTIC_LEVER_EFFECTIVENESS:.0%} of target.",
        "Replacement cargoes all arrive on the lead-time day; no partial deliveries before then.",
        f"After arrival the reserve refills at {replenish_share:.0%} of the disrupted daily volume (an assumption, not a cargo schedule).",
    ]

    return {
        "blocked_chokepoint":       blocked_chokepoint,
        "daily_shortfall_mbpd":     round(daily_shortfall, 2),
        "lead_time_days":           lead_time_days,
        "spr_capacity_mb":          SPR_CAPACITY_MB,
        "spr_sites":                SPR_SITES,
        "survival_days":            round(actual_spr_survival_days, 1),
        "survival_days_is_unlimited": survival_days_is_unlimited,
        "supply_gap_days":          round(supply_gap_days, 1),
        "adjusted_gap_days":        round(adjusted_gap, 1),
        "adjusted_survival_days":   round(adjusted_survival, 1),
        "pessimistic_survival_days": round(pessimistic_survival, 1),
        "pessimistic_gap_days":     round(pessimistic_gap, 1),
        "assumptions":              assumptions,
        "burndown_df":              df_burndown,
        "demand_actions":           demand_actions,
        "recommendation":           recommendation,
        "status_color":             status_color,
        "macro_gdp_impact_pct":     f"-{abs(gdp_hit):.3f}%" if gdp_hit > 0 else "0.000%",
        "macro_gdp_impact_usd":     f"~${gdp_usd_loss:,.0f}M loss" if gdp_usd_loss > 0 else "$0 loss",
        "macro_infl_impact":        f"+{abs(infl_hit):.3f}%" if infl_hit > 0 else "0.000%",
        "macro_gdp_adj":            f"-{abs(gdp_hit_adj):.3f}%" if adjusted_gap > 0 else "Negligible",
        "macro_infl_adj":           f"+{abs(infl_hit_adj):.3f}%" if adjusted_gap > 0 else "Negligible",
        "india_consumption_mbpd":   INDIA_CONSUMPTION_MBPD,
    }
