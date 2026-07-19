import pytest
from datetime import datetime, timezone
from unittest.mock import patch


def test_producer_matrix_uses_worst_active_direct_event_not_average():
    from src.agents.modeler_agent import compute_producer_country_risk_matrix

    source_time = datetime.now(timezone.utc)
    events = [
        {
            'affected_producer_countries': ['WeightedCountry'],
            'severity': 0.4,
            'confidence': 1.0,
            'source_fetched_at': source_time,
            'affected_chokepoints': [],
        },
        {
            'affected_producer_countries': ['WeightedCountry'],
            'severity': 0.8,
            'confidence': 1.0,
            'source_fetched_at': source_time,
            'affected_chokepoints': [],
        },
    ]

    with (
        patch('src.agents.modeler_agent.fetch_risk_events', return_value=events),
        patch(
            'src.agents.modeler_agent._known_producer_countries',
            return_value={'WeightedCountry'},
        ),
    ):
        matrix = compute_producer_country_risk_matrix()

    scores = {row['name']: row['risk_score'] for row in matrix}
    assert scores['WeightedCountry'] == pytest.approx(0.8, abs=0.002)
    assert scores['WeightedCountry'] < 0.95
