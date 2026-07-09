import type { ReactNode } from "react"
import { cn } from "@/lib/utils"
import type { Severity } from "./data"

export function Panel({
  children,
  className,
  title,
  icon,
  action,
}: {
  children: ReactNode
  className?: string
  title?: string
  icon?: ReactNode
  action?: ReactNode
}) {
  return (
    <section
      className={cn(
        "rounded-lg border border-slate-800 bg-slate-900/50 backdrop-blur-sm",
        className,
      )}
    >
      {title && (
        <header className="flex items-center justify-between gap-2 border-b border-slate-800 px-4 py-2.5">
          <div className="flex items-center gap-2 text-slate-200">
            {icon}
            <h2 className="text-sm font-semibold tracking-wide">{title}</h2>
          </div>
          {action}
        </header>
      )}
      {children}
    </section>
  )
}

const severityStyles: Record<Severity, string> = {
  CRITICAL: "bg-rose-500/15 text-rose-400 border-rose-500/40",
  HIGH: "bg-orange-500/15 text-orange-400 border-orange-500/40",
  MODERATE: "bg-amber-500/15 text-amber-400 border-amber-500/40",
  LOW: "bg-slate-500/15 text-slate-400 border-slate-500/40",
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
  accent = "text-white",
}: {
  label: string
  value: string
  accent?: string
}) {
  return (
    <div className="rounded-lg border border-slate-800 bg-slate-950/60 px-3 py-2.5">
      <div className="text-[10px] uppercase tracking-widest text-slate-500">{label}</div>
      <div className={cn("mt-1 font-mono text-lg font-semibold", accent)}>{value}</div>
    </div>
  )
}

export function Divider() {
  return <div className="h-px w-full bg-slate-800" />
}
