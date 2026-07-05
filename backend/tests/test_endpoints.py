import pytest
from fastapi.testclient import TestClient
from api import app

# Import our TestClient
client = TestClient(app)

ENDPOINTS = [
    ("GET", "/api/metrics/live", None),
    ("GET", "/api/risk/events", None),
    ("GET", "/api/risk/chokepoints", None),
    ("GET", "/api/risk/sdi-timeline", None),
    ("GET", "/api/market/prices", None),
    ("GET", "/api/market/vessels", None),
    ("GET", "/api/config/chokepoints", None),
    ("GET", "/api/config/refineries", None),
    ("GET", "/api/config/grades", None),
    # Skipping backtest endpoint in smoke test since it requires specific event name that might not exist in pristine DB
    ("POST", "/api/orchestrator/reroute", {"blocked_chokepoint": "Strait of Hormuz"}),
    ("POST", "/api/orchestrator/spr", {"blocked_chokepoint": "Strait of Hormuz", "lead_time_days": 14}),
    ("POST", "/api/orchestrator/war-room", {"scenario_name": "Test", "blocked_chokepoint": "Strait of Hormuz", "disrupted_volume_mbpd": 2.5})
]

@pytest.mark.parametrize("method, path, body", ENDPOINTS)
def test_api_endpoint(method, path, body):
    if method == "GET":
        response = client.get(path)
    elif method == "POST":
        response = client.post(path, json=body)
    
    # Assert successful status code
    assert response.status_code == 200, f"Endpoint {path} failed with {response.status_code}: {response.text}"
    
    # Assert response is valid JSON
    data = response.json()
    assert data is not None

