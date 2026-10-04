import { Component, ReactNode, useEffect, useState } from 'react'
import { api, STATIC } from './api'
import { G } from './game'
import { Hud, timeCtl } from './hud'
import { NAV } from './nav'
import { Palette } from './palette'
import { useStore } from './store'
import { TimeRibbon } from './time'
import { NewsWatcher, RecapWatcher, Toasts } from './toasts'
import About from './views/About'
import CausalWeb from './views/CausalWeb'
import Crosstab from './views/Crosstab'
import Events from './views/Events'
import Experiments from './views/Experiments'
import FieldExplorer from './views/explore/FieldExplorer'
import Flows from './views/Flows'
import Guide from './views/Guide'
import MapView from './views/MapView'
import ModelCheck from './views/ModelCheck'
import Mechanisms from './views/Mechanisms'
import NetworkView from './views/NetworkView'
import Overview from './views/Overview'
import People from './views/People'
import PersonView from './views/PersonView'
import Places from './views/Places'
import Relationships from './views/Relationships'
import Variables from './views/Variables'
import { ChangeDrawer } from './views/whatif/Change'
import WhatIf from './views/whatif/WhatIf'
import World from './views/World'
import { WorldSetupPage } from './views/WorldSetup'

export default function App() {
  const { route, setRoute, status, refreshStatus, registry } = useStore()
  const [err, setErr] = useState<string | null>(null)
  const [deskOpen, setDeskOpen] = useState<boolean>(() => { try { return localStorage.getItem('ucsim-desk') === 'open' } catch { return false } })
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
  useKeys()

  if (err) return <div className="empty">Could not reach the simulator: {err}<br />Start it with <span className="kbd">python -m ucsim.api.server</span></div>
  if (!registry || !status) return <div className="boot"><div className="boot-orbit"><i /><i /><i /></div>Waking up Provo and Orem…</div>
  if (!STATIC && !status.has_world) return <WorldSetupPage />

  const alias: Record<string, string> = { home: 'world', overview: 'trends', dashboard: 'trends', lab: 'whatif' }
  const view = alias[route[0]] ?? route[0] ?? 'world'
  let body
  switch (view) {
    case 'guide': body = <Guide section={route[1]} />; break
    case 'trends': body = <Overview />; break
    case 'map': body = <MapView initial={route[1]} />; break
    case 'people': body = <People />; break
    case 'person': body = <PersonView id={Number(route[1])} tab={route[2]} />; break
    case 'relationships': body = <Relationships tab={route[1]} />; break
    case 'network': body = <NetworkView />; break
    case 'explore': body = <FieldExplorer field={route[1]} split={route[2]} />; break
    case 'crosstab': body = <Crosstab row0={route[1]} col0={route[2]} />; break
    case 'flows': body = <Flows var0={route[1]} />; break
    case 'events': body = <Events eventId={route[1] && route[1] !== 'type' ? Number(route[1]) : undefined} type0={route[1] === 'type' ? route[2] : undefined} />; break
    case 'places': body = <Places kind={route[1]} id={route[2] ? Number(route[2]) : undefined} />; break
    case 'whatif': body = <WhatIf tab={route[1]} preset={route[0] === 'lab' ? route[1] : undefined} />; break
    case 'experiments': body = <Experiments />; break
    case 'causal': body = <CausalWeb focus={route[1]} />; break
    case 'variables': body = <Variables id={route[1]} />; break
    case 'mechanisms': body = <Mechanisms id={route[1]} />; break
    case 'modelcheck': body = <ModelCheck />; break
    case 'about': body = <About />; break
    default: body = <World />
  }
  const active = view === 'person' ? 'people' : view === 'network' ? 'relationships' : view
  const inDesk = NAV[1].items.some(i => i.id === active)
  const div = status.divergence?.any_state_diff
  return (
    <div className={`game ${view === 'map' ? 'full' : ''}`}>
      <Hud />
      <TimeRibbon />
      <nav className="worldnav" aria-label="Places">
        {NAV[0].items.map(i => (
          <button key={i.id} title={i.hint} className={`wn ${active === i.id ? 'active' : ''}`} onClick={() => setRoute([i.id])} style={{ ['--wc' as any]: `var(${i.color ?? '--accent'})` }}>
            <span className="wn-icon">{G[i.icon]}</span><span className="wn-label">{i.label}</span>
            {i.id === 'whatif' && status.has_alt && <span className="wn-badge tabular" title="Lives that differ between the worlds">{div !== undefined && div !== null ? `${(100 * div).toFixed(div < 0.1 ? 1 : 0)}%` : '•'}</span>}
          </button>
        ))}
        <div className={`desk ${deskOpen || inDesk ? 'open' : ''}`}>
          <button className="desk-head" onClick={() => { const v = !deskOpen; setDeskOpen(v); try { localStorage.setItem('ucsim-desk', v ? 'open' : 'closed') } catch { /* private */ } }} aria-expanded={deskOpen || inDesk}>
            <span className="wn-icon">{G.desk}</span><span className="wn-label">{NAV[1].label}</span><span className="desk-chev">{G.chevron}</span>
          </button>
          {(deskOpen || inDesk) && NAV[1].items.map(i => (
            <button key={i.id} title={i.hint} className={`wn sub ${active === i.id ? 'active' : ''}`} onClick={() => setRoute([i.id])}>
              <span className="wn-icon">{G[i.icon]}</span><span className="wn-label">{i.label}</span>
            </button>
          ))}
        </div>
        <span className="spacer" />
        {NAV[2].items.map(i => (
          <button key={i.id} title={i.hint} className={`wn ${active === i.id ? 'active' : ''}`} onClick={() => setRoute([i.id])}>
            <span className="wn-icon">{G[i.icon]}</span><span className="wn-label">{i.label}</span>
          </button>
        ))}
      </nav>
      <main className="main"><ViewBoundary key={view}>{body}</ViewBoundary></main>
      <NewsWatcher />
      <RecapWatcher />
      <Toasts />
      <Palette />
      <ChangeDrawer />
    </div>
  )
}

