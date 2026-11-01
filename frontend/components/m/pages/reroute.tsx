"use client"

import { useEffect, useState } from "react"
import { fetchChokepoints, fetchGrades, fetchRefineries, fetchReroute, type RerouteResult } from "@/lib/api"
import { Bar, ErrorNote, Eyebrow, Panel, Segmented, fmt, riskColor, riskText } from "../ui"

export const DEFAULT_EXCLUDED = ["Russia", "Iran", "Venezuela", "Syria"]

export function useConfig() {
  const [cfg, setCfg] = useState<{ chokepoints: string[]; refineries: string[]; grades: string[] }>({ chokepoints: [], refineries: [], grades: [] })
  useEffect(() => {
    Promise.allSettled([fetchChokepoints(), fetchRefineries(), fetchGrades()]).then(([c, r, g]) =>
      setCfg({
        chokepoints: c.status === "fulfilled" ? c.value : ["Strait of Hormuz"],
        refineries: r.status === "fulfilled" ? r.value : [],
        grades: g.status === "fulfilled" ? g.value : [],
      }),
    )
  }, [])
  return cfg
}

const field = "h-12 w-full rounded-[10px] border border-edge bg-well px-3 text-[14px] text-head lg:h-11"

export function CountryChips({ value, onChange }: { value: string[]; onChange: (v: string[]) => void }) {
  const [draft, setDraft] = useState("")
  const add = () => {
    const c = draft.trim()
    if (c && !value.includes(c)) onChange([...value, c])
    setDraft("")
  }
  return (
    <div className="flex min-h-12 flex-wrap items-center gap-1.5 rounded-[10px] border border-edge bg-well p-1.5 lg:min-h-11">
      {value.map((c) => (
        <button key={c} type="button" onClick={() => onChange(value.filter((x) => x !== c))} aria-label={`Remove ${c}`} className="rounded-md bg-hair px-2 py-1 text-xs text-fg hover:bg-raise">
          {c} ✕
        </button>
      ))}
      <input
        aria-label="Add country to exclude"
        placeholder="Add…"
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); add() } }}
        onBlur={add}
        maxLength={60}
        className="min-w-[60px] flex-1 bg-transparent text-[13px] text-head outline-none placeholder:text-faint"
      />
    </div>
  )
}

