/**
 * Static geography for the drill-down maps.
 *
 * Kept client-side deliberately: these are fixed reference points, so fetching
 * them would add a request without ever changing the answer.
 */

export const CHOKEPOINT_COORDS: Record<string, [number, number]> = {
  "Strait of Hormuz": [26.56, 56.25],
  "Suez Canal": [30.58, 32.26],
  "Bab-el-Mandeb": [12.58, 43.41],
  "Strait of Malacca": [1.25, 103.82],
  "Cape of Good Hope": [-34.35, 18.47],
  "Panama Canal": [9.08, -79.68],
  "Turkish Straits": [41.11, 29.07],
  "Strait of Gibraltar": [35.98, -5.49],
}

/** Approximate centroids for producer nations tracked by the risk matrix. */
export const PRODUCER_COORDS: Record<string, [number, number]> = {
  "Saudi Arabia": [23.89, 45.08],
  Iran: [32.43, 53.69],
  Iraq: [33.22, 43.68],
  Kuwait: [29.31, 47.48],
  Qatar: [25.35, 51.18],
  "United Arab Emirates": [23.42, 53.85],
  Oman: [21.51, 55.92],
  Russia: [61.52, 105.32],
  Kazakhstan: [48.02, 66.92],
  Azerbaijan: [40.14, 47.58],
  Nigeria: [9.08, 8.68],
  Angola: [-11.2, 17.87],
  Algeria: [28.03, 1.66],
  Libya: [26.34, 17.23],
  Gabon: [-0.8, 11.61],
  Venezuela: [6.42, -66.59],
  Brazil: [-14.24, -51.93],
  Mexico: [23.63, -102.55],
  Ecuador: [-1.83, -78.18],
  "United States": [39.83, -98.58],
  Canada: [56.13, -106.35],
  Norway: [60.47, 8.47],
  "United Kingdom": [55.38, -3.44],
  Indonesia: [-0.79, 113.92],
  Malaysia: [4.21, 101.98],
}

/** Zoom that frames a chokepoint's approaches vs a whole country. */
export const CHOKEPOINT_ZOOM = 5
export const PRODUCER_ZOOM = 3

export function coordsFor(kind: "chokepoint" | "producer", name: string): [number, number] | null {
  const table = kind === "chokepoint" ? CHOKEPOINT_COORDS : PRODUCER_COORDS
  return table[name] ?? null
}
