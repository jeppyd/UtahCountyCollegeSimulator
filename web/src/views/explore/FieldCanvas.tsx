// One field, every angle: right now, over time, by group, against another field, the people behind
// the numbers, and what drives it — in the Original, the What-if, or both.
import { useEffect, useMemo, useState } from 'react'
import { fmt, groupsOf, histogram, pearson, quantile, regress, summary as stats, useCohortData, values } from '../../analysis'
import { api, Column, STATIC } from '../../api'
import { axisStyle, CohortBar, condLabel, cssVar, Decomposition, EChart, Evidence, tokens, VarPicker } from '../../components'
import { DRAWERS, drawerOf, favg, fdelta, fpair, fval, GROUPS, isCat, pctStr, polarity, pretty, sizeWord, SPLITS } from '../../fields'
import { DeltaChip, G, UBadge, uColor, useAsync } from '../../game'
import { nameOf } from '../../names'
import { Cond, useLens, useStore, VarSpec } from '../../store'

const EMO = ['mood', 'loneliness', 'stress', 'anxiety', 'belonging', 'self_esteem', 'guilt', 'fatigue', 'purpose', 'financial_stress', 'academic_pressure', 'romantic_longing']

export function FieldCanvas({ v, tracked, compareRow, split0 }: { v: string; tracked: { weekly: Set<string>; person: Set<string> }; compareRow?: any; split0?: string }) {
  const { registry, cohort, addCond, togglePin, isPinned, pins, setRoute, status } = useStore()
  const { lens, u, compare, hasAlt } = useLens()
  const spec = registry!.variables[v]
  const [tab, setTab] = useState<'groups' | 'relate' | 'people' | 'drivers'>('groups')
  const [split, setSplit] = useState(split0 ?? (v === 'school' ? 'sex' : 'school'))
  useEffect(() => { if (split === v) setSplit(v === 'school' ? 'sex' : 'school') }, [v])
  const vars = useMemo(() => [...new Set([v, 'sex', split])], [v, split])
  const A = useCohortData(vars, { universe: compare ? 'base' : u })
  // in Compare, the filter picks people in the Original and we follow the same people into the What-if
  const B0 = useCohortData(vars, { universe: 'alt', enabled: compare, ignoreCohort: true })
  const B = useMemo(() => {
    if (!compare || !B0.mask || !A.mask) return B0
    const m = new Uint8Array(B0.mask.length)
    let k = 0
    for (let i = 0; i < m.length; i++) { m[i] = i < A.mask.length ? (A.mask[i] & B0.mask[i]) : 0; k += m[i] }
    return { ...B0, mask: m, n: k }
  }, [B0, A.mask, compare])
  void pins
  if (!spec) return <div className="empty">Unknown field “{v}”.</div>
  const drawer = DRAWERS.find(d => d.id === drawerOf(spec))
  const pinned = isPinned({ kind: 'field', var: v })
  const colA = A.cols[v], colB = compare ? B.cols[v] : undefined
  const kpis = kpiOf(spec, colA, A.mask, colB, B.mask)
  return (
    <div className="fcanvas">
      <div className="fc-head">
        <span className="fc-icon" style={{ ['--sc' as any]: 'var(--s6)' }}>{G[drawer?.icon ?? 'explore']}</span>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div className="eyebrow">{drawer?.label}</div>
          <h1>{spec.label}{spec.units && !isCat(spec) ? <small> · {spec.units}</small> : null}</h1>
          {spec.desc && <p>{spec.desc}</p>}
          <div className="row small" style={{ marginTop: 6 }}>
            <Evidence level={spec.evidence} />
            {tracked.person.has(v) ? <span className="pill" title="Kept for every person every two weeks">{G.clock} per-person history</span> : tracked.weekly.has(v) ? <span className="pill" title="Group averages recorded weekly">{G.clock} weekly averages</span> : null}
            <span className="pill">{spec.update === 'static' ? 'fixed trait' : `updates ${spec.update}`}</span>
            <button className="linkish small" onClick={() => setRoute(['variables', v])}>definition & sources</button>
          </div>
        </div>
        <button className={`btn ${pinned ? 'following' : ''}`} onClick={() => togglePin({ kind: 'field', var: v })} title="Pin to your board on the World page">{G.pin} {pinned ? 'Pinned' : 'Pin'}</button>
      </div>

      <CohortBar n={A.n} />
      {compare && cohort.length > 0 && <p className="small muted" style={{ margin: '-8px 0 12px' }}>Compare follows the same people: your filter picks them in the Original world, and the What-if shows those same people's lives.</p>}

      <div className="kpis" style={{ marginBottom: 12 }}>
        {kpis.map(k => <div key={k.label} className="kpi" title={k.title}><span className="k-label">{k.u && <UBadge u={k.u} />} {k.label}</span><span className="k-val tabular">{k.value}</span>{k.sub && <span className="k-sub">{k.sub}</span>}</div>)}
        {compare && compareRow && (
          <div className="kpi" title="Standardized difference (Cohen's d for numbers, h for shares) and share of people whose own value differs">
            <span className="k-label">{G.butterfly} Butterfly effect</span>
            <span className="k-val">{sizeWord(compareRow.effect) === 'no real change' ? 'average holds' : `${sizeWord(compareRow.effect)} shift`}</span>
            <span className="k-sub">{compareRow.changed_share > 0.001 ? `${sizeWord(compareRow.effect) === 'no real change' ? 'yet' : 'and'} ${(100 * compareRow.changed_share).toFixed(1)}% of people are individually different` : 'and individuals match too'} · everyone, size {compareRow.effect >= 0 ? '+' : ''}{compareRow.effect.toFixed(3)}</span>
          </div>
        )}
      </div>

      <div className="grid g2">
        <div className="card">
          <div className="card-head"><div><h3>Right now</h3><p className="hint">{isCat(spec) ? 'Share of people in each category. Click a bar to filter to those people.' : 'How many people have each value. Click a bar to filter to them.'}</p></div>{!compare && hasAlt && <UBadge u={u} />}</div>
          <NowChart spec={spec} A={A} B={compare ? B : null} u={u} onPick={c => addCond(c)} />
        </div>
        <div className="card">
          <OverTime spec={spec} v={v} tracked={tracked} />
        </div>
      </div>

      {compare && <ButterflyPanel spec={spec} A={A} B={B} />}

      <div className="tabs" style={{ marginTop: 16 }}>
        <button className={tab === 'groups' ? 'on' : ''} onClick={() => setTab('groups')}>{G.people} Compare groups</button>
        <button className={tab === 'relate' ? 'on' : ''} onClick={() => setTab('relate')}>{G.explore} Relate to another field</button>
        <button className={tab === 'people' ? 'on' : ''} onClick={() => setTab('people')}>{G.id} The people behind it</button>
        <button className={tab === 'drivers' ? 'on' : ''} onClick={() => setTab('drivers')}>{G.link} What drives it</button>
      </div>
      <div className="card tabcard">
        {tab === 'groups' && <Groups spec={spec} split={split} setSplit={setSplit} A={A} B={compare ? B : null} onPick={c => addCond(c)} />}
        {tab === 'relate' && <Relate spec={spec} />}
        {tab === 'people' && <PeopleBehind spec={spec} A={A} B={compare ? B : null} />}
        {tab === 'drivers' && <Drivers v={v} />}
      </div>
      {cohort.length > 0 && !STATIC && EMO.includes(v) && <WhyGroup v={v} />}
      {status && lens && null}
    </div>
  )
}

// ------------------------------------------------------------------ KPIs
function kpiOf(spec: VarSpec, a?: Column, ma?: Uint8Array | null, b?: Column, mb?: Uint8Array | null) {
  const out: { label: string; value: string; sub?: string; u?: 'base' | 'alt'; title?: string }[] = []
  if (!a || !ma) return out
  if (isCat(spec)) {
    const sh = shares(spec, a, ma)
    const top = sh.map((s, k) => [s, k]).sort((x, y) => y[0] - x[0])
    const labs = catLabels(spec, a)
    out.push({ label: 'Most common', value: pretty(labs[top[0]?.[1]] ?? '—'), sub: `${pctStr(top[0]?.[0] ?? NaN)} of people`, u: b ? 'base' : undefined })
    if (top[1]) out.push({ label: 'Next', value: pretty(labs[top[1][1]]), sub: pctStr(top[1][0]) })
    if (b && mb) {
      const shb = shares(spec, b, mb)
      let j = 0
      shb.forEach((s, k) => { if (Math.abs(s - sh[k]) > Math.abs(shb[j] - sh[j])) j = k })
      out.push({ label: `${pretty(labs[j])} in What-if`, value: pctStr(shb[j]), sub: `${fdelta(spec, shb[j] - sh[j], true)} vs Original`, u: 'alt' })
    }
    out.push({ label: 'People', value: count(ma).toLocaleString() })
    return out
  }
  const va = values(a, ma)
  const s = stats(va)
  const sbm = b && mb ? stats(values(b, mb)).mean : null
  const [avA, avB] = sbm !== null ? fpair(spec, s.mean, sbm) : [favg(spec, s.mean), '']
  out.push({ label: 'Average', value: avA, sub: `typical ${fval(spec, s.median)}`, u: b ? 'base' : undefined })
  out.push({ label: 'Middle half', value: `${fval(spec, s.q1)} – ${fval(spec, s.q3)}`, sub: `range ${fval(spec, s.min)} to ${fval(spec, s.max)}` })
  if (b && mb) {
    out.push({ label: 'Average', value: avB, sub: `${fdelta(spec, (sbm as number) - s.mean)} vs Original`, u: 'alt' })
  }
  out.push({ label: 'People', value: s.n.toLocaleString() })
  return out
}
const count = (m: Uint8Array) => { let k = 0; for (let i = 0; i < m.length; i++) k += m[i]; return k }
function catLabels(spec: VarSpec, c: Column) { return spec.dtype === 'bool' ? ['no', 'yes'] : (c.categories ?? spec.categories ?? []) }
function shares(spec: VarSpec, c: Column, m: Uint8Array) {
  const labs = catLabels(spec, c)
  const cnt = new Array(labs.length).fill(0)
  let t = 0
  for (let i = 0; i < c.data.length; i++) if (m[i]) { const k = c.data[i]; if (k < cnt.length) { cnt[k]++; t++ } }
  return cnt.map(x => (t ? x / t : 0))
}

// ------------------------------------------------------------------ now
function NowChart({ spec, A, B, u, onPick }: { spec: VarSpec; A: any; B: any | null; u: 'base' | 'alt'; onPick: (c: Cond) => void }) {
  const opt = useMemo(() => {
    const a: Column = A.cols[spec.id]
    if (!a || !A.mask) return null
    const ax = axisStyle(), t = tokens()
    const cA = uColor(B ? 'base' : u), cB = uColor('alt')
    if (isCat(spec)) {
      const labs = catLabels(spec, a).map(pretty)
      const sa = shares(spec, a, A.mask)
      const sb = B?.cols[spec.id] && B.mask ? shares(spec, B.cols[spec.id], B.mask) : null
      const order = labs.map((_, k) => k).filter(k => sa[k] > 0 || (sb && sb[k] > 0)).sort((x, y) => (sb ? Math.max(sb[y], sa[y]) - Math.max(sb[x], sa[x]) : sa[y] - sa[x])).slice(0, 14)
      return {
        option: {
          grid: { left: 8, right: 46, top: sb ? 26 : 6, bottom: 4, containLabel: true },
          legend: sb ? { top: 0, textStyle: { color: t.text2 }, data: ['Original', 'What-if'] } : undefined,
          tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' }, valueFormatter: (x: number) => pctStr(x) },
          xAxis: { type: 'value', show: false, max: (m: any) => m.max * 1.12 },
          yAxis: { type: 'category', inverse: true, data: order.map(k => labs[k]), ...ax, axisLine: { show: false } },
          series: [
            { name: sb ? 'Original' : 'Share', type: 'bar', barMaxWidth: 14, barGap: '20%', data: order.map(k => sa[k]), itemStyle: { color: cA, borderRadius: [0, 4, 4, 0] }, label: { show: !sb, position: 'right', color: t.text2, fontSize: 11, formatter: (p: any) => pctStr(p.value, 0) } },
            ...(sb ? [{ name: 'What-if', type: 'bar', barMaxWidth: 14, data: order.map(k => sb[k]), itemStyle: { color: cB, borderRadius: [0, 4, 4, 0] } }] : []),
          ],
        },
        height: Math.max(150, 30 + order.length * (sb ? 30 : 22)),
        click: (p: any) => { const k = order[p.dataIndex]; onPick(spec.dtype === 'bool' ? { var: spec.id, op: 'eq', value: k === 1 } : { var: spec.id, op: 'eq', value: (a.categories ?? spec.categories!)[k] }) },
      }
    }
    const va = values(a, A.mask)
    const vb = B?.cols[spec.id] && B.mask ? values(B.cols[spec.id], B.mask) : null
    if (!va.length) return null
    const s = [...va, ...(vb ?? [])].sort((x, y) => x - y)
    let lo = quantile(s, 0.005), hi = quantile(s, 0.995)
    if (lo === hi) { lo = s[0]; hi = s[s.length - 1] }
    const h = histogram(va, 28, [lo, hi])
    const hb = vb ? histogram(vb, h.counts.length, [lo, hi]) : null
    const labs = h.edges.slice(0, -1).map((e, k) => (h.ints ? String(Math.round(e)) : `${fmt(e)}–${fmt(h.edges[k + 1])}`))
    const mA = stats(va).mean
    const avgTxt = favg(spec, mA)
    return {
      option: {
        grid: { left: 8, right: 12, top: hb ? 26 : 22, bottom: 4, containLabel: true },
        legend: hb ? { top: 0, textStyle: { color: t.text2 }, data: ['Original', 'What-if'] } : undefined,
        tooltip: { trigger: 'axis', valueFormatter: (x: number) => pctStr(x) },
        xAxis: { type: 'category', data: labs, ...ax, axisLabel: { ...ax.axisLabel, hideOverlap: true } },
        yAxis: { type: 'value', ...ax, axisLabel: { ...ax.axisLabel, formatter: (x: number) => `${Math.round(100 * x)}%` } },
        series: [
          { name: hb ? 'Original' : 'People', type: 'bar', barCategoryGap: '10%', data: h.counts.map(c => c / va.length), itemStyle: { color: cA, borderRadius: [3, 3, 0, 0], opacity: hb ? 0.85 : 1 },
            markLine: hb ? undefined : { symbol: 'none', silent: true, label: { formatter: `avg ${avgTxt}`, color: t.text2, fontSize: 10 }, lineStyle: { color: t.text2, type: 'dashed' }, data: [{ xAxis: Math.min(labs.length - 1, Math.max(0, Math.floor((mA - lo) / ((hi - lo) || 1) * labs.length))) }] } },
          ...(hb && vb ? [{ name: 'What-if', type: 'line', step: 'middle', showSymbol: false, lineStyle: { width: 2.5, color: cB }, itemStyle: { color: cB }, data: hb.counts.map(c => c / vb.length) }] : []),
        ],
      },
      height: 240,
      click: (p: any) => onPick({ var: spec.id, op: 'between', value: [h.edges[p.dataIndex], h.edges[p.dataIndex + 1]] }),
    }
  }, [A, B, spec.id, u])
  if (A.loading && !opt) return <div className="empty small">Loading…</div>
  if (!opt) return <div className="empty small">No one in this group has a value.</div>
  return <EChart option={opt.option} height={opt.height} onClick={opt.click} />
}

// ------------------------------------------------------------------ over time
function OverTime({ spec, v, tracked }: { spec: VarSpec; v: string; tracked: { weekly: Set<string>; person: Set<string> } }) {
  const { cohort, dataVersion, status, registry } = useStore()
  const { u, compare } = useLens()
  const [group, setGroup] = useState('all')
  const [cat, setCat] = useState<string>('')
  const useCohort = cohort.length > 0 && tracked.person.has(v) && !STATIC
  const tl = useAsync(() => api.fieldTimeline(v, group), [v, group, dataVersion])
  const ct = useAsync(() => useCohort ? Promise.all([api.cohortTimeline({ filter: { and: cohort }, vars: [v], u: compare ? 'base' : u }), compare ? api.cohortTimeline({ filter: { and: cohort }, vars: [v], u: 'alt', filter_world: 'base' }) : Promise.resolve(null)]) : Promise.resolve(null), [v, JSON.stringify(cohort), u, compare, dataVersion, useCohort])
  const cats = isCat(spec) ? (spec.dtype === 'bool' ? ['true'] : spec.categories ?? []) : []
  useEffect(() => { setCat('') }, [v])
  const start = useMemo(() => { const d = new Date(status.date + 'T12:00:00'); d.setDate(d.getDate() - status.day); return d }, [status.date, status.day])
  const toDate = (day: number) => { const d = new Date(start); d.setDate(d.getDate() + day); return d.toISOString().slice(0, 10) }
  const opt = useMemo(() => {
    const ax = axisStyle(), t = tokens()
    const fork = status.fork_day
    const mk = (fork !== null && fork !== undefined && status.has_alt) ? { symbol: 'none', silent: true, lineStyle: { color: t.muted, type: 'dashed' }, label: { formatter: 'split', color: t.muted, fontSize: 10 }, data: [{ xAxis: toDate(fork) }] } : undefined
    const yFmt = (x: number) => (spec.dtype === 'cat' || spec.dtype === 'bool' ? `${Math.round(100 * x)}%` : Math.abs(x) >= 1000 ? Math.round(x).toLocaleString() : Number(x.toPrecision(3)).toString())
    const base = { grid: { left: 8, right: 12, top: 30, bottom: 4, containLabel: true }, tooltip: { trigger: 'axis', valueFormatter: (x: number) => (x === null || x === undefined ? '—' : isCat(spec) ? pctStr(x) : favg(spec, x, 3)) },
      xAxis: { type: 'time', ...ax, splitLine: { show: false } }, yAxis: { type: 'value', scale: true, ...ax, axisLabel: { ...ax.axisLabel, formatter: yFmt } }, legend: { top: 0, textStyle: { color: t.text2, fontSize: 11 } } }
    // a group of my own (per-person history)
    if (useCohort && ct.data) {
      const [ca, cb] = ct.data as any[]
      const sel = (d: any, who: 'cohort' | 'everyone') => (d?.[who]?.[v] ?? []).map((x: any) => (x === null ? null : isCat(spec) ? x[catKey(spec, cat, d)] ?? null : x))
      const series: any[] = [
        { name: compare ? 'Your group · Original' : 'Your group', type: 'line', showSymbol: false, lineStyle: { width: 2.5, color: uColor(compare ? 'base' : u) }, itemStyle: { color: uColor(compare ? 'base' : u) }, data: ca.days.map((d: number, k: number) => [toDate(d), sel(ca, 'cohort')[k]]), markLine: mk },
        { name: 'Everyone', type: 'line', showSymbol: false, lineStyle: { width: 1.5, type: 'dashed', color: t.muted }, itemStyle: { color: t.muted }, data: ca.days.map((d: number, k: number) => [toDate(d), sel(ca, 'everyone')[k]]) },
      ]
      if (cb) series.push({ name: 'Your group · What-if', type: 'line', showSymbol: false, lineStyle: { width: 2.5, color: uColor('alt') }, itemStyle: { color: uColor('alt') }, data: cb.days.map((d: number, k: number) => [toDate(d), sel(cb, 'cohort')[k]]) })
      return { ...base, series }
    }
    const d = tl.data as any
    if (!d?.base) return null
    const pick = (x: any) => (x ?? null)
    const line = (src: any, uu: 'base' | 'alt', name: string) => {
      if (!src) return null
      if (isCat(spec)) {
        const key = spec.dtype === 'bool' ? null : (cat || topCat(src))
        const ys = spec.dtype === 'bool' ? src.mean : src.shares?.[key!]
        const dd = src.daily_days && (spec.dtype === 'bool' ? src.daily_mean : src.daily_shares?.[key!])
        const days = dd ? src.daily_days : src.days
        const vals = dd ?? ys ?? []
        return { name, type: 'line', showSymbol: false, lineStyle: { width: 2.5, color: uColor(uu) }, itemStyle: { color: uColor(uu) }, data: days.map((x: number, k: number) => [toDate(x), pick(vals[k])]) }
      }
      const days = src.daily_days ?? src.days
      const vals = src.daily_mean ?? src.mean
      return { name, type: 'line', showSymbol: false, lineStyle: { width: 2.5, color: uColor(uu) }, itemStyle: { color: uColor(uu) }, data: days.map((x: number, k: number) => [toDate(x), pick(vals[k])]) }
    }
    const series: any[] = []
    // middle-half band for everyone (numbers only)
    if (!isCat(spec) && group === 'all' && d.base.pct && !compare) {
      const P = d[u]?.pct ?? d.base.pct
      const days = d[u]?.days ?? d.base.days
      series.push({ name: 'p25', type: 'line', stack: 'band', symbol: 'none', lineStyle: { opacity: 0 }, itemStyle: { color: uColor(u) }, data: days.map((x: number, k: number) => [toDate(x), P[k]?.[1] ?? null]), tooltip: { show: false } })
      series.push({ name: 'Middle half', type: 'line', stack: 'band', symbol: 'none', lineStyle: { opacity: 0 }, itemStyle: { color: uColor(u), opacity: 0.35 }, areaStyle: { color: uColor(u), opacity: 0.13 }, data: days.map((x: number, k: number) => [toDate(x), P[k] ? P[k][3] - P[k][1] : null]), tooltip: { show: false } })
    }
    if (compare) {
      const a = line(d.base, 'base', 'Original'); if (a) { (a as any).markLine = mk; series.push(a) }
      const b = line(d.alt, 'alt', 'What-if'); if (b) series.push(b)
    } else {
      const a = line(d[u] ?? d.base, u, isCat(spec) ? 'Share' : 'Average'); if (a) { (a as any).markLine = mk; series.push(a) }
    }
    return { ...base, legend: { ...base.legend, data: series.map(s => s.name).filter(n => n !== 'p25') }, series }
  }, [tl.data, ct.data, compare, u, cat, group, spec.id, useCohort])
  const catOpts = isCat(spec) && spec.dtype === 'cat' ? cats : []
  return (
    <>
      <div className="card-head">
        <div><h3>Over time</h3><p className="hint">{useCohort ? `Your group (people who match the filter today) every two weeks, vs everyone.` : cohort.length && !tracked.person.has(v) ? `${registry!.variables[v]?.label} isn't kept per person, so this shows standard groups, not your filter.` : isCat(spec) ? 'Share of people over time.' : group === 'all' && !compare ? 'Average, with the middle half of people shaded.' : 'Average over time.'}</p></div>
        {catOpts.length > 0 && <select value={cat || topCat((tl.data as any)?.base) || ''} onChange={e => setCat(e.target.value)} aria-label="Category">{catOpts.map(c => <option key={c} value={c}>{pretty(c)}</option>)}</select>}
      </div>
      {!useCohort && <div className="row" style={{ marginBottom: 6, gap: 4 }}>{GROUPS.map(([g, l]) => <button key={g} className={`chip ${group === g ? 'on' : ''}`} onClick={() => setGroup(g)}>{l}</button>)}</div>}
      {tl.error && !useCohort ? <div className="empty small">{tl.error.includes('404') ? 'Not recorded over time yet.' : tl.error}</div>
        : opt ? <EChart option={opt} height={useCohort ? 262 : 232} /> : <div className="empty small">Loading…</div>}
    </>
  )
}
function topCat(src: any) {
  if (!src?.shares) return ''
  let best = '', bv = -1
  for (const [k, arr] of Object.entries(src.shares) as any) { const x = arr[arr.length - 1] ?? 0; if (x > bv) { bv = x; best = k } }
  return best
}
function catKey(spec: VarSpec, cat: string, d: any) {
  if (spec.dtype === 'bool') return 'yes'
  if (cat) return cat
  const last = (d?.everyone?.[spec.id] ?? []).filter((x: any) => x).pop() ?? {}
  return Object.entries(last).sort((a: any, b: any) => b[1] - a[1])[0]?.[0] ?? ''
}

// ------------------------------------------------------------------ the butterfly, person by person
function ButterflyPanel({ spec, A, B }: { spec: VarSpec; A: any; B: any }) {
  const setRoute = useStore(s => s.setRoute)
  const res = useMemo(() => {
    const a: Column = A.cols[spec.id], b: Column = B.cols[spec.id]
    if (!a || !b || !A.mask || !B.mask) return null
    const n = Math.min(a.data.length, b.data.length)
    const sex = A.cols.sex?.data
    if (isCat(spec)) {
      const labs = catLabels(spec, a)
      const flows = new Map<string, number>()
      const ex: number[] = []
      let changed = 0, both = 0
      for (let i = 0; i < n; i++) {
        if (!A.mask[i] || !B.mask[i]) continue
        both++
        if (a.data[i] !== b.data[i]) { changed++; const k = `${labs[a.data[i]]} → ${labs[b.data[i]]}`; flows.set(k, (flows.get(k) ?? 0) + 1); if (ex.length < 400) ex.push(i) }
      }
      return { kind: 'cat' as const, both, changed, flows: [...flows.entries()].sort((x, y) => y[1] - x[1]).slice(0, 8), ex: ex.slice(0, 10).map(i => ({ i, name: sex ? nameOf(i, sex[i]) : `#${i}`, from: pretty(labs[a.data[i]]), to: pretty(labs[b.data[i]]) })) }
    }
    const d: { i: number; d: number }[] = []
    let both = 0
    for (let i = 0; i < n; i++) {
      if (!A.mask[i] || !B.mask[i]) continue
      const x = (b.data[i] as number) - (a.data[i] as number)
      if (!Number.isFinite(x)) continue
      both++
      if (Math.abs(x) > 1e-6) d.push({ i, d: x })
    }
    const s = d.map(x => x.d).sort((x, y) => x - y)
    const up = d.filter(x => x.d > 0).length, down = d.length - up
    d.sort((x, y) => Math.abs(y.d) - Math.abs(x.d))
    return { kind: 'num' as const, both, changed: d.length, up, down, p10: quantile(s, 0.1), p90: quantile(s, 0.9), top: d.slice(0, 8).map(x => ({ ...x, name: sex ? nameOf(x.i, sex[x.i]) : `#${x.i}`, a: a.data[x.i] as number, b: b.data[x.i] as number })) }
  }, [A, B, spec.id])
  if (!res) return null
  return (
    <div className="card butterfly-card" style={{ marginTop: 14 }}>
      <div className="card-head"><div><h3>{G.butterfly} The butterfly, person by person</h3><p className="hint">Same people in both worlds. Averages can hide it: here is how many individual lives moved, and which way.</p></div></div>
      {res.changed === 0 ? <div className="small muted">Nobody's {spec.label.toLowerCase()} differs between the worlds (yet).</div> : res.kind === 'cat' ? (
        <div className="grid g2">
          <div>
            <div className="bf-big"><b className="tabular">{res.changed.toLocaleString()}</b> people ({pctStr(res.changed / (res.both || 1))}) are in a different category in the What-if world.</div>
            {res.flows.map(([k, c]) => <div key={k} className="row small bf-flow"><span style={{ flex: 1 }}>{pretty(k)}</span><b className="tabular">{c.toLocaleString()}</b></div>)}
          </div>
          <div>
            <div className="small muted" style={{ marginBottom: 4 }}>For example</div>
            {res.ex.map(x => <div key={x.i} className="row small bf-flow"><button className="linkish" onClick={() => setRoute(['person', String(x.i), 'other'])}>{x.name}</button><span className="spacer" /><span><span className="u-base-t">{x.from}</span> → <span className="u-alt-t">{x.to}</span></span></div>)}
          </div>
        </div>
      ) : (
        <div className="grid g2">
          <div>
            <div className="bf-big"><b className="tabular">{res.changed.toLocaleString()}</b> people ({pctStr(res.changed / (res.both || 1))}) have a different {spec.label.toLowerCase()}: <b className="tabular">{res.up.toLocaleString()}</b> higher, <b className="tabular">{res.down.toLocaleString()}</b> lower.</div>
            <div className="small secondary">Most changes fall between {fdelta(spec, res.p10)} and {fdelta(spec, res.p90)}.</div>
          </div>
          <div>
            <div className="small muted" style={{ marginBottom: 4 }}>Biggest individual changes</div>
            {res.top.map(x => <div key={x.i} className="row small bf-flow"><button className="linkish" onClick={() => setRoute(['person', String(x.i), 'other'])}>{x.name}</button><span className="spacer" /><span className="tabular"><span className="u-base-t">{fval(spec, x.a)}</span> → <span className="u-alt-t">{fval(spec, x.b)}</span></span></div>)}
          </div>
        </div>
      )}
    </div>
  )
}

