// The valley: the home screen. Your people on the left (the lives you follow, with what they're doing right now), the
// living map in the middle, and the story on the right: what just happened to your people, or to the whole valley,
// as plain moments with their reasons. Click a name to focus that life (the map follows), a moment to see why it
// happened and what it led to, "Watch" to play the scene, and "Make it happen" to change what someone does.
import { useEffect, useMemo, useRef, useState } from 'react'
import { valleyApi, type CastNow, type CastPick, type Moment } from '../../api'
import { useBench } from '../../bench/selection'
import { subjectPerson } from '../../bench/sel'
import { tool as mapTool } from '../../bench/tools/Map'
import { useLayout } from '../../bench/layout'
import { FindPerson } from '../../bench/SelectionBar'
import { CatIcon, G, useAsync } from '../../game'
import { timeCtl } from '../../hud'
import { usePersonName } from '../../kit/RefChip'
import { useLens, useStore } from '../../store'
import { openMake } from './MakeItHappen'
import { Initials, openScene } from './Scene'
import '../../bench/bench.css'
import '../../bench/tools.css'
import './valley.css'

const DOING: Record<string, string> = {
  home: 'at home', class: 'in class', work: 'at work', church: 'at church', campus: 'on campus', gym: 'at the gym',
  gathering: 'at a get-together', date: 'on a date', venue: 'out', outdoors: 'outdoors', ward_activity: 'at a ward activity', away: 'away',
}
const focusPerson = (id: number, name: string) => useBench.getState().focus({ kind: 'person', id, label: name })

export default function Valley() {
  const followed = useStore(s => s.followed)()
  useStore(s => s.following)               // re-render when the cast changes
  const sel = useBench(s => s.sel)
  const focus = subjectPerson(sel)
  return (
    <div className="vl">
      <CastRail ids={followed} focus={focus} />
      <section className="vl-stage">
        <MapStage />
        {focus !== null && <FocusCard id={focus} followed={followed.includes(focus)} />}
      </section>
      <Feed cast={followed} focus={focus} />
    </div>
  )
}

// ---------------------------------------------------------------- the cast
function CastRail({ ids, focus }: { ids: number[]; focus: number | null }) {
  const { u } = useLens()
  const dataVersion = useStore(s => s.dataVersion)
  const toggleFollow = useStore(s => s.toggleFollow)
  const now = useAsync(() => (ids.length ? valleyApi.now(ids, u) : Promise.resolve({ people: [] as CastNow[] } as any)), [ids.join(','), u, dataVersion])
  const rows: CastNow[] = now.data?.people ?? []
  return (
    <aside className="vl-cast" aria-label="Your people">
      <div className="vl-h"><b>Your people</b><span className="small muted">{ids.length ? `${ids.length} followed` : ''}</span></div>
      <div className="vl-find"><FindPerson onPick={(id, name) => { if (!ids.includes(id)) toggleFollow(id); focusPerson(id, name) }} /></div>
      {rows.map(p => (
        <button key={p.id} className={`vl-person ${focus === p.id ? 'on' : ''}`} onClick={() => focusPerson(p.id, p.name)}>
          <Initials name={p.name} id={p.id} size={34} />
          <span className="vl-p-main">
            <span className="vl-p-name">{p.name}</span>
            <span className="vl-p-now">{p.present ? DOING[p.doing] ?? p.doing : 'away'}{p.next ? <> · next: {p.next.what} {p.next.time?.split('–')[0]}</> : null}</span>
            <Feel p={p} />
            {p.last && <span className="vl-p-last">{p.last.text}</span>}
            <Plans p={p} today={now.data?.day ?? 0} />
          </span>
        </button>
      ))}
      {ids.length < 3 && <Suggestions have={ids} onFollow={(c) => { toggleFollow(c.id); focusPerson(c.id, c.name) }} />}
      {ids.length > 0 && <p className="vl-tip small muted">Follow anyone from the map, the story, or their page. {focus !== null && ids.includes(focus) && <button className="linkish" onClick={() => toggleFollow(focus)}>Stop following the selected person</button>}</p>}
    </aside>
  )
}

