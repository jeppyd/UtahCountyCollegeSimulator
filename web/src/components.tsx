import * as echarts from 'echarts'
import { ReactNode, useEffect, useMemo, useRef, useState } from 'react'
import { fmt } from './analysis'
import { Cond, useStore, VarSpec } from './store'

// ---------------------------------------------------------------- theme tokens
export function cssVar(name: string) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim()
}
export function series(k: number) { return cssVar(`--s${(k % 8) + 1}`) }
export function tokens() {
  return {
    surface: cssVar('--surface-1'), text: cssVar('--text-primary'), text2: cssVar('--text-secondary'),
    muted: cssVar('--text-muted'), grid: cssVar('--grid'), axis: cssVar('--axis'), accent: cssVar('--accent'),
  }
}
/** Sequential blue ramp (light→dark) for magnitudes. */
export const SEQ = ['#cde2fb', '#9ec5f4', '#6da7ec', '#3987e5', '#256abf', '#184f95', '#0d366b']
export function seqColor(t: number): [number, number, number] {
  const c = SEQ[Math.max(0, Math.min(SEQ.length - 1, Math.round(t * (SEQ.length - 1))))]
  return hexRgb(c)
}
export function divColor(t: number): [number, number, number] {
  // t in [-1,1]: blue (negative) — gray — red (positive)
  const neg = hexRgb('#2a78d6'), pos = hexRgb('#e34948'), mid = hexRgb(document.documentElement.getAttribute('data-theme') === 'dark' ? '#383835' : '#d9d8d2')
  const a = Math.max(-1, Math.min(1, t))
  const end = a < 0 ? neg : pos
  const f = Math.abs(a)
  return [0, 1, 2].map(i => Math.round(mid[i] + (end[i] - mid[i]) * f)) as [number, number, number]
}
export function hexRgb(h: string): [number, number, number] {
  const x = h.replace('#', '')
  return [parseInt(x.slice(0, 2), 16), parseInt(x.slice(2, 4), 16), parseInt(x.slice(4, 6), 16)]
}

// ---------------------------------------------------------------- ECharts wrapper
export function EChart({ option, height = 260, onClick }: { option: any; height?: number; onClick?: (p: any) => void }) {
  const ref = useRef<HTMLDivElement>(null)
  const chart = useRef<echarts.ECharts | null>(null)
  const theme = useStore(s => s.theme)
  useEffect(() => {
    if (!ref.current) return
    chart.current = echarts.init(ref.current, undefined, { renderer: 'canvas' })
    const ro = new ResizeObserver(() => chart.current?.resize())
    ro.observe(ref.current)
    return () => { ro.disconnect(); chart.current?.dispose() }
  }, [])
  useEffect(() => {
    const t = tokens()
    const base = {
      backgroundColor: 'transparent',
      textStyle: { fontFamily: 'system-ui, -apple-system, Segoe UI, sans-serif', color: t.text2 },
      color: [1, 2, 3, 4, 5, 6, 7, 8].map(k => cssVar(`--s${k}`)),
      tooltip: { backgroundColor: t.surface, borderColor: t.axis, textStyle: { color: t.text, fontSize: 12 } },
      animationDuration: 300,
    }
    chart.current?.setOption({ ...base, ...option }, true)
  }, [option, theme])
  useEffect(() => {
    if (!chart.current) return
    chart.current.off('click')
    if (onClick) chart.current.on('click', onClick)
  }, [onClick])
  return <div ref={ref} style={{ height, width: '100%' }} />
}

export function axisStyle() {
  const t = tokens()
  return {
    axisLine: { lineStyle: { color: t.axis } }, axisTick: { show: false },
    axisLabel: { color: t.muted, fontSize: 11 }, splitLine: { lineStyle: { color: t.grid } },
    nameTextStyle: { color: t.muted, fontSize: 11 },
  }
}

// ---------------------------------------------------------------- small pieces
export function Evidence({ level }: { level?: string }) {
  if (!level) return null
  return <span className={`ev ${level}`} title={useStore.getState().registry?.evidence_levels?.[level] ?? level}><i />{level}</span>
}

export function Tile({ label, value, delta, deltaGood, hint }: { label: string; value: ReactNode; delta?: string; deltaGood?: boolean | null; hint?: string }) {
  return (
    <div className="card tile" title={hint}>
      <div className="label">{label}</div>
      <div className="value tabular">{value}</div>
      {delta && <div className={`delta ${deltaGood === true ? 'up' : deltaGood === false ? 'down' : ''}`}>{delta}</div>}
    </div>
  )
}

