// Make it happen: change your own world (or a What-if copy) through one person — have them throw a dinner, start a
// weekly game night, text someone, meet someone new, or fall for someone. The world arranges the opportunity; the
// people involved still decide for their own reasons, so you then let time run and watch what they do.
import { useState } from 'react'
import { create } from 'zustand'
import { valleyApi } from '../../api'
import { FindPerson } from '../../bench/SelectionBar'
import { G } from '../../game'
import { useStore } from '../../store'
import { usePersonName } from '../../kit/RefChip'

export const useMake = create<{ who: number | null; set: (i: number | null) => void }>(set => ({ who: null, set: i => set({ who: i }) }))
export const openMake = (i: number) => useMake.getState().set(i)

type Kind = 'invite' | 'series' | 'reach_out' | 'introduce' | 'spark' | 'ask_out' | 'break_up' | 'go_home'
const CHOICES: { k: Kind; icon: string; t: string; d: string }[] = [
  { k: 'invite', icon: 'home', t: 'Throw a get-together', d: 'A dinner, game night or party: they invite people and see who comes.' },
  { k: 'series', icon: 'clock', t: 'Start a weekly tradition', d: 'Sunday dinner, Tuesday game night: the same people, every week.' },
  { k: 'reach_out', icon: 'send', t: 'Get in touch with someone', d: 'A text, or dropping by. Only people they know.' },
  { k: 'introduce', icon: 'people', t: 'Meet someone new', d: 'You set it up: the two of them meet for a bit.' },
  { k: 'ask_out', icon: 'rings', t: 'Ask someone out', d: 'Today, someone they know. The answer is the other person\'s.' },
  { k: 'spark', icon: 'heart', t: 'Fall for someone', d: 'Give them feelings for someone they know. Whether they ask, and the answer, is up to them.' },
  { k: 'break_up', icon: 'close', t: 'End it', d: 'Break up with the person they\'re seeing.' },
  { k: 'go_home', icon: 'key', t: 'Go home for a bit', d: 'A few days with family. They\'re away from Provo until they\'re back.' },
]
const KINDS = [['dinner', 'a dinner'], ['game_night', 'a game night'], ['party', 'a party'], ['gathering', 'a hangout'], ['study_group', 'a study group']]
const GROUPS = [['friends', 'their friends'], ['close_friends', 'their close friends'], ['roommates', 'their roommates'], ['housemates', 'everyone in their apartment'], ['neighbors', 'their neighbors']]
const DAYS = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']

