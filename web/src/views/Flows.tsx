import { useEffect, useMemo, useState } from 'react'
import { fmt } from '../analysis'
import { api, STATIC } from '../api'
import { axisStyle, CohortBar, condLabel, cssVar, EChart, Loading, PersonLink, tokens } from '../components'
import { useStore } from '../store'
import { PageHeader } from '../ui'

// Friendly names and a sensible default order for each tracked state variable.
const FLOW_VARS: [string, string][] = [
  ['rel_status', 'Relationship status'], ['activity', 'Church activity'], ['mission_status', 'Mission status'], ['living', 'Living situation'],
  ['class_standing', 'Class standing'], ['academic_standing', 'Academic standing'], ['school', 'School'], ['enrolled', 'Enrolled in school'],
  ['employed', 'Has a job'], ['faith_crisis', 'In a faith crisis'], ['depressive_episode', 'In a depressive episode'],
  ['app_user', 'Uses dating apps'], ['temple_recommend', 'Holds a temple recommend'],
]
const TRAJ_VARS: [string, string][] = [
  ['loneliness', 'Loneliness'], ['mood', 'Happiness'], ['stress', 'Stress'], ['belonging', 'Belonging'], ['n_friends', 'Friends'],
  ['n_close_friends', 'Close friends'], ['faith_belief', 'Belief'], ['attend_rate', 'Church attendance'], ['dates_30d', 'Dates / month'],
  ['financial_stress', 'Money stress'], ['life_satisfaction', 'Life satisfaction'], ['romantic_longing', 'Romantic longing'],
]
const NOT_HERE = 'not here'

