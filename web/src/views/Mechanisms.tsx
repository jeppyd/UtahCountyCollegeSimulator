import { useState } from 'react'
import { Evidence } from '../components'
import { useStore } from '../store'
import { PageHeader } from '../ui'
import { MechBrief } from './CausalWeb'

export default function Mechanisms({ id }: { id?: string }) {
  const { registry, setRoute } = useStore()
  const [q, setQ] = useState('')
  const [ev, setEv] = useState('')
  const all = Object.values(registry!.mechanisms) as any[]
  if (id && registry!.mechanisms[id]) {
    const m = registry!.mechanisms[id]
    const tg = Array.isArray(m.target) ? m.target : [m.target]
    const link = (v: string) => registry!.variables[v] ? <a key={v} href={`#/variables/${v}`} style={{ marginRight: 8 }}>{registry!.variables[v].label}</a> : <span key={v} className="muted" style={{ marginRight: 8 }}>{v}</span>
    return (
      <div className="page">
        <button className="btn small" onClick={() => setRoute(['mechanisms'])}>‹ Mechanisms</button>
        <div className="row" style={{ marginTop: 10 }}><h1 style={{ margin: 0 }}>{m.label}</h1><Evidence level={m.evidence} /><span className="muted">{m.id}</span></div>
        <div className="grid g2" style={{ marginTop: 14 }}>
          <div className="card"><h3>Specification</h3><MechBrief m={m} />
            {m.applicability && <div className="small" style={{ marginTop: 6 }}><b>Applicability</b>: {m.applicability}</div>}
            <div className="small" style={{ marginTop: 6 }}><b>Timescale</b>: {m.timescale} · <b>delay</b>: {m.delay}</div></div>
          <div className="card"><h3>Inputs → output</h3>
            <div className="small"><b>Sources</b>: {m.sources.map(link)}</div>
            {m.moderators?.length > 0 && <div className="small" style={{ marginTop: 6 }}><b>Moderators</b>: {m.moderators.map(link)}</div>}
            {m.context?.length > 0 && <div className="small" style={{ marginTop: 6 }}><b>Other inputs</b>: <span className="secondary">{m.context.join(', ')}</span></div>}
            <div className="small" style={{ marginTop: 6 }}><b>Target</b>: {tg.map(link)}</div>
            <p className="small secondary" style={{ marginTop: 10 }}>Every parameter can be changed per run (Scenario lab → custom intervention → mechanism strength) or swept for sensitivity analysis.</p>
            <button className="btn small" onClick={() => setRoute(['causal', tg[0]])}>See in causal web</button></div>
        </div>
      </div>
    )
  }
  const rows = all.filter(m => (!ev || m.evidence === ev) && (!q || (m.label + m.id + m.form + (m.desc ?? '')).toLowerCase().includes(q.toLowerCase())))
  const bySys: Record<string, any[]> = {}
  for (const m of rows) (bySys[m.system] ??= []).push(m)
  const counts: Record<string, number> = {}
  for (const m of all) counts[m.evidence] = (counts[m.evidence] ?? 0) + 1
  return (
    <div className="page">
      <PageHeader id="mechanisms" eyebrow="The model" title="Rules"
        sub="Every behavioral rule in the model: what it affects, its formula and strengths, and the evidence behind it." />
      <div className="row" style={{ marginBottom: 12 }}>
        <input type="search" placeholder="Search mechanisms" value={q} onChange={e => setQ(e.target.value)} />
        {Object.keys(registry!.evidence_levels).map(k => <button key={k} className={`btn small ${ev === k ? 'primary' : ''}`} onClick={() => setEv(ev === k ? '' : k)}><Evidence level={k} /> {counts[k] ?? 0}</button>)}
      </div>
      {Object.entries(bySys).map(([s, ms]) => (
        <div key={s} className="card" style={{ marginBottom: 12 }}>
          <h3>{s} <span className="muted small">({ms.length})</span></h3>
          <table className="data"><thead><tr><th>Mechanism</th><th>Target</th><th>Form</th><th>Evidence</th></tr></thead>
            <tbody>{ms.map(m => (
              <tr key={m.id} className="click" onClick={() => setRoute(['mechanisms', m.id])}>
                <td><b>{m.label}</b><div className="small muted">{m.id}</div></td>
                <td className="small">{(Array.isArray(m.target) ? m.target : [m.target]).join(', ')}</td>
                <td className="small secondary">{m.form}</td><td><Evidence level={m.evidence} /></td>
              </tr>))}</tbody></table>
        </div>
      ))}
    </div>
  )
}
