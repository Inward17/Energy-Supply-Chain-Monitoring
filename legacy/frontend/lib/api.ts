/**
 * lib/api.ts
 * ──────────
 * Typed fetch utility for all Energy Resilience OS API endpoints.
 *
 * All functions return strongly-typed data or throw an Error on failure.
 * Import these into your React components to replace mock data from data.ts.
 *
 * Base URL defaults to http://localhost:8000 (FastAPI dev server).
 * Override by setting NEXT_PUBLIC_API_URL in .env.local
 */

const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"

// ── Generic fetch helper ──────────────────────────────────────────────────────

async function apiFetch<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  })
  if (!res.ok) {
    const body = await res.text()
    throw new Error(`API ${res.status}: ${body}`)
  }
  return res.json() as Promise<T>
}

// ── Types ─────────────────────────────────────────────────────────────────────

export type SdiBand = "LOW" | "MODERATE" | "ELEVATED" | "SEVERE" | "CRITICAL"

export interface LiveMetrics {
  sdi_score: number
  /** Server-side severity banding; the source of truth for headline colour. */
  sdi_band?: SdiBand
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
  gemini_configured?: boolean
  ais_configured?: boolean
  w1?: number
  w2?: number
  w3?: number
  w4?: number
  confidence?: number
  ais_status?: "available" | "partial" | "unavailable"
  ais_type_coverage?: number
  market_status?: "available" | "partial" | "stale" | "unavailable"
  event_source_at?: string | null
  vessel_source_at?: string | null
  market_source_date?: string | null
  computed_at?: string
  updated_at?: string
  status?: string
  error?: string
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
  source_urls?: string[]
  source_fetched_at?: string
  scored_at: string
}

export interface RiskEventDetail extends RiskEvent {
  severity_reasoning: string
  affected_producer_countries: string[]
  directly_affected_producer_countries?: string[]
  affected_grades: string[]
  inferred_chokepoints?: string[]
  inference_source?: string
}

export interface ChokepointRisk {
  name: string
  flow_mb_day: number
  risk_score: number
  sdi_contribution: number
  vessels_current?: number
  vessels_baseline?: number
  price_impact_usd?: number
  inference_source?: string
  status?: string
  error?: string
}

export interface SdiPoint {
  scored_at: string
  sdi_score: number
  confidence_low: number
  confidence_high: number
}

export interface ProducerRisk {
  name: string
  risk_score: number
  exposure_type: "baseline" | "direct" | "transit"
  risk_driver?: string | null
  source_event_id?: number | null
}

export interface PriceSeries {
  d: string
  price: number
  ma: number
}

export interface Instrument {
  ticker: string
  price: number
  high_52w: number
  low_52w: number
  volume: number
  series: PriceSeries[]
}

