// An answer from Ask the world or an interview: each sentence with the people, places and events it rests on as
// chips (click to focus), "what this rests on" listing the facts it cites, sentences the checker removed with the
// reason, and which model answered and how long it took. useTalkJob starts and polls the background job.
import { useEffect, useRef, useState } from 'react'
import { talkApi, type TalkJob, type TalkRef, type TalkResult, type Universe } from '../api'
import type { Ref, RefKind } from '../bench/selection'
import { RefChip } from './RefChip'
import './talk.css'

const KIND_WORDS: Record<string, string> = { fact: 'fact', perception: 'how they see it', cause: 'a reason', measurement: 'a measurement', belief: 'what they believe' }
const BACKEND_WORDS: Record<string, string> = { claude: 'Claude (your subscription)', codex: 'Codex (your ChatGPT plan)', openai: 'the model on this computer', fake: 'a test stand-in' }

export function toRef(r: TalkRef, u: Universe): Ref | null {
  if (!['person', 'place', 'event', 'decision', 'tie'].includes(r.kind)) return null
  return { kind: r.kind as RefKind, id: r.id, label: r.name, u }
}

function Chips({ refs, u, hide }: { refs: TalkRef[]; u: Universe; hide?: number }) {
  const rs = refs.filter(r => !(hide !== undefined && r.kind === 'person' && Number(r.id) === hide)).map(r => toRef(r, u)).filter((r): r is Ref => !!r)
  if (!rs.length) return null
  return <span className="ta-chips">{rs.slice(0, 6).map(r => <RefChip key={`${r.kind}:${r.id}`} r={r} />)}</span>
}

export function Answer({ res, firstPerson = false }: { res: TalkResult; firstPerson?: boolean }) {
  const [open, setOpen] = useState(false)
  const u = res.u ?? 'base'
  const hide = firstPerson && res.person ? Number(res.person.id) : undefined   // the interviewee is the speaker
  const byId = new Map(res.claims.map(c => [c.id, c]))
  const cited = [...new Set(res.sentences.flatMap(s => s.claims))].map(id => byId.get(id)).filter(Boolean)
  return (
    <div className={`ta-answer ${firstPerson ? 'first' : ''}`}>
      {res.sentences.length === 0 && <div className="ta-none">No sentence of the answer held up against the facts.</div>}
      {res.sentences.map((s, k) => (
        <p key={k} className="ta-sent">{s.text} <Chips refs={s.refs} u={u} hide={hide} /></p>
      ))}
      {res.removed.length > 0 && (
        <div className="ta-removed">
          {res.removed.map((r, k) => (
            <div key={k}><s>{r.text}</s> <span className="why">removed: {r.reasons.join('; ')}</span></div>
          ))}
        </div>
      )}
      <button className="ta-more" onClick={() => setOpen(!open)}>{open ? '▾' : '▸'} What this rests on ({cited.length} fact{cited.length === 1 ? '' : 's'})</button>
      {open && (
        <ul className="ta-claims">
          {cited.map(c => c && (
            <li key={c.id}><span className={`ta-kind k-${c.kind}`}>{KIND_WORDS[c.kind] ?? c.kind}</span> {c.text} <Chips refs={[c.subject, ...c.refs]} u={u} /></li>
          ))}
        </ul>
      )}
      <div className="ta-foot">
        Answered by {BACKEND_WORDS[res.backend] ?? res.backend} in {res.seconds.toFixed(0)} s
        {res.repaired ? ' · fixed once after checking' : ''} · every sentence was checked against the simulator's facts
      </div>
    </div>
  )
}

/** Start a talk job and follow it until it ends. */
export function useTalkJob() {
  const [job, setJob] = useState<TalkJob | null>(null)
  const [error, setError] = useState<string | null>(null)
  const timer = useRef<number | null>(null)
  const stop = () => { if (timer.current !== null) { window.clearTimeout(timer.current); timer.current = null } }
  useEffect(() => stop, [])
  const follow = (id: string) => {
    const tick = async () => {
      try {
        const j = await talkApi.poll(id)
        setJob(j)
        if (j.state === 'queued' || j.state === 'running') timer.current = window.setTimeout(tick, 700)
      } catch (e: any) { setError(String(e?.message ?? e)) }
    }
    tick()
  }
  const run = async (start: () => Promise<{ job: string }>) => {
    stop(); setError(null); setJob(null)
    try { follow((await start()).job) } catch (e: any) { setError(String(e?.message ?? e)) }
  }
  const cancel = () => { if (job) talkApi.cancel(job.id).then(setJob).catch(() => undefined) }
  const busy = !!job && (job.state === 'queued' || job.state === 'running')
  return { job, error, busy, run, cancel, reset: () => { stop(); setJob(null); setError(null) } }
}

export function Steps({ job }: { job: TalkJob }) {
  const last = job.steps[job.steps.length - 1]
  return <div className="ta-steps"><i className="ta-dot" />{last?.text ?? 'Starting'}… <span className="t">{job.elapsed.toFixed(0)} s</span></div>
}
