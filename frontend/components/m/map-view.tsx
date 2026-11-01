"use client"

import { Fragment } from "react"
import { Circle, CircleMarker, MapContainer, TileLayer, Tooltip } from "react-leaflet"
import type { LatLngBoundsExpression } from "leaflet"
import type { ChokepointRisk, VesselPosition } from "@/lib/api"
import { CHOKEPOINT_COORDS, basemap } from "./geo"
import { riskColor } from "./ui"
import { cssColor, useTheme } from "./theme"

const BOUNDS: LatLngBoundsExpression = [[-75, -180], [85, 180]]

/** Default-exported for next/dynamic (Leaflet touches window at import). */
export default function MapView({
  chokepoints,
  vessels,
  showHalos,
  showVessels,
  selected,
  onSelect,
}: {
  chokepoints: ChokepointRisk[]
  vessels: VesselPosition[]
  showHalos: boolean
  showVessels: boolean
  selected: string | null
  onSelect: (name: string) => void
}) {
  const [theme] = useTheme()
  const tiles = basemap(theme)
  // Leaflet writes colours into SVG attributes: resolve the theme variables.
  const C = (v: string) => cssColor(v)
  return (
    <MapContainer
      center={[24, 52]}
      zoom={3}
      minZoom={2}
      maxBounds={BOUNDS}
      maxBoundsViscosity={1}
      zoomControl
      style={{ position: "absolute", inset: 0, background: "var(--x-0a0e13)" }}
    >
      <TileLayer key={tiles.url} url={tiles.url} attribution={tiles.attribution} noWrap />
      {chokepoints.map((c) => {
        const at = CHOKEPOINT_COORDS[c.name]
        if (!at) return null
        const col = C(riskColor(c.risk_score))
        const on = c.name === selected
        return (
          <Fragment key={c.name}>
            {showHalos && (
              <Circle
                center={at}
                radius={120000 + c.risk_score * 520000}
                pathOptions={{ color: col, fillColor: col, fillOpacity: 0.14, weight: 1, opacity: 0.5 }}
                eventHandlers={{ click: () => onSelect(c.name) }}
              />
            )}
            <CircleMarker
              center={at}
              radius={on ? 10 : c.risk_score >= 0.4 ? 9 : 6}
              pathOptions={{ color: on ? C("var(--x-f5f7fa)") : C("var(--x-0a0e13)"), weight: on ? 3 : 2, fillColor: col, fillOpacity: 1 }}
              eventHandlers={{ click: () => onSelect(c.name) }}
            >
              <Tooltip direction="right" offset={[10, 0]} permanent={c.risk_score >= 0.4 || on} className="m-label">
                {c.name.replace("Strait of ", "")} <span style={{ fontFamily: "var(--font-plex-mono)", color: col }}>{c.risk_score.toFixed(2)}</span>
              </Tooltip>
            </CircleMarker>
          </Fragment>
        )
      })}
      {showVessels &&
        vessels.map((v, i) => (
          <CircleMarker key={`${v.mmsi ?? i}`} center={[v.lat, v.lon]} radius={3} pathOptions={{ color: C("var(--x-5aaeff)"), fillColor: C("var(--x-5aaeff)"), fillOpacity: 0.85, weight: 0 }}>
            <Tooltip>{v.vessel_name || "Tanker"} · {v.speed?.toFixed?.(1) ?? "—"} kn</Tooltip>
          </CircleMarker>
        ))}
    </MapContainer>
  )
}
