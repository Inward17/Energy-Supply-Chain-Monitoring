"use client"

import {
  IconThreat,
  IconRisk,
  IconMarket,
  IconReroute,
  IconSpr,
  IconWar,
  IconHistorical,
} from "./icons"

export const TABS = [
  { key: "threat", label: "Threat Map", icon: IconThreat },
  { key: "risk", label: "Risk Intelligence", icon: IconRisk },
  { key: "market", label: "Market Pulse", icon: IconMarket },
  { key: "reroute", label: "Reroute Matrix", icon: IconReroute },
  { key: "spr", label: "SPR Optimizer", icon: IconSpr },
  { key: "war", label: "War Room", icon: IconWar },
  { key: "historical", label: "Historical Validation", icon: IconHistorical },
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
    <nav className="flex flex-wrap gap-1 rounded-[10px] border border-border bg-panel p-1.5">
      {TABS.map((tab) => {
        const Icon = tab.icon
        const isActive = active === tab.key
        return (
          <button
            key={tab.key}
            type="button"
            onClick={() => onChange(tab.key)}
            className={`flex items-center gap-[7px] rounded-[7px] px-3.5 py-2 text-[12.5px] font-medium transition-colors ${
              isActive
                ? "bg-accent-soft text-accent ring-1 ring-inset ring-accent-border"
                : "text-muted hover:bg-hair hover:text-fg"
            }`}
          >
            <Icon />
            {tab.label}
          </button>
        )
      })}
    </nav>
  )
}
