import type { TooltipProps } from "recharts"

export function chartTooltip({ active, payload, label }: any) {
  if (!active || !payload || payload.length === 0) return null
  return (
    <div className="rounded-md border border-slate-700 bg-slate-950/95 px-3 py-2 text-xs shadow-lg backdrop-blur-sm">
      {label !== undefined && (
        <p className="mb-1 font-medium text-slate-300">{String(label)}</p>
      )}
      {payload.map((entry: any, i: number) => (
        <p key={i} className="flex items-center gap-2 font-mono" style={{ color: entry.color }}>
          <span className="inline-block h-2 w-2 rounded-full" style={{ background: entry.color }} />
          {entry.name}: {entry.value}
        </p>
      ))}
    </div>
  )
}
