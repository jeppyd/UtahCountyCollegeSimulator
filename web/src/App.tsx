import { Component, ReactNode, useEffect, useRef, useState } from 'react'
import { api, STATIC } from './api'
import Bench from './bench/Bench'
import { G } from './game'
import { Hud, timeCtl } from './hud'
import { CLASSIC, NAV, TOP } from './nav'
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
import Valley from './views/valley/Valley'
import { ScenePlayer } from './views/valley/Scene'
import { MakeItHappen } from './views/valley/MakeItHappen'
import { WorldSetupPage } from './views/WorldSetup'
import { AiSetup } from './kit/AiSetup'

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
  useKeys()

  if (err) return <div className="empty">Could not reach the simulator: {err}<br />Start it with <span className="kbd">python -m ucsim.api.server</span></div>
  if (!registry || !status) return <div className="boot"><div className="boot-orbit"><i /><i /><i /></div>Waking up Provo and Orem…</div>
  if (!STATIC && !status.has_world) return <WorldSetupPage />

  const alias: Record<string, string> = { home: 'valley', workbench: 'bench', overview: 'trends', dashboard: 'trends', lab: 'whatif' }
  const view = alias[route[0]] ?? route[0] ?? 'valley'
  let body
  switch (view) {
    case 'valley': body = STATIC ? <World /> : <Valley />; break
    case 'bench': body = STATIC ? <World /> : <Bench />; break
    case 'world': body = <World />; break
    case 'guide': body = <Guide section={route[1]} />; break
    case 'trends': body = <Overview />; break
    case 'map': body = <MapView initial={route[1]} />; break
    case 'people': body = STATIC ? <People /> : <Valley />; break
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
    default: body = STATIC ? <World /> : <Valley />
  }
  const active = view === 'person' ? 'people' : view === 'network' ? 'relationships' : view
  const div = status.divergence?.any_state_diff
  return (
    <div className={`game v6 ${view === 'map' ? 'full' : ''} ${view === 'bench' ? 'on-bench' : ''} ${view === 'valley' ? 'on-valley' : ''}`}>
      <Hud />
      <TimeRibbon />
      <TopNav active={active} hasAlt={!!status.has_alt} div={div} />
      <main className="main"><ViewBoundary key={view}>{body}</ViewBoundary></main>
      <AiSetup />
      <NewsWatcher />
      <RecapWatcher />
      <Toasts />
      <Palette />
      <ChangeDrawer />
      <ScenePlayer />
      <MakeItHappen />
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

/** The app's top navigation: the valley (home), the workbench, the What-if, every other page under "More", and the guide. */
function TopNav({ active, hasAlt, div }: { active: string; hasAlt: boolean; div: number | null | undefined }) {
  const setRoute = useStore(s => s.setRoute)
  const [open, setOpen] = useState(false)
  const box = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!open) return
    const h = (e: MouseEvent) => { if (box.current && !box.current.contains(e.target as Node)) setOpen(false) }
    const k = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpen(false) }
    document.addEventListener('mousedown', h); document.addEventListener('keydown', k)
    return () => { document.removeEventListener('mousedown', h); document.removeEventListener('keydown', k) }
  }, [open])
  const all = NAV.flatMap(g => g.items)
  const top = TOP.map(id => all.find(i => i.id === id)!).filter(i => i && !(STATIC && i.id === 'bench'))
  const classic = CLASSIC.flatMap(g => g.items).find(i => i.id === active)
  const help = NAV[2].items
  const go = (id: string) => { setRoute([id]); setOpen(false) }
  return (
    <nav className="topnav" aria-label="Places">
      {top.map(i => (
        <button key={i.id} title={i.hint} className={`tn ${active === i.id ? 'active' : ''}`} onClick={() => go(i.id)} style={{ ['--wc' as any]: `var(${i.color ?? '--accent'})` }}>
          <span className="tn-icon">{G[i.icon]}</span><span>{i.label}</span>
          {i.id === 'whatif' && hasAlt && <span className="wn-badge tabular" title="Lives that differ between the worlds">{div !== undefined && div !== null ? `${(100 * div).toFixed(div < 0.1 ? 1 : 0)}%` : '•'}</span>}
        </button>
      ))}
      <div className="tn-menu" ref={box}>
        <button className={`tn ${classic ? 'active classic' : ''}`} onClick={() => setOpen(!open)} aria-expanded={open} aria-haspopup="menu"
          title="Every other page: the overview, people, relationships, places, events, every field, and the research desk">
          <span className="tn-icon">{G[classic?.icon ?? 'explore']}</span><span>{classic ? `More · ${classic.label}` : 'More'}</span><span className="tn-chev">{G.chevron}</span>
        </button>
        {open && (
          <div className="tn-pop" role="menu">
            {CLASSIC.map(g => (
              <div key={g.label} className="tn-group">
                <div className="tn-g">{g.label}</div>
                {g.items.map(i => (
                  <button key={i.id} role="menuitem" className={`tn-item ${active === i.id ? 'on' : ''}`} onClick={() => go(i.id)}>
                    <span className="tn-icon sm">{G[i.icon]}</span><span className="tn-t"><b>{i.label}</b><small>{i.hint}</small></span>
                  </button>
                ))}
              </div>
            ))}
          </div>
        )}
      </div>
      <span className="spacer" />
      {help.map(i => (
        <button key={i.id} title={i.hint} className={`tn ${active === i.id ? 'active' : ''}`} onClick={() => go(i.id)}>
          <span className="tn-icon">{G[i.icon]}</span><span>{i.label}</span>
        </button>
      ))}
    </nav>
  )
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
