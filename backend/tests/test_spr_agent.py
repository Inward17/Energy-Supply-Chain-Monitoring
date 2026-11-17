import pytest
import pandas as pd
from src.agents.spr_agent import calculate_spr_impact, SPR_CAPACITY_MB, INDIA_CONSUMPTION_MBPD

def test_calculate_spr_impact_no_gap():
    # If lead time is very short, survival gap is 0
    result = calculate_spr_impact(
        lead_time_days=2.0,
        blocked_chokepoint="Strait of Hormuz"
    )
    assert result["supply_gap_days"] == 0.0
    assert result["adjusted_gap_days"] == 0.0
    assert result["status_color"] == "green"
    
    df = result["burndown_df"]
    assert isinstance(df, pd.DataFrame)
    assert len(df) > 2

def test_calculate_spr_impact_with_gap():
    # Force a long lead time to create a gap
    result = calculate_spr_impact(
        lead_time_days=60.0,
        blocked_chokepoint="Strait of Hormuz"
    )
    # India consumes 5.4 mbpd, Hormuz is 40% -> 2.16 mbpd shortfall
    # SPR is 39 MB. 39 / 2.16 = 18.05 days survival
    # Gap = 60 - 18.05 = 41.95
    assert result["supply_gap_days"] > 40.0
    
    # Check that demand actions were populated
    assert len(result["demand_actions"]) == 4

def test_calculate_spr_impact_custom_shortfall():
    result = calculate_spr_impact(
        lead_time_days=30.0,
        blocked_chokepoint="Custom",
        disrupted_volume_mbpd=1.0  # Exactly 1 mbpd
    )
    # capacity MB / 1 mbpd = capacity days of survival
    assert result["survival_days"] == SPR_CAPACITY_MB
    assert result["supply_gap_days"] == 0.0


def test_no_shortfall_marks_survival_sentinel_as_unlimited():
    result = calculate_spr_impact(
        lead_time_days=30.0,
        blocked_chokepoint="Custom",
        disrupted_volume_mbpd=0.0,
    )

    assert result["survival_days"] == 999.0
    assert result["survival_days_is_unlimited"] is True


def test_site_capacities_sum_to_declared_total():
    from src.agents.spr_agent import SPR_SITES
    assert abs(sum(SPR_SITES.values()) - SPR_CAPACITY_MB) < 0.1
    assert 38.5 < SPR_CAPACITY_MB < 39.5  # ISPRL Phase I: 5.33 MMT ≈ 39 MB


def test_levers_ramp_in_rather_than_apply_instantly():
    result = calculate_spr_impact(lead_time_days=60.0, blocked_chokepoint="Strait of Hormuz")
    instant_steady_state = SPR_CAPACITY_MB / (
        result["daily_shortfall_mbpd"] - sum(a["saves_mbpd"] for a in result["demand_actions"])
    )
    assert result["adjusted_survival_days"] < instant_steady_state
    assert result["survival_days"] < result["pessimistic_survival_days"] < result["adjusted_survival_days"]
    assert all("ramp_days" in a for a in result["demand_actions"])
    assert any("ramp" in line for line in result["assumptions"])


def test_levers_off_match_no_action():
    result = calculate_spr_impact(
        lead_time_days=60.0, blocked_chokepoint="Strait of Hormuz",
        run_rate_cut=0.0, industrial_cut=0.0, transport_cut=0.0,
    )
    assert result["adjusted_survival_days"] == result["survival_days"]
    assert result["pessimistic_survival_days"] == result["survival_days"]
