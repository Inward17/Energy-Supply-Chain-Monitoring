import { clsx, type ClassValue } from 'clsx'
import { twMerge } from 'tailwind-merge'

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

export function timeAgo(dateString: string): string {
  const date = new Date(dateString)
  if (isNaN(date.getTime())) return ""
  const seconds = Math.floor((new Date().getTime() - date.getTime()) / 1000)
  
  if (seconds < 60) return "just now"
  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) return `${minutes} min${minutes === 1 ? "" : "s"} ago`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours} hr${hours === 1 ? "" : "s"} ago`
  const days = Math.floor(hours / 24)
  return `${days} day${days === 1 ? "" : "s"} ago`
}

/**
 * Return a URL only if it uses a safe scheme, otherwise null.
 *
 * Article links come from external news providers, so the scheme is untrusted
 * input. React escapes text but does NOT sanitise `href` — a `javascript:` or
 * `data:` URL would execute in this origin when clicked. Anchors should render
 * as plain text when this returns null.
 */
export function safeExternalUrl(url: string | null | undefined): string | null {
  if (!url) return null
  const trimmed = String(url).trim()
  try {
    // Relative URLs resolve against the current origin and are safe; the base
    // is only needed so the parser accepts them.
    const parsed = new URL(trimmed, "https://placeholder.invalid")
    return parsed.protocol === "http:" || parsed.protocol === "https:" ? trimmed : null
  } catch {
    return null
  }
}

/** Hostname of a URL for display, or the raw string if it will not parse. */
export function displayDomain(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, "")
  } catch {
    return url
  }
}
