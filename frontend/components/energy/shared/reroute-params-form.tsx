"use client"

import React, { useState } from "react"
import { InfoTooltip } from "@/components/ui/info-tooltip"
import { X } from "lucide-react"

export interface RerouteParamsValue {
  grade: string
  mode: "cost" | "speed"
  excludedCountries: string[]
  strictGradeMatch: boolean
}

interface FieldProps {
  value: RerouteParamsValue
  onChange: (next: RerouteParamsValue) => void
}

interface RerouteParamsFormProps extends FieldProps {
  grades: string[]
  /** Optional: when rendered inside a <select> option can't hold React nodes.
   *  Pass compact=true to skip the InfoTooltip wrappers. */
  compact?: boolean
}

const selectClass =
  "w-full rounded-md border border-border bg-panel-2 px-3 py-2 text-sm text-fg outline-none focus:border-accent"

const labelClass =
  "mb-1.5 block text-[11px] font-medium uppercase tracking-wider text-muted"

/*
 * The three controls are exported individually so callers can lay them out in
 * rows alongside their own fields. Composing them here instead would force a
 * fixed two-column block and leave large gaps in a wide panel.
 */

export function CrudeGradeField({ value, onChange, grades }: FieldProps & { grades: string[] }) {
  return (
    <div>
      <div className={labelClass}>Crude Grade</div>
      <select
        value={value.grade}
        onChange={(e) => onChange({ ...value, grade: e.target.value })}
        className={selectClass}
      >
        {grades.length === 0 ? (
          <option value="Any">Any</option>
        ) : (
          grades.map((g) => <option key={g}>{g}</option>)
        )}
      </select>
      {value.grade !== "Any" && (
        <div className="mt-2 flex items-center gap-3 text-xs">
          <label className="flex cursor-pointer items-center gap-1.5 text-fg">
            <input
              type="radio"
              checked={!value.strictGradeMatch}
              onChange={() => onChange({ ...value, strictGradeMatch: false })}
              className="accent-accent"
            />
            Allow substitutes
          </label>
          <label className="flex cursor-pointer items-center gap-1.5 text-fg">
            <input
              type="radio"
              checked={value.strictGradeMatch}
              onChange={() => onChange({ ...value, strictGradeMatch: true })}
              className="accent-accent"
            />
            Strict match
          </label>
        </div>
      )}
    </div>
  )
}

export function OptimiseForField({ value, onChange, compact }: FieldProps & { compact?: boolean }) {
  return (
    <div>
      <div className={labelClass}>
        {compact ? "Optimise For" : <InfoTooltip term="Landed Cost" label="Optimise For" />}
      </div>
      {/* Segmented control per the design. The underlying values stay
          "cost" | "speed" — only the affordance changed. */}
      <div
        role="group"
        aria-label="Optimise for"
        className="inline-flex overflow-hidden rounded-lg border border-border"
      >
        {(
          [
            { mode: "cost", label: "Cost", hint: "Lowest landed cost" },
            { mode: "speed", label: "Time", hint: "Fastest arrival" },
          ] as const
        ).map((opt) => {
          const active = value.mode === opt.mode
          return (
            <button
              key={opt.mode}
              type="button"
              title={opt.hint}
              aria-pressed={active}
              onClick={() => onChange({ ...value, mode: opt.mode })}
              className={`px-4 py-2 text-[12.5px] font-semibold transition-colors ${
                active ? "bg-accent text-bg" : "text-muted hover:text-fg"
              }`}
            >
              {opt.label}
            </button>
          )
        })}
      </div>
    </div>
  )
}

export function ExcludedCountriesField({ value, onChange }: FieldProps) {
  const [newCountry, setNewCountry] = useState("")

  const handleAddCountry = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter" && newCountry.trim()) {
      e.preventDefault()
      const country = newCountry.trim()
      if (!value.excludedCountries.includes(country)) {
        onChange({ ...value, excludedCountries: [...value.excludedCountries, country] })
      }
      setNewCountry("")
    }
  }

  const handleRemoveCountry = (country: string) => {
    onChange({
      ...value,
      excludedCountries: value.excludedCountries.filter((c) => c !== country),
    })
  }

  return (
    <div className="min-w-0">
      <div className={labelClass}>Excluded Countries</div>
      <div className="flex min-h-[38px] flex-wrap items-center gap-2 rounded-md border border-border bg-panel-2 px-3 py-1.5 focus-within:border-accent">
        {value.excludedCountries.map((country) => (
          <span
            key={country}
            className="flex items-center gap-1 rounded bg-hair px-2 py-1 text-xs font-medium text-fg"
          >
            {country}
            <button
              type="button"
              onClick={() => handleRemoveCountry(country)}
              className="text-muted transition-colors hover:text-head"
            >
              <X className="h-3 w-3" />
            </button>
          </span>
        ))}
        <input
          type="text"
          placeholder="+ Add (Enter)"
          value={newCountry}
          onChange={(e) => setNewCountry(e.target.value)}
          onKeyDown={handleAddCountry}
          className="min-w-[110px] flex-1 bg-transparent text-sm text-fg outline-none placeholder:text-faint"
        />
      </div>
    </div>
  )
}

/** Composed default: grade + optimise-for side by side, exclusions beneath.
 *  Retained for callers that don't need to interleave their own fields. */
export function RerouteParamsForm({ value, grades, onChange, compact }: RerouteParamsFormProps) {
  return (
    <>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <CrudeGradeField value={value} onChange={onChange} grades={grades} />
        <OptimiseForField value={value} onChange={onChange} compact={compact} />
      </div>
      <div className="mt-3">
        <ExcludedCountriesField value={value} onChange={onChange} />
      </div>
    </>
  )
}
