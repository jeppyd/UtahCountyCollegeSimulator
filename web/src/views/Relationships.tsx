// Relationships: couples, friendships and how people meet — and in Compare, the couples and friendships
// that only exist in one of the two worlds.
import { useMemo, useState } from 'react'
import { api } from '../api'
import { axisStyle, EChart, PersonLink, tokens } from '../components'
import { pctStr, pretty } from '../fields'
import { G, Ticker, UBadge, uColor, useAsync, whatifKey } from '../game'
import { useLens, useStore } from '../store'
import NetworkView from './NetworkView'

const STATUS = ['talking', 'dating', 'engaged', 'married']

export default function Relationships({ tab: tab0 }: { tab?: string }) {
  const { dataVersion, setRoute, status } = useStore()
  const { u, compare, hasAlt } = useLens()
  const tab = tab0 ?? 'couples'
  const [st, setSt] = useState('')
  const R = useAsync(() => api.relationships(compare ? 'base' : u, st), [u, compare, st, dataVersion])
  const RA = useAsync(() => (compare ? api.relationships('alt', st) : Promise.resolve(null)), [compare, st, dataVersion])
  const d: any = R.data, da: any = RA.data
  return (
    <div className="page">
      <div className="scene-head" style={{ ['--sc' as any]: 'var(--s5)' }}>
        <span className="sh-icon">{G.rings}</span>
        <div className="sh-text"><h1>Relationships</h1><p>Who is talking, dating, engaged and married; the friendships that hold the world together; and where it all begins: apartments, wards, FHE groups, classes, apps.</p></div>
        {hasAlt && <span className="lens-note">{compare ? <>Showing <UBadge u="base" /> and <UBadge u="alt" /></> : <>Showing <UBadge u={u} /></>}</span>}
      </div>
      <div className="kpis" style={{ marginBottom: 14 }}>
        {STATUS.map(s => (
          <button key={s} className={`kpi click ${st === s ? 'sel' : ''}`} onClick={() => { setSt(st === s ? '' : s); setRoute(['relationships', 'couples']) }} title={`Show ${s} couples`}>
            <span className="k-label">{pretty(s)} couples</span>
            <span className="k-val tabular"><Ticker value={d?.couples_by_status?.[s] ?? 0} />{da ? <small className="u-alt-t"> → {da.couples_by_status?.[s] ?? 0}</small> : null}</span>
          </button>
        ))}
        <div className="kpi"><span className="k-label">Friendships</span><span className="k-val tabular"><Ticker value={d?.friendships ?? 0} />{da ? <small className="u-alt-t"> → {da.friendships.toLocaleString()}</small> : null}</span><span className="k-sub">{(d?.close ?? 0).toLocaleString()} close</span></div>
        <div className="kpi"><span className="k-label">Friends per person</span><span className="k-val tabular">{d ? d.mean_friends.toFixed(1) : '—'}{da ? <small className="u-alt-t"> → {da.mean_friends.toFixed(1)}</small> : null}</span><span className="k-sub">{d ? `${d.mean_close.toFixed(1)} close` : ''}</span></div>
        <div className="kpi" title="People present with no friend-level ties"><span className="k-label">Without a friend</span><span className="k-val tabular">{d ? d.isolated.toLocaleString() : '—'}{da ? <small className="u-alt-t"> → {da.isolated.toLocaleString()}</small> : null}</span><span className="k-sub">{d && status.present ? pctStr(d.isolated / status.present) : ''}</span></div>
      </div>
      <div className="tabs" style={{ marginBottom: 14 }}>
        {[['couples', 'Couples', 'rings'], ['network', 'Friendship network', 'network'], ['meet', 'How people meet', 'spark'], ...(hasAlt ? [['diff', 'Only in one world', 'butterfly']] : [])].map(([k, l, i]) => (
          <button key={k} className={tab === k ? 'on' : ''} onClick={() => setRoute(['relationships', k])}>{G[i]} {l}</button>
        ))}
      </div>
      {tab === 'couples' && <Couples d={d} da={da} st={st} setSt={setSt} />}
      {tab === 'network' && <NetworkView embedded />}
      {tab === 'meet' && <Meet d={d} da={da} />}
      {tab === 'diff' && hasAlt && <Diff />}
    </div>
  )
}

