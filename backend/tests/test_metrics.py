import pytest
from src.utils.metrics import (
    supply_disruption_index,
    normalise_price_delta,
    normalise_freight_delta,
    flow_weighted_risk,
    compute_resilience_score,
)

def test_supply_disruption_index():
    # Known inputs -> known output
    # w1=0.4, w2=0.25, w3=0.15, w4=0.20
    # p_risk=0.5, d=0.5, p=0.5, f=0.5 -> expected raw = 0.5 * 1.0 = 0.50
    # expected SDI = 50.0
    assert supply_disruption_index(0.5, 0.5, 0.5, 0.5, w1=0.4, w2=0.25, w3=0.15, w4=0.20) == 50.0
    
    # Boundary cases
    assert supply_disruption_index(0.0, 0.0, 0.0, 0.0, w1=0.4, w2=0.25, w3=0.15, w4=0.20) == 0.0
    assert supply_disruption_index(1.0, 1.0, 1.0, 1.0, w1=0.4, w2=0.25, w3=0.15, w4=0.20) == 100.0

    # Invariant testing
    with pytest.raises(ValueError):
        supply_disruption_index(0.5, 0.5, 0.5, 0.5, w1=0.1, w2=0.1, w3=0.1, w4=0.1)

def test_normalise_price_delta():
    # z = (current - mean) / std
    # z = (80 - 70) / 10 = 1.0
    # clipped = 1.0. range is -3 to 3.
    # norm = (1.0 + 3.0) / 6.0 = 4.0 / 6.0 = 0.6667
    assert normalise_price_delta(80, 70, 10, clip_sigmas=3.0) == 0.6667
    
    # Zero std fallback
    assert normalise_price_delta(80, 70, 0) == 0.5

def test_normalise_freight_delta():
    # Similar logic to price delta
    # z = (45 - 50) / 5 = -1.0
    # norm = (-1.0 + 3.0) / 6.0 = 2.0 / 6.0 = 0.3333
    assert normalise_freight_delta(45, 50, 5, clip_sigmas=3.0) == 0.3333
    
    # Zero std fallback
    assert normalise_freight_delta(50, 50, 0) == 0.5

def test_flow_weighted_risk():
    flows = [10.0, 20.0]
    risks = [0.2, 0.8]
    # (10*0.2 + 20*0.8) / 30 = (2 + 16) / 30 = 18 / 30 = 0.6
    assert flow_weighted_risk(flows, risks) == 0.6
    
    # Boundary cases
    assert flow_weighted_risk([0.0, 0.0], [0.5, 0.5]) == 0.0
    
    with pytest.raises(ValueError):
        flow_weighted_risk([10.0], [0.5, 0.5])

def test_compute_resilience_score():
    # Base = 5 alts -> min(5/5, 1)*60 = 60
    # Detour = 15 days -> min(15/30, 1)*25 = 12.5
    # Cost = 10% -> min(10/50, 1)*15 = 3.0
    # Score = 60 - 12.5 - 3.0 = 44.5
    assert compute_resilience_score(5, 15, 10) == 44.5
    
    # 0 alternatives
    assert compute_resilience_score(0, 10, 10) == 0.0