// ------------------------------------------------------------------ groups
function Groups({ spec, split, setSplit, A, B, onPick }: { spec: VarSpec; split: string; setSplit: (s: string) => void; A: any; B: any | null; onPick: (c: Cond) => void }) {
  const reg = useStore(s => s.registry)!
  const { u } = useLens()
  const sg = reg.variables[split]
  const opt = useMemo(() => {
    const x: Column = A.cols[spec.id], g: Column = A.cols[split]
    if (!x || !g || !A.mask || !sg) return null
    const ax = axisStyle(), t = tokens()
    const G1 = groupsOf(sg, g, A.mask, 6)
    const xb: Column | undefined = B?.cols[spec.id], gb: Column | undefined = B?.cols[split]
    const G2 = B && gb && B.mask ? groupsOf(sg, gb, B.mask, 6) : null
    const idx = G1.labels.map((_, k) => k)
    if (isCat(spec)) {
      const labs = catLabels(spec, x)
      const shareBy = (col: Column, gg: typeof G1, m: Uint8Array) => idx.map(k => { const c = new Array(labs.length).fill(0); let tt = 0; for (let i = 0; i < col.data.length; i++) if (m[i] && gg.code[i] === k) { c[col.data[i]]++; tt++ } return { n: tt, s: c.map(v => (tt ? v / tt : 0)) } })
      const SA = shareBy(x, G1, A.mask)
      const keep = idx.filter(k => SA[k].n >= 5)
      if (G2 && xb) {
        const SB = shareBy(xb, G2, B.mask)
        const tot = labs.map((_, c) => keep.reduce((s, k) => s + Math.abs(SB[k].s[c] - SA[k].s[c]), 0))
        const c = spec.dtype === 'bool' ? 1 : tot.indexOf(Math.max(...tot))
        return { opt: { grid: { left: 8, right: 16, top: 26, bottom: 4, containLabel: true }, legend: { top: 0, textStyle: { color: t.text2 } }, tooltip: { trigger: 'axis', valueFormatter: (v: number) => pctStr(v) },
          xAxis: { type: 'category', data: keep.map(k => G1.labels[k]), ...ax }, yAxis: { type: 'value', ...ax, axisLabel: { ...ax.axisLabel, formatter: (v: number) => `${Math.round(100 * v)}%` } },
          series: [{ name: `${pretty(labs[c])} · Original`, type: 'bar', barMaxWidth: 26, data: keep.map(k => SA[k].s[c]), itemStyle: { color: uColor('base'), borderRadius: [4, 4, 0, 0] } },
            { name: `${pretty(labs[c])} · What-if`, type: 'bar', barMaxWidth: 26, data: keep.map(k => SB[k].s[c]), itemStyle: { color: uColor('alt'), borderRadius: [4, 4, 0, 0] } }] }, keep, note: `Share "${pretty(labs[c])}" (the category that moved most) in each group.` }
      }
      const order = labs.map((_, c) => c).filter(c => keep.some(k => SA[k].s[c] > 0.005)).slice(0, 8)
      return { opt: { grid: { left: 8, right: 16, top: 26, bottom: 4, containLabel: true }, legend: { top: 0, type: 'scroll', textStyle: { color: t.text2 } }, tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' }, valueFormatter: (v: number) => pctStr(v) },
        yAxis: { type: 'category', inverse: true, data: keep.map(k => `${G1.labels[k]} (${SA[k].n.toLocaleString()})`), ...ax }, xAxis: { type: 'value', max: 1, ...ax, axisLabel: { ...ax.axisLabel, formatter: (v: number) => `${Math.round(100 * v)}%` } },
        series: order.map((c, j) => ({ name: pretty(labs[c]), type: 'bar', stack: 's', barMaxWidth: 22, data: keep.map(k => SA[k].s[c]), itemStyle: { color: cssVar(`--s${(j % 8) + 1}`) } })) }, keep, note: 'Each bar is one group, split into categories (100%).', height: 60 + keep.length * 34 }
    }
    const meanBy = (col: Column, gg: typeof G1, m: Uint8Array) => idx.map(k => { const vv: number[] = []; for (let i = 0; i < col.data.length; i++) if (m[i] && gg.code[i] === k && !Number.isNaN(col.data[i])) vv.push(col.data[i] as number); const s = stats(vv); return { n: vv.length, m: s.mean, se: s.sd / Math.sqrt(Math.max(vv.length, 1)) } })
    const MA = meanBy(x, G1, A.mask)
    const keep = idx.filter(k => MA[k].n >= 3)
    const MB = G2 && xb ? meanBy(xb, G2, B.mask) : null
    // a dot plot: honest on a zoomed axis, unlike bars that don't start at zero
    const whisk = (rows: typeof MA, off: number, color: string) => ({ type: 'custom', silent: true, z: 5, data: keep.map((k, j) => [j, rows[k].m]), renderItem: (_p: any, api: any) => { const j = api.value(0), r = rows[keep[j]]; const a = api.coord([j, r.m + 1.96 * r.se]), b = api.coord([j, r.m - 1.96 * r.se]); const xx = a[0] + off * 9; return { type: 'line', shape: { x1: xx, y1: a[1], x2: xx, y2: b[1] }, style: { stroke: color, lineWidth: 2, opacity: 0.6 } } } })
    const cA = uColor(MB ? 'base' : u), cB = uColor('alt')
    const series: any[] = [{ name: MB ? 'Original' : 'Average', type: 'scatter', symbolSize: 13, symbolOffset: [MB ? -9 : 0, 0], z: 10, data: keep.map(k => MA[k].m), itemStyle: { color: cA, borderColor: t.text === '#ffffff' ? '#1a1a19' : '#fff', borderWidth: 1.5 } }, whisk(MA, MB ? -1 : 0, cA)]
    if (MB) series.push({ name: 'What-if', type: 'scatter', symbolSize: 13, symbolOffset: [9, 0], z: 10, data: keep.map(k => MB[k].m), itemStyle: { color: cB, borderColor: '#fff', borderWidth: 1.5 } }, whisk(MB, 1, cB))
    return { opt: { grid: { left: 8, right: 16, top: MB ? 26 : 10, bottom: 4, containLabel: true }, legend: MB ? { top: 0, data: ['Original', 'What-if'], textStyle: { color: t.text2 } } : undefined,
      tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' }, formatter: (ps: any) => { const k = keep[ps[0].dataIndex]; return `<b>${G1.labels[k]}</b><br/>average ${favg(spec, MA[k].m, 3)} ± ${fmt(1.96 * MA[k].se, 3)} (n=${MA[k].n.toLocaleString()})${MB ? `<br/>What-if ${favg(spec, MB[k].m, 3)}` : ''}` } },
      xAxis: { type: 'category', data: keep.map(k => G1.labels[k]), ...ax, axisLabel: { ...ax.axisLabel, interval: 0, rotate: keep.length > 5 ? 25 : 0 }, splitLine: { show: true, lineStyle: { color: t.grid } } },
      yAxis: { type: 'value', scale: true, ...ax }, series }, keep, note: 'Each dot is a group average; the bar through it shows 95% uncertainty. The axis is zoomed in to show differences.' }
  }, [A, B, spec.id, split])
  const click = (p: any) => {
    if (!opt || p.componentType !== 'series' || !sg) return
    const k = opt.keep[p.dataIndex]
    if (sg.dtype === 'cat') onPick({ var: split, op: 'eq', value: (A.cols[split]?.categories ?? sg.categories!)[k] })
    else if (sg.dtype === 'bool') onPick({ var: split, op: 'eq', value: k === 1 })
  }
  return (
    <>
      <div className="row" style={{ marginBottom: 8 }}>
        <span className="small muted">Split by</span>
        {SPLITS.filter(s => s !== spec.id && reg.variables[s]).map(s => <button key={s} className={`chip ${split === s ? 'on' : ''}`} onClick={() => setSplit(s)}>{reg.variables[s].label}</button>)}
        <VarPicker value={SPLITS.includes(split) ? '' : split} onChange={x => x && setSplit(x)} filter={x => !!x.filterable && x.id !== spec.id} allowEmpty placeholder="any other field…" />
      </div>
      {opt ? <><EChart option={opt.opt} height={(opt as any).height ?? 300} onClick={click} /><p className="small muted" style={{ margin: '4px 0 0' }}>{opt.note} Click a group to filter to it.</p></> : <div className="empty small">Loading…</div>}
    </>
  )
}