export function ReroutePage() {
  const cfg = useConfig()
  const [blocked, setBlocked] = useState("Strait of Hormuz")
  const [refinery, setRefinery] = useState("Jamnagar (India)")
  const [grade, setGrade] = useState("Any")
  const [mode, setMode] = useState<"cost" | "speed">("cost")
  const [excluded, setExcluded] = useState<string[]>(DEFAULT_EXCLUDED)
  const [strict, setStrict] = useState(false)
  const [maxLead, setMaxLead] = useState(90)
  const [more, setMore] = useState(false)
  const [res, setRes] = useState<RerouteResult | null>(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)

  const run = async (over?: Partial<{ excluded: string[]; strict: boolean }>) => {
    setBusy(true)
    setErr(null)
    try {
      setRes(
        await fetchReroute({
          blocked_chokepoint: blocked,
          destination_refinery: refinery || undefined,
          crude_grade: grade === "Any" ? undefined : grade,
          ranking_mode: mode,
          excluded_countries: over?.excluded ?? excluded,
          strict_grade_match: over?.strict ?? strict,
        }),
      )
    } catch {
      setErr("The reroute model did not respond. Check that the backend is running.")
    } finally {
      setBusy(false)
    }
  }

  const rows = (res?.procurement_matrix ?? []).filter((r) => r.lead_time_days <= maxLead)
  const best = rows[0]
  const uniform = rows.length > 2 && rows.every((r) => r.landed_cost_usd === rows[0].landed_cost_usd && r.lead_time_days === rows[0].lead_time_days)

  return (
    <div className="flex flex-col gap-4 lg:gap-5">
      <form onSubmit={(e) => { e.preventDefault(); void run() }} className="panel flex flex-col gap-3.5 rounded-[18px] p-4 lg:p-5">
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          <label className="flex flex-col gap-1.5"><Eyebrow>Blocked chokepoint</Eyebrow>
            <select value={blocked} onChange={(e) => setBlocked(e.target.value)} className={`${field} border-orange bg-orange-soft`}>
              {(cfg.chokepoints.length ? cfg.chokepoints : [blocked]).map((c) => <option key={c}>{c}</option>)}
            </select></label>
          <label className="flex flex-col gap-1.5"><Eyebrow>Destination refinery</Eyebrow>
            <select value={refinery} onChange={(e) => setRefinery(e.target.value)} className={field}>
              {(cfg.refineries.length ? cfg.refineries : [refinery]).map((c) => <option key={c}>{c}</option>)}
            </select></label>
          <label className="flex flex-col gap-1.5"><Eyebrow>Crude grade</Eyebrow>
            <select value={grade} onChange={(e) => setGrade(e.target.value)} className={field}>
              <option>Any</option>
              {cfg.grades.map((c) => <option key={c}>{c}</option>)}
            </select></label>
        </div>
        <div className="grid grid-cols-2 items-end gap-3 lg:grid-cols-[200px_minmax(0,1fr)_220px_160px]">
          <div className="flex flex-col gap-1.5"><Eyebrow>Optimise for</Eyebrow>
            <Segmented label="Optimise for" value={mode} onChange={setMode} options={[{ value: "cost", label: "Cost" }, { value: "speed", label: "Time" }]} />
          </div>
          <button type="button" onClick={() => setMore((v) => !v)} aria-expanded={more} className="h-12 rounded-[10px] border border-edge bg-well px-3 text-left text-[13px] text-muted lg:hidden">
            More · {maxLead} d, {excluded.length} excluded
          </button>
          <div className={`col-span-2 flex-col gap-1.5 lg:col-span-1 lg:flex ${more ? "flex" : "hidden"}`}><Eyebrow>Exclude countries</Eyebrow>
            <CountryChips value={excluded} onChange={setExcluded} />
          </div>
          <label className={`col-span-2 flex-col gap-1.5 lg:col-span-1 lg:flex ${more ? "flex" : "hidden"}`}>
            <span className="eyebrow flex justify-between">Max lead time <span className="text-head">{maxLead} d</span></span>
            <input type="range" min={5} max={90} value={maxLead} onChange={(e) => setMaxLead(Number(e.target.value))} className="h-11 accent-accent" />
          </label>
          <button type="submit" disabled={busy} className="col-span-2 h-12 rounded-[10px] bg-accent text-[15px] font-bold text-[var(--x-06121f)] disabled:opacity-60 lg:col-span-1 lg:h-11">
            {busy ? "Running…" : "Generate"}
          </button>
        </div>
        <label className={`items-center gap-2 text-xs text-muted lg:flex ${more ? "flex" : "hidden"}`}>
          <input type="checkbox" checked={strict} onChange={(e) => setStrict(e.target.checked)} className="h-4 w-4 accent-accent" />
          Exact grade only (no substitutes)
        </label>
      </form>

      {err && <ErrorNote message={err} onRetry={() => void run()} />}

      {res?.diagnostic && (
        <div className="flex flex-col gap-2 rounded-xl border border-warn-boxline bg-warn-box p-4 text-sm text-fg">
          <span>{res.diagnostic.message}</span>
          <div className="flex flex-wrap gap-2">
            {res.diagnostic.reason === "grade_only_available_from_excluded_countries" && (
              <button type="button" className="text-xs font-semibold text-warn" onClick={() => {
                const keep = excluded.filter((c) => !res.diagnostic!.grade_suppliers.includes(c))
                setExcluded(keep); void run({ excluded: keep })
              }}>Allow {res.diagnostic.grade_suppliers.join(", ")} →</button>
            )}
            {strict && <button type="button" className="text-xs font-semibold text-warn" onClick={() => { setStrict(false); void run({ strict: false }) }}>Allow substitutes →</button>}
          </div>
        </div>
      )}

      {!res && !busy && !err && (
        <Panel className="p-6 text-sm text-dim">Choose a chokepoint to close and press Generate to rank alternative supply.</Panel>
      )}

      {res && (
        <>
          <section className="flex flex-wrap gap-4 lg:gap-5">
            {best ? (
              <div className="flex min-w-0 flex-[2_1_420px] flex-col gap-3.5 rounded-[18px] border border-safe-line bg-safe-soft p-5 lg:p-[22px]">
                <span className="eyebrow text-safe">Recommended</span>
                <div className="flex flex-wrap items-end justify-between gap-3">
                  <div className="flex flex-col gap-1">
                    <span className="text-xl font-bold text-head [font-stretch:108%] lg:text-2xl">{best.crude_grade} · {best.country}</span>
                    <span className="text-[13px] text-muted">{best.export_port} → {res.destination_refinery} · avoids {blocked.replace("Strait of ", "")}</span>
                  </div>
                  <span className="text-3xl font-bold text-head [font-stretch:108%] lg:text-4xl">${fmt(best.landed_cost_usd)}<span className="text-[13px] font-normal text-dim"> /bbl landed</span></span>
                </div>
                <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-4">
                  {[["Lead time", `${best.lead_time_days.toFixed(1)} d`], ["Freight", `+$${fmt(best.freight_premium)}`], ["Route risk", fmt(best.risk_score)], ["Match", best.match_type]].map(([k, v]) => (
                    <div key={k} className="flex flex-col gap-1 rounded-[10px] bg-[var(--x-0a1410)] p-2.5">
                      <span className="font-mono text-[10px] uppercase text-dim">{k}</span>
                      <span className={`text-base font-semibold ${k === "Match" && v === "exact" ? "text-safe" : "text-head"}`}>{v}</span>
                    </div>
                  ))}
                </div>
              </div>
            ) : (
              <Panel className="flex-[2_1_420px] p-5 text-sm text-dim">No routes within {maxLead} days — raise the max lead time.</Panel>
            )}
            <Panel className="flex min-w-0 flex-[1_1_260px] flex-col gap-3 p-5 lg:p-[22px]">
              <Eyebrow>Supply resilience</Eyebrow>
              <div className="flex items-baseline gap-1.5">
                <span className="text-[44px] font-bold [font-stretch:108%]" style={{ color: res.resilience_score < 40 ? "var(--x-ff8a8d)" : res.resilience_score < 70 ? "var(--x-f2c14e)" : "var(--x-3fcf8e)" }}>{Math.round(res.resilience_score)}</span>
                <span className="text-[13px] text-dim">/ 100</span>
              </div>
              <Bar value={res.resilience_score / 100} color={res.resilience_score < 40 ? "var(--x-ff5a5f)" : res.resilience_score < 70 ? "var(--x-f2c14e)" : "var(--x-3fcf8e)"} h={8} />
              <span className="text-xs leading-relaxed text-muted">
                {res.resilience_score < 40 ? "Few alternatives clear the risk filter. Diversify contracts before a closure, not after." : "Several alternatives clear the risk filter."}
              </span>
            </Panel>
          </section>

          <Panel className="flex flex-col p-4 lg:p-[22px]">
            <div className="flex items-baseline justify-between pb-3">
              <h2 className="text-[15px] font-bold text-head">Procurement matrix</h2>
              <span className="font-mono text-[11px] text-faint">{rows.length} of {res.procurement_matrix.length} options · by {mode === "cost" ? "cost" : "time"}</span>
            </div>
            {uniform && (
              <p className="mb-3 rounded-lg border border-warn-boxline bg-warn-box px-3 py-2 text-xs text-fg">
                Every option shares one landed cost and lead time — route distances are likely falling back to a default, so ranking reflects risk only.
              </p>
            )}
            {/* Phones: cards */}
            <div className="flex flex-col gap-2.5 lg:hidden">
              {rows.map((r, i) => (
                <div key={`${r.export_port}-${r.crude_grade}`} className={`grid grid-cols-[28px_1fr_auto] items-center gap-2.5 rounded-[14px] border p-3.5 ${r.risk_score >= 0.4 ? "border-orange-line" : i === 0 ? "border-safe-line" : "border-line"} bg-panel`}>
                  <span className="font-mono text-[11px] text-faint">{String(i + 1).padStart(2, "0")}</span>
                  <span className="flex flex-col gap-0.5"><span className="text-sm text-head">{r.crude_grade} · {r.country}</span>
                    <span className="font-mono text-[11px]" style={{ color: riskText(r.risk_score) === "var(--x-aeb8c5)" ? "var(--x-94a0af)" : riskText(r.risk_score) }}>{r.lead_time_days.toFixed(1)} d · risk {r.risk_score.toFixed(2)}</span></span>
                  <span className="font-mono text-sm text-head">${fmt(r.landed_cost_usd)}</span>
                </div>
              ))}
            </div>
            {/* Desktop: table */}
            <div className="hidden overflow-x-auto lg:block">
              <table className="w-full min-w-[760px] border-collapse text-[13px]">
                <thead>
                  <tr className="text-left font-mono text-[10px] tracking-[0.1em] text-faint">
                    {["#", "Grade · origin", "Port", "Landed", "Lead", "Route risk", "Score"].map((h, i) => (
                      <th key={h} scope="col" className={`px-2.5 py-2 font-medium uppercase ${i >= 3 && i !== 5 ? "text-right" : ""}`}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r, i) => (
                    <tr key={`${r.export_port}-${r.crude_grade}`} className={i === 0 ? "bg-safe-soft" : "border-t border-hair"}>
                      <td className={`px-2.5 py-3 font-mono ${i === 0 ? "text-safe" : "text-faint"}`}>{String(i + 1).padStart(2, "0")}</td>
                      <td className={`px-2.5 py-3 ${i === 0 ? "font-semibold text-head" : "text-fg"}`}>{r.crude_grade} · {r.country}{r.match_type !== "exact" && <span className="ml-2 font-mono text-[10px] text-warn">{r.match_type}</span>}</td>
                      <td className="px-2.5 py-3 text-muted">{r.export_port}</td>
                      <td className="px-2.5 py-3 text-right font-mono">${fmt(r.landed_cost_usd)}</td>
                      <td className="px-2.5 py-3 text-right font-mono">{r.lead_time_days.toFixed(1)} d</td>
                      <td className="px-2.5 py-3"><span className="flex items-center gap-2"><span className="w-20"><Bar value={r.risk_score} color={riskColor(r.risk_score)} /></span><span className="font-mono" style={{ color: riskText(r.risk_score) }}>{dot(r.risk_score)}</span></span></td>
                      <td className="px-2.5 py-3 text-right font-mono">{fmt(r.composite_score)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Panel>
        </>
      )}
    </div>
  )
}

const dot = (v: number) => v.toFixed(2).replace(/^0/, "")
