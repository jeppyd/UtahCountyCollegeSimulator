// Chats: how people coordinate by text. For a person, their group chats (apartment, friends, club, team, ward) and the
// messages they sent or got — invitations, check-ins, replies, and silences with how they were read. For a chat, its
// members and messages. For an event, how the news spread: who heard, from whom and when. Everything is a chip.
import { useState } from 'react'
import { msgApi, type MsgAct } from '../../api'
import { useAsync } from '../../game'
import { Busy, dayWords, Empty, Problem, useWorldDays } from '../../kit/Bits'
import { RefChip } from '../../kit/RefChip'
import { useLens, useStore } from '../../store'
import type { PanelProps, ToolDef } from '../registry'
import { focusItem, subjectPerson } from '../sel'
import '../../kit/talk.css'

const KIND_WORDS: Record<string, string> = { household: 'Apartment', friends: 'Friends', club: 'Club', team: 'Team', ward: 'Ward', family: 'Family' }
const READ_AS: Record<string, string> = { felt_ignored: 'they felt ignored', assumed_busy: 'they figured it was just busy' }

function Act({ a, u, start, setSel }: { a: MsgAct; u: 'base' | 'alt'; start?: string; setSel: PanelProps['setSel'] }) {
  return (
    <div className={`bk-li ${a.kind === 'silence' ? 'ms-silence' : ''}`}>
      <span className="when">{dayWords(start, a.day)}</span>
      <span className="grow">
        <RefChip r={{ kind: 'person', id: a.sender, label: a.sender_name ?? undefined, u }} /> {a.words}
        {a.to !== null && <> {a.kind === 'silence' ? 'to' : a.kind === 'reply' ? 'to' : 'with'} <RefChip r={{ kind: 'person', id: a.to, label: a.to_name ?? undefined, u }} /></>}
        {a.occasion && <> — <RefChip r={{ kind: 'occasion', id: a.occasion.id, label: a.occasion.label, u }} /></>}
        {a.news && <> — <RefChip r={{ kind: 'event', id: a.news.id, label: a.news.label, u }} /></>}
        {a.kind === 'checkin' && a.replied_day === null && <span className="ms-flag"> no reply yet</span>}
        {a.read_as && a.event !== null && <> — <span className="ms-flag" onClick={() => focusItem(setSel, { kind: 'event', id: a.event!, u })} style={{ cursor: 'pointer' }}>{READ_AS[a.read_as] ?? a.read_as}</span></>}
      </span>
    </div>
  )
}

function PersonChats({ i, sel, setSel }: { i: number } & Pick<PanelProps, 'sel' | 'setSel'>) {
  const u = useLens().u
  const v = useStore(s => s.dataVersion)
  const { start } = useWorldDays()
  const [kind, setKind] = useState('')
  const d = useAsync(() => msgApi.person(i, u), [i, u, v])
  if (d.error && !d.data) return <Problem error={d.error} />
  if (!d.data) return <Busy what="Reading their messages" />
  const acts = d.data.acts.filter(a => !kind || a.kind === kind)
  return (
    <>
      <div className="ta-who"><RefChip r={{ kind: 'person', id: i, label: d.data.name, u }} />
        {d.data.threads.length ? 'is in' : 'is in no group chats right now.'}
        {d.data.threads.map(t => (
          <RefChip key={t.id} r={{ kind: 'thread', id: t.id, label: `${KIND_WORDS[t.kind] ?? t.kind}: ${t.name}${t.muted ? ' (muted)' : ''}`, u }} />
        ))}
      </div>
      <div className="bt-row" style={{ gap: 6, margin: '4px 0' }}>
        <select value={kind} onChange={e => setKind(e.target.value)}>
          <option value="">All messages</option><option value="checkin">Check-ins</option><option value="reply">Replies</option>
          <option value="silence">Silences</option><option value="invite">Invitations</option><option value="news">News</option><option value="plan_change">Plans called off</option>
        </select>
        <span className="bx-note">Recorded messages from the last 60 days; everyday chatter is only counted.</span>
      </div>
      {acts.length === 0 ? <Empty title="No recorded messages">Nothing of this kind lately.</Empty> :
        <div className="bk-list">{acts.map(a => <Act key={a.id} a={a} u={u} start={start} setSel={setSel} />)}</div>}
      {void sel}
    </>
  )
}

