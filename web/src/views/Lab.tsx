import { useEffect, useMemo, useState } from 'react'
import { fmt, quantile } from '../analysis'
import { api, STATIC } from '../api'
import { axisStyle, condLabel, Decomposition, EChart, Evidence, Loading, PersonLink, series, tokens, VarPicker } from '../components'
import { useStore } from '../store'
import { effectWord, PageHeader, useAdvanced } from '../ui'
import { dayToDate, TSChart } from './Overview'

const DERIVED_ENV = /^(temp_f|weekday|term_|date|month|outdoor_appeal|holiday|conference|exam_week|term_progress)/
const STATES = ['loneliness', 'mood', 'stress', 'belonging', 'romantic_longing', 'financial_stress', 'academic_pressure', 'guilt', 'self_esteem', 'purpose', 'fatigue', 'anxiety']

const THEMES: [string, string[]][] = [
  ['Money & housing', ['rent_up_20', 'tuition_up_20', 'construction_30', 'recession', 'contracted_housing_removed', 'contracted_housing_all_years', 'transit_improved']],
  ['Dating & marriage', ['new_dating_app', 'women_ask_more', 'marriage_norm_weaker', 'new_dance_hall']],
  ['Faith & culture', ['coffee_permitted', 'church_attendance_decline', 'mission_participation_minus_15', 'missionary_outreach', 'interfaith_welcome', 'pickleball_craze', 'stronger_peer_influence']],
  ['School & environment', ['enrollment_up_20', 'warmer_plus_5f']],
]
const DURATIONS: [number, string][] = [[30, '1 month'], [112, '1 semester'], [365, '1 year'], [730, '2 years']]

export default function Lab({ preset }: { preset?: string }) {
  const { status } = useStore()
  const adv = useAdvanced()
  return (
    <div className="page">
      <PageHeader id="lab" eyebrow="What if?" title="What-if lab"
        sub="Change something about Provo, split the world in two, and compare what happens. Both worlds start identical and roll the same dice, so differences come from your change."
        tips={[
          'Pick one or more changes. Each card says how confident we are that the effect is realistic.',
          'Choose how long to watch, then split the world. The original keeps going unchanged; the copy gets your change.',
          'Results show what changed most, what happened more or less often, why feelings changed, and the people most affected.',
          <>Use the <b>Original / What-if</b> switch at the top right to view any page (map, people, charts) in either world.</>,
        ]} />
      {status.has_alt ? <Results /> : <Wizard preset={preset} />}
      {adv && (
        <>
          <div className="section-title"><h2>Many runs & sweeps</h2><span className="small muted">Advanced: repeat experiments with different dice, or try a range of strengths.</span></div>
          <div className="grid g2">
            <MonteCarlo />
            <Sweep />
          </div>
        </>
      )}
    </div>
  )
}

type Saved = { name: string; queue: any[]; days: number }
const SAVED_KEY = 'ucsim-saved-experiments'
const loadSaved = (): Saved[] => { try { return JSON.parse(localStorage.getItem(SAVED_KEY) ?? '[]') } catch { return [] } }
const storeSaved = (s: Saved[]) => { try { localStorage.setItem(SAVED_KEY, JSON.stringify(s)) } catch { /* private mode */ } }

