// Phone: the selected person's texts, group chats and dating app as they'd see them, with "why?" on every message
// (views/valley/Phone.tsx). Two people selected: their text thread.
import { useState } from 'react'
import { phoneApi, type PhoneViewRef } from '../../api'
import { useAsync } from '../../game'
import { Busy, Empty, Problem } from '../../kit/Bits'
import { useLens, useStore } from '../../store'
import { openListen } from '../../views/valley/Listen'
import { openPhone, Thread } from '../../views/valley/Phone'
import '../../views/valley/valley.css'
import type { PanelProps, ToolDef } from '../registry'
import { subjectPerson } from '../sel'

function PhoneTool({ sel }: PanelProps) {
  const who = subjectPerson(sel)
  const two = (sel.people ?? []).length >= 2 ? sel.people!.slice(0, 2) : null
  const { u } = useLens()
  const v = useStore(s => s.dataVersion)
  const [pick, setPick] = useState<PhoneViewRef | null>(null)
  const ib = useAsync(() => (who === null ? Promise.resolve(null) : phoneApi.inbox(who, u)), [who, u, v])
  if (two) return <div className="bk ph-tool"><Thread view={{ kind: 'dm', a: two[0], b: two[1] }} me={two[0]} /></div>
  if (who === null) return <Empty title="Nothing selected">Select a person to open their phone, or two people for their texts.</Empty>
  if (ib.error && !ib.data) return <Problem error={ib.error} />
  if (!ib.data) return <Busy what="Opening their phone" />
  const d = ib.data
  if (pick) return <div className="bk ph-tool"><Thread view={pick} me={who} onBack={() => setPick(null)} key={JSON.stringify(pick)} /></div>
  return (
    <div className="bk">
      <div className="bt-row" style={{ gap: 8, marginBottom: 6 }}>
        <button className="btn small" onClick={() => openPhone(who)}>Open full screen</button>
        <button className="btn small" onClick={() => openListen({ people: [who], title: `Listening to ${d.name.split(' ')[0]}` })}>Listen in</button>
      </div>
      <div className="bk-list">
        {d.dms.slice(0, 30).map(c => <div key={c.id} className="bk-li" style={{ cursor: 'pointer' }} onClick={() => setPick({ kind: 'dm', a: who, b: c.id })}>
          <span className="when">{c.date?.slice(5)}</span><span className="grow"><b>{c.name}</b> · {c.preview}</span></div>)}
        {d.groups.map(g => <div key={g.id} className="bk-li" style={{ cursor: 'pointer' }} onClick={() => setPick({ kind: 'group', viewer: who, t: g.id })}>
          <span className="when">group</span><span className="grow"><b>{g.name}</b>{g.member ? '' : ' (left)'}</span></div>)}
        {d.apps.map(a => <div key={a.id} className="bk-li" style={{ cursor: 'pointer' }} onClick={() => setPick({ kind: 'app', id: a.id })}>
          <span className="when">app</span><span className="grow"><b>{a.with.name.split(' ')[0]}</b> · {a.words}</span></div>)}
      </div>
      <p className="bx-note">{d.note}</p>
    </div>
  )
}

export const tool: ToolDef = {
  id: 'phone',
  label: 'Phone',
  icon: 'send',
  hint: "A person's phone: texts, group chats (only while they were in them) and dating app, with why each message was sent and how it was read.",
  group: 'talk',
  order: 31,
  component: PhoneTool,
  size: { w: 5, h: 9 },
}
