// Make it happen: change your own world (or a What-if copy) through one person — have them throw a dinner, start a
// weekly game night, text someone, meet someone new, make up after a fight, fall for someone, get set up on a blind
// date, take a job offer or have something happen to them. The world arranges the opportunity; the people involved
// still decide for their own reasons, so you then let time run and watch what they do. The other person is found
// with filters (PersonFinder), not by guessing names.
import { useEffect, useState } from 'react'
import { create } from 'zustand'
import { valleyApi } from '../../api'
import { G, useAsync } from '../../game'
import { useStore } from '../../store'
import { usePersonName } from '../../kit/RefChip'
import { PersonFinder } from './PersonFinder'

export const useMake = create<{ who: number | null; set: (i: number | null) => void }>(set => ({ who: null, set: i => set({ who: i }) }))
export const openMake = (i: number) => useMake.getState().set(i)

type Kind = 'invite' | 'series' | 'reach_out' | 'introduce' | 'make_up' | 'fall_out' | 'spark' | 'ask_out' | 'set_up' | 'break_up'
  | 'go_home' | 'job_offer' | 'happen'
type Choice = { k: Kind; icon: string; t: string; d: string; other?: string }
// `other`: the person to pick, and which of the subject's people the finder starts on
const GROUPS: { label: string; items: Choice[] }[] = [
  { label: 'Get together', items: [
    { k: 'invite', icon: 'home', t: 'Throw a get-together', d: 'A dinner, game night or party: they invite people and see who comes.' },
    { k: 'series', icon: 'clock', t: 'Start a weekly tradition', d: 'Sunday dinner, Tuesday game night: the same people, every week.' },
  ] },
  { label: 'Friends and drama', items: [
    { k: 'reach_out', icon: 'send', t: 'Get in touch', d: 'A text, or dropping by. Only people they know.', other: 'knows' },
    { k: 'introduce', icon: 'people', t: 'Meet someone new', d: 'You set it up: the two of them meet for a bit.', other: 'strangers' },
    { k: 'fall_out', icon: 'close', t: 'Have a falling-out', d: 'A fight with someone they know. The hurt stays on their tie until it heals or they make up.', other: 'knows' },
    { k: 'make_up', icon: 'link', t: 'Make up', d: 'They go to make things right. Whether the other lets it go is up to them.', other: 'tense' },
  ] },
  { label: 'Romance', items: [
    { k: 'ask_out', icon: 'rings', t: 'Ask someone out', d: 'Today, someone they know. The answer is the other person\'s.', other: 'knows' },
    { k: 'spark', icon: 'heart', t: 'Fall for someone', d: 'Feelings for someone they know, or both ways. What they do about it is up to them.', other: 'knows' },
    { k: 'set_up', icon: 'spark', t: 'Set them up', d: 'A blind date at a café. They arrive hopeful; whether they click is theirs.', other: 'strangers' },
    { k: 'break_up', icon: 'close', t: 'End it', d: 'Break up with the person they\'re seeing.' },
  ] },
  { label: 'Life', items: [
    { k: 'go_home', icon: 'key', t: 'Go home for a bit', d: 'A few days with family. They\'re away from Provo until they\'re back.' },
    { k: 'job_offer', icon: 'work', t: 'Get a job offer', d: 'A nearby workplace offers hours. Taking it is their call, around their classes.' },
    { k: 'happen', icon: 'bell', t: 'Something happens to them', d: 'An illness, a failed exam, a family crisis, a spiritual experience: they live with it.' },
  ] },
]
const CHOICES = GROUPS.flatMap(g => g.items)
const KINDS = [['dinner', 'a dinner'], ['game_night', 'a game night'], ['party', 'a party'], ['gathering', 'a hangout'], ['study_group', 'a study group']]
const PEOPLE = [['friends', 'their friends'], ['close_friends', 'their close friends'], ['roommates', 'their roommates'], ['housemates', 'everyone in their apartment'], ['neighbors', 'their neighbors']]
const DAYS = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
const HAPPENINGS = ['illness', 'car_accident', 'exam_failure', 'academic_success', 'family_crisis', 'death_in_family', 'financial_hardship',
  'spiritual_experience', 'faith_challenge']
const SEVERITY: [number, string][] = [[0.5, 'mildly'], [1, 'as it usually hits'], [2, 'hard'], [3, 'very hard']]
const FEEL: [number, string][] = [[0.4, 'a little'], [0.7, 'a real crush'], [0.95, 'head over heels']]
const OPEN: [number, string][] = [[0.1, 'curious'], [0.25, 'hopeful'], [0.45, 'really hoping it works']]
const FALL: [string, string][] = [['small', 'have words'], ['real', 'have a real falling-out'], ['big', 'have a blowup']]

