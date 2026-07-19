"use client"

import { MapContainer, TileLayer, CircleMarker, Circle, Tooltip } from "react-leaflet"
import "leaflet/dist/leaflet.css"
import { useTheme } from "@/components/theme-provider"
import { useChartTheme } from "../chart-theme"

/**
 * Small locator map for the drill-down modals: where the chokepoint or
 * producer sits, with its risk rendered as a proportional halo.
 *
 * Default-exported and loaded via next/dynamic with `ssr: false` — Leaflet
 * touches `window` at import time and cannot be server-rendered.
 */
export default function MiniMap({
  center,
  zoom,
  label,
  risk,
}: {
  center: [number, number]
  zoom: number
  label: string
  risk: number
}) {
  const { theme } = useTheme()
  const c = useChartTheme()

  const tileUrl =
    theme === "dark"
      ? "https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png"
      : "https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}.png"

  const tone = risk > 0.6 ? c.crit : risk > 0.4 ? c.orange : c.safe

  return (
    <MapContainer
      center={center}
      zoom={zoom}
      minZoom={2}
      scrollWheelZoom={false}
      zoomControl={false}
      attributionControl={false}
      style={{ height: "100%", width: "100%", background: "var(--t-map-bg)" }}
    >
      {/* Keyed so a theme switch swaps basemaps cleanly without remounting the
          map itself (which would reset the view). */}
      <TileLayer key={tileUrl} url={tileUrl} noWrap />

      {/* Halo scaled by risk, so severity reads at a glance. */}
      <Circle
        center={center}
        radius={140000 + risk * 420000}
        pathOptions={{ color: tone, fillColor: tone, fillOpacity: 0.18, weight: 1 }}
      />
      <CircleMarker
        center={center}
        radius={6}
        pathOptions={{ color: tone, fillColor: tone, fillOpacity: 0.95, weight: 2 }}
      >
        <Tooltip direction="top" offset={[0, -6]} permanent>
          {label}
        </Tooltip>
      </CircleMarker>
    </MapContainer>
  )
}
