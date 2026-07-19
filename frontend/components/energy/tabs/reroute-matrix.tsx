"use client"

import { useEffect, useState } from "react"
import { Anchor, Loader, Filter, Activity } from "lucide-react"
import { InfoTooltip } from "@/components/ui/info-tooltip"
import { Panel, StatChip } from "../ui"
import { fetchReroute, fetchChokepoints, fetchRefineries, fetchGrades, type ProcurementRow, type Diagnostic } from "@/lib/api"
import {
  CrudeGradeField,
  OptimiseForField,
  ExcludedCountriesField,
  type RerouteParamsValue,
} from "../shared/reroute-params-form"

type Phase = "idle" | "loading" | "done" | "error"

// Fallback lists while API is loading
const FALLBACK_CHOKEPOINTS = [
  "Strait of Hormuz", "Suez Canal", "Bab-el-Mandeb",
  "Strait of Malacca", "Turkish Straits", "Cape of Good Hope",
]

export function RerouteMatrix() {
  const [chokepoints, setChokepoints] = useState<string[]>(FALLBACK_CHOKEPOINTS)
  const [refineries, setRefineries]   = useState<string[]>([])
  const [grades, setGrades]           = useState<string[]>(["Any"])
  const [blocked, setBlocked]         = useState(FALLBACK_CHOKEPOINTS[0])
  const [dest, setDest]               = useState("")
  const [params, setParams]           = useState<RerouteParamsValue>({ grade: "Any", mode: "cost", excludedCountries: ["Russia", "Iran", "Venezuela", "Syria"], strictGradeMatch: false })
  const [maxLeadTime, setMaxLeadTime] = useState<number>(90)
  const [phase, setPhase]             = useState<Phase>("idle")
  const [pm, setPm]                   = useState<ProcurementRow[]>([])
  const [diagnostic, setDiagnostic]   = useState<Diagnostic | null>(null)
  const [meta, setMeta]               = useState({ resilience: 0, brent: 0, count: 0 })
  const [error, setError]             = useState("")

  useEffect(() => {
    Promise.all([fetchChokepoints(), fetchRefineries(), fetchGrades()])
      .then(([cps, refs, grs]) => {
        if (cps.length) { setChokepoints(cps); setBlocked(cps[0]) }
        if (refs.length) { setRefineries(refs); setDest(refs[0]) }
        if (grs.length) { setGrades(["Any", ...grs]) }
      })
      .catch(() => {
        setRefineries(["Jamnagar (India)"])
        setDest("Jamnagar (India)")
        setGrades(["Any", "Arab Light", "Brent"])
      })
  }, [])

  async function generate() {
    setPhase("loading")
    setError("")
    try {
      const result = await fetchReroute({
        blocked_chokepoint:   blocked,
        destination_refinery: dest.split(" (")[0],
        crude_grade:          params.grade === "Any" ? undefined : params.grade,
        ranking_mode:         params.mode,
        excluded_countries:   params.excludedCountries,
        strict_grade_match:   params.strictGradeMatch,
      })
      setPm(result.procurement_matrix)
      setDiagnostic(result.diagnostic || null)
      setMeta({
        resilience: result.resilience_score,
        brent:      result.current_brent_usd,
        count:      result.procurement_matrix.length,
      })
      setPhase("done")
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error")
      setPhase("error")
    }
  }

  // Client-side max lead-time filter
  const filteredPm = pm.filter((r) => r.lead_time_days <= maxLeadTime)

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col gap-4">
        <Panel title="Reroute Matrix" tone="accent">
          <div className="space-y-4 p-4">
        {/* Row 1: what is blocked, where it must land, which grade. */}
        <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
          <Field label={<InfoTooltip term="Chokepoint" label="Blocked Chokepoint" />}>
            <select
              value={blocked}
              onChange={(e) => { setBlocked(e.target.value); setPhase("idle") }}
              className="w-full rounded-md border border-border bg-panel-2 px-3 py-2 text-sm text-fg outline-none focus:border-accent"
            >
              {chokepoints.map((c) => <option key={c}>{c}</option>)}
            </select>
          </Field>
          <Field label="Destination Refinery">
            <select
              value={dest}
              onChange={(e) => { setDest(e.target.value); setPhase("idle") }}
              className="w-full rounded-md border border-border bg-panel-2 px-3 py-2 text-sm text-fg outline-none focus:border-accent"
            >
              {refineries.map((r) => <option key={r}>{r}</option>)}
            </select>
          </Field>
          <CrudeGradeField
            value={params}
            grades={grades}
            onChange={(next) => { setParams(next); setPhase("idle") }}
          />
        </div>

        {/* Row 2: constraints and the action. Exclusions take the flexible
            column since its chips grow; the rest size to their content. */}
        <div className="grid grid-cols-1 items-end gap-3 md:grid-cols-[auto_minmax(200px,1fr)_190px_auto]">
          <OptimiseForField
            value={params}
            onChange={(next) => { setParams(next); setPhase("idle") }}
          />
          <ExcludedCountriesField
            value={params}
            onChange={(next) => { setParams(next); setPhase("idle") }}
          />

          <div>
            <div className="mb-1.5 flex items-center justify-between text-[11px] font-medium uppercase tracking-wider text-muted">
              <span className="flex items-center gap-1"><Filter className="h-3 w-3" /> Max Lead Time</span>
              <span className="font-mono text-accent">{maxLeadTime}d</span>
            </div>
            <input
              type="range" min={5} max={90} step={1} value={maxLeadTime}
              onChange={(e) => setMaxLeadTime(Number(e.target.value))}
              style={{ background: `linear-gradient(to right, var(--t-accent) 0%, var(--t-accent) ${((maxLeadTime - 5) / 85) * 100}%, var(--t-track) ${((maxLeadTime - 5) / 85) * 100}%, var(--t-track) 100%)` }}
              className="slider-slim mb-2.5 w-full cursor-pointer"
            />
          </div>

          <button
            id="reroute-generate-btn"
            type="button"
            onClick={generate}
            disabled={phase === "loading"}
            className="flex h-[38px] items-center justify-center gap-2 rounded-md bg-accent px-5 text-sm font-semibold text-bg transition-colors hover:opacity-90 disabled:opacity-60"
          >
            {phase === "loading" ? (
              <><Loader className="h-4 w-4 animate-spin" /> Generating...</>
            ) : "Generate"}
          </button>
        </div>

        {phase === "error" && (
          <div className="rounded border border-crit/40 bg-crit-soft p-3 text-sm text-crit">
            {error}
          </div>
        )}

        {phase === "done" && diagnostic && (
          <div className="rounded-lg border border-warn/30 bg-warn-soft p-5 text-sm">
            <div className="mb-2 flex items-center gap-2 font-semibold text-warn">
              <Activity className="h-4 w-4" /> No viable alternatives found
            </div>
            <div className="mb-4 text-fg">
              {diagnostic.message}
            </div>
            <div className="flex flex-wrap gap-2">
              {diagnostic.reason === "grade_only_available_from_excluded_countries" && (
                <button
                  type="button"
                  onClick={() => {
                    const toKeep = params.excludedCountries.filter(c => !diagnostic.grade_suppliers.includes(c))
                    const newParams = { ...params, excludedCountries: toKeep }
                    setParams(newParams)
                    // Auto-trigger using the next state
                    setTimeout(() => document.getElementById("reroute-generate-btn")?.click(), 100)
                  }}
                  className="rounded bg-warn-soft px-3 py-1.5 font-medium text-warn hover:bg-warn-soft transition-colors"
                >
                  Remove conflicts ({diagnostic.grade_suppliers.join(", ")})
                </button>
              )}
              {params.strictGradeMatch && (
                <button
                  type="button"
                  onClick={() => {
                    const newParams = { ...params, strictGradeMatch: false }
                    setParams(newParams)
                    setTimeout(() => document.getElementById("reroute-generate-btn")?.click(), 100)
                  }}
                  className="rounded bg-track px-3 py-1.5 font-medium text-fg hover:bg-track transition-colors"
                >
                  Allow compatible substitute grades
                </button>
              )}
            </div>
          </div>
        )}

        {phase === "done" && pm.length > 0 && !diagnostic && (
          <>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
              <StatChip label={<InfoTooltip term="Resilience Index" />} value={meta.resilience.toFixed(2)} accent="text-safe" />
              <StatChip label="Brent Spot"     value={`$${meta.brent.toFixed(2)}`} accent="text-accent" />
              <StatChip label="Viable Sources" value={String(filteredPm.length)} accent="text-head" />
            </div>

            {maxLeadTime < 90 && filteredPm.length < pm.length && (
              <div className="text-[11px] text-muted">
                Showing {filteredPm.length} of {pm.length} sources — {pm.length - filteredPm.length} filtered by max lead time ({maxLeadTime} days)
              </div>
            )}

            <div className="overflow-x-auto rounded-lg border border-border">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border bg-panel-2 text-left text-[11px] uppercase tracking-wider text-muted">
                    <th className="px-4 py-2.5 font-medium">Export Terminal</th>
                    <th className="px-4 py-2.5 font-medium">Country</th>
                    <th className="px-4 py-2.5 font-medium">Crude Grade</th>
                    <th className="px-4 py-2.5 font-medium"><InfoTooltip term="Landed Cost" /></th>
                    <th className="px-4 py-2.5 font-medium"><InfoTooltip term="Freight Premium" /></th>
                    <th className="px-4 py-2.5 font-medium">Lead Time</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredPm.map((r, i) => (
                    <tr
                      key={`${r.export_port}-${i}`}
                      className={`border-b border-hair last:border-0 ${i === 0 ? "bg-row-hi" : ""}`}
                    >
                      <td className="px-4 py-2.5 font-medium text-fg">
                        <span className="flex items-center gap-2">
                          {i === 0 && <Anchor className="h-3.5 w-3.5 text-safe" />}
                          {r.export_port}
                          {i === 0 && (
                            <span className="rounded bg-safe-soft px-1.5 py-0.5 text-[10px] font-bold tracking-wider text-safe">
                              TOP PICK
                            </span>
                          )}
                        </span>
                      </td>
                      <td className="px-4 py-2.5 text-muted">{r.country}</td>
                      <td className="px-4 py-2.5 text-muted">
                        <div className="flex items-center gap-2">
                          {r.crude_grade}
                          {r.match_type === "exact" && (
                            <span className="rounded bg-safe-soft px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wider text-safe">
                              Exact Match
                            </span>
                          )}
                          {r.match_type === "substitute" && (
                            <div className="group relative flex items-center">
                              <span className="cursor-help rounded bg-warn-soft px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wider text-warn">
                                Substitute
                              </span>
                              <div className="z-10 pointer-events-none absolute bottom-full left-1/2 mb-2 w-max max-w-xs whitespace-normal text-center -translate-x-1/2 rounded bg-track px-2 py-1 text-xs text-fg opacity-0 transition-opacity group-hover:opacity-100">
                                {r.match_reason}
                                <div className="absolute left-1/2 top-full -translate-x-1/2 border-4 border-transparent border-t-border" />
                              </div>
                            </div>
                          )}
                          {r.match_type === "blend" && (
                            <div className="group relative flex items-center">
                              <span className="cursor-help rounded bg-accent-soft px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wider text-accent">
                                Modeled Blend
                              </span>
                              <div className="z-10 pointer-events-none absolute bottom-full left-1/2 mb-2 w-max max-w-xs whitespace-normal text-center -translate-x-1/2 rounded bg-track px-2 py-1 text-xs text-fg opacity-0 transition-opacity group-hover:opacity-100">
                                {r.match_reason}
                                <div className="absolute left-1/2 top-full -translate-x-1/2 border-4 border-transparent border-t-border" />
                              </div>
                            </div>
                          )}
                        </div>
                      </td>
                      <td className="px-4 py-2.5 font-mono text-fg">${r.landed_cost_usd.toFixed(2)}</td>
                      <td className="px-4 py-2.5 font-mono text-orange">+${r.freight_premium.toFixed(2)}</td>
                      <td className="px-4 py-2.5 font-mono text-accent">{r.lead_time_days.toFixed(1)} days</td>
                    </tr>
                  ))}
                  {filteredPm.length === 0 && phase === "done" && (
                    <tr>
                      <td colSpan={6} className="px-4 py-6 text-center text-sm text-muted">
                        No routes within {maxLeadTime}-day lead time — try increasing the filter.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
            </>
          )}
        </div>
      </Panel>
      </div>
    </div>
  )
}

function Field({ label, children }: { label: React.ReactNode; children: React.ReactNode }) {
  return (
    <div>
      <label className="mb-1.5 block text-[11px] font-medium uppercase tracking-wider text-muted">
        {label}
      </label>
      {children}
    </div>
  )
}
