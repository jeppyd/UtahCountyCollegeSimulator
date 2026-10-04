import { useEffect, useMemo, useState } from 'react'
import { fmt } from '../analysis'
import { api } from '../api'
import { axisStyle, EChart, Loading, PersonLink, VarPicker } from '../components'
import { favg, fdelta, fpair } from '../fields'
import { G, UBadge } from '../game'
import { useLens, useStore } from '../store'

export default function Places({ kind, id }: { kind?: string; id?: number }) {
  if (kind && id !== undefined) return <Institution kind={kind} id={id} />
  return <PlaceList />
}

function PlaceList() {
  const { dataVersion, setRoute, registry } = useStore()
  const { u: universe, compare, hasAlt } = useLens()
  const [v, setV] = useState('loneliness')
  const [tab, setTab] = useState<'complex' | 'ward'>('complex')
  const [rows, setRows] = useState<any[]>([])
  const [cmp, setCmp] = useState<any[] | null>(null)
  const [sort, setSort] = useState(-1)
  useEffect(() => { (tab === 'complex' ? api.complexes(v, universe) : api.wards(v, universe)).then(setRows).catch(() => setRows([])) }, [v, tab, universe, dataVersion])
  useEffect(() => { if (compare) api.comparePlaces(tab, v).then(setCmp).catch(() => setCmp([])); else setCmp(null) }, [v, tab, compare, dataVersion])
  const sorted = useMemo(() => [...rows].filter(r => r.n >= 5).sort((a, b) => sort * ((a.mean ?? 0) - (b.mean ?? 0))), [rows, sort])
  const spec = registry!.variables[v]
  return (
    <div className="page">
      <div className="scene-head" style={{ ['--sc' as any]: 'var(--s4)' }}>
        <span className="sh-icon">{G.places}</span>
        <div className="sh-text"><h1>Places</h1><p>Apartment complexes, wards, schools and employers, described by the people in them. Rank places by any field, then open one to see who lives there and what happens there.</p></div>
        {hasAlt && <span className="lens-note">{compare ? <><UBadge u="base" /> vs <UBadge u="alt" /></> : <UBadge u={universe} />}</span>}
      </div>
      <div className="row" style={{ marginBottom: 12 }}>
        <div className="seg"><button className={tab === 'complex' ? 'on' : ''} onClick={() => setTab('complex')}>Housing complexes</button><button className={tab === 'ward' ? 'on' : ''} onClick={() => setTab('ward')}>Wards</button></div>
        <span className="small muted">rank by</span><VarPicker value={v} onChange={setV} filter={s => !!s.mappable && s.dtype !== 'cat'} />
        <button className="btn small" onClick={() => setRoute(['places', 'school', '1'])}>BYU</button>
        <button className="btn small" onClick={() => setRoute(['places', 'school', '2'])}>UVU</button>
        <span className="spacer" />
        <button className="btn small" onClick={() => setRoute(['map', `${tab === 'complex' ? 'complexes' : 'wards'}:${v}`])}>{G.map} On the map</button>
      </div>
      {compare && cmp && (
        <div className="card" style={{ marginBottom: 14 }}>
          <h3>Where the What-if changed things most</h3>
          <p className="hint">Average {spec?.label.toLowerCase()} per place in both worlds, biggest difference first.</p>
          <div className="scroll" style={{ maxHeight: 320 }}>
            <table className="data"><thead><tr><th>{tab === 'complex' ? 'Complex' : 'Ward'}</th><th className="num"><UBadge u="base" /></th><th className="num"><UBadge u="alt" /></th><th className="num">Difference</th><th className="num">Residents</th></tr></thead>
              <tbody>{cmp.slice(0, 40).map(r => (
                <tr key={r.id} className="click" onClick={() => setRoute(['places', tab, String(r.id)])}><td>{r.name}</td><td className="num tabular">{fpair(spec, r.base, r.alt)[0]}</td><td className="num tabular">{fpair(spec, r.base, r.alt)[1]}</td><td className="num tabular"><b>{fdelta(spec, r.delta ?? 0)}</b></td><td className="num tabular">{r.n_base} → {r.n_alt}</td></tr>
              ))}</tbody></table>
          </div>
        </div>
      )}
      <div className="card">
        <div className="scroll" style={{ maxHeight: 640 }}>
          <table className="data"><thead><tr><th>{tab === 'complex' ? 'Complex' : 'Ward'}</th><th>Kind</th><th className="num">Residents</th><th className="num" style={{ cursor: 'pointer' }} onClick={() => setSort(-sort)}>Mean {sort > 0 ? '↑' : '↓'}</th><th style={{ width: '30%' }}></th></tr></thead>
            <tbody>{sorted.map(r => {
              const ms = sorted.map(x => x.mean ?? 0); const lo = Math.min(...ms), hi = Math.max(...ms)
              return (
                <tr key={r.id} className="click" onClick={() => setRoute(['places', tab, String(r.id)])}>
                  <td>{r.name ?? `${r.kind.replace(/_/g, ' ')} ward #${r.id}`}{r.contracted && <span className="pill" style={{ marginLeft: 6 }}>BYU contracted</span>}</td>
                  <td className="small">{(r.kind ?? '').replace(/_/g, ' ')}</td><td className="num">{r.n}</td><td className="num">{fmt(r.mean, 3)}</td>
                  <td><div style={{ height: 8, borderRadius: 4, background: 'var(--surface-2)' }}><div style={{ height: 8, borderRadius: 4, width: `${100 * ((r.mean ?? 0) - lo) / ((hi - lo) || 1)}%`, background: 'var(--s1)' }} /></div></td>
                </tr>)
            })}</tbody></table>
        </div>
      </div>
    </div>
  )
}

