"use client"

import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react"
import {
  fetchChokepointDetail,
  fetchProducerDetail,
  fetchRiskEventDetail,
  type ChokepointDetail,
  type ProducerDetail,
  type RiskContributor,
  type RiskEventDetail,
} from "@/lib/api"
import { displayDomain, safeExternalUrl } from "@/lib/utils"
import { Sheet } from "./sheet"
import { Bar, ErrorNote, Eyebrow, Loading, Ring, SevChip, riskColor, shortDate, titleCase } from "./ui"

type Target = { kind: "chokepoint"; name: string } | { kind: "producer"; name: string } | { kind: "event"; id: number }

const Ctx = createContext<(t: Target) => void>(() => {})
export const useDetail = () => useContext(Ctx)

export function DetailProvider({ children }: { children: ReactNode }) {
  const [target, setTarget] = useState<Target | null>(null)
  const [data, setData] = useState<ChokepointDetail | ProducerDetail | RiskEventDetail | null>(null)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback((t: Target) => {
    setData(null)
    setError(null)
    const p =
      t.kind === "chokepoint" ? fetchChokepointDetail(t.name) : t.kind === "producer" ? fetchProducerDetail(t.name) : fetchRiskEventDetail(t.id)
    p.then(setData).catch(() => setError("Could not load details."))
  }, [])

  useEffect(() => {
    if (target) load(target)
  }, [target, load])

  const title = !target ? "" : target.kind === "event" ? "Event" : target.name

  return (
    <Ctx.Provider value={setTarget}>
      {children}
      <Sheet open={!!target} onClose={() => { setTarget(null); setData(null) }} title={title} wide>
        {!target ? null : error ? (
          <ErrorNote message={error} onRetry={() => load(target)} />
        ) : !data ? (
          <Loading />
        ) : target.kind === "event" ? (
          <EventBody e={data as RiskEventDetail} />
        ) : (
          <ScoreBody d={data as ChokepointDetail | ProducerDetail} kind={target.kind} />
        )}
      </Sheet>
    </Ctx.Provider>
  )
}

function Links({ urls }: { urls?: string[] }) {
  const safe = (urls ?? []).map((u) => safeExternalUrl(u)).filter(Boolean) as string[]
  if (!safe.length) return null
  return (
    <div className="flex flex-wrap gap-2">
      {safe.slice(0, 6).map((u) => (
        <a key={u} href={u} target="_blank" rel="noopener noreferrer" className="rounded-md bg-hair px-2 py-1 text-xs text-accent hover:underline">
          {displayDomain(u)} ↗
        </a>
      ))}
    </div>
  )
}

function Contributor({ c, driver }: { c: RiskContributor; driver: boolean }) {
  return (
    <li className={`rounded-xl border p-3 ${driver ? "border-crit-line bg-crit-soft" : "border-line bg-well"}`}>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-[13px] font-semibold text-head">
            {c.region || "Unknown region"}
            {driver && <span className="ml-2 font-mono text-[10px] tracking-[0.1em] text-crit-text">SETS SCORE</span>}
          </p>
          <p className="mt-0.5 text-[11px] text-dim">{c.basis}</p>
        </div>
        <span className="font-mono text-sm" style={{ color: riskColor(c.contribution) }}>{c.contribution.toFixed(3)}</span>
      </div>
      <p className="mt-2 font-mono text-[10px] text-faint">
        severity {c.severity.toFixed(2)}
        {c.multiplier !== 1 && ` × ${c.multiplier} discount`}
        {c.age_hours != null && ` · decayed over ${c.age_hours}h`}
      </p>
      {c.summary && <p className="mt-2 line-clamp-3 text-xs leading-relaxed text-muted">{c.summary}</p>}
      <div className="mt-2"><Links urls={c.source_urls} /></div>
    </li>
  )
}

