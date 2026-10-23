// How the Map paints people. Everyone starts as the same dot; pick any field and decide how it shows:
// a category field gives each category its own color (click categories to show only some),
// a number field can be a color ramp, a fade (one color, higher values solid, lower ones see-through) or a threshold
// (only the people past a value you set are on the map). Hidden categories and people outside a threshold leave the
// map altogether (alpha 0: the map skips them). The settings live in the panel's options, so they persist.
import { quantile } from '../../analysis'
import { type Column } from '../../api'
import { cssVar, hexRgb, seqColor } from '../../components'
import { fval, pretty } from '../../fields'
import type { VarSpec } from '../../store'

export type Rgba = [number, number, number, number]
export type NumMode = 'ramp' | 'fade' | 'threshold'
export type ThrOp = 'ge' | 'le' | 'between' | 'outside'
export type Paint = {
  mode?: NumMode
  op?: ThrOp
  a?: number                 // the threshold (or the lower end of a range)
  b?: number                 // the upper end of a range
  flip?: boolean             // ramp and fade: lower values strong instead
  only?: string[]            // categories shown in color (empty: all of them)
}
export type Stats = { min: number; max: number; lo: number; hi: number; med: number; int: boolean }

const FAINT = 50, SOLID = 225
const HIDDEN: Rgba = [0, 0, 0, 0]

/** n colors as distinct from one another as we can make them: the app's eight series colors when they suffice, else
 *  n hues spread evenly around the wheel with alternating lightness, so a field with 20 categories still has 20
 *  tellable colors (and none repeats). */
export function distinctColors(n: number): [number, number, number][] {
  if (n <= 8) return Array.from({ length: n }, (_, k) => hexRgb(cssVar(`--s${k + 1}`)))
  return Array.from({ length: n }, (_, k) => hsl((k * 360) / n + 210, [0.72, 0.6, 0.68][k % 3], [0.46, 0.64, 0.32][k % 3]))
}
function hsl(h: number, s: number, l: number): [number, number, number] {
  const a = s * Math.min(l, 1 - l)
  const f = (n: number) => { const k = (n + h / 30) % 12; return Math.round(255 * (l - a * Math.max(-1, Math.min(k - 3, 9 - k, 1)))) }
  return [f(0), f(8), f(4)]
}
export const rgbCss = (c: number[]) => `rgb(${c[0]},${c[1]},${c[2]})`

export function numStats(col: Column, spec?: VarSpec): Stats {
  const vals: number[] = []
  const step = Math.max(1, Math.floor(col.data.length / 20000))
  for (let i = 0; i < col.data.length; i += step) if (!Number.isNaN(col.data[i])) vals.push(col.data[i] as number)
  vals.sort((a, b) => a - b)
  const int = !!spec && /^[iu]/.test(spec.dtype)
  return { min: vals[0] ?? 0, max: vals[vals.length - 1] ?? 1, lo: quantile(vals, 0.02), hi: quantile(vals, 0.98), med: quantile(vals, 0.5), int }
}

export function passes(x: number, p: Paint, st: Stats) {
  const a = p.a ?? st.med, b = p.b ?? st.hi
  switch (p.op ?? 'ge') {
    case 'ge': return x >= a
    case 'le': return x <= a
    case 'between': return x >= Math.min(a, b) && x <= Math.max(a, b)
    case 'outside': return x < Math.min(a, b) || x > Math.max(a, b)
  }
}

/** The painter for one field: person i → rgba, plus what the legend needs. */
export function painter(col: Column, spec: VarSpec | undefined, p: Paint, base: [number, number, number], other: [number, number, number]) {
  const faint: Rgba = [...base, FAINT]          // no value (and not filtered out)
  if (col.categories || col.bool) {
    const cats = col.categories ?? ['no', 'yes']
    const pal = distinctColors(cats.length)
    const only = p.only?.length ? new Set(p.only) : null
    const show = cats.map(c => !only || only.has(c))
    const counts = new Array(cats.length).fill(0)
    for (let i = 0; i < col.data.length; i++) { const k = col.data[i]; if (k < cats.length) counts[k]++ }
    return {
      fn: (i: number): Rgba => { const k = col.data[i]; return k < cats.length ? (show[k] ? [...pal[k], SOLID] : HIDDEN) : only ? HIDDEN : faint },
      legend: { kind: 'cat' as const, cats: cats.map((c, k) => ({ key: c, label: pretty(c), color: pal[k], n: counts[k], on: show[k] })) },
    }
  }
  const st = numStats(col, spec)
  const mode = p.mode ?? 'ramp'
  const lo = st.lo, span = (st.hi - st.lo) || 1
  const t = (x: number) => { const v = Math.max(0, Math.min(1, (x - lo) / span)); return p.flip ? 1 - v : v }
  let n = 0
  if (mode === 'threshold') for (let i = 0; i < col.data.length; i++) { const x = col.data[i] as number; if (!Number.isNaN(x) && passes(x, p, st)) n++ }
  const hit = hexRgb(cssVar('--s2'))
  const fn = mode === 'ramp'
    ? (i: number): Rgba => { const x = col.data[i] as number; return Number.isNaN(x) ? [...other, FAINT] : [...seqColor(t(x)), SOLID] }
    : mode === 'fade'
      ? (i: number): Rgba => { const x = col.data[i] as number; return Number.isNaN(x) ? [...base, 8] : [...base, Math.round(14 + 241 * t(x) ** 1.3)] }
      : (i: number): Rgba => { const x = col.data[i] as number; return !Number.isNaN(x) && passes(x, p, st) ? [...hit, 245] : HIDDEN }
  return { fn, legend: { kind: 'num' as const, st, mode, n, total: col.data.length, hit } }
}

