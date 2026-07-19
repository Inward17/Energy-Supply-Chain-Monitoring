"use client"

import dynamic from "next/dynamic"
import { ExternalLink, Anchor, Gauge } from "lucide-react"
import { DetailShell, Section, RailCard } from "./detail-shell"
import { coordsFor, CHOKEPOINT_ZOOM, PRODUCER_ZOOM } from "../geo"
import type { ChokepointDetail, ProducerDetail, RiskContributor } from "@/lib/api"

const MiniMap = dynamic(() => import("./mini-map"), {
  ssr: false,
  loading: () => (
    <div className="flex h-full w-full items-center justify-center text-xs text-muted">
      Loading map…
    </div>
  ),
})

const riskTone = (v: number) => (v > 0.6 ? "text-crit" : v > 0.4 ? "text-orange" : "text-safe")
const riskBar = (v: number) => (v > 0.6 ? "bg-crit" : v > 0.4 ? "bg-orange" : "bg-safe")

function domainOf(url: string) {
  try {
    return new URL(url).hostname.replace(/^www\./, "")
  } catch {
    return url
  }
}

/** One event's contribution, showing the arithmetic that produced it. */
function ContributorRow({ c, isDriver }: { c: RiskContributor; isDriver: boolean }) {
  return (
    <li
      className={`rounded-lg border p-3 ${
        isDriver ? "border-accent-border bg-accent-soft" : "border-hair bg-panel-2"
      }`}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-xs font-semibold text-fg">
            {c.region || "Unknown region"}
            {isDriver && (
              <span className="ml-2 rounded bg-accent-soft px-1.5 py-0.5 font-mono text-[9px] font-bold uppercase tracking-wide text-accent">
                sets score
              </span>
            )}
          </p>
          <p className="mt-0.5 text-[11px] text-muted">{c.basis}</p>
        </div>
        <span className={`shrink-0 font-mono text-sm tabular-nums ${riskTone(c.contribution)}`}>
          {c.contribution.toFixed(3)}
        </span>
      </div>

      {/* The arithmetic: raw severity, any discount, and time decay. */}
      <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 font-mono text-[10px] text-faint">
        <span>severity {c.severity.toFixed(2)}</span>
        {c.multiplier !== 1 && <span className="text-warn">× {c.multiplier} discount</span>}
        {c.age_hours != null && <span>· decayed over {c.age_hours}h</span>}
        {c.confidence != null && <span>· confidence {Number(c.confidence).toFixed(2)}</span>}
      </div>

      {c.summary && (
        <p className="mt-2 line-clamp-2 text-[11px] leading-relaxed text-muted">{c.summary}</p>
      )}

      {c.source_urls?.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-2">
          {c.source_urls.slice(0, 4).map((u, i) => (
            <a
              key={i}
              href={u}
              target="_blank"
              rel="noreferrer"
              className="flex items-center gap-1 text-[10px] text-accent hover:underline"
            >
              <ExternalLink className="h-2.5 w-2.5" />
              {domainOf(u)}
            </a>
          ))}
        </div>
      )}
    </li>
  )
}

function ScoreRail({
  score,
  isBaseline,
  explanation,
  extras,
}: {
  score: number
  isBaseline: boolean
  explanation: string
  extras: { label: string; value: string; tone?: string }[]
}) {
  return (
    <RailCard label="Risk Assessment">
      <div className="flex items-baseline gap-2">
        <span className={`font-mono text-3xl font-bold tabular-nums ${riskTone(score)}`}>
          {score.toFixed(2)}
        </span>
        <span className="text-xs text-faint">/ 1.00</span>
      </div>
      <div className="mt-3 h-1.5 w-full overflow-hidden rounded-full bg-track">
        <div className={`h-full rounded-full ${riskBar(score)}`} style={{ width: `${score * 100}%` }} />
      </div>

      {isBaseline && (
        <p className="mt-3 rounded border border-hair bg-panel px-2 py-1.5 text-[11px] text-muted">
          At the baseline floor — no active event references it.
        </p>
      )}

      <dl className="mt-4 space-y-2">
        {extras.map((x) => (
          <div key={x.label} className="flex items-center justify-between text-[11px]">
            <dt className="text-muted">{x.label}</dt>
            <dd className={`font-mono tabular-nums ${x.tone ?? "text-fg"}`}>{x.value}</dd>
          </div>
        ))}
      </dl>

      <p className="mt-4 border-t border-hair pt-3 text-[11px] leading-relaxed text-muted">
        {explanation}
      </p>
    </RailCard>
  )
}

function LocationCard({
  kind,
  name,
  risk,
}: {
  kind: "chokepoint" | "producer"
  name: string
  risk: number
}) {
  const center = coordsFor(kind, name)
  if (!center) return null
  return (
    <RailCard label="Location">
      <div className="h-[190px] overflow-hidden rounded-md border border-border">
        <MiniMap
          center={center}
          zoom={kind === "chokepoint" ? CHOKEPOINT_ZOOM : PRODUCER_ZOOM}
          label={name}
          risk={risk}
        />
      </div>
      <p className="mt-2 font-mono text-[10px] text-faint">
        {center[0].toFixed(2)}°, {center[1].toFixed(2)}°
      </p>
    </RailCard>
  )
}

