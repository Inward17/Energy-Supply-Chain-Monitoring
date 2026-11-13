"use client"

import { REGIONS, FEED_COLOR, components, feedHealth, healthSummary, useData } from "./data"
import { Eyebrow } from "./ui"
import { useTheme } from "./theme"

/** Data-health checklist (desktop popover + mobile sheet share it). */
export function HealthPanel() {
  const { live, failed, refresh, lastOk } = useData()
  const s = healthSummary(live, failed)
  const feeds = feedHealth(live)

  if (failed) {
    return (
      <div className="flex flex-col gap-4">
        <p className="rounded-xl border border-crit-line bg-crit-soft p-4 text-sm leading-relaxed text-fg">
          The backend did not answer. Values on screen are the last ones received
          {lastOk ? ` (${new Date(lastOk).toISOString().slice(11, 16)} UTC)` : ""} and refresh when it returns.
        </p>
        <button type="button" onClick={() => void refresh()} className="min-h-12 rounded-xl border border-edge bg-hair font-semibold text-head">
          Retry now
        </button>
      </div>
    )
  }
  if (!live) return <p className="text-sm text-dim">Checking feeds…</p>

  const comp = components(live)
  const liveShare = comp.filter((c) => !c.missing).reduce((a, c) => a + c.max, 0)

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col gap-2">
        <div className="flex items-baseline justify-between">
          <span className="text-[13px] text-muted">Feeds live</span>
          <span className="font-mono text-[15px] text-head">
            {s.live}
            <span className="text-faint">/{s.total}</span>
          </span>
        </div>
        <div className="flex gap-1">
          {feeds.map((f) => (
            <span key={f.key} className="h-1.5 flex-1 rounded-full" style={{ background: FEED_COLOR[f.state] }} />
          ))}
        </div>
      </div>

      <div className="flex flex-col gap-2.5 rounded-[14px] border border-line bg-well p-3.5">
        <Eyebrow>Effect on SDI</Eyebrow>
        <div className="flex h-2.5 gap-0.5 overflow-hidden rounded-full">
          {comp.map((c) => (
            <span key={c.key} className={c.missing ? "hatch" : ""} style={{ flex: c.max, background: c.missing ? undefined : "var(--x-5aaeff)" }} />
          ))}
        </div>
        <span className="text-[13px] leading-relaxed text-fg">
          {liveShare >= 99.5
            ? "Every SDI input is live."
            : `${Math.round(liveShare)}% of the index has live inputs. Missing inputs count as zero, so ${live.sdi_score.toFixed(1)} may understate risk.`}
        </span>
      </div>

      <ul className="flex flex-col overflow-hidden rounded-[14px] border border-line">
        {feeds.map((f) => {
          const bad = f.state !== "ok"
          return (
            <li
              key={f.key}
              className="flex gap-3 border-b border-hair p-3.5 last:border-b-0"
              style={{ background: f.state === "down" ? "var(--x-1f1112)" : f.state === "stale" ? "var(--x-1e190c)" : "var(--x-0e1319)" }}
            >
              <span className="mt-1.5 h-2.5 w-2.5 shrink-0 rounded-full" style={{ background: FEED_COLOR[f.state] }} />
              <div className="flex flex-1 flex-col gap-1">
                <div className="flex justify-between gap-2">
                  <span className={`text-sm ${bad ? "font-semibold text-head" : "text-fg"}`}>{f.name}</span>
                  <span className="font-mono text-[11px]" style={{ color: bad ? FEED_COLOR[f.state] : "var(--x-94a0af)" }}>
                    {f.state === "ok" ? "LIVE" : f.state === "stale" ? "STALE" : "OFFLINE"}
                  </span>
                </div>
                {bad && <span className="text-xs leading-snug text-muted">{f.detail}</span>}
                {f.feeds && <span className="font-mono text-[11px] text-faint">feeds: {f.feeds}</span>}
              </div>
            </li>
          )
        })}
      </ul>

      <button
        type="button"
        onClick={() => void refresh()}
        className="flex min-h-12 items-center justify-center gap-2 rounded-xl border border-edge bg-hair text-sm font-semibold text-head"
      >
        Re-check now
      </button>
    </div>
  )
}

/** Region / severity / auto-refresh. Previously these sidebar controls were not
 *  wired to anything; they now filter every event list. */
export function FilterPanel({ onDone }: { onDone?: () => void }) {
  const { filters, setFilters, refresh } = useData()
  const [theme, toggleTheme] = useTheme()
  return (
    <div className="flex flex-col gap-6">
      <fieldset className="flex flex-col gap-2.5">
        <legend className="eyebrow pb-2.5">Region</legend>
        <div className="flex flex-wrap gap-2">
          {REGIONS.map((r) => (
            <button
              key={r}
              type="button"
              aria-pressed={filters.region === r}
              onClick={() => setFilters({ region: r })}
              className={`min-h-10 rounded-full border px-3.5 text-[13px] ${
                filters.region === r ? "border-fg bg-fg font-semibold text-ground" : "border-edge text-muted"
              }`}
            >
              {r}
            </button>
          ))}
        </div>
      </fieldset>

      <div className="flex flex-col gap-2.5">
        <div className="flex items-baseline justify-between">
          <label htmlFor="minsev" className="eyebrow">Min severity</label>
          <span className="font-mono text-sm text-head">{filters.minSeverity.toFixed(2)}</span>
        </div>
        <input
          id="minsev"
          type="range"
          min={0}
          max={100}
          value={Math.round(filters.minSeverity * 100)}
          onChange={(e) => setFilters({ minSeverity: Number(e.target.value) / 100 })}
          className="h-7 w-full accent-accent"
        />
        <div className="flex justify-between font-mono text-[10px] text-faint">
          <span>show all</span>
          <span>critical only</span>
        </div>
      </div>

      <label className="flex min-h-14 items-center justify-between rounded-[14px] border border-line bg-panel px-3.5">
        <span className="flex flex-col gap-0.5">
          <span className="text-sm text-head">Auto-refresh</span>
          <span className="text-xs text-dim">every 30 s, paused in background</span>
        </span>
        <input
          type="checkbox"
          checked={filters.autoRefresh}
          onChange={(e) => setFilters({ autoRefresh: e.target.checked })}
          className="h-[22px] w-[22px] accent-accent"
        />
      </label>

      <label className="flex min-h-14 items-center justify-between rounded-[14px] border border-line bg-panel px-3.5">
        <span className="text-sm text-head">Light theme</span>
        <input type="checkbox" checked={theme === "light"} onChange={toggleTheme} className="h-[22px] w-[22px] accent-accent" />
      </label>

      <div className="grid grid-cols-2 gap-2.5">
        <button
          type="button"
          onClick={() => setFilters({ region: "All regions", minSeverity: 0 })}
          className="min-h-12 rounded-xl border border-edge bg-hair text-sm font-semibold text-head"
        >
          Reset
        </button>
        <button
          type="button"
          onClick={() => {
            void refresh()
            onDone?.()
          }}
          className="min-h-12 rounded-xl bg-accent text-sm font-bold text-[var(--x-06121f)]"
        >
          Apply
        </button>
      </div>
    </div>
  )
}