function Wizard({ preset }: { preset?: string }) {
  const { presets, status, refreshStatus } = useStore()
  const adv = useAdvanced()
  const [queue, setQueue] = useState<any[]>(() => (preset && presets?.[preset] ? [{ preset, name: presets[preset].name }] : []))
  const [days, setDays] = useState(112)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const [saved, setSaved] = useState<Saved[]>(loadSaved)
  const [naming, setNaming] = useState<string | null>(null)
  const keep = (s: Saved[]) => { setSaved(s); storeSaved(s) }
  const saveCurrent = () => {
    const name = (naming ?? '').trim() || queue.map(q => q.name ?? q.preset).join(' + ')
    keep([{ name, queue, days }, ...saved.filter(s => s.name !== name)].slice(0, 20))
    setNaming(null)
  }
  useEffect(() => { if (preset && presets?.[preset] && !queue.some(q => q.preset === preset)) setQueue([{ preset, name: presets[preset].name }]) }, [preset])
  const toggle = (id: string) => setQueue(queue.some(q => q.preset === id) ? queue.filter(q => q.preset !== id) : [...queue, { preset: id, name: presets[id].name }])
  const run = async () => {
    setBusy(true); setErr('')
    try { await api.fork(queue); await api.step({ days }); await refreshStatus() } catch (e: any) { setErr(String(e.message ?? e)) }
    setBusy(false)
  }
  const listed = new Set(THEMES.flatMap(t => t[1]))
  const others = Object.keys(presets ?? {}).filter(k => !listed.has(k))
  const step = queue.length ? 2 : 1
  return (
    <>
      {saved.length > 0 && (
        <div className="card" style={{ marginBottom: 14 }}>
          <div className="small muted" style={{ marginBottom: 6, fontWeight: 600 }}>Your saved experiments</div>
          <div className="row">{saved.map(s => (
            <span key={s.name} className="cond">
              <button style={{ color: "var(--accent)", fontWeight: 600 }} onClick={() => { setQueue(s.queue); setDays(s.days) }} title="Load these changes and duration">{s.name}</button>
              <button onClick={() => keep(saved.filter(x => x.name !== s.name))} aria-label={`delete ${s.name}`}>×</button>
            </span>
          ))}</div>
        </div>
      )}
      <div className="wizard-steps"><span className={`ws ${step === 1 ? 'on' : 'done'}`}>1 · Choose a change</span><span className={`ws ${step === 2 ? 'on' : ''}`}>2 · How long to watch</span><span className="ws">3 · See what changed</span></div>
      {[...THEMES, ...(others.length ? [['Other', others] as [string, string[]]] : [])].map(([theme, ids]) => (
        <div key={theme} style={{ marginBottom: 14 }}>
          <div className="small muted" style={{ marginBottom: 6, fontWeight: 600 }}>{theme}</div>
          <div className="grid g3">{ids.filter(id => presets?.[id]).map(id => {
            const p = presets[id], on = queue.some(q => q.preset === id)
            return (
              <button key={id} className={`card preset-card ${on ? 'on' : ''}`} onClick={() => toggle(id)} disabled={STATIC} aria-pressed={on}>
                <div className="row" style={{ flexWrap: 'nowrap' }}><b style={{ flex: 1 }}>{p.name}</b><span className="pill" title="How defensible the size of this effect is">{p.confidence === 'plausible' ? 'plausible' : 'speculative'}</span></div>
                <span className="pc-desc">{p.description}</span>
                <span className="small" style={{ color: on ? 'var(--accent)' : 'var(--text-muted)', fontWeight: 600 }}>{on ? '✓ selected' : 'select'}</span>
              </button>
            )
          })}</div>
        </div>
      ))}
      {adv && <CustomBuilder onAdd={spec => setQueue([...queue, spec])} />}
      <div className="card" style={{ position: 'sticky', bottom: 10, marginTop: 10, zIndex: 3 }}>
        <div className="row">
          <div style={{ minWidth: 0 }}>
            <b>{queue.length ? `${queue.length} change${queue.length > 1 ? 's' : ''}:` : 'Select at least one change above.'}</b>{' '}
            {queue.map((q, k) => <span key={k} className="cond" style={{ marginRight: 4 }}>{q.name ?? q.preset}<button onClick={() => setQueue(queue.filter((_, j) => j !== k))} aria-label="remove">×</button></span>)}
          </div>
          <span className="spacer" />
          <span className="small muted">Watch for</span>
          <div className="seg">{DURATIONS.map(([d, l]) => <button key={d} className={days === d ? 'on' : ''} onClick={() => setDays(d)}>{l}</button>)}</div>
          {queue.length > 0 && (naming === null
            ? <button className="btn" onClick={() => setNaming('')} title="Keep this combination of changes to rerun later">Save…</button>
            : <span className="row" style={{ gap: 4 }}><input type="text" autoFocus placeholder="Name this experiment" value={naming} onChange={e => setNaming(e.target.value)} onKeyDown={e => { if (e.key === 'Enter') saveCurrent(); if (e.key === 'Escape') setNaming(null) }} style={{ width: 190 }} /><button className="btn" onClick={saveCurrent}>Save</button></span>)}
          <button className="btn primary" disabled={!queue.length || busy || STATIC} onClick={run}>{busy ? 'Starting…' : 'Split the world and run ▶'}</button>
        </div>
        {status.day < 14 && <p className="small muted" style={{ margin: '8px 0 0' }}>Tip: the world is only {status.day} days old. Friendships and dating need a few weeks to get going, so effects will be clearer if you run a couple of weeks first.</p>}
        {err && <div className="banner" style={{ marginTop: 8 }}>{err}</div>}
        {STATIC && <p className="small muted" style={{ margin: '8px 0 0' }}>Running experiments needs the installed app.</p>}
      </div>
    </>
  )
}

