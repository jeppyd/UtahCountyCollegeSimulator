import { useEffect, useMemo, useState } from 'react'
import { fmt, quantile } from '../analysis'
import { api, STATIC } from '../api'
import { axisStyle, condLabel, Decomposition, EChart, Evidence, Loading, PersonLink, series, tokens, VarPicker } from '../components'
import { useStore } from '../store'
import { dayToDate, TSChart } from './Overview'

const DERIVED_ENV = /^(temp_f|weekday|term_|date|month|outdoor_appeal|holiday|conference|exam_week|term_progress)/
const STATES = ['loneliness', 'mood', 'stress', 'belonging', 'romantic_longing', 'financial_stress', 'academic_pressure', 'guilt', 'self_esteem', 'purpose', 'fatigue', 'anxiety']

export default function Lab() {
  const { status } = useStore()
  return (
    <div className="page">
      <h1>Scenario lab</h1>
      <p className="sub">Change something, branch the universe, and watch consequences propagate. Both universes start from the identical state and share random-number streams, so differences are attributable to the intervention and the chains it sets off.</p>
      {status.has_alt ? <Compare /> : <Builder />}
      <div className="grid g2" style={{ marginTop: 14 }}>
        <MonteCarlo />
        <Sweep />
      </div>
    </div>
  )
}

