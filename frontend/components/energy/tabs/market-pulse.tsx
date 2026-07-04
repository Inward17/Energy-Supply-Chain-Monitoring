"use client"

import { useState, useEffect } from "react"
import { Loader2, TrendingDown, TrendingUp } from "lucide-react"
import {
  Area,
  Bar,
  CartesianGrid,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts"
import { Panel, StatChip } from "../ui"
import { chartTooltip } from "../chart-tooltip"
import { fetchMarketPrices, type Instrument } from "@/lib/api"

export function MarketPulse() {
  const [instruments, setInstruments] = useState<Instrument[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [selected, setSelected] = useState("")

  useEffect(() => {
    fetchMarketPrices()
      .then((data) => {
        setInstruments(data.instruments)
        if (data.instruments.length > 0) {
          setSelected(data.instruments[0].ticker)
        }
        setLoading(false)
      })
      .catch((err) => {
        console.error("Failed to fetch market prices:", err)
        setError(String(err))
        setLoading(false)
      })
  }, [])

  if (loading) {
    return (
      <Panel title="Market Pulse" icon={<TrendingDown className="h-4 w-4 text-rose-500" />}>
        <div className="flex h-[400px] items-center justify-center">
          <Loader2 className="h-8 w-8 animate-spin text-cyan-500" />
        </div>
      </Panel>
    )
  }

  if (error) {
    return (
      <Panel title="Market Pulse" icon={<TrendingDown className="h-4 w-4 text-rose-500" />}>
        <div className="p-4 text-rose-500 bg-rose-500/10 rounded m-4">
          Failed to load market data: {error}
        </div>
      </Panel>
    )
  }

  const active = instruments.find((i) => i.ticker === selected) ?? instruments[0]
  
  const startPrice = active.series[0]?.price || active.price
  const pctChange = startPrice !== 0 ? ((active.price - startPrice) / startPrice) * 100 : 0
  const isUp = pctChange >= 0

  return (
    <Panel title="Market Pulse" icon={<TrendingDown className="h-4 w-4 text-rose-500" />}>
      <div className="space-y-4 p-4">
        {/* Instrument selector */}
        <div className="flex flex-wrap gap-2">
          {instruments.map((ins) => (
            <label
              key={ins.ticker}
              className={`flex cursor-pointer items-center gap-2 rounded-md border px-3 py-1.5 text-sm transition-colors ${
                selected === ins.ticker
                  ? "border-cyan-500/50 bg-cyan-500/10 text-cyan-300"
                  : "border-slate-800 bg-slate-950/60 text-slate-400 hover:border-slate-700"
              }`}
            >
              <input
                type="radio"
                name="instrument"
                value={ins.ticker}
                checked={selected === ins.ticker}
                onChange={() => setSelected(ins.ticker)}
                className="h-3 w-3 accent-cyan-500"
              />
              {ins.ticker}
            </label>
          ))}
        </div>

        {/* Chart */}
        <div className="rounded-lg border border-slate-800 bg-slate-950/40 p-3">
          <div className="mb-2 flex items-center justify-between">
            <div>
              <p className="text-xs uppercase tracking-wider text-slate-500">{active.ticker} · 60d</p>
              <p className="font-mono text-2xl font-bold text-white">
                ${active.price.toFixed(2)}
              </p>
            </div>
            <span className={`flex items-center gap-1 rounded-md px-2 py-1 text-xs font-medium ${isUp ? "bg-emerald-500/15 text-emerald-400" : "bg-rose-500/15 text-rose-400"}`}>
              {isUp ? <TrendingUp className="h-3.5 w-3.5" /> : <TrendingDown className="h-3.5 w-3.5" />}
              {isUp ? "+" : ""}{pctChange.toFixed(1)}%
            </span>
          </div>
          <div className="h-72">
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart data={active.series} margin={{ top: 8, right: 12, left: -12, bottom: 0 }}>
                <defs>
                  <linearGradient id="priceFill" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#22d3ee" stopOpacity={0.35} />
                    <stop offset="100%" stopColor="#22d3ee" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                <XAxis dataKey="d" stroke="#64748b" fontSize={11} tickLine={false} />
                <YAxis
                  yAxisId="price"
                  stroke="#64748b"
                  fontSize={11}
                  tickLine={false}
                  domain={["dataMin - 4", "dataMax + 4"]}
                  tickFormatter={(v) => `$${v}`}
                />
                <YAxis yAxisId="vol" orientation="right" stroke="#334155" fontSize={11} tickLine={false} />
                <Tooltip content={chartTooltip} />
                <Bar
                  yAxisId="vol"
                  dataKey="vol"
                  name="Volume"
                  barSize={14}
                  fill="#334155"
                  radius={[2, 2, 0, 0]}
                  isAnimationActive={false}
                />
                <Area
                  yAxisId="price"
                  type="monotone"
                  dataKey="price"
                  name="Price"
                  stroke="#22d3ee"
                  strokeWidth={2}
                  fill="url(#priceFill)"
                  isAnimationActive={false}
                />
                <Line
                  yAxisId="price"
                  type="monotone"
                  dataKey="ma"
                  name="MA(20)"
                  stroke="#facc15"
                  strokeWidth={1.5}
                  dot={false}
                  isAnimationActive={false}
                />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* KPI cards */}
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          <StatChip label="Current Price" value={`$${active.price.toFixed(2)}`} accent="text-white" />
          <StatChip label="52w High" value={`$${active.high_52w.toFixed(2)}`} accent="text-emerald-400" />
          <StatChip label="52w Low" value={`$${active.low_52w.toFixed(2)}`} accent="text-rose-400" />
          <StatChip label="Avg Volume" value={active.volume} accent="text-cyan-400" />
        </div>
      </div>
    </Panel>
  )
}
