// Client-side analytics over columnar agent data: cohort masks, distributions, cross-tabs, stats.
import { useEffect, useState } from 'react'
import { api, Column, Universe } from './api'
import { Cond, loadColumns, useStore, VarSpec } from './store'

export const SERVER_ONLY = (c: Cond) => !!(c.recent_event || c.household)

export function condVars(conds: Cond[]): string[] {
  const s = new Set<string>(['present'])
  for (const c of conds) if (c.var && !SERVER_ONLY(c)) s.add(c.var)
  return [...s]
}

function catCode(col: Column, v: any): number {
  if (typeof v === 'number') return v
  return col.categories ? col.categories.indexOf(String(v)) : Number(v)
}

export function evalCond(c: Cond, cols: Record<string, Column>, n: number): Uint8Array {
  const out = new Uint8Array(n)
  const col = cols[c.var!]
  if (!col) return out.fill(1)
  const x = col.data
  const op = c.op ?? 'eq'
  if (op === 'eq' || op === 'ne' || op === 'in' || op === 'notin') {
    const vals = (Array.isArray(c.value) ? c.value : [c.value]).map(v => col.categories || col.bool ? (col.bool ? (v === true || v === 'true' || v === 1 ? 1 : 0) : catCode(col, v)) : Number(v))
    const set = new Set(vals)
    for (let i = 0; i < n; i++) { const hit = set.has(x[i]); out[i] = (op === 'eq' || op === 'in') ? (hit ? 1 : 0) : (hit ? 0 : 1) }
    return out
  }
  if (op === 'between') { const [lo, hi] = c.value; for (let i = 0; i < n; i++) out[i] = x[i] >= lo && x[i] <= hi ? 1 : 0; return out }
  if (op === 'isnull') { for (let i = 0; i < n; i++) out[i] = Number.isNaN(x[i]) ? 1 : 0; return out }
  if (op === 'notnull') { for (let i = 0; i < n; i++) out[i] = Number.isNaN(x[i]) ? 0 : 1; return out }
  if (op === 'quantile_ge' || op === 'quantile_le') {
    const vals = Array.from(x).filter(v => !Number.isNaN(v)).sort((a, b) => a - b)
    const q = vals[Math.floor((vals.length - 1) * Number(c.value))] ?? 0
    for (let i = 0; i < n; i++) out[i] = op === 'quantile_ge' ? (x[i] >= q ? 1 : 0) : (x[i] <= q ? 1 : 0)
    return out
  }
  const v = Number(c.value)
  for (let i = 0; i < n; i++) {
    const a = x[i]
    out[i] = (op === 'lt' ? a < v : op === 'le' ? a <= v : op === 'gt' ? a > v : a >= v) ? 1 : 0
  }
  return out
}

export async function cohortMask(conds: Cond[], u: Universe): Promise<{ mask: Uint8Array; n: number }> {
  const cols = await loadColumns(condVars(conds), u)
  const present = cols.present
  const n = present ? present.data.length : 0
  const mask = new Uint8Array(n)
  for (let i = 0; i < n; i++) mask[i] = present.data[i]
  for (const c of conds) {
    if (SERVER_ONLY(c)) {
      try {
        const r = await api.cohortServer({ and: [c] }, u)
        const m = new Uint8Array(n)
        for (const id of r.ids) if (id < n) m[id] = 1
        for (let i = 0; i < n; i++) mask[i] &= m[i]
      } catch { /* static mode: ignore server-only clause */ }
      continue
    }
    const m = evalCond(c, cols, n)
    for (let i = 0; i < n; i++) mask[i] &= m[i]
  }
  let k = 0
  for (let i = 0; i < n; i++) k += mask[i]
  return { mask, n: k }
}

/** React hook: load columns + cohort mask, re-run when the sim advances or the cohort changes. */
export function useCohortData(vars: string[], opts: { universe?: Universe; ignoreCohort?: boolean; enabled?: boolean } = {}) {
  const { cohort, universe, dataVersion } = useStore()
  const u = opts.universe ?? universe
  const [state, setState] = useState<{ cols: Record<string, Column>; mask: Uint8Array | null; n: number; loading: boolean; error?: string }>({ cols: {}, mask: null, n: 0, loading: true })
  const enabled = opts.enabled ?? true
  const key = vars.join(',') + '|' + JSON.stringify(opts.ignoreCohort ? [] : cohort) + '|' + u + '|' + dataVersion + '|' + enabled
  useEffect(() => {
    let alive = true
    if (!enabled) { setState({ cols: {}, mask: null, n: 0, loading: false }); return }
    setState(s => ({ ...s, loading: true }))
    ;(async () => {
      try {
        const cols = await loadColumns([...new Set([...vars, 'present'])], u)
        const { mask, n } = await cohortMask(opts.ignoreCohort ? [] : cohort, u)
        if (alive) setState({ cols, mask, n, loading: false })
      } catch (e: any) {
        if (alive) setState({ cols: {}, mask: null, n: 0, loading: false, error: String(e.message ?? e) })
      }
    })()
    return () => { alive = false }
  }, [key])
  return state
}

