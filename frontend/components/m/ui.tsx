"use client"

import type { ReactNode } from "react"
import type { SdiBand } from "@/lib/api"

// ── Scales ────────────────────────────────────────────────────────────────────

/** Same thresholds the backend uses for sdi_band (constants.SDI_BANDS). */
export const BANDS: { band: SdiBand; from: number; to: number; dim: string; on: string; text: string }[] = [
  { band: "LOW", from: 0, to: 30, dim: "var(--x-14322a)", on: "var(--x-3fcf8e)", text: "var(--x-3fcf8e)" },
  { band: "MODERATE", from: 30, to: 50, dim: "var(--x-33290f)", on: "var(--x-f2c14e)", text: "var(--x-f2c14e)" },
  { band: "ELEVATED", from: 50, to: 65, dim: "var(--x-3a2414)", on: "var(--x-ff8a3d)", text: "var(--x-ff8a3d)" },
  { band: "SEVERE", from: 65, to: 80, dim: "var(--x-3d1c1e)", on: "var(--x-ff5a5f)", text: "var(--x-ff8a8d)" },
  { band: "CRITICAL", from: 80, to: 100, dim: "var(--x-4a181c)", on: "var(--x-ff5a5f)", text: "var(--x-ff8a8d)" },
]

export function bandFor(score: number): (typeof BANDS)[number] {
  return BANDS.find((b) => score < b.to) ?? BANDS[BANDS.length - 1]
}

/** Risk 0–1 → colour. Matches the canvas: <0.4 safe, <0.7 orange, else crit. */
export function riskColor(v: number): string {
  return v >= 0.7 ? "var(--x-ff5a5f)" : v >= 0.4 ? "var(--x-ff8a3d)" : "var(--x-3fcf8e)"
}
export function riskText(v: number): string {
  return v >= 0.7 ? "var(--x-ff8a8d)" : v >= 0.4 ? "var(--x-ff8a3d)" : "var(--x-aeb8c5)"
}

/** Event severity chip colours (bg, fg). */
export function sevChip(v: number): [string, string] {
  if (v >= 0.7) return ["var(--x-4a1d20)", "var(--x-ff8a8d)"]
  if (v >= 0.55) return ["var(--x-45291a)", "var(--x-ffa86b)"]
  if (v >= 0.4) return ["var(--x-3b3215)", "var(--x-f2c14e)"]
  return ["var(--x-17392b)", "var(--x-6fe0ab)"]
}

// ── Formatting ────────────────────────────────────────────────────────────────

export const fmt = (v: number | null | undefined, d = 2) =>
  v == null || Number.isNaN(v) ? "—" : v.toFixed(d)

/** ".66" style for 0–1 scores, as on the canvas dials. */
export const dot2 = (v: number) => v.toFixed(2).replace(/^0/, "")

export function ageMs(iso?: string | null): number | null {
  if (!iso) return null
  const t = new Date(iso).getTime()
  return Number.isNaN(t) ? null : Date.now() - t
}

export function ago(iso?: string | null): string {
  const ms = ageMs(iso)
  if (ms == null) return "—"
  const m = Math.floor(ms / 60000)
  if (m < 60) return `${Math.max(m, 0)}m ago`
  const h = Math.floor(m / 60)
  if (h < 48) return `${h}h ago`
  return `${Math.floor(h / 24)}d ago`
}

export function shortDate(iso?: string | null): string {
  if (!iso) return "—"
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleDateString("en-GB", { day: "numeric", month: "short", timeZone: "UTC" })
}

export function utcTime(iso?: string | null): string {
  if (!iso) return "—"
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return "—"
  return `${shortDate(iso)} · ${d.toISOString().slice(11, 16)} UTC`
}

export const titleCase = (s: string) =>
  s.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase())

// ── Primitives ────────────────────────────────────────────────────────────────

export function Panel({
  children,
  className = "",
  as: Tag = "section",
  ...rest
}: { children: ReactNode; className?: string; as?: "section" | "div" | "figure" | "article" } & Record<string, unknown>) {
  return (
    <Tag className={`panel rounded-[18px] ${className}`} {...rest}>
      {children}
    </Tag>
  )
}

export function Eyebrow({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <span className={`eyebrow ${className}`}>{children}</span>
}

export function Dot({ color, size = 8, glow = false }: { color: string; size?: number; glow?: boolean }) {
  return (
    <span
      aria-hidden="true"
      className="inline-block shrink-0 rounded-full"
      style={{ width: size, height: size, background: color, boxShadow: glow ? `0 0 0 3px color-mix(in srgb, ${color} 18%, transparent)` : undefined }}
    />
  )
}

export function Bar({ value, color, track = "var(--x-1a2330)", h = 6 }: { value: number; color: string; track?: string; h?: number }) {
  return (
    <span className="block w-full rounded-full" style={{ height: h, background: track }}>
      <span
        className="block rounded-full"
        style={{ height: h, width: `${Math.max(0, Math.min(1, value)) * 100}%`, background: color }}
      />
    </span>
  )
}

/** Ring dial for a 0–1 score. */
export function Ring({ value, size = 56, stroke = 5, label }: { value: number; size?: number; stroke?: number; label?: string }) {
  const r = (size - stroke) / 2 - 1
  const c = 2 * Math.PI * r
  const color = riskColor(value)
  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} aria-hidden="true" className="shrink-0">
      <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="var(--x-1a2330)" strokeWidth={stroke} />
      <circle
        cx={size / 2}
        cy={size / 2}
        r={r}
        fill="none"
        stroke={color}
        strokeWidth={stroke}
        strokeLinecap="round"
        strokeDasharray={`${Math.max(0.001, value) * c} ${c}`}
        transform={`rotate(-90 ${size / 2} ${size / 2})`}
      />
      <text
        x="50%"
        y="50%"
        dominantBaseline="central"
        textAnchor="middle"
        fill="var(--x-f5f7fa)"
        fontFamily="var(--font-plex-mono), monospace"
        fontSize={size * 0.22}
        fontWeight={600}
      >
        {label ?? dot2(value)}
      </text>
    </svg>
  )
}

