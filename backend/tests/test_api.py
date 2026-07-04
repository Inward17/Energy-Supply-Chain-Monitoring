import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__))))

from api import get_backtest

try:
    result = get_backtest("red_sea_attacks")
    print(f"Success! Length of series: {len(result['series'])}")
    if len(result['series']) > 0:
        print(f"First element: {result['series'][0]}")
except Exception as e:
    print(f"Error: {e}")