export function MakeItHappen() {
  const { who, set } = useMake()
  const status = useStore(s => s.status)
  const name = usePersonName('base')
  const [k, setK] = useState<Kind>('invite')
  const [f, setF] = useState<Record<string, any>>({ kind: 'dinner', group: 'friends', weekday: 'friday', start: '19:00', channel: 'text' })
  const [other, setOther] = useState<{ id: number; name: string } | null>(null)
  const [world, setWorld] = useState<'original' | 'whatif'>('original')
  const [res, setRes] = useState<{ checked?: any; done?: any; error?: string } | null>(null)
  const [busy, setBusy] = useState(false)
  if (who === null) return null
  const me = name(who), first = me.split(' ')[0]
  const reset = () => setRes(null)
  const needOther = k === 'reach_out' || k === 'introduce' || k === 'spark' || k === 'ask_out'
  const action = (): any => {
    if (k === 'invite' || k === 'series') return { action: k, as: who, kind: f.kind, people: f.group, weekday: f.weekday, start: f.start }
    if (k === 'reach_out') return { action: 'reach_out', as: who, to: other?.id, channel: f.channel }
    if (k === 'introduce') return { action: 'introduce', a: who, b: other?.id }
    if (k === 'ask_out') return { action: 'ask_out', as: who, to: other?.id }
    if (k === 'break_up') return { action: 'break_up', as: who }
    if (k === 'go_home') return { action: 'go_home', as: who, nights: f.nights ?? 2 }
    return { action: 'spark', from: who, to: other?.id, strength: 0.8 }
  }
  const run = async (doIt: boolean) => {
    setBusy(true)
    try {
      if (doIt) {
        const r = await valleyApi.act(action(), world)
        setRes({ done: r, checked: res?.checked })
        if (r.ok !== false) { useStore.getState().refreshStatus?.(); useStore.getState().toast?.({ kind: 'world', title: r.summary ?? 'Done', body: 'Let time run to see what they decide.', ttl: 6000 }) }
      } else setRes({ checked: await valleyApi.check(action(), world) })
    } catch (e: any) { setRes({ error: String(e?.message ?? e) }) }
    setBusy(false)
  }
  const r = res?.checked
  const close = () => { set(null); setRes(null); setOther(null) }
  return (
    <div className="sc-veil" onMouseDown={e => { if (e.target === e.currentTarget) close() }}>
      <section className="mk" role="dialog" aria-label="Make something happen">
        <header className="sc-h">
          <div className="grow">
            <div className="eyebrow">Make it happen</div>
            <h2>What should {first} do?</h2>
            <div className="secondary small">You arrange the chance; {first} and everyone else still decide for their own reasons.</div>
          </div>
          <button className="bx-icon" onClick={close} title="Close (Esc)">{G.close}</button>
        </header>
        <div className="mk-choices">
          {CHOICES.map(c => (
            <button key={c.k} className={`mk-choice ${k === c.k ? 'on' : ''}`} onClick={() => { setK(c.k); reset() }}>
              <span className="mk-i">{G[c.icon]}</span><span><b>{c.t}</b><small>{c.d}</small></span>
            </button>
          ))}
        </div>
        <div className="mk-form">
          {(k === 'invite' || k === 'series') && <p className="mk-sentence">
            {first} {k === 'series' ? 'starts' : 'throws'} <select value={f.kind} onChange={e => { setF({ ...f, kind: e.target.value }); reset() }}>{KINDS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select>
            {' '}for <select value={f.group} onChange={e => { setF({ ...f, group: e.target.value }); reset() }}>{GROUPS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select>
            {' '}{k === 'series' ? 'every' : 'on'} <select value={f.weekday} onChange={e => { setF({ ...f, weekday: e.target.value }); reset() }}>{DAYS.map(d => <option key={d} value={d}>{d[0].toUpperCase() + d.slice(1)}</option>)}</select>
            {' '}at <input type="time" value={f.start} onChange={e => { setF({ ...f, start: e.target.value }); reset() }} />
          </p>}
          {k === 'break_up' && <p className="mk-sentence">{first} ends things with the person they're seeing. Press Check to see who.</p>}
          {k === 'go_home' && <p className="mk-sentence">{first} goes home for <select value={f.nights ?? 2} onChange={e => { setF({ ...f, nights: Number(e.target.value) }); reset() }}>
            {[1, 2, 3, 5, 7, 14].map(n => <option key={n} value={n}>{n} night{n === 1 ? '' : 's'}</option>)}</select>, starting today</p>}
          {needOther && <div className="mk-sentence">
            {k === 'reach_out' ? <>{first} <select value={f.channel} onChange={e => { setF({ ...f, channel: e.target.value }); reset() }}><option value="text">texts</option><option value="in_person">drops by to see</option></select></>
              : k === 'introduce' ? <>{first} meets</> : k === 'ask_out' ? <>{first} asks out</> : <>{first} falls for</>}
            {' '}{other ? <span className="pill">{other.name} <button className="bx-icon" onClick={() => { setOther(null); reset() }}>{G.close}</button></span>
              : <span className="mk-find"><FindPerson onPick={(id, nm) => { setOther({ id, name: nm }); reset() }} /></span>}
          </div>}
          <div className="mk-world" role="radiogroup" aria-label="Where">
            <label><input type="radio" checked={world === 'original'} onChange={() => { setWorld('original'); reset() }} /> <b>In my world</b> <small>it becomes part of this world's history</small></label>
            <label><input type="radio" checked={world === 'whatif'} onChange={() => { setWorld('whatif'); reset() }} /> <b>In a What-if</b> <small>{status?.has_alt ? 'the What-if world gets it; the Original stays as it is' : 'split the world first, so you can compare'}</small></label>
          </div>
        </div>
        {res?.error && <div className="bk-bad">{res.error}</div>}
        {r && (
          <div className="mk-check">
            {r.summary && <div><b>{r.summary}</b></div>}
            {r.problems?.map((p: string, i: number) => <div key={i} className="bk-bad">{p}</div>)}
            {r.warnings?.map((p: string, i: number) => <div key={i} className="bx-note">{p}</div>)}
            {r.people?.length > 0 && <div className="mk-people">{r.people.slice(0, 12).map((p: any) => <span key={p.id} className={`pill ${p.free ? '' : 'mk-busy'}`} title={p.reason}>{p.name}{p.free ? '' : ' · busy'}</span>)}{r.people.length > 12 && <span className="small muted">and {r.people.length - 12} more</span>}</div>}
          </div>
        )}
        {res?.done && (res.done.ok === false
          ? <div className="bk-bad">Not done: {(res.done.problems ?? []).join(' ')}</div>
          : <div className="bk-ok">Done{res.done.world === 'Original' ? ' in your world' : ' in the What-if'}. Let time run and watch what happens.</div>)}
        <footer className="sc-f">
          <button className="btn" disabled={busy || (needOther && !other)} onClick={() => run(false)}>Check</button>
          <button className="btn primary" disabled={busy || !r?.ok || !!res?.done} onClick={() => run(true)}>Make it happen</button>
          <span className="spacer" />
          {needOther && !other && <span className="small muted">Pick who.</span>}
        </footer>
      </section>
    </div>
  )
}