export interface MarketData {
  instruments: Instrument[]
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

export interface ProcurementRow {
  export_port: string
  country: string
  crude_grade: string
  brent_spot_usd: number
  freight_premium: number
  landed_cost_usd: number
  lead_time_days: number
  risk_score: number
  composite_score: number
  recommended: boolean
  top: boolean
  match_type: "exact" | "substitute" | "blend"
  match_reason: string
}

export interface Diagnostic {
  reason: "no_data_for_grade" | "chokepoint_bypass_eliminates_all_grade_sources" | "grade_only_available_from_excluded_countries"
  requested_grade: string
  excluding: string[]
  grade_suppliers: string[]
  message: string
}

export interface RerouteResult {
  procurement_matrix: ProcurementRow[]
  resilience_score: number
  current_brent_usd: number
  grade_filtered: boolean
  destination_refinery: string
  refinery_options: { refinery: string; country: string; capacity_kbd: number }[]
  freight_params: Record<string, number>
  context_events: RiskEvent[]
  diagnostic?: Diagnostic
}

export interface BurndownPoint {
  day: number
  baseline: number
  managed: number
}

export interface SprResult {
  blocked_chokepoint: string
  daily_shortfall_mbpd: number
  lead_time_days: number
  spr_capacity_mb: number
  survival_days: number
  supply_gap_days: number
  adjusted_gap_days: number
  adjusted_survival_days: number
  demand_actions: { action: string; reduction: string; saves_mbpd: number; cost: string }[]
  recommendation: string
  status_color: "green" | "orange" | "red"
  macro_gdp_impact_pct: string
  macro_gdp_impact_usd: string
  macro_infl_impact: string
  macro_gdp_adj: string
  macro_infl_adj: string
  india_consumption_mbpd: number
  burndown_series: BurndownPoint[]
}

export interface WarRoomRoute {
  terminal: string
  grade: string
  landed: string
  lead: string
  match_type: "exact" | "substitute"
  match_reason: string
}

export interface WarRoomSpr {
  survival_days: number
  supply_gap_days: number
  gdp_impact: string
  infl_impact: string
  recommendation: string
  status_color: string
}

export interface WarRoomResult {
  top_routes: WarRoomRoute[]
  spr_trajectory: WarRoomSpr
  burndown_series: BurndownPoint[]
  executive_brief: string
  diagnostic?: Diagnostic
}

// ── API Functions ─────────────────────────────────────────────────────────────

/** KPI header data — SDI, Brent, vessel count, active alerts */
export const fetchLiveMetrics = () =>
  apiFetch<LiveMetrics>("/api/metrics/live")

/** Sentinel-scored geopolitical risk events */
export const fetchRiskEvents = (limit = 10) =>
  apiFetch<RiskEvent[]>(`/api/risk/events?limit=${limit}`)

/** Single risk event detailed view */
export const fetchRiskEventDetail = (eventId: number) =>
  apiFetch<RiskEventDetail>(`/api/risk/events/${eventId}`)

/** Per-chokepoint risk matrix */
export const fetchChokepointMatrix = () =>
  apiFetch<ChokepointRisk[]>("/api/risk/chokepoints")

/** Per-producer risk matrix */
export const fetchProducerMatrix = () =>
  apiFetch<ProducerRisk[]>("/api/risk/producers")

/** One event's contribution to a chokepoint or producer score. */
export interface RiskContributor {
  id: number | null
  region: string | null
  disruption_type: string | null
  severity: number
  confidence: number | null
  summary: string | null
  source_urls: string[]
  source_fetched_at: string | null
  age_hours: number | null
  contribution: number
  multiplier: number
  basis: string
  exposure_type?: string
}

export interface ChokepointDetail {
  name: string
  risk_score: number
  flow_mb_day: number
  price_impact_usd: number
  is_baseline: boolean
  baseline_risk: number
  elevated_threshold: number
  driver: RiskContributor | null
  contributors: RiskContributor[]
  dependent_producers: string[]
  explanation: string
}

export interface ProducerDetail {
  name: string
  risk_score: number
  exposure_type: string
  is_baseline: boolean
  baseline_risk: number
  transit_chokepoints: string[]
  transit_discount: number
  driver: RiskContributor | null
  contributors: RiskContributor[]
  explanation: string
}

/** Score attribution for a single chokepoint */
export const fetchChokepointDetail = (name: string) =>
  apiFetch<ChokepointDetail>(`/api/risk/chokepoints/${encodeURIComponent(name)}`)

/** Score attribution for a single producer country */
export const fetchProducerDetail = (name: string) =>
  apiFetch<ProducerDetail>(`/api/risk/producers/${encodeURIComponent(name)}`)

/** SDI timeline for line chart */
export const fetchSdiTimeline = () =>
  apiFetch<SdiPoint[]>("/api/risk/sdi-timeline")

/** Market price data for all tracked tickers */
export const fetchMarketPrices = () =>
  apiFetch<MarketData>("/api/market/prices")

/** Live AIS vessel positions */
export const fetchVessels = () =>
  apiFetch<VesselPosition[]>("/api/market/vessels")

/** Dropdown: list of chokepoints */
export const fetchChokepoints = () =>
  apiFetch<string[]>("/api/config/chokepoints")

/** Dropdown: list of destination refineries */
export const fetchRefineries = () =>
  apiFetch<string[]>("/api/config/refineries")

/** Dropdown: list of crude grades */
export const fetchGrades = () =>
  apiFetch<string[]>("/api/config/grades")

/** Run the 5-step Fixer Agent (Reroute Matrix tab) */
export const fetchReroute = (params: {
  blocked_chokepoint: string
  destination_refinery?: string
  crude_grade?: string
  ranking_mode?: "cost" | "speed"
  excluded_countries?: string[]
  strict_grade_match?: boolean
}) =>
  apiFetch<RerouteResult>("/api/orchestrator/reroute", {
    method: "POST",
    body: JSON.stringify(params),
  })

/** Run the SPR Burn-Down Modeller (SPR Optimizer tab) */
export const fetchSpr = (params: {
  blocked_chokepoint: string
  lead_time_days: number
  disrupted_volume_mbpd?: number
  gdp_impact_rate_pct?: number
  run_rate_cut_pct?: number
  industrial_cut_pct?: number
  transport_cut_pct?: number
}) => {
  const body = {
    ...params,
    gdp_impact_rate: params.gdp_impact_rate_pct !== undefined ? params.gdp_impact_rate_pct / 100 : undefined,
    run_rate_cut: params.run_rate_cut_pct !== undefined ? params.run_rate_cut_pct / 100 : undefined,
    industrial_cut: params.industrial_cut_pct !== undefined ? params.industrial_cut_pct / 100 : undefined,
    transport_cut: params.transport_cut_pct !== undefined ? params.transport_cut_pct / 100 : undefined,
  }
  return apiFetch<SprResult>("/api/orchestrator/spr", {
    method: "POST",
    body: JSON.stringify(body),
  })
}

/** Run the full War Room pipeline (Reroute + SPR + Gemini Brief) */
export const fetchWarRoom = (params: {
  scenario_name: string
  blocked_chokepoint: string
  destination_refinery?: string
  disrupted_volume_mbpd: number
  crude_grade?: string
  ranking_mode?: "cost" | "speed"
  excluded_countries?: string[]
  strict_grade_match?: boolean
  gdp_impact_rate_pct?: number
  run_rate_cut_pct?: number
  industrial_cut_pct?: number
  transport_cut_pct?: number
}) => {
  const body = {
    ...params,
    gdp_impact_rate: params.gdp_impact_rate_pct !== undefined ? params.gdp_impact_rate_pct / 100 : undefined,
    run_rate_cut: params.run_rate_cut_pct !== undefined ? params.run_rate_cut_pct / 100 : undefined,
    industrial_cut: params.industrial_cut_pct !== undefined ? params.industrial_cut_pct / 100 : undefined,
    transport_cut: params.transport_cut_pct !== undefined ? params.transport_cut_pct / 100 : undefined,
  }
  return apiFetch<WarRoomResult>("/api/orchestrator/war-room", {
    method: "POST",
    body: JSON.stringify(body),
  })
}

export interface BacktestPoint {
  date: string
  sdi_score: number
  brent_price: number
}

export interface BacktestSensitivityPoint {
  threshold: number
  alert_date: string | null
  lead_time_days: number
}

export interface BacktestResult {
  series: BacktestPoint[]
  system_alert_date: string | null
  market_reaction_date: string | null
  lead_time_days: number
  verdict: string
  sdi_threshold?: number
  threshold_sensitivity?: BacktestSensitivityPoint[]
}

export const fetchBacktest = (eventName: string) =>
  apiFetch<BacktestResult>(`/api/backtest/${eventName}`)

export interface BacktestJob {
  id: number
  event_name: string
  status: string
  progress_pct: number | null
  progress_note: string | null
  start_time: string | null
  end_time: string | null
  created_at: string
  error_log: string | null
}

export const fetchBacktestJobs = () =>
  apiFetch<BacktestJob[]>("/api/backtest/jobs")

export const triggerBacktest = (eventName: string) =>
  apiFetch<{job_id: number, status: string}>("/api/backtest/trigger", {
    method: "POST",
    body: JSON.stringify({ event_name: eventName })
  })
