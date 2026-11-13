"use client"

import { useCallback, useEffect, useState, type ReactNode } from "react"
import { DataProvider, FEED_COLOR, feedHealth, healthSummary, useData } from "./data"
import { DetailProvider } from "./detail"
import { FilterPanel, HealthPanel } from "./panels"
import { Sheet } from "./sheet"
import { ThemeToggle } from "./theme"
import { utcTime } from "./ui"
import { Overview } from "./pages/overview"
import { ThreatMapPage } from "./pages/threat-map"
import { RiskPage } from "./pages/risk"
import { MarketPage } from "./pages/market"
import { ReroutePage } from "./pages/reroute"
import { SprPage } from "./pages/spr"
import { WarRoomPage } from "./pages/war-room"
import { HistoryPage } from "./pages/history"

export type PageKey = "overview" | "map" | "risk" | "market" | "reroute" | "spr" | "war" | "history"

const PAGES: Record<PageKey, { title: string; sub: string }> = {
  overview: { title: "Overview", sub: "" },
  map: { title: "Threat Map", sub: "Chokepoint risk & vessel tracking" },
  risk: { title: "Risk Intelligence", sub: "Sentinel events · SDI timeline · chokepoint & producer exposure" },
  market: { title: "Market Pulse", sub: "Crude, gas, energy equities & tanker freight" },
  reroute: { title: "Reroute Matrix", sub: "Alternative supply if a chokepoint closes" },
  spr: { title: "SPR Optimizer", sub: "India strategic reserve · burn-down & demand levers" },
  war: { title: "Executive War Room", sub: "Scenario simulation · reroute + reserve plan in one brief" },
  history: { title: "Historical Validation", sub: "Would the SDI have warned before Brent moved >1.5σ?" },
}

const ICON: Record<string, ReactNode> = {
  overview: <><path d="M4 18a8 8 0 1 1 16 0" /><path d="M12 18l4-6" /></>,
  map: <><circle cx="12" cy="12" r="9" /><path d="M3 12h18M12 3c3 3.5 3 14.5 0 18M12 3c-3 3.5-3 14.5 0 18" /></>,
  risk: <path d="M12 3l9 4v5c0 5-4 8-9 9-5-1-9-4-9-9V7z" />,
  market: <path d="M3 17l5-6 4 4 8-9" />,
  reroute: <path d="M4 7h11l-3-3M20 17H9l3 3" />,
  spr: <><rect x="5" y="3" width="14" height="18" rx="2" /><path d="M5 14h14" /></>,
  war: <><circle cx="12" cy="12" r="8" /><circle cx="12" cy="12" r="3" /></>,
  history: <><path d="M12 7v5l3 2" /><path d="M3 12a9 9 0 1 0 3-6.7L3 8" /><path d="M3 3v5h5" /></>,
}

function Icon({ name, size = 16 }: { name: string; size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true">
      {ICON[name]}
    </svg>
  )
}

function Logo({ size = 32 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden="true">
      <circle cx="16" cy="16" r="15" fill="var(--x-0f1c2b)" stroke="var(--x-24405f)" />
      <path d="M16 4v24M4 16h24" stroke="var(--x-24405f)" strokeWidth="1" />
      <circle cx="16" cy="16" r="6" fill="none" stroke="var(--x-5aaeff)" strokeWidth="2" />
      <circle cx="16" cy="16" r="2" fill="var(--x-5aaeff)" />
    </svg>
  )
}

function usePage(): [PageKey, (p: PageKey) => void] {
  const read = () => {
    if (typeof window === "undefined") return "overview" as PageKey
    const h = window.location.hash.replace("#", "") as PageKey
    return h in PAGES ? h : "overview"
  }
  const [page, setPage] = useState<PageKey>("overview")
  useEffect(() => {
    setPage(read())
    const on = () => setPage(read())
    window.addEventListener("hashchange", on)
    return () => window.removeEventListener("hashchange", on)
  }, [])
  const go = useCallback((p: PageKey) => {
    window.location.hash = p
    window.scrollTo({ top: 0 })
  }, [])
  return [page, go]
}

// ── Status pill ──────────────────────────────────────────────────────────────

function StatusPill({ onClick, compact = false }: { onClick: () => void; compact?: boolean }) {
  const { live, failed } = useData()
  const s = healthSummary(live, failed)
  const sty = {
    ok: "border-safe-line bg-safe-soft text-safe",
    degraded: "border-warn-line bg-warn-soft text-warn",
    offline: "border-crit-line bg-crit-soft text-crit-text",
    checking: "border-edge bg-panel text-dim",
  }[s.level]
  const dot = { ok: "var(--x-3fcf8e)", degraded: "var(--x-f2c14e)", offline: "var(--x-ff5a5f)", checking: "var(--x-7a8697)" }[s.level]
  return (
    <button
      type="button"
      onClick={onClick}
      aria-haspopup="dialog"
      className={`flex h-11 items-center gap-2 rounded-full border px-3 text-[13px] font-semibold lg:h-10 ${sty}`}
    >
      <span className="h-2 w-2 rounded-full" style={{ background: dot, boxShadow: `0 0 0 3px color-mix(in srgb, ${dot} 18%, transparent)` }} />
      {compact && s.level === "degraded" ? `${s.live}/${s.total} live` : s.label}
      <span className="sr-only">: {s.problems.map((p) => p.name).join(", ") || "open data health"}</span>
    </button>
  )
}

