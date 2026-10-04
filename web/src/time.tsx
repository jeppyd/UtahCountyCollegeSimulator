// The academic-year ribbon (terms, breaks, today, the what-if split) that you can click to run to a date.
// Play/pause and speed live in the HUD (hud.tsx).
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
