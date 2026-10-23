// Find someone without guessing names: how they stand with the person you're acting through (friends, roommates,
// people they haven't met, people into them, people things are tense with…), any filter the rest of the app uses
// (age, school, faith, relationship status, loneliness…), a name if you have one, and a sort by closeness, distance,
// interest either way, tension or any variable. Click a row to pick them.
import { useState } from 'react'
import { valleyApi, type FindResult, type FoundPerson, type Universe } from '../../api'
import { condLabel, CondEditor, VarPicker } from '../../components'
import { G, useAsync } from '../../game'
import { useStore, type Cond } from '../../store'

const QUICK_PICK: { label: string; c: Cond }[] = [
  { label: 'Women', c: { var: 'sex', op: 'eq', value: 'F' } },
  { label: 'Men', c: { var: 'sex', op: 'eq', value: 'M' } },
  { label: 'Single', c: { var: 'rel_status', op: 'in', value: ['single', 'talking'] } },
  { label: 'BYU', c: { var: 'school', op: 'eq', value: 'BYU' } },
  { label: 'UVU', c: { var: 'school', op: 'eq', value: 'UVU' } },
  { label: 'Returned missionaries', c: { var: 'mission_status', op: 'in', value: ['returned', 'early_returned'] } },
  { label: 'Lonely', c: { var: 'loneliness', op: 'quantile_ge', value: 0.8 } },
]
const PAGE = 20

function relLabels(f: string): Record<string, string> {
  return {
    any: 'Anyone', knows: `People ${f} knows`, strangers: `People ${f} hasn't met`, friends: `${f}'s friends`,
    close_friends: `${f}'s close friends`, roommates: `${f}'s roommates`, neighbors: `${f}'s neighbors`, ward: `${f}'s ward`,
    classmates: `${f}'s classmates`, coworkers: `${f}'s coworkers`, family: `${f}'s family`, exes: `${f}'s exes`,
    partner: `${f}'s partner`, likes: `People ${f} is into`, into_them: `People into ${f}`, tense: `Things are tense with ${f}`,
  }
}

