// Scenes you can watch: a get-together or two people's history played back beat by beat — texts as bubbles, arrivals,
// glances across the room, introductions and what happened next. What happens is what the simulation recorded; the
// words people say are illustrative lines that fit (analysis/script.py). Open one from anywhere with openScene().
import { useEffect, useMemo, useRef, useState } from 'react'
import { create } from 'zustand'
import { talkApi, valleyApi, type Beat, type Script } from '../../api'
import { G, useAsync } from '../../game'
import { useBench } from '../../bench/selection'
import { timeCtl } from '../../hud'
import { useStore } from '../../store'

type SceneRef = { kind: 'occasion'; id: number } | { kind: 'pair'; a: number; b: number }
export const useScene = create<{ open: SceneRef | null; pov: number | null; set: (r: SceneRef | null, pov?: number | null) => void }>(set => ({
  open: null, pov: null, set: (r, pov = null) => set({ open: r, pov }),
}))
export const openScene = (r: SceneRef, pov: number | null = null) => useScene.getState().set(r, pov)

const STEP_MS = 1100

export function ScenePlayer() {
  const { open, pov, set } = useScene()
  const dataVersion = useStore(s => s.dataVersion)
  const status = useStore(s => s.status)
  const s = useAsync<Script | null>(() => {
    if (!open) return Promise.resolve(null)
    return open.kind === 'occasion' ? valleyApi.occasion(open.id) : valleyApi.pair(open.a, open.b)
  }, [JSON.stringify(open), open ? dataVersion : 0], true)   // keep the scene on screen while it reloads (live scenes)
  const [shown, setShown] = useState(0)
  const [playing, setPlaying] = useState(true)
  const end = useRef<HTMLDivElement>(null)
  // the answer for this scene (a reload keeps the old one showing; another scene's never does)
  const cur = s.data && open && (open.kind === 'occasion' ? s.data.kind === 'occasion' && s.data.id === open.id
    : s.data.kind === 'pair' && s.data.a?.id === open.a && s.data.b?.id === open.b) ? s.data : null
  const beats = cur?.beats ?? []
  // the story: the same beats told as prose by the owner's model login, checked against the beats
  const [story, setStory] = useState<any>(null)
  const [asStory, setAsStory] = useState(false)
  const alive = useRef(0)
  useEffect(() => { setShown(0); setPlaying(true); setStory(null); setAsStory(false); alive.current++ }, [JSON.stringify(open)])
  const tell = async () => {
    if (!open) return
    const me0 = pov ?? (open.kind === 'pair' ? open.a : cur?.organizer?.id) ?? null
    const run = ++alive.current
    setAsStory(true)
    setStory({ state: 'running', steps: [] })
    try {
      const { job } = await valleyApi.narrate(open, me0)
      for (;;) {
        const r = await talkApi.poll(job)
        if (alive.current !== run) return
        setStory(r)
        if (r.state !== 'queued' && r.state !== 'running') break
        await new Promise(res => setTimeout(res, 900))
      }
    } catch (e: any) { if (alive.current === run) setStory({ state: 'error', error: String(e?.message ?? e) }) }
  }
  useEffect(() => {
    if (!playing || !cur || shown >= beats.length) return
    const b = beats[shown]
    const t = setTimeout(() => setShown(shown + 1), b && (b.kind === 'text' || b.kind === 'say') ? STEP_MS + 300 : STEP_MS)
    return () => clearTimeout(t)
  }, [playing, shown, cur])
  useEffect(() => { end.current?.scrollIntoView({ block: 'end', behavior: 'smooth' }) }, [shown])
  useEffect(() => {
    if (!open) return
    const k = (e: KeyboardEvent) => { if (e.key === 'Escape') set(null) }
    window.addEventListener('keydown', k)
    return () => window.removeEventListener('keydown', k)
  }, [!!open])
  if (!open) return null
  const sc = cur
  // the point of view: the followed person on the right, like their own phone
  const me = pov ?? (sc?.kind === 'pair' ? sc.a?.id : sc?.organizer?.id) ?? null
  const done = shown >= beats.length
  // a get-together happening today: new beats arrive as time runs (the scene reloads with the world)
  const live = sc?.kind === 'occasion' && sc.status === 'planned' && sc.date === status?.date
  const running = status?.job?.state === 'running'
  const focus = (id: number, name: string) => { useBench.getState().focus({ kind: 'person', id, label: name }) }
  return (
    <div className="sc-veil" onMouseDown={e => { if (e.target === e.currentTarget) set(null) }}>
      <section className="sc" role="dialog" aria-label="A scene">
        <header className="sc-h">
          <div className="grow">
            <div className="eyebrow">{sc?.kind === 'pair' ? 'Two people' : sc ? `${sc.weekday}, ${sc.date} · ${sc.time}` : 'A scene'}</div>
            <h2>{sc?.kind === 'pair' ? `${sc.a?.name} & ${sc.b?.name}` : sc?.title ?? 'Loading…'}</h2>
            {sc?.place && <div className="secondary small">{live && <span className="sc-live">● live</span>}{sc.place}{sc.status && sc.status !== 'happened' && !live ? ` · ${sc.status}` : ''}</div>}
            {sc?.kind === 'pair' && sc.tie && <TieLine tie={sc.tie} a={sc.a!.name} b={sc.b!.name} />}
          </div>
          <button className="bx-icon" onClick={() => set(null)} title="Close (Esc)">{G.close}</button>
        </header>
        {s.error && <div className="bx-problem">{s.error}</div>}
        {sc && sc.cast && sc.cast.length > 0 && (
          <div className="sc-cast">{sc.cast.slice(0, 14).map(p => <button key={p.id} className="sc-face" title={`${p.name}: focus them`} onClick={() => focus(p.id, p.name)}><Initials name={p.name} id={p.id} />{p.name.split(' ')[0]}</button>)}</div>
        )}
        {asStory ? <StoryView story={story} beats={beats} /> : <div className="sc-body">
          {!sc && !s.error && <div className="sc-wait">Setting the scene…</div>}
          {sc && !beats.length && <div className="sc-wait">Nothing recorded between them yet. Let time run.</div>}
          {beats.slice(0, shown).map((b, k) => <BeatView key={k} b={b} me={me} prev={beats[k - 1]} onWho={focus} />)}
          {sc && !done && playing && <div className="sc-typing"><i /><i /><i /></div>}
          {sc && done && live && <div className="sc-wait">{running ? 'Watching… the next moments appear as time passes.' : 'That’s everything so far. Let time run to see what happens next.'}</div>}
          <div ref={end} />
        </div>}
        <footer className="sc-f">
          {asStory
            ? <button className="btn small" onClick={() => setAsStory(false)}>{G.step} Back to the beats</button>
            : sc && beats.length > 0 && <button className="btn small" onClick={() => (story?.state === 'done' ? setAsStory(true) : tell())}
              title="Your Claude login writes the scene as prose, with dialogue and thoughts; it's checked against what happened">✍ Tell it as a story</button>}
          {asStory ? null : !done
            ? <>
              <button className="btn small" onClick={() => setPlaying(!playing)}>{playing ? <>{G.pause} Pause</> : <>{G.play} Play</>}</button>
              <button className="btn small" onClick={() => setShown(Math.min(beats.length, shown + 1))}>{G.step} Next</button>
              <button className="btn small ghost" onClick={() => setShown(beats.length)}>Show it all</button>
            </>
            : live
              ? (!running && <button className="btn small primary" onClick={() => timeCtl.play()}>{G.play} Let time run</button>)
              : <button className="btn small" onClick={() => { setShown(0); setPlaying(true) }}>{G.play} Watch again</button>}
          <span className="spacer" />
          <span className="sc-note" title={asStory ? story?.result?.note : sc?.note}>{asStory ? 'What happens is recorded; the telling is the model\'s.' : 'What happens is recorded; the words are illustrative.'}</span>
        </footer>
      </section>
    </div>
  )
}

