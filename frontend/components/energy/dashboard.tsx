"use client"

import { useState } from "react"
import { Activity } from "lucide-react"
import { Sidebar } from "./sidebar"
import { KpiHeader } from "./kpi-header"
import { TabNav, type TabKey } from "./tab-nav"
import { ThreatMap } from "./tabs/threat-map"
import { RiskIntelligence } from "./tabs/risk-intelligence"
import { MarketPulse } from "./tabs/market-pulse"
import { RerouteMatrix } from "./tabs/reroute-matrix"
import { SprOptimizer } from "./tabs/spr-optimizer"
import { WarRoom } from "./tabs/war-room"

export function Dashboard() {
  const [region, setRegion] = useState("All Regions")
  const [severity, setSeverity] = useState(45)
  const [autoRefresh, setAutoRefresh] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [tab, setTab] = useState<TabKey>("war")

  function handleRefresh() {
    setRefreshing(true)
    setTimeout(() => setRefreshing(false), 1200)
  }

  return (
    <div className="dark flex h-screen overflow-hidden bg-slate-950 text-slate-300">
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
        <header className="flex items-center justify-between border-b border-slate-800 bg-slate-900/40 px-6 py-3">
          <div className="flex items-center gap-2.5">
            <Activity className="h-5 w-5 text-cyan-400" />
            <div>
              <h1 className="text-sm font-bold tracking-wide text-white">
                Energy Supply Chain Resilience OS
              </h1>
              <p className="text-[11px] text-slate-500">Command Center · Live</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <span className="relative flex h-2 w-2">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75" />
              <span className="relative inline-flex h-2 w-2 rounded-full bg-emerald-400" />
            </span>
            <span className="text-xs text-emerald-400">Systems Nominal</span>
          </div>
        </header>

        <div className="flex-1 space-y-4 overflow-y-auto p-6">
          <KpiHeader />
          <TabNav active={tab} onChange={setTab} />

          {tab === "threat" && <ThreatMap />}
          {tab === "risk" && <RiskIntelligence />}
          {tab === "market" && <MarketPulse />}
          {tab === "reroute" && <RerouteMatrix />}
          {tab === "spr" && <SprOptimizer />}
          {tab === "war" && <WarRoom />}
        </div>
      </main>
    </div>
  )
}