function ScoreBody({ d, kind }: { d: ChokepointDetail | ProducerDetail; kind: "chokepoint" | "producer" }) {
  const cp = kind === "chokepoint" ? (d as ChokepointDetail) : null
  const pr = kind === "producer" ? (d as ProducerDetail) : null
  return (
    <div className="flex flex-col gap-5">
      <div className="flex items-center gap-4">
        <Ring value={d.risk_score} size={72} stroke={7} />
        <div className="flex flex-col gap-1">
          <span className="eyebrow">{kind === "chokepoint" ? "Chokepoint" : `Producer · ${pr?.exposure_type} exposure`}</span>
          <span className="text-sm text-muted">
            {cp ? `${cp.flow_mb_day.toFixed(1)} mbpd · +$${cp.price_impact_usd.toFixed(2)}/bbl` : `Transit discount ${Math.round((pr?.transit_discount ?? 0) * 100)}%`}
          </span>
          {d.is_baseline && <span className="text-xs text-dim">At the {d.baseline_risk.toFixed(2)} baseline floor — no active event references it.</span>}
        </div>
      </div>
      <div className="flex flex-col gap-2">
        <Eyebrow>Why this score</Eyebrow>
        <p className="text-sm leading-relaxed text-fg">{d.explanation}</p>
      </div>
      <div className="flex flex-col gap-2">
        <Eyebrow>Contributing events · {d.contributors.length}</Eyebrow>
        {d.contributors.length ? (
          <ul className="flex flex-col gap-2">
            {d.contributors.map((c, i) => <Contributor key={`${c.id}-${i}`} c={c} driver={i === 0} />)}
          </ul>
        ) : (
          <p className="rounded-xl border border-line bg-well p-4 text-sm text-dim">No active events contribute.</p>
        )}
      </div>
      {(cp?.dependent_producers.length || pr?.transit_chokepoints.length) ? (
        <div className="flex flex-col gap-2">
          <Eyebrow>{cp ? "Producers routing through here" : "Export routes transit"}</Eyebrow>
          <div className="flex flex-wrap gap-1.5">
            {(cp?.dependent_producers ?? pr?.transit_chokepoints ?? []).map((n) => (
              <span key={n} className="rounded-md bg-raise px-2.5 py-1.5 text-xs text-soft">{n}</span>
            ))}
          </div>
        </div>
      ) : null}
    </div>
  )
}

function EventBody({ e }: { e: RiskEventDetail }) {
  return (
    <div className="flex flex-col gap-5">
      <div className="flex items-center gap-3">
        <SevChip v={e.severity} />
        <div className="flex flex-col">
          <span className="text-base font-bold text-head">{titleCase(e.disruption_type)}</span>
          <span className="font-mono text-[11px] text-dim">{e.region} · scored {shortDate(e.scored_at)}</span>
        </div>
      </div>
      <Bar value={e.severity} color={riskColor(e.severity)} />
      <div className="flex flex-col gap-2">
        <Eyebrow>Briefing</Eyebrow>
        <p className="whitespace-pre-wrap text-sm leading-relaxed text-fg">{e.summary}</p>
      </div>
      {e.severity_reasoning && (
        <div className="flex flex-col gap-2">
          <Eyebrow>Severity reasoning</Eyebrow>
          <p className="whitespace-pre-wrap border-l-2 border-edge pl-3 text-[13px] leading-relaxed text-muted">{e.severity_reasoning}</p>
        </div>
      )}
      {[
        ["Chokepoints", [...(e.affected_chokepoints ?? []), ...(e.inferred_chokepoints ?? []).map((c) => `${c} (inferred)`)]],
        ["Producers", e.affected_producer_countries ?? []],
        ["Crude grades", e.affected_grades ?? []],
      ].map(([label, items]) =>
        (items as string[]).length ? (
          <div key={label as string} className="flex flex-col gap-2">
            <Eyebrow>{label as string}</Eyebrow>
            <div className="flex flex-wrap gap-1.5">
              {(items as string[]).map((n) => <span key={n} className="rounded-md bg-raise px-2.5 py-1.5 text-xs text-soft">{n}</span>)}
            </div>
          </div>
        ) : null,
      )}
      {e.source_urls?.length ? (
        <div className="flex flex-col gap-2">
          <Eyebrow>Sources · {e.source_urls.length}</Eyebrow>
          <Links urls={e.source_urls} />
        </div>
      ) : null}
    </div>
  )
}
