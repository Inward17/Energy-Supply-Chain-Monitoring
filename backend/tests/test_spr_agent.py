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
    # 39 MB / 1 mbpd = 39 days survival
    # Gap = 30 - 39 = 0
    assert result["survival_days"] == 39.0
    assert result["supply_gap_days"] == 0.0
