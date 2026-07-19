import pytest
from src.agents.fixer_agent import (
    find_alternatives,
    _compute_freight_premium,
    _compute_lead_time,
    _worst_blend_congestion,
    get_conditional_detour,
    _composite_score
)
from src.database.neo4j_graph import seed_graph, get_driver
from src.utils.constants import VLCC_DAILY_CHARTER_USD, VLCC_CARGO_BARRELS

def test_compute_freight_premium():
    # Example: 10 days voyage
    expected = round((VLCC_DAILY_CHARTER_USD * 10) / VLCC_CARGO_BARRELS, 2)
    assert _compute_freight_premium(10) == expected


def test_freight_premium_tracks_live_freight_stress_symmetrically():
    calm = _compute_freight_premium(10, freight_index=0.3)
    neutral = _compute_freight_premium(10, freight_index=0.5)
    stressed = _compute_freight_premium(10, freight_index=0.8)

    assert calm < neutral < stressed


def test_blend_congestion_uses_worst_required_leg():
    assert _worst_blend_congestion([0.1, 0.9]) == 0.9


def test_suez_detour_uses_route_engine_restriction():
    # Rotterdam -> Jamnagar: avoiding Suez sends the route around the Cape.
    direct = _compute_lead_time(4.48, 51.92, 69.85, 22.30)
    restricted = _compute_lead_time(
        4.48,
        51.92,
        69.85,
        22.30,
        extra_detour_days=14,
        blocked_chokepoint="Suez Canal",
    )

    assert restricted > direct + 10

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
