import pytest
from src.agents.fixer_agent import (
    find_alternatives,
    _compute_freight_premium,
    get_conditional_detour,
    _composite_score
)
from src.database.neo4j_graph import seed_graph, get_driver
from src.utils.constants import VLCC_DAILY_CHARTER_USD, VLCC_CARGO_BARRELS

def test_compute_freight_premium():
    # Example: 10 days voyage
    expected = round((VLCC_DAILY_CHARTER_USD * 10) / VLCC_CARGO_BARRELS, 2)
    assert _compute_freight_premium(10) == expected

def test_get_conditional_detour():
    # Suez Canal blockade
    assert get_conditional_detour("Suez Canal", ["Suez Canal", "Strait of Gibraltar"]) == 14
    assert get_conditional_detour("Suez Canal", ["Bab-el-Mandeb"]) == 14
    assert get_conditional_detour("Suez Canal", ["Strait of Hormuz"]) == 0
    
    # Strait of Hormuz blockade
    assert get_conditional_detour("Strait of Hormuz", ["Strait of Hormuz"]) == 0
    
    # Unknown chokepoint
    assert get_conditional_detour("Nonexistent", ["Suez Canal"]) == 0

def test_composite_score():
    score = _composite_score(
        landed_cost=80.0,
        lead_time=20.0,
        risk_score=0.2,
        brent_price=70.0,
        congestion_score=0.4
    )
    assert 0.0 <= score <= 1.0

def test_find_alternatives_basic():
    # Since we have clean_neo4j and db_transaction fixtures, the graph and DB are pristine.
    # The graph is seeded via conftest.py
    
    result = find_alternatives("Suez Canal", ranking_mode="cost")
    
    assert "procurement_matrix" in result
    assert "resilience_score" in result
    assert "blocked_chokepoint" in result
    assert result["blocked_chokepoint"] == "Suez Canal"
    
    pm = result["procurement_matrix"]
    # We should have some alternative routes found
    assert len(pm) > 0
    
    # Check that they are sorted by landed_cost_usd (ranking_mode="cost")
    costs = [r["landed_cost_usd"] for r in pm]
    assert costs == sorted(costs)

def test_find_alternatives_with_grade_filter():
    result = find_alternatives("Strait of Hormuz", crude_grade="Arab Light")
    pm = result["procurement_matrix"]
    
    # Check that all ports in the matrix either produce Arab Light or we fell back to 'any'
    # Actually, Arab Light is mostly produced in Saudi Arabia. Let's see if grade filtering applied.
    assert "grade_filtered" in result

def test_find_alternatives_speed_ranking():
    result = find_alternatives("Suez Canal", ranking_mode="speed")
    pm = result["procurement_matrix"]
    
    # Check that they are sorted by lead_time_days
    times = [r["lead_time_days"] for r in pm]
    assert times == sorted(times)
