import type { ReactNode } from "react"
import { cn } from "@/lib/utils"
import type { Severity } from "./data"

/** Tones available for a panel's header chip. */
export type PanelTone = "accent" | "crit" | "safe" | "warn" | "orange" | "muted"

const toneChip: Record<PanelTone, string> = {
  accent: "bg-accent",
  crit: "bg-crit",
  safe: "bg-safe",
  warn: "bg-warn",
  orange: "bg-orange",
  muted: "bg-faint",
}

export function Panel({
  children,
  className,
  title,
  tone = "accent",
  icon,
  action,
}: {
  children: ReactNode
  className?: string
  title?: string
  /** Colour of the design's 8x8 header chip. Ignored when `icon` is supplied. */
  tone?: PanelTone
  icon?: ReactNode
  action?: ReactNode
}) {
  return (
    <section
      className={cn("overflow-hidden rounded-xl border border-border bg-panel", className)}
    >
      {title && (
        <header className="flex items-center justify-between gap-2 border-b border-hair px-[18px] py-3">
          <div className="flex items-center gap-[9px] text-head">
            {/* The design marks panels with a small rounded colour chip rather
                than a glyph. `icon` remains supported as an override. */}
            {icon ?? <span className={cn("h-2 w-2 shrink-0 rounded-sm", toneChip[tone])} />}
            <h2 className="text-[13.5px] font-bold tracking-wide">{title}</h2>
          </div>
          {action}
        </header>
      )}
      {children}
    </section>
  )
}

/**
 * Single source of truth for severity colour. The Leaflet hex equivalent lives
 * in chart-theme.ts (`severityHex`) — update both together.
 */
const severityStyles: Record<Severity, string> = {
  CRITICAL: "bg-crit-soft text-crit border-crit-soft",
  HIGH: "bg-orange-soft text-orange border-orange-soft",
  MODERATE: "bg-warn-soft text-warn border-warn-soft",
  LOW: "bg-hair text-muted border-border",
}

/** Left accent border per severity, for the risk-event feed cards. */
export const SEVERITY_BORDER_L: Record<Severity, string> = {
  CRITICAL: "border-l-crit",
  HIGH: "border-l-orange",
  MODERATE: "border-l-warn",
  LOW: "border-l-border",
}

export function SeverityBadge({ severity }: { severity: Severity }) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded border px-2 py-0.5 text-[10px] font-bold tracking-widest",
        severityStyles[severity],
      )}
    >
      {severity}
    </span>
  )
}

export function StatChip({
  label,
  value,
  accent = "text-head",
}: {
  label: string
  value: string
  accent?: string
}) {
  return (
    <div className="rounded-lg border border-border bg-panel-2 px-3 py-2.5">
      <div className="text-[10px] font-semibold uppercase tracking-widest text-faint">{label}</div>
      <div className={cn("mt-1 font-mono text-lg font-semibold tabular-nums", accent)}>{value}</div>
    </div>
  )
}

export function Divider() {
  return <div className="h-px w-full bg-hair" />
}
