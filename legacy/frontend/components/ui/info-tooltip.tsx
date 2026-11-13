"use client"

import * as React from "react"
import { createPortal } from "react-dom"
import { Info } from "lucide-react"

// Static Glossary Dictionary
const GLOSSARY: Record<string, string> = {
  "SDI": "The Supply Disruption Index is a real-time metric combining geopolitical risk, vessel traffic, and market prices to quantify global energy stress (0-100).",
  "Landed Cost": "The total estimated cost to deliver a barrel of oil, including the commodity price plus all freight and insurance premiums.",
  "Freight Premium": "The additional cost of shipping along this specific route compared to baseline historical rates, driven by risk or distance.",
  "Resilience Index": "A 0-10 score measuring how robust an alternative route is against current geopolitical or physical disruptions.",
  "Chokepoint": "A strategic strait or canal where global maritime trade is concentrated and highly vulnerable to blockage or attack.",
  "Composite Score": "An aggregated metric blending multiple risk indicators into a single easy-to-read severity rating."
}

interface InfoTooltipProps {
  term: string
  label?: string
}

export function InfoTooltip({ term, label }: InfoTooltipProps) {
  const definition = GLOSSARY[term]
  const [open, setOpen] = React.useState(false)
  const triggerRef = React.useRef<HTMLDivElement>(null)
  const [coords, setCoords] = React.useState({ left: 0, top: 0 })
  const [mounted, setMounted] = React.useState(false)

  React.useEffect(() => {
    setMounted(true)
  }, [])

  const updateCoords = () => {
    if (triggerRef.current) {
      const rect = triggerRef.current.getBoundingClientRect()
      setCoords({ 
        left: rect.left + rect.width / 2, 
        top: rect.top 
      })
    }
  }

  React.useEffect(() => {
    if (open) {
      updateCoords()
      window.addEventListener("scroll", updateCoords, true)
      window.addEventListener("resize", updateCoords)
      return () => {
        window.removeEventListener("scroll", updateCoords, true)
        window.removeEventListener("resize", updateCoords)
      }
    }
  }, [open])

  if (!definition) {
    return <span>{label || term}</span>
  }

  return (
    <>
      <div 
        ref={triggerRef}
        className="group relative inline-flex items-center gap-1 cursor-help"
        onMouseEnter={() => setOpen(true)}
        onMouseLeave={() => setOpen(false)}
      >
        <span className="underline decoration-muted/50 decoration-dashed underline-offset-4">{label || term}</span>
        <Info className="h-3 w-3 text-muted" />
      </div>
      
      {/* Tooltip Content in Portal */}
      {mounted && open && createPortal(
        <div 
          className="pointer-events-none fixed z-[9999] mb-2 w-64 -translate-x-1/2 -translate-y-full"
          style={{ left: coords.left, top: coords.top }}
        >
          <div className="rounded-md border border-border bg-panel px-3 py-2 text-xs font-normal text-fg shadow-xl">
            <strong className="mb-1 block text-head">{term}</strong>
            {definition}
            {/* Arrow */}
            <div className="absolute -bottom-1.5 left-1/2 -ml-1.5 h-3 w-3 rotate-45 border-b border-r border-border bg-panel" />
          </div>
        </div>,
        document.body
      )}
    </>
  )
}
