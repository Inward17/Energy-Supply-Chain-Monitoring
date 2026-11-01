import type { SVGProps } from "react"

/*
 * Tab symbols taken verbatim from the MERIDIAN design (Redesign.dc.html).
 * The path data is copied from the design's ICONS map rather than substituted
 * with the nearest lucide equivalent, so the glyphs match the spec exactly.
 */

function Glyph({ children, ...props }: SVGProps<SVGSVGElement> & { children: React.ReactNode }) {
  return (
    <svg
      width={15}
      height={15}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      style={{ flexShrink: 0 }}
      aria-hidden="true"
      {...props}
    >
      {children}
    </svg>
  )
}

/** Radar sweep — Threat Map */
export function IconThreat(props: SVGProps<SVGSVGElement>) {
  return (
    <Glyph {...props}>
      <path d="M19.07 4.93A10 10 0 0 0 6.99 3.34" />
      <path d="M4 6h.01" />
      <path d="M2.29 9.62A10 10 0 1 0 21.31 8.35" />
      <path d="M16.24 7.76A6 6 0 1 0 8.23 16.67" />
      <path d="M12 18h.01" />
      <path d="M17.99 11.66A6 6 0 0 1 15.77 16.67" />
      <circle cx={12} cy={12} r={2} />
      <path d="m13.41 10.59 5.66-5.66" />
    </Glyph>
  )
}

/** Shield with alert — Risk Intelligence */
export function IconRisk(props: SVGProps<SVGSVGElement>) {
  return (
    <Glyph {...props}>
      <path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z" />
      <path d="M12 8v4" />
      <path d="M12 16h.01" />
    </Glyph>
  )
}

/** Pulse trace — Market Pulse */
export function IconMarket(props: SVGProps<SVGSVGElement>) {
  return (
    <Glyph {...props}>
      <path d="M22 12h-2.48a2 2 0 0 0-1.93 1.46l-2.35 8.36a.25.25 0 0 1-.48 0L9.24 2.18a.25.25 0 0 0-.48 0l-2.35 8.36A2 2 0 0 1 4.49 12H2" />
    </Glyph>
  )
}

/** Two nodes joined by a re-routed path — Reroute Matrix */
export function IconReroute(props: SVGProps<SVGSVGElement>) {
  return (
    <Glyph {...props}>
      <circle cx={6} cy={19} r={3} />
      <path d="M9 19h8.5a3.5 3.5 0 0 0 0-7h-11a3.5 3.5 0 0 1 0-7H15" />
      <circle cx={18} cy={5} r={3} />
    </Glyph>
  )
}

/** Fuel pump — SPR Optimizer */
export function IconSpr(props: SVGProps<SVGSVGElement>) {
  return (
    <Glyph {...props}>
      <line x1={3} y1={22} x2={15} y2={22} />
      <line x1={4} y1={9} x2={14} y2={9} />
      <path d="M14 22V4a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v18" />
      <path d="M14 13h2a2 2 0 0 1 2 2v2a2 2 0 0 0 2 2a2 2 0 0 0 2-2V9.83a2 2 0 0 0-.59-1.42L18 5" />
    </Glyph>
  )
}

/** Concentric target — War Room */
export function IconWar(props: SVGProps<SVGSVGElement>) {
  return (
    <Glyph {...props}>
      <circle cx={12} cy={12} r={10} />
      <circle cx={12} cy={12} r={6} />
      <circle cx={12} cy={12} r={2} />
    </Glyph>
  )
}

/** Rewind — Historical Validation */
export function IconHistorical(props: SVGProps<SVGSVGElement>) {
  return (
    <Glyph {...props}>
      <polygon points="11 19 2 12 11 5 11 19" />
      <polygon points="22 19 13 12 22 5 22 19" />
    </Glyph>
  )
}
