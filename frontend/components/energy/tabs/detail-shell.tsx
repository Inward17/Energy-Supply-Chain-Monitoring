"use client"

import { useEffect, type ReactNode } from "react"
import { X } from "lucide-react"

/**
 * Shared chrome for the drill-down modals (event / chokepoint / producer).
 *
 * Layout is a wide two-column split: the narrative and supporting evidence run
 * down the left, and the score assessment sits in a fixed-width right rail so
 * the number being explained stays visible while the evidence scrolls.
 */
export function DetailShell({
  title,
  subtitle,
  badge,
  onClose,
  left,
  right,
}: {
  title: string
  subtitle?: ReactNode
  badge?: ReactNode
  onClose: () => void
  left: ReactNode
  right: ReactNode
}) {
  // Lock background scroll while open.
  useEffect(() => {
    document.body.style.overflow = "hidden"
    return () => {
      document.body.style.overflow = "unset"
    }
  }, [])

  useEffect(() => {
    const handleEsc = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose()
    }
    window.addEventListener("keydown", handleEsc)
    return () => window.removeEventListener("keydown", handleEsc)
  }, [onClose])

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/50 backdrop-blur-sm" onClick={onClose} />

      <div className="relative flex max-h-[90vh] w-full max-w-6xl flex-col overflow-hidden rounded-xl border border-border bg-panel shadow-2xl">
        <div className="flex items-start justify-between border-b border-border bg-panel-2 p-5">
          <div>
            <div className="mb-2 flex items-center gap-2">
              <h2 className="text-xl font-semibold text-head">{title}</h2>
              {badge}
            </div>
            {subtitle && <div className="text-sm font-medium text-accent">{subtitle}</div>}
          </div>
          <button
            onClick={onClose}
            aria-label="Close"
            className="rounded p-1 text-muted transition-colors hover:bg-hair hover:text-head"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-6 [&::-webkit-scrollbar]:w-2 [&::-webkit-scrollbar-track]:bg-transparent [&::-webkit-scrollbar-thumb]:rounded-full [&::-webkit-scrollbar-thumb]:bg-track hover:[&::-webkit-scrollbar-thumb]:bg-muted">
          <div className="grid grid-cols-1 gap-8 lg:grid-cols-[minmax(0,1fr)_340px]">
            <div className="min-w-0 space-y-6">{left}</div>
            <div className="space-y-4">{right}</div>
          </div>
        </div>
      </div>
    </div>
  )
}

/** Small labelled section used inside either column. */
export function Section({ label, children }: { label: string; children: ReactNode }) {
  return (
    <section>
      <h3 className="mb-2 text-xs font-bold uppercase tracking-wider text-muted">{label}</h3>
      {children}
    </section>
  )
}

/** Boxed panel for the right-hand assessment rail. */
export function RailCard({
  label,
  children,
  tone = "border-border",
}: {
  label: string
  children: ReactNode
  tone?: string
}) {
  return (
    <div className={`rounded-lg border ${tone} bg-panel-2 p-4`}>
      <h3 className="mb-3 text-xs font-bold uppercase tracking-wider text-muted">{label}</h3>
      {children}
    </div>
  )
}
