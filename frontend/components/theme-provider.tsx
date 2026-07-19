"use client"

import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react"

export type Theme = "light" | "dark"

/** Shared with the pre-paint init script in app/layout.tsx. */
export const THEME_STORAGE_KEY = "meridian-theme"

const ThemeContext = createContext<{ theme: Theme; toggle: () => void }>({
  theme: "dark",
  toggle: () => {},
})

export function ThemeProvider({ children }: { children: ReactNode }) {
  // The SSR value is a constant so server and client markup agree on first
  // render. The real theme was already applied to <html> by the init script
  // before paint; we only mirror it into React state on mount.
  const [theme, setTheme] = useState<Theme>("dark")

  useEffect(() => {
    setTheme(document.documentElement.classList.contains("dark") ? "dark" : "light")
  }, [])

  const toggle = useCallback(() => {
    setTheme((prev) => {
      const next: Theme = prev === "dark" ? "light" : "dark"
      const root = document.documentElement
      root.classList.toggle("dark", next === "dark")
      root.classList.toggle("light", next === "light")
      root.style.colorScheme = next
      try {
        localStorage.setItem(THEME_STORAGE_KEY, next)
      } catch {
        // Private mode / storage disabled: theme still applies for this session.
      }
      return next
    })
  }, [])

  return <ThemeContext.Provider value={{ theme, toggle }}>{children}</ThemeContext.Provider>
}

export const useTheme = () => useContext(ThemeContext)
