"use client"

import { useState } from "react"
import { useData } from "../data"
import { Eyebrow, Loading, Panel, Segmented, Spark, fmt, shortDate } from "../ui"

const META: Record<string, { name: string; color: string }> = {
  "BZ=F": { name: "Brent crude", color: "var(--x-5aaeff)" },
  USO: { name: "US Oil Fund", color: "var(--x-5aaeff)" },
  "NG=F": { name: "Henry Hub gas", color: "var(--x-c9a8ff)" },
  XLE: { name: "Energy sector", color: "var(--x-ffb86b)" },
}
const RANGE = { "2W": 10, "1M": 21, "2M": 9999 } as const
type Range = keyof typeof RANGE

export function MarketPage() {
  const { market, live } = useData()
  const [range, setRange] = useState<Range>("2M")
  if (!market) return <Loading label="Loading market data…" />

  const brent = market.instruments.find((i) => i.ticker === "BZ=F")
  const others = market.instruments.filter((i) => i.ticker !== "BZ=F")
  const slice = <T,>(xs: T[]) => xs.slice(-RANGE[range])
  const z = market.brent_std_30d ? (market.brent_current - market.brent_mean_30d) / market.brent_std_30d : 0
  const chg = (vals: number[]) => (vals.length > 1 ? ((vals[vals.length - 1] - vals[0]) / vals[0]) * 100 : 0)
  const brentSeries = brent ? slice(brent.series) : []
  const bv = brentSeries.map((p) => p.price)
  const peak = brentSeries.reduce((m, p) => (p.price > m.price ? p : m), brentSeries[0] ?? { price: 0, d: "" })
  const zPos = Math.max(0, Math.min(100, 50 + (z / 4) * 50))

  return (
    <div className="flex flex-col gap-4 lg:gap-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <span className="font-mono text-[11px] text-dim">
          {brentSeries.length} sessions · {shortDate(brentSeries[0]?.d)} – {shortDate(brentSeries[brentSeries.length - 1]?.d)}
        </span>
        <div className="w-[220px]"><Segmented label="Range" value={range} onChange={setRange} options={(["2W", "1M", "2M"] as Range[]).map((r) => ({ value: r, label: r }))} /></div>
      </div>

      <section className="flex flex-wrap gap-4 lg:gap-5">
        {brent && (
          <Panel as="figure" className="m-0 flex min-w-0 flex-[3_1_560px] flex-col gap-3.5 p-5 lg:p-[22px]">
            <div className="flex flex-wrap items-end justify-between gap-3">
              <div className="flex flex-col gap-1.5">
                <h2 className="eyebrow text-[11px]">Brent crude · BZ=F</h2>
                <div className="flex items-baseline gap-3">
                  <span className="text-[44px] font-bold leading-[0.95] tracking-[-0.03em] text-head [font-stretch:108%] lg:text-[52px]">${fmt(brent.price)}</span>
                  <span className="font-mono text-[13px]" style={{ color: chg(bv) >= 0 ? "var(--x-ff8a8d)" : "var(--x-6fe0ab)" }}>{chg(bv) >= 0 ? "▲" : "▼"} {Math.abs(chg(bv)).toFixed(1)}% · {range}</span>
                </div>
              </div>
              {peak?.d && <span className="font-mono text-[11px] text-dim">peak ${fmt(peak.price)} · {shortDate(peak.d)}</span>}
            </div>
            <Spark values={bv} height={260} className="min-h-[170px]" />
            <div className="flex justify-between font-mono text-[10px] text-faint">
              <span>{shortDate(brentSeries[0]?.d)}</span>
              <span>{shortDate(brentSeries[brentSeries.length - 1]?.d)}</span>
            </div>
          </Panel>
        )}

        <Panel className="flex min-w-0 flex-[1_1_280px] flex-col gap-4 p-5 lg:p-[22px]">
          <Eyebrow className="text-[11px]">vs 30-day trend</Eyebrow>
          <span className="text-[44px] font-bold text-head [font-stretch:108%]">{z >= 0 ? "+" : ""}{z.toFixed(2)}σ</span>
          <div className="relative h-10" aria-hidden="true">
            <div className="absolute inset-x-0 top-[18px] h-1 rounded-full bg-track" />
            <div className="absolute top-2.5 h-5 w-px bg-[var(--x-3a4656)]" style={{ left: "50%" }} />
            <div className="absolute top-2.5 h-5 w-px bg-[var(--x-3a4656)]" style={{ left: "75%" }} />
            <div className="absolute top-[18px] h-1 bg-warn" style={{ left: `${Math.min(50, zPos)}%`, width: `${Math.abs(zPos - 50)}%` }} />
            <div className="absolute top-[13px] h-3.5 w-3.5 -translate-x-1/2 rounded-full bg-head shadow-[0_0_0_3px_var(--x-0e1319)]" style={{ left: `${zPos}%` }} />
            <span className="absolute top-8 -translate-x-1/2 font-mono text-[10px] text-faint" style={{ left: "50%" }}>mean</span>
            <span className="absolute top-8 -translate-x-1/2 font-mono text-[10px] text-faint" style={{ left: "75%" }}>+2σ</span>
          </div>
          <dl className="grid grid-cols-[1fr_auto] gap-2.5 border-t border-hair pt-2 text-[13px]">
            <dt className="text-muted">30-day mean</dt><dd className="font-mono text-head">${fmt(market.brent_mean_30d)}</dd>
            <dt className="text-muted">30-day σ</dt><dd className="font-mono text-head">${fmt(market.brent_std_30d)}</dd>
            {live && (<><dt className="text-muted">SDI contribution</dt><dd className="font-mono text-head">{(live.delta_p * (live.w3 ?? 0.1) * 100).toFixed(1)} / {Math.round((live.w3 ?? 0.1) * 100)}</dd></>)}
          </dl>
          <span className="text-xs leading-relaxed text-dim">The index uses this deviation, not the raw price.</span>
        </Panel>
      </section>

      <section aria-label="Benchmarks" className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {others.map((i) => {
          const vals = slice(i.series).map((p) => p.price)
          const c = chg(vals)
          const m = META[i.ticker] ?? { name: i.ticker, color: "var(--x-5aaeff)" }
          return (
            <div key={i.ticker} className="panel relative flex flex-col gap-1.5 overflow-hidden rounded-2xl p-[18px] pb-[84px]">
              <div className="flex justify-between gap-2"><Eyebrow>{m.name} · {i.ticker}</Eyebrow><span className="font-mono text-[11px]" style={{ color: c >= 0 ? "var(--x-ff8a8d)" : "var(--x-6fe0ab)" }}>{c >= 0 ? "▲" : "▼"} {Math.abs(c).toFixed(1)}%</span></div>
              <span className="text-[28px] font-bold text-head [font-stretch:108%]">${fmt(i.price)}</span>
              <span className="font-mono text-[11px] text-dim">{i.price >= i.high_52w ? "52w high today" : `52w $${fmt(i.low_52w)}–$${fmt(i.high_52w)}`}</span>
              <div className="absolute inset-x-0 bottom-0"><Spark values={vals} color={m.color} height={72} /></div>
            </div>
          )
        })}
        {live && (
          <div className="panel flex flex-col gap-1.5 rounded-2xl p-[18px]">
            <div className="flex justify-between"><Eyebrow>Tanker freight · BOAT</Eyebrow><span className="font-mono text-[11px] text-dim">stress</span></div>
            <span className="text-[28px] font-bold text-head [font-stretch:108%]">${fmt(live.current_freight)}</span>
            <span className="font-mono text-[11px] text-dim">stress index {fmt(live.delta_f)}</span>
            <div className="mt-auto flex flex-col gap-1.5 pt-3.5">
              <div className="h-2 rounded-full bg-track"><div className="h-2 rounded-full bg-accent" style={{ width: `${Math.min(1, live.delta_f) * 100}%` }} /></div>
              <span className="text-[11px] text-faint">Daily series not cached yet</span>
            </div>
          </div>
        )}
      </section>
    </div>
  )
}