/** Their get-togethers and dates around now: what's coming (and their answer), and what happened (watch it). */
function Plans({ p, today }: { p: CastNow; today: number }) {
  const rows = (p.plans ?? []).filter(x => x.status !== 'cancelled' && (x.status === 'planned' || x.came)).slice(0, 3)
  if (!rows.length) return null
  const when = (d: number) => (d === today ? 'today' : d === today - 1 ? 'yesterday' : d === today + 1 ? 'tomorrow' : `in ${d - today} days`)
  return (
    <span className="vl-plans">
      {rows.map(x => (
        <span key={x.occasion} className={`vl-plan ${x.status}`}>
          <span className="vl-plan-t">{when(x.day)} {x.time.split('–')[0]} · {x.label}{x.hosting ? ' (hosting)' : x.answer && x.status === 'planned' ? ` · ${x.answer}` : ''}</span>
          {x.status === 'happened' && <span role="button" tabIndex={0} className="vl-watch" onClick={e => { e.stopPropagation(); openScene({ kind: 'occasion', id: x.occasion }, p.id) }}>{G.play} watch</span>}
          {x.status === 'planned' && x.day === today && <span role="button" tabIndex={0} className="vl-watch live" title="Open it now and watch it unfold as time runs"
            onClick={e => { e.stopPropagation(); openScene({ kind: 'occasion', id: x.occasion }, p.id) }}>● watch live</span>}
        </span>
      ))}
    </span>
  )
}

function Feel({ p }: { p: { mood: number; loneliness: number; stress: number } }) {
  const m = (v: number, good: boolean) => <i style={{ width: `${Math.round(100 * Math.max(0.04, Math.min(1, v)))}%`, background: `var(${good ? '--good' : '--serious'})` }} />
  return (
    <span className="vl-feel" title={`happiness ${p.mood.toFixed(2)} · loneliness ${p.loneliness.toFixed(2)} · stress ${p.stress.toFixed(2)} (0 to 1)`}>
      <span><b>happy</b><span className="vl-bar">{m(p.mood, true)}</span></span>
      <span><b>lonely</b><span className="vl-bar">{m(p.loneliness, false)}</span></span>
      <span><b>stressed</b><span className="vl-bar">{m(p.stress, false)}</span></span>
    </span>
  )
}

function Suggestions({ have, onFollow }: { have: number[]; onFollow: (c: CastPick) => void }) {
  const [shuffle, setShuffle] = useState(0)
  const c = useAsync(() => valleyApi.cast(shuffle), [shuffle])
  const picks = (c.data?.cast ?? []).filter(x => !have.includes(x.id))
  return (
    <div className="vl-suggest">
      <div className="vl-h"><b>{have.length ? 'More lives to follow' : 'Pick some lives to follow'}</b><button className="btn small ghost" onClick={() => setShuffle(shuffle + 1)} title="Other people of the same kinds">Others</button></div>
      {!have.length && <p className="small secondary">Everyone here is synthetic, living in real Provo and Orem. Follow a few and let time run: their story fills the right side.</p>}
      {picks.slice(0, have.length ? 4 : 9).map(p => (
        <div key={p.id} className="vl-pick">
          <div className="vl-pick-top"><span className="vl-kind">{p.label}</span><button className="btn small" onClick={() => onFollow(p)}>{G.plus} Follow</button></div>
          <button className="vl-pick-name" onClick={() => focusPerson(p.id, p.name)}>{p.name}</button>
          <div className="small secondary">{p.hook}</div>
          <div className="small muted vl-clip">{p.headline}</div>
        </div>
      ))}
      {c.loading && !picks.length && <div className="small muted">Finding people…</div>}
    </div>
  )
}

// ---------------------------------------------------------------- the map and the focused life
function MapStage() {
  const sel = useBench(s => s.sel)
  const setSel = useBench(s => s.setSel)
  const [opts, setOpts] = useState<Record<string, any>>(() => { try { return JSON.parse(localStorage.getItem('ucsim-valley-map') ?? '{}') } catch { return {} } })
  const save = (o: Record<string, any>) => { setOpts(o); try { localStorage.setItem('ucsim-valley-map', JSON.stringify(o)) } catch { /* private */ } }
  const C = mapTool.component
  return <div className="vl-map"><C sel={sel} setSel={setSel} panelId="valley-map" opts={opts} setOpts={save} /></div>
}

