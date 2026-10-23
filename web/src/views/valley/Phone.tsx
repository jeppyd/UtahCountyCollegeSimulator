// Someone's phone: the people they text, their group chats and their dating app, read from the records. Every message
// is one recorded act (the same words on both phones); everyday chatter is summarized, never invented. "Why?" on a
// message shows it from both sides: what the sender meant and kept back, how it was read, and what came of it.
// "Write it with your model" asks the owner's model to word the thread; the meaning can't change, and anything the
// model adds that the records don't support is left in the structured wording. Open with openPhone(person).
import { useEffect, useRef, useState } from 'react'
import { create } from 'zustand'
import { phoneApi, type AppItem, type Inbox, type PLine, type PView, type PhoneViewRef, type Wording } from '../../api'
import { G, useAsync } from '../../game'
import { useBench } from '../../bench/selection'
import { useLens, useStore } from '../../store'
import { Initials } from './Scene'
import { BackendPick } from '../../bench/tools/Ask'
import './phone.css'

type Tab = 'texts' | 'groups' | 'app'
type Open = { person: number; tab?: Tab; with?: number; group?: number; app?: number }
export const usePhone = create<{ open: Open | null; set: (o: Open | null) => void }>(set => ({ open: null, set: open => set({ open }) }))
export const openPhone = (person: number, more: Omit<Open, 'person'> = {}) => usePhone.getState().set({ person, ...more })

const first = (n?: string | null) => (n ?? '').split(' ')[0]
const dayLabel = (date: string) => new Date(date + 'T12:00:00').toLocaleDateString(undefined, { weekday: 'long', month: 'short', day: 'numeric' })

export function PhoneView() {
  const { open, set } = usePhone()
  const { u } = useLens()
  const v = useStore(s => s.dataVersion)
  const ib = useAsync<Inbox | null>(() => (open ? phoneApi.inbox(open.person, u) : Promise.resolve(null)), [open?.person, u, v])
  const [tab, setTab] = useState<Tab>('texts')
  const [pick, setPick] = useState<PhoneViewRef | null>(null)
  useEffect(() => {
    if (!open) return
    setTab(open.tab ?? (open.app != null ? 'app' : open.group != null ? 'groups' : 'texts'))
    setPick(open.with != null ? { kind: 'dm', a: open.person, b: open.with } : open.group != null ? { kind: 'group', viewer: open.person, t: open.group }
      : open.app != null ? { kind: 'app', id: open.app } : null)
  }, [JSON.stringify(open)])
  useEffect(() => {
    if (!open) return
    const k = (e: KeyboardEvent) => { if (e.key === 'Escape') set(null) }
    window.addEventListener('keydown', k)
    return () => window.removeEventListener('keydown', k)
  }, [!!open])
  if (!open) return null
  const d = ib.data?.person === open.person ? ib.data : null
  const me = open.person
  return (
    <div className="sc-veil" onMouseDown={e => { if (e.target === e.currentTarget) set(null) }}>
      <section className="ph" role="dialog" aria-label="A phone">
        <header className="sc-h">
          <Initials name={d?.name ?? '?'} id={me} size={36} />
          <div className="grow">
            <div className="eyebrow">Their phone</div>
            <h2>{d?.name ?? 'Opening…'}</h2>
            {d && <div className="secondary small" title={d.style_note}>Texts {d.style}</div>}
          </div>
          <button className="bx-icon" onClick={() => set(null)} title="Close (Esc)">{G.close}</button>
        </header>
        <div className="ph-main">
          <nav className={`ph-list ${pick ? 'has-pick' : ''}`} aria-label="Conversations">
            <div className="vl-tabs ph-tabs">
              {(['texts', 'groups', 'app'] as Tab[]).map(t => (
                <button key={t} className={tab === t ? 'on' : ''} onClick={() => setTab(t)}>
                  {t === 'texts' ? 'Messages' : t === 'groups' ? 'Groups' : 'Dating app'}
                  {t === 'app' && d?.apps.some(a => ['opened', 'chatting', 'asked', 'date_set'].includes(a.stage)) ? <i className="ph-dot" /> : null}
                </button>
              ))}
            </div>
            {ib.error && <div className="bx-problem">{ib.error}</div>}
            {!d && !ib.error && <div className="small muted ph-pad">Reading…</div>}
            {d && tab === 'texts' && (d.dms.length ? d.dms.map(c => (
              <button key={c.id} className={`ph-row ${pick?.kind === 'dm' && pick.b === c.id ? 'on' : ''}`} onClick={() => setPick({ kind: 'dm', a: me, b: c.id })}>
                <Initials name={c.name} id={c.id} size={32} />
                <span className="ph-row-main"><b>{c.name}</b><span className="ph-prev">{c.preview_me ? 'You: ' : ''}{c.preview ?? ''}</span></span>
                <span className="ph-when">{c.date ? new Date(c.date + 'T12:00:00').toLocaleDateString(undefined, { month: 'short', day: 'numeric' }) : ''}{c.waiting && <i className="ph-dot" title="waiting on them" />}</span>
              </button>
            )) : <div className="small muted ph-pad">No texts recorded with anyone yet. Let time run.</div>)}
            {d && tab === 'groups' && (d.groups.length ? d.groups.map(g => (
              <button key={g.id} className={`ph-row ${pick?.kind === 'group' && pick.t === g.id ? 'on' : ''} ${g.member ? '' : 'left'}`} onClick={() => setPick({ kind: 'group', viewer: me, t: g.id })}>
                <span className="ph-group-ic">{G.people}</span>
                <span className="ph-row-main"><b>{g.name}</b><span className="ph-prev">{g.n} {g.n === 1 ? 'person' : 'people'} · about {Math.round(g.volume)} message{Math.round(g.volume) === 1 ? '' : 's'} a day{g.muted ? ' · muted' : ''}{!g.member ? ' · they left' : ''}</span></span>
              </button>
            )) : <div className="small muted ph-pad">In no group chats.</div>)}
            {d && tab === 'app' && <AppList apps={d.apps} pick={pick} setPick={setPick} />}
            {d && <p className="small muted ph-pad">{d.note}</p>}
          </nav>
          <div className="ph-thread">
            {pick ? <Thread view={pick} me={me} onBack={() => setPick(null)} key={JSON.stringify(pick)} />
              : <div className="sc-wait">Pick a conversation.</div>}
          </div>
        </div>
      </section>
    </div>
  )
}