/** Global keys: Space play/pause, 1/2/3 lens, . +1 day, > +1 week, / or Ctrl-K search. */
function useKeys() {
  useEffect(() => {
    const h = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement
      const typing = t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.tagName === 'SELECT' || t.isContentEditable)
      const st = useStore.getState()
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); st.setPalette(!st.palette); return }
      if (typing || e.ctrlKey || e.metaKey || e.altKey) return
      if (e.key === 'Escape') { if (st.palette) st.setPalette(false); else if (st.drawer) st.openDrawer(null); return }
      if (st.palette || st.drawer) return
      if (e.key === '/') { e.preventDefault(); st.setPalette(true); return }
      if (STATIC) { if (['1', '2', '3'].includes(e.key) && st.status?.has_alt) st.setLens((['base', 'alt', 'compare'] as const)[Number(e.key) - 1]); return }
      const report = (p: Promise<any>) => p.catch((err: any) => st.toast({ kind: 'info', title: String(err?.message ?? err), ttl: 6000 }))
      const idle = st.status?.job?.state !== 'running'
      if (e.key === ' ') { e.preventDefault(); report(timeCtl.toggle()); return }
      if (e.key === '.') { if (idle) report(timeCtl.step({ days: 1 })); return }
      if (e.key === '>') { if (idle) report(timeCtl.step({ days: 7 })); return }
      if (['1', '2', '3'].includes(e.key) && st.status?.has_alt) st.setLens((['base', 'alt', 'compare'] as const)[Number(e.key) - 1])
    }
    window.addEventListener('keydown', h)
    return () => window.removeEventListener('keydown', h)
  }, [])
}

/** Keeps one broken view from blanking the whole app; offers a way back. */
class ViewBoundary extends Component<{ children: ReactNode }, { err: string | null }> {
  state = { err: null as string | null }
  static getDerivedStateFromError(e: any) { return { err: String(e?.message ?? e) } }
  componentDidCatch(e: any) { console.error(e) }
  render() {
    if (!this.state.err) return this.props.children
    return (
      <div className="page"><div className="card">
        <h3>This page hit a problem</h3>
        <p className="small secondary">{this.state.err}</p>
        <div className="row"><button className="btn primary" onClick={() => this.setState({ err: null })}>Try again</button><button className="btn" onClick={() => useStore.getState().setRoute(['world'])}>Go to the world</button></div>
      </div></div>
    )
  }
}
