import { useEffect, useMemo, useState } from 'react'
import { fmt } from '../analysis'
import { api } from '../api'
import { axisStyle, EChart, Loading, PersonLink, tokens } from '../components'
import { useStore } from '../store'

export default function Events({ eventId }: { eventId?: number }) {
  const { universe, dataVersion, status, setRoute, registry } = useStore()
  const [summary, setSummary] = useState<any>(null)
  const [log, setLog] = useState<any>(null)
  const [type, setType] = useState('')
  const [minSal, setMinSal] = useState(0.5)
  const [page, setPage] = useState(0)
  useEffect(() => { api.eventsSummary(universe).then(setSummary).catch(() => {}) }, [universe, dataVersion])
  useEffect(() => { api.events({ u: universe, type, min_salience: minSal, limit: 100, offset: page * 100 }).then(setLog).catch(() => {}) }, [universe, type, minSal, page, dataVersion])
  const opt = useMemo(() => {
    if (!summary) return null
    const ax = axisStyle()
    const rows = summary.types.slice(0, 28)
    return {
      grid: { left: 190, right: 60, top: 6, bottom: 6 },
      tooltip: { trigger: 'item', formatter: (p: any) => { const r = rows[p.dataIndex]; return `<b>${r.label}</b> (${r.category})<br/>${r.count.toLocaleString()} events<br/>${r.children.toLocaleString()} directly caused events` } },
      xAxis: { type: 'value', show: false },
      yAxis: { type: 'category', inverse: true, data: rows.map((r: any) => r.label), ...ax, axisLine: { show: false } },
      series: [{ type: 'bar', barWidth: 12, data: rows.map((r: any) => r.count), itemStyle: { borderRadius: [0, 4, 4, 0] }, label: { show: true, position: 'right', color: tokens().text2, fontSize: 11, formatter: (p: any) => p.value.toLocaleString() } }],
    }
  }, [summary])
  if (eventId !== undefined) return <EventDetail id={eventId} />
  return (
    <div className="page">
      <h1>Events</h1>
      <p className="sub">Salient events form the simulation's memory and its causal provenance: each event records the event that caused it, so chains like <i>FHE group → first date → DTR → engagement → wedding → move → new ward</i> can be followed.</p>
      <div className="grid g2">
        <div className="card">
          <h3>Most frequent events</h3>
          <p className="hint">Since the start of the run ({status.day} days). Hover for how many downstream events each type directly caused.</p>
          {opt ? <EChart option={opt} height={560} onClick={(p: any) => { setType(summary.types[p.dataIndex].type); setPage(0) }} /> : <Loading />}
        </div>
        <div className="card">
          <div className="card-head">
            <div><h3>Event log</h3><p className="hint">{log?.total?.toLocaleString() ?? '…'} events · newest first</p></div>
            <div className="row">
              <select value={type} onChange={e => { setType(e.target.value); setPage(0) }}>
                <option value="">All types</option>
                {registry && Object.values(registry.events).sort((a: any, b: any) => a.label.localeCompare(b.label)).map((e: any) => <option key={e.id} value={e.id}>{e.label}</option>)}
              </select>
              <label className="inline small">salience ≥ <input type="number" step={0.1} min={0} max={1} value={minSal} onChange={e => setMinSal(Number(e.target.value))} style={{ width: 56 }} /></label>
            </div>
          </div>
          <div className="scroll" style={{ maxHeight: 520 }}>
            <table className="data"><thead><tr><th>Date</th><th>Event</th><th>Who</th><th>Caused by</th></tr></thead>
              <tbody>{log?.events.map((e: any) => (
                <tr key={e.id} className="click" onClick={() => setRoute(['events', String(e.id)])}>
                  <td className="small tabular">{e.date}</td><td>{e.label}</td>
                  <td className="small"><PersonLink id={e.a} name={e.a_name} />{e.b_name && <> · <PersonLink id={e.b} name={e.b_name} /></>}</td>
                  <td className="small muted">{e.cause !== null ? `#${e.cause}` : ''}{e.mechanism ? ` · ${e.mechanism}` : ''}</td>
                </tr>))}</tbody>
            </table>
          </div>
          <div className="row" style={{ marginTop: 8 }}>
            <button className="btn small" disabled={page === 0} onClick={() => setPage(page - 1)}>‹ newer</button>
            <button className="btn small" disabled={!log || (page + 1) * 100 >= log.total} onClick={() => setPage(page + 1)}>older ›</button>
          </div>
        </div>
      </div>
      {summary && (
        <div className="card" style={{ marginTop: 14 }}>
          <h3>Event types by consequence</h3>
          <p className="hint">“Caused” counts events whose recorded parent is an event of this type — a crude measure of how consequential a type is within the simulation.</p>
          <div className="scroll"><table className="data"><thead><tr><th>Event</th><th>Category</th><th className="num">Count</th><th className="num">Per 1,000 people</th><th className="num">Directly caused</th><th className="num">Salience</th></tr></thead>
            <tbody>{[...summary.types].sort((a: any, b: any) => b.children - a.children).map((r: any) => (
              <tr key={r.type} className="click" onClick={() => { setType(r.type); setPage(0) }}><td>{r.label}</td><td className="small">{r.category}</td><td className="num">{r.count.toLocaleString()}</td>
                <td className="num">{fmt(1000 * r.count / (status.present || 1), 1)}</td><td className="num">{r.children.toLocaleString()}</td><td className="num">{r.salience}</td></tr>))}</tbody></table></div>
        </div>
      )}
    </div>
  )
}

function EventDetail({ id }: { id: number }) {
  const [d, setD] = useState<any>(null)
  const [err, setErr] = useState('')
  const setRoute = useStore(s => s.setRoute)
  useEffect(() => { api.event(id).then(setD).catch(e => setErr(String(e.message ?? e))) }, [id])
  if (err) return <div className="page"><div className="empty">{err}</div></div>
  if (!d) return <Loading />
  const Ev = ({ e, focus = false }: { e: any; focus?: boolean }) => (
    <div className="card" style={{ padding: 10, borderColor: focus ? 'var(--accent)' : undefined }}>
      <div className="small muted tabular">{e.date} · {e.category}{e.mechanism ? ` · ${e.mechanism}` : ''}</div>
      <div><a href={`#/events/${e.id}`}><b>{e.label}</b></a> — <PersonLink id={e.a} name={e.a_name} />{e.b_name && <> & <PersonLink id={e.b} name={e.b_name} /></>}</div>
    </div>
  )
  const chain = [...d.ancestors].reverse()
  return (
    <div className="page">
      <button className="btn small" onClick={() => setRoute(['events'])}>‹ All events</button>
      <h1 style={{ marginTop: 10 }}>Why did this happen?</h1>
      <p className="sub">The recorded causal chain inside the simulation (simulation provenance, not proof of real-world causality). Mechanisms named on each step are in the mechanism registry.</p>
      <div className="grid g2">
        <div>
          <h3>Causal ancestry</h3>
          {chain.length === 0 && <div className="muted small">No recorded parent: this event arose from an agent's state and chance (see the person's "why" panel).</div>}
          {chain.map((e: any) => <div key={e.id}><Ev e={e} /><div style={{ textAlign: 'center', color: 'var(--text-muted)' }}>↓</div></div>)}
          <Ev e={d.event} focus />
        </div>
        <div>
          <h3>Downstream consequences</h3>
          {d.descendants.length === 0 && <div className="muted small">No recorded consequences (yet).</div>}
          {d.descendants.map((e: any) => <div key={e.id} style={{ marginBottom: 6 }}><Ev e={e} /></div>)}
        </div>
      </div>
    </div>
  )
}
