"use client"

import { useEffect, useState } from "react"
import { Swords, Loader, ShieldAlert, Crosshair, Droplet, Activity } from "lucide-react"
import { Panel } from "../ui"
import {
  fetchWarRoom,
  fetchChokepoints,
  fetchRefineries,
  type WarRoomResult,
} from "@/lib/api"

// Scenario map: display label -> { chokepoint, disrupted_volume_mbpd }
const SCENARIOS: Record<string, { chokepoint: string; volume: number }> = {
  "Scenario A: Hormuz Mine Closure":       { chokepoint: "Strait of Hormuz", volume: 2.5 },
  "Scenario B: Suez Canal Drone Strikes":  { chokepoint: "Suez Canal",        volume: 1.2 },
  "Scenario C: Black Sea Naval Blockade":  { chokepoint: "Turkish Straits",   volume: 0.8 },
  "Scenario D: Malacca Piracy Surge":      { chokepoint: "Strait of Malacca", volume: 0.8 },
}

const DEFAULT_SCENARIOS = Object.keys(SCENARIOS)

type Phase = "idle" | "loading" | "done" | "error"

export function WarRoom() {
  const [scenarios]             = useState(DEFAULT_SCENARIOS)
  const [refineries, setRefineries] = useState<string[]>([])
  const [scenario, setScenario] = useState(DEFAULT_SCENARIOS[1])
  const [refinery, setRefinery] = useState("")
  const [phase, setPhase]       = useState<Phase>("idle")
  const [result, setResult]     = useState<WarRoomResult | null>(null)
  const [error, setError]       = useState("")

  // Load refinery list from API on mount
  useEffect(() => {
    fetchRefineries()
      .then((list) => {
        setRefineries(list)
        if (list.length > 0) setRefinery(list[0])
      })
      .catch(() => {
        // fallback
        const fallback = ["Jamnagar (India)", "Rotterdam (Netherlands)", "Ulsan (South Korea)"]
        setRefineries(fallback)
        setRefinery(fallback[0])
      })
  }, [])

  async function simulate() {
    setPhase("loading")
    setError("")
    setResult(null)

    const cfg = SCENARIOS[scenario]
    const refineryName = refinery.split(" (")[0]  // strip " (Country)" suffix

    try {
      const data = await fetchWarRoom({
        scenario_name:          scenario,
        blocked_chokepoint:     cfg.chokepoint,
        destination_refinery:   refineryName,
        disrupted_volume_mbpd:  cfg.volume,
      })
      setResult(data)
      setPhase("done")
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error")
      setPhase("error")
    }
  }

  const spr = result?.spr_trajectory
  const gapSafe = (spr?.supply_gap_days ?? 0) <= 0

  return (
    <div className="space-y-4">
      <Panel title="Executive War Room" icon={<Swords className="h-4 w-4 text-rose-500" />}>
        <div className="space-y-4 p-4">
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
            <div>
              <label className="mb-1.5 block text-[11px] font-medium uppercase tracking-wider text-slate-400">
                Select Crisis Scenario
              </label>
              <select
                value={scenario}
                onChange={(e) => { setScenario(e.target.value); setPhase("idle") }}
                className="w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-200 outline-none focus:border-rose-500"
              >
                {scenarios.map((s) => <option key={s}>{s}</option>)}
              </select>
            </div>
            <div>
              <label className="mb-1.5 block text-[11px] font-medium uppercase tracking-wider text-slate-400">
                Target Refinery
              </label>
              <select
                value={refinery}
                onChange={(e) => { setRefinery(e.target.value); setPhase("idle") }}
                className="w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-200 outline-none focus:border-rose-500"
              >
                {refineries.map((r) => <option key={r}>{r}</option>)}
              </select>
            </div>
          </div>

          <button
            type="button"
            onClick={simulate}
            disabled={phase === "loading"}
            className="flex w-full items-center justify-center gap-2 rounded-lg bg-rose-600 px-4 py-3.5 text-base font-bold tracking-wide text-white shadow-lg shadow-rose-900/40 transition-colors hover:bg-rose-500 disabled:opacity-70"
          >
            {phase === "loading" ? (
              <><Loader className="h-5 w-5 animate-spin" /> RUNNING SIMULATION...</>
            ) : (
              <><ShieldAlert className="h-5 w-5" /> SIMULATE SCENARIO</>
            )}
          </button>
        </div>
      </Panel>

      {phase === "loading" && <LoadingSkeleton />}

      {phase === "error" && (
        <div className="rounded-lg border border-rose-500/40 bg-rose-500/10 p-4 text-sm text-rose-300">
          <b>Simulation failed:</b> {error}
        </div>
      )}

      {phase === "done" && result && (
        <div className="space-y-4">
          {/* Section 1: Reroute */}
          <Panel title="Optimal Reroute Strategy" icon={<Crosshair className="h-4 w-4 text-cyan-400" />}>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-slate-800 text-left text-[11px] uppercase tracking-wider text-slate-500">
                    <th className="px-4 py-2.5 font-medium">Export Terminal</th>
                    <th className="px-4 py-2.5 font-medium">Crude Grade</th>
                    <th className="px-4 py-2.5 font-medium">Landed Cost</th>
                    <th className="px-4 py-2.5 font-medium">Lead Time</th>
                  </tr>
                </thead>
                <tbody>
                  {result.top_routes.map((r, i) => (
                    <tr
                      key={r.terminal}
                      className={`border-b border-slate-800/60 last:border-0 ${i === 0 ? "bg-emerald-500/10" : ""}`}
                    >
                      <td className="px-4 py-2.5 font-medium text-slate-200">{r.terminal}</td>
                      <td className="px-4 py-2.5 text-slate-400">{r.grade}</td>
                      <td className="px-4 py-2.5 font-mono text-slate-200">{r.landed}</td>
                      <td className="px-4 py-2.5 font-mono text-cyan-400">{r.lead}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Panel>

          {/* Section 2: SPR trajectory KPIs */}
          <Panel title="SPR Trajectory" icon={<Droplet className="h-4 w-4 text-cyan-400" />}>
            <div className="grid grid-cols-1 gap-4 p-4 sm:grid-cols-3">
              <BigKpi
                label="SPR Survival Days"
                value={spr!.survival_days.toFixed(1)}
                unit="days"
                accent="text-cyan-400"
              />
              <BigKpi
                label="Supply Gap"
                value={spr!.supply_gap_days.toFixed(1)}
                unit={gapSafe ? "days · SAFE" : "days · CRITICAL"}
                accent={gapSafe ? "text-emerald-400" : "text-rose-500"}
              />
              <BigKpi
                label="GDP Impact"
                value={spr!.gdp_impact}
                unit="%"
                accent={gapSafe ? "text-emerald-400" : "text-rose-400"}
              />
            </div>
          </Panel>

          {/* Section 3: Executive brief */}
          <Panel title="Ministry of Petroleum — Executive Brief" icon={<Activity className="h-4 w-4 text-cyan-400" />}>
            <div className="p-4">
              <div className="space-y-3 rounded-md border-l-4 border-blue-500 bg-blue-900/20 p-4 text-sm leading-relaxed text-slate-300 whitespace-pre-wrap">
                {result.executive_brief}
              </div>
            </div>
          </Panel>
        </div>
      )}
    </div>
  )
}

function BigKpi({ label, value, unit, accent }: { label: string; value: string; unit: string; accent: string }) {
  return (
    <div className="rounded-lg border border-slate-800 bg-slate-950/60 p-4 text-center">
      <p className="text-[11px] uppercase tracking-widest text-slate-500">{label}</p>
      <p className={`mt-2 font-mono text-4xl font-bold ${accent}`}>{value}</p>
      <p className="mt-1 text-xs text-slate-500">{unit}</p>
    </div>
  )
}

function LoadingSkeleton() {
  return (
    <div className="space-y-4">
      <Panel>
        <div className="space-y-3 p-4">
          <div className="h-4 w-48 animate-pulse rounded bg-slate-800" />
          {[0, 1, 2].map((i) => (
            <div key={i} className="h-8 w-full animate-pulse rounded bg-slate-800/70" />
          ))}
        </div>
      </Panel>
      <Panel>
        <div className="grid grid-cols-3 gap-4 p-4">
          {[0, 1, 2].map((i) => (
            <div key={i} className="h-24 animate-pulse rounded-lg bg-slate-800/70" />
          ))}
        </div>
      </Panel>
    </div>
  )
}
