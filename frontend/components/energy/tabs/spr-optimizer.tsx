"use client"

import { useEffect, useState } from "react"
import { Droplet, Gauge, Loader } from "lucide-react"
import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts"
import { Panel, StatChip } from "../ui"
import { fetchSpr, fetchChokepoints, type SprResult } from "@/lib/api"
import { chartTooltip } from "../chart-tooltip"
import { demandPlaybook, sprSites } from "../data"

const INDIA_SPR_SITES = [
  { name: "Visakhapatnam", pct: 85 },
  { name: "Mangaluru",     pct: 72 },
  { name: "Padur",         pct: 68 },
]

export function SprOptimizer() {
  const [chokepoints, setChokepoints] = useState<string[]>([])
  const [blocked, setBlocked]         = useState("")
  const [leadTime, setLeadTime]       = useState(14)
  const [gdpRate, setGdpRate]         = useState(0.035)
  const [runCut, setRunCut]           = useState(15)
  const [indCut, setIndCut]           = useState(8)
  const [transCut, setTransCut]       = useState(10)
  const [phase, setPhase]             = useState<"idle" | "loading" | "done" | "error">("idle")
  const [result, setResult]           = useState<SprResult | null>(null)
  const [error, setError]             = useState("")
  const isStale = phase === "idle" && result !== null

  useEffect(() => {
    fetchChokepoints()
      .then((cps) => { if (cps.length) { setChokepoints(cps); setBlocked(cps[0]) } })
      .catch(() => {}) // keep fallback
  }, [])

  async function runSpr() {
    setPhase("loading")
    setError("")
    try {
      const data = await fetchSpr({
        blocked_chokepoint: blocked,
        lead_time_days: leadTime,
        gdp_impact_rate_pct: gdpRate,
        run_rate_cut_pct: runCut,
        industrial_cut_pct: indCut,
        transport_cut_pct: transCut,
      })
      setResult(data)
      setPhase("done")
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error")
      setPhase("error")
    }
  }

  const burndown = result?.burndown_series ?? []
  const actions  = result?.demand_actions  ?? []
  const statusColor = result?.status_color ?? "green"

  return (
    <div className="space-y-4">
      <Panel title="SPR Optimizer" icon={<Droplet className="h-4 w-4 text-cyan-400" />}>
        <div className="space-y-4 p-4">
          {/* Controls */}
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
            <div>
              <label className="mb-1.5 block text-[11px] font-medium uppercase tracking-wider text-slate-400">
                Blocked Chokepoint
              </label>
              <select
                value={blocked}
                onChange={(e) => { setBlocked(e.target.value); setPhase("idle") }}
                className="w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-200 outline-none focus:border-cyan-500"
              >
                {chokepoints.map((c) => <option key={c}>{c}</option>)}
              </select>
            </div>
            <div>
              <div className="mb-1.5 flex items-center justify-between text-[11px] font-medium uppercase tracking-wider text-slate-400">
                <span>Rerouted Shipment Lead Time</span>
                <span className="font-mono text-cyan-400">{leadTime} days</span>
              </div>
              <input
                type="range"
                min={5}
                max={60}
                value={leadTime}
                onChange={(e) => { setLeadTime(Number(e.target.value)); setPhase("idle") }}
                className="mt-2.5 h-1.5 w-full cursor-pointer appearance-none rounded-full bg-slate-700 accent-cyan-500"
              />
            </div>
          </div>

          <div className="rounded-md border border-slate-700/50 bg-slate-900/50 p-4">
            <h4 className="mb-3 text-[11px] font-medium uppercase tracking-wider text-slate-400">
              Model Assumptions
            </h4>
            <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
              <div>
                <div className="mb-1.5 flex items-center justify-between text-[11px] font-medium uppercase tracking-wider text-slate-400">
                  <span>GDP Impact per Day</span>
                  <span className="font-mono text-cyan-400">{gdpRate.toFixed(3)}%</span>
                </div>
                <input
                  type="range" min={0.01} max={0.1} step={0.005} value={gdpRate}
                  onChange={(e) => { setGdpRate(Number(e.target.value)); setPhase("idle") }}
                  className="h-1.5 w-full cursor-pointer appearance-none rounded-full bg-slate-700 accent-cyan-500"
                />
              </div>
              <div>
                <div className="mb-1.5 flex items-center justify-between text-[11px] font-medium uppercase tracking-wider text-slate-400">
                  <span>Refinery Run-Rate Cut</span>
                  <span className="font-mono text-cyan-400">{runCut}%</span>
                </div>
                <input
                  type="range" min={0} max={50} step={1} value={runCut}
                  onChange={(e) => { setRunCut(Number(e.target.value)); setPhase("idle") }}
                  className="h-1.5 w-full cursor-pointer appearance-none rounded-full bg-slate-700 accent-cyan-500"
                />
              </div>
              <div>
                <div className="mb-1.5 flex items-center justify-between text-[11px] font-medium uppercase tracking-wider text-slate-400">
                  <span>Industrial Priority Scheme</span>
                  <span className="font-mono text-cyan-400">{indCut}%</span>
                </div>
                <input
                  type="range" min={0} max={50} step={1} value={indCut}
                  onChange={(e) => { setIndCut(Number(e.target.value)); setPhase("idle") }}
                  className="h-1.5 w-full cursor-pointer appearance-none rounded-full bg-slate-700 accent-cyan-500"
                />
              </div>
              <div>
                <div className="mb-1.5 flex items-center justify-between text-[11px] font-medium uppercase tracking-wider text-slate-400">
                  <span>Transport Fuel Rationing</span>
                  <span className="font-mono text-cyan-400">{transCut}%</span>
                </div>
                <input
                  type="range" min={0} max={50} step={1} value={transCut}
                  onChange={(e) => { setTransCut(Number(e.target.value)); setPhase("idle") }}
                  className="h-1.5 w-full cursor-pointer appearance-none rounded-full bg-slate-700 accent-cyan-500"
                />
              </div>
            </div>
            
            {(runCut + indCut + transCut > 60) && (
              <div className="mt-4 rounded border border-orange-500/40 bg-orange-500/10 p-3 text-xs text-orange-300">
                ⚠️ Combined demand cuts ({runCut + indCut + transCut}%) exceed typical operational limits.
              </div>
            )}
          </div>

          <button
            type="button"
            onClick={runSpr}
            disabled={phase === "loading"}
            className="flex w-full items-center justify-center gap-2 rounded-md bg-cyan-500 px-4 py-2.5 text-sm font-semibold text-slate-950 transition-colors hover:bg-cyan-400 disabled:opacity-60"
          >
            {phase === "loading" ? (
              <><Loader className="h-4 w-4 animate-spin" /> Running Simulation...</>
            ) : "Run SPR Simulation"}
          </button>

          {phase === "error" && (
            <div className="rounded border border-rose-500/40 bg-rose-500/10 p-3 text-sm text-rose-300">{error}</div>
          )}

          {result && (
            <div className={`space-y-4 ${isStale ? "opacity-50 transition-opacity" : "transition-opacity"}`}>
              {/* KPI cards */}
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
                <StatChip
                  label="Daily Shortfall"
                  value={`${result.daily_shortfall_mbpd.toFixed(2)} mbpd`}
                  accent="text-orange-400"
                />
                <StatChip
                  label="SPR Survival Days"
                  value={`${result.survival_days.toFixed(1)} days`}
                  accent="text-cyan-400"
                />
                <StatChip
                  label="Supply Gap"
                  value={`${result.supply_gap_days.toFixed(1)} days`}
                  accent={result.supply_gap_days > 0 ? "text-rose-500" : "text-emerald-400"}
                />
              </div>

              {/* Recommendation badge */}
              <div className={`rounded-md border p-3 text-sm ${
                statusColor === "red"    ? "border-rose-500/40 bg-rose-500/10 text-rose-300" :
                statusColor === "orange" ? "border-orange-500/40 bg-orange-500/10 text-orange-300" :
                                           "border-emerald-500/40 bg-emerald-500/10 text-emerald-300"
              }`}>
                {result.recommendation}
              </div>

              {/* Burndown chart */}
              {burndown.length > 0 && (
                <div className="rounded-lg border border-slate-800 bg-slate-950/40 p-3">
                  <p className="mb-2 flex items-center gap-2 text-sm font-medium text-slate-200">
                    <Gauge className="h-4 w-4 text-cyan-400" />
                    SPR Burn-Down Trajectory (% of capacity)
                  </p>
                  <div className="h-72">
                    <ResponsiveContainer width="100%" height="100%">
                      <LineChart data={burndown} margin={{ top: 24, right: 16, left: -12, bottom: 0 }}>
                        <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                        <XAxis
                          dataKey="day"
                          stroke="#64748b"
                          fontSize={11}
                          tickLine={false}
                          tickFormatter={(d) => `D${d}`}
                        />
                        <YAxis stroke="#64748b" fontSize={11} tickLine={false} domain={[0, 100]} />
                        <Tooltip content={chartTooltip} />
                        <ReferenceLine
                          x={Math.round(leadTime)}
                          stroke="#f43f5e"
                          strokeDasharray="4 4"
                          label={{ value: "Ships Arrive", fill: "#f43f5e", fontSize: 11, position: "insideTopLeft", offset: 10 }}
                        />
                        <Line type="monotone" dataKey="baseline" name="Baseline"      stroke="#f43f5e" strokeWidth={2} dot={false} isAnimationActive={false} />
                        <Line type="monotone" dataKey="managed"  name="With Demand Mgmt" stroke="#34d399" strokeWidth={2} dot={false} isAnimationActive={false} />
                      </LineChart>
                    </ResponsiveContainer>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </Panel>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Panel title="Demand Management Playbook">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-800 text-left text-[11px] uppercase tracking-wider text-slate-500">
                  <th className="px-4 py-2.5 font-medium">Action</th>
                  <th className="px-4 py-2.5 font-medium">Impact</th>
                  <th className="px-4 py-2.5 font-medium">Status</th>
                </tr>
              </thead>
              <tbody>
                {(actions.length > 0
                  ? actions.map((a) => ({ action: a.action, impact: `${a.saves_mbpd.toFixed(2)} mbpd`, status: "Ready" }))
                  : demandPlaybook
                ).map((p) => (
                  <tr key={p.action} className="border-b border-slate-800/60 last:border-0">
                    <td className="px-4 py-2.5 text-slate-200">{p.action}</td>
                    <td className="px-4 py-2.5 font-mono text-emerald-400">{p.impact}</td>
                    <td className="px-4 py-2.5">
                      <span className={`rounded border px-2 py-0.5 text-[10px] font-bold tracking-wider ${
                        p.status === "Ready"
                          ? "border-emerald-500/40 bg-emerald-500/15 text-emerald-400"
                          : p.status === "Armed"
                          ? "border-orange-500/40 bg-orange-500/15 text-orange-400"
                          : "border-slate-600/50 bg-slate-500/15 text-slate-400"
                      }`}>
                        {p.status.toUpperCase()}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Panel>

        <Panel title="India SPR Sites Status">
          <div className="space-y-3.5 p-4">
            {INDIA_SPR_SITES.map((s) => (
              <div key={s.name}>
                <div className="mb-1 flex items-center justify-between text-xs">
                  <span className="text-slate-300">{s.name}</span>
                  <span className="font-mono text-slate-400">{s.pct}%</span>
                </div>
                <div className="h-2 overflow-hidden rounded-full bg-slate-800">
                  <div
                    className={`h-full rounded-full ${s.pct > 70 ? "bg-emerald-400" : s.pct > 55 ? "bg-cyan-400" : "bg-orange-400"}`}
                    style={{ width: `${s.pct}%` }}
                  />
                </div>
              </div>
            ))}
          </div>
        </Panel>
      </div>
    </div>
  )
}
