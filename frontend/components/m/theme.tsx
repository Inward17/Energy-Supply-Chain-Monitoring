"use client"

import { useCallback, useSyncExternalStore } from "react"
import { THEME_KEY } from "./theme-script"

export type Theme = "dark" | "light"

const listeners = new Set<() => void>()
const read = (): Theme =>
  typeof document !== "undefined" && document.documentElement.classList.contains("light") ? "light" : "dark"

function subscribe(fn: () => void) {
  listeners.add(fn)
  return () => listeners.delete(fn)
}

export function useTheme(): [Theme, () => void] {
  const theme = useSyncExternalStore(subscribe, read, () => "dark" as Theme)
  const toggle = useCallback(() => {
    const next: Theme = read() === "light" ? "dark" : "light"
    document.documentElement.classList.toggle("light", next === "light")
    document.documentElement.classList.toggle("dark", next === "dark")
    try {
      localStorage.setItem(THEME_KEY, next)
    } catch {
      /* private mode: the choice still applies for this session */
    }
    listeners.forEach((l) => l())
  }, [])
  return [theme, toggle]
}

/** Resolve a CSS colour variable to a concrete value — Leaflet writes colours
 *  into SVG attributes, so it needs real values rather than var(). */
export function cssColor(v: string): string {
  const m = /^var\((--[\w-]+)\)$/.exec(v)
  if (!m || typeof document === "undefined") return v
  return getComputedStyle(document.documentElement).getPropertyValue(m[1]).trim() || v
}

export function ThemeToggle({ className = "" }: { className?: string }) {
  const [theme, toggle] = useTheme()
  const light = theme === "light"
  return (
    <button
      type="button"
      onClick={toggle}
      aria-label={light ? "Switch to dark theme" : "Switch to light theme"}
      title={light ? "Dark theme" : "Light theme"}
      className={`flex items-center justify-center rounded-[10px] border border-edge bg-[var(--x-0f141a)] text-muted hover:text-fg ${className}`}
    >
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true">
        {light ? (
          <path d="M20 14.5A8 8 0 0 1 9.5 4 8 8 0 1 0 20 14.5z" />
        ) : (
          <>
            <circle cx="12" cy="12" r="4" />
            <path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
          </>
        )}
      </svg>
    </button>
  )
}