export default function Flows({ var0 }: { var0?: string }) {
  const { universe, dataVersion, cohort, registry, status, addCond } = useStore()
  const [v, setV] = useState(var0 && FLOW_VARS.some(f => f[0] === var0) ? var0 : 'rel_status')
  const [info, setInfo] = useState<any>(null)
  const [preset, setPreset] = useState<'two' | 'three' | 'monthly'>('three')
  const [onlyChanges, setOnlyChanges] = useState(false)
  const [data, setData] = useState<any>(null)
  const [err, setErr] = useState('')
  const [pick, setPick] = useState<{ from: string; to: string; step: number } | null>(null)
  useEffect(() => { if (var0) setV(var0) }, [var0])
  useEffect(() => { api.historyInfo(universe).then(setInfo).catch(e => setErr(String(e.message ?? e))) }, [universe, dataVersion])
  const days = useMemo(() => {
    if (!info) return []
    const now = info.now
    const snaps: number[] = info.days.filter((d: number) => d < now)
    if (preset === 'two') return [0, now]
    if (preset === 'three') return [...new Set([0, snaps[Math.floor(snaps.length / 2)] ?? 0, now])]
    const monthly = snaps.filter((d: number) => d % 28 === 0)
    const pickEvery = Math.max(1, Math.ceil(monthly.length / 7))
    return [...new Set([...monthly.filter((_: number, k: number) => k % pickEvery === 0), now])]
  }, [info, preset])
  useEffect(() => {
    if (!days.length) return
    setData(null); setErr(''); setPick(null)
    api.flows({ var: v, days, filter: cohort.length ? { and: cohort } : null, u: universe }).then(setData).catch(e => setErr(String(e.message ?? e)))
  }, [v, JSON.stringify(days), JSON.stringify(cohort), universe, dataVersion])

  const start = info?.start_date
  const dateOf = (d: number) => { if (!start) return `day ${d}`; const x = new Date(start + 'T12:00:00'); x.setDate(x.getDate() + d); return x.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: '2-digit' }) }
  const states: string[] = data?.states ?? []
  const color = (s: string) => s === NOT_HERE ? cssVar('--axis') : cssVar(`--s${(states.indexOf(s) % 8) + 1}`)
  const label = (s: string) => s.replace(/_/g, ' ')

  const opt = useMemo(() => {
    if (!data) return null
    const t = tokens()
    const nodes: any[] = [], seen = new Set<string>()
    const id = (k: number, s: string) => `${s}§${k}`
    data.columns.forEach((c: any, k: number) => c.nodes.forEach((nd: any) => {
      const key = id(k, nd.state)
      if (!seen.has(key)) { seen.add(key); nodes.push({ name: key, depth: k, itemStyle: { color: color(nd.state), borderColor: t.surface }, label: { formatter: () => `${label(nd.state)}  ${nd.n.toLocaleString()}` } }) }
    }))
    const links = data.links.filter((l: any) => !onlyChanges || l.from !== l.to).map((l: any) => ({
      source: id(l.step, l.from), target: id(l.step + 1, l.to), value: l.n, meta: l,
      lineStyle: { color: l.from === l.to ? t.grid : color(l.to), opacity: l.from === l.to ? 0.55 : 0.45 },
    }))
    return {
      tooltip: { trigger: 'item', formatter: (p: any) => p.dataType === 'edge'
        ? `${label(p.data.meta.from)} → ${label(p.data.meta.to)}<br/><b>${p.data.value.toLocaleString()}</b> people<br/><span style="opacity:.7">click to make them your group</span>`
        : `${label(p.name.split('§')[0])}: ${p.value?.toLocaleString?.() ?? ''}` },
      series: [{ type: 'sankey', left: 10, right: 120, top: 26, bottom: 10, nodeWidth: 14, nodeGap: 10, draggable: false, layoutIterations: 0,
        emphasis: { focus: 'adjacency' }, label: { color: t.text2, fontSize: 11 }, data: nodes, links }],
      graphic: data.columns.map((c: any, k: number) => ({ type: 'text', top: 4, left: `${2 + (k / Math.max(1, data.columns.length - 1)) * 82}%`, style: { text: k === data.columns.length - 1 && c.day === info?.now ? 'now' : dateOf(c.day), fill: t.muted, fontSize: 11 } })),
    }
  }, [data, onlyChanges])

  // transition matrix between the first and last columns (row %)
  const matrix = useMemo(() => {
    if (!data || data.columns.length < 2) return null
    const last = data.columns.length - 1
    // compose step links into first→last by re-requesting would be exact; here we use the direct pair when only two columns
    return { first: data.columns[0], last: data.columns[last] }
  }, [data])

  const makeGroup = (from: string, to: string, step: number) => {
    const d0 = data.days[step], d1 = data.days[step + 1]
    addCond({ transition: { var: v, from: [from], to: [to], d0, d1: d1 >= (info?.now ?? 0) ? undefined : d1 } })
  }

  return (
    <div className="page">
      <PageHeader id="flows" eyebrow="Ask questions" title="Flows over time"
        sub="How people move between states. Each band is a group of people who were in one state at one date and another state at the next."
        tips={[
          'Pick what to follow (relationship status, church activity, living situation…) and how many points in time.',
          'Thick gray bands are people who stayed the same; colored bands are people who changed. Turn on "Only show changes" to focus on movement.',
          <>Click a band to make those people your group (e.g. <i>single → dating since September</i>). Every page then analyzes just them: open People to read their stories, or Explore to see why.</>,
          '"Not here" means away at that time: not yet arrived, serving a mission, or moved away.',
        ]} />
      <CohortBar />
      <div className="card">
        <div className="row" style={{ marginBottom: 8 }}>
          <span className="small muted">Follow</span>
          <select value={v} onChange={e => setV(e.target.value)} aria-label="State to follow">{FLOW_VARS.map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select>
          <span className="small muted" style={{ marginLeft: 8 }}>Points in time</span>
          <div className="seg">
            <button className={preset === 'two' ? 'on' : ''} onClick={() => setPreset('two')}>Start → now</button>
            <button className={preset === 'three' ? 'on' : ''} onClick={() => setPreset('three')}>Start → middle → now</button>
            <button className={preset === 'monthly' ? 'on' : ''} onClick={() => setPreset('monthly')}>Monthly</button>
          </div>
          <label className="inline small"><input type="checkbox" checked={onlyChanges} onChange={e => setOnlyChanges(e.target.checked)} />Only show changes</label>
          <span className="spacer" />
          {data && <span className="pill tabular">{data.total.toLocaleString()} people</span>}
        </div>
        {info && info.now < 14 && <div className="banner">History is recorded every two weeks. Run time forward a few weeks to see flows.</div>}
        {err && <div className="banner">{err}</div>}
        {!data && !err && <Loading what="Tracing who moved where" />}
        {opt && <EChart option={opt} height={Math.max(320, 46 * (data?.columns?.[0]?.nodes?.length ?? 6) + 80)}
          onClick={(p: any) => { if (p.dataType === 'edge' && !STATIC) { setPick({ ...p.data.meta }); } }} />}
        {pick && (
          <div className="banner row" style={{ marginTop: 8 }}>
            <span><b>{data.links.find((l: any) => l.step === pick.step && l.from === pick.from && l.to === pick.to)?.n.toLocaleString()}</b> people went from <b>{label(pick.from)}</b> to <b>{label(pick.to)}</b> between {dateOf(data.days[pick.step])} and {data.days[pick.step + 1] >= info.now ? 'now' : dateOf(data.days[pick.step + 1])}.</span>
            <span className="spacer" />
            <button className="btn small primary" onClick={() => { makeGroup(pick.from, pick.to, pick.step); setPick(null) }}>Make them my group</button>
            <button className="btn small ghost" onClick={() => setPick(null)}>✕</button>
          </div>
        )}
      </div>
      {matrix && data && <Transitions data={data} label={label} dateOf={dateOf} now={info.now} onPick={(f, t, s) => setPick({ from: f, to: t, step: s })} />}
      <Trajectory cohortLabel={cohort.length ? cohort.map(c => condLabel(c, registry)).join(' · ') : ''} start={start} />
      <p className="small muted" style={{ marginTop: 10 }}>History is snapshotted every 2 weeks (day {info?.days?.slice(-1)[0] ?? 0} is the latest, plus "now" = day {status.day}).</p>
    </div>
  )
}

