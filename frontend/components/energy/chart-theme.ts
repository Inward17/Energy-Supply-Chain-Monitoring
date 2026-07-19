"use client"

import { useMemo } from "react"
import { useTheme } from "@/components/theme-provider"
import type { Severity } from "./data"

/*
 * Recharts and Leaflet take colours as props/SVG presentation attributes, not
 * CSS classes, so they cannot consume the Tailwind tokens. `var()` in an SVG
 * presentation attribute is spec-legal but degrades silently to black where it
 * is unsupported, so we resolve to plain hex here instead.
 *
 * These values mirror the tokens in app/globals.css — keep the two in sync.
 */
export type ChartTheme = {
  grid: string
  axis: string
  tick: string
  accent: string
  crit: string
  safe: string
  warn: string
  orange: string
  neutral: string
  panel: string
  border: string
  fg: string
  muted: string
  mapBg: string
}

const PALETTE: Record<"dark" | "light", ChartTheme> = {
  dark: {
    grid: "#1f2836",
    axis: "#7c8aa0",
    tick: "#566178",
    accent: "#59a6ff",
    crit: "#ff5c6c",
    safe: "#46d19e",
    warn: "#f5b642",
    orange: "#ff9f45",
    neutral: "#1f2836",
    panel: "#0e131d",
    border: "#1f2836",
    fg: "#e6ebf2",
    muted: "#7c8aa0",
    mapBg: "#070b11",
  },
  light: {
    grid: "#e3ded4",
    axis: "#6b7484",
    tick: "#98a0b0",
    accent: "#2f5bd0",
    crit: "#d64550",
    safe: "#1f9d6b",
    warn: "#c98a1a",
    orange: "#d97a2b",
    neutral: "#e6e1d7",
    panel: "#ffffff",
    border: "#e3ded4",
    fg: "#1c2230",
    muted: "#6b7484",
    mapBg: "#eef1f4",
  },
}

export function useChartTheme(): ChartTheme {
  const { theme } = useTheme()
  return useMemo(() => PALETTE[theme], [theme])
}

/**
 * Hex counterpart of the severity styling in ui.tsx, for the Leaflet layer.
 * Kept beside the chart palette so the map can never drift from the badges
 * again — LOW previously rendered blue on the map, slate in badges and emerald
 * in the event list.
 */
export function severityHex(severity: Severity, c: ChartTheme): string {
  const map: Record<Severity, string> = {
    CRITICAL: c.crit,
    HIGH: c.orange,
    MODERATE: c.warn,
    LOW: c.muted,
  }
  return map[severity] ?? c.muted
}
