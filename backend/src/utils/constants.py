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

CHOKEPOINT_ALIASES: dict[str, str] = {
    "Hormuz": "Strait of Hormuz",
    "Hormuz Strait": "Strait of Hormuz",
    "Strait of Hormuz": "Strait of Hormuz",
    "Suez": "Suez Canal",
    "Suez Canal": "Suez Canal",
    "Bab el Mandeb": "Bab-el-Mandeb",
    "Bab el-Mandeb": "Bab-el-Mandeb",
    "Bab-el-Mandeb": "Bab-el-Mandeb",
    "Malacca": "Strait of Malacca",
    "Malacca Strait": "Strait of Malacca",
    "Strait of Malacca": "Strait of Malacca",
    "Bosporus": "Turkish Straits",
    "Dardanelles": "Turkish Straits",
    "Turkish Straits": "Turkish Straits",
    "Gibraltar": "Strait of Gibraltar",
    "Strait of Gibraltar": "Strait of Gibraltar",
    "Cape of Good Hope": "Cape of Good Hope",
    "COGH": "Cape of Good Hope",
    "Good Hope": "Cape of Good Hope",
    "Panama": "Panama Canal",
    "Panama Canal": "Panama Canal",
}

def canonical_chokepoint_name(name: str) -> str:
    """Resolve a chokepoint string to its canonical name if known."""
    return CHOKEPOINT_ALIASES.get(name.strip(), name.strip())

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

#: Weights for the Fixer Agent's composite score formula (sum to 1.0)
FIXER_WEIGHT_COST: float = 0.35
FIXER_WEIGHT_TIME: float = 0.25
FIXER_WEIGHT_RISK: float = 0.25
FIXER_WEIGHT_CONGESTION: float = 0.15

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
# AIS Ship Type Filtering
# ---------------------------------------------------------------------------

#: Standard AIS ship types for tankers (hazardous category D and tankers)
TANKER_SHIP_TYPES: frozenset[int] = frozenset(range(80, 90))

# ---------------------------------------------------------------------------
# Modeler Agent — SDI Computation
# ---------------------------------------------------------------------------

#: Baseline geopolitical risk applied to chokepoints with no active events
MODELER_BASELINE_RISK: float = 0.05

#: Severity bands for the composite SDI, as (lower_bound, label).
#: The dashboard previously coloured the headline on a bare `score > 60`, so a
#: 55 reading — geopolitical risk already near its ceiling — rendered green and
#: read as "stable". Bands are graduated so the headline degrades visibly well
#: before the index saturates.
SDI_BANDS: list[tuple[float, str]] = [
    (80.0, "CRITICAL"),
    (65.0, "SEVERE"),
    (50.0, "ELEVATED"),
    (30.0, "MODERATE"),
    (0.0, "LOW"),
]


def sdi_band(score: float) -> str:
    """Return the severity label for a composite SDI score."""
    for lower, label in SDI_BANDS:
        if score >= lower:
            return label
    return "LOW"

#: An incident must exceed this decayed risk before its chokepoint flow is
#: included in the aggregate price-impact estimate.
ELEVATED_RISK_THRESHOLD: float = float(
    os.getenv("ELEVATED_RISK_THRESHOLD", "0.50")
)

#: A wider cap preserves discrimination between severe and extreme market
#: moves while retaining the established linear normalisation shape.
MARKET_Z_CLIP_SIGMAS: float = float(os.getenv("MARKET_Z_CLIP_SIGMAS", "4.5"))

