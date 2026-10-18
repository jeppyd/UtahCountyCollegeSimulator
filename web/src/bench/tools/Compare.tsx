// Compare: the Original world against the What-if, for the selection. For one person: their two lives side by side
// since the split — how they differ now, the first fork in their road, friends gained and lost. With nobody selected:
// the people whose lives diverged most. Needs a What-if (made on the What-if page).
import { api } from '../../api'
import { U_LABEL, useAsync } from '../../game'
import { Busy, dayWords, Empty, Problem, useWorldDays } from '../../kit/Bits'
import { RefChip } from '../../kit/RefChip'
import { useStore } from '../../store'
import type { PanelProps, ToolDef } from '../registry'
import { focusItem, subjectPerson } from '../sel'

const show = (x: any) => typeof x === 'number' ? x.toFixed(2) : String(x ?? '—').replace(/_/g, ' ')

function Chain({ rows, u }: { rows: any[] | null; u: 'base' | 'alt' }) {
  if (!rows?.length) return <div className="bx-note">No fork recorded in this world.</div>
  return (
    <div className="bk-list">
      {rows.slice(0, 5).map((r: any) => (
        <div key={r.id} className="bk-li"><span className="when">{r.date?.slice(5) ?? r.day}</span>
          <span className="grow"><RefChip r={{ kind: 'event', id: r.id, label: r.label, u }} plain />{r.b_name && <span className="bx-note">with {r.b_name}</span>}</span></div>
      ))}
    </div>
  )
}

function CompareTool({ sel, setSel }: PanelProps) {
  const status = useStore(s => s.status)
  const dataVersion = useStore(s => s.dataVersion)
  const { start } = useWorldDays()
  const who = subjectPerson(sel)
  const hasAlt = !!status?.has_alt
  const data = useAsync(async () => {
    if (!hasAlt) return null
    return who !== null ? { one: await api.comparePerson(who), many: null } : { one: null, many: await api.comparePeople(30) }
  }, [hasAlt, who, dataVersion], { key: `bench-compare:${who}` })

  if (!hasAlt) return <Empty title="No What-if yet">Make a What-if (top menu, What-if) to compare the Original world with a changed one here.</Empty>
  if (data.error && !data.data) return <Problem error={data.error} />
  if (!data.data) return <Busy what="Comparing the two worlds" />
  const { one, many } = data.data

  if (many) return (
    <div className="bk">
      <div className="bx-note">
        Since the split, {many.with_any_diff.toLocaleString()} of {many.n.toLocaleString()} people live differently
        ({many.with_event_diff.toLocaleString()} had different events). The most changed lives — click one to compare it:
      </div>
      <div className="bk-list">
        {many.people.map((p: any) => (
          <div key={p.id} className="bk-li click" onClick={() => focusItem(setSel, { kind: 'person', id: p.id, label: p.name })}>
            <span className="grow"><b>{p.name}</b><span className="bx-note">{p.first_divergence ? `first fork ${dayWords(start, p.first_divergence.day)}: ${p.first_divergence.label} (${U_LABEL[p.first_divergence.world] ?? p.first_divergence.world})` : ''}</span></span>
            <span className="bk-pill">{p.diffs.length} differences</span>
          </div>
        ))}
      </div>
    </div>
  )

  return (
    <div className="bk">
      <div className="bk-title"><h4><RefChip r={{ kind: 'person', id: one.id, label: one.name }} plain /></h4>
        <span className="bx-note">split on {dayWords(start, one.fork_day)}</span></div>
      <table className="bt-table">
        <thead><tr><th /><th style={{ color: 'var(--u-base)' }}>{U_LABEL.base}</th><th style={{ color: 'var(--u-alt)' }}>{U_LABEL.alt}</th></tr></thead>
        <tbody>
          <tr><td>In short</td><td>{one.headline_base}</td><td>{one.headline_alt}</td></tr>
          <tr><td>Partner</td><td>{one.partner_base ? <RefChip r={{ kind: 'person', id: one.partner_base.id, label: one.partner_base.name, u: 'base' }} plain /> : '—'}</td>
            <td>{one.partner_alt ? <RefChip r={{ kind: 'person', id: one.partner_alt.id, label: one.partner_alt.name, u: 'alt' }} plain /> : '—'}</td></tr>
          <tr><td>Friends</td><td>{one.n_friends[0]}</td><td>{one.n_friends[1]}</td></tr>
          {one.states.filter((s: any) => show(s.base) !== show(s.alt)).map((s: any) => (
            <tr key={s.id}><td>{s.label}</td><td>{show(s.base)}</td><td>{show(s.alt)}</td></tr>
          ))}
        </tbody>
      </table>
      <div className="bx-h">Where the road forked</div>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
        <div><div className="bx-note" style={{ color: 'var(--u-base)' }}>{U_LABEL.base}</div><Chain rows={one.first_base} u="base" /></div>
        <div><div className="bx-note" style={{ color: 'var(--u-alt)' }}>{U_LABEL.alt}</div><Chain rows={one.first_alt} u="alt" /></div>
      </div>
      {(one.friends_gained.length > 0 || one.friends_lost.length > 0) && (
        <>
          <div className="bx-h">Friends only in one world</div>
          <div className="bk-chips">
            {one.friends_lost.map((f: any) => <RefChip key={`l${f.id}`} r={{ kind: 'person', id: f.id, label: f.name, u: 'base' }} sub={`only in ${U_LABEL.base}`} />)}
            {one.friends_gained.map((f: any) => <RefChip key={`g${f.id}`} r={{ kind: 'person', id: f.id, label: f.name, u: 'alt' }} sub={`only in ${U_LABEL.alt}`} />)}
          </div>
        </>
      )}
    </div>
  )
}

export const tool: ToolDef = {
  id: 'compare',
  label: 'Compare',
  icon: 'butterfly',
  hint: 'The Original world against the What-if: one person’s two lives, or the lives that changed most.',
  group: 'world',
  order: 20,
  component: CompareTool,
  size: { w: 6, h: 7 },
}
