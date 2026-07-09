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

interface RerouteParamsFormProps {
  value: RerouteParamsValue
  grades: string[]
  onChange: (next: RerouteParamsValue) => void
  /** Optional: when rendered inside a <select> option can't hold React nodes.
   *  Pass compact=true to skip the InfoTooltip wrappers. */
  compact?: boolean
}

/** Controlled form for the two procurement-style dropdowns
 *  (Crude Grade + Optimise For). Shared by Reroute Matrix and War Room. */
export function RerouteParamsForm({ value, grades, onChange, compact }: RerouteParamsFormProps) {
  const [newCountry, setNewCountry] = useState("")

  const selectClass =
    "w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-200 outline-none focus:border-cyan-500"

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
      excludedCountries: value.excludedCountries.filter(c => c !== country) 
    })
  }

  return (
    <>
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
      <div>
        <div className="mb-1.5 text-[11px] font-medium uppercase tracking-wider text-slate-400">
          {compact ? "Crude Grade" : "Crude Grade"}
        </div>
        <select
          value={value.grade}
          onChange={(e) => onChange({ ...value, grade: e.target.value })}
          className={selectClass}
        >
          {grades.length === 0
            ? <option value="Any">Any</option>
            : grades.map((g) => <option key={g}>{g}</option>)
          }
        </select>
        {value.grade !== "Any" && (
          <div className="mt-2 flex items-center gap-3 text-xs">
            <label className="flex items-center gap-1.5 text-slate-300 cursor-pointer">
              <input 
                type="radio" 
                checked={!value.strictGradeMatch} 
                onChange={() => onChange({ ...value, strictGradeMatch: false })}
                className="accent-cyan-500"
              />
              Allow substitutes
            </label>
            <label className="flex items-center gap-1.5 text-slate-300 cursor-pointer">
              <input 
                type="radio" 
                checked={value.strictGradeMatch} 
                onChange={() => onChange({ ...value, strictGradeMatch: true })}
                className="accent-cyan-500"
              />
              Strict match
            </label>
          </div>
        )}
      </div>

      <div>
        <div className="mb-1.5 text-[11px] font-medium uppercase tracking-wider text-slate-400">
          {compact ? "Optimise For" : <InfoTooltip term="Landed Cost" label="Optimise For" />}
        </div>
        <select
          value={value.mode}
          onChange={(e) => onChange({ ...value, mode: e.target.value as "cost" | "speed" })}
          className={selectClass}
        >
          <option value="cost">Lowest Landed Cost</option>
          <option value="speed">Fastest Arrival (Speed)</option>
        </select>
      </div>
    </div>
    
    <div className="mt-3">
      <div className="mb-1.5 flex items-center gap-1 text-[11px] font-medium uppercase tracking-wider text-slate-400">
        Excluded Countries
      </div>
      <div className="flex flex-wrap items-center gap-2 rounded-md border border-slate-700 bg-slate-950 px-3 py-2 focus-within:border-cyan-500">
        {value.excludedCountries.map(country => (
          <span 
            key={country} 
            className="flex items-center gap-1 rounded bg-[#2a304f] px-2 py-1 text-xs font-medium text-slate-200"
          >
            {country}
            <button 
              type="button" 
              onClick={() => handleRemoveCountry(country)}
              className="text-slate-400 hover:text-white transition-colors"
            >
              <X className="h-3 w-3" />
            </button>
          </span>
        ))}
        <input
          type="text"
          placeholder="+ Add Country (Press Enter)"
          value={newCountry}
          onChange={(e) => setNewCountry(e.target.value)}
          onKeyDown={handleAddCountry}
          className="flex-1 min-w-[160px] bg-transparent text-sm text-slate-200 outline-none placeholder:text-slate-500"
        />
      </div>
    </div>
    </>
  )
}