export function MakeItHappen() {
  const { who, set } = useMake()
  const status = useStore(s => s.status)
  const registry = useStore(s => s.registry)
  const name = usePersonName('base')
  const [k, setK] = useState<Kind>('invite')
  const [f, setF] = useState<Record<string, any>>({ kind: 'dinner', group: 'friends', weekday: 'friday', start: '19:00', channel: 'text',
    how: 'real', strength: 0.7, mutual: false, open: 0.25, event: 'illness', severity: 1, hours: 15, wage: 14, employer: '' })
  const [other, setOther] = useState<{ id: number; name: string } | null>(null)
  const [world, setWorld] = useState<'original' | 'whatif'>('original')
  const [res, setRes] = useState<{ checked?: any; done?: any; error?: string } | null>(null)
  const [busy, setBusy] = useState(false)
  const u = world === 'original' || !status?.has_alt ? 'base' : 'alt'
  const jobs = useAsync(() => (who !== null && k === 'job_offer' ? valleyApi.workplaces(who, u) : Promise.resolve([])), [who, k, u], false)
  useEffect(() => { setOther(null); setRes(null) }, [who])
  if (who === null) return null
  const me = name(who), first = me.split(' ')[0]
  const choice = CHOICES.find(c => c.k === k)!
  const needOther = !!choice.other
  const reset = () => setRes(null)
  const put = (patch: Record<string, any>) => { setF({ ...f, ...patch }); reset() }
  const action = (): any => {
    const to = other?.id
    switch (k) {
      case 'invite': case 'series': return { action: k, as: who, kind: f.kind, people: f.group, weekday: f.weekday, start: f.start }
      case 'reach_out': return { action: 'reach_out', as: who, to, channel: f.channel }
      case 'introduce': return { action: 'introduce', a: who, b: to }
      case 'make_up': return { action: 'make_up', as: who, to }
      case 'fall_out': return { action: 'fall_out', a: who, b: to, how: f.how }
      case 'ask_out': return { action: 'ask_out', as: who, to }
      case 'spark': return { action: 'spark', from: who, to, strength: f.strength, mutual: f.mutual }
      case 'set_up': return { action: 'set_up', a: who, b: to, open: f.open }
      case 'break_up': return { action: 'break_up', as: who }
      case 'go_home': return { action: 'go_home', as: who, nights: f.nights ?? 2 }
      case 'job_offer': return { action: 'job_offer', to: who, hours: f.hours, wage: f.wage, ...(f.employer !== '' ? { employer: Number(f.employer) } : {}) }
      case 'happen': return { action: 'happen', who, event: f.event, severity: f.severity }
    }
  }
  const run = async (doIt: boolean) => {
    setBusy(true)
    try {
      if (doIt) {
        const r = await valleyApi.act(action(), world)
        setRes({ done: r, checked: res?.checked })
        if (r.ok !== false) { useStore.getState().refreshStatus?.(); useStore.getState().toast?.({ kind: 'world', title: r.summary ?? 'Done', body: outcome(r, other?.name ?? '') ?? 'Let time run to see what they decide.', ttl: 6000 }) }
      } else setRes({ checked: await valleyApi.check(action(), world) })
    } catch (e: any) { setRes({ error: String(e?.message ?? e) }) }
    setBusy(false)
  }
  const r = res?.checked
  const close = () => { set(null); setRes(null); setOther(null) }
  const sel = (key: string, opts: [any, string][], num = false) =>
    <select value={f[key]} onChange={e => put({ [key]: num ? Number(e.target.value) : e.target.value })}>{opts.map(([v, l]) => <option key={String(v)} value={v}>{l}</option>)}</select>
  const pick = <>{other
    ? <span className="pill">{other.name} <button className="bx-icon" title="Pick someone else" onClick={() => { setOther(null); reset() }}>{G.close}</button></span>
    : <span className="muted">someone (pick below)</span>}</>
  return (
    <div className="sc-veil" onMouseDown={e => { if (e.target === e.currentTarget) close() }}>
      <section className="mk" role="dialog" aria-label="Make something happen">
        <header className="sc-h">
          <div className="grow">
            <div className="eyebrow">Make it happen</div>
            <h2>What should happen to {first}?</h2>
            <div className="secondary small">You arrange the chance; {first} and everyone else still decide for their own reasons.</div>
          </div>
          <button className="bx-icon" onClick={close} title="Close (Esc)">{G.close}</button>
        </header>
        <div className="mk-body">
          <div className="mk-groups">
            {GROUPS.map(g => (
              <div key={g.label} className="mk-group">
                <div className="mk-gl">{g.label}</div>
                <div className="mk-chips">
                  {g.items.map(c => (
                    <button key={c.k} className={`mk-chip ${k === c.k ? 'on' : ''}`} title={c.d} onClick={() => { setK(c.k); reset() }}>
                      <span className="mk-i">{G[c.icon]}</span>{c.t}
                    </button>
                  ))}
                </div>
              </div>
            ))}
          </div>
          <div className="mk-form">
            <div className="small secondary">{choice.d}</div>
            {(k === 'invite' || k === 'series') && <p className="mk-sentence">
              {first} {k === 'series' ? 'starts' : 'throws'} {sel('kind', KINDS as any)}
              {' '}for {sel('group', PEOPLE as any)}
              {' '}{k === 'series' ? 'every' : 'on'} {sel('weekday', DAYS.map(d => [d, d[0].toUpperCase() + d.slice(1)]))}
              {' '}at <input type="time" value={f.start} onChange={e => put({ start: e.target.value })} />
            </p>}
            {k === 'reach_out' && <p className="mk-sentence">{first} {sel('channel', [['text', 'texts'], ['in_person', 'drops by to see']])} {pick}</p>}
            {k === 'introduce' && <p className="mk-sentence">{first} meets {pick}</p>}
            {k === 'make_up' && <p className="mk-sentence">{first} goes to {pick} to make things right</p>}
            {k === 'fall_out' && <p className="mk-sentence">{first} and {pick} {sel('how', FALL)}</p>}
            {k === 'ask_out' && <p className="mk-sentence">{first} asks out {pick}</p>}
            {k === 'spark' && <p className="mk-sentence">
              {first} falls for {pick}: {sel('strength', FEEL, true)}
              <label className="mk-inline"><input type="checkbox" checked={!!f.mutual} onChange={e => put({ mutual: e.target.checked })} /> and they fall for {first} too</label>
            </p>}
            {k === 'set_up' && <p className="mk-sentence">{first} goes on a blind date with {pick}, both {sel('open', OPEN, true)}</p>}
            {k === 'break_up' && <p className="mk-sentence">{first} ends things with the person they're seeing. Press Check to see who.</p>}
            {k === 'go_home' && <p className="mk-sentence">{first} goes home for {sel('nights', [1, 2, 3, 5, 7, 14].map(n => [n, `${n} night${n === 1 ? '' : 's'}`]), true)}, starting today</p>}
            {k === 'job_offer' && <p className="mk-sentence">
              <select value={f.employer} onChange={e => put({ employer: e.target.value })}>
                <option value="">The nearest workplace</option>
                {(jobs.data ?? []).map(j => <option key={j.id} value={j.id}>{j.name} ({j.type}, {j.km} km)</option>)}
              </select>
              offers {first} <input type="number" min={2} max={60} style={{ width: 64 }} value={f.hours} onChange={e => put({ hours: Number(e.target.value) })} /> hours a week
              at $<input type="number" min={7} max={60} step={0.25} style={{ width: 72 }} value={f.wage} onChange={e => put({ wage: Number(e.target.value) })} />/h
            </p>}
            {k === 'happen' && <p className="mk-sentence">
              {first}: {sel('event', HAPPENINGS.map(e => [e, registry?.events?.[e]?.label ?? e.replace(/_/g, ' ')]))}, {sel('severity', SEVERITY, true)}
            </p>}
            {needOther && !other && <PersonFinder key={k} around={who} first={first} relation={choice.other} u={u}
              onPick={(id, nm) => { setOther({ id, name: nm }); reset() }} />}
            <div className="mk-world" role="radiogroup" aria-label="Where">
              <label><input type="radio" checked={world === 'original'} onChange={() => { setWorld('original'); reset() }} /> <b>In my world</b> <small>it becomes part of this world's history</small></label>
              <label><input type="radio" checked={world === 'whatif'} onChange={() => { setWorld('whatif'); reset() }} /> <b>In a What-if</b> <small>{status?.has_alt ? 'the What-if world gets it; the Original stays as it is' : 'split the world first, so you can compare'}</small></label>
            </div>
          </div>
          {res?.error && <div className="bk-bad mk-msg">{res.error}</div>}
          {r && (
            <div className="mk-check">
              {r.summary && <div><b>{r.summary}</b></div>}
              {r.problems?.map((p: string, i: number) => <div key={i} className="bk-bad">{p}</div>)}
              {r.warnings?.map((p: string, i: number) => <div key={i} className="bx-note">{p}</div>)}
              {r.people?.length > 0 && <div className="mk-people">{r.people.slice(0, 12).map((p: any) => <span key={p.id} className={`pill ${p.free ? '' : 'mk-busy'}`} title={p.reason}>{p.name}{p.free ? '' : ' · busy'}</span>)}{r.people.length > 12 && <span className="small muted">and {r.people.length - 12} more</span>}</div>}
            </div>
          )}
          {res?.done && (res.done.ok === false
            ? <div className="bk-bad mk-msg">Not done: {(res.done.problems ?? []).join(' ')}</div>
            : <div className="bk-ok mk-msg">Done{res.done.world === 'Original' ? ' in your world' : ' in the What-if'}. {outcome(res.done, other?.name ?? '') ?? 'Let time run and watch what happens.'}</div>)}
        </div>
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

/** What was decided on the spot, in words (the rest plays out as time runs). */
function outcome(d: any, other: string): string | null {
  const o = other.split(' ')[0] || 'They'
  if (d.forgiven === true) return `${o} let it go.`
  if (d.forgiven === false) return `${o} wasn't ready to let it go.`
  if (d.asked) return d.yes ? `${o} said yes: a date is booked.` : `${o} said no.`
  if (d.accepted === true) return 'They took the job.'
  if (d.accepted === false) return `They turned it down (${d.why ?? 'declined'}).`
  if (d.reached_out === false) return 'They didn\'t get around to it.'
  return null
}
