"use client"

import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react"
import {
  fetchChokepointMatrix,
  fetchLiveMetrics,
  fetchMarketPrices,
  fetchProducerMatrix,
  fetchRiskEvents,
  fetchSdiTimeline,
  fetchVessels,
  type ChokepointRisk,
  type LiveMetrics,
  type MarketData,
  type ProducerRisk,
  type RiskEvent,
  type SdiPoint,
  type VesselPosition,
} from "@/lib/api"
import { ageMs } from "./ui"

/** Shared dashboard data. One fetch cycle feeds every page, so switching pages
 *  never refetches, and the 30 s poll pauses while the tab is hidden — an open
 *  background tab no longer keeps the database awake. */
export interface Snapshot {
  live: LiveMetrics | null
  events: RiskEvent[]
  chokepoints: ChokepointRisk[]
  producers: ProducerRisk[]
  timeline: SdiPoint[]
  market: MarketData | null
  vessels: VesselPosition[]
}

export interface Filters {
  region: string
  minSeverity: number // 0–1
  autoRefresh: boolean
}

interface Ctx extends Snapshot {
  loading: boolean
  failed: boolean
  lastOk: string | null
  refresh: () => Promise<void>
  filters: Filters
  setFilters: (f: Partial<Filters>) => void
  /** Events after the region/severity filters. */
  visibleEvents: RiskEvent[]
}

const DataCtx = createContext<Ctx | null>(null)

const EMPTY: Snapshot = { live: null, events: [], chokepoints: [], producers: [], timeline: [], market: null, vessels: [] }
const POLL_MS = 30_000

export const REGIONS = ["All regions", "Persian Gulf", "Middle East", "Red Sea", "Eastern Europe", "West Africa", "Southeast Asia", "North America"]

export function DataProvider({ children }: { children: ReactNode }) {
  const [snap, setSnap] = useState<Snapshot>(EMPTY)
  const [loading, setLoading] = useState(true)
  const [failed, setFailed] = useState(false)
  const [lastOk, setLastOk] = useState<string | null>(null)
  const [filters, setF] = useState<Filters>({ region: "All regions", minSeverity: 0, autoRefresh: true })
  const inflight = useRef<Promise<void> | null>(null)

  const refresh = useCallback(() => {
    if (inflight.current) return inflight.current
    const p = (async () => {
      // Each source is independent: one failing endpoint must not blank the rest.
      const [live, events, chokepoints, producers, timeline, market, vessels] = await Promise.allSettled([
        fetchLiveMetrics(),
        fetchRiskEvents(50),
        fetchChokepointMatrix(),
        fetchProducerMatrix(),
        fetchSdiTimeline(),
        fetchMarketPrices(),
        fetchVessels(),
      ])
      const val = <T,>(r: PromiseSettledResult<T>, prev: T) => (r.status === "fulfilled" ? r.value : prev)
      setSnap((prev) => ({
        live: val(live, prev.live),
        events: val(events, prev.events),
        chokepoints: val(chokepoints, prev.chokepoints),
        producers: val(producers, prev.producers),
        timeline: val(timeline, prev.timeline),
        market: val(market, prev.market),
        vessels: val(vessels, prev.vessels),
      }))
      const ok = live.status === "fulfilled"
      setFailed(!ok)
      if (ok) setLastOk(new Date().toISOString())
      setLoading(false)
    })().finally(() => {
      inflight.current = null
    })
    inflight.current = p
    return p
  }, [])

  useEffect(() => {
    void refresh()
  }, [refresh])

  useEffect(() => {
    if (!filters.autoRefresh) return
    let id: number | undefined
    const start = () => {
      stop()
      id = window.setInterval(() => void refresh(), POLL_MS)
    }
    const stop = () => {
      if (id) window.clearInterval(id)
      id = undefined
    }
    const onVis = () => {
      if (document.visibilityState === "visible") {
        void refresh()
        start()
      } else stop()
    }
    if (document.visibilityState === "visible") start()
    document.addEventListener("visibilitychange", onVis)
    return () => {
      stop()
      document.removeEventListener("visibilitychange", onVis)
    }
  }, [filters.autoRefresh, refresh])

  const setFilters = useCallback((f: Partial<Filters>) => setF((p) => ({ ...p, ...f })), [])

  const visibleEvents = useMemo(
    () =>
      snap.events.filter(
        (e) =>
          e.severity >= filters.minSeverity &&
          (filters.region === "All regions" || e.region === filters.region),
      ),
    [snap.events, filters],
  )

  return (
    <DataCtx.Provider value={{ ...snap, loading, failed, lastOk, refresh, filters, setFilters, visibleEvents }}>
      {children}
    </DataCtx.Provider>
  )
}

export function useData(): Ctx {
  const c = useContext(DataCtx)
  if (!c) throw new Error("useData outside DataProvider")
  return c
}

// ── Feed health ───────────────────────────────────────────────────────────────

