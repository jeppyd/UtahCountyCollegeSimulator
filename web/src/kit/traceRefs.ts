// Small helpers shared by the trace tools: turning a workbench Ref into the server's ref string, and days into dates.
import type { Ref } from '../bench/selection'

/** The ref string /api/trace understands (event:12, tie:3-9, var:mood@12, place:complex:4…), or null when this kind
 *  of item cannot be traced (a var needs one person). */
export function refString(r: Ref | { kind: string; id: string | number } | undefined, people?: number[]): string | null {
  if (!r) return null
  switch (r.kind) {
    case 'person': case 'event': case 'decision': case 'occasion':
      return Number.isFinite(Number(r.id)) ? `${r.kind}:${Number(r.id)}` : null
    case 'tie': return `tie:${r.id}`
    case 'place': return `place:${r.id}`
    case 'var': case 'state': {
      const s = String(r.id)
      if (s.includes('@')) return `var:${s}`
      return people?.length === 1 ? `var:${s}@${people[0]}` : null
    }
    default: return null
  }
}

/** Kinds of trace node that can become the focus of a new trace. */
export const TRACEABLE = new Set(['person', 'event', 'decision', 'occasion', 'tie', 'place', 'var', 'state'])

const DAY_MS = 86400000
/** "Mon, Sep 14" for a simulation day, given the world's first date (ISO). Days before the story say so. */
export function dayLabel(start: string | undefined, d: number, opts: Intl.DateTimeFormatOptions = { weekday: 'short', month: 'short', day: 'numeric' }) {
  if (d < 0) return 'before the story'
  if (!start) return `day ${d}`
  const t = new Date(start + 'T12:00:00').getTime() + d * DAY_MS
  return new Date(t).toLocaleDateString(undefined, opts)
}

/** "7:30 pm" for a minute of the day. */
export function clockLabel(minute: number | null | undefined) {
  if (minute === null || minute === undefined || minute < 0) return ''
  const h = Math.floor(minute / 60) % 24, m = Math.round(minute % 60)
  const ap = h >= 12 ? 'pm' : 'am'
  return `${((h + 11) % 12) + 1}:${String(m).padStart(2, '0')} ${ap}`
}

/** Days between two simulation days, in words ("the same day", "3 days later", "5 weeks later"). */
export function gapWords(days: number) {
  if (days <= 0) return 'the same day'
  if (days === 1) return 'the next day'
  if (days < 14) return `${days} days later`
  if (days < 70) return `${Math.round(days / 7)} weeks later`
  return `${Math.round(days / 30.4)} months later`
}
