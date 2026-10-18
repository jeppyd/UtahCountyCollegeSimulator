// Occasion: one get-together, date, dance or study group as it happened — when and where, who planned it and why,
// who was asked and how, who said yes and who came (late, by what ride), who met there and what it led to. With no
// occasion focused it lists the selected person's occasions (or today's), to pick one.
import { useState } from 'react'
import { benchApi } from '../../api'
import { useAsync } from '../../game'
import { Busy, dayWords, Empty, Problem, useWorldDays } from '../../kit/Bits'
import { DecisionCard } from '../../kit/DecisionCard'
import { RefChip } from '../../kit/RefChip'
import { useLens, useStore } from '../../store'
import type { PanelProps, ToolDef } from '../registry'
import { focusItem, subjectPerson, worldOf } from '../sel'

const RESP: Record<string, string> = { yes: 'said yes', no: 'said no', maybe: 'maybe', none: 'no answer', unseen: 'never saw it' }

function OccasionList({ sel, setSel }: Pick<PanelProps, 'sel' | 'setSel'>) {
  const u = useLens().u
  const dataVersion = useStore(s => s.dataVersion)
  const { start, today } = useWorldDays()
  const who = subjectPerson(sel)
  const data = useAsync(async () => {
    if (who !== null) return benchApi.occasions({ person: who, limit: 200 }, u)
    const r = await benchApi.occasions({ limit: 200 }, u)
    return r.n ? r : benchApi.occasions({ day: Math.max(0, today - 1), limit: 200 }, u)
  }, [who, u, dataVersion, today])
  if (data.error && !data.data) return <Problem error={data.error} />
  if (!data.data) return <Busy what="Reading the occasions" />
  const occ: any[] = data.data.occasions
  return (
    <div className="bk">
      <div className="bx-note">{who !== null ? 'Occasions the selected person was part of' : `Occasions on ${dayWords(start, occ[0]?.day ?? today)}`} ({data.data.n.toLocaleString()}); click one to see it.</div>
      {occ.length === 0 && <Empty title="No occasions yet">Get-togethers, dates and study groups appear here as days run.</Empty>}
      <div className="bk-list">
        {occ.map(o => (
          <div key={o.id} className="bk-li click" onClick={() => focusItem(setSel, { kind: 'occasion', id: o.id, label: o.name ?? o.kind_label, u })}>
            <span className="when">{dayWords(start, o.day)} {o.time?.split('–')[0]}</span>
            <span className="grow"><b>{o.name ?? o.kind_label}</b><span className="bx-note">{o.place}</span></span>
            <span className="bk-pill">{o.came} came</span>
          </div>
        ))}
      </div>
    </div>
  )
}

function OccasionTool({ sel, setSel }: PanelProps) {
  const lensU = useLens().u
  const u = worldOf(sel, lensU)
  const dataVersion = useStore(s => s.dataVersion)
  const { start } = useWorldDays()
  const [open, setOpen] = useState<number | null>(null)
  const id = sel.item?.kind === 'occasion' ? Number(sel.item.id) : null
  const data = useAsync(() => (id === null ? Promise.resolve(null) : benchApi.occasion(id, u)), [id, u, dataVersion])
  if (id === null) return <OccasionList sel={sel} setSel={setSel} />
  if (data.error && !data.data) return <Problem error={data.error} />
  if (!data.data) return <Busy what="Reading the occasion" />
  const o = data.data
  return (
    <div className="bk">
      <div className="bk-title">
        <h4>{o.name ?? o.kind_label}</h4><span className="bk-pill">{o.status}</span>
        <button className="bk-more" onClick={() => setSel({ item: undefined })}>back to the list</button>
      </div>
      <div className="bk-sub">
        {o.weekday}, {dayWords(start, o.day)}, {o.time} · {o.place} · organized by{' '}
        <RefChip r={{ kind: 'person', id: o.organizer.id, label: o.organizer.name, u }} plain /> ({o.how})
      </div>
      <div className="bk-facts">
        <span><b>{o.invited}</b> asked</span><span><b>{o.said_yes}</b> said yes</span><span><b>{o.came}</b> came</span>
        <span><b>{o.new_ties}</b> new ties</span>{o.host_burden !== null && <span title="How much hosting wore on the organizer">hosting load <b>{o.host_burden.toFixed(1)}</b></span>}
      </div>
      {o.host_decision && <><div className="bx-h">Why it happened</div><DecisionCard data={o.host_decision} u={u} startDate={start} compact /></>}
      <div className="bx-h">Who was asked</div>
      <div className="bk-list">
        {o.people.map((p: any) => (
          <div key={p.person.id}>
            <div className={`bk-li ${p.decision ? 'click' : ''}`} onClick={() => p.decision && setOpen(open === p.person.id ? null : p.person.id)}>
              <span className="grow">
                <RefChip r={{ kind: 'person', id: p.person.id, label: p.person.name, u }} />
                <span className="bx-note">{p.role === 'walk_in' ? 'walked in' : p.channel_words}{p.inviter && p.inviter.id !== o.organizer.id ? ` from ${p.inviter.name}` : ''}</span>
              </span>
              <span className={`bk-pill ${p.response === 'yes' ? 'yes' : p.response === 'no' ? 'no' : 'quiet'}`}>{RESP[p.response] ?? p.response ?? ''}</span>
              <span className="bk-pill">{p.came ? `came ${p.arrive ?? ''}${p.late_minutes ? ` (${p.late_minutes} min late)` : ''}` : 'didn’t come'}</span>
              {p.trip && <span className="bx-note">{p.trip.minutes} min by {p.trip.mode}{p.ride ? `, ride from ${p.ride.name ?? p.ride}` : ''}</span>}
            </div>
            {open === p.person.id && p.decision && <div className="bk-why"><DecisionCard data={p.decision} u={u} startDate={start} compact /></div>}
          </div>
        ))}
      </div>
      {o.met?.length > 0 && (
        <>
          <div className="bx-h">Who met here</div>
          <div className="bk-list">
            {o.met.map((m: any, k: number) => (
              <div key={k} className="bk-li"><span className="grow">
                <RefChip r={{ kind: 'person', id: m.a.id, label: m.a.name, u }} /> and <RefChip r={{ kind: 'person', id: m.b.id, label: m.b.name, u }} />
                {m.introducer && <span className="bx-note">introduced by {m.introducer.name}</span>}
              </span><RefChip r={{ kind: 'tie', id: `${Math.min(m.a.id, m.b.id)}-${Math.max(m.a.id, m.b.id)}`, label: 'their tie', u }} /></div>
            ))}
          </div>
        </>
      )}
      {o.events?.length > 0 && (
        <>
          <div className="bx-h">What it led to</div>
          <div className="bk-chips">{o.events.map((e: any) => <RefChip key={e.id} r={{ kind: 'event', id: e.id, label: e.label, u }} sub={e.a_name?.split(' ')[0]} />)}</div>
        </>
      )}
      <div className="bx-note">{o.note}</div>
    </div>
  )
}

export const tool: ToolDef = {
  id: 'occasion',
  label: 'Occasion',
  icon: 'coffee',
  hint: 'One get-together, date or study group: who planned it and why, who was asked, who came, who met and what it led to.',
  group: 'trace',
  order: 40,
  component: OccasionTool,
  size: { w: 5, h: 8 },
}