function CustomBuilder({ onAdd }: { onAdd: (spec: any) => void }) {
  const { status, cohort, registry } = useStore()
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
  const add = () => {
    const v = value === 'true' ? true : value === 'false' ? false : Number(value)
    const spec: any = { target_type: tt, target, op, value: v, ramp_days: ramp, start_day: status.day + delay, name: `${target} ${op} ${value}` }
    if (dur) spec.duration_days = Number(dur)
    if (tt === 'agent' && useCohort && cohort.length) { spec.population = { and: cohort }; spec.name += ` for ${cohort.map(c => condLabel(c, registry)).join(', ')}` }
    onAdd(spec)
  }
  return (
    <div className="card" style={{ marginBottom: 14 }}>
      <h3>Custom change (advanced)</h3>
      <p className="hint">Anything in the world, the strength of any rule, or any personal measure for your current group.</p>
      <div className="seg" style={{ marginBottom: 8 }}>
        {(['world', 'param', 'agent'] as const).map(k => <button key={k} className={tt === k ? 'on' : ''} onClick={() => { setTt(k); setTarget(k === 'world' ? 'tuition_byu' : k === 'param' ? params[0]?.key : 'faith_belief') }}>{k === 'world' ? 'World variable' : k === 'param' ? 'Rule strength' : 'People (your group)'}</button>)}
      </div>
      <div className="row" style={{ marginBottom: 8 }}>
        {tt === 'world' && <select value={target} onChange={e => setTarget(e.target.value)}>{envKeys.map(k => <option key={k}>{k}</option>)}</select>}
        {tt === 'param' && <select value={target} onChange={e => setTarget(e.target.value)} style={{ maxWidth: 360 }}>{params.map(p => <option key={p.key} value={p.key}>{p.label} ({fmt(p.value)})</option>)}</select>}
        {tt === 'agent' && <VarPicker value={target} onChange={setTarget} filter={v => !!v.intervenable && v.dtype !== 'cat'} />}
        <select value={op} onChange={e => setOp(e.target.value)}><option value="mul">× multiply</option><option value="add">+ add</option><option value="set">= set</option></select>
        <input type="text" value={value} onChange={e => setValue(e.target.value)} style={{ width: 80 }} aria-label="Value" />
        {tt === 'world' && <span className="small muted">now: {String(status.env?.[target])}</span>}
      </div>
      <div className="row small" style={{ marginBottom: 8 }}>
        <label className="inline">starts in <input type="number" value={delay} onChange={e => setDelay(Number(e.target.value))} style={{ width: 60 }} /> days</label>
        <label className="inline">ramps up over <input type="number" value={ramp} onChange={e => setRamp(Number(e.target.value))} style={{ width: 60 }} /> days</label>
        <label className="inline">lasts <input type="text" placeholder="forever" value={dur} onChange={e => setDur(e.target.value)} style={{ width: 70 }} /> days</label>
        {tt === 'agent' && <label className="inline"><input type="checkbox" checked={useCohort} onChange={e => setUseCohort(e.target.checked)} />only my group ({cohort.length ? cohort.map(c => condLabel(c, registry)).join(', ') : 'everyone'})</label>}
        <button className="btn small" disabled={STATIC} onClick={add}>+ Add</button>
      </div>
    </div>
  )
}