/** Half-circle SDI gauge split into the five bands. */
export function Gauge({ score, band }: { score: number; band?: SdiBand }) {
  const cx = 130, cy = 130, r = 110
  const pt = (v: number) => {
    const a = Math.PI - (Math.min(100, Math.max(0, v)) / 100) * Math.PI
    return [cx + r * Math.cos(a), cy - r * Math.sin(a)] as const
  }
  const arc = (a: number, b: number) => {
    const [x1, y1] = pt(a)
    const [x2, y2] = pt(b)
    return `M${x1.toFixed(2)} ${y1.toFixed(2)} A${r} ${r} 0 0 1 ${x2.toFixed(2)} ${y2.toFixed(2)}`
  }
  const b = band ? BANDS.find((x) => x.band === band) ?? bandFor(score) : bandFor(score)
  const [mx, my] = pt(score)
  return (
    <div className="relative mx-auto h-[150px] w-[260px]">
      <svg width="260" height="150" viewBox="0 0 260 150" role="img" aria-label={`SDI ${score.toFixed(1)} of 100, ${b.band.toLowerCase()} band`}>
        {BANDS.map((x) => (
          <path key={x.band} d={arc(x.from, x.to)} fill="none" stroke={x.dim} strokeWidth="14" />
        ))}
        {BANDS.filter((x) => x.from < score).map((x) => (
          <path key={`on-${x.band}`} d={arc(x.from, Math.min(x.to, score))} fill="none" stroke={x.on} strokeWidth="14" />
        ))}
        <circle cx={mx} cy={my} r="10" fill="var(--x-0e1319)" stroke="var(--x-f5f7fa)" strokeWidth="3" />
      </svg>
      <div className="absolute inset-x-0 top-[54px] flex flex-col items-center gap-1.5">
        <span className="text-[64px] font-[300] leading-[0.9] tracking-[-0.04em] text-head">{score.toFixed(1)}</span>
        <span
          className="rounded-md px-2 py-[3px] font-mono text-[11px] font-semibold tracking-[0.1em]"
          style={{ background: `color-mix(in srgb, ${b.on} 14%, transparent)`, color: b.text }}
        >
          {b.band}
        </span>
      </div>
    </div>
  )
}

/** Simple sparkline path for a numeric series, scaled to its own range. */
export function sparkPath(values: number[], w: number, h: number, pad = 3): { line: string; area: string } {
  if (values.length < 2) return { line: "", area: "" }
  const lo = Math.min(...values)
  const hi = Math.max(...values)
  const span = hi - lo || 1
  const pts = values.map((v, i) => [
    (i / (values.length - 1)) * w,
    h - pad - ((v - lo) / span) * (h - 2 * pad),
  ])
  const line = "M" + pts.map(([x, y]) => `${x.toFixed(1)} ${y.toFixed(1)}`).join(" L")
  return { line, area: `${line} L${w} ${h} L0 ${h} Z` }
}

export function Spark({
  values,
  color = "var(--x-5aaeff)",
  height = 48,
  fill = true,
  className = "",
}: {
  values: number[]
  color?: string
  height?: number
  fill?: boolean
  className?: string
}) {
  const { line, area } = sparkPath(values, 400, 120)
  if (!line) return null
  return (
    <svg viewBox="0 0 400 120" width="100%" height={height} preserveAspectRatio="none" aria-hidden="true" className={className}>
      {fill && <path d={area} fill={color} fillOpacity={0.1} />}
      <path d={line} fill="none" stroke={color} strokeWidth={1.75} vectorEffect="non-scaling-stroke" strokeLinejoin="round" />
    </svg>
  )
}

export function SevChip({ v }: { v: number }) {
  const [bg, fg] = sevChip(v)
  return (
    <span
      className="flex h-[26px] w-11 shrink-0 items-center justify-center rounded-md font-mono text-xs"
      style={{ background: bg, color: fg }}
    >
      {v.toFixed(2)}
    </span>
  )
}

export function Loading({ label = "Loading…" }: { label?: string }) {
  return (
    <div className="flex min-h-[120px] items-center justify-center text-sm text-dim" role="status">
      {label}
    </div>
  )
}

export function ErrorNote({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div role="alert" className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-crit-line bg-crit-soft px-4 py-3 text-sm text-fg">
      <span>{message}</span>
      {onRetry && (
        <button type="button" onClick={onRetry} className="min-h-9 rounded-lg border border-crit-line px-3 text-xs font-semibold text-crit-text">
          Retry
        </button>
      )}
    </div>
  )
}

export function Segmented<T extends string>({
  options,
  value,
  onChange,
  label,
}: {
  options: { value: T; label: string }[]
  value: T
  onChange: (v: T) => void
  label: string
}) {
  return (
    <div
      role="group"
      aria-label={label}
      className="grid rounded-xl border border-line bg-panel p-1"
      style={{ gridTemplateColumns: `repeat(${options.length}, minmax(0, 1fr))` }}
    >
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          aria-pressed={o.value === value}
          onClick={() => onChange(o.value)}
          className={`min-h-10 rounded-[9px] text-[13px] ${
            o.value === value ? "bg-track font-semibold text-head" : "text-muted hover:text-fg"
          }`}
        >
          {o.label}
        </button>
      ))}
    </div>
  )
}
