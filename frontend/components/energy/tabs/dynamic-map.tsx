"use client"

import { MapContainer, TileLayer, CircleMarker, Popup, Circle } from "react-leaflet"
import "leaflet/dist/leaflet.css"
import type { VesselPosition, RiskEvent } from "@/lib/api"
import { useTheme } from "@/components/theme-provider"
import { useChartTheme, severityHex } from "../chart-theme"

interface DynamicMapProps {
  vessels: VesselPosition[]
  events: RiskEvent[]
}

const CHOKEPOINT_COORDS: Record<string, [number, number]> = {
  "Strait of Hormuz": [26.56, 56.25],
  "Suez Canal": [30.58, 32.26],
  "Bab-el-Mandeb": [12.58, 43.41],
  "Strait of Malacca": [1.25, 103.82],
  "Cape of Good Hope": [-34.35, 18.47],
  "Panama Canal": [9.08, -79.68],
  "Turkish Straits": [41.11, 29.07],
  "Strait of Gibraltar": [35.98, -5.49],
}

import type { LatLngBoundsExpression } from "leaflet"

export default function DynamicMap({ vessels, events }: DynamicMapProps) {
  const { theme } = useTheme()
  const c = useChartTheme()
  const maxBounds: LatLngBoundsExpression = [
    [-90, -180],
    [90, 180],
  ]

  const tileUrl =
    theme === "dark"
      ? "https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png"
      : "https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}.png"

  // Light basemap tiles are higher-contrast, so the risk circles need a little
  // more fill to stay as legible as they are over the dark basemap.
  const riskFillOpacity = theme === "dark" ? 0.2 : 0.25

  return (
    <MapContainer
      center={[25.0, 50.0]}
      zoom={3}
      minZoom={2.5}
      maxBounds={maxBounds}
      maxBoundsViscosity={1.0}
      style={{ height: "100%", minHeight: "540px", width: "100%", background: "var(--t-map-bg)", position: "absolute", top: 0, left: 0, right: 0, bottom: 0 }}
      zoomControl={false}
      attributionControl={false}
    >
      {/* `key` remounts only the tile layer on theme change so stale tiles are
          dropped cleanly. The MapContainer must NOT be keyed — that would reset
          the user's pan/zoom. */}
      <TileLayer
        key={tileUrl}
        url={tileUrl}
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>'
        noWrap={true}
        bounds={maxBounds}
      />

      {/* Risk Events / Heatmaps */}
      {events.flatMap((ev) => {
        const color = severityHex(ev.severity_label, c)

        return (ev.affected_chokepoints || []).map((cp) => {
          const center = CHOKEPOINT_COORDS[cp]
          if (!center) return null
          
          return (
            <Circle 
              key={`event-${ev.id}-${cp}`} 
              center={center} 
              radius={300000 * ev.severity} 
              pathOptions={{ color, fillColor: color, fillOpacity: riskFillOpacity, weight: 1 }}
            >
              <Popup>
                <strong>{ev.region}</strong><br/>
                Chokepoint: {cp}<br/>
                {ev.severity_label} Risk<br/>
                {ev.disruption_type}
              </Popup>
            </Circle>
          )
        })
      })}

      {/* Vessels */}
      {vessels.map((v, i) => (
        <CircleMarker
          key={`vessel-${v.mmsi || i}`}
          center={[v.lat, v.lon]}
          radius={2}
          pathOptions={{ color: c.accent, fillColor: c.accent, fillOpacity: 0.8, weight: 0 }}
        >
          <Popup>
            <strong>{v.vessel_name}</strong><br/>
            Speed: {v.speed.toFixed(1)} knots<br/>
            Region: {v.region}
          </Popup>
        </CircleMarker>
      ))}
    </MapContainer>
  )
}
