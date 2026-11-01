"use client"

import type { RiskEvent, SdiPoint } from "@/lib/api"
import { shortDate } from "./ui"

const GAP_MS = 12 * 3600 * 1000

/** SDI over time. Stretches with no snapshots (worker asleep) are hatched and
 *  bridged with a dashed line, so a drawn trend is never mistaken for a
 *  measured one. The largest single jump is annotated with the event that
 *  most plausibly caused it. */
export function SdiTrace({
  points,
  events = [],
  height = 196,
  compact = false,
}: {
  points: SdiPoint[]
  events?: RiskEvent[]
  height?: number
  compact?: boolean
}) {
  const W = 640, H = height, top = compact ? 8 : 40, bottom = H - 24
  const pts = [...points]
    .map((p) => ({ t: new Date(p.scored_at).getTime(), v: p.sdi_score }))
    .filter((p) => !Number.isNaN(p.t))
    .sort((a, b) => a.t - b.t)
  if (pts.length < 2) {
    return <p className="py-8 text-center text-sm text-dim">Not enough snapshots yet to draw a trend.</p>
  }
  const t0 = pts[0].t, t1 = pts[pts.length - 1].t
  const lo = Math.min(20, ...pts.map((p) => p.v)) - 2
  const hi = Math.max(70, ...pts.map((p) => p.v)) + 2
  const x = (t: number) => ((t - t0) / (t1 - t0 || 1)) * (W - 12) + 6
  const y = (v: number) => bottom - ((v - lo) / (hi - lo)) * (bottom - top)

  // Split into measured runs and gaps.
  const runs: { x: number; y: number }[][] = []
  const gaps: [number, number][] = []
  let cur: { x: number; y: number }[] = []
  pts.forEach((p, i) => {
    if (i && p.t - pts[i - 1].t > GAP_MS) {
      runs.push(cur)
      gaps.push([pts[i - 1].t, p.t])
      cur = []
    }
    cur.push({ x: x(p.t), y: y(p.v) })
  })
  runs.push(cur)
  const path = (r: { x: number; y: number }[]) => "M" + r.map((p) => `${p.x.toFixed(1)} ${p.y.toFixed(1)}`).join(" L")

  // Biggest jump inside a measured run.
  let jump: { i: number; d: number } | null = null
  pts.forEach((p, i) => {
    if (!i || p.t - pts[i - 1].t > GAP_MS) return
    const d = p.v - pts[i - 1].v
    if (Math.abs(d) >= 8 && (!jump || Math.abs(d) > Math.abs(jump.d))) jump = { i, d }
  })
  let cause: RiskEvent | undefined
  if (jump) {
    const jt = pts[(jump as { i: number }).i].t
    cause = events
      .filter((e) => Math.abs(new Date(e.scored_at).getTime() - jt) < 6 * 3600 * 1000)
      .sort((a, b) => b.severity - a.severity)[0]
  }
  const last = pts[pts.length - 1]
  const guides = [30, 50, 65].filter((g) => g > lo && g < hi)
  const label = `SDI from ${pts[0].v.toFixed(1)} on ${shortDate(new Date(t0).toISOString())} to ${last.v.toFixed(1)} on ${shortDate(new Date(t1).toISOString())}${gaps.length ? `, with ${gaps.length} gap${gaps.length > 1 ? "s" : ""} in the data` : ""}.`
  const fs = compact ? 18 : 10

  return (
    <svg viewBox={`0 0 ${W} ${H}`} width="100%" role="img" aria-label={label}>
      <defs>
        <pattern id="sdi-hatch" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
          <rect width="2" height="6" fill="var(--x-1e2731)" />
        </pattern>
        <linearGradient id="sdi-area" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="var(--x-f5f7fa)" stopOpacity="0.1" />
          <stop offset="1" stopColor="var(--x-f5f7fa)" stopOpacity="0" />
        </linearGradient>
      </defs>
      {guides.map((g) => (
        <g key={g}>
          <line x1="0" y1={y(g)} x2={W} y2={y(g)} stroke={g === 65 ? "var(--x-3a2414)" : g === 50 ? "var(--x-33290f)" : "var(--x-14322a)"} strokeDasharray="2 4" />
          {!compact && (
            <text x={W - 4} y={y(g) - 4} textAnchor="end" fill="var(--x-7a8697)" fontFamily="var(--font-plex-mono)" fontSize="9">
              {g}
            </text>
          )}
        </g>
      ))}
      {gaps.map(([a, b], i) => (
        <g key={i}>
          <rect x={x(a)} y={top - 8} width={x(b) - x(a)} height={bottom - top + 8} fill="url(#sdi-hatch)" />
          {!compact && x(b) - x(a) > 120 && (
            <text x={(x(a) + x(b)) / 2} y={bottom - 6} textAnchor="middle" fill="var(--x-94a0af)" fontFamily="var(--font-plex-mono)" fontSize="10">
              no snapshots · {Math.round((b - a) / 86400000)}d
            </text>
          )}
        </g>
      ))}
      {runs.map((r, i) =>
        r.length > 1 ? (
          <path key={`a${i}`} d={`${path(r)} L${r[r.length - 1].x} ${bottom} L${r[0].x} ${bottom} Z`} fill="url(#sdi-area)" />
        ) : null,
      )}
      {runs.slice(1).map((r, i) => {
        const a = runs[i][runs[i].length - 1]
        return <path key={`g${i}`} d={`M${a.x} ${a.y} L${r[0].x} ${r[0].y}`} fill="none" stroke="var(--x-f5f7fa)" strokeWidth={compact ? 2.5 : 1.2} strokeDasharray="3 5" opacity="0.5" />
      })}
      {runs.map((r, i) =>
        r.length > 1 ? (
          <path key={`l${i}`} d={path(r)} fill="none" stroke="var(--x-f5f7fa)" strokeWidth={compact ? 5 : 2.5} strokeLinejoin="round" strokeLinecap="round" />
        ) : (
          <circle key={`p${i}`} cx={r[0].x} cy={r[0].y} r={compact ? 5 : 3} fill="var(--x-f5f7fa)" />
        ),
      )}
      {jump && !compact && (() => {
        const j = jump as { i: number; d: number }
        const px = x(pts[j.i].t), py = y(pts[j.i].v)
        const bx = Math.max(4, Math.min(W - 196, px - 190))
        return (
          <g>
            <line x1={px} y1={py} x2={px} y2={14} stroke="var(--x-ff8a8d)" />
            <circle cx={px} cy={py} r="6" fill="var(--x-ff5a5f)" stroke="var(--x-0e1319)" strokeWidth="2.5" />
            <rect x={bx} y="2" width="186" height="34" rx="6" fill="var(--x-1c0f11)" stroke="var(--x-44201f)" />
            <text x={bx + 10} y="16" fill="var(--x-ff8a8d)" fontFamily="var(--font-plex-mono)" fontSize="10">
              {shortDate(new Date(pts[j.i].t).toISOString()).toUpperCase()} · {j.d > 0 ? "+" : ""}{j.d.toFixed(1)}
            </text>
            <text x={bx + 10} y="29" fill="var(--x-f5f7fa)" fontSize="11">
              {cause ? (cause.summary.split(/[.,;]/)[0] ?? "").slice(0, 32) : "Largest single move"}
            </text>
          </g>
        )
      })()}
      <circle cx={x(last.t)} cy={y(last.v)} r={compact ? 9 : 5} fill="var(--x-f5f7fa)" stroke="var(--x-0e1319)" strokeWidth={compact ? 4 : 2} />
      <text x="6" y={H - 6} fill="var(--x-7a8697)" fontFamily="var(--font-plex-mono)" fontSize={fs}>
        {shortDate(new Date(t0).toISOString())}
      </text>
      <text x={W - 4} y={H - 6} textAnchor="end" fill="var(--x-7a8697)" fontFamily="var(--font-plex-mono)" fontSize={fs}>
        {shortDate(new Date(t1).toISOString())}
      </text>
    </svg>
  )
}

