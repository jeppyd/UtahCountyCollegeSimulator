import { useEffect, useMemo, useState } from 'react'
import { fmt, groupsOf, histogram, isCategorical, pearson, summary, values } from '../analysis'
import { api } from '../api'
import { axisStyle, DOMAIN_LABEL, EChart, Evidence, Loading, tokens } from '../components'
import { loadColumns, useStore } from '../store'
import { PageHeader } from '../ui'
import { dayToDate, TSChart } from './Overview'

export default function Variables({ id }: { id?: string }) {
  if (id) return <VariableDetail id={id} />
  return <VariableList />
}

function VariableList() {
  const { registry, setRoute } = useStore()
  const [q, setQ] = useState('')
  const [ev, setEv] = useState('')
  const [ent, setEnt] = useState('person')
  const vars = Object.values(registry!.variables).filter(v => v.entity === ent && (!ev || v.evidence === ev) && (!q || (v.label + v.id + (v.desc ?? '')).toLowerCase().includes(q.toLowerCase())))
  const byDomain: Record<string, any[]> = {}
  for (const v of vars) (byDomain[v.domain] ??= []).push(v)
  const counts: Record<string, number> = {}
  for (const v of Object.values(registry!.variables)) counts[v.evidence] = (counts[v.evidence] ?? 0) + 1
  return (
    <div className="page">
      <PageHeader id="variables" eyebrow="The model" title="Data dictionary"
        sub="Every measure the model tracks about people, relationships, places and the world, with what it means and how well it is grounded."
        tips={['Search or filter by area. Click a measure for its definition, distribution, history, what drives it and what it drives.', 'Evidence badges say where a measure comes from: observed in survey data, from research, calibrated, or assumed.']} />
      <div className="row" style={{ marginBottom: 12 }}>
        <input type="search" placeholder="Search variables" value={q} onChange={e => setQ(e.target.value)} />
        <select value={ent} onChange={e => setEnt(e.target.value)}>{['person', 'edge', 'unit', 'complex', 'world'].map(k => <option key={k}>{k}</option>)}</select>
        <div className="row">{Object.keys(registry!.evidence_levels).map(k => <button key={k} className={`btn small ${ev === k ? 'primary' : ''}`} onClick={() => setEv(ev === k ? '' : k)}><Evidence level={k} /> {counts[k] ?? 0}</button>)}</div>
      </div>
      {Object.entries(byDomain).map(([d, vs]) => (
        <div key={d} className="card" style={{ marginBottom: 12 }}>
          <h3>{DOMAIN_LABEL[d] ?? d} <span className="muted small">({vs.length})</span></h3>
          <table className="data"><thead><tr><th>Variable</th><th>Type</th><th>Kind</th><th>Updates</th><th>Evidence</th><th>Source / initialization</th></tr></thead>
            <tbody>{vs.map(v => (
              <tr key={v.id} className={v.entity === 'person' ? 'click' : ''} onClick={() => v.entity === 'person' && setRoute(['variables', v.id])}>
                <td><b>{v.label}</b><div className="small muted">{v.desc?.slice(0, 120)}</div></td>
                <td className="small">{v.dtype}{v.units ? ` · ${v.units}` : ''}</td><td className="small">{v.kind}</td><td className="small">{v.update}</td>
                <td><Evidence level={v.evidence} /></td><td className="small secondary">{(v.source ?? []).join(', ')}{v.init ? <div className="muted">{v.init}</div> : null}</td>
              </tr>))}</tbody></table>
        </div>
      ))}
    </div>
  )
}

const CORR_CANDIDATES = ['age', 'extraversion', 'neuroticism', 'conscientiousness', 'agreeableness', 'openness', 'faith_belief', 'attend_rate', 'religious_identity',
  'orthodoxy', 'loneliness', 'mood', 'stress', 'belonging', 'n_friends', 'n_close_friends', 'dates_30d', 'n_kissed', 'n_ncmo', 'financial_stress', 'gpa', 'work_hours',
  'study_hours', 'social_hours_week', 'romantic_longing', 'guilt', 'savings', 'rent', 'dist_campus_km', 'sleep_hours', 'social_media_hours', 'self_esteem', 'purpose',
  'sensation_seeking', 'chastity_commitment', 'kids_wanted', 'politics', 'parent_income', 'attractiveness', 'ward_belonging']