#: Event persistence is driven by the disruption mechanism, not merely news
#: recency. Values are env-overridable to support calibration after backtests.
RISK_EVENT_HALF_LIFE_DAYS_BY_TYPE: dict[str, float] = {
    "military_conflict": float(os.getenv("RISK_HALF_LIFE_MILITARY_CONFLICT_DAYS", "10")),
    "sanctions": float(os.getenv("RISK_HALF_LIFE_SANCTIONS_DAYS", "45")),
    "producer_supply_shock": float(os.getenv("RISK_HALF_LIFE_PRODUCER_SUPPLY_SHOCK_DAYS", "30")),
    "embargo": float(os.getenv("RISK_HALF_LIFE_EMBARGO_DAYS", "45")),
    "weather": float(os.getenv("RISK_HALF_LIFE_WEATHER_DAYS", "14")),
    "accident": float(os.getenv("RISK_HALF_LIFE_ACCIDENT_DAYS", "7")),
    "piracy": float(os.getenv("RISK_HALF_LIFE_PIRACY_DAYS", "10")),
    "protest": float(os.getenv("RISK_HALF_LIFE_PROTEST_DAYS", "14")),
    "unknown": float(os.getenv("RISK_HALF_LIFE_UNKNOWN_DAYS", "14")),
    "default": float(os.getenv("RISK_EVENT_HALF_LIFE_DAYS", "14")),
}

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

#: Strength of the live freight-index adjustment around its neutral 0.50
#: value. The adjustment is symmetric so calm freight conditions lower the
#: effective rate by the same amount that stressed conditions increase it.
FREIGHT_RATE_SENSITIVITY: float = float(
    os.getenv("FREIGHT_RATE_SENSITIVITY", "0.50")
)

# ---------------------------------------------------------------------------
# Compliance / Sanctions Screening
# ---------------------------------------------------------------------------

#: Countries whose export terminals are currently subject to major sanctions
#: regimes (US OFAC / EU / UN). Maintained as a static list; update when
#: sanctions landscape changes. Used by fixer_agent when exclude_sanctioned=True.
SANCTIONED_SOURCE_COUNTRIES: frozenset[str] = frozenset({
    "Russia",
    "Iran",
    "Venezuela",
    "North Korea",
    "Syria",
    "Libya",   # certain factions — include conservatively
})

# ---------------------------------------------------------------------------
# GDELT Producer-Nation Query Configuration
# ---------------------------------------------------------------------------

#: Max articles to fetch from Query B (producer-nation signals).
#: Capped at 50 (vs 100 for Query A) to prevent doubling the Gemini RPM budget.
GDELT_PRODUCER_MAXRECORDS: int = int(os.getenv("GDELT_PRODUCER_MAXRECORDS", "50"))

#: Slot allocation for the merged 10-article output (must sum to 10).
#: Env-tunable so the ratio can be adjusted once real relative volumes are known.
GDELT_SLOTS_MARITIME: int = int(os.getenv("GDELT_SLOTS_MARITIME", "6"))
GDELT_SLOTS_PRODUCER: int = int(os.getenv("GDELT_SLOTS_PRODUCER", "4"))

# ---------------------------------------------------------------------------
# Producer-Nation Registry
# ---------------------------------------------------------------------------

#: Canonical set of oil-producing nations for query building and validation.
#: Source: IEA top-30 oil producers + OPEC members (2024 data).
PRODUCER_NATIONS: frozenset[str] = frozenset({
    "Russia", "Saudi Arabia", "United States", "USA", "Canada", "Iraq", "UAE",
    "United Arab Emirates",
    "Iran", "Kuwait", "Venezuela", "Nigeria", "Norway", "Kazakhstan",
    "Libya", "Algeria", "Angola", "Brazil", "Mexico", "Azerbaijan",
    "Oman", "Malaysia", "Qatar", "Ecuador", "Gabon", "Indonesia",
})

