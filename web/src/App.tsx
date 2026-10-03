import { useEffect, useRef, useState } from 'react'
import { api, STATIC } from './api'
import { Icons } from './components'
import { useStore } from './store'
import About from './views/About'
import CausalWeb from './views/CausalWeb'
import Crosstab from './views/Crosstab'
import Events from './views/Events'
import Explore from './views/Explore'
import Flows from './views/Flows'
import Guide from './views/Guide'
import Home from './views/Home'
import Lab from './views/Lab'
import MapView from './views/MapView'
import Mechanisms from './views/Mechanisms'
import NetworkView from './views/NetworkView'
import Overview from './views/Overview'
import People from './views/People'
import PersonView from './views/PersonView'
import Places from './views/Places'
import Variables from './views/Variables'
import { WorldDialog, WorldSetupPage } from './views/WorldSetup'

// Navigation is organized by what you are trying to do. `simple: false` items only show in Advanced mode.
const NAV: { group: string; items: { id: string; label: string; icon: string; simple?: boolean; hint: string }[] }[] = [
  { group: '', items: [
    { id: 'home', label: 'Home', icon: 'home', simple: true, hint: 'Your home base: what is happening and where to start' },
    { id: 'guide', label: 'Field guide', icon: 'guide', simple: true, hint: 'How this world works: layers, people, rules, time, evidence' },
  ] },
  { group: 'Watch the world', items: [
    { id: 'dashboard', label: 'Vital signs', icon: 'overview', simple: true, hint: 'Trends over time for the whole population or your group' },
    { id: 'map', label: 'Map', icon: 'map', simple: true, hint: 'Where people are, live, and how places differ' },
    { id: 'network', label: 'Friend network', icon: 'network', simple: true, hint: 'Who is friends with whom' },
  ] },
  { group: 'Follow lives', items: [
    { id: 'people', label: 'People', icon: 'people', simple: true, hint: 'Find and follow individual synthetic people' },
    { id: 'events', label: 'Life events', icon: 'events', simple: true, hint: 'What happened, how often, and what caused it' },
  ] },
  { group: 'Ask questions', items: [
    { id: 'explore', label: 'Explore a measure', icon: 'explore', simple: true, hint: 'Distribution of any measure; relate two measures' },
    { id: 'crosstab', label: 'Compare groups', icon: 'crosstab', simple: true, hint: 'Cross-tabs: how one thing varies by another' },
    { id: 'flows', label: 'Flows over time', icon: 'flows', simple: true, hint: 'How people move between states (single → dating → married…)' },
    { id: 'places', label: 'Places', icon: 'places', simple: true, hint: 'Apartment complexes, wards, schools, neighborhoods' },
  ] },
  { group: 'What if?', items: [
    { id: 'lab', label: 'What-if lab', icon: 'lab', simple: true, hint: 'Change something and compare two versions of the world' },
    { id: 'causal', label: 'Cause & effect', icon: 'causal', simple: true, hint: 'The web of what affects what' },
  ] },
  { group: 'The model', items: [
    { id: 'variables', label: 'Data dictionary', icon: 'variables', simple: true, hint: 'Every measure the model tracks' },
    { id: 'mechanisms', label: 'Rules', icon: 'mechanisms', hint: 'Every behavioral rule, its formula and evidence' },
    { id: 'about', label: 'Evidence & sources', icon: 'about', hint: 'Data sources, evidence levels, limitations' },
  ] },
]