function AppList({ apps, pick, setPick }: { apps: AppItem[]; pick: PhoneViewRef | null; setPick: (p: PhoneViewRef) => void }) {
  if (!apps.length) return <div className="small muted ph-pad">No matches yet (or they don't use dating apps).</div>
  return <>{apps.map(a => (
    <button key={a.id} className={`ph-row ${pick?.kind === 'app' && pick.id === a.id ? 'on' : ''}`} onClick={() => setPick({ kind: 'app', id: a.id })}>
      <Initials name={a.with.name} id={a.with.id} size={32} />
      <span className="ph-row-main"><b>{first(a.with.name)}</b><span className={`ph-prev ph-stage ${a.stage}`}>{a.words}</span></span>
    </button>
  ))}</>
}

/** One conversation: its messages as bubbles (the phone's owner on the right). */
export function Thread({ view, me, onBack }: { view: PhoneViewRef; me: number | null; onBack?: () => void }) {
  const { u } = useLens()
  const v = useStore(s => s.dataVersion)
  const [again, setAgain] = useState(0)
  const load = (): Promise<PView> => view.kind === 'dm' ? phoneApi.dm(view.a, view.b, u) : view.kind === 'group' ? phoneApi.group(view.viewer, view.t, u)
    : view.kind === 'app' ? phoneApi.app(view.id, u) : Promise.reject(new Error('not a thread'))
  const d = useAsync(load, [JSON.stringify(view), u, v, again])
  const [why, setWhy] = useState<number | null>(null)
  const end = useRef<HTMLDivElement>(null)
  useEffect(() => { end.current?.scrollIntoView({ block: 'end' }) }, [d.data?.lines.length])
  const lines = d.data?.lines ?? []
  const other = view.kind === 'dm' ? lines.find(l => l.speaker === view.b)?.speaker_name : null
  return (
    <div className="ph-t">
      <div className="ph-t-h">
        {onBack && <button className="btn small ghost ph-back" onClick={onBack}>‹</button>}
        <b className="grow">{view.kind === 'dm' ? other ?? 'Texts' : view.kind === 'group' ? d.data?.name ?? 'Group chat' : d.data?.b ? `${d.data.a?.name} & ${d.data.b?.name}` : 'Dating app'}</b>
        {view.kind === 'app' && d.data?.b && <span className="small muted">matched {d.data.matched_date} · {d.data.words}</span>}
      </div>
      {view.kind === 'app' && d.data?.b && <Profile id={(d.data.a?.id === me ? d.data.b : d.data.a).id} />}
      {view.kind === 'group' && (d.data?.hidden_before_joining ?? 0) > 0 && <div className="sc-stage">{d.data!.hidden_before_joining} earlier messages from before they joined aren't on their phone.</div>}
      <div className="sc-body ph-body">
        {d.error && !d.data && <div className="bx-problem">{d.error}</div>}
        {!d.data && !d.error && <div className="sc-wait">Opening…</div>}
        {d.data && !lines.length && <div className="sc-wait">Nothing recorded here yet.</div>}
        {lines.map((l, k) => <Line key={l.id + k} l={l} prev={lines[k - 1]} me={me} why={why} setWhy={setWhy} />)}
        {view.kind === 'app' && d.data?.date && <div className="sc-stage event">The date: {d.data.date.state}{d.data.date_date ? ` (${dayLabel(d.data.date_date)})` : ''}</div>}
        <div ref={end} />
      </div>
      {d.data && <WordingBar w={d.data.wording} view={view} onDone={() => setAgain(again + 1)} />}
    </div>
  )
}

export function Line({ l, prev, me, why, setWhy, said }: { l: PLine; prev?: PLine; me: number | null; why: number | null; setWhy: (x: number | null) => void; said?: boolean }) {
  const day = l.date !== prev?.date ? <div className="sc-day">{dayLabel(l.date)}</div> : null
  const time = l.time && (l.time !== prev?.time || l.date !== prev?.date) ? <div className="sc-time">{l.time}</div> : null
  const focus = () => { if (l.speaker != null) useBench.getState().focus({ kind: 'person', id: l.speaker, label: l.speaker_name ?? '' }) }
  if (l.absent || l.kind === 'stage') {
    return <>{day}<div className={`sc-stage silence ${l.kind === 'stage' ? 'ph-gap' : ''}`}>{l.text}
      {l.ex != null && <button className="linkish ph-whyb" onClick={() => setWhy(why === l.ex ? null : l.ex)}>why?</button>}</div>
      {why === l.ex && l.ex != null && <Perspective ex={l.ex} />}</>
  }
  const mine = me !== null && l.speaker === me
  return (
    <>
      {day}{time}
      <div className={`sc-msg ${mine ? 'me' : ''} ${said ? 'said' : ''}`}>
        {!mine && l.speaker_name && <button className="sc-who" onClick={focus}>{first(l.speaker_name)}</button>}
        <div className="sc-bubble">{said ? `“${l.text}”` : l.text}</div>
        {l.ex != null && <button className="linkish ph-whyb" onClick={() => setWhy(why === l.ex ? null : l.ex)} title="What they meant, how it was read, and what came of it">{why === l.ex ? 'hide' : 'why?'}</button>}
      </div>
      {why === l.ex && l.ex != null && <Perspective ex={l.ex} />}
    </>
  )
}

/** The words' source, and the button that asks the owner's model to word this conversation. */
export function WordingBar({ w, view, onDone, compact }: { w: Wording; view: PhoneViewRef; onDone: () => void; compact?: boolean }) {
  const { u } = useLens()
  const [job, setJob] = useState<{ state: string; text?: string; error?: string | null } | null>(null)
  const alive = useRef(0)
  useEffect(() => () => { alive.current++ }, [])
  const go = async () => {
    const run = ++alive.current
    setJob({ state: 'queued', text: 'Asking your model' })
    try {
      const r = await phoneApi.realize(view, u, 0)
      if (!r.job) { setJob(null); onDone(); return }
      for (;;) {
        const s = await phoneApi.realizeStatus(r.job)
        if (alive.current !== run) return
        setJob({ state: s.state, text: s.steps[s.steps.length - 1]?.text, error: s.error })
        if (s.state !== 'queued' && s.state !== 'running') break
        await new Promise(res => setTimeout(res, 800))
      }
      onDone()
    } catch (e: any) { if (alive.current === run) setJob({ state: 'error', error: String(e?.message ?? e) }) }
  }
  const busy = job && (job.state === 'queued' || job.state === 'running')
  if (compact) {
    return (
      <div className="ph-word-c">
        {w.source === 'model' && <span title="Worded by your model; what happens is recorded">✍ worded by your model</span>}
        {job?.state === 'error' && <span style={{ color: 'var(--critical)' }} title={job.error ?? ''}>couldn't word it</span>}
        {busy && <span>{job!.text ?? 'Working'}…</span>}
        {w.realizable && w.source !== 'model' && !busy && <button className="linkish" onClick={go} title="Your model writes the exact words; it can't change what happens">✍ write it with your model</button>}
      </div>
    )
  }
  return (
    <div className="sc-f ph-f">
      {w.source === 'model'
        ? <span className="sc-note">Worded by your model{w.removed ? ` (${w.removed} line${w.removed === 1 ? '' : 's'} kept plain: they said more than the records)` : ''}. What happens is recorded.</span>
        : <span className="sc-note">What happens is recorded; the words are plain and illustrative.</span>}
      <span className="spacer" />
      {job?.state === 'error' && <span className="small" style={{ color: 'var(--critical)' }} title={job.error ?? ''}>Couldn't word it: {job.error}</span>}
      {busy && <span className="small muted">{job!.text ?? 'Working'}…</span>}
      {w.realizable && w.source !== 'model' && !busy && <span title="Which model writes the words (a model on this computer is recommended: fast and private)"><BackendPick feature="dialogue" /></span>}
      {w.realizable && w.source !== 'model' && !busy && <button className="btn small" onClick={go} title="Your model writes the exact words; it can't change what anyone does or says yes or no to">✍ Write it with your model</button>}
      {busy && <button className="btn small ghost" onClick={() => { alive.current++; setJob(null) }}>Stop watching</button>}
    </div>
  )
}

/** What someone shows on their dating profile: self-presented, not their hidden state. */
function Profile({ id }: { id: number }) {
  const { u } = useLens()
  const p = useAsync(() => phoneApi.profile(id, u), [id, u])
  if (!p.data) return null
  const x = p.data
  return (
    <div className="ph-prof" title={x.note}>
      <Initials name={x.first_name} id={id} size={40} />
      <div className="grow">
        <b>{x.first_name}, {x.age}</b>
        <div className="small secondary">{[x.school, x.studying, x.returned_missionary ? 'returned missionary' : null, ...(x.hobbies ?? [])].filter(Boolean).join(' · ')}</div>
        <div className="small muted">Looking for {x.looking_for} · on {x.app}</div>
      </div>
    </div>
  )
}

/** One exchange from both sides, from the records (nothing here is written by a model). */
export function Perspective({ ex }: { ex: number }) {
  const { u } = useLens()
  const p = useAsync(() => phoneApi.perspective(ex, u), [ex, u])
  if (p.error) return <div className="bx-problem">{p.error}</div>
  if (!p.data) return <div className="ph-pv small muted">…</div>
  const x = p.data
  const s = x.speaker, o = x.other, a = x.after
  return (
    <div className="ph-pv" role="note">
      <div className="ph-pv-col">
        <div className="ph-pv-h">{first(s.who?.name)} {s.act_words}</div>
        {s.intent && <div>Meant {s.intent}.</div>}
        {s.communicated && <div>Said {s.communicated}.</div>}
        {s.kept_back && <div>Kept back: {s.kept_back}.</div>}
        {s.decision && <div className="small secondary">Why: {s.decision.factors.slice(0, 3).map((f: any) => f.words || f.label).join('; ') || s.decision.label}{s.decision.chance != null ? ` (it had a ${Math.round(100 * s.decision.chance)}% chance)` : ''}</div>}
        {s.beliefs?.map((b: any, k: number) => <div key={k} className="small secondary">Believed then: {b.words}</div>)}
      </div>
      {o.who && <div className="ph-pv-col">
        <div className="ph-pv-h">How {first(o.who.name)} took it</div>
        {o.reads.length ? o.reads.map((r: any, k: number) => <div key={k}>Took it as: {r.words}{r.expected && r.expected !== r.words ? <span className="small muted"> (sender hoped: {r.expected})</span> : null}</div>)
          : <div className="small muted">No reading recorded.</div>}
        {o.beliefs?.map((b: any, k: number) => <div key={k} className="small secondary">Believed then: {b.words}</div>)}
      </div>}
      <div className="ph-pv-col wide">
        <div className="ph-pv-h">What came of it</div>
        {a.concern && <div>{first(a.concern.owner?.name)}: {a.concern.words}, {a.concern.status === 'open' ? 'still open' : a.concern.status.replace(/_/g, ' ')}.</div>}
        {a.revised?.map((r: any, k: number) => <div key={k}>{first(r.who?.name)} stopped thinking {r.words}.</div>)}
        {a.next?.slice(0, 3).map((n: any) => <div key={n.id} className="small">{n.date?.slice(5)} · {first(n.who?.name)} {n.words} ({n.channel})</div>)}
        {a.tie_then && a.tie_now && <div className="small secondary">Closeness then {a.tie_then.closeness}, now {a.tie_now.closeness}.</div>}
        {!a.concern && !a.revised?.length && !a.next?.length && <div className="small muted">Nothing more yet.</div>}
        {x.unknown?.map((t: string, k: number) => <div key={k} className="small muted">{t}</div>)}
      </div>
    </div>
  )
}