function Couples({ d, da, st, setSt }: { d: any; da: any; st: string; setSt: (s: string) => void }) {
  const list = (x: any, u?: 'base' | 'alt') => (
    <div className="couples">
      {(x?.couples ?? []).map((c: any) => (
        <div key={`${c.a}-${c.b}`} className="couple">
          <span className="cp-ring" style={{ color: `var(--s${STATUS.indexOf(c.status) + 4})` }}>{G.rings}</span>
          <div className="cp-names"><PersonLink id={c.a} name={c.a_name} /> & <PersonLink id={c.b} name={c.b_name} /></div>
          <span className="pill">{c.status}</span>
          <span className="small muted">{[c.since_date ? `together since ${new Date(c.since_date + 'T12:00:00').toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })}` : c.met_date ? `met ${new Date(c.met_date + 'T12:00:00').toLocaleDateString(undefined, { month: 'short', day: 'numeric' })}` : '', c.met ? `at ${pretty(c.met)}` : '', c.dates ? `${c.dates} dates` : ''].filter(Boolean).join(' · ')}</span>
          {u && null}
        </div>
      ))}
      {x && !x.couples?.length && <div className="empty small">No couples here yet.</div>}
      {!x && <div className="empty small">Loading…</div>}
    </div>
  )
  return (
    <div className="card">
      <div className="row" style={{ marginBottom: 8 }}>
        <span className="small muted">Newest first</span>
        <button className={`chip ${!st ? 'on' : ''}`} onClick={() => setSt('')}>All</button>
        {STATUS.map(s => <button key={s} className={`chip ${st === s ? 'on' : ''}`} onClick={() => setSt(s)}>{s}</button>)}
      </div>
      {da ? <div className="two-u"><div className="u-col card flat"><UBadge u="base" />{list(d, 'base')}</div><div className="u-col card flat alt"><UBadge u="alt" />{list(da, 'alt')}</div></div> : list(d)}
    </div>
  )
}

