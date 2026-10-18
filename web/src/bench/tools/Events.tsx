// Events: a searchable list of what happened to the selected people (or to anyone), in the selection's time window.
// Click a row to focus the event (Trace and Chains follow it); every person and event is a chip you can follow.
import { useState } from 'react'
import { benchApi } from '../../api'
import { useAsync } from '../../game'
import { Busy, CAT_ORDER, catLabel, CatDot, dayWords, Empty, Problem, useWorldDays, BLOCK_WORDS } from '../../kit/Bits'
import { RefChip } from '../../kit/RefChip'
import { useLens, useStore } from '../../store'
import { PanelOptions } from '../panel'
import type { PanelProps, ToolDef } from '../registry'
import { focusItem, hasGroup, selGroup } from '../sel'

const PAGE = 150

function EventsTool({ sel, setSel, opts, setOpts }: PanelProps) {
  const u = useLens().u
  const dataVersion = useStore(s => s.dataVersion)
  const { start } = useWorldDays()
  const [q, setQ] = useState('')
  const [limit, setLimit] = useState(PAGE)
  const cat: string = opts.cat ?? ''
  const big: boolean = opts.big ?? false
  const set = (o: Record<string, any>) => setOpts({ ...opts, ...o })
  const g = selGroup(sel)

  const data = useAsync(() => benchApi.events({
    ...g, since: sel.time?.[0], until: sel.time?.[1], cats: cat ? [cat] : undefined, q: q.trim() || undefined,
    minSalience: big ? 0.6 : 0, limit,
  }, u), [JSON.stringify(g), JSON.stringify(sel.time ?? null), cat, big, q, limit, u, dataVersion])

  const focusId = sel.item?.kind === 'event' ? Number(sel.item.id) : null
  const d = data.data
  return (
    <div className="bk">
      <PanelOptions>
        <input type="search" placeholder="Search events" value={q} onChange={e => { setQ(e.target.value); setLimit(PAGE) }} style={{ width: 130 }} />
        <select value={cat} onChange={e => set({ cat: e.target.value })} title="Only one kind of event">
          <option value="">All kinds</option>
          {CAT_ORDER.map(c => <option key={c} value={c}>{catLabel(c)}</option>)}
        </select>
        <label className="bt-row" title="Only events that matter more to a life (first dates, breakups, moves…)">
          <input type="checkbox" checked={big} onChange={e => set({ big: e.target.checked })} /> big ones
        </label>
      </PanelOptions>
      {data.error && !d && <Problem error={data.error} />}
      {!d && !data.error && <Busy what="Reading the record" />}
      {d && (
        <>
          <div className="bx-note">
            {d.total.toLocaleString()} {d.total === 1 ? 'event' : 'events'}
            {hasGroup(sel) ? ` involving ${d.n_people === 1 ? 'the selected person' : `the ${(d.n_people ?? 0).toLocaleString()} selected people`}` : ' involving anyone (nothing is selected)'}
            {sel.time ? `, ${dayWords(start, sel.time[0])} – ${dayWords(start, sel.time[1])}` : ''}; newest first.
          </div>
          {d.events.length === 0 && <Empty title="Nothing matches">Try another search or kind, or widen the time window.</Empty>}
          <div className="bk-list">
            {d.events.map(e => (
              <div key={e.id} className={`bk-li click ${focusId === e.id ? 'on' : ''}`}
                onClick={() => focusItem(setSel, { kind: 'event', id: e.id, label: e.label, u })}>
                <span className="when" title={BLOCK_WORDS[e.block] ?? ''}>{dayWords(start, e.day)}</span>
                <CatDot c={e.category} />
                <span className="grow">
                  <RefChip r={{ kind: 'event', id: e.id, label: e.label, u }} plain />
                  <RefChip r={{ kind: 'person', id: e.a, label: e.a_name ?? undefined, u }} />
                  {e.b !== null && <RefChip r={{ kind: 'person', id: e.b, label: e.b_name ?? undefined, u }} />}
                </span>
              </div>
            ))}
          </div>
          {d.total > d.events.length && <button className="bk-more" onClick={() => setLimit(limit + PAGE)}>Show more ({(d.total - d.events.length).toLocaleString()} left)</button>}
        </>
      )}
    </div>
  )
}

export const tool: ToolDef = {
  id: 'events',
  label: 'Events',
  icon: 'events',
  hint: 'A searchable list of what happened to the selected people (or anyone); click one to trace it.',
  group: 'trace',
  order: 30,
  component: EventsTool,
  size: { w: 5, h: 7 },
}
