"use client"

import { useEffect, useState } from "react"
import { Crosshair, Anchor, Loader, Filter, Shield, Activity } from "lucide-react"
import { InfoTooltip } from "@/components/ui/info-tooltip"
import { Panel, StatChip } from "../ui"
import { fetchReroute, fetchChokepoints, fetchRefineries, fetchGrades, fetchProducerMatrix, type ProcurementRow, type Diagnostic, type ChokepointRisk } from "@/lib/api"
import { RerouteParamsForm, type RerouteParamsValue } from "../shared/reroute-params-form"

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
  const [producers, setProducers]     = useState<ChokepointRisk[]>([])
  const [diagnostic, setDiagnostic]   = useState<Diagnostic | null>(null)
  const [meta, setMeta]               = useState({ resilience: 0, brent: 0, count: 0 })
  const [error, setError]             = useState("")

  useEffect(() => {
    Promise.all([fetchChokepoints(), fetchRefineries(), fetchGrades(), fetchProducerMatrix()])
      .then(([cps, refs, grs, prods]) => {
        if (cps.length) { setChokepoints(cps); setBlocked(cps[0]) }
        if (refs.length) { setRefineries(refs); setDest(refs[0]) }
        if (grs.length) { setGrades(["Any", ...grs]) }
        if (prods) { setProducers(prods) }
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
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-4">
      <div className="flex flex-col gap-4 lg:col-span-3">
        <Panel title="Reroute Matrix" icon={<Crosshair className="h-4 w-4 text-cyan-400" />}>
          <div className="space-y-4 p-4">
        {/* Row 1: Chokepoint + Destination */}
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
          <Field label={<InfoTooltip term="Chokepoint" label="Blocked Chokepoint" />}>
            <select
              value={blocked}
              onChange={(e) => { setBlocked(e.target.value); setPhase("idle") }}
              className="w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-200 outline-none focus:border-cyan-500"
            >
              {chokepoints.map((c) => <option key={c}>{c}</option>)}
            </select>
          </Field>
          <Field label="Destination Refinery">
            <select
              value={dest}
              onChange={(e) => { setDest(e.target.value); setPhase("idle") }}
              className="w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-200 outline-none focus:border-cyan-500"
            >
              {refineries.map((r) => <option key={r}>{r}</option>)}
            </select>
          </Field>
        </div>

        {/* Row 2: Shared RerouteParamsForm (Crude Grade + Optimise For) */}
        <RerouteParamsForm
          value={params}
          grades={grades}
          onChange={(next) => { setParams(next); setPhase("idle") }}
        />

        {/* Row 3: Filters row */}
        <div className="flex flex-wrap items-end gap-4">
          {/* Max lead-time filter */}
          <div className="flex-1 min-w-[180px]">
            <div className="mb-1.5 flex items-center justify-between text-[11px] font-medium uppercase tracking-wider text-slate-400">
              <span className="flex items-center gap-1"><Filter className="h-3 w-3" /> Max Lead Time</span>
              <span className="font-mono text-cyan-400">{maxLeadTime} days</span>
            </div>
            <input
              type="range" min={5} max={90} step={1} value={maxLeadTime}
              onChange={(e) => setMaxLeadTime(Number(e.target.value))}
              className="h-1.5 w-full cursor-pointer appearance-none rounded-full bg-slate-700 accent-cyan-500"
            />
          </div>

          {/* Generate button */}
          <button
            id="reroute-generate-btn"
            type="button"
            onClick={generate}
            disabled={phase === "loading"}
            className="flex items-center justify-center gap-2 rounded-md bg-cyan-500 px-4 py-2 text-sm font-semibold text-slate-950 transition-colors hover:bg-cyan-400 disabled:opacity-60"
          >
            {phase === "loading" ? (
              <><Loader className="h-4 w-4 animate-spin" /> Generating...</>
            ) : "Generate"}
          </button>
        </div>

        {phase === "error" && (
          <div className="rounded border border-rose-500/40 bg-rose-500/10 p-3 text-sm text-rose-300">
            {error}
          </div>
        )}

        {phase === "done" && diagnostic && (
          <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 p-5 text-sm">
            <div className="mb-2 flex items-center gap-2 font-semibold text-amber-400">
              <Activity className="h-4 w-4" /> No viable alternatives found
            </div>
            <div className="mb-4 text-slate-300">
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
                  className="rounded bg-amber-500/20 px-3 py-1.5 font-medium text-amber-300 hover:bg-amber-500/30 transition-colors"
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
                  className="rounded bg-slate-700/50 px-3 py-1.5 font-medium text-slate-200 hover:bg-slate-700 transition-colors"
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
              <StatChip label={<InfoTooltip term="Resilience Index" />} value={meta.resilience.toFixed(2)} accent="text-emerald-400" />
              <StatChip label="Brent Spot"     value={`$${meta.brent.toFixed(2)}`} accent="text-cyan-400" />
              <StatChip label="Viable Sources" value={String(filteredPm.length)} accent="text-white" />
            </div>

            {maxLeadTime < 90 && filteredPm.length < pm.length && (
              <div className="text-[11px] text-slate-500">
                Showing {filteredPm.length} of {pm.length} sources — {pm.length - filteredPm.length} filtered by max lead time ({maxLeadTime} days)
              </div>
            )}

            <div className="overflow-x-auto rounded-lg border border-slate-800">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-slate-800 bg-slate-950/60 text-left text-[11px] uppercase tracking-wider text-slate-500">
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
                      className={`border-b border-slate-800/60 last:border-0 ${i === 0 ? "bg-emerald-500/10" : ""}`}
                    >
                      <td className="px-4 py-2.5 font-medium text-slate-200">
                        <span className="flex items-center gap-2">
                          {i === 0 && <Anchor className="h-3.5 w-3.5 text-emerald-400" />}
                          {r.export_port}
                          {i === 0 && (
                            <span className="rounded bg-emerald-500/20 px-1.5 py-0.5 text-[10px] font-bold tracking-wider text-emerald-400">
                              TOP PICK
                            </span>
                          )}
                        </span>
                      </td>
                      <td className="px-4 py-2.5 text-slate-400">{r.country}</td>
                      <td className="px-4 py-2.5 text-slate-400">
                        <div className="flex items-center gap-2">
                          {r.crude_grade}
                          {r.match_type === "exact" ? (
                            <span className="rounded bg-emerald-500/20 px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wider text-emerald-400">
                              Exact Match
                            </span>
                          ) : (
                            <div className="group relative flex items-center">
                              <span className="cursor-help rounded bg-amber-500/20 px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wider text-amber-400">
                                Substitute
                              </span>
                              <div className="pointer-events-none absolute bottom-full left-1/2 mb-2 w-max -translate-x-1/2 rounded bg-slate-800 px-2 py-1 text-xs text-slate-200 opacity-0 transition-opacity group-hover:opacity-100">
                                {r.match_reason}
                                <div className="absolute left-1/2 top-full -translate-x-1/2 border-4 border-transparent border-t-slate-800" />
                              </div>
                            </div>
                          )}
                        </div>
                      </td>
                      <td className="px-4 py-2.5 font-mono text-slate-200">${r.landed_cost_usd.toFixed(2)}</td>
                      <td className="px-4 py-2.5 font-mono text-orange-400">+${r.freight_premium.toFixed(2)}</td>
                      <td className="px-4 py-2.5 font-mono text-cyan-400">{r.lead_time_days.toFixed(1)} days</td>
                    </tr>
                  ))}
                  {filteredPm.length === 0 && phase === "done" && (
                    <tr>
                      <td colSpan={6} className="px-4 py-6 text-center text-sm text-slate-500">
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

      <div className="flex flex-col gap-4 lg:col-span-1">
        <Panel title="Producer Risk Matrix" icon={<Shield className="h-4 w-4 text-rose-400" />}>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-800 text-left text-[11px] uppercase tracking-wider text-slate-500">
                  <th className="px-4 py-2.5 font-medium">Producer</th>
                  <th className="px-4 py-2.5 font-medium">Risk Score</th>
                </tr>
              </thead>
              <tbody>
                {producers.map((p) => (
                  <tr key={p.name} className="border-b border-slate-800/60 last:border-0">
                    <td className="px-4 py-2.5 font-medium text-slate-200">{p.name}</td>
                    <td className="px-4 py-2.5">
                      <div className="flex items-center gap-2">
                        <div className="h-1.5 w-12 overflow-hidden rounded-full bg-slate-800">
                          <div
                            className={`h-full rounded-full ${p.risk_score > 0.6 ? "bg-rose-500" : p.risk_score > 0.4 ? "bg-orange-400" : "bg-emerald-400"
                              }`}
                            style={{ width: `${p.risk_score * 100}%` }}
                          />
                        </div>
                        <span className="font-mono text-xs text-slate-300">{p.risk_score.toFixed(2)}</span>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Panel>
      </div>
    </div>
  )
}

function Field({ label, children }: { label: React.ReactNode; children: React.ReactNode }) {
  return (
    <div>
      <label className="mb-1.5 block text-[11px] font-medium uppercase tracking-wider text-slate-400">
        {label}
      </label>
      {children}
    </div>
  )
}