function FocusCard({ id, followed }: { id: number; followed: boolean }) {
  const { u } = useLens()
  const dataVersion = useStore(s => s.dataVersion)
  const { toggleFollow, setRoute } = useStore.getState()
  const d = useAsync(() => valleyApi.now([id], u), [id, u, dataVersion])
  const p = d.data?.people?.[0]
  if (!p) return <div className="vl-focus card"><span className="small muted">…</span></div>
  return (
    <div className="vl-focus card">
      <Initials name={p.name} id={p.id} size={44} />
      <div className="grow vl-focus-main">
        <div className="vl-focus-name"><b>{p.name}</b><span className="small muted"> · {p.present ? DOING[p.doing] ?? p.doing : 'away'}{p.next ? ` · next: ${p.next.what}, ${p.next.time}` : ''}</span></div>
        <div className="small secondary vl-clip">{p.headline}</div>
        <div className="row" style={{ marginTop: 8 }}>
          <button className="btn small primary" onClick={() => openMake(p.id)}>{G.spark} Make it happen</button>
          {p.partner && <button className="btn small" onClick={() => openScene({ kind: 'pair', a: p.id, b: p.partner!.id }, p.id)}>{G.send} Texts with {p.partner.name.split(' ')[0]}</button>}
          <button className="btn small" onClick={() => setRoute(['person', String(p.id)])}>{G.id} Their life</button>
          <button className={`btn small ${followed ? 'following' : ''}`} onClick={() => toggleFollow(p.id)}>{followed ? 'Following' : <>{G.plus} Follow</>}</button>
        </div>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------- the story
function Feed({ cast, focus }: { cast: number[]; focus: number | null }) {
  const { u } = useLens()
  const dataVersion = useStore(s => s.dataVersion)
  const status = useStore(s => s.status)
  const [tab, setTab] = useState<'cast' | 'valley'>(cast.length ? 'cast' : 'valley')
  const had = useRef(cast.length)
  useEffect(() => { if (!had.current && cast.length) setTab('cast'); had.current = cast.length }, [cast.length])   // first follow: show their story
  const t = cast.length ? tab : 'valley'
  const only = focus !== null && t === 'cast' && cast.includes(focus) ? [focus] : null
  const people = t === 'cast' ? (only ?? cast) : []
  const f = useAsync(() => valleyApi.feed(people, u, (status?.day ?? 0) - (t === 'cast' ? 30 : 10)), [people.join(','), u, dataVersion, t])
  const days = useMemo(() => {
    const out: { day: number; date: string; weekday: string; items: Moment[] }[] = []
    for (const m of f.data?.moments ?? []) {
      const last = out[out.length - 1]
      if (last && last.day === m.day) last.items.push(m)
      else out.push({ day: m.day, date: m.date, weekday: m.weekday, items: [m] })
    }
    return out
  }, [f.data])
  const running = status?.job?.state === 'running'
  const name = usePersonName(u)
  return (
    <aside className="vl-feed" aria-label="The story">
      <div className="vl-tabs">
        <button className={t === 'cast' ? 'on' : ''} disabled={!cast.length} onClick={() => setTab('cast')} title={cast.length ? '' : 'Follow someone first'}>
          {only ? name(only[0]).split(' ')[0] : 'Your people'}</button>
        <button className={t === 'valley' ? 'on' : ''} onClick={() => setTab('valley')}>The valley</button>
        <span className="spacer" />
        {!running && status?.checkpoint && <Undo cp={status.checkpoint} />}
        {!running && <button className="btn small primary" onClick={() => timeCtl.play()} title="Let time run (Space)">{G.play} Run</button>}
      </div>
      <div className="vl-story">
        {f.error && <div className="bx-problem">{f.error}</div>}
        {!f.data && !f.error && <div className="small muted vl-pad">Reading the story…</div>}
        {f.data && !days.length && <div className="vl-pad small muted">{t === 'cast' ? 'Nothing big has happened to them lately. Let time run.' : 'A quiet stretch. Let time run.'}</div>}
        {days.map(d => (
          <section key={d.day} className="vl-day">
            <div className="vl-day-h">{d.day === status?.day ? 'Today' : d.day === (status?.day ?? 0) - 1 ? 'Yesterday' : new Date(d.date + 'T12:00:00').toLocaleDateString(undefined, { weekday: 'long', month: 'short', day: 'numeric' })}</div>
            {d.items.map(m => <MomentRow key={m.event} m={m} cast={cast} />)}
          </section>
        ))}
      </div>
    </aside>
  )
}

function MomentRow({ m, cast }: { m: Moment; cast: number[] }) {
  const [open, setOpen] = useState(false)
  const pair = m.people.length === 2
  const text = useMemo(() => linkNames(m.text, m.people), [m.text, m.people])
  return (
    <div className={`vl-m ${m.big ? 'big' : ''} ${open ? 'open' : ''}`}>
      <CatIcon c={m.category} />
      <div className="vl-m-body">
        <div className="vl-m-text">{text}{m.times > 1 && <span className="vl-times" title={`since ${m.first_date}`}> ×{m.times}</span>}</div>
        {m.because && <div className="vl-m-why">because {m.because}</div>}
        <div className="vl-m-acts">
          <button className="linkish" onClick={() => setOpen(!open)}>{open ? 'less' : 'why, and what it led to'}</button>
          {m.occasion !== null && <button className="linkish" onClick={() => openScene({ kind: 'occasion', id: m.occasion! }, m.cast[0] ?? null)}>{G.play} watch the scene</button>}
          {pair && <button className="linkish" onClick={() => openScene({ kind: 'pair', a: m.cast[0] ?? m.people[0].id, b: m.people.find(p => p.id !== (m.cast[0] ?? m.people[0].id))!.id }, m.cast[0] ?? null)}>{G.send} their story</button>}
          {!cast.includes(m.people[0].id) && <button className="linkish" onClick={() => useStore.getState().toggleFollow(m.people[0].id)}>follow {m.people[0].name.split(' ')[0]}</button>}
        </div>
        {open && <WhyRipple ev={m.event} />}
      </div>
    </div>
  )
}

/** Names in a sentence become buttons that focus that life. */
function linkNames(text: string, people: { id: number; name: string }[]) {
  let parts: (string | JSX.Element)[] = [text]
  for (const p of people) {
    parts = parts.flatMap(x => {
      if (typeof x !== 'string' || !x.includes(p.name)) return [x]
      const bits = x.split(p.name)
      return bits.flatMap((b, k) => (k < bits.length - 1 ? [b, <button key={`${p.id}-${k}`} className="vl-name" onClick={() => focusPerson(p.id, p.name)}>{p.name}</button>] : [b]))
    })
  }
  return parts
}

function WhyRipple({ ev }: { ev: number }) {
  const { u } = useLens()
  const w = useAsync(() => valleyApi.why(`event:${ev}`, u), [ev, u])
  const r = useAsync(() => valleyApi.ripple(`event:${ev}`, u), [ev, u])
  const toward: any[] = w.data?.toward ?? []
  const steps: any[] = (r.data?.steps ?? []).filter((s: any) => s.level > 0).slice(0, 8)
  return (
    <div className="vl-why">
      {w.data && <>
        <div className="vl-why-h">What pushed it{w.data.chance != null ? <span className="muted"> · it had a {Math.round(100 * w.data.chance)}% chance</span> : null}</div>
        {toward.slice(0, 5).map((t: any, k: number) => (
          <div key={k} className="vl-why-row"><span className="vl-why-bar"><i style={{ width: `${Math.round(100 * t.share)}%` }} /></span><span>{t.words || t.label}</span><b className="tabular">{Math.round(100 * t.share)}%</b></div>
        ))}
        {!toward.length && <div className="small muted">No recorded push: {w.data.constraint ? `couldn't: ${w.data.constraint.words}` : 'it came from the situation itself'}.</div>}
      </>}
      {r.data && <>
        <div className="vl-why-h">What it led to</div>
        {steps.length ? steps.map((s: any) => (
          <div key={s.key} className="vl-led" style={{ paddingLeft: 10 * (s.level - 1) }}><span className="muted small">{s.date?.slice(5)}</span> {s.text}</div>
        )) : <div className="small muted">Nothing yet. Some things take weeks to ripple out.</div>}
        <button className="linkish" onClick={() => { useBench.getState().focus({ kind: 'event', id: ev }); useLayout.getState().ensure('trace'); useStore.getState().setRoute(['bench']) }}>Trace it on the workbench</button>
      </>}
    </div>
  )
}

/** One step back: the world as it was just before your last change in it (and nothing that happened since). */
function Undo({ cp }: { cp: { label: string; date: string; day: number } }) {
  const [busy, setBusy] = useState(false)
  const go = async () => {
    const lost = (useStore.getState().status?.day ?? cp.day) - cp.day
    if (!window.confirm(`Undo "${cp.label}"?${lost > 0 ? ` The ${lost} day${lost === 1 ? '' : 's'} since then will be lost.` : ''}`)) return
    setBusy(true)
    try {
      const r = await valleyApi.undo()
      useStore.getState().toast?.({ kind: 'world', title: `Undone: ${r.undone}`, body: `Back to ${new Date(r.date + 'T12:00:00').toLocaleDateString(undefined, { weekday: 'long', month: 'short', day: 'numeric' })}.`, ttl: 6000 })
      await useStore.getState().refreshStatus()
    } catch (e: any) { window.alert(String(e?.message ?? e)) }
    setBusy(false)
  }
  return <button className="btn small ghost" disabled={busy} onClick={go} title={`Put your world back as it was just before: ${cp.label}`}>↶ Undo</button>
}
