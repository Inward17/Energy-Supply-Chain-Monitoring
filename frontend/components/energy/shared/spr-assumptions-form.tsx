"use client"

import React from "react"

export interface SprAssumptionsValue {
  gdpRate: number   // 0.01–0.1 (decimal, e.g. 0.035 = 3.5%)
  runCut: number    // 0–50 (integer percent)
  indCut: number    // 0–50
  transCut: number  // 0–50
}

export const SPR_ASSUMPTIONS_DEFAULTS: SprAssumptionsValue = {
  gdpRate: 0.035,
  runCut: 15,
  indCut: 8,
  transCut: 10,
}

interface SprAssumptionsFormProps {
  value: SprAssumptionsValue
  onChange: (next: SprAssumptionsValue) => void
  /** If true, suppress the section header (for embedding inside another panel). */
  hideHeader?: boolean
}

/** Track fill for the slim slider — the design shows the consumed portion of
 *  each lever in accent against the neutral track. */
function fillStyle(value: number, min: number, max: number): React.CSSProperties {
  const pct = Math.max(0, Math.min(100, ((value - min) / (max - min)) * 100))
  return {
    background: `linear-gradient(to right, var(--t-accent) 0%, var(--t-accent) ${pct}%, var(--t-track) ${pct}%, var(--t-track) 100%)`,
  }
}

type Lever = {
  label: string
  display: string
  min: number
  max: number
  step: number
  value: number
  apply: (n: number) => Partial<SprAssumptionsValue>
}

/** Controlled form for the four SPR model-assumption sliders.
 *  Shared by SPR Optimizer and War Room Advanced Parameters. */
export function SprAssumptionsForm({ value, onChange, hideHeader }: SprAssumptionsFormProps) {
  const set = (patch: Partial<SprAssumptionsValue>) => onChange({ ...value, ...patch })
  const combinedCuts = value.runCut + value.indCut + value.transCut

  const levers: Lever[] = [
    {
      // NB: this exact label is asserted on by tests/e2e/smoke.spec.ts.
      label: "GDP Impact per Day",
      display: `${value.gdpRate.toFixed(3)}%`,
      min: 0.01, max: 0.1, step: 0.005, value: value.gdpRate,
      apply: (n) => ({ gdpRate: n }),
    },
    {
      label: "Refinery Run-Rate Cut",
      display: `${value.runCut}%`,
      min: 0, max: 50, step: 1, value: value.runCut,
      apply: (n) => ({ runCut: n }),
    },
    {
      label: "Industrial Priority Scheme",
      display: `${value.indCut}%`,
      min: 0, max: 50, step: 1, value: value.indCut,
      apply: (n) => ({ indCut: n }),
    },
    {
      label: "Transport Fuel Rationing",
      display: `${value.transCut}%`,
      min: 0, max: 50, step: 1, value: value.transCut,
      apply: (n) => ({ transCut: n }),
    },
  ]

  return (
    <div className="space-y-3.5">
      {!hideHeader && (
        <h4 className="text-[10px] font-semibold uppercase tracking-[0.12em] text-muted">
          Model Assumptions
        </h4>
      )}

      <div className="grid grid-cols-2 gap-x-3.5 gap-y-4 lg:grid-cols-4">
        {levers.map((lever) => (
          <div key={lever.label}>
            <label className="mb-2 block text-[10px] leading-tight text-muted">
              {lever.label}{" "}
              <span className="font-mono tabular-nums text-accent">{lever.display}</span>
            </label>
            <input
              type="range"
              min={lever.min}
              max={lever.max}
              step={lever.step}
              value={lever.value}
              aria-label={lever.label}
              onChange={(e) => set(lever.apply(Number(e.target.value)))}
              style={fillStyle(lever.value, lever.min, lever.max)}
              className="slider-slim w-full cursor-pointer"
            />
          </div>
        ))}
      </div>

      {combinedCuts > 60 && (
        <div className="rounded border border-orange/40 bg-orange-soft p-3 text-xs text-orange">
          ⚠️ Combined demand cuts ({combinedCuts}%) exceed typical operational limits.
        </div>
      )}
    </div>
  )
}
