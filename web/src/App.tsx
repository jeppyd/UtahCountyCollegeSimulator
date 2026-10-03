import { useEffect, useState } from 'react'
import { api, STATIC } from './api'
import { Icons } from './components'
import { useStore } from './store'
import CausalWeb from './views/CausalWeb'
import Crosstab from './views/Crosstab'
import Events from './views/Events'
import Explore from './views/Explore'
import Lab from './views/Lab'
import MapView from './views/MapView'
import Mechanisms from './views/Mechanisms'
import NetworkView from './views/NetworkView'
import Overview from './views/Overview'
import People from './views/People'
import PersonView from './views/PersonView'
import Places from './views/Places'
import Variables from './views/Variables'
import About from './views/About'

const NAV: [string, string, string][] = [
  ['Observe', 'overview', 'Overview'], ['Observe', 'map', 'Map'], ['Observe', 'people', 'People'], ['Observe', 'network', 'Network'],
  ['Analyze', 'explore', 'Explore'], ['Analyze', 'crosstab', 'Cross-tabs'], ['Analyze', 'events', 'Events'], ['Analyze', 'places', 'Places'],
  ['Experiment', 'lab', 'Scenario lab'], ['Experiment', 'causal', 'Causal web'],
  ['Model', 'variables', 'Variables'], ['Model', 'mechanisms', 'Mechanisms'], ['Model', 'about', 'About & evidence'],
]

export default function App() {
  const { route, setRoute, status, refreshStatus, registry } = useStore()
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
  if (!status.day && status.day !== 0) return <div className="empty">Building the world… <div className="progress" style={{ margin: '12px auto' }}><i style={{ width: '50%' }} /></div></div>

  const view = route[0] || 'overview'
  let body
  switch (view) {
    case 'map': body = <MapView />; break
    case 'people': body = <People />; break
    case 'person': body = <PersonView id={Number(route[1])} />; break
    case 'network': body = <NetworkView />; break
    case 'explore': body = <Explore />; break
    case 'crosstab': body = <Crosstab />; break
    case 'events': body = <Events eventId={route[1] ? Number(route[1]) : undefined} />; break
    case 'places': body = <Places kind={route[1]} id={route[2] ? Number(route[2]) : undefined} />; break
    case 'lab': body = <Lab />; break
    case 'causal': body = <CausalWeb focus={route[1]} />; break
    case 'variables': body = <Variables id={route[1]} />; break
    case 'mechanisms': body = <Mechanisms id={route[1]} />; break
    case 'about': body = <About />; break
    default: body = <Overview />
  }
  let group = ''
  return (
    <div className="app">
      <TopBar />
      <nav className="sidenav">
        {NAV.map(([g, id, label]) => {
          const head = g !== group ? <div className="group" key={'g' + g}>{g}</div> : null
          group = g
          return [head, <button key={id} className={`navitem ${view === id || (view === 'person' && id === 'people') ? 'active' : ''}`} onClick={() => setRoute([id])}>{Icons[id === 'crosstab' ? 'crosstab' : id] ?? Icons.about}{label}</button>]
        })}
      </nav>
      <main className="main">{body}</main>
    </div>
  )
}

function TopBar() {
  const { status, refreshStatus, universe, setUniverse, theme, setTheme } = useStore()
  const job = status?.job ?? {}
  const running = job.state === 'running'
  const [until, setUntil] = useState('')
  const step = async (body: any) => {
    try { await api.step(body); setTimeout(() => refreshStatus(), 150) } catch (e: any) { alert(e.message) }
  }
  const date = status.date ? new Date(status.date + 'T12:00:00') : null
  const hour = status.hour ?? 6
  const hh = `${((hour + 11) % 12) + 1}${hour < 12 || hour >= 24 ? 'am' : 'pm'}`
  return (
    <header className="topbar">
      <div className="brand">
        <svg width="26" height="26" viewBox="0 0 32 32"><circle cx="10" cy="12" r="5" fill="var(--s1)" /><circle cx="22" cy="10" r="4" fill="var(--s2)" /><circle cx="17" cy="22" r="5" fill="var(--s3)" /><path d="M10 12L22 10L17 22Z" stroke="var(--text-secondary)" fill="none" strokeWidth="1.5" /></svg>
        <span>Provo–Orem Social Simulator <small>BYU · UVU</small></span>
      </div>
      <div className="clock">
        <b className="tabular">{date ? date.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' }) : '—'}</b>
        <span>{status.weekday} · {hh} · day {status.day}</span>
      </div>
      {STATIC ? (
        <span className="pill">Static demo snapshot · run locally to simulate</span>
      ) : (
        <div className="controls">
          <button className="btn small" disabled={running} onClick={() => step({ hours: 1 })} title="Advance one hour (activities happen at 8am, 1pm, 6pm; the day closes at 11pm)">+1h</button>
          <button className="btn small" disabled={running} onClick={() => step({ days: 1 })}>+1 day</button>
          <button className="btn small" disabled={running} onClick={() => step({ days: 7 })}>+1 week</button>
          <button className="btn small" disabled={running} onClick={() => step({ days: 30 })}>+1 month</button>
          <button className="btn small" disabled={running} onClick={() => step({ days: 112 })}>+semester</button>
          <button className="btn small" disabled={running} onClick={() => step({ days: 365 })}>+1 year</button>
          <input type="date" value={until} onChange={e => setUntil(e.target.value)} style={{ width: 140 }} title="Run until date" />
          <button className="btn small" disabled={running || !until} onClick={() => {
            const d0 = new Date(status.date + 'T12:00:00'), d1 = new Date(until + 'T12:00:00')
            step({ days: Math.max(0, Math.round((+d1 - +d0) / 864e5)) })
          }}>Run until</button>
          {running && (
            <>
              <div className="progress"><i style={{ width: `${(100 * (job.progress ?? 0)) / (job.total || 1)}%` }} /></div>
              <span className="small muted tabular">{job.progress}/{job.total}</span>
              <button className="btn small" onClick={() => api.cancel()}>Pause</button>
            </>
          )}
          {job.state === 'error' && <span className="pill" style={{ color: 'var(--critical)' }}>error: {job.error}</span>}
        </div>
      )}
      <span className="spacer" />
      {status.has_alt && (
        <div className="seg" title="Which universe the views show">
          <button className={universe === 'base' ? 'on' : ''} onClick={() => setUniverse('base')}>Baseline</button>
          <button className={universe === 'alt' ? 'on' : ''} onClick={() => setUniverse('alt')}>Intervention</button>
        </div>
      )}
      <span className="small muted tabular" title="agents present / allocated">{status.present?.toLocaleString()} people</span>
      <select value={theme} onChange={e => setTheme(e.target.value as any)} title="Theme" style={{ width: 86 }}>
        <option value="auto">Auto</option><option value="light">Light</option><option value="dark">Dark</option>
      </select>
    </header>
  )
}
