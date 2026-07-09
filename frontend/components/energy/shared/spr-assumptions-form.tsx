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

const sliderClass =
  "h-1.5 w-full cursor-pointer appearance-none rounded-full bg-slate-700 accent-cyan-500"

/** Controlled form for the four SPR model-assumption sliders.
 *  Shared by SPR Optimizer and War Room Advanced Parameters. */
export function SprAssumptionsForm({ value, onChange, hideHeader }: SprAssumptionsFormProps) {
  const set = (patch: Partial<SprAssumptionsValue>) => onChange({ ...value, ...patch })
  const combinedCuts = value.runCut + value.indCut + value.transCut

  return (
    <div className="space-y-3">
      {!hideHeader && (
        <h4 className="text-[11px] font-medium uppercase tracking-wider text-slate-400">
          Model Assumptions
        </h4>
      )}

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        {/* GDP Impact */}
        <div>
          <div className="mb-1.5 flex items-center justify-between text-[11px] font-medium uppercase tracking-wider text-slate-400">
            <span>GDP Impact per Day</span>
            <span className="font-mono text-cyan-400">{value.gdpRate.toFixed(3)}%</span>
          </div>
          <input
            type="range" min={0.01} max={0.1} step={0.005} value={value.gdpRate}
            onChange={(e) => set({ gdpRate: Number(e.target.value) })}
            className={sliderClass}
          />
        </div>

        {/* Run-Rate Cut */}
        <div>
          <div className="mb-1.5 flex items-center justify-between text-[11px] font-medium uppercase tracking-wider text-slate-400">
            <span>Refinery Run-Rate Cut</span>
            <span className="font-mono text-cyan-400">{value.runCut}%</span>
          </div>
          <input
            type="range" min={0} max={50} step={1} value={value.runCut}
            onChange={(e) => set({ runCut: Number(e.target.value) })}
            className={sliderClass}
          />
        </div>

        {/* Industrial Priority */}
        <div>
          <div className="mb-1.5 flex items-center justify-between text-[11px] font-medium uppercase tracking-wider text-slate-400">
            <span>Industrial Priority Scheme</span>
            <span className="font-mono text-cyan-400">{value.indCut}%</span>
          </div>
          <input
            type="range" min={0} max={50} step={1} value={value.indCut}
            onChange={(e) => set({ indCut: Number(e.target.value) })}
            className={sliderClass}
          />
        </div>

        {/* Transport Rationing */}
        <div>
          <div className="mb-1.5 flex items-center justify-between text-[11px] font-medium uppercase tracking-wider text-slate-400">
            <span>Transport Fuel Rationing</span>
            <span className="font-mono text-cyan-400">{value.transCut}%</span>
          </div>
          <input
            type="range" min={0} max={50} step={1} value={value.transCut}
            onChange={(e) => set({ transCut: Number(e.target.value) })}
            className={sliderClass}
          />
        </div>
      </div>

      {combinedCuts > 60 && (
        <div className="rounded border border-orange-500/40 bg-orange-500/10 p-3 text-xs text-orange-300">
          ⚠️ Combined demand cuts ({combinedCuts}%) exceed typical operational limits.
        </div>
      )}
    </div>
  )
}