function Builder() {
  const { presets, status, cohort, registry, refreshStatus } = useStore()
  const [queue, setQueue] = useState<any[]>([])
  const [tt, setTt] = useState<'world' | 'param' | 'agent'>('world')
  const envKeys = Object.keys(status.env ?? {}).filter(k => !DERIVED_ENV.test(k))
  const params = useMemo(() => {
    const out: { key: string; label: string; value: number; ev: string }[] = []
    for (const m of Object.values(registry!.mechanisms) as any[]) for (const [p, s] of Object.entries(m.params ?? {}) as any) out.push({ key: `${m.id}.${p}`, label: `${m.label} — ${p}`, value: s.value, ev: m.evidence })
    return out.sort((a, b) => a.key.localeCompare(b.key))
  }, [registry])
  const [target, setTarget] = useState('tuition_byu')
  const [op, setOp] = useState('mul')
  const [value, setValue] = useState('1.2')
  const [ramp, setRamp] = useState(0)
  const [delay, setDelay] = useState(0)
  const [dur, setDur] = useState('')
  const [useCohort, setUseCohort] = useState(false)
  const [busy, setBusy] = useState(false)
  const addCustom = () => {
    const v = value === 'true' ? true : value === 'false' ? false : Number(value)
    const spec: any = { target_type: tt, target, op, value: v, ramp_days: ramp, start_day: status.day + delay, name: `${target} ${op} ${value}` }
    if (dur) spec.duration_days = Number(dur)
    if (tt === 'agent' && useCohort && cohort.length) { spec.population = { and: cohort }; spec.name += ` for ${cohort.map(c => condLabel(c, registry)).join(', ')}` }
    setQueue([...queue, spec])
  }
  const branch = async () => {
    setBusy(true)
    try { await api.fork(queue); await refreshStatus() } catch (e: any) { alert(e.message) }
    setBusy(false)
  }
  return (
    <div className="grid g2">
      <div className="card">
        <h3>Intervention library</h3>
        <p className="hint">Click to queue. Confidence describes how defensible the mechanism/magnitude is.</p>
        <div className="scroll" style={{ maxHeight: 460 }}>
          {presets && Object.entries(presets).map(([id, p]: any) => (
            <div key={id} style={{ padding: '8px 0', borderBottom: '1px solid var(--grid)' }}>
              <div className="row"><b>{p.name}</b><span className="pill">{p.confidence}</span><span className="spacer" /><button className="btn small" disabled={STATIC} onClick={() => setQueue([...queue, { preset: id, name: p.name }])}>+ Queue</button></div>
              <div className="small secondary">{p.description}</div>
            </div>
          ))}
        </div>
      </div>
      <div className="card">
        <h3>Custom intervention</h3>
        <p className="hint">Anything in the world, any mechanism parameter, or any person variable for a cohort.</p>
        <div className="seg" style={{ marginBottom: 8 }}>
          {(['world', 'param', 'agent'] as const).map(k => <button key={k} className={tt === k ? 'on' : ''} onClick={() => { setTt(k); setTarget(k === 'world' ? 'tuition_byu' : k === 'param' ? params[0]?.key : 'faith_belief') }}>{k === 'world' ? 'World variable' : k === 'param' ? 'Mechanism strength' : 'People (cohort)'}</button>)}
        </div>
        <div className="row" style={{ marginBottom: 8 }}>
          {tt === 'world' && <select value={target} onChange={e => setTarget(e.target.value)}>{envKeys.map(k => <option key={k}>{k}</option>)}</select>}
          {tt === 'param' && <select value={target} onChange={e => setTarget(e.target.value)} style={{ maxWidth: 360 }}>{params.map(p => <option key={p.key} value={p.key}>{p.label} ({fmt(p.value)})</option>)}</select>}
          {tt === 'agent' && <VarPicker value={target} onChange={setTarget} filter={v => !!v.intervenable && v.dtype !== 'cat'} />}
          <select value={op} onChange={e => setOp(e.target.value)}><option value="mul">× multiply</option><option value="add">+ add</option><option value="set">= set</option></select>
          <input type="text" value={value} onChange={e => setValue(e.target.value)} style={{ width: 80 }} />
        </div>
        {tt === 'world' && <div className="small muted" style={{ marginBottom: 8 }}>current value: {String(status.env?.[target])}</div>}
        <div className="row small" style={{ marginBottom: 8 }}>
          <label className="inline">starts in <input type="number" value={delay} onChange={e => setDelay(Number(e.target.value))} style={{ width: 60 }} /> days</label>
          <label className="inline">ramp <input type="number" value={ramp} onChange={e => setRamp(Number(e.target.value))} style={{ width: 60 }} /> days</label>
          <label className="inline">lasts <input type="text" placeholder="forever" value={dur} onChange={e => setDur(e.target.value)} style={{ width: 70 }} /> days</label>
        </div>
        {tt === 'agent' && <label className="inline small"><input type="checkbox" checked={useCohort} onChange={e => setUseCohort(e.target.checked)} />apply only to current cohort ({cohort.length ? cohort.map(c => condLabel(c, registry)).join(', ') : 'everyone'})</label>}
        <div style={{ marginTop: 8 }}><button className="btn small" disabled={STATIC} onClick={addCustom}>+ Queue custom</button></div>
        <hr style={{ border: 0, borderTop: '1px solid var(--grid)', margin: '14px 0' }} />
        <h3>Queued for the intervention universe</h3>
        {queue.length === 0 && <div className="muted small">Nothing queued.</div>}
        {queue.map((q, k) => <div key={k} className="row small" style={{ padding: '3px 0' }}><span className="cond">{q.name ?? q.preset}<button onClick={() => setQueue(queue.filter((_, j) => j !== k))}>×</button></span></div>)}
        <div className="row" style={{ marginTop: 10 }}>
          <button className="btn primary" disabled={!queue.length || busy || STATIC} onClick={branch}>Branch universe now (day {status.day})</button>
          {STATIC && <span className="muted small">Interactive branching needs the local simulator.</span>}
        </div>
      </div>
    </div>
  )
}

