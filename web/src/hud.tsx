// The heads-up display: the clock (with a sky that follows the time of day), Sims-style speed controls,
// the world lens, the butterfly meter, search and settings.
import { useEffect, useRef, useState } from 'react'
import { api, STATIC } from './api'
import { DivergenceMeter, G, LensSwitch, timeOfDay } from './game'
import { useStore } from './store'
import { WorldDialog } from './views/WorldSetup'
import { AiPill, useAiSetup } from './kit/AiSetup'

// seconds per simulated day at each speed (the server waits at least this long per day)
const SPEEDS: [number, string, string][] = [[1.4, 'Speed 1: about a day per second and a half', '▶'], [0.45, 'Speed 2: about two days per second', '▶▶'], [0, 'Speed 3: as fast as the computer allows', '▶▶▶']]

export function useOutside(ref: React.RefObject<HTMLElement>, fn: () => void) {
  useEffect(() => {
    const h = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) fn() }
    document.addEventListener('mousedown', h)
    return () => document.removeEventListener('mousedown', h)
  }, [ref, fn])
}

/** Start, stop or change the speed of time. Shared by the HUD buttons and keyboard shortcuts.
 *  Clicks are handled one at a time in order (a quick double click never races itself), a speed change while time
 *  runs only changes the pace (no stop and restart), and a pause shows at once while the day in progress finishes. */
type TimeCtl = { speed: number; waitIdle: () => Promise<void>; play: (speed?: number) => Promise<void>; pause: () => Promise<void>; step: (body: any) => Promise<void>; toggle: () => Promise<void> }
let chain: Promise<unknown> = Promise.resolve()
const queued = <T,>(fn: () => Promise<T>): Promise<T> => {
  const next = chain.then(fn, fn)
  chain = next.catch(() => {})
  return next
}
const markPausing = () => {
  const st = useStore.getState().status
  if (st?.job?.state === 'running') useStore.setState({ status: { ...st, job: { ...st.job, cancel: true } } })
}
export const timeCtl: TimeCtl = {
  speed: (() => { try { return Number(localStorage.getItem('ucsim-speed') ?? '0') } catch { return 0 } })(),
  // A pause takes effect when the day in progress ends, which can take several seconds in a full-size world.
  async waitIdle(maxMs = 90000) {
    const t0 = Date.now()
    while (Date.now() - t0 < maxMs) {
      const s = await useStore.getState().refreshStatus().catch(() => null)
      if (s && s.job?.state !== 'running') return
      await new Promise(r => setTimeout(r, 250))
    }
    throw new Error('Time is still finishing the current day; try again in a moment.')
  },
  play(speed = timeCtl.speed) {
    timeCtl.speed = speed
    try { localStorage.setItem('ucsim-speed', String(speed)) } catch { /* private mode */ }
    return queued(async () => {
      const st = useStore.getState().status
      if (st?.job?.state === 'running' && !st.job.cancel && (st.job.total ?? 0) >= 3000) {
        const r = await api.pace(SPEEDS[speed][0]).catch(() => ({ ok: false }))
        if (r.ok) { await useStore.getState().refreshStatus().catch(() => {}); return }
      }
      if (st?.job?.state === 'running') { await api.cancel(); await timeCtl.waitIdle() }
      await api.step({ days: 3650, pace: SPEEDS[speed][0] })
      await useStore.getState().refreshStatus().catch(() => {})
    })
  },
  pause() {
    markPausing()
    return queued(async () => { await api.cancel(); await useStore.getState().refreshStatus().catch(() => {}) })
  },
  step(body: any) {
    return queued(async () => {
      const st = useStore.getState().status
      if (st?.job?.state === 'building') throw new Error('A new world is still being built.')
      if (st?.job?.state === 'running') { await api.cancel(); await timeCtl.waitIdle() }
      await api.step(body)
      await useStore.getState().refreshStatus().catch(() => {})
    })
  },
  toggle() {
    const st = useStore.getState().status
    return st?.job?.state === 'running' && !st.job.cancel ? timeCtl.pause() : timeCtl.play()
  },
}

