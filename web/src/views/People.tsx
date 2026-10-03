import { useEffect, useMemo, useState } from 'react'
import { fmt, useCohortData } from '../analysis'
import { api, STATIC } from '../api'
import { CohortBar, Loading } from '../components'
import { nameOf } from '../names'
import { useStore } from '../store'

const COLS: [string, string][] = [['age', 'Age'], ['role', 'Role'], ['rel_status', 'Relationship'], ['activity', 'Church activity'],
  ['mission_status', 'Mission'], ['living', 'Living'], ['n_friends', 'Friends'], ['loneliness', 'Loneliness'], ['mood', 'Mood'], ['dates_30d', 'Dates/30d']]

export default function People() {
  const setRoute = useStore(s => s.setRoute)
  const data = useCohortData(['sex', ...COLS.map(c => c[0])])
  const [sort, setSort] = useState<[string, number]>(['loneliness', -1])
  const [q, setQ] = useState('')
  const [page, setPage] = useState(0)
  const [staticIds, setStaticIds] = useState<Set<number> | null>(null)
  useEffect(() => { if (STATIC) api.staticPeople().then(ids => setStaticIds(new Set(ids))) }, [])
  const rows = useMemo(() => {
    if (!data.mask) return []
    const ids: number[] = []
    for (let i = 0; i < data.mask.length; i++) if (data.mask[i] && (!staticIds || staticIds.has(i))) ids.push(i)
    const sx = data.cols.sex.data
    let out = ids
    if (q.trim()) {
      const ql = q.toLowerCase()
      out = ids.filter(i => String(i) === ql || nameOf(i, sx[i]).toLowerCase().includes(ql))
    }
    const c = data.cols[sort[0]]
    if (c) out.sort((a, b) => ((c.data[a] as number) - (c.data[b] as number)) * sort[1])
    return out
  }, [data, sort, q, staticIds])
  if (data.loading && !data.mask) return <Loading />
  const show = rows.slice(page * 100, page * 100 + 100)
  const fmtCell = (v: string, i: number) => {
    const c = data.cols[v]
    if (!c) return ''
    if (c.categories) return c.categories[c.data[i]].replace(/_/g, ' ')
    return fmt(c.data[i], v === 'age' ? 1 : 2)
  }
  return (
    <div className="page">
      <h1>People</h1>
      <p className="sub">Every row is a synthetic person (names are generated, never real respondents). Filter with the cohort bar, sort any column, click to open a life story.
        {STATIC && ' The static demo includes a sample of fully exported lives.'}</p>
      <CohortBar n={data.n} />
      <div className="card">
        <div className="row" style={{ marginBottom: 8 }}>
          <input type="search" placeholder="Search name or id" value={q} onChange={e => { setQ(e.target.value); setPage(0) }} />
          <span className="muted small">{rows.length.toLocaleString()} matching</span>
          <span className="spacer" />
          <button className="btn small" disabled={page === 0} onClick={() => setPage(page - 1)}>‹</button>
          <span className="small tabular">{page + 1} / {Math.max(1, Math.ceil(rows.length / 100))}</span>
          <button className="btn small" disabled={(page + 1) * 100 >= rows.length} onClick={() => setPage(page + 1)}>›</button>
        </div>
        <div style={{ overflowX: 'auto' }}>
          <table className="data">
            <thead><tr><th>Name</th>{COLS.map(([v, l]) => (
              <th key={v} className={['age', 'n_friends', 'loneliness', 'mood', 'dates_30d'].includes(v) ? 'num' : ''} style={{ cursor: 'pointer' }}
                onClick={() => setSort([v, sort[0] === v ? -sort[1] : -1])}>{l}{sort[0] === v ? (sort[1] > 0 ? ' ↑' : ' ↓') : ''}</th>))}</tr></thead>
            <tbody>
              {show.map(i => (
                <tr key={i} className="click" onClick={() => setRoute(['person', String(i)])}>
                  <td><b>{nameOf(i, data.cols.sex.data[i])}</b> <span className="muted small">#{i}</span></td>
                  {COLS.map(([v]) => <td key={v} className={['age', 'n_friends', 'loneliness', 'mood', 'dates_30d'].includes(v) ? 'num' : ''}>{fmtCell(v, i)}</td>)}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
