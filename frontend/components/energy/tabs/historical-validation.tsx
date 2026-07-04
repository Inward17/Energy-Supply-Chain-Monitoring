"use client"

import { useEffect, useState } from "react"
import { ShieldAlert, TrendingUp, Calendar, AlertTriangle } from "lucide-react"
import { 
  LineChart, Line, XAxis, YAxis, CartesianGrid, 
  Tooltip, ResponsiveContainer, ReferenceLine, ComposedChart, Area
} from "recharts"
import { Panel } from "../ui"
import { fetchBacktest, type BacktestResult } from "@/lib/api"

export function HistoricalValidation() {
  const [data, setData] = useState<BacktestResult | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)

  useEffect(() => {
    fetchBacktest("red_sea_attacks")
      .then(res => {
        setData({
          ...res,
          series: res.series.map((s: any) => ({
            ...s,
            sdi_range: [s.confidence_low || s.sdi_score, s.confidence_high || s.sdi_score]
          }))
        })
        setLoading(false)
      })
      .catch(err => {
        console.error("Backtest failed to load", err)
        setError(true)
        setLoading(false)
      })
  }, [])

  if (loading) {
    return (
      <Panel title="Historical Validation: Red Sea Crisis (Nov 2023 - Jan 2024)" icon={<ShieldAlert className="h-4 w-4 text-emerald-400" />}>
        <div className="flex h-[400px] w-full items-center justify-center text-slate-500">Loading backtest data...</div>
      </Panel>
    )
  }

  if (error || !data || data.series.length === 0) {
    return (
      <Panel title="Historical Validation: Red Sea Crisis (Nov 2023 - Jan 2024)" icon={<ShieldAlert className="h-4 w-4 text-emerald-400" />}>
        <div className="flex h-[400px] w-full flex-col items-center justify-center gap-4 text-slate-500">
          <AlertTriangle className="h-8 w-8 text-rose-500/50" />
          <p>No backtest data available.</p>
          <p className="text-xs text-slate-600">Run the `run_backtest.py` script on the backend to populate historical data.</p>
        </div>
      </Panel>
    )
  }

  return (
    <Panel title="Historical Validation: Red Sea Crisis (Nov 2023 - Jan 2024)" icon={<ShieldAlert className="h-4 w-4 text-emerald-400" />}>
      <div className="p-4">
        
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
    </Panel>
  )
}
