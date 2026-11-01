"use client"

import { useMemo, useState } from "react"
import type { ProducerRisk } from "@/lib/api"
import { components, feedHealth, useData } from "../data"
import { useDetail } from "../detail"
import { SdiTrace } from "../charts"
import { Bar, Panel, SevChip, ago, fmt, riskColor, riskText, shortDate, titleCase } from "../ui"
import type { PageKey } from "../shell"

/** Producers with identical score and exposure collapse into one row
 *  ("Iran · UAE · Kuwait · Qatar") — they share a single driving event. */
function groupProducers(rows: ProducerRisk[]) {
  const out: { names: string[]; score: number; exposure: string }[] = []
  for (const r of [...rows].sort((a, b) => b.risk_score - a.risk_score)) {
    const last = out[out.length - 1]
    if (last && Math.abs(last.score - r.risk_score) < 0.0005 && last.exposure === r.exposure_type) last.names.push(r.name)
    else out.push({ names: [r.name], score: r.risk_score, exposure: r.exposure_type })
  }
  return out
}

const EXPOSURE_COLOR: Record<string, string> = { direct: "var(--x-ff8a8d)", transit: "var(--x-f2c14e)", baseline: "var(--x-7a8697)" }

export function RiskPage({ go }: { go: (p: PageKey) => void }) {
  const { live, visibleEvents, events, timeline, chokepoints, producers } = useData()
  const open = useDetail()
  const [type, setType] = useState("all")
  const [showFloor, setShowFloor] = useState(false)

  const types = useMemo(() => {
    const m = new Map<string, number>()
    visibleEvents.forEach((e) => m.set(e.disruption_type, (m.get(e.disruption_type) ?? 0) + 1))
    return [...m.entries()].sort((a, b) => b[1] - a[1])
  }, [visibleEvents])
  const list = visibleEvents.filter((e) => type === "all" || e.disruption_type === type)
  const comp = live ? components(live) : []
  const liveSignals = comp.filter((c) => !c.missing).length
  const groups = groupProducers(producers)
  const floor = groups.filter((g) => g.exposure === "baseline")
  const active = groups.filter((g) => g.exposure !== "baseline")
  const newsStale = feedHealth(live).find((f) => f.key === "news")?.state !== "ok"

  const jump = (id: string) => document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" })

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        {live && (
          <span
            title={`Signals feeding the SDI now: ${comp.filter((c) => !c.missing).map((c) => c.label).join(", ")}.${comp.some((c) => c.missing) ? ` Missing: ${comp.filter((c) => c.missing).map((c) => c.label).join(", ")}.` : ""}`}
            className={`flex h-9 items-center gap-2 rounded-full border px-3.5 text-xs font-semibold ${liveSignals === 4 ? "border-safe-line bg-safe-soft text-safe" : "border-warn-line bg-warn-soft text-warn"}`}
          >
            <span className="flex gap-0.5">
              {comp.map((c) => <span key={c.key} className="h-3 w-1.5 rounded-sm" style={{ background: c.missing ? "var(--x-3a3014)" : liveSignals === 4 ? "var(--x-3fcf8e)" : "var(--x-f2c14e)" }} />)}
            </span>
            {liveSignals} of 4 signals live
          </span>
        )}
        {/* Phones: jump between the four stacked boxes. */}
        <div role="group" aria-label="Jump to section" className="grid w-full grid-cols-4 rounded-xl border border-line bg-panel p-1 lg:hidden">
          {[["ri-ev", "Events"], ["ri-sdi", "SDI"], ["ri-cp", "Chokepts"], ["ri-pr", "Producers"]].map(([id, l]) => (
            <button key={id} type="button" onClick={() => jump(id)} className="min-h-10 rounded-[9px] text-xs text-muted hover:bg-track hover:text-head">{l}</button>
          ))}
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:gap-5 xl:grid-cols-2">
        {/* 1 · Events */}
        <Panel id="ri-ev" className="min-w-0 flex min-h-[440px] scroll-mt-28 flex-col gap-3 p-5 lg:p-[22px]">
          <div className="flex items-baseline justify-between">
            <h2 className="text-[15px] font-bold text-head">Sentinel risk events</h2>
            <span className={`font-mono text-[11px] ${newsStale ? "text-warn" : "text-dim"}`}>newest {ago(events[0]?.scored_at)}</span>
          </div>
          <div className="no-scrollbar flex gap-1.5 overflow-x-auto">
            {[["all", `All ${visibleEvents.length}`], ...types.map(([t, n]) => [t, `${titleCase(t)} ${n}`])].map(([t, l]) => (
              <button
                key={t}
                type="button"
                aria-pressed={type === t}
                onClick={() => setType(t)}
                className={`shrink-0 rounded-full px-2.5 py-1.5 text-[11px] ${type === t ? "bg-fg font-semibold text-ground" : "border border-edge text-muted"}`}
              >
                {l}
              </button>
            ))}
          </div>
          <div className="flex max-h-[420px] flex-col overflow-y-auto">
            {list.length ? list.slice(0, 20).map((e) => (
              <button key={e.id} type="button" onClick={() => open({ kind: "event", id: e.id })} className="flex min-h-[60px] gap-3 border-t border-hair py-3 text-left">
                <SevChip v={e.severity} />
                <span className="flex min-w-0 flex-col gap-1">
                  <span className="line-clamp-2 text-[13px] text-head">{e.summary.split(/(?<=\.)\s/)[0]}</span>
                  <span className="font-mono text-[11px] text-dim">{e.region} · {titleCase(e.disruption_type)} · {shortDate(e.scored_at)}</span>
                </span>
              </button>
            )) : <p className="py-6 text-sm text-dim">No events match the filters.</p>}
          </div>
        </Panel>

        {/* 2 · SDI timeline */}
        <Panel id="ri-sdi" className="min-w-0 flex min-h-[440px] scroll-mt-28 flex-col gap-3.5 p-5 lg:p-[22px]">
          <div className="flex items-baseline justify-between">
            <h2 className="text-[15px] font-bold text-head">SDI timeline</h2>
            {live && <span className="font-mono text-[11px] text-dim">{live.sdi_score.toFixed(1)} now · {live.sdi_band}</span>}
          </div>
          <SdiTrace points={timeline} events={events} height={230} />
          <div className="mt-auto grid grid-cols-4 gap-2.5 border-t border-hair pt-3">
            {comp.map((c) => (
              <div key={c.key} className="flex flex-col gap-1">
                <span className="text-[11px] text-muted">{c.short}</span>
                <span className="font-mono text-[15px]" style={{ color: c.missing ? "var(--x-ff8a8d)" : "var(--x-f5f7fa)" }}>{c.missing ? "—" : c.pts.toFixed(1)}</span>
              </div>
            ))}
          </div>
        </Panel>

        {/* 3 · Chokepoints */}
        <Panel id="ri-cp" className="min-w-0 flex min-h-[440px] scroll-mt-28 flex-col p-5 lg:p-[22px]">
          <h2 className="mb-2 text-[15px] font-bold text-head">Chokepoint risk matrix</h2>
          <div className="grid grid-cols-[minmax(0,1fr)_56px_40px_40px] gap-2.5 pb-2 font-mono text-[10px] tracking-[0.1em] text-faint sm:grid-cols-[minmax(0,1fr)_110px_52px_64px]">
            <span>CHOKEPOINT</span><span>RISK</span><span className="text-right">SCORE</span><span className="text-right">FLOW</span>
          </div>
          {[...chokepoints].sort((a, b) => b.risk_score - a.risk_score).map((c, i) => (
            <button
              key={c.name}
              type="button"
              onClick={() => open({ kind: "chokepoint", name: c.name })}
              className={`grid min-h-11 grid-cols-[minmax(0,1fr)_56px_40px_40px] items-center gap-2.5 text-left text-[13px] sm:grid-cols-[minmax(0,1fr)_110px_52px_64px] ${
                i === 0 && c.risk_score >= 0.4 ? "-mx-2 rounded-lg bg-orange-soft px-2" : "border-t border-hair"
              }`}
            >
              <span className={`truncate ${i === 0 ? "font-semibold text-head" : "text-fg"}`}>{c.name}</span>
              <Bar value={c.risk_score} color={riskColor(c.risk_score)} />
              <span className="text-right font-mono" style={{ color: riskText(c.risk_score) }}>{c.risk_score.toFixed(2)}</span>
              <span className="text-right font-mono text-dim">{c.flow_mb_day.toFixed(1)}</span>
            </button>
          ))}
        </Panel>

        {/* 4 · Producers */}
        <Panel id="ri-pr" className="min-w-0 flex min-h-[440px] scroll-mt-28 flex-col p-5 lg:p-[22px]">
          <div className="mb-2 flex items-baseline justify-between">
            <h2 className="text-[15px] font-bold text-head">Producer risk matrix</h2>
            <span className="font-mono text-[11px] text-faint">{producers.length} producers · {floor.reduce((a, g) => a + g.names.length, 0)} at floor</span>
          </div>
          <div className="grid grid-cols-[minmax(0,1fr)_54px_56px_36px] gap-2.5 pb-2 font-mono text-[10px] tracking-[0.1em] text-faint sm:grid-cols-[minmax(0,1fr)_84px_110px_48px]">
            <span>PRODUCER</span><span>EXPOSURE</span><span>RISK</span><span className="text-right">SCORE</span>
          </div>
          {[...active, ...(showFloor ? floor : [])].map((g) => (
            <button
              key={g.names.join()}
              type="button"
              onClick={() => open({ kind: "producer", name: g.names[0] })}
              className="grid min-h-11 grid-cols-[minmax(0,1fr)_54px_56px_36px] items-center gap-2.5 border-t border-hair py-1.5 text-left text-[13px] sm:grid-cols-[minmax(0,1fr)_84px_110px_48px]"
            >
              <span className="text-head">{g.names.join(" · ")}</span>
              <span className="font-mono text-[11px]" style={{ color: EXPOSURE_COLOR[g.exposure] ?? "var(--x-aeb8c5)" }}>{g.exposure}</span>
              <Bar value={g.score} color={riskColor(g.score)} />
              <span className="text-right font-mono" style={{ color: riskText(g.score) }}>{fmt(g.score)}</span>
            </button>
          ))}
          {floor.length > 0 && (
            <button type="button" onClick={() => setShowFloor((v) => !v)} className="mt-auto self-start pt-3 text-xs text-dim">
              {showFloor ? "Hide" : `${floor.reduce((a, g) => a + g.names.length, 0)} more at the baseline floor —`}{" "}
              <span className="font-semibold text-accent">{showFloor ? "" : "show"}</span>
            </button>
          )}
        </Panel>
      </div>

      <button type="button" onClick={() => go("history")} className="self-start text-[13px] font-semibold text-accent lg:hidden">
        Backtests →
      </button>
    </div>
  )
}
