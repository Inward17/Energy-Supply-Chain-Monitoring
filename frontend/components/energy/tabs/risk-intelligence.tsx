"use client"

import { useCallback, useEffect, useRef, useState } from "react"

import {
  CartesianGrid,
  Line,
  ComposedChart,
  Area,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts"
import { Panel, SeverityBadge, SEVERITY_BORDER_L } from "../ui"
import { fetchRiskEvents, fetchChokepointMatrix, fetchSdiTimeline, fetchLiveMetrics, fetchRiskEventDetail, fetchProducerMatrix, fetchChokepointDetail, fetchProducerDetail, type RiskEvent, type RiskEventDetail, type ChokepointRisk, type SdiPoint, type LiveMetrics, type ProducerRisk, type ChokepointDetail, type ProducerDetail } from "@/lib/api"
import { ChokepointDetailModal, ProducerDetailModal } from "./risk-detail-modal"
import { chartTooltip } from "../chart-tooltip"
import { useChartTheme } from "../chart-theme"
import { InfoTooltip } from "@/components/ui/info-tooltip"
import { Loader2, ExternalLink } from "lucide-react"
import { EventDetailModal } from "./event-detail-modal"

type RiskIntelligenceProps = {
  autoRefresh: boolean
  refreshToken: number
  onRefreshComplete: (target: "kpi" | "risk", refreshToken: number) => void
}

type TimelinePoint = SdiPoint & {
  sdi_range: [number, number]
  sdi: number
}

export function RiskIntelligence({ autoRefresh, refreshToken, onRefreshComplete }: RiskIntelligenceProps) {
  const [events, setEvents] = useState<RiskEvent[]>([])
  const [matrix, setMatrix] = useState<ChokepointRisk[]>([])
  const [producers, setProducers] = useState<ProducerRisk[]>([])
  const [timeline, setTimeline] = useState<TimelinePoint[]>([])
  const [live, setLive] = useState<LiveMetrics | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const mountedRef = useRef(true)
  const hasLoadedRef = useRef(false)
  const inFlightRef = useRef<Promise<void> | null>(null)
  const detailRequestRef = useRef(0)

  const [selectedEventDetail, setSelectedEventDetail] = useState<RiskEventDetail | null>(null)
  const [detailLoadingId, setDetailLoadingId] = useState<number | null>(null)
  const [chokepointDetail, setChokepointDetail] = useState<ChokepointDetail | null>(null)
  const [producerDetail, setProducerDetail] = useState<ProducerDetail | null>(null)
  const [rowLoading, setRowLoading] = useState<string | null>(null)
  const ct = useChartTheme()

  const openChokepoint = async (name: string) => {
    setRowLoading(name)
    try {
      setChokepointDetail(await fetchChokepointDetail(name))
    } catch (err) {
      console.error("Failed to fetch chokepoint detail:", err)
    } finally {
      setRowLoading(null)
    }
  }

  const openProducer = async (name: string) => {
    setRowLoading(name)
    try {
      setProducerDetail(await fetchProducerDetail(name))
    } catch (err) {
      console.error("Failed to fetch producer detail:", err)
    } finally {
      setRowLoading(null)
    }
  }

  const load = useCallback(() => {
    if (inFlightRef.current) return inFlightRef.current

    const request = (async () => {
      try {
        const [evs, mat, tim, liv, prods] = await Promise.all([
          fetchRiskEvents(),
          fetchChokepointMatrix(),
          fetchSdiTimeline(),
          fetchLiveMetrics(),
          fetchProducerMatrix(),
        ])
        if (!mountedRef.current) return

        setEvents(evs)
        setMatrix(mat)
        setProducers(prods ?? [])

        // Map timeline to include an array for the confidence band Area
        const timelineWithBands = tim.map((t): TimelinePoint => ({
          ...t,
          sdi_range: [t.confidence_low, t.confidence_high],
          sdi: t.sdi_score
        }))
        setTimeline(timelineWithBands)
        setLive(liv)
        setError(null)
        hasLoadedRef.current = true
      } catch (err) {
        console.error("Failed to load risk intelligence:", err)
        if (mountedRef.current && !hasLoadedRef.current) setError(String(err))
      } finally {
        if (mountedRef.current) setLoading(false)
      }
    })()

    inFlightRef.current = request
    void request.finally(() => {
      if (inFlightRef.current === request) inFlightRef.current = null
    })
    return request
  }, [])

  useEffect(() => {
    mountedRef.current = true
    void load()
    return () => {
      mountedRef.current = false
      detailRequestRef.current += 1
    }
  }, [load])

  useEffect(() => {
    if (!autoRefresh) return

    void load()
    const interval = window.setInterval(() => void load(), 30_000)
    return () => window.clearInterval(interval)
  }, [autoRefresh, load])

  useEffect(() => {
    if (refreshToken === 0) return
    void load().finally(() => onRefreshComplete("risk", refreshToken))
  }, [load, onRefreshComplete, refreshToken])

  const handleEventClick = async (eventId: number) => {
    const requestId = detailRequestRef.current + 1
    detailRequestRef.current = requestId
    setDetailLoadingId(eventId)
    try {
      const detail = await fetchRiskEventDetail(eventId)
      if (mountedRef.current && detailRequestRef.current === requestId) {
        setSelectedEventDetail(detail)
      }
    } catch (err) {
      console.error("Failed to fetch event detail:", err)
    } finally {
      if (mountedRef.current && detailRequestRef.current === requestId) {
        setDetailLoadingId(null)
      }
    }
  }

  // Map from DB disruption_type to display title
  const eventTitle = (type: string) =>
    type.split("_").map((w) => w.charAt(0).toUpperCase() + w.slice(1)).join(" ")

  // Format time from ISO string to relative display
  const timeAgo = (iso: string) => {
    try {
      const diff = Date.now() - new Date(iso).getTime()
      const mins = Math.floor(diff / 60000)
      if (mins < 60) return `${mins}m ago`
      if (mins < 1440) return `${Math.floor(mins / 60)}h ago`
      return `${Math.floor(mins / 1440)}d ago`
    } catch { return iso.slice(0, 10) }
  }

  if (loading) {
    return (
      <div className="flex h-[600px] items-center justify-center rounded-lg border border-border bg-panel">
        <Loader2 className="h-8 w-8 animate-spin text-accent" />
      </div>
    )
  }

  if (error) {
    return (
      <div className="p-4 text-crit bg-crit-soft rounded m-4 border border-crit/20">
        Failed to load risk intelligence: {error}
      </div>
    )
  }

  const displayEvents = events
  const displayMatrix = matrix

  return (
    // Four equal quadrants. Each panel is a flex column with a scrolling body so
    // the boxes stay the same height regardless of how much data each holds.
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
      <Panel
        title="Sentinel Risk Events"
        tone="crit"
        className="flex h-[420px] flex-col"
      >
        <div className="flex-1 space-y-2.5 overflow-y-auto p-3 pr-2 [&::-webkit-scrollbar]:w-2 [&::-webkit-scrollbar-track]:bg-transparent [&::-webkit-scrollbar-thumb]:rounded-full [&::-webkit-scrollbar-thumb]:bg-track hover:[&::-webkit-scrollbar-thumb]:bg-muted">
          {displayEvents.length === 0 ? (
            <p className="p-4 text-center text-sm text-muted">No active events.</p>
          ) : (
            displayEvents.map((e) => (
              <article
                key={e.id}
                onClick={() => handleEventClick(e.id)}
                className={`cursor-pointer rounded-lg border border-border bg-panel-2 p-3 transition-colors hover:border-muted hover:bg-hair border-l-2 ${detailLoadingId === e.id ? "opacity-50" : ""} ${
                  SEVERITY_BORDER_L[e.severity_label]
                  }`}
              >
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <h3 className="text-sm font-semibold text-head">{eventTitle(e.disruption_type)}</h3>
                    <p className="text-xs text-accent">{e.region}</p>
                  </div>
                  <SeverityBadge severity={e.severity_label} />
                </div>
                <p className="mt-2 text-xs leading-relaxed text-muted">{e.summary}</p>
                <div className="mt-3 flex items-center justify-between border-t border-border pt-2">
                  <p className="text-[10px] uppercase tracking-wider text-faint">
                    {e.source_fetched_at ? "source " : "scored "}{timeAgo(e.source_fetched_at || e.scored_at)}
                  </p>
                  {e.source_urls && e.source_urls.length > 0 && (
                    <div className="group relative">
                      <button className="text-[10px] uppercase tracking-wider text-muted hover:text-accent flex items-center gap-1">
                        Sources ({e.source_urls.length})
                      </button>
                      <div className="pointer-events-none absolute bottom-full right-0 z-50 mb-2 w-64 opacity-0 transition-opacity group-hover:pointer-events-auto group-hover:opacity-100">
                        <div className="rounded-md border border-border bg-panel p-2 shadow-xl">
                          <p className="mb-2 text-[10px] font-bold uppercase tracking-wider text-muted">GDELT Event Sources</p>
                          <ul className="space-y-1.5 max-h-32 overflow-y-auto pr-1 [&::-webkit-scrollbar]:w-1 [&::-webkit-scrollbar-track]:bg-transparent [&::-webkit-scrollbar-thumb]:rounded-full [&::-webkit-scrollbar-thumb]:bg-track">
                            {e.source_urls.map((url, idx) => {
                              try {
                                const domain = new URL(url).hostname.replace(/^www\./, '')
                                return (
                                  <li key={idx} className="truncate">
                                    <a href={url} target="_blank" rel="noreferrer" className="text-[11px] text-accent hover:underline">
                                      {domain}
                                    </a>
                                  </li>
                                )
                              } catch {
                                return null
                              }
                            })}
                          </ul>
                          {/* Arrow */}
                          <div className="absolute -bottom-1.5 right-4 h-3 w-3 rotate-45 border-b border-r border-border bg-panel" />
                        </div>
                      </div>
                    </div>
                  )}
                </div>
              </article>
            ))
          )}
        </div>
      </Panel>

      <Panel
        title={live ? `SDI: ${Math.round(live.sdi_score)} (range ${Math.round(live.confidence_low)}–${Math.round(live.confidence_high)})` : "SDI Score Timeline"}
        tone="accent"
        className="flex h-[420px] flex-col"
        action={live && <SignalCoverageBadge live={live} />}
      >
          <div className="flex-1 p-4">
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart data={timeline} margin={{ top: 8, right: 12, left: -12, bottom: 0 }}>
                <defs>
                  <linearGradient id="sdiBand" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor={ct.warn} stopOpacity={0.15} />
                    <stop offset="95%" stopColor={ct.warn} stopOpacity={0.0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke={ct.grid} />
                <XAxis dataKey="scored_at" stroke={ct.axis} fontSize={11} tickLine={false} tickFormatter={(val) => val ? new Date(val).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : ""} />
                <YAxis stroke={ct.axis} fontSize={11} tickLine={false} domain={[0, 100]} />
                <Tooltip content={chartTooltip} />
                <Area
                  type="monotone"
                  dataKey="sdi_range"
                  stroke="none"
                  fill="url(#sdiBand)"
                />
                <Line
                  type="monotone"
                  dataKey="sdi_score"
                  stroke={ct.warn}
                  strokeWidth={2}
                  dot={{ r: 2, fill: ct.warn }}
                  activeDot={{ r: 4 }}
                  isAnimationActive={false}
                />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        </Panel>

      <Panel title="Chokepoint Risk Matrix" tone="accent" className="flex h-[420px] flex-col">
          <div className="flex-1 overflow-auto">
            <table className="w-full text-sm">
              <thead className="sticky top-0 z-10 bg-panel">
                <tr className="border-b border-border text-left text-[11px] uppercase tracking-wider text-muted">
                  <th className="px-4 py-2.5 font-medium"><InfoTooltip term="Chokepoint" /></th>
                  <th className="px-4 py-2.5 font-medium">Flow</th>
                  <th className="px-4 py-2.5 font-medium">Risk Score</th>
                  <th className="px-4 py-2.5 font-medium">Price Impact</th>
                </tr>
              </thead>
              <tbody>
                {displayMatrix.map((c) => (
                  <tr
                    key={c.name}
                    onClick={() => openChokepoint(c.name)}
                    title="Click to see why this score was assigned"
                    className={`cursor-pointer border-b border-hair transition-colors last:border-0 hover:bg-hair ${
                      rowLoading === c.name ? "opacity-50" : ""
                    }`}
                  >
                    <td className="px-4 py-2.5 font-medium text-fg">
                      {c.name}
                      {c.inference_source && (
                        <span className="ml-2 text-[10px] italic text-warn">
                          ({c.inference_source})
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-2.5 font-mono text-muted">{c.flow_mb_day.toFixed(1)} mbpd</td>
                    <td className="px-4 py-2.5">
                      <div className="flex items-center gap-2">
                        <div className="h-1.5 w-16 overflow-hidden rounded-full bg-track">
                          <div
                            className={`h-full rounded-full ${c.risk_score > 0.6 ? "bg-crit" : c.risk_score > 0.4 ? "bg-orange" : "bg-safe"
                              }`}
                            style={{ width: `${c.risk_score * 100}%` }}
                          />
                        </div>
                        <span className="font-mono text-xs text-fg">{c.risk_score.toFixed(2)}</span>
                      </div>
                    </td>
                    <td className="px-4 py-2.5 font-mono text-crit">+${c.price_impact_usd.toFixed(2)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
      </Panel>

      <Panel title="Producer Risk Matrix" tone="crit" className="flex h-[420px] flex-col">
        <div className="flex-1 overflow-auto">
          <table className="w-full text-sm">
            <thead className="sticky top-0 z-10 bg-panel">
              <tr className="border-b border-border text-left text-[11px] uppercase tracking-wider text-muted">
                <th className="px-4 py-2.5 font-medium">Producer</th>
                <th className="px-4 py-2.5 font-medium">Risk Score</th>
              </tr>
            </thead>
            <tbody>
              {producers.length === 0 ? (
                <tr>
                  <td colSpan={2} className="px-4 py-6 text-center text-sm text-muted">
                    No producer risk data.
                  </td>
                </tr>
              ) : (
                producers.map((p) => (
                  <tr
                    key={p.name}
                    onClick={() => openProducer(p.name)}
                    title="Click to see why this score was assigned"
                    className={`cursor-pointer border-b border-hair transition-colors last:border-0 hover:bg-hair ${
                      rowLoading === p.name ? "opacity-50" : ""
                    }`}
                  >
                    <td className="max-w-[340px] px-4 py-2.5 font-medium text-fg">
                      <div>{p.name}</div>
                      <div
                        className="flex items-center gap-1 text-[10px] font-normal"
                        title={p.risk_driver ?? undefined}
                      >
                        <span
                          className={
                            p.exposure_type === "direct"
                              ? "shrink-0 uppercase tracking-wide text-crit"
                              : p.exposure_type === "transit"
                                ? "shrink-0 uppercase tracking-wide text-warn"
                                : "shrink-0 uppercase tracking-wide text-faint"
                          }
                        >
                          {p.exposure_type}
                        </span>
                        {p.risk_driver ? (
                          <span className="min-w-0 truncate text-muted">· {p.risk_driver}</span>
                        ) : null}
                      </div>
                    </td>
                    <td className="px-4 py-2.5">
                      <div className="flex items-center gap-2">
                        <div className="h-1.5 w-12 overflow-hidden rounded-full bg-track">
                          <div
                            className={`h-full rounded-full ${p.risk_score > 0.6 ? "bg-crit" : p.risk_score > 0.4 ? "bg-orange" : "bg-safe"
                              }`}
                            style={{ width: `${p.risk_score * 100}%` }}
                          />
                        </div>
                        <span className="font-mono text-xs text-fg">{p.risk_score.toFixed(2)}</span>
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </Panel>


      {selectedEventDetail && (
        <EventDetailModal
          event={selectedEventDetail}
          onClose={() => setSelectedEventDetail(null)}
        />
      )}

      {chokepointDetail && (
        <ChokepointDetailModal
          detail={chokepointDetail}
          onClose={() => setChokepointDetail(null)}
        />
      )}

      {producerDetail && (
        <ProducerDetailModal
          detail={producerDetail}
          onClose={() => setProducerDetail(null)}
        />
      )}
    </div>
  )
}

// Human-readable status label per feed.
const marketLabel = (s: string | undefined) =>
  s === "available" ? "Active" : s === "partial" ? "Partial" : s === "stale" ? "Stale" : "Unavailable"
const vesselLabel = (s: string | undefined) =>
  s === "available" ? "Active" : s === "partial" ? "Excluded — low AIS coverage" : "Unavailable"

// Header badge for the SDI chart: how many of the four SDI signals are
// currently feeding the score, with a hover breakdown so "3/4" is legible.
// Note: a "partial" AIS snapshot is excluded from the score (delta_d = 0), so
// it must not be counted as an active signal.
function SignalCoverageBadge({ live }: { live: LiveMetrics }) {
  const vesselActive = live.ais_status === "available"
  const marketCount = live.market_status === "available" ? 2 : live.market_status === "partial" ? 1 : 0
  const active = 1 /* geopolitical: always present */ + (vesselActive ? 1 : 0) + marketCount
  const degraded = active < 4

  const signals: { name: string; status: string; ok: boolean }[] = [
    { name: "Geopolitical Risk (Sentinel)", status: "Active", ok: true },
    { name: "Vessel Density (AIS)", status: vesselLabel(live.ais_status), ok: vesselActive },
    {
      name: "Brent Price",
      status: marketLabel(live.market_status),
      ok: live.market_status === "available" || live.market_status === "partial",
    },
    { name: "Freight Cost", status: marketLabel(live.market_status), ok: live.market_status === "available" },
  ]

  return (
    <div className="group relative">
      <div
        className={`cursor-help rounded border px-2 py-0.5 text-[10px] font-bold uppercase tracking-widest ${
          degraded
            ? "border-warn/40 bg-warn-soft text-warn"
            : "border-safe/40 bg-safe-soft text-safe"
        }`}
      >
        Signal Coverage: {active}/4
      </div>
      <div className="pointer-events-none absolute right-0 top-full z-50 mt-2 w-72 opacity-0 transition-opacity group-hover:opacity-100">
        <div className="relative rounded-md border border-border bg-panel p-3 shadow-xl">
          <p className="mb-1 text-[11px] font-bold uppercase tracking-wider text-fg">SDI Signal Coverage</p>
          <p className="mb-2 text-[11px] leading-relaxed text-muted">
            The Supply Disruption Index blends four live signals. {active} of 4 are currently contributing to the score.
          </p>
          <ul className="space-y-1">
            {signals.map((s) => (
              <li key={s.name} className="flex items-center justify-between gap-2 text-[11px]">
                <span className="flex items-center gap-1.5 text-fg">
                  <span className={`h-1.5 w-1.5 rounded-full ${s.ok ? "bg-safe" : "bg-warn"}`} />
                  {s.name}
                </span>
                <span className={s.ok ? "text-muted" : "text-warn"}>{s.status}</span>
              </li>
            ))}
          </ul>
          <div className="absolute -top-1.5 right-4 h-3 w-3 rotate-45 border-l border-t border-border bg-panel" />
        </div>
      </div>
    </div>
  )
}
