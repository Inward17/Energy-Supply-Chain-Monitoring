import urllib.request
import json
import urllib.error

BASE_URL = "http://localhost:8000"

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
    ("GET", "/api/backtest/red_sea_halt", None),
    ("POST", "/api/orchestrator/reroute", {"blocked_chokepoint": "Strait of Hormuz"}),
    ("POST", "/api/orchestrator/spr", {"blocked_chokepoint": "Strait of Hormuz", "lead_time_days": 14}),
    ("POST", "/api/orchestrator/war-room", {"scenario_name": "Test", "blocked_chokepoint": "Strait of Hormuz", "disrupted_volume_mbpd": 2.5})
]

print("Starting endpoint smoke tests...")
failures = 0
for method, path, body in ENDPOINTS:
    url = BASE_URL + path
    try:
        req = urllib.request.Request(url, method=method)
        if body:
            req.add_header('Content-Type', 'application/json')
            req.data = json.dumps(body).encode('utf-8')
        
        with urllib.request.urlopen(req) as response:
            status = response.status
            data = json.loads(response.read().decode('utf-8'))
            
            # Print success with shape
            if isinstance(data, list):
                shape = f"List[{len(data)}]"
            elif isinstance(data, dict):
                shape = f"Dict with keys: {list(data.keys())[:5]}"
            else:
                shape = type(data).__name__
                
            print(f"? {method} {path} -> {status} OK | Shape: {shape}")
    except urllib.error.HTTPError as e:
        print(f"? {method} {path} -> {e.code} Error | Msg: {e.read().decode('utf-8')}")
        failures += 1
    except Exception as e:
        print(f"? {method} {path} -> Failed to connect | Error: {e}")
        failures += 1

if failures == 0:
    print("\nAll endpoints passed!")
else:
    print(f"\n{failures} endpoints failed.")
