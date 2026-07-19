"use client"

import { useEffect, useMemo, useState } from "react"
import { Gauge, Loader, GitCompare } from "lucide-react"
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
import { useChartTheme } from "../chart-theme"
import { demandPlaybook, sprSites } from "../data"
import { SprAssumptionsForm, SPR_ASSUMPTIONS_DEFAULTS, type SprAssumptionsValue } from "../shared/spr-assumptions-form"

const INDIA_SPR_SITES = [
  { name: "Visakhapatnam", pct: 85 },
  { name: "Mangaluru",     pct: 72 },
  { name: "Padur",         pct: 68 },
]

export function SprOptimizer() {
  const [chokepoints, setChokepoints] = useState<string[]>([])
  const c = useChartTheme()
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
      <Panel title="SPR Optimizer" tone="accent">
        <div className="space-y-4 p-4">
          {/* Controls */}
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
            <div>
              <label className="mb-1.5 block text-[11px] font-medium uppercase tracking-wider text-muted">
                <InfoTooltip term="Chokepoint" label="Blocked Chokepoint" />
              </label>
              <select
                value={blocked}
                onChange={(e) => { setBlocked(e.target.value); setPhase("idle") }}
                className="w-full rounded-md border border-border bg-panel-2 px-3 py-2 text-sm text-fg outline-none focus:border-accent"
              >
                {chokepoints.map((c) => <option key={c}>{c}</option>)}
              </select>
            </div>
            <div>
              <div className="mb-1.5 flex items-center justify-between text-[11px] font-medium uppercase tracking-wider text-muted">
                <span>Rerouted Shipment Lead Time</span>
                <span className="font-mono text-accent">{leadTime} days</span>
              </div>
              <input
                type="range"
                min={5} max={60} value={leadTime}
                onChange={(e) => { setLeadTime(Number(e.target.value)); setPhase("idle") }}
                style={{ background: `linear-gradient(to right, var(--t-accent) 0%, var(--t-accent) ${((leadTime - 5) / 55) * 100}%, var(--t-track) ${((leadTime - 5) / 55) * 100}%, var(--t-track) 100%)` }}
                className="slider-slim mt-2.5 w-full cursor-pointer"
              />
            </div>
          </div>

          {/* Scenario A assumptions */}
          <div className="rounded-[10px] border border-border bg-panel-2 p-[15px]">
            <div className="mb-3.5 flex items-center justify-between">
              <h4 className="text-[10px] font-semibold uppercase tracking-[0.12em] text-muted">
                {compareMode ? "Scenario A — Conservative Levers" : "Model Assumptions"}
              </h4>
              <button
                type="button"
                onClick={() => setCompareMode(!compareMode)}
                className={`flex items-center gap-1.5 rounded-[7px] px-2.5 py-1.5 text-[11px] font-semibold transition-colors ${
                  compareMode
                    ? "border border-accent-border bg-accent-soft text-accent"
                    : "border border-border text-muted hover:border-muted hover:text-fg"
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
            <div className="rounded-md border border-warn/30 bg-warn-soft p-4">
              <h4 className="mb-3 text-[11px] font-medium uppercase tracking-wider text-warn">
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
            className="flex w-full items-center justify-center gap-2 rounded-md bg-accent px-4 py-2.5 text-sm font-semibold text-bg transition-colors hover:opacity-90 disabled:opacity-60"
          >
            {phase === "loading" ? (
              <><Loader className="h-4 w-4 animate-spin" /> Running Simulation...</>
            ) : compareMode ? "Run Both Scenarios" : "Run SPR Simulation"}
          </button>

          {phase === "error" && (
            <div className="rounded border border-crit/40 bg-crit-soft p-3 text-sm text-crit">{error}</div>
          )}

          {result && (
            <div className={`space-y-4 ${isStale ? "opacity-50 transition-opacity" : "transition-opacity"}`}>
              {/* KPI cards (Scenario A) */}
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
                <StatChip
                  label="Daily Shortfall"
                  value={`${result.daily_shortfall_mbpd.toFixed(2)} mbpd`}
                  accent="text-orange"
                />
                <StatChip
                  label="SPR Survival Days"
                  value={`${result.survival_days.toFixed(1)} days`}
                  accent="text-accent"
                />
                <StatChip
                  label="Supply Gap"
                  value={`${result.supply_gap_days.toFixed(1)} days`}
                  accent={result.supply_gap_days > 0 ? "text-crit" : "text-safe"}
                />
              </div>

              {/* Recommendation badge */}
              <div className={`rounded-md border p-3 text-sm ${
                statusColor === "red"    ? "border-crit/40 bg-crit-soft text-crit" :
                statusColor === "orange" ? "border-orange/40 bg-orange-soft text-orange" :
                                           "border-safe/40 bg-safe-soft text-safe"
              }`}>
                {result.recommendation}
              </div>

              {/* Compare KPIs for Scenario B */}
              {compareMode && resultB && (
                <div className="rounded-md border border-warn/30 bg-warn-soft p-3">
                  <div className="mb-2 text-[11px] font-medium uppercase tracking-wider text-warn">
                    Scenario B Outcomes
                  </div>
                  <div className="grid grid-cols-3 gap-3">
                    <StatChip label="Shortfall" value={`${resultB.daily_shortfall_mbpd.toFixed(2)} mbpd`} accent="text-orange" />
                    <StatChip label="Survival" value={`${resultB.survival_days.toFixed(1)} days`} accent="text-warn" />
                    <StatChip label="Supply Gap" value={`${resultB.supply_gap_days.toFixed(1)} days`} accent={resultB.supply_gap_days > 0 ? "text-crit" : "text-safe"} />
                  </div>
                </div>
              )}

              {/* Burndown chart */}
              {burndown.length > 0 && (
                <div className="rounded-lg border border-border bg-panel-2 p-3">
                  <p className="mb-2 flex items-center gap-2 text-sm font-medium text-fg">
                    <Gauge className="h-4 w-4 text-accent" />
                    SPR Burn-Down Trajectory (% of capacity)
                    {compareMode && resultB && (
                      <span className="ml-2 text-[10px] font-normal text-muted">
                        · Cyan = Scenario A · Amber = Scenario B
                      </span>
                    )}
                  </p>
                  <div className="h-72">
                    <ResponsiveContainer width="100%" height="100%">
                      <LineChart data={mergedBurndown} margin={{ top: 24, right: 16, left: -12, bottom: 0 }}>
                        <CartesianGrid strokeDasharray="3 3" stroke={c.grid} />
                        <XAxis
                          dataKey="day"
                          stroke={c.axis}
                          fontSize={11}
                          tickLine={false}
                          tickFormatter={(d) => `D${d}`}
                        />
                        <YAxis stroke={c.axis} fontSize={11} tickLine={false} domain={[0, 100]} />
                        <Tooltip content={chartTooltip} />
                        {compareMode && resultB && <Legend />}
                        <ReferenceLine
                          x={Math.round(leadTime)}
                          stroke={c.crit}
                          strokeDasharray="4 4"
                          label={{ value: "Ships Arrive", fill: c.crit, fontSize: 11, position: "insideTopLeft", offset: 10 }}
                        />
                        <Line type="monotone" dataKey="baseline" name="Baseline (No Mgmt)" stroke={c.crit} strokeWidth={2} dot={false} isAnimationActive={false} />
                        <Line type="monotone" dataKey="managed"  name={compareMode ? "Scenario A" : "With Demand Mgmt"} stroke={c.safe} strokeWidth={2} dot={false} isAnimationActive={false} />
                        {compareMode && resultB && (
                          <Line
                            type="monotone"
                            dataKey="managedB"
                            name="Scenario B"
                            stroke={c.warn}
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
                <tr className="border-b border-border text-left text-[11px] uppercase tracking-wider text-muted">
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
                  <tr key={p.action} className="border-b border-hair last:border-0">
                    <td className="px-4 py-2.5 text-fg">{p.action}</td>
                    <td className="px-4 py-2.5 font-mono text-safe">{p.impact}</td>
                    <td className="px-4 py-2.5">
                      <span className={`rounded border px-2 py-0.5 text-[10px] font-bold tracking-wider ${
                        p.status === "Ready"
                          ? "border-safe/40 bg-safe-soft text-safe"
                          : p.status === "Armed"
                          ? "border-orange/40 bg-orange-soft text-orange"
                          : "border-border bg-hair text-muted"
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
                  <span className="text-fg">{s.name}</span>
                  <span className="font-mono text-muted">{s.pct}%</span>
                </div>
                <div className="h-2 overflow-hidden rounded-full bg-track">
                  <div
                    className={`h-full rounded-full ${s.pct > 70 ? "bg-safe" : s.pct > 55 ? "bg-accent" : "bg-orange"}`}
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
