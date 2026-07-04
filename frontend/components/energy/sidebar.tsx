"use client"

import { RefreshCw, Settings, SlidersHorizontal } from "lucide-react"
import { REGIONS } from "./data"

export function Sidebar({
  region,
  setRegion,
  severity,
  setSeverity,
  autoRefresh,
  setAutoRefresh,
  onRefresh,
  refreshing,
}: {
  region: string
  setRegion: (v: string) => void
  severity: number
  setSeverity: (v: number) => void
  autoRefresh: boolean
  setAutoRefresh: (v: boolean) => void
  onRefresh: () => void
  refreshing: boolean
}) {
  return (
    <aside className="flex w-56 shrink-0 flex-col border-r border-slate-800 bg-slate-900/40">
      {/* Controls */}
      <div className="flex items-center gap-2 border-b border-slate-800 px-4 py-3.5">
        <Settings className="h-4 w-4 text-cyan-400" />
        <h1 className="text-sm font-semibold tracking-widest text-white">CONTROLS</h1>
      </div>

      <div className="flex flex-col gap-5 px-4 py-4">
        <div>
          <label className="mb-1.5 flex items-center gap-1.5 text-[11px] font-medium uppercase tracking-wider text-slate-400">
            <SlidersHorizontal className="h-3 w-3" /> Filter by Region
          </label>
          <select
            value={region}
            onChange={(e) => setRegion(e.target.value)}
            className="w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-200 outline-none focus:border-cyan-500"
          >
            {REGIONS.map((r) => (
              <option key={r} value={r}>
                {r}
              </option>
            ))}
          </select>
        </div>

        <div>
          <div className="mb-1.5 flex items-center justify-between text-[11px] font-medium uppercase tracking-wider text-slate-400">
            <span>Severity Threshold</span>
            <span className="font-mono text-cyan-400">{severity}</span>
          </div>
          <input
            type="range"
            min={0}
            max={100}
            value={severity}
            onChange={(e) => setSeverity(Number(e.target.value))}
            className="h-1.5 w-full cursor-pointer appearance-none rounded-full bg-slate-700 accent-cyan-500"
          />
        </div>

        <div className="flex items-center justify-between rounded-md border border-slate-800 bg-slate-950/60 px-3 py-2.5">
          <span className="text-sm text-slate-300">Auto-refresh</span>
          <button
            type="button"
            role="switch"
            aria-checked={autoRefresh}
            onClick={() => setAutoRefresh(!autoRefresh)}
            className={`relative h-5 w-9 rounded-full transition-colors ${
              autoRefresh ? "bg-cyan-500" : "bg-slate-600"
            }`}
          >
            <span
              className={`absolute left-0.5 top-0.5 h-4 w-4 rounded-full bg-white transition-transform ${
                autoRefresh ? "translate-x-4" : "translate-x-0"
              }`}
            />
          </button>
        </div>
      </div>

      {/* Live Metrics removed to reclaim space for main content */}
      <div className="mt-auto border-t border-slate-800 px-4 py-4">
        <button
          type="button"
          onClick={onRefresh}
          className="mt-4 flex w-full items-center justify-center gap-2 rounded-md border border-cyan-500/40 bg-cyan-500/10 px-3 py-2 text-sm font-semibold text-cyan-300 transition-colors hover:bg-cyan-500/20"
        >
          <RefreshCw className={`h-3.5 w-3.5 ${refreshing ? "animate-spin" : ""}`} />
          Force Refresh
        </button>
      </div>
    </aside>
  )
}

