"use client"

import { useEffect, useState } from "react"
import { ShieldAlert, TrendingUp, Calendar, AlertTriangle } from "lucide-react"
import { 
  LineChart, Line, XAxis, YAxis, CartesianGrid, 
  Tooltip, ResponsiveContainer, ReferenceLine, ComposedChart, Area
} from "recharts"
import { Panel } from "../ui"
import { fetchBacktest, fetchBacktestJobs, triggerBacktest, type BacktestResult, type BacktestJob } from "@/lib/api"
import { Loader2 } from "lucide-react"

const EVENTS = [
  { id: "red_sea_attacks", name: "Red Sea Crisis (Nov 2023 - Jan 2024)" },
  { id: "russia_ukraine_buildup", name: "Russia-Ukraine Buildup (Dec 2021 - Feb 2022)" },
  { id: "israel_iran_war_2025", name: "Twelve-Day War (Israel-Iran 2025)" }
]

export function HistoricalValidation() {
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
      <Panel title="Backtest Job Manager" icon={<ShieldAlert className="h-4 w-4 text-slate-400" />}>
        <div className="p-4 flex flex-col gap-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-4">
              <h3 className="text-sm font-semibold text-slate-200">Historical Scenarios</h3>
              <select 
                value={selectedEventId}
                onChange={(e) => setSelectedEventId(e.target.value)}
                className="bg-slate-900 border border-slate-700 text-slate-300 text-sm rounded px-3 py-1.5 focus:outline-none focus:ring-1 focus:ring-emerald-500"
              >
                {EVENTS.map(ev => (
                  <option key={ev.id} value={ev.id}>{ev.name}</option>
                ))}
              </select>
            </div>
            <button 
              onClick={handleRunBacktest} 
              disabled={triggering || jobs.some(j => j.status === 'pending' || j.status === 'running')}
              className="px-4 py-2 bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white text-sm rounded transition-colors flex items-center gap-2"
            >
              {triggering && <Loader2 className="h-4 w-4 animate-spin" />}
              Run Selected Backtest
            </button>
          </div>
          
          {jobs.length > 0 && (
            <div className="overflow-x-auto rounded border border-slate-800">
              <table className="w-full text-left text-sm text-slate-300">
                <thead className="bg-slate-900 text-xs uppercase text-slate-500">
                  <tr>
                    <th className="px-4 py-3">ID</th>
                    <th className="px-4 py-3">Event</th>
                    <th className="px-4 py-3">Status</th>
                    <th className="px-4 py-3">Created</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800 bg-slate-950">
                  {jobs.slice(0, 5).map(job => (
                    <tr key={job.id}>
                      <td className="px-4 py-3 font-mono text-xs">{job.id}</td>
                      <td className="px-4 py-3">{job.event_name}</td>
                      <td className="px-4 py-3">
                        <div className="flex flex-col gap-1">
                          <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium
                            ${job.status === 'completed' ? 'bg-emerald-500/10 text-emerald-400' :
                              job.status === 'failed' ? 'bg-rose-500/10 text-rose-400' :
                              job.status === 'running' ? 'bg-cyan-500/10 text-cyan-400' :
                              'bg-amber-500/10 text-amber-400'}`}>
                            {job.status === 'running' && <Loader2 className="mr-1.5 h-3 w-3 animate-spin" />}
                            {job.status === 'running' && job.progress_pct != null
                              ? `running ${job.progress_pct}%`
                              : job.status}
                          </span>
                          {job.status === 'running' && job.progress_note && (
                            <span className="text-[10px] text-slate-500">processing {job.progress_note}</span>
                          )}
                          {job.status === 'running' && job.progress_pct != null && (
                            <div className="h-1 w-full rounded-full bg-slate-800 overflow-hidden">
                              <div
                                className="h-1 rounded-full bg-cyan-500 transition-all duration-500"
                                style={{ width: `${job.progress_pct}%` }}
                              />
                            </div>
                          )}
                        </div>
                      </td>
                      <td className="px-4 py-3 text-xs text-slate-500">
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

      <Panel title={`Historical Validation: ${EVENTS.find(e => e.id === selectedEventId)?.name}`} icon={<ShieldAlert className="h-4 w-4 text-emerald-400" />}>
        <div className="p-4">
          {loading ? (
            <div className="flex h-[400px] w-full items-center justify-center text-slate-500">Loading backtest data...</div>
          ) : error || !data || data.series.length === 0 ? (
            <div className="flex h-[400px] w-full flex-col items-center justify-center gap-4 text-slate-500">
              <AlertTriangle className="h-8 w-8 text-rose-500/50" />
              <p>No backtest data available.</p>
              <p className="text-xs text-slate-600">Run the backtest using the button above to populate historical data.</p>
            </div>
          ) : (
            <div className="w-full">
        {/* Headline Metric */}
        <div className="mb-6 rounded-lg border border-emerald-500/30 bg-emerald-950/20 p-4">
          <div className="flex items-center gap-4">
            <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-full bg-emerald-500/20">
              <span className="text-xl font-bold text-emerald-400">{data.lead_time_days > 0 ? `+${data.lead_time_days}` : data.lead_time_days}</span>
            </div>
            <div>
              <h3 className="text-lg font-semibold text-emerald-400">Days of Advance Warning</h3>
              <p className="text-sm text-slate-300">{data.verdict}</p>
            </div>
          </div>
        </div>
        <p className="mb-4 text-xs italic text-slate-500">
          * Note: Vessel density is a live-only signal (requires real-time AIS ingestion); this historical validation reflects the other three signal sources.
        </p>

        {/* Dual Axis Chart */}
        <div className="h-[350px] w-full">
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={data.series} margin={{ top: 20, right: 30, left: 20, bottom: 20 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" vertical={false} />
              <XAxis 
                dataKey="date" 
                stroke="#64748b" 
                fontSize={12} 
                tickFormatter={(val) => new Date(val).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}
                tickMargin={10}
              />
              <YAxis 
                yAxisId="left"
                stroke="#f43f5e" 
                fontSize={12}
                domain={[0, 100]}
                tickFormatter={(val) => `${val}`}
                axisLine={false}
                tickLine={false}
              />
              <YAxis 
                yAxisId="right"
                orientation="right"
                stroke="#3b82f6" 
                fontSize={12}
                domain={['dataMin - 2', 'dataMax + 2']}
                tickFormatter={(val) => `$${val}`}
                axisLine={false}
                tickLine={false}
              />
              <Tooltip
                contentStyle={{ backgroundColor: "#0f172a", borderColor: "#1e293b", color: "#f8fafc" }}
                itemStyle={{ color: "#e2e8f0" }}
                labelStyle={{ color: "#94a3b8", marginBottom: "4px" }}
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
                  stroke="#f43f5e" 
                  strokeDasharray="3 3"
                  label={{ value: "System Alert", position: "insideTopLeft", fill: "#f43f5e", fontSize: 11 }} 
                />
              )}
              {data.market_reaction_date && (
                <ReferenceLine 
                  yAxisId="right"
                  x={data.market_reaction_date} 
                  stroke="#3b82f6" 
                  strokeDasharray="3 3"
                  label={{ value: "Market Reaction", position: "insideTopRight", fill: "#3b82f6", fontSize: 11 }} 
                />
              )}

              <defs>
                <linearGradient id="backtestBand" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#f43f5e" stopOpacity={0.25}/>
                  <stop offset="95%" stopColor="#f43f5e" stopOpacity={0.0}/>
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
                stroke="#f43f5e" 
                strokeWidth={2}
                dot={false}
                activeDot={{ r: 6, fill: "#f43f5e", stroke: "#0f172a", strokeWidth: 2 }}
                name="sdi_score"
              />
              <Line 
                yAxisId="right"
                type="monotone" 
                dataKey="brent_price" 
                stroke="#3b82f6" 
                strokeWidth={2}
                dot={false}
                activeDot={{ r: 6, fill: "#3b82f6", stroke: "#0f172a", strokeWidth: 2 }}
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