function VariableDetail({ id }: { id: string }) {
  const { registry, dataVersion, universe, status, setRoute } = useStore()
  const spec = registry!.variables[id]
  const [cols, setCols] = useState<any>(null)
  const [ts, setTs] = useState<any>(null)
  useEffect(() => {
    const cand = isCategorical(spec) ? [] : CORR_CANDIDATES.filter(c => c !== id)
    loadColumns([id, 'present', 'sex', 'school', 'activity', 'rel_status', ...cand], universe).then(setCols)
    if (spec.flags?.includes('timeseries')) api.timeseries(spec.dtype === 'cat' ? (spec.categories ?? []).map(c => `${id}=${c}`) : [id]).then(setTs).catch(() => {})
  }, [id, dataVersion, universe])
  const dist = useMemo(() => {
    if (!cols?.[id]) return null
    const mask = cols.present.data
    const ax = axisStyle()
    if (isCategorical(spec)) {
      const g = groupsOf(spec, cols[id], mask)
      const cnt = new Array(g.labels.length).fill(0); let tot = 0
      for (let i = 0; i < g.code.length; i++) if (mask[i] && g.code[i] >= 0) { cnt[g.code[i]]++; tot++ }
      return { option: { grid: { left: 50, right: 10, top: 10, bottom: 50 }, tooltip: { trigger: 'axis', valueFormatter: (v: number) => (100 * v).toFixed(1) + '%' }, xAxis: { type: 'category', data: g.labels, ...ax }, yAxis: { type: 'value', ...ax, axisLabel: { ...ax.axisLabel, formatter: (v: number) => (100 * v).toFixed(0) + '%' } }, series: [{ type: 'bar', barMaxWidth: 24, data: cnt.map(c => c / (tot || 1)), itemStyle: { borderRadius: [4, 4, 0, 0] } }] } }
    }
    const v = values(cols[id], mask)
    const h = histogram(v, 30)
    return { stats: summary(v), option: { grid: { left: 50, right: 10, top: 10, bottom: 30 }, tooltip: { trigger: 'axis' }, xAxis: { type: 'category', data: h.edges.slice(0, -1).map(e => fmt(e)), ...ax }, yAxis: { type: 'value', ...ax }, series: [{ type: 'bar', barCategoryGap: '8%', data: h.counts, itemStyle: { borderRadius: [3, 3, 0, 0] } }] } }
  }, [cols])
  const bySub = useMemo(() => {
    if (!cols?.[id] || isCategorical(spec)) return null
    const mask = cols.present.data
    const out: any[] = []
    for (const g of ['sex', 'school', 'activity', 'rel_status']) {
      const gs = registry!.variables[g]
      const gg = groupsOf(gs, cols[g], mask)
      gg.labels.forEach((lab, k) => {
        const vv: number[] = []
        for (let i = 0; i < gg.code.length; i++) if (mask[i] && gg.code[i] === k && !Number.isNaN(cols[id].data[i])) vv.push(cols[id].data[i])
        if (vv.length >= 10) out.push({ g: gs.label, lab, n: vv.length, m: summary(vv).mean })
      })
    }
    return out
  }, [cols])
  const corr = useMemo(() => {
    if (!cols?.[id] || isCategorical(spec)) return []
    return CORR_CANDIDATES.filter(c => c !== id && cols[c]).map(c => ({ c, r: pearson(cols[id].data, cols[c].data, cols.present.data).r })).filter(x => !Number.isNaN(x.r)).sort((a, b) => Math.abs(b.r) - Math.abs(a.r)).slice(0, 12)
  }, [cols])
  if (!spec) return <div className="page"><div className="empty">Unknown variable</div></div>
  const into = Object.values(registry!.mechanisms).filter((m: any) => (Array.isArray(m.target) ? m.target : [m.target]).includes(id))
  const from = Object.values(registry!.mechanisms).filter((m: any) => m.sources?.includes(id) || m.moderators?.includes(id))
  const evs = Object.values(registry!.events).filter((e: any) => e.effects?.some((f: any) => f.var === id || Object.keys(f.mods ?? {}).includes(id)))
  return (
    <div className="page">
      <button className="btn small" onClick={() => setRoute(['variables'])}>‹ Registry</button>
      <div className="row" style={{ marginTop: 10 }}><h1 style={{ margin: 0 }}>{spec.label}</h1><Evidence level={spec.evidence} /><span className="muted">{id}</span></div>
      <p className="sub" style={{ marginTop: 6 }}>{spec.desc || 'No description.'}</p>
      <div className="row small" style={{ marginBottom: 14 }}>
        <span className="pill">{spec.entity}</span><span className="pill">{spec.domain}</span><span className="pill">{spec.kind}</span><span className="pill">{spec.dtype}{spec.units ? ` · ${spec.units}` : ''}</span>
        <span className="pill">updates: {spec.update}</span>{spec.range && <span className="pill">range {spec.range.join(' – ')}</span>}
        {spec.source?.length ? <span className="pill">source: {spec.source.join(', ')}</span> : null}
        <button className="btn small" onClick={() => setRoute(['causal', id])}>Open in causal web</button>
      </div>
      {spec.init && <div className="banner"><b>Initialization:</b> {spec.init}</div>}
      <div className="grid g2">
        <div className="card"><h3>Distribution now</h3><p className="hint">Everyone present, {universe === 'alt' ? 'intervention' : 'baseline'} universe.</p>
          {dist ? <EChart option={dist.option} height={240} /> : <Loading />}
          {dist?.stats && <div className="row small tabular">{(['n', 'mean', 'sd', 'p10', 'median', 'p90'] as const).map(k => <span key={k} className="pill">{k} {fmt((dist.stats as any)[k], 3)}</span>)}</div>}
        </div>
        {ts ? (spec.dtype === 'cat'
          ? <TSChart data={ts} v={`${id}=${(spec.categories ?? [])[spec.categories!.length - 1]}`} label={`Share: ${spec.label} = ${(spec.categories ?? []).slice(-1)[0]}`} startDate={dayToDate(status.date, -status.day)} forkDay={status.fork_day} height={240} />
          : <TSChart data={ts} v={id} label="Over time (population mean)" startDate={dayToDate(status.date, -status.day)} forkDay={status.fork_day} height={240} />)
          : <div className="card"><h3>Over time</h3><div className="muted small">Not recorded as a daily series (add the <span className="kbd">timeseries</span> flag in the registry to track it).</div></div>}
      </div>
      <div className="grid g3" style={{ marginTop: 14 }}>
        <div className="card"><h3>Subgroups</h3><div className="scroll" style={{ maxHeight: 340 }}><table className="data"><tbody>{bySub?.map((r, k) => <tr key={k}><td className="small muted">{r.g}</td><td>{r.lab}</td><td className="num">{fmt(r.m, 3)}</td><td className="num muted small">n {r.n}</td></tr>)}</tbody></table></div></div>
        <div className="card"><h3>Strongest correlates</h3><p className="hint">Simulated associations (Pearson r), not causal effects.</p>
          <table className="data"><tbody>{corr.map(x => <tr key={x.c} className="click" onClick={() => setRoute(['variables', x.c])}><td>{registry!.variables[x.c]?.label}</td><td className="num">{x.r > 0 ? '+' : ''}{fmt(x.r, 3)}</td>
            <td style={{ width: 90 }}><div style={{ height: 8, background: 'var(--surface-2)', borderRadius: 4, position: 'relative' }}><div style={{ position: 'absolute', left: x.r >= 0 ? '50%' : `${50 - 50 * Math.abs(x.r)}%`, width: `${50 * Math.abs(x.r)}%`, height: 8, borderRadius: 4, background: x.r >= 0 ? 'var(--s8)' : 'var(--s1)' }} /></div></td></tr>)}</tbody></table></div>
        <div className="card"><h3>Mechanisms & events</h3>
          <div className="small"><b>Set by</b>{into.length ? into.map((m: any) => <div key={m.id}><a href={`#/mechanisms/${m.id}`}>{m.label}</a> <Evidence level={m.evidence} /></div>) : <div className="muted">— (initialized, then static or event-driven)</div>}</div>
          <div className="small" style={{ marginTop: 8 }}><b>Feeds into</b>{from.length ? from.map((m: any) => <div key={m.id}><a href={`#/mechanisms/${m.id}`}>{m.label}</a> <Evidence level={m.evidence} /></div>) : <div className="muted">—</div>}</div>
          <div className="small" style={{ marginTop: 8 }}><b>Events that move or moderate it</b>{evs.length ? evs.map((e: any) => <div key={e.id}>{e.label}</div>) : <div className="muted">—</div>}</div>
        </div>
      </div>
    </div>
  )
}

export function Dummy() { return tokens() }
