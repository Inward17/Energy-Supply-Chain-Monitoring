"use client"

import { useEffect, useState } from "react"
import dynamic from "next/dynamic"
import { Ship, Loader2 } from "lucide-react"
import { Panel } from "../ui"
import { fetchVessels, fetchRiskEvents, fetchLiveMetrics, type VesselPosition, type RiskEvent } from "@/lib/api"

// Dynamically import the map component with SSR disabled
const DynamicMap = dynamic(() => import("./dynamic-map"), { 
  ssr: false,
  loading: () => <div className="flex h-full w-full items-center justify-center text-muted">Loading Map...</div>
})

export function ThreatMap() {
  const [vessels, setVessels] = useState<VesselPosition[]>([])
  const [events, setEvents] = useState<RiskEvent[]>([])
  const [aisConfigured, setAisConfigured] = useState<boolean>(true)

  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    Promise.all([fetchVessels(), fetchRiskEvents(20), fetchLiveMetrics()])
      .then(([v, e, metrics]) => {
        setVessels(v)
        setEvents(e)
        setAisConfigured(metrics.ais_configured !== false)
      })
      .catch((err) => {
        console.error("Failed to load map data", err)
        setError(String(err))
      })
      .finally(() => setLoading(false))
  }, [])

  return (
    <Panel title="Global Threat Map" tone="accent">
      <div className="p-4 flex flex-col h-full">
        {!aisConfigured && (
          <div className="mb-4 text-orange bg-orange-soft p-3 rounded border border-orange/20 text-sm">
            <strong>AISStream Key Missing:</strong> Live vessel telemetry is disabled. Showing last-known historical vessel positions.
          </div>
        )}
        {error && <div className="mb-4 text-crit bg-crit-soft p-2 rounded">Failed to load map data: {error}</div>}
        <div className="relative flex-1 min-h-[540px] w-full overflow-hidden rounded-lg border border-border bg-panel-2">
          
          {loading ? (
            <div className="flex h-full w-full items-center justify-center">
              <Loader2 className="h-8 w-8 animate-spin text-accent" />
            </div>
          ) : (
            <DynamicMap vessels={vessels} events={events} />
          )}

          {/* Legend */}
          <div className="absolute bottom-3 left-3 z-[1000] flex flex-col gap-1.5 rounded-md border border-border bg-panel/90 px-3 py-2 text-[11px] text-fg backdrop-blur-sm pointer-events-none">
            <span className="flex items-center gap-2">
              <span className="h-2 w-2 rounded-full bg-accent shadow-[0_0_6px_1px_rgba(34,211,238,0.7)]" />
              Tracked Vessel
            </span>
            <span className="flex items-center gap-2">
              <span className="h-2 w-2 rounded-full bg-crit" />
              Risk Heatmap
            </span>
          </div>

          <div className="absolute right-3 top-3 z-[1000] flex items-center gap-1.5 rounded-md border border-border bg-panel/90 px-3 py-1.5 text-[11px] font-medium text-accent pointer-events-none">
            <Ship className="h-3.5 w-3.5" />
            {vessels.length} vessels live
          </div>
        </div>
        <p className="mt-3 text-[10px] text-muted italic">
          * Note: Vessel positions (AIS) and geopolitical risk heatmaps are independent signals. A region may exhibit high geopolitical risk without active vessel tracking coverage.
        </p>
      </div>
    </Panel>
  )
}
