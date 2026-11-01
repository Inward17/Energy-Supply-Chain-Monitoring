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
import { useChartTheme } from "../chart-theme"
import { fetchMarketPrices, type Instrument } from "@/lib/api"

export function MarketPulse() {
  const c = useChartTheme()
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
      <Panel title="Market Pulse" tone="crit">
        <div className="flex h-[400px] items-center justify-center">
          <Loader2 className="h-8 w-8 animate-spin text-accent" />
        </div>
      </Panel>
    )
  }

  if (error) {
    return (
      <Panel title="Market Pulse" tone="crit">
        <div className="p-4 text-crit bg-crit-soft rounded m-4">
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
    <Panel title="Market Pulse" tone="crit">
      <div className="space-y-4 p-4">
        {/* Instrument selector */}
        <div className="flex flex-wrap gap-2">
          {instruments.map((ins) => (
            <label
              key={ins.ticker}
              className={`flex cursor-pointer items-center gap-2 rounded-md border px-3 py-1.5 text-sm transition-colors ${
                selected === ins.ticker
                  ? "border-accent-border bg-accent-soft text-accent"
                  : "border-border bg-panel-2 text-muted hover:border-border"
              }`}
            >
              <input
                type="radio"
                name="instrument"
                value={ins.ticker}
                checked={selected === ins.ticker}
                onChange={() => setSelected(ins.ticker)}
                className="h-3 w-3 accent-accent"
              />
              {ins.ticker}
            </label>
          ))}
        </div>

        {/* Chart */}
        <div className="rounded-lg border border-border bg-panel-2 p-3">
          <div className="mb-2 flex items-center justify-between">
            <div>
              <p className="text-xs uppercase tracking-wider text-muted">{active.ticker} · 60d</p>
              <p className="font-mono text-2xl font-bold text-head">
                ${active.price.toFixed(2)}
              </p>
            </div>
            <span className={`flex items-center gap-1 rounded-md px-2 py-1 text-xs font-medium ${isUp ? "bg-safe-soft text-safe" : "bg-crit-soft text-crit"}`}>
              {isUp ? <TrendingUp className="h-3.5 w-3.5" /> : <TrendingDown className="h-3.5 w-3.5" />}
              {isUp ? "+" : ""}{pctChange.toFixed(1)}%
            </span>
          </div>
          <div className="h-72">
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart data={active.series} margin={{ top: 8, right: 12, left: -12, bottom: 0 }}>
                <defs>
                  <linearGradient id="priceFill" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor={c.accent} stopOpacity={0.35} />
                    <stop offset="100%" stopColor={c.accent} stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke={c.grid} />
                <XAxis
                  dataKey="d"
                  stroke={c.axis}
                  fontSize={11}
                  tickLine={false}
                  tickFormatter={(val: string) => {
                    try {
                      const d = new Date(val)
                      return d.toLocaleDateString("en-US", { month: "short", day: "numeric" })
                    } catch { return val }
                  }}
                  interval={Math.ceil((active.series?.length ?? 60) / 8)}
                />
                <YAxis
                  yAxisId="price"
                  stroke={c.axis}
                  fontSize={11}
                  tickLine={false}
                  domain={["dataMin - 4", "dataMax + 4"]}
                  tickFormatter={(v) => `$${v}`}
                />
                <YAxis yAxisId="vol" orientation="right" stroke={c.tick} fontSize={11} tickLine={false} />
                <Tooltip content={chartTooltip} />
                <Bar
                  yAxisId="vol"
                  dataKey="vol"
                  name="Volume"
                  barSize={14}
                  fill={c.neutral}
                  radius={[2, 2, 0, 0]}
                  isAnimationActive={false}
                />
                <Area
                  yAxisId="price"
                  type="monotone"
                  dataKey="price"
                  name="Price"
                  stroke={c.accent}
                  strokeWidth={2}
                  fill="url(#priceFill)"
                  isAnimationActive={false}
                />
                <Line
                  yAxisId="price"
                  type="monotone"
                  dataKey="ma"
                  name="MA(20)"
                  stroke={c.warn}
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
          <StatChip label="Current Price" value={`$${active.price.toFixed(2)}`} accent="text-head" />
          <StatChip label="60d High" value={`$${active.high_52w.toFixed(2)}`} accent="text-safe" />
          <StatChip label="60d Low" value={`$${active.low_52w.toFixed(2)}`} accent="text-crit" />
          <StatChip label="Avg Volume" value={active.volume} accent="text-accent" />
        </div>
      </div>
    </Panel>
  )
}