export function PersonLink({ id, name }: { id: number; name?: string }) {
  const setRoute = useStore(s => s.setRoute)
  return <a href={`#/person/${id}`} onClick={e => { e.preventDefault(); setRoute(['person', String(id)]) }}>{name ?? `#${id}`}</a>
}

export function Loading({ what = 'Loading' }: { what?: string }) { return <div className="empty">{what}…</div> }

export function VarPicker({ value, onChange, filter, placeholder = 'Choose a variable', allowEmpty = false }:
  { value: string; onChange: (v: string) => void; filter?: (v: VarSpec) => boolean; placeholder?: string; allowEmpty?: boolean }) {
  const reg = useStore(s => s.registry)
  const groups = useMemo(() => {
    const g: Record<string, VarSpec[]> = {}
    if (!reg) return g
    for (const v of Object.values(reg.variables)) {
      if (v.entity !== 'person' || v.dtype === 'str') continue
      if (filter && !filter(v)) continue
      if (!v.flags?.length) continue
      ;(g[v.domain] ??= []).push(v)
    }
    for (const k of Object.keys(g)) g[k].sort((a, b) => a.label.localeCompare(b.label))
    return g
  }, [reg, filter])
  return (
    <select value={value} onChange={e => onChange(e.target.value)} style={{ maxWidth: 260 }}>
      {(allowEmpty || !value) && <option value="">{placeholder}</option>}
      {Object.entries(groups).sort().map(([d, vs]) => (
        <optgroup key={d} label={DOMAIN_LABEL[d] ?? d}>
          {vs.map(v => <option key={v.id} value={v.id}>{v.label}</option>)}
        </optgroup>
      ))}
    </select>
  )
}

export const DOMAIN_LABEL: Record<string, string> = {
  demographics: 'Demographics & background', personality: 'Personality', religion: 'Religion & faith',
  values_sexuality: 'Values, sexuality & intimacy', dating: 'Dating & relationships', social_emotion: 'Social life & wellbeing',
  habits_interests: 'Habits & interests', academics_work: 'School, work, money & place', preferences_dates: 'Date preferences',
}

// ---------------------------------------------------------------- cohort builder
const OPS_NUM = [['between', 'between'], ['ge', '≥'], ['le', '≤'], ['gt', '>'], ['lt', '<'], ['quantile_ge', 'top % (quantile ≥)'], ['quantile_le', 'bottom % (quantile ≤)']]

export function condLabel(c: Cond, reg: any): string {
  if (c.label) return c.label
  if (c.recent_event) return `${reg?.events?.[c.recent_event]?.label ?? c.recent_event} (last ${c.days ?? 90}d)`
  if (c.transition) {
    const t = c.transition
    const nm = reg?.variables?.[t.var]?.label ?? t.var
    const f = (x?: string[]) => (x?.length ? x.map(s => s.replace(/_/g, ' ')).join('/') : 'anything')
    return `${nm}: ${f(t.from)} → ${f(t.to)}`
  }
  if (c.household) return `co-residents ${c.share ?? '≥'} ${Math.round(100 * (c.value ?? 0.5))}% ${condLabel(c.household, reg)}`
  const spec = reg?.variables?.[c.var!]
  const name = spec?.label ?? c.var
  const v = Array.isArray(c.value) ? (c.op === 'between' ? `${fmt(c.value[0])}–${fmt(c.value[1])}` : c.value.map((x: any) => String(x).replace(/_/g, ' ')).join(' or ')) : String(c.value).replace(/_/g, ' ')
  const op = { eq: '=', ne: '≠', in: 'is', notin: 'is not', between: '', ge: '≥', le: '≤', gt: '>', lt: '<', quantile_ge: '≥ quantile', quantile_le: '≤ quantile' }[c.op ?? 'eq'] ?? c.op
  return `${name} ${op} ${v}`
}

export function CohortBar({ n, total }: { n?: number; total?: number }) {
  const { cohort, removeCond, setCohort, registry } = useStore()
  const [adding, setAdding] = useState(false)
  return (
    <div className="cohort-bar">
      <b style={{ fontSize: 13 }}>Cohort</b>
      {cohort.length === 0 && <span className="muted small">everyone present</span>}
      {cohort.map((c, i) => (
        <span key={i} className="cond">{condLabel(c, registry)}<button onClick={() => removeCond(i)} aria-label="remove">×</button></span>
      ))}
      <button className="btn small" onClick={() => setAdding(!adding)}>+ condition</button>
      {cohort.length > 0 && <button className="btn small ghost" onClick={() => setCohort([])}>clear</button>}
      <span className="spacer" />
      {n !== undefined && <span className="pill tabular">{n.toLocaleString()} people{total ? ` · ${(100 * n / total).toFixed(1)}%` : ''}</span>}
      {adding && <CondEditor onDone={() => setAdding(false)} />}
    </div>
  )
}