// ---------------------------------------------------------------- statistics
export function values(col: Column, mask: Uint8Array | null): number[] {
  const out: number[] = []
  const x = col.data
  for (let i = 0; i < x.length; i++) if ((!mask || mask[i]) && !Number.isNaN(x[i])) out.push(x[i])
  return out
}

export function mean(a: number[]) { return a.length ? a.reduce((s, v) => s + v, 0) / a.length : NaN }
export function quantile(sorted: number[], q: number) {
  if (!sorted.length) return NaN
  const p = (sorted.length - 1) * q
  const lo = Math.floor(p), hi = Math.ceil(p)
  return sorted[lo] + (sorted[hi] - sorted[lo]) * (p - lo)
}
export function summary(a: number[]) {
  const s = [...a].sort((x, y) => x - y)
  const m = mean(a)
  const sd = Math.sqrt(mean(a.map(v => (v - m) ** 2)))
  return { n: a.length, mean: m, sd, min: s[0], p10: quantile(s, 0.1), q1: quantile(s, 0.25), median: quantile(s, 0.5), q3: quantile(s, 0.75), p90: quantile(s, 0.9), max: s[s.length - 1] }
}

export function histogram(a: number[], bins = 24, range?: [number, number]) {
  if (!a.length) return { edges: [], counts: [] }
  let lo = range?.[0] ?? Math.min(...a), hi = range?.[1] ?? Math.max(...a)
  const ints = a.every(v => Number.isInteger(v))
  if (ints && hi - lo <= 40) { bins = hi - lo + 1; hi = hi + 1 }
  if (hi === lo) hi = lo + 1
  const w = (hi - lo) / bins
  const counts = new Array(bins).fill(0)
  for (const v of a) { let k = Math.floor((v - lo) / w); if (k >= bins) k = bins - 1; if (k < 0) k = 0; counts[k]++ }
  return { edges: Array.from({ length: bins + 1 }, (_, k) => lo + k * w), counts, ints }
}

export function isCategorical(spec?: VarSpec) { return !!spec && (spec.dtype === 'cat' || spec.dtype === 'bool') }

/** Discretize any variable into labeled groups (categories, booleans, or quantile/ordinal bins). */
export function groupsOf(spec: VarSpec, col: Column, mask: Uint8Array | null, maxBins = 6): { labels: string[]; code: Int16Array } {
  const n = col.data.length
  const code = new Int16Array(n).fill(-1)
  if (spec.dtype === 'cat') {
    const cats = col.categories ?? spec.categories ?? []
    for (let i = 0; i < n; i++) code[i] = col.data[i]
    return { labels: cats.map(c => c.replace(/_/g, ' ')), code }
  }
  if (spec.dtype === 'bool') { for (let i = 0; i < n; i++) code[i] = col.data[i]; return { labels: ['no', 'yes'], code } }
  const vals = values(col, mask)
  const uniq = [...new Set(vals)].sort((a, b) => a - b)
  if (uniq.length <= maxBins + 1 && uniq.every(v => Number.isInteger(v))) {
    const labels = uniq.map(v => spec.ordinal?.[v] ?? String(v))
    const idx = new Map(uniq.map((v, k) => [v, k]))
    for (let i = 0; i < n; i++) { const k = idx.get(col.data[i]); code[i] = k === undefined ? -1 : k }
    return { labels, code }
  }
  const s = [...vals].sort((a, b) => a - b)
  const cuts: number[] = []
  for (let k = 1; k < maxBins; k++) cuts.push(quantile(s, k / maxBins))
  const uc = [...new Set(cuts.map(c => +c.toPrecision(3)))]
  const fmt = (v: number) => Math.abs(v) >= 100 ? v.toFixed(0) : Math.abs(v) >= 10 ? v.toFixed(1) : v.toFixed(2)
  const labels = [`< ${fmt(uc[0])}`, ...uc.slice(1).map((c, k) => `${fmt(uc[k])}–${fmt(c)}`), `≥ ${fmt(uc[uc.length - 1])}`]
  for (let i = 0; i < n; i++) {
    const v = col.data[i]
    if (Number.isNaN(v)) continue
    let k = 0
    while (k < uc.length && v >= uc[k]) k++
    code[i] = k
  }
  return { labels, code }
}