function Institution({ kind, id }: { kind: string; id: number }) {
  const { dataVersion, setRoute, registry } = useStore()
  const { u: universe } = useLens()
  const [d, setD] = useState<any>(null)
  const [err, setErr] = useState('')
  useEffect(() => { api.institution(kind, id, universe).then(setD).catch(e => setErr(String(e.message ?? e))) }, [kind, id, universe, dataVersion])
  if (err) return <div className="page"><div className="empty">{err}</div></div>
  if (!d) return <Loading />
  const ax = axisStyle()
  const compOpt = (key: string) => {
    const rows = Object.entries(d.composition[key] ?? {}) as [string, number][]
    return {
      grid: { left: 110, right: 40, top: 4, bottom: 4 }, tooltip: { trigger: 'item' },
      xAxis: { type: 'value', show: false },
      yAxis: { type: 'category', inverse: true, data: rows.map(r => r[0].replace(/_/g, ' ')), ...ax, axisLine: { show: false } },
      series: [{ type: 'bar', barWidth: 12, data: rows.map(r => r[1]), itemStyle: { borderRadius: [0, 4, 4, 0] }, label: { show: true, position: 'right', fontSize: 11 } }],
    }
  }
  return (
    <div className="page">
      <button className="btn small" onClick={() => setRoute(['places'])}>‹ Places</button>
      <div className="scene-head" style={{ ['--sc' as any]: 'var(--s4)', marginTop: 10 }}><span className="sh-icon">{G[kind === 'school' ? 'school' : kind === 'ward' ? 'faith' : kind === 'employer' ? 'work' : 'places']}</span><div className="sh-text"><h1>{d.name}</h1></div></div>
      <p className="sub">{d.n.toLocaleString()} people present · {d.friend_ties_inside.toLocaleString()} friendships inside (density {fmt(d.density, 4)})</p>
      <div className="kpis" style={{ marginBottom: 14 }}>
        {Object.entries(d.stats).slice(0, 12).map(([k, v]: any) => <div key={k} className="kpi click" onClick={() => setRoute(['explore', k])}><span className="k-label">{registry!.variables[k]?.label ?? k.replace(/_/g, ' ')}</span><span className="k-val tabular">{favg(registry!.variables[k], v)}</span></div>)}
      </div>
      <div className="grid g3">
        {['rel_status', 'activity', 'role', 'mission_status', 'sex', 'school'].map(k => (
          <div className="card" key={k}><h3>{registry!.variables[k]?.label ?? k.replace(/_/g, ' ')}</h3><EChart option={compOpt(k)} height={150} /></div>
        ))}
      </div>
      <div className="grid g2" style={{ marginTop: 14 }}>
        <div className="card"><h3>Recent events here (60 days)</h3>
          <table className="data"><tbody>{d.recent_events.map((e: any) => <tr key={e.type}><td>{e.label}</td><td className="num">{e.count}</td></tr>)}</tbody></table></div>
        <div className="card"><h3>Members</h3><div className="scroll" style={{ maxHeight: 300 }}>{d.members.map((m: any) => <span key={m.id} style={{ display: 'inline-block', marginRight: 10 }}><PersonLink id={m.id} name={m.name} /></span>)}</div></div>
      </div>
    </div>
  )
}