export const QUICK: { label: string; conds: Cond[] }[] = [
  { label: 'BYU students', conds: [{ var: 'school', op: 'eq', value: 'BYU' }, { var: 'enrolled', op: 'eq', value: true }] },
  { label: 'UVU students', conds: [{ var: 'school', op: 'eq', value: 'UVU' }, { var: 'enrolled', op: 'eq', value: true }] },
  { label: 'Single women 18–23', conds: [{ var: 'sex', op: 'eq', value: 'F' }, { var: 'age', op: 'between', value: [18, 23] }, { var: 'rel_status', op: 'in', value: ['single', 'talking'] }] },
  { label: 'Returned missionaries', conds: [{ var: 'mission_status', op: 'in', value: ['returned', 'early_returned'] }] },
  { label: 'Active LDS', conds: [{ var: 'activity', op: 'eq', value: 'active' }] },
  { label: 'Other faiths or none', conds: [{ var: 'lds_member', op: 'eq', value: false }] },
  { label: 'Married', conds: [{ var: 'rel_status', op: 'eq', value: 'married' }] },
  { label: 'Broken up (90 days)', conds: [{ recent_event: 'breakup_received', days: 90 }] },
  { label: 'Lonely (top 20%)', conds: [{ var: 'loneliness', op: 'quantile_ge', value: 0.8 }] },
  { label: 'Lives with active roommates', conds: [{ household: { var: 'activity', op: 'eq', value: 'active' }, share: '>=', value: 0.75 }] },
  { label: 'In a faith crisis', conds: [{ var: 'faith_crisis', op: 'eq', value: true }] },
]

