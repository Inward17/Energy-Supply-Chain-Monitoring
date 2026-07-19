"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import { fetchLiveMetrics, type LiveMetrics } from "@/lib/api"
import { Loader2 } from "lucide-react"
import { timeAgo } from "@/lib/utils"

const toneMap = {
  safe: "text-safe",
  warn: "text-warn",
  orange: "text-orange",
  crit: "text-crit",
  accent: "text-accent",
} as const

/** Colour for the SDI headline, driven by the server's severity band rather
 *  than a local threshold. The previous `score > 60 ? crit : safe` rendered a
 *  55 — geopolitical risk already near its ceiling — as reassuring green. */
const sdiBandTone: Record<string, keyof typeof toneMap> = {
  LOW: "safe",
  MODERATE: "warn",
  ELEVATED: "orange",
  SEVERE: "crit",
  CRITICAL: "crit",
}

type KpiHeaderProps = {
  autoRefresh: boolean
  refreshToken: number
  onRefreshComplete: (target: "kpi" | "risk", refreshToken: number) => void
}

export function KpiHeader({ autoRefresh, refreshToken, onRefreshComplete }: KpiHeaderProps) {
  const [live, setLive] = useState<LiveMetrics | null>(null)
  const mountedRef = useRef(true)
  const inFlightRef = useRef<Promise<void> | null>(null)

  const load = useCallback(() => {
    if (inFlightRef.current) return inFlightRef.current

    const request = fetchLiveMetrics()
      .then((metrics) => {
        if (mountedRef.current) setLive(metrics)
      })
      .catch((error) => {
        console.error("Failed to load live metrics:", error)
      })

    inFlightRef.current = request
    void request.finally(() => {
      if (inFlightRef.current === request) inFlightRef.current = null
    })
    return request
  }, [])

  useEffect(() => {
    mountedRef.current = true
    void load()
    return () => {
      mountedRef.current = false
    }
  }, [load])

  useEffect(() => {
    if (!autoRefresh) return

    void load()
    const interval = window.setInterval(() => void load(), 30_000)
    return () => window.clearInterval(interval)
  }, [autoRefresh, load])

  useEffect(() => {
    if (refreshToken === 0) return
    void load().finally(() => onRefreshComplete("kpi", refreshToken))
  }, [load, onRefreshComplete, refreshToken])

  if (!live) {
    return (
      <div className="flex min-h-[104px] items-center justify-center rounded-lg border border-border bg-panel">
        <Loader2 className="h-6 w-6 animate-spin text-muted" />
      </div>
    )
  }

  // Deterministic sentence logic
  let sdiSentence = ""
  let breakdownData: any = null

  if (live.gemini_configured === false) {
    sdiSentence = "Score currently reflects only market and vessel signals — geopolitical scoring disabled."
  } else {
    const w1 = live.w1 ?? 0.40
    const w2 = live.w2 ?? 0.25
    const w3 = live.w3 ?? 0.15
    const w4 = live.w4 ?? 0.20

    const components = [
      { priority: 1, name: "Geopolitical Risk", raw: live.p_risk, weight: w1, pts: live.p_risk * w1 * 100, max: w1 * 100, label: "geopolitical news severity" },
      { priority: 2, name: "Vessel Density Anomaly", raw: live.delta_d, weight: w2, pts: live.delta_d * w2 * 100, max: w2 * 100, label: "unusually low vessel traffic" },
      { priority: 3, name: "Brent Price Deviation", raw: live.delta_p, weight: w3, pts: live.delta_p * w3 * 100, max: w3 * 100, label: "elevated Brent prices" },
      { priority: 4, name: "Freight Cost Stress", raw: live.delta_f, weight: w4, pts: live.delta_f * w4 * 100, max: w4 * 100, label: "freight cost stress" },
    ]

    breakdownData = components

    const sorted = [...components].sort((a, b) => {
      if (Math.abs(b.pts - a.pts) > 0.01) return b.pts - a.pts
      return a.priority - b.priority
    })

    const top1 = sorted[0]
    const top2 = sorted[1]

    sdiSentence = `This score is elevated mainly because of ${top1.label} (${top1.pts.toFixed(1)}/${top1.max} pts) and ${top2.label} (${top2.pts.toFixed(1)}/${top2.max} pts).`
  }

  // Build the 6 KPI tiles from live data
  const kpis = [
    {
      label: "SDI Score",
      value: live.sdi_score.toFixed(1),
      unit: "/ 100",
      sub: live.sdi_band
        ? `${live.sdi_band} · range ${Math.round(live.confidence_low)}–${Math.round(live.confidence_high)}`
        : `range ${Math.round(live.confidence_low)}–${Math.round(live.confidence_high)}`,
      tone: sdiBandTone[live.sdi_band ?? "LOW"] ?? ("safe" as const),
      hasBreakdown: true,
    },
    {
      label: "Top Risk Region",
      value: live.top_region || "—",
      unit: "",
      sub: live.top_chokepoints.slice(0, 1).join("") || "No active alerts",
      tone: "crit" as const,
    },
    {
      label: "Vessel Density Δ",
      value: live.delta_d.toFixed(2),
      unit: "",
      sub: live.ais_status === "unavailable" ? "AIS unavailable \u00b7 excluded" : live.ais_status === "partial" ? "AIS " + (100 * (live.ais_type_coverage ?? 0)).toFixed(0) + "% classified - excluded" : "vs baseline",
      tone: live.delta_d > 0.3 ? ("crit" as const) : ("safe" as const),
    },
    {
      label: "Brent Spot",
      value: `$${live.current_brent.toFixed(2)}`,
      unit: "/bbl",
      sub: live.market_status === "unavailable" ? "Market unavailable \u00b7 excluded" : live.market_status === "stale" ? "Market cache stale - excluded" : live.market_status === "partial" ? `Partial market data \u00b7 +$${live.price_impact_usd.toFixed(2)}/bbl impact` : `Impact est. +$${live.price_impact_usd.toFixed(2)}/bbl`,
      tone: "accent" as const,
    },
    {
      label: "Active Alerts",
      value: String(live.active_alerts),
      unit: "",
      sub: `${live.vessel_count} vessels tracked`,
      tone: live.active_alerts > 0 ? ("crit" as const) : ("safe" as const),
    },
    {
      label: "Freight Stress",
      value: live.delta_f.toFixed(2),
      unit: "",
      sub: live.market_status === "unavailable" ? "Market unavailable \u00b7 excluded" : live.market_status === "stale" ? "Market cache stale - excluded" : live.market_status === "partial" ? `Partial market data \u00b7 BOAT $${live.current_freight.toFixed(2)}` : `BOAT ETF at $${live.current_freight.toFixed(2)}`,
      tone: live.delta_f > 0.3 ? ("crit" as const) : ("safe" as const),
    },
  ]

  // NB: no `overflow-hidden` on the strip below — the SDI breakdown popover
  // renders under it (top-full) and would be clipped.
  return (
    <div className="relative grid grid-cols-2 rounded-xl border border-border bg-panel sm:grid-cols-3 lg:grid-cols-6">
      {kpis.map((kpi, i) => (
        <div
          key={kpi.label}
          className={`group relative px-4 py-3.5 ${i !== 0 ? "border-l border-hair" : ""} ${kpi.hasBreakdown ? "cursor-help" : ""}`}
        >
          <p className={`text-[9.5px] font-semibold uppercase tracking-[0.15em] text-faint ${kpi.hasBreakdown ? "underline decoration-muted/50 decoration-dashed underline-offset-4" : ""}`}>
            {kpi.label}
          </p>
          <p className="mt-2 flex items-baseline gap-1.5">
            <span className="truncate font-mono text-[23px] font-semibold tabular-nums text-head">{kpi.value}</span>
            {kpi.unit && <span className="text-[11px] text-faint">{kpi.unit}</span>}
          </p>
          <p className={`mt-1 text-[10.5px] ${toneMap[kpi.tone]}`}>{kpi.sub}</p>

          {kpi.hasBreakdown && breakdownData && (
            <div className="pointer-events-none absolute left-0 top-full mt-2 w-72 opacity-0 transition-opacity group-hover:opacity-100 z-50">
              <div className="rounded-md border border-border bg-panel p-4 shadow-xl">
                <p className="text-xs text-fg mb-3 leading-relaxed">{sdiSentence}</p>
                <div className="space-y-1.5 font-mono text-[10px] text-muted">
                  {breakdownData.map((c: any) => (
                    <div key={c.name} className="flex justify-between border-b border-border pb-1">
                      <span>{c.name}</span>
                      <span className="text-fg">{c.raw.toFixed(2)} × {(c.weight * 100).toFixed(0)}% = <strong className="text-head">{c.pts.toFixed(1)}</strong></span>
                    </div>
                  ))}
                  <div className="flex justify-between pt-1">
                    <span className="font-bold text-fg">Total SDI</span>
                    <strong className="text-accent">{live.sdi_score.toFixed(1)}</strong>
                  </div>
                </div>
                {live.confidence != null && (
                  <p className="text-[10px] text-muted mt-2 text-right italic">
                    Geopolitical confidence: {(live.confidence * 100).toFixed(0)}%
                  </p>
                )}
              </div>
            </div>
          )}
        </div>
      ))}
      {(live.computed_at || live.updated_at) && (
        <div className="absolute top-2 right-4 text-[10px] text-muted">
          computed {timeAgo(live.computed_at || live.updated_at!)} {"\u00b7 news "}
          {live.event_source_at ? timeAgo(live.event_source_at) : "unavailable"}
        </div>
      )}
    </div>
  )
}
