"""One-off sensitivity check for historical SDI alert thresholds.

Run from ``backend`` before a demo or after changing the SDI formula:
    .\\venv\\Scripts\\python.exe tests/verify_backtest_robustness.py
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from api import get_backtest


THRESHOLDS = (50, 55, 60, 65, 70, 75, 80)
EVENTS = ("red_sea_attacks", "israel_iran_war_2025")


def main() -> None:
    for event_name in EVENTS:
        print(f"\n{event_name}")
        print("threshold | alert date | lead time (days)")
        print("----------|------------|-----------------")
        for threshold in THRESHOLDS:
            result = get_backtest(event_name, sdi_threshold=float(threshold))
            print(
                f"{threshold:>9} | "
                f"{result['system_alert_date'] or '-':<10} | "
                f"{result['lead_time_days']:>16}"
            )


if __name__ == "__main__":
    main()