function Contributors({ items }: { items: RiskContributor[] }) {
  return (
    <Section label={`Contributing Events (${items.length})`}>
      {items.length === 0 ? (
        <p className="rounded-lg border border-hair bg-panel-2 p-4 text-sm text-muted">
          No active events contribute to this score.
        </p>
      ) : (
        <ul className="space-y-2">
          {items.map((c, i) => (
            <ContributorRow key={`${c.id}-${i}`} c={c} isDriver={i === 0} />
          ))}
        </ul>
      )}
    </Section>
  )
}

export function ChokepointDetailModal({
  detail,
  onClose,
}: {
  detail: ChokepointDetail
  onClose: () => void
}) {
  return (
    <DetailShell
      title={detail.name}
      subtitle={`Maritime chokepoint · ${detail.flow_mb_day.toFixed(1)} mbpd transits here`}
      onClose={onClose}
      left={
        <>
          <Section label="Why this score">
            <p className="text-sm leading-relaxed text-fg">{detail.explanation}</p>
          </Section>
          <Contributors items={detail.contributors} />
          {detail.dependent_producers.length > 0 && (
            <Section label="Producers routing through here">
              <div className="flex flex-wrap gap-2">
                {detail.dependent_producers.map((p) => (
                  <span
                    key={p}
                    className="flex items-center gap-1.5 rounded border border-accent-border bg-accent-soft px-2.5 py-1.5 text-xs font-medium text-accent"
                  >
                    <Anchor className="h-3 w-3" />
                    {p}
                  </span>
                ))}
              </div>
            </Section>
          )}
        </>
      }
      right={
        <>
          <ScoreRail
            score={detail.risk_score}
            isBaseline={detail.is_baseline}
            explanation={detail.explanation}
            extras={[
              { label: "Daily flow", value: `${detail.flow_mb_day.toFixed(1)} mbpd` },
              {
                label: "Est. price impact",
                value: `+$${detail.price_impact_usd.toFixed(2)}`,
                tone: "text-crit",
              },
              { label: "Elevated above", value: detail.elevated_threshold.toFixed(2) },
              { label: "Baseline floor", value: detail.baseline_risk.toFixed(2) },
            ]}
          />
          <LocationCard kind="chokepoint" name={detail.name} risk={detail.risk_score} />
        </>
      }
    />
  )
}

export function ProducerDetailModal({
  detail,
  onClose,
}: {
  detail: ProducerDetail
  onClose: () => void
}) {
  const exposureTone =
    detail.exposure_type === "direct"
      ? "text-crit"
      : detail.exposure_type === "transit"
        ? "text-warn"
        : "text-faint"

  return (
    <DetailShell
      title={detail.name}
      subtitle={
        <span className="flex items-center gap-1.5">
          <Gauge className="h-3.5 w-3.5" />
          Producer nation ·{" "}
          <span className={`uppercase ${exposureTone}`}>{detail.exposure_type}</span> exposure
        </span>
      }
      onClose={onClose}
      left={
        <>
          <Section label="Why this score">
            <p className="text-sm leading-relaxed text-fg">{detail.explanation}</p>
          </Section>
          <Contributors items={detail.contributors} />
          {detail.transit_chokepoints.length > 0 && (
            <Section label="Export routes transit">
              <div className="flex flex-wrap gap-2">
                {detail.transit_chokepoints.map((cp) => (
                  <span
                    key={cp}
                    className="flex items-center gap-1.5 rounded border border-accent-border bg-accent-soft px-2.5 py-1.5 text-xs font-medium text-accent"
                  >
                    <Anchor className="h-3 w-3" />
                    {cp}
                  </span>
                ))}
              </div>
              <p className="mt-2 text-[11px] text-faint">
                Disruption reaching this producer only through one of these routes is
                discounted to {(detail.transit_discount * 100).toFixed(0)}% of the event severity.
              </p>
            </Section>
          )}
        </>
      }
      right={
        <>
          <ScoreRail
            score={detail.risk_score}
            isBaseline={detail.is_baseline}
            explanation={detail.explanation}
            extras={[
              { label: "Exposure", value: detail.exposure_type, tone: exposureTone },
              { label: "Transit discount", value: `${(detail.transit_discount * 100).toFixed(0)}%` },
              { label: "Routes tracked", value: String(detail.transit_chokepoints.length) },
              { label: "Baseline floor", value: detail.baseline_risk.toFixed(2) },
            ]}
          />
          <LocationCard kind="producer" name={detail.name} risk={detail.risk_score} />
        </>
      }
    />
  )
}