export function Hud() {
  const { status, setRoute, setPalette } = useStore()
  const job = status?.job ?? {}
  const running = job.state === 'running'
  const pausing = running && !!job.cancel
  const playing = running && !pausing && (job.total ?? 0) >= 3000
  const building = job.state === 'building'
  const [err, setErr] = useState('')
  const wrap = (p: Promise<any>) => p.catch(e => setErr(String(e?.message ?? e)))
  const date = status.date ? new Date(status.date + 'T12:00:00') : null
  const hour = status.hour ?? 6
  const hh = `${((hour + 11) % 12) + 1} ${hour < 12 || hour >= 24 ? 'am' : 'pm'}`
  const tod = timeOfDay(hour)
  const activeSpeed = playing ? SPEEDS.findIndex(s => Math.abs(s[0] - (job.pace ?? 0)) < 1e-6) : -1
  return (
    <header className="hud">
      <button className="hud-brand" onClick={() => setRoute(['bench'])} title="The workbench (home)">
        <svg width="28" height="28" viewBox="0 0 32 32" aria-hidden="true"><circle cx="10" cy="12" r="5" fill="var(--u-base)" /><circle cx="22" cy="10" r="4" fill="var(--u-alt)" /><circle cx="17" cy="22" r="5" fill="var(--s3)" /><path d="M10 12L22 10L17 22Z" stroke="var(--text-secondary)" fill="none" strokeWidth="1.5" /></svg>
        <span>Provo–Orem<small>Social Simulator</small></span>
      </button>

      <div className={`sky ${tod} ${running ? 'live' : ''}`} title={`Day ${status.day} of the simulation`}>
        <span className="sky-icon">{tod === 'night' ? G.moon : G.sun}</span>
        <div className="sky-text">
          <b className="tabular">{date ? date.toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric', year: 'numeric' }) : '—'}<span className="sky-hour"> · {hh}</span></b>
          <span>{pausing ? 'pausing after this day…' : running ? <span className="live-dot">{playing ? `time is running · +${job.progress ?? 0} days` : `running ${job.progress ?? 0}/${job.total} days`}</span> : status.season ?? ''}</span>
        </div>
      </div>

      {STATIC ? <span className="pill">Read-only snapshot · install the app to run time</span> : (
        <div className="speed" role="group" aria-label="Time speed">
          <button className={`sp pause ${!running || pausing ? 'on' : ''}`} onClick={() => wrap(timeCtl.pause())} disabled={!running || pausing} title="Pause (Space)">{G.pause}</button>
          {SPEEDS.map(([, t, l], k) => (
            <button key={k} className={`sp ${activeSpeed === k ? 'on' : ''}`} onClick={() => wrap(timeCtl.play(k))} disabled={building} title={`${t} (Space plays at the last speed)`}>{l}</button>
          ))}
          <span className="sp-sep" />
          <button className="sp txt" disabled={running || building} onClick={() => wrap(timeCtl.step({ days: 1 }))} title="One day (.)">+1d</button>
          <button className="sp txt" disabled={running || building} onClick={() => wrap(timeCtl.step({ days: 7 }))} title="One week (>)">+1w</button>
          <JumpMenu disabled={running || building} onErr={setErr} />
        </div>
      )}
      {running && !playing && <div className="progress"><i style={{ width: `${(100 * (job.progress ?? 0)) / (job.total || 1)}%` }} /></div>}
      {building && <span className="small muted">{job.phase === 'warming up' ? `New world: warming up ${job.progress}/${job.total}` : 'Building a new world…'}</span>}
      {job.state === 'error' && <span className="pill" style={{ color: 'var(--critical)' }}>error: {job.error}</span>}
      {err && <button className="pill" onClick={() => setErr('')} style={{ color: 'var(--critical)' }}>{err} ✕</button>}

      <span className="spacer" />
      <LensSwitch />
      <DivergenceMeter onClick={() => setRoute(['whatif'])} />
      <button className="hud-search" onClick={() => setPalette(true)} title="Search fields, people, places, pages and actions (Ctrl K or /)">
        {G.search}<span>Search anything</span><kbd>Ctrl K</kbd>
      </button>
      <span className="hud-pop small tabular" title="People living in Provo/Orem right now">{G.people}{status.present?.toLocaleString()}</span>
      <UpdatePill />
      <AiPill />
      <Settings />
    </header>
  )
}

function JumpMenu({ disabled, onErr }: { disabled: boolean; onErr: (s: string) => void }) {
  const status = useStore(s => s.status)
  const [open, setOpen] = useState(false)
  const [until, setUntil] = useState('')
  const ref = useRef<HTMLDivElement>(null)
  useOutside(ref, () => setOpen(false))
  const go = (body: any) => { setOpen(false); timeCtl.step(body).catch((e: any) => onErr(String(e?.message ?? e))) }
  return (
    <div className="menu-wrap" ref={ref}>
      <button className="sp txt" disabled={disabled} onClick={() => setOpen(!open)} aria-expanded={open}>Jump ▾</button>
      {open && (
        <div className="menu">
          <button onClick={() => go({ hours: 1 })}>+1 hour <span className="muted">watch the map move</span></button>
          <button onClick={() => go({ days: 30 })}>+1 month</button>
          <button onClick={() => go({ days: 112 })}>+1 semester <span className="muted">≈16 weeks</span></button>
          <button onClick={() => go({ days: 365 })}>+1 year</button>
          <button onClick={() => go({ days: 1461 })}>+4 years <span className="muted">a whole college career</span></button>
          <div className="menu-sep" />
          <div className="menu-row">
            <label className="small muted" htmlFor="run-until">Run until</label>
            <input id="run-until" type="date" value={until} onChange={e => setUntil(e.target.value)} />
            <button className="btn small primary" disabled={!until} onClick={() => {
              const d0 = new Date(status.date + 'T12:00:00'), d1 = new Date(until + 'T12:00:00')
              go({ days: Math.max(0, Math.round((+d1 - +d0) / 864e5)) })
            }}>Go</button>
          </div>
          <p className="small muted" style={{ margin: '6px 8px 2px', maxWidth: 260 }}>Tip: click any future date on the calendar strip to run to it.</p>
        </div>
      )}
    </div>
  )
}

function Settings() {
  const { theme, setTheme, news, setNews, mode, setMode, status } = useStore()
  const [open, setOpen] = useState(false)
  const [worldOpen, setWorldOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)
  useOutside(ref, () => setOpen(false))
  return (
    <div className="menu-wrap" ref={ref}>
      <button className="hud-icon" onClick={() => setOpen(!open)} aria-expanded={open} aria-label="Settings" title="Settings">{G.gear}</button>
      {open && (
        <div className="menu right">
          <div className="menu-row"><span className="small muted" style={{ width: 92 }}>Theme</span>
            <div className="seg small-seg">{(['auto', 'light', 'dark'] as const).map(t => <button key={t} className={theme === t ? 'on' : ''} onClick={() => setTheme(t)}>{t}</button>)}</div></div>
          <div className="menu-row"><span className="small muted" style={{ width: 92 }}>News pop-ups</span>
            <div className="seg small-seg"><button className={news ? 'on' : ''} onClick={() => setNews(true)}>on</button><button className={!news ? 'on' : ''} onClick={() => setNews(false)}>off</button></div></div>
          <div className="menu-row"><span className="small muted" style={{ width: 92 }} title="Show formulas, evidence labels, parameters and research tools inside pages">Research details</span>
            <div className="seg small-seg"><button className={mode === 'simple' ? 'on' : ''} onClick={() => setMode('simple')}>hide</button><button className={mode === 'advanced' ? 'on' : ''} onClick={() => setMode('advanced')}>show</button></div></div>
          {!STATIC && <><div className="menu-sep" />
            <button onClick={() => { setOpen(false); useAiSetup.getState().show() }}>Connect an AI… <span className="muted">Claude, ChatGPT or a local model</span></button>
            <button onClick={() => { setOpen(false); setWorldOpen(true) }}>Build a new world… <span className="muted">scale {status.scale} · seed {status.seed}</span></button>
            <UpdateRow /></>}
          <div className="menu-sep" />
          <div className="small muted" style={{ padding: '4px 9px 6px', lineHeight: 1.6 }}>
            Keys: <span className="kbd">Space</span> play/pause · <span className="kbd">1</span><span className="kbd">2</span><span className="kbd">3</span> Original / What-if / Compare · <span className="kbd">.</span> +1 day · <span className="kbd">&gt;</span> +1 week · <span className="kbd">/</span> search
          </div>
        </div>
      )}
      {worldOpen && <WorldDialog onClose={() => setWorldOpen(false)} />}
    </div>
  )
}

// ------------------------------------------------------------------ in-app updates
let updateInfo: any = null                 // one check per session, shared by the pill and the settings menu
const updateSubs = new Set<(u: any) => void>()
function setUpdate(u: any) { updateInfo = u; updateSubs.forEach(f => f(u)) }
function useUpdate() {
  const [u, setU] = useState<any>(updateInfo)
  useEffect(() => { updateSubs.add(setU); return () => { updateSubs.delete(setU) } }, [])
  return u
}
let checked = false
async function checkUpdate(force = false) {
  try { setUpdate(await api.updateCheck(force)) } catch (e: any) { setUpdate({ error: String(e?.message ?? e) }) }
}

function UpdatePanel({ u }: { u: any }) {
  const [st, setSt] = useState<any>(u?.state ?? { state: 'idle' })
  const [err, setErr] = useState('')
  useEffect(() => {
    if (st.state !== 'downloading' && st.state !== 'installing') return
    const t = window.setInterval(() => api.updateStatus().then(setSt).catch(() => setSt({ state: 'installing' })), 700)   // the app quits while installing
    return () => window.clearInterval(t)
  }, [st.state])
  const go = async () => {
    setErr('')
    const r: any = await api.updateInstall().catch((e: any) => ({ ok: false, error: String(e?.message ?? e) }))
    if (!r.ok) setErr(r.error); else setSt(r.state)
  }
  if (!u) return <p className="small muted">Checking for updates…</p>
  const pct = st.total ? Math.round((100 * (st.done ?? 0)) / st.total) : 0
  return (
    <div className="update-panel">
      <div className="small">This version: <b>{u.current ?? 'running from source'}</b>{u.latest ? <> · latest: <b>{u.latest}</b></> : null}</div>
      {u.error && <p className="small pc-warn">{u.error}</p>}
      {u.source && !u.error && <p className="small muted">You're running from source: update with <code>git pull</code>, then restart.</p>}
      {!u.available && !u.error && !u.source && <p className="small">✓ You have the latest version.</p>}
      {u.available && <>
        <p className="small">Version {u.latest} is ready{u.published ? ` (released ${new Date(u.published).toLocaleDateString()})` : ''}.</p>
        {st.state === 'downloading' && <div className="progress" style={{ position: 'relative', height: 6 }}><i style={{ width: `${pct}%` }} /></div>}
        {st.state === 'downloading' && <p className="small muted">Downloading… {pct}%</p>}
        {st.state === 'installing' && <p className="small"><b>Installing.</b> The simulator closes and reopens by itself in a few seconds.</p>}
        {st.state === 'error' && <p className="small pc-warn">The update failed: {st.error}</p>}
        {(st.state === 'idle' || st.state === 'error') && <>
          {u.can_install
            ? <button className="btn primary small" onClick={go}>Update now</button>
            : <a className="btn small" href={u.page} target="_blank" rel="noreferrer">Download from GitHub</a>}
          <p className="small muted" style={{ marginBottom: 0 }}>The app restarts, so the current world closes; build a new one after the update.</p>
        </>}
      </>}
      {err && <p className="small pc-warn">{err}</p>}
    </div>
  )
}

function UpdatePill() {
  const u = useUpdate()
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)
  useOutside(ref, () => setOpen(false))
  useEffect(() => { if (!checked && !STATIC) { checked = true; window.setTimeout(() => checkUpdate(), 3000) } }, [])
  if (!u?.available) return null
  return (
    <div className="menu-wrap" ref={ref}>
      <button className="pill update-pill" onClick={() => setOpen(!open)} title={`Version ${u.latest} is available`}>⬆ Update</button>
      {open && <div className="menu right" style={{ width: 300, padding: 12 }}><UpdatePanel u={u} /></div>}
    </div>
  )
}

function UpdateRow() {
  const u = useUpdate()
  const [open, setOpen] = useState(false)
  return <>
    <button onClick={() => { setOpen(!open); if (!open) checkUpdate(true) }}>Check for updates <span className="muted">{u?.current ? `v${u.current}` : ''}{u?.available ? ' · update ready' : ''}</span></button>
    {open && <div style={{ padding: '4px 9px 8px', maxWidth: 300 }}><UpdatePanel u={u} /></div>}
  </>
}
