import { useEffect, useMemo, useState } from 'react'
import { fmt, useCohortData } from '../analysis'
import { api, STATIC } from '../api'
import { CohortBar, Loading, QUICK } from '../components'
import { nameOf } from '../names'
import { useStore } from '../store'
import { FollowButton, PageHeader, Story } from '../ui'

const COLS: [string, string][] = [['age', 'Age'], ['role', 'Role'], ['rel_status', 'Relationship'], ['activity', 'Church activity'],
  ['mission_status', 'Mission'], ['living', 'Living'], ['n_friends', 'Friends'], ['loneliness', 'Loneliness'], ['mood', 'Happiness'], ['dates_30d', 'Dates/month']]
const NUM = ['age', 'n_friends', 'loneliness', 'mood', 'dates_30d']

export default function People() {
  const { setRoute, setCohort, followed, following, universe, dataVersion } = useStore()
  const data = useCohortData(['sex', ...COLS.map(c => c[0])])
  const [tab, setTab] = useState<'all' | 'following'>('all')
  const [sort, setSort] = useState<[string, number]>(['loneliness', -1])
  const [q, setQ] = useState('')
  const [page, setPage] = useState(0)
  const [staticIds, setStaticIds] = useState<Set<number> | null>(null)
  const [mine, setMine] = useState<any[] | null>(null)
  const ids = followed()
  useEffect(() => { if (STATIC) api.staticPeople().then(x => setStaticIds(new Set(x))) }, [])
  useEffect(() => { if (tab === 'following') { setMine(null); api.brief(ids, universe).then(setMine).catch(() => setMine([])) } }, [tab, JSON.stringify(following), universe, dataVersion])
  const rows = useMemo(() => {
    if (!data.mask) return []
    const out0: number[] = []
    for (let i = 0; i < data.mask.length; i++) if (data.mask[i] && (!staticIds || staticIds.has(i))) out0.push(i)
    const sx = data.cols.sex.data
    let out = out0
    if (q.trim()) {
      const ql = q.toLowerCase()
      out = out0.filter(i => String(i) === ql || nameOf(i, sx[i]).toLowerCase().includes(ql))
    }
    const c = data.cols[sort[0]]
    if (c) out.sort((a, b) => ((c.data[a] as number) - (c.data[b] as number)) * sort[1])
    return out
  }, [data, sort, q, staticIds])
  const show = rows.slice(page * 100, page * 100 + 100)
  const fmtCell = (v: string, i: number) => {
    const c = data.cols[v]
    if (!c) return ''
    if (c.categories) return c.categories[c.data[i]].replace(/_/g, ' ')
    return fmt(c.data[i], v === 'age' ? 0 : v === 'n_friends' ? 0 : 2)
  }
  return (
    <div className="page">
      <PageHeader id="people" eyebrow="Follow lives" title="People"
        sub="Every row is a synthetic person (generated names, never real respondents). Find someone interesting, open their life, and follow them as time runs."
        tips={[
          'Narrow the list with a quick group below (or "+ condition" for anything), search by name, and click a column to sort (e.g. loneliest first).',
          'Click a person to open their life story, feelings (and why), relationships and faith.',
          <>Press <b>☆ Follow</b> on anyone: they appear on Home and in the Following tab, with their latest news after every run.</>,
        ]} />
      <div className="seg" style={{ marginBottom: 12 }}>
        <button className={tab === 'all' ? 'on' : ''} onClick={() => setTab('all')}>Everyone</button>
        <button className={tab === 'following' ? 'on' : ''} onClick={() => setTab('following')}>Following ({ids.length})</button>
      </div>
      {tab === 'following' ? (
        ids.length === 0 ? <div className="card empty">You aren't following anyone yet. Open a person and press ☆ Follow, or pick someone from <a href="#/home">Lives worth following</a> on Home.</div>
          : mine === null ? <Loading what="Catching up on their lives" /> : (
            <div className="grid g3">{mine.map(p => (
              <div key={p.id} className="card person-card" onClick={() => setRoute(['person', String(p.id)])}>
                <div className="row" style={{ flexWrap: 'nowrap' }}><div style={{ flex: 1, minWidth: 0 }}><div className="pc-name">{p.name}</div><div className="pc-head">{p.headline}{p.present === false ? ' · currently away' : ''}</div></div><FollowButton id={p.id} small /></div>
                {typeof p.mood === 'number' && <div className="small secondary">Happiness {fmt(p.mood, 2)} · loneliness {fmt(p.loneliness, 2)}</div>}
                <div>{(p.events ?? []).map((e: any) => <div key={e.id} className="story" style={{ padding: '4px 0' }}><span className="when tabular">{e.date}</span><Story e={e} me={p.id} /></div>)}</div>
              </div>
            ))}</div>
          )
      ) : (
        <>
          <div className="row" style={{ marginBottom: 8 }}>
            <span className="small muted">Quick groups:</span>
            {QUICK.slice(0, 9).map(qk => <button key={qk.label} className="chip" onClick={() => setCohort(qk.conds)}>{qk.label}</button>)}
          </div>
          <CohortBar n={data.n} />
          {data.loading && !data.mask ? <Loading /> : (
            <div className="card">
              <div className="row" style={{ marginBottom: 8 }}>
                <input type="search" placeholder="Search by name" value={q} onChange={e => { setQ(e.target.value); setPage(0) }} aria-label="Search by name" />
                <span className="muted small">{rows.length.toLocaleString()} people{STATIC ? ' (the snapshot includes a sample of complete lives)' : ''}</span>
                <span className="spacer" />
                <button className="btn small" disabled={page === 0} onClick={() => setPage(page - 1)} aria-label="Previous page">‹</button>
                <span className="small tabular">{page + 1} / {Math.max(1, Math.ceil(rows.length / 100))}</span>
                <button className="btn small" disabled={(page + 1) * 100 >= rows.length} onClick={() => setPage(page + 1)} aria-label="Next page">›</button>
              </div>
              <div style={{ overflowX: 'auto' }}>
                <table className="data">
                  <thead><tr><th style={{ width: 30 }} /><th>Name</th>{COLS.map(([v, l]) => (
                    <th key={v} className={NUM.includes(v) ? 'num' : ''} style={{ cursor: 'pointer' }}
                      onClick={() => setSort([v, sort[0] === v ? -sort[1] : -1])}>{l}{sort[0] === v ? (sort[1] > 0 ? ' ↑' : ' ↓') : ''}</th>))}</tr></thead>
                  <tbody>
                    {show.map(i => (
                      <tr key={i} className="click" onClick={() => setRoute(['person', String(i)])}>
                        <td><StarToggle id={i} /></td>
                        <td><b>{nameOf(i, data.cols.sex.data[i])}</b></td>
                        {COLS.map(([v]) => <td key={v} className={NUM.includes(v) ? 'num' : ''}>{fmtCell(v, i)}</td>)}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  )
}

function StarToggle({ id }: { id: number }) {
  const { toggleFollow, following } = useStore()
  void following
  const on = useStore.getState().followed().includes(id)
  return <button className="btn ghost small" aria-label={on ? 'Unfollow' : 'Follow'} title={on ? 'Unfollow' : 'Follow'} onClick={e => { e.stopPropagation(); toggleFollow(id) }} style={{ padding: '0 4px', color: on ? 'var(--accent)' : 'var(--text-muted)' }}>{on ? '★' : '☆'}</button>
}
