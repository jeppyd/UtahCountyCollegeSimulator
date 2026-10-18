// Small shared pieces for workbench tools: empty, loading and problem states; event-category colors and words; the
// world's calendar (simulation day → date words).
import type { ReactNode } from 'react'
import { useStore } from '../store'
import { dayLabel } from './traceRefs'

export function Empty({ title, children }: { title: string; children?: ReactNode }) {
  return <div className="bx-empty"><b>{title}</b>{children && <div>{children}</div>}</div>
}
export function Busy({ what = 'Loading' }: { what?: string }) { return <div className="bx-busy"><i />{what}…</div> }
export function Problem({ error }: { error: string }) {
  const plain = /did not answer|Failed to fetch|NetworkError/.test(error) ? 'The simulator is busy or not answering; it will try again.' : error
  return <div className="bx-problem">{plain}</div>
}

// ---------------------------------------------------------------- event categories
const CAT: Record<string, [string, string]> = {
  social: ['--s3', 'Friends & social life'], romance: ['--s5', 'Dating & romance'], sexuality: ['--s5', 'Intimacy'],
  religion: ['--s7', 'Faith'], academics: ['--s4', 'School'], work: ['--s2', 'Work & money'], family: ['--s8', 'Family'],
  health: ['--s1', 'Health'], coping: ['--s1', 'Coping'], housing: ['--s6', 'Home'], habits: ['--text-muted', 'Habits'],
  plans: ['--text-muted', 'Plans'], intervention: ['--u-alt', 'What-if changes'],
}
export const CAT_ORDER = ['romance', 'social', 'religion', 'academics', 'work', 'family', 'housing', 'health', 'coping', 'habits', 'sexuality', 'plans', 'intervention']
export const catVar = (c: string) => `var(${CAT[c]?.[0] ?? '--text-muted'})`
export const catLabel = (c: string) => CAT[c]?.[1] ?? c.replace(/_/g, ' ')
export function catRgb(c: string): [number, number, number] {
  const v = getComputedStyle(document.documentElement).getPropertyValue(CAT[c]?.[0] ?? '--text-muted').trim()
  const x = v.replace('#', '')
  return x.length >= 6 ? [parseInt(x.slice(0, 2), 16), parseInt(x.slice(2, 4), 16), parseInt(x.slice(4, 6), 16)] : [137, 135, 129]
}
export function CatDot({ c }: { c: string }) { return <i className="bx-catdot" style={{ background: catVar(c) }} /> }

// ---------------------------------------------------------------- calendar
/** The world's first date (ISO) and today's simulation day. */
export function useWorldDays(): { start: string | undefined; today: number } {
  const status = useStore(s => s.status)
  if (!status?.date || status.day === undefined) return { start: undefined, today: 0 }
  const t = new Date(status.date + 'T12:00:00')
  t.setDate(t.getDate() - status.day)
  return { start: t.toISOString().slice(0, 10), today: status.day }
}
/** "Sep 14" (short) or "Mon, Sep 14" for a simulation day. */
export const dayWords = (start: string | undefined, d: number, long = false) =>
  dayLabel(start, d, long ? { weekday: 'short', month: 'short', day: 'numeric' } : { month: 'short', day: 'numeric' })
export const BLOCK_WORDS = ['morning', 'afternoon', 'evening', 'late evening']