function Results() {
  const { status, dataVersion, refreshStatus, setRoute, registry, setUniverse } = useStore()
  const adv = useAdvanced()
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
    const keys: [string, string][] = [['any_state_diff', 'Lives that differ in some way'], ['diff_rel_status', 'Different relationship status'], ['friendship_jaccard_distance', 'Friendships that differ']]
    return {
      grid: { left: 46, right: 16, top: 30, bottom: 26 }, legend: { top: 0, textStyle: { color: tokens().text2, fontSize: 11 } },
      tooltip: { trigger: 'axis', valueFormatter: (v: number) => (100 * v).toFixed(1) + '%' },
      xAxis: { type: 'time', ...ax, splitLine: { show: false } },
      yAxis: { type: 'value', ...ax, axisLabel: { ...ax.axisLabel, formatter: (v: number) => (100 * v).toFixed(0) + '%' } },
      series: keys.map(([k, l]) => ({ name: l, type: 'line', showSymbol: false, lineStyle: { width: 2 }, data: c.divergence.map((d: any) => [dayToDate(start, d.day), d[k]]) })),
    }
  }, [c])
  if (!c) return <Loading what="Comparing the two worlds" />
  const running = status.job?.state === 'running'
  const since = status.day - (status.fork_day ?? status.day)
  const vars = Object.entries(c.variables).filter(([k, v]: any) => v.kind === 'num' && Math.abs(v.delta) > 1e-6 && registry!.variables[k]?.chartable)
    .sort((a: any, b: any) => Math.abs(b[1].delta_sd) - Math.abs(a[1].delta_sd))
  const st = c.states[state]
  const lastDiv = c.divergence?.[c.divergence.length - 1]
  const changes = c.events.filter((e: any) => e.base + e.alt >= 10 && Math.abs(e.rel) >= 0.05 && e.type !== 'intervention_exposure').slice(0, 8)
  return (
    <>
      <div className="card" style={{ marginBottom: 14 }}>
        <div className="row">
          <div style={{ minWidth: 0 }}>
            <div className="eyebrow">Your experiment</div>
            <div className="row">{[...new Set<string>(c.interventions.map((i: any) => i.name ?? i.preset ?? `${i.target} ${i.op} ${i.value}`))].map(label => <span key={label} className="pill" style={{ fontSize: 13 }}><b>{label}</b></span>)}</div>
            <div className="small secondary" style={{ marginTop: 6 }}>Split on day {status.fork_day} · running for {since} days so far{running ? ' (still running…)' : ''} · {c.n.toLocaleString()} people in both worlds.</div>
          </div>
          <span className="spacer" />
          {!STATIC && <>
            <button className="btn" disabled={running} onClick={async () => { await api.step({ days: 30 }); refreshStatus() }}>Run 1 more month</button>
            <button className="btn" onClick={() => setUniverse('alt')} title="View every page in the what-if world">View the what-if world</button>
            <button className="btn" onClick={async () => { await api.unfork(); await refreshStatus() }}>Start a new experiment</button>
          </>}
        </div>
      </div>

      <div className="grid g2">
        <div className="card">
          <h3>How far apart the worlds have drifted</h3>
          <p className="hint">{lastDiv ? <>So far <b>{(100 * lastDiv.any_state_diff).toFixed(1)}%</b> of people live a noticeably different life in the what-if world: the change itself plus its ripple effects.</> : 'Run time forward to see the worlds drift apart.'}</p>
          {divOpt ? <EChart option={divOpt} height={220} /> : <div className="empty small">Run time forward.</div>}
        </div>
        <div className="card">
          <div className="row"><h3>Side by side over time</h3><span className="spacer" /><VarPicker value={tsVar} onChange={setTsVar} filter={v => !!v.flags?.includes('timeseries') && v.dtype !== 'cat'} /></div>
          {ts && <TSChart data={ts} v={tsVar} label={registry!.variables[tsVar]?.label ?? tsVar} height={200} startDate={dayToDate(status.date, -status.day)} forkDay={status.fork_day} />}
        </div>
      </div>

      <div className="section-title"><h2>What changed most</h2><span className="small muted">Averages in the what-if world vs the original. Size is judged relative to how much people normally differ.</span></div>
      <div className="grid g3">
        {vars.slice(0, 6).map(([k, v]: any) => {
          const spec = registry!.variables[k]
          const why = c.states[k]?.terms?.filter((t: any) => Math.abs(t.delta) > 1e-4).slice(0, 2) ?? []
          return (
            <div key={k} className="card change-card" style={{ cursor: 'pointer' }} onClick={() => setRoute(['variables', k])}>
              <div className="small muted">{spec?.label} <Evidence level={spec?.evidence} /></div>
              <div className="cc-big tabular">{v.delta > 0 ? '▲' : '▼'} {fmt(v.base, 3)} → {fmt(v.alt, 3)}</div>
              <div className="small"><b>{effectWord(v.delta_sd)}</b> · {(100 * v.changed_share).toFixed(0)}% of people affected</div>
              {why.length > 0 && <ul className="why-list">{why.map((t: any) => <li key={t.term}>{t.mechanism ? (registry!.mechanisms[t.mechanism]?.label ?? t.term) : 'after-effects of events'} ({t.delta > 0 ? '+' : ''}{fmt(t.delta, 3)})</li>)}</ul>}
            </div>
          )
        })}
      </div>

      <div className="grid g2" style={{ marginTop: 14 }}>
        <div className="card">
          <h3>Things that happened more or less often</h3><p className="hint">Life events since the split, what-if world vs original.</p>
          {changes.length === 0 && <div className="empty small">No clear differences yet. Run longer.</div>}
          {changes.map((e: any) => (
            <div key={e.type} className="row small" style={{ padding: '5px 0', borderBottom: '1px solid var(--grid)' }}>
              <span style={{ width: 24, textAlign: 'center', fontWeight: 700, color: e.delta > 0 ? 'var(--text-primary)' : 'var(--text-secondary)' }}>{e.delta > 0 ? '▲' : '▼'}</span>
              <span style={{ flex: 1 }}>{e.label}</span>
              <span className="tabular muted">{e.base.toLocaleString()} → {e.alt.toLocaleString()}</span>
              <b className="tabular" style={{ width: 60, textAlign: 'right' }}>{e.rel > 0 ? '+' : ''}{(100 * e.rel).toFixed(0)}%</b>
            </div>
          ))}
        </div>
        <div className="card">
          <div className="row"><h3>Why did feelings change?</h3><span className="spacer" />
            <select value={state} onChange={e => setState(e.target.value)} aria-label="Feeling">{STATES.map(s => <option key={s} value={s}>{registry!.variables[s]?.label}</option>)}</select></div>
          <p className="hint">The change in average {registry!.variables[state]?.label.toLowerCase()} ({st ? `${st.delta >= 0 ? '+' : ''}${fmt(st.delta, 4)}` : '—'}) split exactly into the model's forces. Red raises it, blue lowers it.</p>
          {st && <Decomposition rows={st.terms.slice(0, 8).map((t: any) => ({ label: t.mechanism ? (registry!.mechanisms[t.mechanism]?.label ?? t.term) : 'After-effects of events', value: t.delta, evidence: t.mechanism ? registry!.mechanisms[t.mechanism]?.evidence : undefined }))} />}
          <div className="small" style={{ marginTop: 8 }}><a href={`#/causal/${state}`}>Trace these forces in Cause & effect →</a></div>
        </div>
      </div>

      <div className="card" style={{ marginTop: 14 }}>
        <h3>People most affected</h3><p className="hint">Open someone to compare their two lives side by side.</p>
        <div className="grid g4">{Object.entries(c.most_affected).map(([v, rows]: any) => (
          <div key={v}><b className="small">{registry!.variables[v]?.label}</b>
            {rows.slice(0, 5).map((r: any) => <div key={r.id} className="row small" style={{ padding: '3px 0' }}><PersonLink id={r.id} name={r.name} /><span className="spacer" /><span className="tabular muted">{r.delta > 0 ? '+' : ''}{fmt(r.delta, 2)}</span></div>)}</div>
        ))}</div>
      </div>

      {adv && (
        <div className="grid g2" style={{ marginTop: 14 }}>
          <div className="card">
            <h3>All measure differences</h3><p className="hint">Mean difference (what-if − original) and in standard deviations.</p>
            <div className="scroll" style={{ maxHeight: 420 }}><table className="data"><thead><tr><th>Measure</th><th className="num">Original</th><th className="num">What-if</th><th className="num">Δ</th><th className="num">Δ / sd</th><th className="num">changed</th></tr></thead>
              <tbody>{vars.slice(0, 40).map(([k, v]: any) => (
                <tr key={k} className="click" onClick={() => setRoute(['variables', k])}><td>{registry!.variables[k]?.label ?? k}</td>
                  <td className="num">{fmt(v.base, 3)}</td><td className="num">{fmt(v.alt, 3)}</td><td className="num">{v.delta > 0 ? '+' : ''}{fmt(v.delta, 3)}</td>
                  <td className="num"><b>{v.delta_sd > 0 ? '+' : ''}{fmt(v.delta_sd, 3)}</b></td><td className="num">{(100 * v.changed_share).toFixed(1)}%</td></tr>))}</tbody></table></div>
          </div>
          <div className="card">
            <h3>All event differences</h3><p className="hint">Counts since the split.</p>
            <div className="scroll" style={{ maxHeight: 420 }}><table className="data"><thead><tr><th>Event</th><th className="num">Original</th><th className="num">What-if</th><th className="num">Change</th></tr></thead>
              <tbody>{c.events.slice(0, 60).map((e: any) => (
                <tr key={e.type}><td>{e.label}</td><td className="num">{e.base.toLocaleString()}</td><td className="num">{e.alt.toLocaleString()}</td>
                  <td className="num">{e.delta > 0 ? '+' : ''}{e.delta} ({e.rel > 0 ? '+' : ''}{(100 * e.rel).toFixed(0)}%)</td></tr>))}</tbody></table></div>
          </div>
        </div>
      )}
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
