"use client"

import { Globe, CircleDot, TrendingUp, Crosshair, Droplet, Swords } from "lucide-react"

export const TABS = [
  { key: "threat", label: "Threat Map", icon: Globe },
  { key: "risk", label: "Risk Intelligence", icon: CircleDot },
  { key: "market", label: "Market Pulse", icon: TrendingUp },
  { key: "reroute", label: "Reroute Matrix", icon: Crosshair },
  { key: "spr", label: "SPR Optimizer", icon: Droplet },
  { key: "war", label: "War Room", icon: Swords },
] as const

export type TabKey = (typeof TABS)[number]["key"]

export function TabNav({
  active,
  onChange,
}: {
  active: TabKey
  onChange: (key: TabKey) => void
}) {
  return (
    <nav className="flex flex-wrap gap-1.5 rounded-lg border border-slate-800 bg-slate-900/40 p-1.5">
      {TABS.map((tab) => {
        const Icon = tab.icon
        const isActive = active === tab.key
        return (
          <button
            key={tab.key}
            type="button"
            onClick={() => onChange(tab.key)}
            className={`flex items-center gap-2 rounded-md px-3.5 py-2 text-sm font-medium transition-colors ${
              isActive
                ? "bg-cyan-500/15 text-cyan-300 ring-1 ring-inset ring-cyan-500/40"
                : "text-slate-400 hover:bg-slate-800/60 hover:text-slate-200"
            }`}
          >
            <Icon className="h-4 w-4" />
            {tab.label}
          </button>
        )
      })}
    </nav>
  )
}