function Transitions({ data, label, dateOf, now, onPick }: { data: any; label: (s: string) => string; dateOf: (d: number) => string; now: number; onPick: (f: string, t: string, s: number) => void }) {
  const [step, setStep] = useState(0)
  const steps = data.columns.length - 1
  const links = data.links.filter((l: any) => l.step === step)
  const from: string[] = [...new Set<string>(links.map((l: any) => l.from))]
  const to: string[] = [...new Set<string>(links.map((l: any) => l.to))]
  const order = (a: string, b: string) => (a === NOT_HERE ? 1 : b === NOT_HERE ? -1 : data.states.indexOf(a) - data.states.indexOf(b))
  from.sort(order); to.sort(order)
  const cell = (f: string, t: string) => links.find((l: any) => l.from === f && l.to === t)?.n ?? 0
  const rowTot = (f: string) => to.reduce((s, t) => s + cell(f, t), 0)
  return (
    <div className="card" style={{ marginTop: 14 }}>
      <div className="row"><h3>Transition table</h3><span className="spacer" />
        {steps > 1 && <select value={step} onChange={e => setStep(Number(e.target.value))}>{Array.from({ length: steps }, (_, k) => <option key={k} value={k}>{dateOf(data.days[k])} → {data.days[k + 1] >= now ? 'now' : dateOf(data.days[k + 1])}</option>)}</select>}</div>
      <p className="hint">Rows: where people were at the start · columns: where they ended up. Percentages are of each row. Click a cell to select those people.</p>
      <div style={{ overflowX: 'auto' }}>
        <table className="data">
          <thead><tr><th>from \ to</th>{to.map(t => <th key={t} className="num">{label(t)}</th>)}<th className="num">total</th></tr></thead>
          <tbody>{from.map(f => {
            const tot = rowTot(f)
            return (
              <tr key={f}><td><b>{label(f)}</b></td>
                {to.map(t => {
                  const c = cell(f, t), share = tot ? c / tot : 0
                  return <td key={t} className="num" style={{ cursor: c ? 'pointer' : 'default', background: c && f !== t ? `color-mix(in srgb, var(--accent) ${Math.round(8 + 50 * share)}%, transparent)` : undefined }}
                    onClick={() => c && onPick(f, t, step)} title={`${c.toLocaleString()} people`}>{c ? `${(100 * share).toFixed(share < 0.1 ? 1 : 0)}%` : '·'}</td>
                })}
                <td className="num muted">{tot.toLocaleString()}</td></tr>
            )
          })}</tbody>
        </table>
      </div>
    </div>
  )
}