// ── Sidebar (lg+) ────────────────────────────────────────────────────────────

function Sidebar({ page, go, onHealth }: { page: PageKey; go: (p: PageKey) => void; onHealth: () => void }) {
  const { live, failed } = useData()
  const feeds = feedHealth(live)
  const s = healthSummary(live, failed)
  const item = (k: PageKey) => {
    const on = page === k
    return (
      <a
        key={k}
        href={`#${k}`}
        aria-current={on ? "page" : undefined}
        onClick={(e) => { e.preventDefault(); go(k) }}
        className={`flex items-center gap-2.5 rounded-lg p-2.5 text-[13px] ${
          on ? "bg-[var(--x-111a24)] font-semibold text-head shadow-[inset_2px_0_0_var(--x-5aaeff)]" : "text-muted hover:bg-[var(--x-0f151c)] hover:text-fg"
        }`}
      >
        <span className={on ? "text-accent" : ""}><Icon name={k} /></span>
        {PAGES[k].title === "Executive War Room" ? "War Room" : PAGES[k].title}
      </a>
    )
  }
  return (
    <nav aria-label="Primary" className="sticky top-0 hidden h-screen w-[240px] shrink-0 flex-col gap-6 overflow-y-auto border-r border-hair bg-side px-3.5 py-5 lg:flex">
      <div className="flex items-center gap-2.5 px-1.5">
        <Logo />
        <div className="flex flex-col">
          <span className="text-[15px] font-extrabold tracking-[0.16em] text-head [font-stretch:125%]">MERIDIAN</span>
          <span className="font-mono text-[10px] tracking-[0.16em] text-faint">RESILIENCE OS</span>
        </div>
      </div>
      <div className="flex flex-col gap-0.5">
        <span className="eyebrow px-2.5 pb-2 text-faint">Monitor</span>
        {(["overview", "map", "risk", "market"] as PageKey[]).map(item)}
        <span className="eyebrow px-2.5 pb-2 pt-4 text-faint">Respond</span>
        {(["reroute", "spr", "war", "history"] as PageKey[]).map(item)}
      </div>
      <button
        type="button"
        onClick={onHealth}
        className="mt-auto flex flex-col gap-2.5 rounded-xl border border-line bg-[var(--x-0d1218)] p-3.5 text-left"
      >
        <span className="flex items-baseline justify-between">
          <span className="eyebrow">Data feeds</span>
          <span className="font-mono text-xs text-head">
            {s.live}
            <span className="text-faint">/{s.total}</span>
          </span>
        </span>
        <span className="flex gap-[3px]">
          {(feeds.length ? feeds : Array.from({ length: 5 }, () => null)).map((f, i) => (
            <span key={i} className="h-1 flex-1 rounded-full" style={{ background: f ? FEED_COLOR[f.state] : "var(--x-1a2330)" }} />
          ))}
        </span>
        <span className="text-xs leading-snug text-muted">
          {failed ? "Backend offline" : s.problems.length ? s.problems.map((p) => p.name.split(" ")[0]).join(" · ") + " need attention" : live ? "All feeds live" : "Checking…"}
        </span>
      </button>
    </nav>
  )
}

// ── Mobile chrome ────────────────────────────────────────────────────────────

const TABS: { key: PageKey; label: string; icon: string; group: PageKey[] }[] = [
  { key: "overview", label: "Overview", icon: "overview", group: ["overview"] },
  { key: "map", label: "Map", icon: "map", group: ["map"] },
  { key: "risk", label: "Risk", icon: "risk", group: ["risk", "history"] },
  { key: "market", label: "Markets", icon: "market", group: ["market"] },
  { key: "war", label: "Respond", icon: "war", group: ["war", "reroute", "spr"] },
]

function TabBar({ page, go }: { page: PageKey; go: (p: PageKey) => void }) {
  return (
    <nav
      aria-label="Main"
      className="safe-bottom fixed inset-x-0 bottom-0 z-[900] grid grid-cols-5 border-t border-hair bg-side px-1 pt-1.5 lg:hidden"
    >
      {TABS.map((t) => {
        const on = t.group.includes(page)
        return (
          <a
            key={t.key}
            href={`#${t.key}`}
            aria-current={on ? "page" : undefined}
            onClick={(e) => { e.preventDefault(); go(t.key) }}
            className={`flex min-h-[52px] flex-col items-center justify-center gap-1 text-[11px] ${on ? "text-accent" : "text-dim"}`}
          >
            <Icon name={t.icon} size={20} />
            {t.label}
          </a>
        )
      })}
    </nav>
  )
}