// ------------------------------------------------------------------ relate
function Relate({ spec }: { spec: VarSpec }) {
  const reg = useStore(s => s.registry)!
  const setRoute = useStore(s => s.setRoute)
  const { u, compare } = useLens()
  const [y, setY] = useState(spec.id === 'loneliness' ? 'n_close_friends' : 'loneliness')
  const sy = reg.variables[y]
  const D = useCohortData([spec.id, y, 'sex'], { universe: compare ? 'base' : u })
  const res = useMemo(() => {
    const cx: Column = D.cols[spec.id], cy: Column = D.cols[y]
    if (!cx || !cy || !D.mask || !sy) return null
    const ax = axisStyle(), t = tokens()
    if (isCat(spec) && !isCat(sy)) {
      const g = groupsOf(spec, cx, D.mask)
      const rows = g.labels.map((lab, k) => { const vv: number[] = []; for (let i = 0; i < g.code.length; i++) if (D.mask![i] && g.code[i] === k && !Number.isNaN(cy.data[i])) vv.push(cy.data[i] as number); const s = stats(vv); return { lab, n: vv.length, m: s.mean } }).filter(r => r.n > 2)
      return { text: `Average ${sy.label.toLowerCase()} for each ${spec.label.toLowerCase()} group.`, opt: { grid: { left: 8, right: 12, top: 10, bottom: 4, containLabel: true }, tooltip: { trigger: 'axis' }, xAxis: { type: 'category', data: rows.map(r => r.lab), ...ax, axisLabel: { ...ax.axisLabel, interval: 0, rotate: rows.length > 5 ? 25 : 0 } }, yAxis: { type: 'value', scale: true, name: sy.label, ...ax }, series: [{ type: 'bar', barMaxWidth: 30, data: rows.map(r => r.m), itemStyle: { color: uColor(u), borderRadius: [4, 4, 0, 0] } }] } }
    }
    if (isCat(sy)) return { text: 'Pick a numeric field to relate (or use Compare groups with this one as the split).', opt: null }
    const idx: number[] = []
    for (let i = 0; i < D.mask.length; i++) if (D.mask[i] && !Number.isNaN(cx.data[i]) && !Number.isNaN(cy.data[i])) idx.push(i)
    const step = Math.max(1, Math.floor(idx.length / 3500))
    const xs = idx.map(i => cx.data[i] as number), ys = idx.map(i => cy.data[i] as number)
    const fit = regress(xs, ys), r = pearson(cx.data, cy.data, D.mask)
    const lo = Math.min(...xs), hi = Math.max(...xs)
    const jit = (v: number, s: VarSpec) => (s.dtype !== 'f4' && s.dtype !== 'f8' ? v + (Math.random() - 0.5) * 0.4 : v)
    const a = Math.abs(r.r)
    const word = a < 0.1 ? 'Essentially no relationship' : a < 0.3 ? 'A weak relationship' : a < 0.5 ? 'A moderate relationship' : 'A strong relationship'
    return {
      text: `${word}: ${r.r >= 0 ? 'higher' : 'lower'} ${spec.label.toLowerCase()} tends to go with ${r.r >= 0 ? 'higher' : 'lower'} ${sy.label.toLowerCase()} (correlation ${fmt(r.r, 2)}, ${r.n.toLocaleString()} people). An association inside the simulation, not proof of cause: see "What drives it".`,
      opt: { grid: { left: 8, right: 16, top: 10, bottom: 24, containLabel: true }, tooltip: { trigger: 'item', formatter: (p: any) => p.seriesType === 'scatter' ? `${D.cols.sex ? nameOf(p.data[2], D.cols.sex.data[p.data[2]]) : '#' + p.data[2]}<br/>${spec.label}: ${fval(spec, p.data[0])}<br/>${sy.label}: ${fval(sy, p.data[1])}` : '' },
        xAxis: { type: 'value', scale: true, name: spec.label, nameLocation: 'middle', nameGap: 26, ...ax }, yAxis: { type: 'value', scale: true, name: sy.label, ...ax },
        series: [{ type: 'scatter', symbolSize: 5, data: idx.filter((_, k) => k % step === 0).map(i => [jit(cx.data[i] as number, spec), jit(cy.data[i] as number, sy), i]), itemStyle: { color: uColor(u), opacity: 0.4 } },
          { type: 'line', showSymbol: false, silent: true, data: [[lo, fit.intercept + fit.slope * lo], [hi, fit.intercept + fit.slope * hi]], lineStyle: { width: 2, color: t.text } }] },
      click: (p: any) => p.data?.[2] !== undefined && setRoute(['person', String(p.data[2])]),
    }
  }, [D, spec.id, y])
  return (
    <>
      <div className="row" style={{ marginBottom: 8 }}><span className="small muted">{spec.label} vs</span><VarPicker value={y} onChange={setY} filter={x => !!x.chartable && x.dtype !== 'cat' && x.dtype !== 'bool' && x.id !== spec.id} />
        {compare && <span className="small muted">(showing the Original world)</span>}</div>
      {res?.opt ? <EChart option={res.opt} height={340} onClick={(res as any).click} /> : null}
      {res && <p className="small secondary" style={{ margin: '6px 0 0' }}>{res.text}</p>}
    </>
  )
}