function Trajectory({ cohortLabel, start }: { cohortLabel: string; start?: string }) {
  const { cohort, universe, dataVersion } = useStore()
  const [vars, setVars] = useState<string[]>(['loneliness', 'mood', 'n_close_friends'])
  const [res, setRes] = useState<any>(null)
  const [err, setErr] = useState('')
  useEffect(() => {
    setRes(null); setErr('')
    api.cohortTimeline({ vars, filter: cohort.length ? { and: cohort } : null, u: universe }).then(setRes).catch(e => setErr(String(e.message ?? e)))
  }, [JSON.stringify(vars), JSON.stringify(cohort), universe, dataVersion])
  const charts = useMemo(() => {
    if (!res) return []
    const ax = axisStyle(), t = tokens()
    return vars.map(v => ({
      v, opt: {
        grid: { left: 44, right: 10, top: 26, bottom: 22 },
        legend: { top: 0, right: 0, textStyle: { color: t.text2, fontSize: 11 }, icon: 'roundRect', itemHeight: 3, itemWidth: 14 },
        tooltip: { trigger: 'axis', valueFormatter: (x: number) => fmt(x, 3) },
        xAxis: { type: 'time', ...ax, splitLine: { show: false } }, yAxis: { type: 'value', scale: true, ...ax },
        series: [
          { name: cohort.length ? 'Your group' : 'Everyone', type: 'line', showSymbol: false, lineStyle: { width: 2.5 }, data: res.dates.map((d: string, k: number) => [d, res.cohort[v][k]]) },
          ...(cohort.length ? [{ name: 'Everyone', type: 'line', showSymbol: false, lineStyle: { width: 1.5, type: 'dashed' }, itemStyle: { color: t.muted }, data: res.dates.map((d: string, k: number) => [d, res.everyone[v][k]]) }] : []),
        ],
      },
    }))
  }, [res])
  void start
  return (
    <div className="card" style={{ marginTop: 14 }}>
      <div className="row"><div><h3>How did {cohort.length ? 'this group' : 'everyone'} get here?</h3>
        <p className="hint">{cohort.length ? <>The average path of the people in your group today ({cohortLabel}), compared with everyone, using the two-week history.</> : 'Pick a group with the bar above to compare its path with everyone else\'s.'}</p></div></div>
      <div className="row" style={{ marginBottom: 8 }}>{TRAJ_VARS.map(([k, l]) => (
        <label key={k} className="inline small"><input type="checkbox" checked={vars.includes(k)} onChange={e => setVars(e.target.checked ? [...vars, k].slice(-4) : vars.filter(x => x !== k))} />{l}</label>))}</div>
      {err && <div className="banner">{err}</div>}
      {!res && !err && <Loading what="Rebuilding their history" />}
      <div className="grid g2">{charts.map(c => <div key={c.v}><div className="small" style={{ fontWeight: 600 }}>{TRAJ_VARS.find(x => x[0] === c.v)?.[1]}</div><EChart option={c.opt} height={190} /></div>)}</div>
      {res && cohort.length > 0 && <SampleLives />}
    </div>
  )
}

function SampleLives() {
  const { cohort, universe, dataVersion } = useStore()
  const [ids, setIds] = useState<{ id: number; name: string }[]>([])
  useEffect(() => {
    api.cohortServer({ and: cohort }, universe).then(async (r: any) => {
      const pick = r.ids.length <= 6 ? r.ids : Array.from({ length: 6 }, (_, k) => r.ids[Math.floor((k + 0.5) * r.ids.length / 6)])
      const b = await api.brief(pick, universe)
      setIds(b.map((x: any) => ({ id: x.id, name: x.name })))
    }).catch(() => setIds([]))
  }, [JSON.stringify(cohort), universe, dataVersion])
  if (!ids.length) return null
  return <div className="row small" style={{ marginTop: 10 }}><span className="muted">Read some of their lives:</span>{ids.map(p => <span key={p.id} className="pill"><PersonLink id={p.id} name={p.name} /></span>)}</div>
}
