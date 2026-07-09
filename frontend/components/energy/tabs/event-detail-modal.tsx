import { X, ExternalLink, ShieldAlert, Anchor, Activity, AlertTriangle } from "lucide-react"
import { SeverityBadge } from "../ui"
import type { RiskEventDetail } from "@/lib/api"
import { useEffect } from "react"

interface EventDetailModalProps {
  event: RiskEventDetail
  onClose: () => void
}

export function EventDetailModal({ event, onClose }: EventDetailModalProps) {
  // Prevent body scroll when modal is open
  useEffect(() => {
    document.body.style.overflow = "hidden"
    return () => {
      document.body.style.overflow = "unset"
    }
  }, [])

  // Close on escape key
  useEffect(() => {
    const handleEsc = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose()
    }
    window.addEventListener("keydown", handleEsc)
    return () => window.removeEventListener("keydown", handleEsc)
  }, [onClose])

  const eventTitle = (type: string) =>
    type.split("_").map((w) => w.charAt(0).toUpperCase() + w.slice(1)).join(" ")

  const timeAgo = (iso: string) => {
    try {
      const diff = Date.now() - new Date(iso).getTime()
      const mins = Math.floor(diff / 60000)
      if (mins < 60) return `${mins}m ago`
      if (mins < 1440) return `${Math.floor(mins / 60)}h ago`
      return `${Math.floor(mins / 1440)}d ago`
    } catch { return iso.slice(0, 10) }
  }

  const hasChokepoints = event.affected_chokepoints && event.affected_chokepoints.length > 0
  const hasCountries = event.affected_producer_countries && event.affected_producer_countries.length > 0
  const hasGrades = event.affected_grades && event.affected_grades.length > 0

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center p-4">
      {/* Backdrop */}
      <div 
        className="absolute inset-0 bg-slate-950/80 backdrop-blur-sm"
        onClick={onClose}
      />
      
      {/* Modal */}
      <div className="relative w-full max-w-4xl overflow-hidden rounded-xl border border-slate-700 bg-slate-900 shadow-2xl flex flex-col max-h-[90vh]">
        
        {/* Header */}
        <div className="flex items-start justify-between border-b border-slate-800 p-5 bg-slate-950/40">
          <div>
            <div className="flex items-center gap-2 mb-2">
              <h2 className="text-xl font-semibold text-white">
                {eventTitle(event.disruption_type)}
              </h2>
              <SeverityBadge severity={event.severity_label} />
            </div>
            <p className="text-sm font-medium text-cyan-400">{event.region}</p>
          </div>
          <button 
            onClick={onClose}
            className="rounded p-1 text-slate-400 hover:bg-slate-800 hover:text-white transition-colors"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Scrollable Content */}
        <div className="flex-1 overflow-y-auto p-6 [&::-webkit-scrollbar]:w-2 [&::-webkit-scrollbar-track]:bg-transparent [&::-webkit-scrollbar-thumb]:rounded-full [&::-webkit-scrollbar-thumb]:bg-slate-700 hover:[&::-webkit-scrollbar-thumb]:bg-slate-600">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
            
            {/* Column 1: Core Details */}
            <div className="space-y-6">
              {/* Summary */}
              <section>
                <h3 className="text-xs font-bold uppercase tracking-wider text-slate-500 mb-2">Intelligence Briefing</h3>
                <p className="text-sm leading-relaxed text-slate-200">
                  {event.summary}
                </p>
              </section>

              {/* Severity & Reasoning */}
              <section className="rounded-lg border border-slate-800 bg-slate-950/60 p-4">
                <div className="flex items-center gap-2 mb-3">
                  <Activity className="h-4 w-4 text-rose-400" />
                  <h3 className="text-sm font-semibold text-slate-300">Severity Assessment</h3>
                  <span className="font-mono text-sm text-white ml-auto">{event.severity.toFixed(2)}</span>
                </div>
                <p className="text-sm text-slate-400 leading-relaxed border-l-2 border-slate-700 pl-3 py-1">
                  {event.severity_reasoning || "Severity scored based on regional risk patterns."}
                </p>
              </section>

              {/* Sources */}
              {event.source_urls && event.source_urls.length > 0 && (
                <section className="border-t border-slate-800 pt-4">
                  <h3 className="text-xs font-bold uppercase tracking-wider text-slate-500 mb-3 flex items-center gap-2">
                    <ExternalLink className="h-3.5 w-3.5" />
                    Sourced Articles ({event.source_urls.length})
                  </h3>
                  <ul className="space-y-2">
                    {event.source_urls.map((url, idx) => {
                      try {
                        const domain = new URL(url).hostname.replace(/^www\./, '')
                        return (
                          <li key={idx} className="text-sm truncate">
                            <a 
                              href={url} 
                              target="_blank" 
                              rel="noreferrer" 
                              className="text-cyan-400 hover:text-cyan-300 hover:underline transition-colors"
                            >
                              {domain}
                            </a>
                          </li>
                        )
                      } catch {
                        return null
                      }
                    })}
                  </ul>
                </section>
              )}
            </div>

            {/* Column 2: Graph Extrapolations */}
            <div className="space-y-6 bg-slate-950/30 p-5 rounded-lg border border-slate-800/50">
              
              {/* Chokepoints */}
              <div>
                <h3 className="text-xs font-bold uppercase tracking-wider text-slate-500 mb-2">Affected Chokepoints</h3>
                {hasChokepoints ? (
                  <div className="flex flex-wrap gap-2">
                    {event.affected_chokepoints.map((cp) => (
                      <span key={cp} className="flex items-center gap-1.5 rounded bg-blue-500/10 px-2.5 py-1.5 text-xs font-medium text-blue-400 border border-blue-500/20">
                        <Anchor className="h-3.5 w-3.5" />
                        {cp}
                      </span>
                    ))}
                  </div>
                ) : (
                  <p className="text-xs text-slate-600 italic">None identified</p>
                )}
              </div>

              {/* Countries */}
              <div>
                <h3 className="text-xs font-bold uppercase tracking-wider text-slate-500 mb-2">Affected Producer Nations</h3>
                {hasCountries ? (
                  <div className="flex flex-wrap gap-2">
                    {event.affected_producer_countries.map((country) => (
                      <span key={country} className="flex items-center gap-1.5 rounded bg-emerald-500/10 px-2.5 py-1.5 text-xs font-medium text-emerald-400 border border-emerald-500/20">
                        <ShieldAlert className="h-3.5 w-3.5" />
                        {country}
                      </span>
                    ))}
                  </div>
                ) : (
                  <p className="text-xs text-slate-600 italic">None identified</p>
                )}
              </div>

              {/* Derived Crude Grades */}
              <div className="pt-2 border-t border-slate-800/60">
                <h3 className="flex items-center gap-1.5 text-xs font-bold uppercase tracking-wider text-slate-500 mb-3">
                  Potentially Affected Crude Grades
                  <AlertTriangle className="h-3.5 w-3.5 text-amber-500/70 ml-1" />
                </h3>
                {hasGrades ? (
                  <div className="flex flex-wrap gap-2">
                    {event.affected_grades.map((grade) => (
                      <span key={grade} className="flex items-center gap-1.5 rounded bg-amber-500/10 px-2.5 py-1.5 text-xs font-medium text-amber-400 border border-amber-500/20 shadow-sm">
                        {grade}
                      </span>
                    ))}
                  </div>
                ) : (
                  <p className="text-xs text-slate-600 italic">No specific crude grades identified for this event</p>
                )}
              </div>
            </div>
            
          </div>
        </div>

        {/* Footer */}
        <div className="border-t border-slate-800 p-4 bg-slate-950/40 text-right">
          <span className="text-xs text-slate-500 mr-4">
            Scored {timeAgo(event.scored_at)}
          </span>
          <button 
            onClick={onClose}
            className="rounded bg-slate-800 px-4 py-2 text-sm font-medium text-white hover:bg-slate-700 transition-colors"
          >
            Close
          </button>
        </div>

      </div>
    </div>
  )
}
