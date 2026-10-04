import { useEffect, useMemo, useState } from 'react'
import { fmt } from '../analysis'
import { api } from '../api'
import { axisStyle, EChart, Loading, PersonLink, tokens } from '../components'
import { G, UBadge, uColor } from '../game'
import { useLens, useStore } from '../store'
import { Story } from '../ui'

export default function Events({ eventId, type0 }: { eventId?: number; type0?: string }) {
  const { dataVersion, status, setRoute, registry } = useStore()
  const { u, compare, hasAlt } = useLens()
  const universe = compare ? 'base' : u
  const [summary, setSummary] = useState<any>(null)
  const [summaryAlt, setSummaryAlt] = useState<any>(null)
  const [log, setLog] = useState<any>(null)
  const [type, setType] = useState(type0 ?? '')
  const [logU, setLogU] = useState<'base' | 'alt'>('base')
  useEffect(() => { if (type0 !== undefined) { setType(type0); setPage(0) } }, [type0])
  const [minSal, setMinSal] = useState(0.5)
  const [page, setPage] = useState(0)
  const lu = compare ? logU : universe
  useEffect(() => { api.eventsSummary(universe).then(setSummary).catch(() => {}) }, [universe, dataVersion])
  useEffect(() => { if (compare) api.eventsSummary('alt').then(setSummaryAlt).catch(() => {}); else setSummaryAlt(null) }, [compare, dataVersion])
  useEffect(() => { api.events({ u: lu, type, min_salience: type ? 0 : minSal, limit: 100, offset: page * 100 }).then(setLog).catch(() => {}) }, [lu, type, minSal, page, dataVersion])
  const opt = useMemo(() => {
    if (!summary) return null
    const ax = axisStyle()
    const rows = summary.types.filter((r: any) => r.type !== 'intervention_exposure').slice(0, 28)
    const alt = summaryAlt ? Object.fromEntries(summaryAlt.types.map((r: any) => [r.type, r.count])) : null
    return {
      grid: { left: 8, right: 60, top: alt ? 26 : 6, bottom: 6, containLabel: true },
      legend: alt ? { top: 0, textStyle: { color: tokens().text2 } } : undefined,
      tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' }, formatter: (ps: any) => { const r = rows[ps[0].dataIndex]; return `<b>${r.label}</b> (${r.category})<br/>${r.count.toLocaleString()} events${alt ? ` · What-if ${(alt[r.type] ?? 0).toLocaleString()}` : ''}<br/>${r.children.toLocaleString()} directly caused events` } },
      xAxis: { type: 'value', show: false },
      yAxis: { type: 'category', inverse: true, data: rows.map((r: any) => r.label), ...ax, axisLine: { show: false }, axisLabel: { ...ax.axisLabel, width: 170, overflow: 'truncate' } },
      series: [{ name: 'Original', type: 'bar', barMaxWidth: 12, data: rows.map((r: any) => r.count), itemStyle: { color: uColor(alt ? 'base' : universe), borderRadius: [0, 4, 4, 0] }, label: { show: !alt, position: 'right', color: tokens().text2, fontSize: 11, formatter: (p: any) => p.value.toLocaleString() } },
        ...(alt ? [{ name: 'What-if', type: 'bar', barMaxWidth: 12, data: rows.map((r: any) => alt[r.type] ?? 0), itemStyle: { color: uColor('alt'), borderRadius: [0, 4, 4, 0] } }] : [])],
      _rows: rows,
    }
  }, [summary, summaryAlt])
  if (eventId !== undefined) return <EventDetail id={eventId} />
  const tlabel = type ? registry?.events?.[type]?.label : ''
  return (
    <div className="page">
      <div className="scene-head" style={{ ['--sc' as any]: 'var(--s2)' }}>
        <span className="sh-icon">{G.events}</span>
        <div className="sh-text"><h1>{tlabel ? `Every “${tlabel.toLowerCase()}”` : 'Events'}</h1><p>Everything memorable that happens: first dates, breakups, faith crises, graduations, job losses, baptisms. Each event remembers what caused it: click one to follow the chain.</p></div>
        {hasAlt && <span className="lens-note">{compare ? <>Counting <UBadge u="base" /> and <UBadge u="alt" /></> : <UBadge u={u} />}</span>}
      </div>
      <div className="grid g2">
        <div className="card">
          <h3>Most frequent events</h3>
          <p className="hint">Since the start of the run ({status.day} days). Click a bar to read those stories; hover for how many further events each type set off.</p>
          {opt ? <EChart option={opt} height={summaryAlt ? 760 : 560} onClick={(p: any) => { setType((opt as any)._rows[p.dataIndex].type); setPage(0) }} /> : <Loading />}
        </div>
        <div className="card">
          <div className="card-head">
            <div><h3>The stories</h3><p className="hint">{log?.total?.toLocaleString() ?? '…'} events · newest first</p></div>
            <div className="row">
              {compare && <div className="seg small-seg"><button className={logU === 'base' ? 'on' : ''} onClick={() => setLogU('base')}>Original</button><button className={logU === 'alt' ? 'on' : ''} onClick={() => setLogU('alt')}>What-if</button></div>}
              <select value={type} onChange={e => { setType(e.target.value); setPage(0); if (e.target.value) setRoute(['events', 'type', e.target.value]); else setRoute(['events']) }}>
                <option value="">All types</option>
                {registry && Object.values(registry.events).sort((a: any, b: any) => a.label.localeCompare(b.label)).map((e: any) => <option key={e.id} value={e.id}>{e.label}</option>)}
              </select>
              <label className="inline small">salience ≥ <input type="number" step={0.1} min={0} max={1} value={minSal} onChange={e => setMinSal(Number(e.target.value))} style={{ width: 56 }} /></label>
            </div>
          </div>
          <div className="scroll" style={{ maxHeight: 520 }}>
            <table className="data"><thead><tr><th>Date</th><th>What happened</th><th /></tr></thead>
              <tbody>{dedupePairs(log?.events ?? []).map((e: any) => (
                <tr key={e.id}>
                  <td className="small tabular" style={{ whiteSpace: 'nowrap' }}>{new Date(e.date + 'T12:00:00').toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: '2-digit' })}</td>
                  <td><Story e={e} /></td>
                  <td className="small">{lu === 'base' && <a href={`#/events/${e.id}`}>why?</a>}</td>
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

/** Two-person events are logged once per person; show each pair once. */
function dedupePairs(evs: any[]) {
  const seen = new Set<string>()
  return evs.filter(e => {
    const k = e.b == null ? `${e.id}` : `${e.type}|${e.day}|${Math.min(e.a, e.b)}|${Math.max(e.a, e.b)}`
    if (seen.has(k)) return false
    seen.add(k)
    return true
  })
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
