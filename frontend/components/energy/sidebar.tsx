"use client"

import { RefreshCw } from "lucide-react"
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
    <aside className="flex w-[244px] shrink-0 flex-col border-r border-border bg-panel">
      {/* Brand */}
      <div className="flex items-center gap-3 border-b border-hair px-[18px] py-4">
        <svg width="34" height="34" viewBox="0 0 32 32" aria-hidden="true">
          <rect x="0" y="0" width="32" height="32" rx="8" className="fill-accent" />
          <path
            d="M8 22 L8 10 L16 18 L24 10 L24 22"
            fill="none"
            className="stroke-panel"
            strokeWidth="2.6"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
        <div className="leading-none">
          <div className="text-[17px] font-extrabold tracking-[0.15em] text-head">MERIDIAN</div>
          <div className="mt-1 text-[9px] uppercase tracking-[0.14em] text-faint">
            Resilience OS
          </div>
        </div>
      </div>

      <div className="px-[18px] pb-2 pt-4 text-[10px] font-bold uppercase tracking-[0.22em] text-faint">
        Controls
      </div>

      <div className="flex flex-col gap-[18px] px-[18px] py-1.5">
        <div>
          <label className="mb-2 block text-[10px] font-semibold uppercase tracking-[0.12em] text-muted">
            Filter by Region
          </label>
          <select
            value={region}
            onChange={(e) => setRegion(e.target.value)}
            className="w-full rounded-lg border border-border bg-input-bg px-3 py-2.5 text-[13px] text-fg outline-none focus:border-accent"
          >
            {REGIONS.map((r) => (
              <option key={r} value={r}>
                {r}
              </option>
            ))}
          </select>
        </div>

        <div>
          <div className="mb-2.5 flex items-center justify-between">
            <span className="text-[10px] font-semibold uppercase tracking-[0.12em] text-muted">
              Severity Threshold
            </span>
            <span className="font-mono text-[13px] font-semibold tabular-nums text-accent">
              {severity}
            </span>
          </div>
          <input
            type="range"
            min={0}
            max={100}
            value={severity}
            onChange={(e) => setSeverity(Number(e.target.value))}
            style={{ background: `linear-gradient(to right, var(--t-accent) 0%, var(--t-accent) ${severity}%, var(--t-track) ${severity}%, var(--t-track) 100%)` }}
            className="slider-slim w-full cursor-pointer"
          />
        </div>

        <div className="flex items-center justify-between rounded-lg border border-border bg-input-bg px-3 py-2.5">
          <span className="text-[13px] text-fg">Auto-refresh</span>
          <button
            type="button"
            role="switch"
            aria-checked={autoRefresh}
            onClick={() => setAutoRefresh(!autoRefresh)}
            className={`relative h-5 w-9 rounded-full transition-colors ${
              autoRefresh ? "bg-accent" : "bg-track"
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

      <div className="mt-auto border-t border-hair px-[18px] py-4">
        <div className="mb-3 text-[10px] font-bold uppercase tracking-[0.18em] text-faint">
          System Health
        </div>
        <div className="mb-4 flex flex-col gap-2.5">
          <div className="flex justify-between text-[11px]">
            <span className="text-muted">Auto-refresh</span>
            <span className={`font-mono ${autoRefresh ? "text-safe" : "text-muted"}`}>
              {autoRefresh ? "LIVE" : "PAUSED"}
            </span>
          </div>
          <div className="flex justify-between text-[11px]">
            <span className="text-muted">Region filter</span>
            <span className="font-mono text-fg">
              {region === "All Regions" ? "ALL" : "FILTERED"}
            </span>
          </div>
          <div className="flex justify-between text-[11px]">
            <span className="text-muted">Severity floor</span>
            <span className="font-mono tabular-nums text-fg">{severity}</span>
          </div>
        </div>
        <button
          type="button"
          onClick={onRefresh}
          className="flex w-full items-center justify-center gap-2 rounded-lg border border-accent-border bg-accent-soft px-3 py-2.5 text-[13px] font-semibold text-accent transition-opacity hover:opacity-80"
        >
          <RefreshCw className={`h-3.5 w-3.5 ${refreshing ? "animate-spin" : ""}`} />
          Force Refresh
        </button>
      </div>
    </aside>
  )
}
