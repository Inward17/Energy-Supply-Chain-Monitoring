"use client"

import dynamic from "next/dynamic"
import { useState } from "react"
import { feedHealth, useData } from "../data"
import { useDetail } from "../detail"
import { Eyebrow, Panel, Ring, fmt, riskText } from "../ui"

const MapView = dynamic(() => import("../map-view"), {
  ssr: false,
  loading: () => <div className="absolute inset-0 flex items-center justify-center text-sm text-dim">Loading map…</div>,
})

export function ThreatMapPage() {
  const { chokepoints, vessels, live } = useData()
  const open = useDetail()
  const sorted = [...chokepoints].sort((a, b) => b.risk_score - a.risk_score)
  const [selected, setSelected] = useState<string | null>(null)
  const sel = sorted.find((c) => c.name === selected) ?? sorted[0]
  const [halos, setHalos] = useState(true)
  const ais = feedHealth(live).find((f) => f.key === "ais")
  const aisOk = ais?.state === "ok" && vessels.length > 0
  const [showVessels, setShowVessels] = useState(true)

  const chip = (on: boolean, label: string, onClick?: () => void, disabled = false) => (
    <button
      type="button"
      aria-pressed={on}
      disabled={disabled}
      onClick={onClick}
      className={`h-9 rounded-full border px-3.5 text-xs ${
        disabled ? "cursor-not-allowed border-dashed border-[var(--x-4a2224)] text-faint" : on ? "border-accent-line bg-accent-soft font-semibold text-head" : "border-edge bg-[var(--x-0f141a)] text-muted"
      }`}
    >
      {label}
    </button>
  )

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <span className="font-mono text-[11px] text-dim">
          {chokepoints.length} chokepoints · {aisOk ? `${vessels.length} vessels live` : `0 vessels (AIS ${ais?.state === "stale" ? "partial" : "offline"})`}
        </span>
        <div role="group" aria-label="Map layers" className="flex flex-wrap gap-2">
          {chip(halos, "Risk halos", () => setHalos((v) => !v))}
          {chip(aisOk && showVessels, aisOk ? "Vessels" : "Vessels · offline", () => setShowVessels((v) => !v), !aisOk)}
        </div>
      </div>

      <div className="flex flex-wrap gap-4 lg:gap-5">
        <div className="relative min-h-[460px] min-w-0 flex-[3_1_560px] overflow-hidden rounded-[18px] border border-line lg:min-h-[680px]">
          <MapView chokepoints={sorted} vessels={vessels} showHalos={halos} showVessels={aisOk && showVessels} selected={sel?.name ?? null} onSelect={setSelected} />
          {!aisOk && (
            <div role="status" className="pointer-events-none absolute left-14 top-3 z-[500] flex max-w-[calc(100%-5rem)] items-center gap-2.5 rounded-xl border border-crit-line bg-[var(--x-1c0f11)]/95 px-3.5 py-2.5 text-xs text-fg">
              <span className="h-2 w-2 shrink-0 rounded-full bg-crit" />
              Vessel layer unavailable — {ais?.detail}
            </div>
          )}
          <div className="pointer-events-none absolute bottom-6 left-3 z-[500] hidden gap-3.5 rounded-xl border border-edge bg-[var(--x-10161d)]/95 px-3.5 py-2.5 font-mono text-[11px] text-muted sm:flex">
            <span className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-full bg-safe" />&lt; 0.40</span>
            <span className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-full bg-orange" />0.40–0.70</span>
            <span className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-full bg-crit" />&gt; 0.70</span>
          </div>
        </div>

        <aside className="flex min-w-0 flex-[1_1_300px] flex-col gap-4">
          {sel && (
            <Panel className="flex flex-col gap-3.5 p-5">
              <Eyebrow>Selected</Eyebrow>
              <div className="flex items-center gap-3.5">
                <Ring value={sel.risk_score} size={64} stroke={7} />
                <div className="flex flex-col gap-1">
                  <h2 className="text-[19px] font-bold text-head">{sel.name}</h2>
                  <span className="text-xs text-muted">{sel.flow_mb_day.toFixed(1)} mbpd · +${fmt(sel.price_impact_usd)}/bbl</span>
                </div>
              </div>
              <div className="grid grid-cols-2 gap-2">
                <div className="flex flex-col gap-1 rounded-[10px] bg-well p-2.5">
                  <span className="font-mono text-[10px] text-dim">SDI SHARE</span>
                  <span className="text-[15px] font-semibold text-head">{fmt(sel.sdi_contribution, 1)} pts</span>
                </div>
                <div className={`flex flex-col gap-1 rounded-[10px] p-2.5 ${aisOk ? "bg-well" : "hatch-card"}`}>
                  <span className="font-mono text-[10px] text-dim">TRANSITS</span>
                  <span className={`text-[15px] font-semibold ${aisOk ? "text-head" : "text-faint"}`}>
                    {aisOk && sel.vessels_current != null ? `${sel.vessels_current} / ${sel.vessels_baseline}` : "no AIS"}
                  </span>
                </div>
              </div>
              <button
                type="button"
                onClick={() => open({ kind: "chokepoint", name: sel.name })}
                className="min-h-11 rounded-[10px] bg-accent text-[13px] font-bold text-[var(--x-06121f)]"
              >
                Why this score →
              </button>
            </Panel>
          )}
          <Panel className="flex flex-col px-[18px] py-2" aria-label="All chokepoints">
            {sorted.map((c) => (
              <button
                key={c.name}
                type="button"
                onClick={() => setSelected(c.name)}
                aria-pressed={c.name === sel?.name}
                className={`flex min-h-11 items-center justify-between border-b border-hair text-left text-[13px] last:border-b-0 ${c.name === sel?.name ? "font-semibold text-head" : "text-fg"}`}
              >
                <span>{c.name}</span>
                <span className="font-mono" style={{ color: riskText(c.risk_score) }}>{c.risk_score.toFixed(2)}</span>
              </button>
            ))}
          </Panel>
        </aside>
      </div>
    </div>
  )
}
