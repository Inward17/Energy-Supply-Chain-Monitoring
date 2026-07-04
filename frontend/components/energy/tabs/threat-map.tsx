"use client"

import { useEffect, useState } from "react"
import dynamic from "next/dynamic"
import { Globe, Ship, Loader2 } from "lucide-react"
import { Panel } from "../ui"
import { fetchVessels, fetchRiskEvents, type VesselPosition, type RiskEvent } from "@/lib/api"

// Dynamically import the map component with SSR disabled
const DynamicMap = dynamic(() => import("./dynamic-map"), { 
  ssr: false,
  loading: () => <div className="flex h-full w-full items-center justify-center text-slate-500">Loading Map...</div>
})

export function ThreatMap() {
  const [vessels, setVessels] = useState<VesselPosition[]>([])
  const [events, setEvents] = useState<RiskEvent[]>([])

  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    Promise.all([fetchVessels(), fetchRiskEvents(20)])
      .then(([v, e]) => {
        setVessels(v)
        setEvents(e)
      })
      .catch((err) => {
        console.error("Failed to load map data", err)
        setError(String(err))
      })
      .finally(() => setLoading(false))
  }, [])

  return (
    <Panel title="Global Threat Map" icon={<Globe className="h-4 w-4 text-cyan-400" />}>
      <div className="p-4">
        {error && <div className="mb-4 text-rose-500 bg-rose-500/10 p-2 rounded">Failed to load map data: {error}</div>}
        <div className="relative h-[540px] w-full overflow-hidden rounded-lg border border-slate-800 bg-slate-950">
          
          {loading ? (
            <div className="flex h-full w-full items-center justify-center">
              <Loader2 className="h-8 w-8 animate-spin text-cyan-500" />
            </div>
          ) : (
            <DynamicMap vessels={vessels} events={events} />
          )}

          {/* Legend */}
          <div className="absolute bottom-3 left-3 z-[1000] flex flex-col gap-1.5 rounded-md border border-slate-800 bg-slate-950/80 px-3 py-2 text-[11px] text-slate-300 backdrop-blur-sm pointer-events-none">
            <span className="flex items-center gap-2">
              <span className="h-2 w-2 rounded-full bg-cyan-400 shadow-[0_0_6px_1px_rgba(34,211,238,0.7)]" />
              Tracked Vessel
            </span>
            <span className="flex items-center gap-2">
              <span className="h-2 w-2 rounded-full bg-rose-500" />
              Risk Heatmap
            </span>
          </div>

          <div className="absolute right-3 top-3 z-[1000] flex items-center gap-1.5 rounded-md border border-slate-800 bg-slate-950/80 px-3 py-1.5 text-[11px] font-medium text-cyan-300 pointer-events-none">
            <Ship className="h-3.5 w-3.5" />
            {vessels.length} vessels live
          </div>
        </div>
        <p className="mt-3 text-[10px] text-slate-500 italic">
          * Note: Vessel positions (AIS) and geopolitical risk heatmaps are independent signals. A region may exhibit high geopolitical risk without active vessel tracking coverage.
        </p>
      </div>
    </Panel>
  )
}