function Compare() {
  const { status, dataVersion, refreshStatus, setRoute, registry } = useStore()
  const [c, setC] = useState<any>(null)
  const [state, setState] = useState('loneliness')
  const [tsVar, setTsVar] = useState('loneliness')
  const [ts, setTs] = useState<any>(null)
  useEffect(() => { api.compare().then(setC).catch(() => {}) }, [dataVersion])
  useEffect(() => { api.timeseries([tsVar]).then(setTs).catch(() => {}) }, [tsVar, dataVersion])
  const divOpt = useMemo(() => {
    if (!c?.divergence?.length) return null
    const ax = axisStyle()
    const start = dayToDate(status.date, -status.day)
    const keys: [string, string][] = [['any_state_diff', 'People in a different state'], ['friendship_jaccard_distance', 'Friendship network difference'], ['diff_rel_status', 'Different relationship status']]
    return {
      grid: { left: 50, right: 16, top: 30, bottom: 26 }, legend: { top: 0, textStyle: { color: tokens().text2, fontSize: 11 } },
      tooltip: { trigger: 'axis', valueFormatter: (v: number) => (100 * v).toFixed(2) + '%' },
      xAxis: { type: 'time', ...ax, splitLine: { show: false } },
      yAxis: { type: 'value', ...ax, axisLabel: { ...ax.axisLabel, formatter: (v: number) => (100 * v).toFixed(0) + '%' } },
      series: keys.map(([k, l]) => ({ name: l, type: 'line', showSymbol: false, lineStyle: { width: 2 }, data: c.divergence.map((d: any) => [dayToDate(start, d.day), d[k]]) })),
    }
  }, [c])
  if (!c) return <Loading what="Comparing universes" />
  const vars = Object.entries(c.variables).filter(([, v]: any) => v.kind === 'num' && Math.abs(v.delta) > 1e-6).sort((a: any, b: any) => Math.abs(b[1].delta_sd) - Math.abs(a[1].delta_sd)).slice(0, 25)
  const st = c.states[state]
  return (
    <>
      <div className="card" style={{ marginBottom: 14 }}>
        <div className="row">
          <div><h3>Intervention universe (branched on day {status.fork_day})</h3>
            <div className="row small">{c.interventions.map((i: any, k: number) => <span key={k} className="pill">{i.name ?? i.preset ?? `${i.target} ${i.op} ${i.value}`}</span>)}</div></div>
          <span className="spacer" />
          {!STATIC && <button className="btn" onClick={async () => { await api.unfork(); await refreshStatus() }}>Discard intervention universe</button>}
        </div>
        <p className="small muted" style={{ marginBottom: 0 }}>{c.n.toLocaleString()} people present in both universes · use the top-right toggle to view any page in the intervention universe · open any person to see their counterfactual life.</p>
      </div>
      <div className="grid g2">
        <div className="card"><h3>Where the universes diverge</h3><p className="hint">Butterfly effects: share of people whose life has changed so far.</p>{divOpt ? <EChart option={divOpt} height={240} /> : <div className="empty small">Advance the clock.</div>}</div>
        <div className="card">
          <div className="row"><h3>Outcome over time</h3><span className="spacer" /><VarPicker value={tsVar} onChange={setTsVar} filter={v => !!v.flags?.includes('timeseries') && v.dtype !== 'cat'} /></div>
          {ts && <TSChart data={ts} v={tsVar} label={registry!.variables[tsVar]?.label ?? tsVar} height={210} startDate={dayToDate(status.date, -status.day)} forkDay={status.fork_day} />}
        </div>
      </div>
      <div className="grid g2" style={{ marginTop: 14 }}>
        <div className="card">
          <h3>Biggest outcome differences</h3><p className="hint">Mean difference (intervention − baseline), in standard deviations. Click for the variable.</p>
          <div className="scroll" style={{ maxHeight: 420 }}><table className="data"><thead><tr><th>Variable</th><th className="num">Baseline</th><th className="num">Intervention</th><th className="num">Δ</th><th className="num">Δ / sd</th><th className="num">people changed</th></tr></thead>
            <tbody>{vars.map(([k, v]: any) => (
              <tr key={k} className="click" onClick={() => setRoute(['variables', k])}><td>{registry!.variables[k]?.label ?? k} <Evidence level={registry!.variables[k]?.evidence} /></td>
                <td className="num">{fmt(v.base, 3)}</td><td className="num">{fmt(v.alt, 3)}</td><td className="num">{v.delta > 0 ? '+' : ''}{fmt(v.delta, 3)}</td>
                <td className="num"><b>{v.delta_sd > 0 ? '+' : ''}{fmt(v.delta_sd, 3)}</b></td><td className="num">{(100 * v.changed_share).toFixed(1)}%</td></tr>))}</tbody></table></div>
        </div>
        <div className="card">
          <h3>Consequence chains: event counts since the fork</h3><p className="hint">Discrete events that became more or less common.</p>
          <div className="scroll" style={{ maxHeight: 420 }}><table className="data"><thead><tr><th>Event</th><th className="num">Baseline</th><th className="num">Intervention</th><th className="num">Change</th></tr></thead>
            <tbody>{c.events.slice(0, 40).map((e: any) => (
              <tr key={e.type}><td>{e.label}</td><td className="num">{e.base.toLocaleString()}</td><td className="num">{e.alt.toLocaleString()}</td>
                <td className="num" style={{ color: e.delta > 0 ? 'var(--text-primary)' : 'var(--text-secondary)' }}>{e.delta > 0 ? '+' : ''}{e.delta} ({e.rel > 0 ? '+' : ''}{(100 * e.rel).toFixed(0)}%)</td></tr>))}</tbody></table></div>
        </div>
      </div>
      <div className="grid g2" style={{ marginTop: 14 }}>
        <div className="card">
          <div className="row"><h3>Why did it change? Mechanism attribution</h3><span className="spacer" />
            <select value={state} onChange={e => setState(e.target.value)}>{STATES.map(s => <option key={s} value={s}>{registry!.variables[s]?.label}</option>)}</select></div>
          <p className="hint">Exact additive split of the change in mean {registry!.variables[state]?.label.toLowerCase()} (Δ = {fmt(st?.delta, 4)}) across mechanism terms. Follow a mechanism into the causal web.</p>
          {st && <Decomposition rows={st.terms.slice(0, 12).map((t: any) => ({ label: t.mechanism ? (registry!.mechanisms[t.mechanism]?.label ?? t.term) : 'Event after-effects', value: t.delta, evidence: t.mechanism ? registry!.mechanisms[t.mechanism]?.evidence : undefined }))} />}
          <div className="small" style={{ marginTop: 8 }}><a href={`#/causal/${state}`}>Open the causal web for {registry!.variables[state]?.label.toLowerCase()} →</a></div>
        </div>
        <div className="card">
          <h3>Most affected people</h3><p className="hint">Representative lives to read — open one to compare their two timelines.</p>
          {Object.entries(c.most_affected).map(([v, rows]: any) => (
            <div key={v} style={{ marginBottom: 8 }}><b className="small">{registry!.variables[v]?.label}</b>
              <div className="row small">{rows.slice(0, 6).map((r: any) => <span key={r.id} className="pill"><PersonLink id={r.id} name={r.name} /> {r.delta > 0 ? '+' : ''}{fmt(r.delta, 2)}</span>)}</div></div>
          ))}
        </div>
      </div>
    </>
  )
}

