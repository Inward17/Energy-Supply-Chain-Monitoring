"use client"

import { useEffect, useState } from "react"
import { Crosshair, Anchor, Loader } from "lucide-react"
import { Panel, StatChip } from "../ui"
import { fetchReroute, fetchChokepoints, fetchRefineries, fetchGrades, type ProcurementRow } from "@/lib/api"

type Phase = "idle" | "loading" | "done" | "error"

// Fallback lists while API is loading
const FALLBACK_CHOKEPOINTS = [
  "Strait of Hormuz", "Suez Canal", "Bab-el-Mandeb",
  "Strait of Malacca", "Turkish Straits", "Cape of Good Hope",
]

export function RerouteMatrix() {
  const [chokepoints, setChokepoints] = useState<string[]>(FALLBACK_CHOKEPOINTS)
  const [refineries, setRefineries]   = useState<string[]>([])
  const [grades, setGrades]           = useState<string[]>([])
  const [blocked, setBlocked]         = useState(FALLBACK_CHOKEPOINTS[0])
  const [dest, setDest]               = useState("")
  const [grade, setGrade]             = useState("Any")
  const [mode, setMode]               = useState<"cost" | "speed">("cost")
  const [phase, setPhase]             = useState<Phase>("idle")
  const [pm, setPm]                   = useState<ProcurementRow[]>([])
  const [meta, setMeta]               = useState({ resilience: 0, brent: 0, count: 0 })
  const [error, setError]             = useState("")

  useEffect(() => {
    // Load dropdown options from API
    Promise.all([fetchChokepoints(), fetchRefineries(), fetchGrades()])
      .then(([cps, refs, grs]) => {
        if (cps.length) { setChokepoints(cps); setBlocked(cps[0]) }
        if (refs.length) { setRefineries(refs); setDest(refs[0]) }
        if (grs.length) { setGrades(["Any", ...grs]); setGrade("Any") }
      })
      .catch(() => {
        // keep fallback chokepoints; set a basic refinery
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
        crude_grade:          grade === "Any" ? undefined : grade,
        ranking_mode:         mode,
      })
      setPm(result.procurement_matrix)
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

  return (
    <Panel title="Reroute Matrix" icon={<Crosshair className="h-4 w-4 text-cyan-400" />}>
      <div className="space-y-4 p-4">
        {/* Controls */}
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-5">
          <Field label="Blocked Chokepoint">
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
          <Field label="Crude Grade">
            <select
              value={grade}
              onChange={(e) => { setGrade(e.target.value); setPhase("idle") }}
              className="w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-200 outline-none focus:border-cyan-500"
            >
              {grades.map((g) => <option key={g}>{g}</option>)}
            </select>
          </Field>
          <Field label="Optimise For">
            <select
              value={mode}
              onChange={(e) => { setMode(e.target.value as "cost" | "speed"); setPhase("idle") }}
              className="w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-200 outline-none focus:border-cyan-500"
            >
              <option value="cost">Lowest Landed Cost</option>
              <option value="speed">Fastest Arrival (Speed)</option>
            </select>
          </Field>
          <div className="flex items-end md:col-span-2 lg:col-span-1">
            <button
              type="button"
              onClick={generate}
              disabled={phase === "loading"}
              className="flex w-full items-center justify-center gap-2 rounded-md bg-cyan-500 px-4 py-2 text-sm font-semibold text-slate-950 transition-colors hover:bg-cyan-400 disabled:opacity-60"
            >
              {phase === "loading" ? (
                <><Loader className="h-4 w-4 animate-spin" /> Generating...</>
              ) : "Generate Reroute Matrix"}
            </button>
          </div>
        </div>

        {phase === "error" && (
          <div className="rounded border border-rose-500/40 bg-rose-500/10 p-3 text-sm text-rose-300">
            {error}
          </div>
        )}

        {phase === "done" && pm.length > 0 && (
          <>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
              <StatChip label="Resilience Index" value={meta.resilience.toFixed(2)} accent="text-emerald-400" />
              <StatChip label="Brent Spot"       value={`$${meta.brent.toFixed(2)}`} accent="text-cyan-400" />
              <StatChip label="Viable Sources"   value={String(meta.count)}           accent="text-white" />
            </div>

            <div className="overflow-x-auto rounded-lg border border-slate-800">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-slate-800 bg-slate-950/60 text-left text-[11px] uppercase tracking-wider text-slate-500">
                    <th className="px-4 py-2.5 font-medium">Export Terminal</th>
                    <th className="px-4 py-2.5 font-medium">Country</th>
                    <th className="px-4 py-2.5 font-medium">Crude Grade</th>
                    <th className="px-4 py-2.5 font-medium">Landed Cost</th>
                    <th className="px-4 py-2.5 font-medium">Freight Premium</th>
                    <th className="px-4 py-2.5 font-medium">Lead Time</th>
                  </tr>
                </thead>
                <tbody>
                  {pm.map((r, i) => (
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
                      <td className="px-4 py-2.5 text-slate-400">{r.crude_grade}</td>
                      <td className="px-4 py-2.5 font-mono text-slate-200">${r.landed_cost_usd.toFixed(2)}</td>
                      <td className="px-4 py-2.5 font-mono text-orange-400">+${r.freight_premium.toFixed(2)}</td>
                      <td className="px-4 py-2.5 font-mono text-cyan-400">{r.lead_time_days.toFixed(1)} days</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}
      </div>
    </Panel>
  )
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <label className="mb-1.5 block text-[11px] font-medium uppercase tracking-wider text-slate-400">
        {label}
      </label>
      {children}
    </div>
  )
}