export type Legend = ReturnType<typeof painter>['legend'] | { kind: 'cat'; cats: { key: string; label: string; color: [number, number, number]; n: number; on: boolean }[] }

/** The legend and its controls: categories to switch on and off, or the way a number shows (with its threshold). */
export function PaintLegend({ title, spec, legend, paint, setPaint, base }:
  { title: string; spec?: VarSpec; legend: Legend; paint: Paint; setPaint: (p: Paint) => void; base: [number, number, number] }) {
  if (legend.kind === 'cat') {
    const all = legend.cats.every(c => c.on)
    const toggle = (key: string) => {
      const on = legend.cats.filter(c => c.on).map(c => c.key)
      const next = all ? [key] : on.includes(key) ? on.filter(k => k !== key) : [...on, key]
      setPaint({ ...paint, only: next.length === legend.cats.length ? [] : next })
    }
    return (
      <div className="bm-legend">
        <div className="bm-lg-h"><b>{title}</b>{!all && <button className="lm-link" onClick={() => setPaint({ ...paint, only: [] })}>show all</button>}</div>
        <div className="bx-legend bm-cats">{legend.cats.filter(c => c.n > 0 || !c.on).map(c => (
          <button key={c.key} className={c.on ? '' : 'off'} onClick={() => toggle(c.key)} title={all ? `Show only ${c.label}` : c.on ? `Hide ${c.label}` : `Show ${c.label} too`}>
            <i className="bx-catdot" style={{ background: rgbCss(c.color) }} />{c.label}<small className="muted"> {c.n.toLocaleString()}</small>
          </button>))}
        </div>
        <small className="muted">Click a category to show only it; click more to add them. Hidden ones leave the map.</small>
      </div>
    )
  }
  const { st, mode, n, total, hit } = legend
  const op = paint.op ?? 'ge', a = paint.a ?? st.med, b = paint.b ?? st.hi
  const step = st.int ? 1 : niceStep((st.max - st.min) / 200)
  const two = op === 'between' || op === 'outside'
  const num = (v: number, on: (x: number) => void) => (
    <span className="bm-thr-v">
      <input type="range" min={st.min} max={st.max} step={step} value={v} onChange={e => on(Number(e.target.value))} />
      <input type="number" step={step} value={round(v, step)} onChange={e => e.target.value !== '' && on(Number(e.target.value))} />
    </span>
  )
  const ends = paint.flip ? [st.hi, st.lo] : [st.lo, st.hi]
  return (
    <div className="bm-legend">
      <b>{title}</b>
      <div className="seg bm-seg">
        {(['ramp', 'fade', 'threshold'] as NumMode[]).map(m => <button key={m} className={mode === m ? 'on' : ''} onClick={() => setPaint({ ...paint, mode: m })}
          title={m === 'ramp' ? 'A color ramp from light to dark' : m === 'fade' ? 'One color: higher values solid, lower ones see-through' : 'Only the people past a value you set stand out'}>
          {m === 'ramp' ? 'Colors' : m === 'fade' ? 'Fade' : 'Threshold'}</button>)}
      </div>
      {mode !== 'threshold' && <>
        <div className="bm-ramp"><span>{fval(spec, ends[0])}{spec?.scale?.low && !paint.flip ? ` · ${spec.scale.low}` : ''}</span>
          <i style={mode === 'fade' ? { background: `linear-gradient(90deg, rgba(${base.join(',')},.06), rgb(${base.join(',')}))` } : undefined} />
          <span>{fval(spec, ends[1])}{spec?.scale?.high && !paint.flip ? ` · ${spec.scale.high}` : ''}</span></div>
        <label className="inline small"><input type="checkbox" checked={!!paint.flip} onChange={e => setPaint({ ...paint, flip: e.target.checked })} /> lower values strongest</label>
      </>}
      {mode === 'threshold' && <>
        <div className="bm-thr">
          <select value={op} onChange={e => setPaint({ ...paint, op: e.target.value as ThrOp })}>
            <option value="ge">at least</option><option value="le">at most</option><option value="between">between</option><option value="outside">outside</option>
          </select>
          {num(a, x => setPaint({ ...paint, a: x }))}
          {two && <><span className="small muted">and</span>{num(b, x => setPaint({ ...paint, b: x }))}</>}
        </div>
        <small><i className="bx-catdot" style={{ background: rgbCss(hit) }} /> <b>{n.toLocaleString()}</b> of {total.toLocaleString()} people ({Math.round((100 * n) / (total || 1))}%)
          <span className="muted"> · range {fval(spec, st.min)} to {fval(spec, st.max)}, typical {fval(spec, st.med)}</span></small>
      </>}
    </div>
  )
}
function niceStep(x: number) {
  if (!(x > 0)) return 0.01
  const p = 10 ** Math.floor(Math.log10(x)), m = x / p
  return (m < 1.5 ? 1 : m < 3.5 ? 2 : m < 7.5 ? 5 : 10) * p
}
function round(v: number, step: number) {
  const d = Math.max(0, -Math.floor(Math.log10(step)))
  return Number(v.toFixed(d))
}
