export const REGIONS = [
  "All Regions",
  "Persian Gulf",
  "Russia / Black Sea",
  "North America",
  "West Africa",
  "Southeast Asia",
] as const

export type Severity = "CRITICAL" | "HIGH" | "MODERATE" | "LOW"

export const sprSites = [
  { name: "Bryan Mound, TX", pct: 82 },
  { name: "Big Hill, TX", pct: 64 },
  { name: "West Hackberry, LA", pct: 71 },
  { name: "Bayou Choctaw, LA", pct: 58 },
]

export const demandPlaybook = [
  { action: "Refinery Run-Rate Cut", impact: "0.60 mbpd", status: "Ready" },
  { action: "Strategic Draw Release", impact: "1.10 mbpd", status: "Armed" },
  { action: "Odd/Even Rationing", impact: "0.40 mbpd", status: "Standby" },
  { action: "Industrial Curtailment", impact: "0.35 mbpd", status: "Standby" },
]

export const crisisScenarios = [
  "Scenario A: Hormuz Mine Closure",
  "Scenario B: Suez Canal Drone Strikes",
  "Scenario C: Black Sea Naval Blockade",
  "Scenario D: Malacca Piracy Surge",
]

export const targetRefineries = [
  "Leuna, Germany",
  "Rotterdam, Netherlands",
  "Jamnagar, India",
  "Ulsan, South Korea",
]
