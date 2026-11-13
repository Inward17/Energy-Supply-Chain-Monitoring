"use client"

import { useEffect, useState } from "react"
import { Loader, ShieldAlert, Activity, ChevronDown } from "lucide-react"
import { Panel } from "../ui"
import { InfoTooltip } from "@/components/ui/info-tooltip"
import {
  fetchWarRoom,
  fetchRefineries,
  fetchGrades,
  type WarRoomResult,
} from "@/lib/api"
import {
  CrudeGradeField,
  OptimiseForField,
  ExcludedCountriesField,
  type RerouteParamsValue,
} from "../shared/reroute-params-form"
import { SprAssumptionsForm, SPR_ASSUMPTIONS_DEFAULTS, type SprAssumptionsValue } from "../shared/spr-assumptions-form"

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
  const [grades, setGrades]     = useState<string[]>(["Any"])
  const [scenario, setScenario] = useState(DEFAULT_SCENARIOS[1])
  const [refinery, setRefinery] = useState("")
  const [phase, setPhase]       = useState<Phase>("idle")
  const [result, setResult]     = useState<WarRoomResult | null>(null)
  const [error, setError]       = useState("")
  const [advancedOpen, setAdvancedOpen] = useState(false)

  // Advanced parameters (default = identical to individual tab defaults → same output if untouched)
  const [rerouteParams, setRerouteParams] = useState<RerouteParamsValue>({ 
    grade: "Any", 
    mode: "cost",
    excludedCountries: ["Russia", "Iran", "Venezuela", "Syria"],
    strictGradeMatch: false,
  })
  const [sprParams, setSprParams]         = useState<SprAssumptionsValue>(SPR_ASSUMPTIONS_DEFAULTS)

  useEffect(() => {
    Promise.all([fetchRefineries(), fetchGrades()])
      .then(([list, grs]) => {
        setRefineries(list)
        if (list.length > 0) setRefinery(list[0])
        if (grs.length > 0) setGrades(["Any", ...grs])
      })
      .catch(() => {
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
    const refineryName = refinery.split(" (")[0]

    try {
      const data = await fetchWarRoom({
        scenario_name:         scenario,
        blocked_chokepoint:    cfg.chokepoint,
        destination_refinery:  refineryName,
        disrupted_volume_mbpd: cfg.volume,
        // Reroute advanced params
        crude_grade:  rerouteParams.grade === "Any" ? undefined : rerouteParams.grade,
        ranking_mode: rerouteParams.mode,
        excluded_countries: rerouteParams.excludedCountries,
        strict_grade_match: rerouteParams.strictGradeMatch,
        // SPR advanced params (percentages — API helper divides by 100)
        gdp_impact_rate_pct: sprParams.gdpRate,
        run_rate_cut_pct:    sprParams.runCut,
        industrial_cut_pct:  sprParams.indCut,
        transport_cut_pct:   sprParams.transCut,
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
      <Panel title="Executive War Room" tone="crit">
        <div className="space-y-4 p-4">
          {/* Core scenario + refinery selectors */}
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
            <div>
              <label className="mb-1.5 block text-[11px] font-medium uppercase tracking-wider text-muted">
                Select Crisis Scenario
              </label>
              <select
                value={scenario}
                onChange={(e) => { setScenario(e.target.value); setPhase("idle") }}
                className="w-full rounded-md border border-border bg-panel-2 px-3 py-2 text-sm text-fg outline-none focus:border-crit"
              >
                {scenarios.map((s) => <option key={s}>{s}</option>)}
              </select>
            </div>
            <div>
              <label className="mb-1.5 block text-[11px] font-medium uppercase tracking-wider text-muted">
                Target Refinery
              </label>
              <select
                value={refinery}
                onChange={(e) => { setRefinery(e.target.value); setPhase("idle") }}
                className="w-full rounded-md border border-border bg-panel-2 px-3 py-2 text-sm text-fg outline-none focus:border-crit"
              >
                {refineries.map((r) => <option key={r}>{r}</option>)}
              </select>
            </div>
          </div>

          {/* Advanced Parameters accordion */}
          <div className="rounded-md border border-hair">
            <button
              type="button"
              onClick={() => setAdvancedOpen(!advancedOpen)}
              className="flex w-full items-center justify-between px-4 py-2.5 text-[11px] font-medium uppercase tracking-wider text-muted hover:text-fg transition-colors"
            >
              <span>Advanced Parameters</span>
              <span className="flex items-center gap-2">
                {(rerouteParams.grade !== "Any" || rerouteParams.mode !== "cost" ||
                  rerouteParams.excludedCountries !== "Russia, Iran, Venezuela, Syria" ||
                  sprParams.gdpRate !== SPR_ASSUMPTIONS_DEFAULTS.gdpRate ||
                  sprParams.runCut !== SPR_ASSUMPTIONS_DEFAULTS.runCut ||
                  sprParams.indCut !== SPR_ASSUMPTIONS_DEFAULTS.indCut ||
                  sprParams.transCut !== SPR_ASSUMPTIONS_DEFAULTS.transCut) && (
                  <span className="rounded-full bg-accent-soft px-1.5 py-0.5 text-[10px] font-bold text-accent">
                    CUSTOMISED
                  </span>
                )}
                <ChevronDown className={`h-4 w-4 transition-transform ${advancedOpen ? "rotate-180" : ""}`} />
              </span>
            </button>

            {advancedOpen && (
              <div className="space-y-4 border-t border-hair px-4 pb-4 pt-3">
                <div>
                  <div className="mb-2 text-[10px] font-bold uppercase tracking-wider text-muted">Procurement Preferences</div>
                  {/* One row: grade, optimise-for, exclusions. The exclusions
                      chip field takes the flexible column since it grows. */}
                  <div className="grid grid-cols-1 items-end gap-3 md:grid-cols-[minmax(180px,1fr)_auto_minmax(220px,1.4fr)]">
                    <CrudeGradeField
                      value={rerouteParams}
                      grades={grades}
                      onChange={(next) => { setRerouteParams(next); setPhase("idle") }}
                    />
                    <OptimiseForField
                      value={rerouteParams}
                      onChange={(next) => { setRerouteParams(next); setPhase("idle") }}
                      compact
                    />
                    <ExcludedCountriesField
                      value={rerouteParams}
                      onChange={(next) => { setRerouteParams(next); setPhase("idle") }}
                    />
                  </div>
                </div>
                <div>
                  <div className="mb-2 text-[10px] font-bold uppercase tracking-wider text-muted">SPR Model Assumptions</div>
                  <SprAssumptionsForm
                    value={sprParams}
                    onChange={(next) => { setSprParams(next); setPhase("idle") }}
                    hideHeader
                  />
                </div>
                </div>
            )}
          </div>

          <button
            id="warroom-simulate-btn"
            type="button"
            onClick={simulate}
            disabled={phase === "loading"}
            className="flex w-full items-center justify-center gap-2 rounded-lg bg-crit px-4 py-3.5 text-base font-bold tracking-wide text-bg shadow-lg shadow-crit/30 transition-colors hover:opacity-90 disabled:opacity-70"
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
        <div className="rounded-lg border border-crit/40 bg-crit-soft p-4 text-sm text-crit">
          <b>Simulation failed:</b> {error}
        </div>
      )}

      {phase === "done" && result?.diagnostic && (
        <div className="rounded-lg border border-warn/30 bg-warn-soft p-5 text-sm">
          <div className="mb-2 flex items-center gap-2 font-semibold text-warn">
            <Activity className="h-4 w-4" /> No viable alternatives found
          </div>
          <div className="mb-4 text-fg">
            {result.diagnostic.message}
          </div>
          <div className="flex flex-wrap gap-2">
            {result.diagnostic.reason === "grade_only_available_from_excluded_countries" && (
              <button
                type="button"
                onClick={() => {
                  const toKeep = rerouteParams.excludedCountries.filter(c => !result.diagnostic!.grade_suppliers.includes(c))
                  const newParams = { ...rerouteParams, excludedCountries: toKeep }
                  setRerouteParams(newParams)
                  setTimeout(() => document.getElementById("warroom-simulate-btn")?.click(), 100)
                }}
                className="rounded bg-warn-soft px-3 py-1.5 font-medium text-warn hover:bg-warn-soft transition-colors"
              >
                Remove conflicts ({result.diagnostic.grade_suppliers.join(", ")})
              </button>
            )}
            {rerouteParams.strictGradeMatch && (
              <button
                type="button"
                onClick={() => {
                  const newParams = { ...rerouteParams, strictGradeMatch: false }
                  setRerouteParams(newParams)
                  setTimeout(() => document.getElementById("warroom-simulate-btn")?.click(), 100)
                }}
                className="rounded bg-track px-3 py-1.5 font-medium text-fg hover:bg-track transition-colors"
              >
                Allow compatible substitute grades
              </button>
            )}
          </div>
        </div>
      )}

      {phase === "done" && result && !result.diagnostic && (
        <div className="space-y-4">
          {/* Section 1: Reroute */}
          <Panel title="Optimal Reroute Strategy" tone="accent">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border text-left text-[11px] uppercase tracking-wider text-muted">
                    <th className="px-4 py-2.5 font-medium">Export Terminal</th>
                    <th className="px-4 py-2.5 font-medium">Crude Grade</th>
                    <th className="px-4 py-2.5 font-medium"><InfoTooltip term="Landed Cost" /></th>
                    <th className="px-4 py-2.5 font-medium">Lead Time</th>
                  </tr>
                </thead>
                <tbody>
                  {result.top_routes.map((r, i) => (
                    <tr
                      key={`${r.terminal}-${r.grade}`}
                      className={`border-b border-hair last:border-0 ${i === 0 ? "bg-row-hi" : ""}`}
                    >
                      <td className="px-4 py-2.5 font-medium text-fg">{r.terminal}</td>
                      <td className="px-4 py-2.5 text-muted">
                        <div className="flex items-center gap-2">
                          {r.grade}
                          {r.match_type === "exact" ? (
                            <span className="rounded bg-safe-soft px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wider text-safe">
                              Exact Match
                            </span>
                          ) : (
                            <div className="group relative flex items-center">
                              <span className="cursor-help rounded bg-warn-soft px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wider text-warn">
                                Substitute
                              </span>
                              <div className="pointer-events-none absolute bottom-full left-1/2 mb-2 w-max -translate-x-1/2 rounded bg-track px-2 py-1 text-xs text-fg opacity-0 transition-opacity group-hover:opacity-100 z-10">
                                {r.match_reason}
                                <div className="absolute left-1/2 top-full -translate-x-1/2 border-4 border-transparent border-t-border" />
                              </div>
                            </div>
                          )}
                        </div>
                      </td>
                      <td className="px-4 py-2.5 font-mono text-fg">{r.landed}</td>
                      <td className="px-4 py-2.5 font-mono text-accent">{r.lead}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Panel>

          {/* Section 2: SPR trajectory KPIs */}
          <Panel title="SPR Trajectory" tone="accent">
            <div className="grid grid-cols-1 gap-4 p-4 sm:grid-cols-3">
              <BigKpi
                label="SPR Survival Days"
                value={spr!.survival_days.toFixed(1)}
                unit="days"
                accent="text-accent"
              />
              <BigKpi
                label="Supply Gap"
                value={spr!.supply_gap_days.toFixed(1)}
                unit={gapSafe ? "days · SAFE" : "days · CRITICAL"}
                accent={gapSafe ? "text-safe" : "text-crit"}
              />
              <BigKpi
                label="GDP Impact"
                value={spr!.gdp_impact}
                unit="of India GDP"
                accent={gapSafe ? "text-safe" : "text-crit"}
              />
            </div>
          </Panel>

          {/* Section 3: Executive brief */}
          <Panel title="Ministry of Petroleum — Executive Brief" tone="accent">
            <div className="p-4">
              <div className="space-y-3 rounded-md border-l-4 border-accent bg-accent-soft p-4 text-sm leading-relaxed text-fg whitespace-pre-wrap">
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
    <div className="rounded-lg border border-border bg-panel-2 p-4 text-center">
      <div className="text-[11px] uppercase tracking-widest text-muted">{label}</div>
      <div className={`mt-2 font-mono text-4xl font-bold ${accent}`}>{value}</div>
      <div className="mt-1 text-xs text-muted">{unit}</div>
    </div>
  )
}

function LoadingSkeleton() {
  return (
    <div className="space-y-4">
      <Panel>
        <div className="space-y-3 p-4">
          <div className="h-4 w-48 animate-pulse rounded bg-track" />
          {[0, 1, 2].map((i) => (
            <div key={i} className="h-8 w-full animate-pulse rounded bg-hair" />
          ))}
        </div>
      </Panel>
      <Panel>
        <div className="grid grid-cols-3 gap-4 p-4">
          {[0, 1, 2].map((i) => (
            <div key={i} className="h-24 animate-pulse rounded-lg bg-hair" />
          ))}
        </div>
      </Panel>
    </div>
  )
}