/** Largest jump info for headlines ("One event moved the index N points"). */
export function biggestJump(points: SdiPoint[]): number | null {
  const pts = [...points].map((p) => ({ t: new Date(p.scored_at).getTime(), v: p.sdi_score })).sort((a, b) => a.t - b.t)
  let best: number | null = null
  for (let i = 1; i < pts.length; i++) {
    if (pts[i].t - pts[i - 1].t > GAP_MS) continue
    const d = pts[i].v - pts[i - 1].v
    if (Math.abs(d) >= 8 && (best == null || Math.abs(d) > Math.abs(best))) best = d
  }
  return best
}

/** Generic multi-line chart on a fixed 0..N x-axis (SPR burn-down, backtests). */
export function LineChart({
  series,
  height = 220,
  yMin,
  yMax,
  children,
  label,
}: {
  series: { values: number[]; color: string; width?: number; opacity?: number }[]
  height?: number
  yMin: number
  yMax: number
  children?: (sx: (i: number) => number, sy: (v: number) => number, W: number, H: number) => React.ReactNode
  label: string
}) {
  const W = 640, H = height, bottom = H - 22, top = 6
  const n = Math.max(...series.map((s) => s.values.length))
  const sx = (i: number) => (i / Math.max(1, n - 1)) * W
  const sy = (v: number) => bottom - ((v - yMin) / (yMax - yMin || 1)) * (bottom - top)
  return (
    <svg viewBox={`0 0 ${W} ${H}`} width="100%" role="img" aria-label={label}>
      {children?.(sx, sy, W, H)}
      {series.map((s, k) => (
        <path
          key={k}
          d={"M" + s.values.map((v, i) => `${sx(i).toFixed(1)} ${sy(v).toFixed(1)}`).join(" L")}
          fill="none"
          stroke={s.color}
          strokeWidth={s.width ?? 2.5}
          opacity={s.opacity ?? 1}
          strokeLinejoin="round"
        />
      ))}
    </svg>
  )
}