// ------------------------------------------------------------------ people
function PeopleBehind({ spec, A, B }: { spec: VarSpec; A: any; B: any | null }) {
  const setRoute = useStore(s => s.setRoute)
  const lists = useMemo(() => {
    const c: Column = A.cols[spec.id], sex = A.cols.sex
    if (!c || !A.mask || !sex) return null
    const nm = (i: number) => nameOf(i, sex.data[i])
    if (isCat(spec)) {
      const labs = catLabels(spec, c)
      const by: Record<string, number[]> = {}
      for (let i = 0; i < c.data.length; i++) if (A.mask[i]) { const k = labs[c.data[i]]; if (k === undefined) continue; const arr = (by[k] ??= []); if (arr.length < 400) arr.push(i) }
      return { kind: 'cat' as const, groups: Object.entries(by).sort((a, b) => b[1].length - a[1].length).slice(0, 6).map(([k, ids]) => ({ k, people: ids.filter((_, j) => j % Math.max(1, Math.floor(ids.length / 6)) === 0).slice(0, 6).map(i => ({ i, name: nm(i) })) })) }
    }
    const idx: number[] = []
    for (let i = 0; i < c.data.length; i++) if (A.mask[i] && !Number.isNaN(c.data[i])) idx.push(i)
    idx.sort((a, b) => (c.data[b] as number) - (c.data[a] as number))
    const mid = Math.floor(idx.length / 2)
    const row = (i: number) => ({ i, name: nm(i), v: c.data[i] as number, alt: B?.cols[spec.id]?.data[i] as number | undefined })
    return { kind: 'num' as const, top: idx.slice(0, 7).map(row), mid: idx.slice(Math.max(0, mid - 2), mid + 3).map(row), bottom: idx.slice(-7).reverse().map(row) }
  }, [A, B, spec.id])
  if (!lists) return <div className="empty small">Loading…</div>
  const P = ({ p }: { p: any }) => (
    <div className="row small bf-flow"><button className="linkish" onClick={() => setRoute(['person', String(p.i)])}>{p.name}</button><span className="spacer" />
      <span className="tabular">{p.v !== undefined ? fval(spec, p.v) : ''}{p.alt !== undefined && Number.isFinite(p.alt) && Math.abs(p.alt - p.v) > 1e-6 ? <span className="u-alt-t"> → {fval(spec, p.alt)}</span> : null}</span></div>
  )
  if (lists.kind === 'cat') return (
    <div className="grid g3">{lists.groups.map(g => <div key={g.k}><b className="small">{pretty(g.k)}</b>{g.people.map(p => <P key={p.i} p={p} />)}</div>)}</div>
  )
  return (
    <div className="grid g3">
      <div><b className="small">Highest</b>{lists.top.map(p => <P key={p.i} p={p} />)}</div>
      <div><b className="small">Right in the middle</b>{lists.mid.map(p => <P key={p.i} p={p} />)}</div>
      <div><b className="small">Lowest</b>{lists.bottom.map(p => <P key={p.i} p={p} />)}</div>
    </div>
  )
}

