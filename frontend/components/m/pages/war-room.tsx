"use client"

import { useState } from "react"
import { fetchReroute, fetchSpr, fetchWarRoom, type ProcurementRow, type RerouteResult, type SprResult, type WarRoomResult } from "@/lib/api"
import { useData } from "../data"
import { ErrorNote, Eyebrow, Panel, Segmented, fmt } from "../ui"
import { CountryChips, DEFAULT_EXCLUDED, useConfig } from "./reroute"

// Same scenario definitions as the original War Room.
const SCENARIOS = [
  { id: "A", name: "Scenario A: Hormuz Mine Closure", short: "Hormuz mine closure", chokepoint: "Strait of Hormuz", volume: 2.5 },
  { id: "B", name: "Scenario B: Suez Canal Drone Strikes", short: "Suez Canal drone strikes", chokepoint: "Suez Canal", volume: 1.2 },
  { id: "C", name: "Scenario C: Black Sea Naval Blockade", short: "Black Sea naval blockade", chokepoint: "Turkish Straits", volume: 0.8 },
  { id: "D", name: "Scenario D: Malacca Piracy Surge", short: "Malacca piracy surge", chokepoint: "Strait of Malacca", volume: 0.8 },
]

export function WarRoomPage() {
  const { chokepoints } = useData()
  const cfg = useConfig()
  const [sid, setSid] = useState("A")
  const [refinery, setRefinery] = useState("Jamnagar (India)")
  const [mode, setMode] = useState<"cost" | "speed">("cost")
  const [excluded, setExcluded] = useState<string[]>(DEFAULT_EXCLUDED)
  const [levers, setLevers] = useState({ run: 15, ind: 8, trans: 10 })
  const [edit, setEdit] = useState(false)
  const [facts, setFacts] = useState<{ reroute: RerouteResult; spr: SprResult; top?: ProcurementRow } | null>(null)
  const [ai, setAi] = useState<WarRoomResult | null>(null)
  const [aiState, setAiState] = useState<"idle" | "pending" | "done" | "failed">("idle")
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [copied, setCopied] = useState(false)
  const sc = SCENARIOS.find((s) => s.id === sid)!

  const simulate = async () => {
    setBusy(true)
    setErr(null)
    setFacts(null)
    setAi(null)
    const common = { destination_refinery: refinery, ranking_mode: mode, excluded_countries: excluded }
    // Deterministic facts first: the brief renders without waiting on Gemini.
    try {
      const reroute = await fetchReroute({ blocked_chokepoint: sc.chokepoint, ...common })
      const top = reroute.procurement_matrix[0]
      const spr = await fetchSpr({
        blocked_chokepoint: sc.chokepoint,
        lead_time_days: Math.max(1, Math.round(top?.lead_time_days ?? 30)),
        disrupted_volume_mbpd: sc.volume,
        run_rate_cut_pct: levers.run,
        industrial_cut_pct: levers.ind,
        transport_cut_pct: levers.trans,
      })
      setFacts({ reroute, spr, top })
    } catch {
      setErr("The models did not respond. Check that the backend is running.")
      setBusy(false)
      return
    }
    setBusy(false)
    setAiState("pending")
    fetchWarRoom({
      scenario_name: sc.name,
      blocked_chokepoint: sc.chokepoint,
      disrupted_volume_mbpd: sc.volume,
      ...common,
      run_rate_cut_pct: levers.run,
      industrial_cut_pct: levers.ind,
      transport_cut_pct: levers.trans,
    })
      .then((r) => { setAi(r); setAiState("done") })
      .catch(() => setAiState("failed"))
  }

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(window.location.href)
      setCopied(true)
      window.setTimeout(() => setCopied(false), 1500)
    } catch { /* clipboard blocked */ }
  }

  const s = facts?.spr
  const t = facts?.top
  const risky = facts?.reroute.procurement_matrix.filter((r) => r.risk_score >= 0.4)
  const saved = s?.demand_actions.reduce((a, d) => a + d.saves_mbpd, 0) ?? 0

  return (
    <div className="flex flex-col gap-4 lg:gap-5">
      <section aria-label="Crisis scenario" className="no-scrollbar -mr-4 flex gap-3 overflow-x-auto pr-4 lg:mr-0 lg:grid lg:grid-cols-4 lg:overflow-visible lg:pr-0">
        {SCENARIOS.map((x) => {
          const live = chokepoints.find((c) => c.name === x.chokepoint)
          const on = x.id === sid
          return (
            <button
              key={x.id}
              type="button"
              aria-pressed={on}
              onClick={() => { setSid(x.id); setFacts(null); setAi(null); setAiState("idle") }}
              className={`flex w-[200px] shrink-0 flex-col gap-1.5 rounded-[14px] border p-4 text-left lg:w-auto ${on ? "border-orange bg-orange-soft" : "border-line bg-panel"}`}
            >
              <span className={`font-mono text-[10px] tracking-[0.1em] ${on ? "text-orange" : "text-dim"}`}>
                SCENARIO {x.id}{live ? ` · LIVE RISK ${live.risk_score.toFixed(2)}` : ""}
              </span>
              <span className="text-[15px] font-bold text-head">{x.short}</span>
              <span className="text-xs text-muted">{x.volume} mbpd to India at stake</span>
            </button>
          )
        })}
      </section>

      <div className="panel flex flex-col gap-3 rounded-[14px] px-4 py-3.5">
        <div className="flex flex-wrap items-center gap-x-3 gap-y-2 text-[13px] text-muted">
          <span>Refinery <strong className="text-head">{refinery.split(" (")[0]}</strong></span><span className="text-[var(--x-3a4656)]">·</span>
          <span>Optimise <strong className="text-head">{mode === "cost" ? "cost" : "time"}</strong></span><span className="text-[var(--x-3a4656)]">·</span>
          <span>Excluded <strong className="text-head">{excluded.length}</strong></span><span className="text-[var(--x-3a4656)]">·</span>
          <span>Levers <strong className="text-head">{levers.run}/{levers.ind}/{levers.trans}%</strong></span>
          <button type="button" onClick={() => setEdit((v) => !v)} aria-expanded={edit} className="font-semibold text-accent">{edit ? "Done" : "Edit parameters"}</button>
          <button type="button" onClick={() => void simulate()} disabled={busy} className="ml-auto hidden h-11 items-center gap-2 rounded-[10px] bg-crit px-5 text-sm font-bold text-[var(--x-1c0f11)] disabled:opacity-60 lg:flex">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M7 5l12 7-12 7z" /></svg>
            {busy ? "Simulating…" : "Simulate"}
          </button>
        </div>
        {edit && (
          <div className="grid grid-cols-1 gap-3 border-t border-hair pt-3 sm:grid-cols-2 lg:grid-cols-4">
            <label className="flex flex-col gap-1.5"><Eyebrow>Refinery</Eyebrow>
              <select value={refinery} onChange={(e) => setRefinery(e.target.value)} className="h-11 rounded-[10px] border border-edge bg-well px-3 text-sm text-head">
                {(cfg.refineries.length ? cfg.refineries : [refinery]).map((r) => <option key={r}>{r}</option>)}
              </select></label>
            <div className="flex flex-col gap-1.5"><Eyebrow>Optimise for</Eyebrow>
              <Segmented label="Optimise for" value={mode} onChange={setMode} options={[{ value: "cost", label: "Cost" }, { value: "speed", label: "Time" }]} /></div>
            <div className="flex flex-col gap-1.5 sm:col-span-2"><Eyebrow>Exclude countries</Eyebrow><CountryChips value={excluded} onChange={setExcluded} /></div>
            {([["run", "Run-rate cut"], ["ind", "Industrial priority"], ["trans", "Fuel rationing"]] as const).map(([k, l]) => (
              <label key={k} className="flex flex-col gap-1.5">
                <span className="eyebrow flex justify-between">{l} <span className="text-head">{levers[k]}%</span></span>
                <input type="range" min={0} max={50} value={levers[k]} onChange={(e) => setLevers((p) => ({ ...p, [k]: Number(e.target.value) }))} className="accent-accent" />
              </label>
            ))}
          </div>
        )}
      </div>
      <button type="button" onClick={() => void simulate()} disabled={busy} className="flex h-[52px] items-center justify-center gap-2 rounded-xl bg-crit text-[15px] font-bold text-[var(--x-1c0f11)] disabled:opacity-60 lg:hidden">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M7 5l12 7-12 7z" /></svg>
        {busy ? "Simulating…" : "Simulate"}
      </button>

      {err && <ErrorNote message={err} onRetry={() => void simulate()} />}
      {!facts && !busy && !err && <Panel className="p-6 text-sm text-dim">Pick a scenario and press Simulate. The brief appears as soon as the models finish; the AI narrative follows.</Panel>}

      {facts && s && (
        <section aria-labelledby="brief-h" className="flex flex-wrap gap-4 lg:gap-5">
          <Panel as="article" className="flex min-w-0 flex-[3_1_520px] flex-col gap-4 p-5 lg:p-[26px]">
            <div className="flex flex-wrap items-center justify-between gap-2.5">
              <h2 id="brief-h" className="text-lg font-bold text-head [font-stretch:108%] lg:text-xl">Brief · {sc.short}</h2>
              <span className={`flex items-center gap-2 rounded-full border px-2.5 py-1 font-mono text-[11px] ${
                aiState === "pending" ? "border-[var(--x-24405f)] bg-[var(--x-121a24)] text-accent-hi" : aiState === "failed" ? "border-crit-line bg-crit-soft text-crit-text" : "border-safe-line bg-safe-soft text-safe"
              }`}>
                <span className="h-1.5 w-1.5 rounded-full" style={{ background: aiState === "pending" ? "var(--x-5aaeff)" : aiState === "failed" ? "var(--x-ff5a5f)" : "var(--x-3fcf8e)" }} />
                {aiState === "pending" ? "AI narrative generating…" : aiState === "failed" ? "AI narrative unavailable" : "AI narrative ready"}
              </span>
            </div>
            <div className="flex flex-col gap-1.5">
              <span className="eyebrow text-crit-text">Situation</span>
              <p className="text-sm leading-relaxed text-fg">
                Closing {sc.chokepoint.replace("Strait of ", "")} removes {s.daily_shortfall_mbpd.toFixed(2)} mbpd from India’s supply.{" "}
                {s.supply_gap_days > 0
                  ? `Without action the strategic reserve empties in ${s.survival_days.toFixed(1)} days, ${s.supply_gap_days.toFixed(1)} days before replacement cargoes land.`
                  : `The reserve covers the ${s.lead_time_days.toFixed(0)}-day replacement window.`}
              </p>
            </div>
            <div className="flex flex-col gap-1.5">
              <span className="eyebrow text-safe">Recommended actions</span>
              <ol className="flex list-decimal flex-col gap-2 pl-[18px] text-sm leading-relaxed text-fg">
                {t && <li>Contract {t.crude_grade} from {t.country} at ${fmt(t.landed_cost_usd)}/bbl landed, {t.lead_time_days.toFixed(1)} days to {facts.reroute.destination_refinery}.</li>}
                <li>Apply the demand levers ({levers.run}% run-rate, {levers.ind}% industrial, {levers.trans}% transport) — saves {saved.toFixed(2)} mbpd.</li>
                <li>{s.adjusted_gap_days > 0 ? `Even with both, a ${s.adjusted_gap_days.toFixed(1)}-day gap remains — accelerate imports.` : `With both, reserves last ${s.adjusted_survival_days >= 999 ? "the whole window" : `${s.adjusted_survival_days.toFixed(0)} days`}.`}</li>
              </ol>
            </div>
            <div className="flex flex-col gap-1.5">
              <span className="eyebrow text-warn">Watch</span>
              <p className="text-sm leading-relaxed text-fg">
                Supply resilience is {Math.round(facts.reroute.resilience_score)}/100.
                {risky?.length ? ` ${risky.map((r) => `${r.crude_grade} (${r.country})`).slice(0, 2).join(", ")} carr${risky.length > 1 ? "y" : "ies"} elevated route risk.` : ""}
              </p>
            </div>
            {aiState === "done" && ai?.executive_brief && (
              <div className="flex flex-col gap-1.5 border-t border-hair pt-4">
                <span className="eyebrow text-accent">AI narrative</span>
                <p className="whitespace-pre-wrap text-sm leading-relaxed text-fg">{ai.executive_brief}</p>
              </div>
            )}
            <span className="text-[11px] text-faint">Facts above come straight from the models; the AI narrative is added when ready and never blocks the brief.</span>
            <div className="grid grid-cols-2 gap-2.5 print:hidden">
              <button type="button" onClick={() => window.print()} className="min-h-11 rounded-[10px] border border-edge bg-[var(--x-0f141a)] text-[13px] text-head">Export PDF</button>
              <button type="button" onClick={() => void copy()} className="min-h-11 rounded-[10px] border border-edge bg-[var(--x-0f141a)] text-[13px] text-head">{copied ? "Copied" : "Copy link"}</button>
            </div>
          </Panel>

          <aside className="grid min-w-0 flex-[1_1_280px] grid-cols-2 gap-3 lg:flex lg:flex-col">
            <div className="flex flex-col gap-1.5 rounded-2xl border border-crit-line bg-crit-soft p-4"><span className="eyebrow text-crit-text">Reserve · no action</span><span className="text-[26px] font-bold text-head lg:text-[30px]">{s.survival_days.toFixed(1)} d</span></div>
            <div className="flex flex-col gap-1.5 rounded-2xl border border-safe-line bg-safe-soft p-4"><span className="eyebrow text-safe">Reserve · with plan</span><span className="text-[26px] font-bold text-head lg:text-[30px]">{s.adjusted_survival_days >= 999 ? "∞" : `${s.adjusted_survival_days.toFixed(1)} d`}</span></div>
            {t && <div className="panel col-span-2 flex flex-col gap-1.5 rounded-2xl p-4"><Eyebrow>Top reroute</Eyebrow><span className="text-lg font-bold text-head">{t.crude_grade} · ${fmt(t.landed_cost_usd)}</span><span className="text-xs text-muted">{t.lead_time_days.toFixed(1)} days · risk {t.risk_score.toFixed(2)}</span></div>}
            <div className="panel col-span-2 flex flex-col gap-1.5 rounded-2xl p-4"><Eyebrow>Macro · no action</Eyebrow><span className="text-lg font-bold text-head">GDP {s.macro_gdp_impact_pct} · CPI {s.macro_infl_impact}</span></div>
          </aside>
        </section>
      )}
    </div>
  )
}
