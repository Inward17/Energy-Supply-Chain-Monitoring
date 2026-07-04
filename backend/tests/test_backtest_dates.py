import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__))))

from src.database.postgres_db import fetch_risk_events_backtest
events = fetch_risk_events_backtest("red_sea_attacks")
print(f"Fetched {len(events)} events")
if events:
    print(f"Type of created_at: {type(events[0]['created_at'])}")
    try:
        existing_dates = {ev["created_at"].date() for ev in events if "created_at" in ev}
        print(f"Successfully extracted {len(existing_dates)} dates: {list(existing_dates)[:3]}")
    except Exception as e:
        print(f"Error parsing dates: {e}")
