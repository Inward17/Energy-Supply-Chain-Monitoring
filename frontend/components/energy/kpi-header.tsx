"use client"

import { useEffect, useState } from "react"
import { fetchLiveMetrics, type LiveMetrics } from "@/lib/api"
import { Loader2 } from "lucide-react"
import { timeAgo } from "@/lib/utils"

const toneMap = {
  emerald: "text-emerald-400",
  rose: "text-rose-500",
  cyan: "text-cyan-400",
} as const

export function KpiHeader() {
  const [live, setLive] = useState<LiveMetrics | null>(null)

  useEffect(() => {
    // Fetch immediately then poll every 30s
    const load = () => fetchLiveMetrics().then(setLive).catch(() => { })
    load()
    const interval = setInterval(load, 30_000)
    return () => clearInterval(interval)
  }, [])

  if (!live) {
    return (
      <div className="flex min-h-[104px] items-center justify-center rounded-lg border border-slate-800 bg-slate-900/40">
        <Loader2 className="h-6 w-6 animate-spin text-slate-500" />
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
      sub: `range ${Math.round(live.confidence_low)}–${Math.round(live.confidence_high)}`,
      tone: live.sdi_score > 60 ? ("rose" as const) : ("emerald" as const),
      hasBreakdown: true,
    },
    {
      label: "Top Risk Region",
      value: live.top_region || "—",
      unit: "",
      sub: live.top_chokepoints.slice(0, 1).join("") || "No active alerts",
      tone: "rose" as const,
    },
    {
      label: "Vessel Density Δ",
      value: live.delta_d.toFixed(2),
      unit: "",
      sub: "vs baseline",
      tone: live.delta_d > 0.3 ? ("rose" as const) : ("emerald" as const),
    },
    {
      label: "Brent Spot",
      value: `$${live.current_brent.toFixed(2)}`,
      unit: "/bbl",
      sub: `Impact est. +$${live.price_impact_usd.toFixed(2)}/bbl`,
      tone: "cyan" as const,
    },
    {
      label: "Active Alerts",
      value: String(live.active_alerts),
      unit: "",
      sub: `${live.vessel_count} vessels tracked`,
      tone: live.active_alerts > 0 ? ("rose" as const) : ("emerald" as const),
    },
    {
      label: "Freight Stress",
      value: live.delta_f.toFixed(2),
      unit: "",
      sub: `BOAT ETF at $${live.current_freight.toFixed(2)}`,
      tone: live.delta_f > 0.3 ? ("rose" as const) : ("emerald" as const),
    },
  ]

  return (
    <div className="relative grid grid-cols-2 gap-y-4 rounded-lg border border-slate-800 bg-slate-900/40 px-4 py-4 sm:grid-cols-3 lg:grid-cols-6">
      {kpis.map((kpi, i) => (
        <div
          key={kpi.label}
          className={`group relative px-4 ${i !== 0 ? "lg:border-l lg:border-slate-800" : ""} ${kpi.hasBreakdown ? "cursor-help" : ""}`}
        >
          <p className={`text-[11px] uppercase tracking-widest text-slate-500 ${kpi.hasBreakdown ? "underline decoration-slate-500/50 decoration-dashed underline-offset-4" : ""}`}>
            {kpi.label}
          </p>
          <p className="mt-1 flex items-baseline gap-1.5">
            <span className="font-mono text-2xl font-bold text-white">{kpi.value}</span>
            {kpi.unit && <span className="text-xs text-slate-500">{kpi.unit}</span>}
          </p>
          <p className={`mt-0.5 text-[11px] ${toneMap[kpi.tone]}`}>{kpi.sub}</p>

          {kpi.hasBreakdown && breakdownData && (
            <div className="pointer-events-none absolute left-0 top-full mt-2 w-72 opacity-0 transition-opacity group-hover:opacity-100 z-50">
              <div className="rounded-md border border-slate-700 bg-slate-900 p-4 shadow-xl">
                <p className="text-xs text-slate-300 mb-3 leading-relaxed">{sdiSentence}</p>
                <div className="space-y-1.5 font-mono text-[10px] text-slate-400">
                  {breakdownData.map((c: any) => (
                    <div key={c.name} className="flex justify-between border-b border-slate-800 pb-1">
                      <span>{c.name}</span>
                      <span className="text-slate-200">{c.raw.toFixed(2)} × {(c.weight * 100).toFixed(0)}% = <strong className="text-white">{c.pts.toFixed(1)}</strong></span>
                    </div>
                  ))}
                  <div className="flex justify-between pt-1">
                    <span className="font-bold text-slate-300">Total SDI</span>
                    <strong className="text-cyan-400">{live.sdi_score.toFixed(1)}</strong>
                  </div>
                </div>
                {live.confidence != null && (
                  <p className="text-[10px] text-slate-500 mt-2 text-right italic">
                    Geopolitical confidence: {(live.confidence * 100).toFixed(0)}%
                  </p>
                )}
              </div>
            </div>
          )}
        </div>
      ))}
      {live.updated_at && (
        <div className="absolute top-2 right-4 text-[10px] text-slate-500">
          updated {timeAgo(live.updated_at)}
        </div>
      )}
    </div>
  )
}
