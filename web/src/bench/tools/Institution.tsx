// Institution: one organization with its limits — a club or team, a ward (and its bishop's interview slots), a
// counseling center (capacity, waitlist, who is waiting and who is being seen), an employer, a complex's management.
// Demand against what it could serve over time, the events it ran, and the decisions its people made when things
// didn't work (more food, another night, recruiting). Pick one from the list, or focus a ward or complex.
import { useState } from 'react'
import { instApi, type InstDetail } from '../../api'
import { useAsync } from '../../game'
import { Busy, dayWords, Empty, Problem, useWorldDays } from '../../kit/Bits'
import { RefChip } from '../../kit/RefChip'
import { useLens, useStore } from '../../store'
import { PanelOptions } from '../panel'
import type { PanelProps, ToolDef } from '../registry'
import { focusItem } from '../sel'
import '../../kit/talk.css'

const KIND_WORDS: Record<string, string> = { club: 'Club', team: 'Team', institute: 'Institute class', ward: 'Ward', counseling: 'Counseling center', employer: 'Employer', complex: 'Apartment complex' }
const DAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']

function Chart({ d }: { d: InstDetail }) {
  const h = d.history
  if (h.length < 2) return <div className="bx-note">The history fills in week by week.</div>
  const W = 420, H = 90, pad = 4
  const maxY = Math.max(1, ...h.map(r => Math.max(r.demand, r.served + r.waitlist)))
  const x = (i: number) => pad + (i / (h.length - 1)) * (W - 2 * pad)
  const y = (v: number) => H - pad - (v / maxY) * (H - 2 * pad)
  const line = (f: (r: typeof h[0]) => number) => h.map((r, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)},${y(f(r)).toFixed(1)}`).join('')
  const cap = d.capacity !== undefined && d.capacity > 0 && d.kind !== 'employer' ? d.capacity : null
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="in-chart" role="img" aria-label="Demand and served over time">
      {cap !== null && cap <= maxY && <line x1={pad} x2={W - pad} y1={y(cap)} y2={y(cap)} className="in-cap" />}
      {h.map((r, i) => r.waitlist > 0 && <rect key={i} x={x(i) - 3} width={6} y={y(r.waitlist)} height={H - pad - y(r.waitlist)} className="in-wait" />)}
      <path d={line(r => r.demand)} className="in-demand" />
      <path d={line(r => r.served)} className="in-served" />
    </svg>
  )
}

function Detail({ id, setSel }: { id: number; setSel: PanelProps['setSel'] }) {
  const u = useLens().u
  const v = useStore(s => s.dataVersion)
  const { start } = useWorldDays()
  const d = useAsync(() => instApi.get(id, u), [id, u, v])
  if (d.error && !d.data) return <Problem error={d.error} />
  if (!d.data) return <Busy what="Opening the records" />
  const x = d.data
  const lim = x.kind === 'counseling' ? `${x.capacity} sessions a week` : x.kind === 'ward' ? `${x.served ?? 0} meetings with the bishop this week (no waiting: bishops make time)`
    : x.kind === 'employer' ? `lets about ${Math.round((x.flexibility ?? 0) * 100)}% of shift swaps through` : x.capacity && x.capacity > 0 ? `room for ${x.capacity}` : ''
  return (
    <>
      <div className="ta-who"><b>{x.name}</b> · {KIND_WORDS[x.kind]}{x.members !== undefined ? ` · ${x.members} ${x.kind === 'employer' ? 'employees' : x.kind === 'complex' ? 'residents' : 'members'}` : ''}</div>
      <div className="bx-note">
        {lim}{x.budget > 0 ? ` · $${x.budget.toFixed(0)} left this semester` : ''}{x.weekday >= 0 && x.kind !== 'complex' ? ` · meets on ${DAYS[x.weekday]}s` : ''}{x.food ? ' · now with food' : ''}
      </div>
      <Chart d={x} />
      <div className="in-legend"><span className="d">wanted it</span><span className="s">{x.kind === 'counseling' ? 'were seen' : x.kind === 'ward' ? 'were seen' : 'came'}</span>{x.history.some(r => r.waitlist > 0) && <span className="w">waiting</span>}</div>
      {x.queue && (
        <div className="in-sec">
          <h4>Waiting list</h4>
          <div className="bx-note">{x.queue.n_waiting} waiting · {x.queue.n_in_care} being seen · {x.queue.n_finished} finished · {x.queue.n_gave_up} gave up
            {x.queue.mean_wait_days !== null ? ` · average wait ${x.queue.mean_wait_days} days` : ''}. People in crisis go first.</div>
          <div className="ta-chips">{x.queue.waiting.map(p => <RefChip key={p.person} r={{ kind: 'person', id: p.person, label: `${p.name} · ${p.waited} d${p.crisis ? ' · crisis' : ''}`, u }} />)}</div>
        </div>
      )}
      {x.decisions.length > 0 && (
        <div className="in-sec">
          <h4>What they changed</h4>
          <div className="bk-list">{x.decisions.map((r, k) => (
            <div key={k} className="bk-li">
              <span className="when">{dayWords(start, r.day)}</span>
              <span className="grow">{r.officer !== null && <RefChip r={{ kind: 'person', id: r.officer, label: r.officer_name ?? undefined, u }} />} {r.words}
                {r.action !== 'cap' ? ` after turnout of ${Math.round(r.turnout * 100)}%` : ''}
                {r.event !== null && <> · <span className="ms-flag" style={{ cursor: 'pointer', color: 'var(--accent)' }} onClick={() => focusItem(setSel, { kind: 'event', id: r.event!, u })}>trace</span></>}</span>
            </div>))}</div>
        </div>
      )}
      {x.occasions.length > 0 && (
        <div className="in-sec">
          <h4>Events they ran</h4>
          <div className="bk-list">{x.occasions.map(o => (
            <div key={o.id} className="bk-li"><span className="when">{dayWords(start, o.day)}</span>
              <span className="grow"><RefChip r={{ kind: 'occasion', id: o.id, label: o.label, u }} /> {o.status === 'planned' ? 'coming up' : o.status === 'cancelled' ? 'called off' : `${o.came} came`}</span></div>))}</div>
        </div>
      )}
    </>
  )
}

function Picker({ onPick }: { onPick: (id: number) => void }) {
  const u = useLens().u
  const [kind, setKind] = useState('counseling')
  const [q, setQ] = useState('')
  const d = useAsync(() => instApi.list(u, kind), [u, kind])
  const rows = (d.data ?? []).filter(r => !q || r.name.toLowerCase().includes(q.toLowerCase()))
  return (
    <>
      <PanelOptions>
        <select value={kind} onChange={e => setKind(e.target.value)}>{Object.entries(KIND_WORDS).map(([k, w]) => <option key={k} value={k}>{w}</option>)}</select>
        <input type="search" placeholder="Search" value={q} onChange={e => setQ(e.target.value)} style={{ width: 100 }} />
      </PanelOptions>
      {!d.data && <Busy what="Listing organizations" />}
      {d.data && rows.length === 0 && <Empty title="None">No organization of this kind here.</Empty>}
      <div className="bk-list">{rows.slice(0, 200).map(r => (
        <div key={r.id} className="bk-li click" onClick={() => onPick(r.id)}>
          <span className="grow">{r.name}</span>
          <span className="bx-note">{r.kind === 'employer' ? '' : r.waitlist > 0 ? `${r.waitlist} waiting` : r.demand ? `${Math.round(r.served)} of ${Math.round(r.demand)}` : ''}</span>
        </div>))}</div>
    </>
  )
}

function InstitutionTool({ sel, setSel, opts, setOpts }: PanelProps) {
  const u = useLens().u
  const it = sel.item
  const placeRef = it?.kind === 'place' ? String(it.id).split(':') : null
  const found = useAsync(() => (placeRef && (placeRef[0] === 'complex' || placeRef[0] === 'ward') ? instApi.find(placeRef[0], Number(placeRef[1]), u) : Promise.resolve(null)),
    [placeRef?.join(':'), u])
  const id = it?.kind === 'institution' ? Number(it.id) : found.data?.id ?? (opts.picked as number | undefined)
  if (id === undefined || id === null) return <div className="bk"><Picker onPick={i => setOpts({ ...opts, picked: i })} /></div>
  return (
    <div className="bk">
      {it?.kind !== 'institution' && !found.data && <button className="bk-more" onClick={() => setOpts({ ...opts, picked: undefined })}>← All organizations</button>}
      <Detail id={id} setSel={setSel} />
    </div>
  )
}

export const tool: ToolDef = {
  id: 'institution',
  label: 'Institution',
  icon: 'places',
  hint: 'One organization and its limits: demand against capacity over time, waiting lists, the events it ran and what it changed.',
  group: 'places',
  order: 40,
  component: InstitutionTool,
  size: { w: 5, h: 8 },
}
