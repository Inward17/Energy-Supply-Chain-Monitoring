"use client"

import { useCallback, useEffect, useState } from "react"
import { fetchBacktest, fetchBacktestJobs, triggerBacktest, type BacktestJob, type BacktestResult } from "@/lib/api"
import { LineChart } from "../charts"
import { ErrorNote, Eyebrow, Loading, Panel } from "../ui"

const EVENTS = [
  { id: "red_sea_attacks", name: "Red Sea attacks", span: "Nov 2023 – Jan 2024" },
  { id: "israel_iran_war_2025", name: "Israel–Iran war", span: "May – Jun 2025" },
  { id: "russia_ukraine_buildup", name: "Russia–Ukraine build-up", span: "Dec 2021 – Feb 2022" },
]

const NEWS_GAP_SDI = 35 // a day with no scored headlines lands near 20–30

const longDate = (d?: string | null) =>
  d ? new Date(d).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" }) : "—"

/** The API only ever returns fixed, reader-facing failure messages. */
function explain(job: BacktestJob): string {
  return job.error_log || "The run stopped without an error message."
}

export function HistoryPage() {
  const [sel, setSel] = useState(EVENTS[0].id)
  const [res, setRes] = useState<BacktestResult | null>(null)
  const [jobs, setJobs] = useState<BacktestJob[]>([])
  const [err, setErr] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [triggering, setTriggering] = useState(false)

  const load = useCallback((id: string) => {
    setLoading(true)
    setErr(null)
    fetchBacktest(id)
      .then(setRes)
      .catch(() => { setRes(null); setErr("No completed backtest for this event yet.") })
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => load(sel), [sel, load])

  const running = jobs.some((j) => j.status === "pending" || j.status === "running")
  useEffect(() => {
    const tick = () => fetchBacktestJobs().then(setJobs).catch(() => {})
    tick()
    if (!running) return
    const id = window.setInterval(tick, 5000)
    return () => window.clearInterval(id)
  }, [running])

  // Reload the chart when a run for the selected event completes.
  const latest = (id: string) => jobs.filter((j) => j.event_name === id).sort((a, b) => b.id - a.id)[0]
  const selJob = latest(sel)
  useEffect(() => {
    if (selJob?.status === "completed") load(sel)
  }, [selJob?.status, sel, load])

  const run = async () => {
    setTriggering(true)
    try {
      await triggerBacktest(sel)
      setJobs(await fetchBacktestJobs())
    } catch {
      setErr("Could not start the backtest — another run may be in progress.")
    } finally {
      setTriggering(false)
    }
  }

  const series = res?.series ?? []
  const sdi = series.map((p) => p.sdi_score)
  const brent = series.map((p) => p.brent_price)
  const bLo = brent.length ? Math.min(...brent) - 1 : 0
  const bHi = brent.length ? Math.max(...brent) + 1 : 1
  const idx = (d?: string | null) => (d ? series.findIndex((p) => p.date.slice(0, 10) === d.slice(0, 10)) : -1)
  const ai = idx(res?.system_alert_date), mi = idx(res?.market_reaction_date)
  const thr = res?.sdi_threshold ?? 65
  const gapDays = sdi.filter((v) => v < NEWS_GAP_SDI).length
  const sens = res?.threshold_sensitivity ?? []
  const maxLead = Math.max(1, ...sens.map((s) => Math.abs(s.lead_time_days)))

  return (
    <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:gap-5">
      <aside aria-label="Backtests" className="no-scrollbar -mr-4 flex gap-2.5 overflow-x-auto pr-4 lg:mr-0 lg:w-[280px] lg:shrink-0 lg:flex-col lg:overflow-visible lg:pr-0">
        {EVENTS.map((ev) => {
          const j = latest(ev.id)
          const on = ev.id === sel
          const failed = j?.status === "failed"
          const busy = j?.status === "running" || j?.status === "pending"
          return (
            <div
              key={ev.id}
              className={`flex w-[200px] shrink-0 flex-col gap-1.5 rounded-[14px] border p-4 lg:w-auto ${
                on ? "border-accent-line bg-accent-soft" : failed ? "border-crit-line bg-crit-soft" : "border-line bg-panel"
              }`}
            >
              <button type="button" onClick={() => setSel(ev.id)} aria-pressed={on} className="flex flex-col gap-1 text-left">
                <span className="text-sm font-bold text-head">{ev.name}</span>
                <span className="font-mono text-[11px] text-dim">{ev.span}</span>
                {busy && <span className="font-mono text-[11px] text-accent">running {j.progress_pct ?? 0}% · {j.progress_note}</span>}
                {failed && <span className="font-mono text-[11px] text-crit-text">failed at {j.progress_pct ?? 0}%</span>}
              </button>
              {failed && <span className="text-xs leading-snug text-muted">{explain(j)}</span>}
            </div>
          )
        })}
        <button
          type="button"
          onClick={() => void run()}
          disabled={triggering || running}
          className="h-11 shrink-0 rounded-[10px] bg-accent px-4 text-[13px] font-bold text-[var(--x-06121f)] disabled:opacity-50"
        >
          {running ? "Backtest running…" : triggering ? "Starting…" : selJob?.status === "failed" ? "Retry this backtest" : "Run backtest"}
        </button>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col gap-4 lg:gap-5">
        {loading && <Loading label="Loading backtest…" />}
        {err && !loading && <ErrorNote message={err} />}
        {res && !loading && (
          <>
            <section className="grid grid-cols-2 gap-3 lg:grid-cols-3">
              <div className={`col-span-2 flex flex-col gap-1 rounded-2xl border p-[18px] lg:col-span-1 ${res.lead_time_days > 0 ? "border-safe-line bg-safe-soft" : "border-crit-line bg-crit-soft"}`}>
                <span className={`eyebrow ${res.lead_time_days > 0 ? "text-safe" : "text-crit-text"}`}>{res.lead_time_days > 0 ? "Early warning" : "No early warning"}</span>
                <span className="text-[38px] font-bold text-head [font-stretch:108%]">{Math.abs(res.lead_time_days)} days</span>
                <span className="text-xs text-muted">{res.lead_time_days > 0 ? "before Brent broke out" : "after Brent moved"}</span>
              </div>
              <div className="panel flex flex-col gap-1 rounded-2xl p-[18px]"><Eyebrow>SDI alert ≥ {thr}</Eyebrow><span className="text-lg font-bold text-head lg:text-[22px]">{longDate(res.system_alert_date)}</span></div>
              <div className="panel flex flex-col gap-1 rounded-2xl p-[18px]"><Eyebrow>Brent &gt;1.5σ</Eyebrow><span className="text-lg font-bold text-head lg:text-[22px]">{longDate(res.market_reaction_date)}</span></div>
            </section>

            <Panel as="figure" className="m-0 flex flex-col gap-3 p-4 lg:p-[22px]">
              <div className="flex flex-wrap items-baseline justify-between gap-2.5">
                <span className="text-[15px] font-bold text-head">{EVENTS.find((e) => e.id === sel)?.name} · SDI vs Brent</span>
                <div className="flex gap-3.5 font-mono text-[11px] text-dim">
                  <span className="flex items-center gap-1.5"><span className="h-[3px] w-3.5 bg-accent" />SDI</span>
                  <span className="flex items-center gap-1.5"><span className="h-[3px] w-3.5 bg-[var(--x-ffb86b)]" />Brent (${bLo.toFixed(0)}–{bHi.toFixed(0)})</span>
                </div>
              </div>
              <LineChart
                label={`SDI and Brent across ${series.length} days. ${ai >= 0 ? `SDI crossed ${thr} on ${longDate(res.system_alert_date)}.` : ""} ${mi >= 0 ? `Brent broke out on ${longDate(res.market_reaction_date)}.` : ""}`}
                yMin={0}
                yMax={100}
                series={[
                  { values: brent.map((b) => ((b - bLo) / (bHi - bLo || 1)) * 100), color: "var(--x-ffb86b)", width: 1.5, opacity: 0.85 },
                  { values: sdi, color: "var(--x-5aaeff)", width: 2 },
                ]}
              >
                {(sx, sy, W) => (
                  <>
                    <line x1="0" y1={sy(thr)} x2={W} y2={sy(thr)} stroke="var(--x-f2c14e)" strokeDasharray="4 4" />
                    <text x={W - 4} y={sy(thr) - 5} textAnchor="end" fill="var(--x-f2c14e)" fontFamily="var(--font-plex-mono)" fontSize="10">alert {thr}</text>
                    {ai >= 0 && mi > ai && <rect x={sx(ai)} y={sy(100)} width={sx(mi) - sx(ai)} height={sy(0) - sy(100)} fill="var(--x-5aaeff)" fillOpacity="0.06" />}
                    {ai >= 0 && (<><line x1={sx(ai)} y1={sy(100)} x2={sx(ai)} y2={sy(0)} stroke="var(--x-5aaeff)" /><text x={sx(ai) + 5} y={sy(94)} fill="var(--x-5aaeff)" fontFamily="var(--font-plex-mono)" fontSize="10">SDI alert</text></>)}
                    {mi >= 0 && (<><line x1={sx(mi)} y1={sy(100)} x2={sx(mi)} y2={sy(0)} stroke="var(--x-ffb86b)" /><text x={sx(mi) + 5} y={sy(94)} fill="var(--x-ffb86b)" fontFamily="var(--font-plex-mono)" fontSize="10">Brent &gt;1.5σ</text></>)}
                    {ai >= 0 && mi > ai && <text x={(sx(ai) + sx(mi)) / 2} y={sy(84)} textAnchor="middle" fill="var(--x-9cceff)" fontFamily="var(--font-plex-mono)" fontSize="11">← {res.lead_time_days} days →</text>}
                    <text x="0" y={sy(0) + 16} fill="var(--x-7a8697)" fontFamily="var(--font-plex-mono)" fontSize="10">{longDate(series[0]?.date)}</text>
                    <text x={W} y={sy(0) + 16} textAnchor="end" fill="var(--x-7a8697)" fontFamily="var(--font-plex-mono)" fontSize="10">{longDate(series[series.length - 1]?.date)}</text>
                  </>
                )}
              </LineChart>
              {gapDays > 0 && (
                <div className="flex items-start gap-2.5 rounded-xl border border-warn-boxline bg-warn-box px-3.5 py-3">
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--x-f2c14e)" strokeWidth="2" aria-hidden="true" className="mt-0.5 shrink-0"><path d="M12 3l10 18H2z" /><path d="M12 10v5M12 18v.5" /></svg>
                  <span className="text-xs leading-relaxed text-fg">
                    {gapDays} of {series.length} days had no scored headlines, so the SDI drops to ~25 on those days. Those dips are missing news, not calm — read the upper envelope.
                  </span>
                </div>
              )}
            </Panel>

            {sens.length > 0 && (
              <Panel className="flex flex-col gap-3 p-4 lg:p-[22px]">
                <div className="flex items-baseline justify-between">
                  <h2 className="text-[15px] font-bold text-head">Threshold sensitivity</h2>
                  <span className="font-mono text-[11px] text-faint">days of warning per alert level</span>
                </div>
                <div className="grid grid-cols-[48px_1fr_72px] items-center gap-x-3 gap-y-2 font-mono text-xs">
                  {sens.map((s) => {
                    const cur = s.threshold === thr
                    const late = s.lead_time_days < 0
                    const none = !s.alert_date
                    return [
                      <span key={`t${s.threshold}`} className={cur ? "font-semibold text-head" : "text-muted"}>{s.threshold}{cur ? " ←" : ""}</span>,
                      <div key={`b${s.threshold}`} className={`h-3.5 rounded-sm ${late ? "hatch" : ""}`} style={{ width: none ? "2%" : `${(Math.abs(s.lead_time_days) / maxLead) * 100}%`, background: late ? undefined : cur ? "var(--x-3fcf8e)" : s.lead_time_days < 10 ? "var(--x-6b5a24)" : "var(--x-1f4a36)" }} />,
                      <span key={`v${s.threshold}`} className={`text-right ${none ? "text-faint" : late ? "text-crit-text" : s.lead_time_days < 10 ? "text-warn" : "text-head"}`}>
                        {none ? "never" : late ? `${-s.lead_time_days} d late` : `${s.lead_time_days} d`}
                      </span>,
                    ]
                  })}
                </div>
              </Panel>
            )}
          </>
        )}
      </div>
    </div>
  )
}
