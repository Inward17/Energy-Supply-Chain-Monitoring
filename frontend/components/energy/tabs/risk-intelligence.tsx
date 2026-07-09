"use client"

import { useEffect, useState } from "react"
import { CircleDot, Activity, Crosshair } from "lucide-react"
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
import { Panel, SeverityBadge } from "../ui"
import { HistoricalValidation } from "./historical-validation"
import { fetchRiskEvents, fetchChokepointMatrix, fetchSdiTimeline, fetchLiveMetrics, fetchRiskEventDetail, type RiskEvent, type RiskEventDetail, type ChokepointRisk, type SdiPoint, type LiveMetrics } from "@/lib/api"
import { chartTooltip } from "../chart-tooltip"
import { InfoTooltip } from "@/components/ui/info-tooltip"
import { Loader2, ExternalLink } from "lucide-react"
import { EventDetailModal } from "./event-detail-modal"

export function RiskIntelligence() {
  const [events, setEvents] = useState<RiskEvent[]>([])
  const [matrix, setMatrix] = useState<ChokepointRisk[]>([])
  const [timeline, setTimeline] = useState<any[]>([])
  const [live, setLive] = useState<LiveMetrics | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  
  const [selectedEventDetail, setSelectedEventDetail] = useState<RiskEventDetail | null>(null)
  const [detailLoadingId, setDetailLoadingId] = useState<number | null>(null)

  useEffect(() => {
    (async () => {
      try {
        const [evs, mat, tim, liv] = await Promise.all([
          fetchRiskEvents(),
          fetchChokepointMatrix(),
          fetchSdiTimeline(),
          fetchLiveMetrics(),
        ])
        setEvents(evs)
        setMatrix(mat)

        // Map timeline to include an array for the confidence band Area
        const timelineWithBands = tim.map(t => ({
          ...t,
          sdi_range: [t.confidence_low, t.confidence_high],
          sdi: t.sdi_score
        }))
        setTimeline(timelineWithBands)
        setLive(liv)
      } catch (err) {
        console.error("Failed to load risk intelligence:", err)
        setError(String(err))
      } finally {
        setLoading(false)
      }
    })()
  }, [])

  const handleEventClick = async (eventId: number) => {
    setDetailLoadingId(eventId)
    try {
      const detail = await fetchRiskEventDetail(eventId)
      setSelectedEventDetail(detail)
    } catch (err) {
      console.error("Failed to fetch event detail:", err)
    } finally {
      setDetailLoadingId(null)
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
      <div className="flex h-[600px] items-center justify-center rounded-lg border border-slate-800 bg-slate-900/40">
        <Loader2 className="h-8 w-8 animate-spin text-cyan-500" />
      </div>
    )
  }

  if (error) {
    return (
      <div className="p-4 text-rose-500 bg-rose-500/10 rounded m-4 border border-rose-500/20">
        Failed to load risk intelligence: {error}
      </div>
    )
  }

  const displayEvents = events
  const displayMatrix = matrix

  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-5">
      <Panel
        title="Sentinel Risk Events"
        icon={<CircleDot className="h-4 w-4 text-rose-500" />}
        className="lg:col-span-2"
      >
        <div className="max-h-[560px] space-y-2.5 overflow-y-auto p-3 pr-2 [&::-webkit-scrollbar]:w-2 [&::-webkit-scrollbar-track]:bg-transparent [&::-webkit-scrollbar-thumb]:rounded-full [&::-webkit-scrollbar-thumb]:bg-slate-800 hover:[&::-webkit-scrollbar-thumb]:bg-slate-700">
          {displayEvents.length === 0 ? (
            <p className="p-4 text-center text-sm text-slate-500">No active events.</p>
          ) : (
            displayEvents.map((e) => (
              <article
                key={e.id}
                onClick={() => handleEventClick(e.id)}
                className={`cursor-pointer rounded-lg border border-slate-800 bg-slate-950/60 p-3 transition-colors hover:border-slate-700 hover:bg-slate-900/60 border-l-2 ${detailLoadingId === e.id ? "opacity-50" : ""} ${
                  e.severity_label === "CRITICAL" ? "border-l-rose-500" :
                    e.severity_label === "HIGH" ? "border-l-orange-500" :
                      e.severity_label === "MODERATE" ? "border-l-yellow-500" :
                        "border-l-emerald-500"
                  }`}
              >
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <h3 className="text-sm font-semibold text-white">{eventTitle(e.disruption_type)}</h3>
                    <p className="text-xs text-cyan-400">{e.region}</p>
                  </div>
                  <SeverityBadge severity={e.severity_label} />
                </div>
                <p className="mt-2 text-xs leading-relaxed text-slate-400">{e.summary}</p>
                <div className="mt-3 flex items-center justify-between border-t border-slate-800 pt-2">
                  {e.scored_at && (
                    <p className="text-[10px] uppercase tracking-wider text-slate-600">{timeAgo(e.scored_at)}</p>
                  )}
                  {e.source_urls && e.source_urls.length > 0 && (
                    <div className="group relative">
                      <button className="text-[10px] uppercase tracking-wider text-slate-500 hover:text-cyan-400 flex items-center gap-1">
                        Sources ({e.source_urls.length})
                      </button>
                      <div className="pointer-events-none absolute bottom-full right-0 z-50 mb-2 w-64 opacity-0 transition-opacity group-hover:pointer-events-auto group-hover:opacity-100">
                        <div className="rounded-md border border-slate-700 bg-slate-900 p-2 shadow-xl">
                          <p className="mb-2 text-[10px] font-bold uppercase tracking-wider text-slate-500">GDELT Event Sources</p>
                          <ul className="space-y-1.5 max-h-32 overflow-y-auto pr-1 [&::-webkit-scrollbar]:w-1 [&::-webkit-scrollbar-track]:bg-transparent [&::-webkit-scrollbar-thumb]:rounded-full [&::-webkit-scrollbar-thumb]:bg-slate-700">
                            {e.source_urls.map((url, idx) => {
                              try {
                                const domain = new URL(url).hostname.replace(/^www\./, '')
                                return (
                                  <li key={idx} className="truncate">
                                    <a href={url} target="_blank" rel="noreferrer" className="text-[11px] text-cyan-400 hover:underline">
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
                          <div className="absolute -bottom-1.5 right-4 h-3 w-3 rotate-45 border-b border-r border-slate-700 bg-slate-900" />
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

      <div className="flex flex-col gap-4 lg:col-span-3">
        <Panel
          title={live ? `SDI: ${Math.round(live.sdi_score)} (range ${Math.round(live.confidence_low)}–${Math.round(live.confidence_high)})` : "SDI Score Timeline"}
          icon={<Activity className="h-4 w-4 text-cyan-400" />}
        >
          <div className="h-64 p-4">
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart data={timeline} margin={{ top: 8, right: 12, left: -12, bottom: 0 }}>
                <defs>
                  <linearGradient id="sdiBand" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#facc15" stopOpacity={0.15} />
                    <stop offset="95%" stopColor="#facc15" stopOpacity={0.0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                <XAxis dataKey="scored_at" stroke="#64748b" fontSize={11} tickLine={false} tickFormatter={(val) => val ? new Date(val).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : ""} />
                <YAxis stroke="#64748b" fontSize={11} tickLine={false} domain={[0, 100]} />
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
                  stroke="#facc15"
                  strokeWidth={2}
                  dot={{ r: 2, fill: "#facc15" }}
                  activeDot={{ r: 4 }}
                  isAnimationActive={false}
                />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        </Panel>

        <Panel title="Chokepoint Risk Matrix" icon={<Crosshair className="h-4 w-4 text-cyan-400" />}>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-800 text-left text-[11px] uppercase tracking-wider text-slate-500">
                  <th className="px-4 py-2.5 font-medium"><InfoTooltip term="Chokepoint" /></th>
                  <th className="px-4 py-2.5 font-medium">Flow</th>
                  <th className="px-4 py-2.5 font-medium">Risk Score</th>
                  <th className="px-4 py-2.5 font-medium">Price Impact</th>
                </tr>
              </thead>
              <tbody>
                {displayMatrix.map((c) => (
                  <tr key={c.name} className="border-b border-slate-800/60 last:border-0">
                    <td className="px-4 py-2.5 font-medium text-slate-200">{c.name}</td>
                    <td className="px-4 py-2.5 font-mono text-slate-400">{c.flow_mb_day.toFixed(1)} mbpd</td>
                    <td className="px-4 py-2.5">
                      <div className="flex items-center gap-2">
                        <div className="h-1.5 w-16 overflow-hidden rounded-full bg-slate-800">
                          <div
                            className={`h-full rounded-full ${c.risk_score > 0.6 ? "bg-rose-500" : c.risk_score > 0.4 ? "bg-orange-400" : "bg-emerald-400"
                              }`}
                            style={{ width: `${c.risk_score * 100}%` }}
                          />
                        </div>
                        <span className="font-mono text-xs text-slate-300">{c.risk_score.toFixed(2)}</span>
                      </div>
                    </td>
                    <td className="px-4 py-2.5 font-mono text-rose-400">+${c.price_impact_usd.toFixed(2)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Panel>
      </div>

      {/* Historical Backtest Validation */}
      <div className="lg:col-span-5">
        <HistoricalValidation />
      </div>
      
      {selectedEventDetail && (
        <EventDetailModal
          event={selectedEventDetail}
          onClose={() => setSelectedEventDetail(null)}
        />
      )}
    </div>
  )
}