// ------------------------------------------------------------------ drivers
function Drivers({ v }: { v: string }) {
  const { registry, setRoute } = useStore()
  const reg = registry!
  const mechs = Object.values(reg.mechanisms) as any[]
  const tgt = (m: any) => (Array.isArray(m.target) ? m.target : [m.target])
  const drivers = mechs.filter(m => tgt(m).includes(v))
  const effects = mechs.filter(m => (m.sources ?? []).includes(v))
  const events = (Object.values(reg.events) as any[]).filter(e => (e.effects ?? []).some((f: any) => f.var === v))
  const chip = (id: string) => reg.variables[id] ? <button key={id} className="chip" onClick={() => setRoute(['explore', id])}>{reg.variables[id].label}</button> : null
  return (
    <div className="grid g2">
      <div>
        <h3 className="small-h">What moves {reg.variables[v]?.label.toLowerCase()}</h3>
        {drivers.length === 0 && events.length === 0 && <p className="small muted">No rule sets this field directly: it is a fixed trait, set when the person is created, or a count kept by the model.</p>}
        {drivers.map(m => (
          <div key={m.id} className="drv">
            <div className="row" style={{ gap: 6 }}><b className="small">{m.label}</b><Evidence level={m.evidence} /><span className="spacer" /><button className="linkish small" onClick={() => setRoute(['mechanisms', m.id])}>rule</button></div>
            {(m.sources ?? []).length > 0 && <div className="chips">{(m.sources ?? []).map(chip)}</div>}
          </div>
        ))}
        {events.length > 0 && <div className="drv"><b className="small">Events that shift it for a while</b><div className="chips">{events.map(e => <button key={e.id} className="chip" onClick={() => setRoute(['events', 'type', e.id])}>{e.label}</button>)}</div></div>}
      </div>
      <div>
        <h3 className="small-h">What it moves</h3>
        {effects.length === 0 && <p className="small muted">No rule uses this field as an input.</p>}
        {effects.map(m => (
          <div key={m.id} className="drv">
            <div className="row" style={{ gap: 6 }}><b className="small">{m.label}</b><Evidence level={m.evidence} /></div>
            <div className="chips">{tgt(m).map(chip)}</div>
          </div>
        ))}
        <button className="btn small" style={{ marginTop: 8 }} onClick={() => setRoute(['causal', v])}>{G.link} Trace it in Cause & effect</button>
      </div>
    </div>
  )
}