export function crosstab(r: { labels: string[]; code: Int16Array }, c: { labels: string[]; code: Int16Array }, mask: Uint8Array | null) {
  const R = r.labels.length, C = c.labels.length
  const counts = Array.from({ length: R }, () => new Array(C).fill(0))
  const n = r.code.length
  for (let i = 0; i < n; i++) {
    if (mask && !mask[i]) continue
    const a = r.code[i], b = c.code[i]
    if (a < 0 || b < 0 || a >= R || b >= C) continue
    counts[a][b]++
  }
  const rowT = counts.map(row => row.reduce((s, v) => s + v, 0))
  const colT = counts[0]?.map((_, j) => counts.reduce((s, row) => s + row[j], 0)) ?? []
  const total = rowT.reduce((s, v) => s + v, 0)
  let chi2 = 0
  for (let a = 0; a < R; a++) for (let b = 0; b < C; b++) {
    const e = (rowT[a] * colT[b]) / (total || 1)
    if (e > 0) chi2 += (counts[a][b] - e) ** 2 / e
  }
  const dof = (R - 1) * (C - 1)
  const cramer = total > 0 ? Math.sqrt(chi2 / (total * Math.max(1, Math.min(R - 1, C - 1)))) : 0
  return { counts, rowT, colT, total, chi2, dof, cramer, p: chi2pValue(chi2, dof) }
}

// Wilson–Hilferty approximation for chi-square upper-tail p-values
function chi2pValue(x: number, k: number) {
  if (k <= 0) return NaN
  const z = (Math.cbrt(x / k) - (1 - 2 / (9 * k))) / Math.sqrt(2 / (9 * k))
  return 0.5 * erfc(z / Math.SQRT2)
}
function erfc(x: number) {
  const t = 1 / (1 + 0.5 * Math.abs(x))
  const r = t * Math.exp(-x * x - 1.26551223 + t * (1.00002368 + t * (0.37409196 + t * (0.09678418 + t * (-0.18628806 + t * (0.27886807 + t * (-1.13520398 + t * (1.48851587 + t * (-0.82215223 + t * 0.17087277)))))))))
  return x >= 0 ? r : 2 - r
}

export function pearson(x: Float32Array | Uint8Array | Int32Array, y: Float32Array | Uint8Array | Int32Array, mask: Uint8Array | null) {
  let n = 0, sx = 0, sy = 0, sxx = 0, syy = 0, sxy = 0
  for (let i = 0; i < x.length; i++) {
    if (mask && !mask[i]) continue
    const a = x[i], b = y[i]
    if (Number.isNaN(a) || Number.isNaN(b)) continue
    n++; sx += a; sy += b; sxx += a * a; syy += b * b; sxy += a * b
  }
  const cov = sxy / n - (sx / n) * (sy / n)
  const vx = sxx / n - (sx / n) ** 2, vy = syy / n - (sy / n) ** 2
  return { r: vx > 0 && vy > 0 ? cov / Math.sqrt(vx * vy) : NaN, n }
}

/** OLS slope/intercept + r² for y ~ x. */
export function regress(x: number[], y: number[]) {
  const n = x.length
  const mx = mean(x), my = mean(y)
  let sxy = 0, sxx = 0, syy = 0
  for (let i = 0; i < n; i++) { sxy += (x[i] - mx) * (y[i] - my); sxx += (x[i] - mx) ** 2; syy += (y[i] - my) ** 2 }
  const b = sxy / (sxx || 1)
  return { slope: b, intercept: my - b * mx, r2: sxx && syy ? (sxy * sxy) / (sxx * syy) : 0, n }
}

export const fmt = (v: any, d = 2): string => {
  if (v === null || v === undefined || (typeof v === 'number' && Number.isNaN(v))) return '—'
  if (typeof v !== 'number') return String(v)
  const a = Math.abs(v)
  if (a >= 1e6) return (v / 1e6).toFixed(1) + 'M'
  if (a >= 1e4) return (v / 1e3).toFixed(1) + 'K'
  if (a >= 1000) return v.toLocaleString(undefined, { maximumFractionDigits: 0 })
  if (Number.isInteger(v)) return String(v)
  return v.toFixed(a < 1 ? Math.max(d, 2) : d)
}
export const pct = (v: number, d = 1) => (Number.isNaN(v) ? '—' : (100 * v).toFixed(d) + '%')