function MonteCarlo() {
  const { presets, registry } = useStore()
  const [res, setRes] = useState<any>(null)
  const [pick, setPick] = useState<string[]>(['new_dating_app'])
  const [seeds, setSeeds] = useState(6)
  const [days, setDays] = useState(150)
  const [scale, setScale] = useState(0.08)
  const [metric, setMetric] = useState('married_share')
  useEffect(() => { api.montecarlo().then(setRes).catch(() => {}) }, [])
  useEffect(() => {
    if (res?.state !== 'running') return
    const t = setInterval(() => api.montecarlo().then(setRes), 2000)
    return () => clearInterval(t)
  }, [res?.state])
  const run = async () => {
    const scenarios: any = {}
    for (const p of pick) scenarios[p] = [{ preset: p }]
    await api.montecarloStart({ scenarios, seeds, days, scale })
    setRes({ state: 'running' })
  }
  const metrics = res?.scenarios?.baseline ? Object.keys(res.scenarios.baseline.final) : []
  const opt = useMemo(() => {
    if (!res?.scenarios) return null
    const ax = axisStyle()
    const names = Object.keys(res.scenarios)
    const data = names.map(n => res.scenarios[n].final[metric])
    return {
      grid: { left: 140, right: 20, top: 10, bottom: 30 },
      tooltip: { trigger: 'item', formatter: (p: any) => p.seriesType === 'boxplot' ? `${p.name}<br/>p10 ${fmt(p.data[1], 4)} · median ${fmt(p.data[3], 4)} · p90 ${fmt(p.data[5], 4)}` : `seed run: ${fmt(p.data[0], 4)}` },
      yAxis: { type: 'category', data: names.map(n => presets?.[n]?.name ?? n), ...ax },
      xAxis: { type: 'value', scale: true, ...ax },
      series: [
        { type: 'boxplot', data: data.map((d: any) => { const s = [...d.values].sort((a: number, b: number) => a - b); return [0.1, 0.25, 0.5, 0.75, 0.9].map(q => quantile(s, q)) }), itemStyle: { color: series(0) + '22', borderColor: series(0), borderWidth: 1.5 }, boxWidth: [6, 18] },
        { type: 'scatter', symbolSize: 7, data: data.flatMap((d: any, k: number) => d.values.map((v: number) => [v, k])), itemStyle: { color: series(1), opacity: 0.8 } },
      ],
    }
  }, [res, metric])
  const diffs = res?.scenarios ? Object.entries(res.scenarios).filter(([n]) => n !== 'baseline').map(([n, s]: any) => ({ n, d: s.paired_diff?.[metric] })) : []
  return (
    <div className="card">
      <h3>Monte Carlo: one future is not truth</h3>
      <p className="hint">Each scenario runs from fresh worlds under several seeds; the same seed is shared across scenarios, so per-seed differences are paired.</p>
      {!STATIC && (
        <>
          <div className="row small" style={{ marginBottom: 6 }}>{presets && Object.entries(presets).slice(0, 18).map(([id, p]: any) => (
            <label key={id} className="inline"><input type="checkbox" checked={pick.includes(id)} onChange={e => setPick(e.target.checked ? [...pick, id] : pick.filter(x => x !== id))} />{p.name}</label>))}</div>
          <div className="row small" style={{ marginBottom: 8 }}>
            <label className="inline">seeds <input type="number" value={seeds} min={2} max={60} onChange={e => setSeeds(Number(e.target.value))} style={{ width: 56 }} /></label>
            <label className="inline">days <input type="number" value={days} onChange={e => setDays(Number(e.target.value))} style={{ width: 70 }} /></label>
            <label className="inline">scale <input type="number" step={0.01} value={scale} onChange={e => setScale(Number(e.target.value))} style={{ width: 64 }} /></label>
            <button className="btn primary small" disabled={res?.state === 'running' || !pick.length} onClick={run}>{res?.state === 'running' ? 'Running…' : 'Run'}</button>
          </div>
        </>
      )}
      {res?.state === 'error' && <div className="banner">Error: {res.error}</div>}
      {res?.scenarios && (
        <>
          <div className="row" style={{ marginBottom: 6 }}><span className="small muted">Outcome</span>
            <select value={metric} onChange={e => setMetric(e.target.value)}>{metrics.map(m => <option key={m} value={m}>{registry?.variables[m]?.label ?? m.replace(/_/g, ' ')}</option>)}</select>
            <span className="small muted">{res.runs} runs</span></div>
          {opt && <EChart option={opt} height={60 + 40 * Object.keys(res.scenarios).length} />}
          <table className="data small" style={{ marginTop: 8 }}><thead><tr><th>Scenario − baseline (paired by seed)</th><th className="num">mean</th><th className="num">p10</th><th className="num">p90</th><th className="num">P(Δ &gt; 0)</th></tr></thead>
            <tbody>{diffs.map(({ n, d }: any) => d && <tr key={n}><td>{presets?.[n]?.name ?? n}</td><td className="num">{fmt(d.mean, 4)}</td><td className="num">{fmt(d.p10, 4)}</td><td className="num">{fmt(d.p90, 4)}</td><td className="num">{(100 * d.prob_positive).toFixed(0)}%</td></tr>)}</tbody></table>
        </>
      )}
      {!res?.scenarios && res?.state !== 'running' && <div className="empty small">No Monte Carlo results yet.</div>}
    </div>
  )
}

