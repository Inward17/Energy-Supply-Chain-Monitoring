"use client"

import { useEffect, useMemo, useState } from "react"
import { Droplet, Gauge, Loader, GitCompare } from "lucide-react"
import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  Legend,
} from "recharts"
import { Panel, StatChip } from "../ui"
import { InfoTooltip } from "@/components/ui/info-tooltip"
import { fetchSpr, fetchChokepoints, type SprResult } from "@/lib/api"
import { chartTooltip } from "../chart-tooltip"
import { demandPlaybook, sprSites } from "../data"
import { SprAssumptionsForm, SPR_ASSUMPTIONS_DEFAULTS, type SprAssumptionsValue } from "../shared/spr-assumptions-form"

const INDIA_SPR_SITES = [
  { name: "Visakhapatnam", pct: 85 },
  { name: "Mangaluru",     pct: 72 },
  { name: "Padur",         pct: 68 },
]

export function SprOptimizer() {
  const [chokepoints, setChokepoints] = useState<string[]>([])
  const [blocked, setBlocked]         = useState("")
  const [leadTime, setLeadTime]       = useState(14)
  const [assumptions, setAssumptions] = useState<SprAssumptionsValue>(SPR_ASSUMPTIONS_DEFAULTS)

  // Compare mode: second scenario
  const [compareMode, setCompareMode] = useState(false)
  const [assumptionsB, setAssumptionsB] = useState<SprAssumptionsValue>({
    gdpRate: 0.05,
    runCut: 15,
    indCut: 10,
    transCut: 5,
  })

  const [phase, setPhase]   = useState<"idle" | "loading" | "done" | "error">("idle")
  const [result, setResult] = useState<SprResult | null>(null)
  const [resultB, setResultB] = useState<SprResult | null>(null)
  const [error, setError]   = useState("")
  const isStale = phase === "idle" && result !== null

  useEffect(() => {
    fetchChokepoints()
      .then((cps) => { if (cps.length) { setChokepoints(cps); setBlocked(cps[0]) } })
      .catch(() => {})
  }, [])

  async function runSpr() {
    setPhase("loading")
    setError("")
    setResult(null)
    setResultB(null)
    try {
      const calls: Promise<SprResult>[] = [
        fetchSpr({
          blocked_chokepoint: blocked,
          lead_time_days: leadTime,
          gdp_impact_rate_pct: assumptions.gdpRate * 100,  // slider is decimal, _pct helper /100 cancels out
          run_rate_cut_pct: assumptions.runCut,
          industrial_cut_pct: assumptions.indCut,
          transport_cut_pct: assumptions.transCut,
        }),
      ]
      if (compareMode) {
        calls.push(
          fetchSpr({
            blocked_chokepoint: blocked,
            lead_time_days: leadTime,
            gdp_impact_rate_pct: assumptionsB.gdpRate * 100,  // slider is decimal, _pct helper /100 cancels out
            run_rate_cut_pct: assumptionsB.runCut,
            industrial_cut_pct: assumptionsB.indCut,
            transport_cut_pct: assumptionsB.transCut,
          })
        )
      }
      const results = await Promise.all(calls)
      setResult(results[0])
      setResultB(results[1] ?? null)
      setPhase("done")
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error")
      setPhase("error")
    }
  }

  const burndown = result?.burndown_series ?? []
  const actions  = result?.demand_actions  ?? []
  const statusColor = result?.status_color ?? "green"

  // Merge burndown series for compare mode
  // IMPORTANT: use result.burndown_series directly (not the `burndown` derived var)
  // to avoid stale-closure issues with useMemo.
  const mergedBurndown = useMemo(() => {
    const base = result?.burndown_series ?? []
    if (!compareMode || !resultB) return base
    return base.map((pt, i) => ({
      ...pt,
      managedB: resultB.burndown_series[i]?.managed ?? undefined,
    }))
  }, [result, resultB, compareMode])

  return (
    <div className="space-y-4">
      <Panel title="SPR Optimizer" icon={<Droplet className="h-4 w-4 text-cyan-400" />}>
        <div className="space-y-4 p-4">
          {/* Controls */}
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
            <div>
              <label className="mb-1.5 block text-[11px] font-medium uppercase tracking-wider text-slate-400">
                <InfoTooltip term="Chokepoint" label="Blocked Chokepoint" />
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
                min={5} max={60} value={leadTime}
                onChange={(e) => { setLeadTime(Number(e.target.value)); setPhase("idle") }}
                className="mt-2.5 h-1.5 w-full cursor-pointer appearance-none rounded-full bg-slate-700 accent-cyan-500"
              />
            </div>
          </div>

          {/* Scenario A assumptions */}
          <div className="rounded-md border border-slate-700/50 bg-slate-900/50 p-4">
            <div className="mb-3 flex items-center justify-between">
              <h4 className="text-[11px] font-medium uppercase tracking-wider text-slate-400">
                {compareMode ? "Scenario A — Conservative Levers" : "Model Assumptions"}
              </h4>
              <button
                type="button"
                onClick={() => setCompareMode(!compareMode)}
                className={`flex items-center gap-1.5 rounded-md px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wider transition-colors ${
                  compareMode
                    ? "bg-cyan-500/20 text-cyan-400 border border-cyan-500/30"
                    : "border border-slate-700 text-slate-400 hover:border-slate-600 hover:text-slate-300"
                }`}
              >
                <GitCompare className="h-3 w-3" />
                {compareMode ? "Exit Compare" : "Compare Scenarios"}
              </button>
            </div>
            <SprAssumptionsForm
              value={assumptions}
              onChange={(next) => { setAssumptions(next); setPhase("idle") }}
              hideHeader
            />
          </div>

          {/* Scenario B assumptions (compare mode only) */}
          {compareMode && (
            <div className="rounded-md border border-amber-500/30 bg-amber-900/10 p-4">
              <h4 className="mb-3 text-[11px] font-medium uppercase tracking-wider text-amber-400">
                Scenario B — Aggressive Levers
              </h4>
              <SprAssumptionsForm
                value={assumptionsB}
                onChange={(next) => { setAssumptionsB(next); setPhase("idle") }}
                hideHeader
              />
            </div>
          )}

          <button
            type="button"
            onClick={runSpr}
            disabled={phase === "loading"}
            className="flex w-full items-center justify-center gap-2 rounded-md bg-cyan-500 px-4 py-2.5 text-sm font-semibold text-slate-950 transition-colors hover:bg-cyan-400 disabled:opacity-60"
          >
            {phase === "loading" ? (
              <><Loader className="h-4 w-4 animate-spin" /> Running Simulation...</>
            ) : compareMode ? "Run Both Scenarios" : "Run SPR Simulation"}
          </button>

          {phase === "error" && (
            <div className="rounded border border-rose-500/40 bg-rose-500/10 p-3 text-sm text-rose-300">{error}</div>
          )}

          {result && (
            <div className={`space-y-4 ${isStale ? "opacity-50 transition-opacity" : "transition-opacity"}`}>
              {/* KPI cards (Scenario A) */}
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

              {/* Compare KPIs for Scenario B */}
              {compareMode && resultB && (
                <div className="rounded-md border border-amber-500/30 bg-amber-900/10 p-3">
                  <div className="mb-2 text-[11px] font-medium uppercase tracking-wider text-amber-400">
                    Scenario B Outcomes
                  </div>
                  <div className="grid grid-cols-3 gap-3">
                    <StatChip label="Shortfall" value={`${resultB.daily_shortfall_mbpd.toFixed(2)} mbpd`} accent="text-orange-400" />
                    <StatChip label="Survival" value={`${resultB.survival_days.toFixed(1)} days`} accent="text-amber-400" />
                    <StatChip label="Supply Gap" value={`${resultB.supply_gap_days.toFixed(1)} days`} accent={resultB.supply_gap_days > 0 ? "text-rose-500" : "text-emerald-400"} />
                  </div>
                </div>
              )}

              {/* Burndown chart */}
              {burndown.length > 0 && (
                <div className="rounded-lg border border-slate-800 bg-slate-950/40 p-3">
                  <p className="mb-2 flex items-center gap-2 text-sm font-medium text-slate-200">
                    <Gauge className="h-4 w-4 text-cyan-400" />
                    SPR Burn-Down Trajectory (% of capacity)
                    {compareMode && resultB && (
                      <span className="ml-2 text-[10px] font-normal text-slate-500">
                        · Cyan = Scenario A · Amber = Scenario B
                      </span>
                    )}
                  </p>
                  <div className="h-72">
                    <ResponsiveContainer width="100%" height="100%">
                      <LineChart data={mergedBurndown} margin={{ top: 24, right: 16, left: -12, bottom: 0 }}>
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
                        {compareMode && resultB && <Legend />}
                        <ReferenceLine
                          x={Math.round(leadTime)}
                          stroke="#f43f5e"
                          strokeDasharray="4 4"
                          label={{ value: "Ships Arrive", fill: "#f43f5e", fontSize: 11, position: "insideTopLeft", offset: 10 }}
                        />
                        <Line type="monotone" dataKey="baseline" name="Baseline (No Mgmt)" stroke="#f43f5e" strokeWidth={2} dot={false} isAnimationActive={false} />
                        <Line type="monotone" dataKey="managed"  name={compareMode ? "Scenario A" : "With Demand Mgmt"} stroke="#34d399" strokeWidth={2} dot={false} isAnimationActive={false} />
                        {compareMode && resultB && (
                          <Line
                            type="monotone"
                            dataKey="managedB"
                            name="Scenario B"
                            stroke="#fbbf24"
                            strokeWidth={2}
                            strokeDasharray="5 3"
                            dot={false}
                            isAnimationActive={false}
                            connectNulls={false}
                          />
                        )}
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
