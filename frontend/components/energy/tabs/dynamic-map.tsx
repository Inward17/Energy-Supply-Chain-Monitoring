"use client"

import { MapContainer, TileLayer, CircleMarker, Popup, Circle } from "react-leaflet"
import "leaflet/dist/leaflet.css"
import type { VesselPosition, RiskEvent } from "@/lib/api"

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
  const maxBounds: LatLngBoundsExpression = [
    [-90, -180],
    [90, 180],
  ]

  return (
    <MapContainer 
      center={[25.0, 50.0]} 
      zoom={3} 
      minZoom={2.5}
      maxBounds={maxBounds}
      maxBoundsViscosity={1.0}
      style={{ height: "100%", width: "100%", background: "#020617" }}
      zoomControl={false}
      attributionControl={false}
    >
      <TileLayer
        url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
        noWrap={true}
        bounds={maxBounds}
      />
      
      {/* Risk Events / Heatmaps */}
      {events.flatMap((ev) => {
        const color = ev.severity_label === "CRITICAL" ? "#e11d48" : 
                      ev.severity_label === "HIGH" ? "#f97316" : 
                      ev.severity_label === "MODERATE" ? "#eab308" : "#3b82f6"
                      
        return (ev.affected_chokepoints || []).map((cp) => {
          const center = CHOKEPOINT_COORDS[cp]
          if (!center) return null
          
          return (
            <Circle 
              key={`event-${ev.id}-${cp}`} 
              center={center} 
              radius={300000 * ev.severity} 
              pathOptions={{ color, fillColor: color, fillOpacity: 0.2, weight: 1 }}
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
          pathOptions={{ color: "#22d3ee", fillColor: "#22d3ee", fillOpacity: 0.8, weight: 0 }}
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
