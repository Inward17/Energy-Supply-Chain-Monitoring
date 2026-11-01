export interface LiveMetrics {
  sdi_score: number
  confidence_low: number
  confidence_high: number
  p_risk: number
  delta_d: number
  delta_p: number
  delta_f: number
  current_brent: number
  current_freight: number
  price_impact_usd: number
  top_region: string
  top_chokepoints: string[]
  vessel_count: number
  active_alerts: number
}

export interface RiskEvent {
  id: number
  region: string
  disruption_type: string
  severity: number
  severity_label: "CRITICAL" | "HIGH" | "MODERATE" | "LOW"
  affected_chokepoints: string[]
  summary: string
  sdi_score: number
  scored_at: string
}

export interface ChokepointRisk {
  name: string
  flow_mb_day: number
  risk_score: number
  sdi_contribution: number
  vessels_current: number
  vessels_baseline: number
  price_impact_usd: number
}

export interface SdiPoint {
  scored_at: string
  sdi_score: number
  confidence_low: number
  confidence_high: number
}

export interface MarketDataSeriesPoint {
  d: string
  price: number
  ma: number
}

export interface MarketDataInstrument {
  ticker: string
  price: number
  high_52w: number
  low_52w: number
  volume: number
  series: MarketDataSeriesPoint[]
}

export interface MarketData {
  instruments: MarketDataInstrument[]
  brent_current: number
  brent_mean_30d: number
  brent_std_30d: number
}

export interface VesselPosition {
  mmsi: number | null
  vessel_name: string
  lat: number
  lon: number
  speed: number
  region: string
}

export interface RerouteResult {
  blocked_chokepoint: string
  bypassed_via: string
  alternatives: Array<{
    terminal: string
    country: string
    grade: string
    landed_cost_usd: number
    freight_premium_usd: number
    lead_time_days: number
  }>
  computation_time_ms: number
}

export interface SprResult {
  blocked_chokepoint: string
  gap_days: number
  scenario: {
    disrupted_volume_mbpd: number
    lead_time_days: number
    gdp_impact_rate: number
    run_rate_cut: number
    industrial_cut: number
    transport_cut: number
  }
  burn_down: Array<{
    day: number
    baseline_inventory: number
    managed_inventory: number
  }>
  economic_impact: {
    baseline_gdp_loss_usd: number
    managed_gdp_loss_usd: number
    savings_usd: number
  }
}

export interface WarRoomResult {
  scenario_name: string
  blocked_chokepoint: string
  disrupted_volume_mbpd: number
  reroute_options: Array<{
    terminal: string
    country: string
    grade: string
    landed_cost_usd: number
    lead_time_days: number
  }>
  spr_gap_days: number
  spr_savings_usd: number
  briefing: string
}

export interface BacktestPoint {
  date: string
  sdi_score: number
  brent_price: number
}

export interface BacktestResult {
  series: BacktestPoint[]
  system_alert_date: string | null
  market_reaction_date: string | null
  lead_time_days: number
  verdict: string
}
