"use client"

import { useCallback, useRef, useState } from "react"
import { Moon, Sun } from "lucide-react"
import { useTheme } from "@/components/theme-provider"
import { Sidebar } from "./sidebar"
import { KpiHeader } from "./kpi-header"
import { TabNav, type TabKey } from "./tab-nav"
import { ThreatMap } from "./tabs/threat-map"
import { RiskIntelligence } from "./tabs/risk-intelligence"
import { MarketPulse } from "./tabs/market-pulse"
import { RerouteMatrix } from "./tabs/reroute-matrix"
import { SprOptimizer } from "./tabs/spr-optimizer"
import { WarRoom } from "./tabs/war-room"
import { HistoricalValidation } from "./tabs/historical-validation"

const TAB_TITLES: Record<TabKey, [string, string]> = {
  threat: ["Global Threat Map", "live vessel tracking & risk heatmap"],
  risk: ["Risk Intelligence", "sentinel events, SDI timeline & chokepoints"],
  market: ["Market Pulse", "crude, freight & product benchmarks"],
  reroute: ["Reroute Matrix", "procurement & producer risk optimization"],
  spr: ["SPR Optimizer", "reserve burn-down & demand levers"],
  war: ["Executive War Room", "scenario simulation & reroute optimization"],
  historical: ["Historical Validation", "backtests against past crises"],
}

export function Dashboard() {
  const [region, setRegion] = useState("All Regions")
  const [severity, setSeverity] = useState(45)
  const [autoRefresh, setAutoRefresh] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [refreshToken, setRefreshToken] = useState(0)
  const [tab, setTab] = useState<TabKey>("war")
  const refreshTokenRef = useRef(0)
  const pendingRefreshesRef = useRef<Set<"kpi" | "risk">>(new Set())
  const { theme, toggle } = useTheme()

  const handleRefresh = useCallback(() => {
    const nextToken = refreshTokenRef.current + 1
    refreshTokenRef.current = nextToken
    pendingRefreshesRef.current = new Set(tab === "risk" ? ["kpi", "risk"] : ["kpi"])
    setRefreshing(true)
    setRefreshToken(nextToken)
  }, [tab])

  const handleRefreshComplete = useCallback((target: "kpi" | "risk", completedToken: number) => {
    if (completedToken !== refreshTokenRef.current) return

    const pending = pendingRefreshesRef.current
    pending.delete(target)
    if (pending.size === 0) setRefreshing(false)
  }, [])

  const [activeTitle, activeSub] = TAB_TITLES[tab]

  return (
    <div className="flex h-screen overflow-hidden bg-bg text-fg">
      <Sidebar
        region={region}
        setRegion={setRegion}
        severity={severity}
        setSeverity={setSeverity}
        autoRefresh={autoRefresh}
        setAutoRefresh={setAutoRefresh}
        onRefresh={handleRefresh}
        refreshing={refreshing}
      />

      <main className="flex flex-1 flex-col overflow-hidden">
        <header className="flex items-center justify-between border-b border-border bg-panel px-6 py-3">
          <div>
            <h1 className="text-[15px] font-bold text-head">{activeTitle}</h1>
            <p className="mt-0.5 text-[11px] text-faint">Command Center · {activeSub}</p>
          </div>

          <div className="flex items-center gap-4">
            <div className="flex items-center rounded-full border border-border p-0.5">
              <button
                type="button"
                onClick={theme === "dark" ? toggle : undefined}
                aria-label="Switch to light theme"
                aria-pressed={theme === "light"}
                className={`flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-semibold transition-colors ${
                  theme === "light" ? "bg-accent-soft text-accent" : "text-muted hover:text-fg"
                }`}
              >
                <Sun className="h-3.5 w-3.5" />
                Light
              </button>
              <button
                type="button"
                onClick={theme === "light" ? toggle : undefined}
                aria-label="Switch to dark theme"
                aria-pressed={theme === "dark"}
                className={`flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-semibold transition-colors ${
                  theme === "dark" ? "bg-accent-soft text-accent" : "text-muted hover:text-fg"
                }`}
              >
                <Moon className="h-3.5 w-3.5" />
                Dark
              </button>
            </div>

            <div className="flex items-center gap-2 rounded-full bg-safe-soft px-3 py-1.5">
              <span className="relative flex h-2 w-2">
                <span className="absolute inline-flex h-full w-full rounded-full bg-safe [animation:omping_1.6s_ease-out_infinite]" />
                <span className="relative inline-flex h-2 w-2 rounded-full bg-safe" />
              </span>
              <span className="text-xs font-semibold text-safe">Systems Nominal</span>
            </div>
          </div>
        </header>

        {/* NOTE: `space-y-4` is asserted on by tests/e2e/smoke.spec.ts — keep it. */}
        <div className="flex-1 space-y-4 overflow-y-auto p-6">
          <KpiHeader
            autoRefresh={autoRefresh}
            refreshToken={refreshToken}
            onRefreshComplete={handleRefreshComplete}
          />
          <TabNav active={tab} onChange={setTab} />

          {tab === "threat" && <ThreatMap />}
          {tab === "risk" && (
            <RiskIntelligence
              autoRefresh={autoRefresh}
              refreshToken={refreshToken}
              onRefreshComplete={handleRefreshComplete}
            />
          )}
          {tab === "market" && <MarketPulse />}
          {tab === "reroute" && <RerouteMatrix />}
          {tab === "spr" && <SprOptimizer />}
          {tab === "war" && <WarRoom />}
          {tab === "historical" && <HistoricalValidation />}
        </div>
      </main>
    </div>
  )
}
