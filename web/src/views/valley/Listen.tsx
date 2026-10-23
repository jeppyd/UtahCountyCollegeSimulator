// Listening in: the in-person conversations of the people you follow (or at one get-together), as they happen. The
// simulation resolves each part of the day at once, so new conversations arrive block by block while time runs and
// are appended (never reshuffled). Pause, step and replay; switch whose side you're on. Being near each other isn't
// a conversation: only talk the engine recorded is shown. Open with openListen({ people } | { occ }).
import { useEffect, useMemo, useRef, useState } from 'react'
import { create } from 'zustand'
import { phoneApi, type Conversation } from '../../api'
import { G } from '../../game'
import { timeCtl } from '../../hud'
import { useLens, useStore } from '../../store'
import { Initials } from './Scene'
import { Line, WordingBar } from './Phone'
import './phone.css'

type Ref = { people?: number[]; occ?: number; title?: string }
export const useListen = create<{ open: Ref | null; set: (r: Ref | null) => void }>(set => ({ open: null, set: open => set({ open }) }))
export const openListen = (r: Ref) => useListen.getState().set(r)

const STEP_MS = 1300

export function ListenView() {
  const { open, set } = useListen()
  const { u } = useLens()
  const v = useStore(s => s.dataVersion)
  const status = useStore(s => s.status)
  const [convs, setConvs] = useState<Conversation[]>([])
  const [err, setErr] = useState('')
  const [loaded, setLoaded] = useState(false)
  const last = useRef(-1)
  const gen = useRef(0)
  const [shown, setShown] = useState(0)      // lines shown, over all conversations in order
  const [playing, setPlaying] = useState(true)
  const [pov, setPov] = useState<number | null>(null)
  const [why, setWhy] = useState<number | null>(null)
  const end = useRef<HTMLDivElement>(null)
  // a new subject (or world): start over
  useEffect(() => { setConvs([]); setLoaded(false); last.current = -1; setShown(0); setPlaying(true); setPov(open?.people?.[0] ?? null); gen.current++ }, [JSON.stringify(open), u])
  // each time the world moves on, fetch only what's newer and append it
  useEffect(() => {
    if (!open) return
    const g = gen.current
    const since = last.current
    phoneApi.listen({ people: open.people, occ: open.occ, since_ex: since, days: since < 0 ? 2 : 30 }, u).then(r => {
      if (g !== gen.current) return
      setErr('')
      setLoaded(true)
      if (r.last_ex > last.current) last.current = r.last_ex
      if (!r.conversations.length) return
      setConvs(old => {
        const byKey = new Map(old.map(c => [c.key, c]))
        const out = [...old]
        for (const c of r.conversations) {
          const had = byKey.get(c.key)
          if (had) {   // more of a conversation already shown: append its new lines only
            const seen = new Set(had.lines.map(l => l.id))
            const i = out.indexOf(had)
            out[i] = { ...had, lines: [...had.lines, ...c.lines.filter(l => !seen.has(l.id))], exchanges: [...had.exchanges, ...c.exchanges] }
          } else out.push(c)
        }
        return out
      })
    }).catch(e => { if (g === gen.current) setErr(String(e?.message ?? e)) })
  }, [JSON.stringify(open), u, v])
  // re-read one conversation's words after the model has worded it (the same view the wording was asked for)
  const reword = (c: Conversation) => {
    phoneApi.listen({ people: c.people.map(p => p.id), occ: c.occasion ?? undefined, since_ex: -1, days: 30 }, u).then(r => {
      const n = r.conversations.find(x => x.key === c.key)
      if (!n) return
      const t = new Map(n.lines.map(l => [l.id, l.text]))
      setConvs(old => old.map(x => (x.key !== c.key ? x : { ...x, wording: n.wording, lines: x.lines.map(l => ({ ...l, text: t.get(l.id) ?? l.text })) })))
    }).catch(() => { /* keep the plain words */ })
  }
  const total = useMemo(() => convs.reduce((n, c) => n + c.lines.length, 0), [convs])
  useEffect(() => {
    if (!playing || shown >= total) return
    const t = setTimeout(() => setShown(shown + 1), STEP_MS)
    return () => clearTimeout(t)
  }, [playing, shown, total])
  useEffect(() => { end.current?.scrollIntoView({ block: 'end', behavior: 'smooth' }) }, [shown])
  useEffect(() => {
    if (!open) return
    const k = (e: KeyboardEvent) => { if (e.key === 'Escape') set(null) }
    window.addEventListener('keydown', k)
    return () => window.removeEventListener('keydown', k)
  }, [!!open])
  if (!open) return null
  const running = status?.job?.state === 'running'
  const people = new Map<number, string>()
  for (const c of convs) for (const p of c.people) people.set(p.id, p.name)
  let left = shown
  const done = shown >= total
  return (
    <div className="sc-veil" onMouseDown={e => { if (e.target === e.currentTarget) set(null) }}>
      <section className="sc" role="dialog" aria-label="Listening in">
        <header className="sc-h">
          <div className="grow">
            <div className="eyebrow"><span className="sc-live">● listening</span>{status?.date ? new Date(status.date + 'T12:00:00').toLocaleDateString(undefined, { weekday: 'long', month: 'short', day: 'numeric' }) : ''}</div>
            <h2>{open.title ?? 'Listening in'}</h2>
            <div className="secondary small">Conversations the simulation resolved, one part of the day at a time. Ordinary talk is a sample; what mattered is always kept.</div>
          </div>
          <button className="bx-icon" onClick={() => set(null)} title="Close (Esc)">{G.close}</button>
        </header>
        {people.size > 1 && <div className="sc-cast">
          <span className="small muted">Whose side:</span>
          {[...people].slice(0, 12).map(([id, name]) => <button key={id} className={`sc-face ${pov === id ? 'on' : ''}`} onClick={() => setPov(pov === id ? null : id)}><Initials name={name} id={id} />{name.split(' ')[0]}</button>)}
        </div>}
        <div className="sc-body">
          {err && <div className="bx-problem">{err}</div>}
          {!loaded && !err && <div className="sc-wait">Listening…</div>}
          {loaded && !convs.length && <div className="sc-wait">Nobody's talking right now. {running ? 'Conversations appear as time passes.' : 'Let time run, and conversations appear here as they happen.'}</div>}
          {convs.map(c => {
            if (left <= 0) return null
            const n = Math.min(left, c.lines.length)
            left -= n
            return (
              <div key={c.key} className="ph-conv">
                <div className="sc-stage">{c.block_name} · {c.where} · {c.people.map(p => p.name.split(' ')[0]).join(', ')}</div>
                {c.lines.slice(0, n).map((l, k) => <Line key={l.id + k} l={l} prev={c.lines[k - 1] ?? { ...l, date: '', time: null }} me={pov} why={why} setWhy={setWhy} said />)}
                {n === c.lines.length && c.wording.realizable && <WordingBar w={c.wording} view={{ kind: 'listen', people: c.people.map(p => p.id), occ: c.occasion ?? undefined, days: 30, conv: c.key }} onDone={() => reword(c)} />}
              </div>
            )
          })}
          {!done && playing && <div className="sc-typing"><i /><i /><i /></div>}
          {loaded && done && convs.length > 0 && <div className="sc-wait">{running ? 'Listening… more as time passes.' : 'That’s everything so far.'}</div>}
          <div ref={end} />
        </div>
        <footer className="sc-f">
          {!done ? <>
            <button className="btn small" onClick={() => setPlaying(!playing)}>{playing ? <>{G.pause} Pause</> : <>{G.play} Play</>}</button>
            <button className="btn small" onClick={() => setShown(Math.min(total, shown + 1))}>{G.step} Next</button>
            <button className="btn small ghost" onClick={() => setShown(total)}>Show it all</button>
          </> : <>
            <button className="btn small" onClick={() => { setShown(0); setPlaying(true) }}>{G.play} Replay</button>
            {!running && <button className="btn small primary" onClick={() => timeCtl.play()}>{G.play} Let time run</button>}
          </>}
          <span className="spacer" />
          <span className="sc-note">What happens is recorded; the words are illustrative.</span>
        </footer>
      </section>
    </div>
  )
}
