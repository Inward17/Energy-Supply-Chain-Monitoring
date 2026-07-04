"""
src/utils/constants.py
──────────────────────
Single source of truth for all domain constants shared across modules.

Importing from here prevents magic literals from scattering across files
and ensures any value change is made in exactly one place.
"""

from __future__ import annotations

import os

# ---------------------------------------------------------------------------
# Canonical Chokepoint Registry
# ---------------------------------------------------------------------------

CHOKEPOINTS: list[str] = [
    "Strait of Hormuz",
    "Suez Canal",
    "Bab-el-Mandeb",
    "Strait of Malacca",
    "Turkish Straits",
    "Cape of Good Hope",
    "Strait of Gibraltar",
    "Panama Canal",
]

#: Frozenset for O(1) membership tests (used in sentinel_agent validation)
CHOKEPOINTS_SET: frozenset[str] = frozenset(CHOKEPOINTS)

# ---------------------------------------------------------------------------
# Fixer Agent — Procurement Orchestrator
# ---------------------------------------------------------------------------

#: Fallback Brent crude price (USD/bbl) used when the local DB has no data
FIXER_BRENT_FALLBACK_USD: float = 75.0

#: Fallback one-way distance (nautical miles) when a port has no coordinates
FIXER_FALLBACK_DISTANCE_NM: int = 8_000

#: Worst-case lead time (days) used as the normalisation ceiling in the
#: composite score formula  (time_score = 1 - lead_time / ceiling)
FIXER_WORST_CASE_LEAD_DAYS: int = 45

# ---------------------------------------------------------------------------
# Sentinel Agent — Geopolitical Risk Scoring
# ---------------------------------------------------------------------------

#: Gemini model used for news analysis; overridable via GEMINI_MODEL env var
SENTINEL_GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

#: Approximate vessel density divergence assigned when a high-severity event
#: is detected but no live AIS baseline is available
SENTINEL_DELTA_D_HIGH: float = 0.3

#: Same approximation for low-severity events
SENTINEL_DELTA_D_LOW: float = 0.1

#: Severity threshold above which the high delta-D approximation is used
SENTINEL_SEVERITY_THRESHOLD: float = 0.5

# ---------------------------------------------------------------------------
# Modeler Agent — SDI Computation
# ---------------------------------------------------------------------------

#: Baseline geopolitical risk applied to chokepoints with no active events
MODELER_BASELINE_RISK: float = 0.05

# ---------------------------------------------------------------------------
# Market Trawler — yfinance
# ---------------------------------------------------------------------------

#: Default historical look-back window for OHLCV download
MARKET_HISTORY_PERIOD: str = "60d"

#: Look-back window for Brent rolling statistics (mean / std)
BRENT_STATS_PERIOD: str = "35d"
# ---------------------------------------------------------------------------
# Fixer Agent: VLCC Economic Parameters
# ---------------------------------------------------------------------------
VLCC_DAILY_CHARTER_USD = 65_000
VLCC_CARGO_BARRELS = 2_000_000
VLCC_SPEED_KNOTS = 13.0
