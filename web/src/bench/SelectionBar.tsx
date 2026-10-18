// The bench's shared selection, always in view: the selected people (or a group), the time window and the focused
// item, with a way back and a way to start over. Every chip is a RefChip, so it can be traced or opened from here.
import { useEffect, useRef, useState } from 'react'
import { cohortMask } from '../analysis'
import { api } from '../api'
import { condLabel, CondEditor } from '../components'
import { G, useAsync } from '../game'
import { dayWords, useWorldDays } from '../kit/Bits'
import { RefChip } from '../kit/RefChip'
import { useLens, useStore } from '../store'
import { SERVER_ONLY } from '../analysis'
import { useBench } from './selection'

const SHOW = 6

export function SelectionBar() {
  const { sel, setSel, back, clear, history, focus, addPeople } = useBench()
  const { u } = useLens()
  const reg = useStore(s => s.registry)
  const dataVersion = useStore(s => s.dataVersion)
  const { start } = useWorldDays()
  const [adding, setAdding] = useState(false)
  const [more, setMore] = useState(false)
  const people = sel.people ?? []
  const filter = sel.filter ?? []
  const groupN = useAsync(() => (filter.length && !filter.some(SERVER_ONLY) ? cohortMask(filter, u).then(r => r.n)
    : filter.length ? api.cohortServer({ and: filter }, u).then((r: any) => r.n as number) : Promise.resolve(null)),
  [JSON.stringify(filter), u, dataVersion])
  const empty = !people.length && !filter.length && !sel.time && !sel.item
  return (
    <div className="selbar" role="region" aria-label="The selection">
      <span className="selbar-k">Selection</span>
      {empty && <span className="selbar-none">nothing selected — pick someone or something in any tool</span>}
      {people.length > 0 && (
        <span className="selbar-set">
          {(more ? people : people.slice(0, SHOW)).map(i => <RefChip key={i} r={{ kind: 'person', id: i }} />)}
          {people.length > SHOW && <button className="selbar-more" onClick={() => setMore(!more)}>{more ? 'fewer' : `+${(people.length - SHOW).toLocaleString()} more`}</button>}
          <button className="selbar-x" title="Clear the people" onClick={() => setSel({ people: undefined })}>{G.close}</button>
        </span>
      )}
      {filter.length > 0 && (
        <span className="selbar-set group">
          <span className="selbar-sub">group</span>
          {filter.map((c, k) => (
            <span key={k} className="cond">{condLabel(c, reg)}<button onClick={() => setSel({ filter: filter.filter((_, j) => j !== k) })} aria-label="remove">×</button></span>
          ))}
          {groupN.data !== null && groupN.data !== undefined && <span className="selbar-n tabular">{groupN.data.toLocaleString()} people</span>}
        </span>
      )}
      {sel.time && (
        <span className="selbar-set">
          <span className="selbar-sub">when</span>
          <span className="selbar-time tabular">{dayWords(start, sel.time[0], true)} – {dayWords(start, sel.time[1], true)}</span>
          <button className="selbar-x" title="Any time" onClick={() => setSel({ time: undefined })}>{G.close}</button>
        </span>
      )}
      {sel.item && sel.item.kind !== 'person' && (
        <span className="selbar-set">
          <span className="selbar-sub">focus</span>
          <RefChip r={sel.item} />
          <button className="selbar-x" title="Clear the focus" onClick={() => setSel({ item: undefined })}>{G.close}</button>
        </span>
      )}
      <span className="spacer" />
      <FindPerson onPick={(id, name, add) => (add ? addPeople([id]) : focus({ kind: 'person', id, label: name }))} />
      <span className="menu-wrap">
        <button className="btn small" onClick={() => setAdding(!adding)} title="Select everyone who matches a description (a filter)">+ group</button>
        {adding && <div className="selbar-pop card"><CondEditor onDone={() => setAdding(false)} onAdd={cs => setSel({ filter: [...filter, ...cs] })} /></div>}
      </span>
      <button className="btn small ghost" onClick={back} disabled={!history.length} title="Back to the previous selection">← Back</button>
      <button className="btn small ghost" onClick={clear} disabled={empty} title="Select nothing">Clear</button>
    </div>
  )
}

/** Find someone by name or number; Enter or click selects them, the + adds them to the selection. */
function FindPerson({ onPick }: { onPick: (id: number, name: string, add: boolean) => void }) {
  const { u } = useLens()
  const [q, setQ] = useState('')
  const [open, setOpen] = useState(false)
  const box = useRef<HTMLDivElement>(null)
  const found = useAsync(() => (q.trim().length >= 2 ? api.searchPeople(q.trim(), u) : Promise.resolve([])), [q, u], false)
  useEffect(() => {
    const h = (e: MouseEvent) => { if (box.current && !box.current.contains(e.target as Node)) setOpen(false) }
    document.addEventListener('mousedown', h)
    return () => document.removeEventListener('mousedown', h)
  }, [])
  const rows: any[] = found.data ?? []
  return (
    <div className="findp" ref={box}>
      <input type="search" placeholder="Find a person…" value={q} onFocus={() => setOpen(true)}
        onChange={e => { setQ(e.target.value); setOpen(true) }}
        onKeyDown={e => { if (e.key === 'Enter' && rows[0]) { onPick(rows[0].id, rows[0].name, e.shiftKey); setOpen(false); setQ('') } }} />
      {open && rows.length > 0 && (
        <div className="findp-list card">
          {rows.map(p => (
            <div key={p.id} className="findp-row">
              <button className="findp-name" onClick={() => { onPick(p.id, p.name, false); setOpen(false); setQ('') }}>
                <b>{p.name}</b><small>{p.headline ?? ''}</small>
              </button>
              <button className="bx-icon" title="Add to the selection" onClick={() => onPick(p.id, p.name, true)}>{G.plus}</button>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