function Sweep() {
  const { registry } = useStore()
  const [res, setRes] = useState<any>(null)
  const [param, setParam] = useState('world:men_initiate_norm')
  const [vals, setVals] = useState('0.4, 0.7, 1.0, 1.3')
  const [metric, setMetric] = useState('dating_share')
  useEffect(() => { api.sweep().then(setRes).catch(() => {}) }, [])
  useEffect(() => { if (res?.state !== 'running') return; const t = setInterval(() => api.sweep().then(setRes), 2000); return () => clearInterval(t) }, [res?.state])
  const params = useMemo(() => {
    const out: string[] = ['world:men_initiate_norm', 'world:rent_shock', 'world:tuition_byu', 'world:app_appeal', 'world:mission_norm', 'world:marriage_norm', 'world:church_attendance_norm', 'world:unemployment']
    for (const m of Object.values(registry!.mechanisms) as any[]) for (const p of Object.keys(m.params ?? {})) out.push(`${m.id}.${p}`)
    return out
  }, [registry])
  const opt = useMemo(() => {
    const c = res?.curves?.[metric]
    if (!c) return null
    const ax = axisStyle()
    return {
      grid: { left: 56, right: 16, top: 14, bottom: 40 }, tooltip: { trigger: 'axis', valueFormatter: (v: number) => fmt(v, 4) },
      xAxis: { type: 'value', scale: true, name: res.param, nameLocation: 'middle', nameGap: 26, ...ax },
      yAxis: { type: 'value', scale: true, ...ax },
      series: [
        { name: 'p10', type: 'line', data: c.map((r: any) => [r.value, r.p10]), lineStyle: { opacity: 0 }, stack: 'band', showSymbol: false },
        { name: 'p10–p90', type: 'line', data: c.map((r: any) => [r.value, r.p90 - r.p10]), lineStyle: { opacity: 0 }, areaStyle: { color: series(0), opacity: 0.12 }, stack: 'band', showSymbol: false },
        { name: 'mean', type: 'line', data: c.map((r: any) => [r.value, r.mean]), lineStyle: { width: 2, color: series(0) }, symbolSize: 8, itemStyle: { color: series(0) } },
      ],
    }
  }, [res, metric])
  return (
    <div className="card">
      <h3>Parameter sweep: response curves & sensitivity</h3>
      <p className="hint">How an outcome responds to a world variable or a mechanism strength (mean with 10–90% band across seeds).</p>
      {!STATIC && (
        <div className="row small" style={{ marginBottom: 8 }}>
          <select value={param} onChange={e => setParam(e.target.value)} style={{ maxWidth: 260 }}>{params.map(p => <option key={p}>{p}</option>)}</select>
          <input type="text" value={vals} onChange={e => setVals(e.target.value)} style={{ width: 150 }} />
          <button className="btn primary small" disabled={res?.state === 'running'} onClick={async () => { await api.sweepStart({ param, values: vals.split(',').map(Number), seeds: 3, days: 150, scale: 0.08 }); setRes({ state: 'running' }) }}>{res?.state === 'running' ? 'Running…' : 'Sweep'}</button>
        </div>
      )}
      {res?.curves && (
        <>
          <div className="row" style={{ marginBottom: 6 }}><span className="small muted">Outcome</span>
            <select value={metric} onChange={e => setMetric(e.target.value)}>{Object.keys(res.curves).map(m => <option key={m} value={m}>{registry?.variables[m]?.label ?? m.replace(/_/g, ' ')}</option>)}</select></div>
          {opt && <EChart option={opt} height={240} />}
        </>
      )}
      {!res?.curves && res?.state !== 'running' && <div className="empty small">No sweep results yet.</div>}
    </div>
  )
}