function Thread({ t, setSel }: { t: number; setSel: PanelProps['setSel'] }) {
  const u = useLens().u
  const v = useStore(s => s.dataVersion)
  const { start } = useWorldDays()
  const d = useAsync(() => msgApi.thread(t, u), [t, u, v])
  if (d.error && !d.data) return <Problem error={d.error} />
  if (!d.data) return <Busy what="Opening the chat" />
  const now = d.data.members.filter(m => m.left === null)
  return (
    <>
      <div className="ta-who"><b>{d.data.name}</b> · {KIND_WORDS[d.data.kind]} chat{d.data.active ? '' : ' (gone quiet)'} · about {d.data.volume.toFixed(0)} messages a day
        {d.data.creator !== null && <> · started by <RefChip r={{ kind: 'person', id: d.data.creator, u }} /></>}</div>
      <div className="ta-chips" style={{ marginBottom: 6 }}>
        {now.slice(0, 40).map(m => <RefChip key={m.id} r={{ kind: 'person', id: m.id, label: m.name + (m.muted ? ' (muted)' : ''), u }} />)}
        {now.length > 40 && <span className="bx-note">+{now.length - 40} more</span>}
      </div>
      {d.data.members.some(m => m.left !== null) && <div className="bx-note">Left: {d.data.members.filter(m => m.left !== null).map(m => m.name).join(', ')}</div>}
      {d.data.acts.length === 0 ? <Empty title="No recorded messages">Only everyday chatter so far.</Empty> :
        <div className="bk-list">{d.data.acts.map(a => <Act key={a.id} a={a} u={u} start={start} setSel={setSel} />)}</div>}
    </>
  )
}

function NewsSpread({ e }: { e: number }) {
  const u = useLens().u
  const { start } = useWorldDays()
  const d = useAsync(() => msgApi.news(e, u), [e, u])
  if (d.error && !d.data) return <Problem error={d.error} />
  if (!d.data) return <Busy what="Following the news" />
  if (!d.data.tracked) return <Empty title="Not news">This kind of event isn't passed on as news (or it is older than the record keeps).</Empty>
  const kids = new Map<number, typeof d.data.knowers>()
  d.data.knowers.forEach(k => { const a = kids.get(k.source) ?? []; a.push(k); kids.set(k.source, a) })
  const day0 = d.data.knowers[0]?.day ?? 0
  const seen = new Set<number>()
  const Node = ({ src, depth }: { src: number; depth: number }) => (
    <>{(kids.get(src) ?? []).map(k => {
      if (seen.has(k.person) || depth > 6) return null
      seen.add(k.person)
      return (
        <div key={k.person}>
          <div className="ms-node" style={{ paddingLeft: depth * 14 }}>
            <span className="when">{k.day === day0 ? 'same day' : `+${k.day - day0} d`}</span>
            <RefChip r={{ kind: 'person', id: k.person, label: k.name, u }} /> <span className="bx-note">{src < 0 ? 'it happened to them' : k.channel}</span>
          </div>
          <Node src={k.person} depth={depth + 1} />
        </div>
      )
    })}</>
  )
  return (
    <>
      <div className="ta-who">How the news spread: <RefChip r={{ kind: 'event', id: e, label: d.data.event.label, u }} /> on {dayWords(start, d.data.event.day)} — {d.data.knowers.length} people heard.</div>
      <div className="bk-list"><Node src={-1} depth={0} /></div>
    </>
  )
}

function ChatsTool({ sel, setSel }: PanelProps) {
  const it = sel.item
  if (it?.kind === 'thread') return <div className="bk"><Thread t={Number(it.id)} setSel={setSel} /></div>
  if (it?.kind === 'event') return <div className="bk"><NewsSpread e={Number(it.id)} /></div>
  const who = subjectPerson(sel)
  if (who === null) return <Empty title="Nothing selected">Select a person to see their chats and messages, a chat to open it, or an event to see how the news spread.</Empty>
  return <div className="bk"><PersonChats i={who} sel={sel} setSel={setSel} /></div>
}

export const tool: ToolDef = {
  id: 'chats',
  label: 'Chats',
  icon: 'send',
  hint: "A person's group chats and messages (check-ins, replies, silences, invitations), a chat's members, or how news of an event spread.",
  group: 'talk',
  order: 30,
  component: ChatsTool,
  size: { w: 5, h: 8 },
}
