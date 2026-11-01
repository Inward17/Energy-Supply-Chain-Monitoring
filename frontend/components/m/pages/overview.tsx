"use client"

import { useEffect, useState } from "react"
import { fetchChokepointDetail, type ChokepointDetail } from "@/lib/api"
import { components, healthSummary, useData } from "../data"
import { useDetail } from "../detail"
import { SdiTrace, biggestJump } from "../charts"
import { Eyebrow, Gauge, Loading, Panel, Ring, SevChip, Spark, ago, fmt, riskText, shortDate, titleCase } from "../ui"
import type { PageKey } from "../shell"

export function Overview({ go, openHealth }: { go: (p: PageKey) => void; openHealth: () => void }) {
  const { live, failed, timeline, chokepoints, visibleEvents, events, market, loading } = useData()
  const open = useDetail()
  const [driver, setDriver] = useState<ChokepointDetail | null>(null)
  const top = [...chokepoints].sort((a, b) => b.risk_score - a.risk_score)[0]

  useEffect(() => {
    if (!top?.name) return
    fetchChokepointDetail(top.name).then(setDriver).catch(() => setDriver(null))
  }, [top?.name])

  if (loading && !live) return <Loading label="Loading snapshot…" />
  if (!live) {
    return (
      <Panel className="p-6">
        <p className="text-sm text-fg">The backend did not answer, so there is nothing to show yet.</p>
        <button type="button" onClick={openHealth} className="mt-3 text-sm font-semibold text-accent">Open data health →</button>
      </Panel>
    )
  }

  const health = healthSummary(live, failed)
  const comp = components(live)
  const missing = comp.filter((c) => c.missing)
  const brent = market?.instruments.find((i) => i.ticker === "BZ=F")
  const brentVals = brent?.series.slice(-12).map((p) => p.price) ?? []
  const brentChg = brentVals.length > 1 ? ((brentVals[brentVals.length - 1] - brentVals[0]) / brentVals[0]) * 100 : null
  // Backend count is decay-aware; old events above 0.45 are not "active".
  const alertCount = live.active_alerts
  const alerts = events.filter((e) => e.severity >= 0.45).slice(0, Math.min(3, alertCount))
  const newest = events[0]?.scored_at
  const evStale = health.problems.some((p) => p.key === "news")
  const aisDown = health.problems.find((p) => p.key === "ais")
  const jump = biggestJump(timeline)
  const dials = [...chokepoints].sort((a, b) => b.risk_score - a.risk_score).slice(0, 6)

  return (
    <div className="flex flex-col gap-4 lg:gap-5">
      {health.level !== "ok" && (
        <button
          type="button"
          onClick={openHealth}
          className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-warn-boxline bg-warn-box px-4 py-3 text-left"
        >
          <span className="flex items-start gap-3 text-[13px] leading-relaxed text-fg">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="var(--x-f2c14e)" strokeWidth="2" aria-hidden="true" className="mt-0.5 shrink-0"><path d="M12 3l10 18H2z" /><path d="M12 10v5M12 18v.5" /></svg>
            <span>
              <strong className="text-head">Partial data.</strong>{" "}
              {missing.length
                ? `SDI uses ${4 - missing.length} of 4 signals — ${missing.map((m) => m.label.toLowerCase()).join(", ")} is missing, so the score may read low.`
                : `${health.problems.map((p) => p.name).join(" and ")} ${health.problems.length > 1 ? "need" : "needs"} attention.`}
            </span>
          </span>
          <span className="text-[13px] font-semibold text-warn">View data health →</span>
        </button>
      )}

      {/* Hero */}
      <section aria-labelledby="sdi-h" className="flex flex-wrap gap-4 lg:gap-5">
        <Panel className="relative flex min-w-0 flex-[3_1_560px] flex-col gap-5 overflow-hidden p-5 lg:p-6">
          <div aria-hidden="true" className="dotgrid absolute inset-0 opacity-70" />
          <div className="relative flex items-center justify-between">
            <h2 id="sdi-h" className="eyebrow text-[11px]">Supply disruption index</h2>
            <span className="font-mono text-[11px] text-dim">band {fmt(live.confidence_low, 1)}–{fmt(live.confidence_high, 1)}</span>
          </div>
          <div className="relative flex flex-wrap items-center gap-7">
            <Gauge score={live.sdi_score} band={live.sdi_band} />
            <div className="flex min-w-0 flex-[1_1_280px] flex-col gap-2.5">
              <div className="flex items-baseline justify-between gap-2">
                <span className="text-[13px] font-semibold text-fg">Last {timeline.length ? Math.max(1, Math.round((Date.now() - new Date(timeline[0].scored_at).getTime()) / 86400000)) : 0} days</span>
                {jump != null && <span className="font-mono text-[11px] text-crit-text">largest move {jump > 0 ? "+" : ""}{jump.toFixed(1)}</span>}
              </div>
              <SdiTrace points={timeline} events={events} height={140} compact />
            </div>
          </div>
          <div className="relative grid grid-cols-2 gap-3.5 border-t border-hair pt-4 sm:grid-cols-4">
            {comp.map((c) => (
              <div key={c.key} className="flex flex-col gap-2">
                <span className="text-xs text-muted">{c.label}</span>
                <span className="font-mono text-lg" style={{ color: c.missing ? "var(--x-ff8a8d)" : "var(--x-f5f7fa)" }}>
                  {c.missing ? "—" : c.pts.toFixed(1)}
                  <span className="text-xs text-faint"> /{Math.round(c.max)}</span>
                </span>
                {c.missing ? <span className="hatch block h-1 rounded-full" /> : (
                  <span className="block h-1 rounded-full bg-track"><span className="block h-1 rounded-full bg-accent" style={{ width: `${Math.min(1, c.frac) * 100}%` }} /></span>
                )}
              </div>
            ))}
          </div>
        </Panel>

        <Panel className="flex min-w-0 flex-[2_1_300px] flex-col gap-4 p-5 lg:p-6">
          <h2 className="eyebrow text-[11px]">What is driving it</h2>
          {top ? (
            <>
              <div className="flex items-center gap-4">
                <Ring value={top.risk_score} size={72} stroke={7} />
                <div className="flex flex-col gap-1">
                  <span className="text-xl font-bold text-head [font-stretch:108%]">{top.name}</span>
                  <span className="text-[13px] text-muted">
                    {top.flow_mb_day.toFixed(1)} mbpd · +${fmt(top.price_impact_usd)}/bbl on Brent
                  </span>
                </div>
              </div>
              {driver?.driver && (
                <div className="flex flex-col gap-1.5 rounded-xl border border-line bg-well p-3.5">
                  <span className="font-mono text-[10px] tracking-[0.1em] text-crit-text">
                    SETS SCORE · {driver.driver.severity.toFixed(2)} · {driver.driver.region?.toUpperCase()}
                  </span>
                  <span className="line-clamp-3 text-[13px] leading-relaxed text-fg">{driver.driver.summary}</span>
                </div>
              )}
              {!!driver?.dependent_producers.length && (
                <div className="flex flex-wrap gap-1.5">
                  {driver.dependent_producers.slice(0, 4).map((p) => (
                    <span key={p} className="rounded-md bg-raise px-2.5 py-1 text-xs text-soft">{p}</span>
                  ))}
                  {driver.dependent_producers.length > 4 && (
                    <span className="rounded-md bg-raise px-2.5 py-1 text-xs text-soft">+{driver.dependent_producers.length - 4} exposed</span>
                  )}
                </div>
              )}
              <button type="button" onClick={() => open({ kind: "chokepoint", name: top.name })} className="mt-auto self-start text-[13px] font-semibold text-accent">
                Why this score →
              </button>
            </>
          ) : (
            <p className="text-sm text-dim">No chokepoint data.</p>
          )}
        </Panel>
      </section>

      {/* Signals */}
      <section aria-label="Signals" className="no-scrollbar -mr-4 flex gap-3 overflow-x-auto pr-4 sm:mr-0 sm:grid sm:grid-cols-2 sm:overflow-visible sm:pr-0 lg:grid-cols-4">
        <div className="panel relative flex w-[156px] shrink-0 flex-col gap-1.5 overflow-hidden rounded-[14px] p-[18px] pb-14 sm:w-auto">
          <div className="flex items-center justify-between"><Eyebrow>Brent spot</Eyebrow>{brentChg != null && <span className="font-mono text-[11px]" style={{ color: brentChg >= 0 ? "var(--x-ff8a8d)" : "var(--x-6fe0ab)" }}>{brentChg >= 0 ? "▲" : "▼"} {Math.abs(brentChg).toFixed(1)}%</span>}</div>
          <span className="text-[28px] font-[300] tracking-[-0.02em] text-head">${fmt(live.current_brent)}</span>
          <span className="flex items-center gap-1.5 font-mono text-[11px] text-dim"><span className="h-1.5 w-1.5 rounded-full bg-safe" />close {shortDate(live.market_source_date)}</span>
          <div className="absolute inset-x-0 bottom-0"><Spark values={brentVals} height={44} /></div>
        </div>
        <div className="panel flex w-[156px] shrink-0 flex-col gap-1.5 rounded-[14px] p-[18px] sm:w-auto">
          <div className="flex items-center justify-between"><Eyebrow>Freight stress</Eyebrow><span className="font-mono text-[11px] text-dim">BOAT ${fmt(live.current_freight)}</span></div>
          <span className="text-[28px] font-[300] tracking-[-0.02em] text-head">{fmt(live.delta_f)}</span>
          <span className="flex items-center gap-1.5 font-mono text-[11px] text-dim"><span className="h-1.5 w-1.5 rounded-full bg-safe" />close {shortDate(live.market_source_date)}</span>
          <div className="mt-auto flex gap-0.5 pt-2.5">
            {Array.from({ length: 10 }, (_, i) => (
              <span key={i} className="h-2 flex-1 rounded-sm" style={{ background: i < Math.round(live.delta_f * 10) ? "var(--x-5aaeff)" : "var(--x-1a2330)" }} />
            ))}
          </div>
        </div>
        <div className="panel flex w-[156px] shrink-0 flex-col gap-1.5 rounded-[14px] p-[18px] sm:w-auto">
          <div className="flex items-center justify-between"><Eyebrow>Active alerts</Eyebrow>{evStale && <span className="font-mono text-[11px] text-warn">stale</span>}</div>
          <span className="text-[28px] font-[300] tracking-[-0.02em] text-soft">{alertCount}</span>
          <span className={`flex items-center gap-1.5 font-mono text-[11px] ${evStale ? "text-warn" : "text-dim"}`}><span className={`h-1.5 w-1.5 rounded-full ${evStale ? "bg-warn" : "bg-safe"}`} />newest {ago(newest)}</span>
          <div className="mt-auto flex flex-wrap gap-1.5 pt-2.5">
            {alerts.slice(0, 3).map((a) => <SevChip key={a.id} v={a.severity} />)}
          </div>
        </div>
        {aisDown ? (
          <div className="hatch-card flex w-[156px] shrink-0 flex-col gap-1.5 rounded-[14px] border border-dashed border-[var(--x-4a2224)] p-[18px] sm:w-auto">
            <div className="flex items-center justify-between"><Eyebrow>Vessel density</Eyebrow><span className="font-mono text-[11px] text-crit-text">offline</span></div>
            <span className="text-[28px] font-[300] text-faint">—</span>
            <span className="text-xs leading-snug text-muted">AIS {aisDown.state === "down" ? "offline" : "partial"}. Not counted in the SDI.</span>
            <button type="button" onClick={openHealth} className="mt-auto self-start text-xs font-semibold text-accent">Check feed →</button>
          </div>
        ) : (
          <div className="panel flex w-[156px] shrink-0 flex-col gap-1.5 rounded-[14px] p-[18px] sm:w-auto">
            <div className="flex items-center justify-between"><Eyebrow>Vessel density</Eyebrow><span className="h-1.5 w-1.5 rounded-full bg-safe" /></div>
            <span className="text-[28px] font-[300] text-head">{fmt(live.delta_d)}</span>
            <span className="font-mono text-[11px] text-dim">{live.vessel_count} vessels · {ago(live.vessel_source_at)}</span>
          </div>
        )}
      </section>

      <section className="flex flex-wrap gap-4 lg:gap-5">
        <Panel className="flex min-w-0 flex-[1_1_420px] flex-col gap-3.5 p-5">
          <div className="flex items-baseline justify-between">
            <h2 className="text-[15px] font-bold text-head">Chokepoints</h2>
            <button type="button" onClick={() => go("risk")} className="text-xs font-semibold text-accent">All {chokepoints.length} →</button>
          </div>
          <div className="grid grid-cols-3 gap-2.5">
            {dials.map((c, i) => (
              <button
                key={c.name}
                type="button"
                onClick={() => open({ kind: "chokepoint", name: c.name })}
                className={`flex flex-col items-center gap-2 rounded-xl border px-2 py-3.5 ${i === 0 && c.risk_score >= 0.4 ? "border-orange-line bg-orange-soft" : "border-hair bg-well"}`}
              >
                <Ring value={c.risk_score} />
                <span className={`text-center text-xs ${i === 0 ? "font-semibold text-head" : "text-fg"}`}>{c.name.replace("Strait of ", "").replace("Canal", "Canal")}</span>
                <span className="font-mono text-[10px] text-dim">{c.flow_mb_day.toFixed(1)} mbpd</span>
              </button>
            ))}
          </div>
        </Panel>

        <Panel className="flex min-w-0 flex-[1_1_420px] flex-col gap-3.5 p-5">
          <div className="flex items-baseline justify-between">
            <h2 className="text-[15px] font-bold text-head">Sentinel feed</h2>
            <span className={`font-mono text-[11px] ${evStale ? "text-warn" : "text-dim"}`}>newest {ago(newest)}</span>
          </div>
          {visibleEvents.length ? (
            <ol className="relative flex flex-col">
              <li aria-hidden="true" className="absolute bottom-2 left-[7px] top-2 w-0.5 bg-hair" />
              {visibleEvents.slice(0, 4).map((e) => (
                <li key={e.id} className="relative flex gap-3.5 py-1.5 pb-3.5">
                  <span
                    className="z-[1] mt-[3px] h-4 w-4 shrink-0 rounded-full border-[3px]"
                    style={{ borderColor: riskText(e.severity) === "var(--x-aeb8c5)" ? "var(--x-3fcf8e)" : riskText(e.severity), background: e.severity >= 0.7 ? "var(--x-ff5a5f)" : "var(--x-0e1319)" }}
                  />
                  <button type="button" onClick={() => open({ kind: "event", id: e.id })} className="flex min-w-0 flex-1 flex-col gap-1 text-left">
                    <span className="flex justify-between gap-2">
                      <span className="line-clamp-2 text-[13px] leading-snug text-head">{e.summary.split(/(?<=\.)\s/)[0]}</span>
                      <span className="font-mono text-xs" style={{ color: riskText(e.severity) }}>{e.severity.toFixed(2)}</span>
                    </span>
                    <span className="font-mono text-[11px] text-dim">{shortDate(e.scored_at)} · {e.region} · {titleCase(e.disruption_type)}</span>
                  </button>
                </li>
              ))}
            </ol>
          ) : (
            <p className="text-sm text-dim">No events match the current filters.</p>
          )}
          <button type="button" onClick={() => go("risk")} className="mt-auto self-start text-[13px] font-semibold text-accent">All events →</button>
        </Panel>
      </section>
    </div>
  )
}
