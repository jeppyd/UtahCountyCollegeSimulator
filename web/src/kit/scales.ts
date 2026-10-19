// What a number means: each field's scale (range, units, anchor words, how it is measured — ucsim/scales.py, served
// in VarSpec.scale) and where people sit on it right now (/api/scales, routes_scales.py). Shared by Ruler, Val and the
// Scales tool. Distributions are fetched in batches and cached per world and day.
import { useEffect, useState } from 'react'
import { STATIC, type Universe } from '../api'
import { useStore } from '../store'

export type Anchor = { at: number; label: string; more?: string }
export type Scale = {
  min?: number; max?: number; view?: [number, number]; low?: string; high?: string; anchors?: Anchor[]
  levels?: string[]; percent?: boolean; z?: boolean; axis?: 'log'; log_c?: number
  basis?: string; unit?: string; how?: string; note?: string
}
export type Dist = {
  n: number; mean: number; min: number; max: number; p10: number; p25: number; p50: number; p75: number; p90: number
  q: number[]; hist?: { edges: number[]; counts: number[]; below: number; above: number }
}

/** The scale of a field (from the registry), or null for categories and fields without one. */
export function useScale(v: string): Scale | null {
  const spec = useStore(s => s.registry?.variables[v])
  return (spec?.scale as Scale | undefined) ?? null
}

// ---------------------------------------------------------------- the ruler's axis (mirrors scales.axis_fwd)
export const fwd = (x: number, sc: Scale) => (sc.axis === 'log' ? Math.sign(x) * Math.log10(1 + Math.abs(x) / (sc.log_c ?? 1)) : x)
/** The part of the range the ruler shows. */
export function viewOf(sc: Scale, d?: Dist | null): [number, number] {
  const lo = sc.view?.[0] ?? sc.min ?? d?.min ?? 0
  let hi = sc.view?.[1] ?? sc.max ?? d?.max ?? 1
  if (!(hi > lo)) hi = lo + 1
  return [lo, hi]
}
/** 0…1 along the ruler. */
export function pos(x: number, sc: Scale, d?: Dist | null): number {
  const [lo, hi] = viewOf(sc, d)
  const t0 = fwd(lo, sc), t1 = fwd(hi, sc)
  return Math.max(0, Math.min(1, (fwd(x, sc) - t0) / (t1 - t0 || 1)))
}

/** The anchor words nearest to x on the ruler (scales.anchor_words). */
export function anchorWords(sc: Scale | null, x: number | null | undefined): string {
  if (!sc?.anchors?.length || x === null || x === undefined || !Number.isFinite(x)) return ''
  const t = fwd(x, sc)
  return sc.anchors.reduce((b, a) => (Math.abs(fwd(a.at, sc) - t) < Math.abs(fwd(b.at, sc) - t) ? a : b)).label
}

/** The share of people below x, read off the percentiles (0…1). */
export function pctOf(d: Dist | null | undefined, x: number): number | null {
  if (!d?.q?.length || !Number.isFinite(x)) return null
  const q = d.q
  if (x <= q[0]) return 0
  if (x >= q[100]) return 1
  let k = 0
  while (k < 100 && q[k + 1] < x) k++
  const span = q[k + 1] - q[k]
  return (k + (span > 0 ? (x - q[k]) / span : 0.5)) / 100
}
/** "higher than 78% of people" / "lower than 90% of people" / "about the middle". */
export function pctWords(p: number | null, among = 'people'): string {
  if (p === null) return ''
  const k = Math.round(p * 100)
  if (k >= 45 && k <= 55) return `about the middle of ${among}`
  return k > 50 ? `higher than ${k}% of ${among}` : `lower than ${100 - k}% of ${among}`
}

// ---------------------------------------------------------------- live distributions, batched and cached
const cache = new Map<string, Dist | null>()
const waiting = new Map<string, ((d: Dist | null) => void)[]>()
let queued: { u: Universe; tag: string; vars: Set<string> } | null = null

function flush() {
  const job = queued
  queued = null
  if (!job) return
  const vars = [...job.vars]
  fetch(`/api/scales?u=${job.u}&vars=${encodeURIComponent(vars.join(','))}`)
    .then(r => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
    .then(res => vars.forEach(v => settle(`${job.tag}:${v}`, res.fields?.[v]?.dist ?? null)))
    .catch(() => vars.forEach(v => settle(`${job.tag}:${v}`, null)))
}
function settle(key: string, d: Dist | null) {
  cache.set(key, d)
  if (cache.size > 2000) cache.delete(cache.keys().next().value as string)
  waiting.get(key)?.forEach(f => f(d))
  waiting.delete(key)
}

/** Where everyone present sits on a field's scale today (null while loading, in the snapshot, or for categories). */
export function useDist(v: string | undefined, u?: Universe): Dist | null {
  const lens = useStore(s => s.lens)
  const day = useStore(s => s.status?.day ?? 0)
  const world = useStore(s => s.status?.world_id ?? '')
  const uu: Universe = u ?? (lens === 'alt' ? 'alt' : 'base')
  const tag = `${world}:${uu}:${day}`
  const key = `${tag}:${v}`
  const [d, setD] = useState<Dist | null>(() => cache.get(key) ?? null)
  useEffect(() => {
    if (!v || STATIC) { setD(null); return }
    if (cache.has(key)) { setD(cache.get(key) ?? null); return }
    let live = true
    const list = waiting.get(key) ?? []
    list.push(x => { if (live) setD(x) })
    waiting.set(key, list)
    if (list.length === 1) {
      if (!queued || queued.tag !== tag) { flush(); queued = { u: uu, tag, vars: new Set() } }
      queued.vars.add(v)
      setTimeout(flush, 30)
    }
    return () => { live = false }
  }, [key])
  return d
}

/** A distribution computed in the browser from a group's values (for a cohort the server wasn't asked about). */
export function distOf(xs: ArrayLike<number>): Dist | null {
  const v = Float64Array.from(Array.prototype.filter.call(xs, (x: number) => Number.isFinite(x)) as number[]).sort()
  const n = v.length
  if (!n) return null
  const at = (p: number) => { const r = (p / 100) * (n - 1), k = Math.floor(r); return v[k] + (v[Math.min(n - 1, k + 1)] - v[k]) * (r - k) }
  const q = Array.from({ length: 101 }, (_, p) => at(p))
  let s = 0
  for (let i = 0; i < n; i++) s += v[i]
  return { n, mean: s / n, min: v[0], max: v[n - 1], p10: q[10], p25: q[25], p50: q[50], p75: q[75], p90: q[90], q }
}
