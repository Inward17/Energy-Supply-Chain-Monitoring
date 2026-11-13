"use client"

import { useEffect, useRef, useState } from "react"
import { fetchSpr, type SprResult } from "@/lib/api"
import { LineChart } from "../charts"
import { ErrorNote, Eyebrow, Loading, Panel } from "../ui"
import { useConfig } from "./reroute"

const LEVERS = [
  { key: "run", label: "Refinery run-rate cut", cost: "low", def: 15, max: 50 },
  { key: "ind", label: "Industrial priority scheme", cost: "low", def: 8, max: 50 },
  { key: "trans", label: "Transport fuel rationing", cost: "medium", def: 10, max: 50 },
] as const

export function SprPage() {
  const cfg = useConfig()
  const [blocked, setBlocked] = useState("Strait of Hormuz")
  const [lead, setLead] = useState(30)
  const [on, setOn] = useState<Record<string, boolean>>({ run: true, ind: true, trans: true })
  const [pct, setPct] = useState<Record<string, number>>({ run: 15, ind: 8, trans: 10 })
  const [gdp, setGdp] = useState(3.5) // ×0.01 → % of GDP lost per day of zero supply (model default 0.035%)
  const [showAssume, setShowAssume] = useState(false)
  const [res, setRes] = useState<SprResult | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const t = useRef<number | undefined>(undefined)

  const run = async () => {
    setBusy(true)
    setErr(null)
    try {
      setRes(
        await fetchSpr({
          blocked_chokepoint: blocked,
          lead_time_days: lead,
          gdp_impact_rate_pct: gdp,
          run_rate_cut_pct: on.run ? pct.run : 0,
          industrial_cut_pct: on.ind ? pct.ind : 0,
          transport_cut_pct: on.trans ? pct.trans : 0,
        }),
      )
    } catch {
      setErr("The reserve model did not respond.")
    } finally {
      setBusy(false)
    }
  }

  // Re-simulate shortly after any input settles.
  useEffect(() => {
    window.clearTimeout(t.current)
    t.current = window.setTimeout(() => void run(), 350)
    return () => window.clearTimeout(t.current)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [blocked, lead, on, pct, gdp])

  const sites = (res as unknown as { spr_sites?: Record<string, number> } | null)?.spr_sites ?? {}
  const maxSite = Math.max(1, ...Object.values(sites))
  const saved = res?.demand_actions.reduce((a, d) => a + d.saves_mbpd, 0) ?? 0
  const series = res?.burndown_series ?? []
  const emptyFrom = series.findIndex((p) => p.baseline <= 0.01)
  const emptyTo = emptyFrom >= 0 ? series.findIndex((p, i) => i > emptyFrom && p.baseline > 0.01) : -1
  const minManaged = series.length ? Math.min(...series.map((p) => p.managed)) : 0
  const minAt = series.findIndex((p) => p.managed === minManaged)

  return (
    <div className="flex flex-col gap-4 lg:gap-5">
      <div className="panel flex flex-wrap items-end gap-3 rounded-[18px] p-4">
        <label className="flex min-w-[220px] flex-1 flex-col gap-1.5"><Eyebrow>Blocked</Eyebrow>
          <select value={blocked} onChange={(e) => setBlocked(e.target.value)} className="h-12 rounded-[10px] border border-orange bg-orange-soft px-3 text-[14px] text-head lg:h-11">
            {(cfg.chokepoints.length ? cfg.chokepoints : [blocked]).map((c) => <option key={c}>{c}</option>)}
          </select></label>
        <label className="flex min-w-[220px] flex-[2] flex-col gap-1.5">
          <span className="eyebrow flex justify-between">Lead time to replacement cargo <span className="text-[13px] text-head">{lead} days</span></span>
          <input type="range" min={1} max={90} value={lead} onChange={(e) => setLead(Number(e.target.value))} className="h-11 accent-accent" />
        </label>
        <button type="button" onClick={() => setShowAssume((v) => !v)} aria-expanded={showAssume} className="h-12 rounded-[10px] border border-edge bg-well px-3.5 text-[13px] text-muted lg:h-11">
          Model assumptions
        </button>
      </div>

      {showAssume && (
        <Panel className="grid grid-cols-1 gap-4 p-4 sm:grid-cols-2 lg:grid-cols-4">
          <label className="flex flex-col gap-1.5">
            <span className="eyebrow flex justify-between">GDP loss / day of shortage <span className="text-head">{(gdp / 100).toFixed(3)}%</span></span>
            <input type="range" min={1} max={10} step={0.5} value={gdp} onChange={(e) => setGdp(Number(e.target.value))} className="accent-accent" />
          </label>
          {LEVERS.map((l) => (
            <label key={l.key} className="flex flex-col gap-1.5">
              <span className="eyebrow flex justify-between">{l.label} <span className="text-head">{pct[l.key]}%</span></span>
              <input type="range" min={0} max={l.max} value={pct[l.key]} onChange={(e) => setPct((p) => ({ ...p, [l.key]: Number(e.target.value) }))} className="accent-accent" />
            </label>
          ))}
          <p className="text-xs leading-relaxed text-warn sm:col-span-2 lg:col-span-4">
            The model starts from a full reserve ({res?.spr_capacity_mb ?? 39} MB). Real fill levels are usually lower — treat survival days as an upper bound.
          </p>
        </Panel>
      )}

      {err && <ErrorNote message={err} onRetry={() => void run()} />}
      {!res && !err && <Loading label="Simulating…" />}

      {res && (
        <>
          <section className="grid grid-cols-2 gap-3 lg:grid-cols-3">
            <div className="flex flex-col gap-1.5 rounded-2xl border border-crit-line bg-crit-soft p-4 lg:p-[18px]">
              <span className="eyebrow text-crit-text">No action</span>
              <span className="text-[28px] font-bold text-head [font-stretch:108%] lg:text-[34px]">{res.survival_days.toFixed(1)} d</span>
              <span className="text-xs text-muted">{res.supply_gap_days > 0 ? `${res.supply_gap_days.toFixed(1)} days short of the ${lead}-day lead time` : "covers the lead time"}</span>
            </div>
            <div className="flex flex-col gap-1.5 rounded-2xl border border-safe-line bg-safe-soft p-4 lg:p-[18px]">
              <span className="eyebrow text-safe">With levers</span>
              <span className="text-[28px] font-bold text-head [font-stretch:108%] lg:text-[34px]">{res.adjusted_survival_days >= 999 ? "∞" : `${res.adjusted_survival_days.toFixed(1)} d`}</span>
              <span className="text-xs text-muted">{res.adjusted_gap_days > 0 ? `${res.adjusted_gap_days.toFixed(1)} days still short` : `gap closed · bottoms at ${Math.round(minManaged)}% on day ${minAt}`}</span>
            </div>
            <div className="panel col-span-2 flex flex-col gap-1.5 rounded-2xl p-4 lg:col-span-1 lg:p-[18px]">
              <Eyebrow>Daily shortfall</Eyebrow>
              <span className="text-[28px] font-bold text-head [font-stretch:108%] lg:text-[34px]">{res.daily_shortfall_mbpd.toFixed(2)} mbpd</span>
              <span className="text-xs text-muted">of {res.india_consumption_mbpd} mbpd demand</span>
            </div>
          </section>

          <section className="flex flex-wrap gap-4 lg:gap-5">
            <Panel as="figure" className="m-0 flex min-w-0 flex-[3_1_560px] flex-col gap-3 p-4 lg:p-[22px]">
              <div className="flex flex-wrap items-baseline justify-between gap-2.5">
                <span className="text-[15px] font-bold text-head">Reserve level, % of capacity</span>
                <div className="flex gap-3.5 font-mono text-[11px] text-dim">
                  <span className="flex items-center gap-1.5"><span className="h-[3px] w-3.5 bg-crit" />no action</span>
                  <span className="flex items-center gap-1.5"><span className="h-[3px] w-3.5 bg-safe" />with levers</span>
                </div>
              </div>
              <LineChart
                label={`Without action the reserve ${emptyFrom >= 0 ? `is empty from day ${emptyFrom}` : "lasts the horizon"}; with levers it bottoms at ${Math.round(minManaged)}%.`}
                yMin={0}
                yMax={100}
                series={[
                  { values: series.map((p) => p.baseline), color: "var(--x-ff5a5f)" },
                  { values: series.map((p) => p.managed), color: "var(--x-3fcf8e)" },
                ]}
              >
                {(sx, sy, W) => (
                  <>
                    <line x1="0" y1={sy(100)} x2={W} y2={sy(100)} stroke="var(--x-1a222c)" />
                    <line x1="0" y1={sy(50)} x2={W} y2={sy(50)} stroke="var(--x-1a222c)" />
                    <line x1="0" y1={sy(10)} x2={W} y2={sy(10)} stroke="var(--x-44201f)" strokeDasharray="3 4" />
                    <text x="4" y={sy(10) - 5} fill="var(--x-ff8a8d)" fontFamily="var(--font-plex-mono)" fontSize="9">10% safety floor</text>
                    {emptyFrom >= 0 && (
                      <>
                        <rect x={sx(emptyFrom)} y={sy(100)} width={sx(emptyTo > 0 ? emptyTo : series.length - 1) - sx(emptyFrom)} height={sy(0) - sy(100)} fill="var(--x-1c0f11)" opacity="0.7" />
                        <text x={(sx(emptyFrom) + sx(emptyTo > 0 ? emptyTo : series.length - 1)) / 2} y={sy(4)} textAnchor="middle" fill="var(--x-ff8a8d)" fontFamily="var(--font-plex-mono)" fontSize="10">
                          {(emptyTo > 0 ? emptyTo : series.length - 1) - emptyFrom} days with no reserve
                        </text>
                      </>
                    )}
                    {lead < series.length && (
                      <>
                        <line x1={sx(lead)} y1={sy(100)} x2={sx(lead)} y2={sy(0)} stroke="var(--x-5aaeff)" strokeDasharray="4 4" />
                        <text x={sx(lead) - 4} y={sy(92)} textAnchor="end" fill="var(--x-5aaeff)" fontFamily="var(--font-plex-mono)" fontSize="10">cargoes arrive · day {lead}</text>
                      </>
                    )}
                    <text x="0" y={sy(0) + 16} fill="var(--x-7a8697)" fontFamily="var(--font-plex-mono)" fontSize="10">day 0</text>
                    <text x={W} y={sy(0) + 16} textAnchor="end" fill="var(--x-7a8697)" fontFamily="var(--font-plex-mono)" fontSize="10">{series.length - 1}</text>
                  </>
                )}
              </LineChart>
            </Panel>

            <Panel className="flex min-w-0 flex-[2_1_320px] flex-col gap-2.5 p-4 lg:p-[22px]">
              <span className="text-[15px] font-bold text-head">Demand levers {busy && <span className="font-mono text-[10px] text-dim">· updating</span>}</span>
              {LEVERS.map((l) => {
                const act = res.demand_actions.find((a) => a.action.toLowerCase().startsWith(l.label.split(" ")[0].toLowerCase()))
                return (
                  <label key={l.key} className="flex min-h-14 items-center gap-3 rounded-xl border border-line bg-well p-3">
                    <input type="checkbox" checked={on[l.key]} onChange={(e) => setOn((p) => ({ ...p, [l.key]: e.target.checked }))} className="h-5 w-5 accent-safe" />
                    <span className="flex flex-1 flex-col gap-0.5"><span className="text-[13px] text-head">{l.label} · {pct[l.key]}%</span><span className="text-[11px] text-dim">cost: {l.cost}</span></span>
                    <span className="font-mono text-[13px]" style={{ color: on[l.key] ? "var(--x-3fcf8e)" : "var(--x-7a8697)" }}>{on[l.key] && act ? `−${act.saves_mbpd.toFixed(2)}` : "0.00"}</span>
                  </label>
                )
              })}
              <div className="flex justify-between border-t border-hair px-0.5 pt-2.5 text-[13px]"><span className="text-muted">Total saved</span><span className="font-mono text-head">{saved.toFixed(2)} mbpd</span></div>
            </Panel>
          </section>

          <section className="flex flex-wrap gap-4 lg:gap-5">
            <Panel className="flex min-w-0 flex-[1_1_320px] flex-col gap-3 p-4 lg:p-[22px]">
              <span className="text-[15px] font-bold text-head">Macro impact · no action</span>
              <div className="grid grid-cols-2 gap-2.5">
                <div className="flex flex-col gap-1 rounded-xl bg-crit-soft p-3"><span className="font-mono text-[10px] text-crit-text">GDP</span><span className="text-[22px] font-bold text-head">{res.macro_gdp_impact_pct}</span><span className="text-[11px] text-muted">{res.macro_gdp_impact_usd}</span></div>
                <div className="flex flex-col gap-1 rounded-xl bg-crit-soft p-3"><span className="font-mono text-[10px] text-crit-text">INFLATION</span><span className="text-[22px] font-bold text-head">{res.macro_infl_impact}</span><span className="text-[11px] text-muted">with levers: {res.macro_infl_adj.toLowerCase()}</span></div>
              </div>
            </Panel>
            <Panel className="flex min-w-0 flex-[1_1_320px] flex-col gap-2.5 p-4 lg:p-[22px]">
              <span className="text-[15px] font-bold text-head">Reserve sites</span>
              {Object.entries(sites).sort((a, b) => b[1] - a[1]).map(([n, v]) => (
                <div key={n} className="grid grid-cols-[110px_1fr_56px] items-center gap-2.5 text-[13px]">
                  <span className="text-fg">{n}</span>
                  <span className="h-2 rounded-full bg-accent" style={{ width: `${(v / maxSite) * 100}%` }} />
                  <span className="text-right font-mono text-muted">{v.toFixed(1)}</span>
                </div>
              ))}
              <span className="pt-1.5 text-xs leading-relaxed text-warn">Assumes all sites full. Adjust in Model assumptions.</span>
            </Panel>
          </section>
        </>
      )}
    </div>
  )
}
