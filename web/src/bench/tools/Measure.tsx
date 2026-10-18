// Measure: one field (loneliness, faith, money stress…) for the selection against everyone — over time, and how it is
// spread out now — with the field's scale in words, so a number always says what it means.
import { useMemo } from 'react'
import { cohortMask } from '../../analysis'
import { api } from '../../api'
import { VarPicker } from '../../components'
import { fval } from '../../fields'
import { useAsync } from '../../game'
import { Busy, dayWords, Problem, useWidth, useWorldDays } from '../../kit/Bits'
import { loadColumns, useLens, useStore } from '../../store'
import { PanelOptions } from '../panel'
import type { PanelProps, ToolDef } from '../registry'
import { selPeople } from '../sel'

const BINS = 24
const SEL_C = 'var(--accent)', ALL_C = 'var(--text-muted)'

function MeasureTool({ sel, opts, setOpts }: PanelProps) {
  const u = useLens().u
  const dataVersion = useStore(s => s.dataVersion)
  const reg = useStore(s => s.registry)!
  const { start } = useWorldDays()
  const v: string = reg.variables[opts.var] ? opts.var : 'loneliness'
  const spec = reg.variables[v]
  const cat = spec?.dtype === 'cat' || spec?.dtype === 'bool'
  // the selected people (or the focused person) and/or the selected group
  const ppl = selPeople(sel)
  const g = { people: ppl.length ? ppl : undefined, filter: sel.filter?.length ? sel.filter : undefined }
  const own = !!(g.people || g.filter)
  const [wrap, w] = useWidth<HTMLDivElement>()

  const over = useAsync(() => api.cohortTimeline({ vars: [v], u, filter: g.filter ?? null, people: g.people ?? null }),
    [v, u, JSON.stringify(g), dataVersion], { key: `bench-measure-t:${u}:${v}:${JSON.stringify(g)}` })
  const now = useAsync(async () => {
    const c = await loadColumns([v, 'present'], u)
    let mask: Uint8Array | null = null
    if (sel.filter?.length) mask = (await cohortMask(sel.filter, u)).mask as any
    return { c, mask }
  }, [v, u, JSON.stringify(sel.filter ?? []), dataVersion], { key: `bench-measure-n:${u}:${v}:${JSON.stringify(sel.filter ?? [])}` })

  // the distribution now: everyone vs the selection
  const dist = useMemo(() => {
    const d = now.data
    const col = d?.c[v], pres = d?.c.present?.data
    if (!col || !pres) return null
    const n = pres.length
    const inSel = new Uint8Array(n)
    if (ppl.length) ppl.forEach(i => { if (i < n && (!d.mask || d.mask[i])) inSel[i] = 1 })
    else if (d.mask) for (let i = 0; i < n; i++) inSel[i] = d.mask[i] ? 1 : 0
    const x = col.data
    if (cat) {
      const labs: string[] = col.categories ?? (col.bool ? ['no', 'yes'] : [])
      const a = new Array(labs.length).fill(0), s = new Array(labs.length).fill(0)
      let na = 0, ns = 0
      for (let i = 0; i < n; i++) if (pres[i] && Number.isFinite(x[i])) { a[x[i]]++; na++; if (inSel[i]) { s[x[i]]++; ns++ } }
      return { cat: true as const, labs, a: a.map(k => k / (na || 1)), s: s.map(k => k / (ns || 1)), na, ns }
    }
    let lo = Infinity, hi = -Infinity
    for (let i = 0; i < n; i++) if (pres[i] && Number.isFinite(x[i])) { lo = Math.min(lo, x[i]); hi = Math.max(hi, x[i]) }
    if (spec?.scale?.min !== undefined) lo = spec.scale.min
    if (spec?.scale?.max !== undefined) hi = spec.scale.max
    if (!(hi > lo)) hi = lo + 1
    const a = new Array(BINS).fill(0), s = new Array(BINS).fill(0)
    let na = 0, ns = 0, sa = 0, ss = 0
    for (let i = 0; i < n; i++) {
      if (!pres[i] || !Number.isFinite(x[i])) continue
      const b = Math.min(BINS - 1, Math.max(0, Math.floor(((x[i] - lo) / (hi - lo)) * BINS)))
      a[b]++; na++; sa += x[i]
      if (inSel[i]) { s[b]++; ns++; ss += x[i] }
    }
    return { cat: false as const, lo, hi, a: a.map(k => k / (na || 1)), s: s.map(k => k / (ns || 1)), na, ns, ma: sa / (na || 1), ms: ns ? ss / ns : null }
  }, [now.data, ppl.join(','), v])

  const t = over.data
  const ser = (k: 'cohort' | 'everyone') => (t?.[k]?.[v] ?? []) as any[]
  const lineVals = (s: any[]): (number | null)[] => cat ? s.map(x => x ? (x.yes ?? x.true ?? Math.max(...Object.values(x) as number[])) : null) : s
  const W = Math.max(200, w), CH = 120, L = 34
  const days: number[] = t?.days ?? []
  const all = [...lineVals(ser('everyone')), ...(own ? lineVals(ser('cohort')) : [])].filter((x): x is number => x !== null && Number.isFinite(x))
  const ylo = cat ? 0 : Math.min(...all, spec?.scale?.min ?? Infinity), yhi = cat ? 1 : Math.max(...all, ylo + 1e-6)
  const X = (k: number) => L + (days.length > 1 ? (k / (days.length - 1)) * (W - L - 8) : 0)
  const Y = (y: number) => 8 + (1 - (y - ylo) / (yhi - ylo || 1)) * (CH - 22)
  const path = (s: (number | null)[]) => {
    let p = '', pen = false
    s.forEach((y, k) => { if (y === null || !Number.isFinite(y)) { pen = false; return } p += `${pen ? 'L' : 'M'}${X(k).toFixed(1)},${Y(y).toFixed(1)}`; pen = true })
    return p
  }
  const fmt = (x: number) => fval(spec, x)

  return (
    <div className="bme" ref={wrap}>
      <PanelOptions>
        <VarPicker value={v} onChange={x => x && setOpts({ ...opts, var: x })} placeholder="Pick a field" />
      </PanelOptions>
      <div className="bme-scale">
        <b style={{ color: 'var(--text-primary)' }}>{spec?.label ?? v}</b>
        {spec?.desc && <span>{spec.desc}</span>}
        {(spec?.scale?.low || spec?.scale?.high) && !spec?.scale?.note && (
          <div className="ends"><span>{spec.scale.min ?? ''} {spec.scale.low ? `= ${spec.scale.low}` : ''}</span><span>{spec.scale.max ?? ''} {spec.scale.high ? `= ${spec.scale.high}` : ''}</span></div>
        )}
        {spec?.scale?.note && <span>{spec.scale.note}</span>}
        <div className="bme-ruler-slot" data-var={v} />
      </div>
      <div className="bx-legend">
        {own && <span><i className="bx-catdot" style={{ background: SEL_C }} />the selection</span>}
        <span><i className="bx-catdot" style={{ background: ALL_C }} />everyone</span>
        {cat && <span className="bx-note">lines show the share in the {dist?.cat ? `"${dist.labs[dist.labs.length - 1]}"` : 'top'} group</span>}
      </div>
      <div className="bx-h">Over time</div>
      {over.error && !t && <div className="bx-note">{/not recorded|not tracked|static/i.test(over.error) ? 'This field is not recorded over time; only its spread now is shown.' : over.error}</div>}
      {!t && !over.error && <Busy what="Reading the record" />}
      {t && days.length > 0 && (
        <svg width={W} height={CH} style={{ display: 'block' }}>
          {[ylo, (ylo + yhi) / 2, yhi].map((y, k) => (
            <g key={k} className="bd-axis"><line x1={L} x2={W - 8} y1={Y(y)} y2={Y(y)} stroke="var(--grid)" /><text x={0} y={Y(y) + 4}>{cat ? `${Math.round(y * 100)}%` : y.toFixed(2)}</text></g>
          ))}
          {days.map((d, k) => (k === 0 || k === days.length - 1 || k % Math.max(1, Math.ceil(days.length / 5)) === 0) && (
            <text key={d} className="bd-axis" x={X(k)} y={CH - 2} textAnchor={k === 0 ? 'start' : k === days.length - 1 ? 'end' : 'middle'} style={{ fill: 'var(--text-muted)', fontSize: 10.5 }}>{dayWords(start, d)}</text>
          ))}
          <path d={path(lineVals(ser('everyone')))} fill="none" stroke={ALL_C} strokeWidth={1.6} />
          {own && <path d={path(lineVals(ser('cohort')))} fill="none" stroke={SEL_C} strokeWidth={2.2} />}
        </svg>
      )}
      {t && own && t.n?.length > 0 && <div className="bx-note">The selection as it is now ({t.n[t.n.length - 1] === 1 ? 'one person' : `${t.n[t.n.length - 1].toLocaleString()} people`}), followed back in time (recorded every two weeks).</div>}
      <div className="bx-h">Now</div>
      {now.error && !dist && <Problem error={now.error} />}
      {!dist && !now.error && <Busy what="Reading everyone" />}
      {dist && !dist.cat && (
        <>
          <div className="bme-nums">
            <span>everyone: average <b>{fmt(dist.ma)}</b> ({dist.na.toLocaleString()} people)</span>
            {own && <span>the selection: average <b>{dist.ms === null ? '—' : fmt(dist.ms)}</b> ({dist.ns.toLocaleString()})</span>}
          </div>
          <svg width={W} height={90} style={{ display: 'block' }}>
            {dist.a.map((p, b) => {
              const bw = (W - L - 8) / BINS
              const few = dist.ns < 20   // a handful of people: mark where they are instead of comparing shapes
              const mx = Math.max(...dist.a, ...(own && !few ? dist.s : [0]), 1e-9)
              return (
                <g key={b}>
                  <rect x={L + b * bw} y={74 - (p / mx) * 66} width={bw - 1} height={(p / mx) * 66} fill={ALL_C} opacity={0.35}>
                    <title>{`${fmt(dist.lo + (b / BINS) * (dist.hi - dist.lo))} – ${fmt(dist.lo + ((b + 1) / BINS) * (dist.hi - dist.lo))}: ${Math.round(p * 100)}% of everyone${own ? `, ${Math.round(dist.s[b] * 100)}% of the selection` : ''}`}</title>
                  </rect>
                  {own && dist.s[b] > 0 && (few
                    ? <rect x={L + b * bw + bw / 2 - 1.5} y={8} width={3} height={66} rx={1.5} fill={SEL_C} pointerEvents="none" />
                    : <rect x={L + b * bw + bw * 0.25} y={74 - (dist.s[b] / mx) * 66} width={Math.max(1, bw * 0.5 - 1)} height={(dist.s[b] / mx) * 66} fill={SEL_C} pointerEvents="none" />)}
                </g>
              )
            })}
            <text className="bd-axis" x={L} y={88} style={{ fill: 'var(--text-muted)', fontSize: 10.5 }}>{fmt(dist.lo)}{spec?.scale?.low ? ` · ${spec.scale.low}` : ''}</text>
            <text className="bd-axis" x={W - 8} y={88} textAnchor="end" style={{ fill: 'var(--text-muted)', fontSize: 10.5 }}>{spec?.scale?.high ? `${spec.scale.high} · ` : ''}{fmt(dist.hi)}</text>
          </svg>
        </>
      )}
      {dist?.cat && (
        <div className="bk-bars">
          {dist.labs.map((l, k) => (
            <div key={l} className="bk-bar" title={`${Math.round(dist.a[k] * 100)}% of everyone${own ? `, ${Math.round(dist.s[k] * 100)}% of the selection` : ''}`}>
              <span>{String(l).replace(/_/g, ' ')}</span>
              <span className="t" style={{ position: 'relative' }}>
                <i style={{ width: `${dist.a[k] * 100}%`, background: ALL_C, opacity: 0.5 }} />
                {own && <i style={{ width: `${dist.s[k] * 100}%`, background: SEL_C, position: 'absolute', top: 0, height: '100%' }} />}
              </span>
              <span>{Math.round((own ? dist.s[k] : dist.a[k]) * 100)}%</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

export const tool: ToolDef = {
  id: 'measure',
  label: 'Measure',
  icon: 'trend',
  hint: 'Any field for the selection against everyone: over time and spread out now, with what its numbers mean.',
  group: 'see',
  order: 30,
  component: MeasureTool,
  size: { w: 5, h: 8 },
}