export default function App() {
  const { route, setRoute, status, refreshStatus, registry, mode } = useStore()
  const [err, setErr] = useState<string | null>(null)
  useEffect(() => {
    useStore.getState().setTheme(useStore.getState().theme)
    ;(async () => {
      try {
        const [reg, presets] = await Promise.all([api.registry(), api.presets()])
        useStore.setState({ registry: reg, presets })
        await refreshStatus()
      } catch (e: any) { setErr(String(e.message ?? e)) }
    })()
  }, [])
  useEffect(() => {
    if (STATIC) return
    const running = status?.job?.state === 'running' || status?.job?.state === 'building'
    const t = setInterval(() => refreshStatus().catch(() => {}), running ? 700 : 4000)
    return () => clearInterval(t)
  }, [status?.job?.state])

  if (err) return <div className="empty">Could not reach the simulator: {err}<br />Start it with <span className="kbd">python -m ucsim.api.server</span></div>
  if (!registry || !status) return <div className="empty">Loading the synthetic society…</div>
  if (!STATIC && !status.has_world) return <WorldSetupPage />

  const view = route[0] === 'overview' ? 'dashboard' : route[0] || 'home'
  let body
  switch (view) {
    case 'guide': body = <Guide section={route[1]} />; break
    case 'dashboard': body = <Overview />; break
    case 'map': body = <MapView initial={route[1]} />; break
    case 'people': body = <People />; break
    case 'person': body = <PersonView id={Number(route[1])} />; break
    case 'network': body = <NetworkView />; break
    case 'explore': body = <Explore x0={route[1]} y0={route[2]} g0={route[3]} />; break
    case 'crosstab': body = <Crosstab row0={route[1]} col0={route[2]} />; break
    case 'flows': body = <Flows var0={route[1]} />; break
    case 'events': body = <Events eventId={route[1] ? Number(route[1]) : undefined} />; break
    case 'places': body = <Places kind={route[1]} id={route[2] ? Number(route[2]) : undefined} />; break
    case 'lab': body = <Lab preset={route[1]} />; break
    case 'causal': body = <CausalWeb focus={route[1]} />; break
    case 'variables': body = <Variables id={route[1]} />; break
    case 'mechanisms': body = <Mechanisms id={route[1]} />; break
    case 'about': body = <About />; break
    default: body = <Home />
  }
  const active = view === 'person' ? 'people' : view
  return (
    <div className="app">
      <TopBar />
      <nav className="sidenav" aria-label="Sections">
        {NAV.map(g => {
          const items = g.items.filter(i => mode === 'advanced' || i.simple)
          if (!items.length) return null
          return (
            <div key={g.group || 'top'} className="navgroup">
              {g.group && <div className="group">{g.group}</div>}
              {items.map(i => (
                <button key={i.id} title={i.hint} className={`navitem ${active === i.id ? 'active' : ''}`} onClick={() => setRoute([i.id])}>
                  {Icons[i.icon] ?? Icons.about}<span>{i.label}</span>
                </button>
              ))}
            </div>
          )
        })}
        <div className="nav-foot">
          <ModeSwitch />
        </div>
      </nav>
      <main className="main">{body}</main>
    </div>
  )
}

function ModeSwitch() {
  const { mode, setMode } = useStore()
  return (
    <div className="mode-switch" title="Simple mode keeps the essentials; Advanced shows every tool (rules, formulas, Monte Carlo, sweeps, custom interventions)">
      <div className="small muted" style={{ marginBottom: 4 }}>Detail level</div>
      <div className="seg" style={{ width: '100%' }}>
        <button className={mode === 'simple' ? 'on' : ''} onClick={() => setMode('simple')} style={{ flex: 1 }}>Simple</button>
        <button className={mode === 'advanced' ? 'on' : ''} onClick={() => setMode('advanced')} style={{ flex: 1 }}>Advanced</button>
      </div>
    </div>
  )
}

function useOutside(ref: React.RefObject<HTMLElement>, onOut: () => void) {
  useEffect(() => {
    const h = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) onOut() }
    document.addEventListener('mousedown', h)
    return () => document.removeEventListener('mousedown', h)
  }, [ref, onOut])
}