export function PersonFinder({ around, first, relation: rel0 = 'knows', u, onPick }:
  { around: number | null; first: string; relation?: string; u: Universe; onPick: (id: number, name: string) => void }) {
  const registry = useStore(s => s.registry)
  const [relation, setRelation] = useState(around === null ? 'any' : rel0)
  const [conds, setConds] = useState<Cond[]>([])
  const [q, setQ] = useState('')
  const [sort, setSort] = useState(around === null ? 'name' : rel0 === 'strangers' ? 'nearest' : 'closeness')
  const [desc, setDesc] = useState<boolean | undefined>(undefined)
  const [page, setPage] = useState(0)
  const [adding, setAdding] = useState(false)
  const res = useAsync<FindResult>(() => valleyApi.find({ around, relation, filter: conds, q, sort, desc, offset: page * PAGE, limit: PAGE }, u),
    [around, relation, JSON.stringify(conds), q, sort, desc, page, u])
  const r = res.data
  const labels = relLabels(first)
  const go = (f: () => void) => { f(); setPage(0) }
  const has = (c: Cond) => conds.some(x => JSON.stringify(x) === JSON.stringify(c))
  const lead: [string, string][] = around === null ? [['name', 'Name']] : [['closeness', `Closest to ${first}`], ['nearest', `Lives nearest ${first}`],
    ['their_interest', `Most into ${first}`], ['my_interest', `${first} is most into`], ['tension', `Most tension with ${first}`], ['name', 'Name']]
  return (
    <div className="pf">
      <div className="pf-top">
        <span className="pf-search">{G.search}<input type="search" placeholder="Name (optional)" value={q} onChange={e => go(() => setQ(e.target.value))} /></span>
        {around !== null && <select value={relation} onChange={e => go(() => setRelation(e.target.value))} aria-label="How they know them">
          {Object.entries(labels).map(([k, l]) => <option key={k} value={k}>{l}{r?.counts?.[k] !== undefined ? ` (${r.counts[k].toLocaleString()})` : ''}</option>)}
        </select>}
      </div>
      <div className="pf-filters">
        {conds.map((c, i) => <span key={i} className="cond">{condLabel(c, registry)}<button onClick={() => go(() => setConds(conds.filter((_, k) => k !== i)))} aria-label="remove">×</button></span>)}
        {QUICK_PICK.filter(x => !has(x.c)).map(x => <button key={x.label} className="chip" onClick={() => go(() => setConds([...conds, x.c]))}>{x.label}</button>)}
        <button className="btn small" onClick={() => setAdding(!adding)} title="Any variable: age, faith, major, loneliness, a recent event…">+ filter</button>
      </div>
      {adding && <CondEditor onDone={() => setAdding(false)} onAdd={cs => go(() => setConds([...conds, ...cs]))} />}
      <div className="pf-sort small">
        <span className="muted">{r ? `${r.total.toLocaleString()} ${r.total === 1 ? 'person' : 'people'}` : res.loading ? 'Looking…' : ''}</span>
        <span className="spacer" />
        <span className="muted">Sort</span>
        <VarPicker value={sort} onChange={v => go(() => { setSort(v); setDesc(undefined) })} lead={lead} filter={s => s.dtype !== 'cat'} />
        <button className="bx-icon" title={r?.desc ? 'Highest first' : 'Lowest first'} onClick={() => go(() => setDesc(!(r?.desc ?? true)))}>{r?.desc ? '↓' : '↑'}</button>
      </div>
      {res.error && <div className="bk-bad">{res.error}</div>}
      <div className="pf-list">
        {r?.rows.map(p => <Row key={p.id} p={p} first={first} sort={sort} onPick={() => onPick(p.id, p.name)} />)}
        {r && r.total === 0 && <div className="muted small pf-empty">Nobody matches. Loosen a filter or pick a wider group.</div>}
      </div>
      {r && r.total > PAGE && <div className="pf-pages small">
        <button className="btn small" disabled={page === 0} onClick={() => setPage(page - 1)}>‹</button>
        <span className="tabular">{page + 1} / {Math.ceil(r.total / PAGE)}</span>
        <button className="btn small" disabled={(page + 1) * PAGE >= r.total} onClick={() => setPage(page + 1)}>›</button>
      </div>}
    </div>
  )
}

function Row({ p, first, sort, onPick }: { p: FoundPerson; first: string; sort: string; onPick: () => void }) {
  const bits: string[] = []
  if (p.closeness !== undefined && p.closeness > 0.01) bits.push(`closeness ${p.closeness.toFixed(2)}`)
  if (p.their_interest !== undefined && p.their_interest >= 0.15) bits.push(`into ${first} ${p.their_interest.toFixed(2)}`)
  if (p.my_interest !== undefined && p.my_interest >= 0.15) bits.push(`${first} into them ${p.my_interest.toFixed(2)}`)
  if (p.hurt !== undefined && p.hurt >= 0.05) bits.push(`hurt ${p.hurt.toFixed(2)}`)
  if (p.km !== undefined && (sort === 'nearest' || !p.closeness)) bits.push(`${p.km} km away`)
  if (p.value !== undefined && p.value !== null) bits.push(`${sort.replace(/_/g, ' ')}: ${typeof p.value === 'boolean' ? (p.value ? 'yes' : 'no') : p.value}`)
  return (
    <button className="pf-row" onClick={onPick} title={`Pick ${p.name}`}>
      <span className="pf-name"><b>{p.name}</b>{p.tie && <span className="pf-tie">{p.tie}</span>}</span>
      <small className="pf-head">{p.headline}</small>
      {bits.length > 0 && <small className="pf-bits">{bits.join(' · ')}</small>}
    </button>
  )
}
