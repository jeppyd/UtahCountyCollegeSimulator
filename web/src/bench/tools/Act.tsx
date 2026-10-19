// Act: change something in the What-if world — invite people to a dinner, start a weekly get-together, introduce two
// people, or have someone get in touch — either as the world's editor or as the selected person (who can only invite
// people they know, when they're free). Check first: it shows who is free, how far they'd travel and why not. The
// people involved still decide for their own reasons; the Original world never changes.
import { useState } from 'react'
import { benchApi } from '../../api'
import { useStore } from '../../store'
import { Empty } from '../../kit/Bits'
import { RefChip, usePersonName } from '../../kit/RefChip'
import type { PanelProps, ToolDef } from '../registry'
import { selPeople, subjectPerson } from '../sel'

const KINDS = [['dinner', 'Dinner'], ['gathering', 'Hanging out'], ['game_night', 'Game night'], ['party', 'Party'], ['study_group', 'Study group']]
const GROUPS = [['roommates', 'their roommates'], ['housemates', 'everyone in their apartment'], ['neighbors', 'neighbors'], ['friends', 'their friends'], ['close_friends', 'their close friends']]
const DAYS = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
const WORDS: Record<string, string> = { invite: 'Invite people', series: 'Start a weekly get-together', introduce: 'Introduce two people', reach_out: 'Get in touch' }

