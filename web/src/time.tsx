// Time controls: play/pause with a watchable or fast pace, quick steps, and the academic-year ribbon
// (terms, breaks, today, the what-if split) that you can click to run to a date.
import { useEffect, useMemo, useRef, useState } from 'react'
import { api, STATIC } from './api'
import { useStore } from './store'

const fmtDate = (iso: string, opts: Intl.DateTimeFormatOptions = { weekday: 'short', month: 'short', day: 'numeric' }) =>
  new Date(iso + 'T12:00:00').toLocaleDateString(undefined, opts)
const dayToIso = (start: string, d: number) => {
  const t = new Date(start + 'T12:00:00')
  t.setDate(t.getDate() + d)
  return t.toISOString().slice(0, 10)
}

function useOutside(ref: React.RefObject<HTMLElement>, fn: () => void) {
  useEffect(() => {
    const h = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) fn() }
    document.addEventListener('mousedown', h)
    return () => document.removeEventListener('mousedown', h)
  }, [ref, fn])
}

/** Play / pause, pace, and quick steps. */
export function TimeControls() {
  const { status, refreshStatus, mode } = useStore()
  const job = status?.job ?? {}
  const running = job.state === 'running'
  const building = job.state === 'building'
  const [pace, setPace] = useState<'watch' | 'fast'>(() => (localStorage.getItem('ucsim-pace') as any) || 'watch')
  const [moreOpen, setMoreOpen] = useState(false)
  const [until, setUntil] = useState('')
  const [msg, setMsg] = useState('')
  const moreRef = useRef<HTMLDivElement>(null)
  useOutside(moreRef, () => setMoreOpen(false))
  const playing = running && (job.total ?? 0) >= 3000
  const step = async (body: any) => {
    setMoreOpen(false)
    try { await api.step(body); setTimeout(() => refreshStatus(), 150) } catch (e: any) { setMsg(String(e.message ?? e)) }
  }
  const play = () => step({ days: 3650, pace: pace === 'watch' ? 1.0 : 0 })
  const pause = async () => { await api.cancel(); setTimeout(() => refreshStatus(), 250) }
  const setP = (p: 'watch' | 'fast') => { setPace(p); try { localStorage.setItem('ucsim-pace', p) } catch { /* private mode */ } }
  if (STATIC) return <span className="pill">Read-only snapshot · install the app to run time forward</span>
  const busy = running || building
  return (
    <div className="controls" role="group" aria-label="Time">
      {running
        ? <button className="btn small primary play" onClick={pause} title="Stop time here">⏸ Pause</button>
        : <button className="btn small primary play" onClick={play} disabled={building} title={pace === 'watch' ? 'Run day by day, slowly enough to watch pages update' : 'Run as fast as the computer allows'}>▶ Play</button>}
      <div className="seg small-seg" title="How fast Play runs">
        <button className={pace === 'watch' ? 'on' : ''} onClick={() => setP('watch')} disabled={running}>Watch</button>
        <button className={pace === 'fast' ? 'on' : ''} onClick={() => setP('fast')} disabled={running}>Fast</button>
      </div>
      {running && !playing && (
        <>
          <div className="progress"><i style={{ width: `${(100 * (job.progress ?? 0)) / (job.total || 1)}%` }} /></div>
          <span className="small muted tabular">{job.progress}/{job.total} days</span>
        </>
      )}
      {playing && <span className="small muted tabular live-dot">running · +{job.progress} days</span>}
      {!running && (
        <>
          {mode === 'advanced' && <button className="btn small" disabled={busy} onClick={() => step({ days: 1 })}>+1 day</button>}
          <button className="btn small" disabled={busy} onClick={() => step({ days: 7 })}>+1 week</button>
          <div className="menu-wrap" ref={moreRef}>
            <button className="btn small" disabled={busy} onClick={() => setMoreOpen(!moreOpen)} aria-expanded={moreOpen}>Jump ▾</button>
            {moreOpen && (
              <div className="menu">
                <button onClick={() => step({ hours: 1 })}>+1 hour <span className="muted">watch the map move</span></button>
                <button onClick={() => step({ days: 1 })}>+1 day</button>
                <button onClick={() => step({ days: 30 })}>+1 month</button>
                <button onClick={() => step({ days: 112 })}>+1 semester <span className="muted">≈16 weeks</span></button>
                <button onClick={() => step({ days: 365 })}>+1 year</button>
                <button onClick={() => step({ days: 1461 })}>+4 years <span className="muted">a whole college career</span></button>
                <div className="menu-sep" />
                <div className="menu-row">
                  <label className="small muted" htmlFor="run-until">Run until</label>
                  <input id="run-until" type="date" value={until} onChange={e => setUntil(e.target.value)} />
                  <button className="btn small primary" disabled={!until} onClick={() => {
                    const d0 = new Date(status.date + 'T12:00:00'), d1 = new Date(until + 'T12:00:00')
                    step({ days: Math.max(0, Math.round((+d1 - +d0) / 864e5)) })
                  }}>Go</button>
                </div>
                <p className="small muted" style={{ margin: '6px 8px 2px', maxWidth: 260 }}>Tip: click any future date on the calendar ribbon below to run to it.</p>
              </div>
            )}
          </div>
        </>
      )}
      {building && <span className="small muted">{job.phase === 'warming up' ? `New world: warming up ${job.progress}/${job.total}` : 'Building new world…'}</span>}
      {job.state === 'error' && <span className="pill" style={{ color: 'var(--critical)' }}>error: {job.error}</span>}
      {msg && <span className="pill" onClick={() => setMsg('')} style={{ color: 'var(--critical)', cursor: 'pointer' }}>{msg} ✕</span>}
    </div>
  )
}

