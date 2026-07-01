"""
src/utils/metrics.py
────────────────────
Pure mathematical functions for supply chain risk quantification.
No external calls — all inputs are scalars drawn from the local DB cache.

SDI Formula:
    SDI = w1·P_risk + w2·ΔD_vessel + w3·ΔP_price

All inputs should be pre-normalised to [0, 1] before passing here.
"""

from __future__ import annotations

import os
import math
from typing import Sequence


# ---------------------------------------------------------------------------
# Default weight coefficients (overridable via .env)
# ---------------------------------------------------------------------------
_W1 = float(os.getenv("SDI_W1", "0.50"))  # Gemini risk score weight
_W2 = float(os.getenv("SDI_W2", "0.30"))  # Vessel density divergence weight
_W3 = float(os.getenv("SDI_W3", "0.20"))  # Price delta weight


# ---------------------------------------------------------------------------
# Core SDI Calculation
# ---------------------------------------------------------------------------

def supply_disruption_index(
    p_risk: float,
    delta_d_vessel: float,
    delta_p_price: float,
    w1: float = _W1,
    w2: float = _W2,
    w3: float = _W3,
) -> float:
    """
    Compute the Composite Supply Disruption Index (SDI).

    SDI = w1·P_risk + w2·ΔD_vessel + w3·ΔP_price

    Args:
        p_risk:         Gemini Sentinel severity score, normalised to [0, 1].
        delta_d_vessel: AIS vessel density divergence, normalised to [0, 1].
                        >0 means fewer vessels than baseline (route avoidance).
        delta_p_price:  Brent crude price deviation from 30-day mean, [0, 1].
        w1, w2, w3:     Configurable weights; must sum to 1.0.

    Returns:
        SDI score in [0, 100] range (scaled for dashboard display).
    """
    raw = w1 * _clamp(p_risk) + w2 * _clamp(delta_d_vessel) + w3 * _clamp(delta_p_price)
    return round(raw * 100, 2)


def flow_weighted_risk(
    chokepoint_flows_mb: Sequence[float],
    risk_scores: Sequence[float],
) -> float:
    """
    Compute a flow-weighted aggregate risk across multiple chokepoints.

    Flow-weighted risk = Σ(flow_i · risk_i) / Σ(flow_i)

    Args:
        chokepoint_flows_mb:  Daily oil flow through each chokepoint (million barrels).
        risk_scores:          Corresponding risk scores (0–1) per chokepoint.

    Returns:
        Weighted risk score in [0, 1].
    """
    if len(chokepoint_flows_mb) != len(risk_scores):
        raise ValueError("flows and risk_scores must have the same length.")
    total_flow = sum(chokepoint_flows_mb)
    if total_flow == 0:
        return 0.0
    weighted_sum = sum(f * r for f, r in zip(chokepoint_flows_mb, risk_scores))
    return round(weighted_sum / total_flow, 4)


def normalise_price_delta(
    current_price: float,
    rolling_mean: float,
    rolling_std: float,
    clip_sigmas: float = 3.0,
) -> float:
    """
    Z-score normalise a price change and clip to [0, 1].

    Used to compute ΔP_price for the SDI formula.

    Args:
        current_price:  Latest Brent Crude close price (USD).
        rolling_mean:   30-day rolling mean close price (USD).
        rolling_std:    30-day rolling std deviation (USD). If 0, returns 0.
        clip_sigmas:    Number of standard deviations to clip at.

    Returns:
        Normalised value in [0, 1].
    """
    if rolling_std == 0:
        return 0.0
    z = (current_price - rolling_mean) / rolling_std
    clipped = max(-clip_sigmas, min(clip_sigmas, z))
    return round((clipped + clip_sigmas) / (2 * clip_sigmas), 4)


def normalise_vessel_density_delta(
    current_count: int,
    baseline_count: int,
) -> float:
    """
    Compute normalised vessel density divergence for a bounding box.

    A drop in vessel count signals route avoidance → higher risk.
    A positive value means FEWER ships than baseline.

    Args:
        current_count:   Current AIS vessel count in the region.
        baseline_count:  Rolling 7-day average vessel count in the region.

    Returns:
        Normalised divergence in [0, 1].
    """
    if baseline_count == 0:
        return 0.0
    # Positive when count drops below baseline
    delta_ratio = (baseline_count - current_count) / baseline_count
    return _clamp(delta_ratio)


def estimate_price_impact(
    disruption_probability: float,
    chokepoint_flow_mb_per_day: float,
    elasticity: float = 0.05,
) -> float:
    """
    Estimate Brent Crude price impact from a supply disruption.

    Impact (USD/bbl) ≈ disruption_prob × (flow / world_demand) × (1/elasticity)
    Approximated with world supply at ~100 mb/day.

    Args:
        disruption_probability:     Probability of full route closure (0–1).
        chokepoint_flow_mb_per_day: Volume at risk (million barrels/day).
        elasticity:                 Price elasticity of oil demand (default 0.05).

    Returns:
        Estimated price impact in USD per barrel.
    """
    world_supply_mb_day = 100.0
    supply_shock_fraction = (disruption_probability * chokepoint_flow_mb_per_day) / world_supply_mb_day
    price_impact = supply_shock_fraction / elasticity
    return round(price_impact, 2)


def compute_resilience_score(
    num_alternatives: int,
    avg_detour_days: float,
    avg_cost_premium_pct: float,
) -> float:
    """
    Compute a Resilience Index for a disrupted route.

    Higher score → more resilient supply chain options available.
    Score is penalised by detour length and cost premium.

    Args:
        num_alternatives:      Number of viable alternative routes.
        avg_detour_days:       Average additional transit days for alternatives.
        avg_cost_premium_pct:  Average cost increase as percentage (0–100).

    Returns:
        Resilience score in [0, 100].
    """
    if num_alternatives == 0:
        return 0.0

    # Base score from number of alternatives (saturates at 5)
    alt_score = min(num_alternatives / 5.0, 1.0) * 60.0

    # Penalty from detour duration (normalised at 30 days max)
    detour_penalty = min(avg_detour_days / 30.0, 1.0) * 25.0

    # Penalty from cost premium (normalised at 50% max)
    cost_penalty = min(avg_cost_premium_pct / 50.0, 1.0) * 15.0

    score = alt_score - detour_penalty - cost_penalty
    return round(max(0.0, score), 2)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    """Clamp a float to [lo, hi]."""
    return max(lo, min(hi, value))