function TopBar() {
  const { status, refreshStatus, universe, setUniverse, theme, setTheme, mode, setRoute } = useStore()
  const job = status?.job ?? {}
  const running = job.state === 'running'
  const building = job.state === 'building'
  const [until, setUntil] = useState('')
  const [worldOpen, setWorldOpen] = useState(false)
  const [moreOpen, setMoreOpen] = useState(false)
  const moreRef = useRef<HTMLDivElement>(null)
  useOutside(moreRef, () => setMoreOpen(false))
  const [msg, setMsg] = useState('')
  const step = async (body: any) => {
    setMoreOpen(false)
    try { await api.step(body); setTimeout(() => refreshStatus(), 150) } catch (e: any) { setMsg(String(e.message ?? e)) }
  }
  const date = status.date ? new Date(status.date + 'T12:00:00') : null
  const hour = status.hour ?? 6
  const hh = `${((hour + 11) % 12) + 1}${hour < 12 || hour >= 24 ? 'am' : 'pm'}`
  const busy = running || building
  const quick: [string, any, string][] = mode === 'advanced'
    ? [['+1 hour', { hours: 1 }, 'Advance one hour (activities happen at 8am, 1pm and 6pm; the day closes at 11pm)'], ['+1 day', { days: 1 }, ''], ['+1 week', { days: 7 }, ''], ['+1 month', { days: 30 }, ''], ['+semester', { days: 112 }, 'About 16 weeks'], ['+1 year', { days: 365 }, '']]
    : [['+1 day', { days: 1 }, ''], ['+1 week', { days: 7 }, ''], ['+1 month', { days: 30 }, '']]
  return (
    <header className="topbar">
      <button className="brand" onClick={() => setRoute(['home'])} title="Home">
        <svg width="26" height="26" viewBox="0 0 32 32" aria-hidden="true"><circle cx="10" cy="12" r="5" fill="var(--s1)" /><circle cx="22" cy="10" r="4" fill="var(--s2)" /><circle cx="17" cy="22" r="5" fill="var(--s3)" /><path d="M10 12L22 10L17 22Z" stroke="var(--text-secondary)" fill="none" strokeWidth="1.5" /></svg>
        <span>Provo–Orem <small>Social Simulator</small></span>
      </button>
      <div className="clock" title={`Day ${status.day} of the simulation`}>
        <b className="tabular">{date ? date.toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric', year: 'numeric' }) : '—'} <span className="muted">· {hh}</span></b>
        <span>{status.season ?? ''}</span>
      </div>
      {STATIC ? (
        <span className="pill">Read-only snapshot · install the app to run time forward</span>
      ) : (
        <div className="controls" role="group" aria-label="Run time forward">
          <span className="small muted run-label">Run</span>
          {quick.map(([l, b, t]) => <button key={l} className="btn small" disabled={busy} title={t || undefined} onClick={() => step(b)}>{l}</button>)}
          <div className="menu-wrap" ref={moreRef}>
            <button className="btn small" disabled={busy} onClick={() => setMoreOpen(!moreOpen)} aria-expanded={moreOpen}>More ▾</button>
            {moreOpen && (
              <div className="menu">
                {mode !== 'advanced' && <>
                  <button onClick={() => step({ hours: 1 })}>+1 hour <span className="muted">watch the map move</span></button>
                  <button onClick={() => step({ days: 112 })}>+1 semester <span className="muted">≈16 weeks</span></button>
                  <button onClick={() => step({ days: 365 })}>+1 year</button>
                </>}
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
              </div>
            )}
          </div>
          {running && (
            <>
              <div className="progress"><i style={{ width: `${(100 * (job.progress ?? 0)) / (job.total || 1)}%` }} /></div>
              <span className="small muted tabular">{job.progress}/{job.total} days</span>
              <button className="btn small" onClick={() => api.cancel()}>Pause</button>
            </>
          )}
          {building && (
            <>
              <span className="small muted">{job.phase === 'warming up' ? `New world: warming up ${job.progress}/${job.total}` : 'Building new world…'}</span>
              <div className="progress"><i style={{ width: `${job.phase === 'warming up' ? (100 * (job.progress ?? 0)) / (job.total || 1) : 8}%` }} /></div>
            </>
          )}
          {job.state === 'error' && <span className="pill" style={{ color: 'var(--critical)' }}>error: {job.error}</span>}
          {msg && <span className="pill" onClick={() => setMsg('')} style={{ color: 'var(--critical)', cursor: 'pointer' }}>{msg} ✕</span>}
        </div>
      )}
      <span className="spacer" />
      {status.has_alt && (
        <div className="seg" title="Which version of the world every page shows">
          <button className={universe === 'base' ? 'on' : ''} onClick={() => setUniverse('base')}>Original</button>
          <button className={universe === 'alt' ? 'on' : ''} onClick={() => setUniverse('alt')}>What-if</button>
        </div>
      )}
      <span className="small muted tabular people-count" title="People currently living in Provo/Orem in the simulation">{status.present?.toLocaleString()} people</span>
      {!STATIC && (
        <button className="btn small" onClick={() => setWorldOpen(true)} disabled={building} title={`Scale ${status.scale} · seed ${status.seed}. Build a new world at a different size or seed.`}>
          World ⚙
        </button>
      )}
      {worldOpen && <WorldDialog onClose={() => setWorldOpen(false)} />}
      <select value={theme} onChange={e => setTheme(e.target.value as any)} title="Light or dark theme" aria-label="Theme" style={{ width: 82 }}>
        <option value="auto">Auto</option><option value="light">Light</option><option value="dark">Dark</option>
      </select>
    </header>
  )
}