/** Page-level switch on phones for grouped tabs (Respond, Risk). */
function SubSwitch({ page, go }: { page: PageKey; go: (p: PageKey) => void }) {
  const groups: { pages: PageKey[]; labels: string[]; label: string }[] = [
    { pages: ["war", "reroute", "spr"], labels: ["War Room", "Reroute", "SPR"], label: "Respond tools" },
    { pages: ["risk", "history"], labels: ["Live risk", "Backtests"], label: "Risk views" },
  ]
  const g = groups.find((x) => x.pages.includes(page))
  if (!g) return null
  return (
    <nav aria-label={g.label} className="border-b border-hair px-4 py-3 lg:hidden">
      <div className="grid rounded-xl border border-line bg-panel p-1" style={{ gridTemplateColumns: `repeat(${g.pages.length}, minmax(0,1fr))` }}>
        {g.pages.map((p, i) => (
          <a
            key={p}
            href={`#${p}`}
            aria-current={p === page ? "page" : undefined}
            onClick={(e) => { e.preventDefault(); go(p) }}
            className={`flex min-h-10 items-center justify-center rounded-[9px] text-[13px] ${
              p === page ? "bg-track font-semibold text-head" : "text-muted"
            }`}
          >
            {g.labels[i]}
          </a>
        ))}
      </div>
    </nav>
  )
}

// ── App ──────────────────────────────────────────────────────────────────────

function Chrome() {
  const [page, go] = usePage()
  const [sheet, setSheet] = useState<null | "health" | "filters">(null)
  const { live, refresh, loading } = useData()
  const close = useCallback(() => setSheet(null), [])
  const meta = PAGES[page]

  const body = {
    overview: <Overview go={go} openHealth={() => setSheet("health")} />,
    map: <ThreatMapPage />,
    risk: <RiskPage go={go} />,
    market: <MarketPage />,
    reroute: <ReroutePage />,
    spr: <SprPage />,
    war: <WarRoomPage />,
    history: <HistoryPage />,
  }[page]

  return (
    <div className="flex min-h-screen bg-ground text-fg">
      <Sidebar page={page} go={go} onHealth={() => setSheet("health")} />

      <div className="flex min-w-0 flex-1 flex-col pb-[84px] lg:pb-0">
        {/* Desktop header */}
        <header className="sticky top-0 z-[800] hidden flex-wrap items-center justify-between gap-4 border-b border-hair bg-top px-8 py-4 lg:flex">
          <div className="flex flex-col gap-1">
            <h1 className="text-[22px] font-bold tracking-[-0.01em] text-head [font-stretch:112%]">{meta.title}</h1>
            <span className="font-mono text-[11px] text-dim">
              {meta.sub || (live ? `Snapshot ${utcTime(live.computed_at)}` : "Loading snapshot…")}
            </span>
          </div>
          <div className="flex items-center gap-2.5">
            <button
              type="button"
              onClick={() => setSheet("filters")}
              className="flex h-10 items-center gap-2 rounded-[10px] border border-edge bg-[var(--x-0f141a)] px-3 text-[13px] text-muted hover:text-fg"
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true"><path d="M4 6h16M7 12h10M10 18h4" /></svg>
              Filters
            </button>
            <ThemeToggle className="h-10 w-10" />
            <button
              type="button"
              aria-label="Refresh data"
              onClick={() => void refresh()}
              className="flex h-10 w-10 items-center justify-center rounded-[10px] border border-edge bg-[var(--x-0f141a)] text-muted hover:text-fg"
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true" className={loading ? "animate-spin" : ""}><path d="M20 11a8 8 0 1 0-2.3 5.7" /><path d="M20 4v7h-7" /></svg>
            </button>
            <StatusPill onClick={() => setSheet("health")} />
          </div>
        </header>

        {/* Mobile app bar */}
        <header className="sticky top-0 z-[800] flex items-center justify-between border-b border-hair bg-side px-4 pb-3 pt-3.5 lg:hidden">
          <div className="flex min-w-0 items-center gap-2.5">
            <Logo size={30} />
            <span className="truncate text-base font-bold text-head">
              {page === "overview" ? "MERIDIAN" : page === "war" ? "War Room" : meta.title}
            </span>
          </div>
          <div className="flex items-center gap-2">
            <StatusPill compact onClick={() => setSheet("health")} />
            <button
              type="button"
              aria-label="Filters"
              onClick={() => setSheet("filters")}
              className="flex h-11 w-11 items-center justify-center rounded-xl border border-edge bg-[var(--x-0f141a)] text-muted"
            >
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true"><path d="M4 6h16M7 12h10M10 18h4" /></svg>
            </button>
          </div>
        </header>
        <SubSwitch page={page} go={go} />

        <main className="w-full max-w-[1240px] flex-1 px-4 py-4 lg:px-8 lg:py-6">{body}</main>
      </div>

      <TabBar page={page} go={go} />

      <Sheet open={sheet === "health"} onClose={close} title="Data health">
        <HealthPanel />
      </Sheet>
      <Sheet open={sheet === "filters"} onClose={close} title="Filters">
        <FilterPanel onDone={close} />
      </Sheet>
    </div>
  )
}

export function App() {
  return (
    <DataProvider>
      <DetailProvider>
        <Chrome />
      </DetailProvider>
    </DataProvider>
  )
}
