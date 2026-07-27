"""
src/utils/schemas.py
────────────────────
Request models for the public API.

Every field is bounded. These endpoints are unauthenticated, so an unbounded
value is a denial-of-service primitive rather than a cosmetic omission:

  * `lead_time_days` drives `range(int(lead_time_days) + 5)` in spr_agent, which
    builds one dict per simulated day. Unbounded, a single request could pin CPU
    and exhaust memory.
  * Free-text fields are forwarded into Gemini prompts and Neo4j lookups, so an
    oversized string costs tokens and memory on every downstream hop.
  * List fields are iterated per candidate route.

Bounds are set well above any legitimate UI value: the lead-time slider tops out
at 90 days and the exclusion list is a handful of countries.
"""

from typing import Literal

from pydantic import BaseModel, Field

#: Long enough for the longest real refinery/chokepoint/grade name with room to
#: spare, short enough that a hostile payload cannot be smuggled through.
_NAME_MAX = 120
#: Scenario labels are sentence-like ("Scenario B: Suez Canal Drone Strikes").
_LABEL_MAX = 200
#: The UI ships four exclusions by default; 50 allows generous manual editing.
_LIST_MAX = 50

#: Ranking modes understood by fixer_agent. A `Literal` rejects anything else at
#: the edge instead of silently falling through to the default branch.
RankingMode = Literal["cost", "speed"]


class RerouteRequest(BaseModel):
    blocked_chokepoint: str = Field(..., min_length=1, max_length=_NAME_MAX)
    destination_refinery: str | None = Field(None, max_length=_NAME_MAX)
    crude_grade: str | None = Field(None, max_length=_NAME_MAX)
    ranking_mode: RankingMode = "cost"
    excluded_countries: list[str] = Field(
        default_factory=list, max_length=_LIST_MAX
    )
    strict_grade_match: bool = False


class SprRequest(BaseModel):
    blocked_chokepoint: str = Field(..., min_length=1, max_length=_NAME_MAX)
    # Upper bound is the simulation horizon, not a modelling opinion: the series
    # is built day by day, so this value directly sizes an allocation.
    lead_time_days: float = Field(..., ge=0.0, le=365.0)
    disrupted_volume_mbpd: float | None = Field(None, ge=0.0, le=100.0)
    gdp_impact_rate: float = Field(0.035, ge=0.0, le=0.1)
    run_rate_cut: float = Field(0.15, ge=0.0, le=0.5)
    industrial_cut: float = Field(0.08, ge=0.0, le=0.5)
    transport_cut: float = Field(0.10, ge=0.0, le=0.5)


class WarRoomRequest(BaseModel):
    scenario_name: str = Field(..., min_length=1, max_length=_LABEL_MAX)
    blocked_chokepoint: str = Field(..., min_length=1, max_length=_NAME_MAX)
    destination_refinery: str | None = Field(None, max_length=_NAME_MAX)
    disrupted_volume_mbpd: float = Field(..., ge=0.0, le=100.0)
    crude_grade: str | None = Field(None, max_length=_NAME_MAX)
    ranking_mode: RankingMode = "cost"
    excluded_countries: list[str] = Field(
        default_factory=list, max_length=_LIST_MAX
    )
    strict_grade_match: bool = False
    gdp_impact_rate: float = Field(0.035, ge=0.0, le=0.1)
    run_rate_cut: float = Field(0.15, ge=0.0, le=0.5)
    industrial_cut: float = Field(0.08, ge=0.0, le=0.5)
    transport_cut: float = Field(0.10, ge=0.0, le=0.5)


class BacktestRequest(BaseModel):
    event_name: str = Field(..., min_length=1, max_length=_NAME_MAX)