function Meet({ d, da }: { d: any; da: any }) {
  const { dataVersion } = useStore()
  const { u, compare } = useLens()
  const [romantic, setRomantic] = useState(true)
  const o = useAsync(() => api.origins(romantic, compare ? 'base' : u), [romantic, u, compare, dataVersion])
  const oa = useAsync(() => (compare ? api.origins(romantic, 'alt') : Promise.resolve(null)), [romantic, compare, dataVersion])
  const opt = useMemo(() => {
    if (!o.data) return null
    const ax = axisStyle(), t = tokens()
    const rows = Object.entries(o.data as any).filter(([k]) => k !== 'preexisting').sort((a: any, b: any) => b[1] - a[1]) as [string, number][]
    const A: any = oa.data
    return {
      grid: { left: 8, right: 40, top: A ? 26 : 6, bottom: 4, containLabel: true }, legend: A ? { top: 0, textStyle: { color: t.text2 } } : undefined, tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
      xAxis: { type: 'value', show: false }, yAxis: { type: 'category', inverse: true, data: rows.map(r => pretty(r[0])), ...ax, axisLine: { show: false } },
      series: [{ name: 'Original', type: 'bar', barMaxWidth: 14, data: rows.map(r => r[1]), itemStyle: { color: uColor(A ? 'base' : u), borderRadius: [0, 4, 4, 0] }, label: { show: !A, position: 'right', color: t.text2, fontSize: 11 } },
        ...(A ? [{ name: 'What-if', type: 'bar', barMaxWidth: 14, data: rows.map(r => A[r[0]] ?? 0), itemStyle: { color: uColor('alt'), borderRadius: [0, 4, 4, 0] } }] : [])],
    }
  }, [o.data, oa.data])
  const typeOpt = useMemo(() => {
    if (!d?.friends_by_type) return null
    const ax = axisStyle(), t = tokens()
    const rows = Object.entries(d.friends_by_type) as [string, number][]
    return {
      grid: { left: 8, right: 40, top: da ? 26 : 6, bottom: 4, containLabel: true }, legend: da ? { top: 0, textStyle: { color: t.text2 } } : undefined, tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
      xAxis: { type: 'value', show: false }, yAxis: { type: 'category', inverse: true, data: rows.map(r => pretty(r[0])), ...ax, axisLine: { show: false } },
      series: [{ name: 'Original', type: 'bar', barMaxWidth: 14, data: rows.map(r => r[1]), itemStyle: { color: uColor(da ? 'base' : u), borderRadius: [0, 4, 4, 0] }, label: { show: !da, position: 'right', color: t.text2, fontSize: 11 } },
        ...(da ? [{ name: 'What-if', type: 'bar', barMaxWidth: 14, data: rows.map(r => da.friends_by_type?.[r[0]] ?? 0), itemStyle: { color: uColor('alt'), borderRadius: [0, 4, 4, 0] } }] : [])],
    }
  }, [d, da])
  return (
    <div className="grid g2">
      <div className="card">
        <div className="card-head"><div><h3>Where relationships began</h3><p className="hint">{romantic ? 'Where every couple (past or present) first met.' : 'Where each friendship formed during the simulation.'}</p></div>
          <div className="seg small-seg"><button className={romantic ? 'on' : ''} onClick={() => setRomantic(true)}>Romances</button><button className={!romantic ? 'on' : ''} onClick={() => setRomantic(false)}>Friendships</button></div></div>
        {opt ? <EChart option={opt} height={320} /> : <div className="empty small">Loading…</div>}
      </div>
      <div className="card">
        <h3>What holds friendships together</h3>
        <p className="hint">Friendships by the kinds of ties between the two people (one friendship can be several: roommates who are also in the same ward).</p>
        {typeOpt ? <EChart option={typeOpt} height={320} /> : <div className="empty small">Loading…</div>}
      </div>
    </div>
  )
}

function Diff() {
  const { status, dataVersion, setRoute } = useStore()
  const r = useAsync(() => api.compareRelationships(), [dataVersion], { key: whatifKey(status, 'relationships') })
  const d: any = r.data
  if (!d) return <div className="empty">{r.error || 'Comparing…'}</div>
  const C = ({ c, u }: { c: any; u: 'base' | 'alt' }) => (
    <div className="couple">
      <span className="dot" style={{ background: `var(--u-${u})` }} />
      <div className="cp-names"><PersonLink id={c.a} name={c.a_name} /> & <PersonLink id={c.b} name={c.b_name} /></div>
      <span className="pill">{c.status_base ? `${c.status_base} → ` : ''}{c.status}</span>
      <span className="small muted">{c.met ? `met: ${c.met}` : ''}</span>
    </div>
  )
  return (
    <div className="grid g2">
      <div className="card"><h3><UBadge u="alt" /> Couples only in the What-if <span className="muted small">({d.couples.only_alt})</span></h3>{d.couples.examples_alt.map((c: any) => <C key={`${c.a}-${c.b}`} c={c} u="alt" />)}{!d.couples.examples_alt.length && <div className="empty small">None (yet).</div>}
        {d.couples.examples_changed.length > 0 && <><h3 style={{ marginTop: 12 }}>Same couple, different stage <span className="muted small">({d.couples.changed_status})</span></h3>{d.couples.examples_changed.map((c: any) => <C key={`c${c.a}-${c.b}`} c={c} u="alt" />)}</>}</div>
      <div className="card"><h3><UBadge u="base" /> Couples only in the Original <span className="muted small">({d.couples.only_base})</span></h3>{d.couples.examples_base.map((c: any) => <C key={`${c.a}-${c.b}`} c={c} u="base" />)}{!d.couples.examples_base.length && <div className="empty small">None (yet).</div>}
        <button className="btn small" style={{ marginTop: 10 }} onClick={() => setRoute(['whatif', 'relationships'])}>{G.butterfly} More in the butterfly view</button></div>
    </div>
  )
}
