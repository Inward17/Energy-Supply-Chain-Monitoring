"use client"

import { useEffect, useState } from "react"
import { AlertTriangle } from "lucide-react"
import { 
  LineChart, Line, XAxis, YAxis, CartesianGrid, 
  Tooltip, ResponsiveContainer, ReferenceLine, ComposedChart, Area
} from "recharts"
import { Panel } from "../ui"
import { useChartTheme } from "../chart-theme"
import { fetchBacktest, fetchBacktestJobs, triggerBacktest, type BacktestResult, type BacktestJob } from "@/lib/api"
import { Loader2 } from "lucide-react"

const EVENTS = [
  { id: "red_sea_attacks", name: "Red Sea Crisis (Nov 2023 - Jan 2024)" },
  { id: "russia_ukraine_buildup", name: "Russia-Ukraine Buildup (Dec 2021 - Feb 2022)" },
  { id: "israel_iran_war_2025", name: "Twelve-Day War (Israel-Iran 2025)" }
]

export function HistoricalValidation() {
  const c = useChartTheme()
  const [selectedEventId, setSelectedEventId] = useState("red_sea_attacks")
  const [data, setData] = useState<BacktestResult | null>(null)
  const [jobs, setJobs] = useState<BacktestJob[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)
  const [triggering, setTriggering] = useState(false)

  const loadData = () => {
    setLoading(true)
    Promise.all([
      fetchBacktest(selectedEventId).catch(() => null),
      fetchBacktestJobs().catch(() => [])
    ]).then(([res, j]) => {
      if (res && res.series && res.series.length > 0) {
        setData({
          ...res,
          series: res.series.map((s: any) => ({
            ...s,
            sdi_range: [s.confidence_low || s.sdi_score, s.confidence_high || s.sdi_score]
          }))
        })
        setError(false)
      } else {
        setData(null)
        setError(true)
      }
      setJobs(j)
      setLoading(false)
    })
  }

  useEffect(() => {
    loadData()
    // Poll jobs every 5s if there's a pending/running job
    const interval = setInterval(() => {
      fetchBacktestJobs().then(j => {
        setJobs(j)
        if (j.some(job => job.status === 'pending' || job.status === 'running')) {
          // If a job just completed, refresh the main chart data
          const hadRunning = jobs.some(old => old.status === 'pending' || old.status === 'running')
          const hasRunning = j.some(newj => newj.status === 'pending' || newj.status === 'running')
          if (hadRunning && !hasRunning) {
            loadData()
          }
        }
      }).catch(console.error)
    }, 5000)
    return () => clearInterval(interval)
  }, [selectedEventId])

  const handleRunBacktest = async () => {
    setTriggering(true)
    try {
      await triggerBacktest(selectedEventId)
      const updatedJobs = await fetchBacktestJobs()
      setJobs(updatedJobs)
    } catch (err) {
      console.error(err)
      alert("Failed to trigger backtest")
    }
    setTriggering(false)
  }

  return (
    <div className="flex flex-col gap-4">
      {/* Job Manager Panel */}
      <Panel title="Backtest Job Manager" tone="muted">
        <div className="p-4 flex flex-col gap-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-4">
              <h3 className="text-sm font-semibold text-fg">Historical Scenarios</h3>
              <select 
                value={selectedEventId}
                onChange={(e) => setSelectedEventId(e.target.value)}
                className="bg-panel border border-border text-fg text-sm rounded px-3 py-1.5 focus:outline-none focus:ring-1 focus:ring-safe"
              >
                {EVENTS.map(ev => (
                  <option key={ev.id} value={ev.id}>{ev.name}</option>
                ))}
              </select>
            </div>
            <button 
              onClick={handleRunBacktest} 
              disabled={triggering || jobs.some(j => j.status === 'pending' || j.status === 'running')}
              className="px-4 py-2 bg-safe hover:opacity-90 disabled:opacity-50 text-bg text-sm rounded transition-colors flex items-center gap-2"
            >
              {triggering && <Loader2 className="h-4 w-4 animate-spin" />}
              Run Selected Backtest
            </button>
          </div>
          
          {jobs.length > 0 && (
            <div className="overflow-x-auto rounded border border-border">
              <table className="w-full text-left text-sm text-fg">
                <thead className="bg-panel text-xs uppercase text-muted">
                  <tr>
                    <th className="px-4 py-3">ID</th>
                    <th className="px-4 py-3">Event</th>
                    <th className="px-4 py-3">Status</th>
                    <th className="px-4 py-3">Created</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-hair bg-panel-2">
                  {jobs.slice(0, 5).map(job => (
                    <tr key={job.id}>
                      <td className="px-4 py-3 font-mono text-xs">{job.id}</td>
                      <td className="px-4 py-3">{job.event_name}</td>
                      <td className="px-4 py-3">
                        <div className="flex flex-col gap-1">
                          {/* Design spec: mono, 9px, bold, tracked, fully rounded. */}
                          <span className={`inline-flex w-fit items-center rounded-full px-2 py-[3px] font-mono text-[9px] font-bold tracking-[0.06em] uppercase
                            ${job.status === 'completed' ? 'bg-safe-soft text-safe' :
                              job.status === 'failed' ? 'bg-crit-soft text-crit' :
                              job.status === 'running' ? 'bg-accent-soft text-accent' :
                              'bg-warn-soft text-warn'}`}>
                            {job.status === 'running' && <Loader2 className="mr-1.5 h-3 w-3 animate-spin" />}
                            {job.status === 'running' && job.progress_pct != null
                              ? `running ${job.progress_pct}%`
                              : job.status}
                          </span>
                          {job.status === 'running' && job.progress_note && (
                            <span className="text-[10px] text-muted">processing {job.progress_note}</span>
                          )}
                          {job.status === 'running' && job.progress_pct != null && (
                            <div className="h-1 w-full rounded-full bg-track overflow-hidden">
                              <div
                                className="h-1 rounded-full bg-accent transition-all duration-500"
                                style={{ width: `${job.progress_pct}%` }}
                              />
                            </div>
                          )}
                        </div>
                      </td>
                      <td className="px-4 py-3 text-xs text-muted">
                        {new Date(job.created_at).toLocaleString()}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </Panel>

      <Panel title={`Historical Validation: ${EVENTS.find(e => e.id === selectedEventId)?.name}`} tone="safe">
        <div className="p-4">
          {loading ? (
            <div className="flex h-[400px] w-full items-center justify-center text-muted">Loading backtest data...</div>
          ) : error || !data || data.series.length === 0 ? (
            <div className="flex h-[400px] w-full flex-col items-center justify-center gap-4 text-muted">
              <AlertTriangle className="h-8 w-8 text-crit/50" />
              <p>No backtest data available.</p>
              <p className="text-xs text-faint">Run the backtest using the button above to populate historical data.</p>
            </div>
          ) : (
            <div className="w-full">
        {/* Headline Metric */}
        {/* Design spec: solid accent-filled disc with the mono figure, beside a
            bold headline, inside a soft-tinted box. */}
        <div className="mb-6 flex items-center gap-4 rounded-[10px] border border-safe-soft bg-safe-soft p-4">
          <div className="flex h-[52px] w-[52px] shrink-0 items-center justify-center rounded-full bg-safe">
            <span className="font-mono text-[19px] font-bold tabular-nums text-bg">
              {data.lead_time_days > 0 ? `+${data.lead_time_days}` : data.lead_time_days}
            </span>
          </div>
          <div>
            <h3 className="text-base font-bold text-safe">Days of Advance Warning</h3>
            <p className="mt-0.5 text-[12.5px] text-muted">{data.verdict}</p>
            {data.threshold_sensitivity && (
              <p className="mt-1 text-xs text-faint">
                Sensitivity across SDI thresholds 50–80: {Math.min(...data.threshold_sensitivity.map((point) => point.lead_time_days))} to {Math.max(...data.threshold_sensitivity.map((point) => point.lead_time_days))} days.
              </p>
            )}
          </div>
        </div>
        <p className="mb-4 text-xs italic text-muted">
          * Note: Vessel density is a live-only signal (requires real-time AIS ingestion); this historical validation reflects the other three signal sources.
        </p>

        {/* Dual Axis Chart */}
        <div className="h-[350px] w-full">
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={data.series} margin={{ top: 20, right: 30, left: 20, bottom: 20 }}>
              <CartesianGrid strokeDasharray="3 3" stroke={c.grid} vertical={false} />
              <XAxis
                dataKey="date"
                stroke={c.axis}
                fontSize={12}
                tickFormatter={(val) => new Date(val).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}
                tickMargin={10}
              />
              <YAxis
                yAxisId="left"
                stroke={c.crit}
                fontSize={12}
                domain={[0, 100]}
                tickFormatter={(val) => `${val}`}
                axisLine={false}
                tickLine={false}
              />
              <YAxis
                yAxisId="right"
                orientation="right"
                stroke={c.accent}
                fontSize={12}
                domain={['dataMin - 2', 'dataMax + 2']}
                tickFormatter={(val) => `$${val}`}
                axisLine={false}
                tickLine={false}
              />
              {/* Kept inline rather than switched to the shared chartTooltip:
                  the formatter below renames the dual-axis series and adds the
                  $ prefix, which the shared renderer cannot express. */}
              <Tooltip
                contentStyle={{ backgroundColor: c.panel, borderColor: c.border, color: c.fg }}
                itemStyle={{ color: c.fg }}
                labelStyle={{ color: c.muted, marginBottom: "4px" }}
                formatter={(value: any, name: any) => [
                  name === "sdi_score" ? value : `$${value}`, 
                  name === "sdi_score" ? "SDI Score" : "Brent Crude"
                ]}
                labelFormatter={(label) => new Date(label).toLocaleDateString('en-US', { month: 'long', day: 'numeric', year: 'numeric' })}
              />
              
              {/* Reference Lines for Milestones */}
              {data.system_alert_date && (
                <ReferenceLine 
                  yAxisId="left"
                  x={data.system_alert_date}
                  stroke={c.crit}
                  strokeDasharray="3 3"
                  label={{ value: "System Alert", position: "insideTopLeft", fill: c.crit, fontSize: 11 }}
                />
              )}
              {data.market_reaction_date && (
                <ReferenceLine 
                  yAxisId="right"
                  x={data.market_reaction_date}
                  stroke={c.accent}
                  strokeDasharray="3 3"
                  label={{ value: "Market Reaction", position: "insideTopRight", fill: c.accent, fontSize: 11 }}
                />
              )}

              <defs>
                <linearGradient id="backtestBand" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor={c.crit} stopOpacity={0.25}/>
                  <stop offset="95%" stopColor={c.crit} stopOpacity={0.0}/>
                </linearGradient>
              </defs>
              <Area 
                yAxisId="left"
                type="monotone" 
                dataKey="sdi_range" 
                stroke="none" 
                fill="url(#backtestBand)" 
                isAnimationActive={false}
              />
              <Line 
                yAxisId="left"
                type="monotone" 
                dataKey="sdi_score"
                stroke={c.crit}
                strokeWidth={2}
                dot={false}
                activeDot={{ r: 6, fill: c.crit, stroke: c.panel, strokeWidth: 2 }}
                name="sdi_score"
              />
              <Line 
                yAxisId="right"
                type="monotone" 
                dataKey="brent_price"
                stroke={c.accent}
                strokeWidth={2}
                dot={false}
                activeDot={{ r: 6, fill: c.accent, stroke: c.panel, strokeWidth: 2 }}
                name="brent_price"
              />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
            </div>
        )}
      </div>
    </Panel>
  </div>
  )
}