#: Canonical display names used when joining Gemini output, Neo4j countries,
#: and static transit mappings. The graph historically used USA/UAE while
#: news models often return the long forms; treating them as separate rows
#: produced duplicate producer scores.
COUNTRY_ALIASES: dict[str, str] = {
    "US": "United States",
    "U.S.": "United States",
    "U.S.A.": "United States",
    "USA": "United States",
    "United States of America": "United States",
    "UAE": "United Arab Emirates",
    "U.A.E.": "United Arab Emirates",
    "Emirates": "United Arab Emirates",
    # An unmapped long form is silently dropped by the producer validator, so a
    # "Russian Federation" attribution scored zero against Russia.
    "Russian Federation": "Russia",
    "Russian Fed.": "Russia",
    "Kingdom of Saudi Arabia": "Saudi Arabia",
    "KSA": "Saudi Arabia",
    "Islamic Republic of Iran": "Iran",
    "Republic of Iraq": "Iraq",
    "State of Kuwait": "Kuwait",
    "State of Qatar": "Qatar",
    "Bolivarian Republic of Venezuela": "Venezuela",
    "UK": "United Kingdom",
    "U.K.": "United Kingdom",
    "Great Britain": "United Kingdom",
    "Republic of Kazakhstan": "Kazakhstan",
    "Federal Republic of Nigeria": "Nigeria",
}


def canonical_country_name(value: str) -> str:
    """Return a stable producer-country name across DB, graph, and model data.

    Matching is case-insensitive on the alias table: model output varies in
    casing and an unrecognised variant is dropped downstream rather than
    flagged, so a near-miss silently costs a producer its risk score.
    """
    name = (value or "").strip()
    if not name:
        return name
    if name in COUNTRY_ALIASES:
        return COUNTRY_ALIASES[name]
    lowered = name.casefold()
    for alias, canonical in COUNTRY_ALIASES.items():
        if alias.casefold() == lowered:
            return canonical
    return name

#: Energy-impact crisis vocabulary for GDELT Query B.
PRODUCER_CRISIS_VOCAB: list[str] = [
    "oil", "energy", "crude", "export", "sanctions", "embargo",
    "pipeline", "refinery", "production cut", "war", "conflict",
    "coup", "mobilise", "troops", "shutdown", "force majeure",
    "nationalisation", "export ban", "blockade", "offensive",
]

#: Mapping from producer country → inferred downstream chokepoints.
#: Used by modeler_agent when a scored event has no direct chokepoint reported.
#: Severity contribution is discounted by PRODUCER_CHOKEPOINT_INFER_DISCOUNT
#: and labeled with inference_source="producer_country" in all API responses.
PRODUCER_TO_CHOKEPOINTS: dict[str, list[str]] = {
    "Russia":        ["Turkish Straits", "Strait of Malacca"],
    "Saudi Arabia":  ["Strait of Hormuz"],
    "Iran":          ["Strait of Hormuz"],
    "Iraq":          ["Strait of Hormuz"],
    "UAE":           ["Strait of Hormuz"],
    "Kuwait":        ["Strait of Hormuz"],
    "Qatar":         ["Strait of Hormuz"],
    "Bahrain":       ["Strait of Hormuz"],
    "Nigeria":       ["Cape of Good Hope"],
    "Angola":        ["Cape of Good Hope"],
    "Libya":         ["Suez Canal", "Strait of Gibraltar"],
    "Algeria":       ["Strait of Gibraltar"],
    "Kazakhstan":    ["Turkish Straits"],
    "Azerbaijan":    ["Turkish Straits"],
    "Venezuela":     [],  # Atlantic routes; no single dominant chokepoint
    "USA":           [],
    "Canada":        [],
    "Norway":        [],
    "Brazil":        [],
    "Mexico":        [],
}

#: Severity multiplier applied to inferred (not directly reported) chokepoint risk.
#: Env-tunable. Labeled as inferred in all UI and API outputs.
PRODUCER_CHOKEPOINT_INFER_DISCOUNT: float = float(
    os.getenv("PRODUCER_CHOKEPOINT_INFER_DISCOUNT", "0.70")
)

#: Weight applied to chokepoints mentioned in conflict news but not directly targeted.
CHOKEPOINT_INDIRECT_MENTION_DISCOUNT: float = 0.5