/** The academic year as a ribbon: terms and breaks, today, the what-if split; click ahead to run there. */
export function TimeRibbon() {
  const { status, dataVersion, refreshStatus } = useStore()
  const [cal, setCal] = useState<any>(null)
  const [hover, setHover] = useState<{ x: number; d: number } | null>(null)
  const [ask, setAsk] = useState<{ x: number; d: number } | null>(null)
  const ref = useRef<HTMLDivElement>(null)
  const yearKey = status?.day !== undefined ? Math.floor((status.day + 0) / 7) : 0
  useEffect(() => { api.calendar().then(setCal).catch(() => setCal(null)) }, [dataVersion, yearKey])
  const span = cal ? cal.end - cal.start + 1 : 1
  const pct = (d: number) => `${(100 * (d - (cal?.start ?? 0))) / span}%`
  const segAt = (d: number) => cal?.segments.find((s: any) => d >= s.start && d <= s.end)
  const months = useMemo(() => {
    if (!cal) return []
    const out: { d: number; label: string }[] = []
    for (let d = cal.start; d <= cal.end; d++) {
      const iso = dayToIso(cal.start_date, d)
      if (iso.endsWith('-01')) out.push({ d, label: fmtDate(iso, { month: 'short' }) })
    }
    return out
  }, [cal])
  if (!cal || !status) return null
  const today = cal.today
  const pick = (e: React.MouseEvent) => {
    const r = ref.current!.getBoundingClientRect()
    const d = Math.round(cal.start + ((e.clientX - r.left) / r.width) * span)
    return { x: e.clientX - r.left, d: Math.max(cal.start, Math.min(cal.end, d)) }
  }
  const running = status.job?.state === 'running' || status.job?.state === 'building'
  return (
    <div className="timebar" aria-label="Academic calendar">
      <span className="timebar-year small">{cal.year}</span>
      <div className="timebar-track" ref={ref}
        onMouseMove={e => setHover(pick(e))} onMouseLeave={() => setHover(null)}
        onClick={e => { const p = pick(e); if (!STATIC && !running && p.d > today) setAsk(p); else setAsk(null) }}>
        {cal.segments.map((s: any) => (
          <div key={s.start} className={`seg-${s.kind}`} style={{ left: pct(s.start), width: `${(100 * (s.end - s.start + 1)) / span}%` }}>
            {(s.end - s.start) > 40 && <span>{s.label}</span>}
          </div>
        ))}
        <div className="timebar-past" style={{ width: pct(today) }} />
        {months.map(m => <i key={m.d} className="timebar-month" style={{ left: pct(m.d) }}><b>{m.label}</b></i>)}
        {cal.fork_day !== null && cal.fork_day !== undefined && cal.fork_day >= cal.start && (
          <i className="timebar-fork" style={{ left: pct(cal.fork_day) }} title="The what-if world split off here" />
        )}
        <i className="timebar-today" style={{ left: pct(today) }} title="Today in the simulation" />
        {hover && (
          <div className="timebar-tip" style={{ left: hover.x }}>
            {fmtDate(dayToIso(cal.start_date, hover.d))} · {segAt(hover.d)?.label ?? ''}{hover.d > today && !STATIC ? ' · click to run here' : hover.d < today ? ' · already happened' : ''}
          </div>
        )}
        {ask && (
          <div className="timebar-ask" style={{ left: Math.min(ask.x, (ref.current?.clientWidth ?? 600) - 250) }} onClick={e => e.stopPropagation()}>
            <span>Run to <b>{fmtDate(dayToIso(cal.start_date, ask.d))}</b>? ({ask.d - today} days)</span>
            <button className="btn small primary" onClick={async () => { setAsk(null); await api.step({ days: ask.d - today }); setTimeout(() => refreshStatus(), 150) }}>Run</button>
            <button className="btn small" onClick={async () => { setAsk(null); await api.step({ days: ask.d - today, pace: 1.0 }); setTimeout(() => refreshStatus(), 150) }}>Watch</button>
            <button className="btn small" onClick={() => setAsk(null)}>✕</button>
          </div>
        )}
      </div>
    </div>
  )
}
