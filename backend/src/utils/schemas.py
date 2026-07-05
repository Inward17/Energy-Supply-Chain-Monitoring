from pydantic import BaseModel, Field

class RerouteRequest(BaseModel):
    blocked_chokepoint: str
    destination_refinery: str | None = None
    crude_grade: str | None = None
    ranking_mode: str = "cost"

class SprRequest(BaseModel):
    blocked_chokepoint: str
    lead_time_days: float
    disrupted_volume_mbpd: float | None = None
    gdp_impact_rate: float = Field(0.035, ge=0.0, le=0.1)
    run_rate_cut: float = Field(0.15, ge=0.0, le=0.5)
    industrial_cut: float = Field(0.08, ge=0.0, le=0.5)
    transport_cut: float = Field(0.10, ge=0.0, le=0.5)

class WarRoomRequest(BaseModel):
    scenario_name: str
    blocked_chokepoint: str
    destination_refinery: str | None = None
    disrupted_volume_mbpd: float
    gdp_impact_rate: float = Field(0.035, ge=0.0, le=0.1)
    run_rate_cut: float = Field(0.15, ge=0.0, le=0.5)
    industrial_cut: float = Field(0.08, ge=0.0, le=0.5)
    transport_cut: float = Field(0.10, ge=0.0, le=0.5)

class BacktestRequest(BaseModel):
    event_name: str
