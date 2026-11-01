"use client"

import type { LiveMetrics } from "@/lib/api"
import { timeAgo } from "@/lib/utils"

/** Newest scored event older than this means ingestion has stalled — the
 *  worker runs hourly, so a healthy pipeline never goes a day without one. */
const EVENT_STALE_MS = 24 * 60 * 60 * 1000

type Level = "checking" | "ok" | "degraded" | "offline"

export function systemStatus(
  live: LiveMetrics | null,
  failed: boolean,
  now = Date.now(),
): { level: Level; label: string; reasons: string[] } {
  if (failed) return { level: "offline", label: "Backend Offline", reasons: ["Live metrics request failed"] }
  if (!live) return { level: "checking", label: "Checking…", reasons: [] }

  const reasons: string[] = []
  if (live.ais_status === "unavailable") reasons.push("AIS vessel feed unavailable")
  else if (live.ais_status === "partial") reasons.push("AIS vessel feed partial")
  if (live.market_status && live.market_status !== "available") reasons.push(`Market data ${live.market_status}`)
  if (live.gemini_configured === false) reasons.push("Geopolitical scoring disabled")

  const eventAt = live.event_source_at ? new Date(live.event_source_at).getTime() : NaN
  if (Number.isNaN(eventAt)) reasons.push("No scored events")
  else if (now - eventAt > EVENT_STALE_MS) reasons.push(`Newest event ${timeAgo(live.event_source_at!)}`)

  return reasons.length
    ? { level: "degraded", label: "Degraded", reasons }
    : { level: "ok", label: "Systems Nominal", reasons }
}

const STYLES: Record<Level, { pill: string; dot: string; text: string }> = {
  checking: { pill: "bg-panel-2", dot: "bg-faint", text: "text-muted" },
  ok: { pill: "bg-safe-soft", dot: "bg-safe", text: "text-safe" },
  degraded: { pill: "bg-warn-soft", dot: "bg-warn", text: "text-warn" },
  offline: { pill: "bg-crit-soft", dot: "bg-crit", text: "text-crit" },
}

export function SystemStatusBadge({ live, failed }: { live: LiveMetrics | null; failed: boolean }) {
  const { level, label, reasons } = systemStatus(live, failed)
  const s = STYLES[level]
  return (
    <div
      role="status"
      title={reasons.join("\n") || undefined}
      className={`flex cursor-default items-center gap-2 rounded-full px-3 py-1.5 ${s.pill}`}
    >
      <span className="relative flex h-2 w-2">
        {level === "ok" && (
          <span className={`absolute inline-flex h-full w-full rounded-full ${s.dot} [animation:omping_1.6s_ease-out_infinite]`} />
        )}
        <span className={`relative inline-flex h-2 w-2 rounded-full ${s.dot}`} />
      </span>
      <span className={`text-xs font-semibold ${s.text}`}>{label}</span>
      {reasons.length > 0 && <span className="sr-only">: {reasons.join(", ")}</span>}
    </div>
  )
}