function ActTool({ sel }: PanelProps) {
  const name = usePersonName('base')
  const status = useStore(s => s.status)
  const who = subjectPerson(sel)
  const picked = selPeople(sel)
  const [f, setF] = useState<Record<string, any>>({ action: 'invite', asPerson: true, kind: 'dinner', group: 'friends', weekday: 'sunday', start: '19:00', channel: 'text' })
  const [res, setRes] = useState<{ checked?: any; done?: any; error?: string } | null>(null)
  const [busy, setBusy] = useState(false)
  const set = (o: Record<string, any>) => { setF({ ...f, ...o }); setRes(null) }
  const others = picked.filter(i => i !== who)
  const actor = f.asPerson && who !== null ? who : undefined

  const body = (): any => {
    const a: any = { action: f.action }
    if (actor !== undefined) a.as = actor
    if (f.action === 'invite' || f.action === 'series') {
      a.kind = f.kind; a.weekday = f.weekday; a.start = f.start
      a.people = f.group === 'picked' ? others : f.group
      if (actor === undefined) a.host = who
    } else if (f.action === 'introduce') {
      a.a = others[0]; a.b = others[1]
      if (actor === undefined && who !== null) a.by = who
    } else if (f.action === 'reach_out') {
      a.to = others[0]; a.channel = f.channel
      if (actor === undefined) a.from = who
    }
    return a
  }
  const run = async (doIt: boolean) => {
    setBusy(true)
    try {
      if (doIt) { const r = await benchApi.act(body()); setRes({ done: r }); if (r.ok !== false) useStore.getState().refreshStatus?.() }
      else setRes({ checked: await benchApi.actCheck(body()) })
    } catch (e: any) { setRes({ error: String(e?.message ?? e) }) }
    setBusy(false)
  }

  if (who === null) return <Empty title="Nobody selected">Select the person who acts (or hosts) first; for an introduction, select three people: the one who introduces, then the two who meet.</Empty>
  const need = f.action === 'introduce' ? others.length < 2 : f.action === 'reach_out' ? others.length < 1 : f.group === 'picked' && others.length < 1
  const r = res?.checked ?? res?.done
  return (
    <div className="bk">
      <div className="bk-sub">Changes happen in the What-if world{status?.has_alt ? '' : ' (made from the Original the first time you do something)'}; the people involved still decide for their own reasons.</div>
      <div className="bk-form">
        <label>Do</label>
        <select value={f.action} onChange={e => set({ action: e.target.value })}>{Object.entries(WORDS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select>
        <label>Who acts</label>
        <span className="bt-row">
          <label className="bt-row"><input type="radio" checked={f.asPerson} onChange={() => set({ asPerson: true })} /> as <RefChip r={{ kind: 'person', id: who, label: name(who) }} plain /></label>
          <label className="bt-row" title="Arrange it as the world's editor, without the person's limits"><input type="radio" checked={!f.asPerson} onChange={() => set({ asPerson: false })} /> as the editor</label>
        </span>
        {(f.action === 'invite' || f.action === 'series') && <>
          <label>What</label>
          <select value={f.kind} onChange={e => set({ kind: e.target.value })}>{KINDS.map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select>
          <label>Whom</label>
          <select value={f.group} onChange={e => set({ group: e.target.value })}>
            {GROUPS.map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            <option value="picked">the other selected people ({others.length})</option>
          </select>
          <label>When</label>
          <span className="bt-row">
            <select value={f.weekday} onChange={e => set({ weekday: e.target.value })}>{DAYS.map(d => <option key={d} value={d}>{f.action === 'series' ? `every ${d}` : `next ${d}`}</option>)}</select>
            <input type="time" value={f.start} onChange={e => set({ start: e.target.value })} />
          </span>
        </>}
        {f.action === 'introduce' && <><label>Who meets</label><span>{others.length >= 2 ? <><RefChip r={{ kind: 'person', id: others[0] }} /> and <RefChip r={{ kind: 'person', id: others[1] }} /></> : 'select two more people'}</span></>}
        {f.action === 'reach_out' && <>
          <label>To</label><span>{others.length ? <RefChip r={{ kind: 'person', id: others[0] }} /> : 'select one more person'}</span>
          <label>How</label>
          <select value={f.channel} onChange={e => set({ channel: e.target.value })}><option value="text">a text</option><option value="in_person">in person</option></select>
        </>}
      </div>
      <div className="bt-row" style={{ marginTop: 6 }}>
        <button className="btn small" disabled={busy || need} onClick={() => run(false)}>Check</button>
        <button className="btn small primary" disabled={busy || need || !res?.checked?.ok} onClick={() => run(true)} title={res?.checked?.ok ? 'Do it in the What-if world' : 'Check it first'}>Do it</button>
        {need && <span className="bx-note">Select the people it involves (in People or on the Map).</span>}
      </div>
      {res?.error && <div className="bk-bad">{res.error}</div>}
      {r && (
        <div className="bk-why">
          {r.summary && <div><b>{r.summary}</b></div>}
          {res?.done && (r.ok === false ? <div className="bk-bad">Not done.</div> : <div className="bk-ok">Done in the What-if world{r.made_whatif ? ' (made just now)' : ''}. Run time forward to see what people decide.</div>)}
          {r.problems?.map((p: string, k: number) => <div key={k} className="bk-bad">{p}</div>)}
          {r.warnings?.map((p: string, k: number) => <div key={k} className="bx-note">{p}</div>)}
          {r.people?.length > 0 && (
            <div className="bk-list">
              {r.people.slice(0, 30).map((p: any) => (
                <div key={p.id} className="bk-li">
                  <span className="grow"><RefChip r={{ kind: 'person', id: p.id, label: p.name }} /><span className="bx-note">{p.role}</span></span>
                  <span className={p.free ? 'bk-ok' : 'bk-bad'} style={{ fontSize: 12 }}>{p.reason}</span>
                </div>
              ))}
              {r.people.length > 30 && <div className="bx-note">and {r.people.length - 30} more</div>}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

export const tool: ToolDef = {
  id: 'act',
  label: 'Act',
  icon: 'send',
  hint: 'Change the What-if world: invite people, start a weekly dinner, introduce two people, or get in touch — as the editor or as someone.',
  group: 'world',
  order: 30,
  component: ActTool,
  size: { w: 5, h: 7 },
  needs: ['people'],
}