export type FeedState = "ok" | "stale" | "down"

export interface Feed {
  key: string
  name: string
  state: FeedState
  detail: string
  /** What part of the SDI this feed drives, for the health sheet. */
  feeds?: string
  at?: string | null
}

const DAY = 24 * 3600 * 1000

/** Per-feed status derived from /api/metrics/live. Thresholds follow the canvas:
 *  events 24 h, market 1 trading day (≈3 calendar days over a weekend). */
export function feedHealth(live: LiveMetrics | null): Feed[] {
  if (!live) return []
  const feeds: Feed[] = []

  const ais = live.ais_status ?? "unavailable"
  feeds.push({
    key: "ais",
    name: "AIS vessel feed",
    state: ais === "available" ? "ok" : ais === "partial" ? "stale" : "down",
    detail:
      ais === "available"
        ? `Positions ${live.vessel_source_at ? `as of ${new Date(live.vessel_source_at).toISOString().slice(11, 16)} UTC` : "current"}`
        : live.vessel_source_at
          ? `Last position ${new Date(live.vessel_source_at).toUTCString().slice(5, 22)} UTC`
          : "No vessel positions in the current window.",
    feeds: `vessel density · ${Math.round((live.w2 ?? 0.25) * 100)}%`,
    at: live.vessel_source_at,
  })

  const evAge = ageMs(live.event_source_at)
  feeds.push({
    key: "news",
    name: "News & Sentinel scoring",
    state: evAge == null ? "down" : evAge > DAY ? "stale" : "ok",
    detail:
      evAge == null
        ? "No scored events yet."
        : `Newest event ${new Date(live.event_source_at!).toUTCString().slice(5, 22)} UTC${evAge > DAY ? " — expected hourly." : ""}`,
    feeds: `geopolitical · ${Math.round((live.w1 ?? 0.5) * 100)}%`,
    at: live.event_source_at,
  })

  const mk = live.market_status ?? "unavailable"
  const mkAge = ageMs(live.market_source_date)
  const mkState: FeedState = mk === "unavailable" ? "down" : mk !== "available" || (mkAge != null && mkAge > 3 * DAY) ? "stale" : "ok"
  feeds.push({ key: "brent", name: "Brent · ICE close", state: mkState, detail: live.market_source_date ?? "—", feeds: `price · ${Math.round((live.w3 ?? 0.1) * 100)}%`, at: live.market_source_date })
  feeds.push({ key: "freight", name: "Freight · BOAT ETF", state: mkState, detail: live.market_source_date ?? "—", feeds: `freight · ${Math.round((live.w4 ?? 0.15) * 100)}%`, at: live.market_source_date })

  feeds.push({
    key: "gemini",
    name: "Gemini scoring",
    state: live.gemini_configured === false ? "down" : "ok",
    detail: live.gemini_configured === false ? "Not configured — geopolitical scoring disabled." : "ready",
  })
  return feeds
}

export function healthSummary(live: LiveMetrics | null, failed: boolean) {
  if (failed) return { level: "offline" as const, label: "Backend offline", live: 0, total: 5, problems: [] as Feed[] }
  if (!live) return { level: "checking" as const, label: "Checking…", live: 0, total: 5, problems: [] as Feed[] }
  const feeds = feedHealth(live)
  const problems = feeds.filter((f) => f.state !== "ok")
  const ok = feeds.length - problems.length
  return {
    level: problems.length ? ("degraded" as const) : ("ok" as const),
    label: problems.length ? `Degraded · ${problems.length} feed${problems.length > 1 ? "s" : ""}` : "All feeds live",
    live: ok,
    total: feeds.length,
    problems,
  }
}

export const FEED_COLOR: Record<FeedState, string> = { ok: "var(--x-3fcf8e)", stale: "var(--x-f2c14e)", down: "var(--x-ff5a5f)" }

/** SDI components in points, with the vessel term marked missing when AIS is down. */
export function components(live: LiveMetrics) {
  const w1 = live.w1 ?? 0.5, w2 = live.w2 ?? 0.25, w3 = live.w3 ?? 0.1, w4 = live.w4 ?? 0.15
  const aisDown = (live.ais_status ?? "unavailable") === "unavailable"
  return [
    { key: "geo", label: "Geopolitical", short: "Geo", pts: live.p_risk * w1 * 100, max: w1 * 100, frac: live.p_risk, missing: false },
    { key: "vessel", label: "Vessel density", short: "Vessel", pts: live.delta_d * w2 * 100, max: w2 * 100, frac: live.delta_d, missing: aisDown },
    { key: "brent", label: "Brent deviation", short: "Brent", pts: live.delta_p * w3 * 100, max: w3 * 100, frac: live.delta_p, missing: false },
    { key: "freight", label: "Freight stress", short: "Freight", pts: live.delta_f * w4 * 100, max: w4 * 100, frac: live.delta_f, missing: false },
  ]
}
