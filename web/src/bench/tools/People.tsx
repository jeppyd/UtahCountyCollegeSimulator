// People: a table of the selection (or of everyone, narrowed by a name search) with columns you choose from any field.
// Click a row to focus that person; sort by any column.
import { useMemo, useState } from 'react'
import { cohortMask } from '../../analysis'
import { VarPicker } from '../../components'
import { fval } from '../../fields'
import { G, useAsync } from '../../game'
import { Busy, Problem } from '../../kit/Bits'
import { usePersonName } from '../../kit/RefChip'
import { nameOf } from '../../names'
import { loadColumns, useLens, useStore } from '../../store'
import { PanelOptions } from '../panel'
import type { PanelProps, ToolDef } from '../registry'
import { focusItem, subjectPerson } from '../sel'

const DEFAULT_COLS = ['age', 'school', 'rel_status', 'mood', 'loneliness']
const SHOW = 300

function PeopleTool({ sel, setSel, opts, setOpts }: PanelProps) {
  const lens = useLens()
  const u = lens.u   // people are the same in both worlds; the lens says which world to show
  const dataVersion = useStore(s => s.dataVersion)
  const reg = useStore(s => s.registry)!
  const name = usePersonName(u)
  const cols: string[] = (opts.cols ?? DEFAULT_COLS).filter((c: string) => reg.variables[c])
  const scope: 'sel' | 'all' = opts.scope ?? 'sel'
  const sort: { col: string; desc: boolean } = opts.sort ?? { col: '', desc: false }
  const set = (o: Record<string, any>) => setOpts({ ...opts, ...o })
  const [q, setQ] = useState('')
  const [adding, setAdding] = useState(false)

  const data = useAsync(async () => {
    const c = await loadColumns([...new Set(['sex', 'present', ...cols])], u)
    const mask = sel.filter?.length ? (await cohortMask(sel.filter, u)).mask : null
    return { c, mask }
  }, [cols.join(','), u, dataVersion, JSON.stringify(sel.filter ?? [])], { key: `bench-people:${u}:${cols.join(',')}:${JSON.stringify(sel.filter ?? [])}` })

  const rows = useMemo(() => {
    const d = data.data
    if (!d?.c.present) return null
    const n = d.c.present.data.length
    const sx = d.c.sex?.data
    let ids: number[]
    const own = scope === 'sel' && (sel.people?.length || sel.filter?.length)
    if (own && sel.people?.length) ids = sel.people.filter(i => i < n && (!d.mask || d.mask[i]))
    else if (own && d.mask) { ids = []; for (let i = 0; i < n; i++) if (d.mask[i]) ids.push(i) }
    else { ids = []; for (let i = 0; i < n; i++) if (d.c.present.data[i]) ids.push(i) }
    const ql = q.trim().toLowerCase()
    if (ql && sx) ids = ids.filter(i => String(i) === ql || nameOf(i, sx[i]).toLowerCase().includes(ql))
    if (sort.col && d.c[sort.col]) {
      const x = d.c[sort.col].data
      const s = sort.desc ? -1 : 1
      ids = [...ids].sort((a, b) => {
        const va = x[a], vb = x[b]
        if (Number.isNaN(va)) return 1
        if (Number.isNaN(vb)) return -1
        return s * (va - vb)
      })
    }
    return { ids, own: !!own }
  }, [data.data, sel.people, scope, q, sort.col, sort.desc])

  const focus = subjectPerson(sel)
  const clickSort = (c: string) => set({ sort: sort.col === c ? { col: c, desc: !sort.desc } : { col: c, desc: true } })
  const cell = (c: string, i: number) => {
    const col = data.data?.c[c]
    if (!col) return '—'
    const x = col.data[i]
    return fval(reg.variables[c], col.categories ? col.categories[x] : col.bool ? !!x : x)
  }
  return (
    <div className="bpe">
      <PanelOptions>
        <div className="seg">
          <button className={scope === 'sel' ? 'on' : ''} onClick={() => set({ scope: 'sel' })} title="The selected people or group">Selection</button>
          <button className={scope === 'all' ? 'on' : ''} onClick={() => set({ scope: 'all' })} title="Everyone in Provo–Orem now">Everyone</button>
        </div>
        <input type="search" placeholder="Name or number" value={q} onChange={e => setQ(e.target.value)} style={{ width: 130 }} />
        <button className="btn small" onClick={() => setAdding(!adding)} title="Add a column">+ column</button>
      </PanelOptions>
      {adding && (
        <div className="bt-row" style={{ marginBottom: 8 }}>
          <VarPicker value="" onChange={v => { if (v && !cols.includes(v)) set({ cols: [...cols, v] }); setAdding(false) }} placeholder="Pick a field to show" />
          <button className="btn small ghost" onClick={() => setAdding(false)}>cancel</button>
        </div>
      )}
      {data.error && !data.data && <Problem error={data.error} />}
      {!rows && !data.error && <Busy what="Reading everyone" />}
      {rows && (
        <>
          <div className="bx-note" style={{ marginBottom: 6 }}>
            {rows.own ? 'The selection' : 'Everyone here now'}: {rows.ids.length.toLocaleString()} {rows.ids.length === 1 ? 'person' : 'people'}
            {rows.ids.length > SHOW ? ` (showing the first ${SHOW}${sort.col ? ' by the sorted column' : ''})` : ''}
            {!rows.own && scope === 'sel' && ' — nothing is selected, so this lists everyone'}
          </div>
          <table className="bt-table">
            <thead>
              <tr>
                <th className="sortable" onClick={() => set({ sort: { col: '', desc: false } })}>Person</th>
                {cols.map(c => (
                  <th key={c} className={`sortable ${reg.variables[c]?.dtype === 'cat' || reg.variables[c]?.dtype === 'bool' ? '' : 'num'}`} title={reg.variables[c]?.desc}>
                    <span onClick={() => clickSort(c)}>{reg.variables[c]?.label ?? c}{sort.col === c ? (sort.desc ? ' ↓' : ' ↑') : ''}</span>
                    <button className="bpe-x" onClick={() => set({ cols: cols.filter(x => x !== c) })} title="Remove this column">{G.close}</button>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.ids.slice(0, SHOW).map(i => (
                <tr key={i} className={`click ${focus === i ? 'on' : ''}`} onClick={() => focusItem(setSel, { kind: 'person', id: i, label: name(i) })}>
                  <td><b>{name(i)}</b></td>
                  {cols.map(c => <td key={c} className={reg.variables[c]?.dtype === 'cat' || reg.variables[c]?.dtype === 'bool' ? '' : 'num'}>{cell(c, i)}</td>)}
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </div>
  )
}

export const tool: ToolDef = {
  id: 'people',
  label: 'People',
  icon: 'people',
  hint: 'A table of the selected people (or everyone) with any fields as columns; click a row to focus that person.',
  group: 'people',
  order: 10,
  component: PeopleTool,
  size: { w: 6, h: 6 },
}
