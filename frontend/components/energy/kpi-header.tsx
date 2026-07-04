"use client"

import { useEffect, useState } from "react"
import { fetchLiveMetrics, type LiveMetrics } from "@/lib/api"
import { Loader2 } from "lucide-react"

const toneMap = {
  emerald: "text-emerald-400",
  rose:    "text-rose-500",
  cyan:    "text-cyan-400",
} as const

export function KpiHeader() {
  const [live, setLive] = useState<LiveMetrics | null>(null)

  useEffect(() => {
    // Fetch immediately then poll every 30s
    const load = () => fetchLiveMetrics().then(setLive).catch(() => {})
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

  // Build the 6 KPI tiles from live data
  const kpis = [
        {
          label: "SDI Score",
          value: live.sdi_score.toFixed(1),
          unit:  "/ 100",
          sub:   `range ${Math.round(live.confidence_low)}–${Math.round(live.confidence_high)}`,
          tone:  live.sdi_score > 60 ? ("rose" as const) : ("emerald" as const),
        },
        {
          label: "Top Risk Region",
          value: live.top_region || "—",
          unit:  "",
          sub:   live.top_chokepoints.slice(0, 1).join("") || "No active alerts",
          tone:  "rose" as const,
        },
        {
          label: "Vessel Density Δ",
          value: live.delta_d.toFixed(2),
          unit:  "",
          sub:   "vs baseline",
          tone:  live.delta_d > 0.3 ? ("rose" as const) : ("emerald" as const),
        },
        {
          label: "Brent Spot",
          value: `$${live.current_brent.toFixed(2)}`,
          unit:  "/bbl",
          sub:   `Impact est. +$${live.price_impact_usd.toFixed(2)}/bbl`,
          tone:  "cyan" as const,
        },
        {
          label: "Active Alerts",
          value: String(live.active_alerts),
          unit:  "",
          sub:   `${live.vessel_count} vessels tracked`,
          tone:  live.active_alerts > 0 ? ("rose" as const) : ("emerald" as const),
        },
        {
          label: "Freight Stress",
          value: live.delta_f.toFixed(2),
          unit:  "",
          sub:   `BOAT ETF at $${live.current_freight.toFixed(2)}`,
          tone:  live.delta_f > 0.3 ? ("rose" as const) : ("emerald" as const),
        },
      ]

  return (
    <div className="grid grid-cols-2 gap-y-4 rounded-lg border border-slate-800 bg-slate-900/40 px-4 py-4 sm:grid-cols-3 lg:grid-cols-6">
      {kpis.map((kpi, i) => (
        <div
          key={kpi.label}
          className={`px-4 ${i !== 0 ? "lg:border-l lg:border-slate-800" : ""}`}
        >
          <p className="text-[11px] uppercase tracking-widest text-slate-500">{kpi.label}</p>
          <p className="mt-1 flex items-baseline gap-1.5">
            <span className="font-mono text-2xl font-bold text-white">{kpi.value}</span>
            {kpi.unit && <span className="text-xs text-slate-500">{kpi.unit}</span>}
          </p>
          <p className={`mt-0.5 text-[11px] ${toneMap[kpi.tone]}`}>{kpi.sub}</p>
        </div>
      ))}
    </div>
  )
}