function StoryView({ story, beats }: { story: any; beats: Beat[] }) {
  const res = story?.result
  if (!story || story.state === 'queued' || story.state === 'running') {
    const last = story?.steps?.[story.steps.length - 1]
    return <div className="sc-body"><div className="sc-wait">{last?.text ?? 'Asking your model to tell it'}…</div><div className="sc-typing"><i /><i /><i /></div></div>
  }
  if (story.state !== 'done' || !res) return <div className="sc-body"><div className="bx-problem">{story.error ?? 'It could not be told.'} (Settings → Models says which login is used.)</div></div>
  return (
    <div className="sc-body sc-story">
      {res.passages.map((p: { text: string; beats: string[] }, k: number) => {
        const quote = /^["“]/.test(p.text.trim())
        return <p key={k} className={quote ? 'said' : ''} title={p.beats.map(b => beats[Number(b.slice(1)) - 1]?.text).filter(Boolean).join('\n')}
          dangerouslySetInnerHTML={{ __html: md(p.text) }} />
      })}
      {res.removed?.length > 0 && <div className="small muted" title={res.removed.map((r: any) => `${r.text} — ${r.reasons.join('; ')}`).join('\n')}>
        {res.removed.length} passage{res.removed.length === 1 ? '' : 's'} left out for straying from what happened.</div>}
    </div>
  )
}

/** Escape, then *italics* (thoughts). */
function md(t: string) {
  const esc = t.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
  return esc.replace(/\*([^*]+)\*/g, '<em>$1</em>')
}

function TieLine({ tie, a, b }: { tie: any; a: string; b: string }) {
  const word = (x: number) => (x >= 0.7 ? 'very' : x >= 0.4 ? 'quite' : x >= 0.15 ? 'a little' : 'not')
  const fa = a.split(' ')[0], fb = b.split(' ')[0]
  const bits = [`${word(tie.closeness)} close`]
  if (tie.drawn_a >= 0.15 || tie.drawn_b >= 0.15) bits.push(`${fa} is ${word(tie.drawn_a)} drawn to ${fb}; ${fb} ${word(tie.drawn_b)} to ${fa}`)
  if (tie.dates) bits.push(`${tie.dates} date${tie.dates === 1 ? '' : 's'}`)
  if (tie.conflict >= 0.25) bits.push('some unresolved conflict')
  return <div className="secondary small">{bits.join(' · ')}</div>
}

function BeatView({ b, me, prev, onWho }: { b: Beat; me: number | null; prev?: Beat; onWho: (id: number, name: string) => void }) {
  const time = b.time && b.time !== prev?.time ? b.time : null
  const day = b.date && b.date !== prev?.date ? b.date : null
  const why = b.why ? <div className="sc-why" title={b.source}>{G.scale}<span>{b.why}</span></div> : null
  const head = (
    <>{day && <div className="sc-day">{new Date(b.date + 'T12:00:00').toLocaleDateString(undefined, { weekday: 'long', month: 'short', day: 'numeric' })}</div>}
      {time && <div className="sc-time">{time}</div>}</>
  )
  if ((b.kind === 'text' || b.kind === 'say') && b.line) {
    const speaker = b.speaker ?? b.who
    const mine = speaker && me !== null && speaker.id === me
    return (
      <>
        {head}
        {b.text && <div className="sc-stage">{b.text}</div>}
        <div className={`sc-msg ${mine ? 'me' : ''} ${b.kind === 'say' ? 'said' : ''}`}>
          {speaker && !mine && <button className="sc-who" onClick={() => onWho(speaker.id, speaker.name)}>{speaker.name.split(' ')[0]}{b.channel ? <small> · {b.channel}</small> : null}</button>}
          <div className="sc-bubble">{b.kind === 'say' ? `“${b.line}”` : b.line}</div>
          {why}
        </div>
      </>
    )
  }
  const cls = b.kind === 'arrive' ? 'arrive' : b.kind === 'event' ? 'event' : b.kind === 'wrap' ? 'wrap' : b.kind === 'decide' ? 'decide'
    : b.kind === 'silence' || b.kind === 'unseen' ? 'silence' : b.kind === 'thought' ? 'thought' : 'stage'
  return (
    <>
      {head}
      <div className={`sc-stage ${cls}`}>
        {b.kind === 'arrive' && <span className="sc-dot" />}
        <span>{b.text}</span>
        {b.line && <span className="sc-said"> “{b.line}”</span>}
        {b.ref?.kind === 'occasion' && <button className="linkish sc-watch" onClick={() => openScene({ kind: 'occasion', id: Number(b.ref!.id) }, me)}>{G.play} watch</button>}
        {why}
      </div>
    </>
  )
}

export function Initials({ name, id, size = 28 }: { name: string; id: number; size?: number }) {
  const ini = useMemo(() => name.split(' ').map(x => x[0]).slice(0, 2).join(''), [name])
  return <span className="ini" style={{ width: size, height: size, fontSize: size * 0.4, background: `var(--s${(id % 8) + 1})` }}>{ini}</span>
}
