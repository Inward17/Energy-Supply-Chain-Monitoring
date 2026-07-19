"use client"

import { ExternalLink, Anchor, Activity, ShieldAlert, AlertTriangle } from "lucide-react"
import { SeverityBadge } from "../ui"
import { DetailShell, Section, RailCard } from "./detail-shell"
import type { RiskEventDetail } from "@/lib/api"

interface EventDetailModalProps {
  event: RiskEventDetail
  onClose: () => void
}

export function EventDetailModal({ event, onClose }: EventDetailModalProps) {
  const eventTitle = (type: string) =>
    type.split("_").map((w) => w.charAt(0).toUpperCase() + w.slice(1)).join(" ")

  const timeAgo = (iso: string) => {
    try {
      const diff = Date.now() - new Date(iso).getTime()
      const mins = Math.floor(diff / 60000)
      if (mins < 60) return `${mins}m ago`
      if (mins < 1440) return `${Math.floor(mins / 60)}h ago`
      return `${Math.floor(mins / 1440)}d ago`
    } catch {
      return iso.slice(0, 10)
    }
  }

  const hasChokepoints = event.affected_chokepoints && event.affected_chokepoints.length > 0
  const hasInferredChokepoints = event.inferred_chokepoints && event.inferred_chokepoints.length > 0
  const hasCountries = event.affected_producer_countries && event.affected_producer_countries.length > 0
  const hasGrades = event.affected_grades && event.affected_grades.length > 0

  return (
    <DetailShell
      title={eventTitle(event.disruption_type)}
      subtitle={event.region}
      badge={<SeverityBadge severity={event.severity_label} />}
      onClose={onClose}
      left={
        <>
          <Section label="Intelligence Briefing">
            <p className="whitespace-pre-wrap text-sm leading-relaxed text-fg">{event.summary}</p>
          </Section>

          <Section label="Affected Chokepoints">
            {hasChokepoints || hasInferredChokepoints ? (
              <div className="flex flex-wrap gap-2">
                {hasChokepoints &&
                  event.affected_chokepoints.map((cp) => (
                    <span
                      key={cp}
                      className="flex items-center gap-1.5 rounded border border-accent-border bg-accent-soft px-2.5 py-1.5 text-xs font-medium text-accent"
                    >
                      <Anchor className="h-3.5 w-3.5" />
                      {cp}
                    </span>
                  ))}
                {hasInferredChokepoints &&
                  event.inferred_chokepoints!.map((cp) => (
                    <span
                      key={`inf-${cp}`}
                      className="flex items-center gap-1.5 rounded border border-warn/20 bg-warn-soft px-2.5 py-1.5 text-[11px] font-medium italic text-warn"
                    >
                      <Anchor className="h-3 w-3" />
                      {cp} (Inferred)
                    </span>
                  ))}
              </div>
            ) : (
              <p className="text-xs italic text-faint">None identified</p>
            )}
          </Section>

          <Section label="Affected Producer Nations">
            {hasCountries ? (
              <div className="flex flex-wrap gap-2">
                {event.affected_producer_countries.map((country) => (
                  <span
                    key={country}
                    className="flex items-center gap-1.5 rounded border border-safe/20 bg-safe-soft px-2.5 py-1.5 text-xs font-medium text-safe"
                  >
                    <ShieldAlert className="h-3.5 w-3.5" />
                    {country}
                  </span>
                ))}
              </div>
            ) : (
              <p className="text-xs italic text-faint">None identified</p>
            )}
          </Section>

          <Section label="Potentially Affected Crude Grades">
            {hasGrades ? (
              <div className="flex flex-wrap gap-2">
                {event.affected_grades.map((grade) => (
                  <span
                    key={grade}
                    className="flex items-center gap-1.5 rounded border border-warn/20 bg-warn-soft px-2.5 py-1.5 text-xs font-medium text-warn"
                  >
                    {grade}
                  </span>
                ))}
              </div>
            ) : (
              <p className="flex items-center gap-1.5 text-xs italic text-faint">
                <AlertTriangle className="h-3.5 w-3.5 text-warn/70" />
                No specific crude grades identified for this event
              </p>
            )}
          </Section>

          {event.source_urls && event.source_urls.length > 0 && (
            <Section label={`Sourced Articles (${event.source_urls.length})`}>
              <ul className="space-y-2">
                {event.source_urls.map((url, idx) => {
                  try {
                    const domain = new URL(url).hostname.replace(/^www\./, "")
                    return (
                      <li key={idx} className="truncate text-sm">
                        <a
                          href={url}
                          target="_blank"
                          rel="noreferrer"
                          className="flex items-center gap-1.5 text-accent transition-colors hover:underline"
                        >
                          <ExternalLink className="h-3 w-3 shrink-0" />
                          {domain}
                        </a>
                      </li>
                    )
                  } catch {
                    return null
                  }
                })}
              </ul>
            </Section>
          )}
        </>
      }
      right={
        <RailCard label="Severity Assessment">
          <div className="mb-3 flex items-center gap-2">
            <Activity className="h-4 w-4 text-crit" />
            <span className="font-mono text-2xl font-bold tabular-nums text-head">
              {event.severity.toFixed(2)}
            </span>
            <span className="text-xs text-faint">/ 1.00</span>
          </div>
          <div className="mb-4 h-1.5 w-full overflow-hidden rounded-full bg-track">
            <div
              className={`h-full rounded-full ${
                event.severity > 0.6 ? "bg-crit" : event.severity > 0.4 ? "bg-orange" : "bg-safe"
              }`}
              style={{ width: `${event.severity * 100}%` }}
            />
          </div>
          <p className="whitespace-pre-wrap border-l-2 border-border py-1 pl-3 text-sm leading-relaxed text-muted">
            {event.severity_reasoning || "Severity scored based on regional risk patterns."}
          </p>
          <p className="mt-4 border-t border-hair pt-3 text-[11px] text-faint">
            Scored {timeAgo(event.scored_at)}
          </p>
        </RailCard>
      }
    />
  )
}
