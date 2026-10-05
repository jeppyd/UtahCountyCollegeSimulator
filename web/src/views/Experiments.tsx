// Research desk: repeat experiments with fresh dice (Monte Carlo) and map response curves (sweeps).
import { useEffect, useMemo, useState } from 'react'
import { fmt, quantile } from '../analysis'
import { api, STATIC } from '../api'
import { axisStyle, EChart, Evidence, series } from '../components'
import { useStore } from '../store'
import { PageHeader } from '../ui'

export default function Experiments() {
  return (
    <div className="page">
      <PageHeader id="experiments" eyebrow="Research desk" title="Experiments: many runs and sweeps"
        sub="One future is not the truth. Repeat an experiment from fresh worlds with different dice to see the spread of outcomes, or sweep a setting across a range to see how strongly the world responds."
        tips={[
          'Monte Carlo: pick changes, the number of seeds (dice), days and world size. Each scenario runs from fresh worlds; the same seed is shared across scenarios, so per-seed differences are paired.',
          'Sweep: pick a world setting or rule strength and a list of values. Each value runs for a few seeds; the band shows the 10–90% range.',
          'These run in separate processes and take a few minutes. The What-if page is the faster, single-world version.',
        ]} />
      <div className="grid g2">
        <MonteCarlo />
        <Sweep />
      </div>
      <Uncertainty />
    </div>
  )
}

const OUT_LABEL: Record<string, string> = {
  loneliness: 'Loneliness', mood: 'Mood', stress: 'Stress', financial_stress: 'Financial stress', faith_belief: 'Belief', attend_rate: 'Church attendance',
  n_friends: 'Friends', n_close_friends: 'Close friends', dates_30d: 'Dates / month', social_events_month: 'Social events / month',
  perceived_support: 'Support they believe they have', life_satisfaction: 'Life satisfaction', married_share: 'Married share',
  dating_share: 'Dating share', active_lds_share: 'Active (members)',
}

/** Two kinds of uncertainty: would the result survive a different random history (seeds), and would it survive
 *  different — still defensible — behavioral assumptions (parameter draws and alternative mechanism forms)? */
function Uncertainty() {
  const { presets } = useStore()
  const [res, setRes] = useState<any>(null)
  const [preset, setPreset] = useState('peer_support_program')
  const [draws, setDraws] = useState(12)
  const [seeds, setSeeds] = useState(3)
  const [days, setDays] = useState(90)
  const [scale, setScale] = useState(0.04)
  useEffect(() => { api.uncertainty().then(setRes).catch(() => {}) }, [])
  useEffect(() => {
    if (res?.state !== 'running') return
    const t = setInterval(() => api.uncertainty().then(setRes), 2500)
    return () => clearInterval(t)
  }, [res?.state])
  const run = async () => { await api.uncertaintyStart({ preset, draws, seeds, days, scale }); setRes({ state: 'running', progress: 0 }) }
  const rows = res?.outcomes ? Object.entries(res.outcomes).map(([k, d]: any) => ({ k, ...d }))
    .sort((a: any, b: any) => Math.abs(b.mean) / (b.sd_total + 1e-9) - Math.abs(a.mean) / (a.sd_total + 1e-9)) : []
  const nm = (k: string) => presets?.[k]?.name ?? k
  return (
    <div className="card" style={{ marginTop: 14 }}>
      <h3>How sure? Random history vs uncertain assumptions</h3>
      <p className="hint">Runs the What-if many times: across <b>seeds</b> (a different random social history, same assumptions) and across <b>parameter draws</b> (the model's uncertain rules varied within their declared ranges — wider for weaker evidence — including alternative mechanism forms). Each run is a paired Original/What-if from the same world. The bar splits the uncertainty of each effect into the part due to chance and the part due to assumptions; “same sign” is how often the effect points the same way.</p>
      {!STATIC && (
        <div className="row small" style={{ marginBottom: 8, flexWrap: 'wrap' }}>
          <select value={preset} onChange={e => setPreset(e.target.value)}>{presets && Object.entries(presets).map(([id, p]: any) => <option key={id} value={id}>{p.name}</option>)}</select>
          <label className="inline">parameter draws <input type="number" min={2} max={40} value={draws} onChange={e => setDraws(Number(e.target.value))} style={{ width: 56 }} /></label>
          <label className="inline">seeds <input type="number" min={2} max={10} value={seeds} onChange={e => setSeeds(Number(e.target.value))} style={{ width: 50 }} /></label>
          <label className="inline">days <input type="number" value={days} onChange={e => setDays(Number(e.target.value))} style={{ width: 64 }} /></label>
          <label className="inline">scale <input type="number" step={0.01} value={scale} onChange={e => setScale(Number(e.target.value))} style={{ width: 60 }} /></label>
          <button className="btn primary small" disabled={res?.state === 'running'} onClick={run}>{res?.state === 'running' ? `Running… ${res.progress ?? 0}/${res.total || draws * seeds}` : 'Run'}</button>
          <span className="muted">≈ {draws * seeds} paired runs; a few minutes</span>
        </div>
      )}
      {res?.state === 'error' && <div className="empty">{res.error}</div>}
      {res?.outcomes && (
        <>
          <div className="small muted" style={{ marginBottom: 6 }}>{nm(res.scenario?.[0]?.preset ?? '')}: {res.n_params} uncertain parameters × {res.n_draws} draws × {res.seeds.length} seeds, {res.days} days at scale {res.scale}.</div>
          <table className="data">
            <thead><tr><th>Outcome</th><th>Effect (10–90%)</th><th style={{ width: 170 }}>Uncertainty from chance · assumptions</th><th>Same sign</th><th>Driven most by</th></tr></thead>
            <tbody>{rows.map((r: any) => (
              <tr key={r.k}>
                <td>{OUT_LABEL[r.k] ?? r.k}</td>
                <td className="num tabular">{r.mean >= 0 ? '+' : ''}{fmt(r.mean, 4)} <span className="muted small">[{fmt(r.p10, 4)}, {fmt(r.p90, 4)}]</span></td>
                <td><span className="unc-split" title={`chance ${Math.round(100 * r.share_stochastic)}% · assumptions ${Math.round(100 * r.share_parametric)}%`}>
                  <i style={{ width: `${100 * r.share_stochastic}%` }} /><b style={{ width: `${100 * r.share_parametric}%` }} /></span></td>
                <td className="num tabular">{r.same_sign === null || r.same_sign === undefined ? '—' : `${Math.round(100 * r.same_sign)}%`}</td>
                <td className="small">{r.drivers?.length ? r.drivers.slice(0, 2).map((d: any) => <div key={d.param}>{d.param} <Evidence level={d.evidence} /> <span className="muted">ρ {d.rho > 0 ? '+' : ''}{d.rho}</span></div>) : <span className="muted">{r.drivers_note ?? 'no single assumption stands out'}</span>}</td>
              </tr>))}</tbody>
          </table>
          <div className="small muted" style={{ marginTop: 6 }}><span className="unc-key chance" /> chance (seeds) · <span className="unc-key assume" /> assumptions (parameter draws)</div>
        </>
      )}
    </div>
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
          <div className="row small" style={{ marginBottom: 6 }}>{presets && Object.entries(presets).map(([id, p]: any) => (
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