/** Why is my group different? The gap split into the model's forces, plus example lives. */
function WhyGroup({ v }: { v: string }) {
  const { cohort, registry, dataVersion, setRoute } = useStore()
  const { u } = useLens()
  const r = useAsync(() => api.cohortExplain({ and: cohort }, v, u), [v, JSON.stringify(cohort), u, dataVersion])
  const spec = registry!.variables[v]
  const d: any = r.data
  return (
    <div className="card" style={{ marginTop: 14 }}>
      <h3>Why is your group's {spec.label.toLowerCase()} different?</h3>
      <p className="hint">Your group: {cohort.map(c => condLabel(c, registry)).join(' · ')}</p>
      {!d ? <div className="empty small">{r.error || 'Tracing causes…'}</div> : (
        <div className="grid g2">
          <div>
            <p className="small" style={{ marginTop: 0 }}>Your group averages <b>{favg(spec, d.cohort_mean)}</b> vs <b>{favg(spec, d.population_mean)}</b> for everyone.</p>
            {d.terms && <Decomposition rows={d.terms.slice(0, 8).map((t: any) => ({ label: t.label, value: t.gap, evidence: t.evidence ?? undefined }))} />}
            <p className="small muted">Red pushes it up for your group, blue pushes it down.</p>
          </div>
          <div>
            <div className="small muted" style={{ marginBottom: 4 }}>Example lives, lowest to highest</div>
            {(d.representatives ?? []).map((p: any) => <div key={p.role} className="row small bf-flow"><span className="muted" style={{ width: 64 }}>{p.role}</span><button className="linkish" onClick={() => setRoute(['person', String(p.id)])}>{p.name}</button><span className="spacer" /><span className="tabular">{fval(spec, p.value)}</span></div>)}
          </div>
        </div>
      )}
    </div>
  )
}

export { DeltaChip, polarity }