function CondEditor({ onDone }: { onDone: () => void }) {
  const { registry, addCond, cohort, setCohort } = useStore()
  const [mode, setMode] = useState<'var' | 'event' | 'quick'>('quick')
  const [v, setV] = useState('age')
  const spec = registry?.variables[v]
  const [op, setOp] = useState('between')
  const [val, setVal] = useState<any>([18, 23])
  const [cats, setCats] = useState<string[]>([])
  const [ev, setEv] = useState('breakup_received')
  const [days, setDays] = useState(90)
  useEffect(() => {
    if (!spec) return
    if (spec.dtype === 'cat') { setOp('in'); setCats([]) }
    else if (spec.dtype === 'bool') { setOp('eq'); setVal(true) }
    else { setOp('between'); setVal([spec.range?.[0] ?? 0, spec.range?.[1] ?? 1]) }
  }, [v])
  const add = () => {
    if (mode === 'event') addCond({ recent_event: ev, days })
    else if (spec?.dtype === 'cat') addCond({ var: v, op: 'in', value: cats })
    else if (spec?.dtype === 'bool') addCond({ var: v, op: 'eq', value: val })
    else addCond({ var: v, op, value: op === 'between' ? val.map(Number) : Number(Array.isArray(val) ? val[0] : val) })
    onDone()
  }
  return (
    <div className="card" style={{ width: '100%', marginTop: 6 }}>
      <div className="row" style={{ marginBottom: 8 }}>
        <div className="seg">
          <button className={mode === 'quick' ? 'on' : ''} onClick={() => setMode('quick')}>Quick cohorts</button>
          <button className={mode === 'var' ? 'on' : ''} onClick={() => setMode('var')}>Variable</button>
          <button className={mode === 'event' ? 'on' : ''} onClick={() => setMode('event')}>Recent event</button>
        </div>
        <span className="spacer" />
        <button className="btn small ghost" onClick={onDone}>close</button>
      </div>
      {mode === 'quick' && (
        <div className="row">
          {QUICK.map(q => <button key={q.label} className="btn small" onClick={() => { setCohort([...cohort, ...q.conds]); onDone() }}>{q.label}</button>)}
        </div>
      )}
      {mode === 'var' && spec && (
        <div className="row">
          <VarPicker value={v} onChange={setV} filter={s => !!s.filterable} />
          {spec.dtype === 'cat' && (
            <div className="row">{(spec.categories ?? []).map(c => (
              <label key={c} className="inline small"><input type="checkbox" checked={cats.includes(c)} onChange={e => setCats(e.target.checked ? [...cats, c] : cats.filter(x => x !== c))} />{c.replace(/_/g, ' ')}</label>
            ))}</div>
          )}
          {spec.dtype === 'bool' && (
            <select value={String(val)} onChange={e => setVal(e.target.value === 'true')}><option value="true">yes</option><option value="false">no</option></select>
          )}
          {spec.dtype !== 'cat' && spec.dtype !== 'bool' && (
            <>
              <select value={op} onChange={e => { setOp(e.target.value); if (e.target.value.startsWith('quantile')) setVal([0.8]) }}>
                {OPS_NUM.map(([k, l]) => <option key={k} value={k}>{l}</option>)}
              </select>
              {op === 'between'
                ? <><input type="number" style={{ width: 80 }} value={val[0]} onChange={e => setVal([e.target.value, val[1]])} /> to <input type="number" style={{ width: 80 }} value={val[1]} onChange={e => setVal([val[0], e.target.value])} /></>
                : <input type="number" step="any" style={{ width: 90 }} value={Array.isArray(val) ? val[0] : val} onChange={e => setVal([e.target.value])} />}
              {spec.units && <span className="muted small">{spec.units}</span>}
            </>
          )}
          <button className="btn primary small" onClick={add}>Add</button>
        </div>
      )}
      {mode === 'event' && registry && (
        <div className="row">
          had
          <select value={ev} onChange={e => setEv(e.target.value)}>
            {Object.values(registry.events).sort((a: any, b: any) => a.label.localeCompare(b.label)).map((e: any) => <option key={e.id} value={e.id}>{e.label}</option>)}
          </select>
          in the last <input type="number" value={days} style={{ width: 70 }} onChange={e => setDays(Number(e.target.value))} /> days
          <button className="btn primary small" onClick={add}>Add</button>
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------- additive decomposition bars
export function Decomposition({ rows, scale }: { rows: { label: string; value: number; evidence?: string; title?: string }[]; scale?: number }) {
  const m = scale ?? Math.max(0.05, ...rows.map(r => Math.abs(r.value)))
  return (
    <div className="decomp">
      {rows.map((r, k) => {
        const w = (Math.abs(r.value) / m) * 50
        const left = r.value >= 0 ? 50 : 50 - w
        return [
          <div key={`l${k}`} title={r.title} style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{r.label} {r.evidence && <Evidence level={r.evidence} />}</div>,
          <div key={`b${k}`} className="bar"><span className="zero" /><i style={{ left: `${left}%`, width: `${Math.max(w, 0.5)}%`, background: r.value >= 0 ? 'var(--s8)' : 'var(--s1)' }} /></div>,
          <div key={`v${k}`} className="tabular small" style={{ textAlign: 'right' }}>{r.value >= 0 ? '+' : ''}{r.value.toFixed(3)}</div>,
        ]
      })}
    </div>
  )
}

// ---------------------------------------------------------------- icons
const P = (d: string) => <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d={d} /></svg>
export const Icons: Record<string, JSX.Element> = {
  home: P('M3 11 12 3l9 8M5 10v10h5v-6h4v6h5V10'),
  guide: P('M4 5a2 2 0 0 1 2-2h13v16H6a2 2 0 0 0-2 2zM4 5v16M8 7h7M8 11h5'),
  flows: P('M3 6h5c4 0 4 12 8 12h5M3 18h5c4 0 4-12 8-12h5'),
  overview: P('M3 13h4v8H3zM10 3h4v18h-4zM17 9h4v12h-4z'),
  map: P('M9 4 3 6v14l6-2 6 2 6-2V4l-6 2-6-2zM9 4v14M15 6v14'),
  explore: P('M3 3v18h18M7 15l4-4 3 3 5-6'),
  crosstab: P('M3 3h18v18H3zM3 9h18M3 15h18M9 3v18M15 3v18'),
  people: P('M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM22 21v-2a4 4 0 0 0-3-3.9M16 3.1a4 4 0 0 1 0 7.8'),
  network: P('M5 6a2 2 0 1 0 0-.1M19 6a2 2 0 1 0 0-.1M12 19a2 2 0 1 0 0-.1M6.7 7.2l4.2 9.6M17.3 7.2l-4.2 9.6M7 6h10'),
  causal: P('M4 4h5v4H4zM15 4h5v4h-5zM9.5 16h5v4h-5zM6.5 8v4h11V8M12 12v4'),
  lab: P('M9 3h6M10 3v6L4 20h16L14 9V3'),
  events: P('M12 8v4l3 3M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18z'),
  variables: P('M4 6h16M4 12h10M4 18h7'),
  mechanisms: P('M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z'),
  places: P('M3 21h18M5 21V7l7-4 7 4v14M9 21v-6h6v6'),
  about: P('M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM12 16v-4M12 8h.01'),
}
