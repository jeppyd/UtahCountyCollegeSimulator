// The living map: real buildings at their real heights (tilt to see them in 3D), and everyone at the exact spot the
// simulation puts them — in their bedroom on the right floor, side by side at a dinner table, seated in the stadium.
// Walls can be made see-through to watch people inside; click a building to open it up floor by floor (a dollhouse);
// click a person to focus them. While time runs, people glide through each day's morning, afternoon, evening, late
// evening and night at the slower speeds, and the map updates once a day (at the evening) at top speed.
import { MapboxOverlay } from '@deck.gl/mapbox'
import { GeoJsonLayer, PathLayer, ScatterplotLayer, SolidPolygonLayer, TextLayer } from '@deck.gl/layers'
import maplibregl from 'maplibre-gl'
import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { api, type Universe } from '../api'
import { cssVar, hexRgb } from '../components'
import { useStore } from '../store'
import { type BuildingInside, type Buildings, type Precise, type Refresh, KINDS, loadBuilding, loadBuildings3d, loadCore, loadPrecise, refreshKey, toLonLat } from './data'

const CENTER: [number, number] = [-111.672, 40.262]
export const BLOCK_NAMES = ['Morning', 'Afternoon', 'Evening', 'Late evening', 'Night']
const GAP = 5            // metres added between floors when a building is opened up
let geoCache: Promise<{ roads: any; cities: any }> | null = null
const loadGeo = () => (geoCache ??= Promise.all([
  fetch(api.geo('roads.json')).then(r => r.json()).catch(() => null),
  fetch(api.geo('cities.json')).then(r => r.json()).catch(() => null),
]).then(([roads, cities]) => ({ roads, cities })))
type Named = { id: number; name: string; lon: number; lat: number; kind: string; floors: number }
let namesCache: Promise<Named[]> | null = null
const loadNames = () => (namesCache ??= fetch(api.geo('building_names.json')).then(r => r.json())
  .then(d => d.rows.map((r: any[]) => ({ id: r[0], name: r[1], lon: r[2], lat: r[3], kind: r[4], floors: r[5] }))).catch(() => []))

export type LivingOpts = {
  view3d?: boolean          // tilted, buildings standing at their heights
  xray?: boolean            // walls see-through, people inside visible
  refresh?: Refresh
  when?: 'now' | number     // the latest part of the day, or part 0–4 of the last full day
  labels?: boolean
  basemap?: boolean
}
export type LivingProps = {
  u: Universe
  opts: LivingOpts
  setOpts: (o: LivingOpts) => void
  /** color of person i (rgb), given the positions frame */
  colorOf: (i: number, p: Precise) => [number, number, number] | null
  /** 1 = chosen (drawn strong), 0 = faint; null = everyone the same */
  chosen?: Uint8Array | null
  focus?: number | null
  onPerson?: (i: number) => void
  onHover?: (h: { x: number; y: number; i: number; p: Precise } | null) => void
  /** extra controls drawn in the corner */
  children?: ReactNode
  /** the map instance, for tools layered on top (drag-a-box) */
  mapRef?: React.MutableRefObject<maplibregl.Map | null>
  /** the positions frame shown (for the parent's legend, box selection and tooltips) */
  onFrame?: (p: Precise | null) => void
}

function kindColor(kind: number, base: [number, number, number], dark: boolean): [number, number, number] {
  const k = KINDS[kind] ?? 'other'
  const tint: Record<string, string> = { campus: '--s1', school: '--s1', church: '--s7', commercial: '--s4', office: '--s4', dorm: '--s3', apartments: '--s3', civic: '--s1', sports: '--s6' }
  const t = tint[k]
  if (!t) return base
  const c = hexRgb(cssVar(t))
  const a = dark ? 0.22 : 0.16
  return [0, 1, 2].map(j => Math.round(base[j] * (1 - a) + c[j] * a)) as [number, number, number]
}

export function LivingMap({ u, opts, setOpts, colorOf, chosen, focus, onPerson, onHover, children, mapRef, onFrame }: LivingProps) {
  const status = useStore(s => s.status)
  const theme = useStore(s => s.theme)
  const dataVersion = useStore(s => s.dataVersion)
  const dark = theme === 'dark' || (theme === 'auto' && window.matchMedia('(prefers-color-scheme: dark)').matches)
  const view3d = opts.view3d ?? true, xray = opts.xray ?? true, refresh: Refresh = opts.refresh ?? 'auto'
  const when = opts.when ?? 'now', labels = opts.labels ?? true
  const el = useRef<HTMLDivElement>(null)
  const map = useRef<maplibregl.Map | null>(null)
  const overlay = useRef<MapboxOverlay | null>(null)
  const [ready, setReady] = useState(false)
  const [zoom, setZoom] = useState(13)
  const [geo, setGeo] = useState<{ roads: any; cities: any } | null>(null)
  const [bld, setBld] = useState<Buildings | null>(null)
  const [names, setNames] = useState<Named[]>([])
  const [prec, setPrec] = useState<Precise | null>(null)
  const [err, setErr] = useState('')
  const [open, setOpen] = useState<number | null>(null)            // building opened up (building id)
  const [inside, setInside] = useState<BuildingInside | null>(null)
  const [glide, setGlide] = useState<number | null>(null)           // part of the day being played while time runs
  const [core, setCore] = useState<Set<number> | null>(null)       // buildings people use (standing); the rest flat

  // ---- the map
  useEffect(() => {
    if (!el.current) return
    const m = new maplibregl.Map({
      container: el.current, style: { version: 8, sources: {}, layers: [{ id: 'bg', type: 'background', paint: { 'background-color': cssVar('--map-bg') } }] } as any,
      center: CENTER, zoom: 13, pitch: view3d ? 50 : 0, bearing: view3d ? -18 : 0, maxPitch: 75, attributionControl: false,
    })
    m.addControl(new maplibregl.NavigationControl({ showCompass: true, visualizePitch: true }), 'top-right')
    const ov = new MapboxOverlay({ interleaved: false, layers: [] })
    m.addControl(ov as any)
    map.current = m; overlay.current = ov
    if (mapRef) mapRef.current = m
    m.on('load', () => setReady(true))
    ;(window as any).__ucsimMap = m; (window as any).__ucsimDeck = ov     // for scripted screenshots and debugging
    m.on('zoomend', () => setZoom(m.getZoom()))
    const ro = new ResizeObserver(() => m.resize())
    ro.observe(el.current)
    loadGeo().then(setGeo)
    loadBuildings3d().then(setBld).catch(e => setErr(String(e.message ?? e)))
    loadNames().then(setNames)
    return () => { ro.disconnect(); m.remove(); map.current = null; overlay.current = null; if (mapRef) mapRef.current = null }
  }, [])
  useEffect(() => { if (ready) map.current?.setPaintProperty('bg', 'background-color', cssVar('--map-bg')) }, [theme, ready])
  useEffect(() => {
    const m = map.current
    if (!m || !ready) return
    m.easeTo(view3d ? { pitch: 55, bearing: m.getBearing() || -18, duration: 700 } : { pitch: 0, bearing: 0, duration: 700 })
  }, [view3d, ready])

  // ---- positions: the latest part of the day, a chosen part of the last full day, or gliding through it
  const key = refreshKey(refresh, status)
  const running = status?.job?.state === 'running'
  const pace = status?.job?.pace ?? 0
  const gliding = running && pace > 0 && (refresh === 'auto' || refresh === 'live') && when === 'now'
  const frames = useRef<Record<string, Promise<Precise>>>({})
  const get = (b: 'now' | number) => {
    const k = `${u}:${b}:${b === 'now' ? key : status?.perf?.day ?? status?.day}:${dataVersion}`
    frames.current[k] ??= loadPrecise(u, b)
    const ks = Object.keys(frames.current)
    if (ks.length > 14) for (const old of ks.slice(0, ks.length - 14)) delete frames.current[old]
    return frames.current[k]
  }
  useEffect(() => {
    if (gliding) return
    let alive = true
    get(when).then(p => { if (alive) { setPrec(p); setErr('') } }).catch(e => { if (alive) setErr(String(e.message ?? e)) })
    return () => { alive = false }
  }, [u, when, key, dataVersion, gliding])
  // while time runs at a slower speed: play the day just finished, part by part, over the time a day takes
  useEffect(() => {
    if (!gliding) { setGlide(null); return }
    let alive = true
    const timers: number[] = []
    Promise.all([0, 1, 2, 3, 4].map(b => get(b))).then(fs => {
      if (!alive) return
      const step = Math.max(250, (pace * 1000) / 5)
      fs.forEach((f, b) => timers.push(window.setTimeout(() => { if (alive) { setPrec(f); setGlide(b) } }, b * step)))
    }).catch(() => {})
    return () => { alive = false; timers.forEach(t => window.clearTimeout(t)) }
  }, [gliding, status?.perf?.day, u])
  useEffect(() => { onFrame?.(prec) }, [prec])
  useEffect(() => { loadCore(u, dataVersion).then(setCore) }, [u, dataVersion])

  // ---- a building opened up
  useEffect(() => {
    if (open === null) { setInside(null); return }
    let alive = true
    loadBuilding(open, u).then(d => { if (alive) setInside(d) }).catch(() => { if (alive) setInside(null) })
    return () => { alive = false }
  }, [open, u, prec?.day, prec?.block])
  const openBuilding = (b: number | null) => {
    setOpen(b)
    if (b === null || !bld || !map.current) return
    const k = bld.byId.get(b)
    if (k === undefined) return
    const r = bld.rings[k]
    const c = r.reduce((a, p) => [a[0] + p[0] / r.length, a[1] + p[1] / r.length], [0, 0])
    map.current.flyTo({ center: c as [number, number], zoom: Math.max(map.current.getZoom(), 18.2), pitch: 60, duration: 900 })
    if (!view3d) setOpts({ ...opts, view3d: true })
  }

  // ---- layers
  // buildings people use stand in 3D and can be clicked; the rest are flat outlines (far cheaper to draw)
  const [bCore, bFlat] = useMemo(() => {
    if (!bld) return [[], []] as number[][]
    const a: number[] = [], b: number[] = []
    for (let k = 0; k < bld.n; k++) ((core?.has(bld.ids[k]) ?? false) ? a : b).push(k)
    return [a, b]
  }, [bld, core])
  const pIdx = useMemo(() => {
    if (!prec) return []
    const out: number[] = []
    for (let i = 0; i < prec.n; i++) if (!Number.isNaN(prec.lon[i])) out.push(i)
    if (chosen) out.sort((a, b) => chosen[a] - chosen[b])
    return out
  }, [prec, chosen])
  const openK = open !== null && bld ? bld.byId.get(open) ?? -1 : -1
  const zOf = (i: number) => {
    const p = prec!
    return p.z[i] + (open !== null && p.building[i] === open ? p.floor[i] * GAP : 0)
  }
  useEffect(() => {
    if (!overlay.current) return
    const layers: any[] = []
    const muted = hexRgb(cssVar('--text-muted')), road = hexRgb(cssVar('--map-road')), base = hexRgb(cssVar('--map-bldg'))
    const surf = hexRgb(cssVar('--surface-1')), text = hexRgb(cssVar('--text-primary')), accent = hexRgb(cssVar('--accent'))
    if (geo?.cities) layers.push(new GeoJsonLayer({ id: 'cities', data: geo.cities, stroked: true, filled: false, getLineColor: [...muted, 80], lineWidthMinPixels: 1 }))
    if (geo?.roads) layers.push(new GeoJsonLayer({ id: 'roads', data: geo.roads, stroked: true, filled: false, getLineColor: [...road, 255], getLineWidth: (f: any) => (f.properties.c === 1 ? 2 : 0.9), lineWidthUnits: 'pixels' }))
    if (bld && zoom >= 13.5) layers.push(new SolidPolygonLayer({
      id: 'bflat', data: bFlat, getPolygon: (k: number) => bld.rings[k], extruded: false,
      getFillColor: [...base, dark ? 150 : 170], pickable: false, parameters: { depthWriteEnabled: false },
    }))
    if (bld) {
      layers.push(new SolidPolygonLayer({
        id: 'b3d', data: bCore, getPolygon: (k: number) => bld.rings[k], extruded: view3d, wireframe: false,
        getElevation: (k: number) => (k === openK ? 0 : bld.height[k]),
        getFillColor: (k: number) => {
          if (k === openK) return [0, 0, 0, 0]
          const c = kindColor(bld.kind[k], base, dark)
          return [c[0], c[1], c[2], view3d && xray ? 120 : 235]
        },
        material: { ambient: 0.6, diffuse: 0.55, shininess: 6, specularColor: [40, 40, 40] },
        parameters: view3d && xray ? { depthWriteEnabled: false } : {},
        pickable: true, autoHighlight: true, highlightColor: [...accent, 70],
        onClick: (info: any) => { if (info.object !== undefined && info.object !== null) openBuilding(bld.ids[info.object]) },
        updateTriggers: { getFillColor: [view3d, xray, dark, openK], getElevation: [openK] },
      }))
    }
    // the opened building: its floors, apartments and bedrooms
    if (inside) {
      const ll = (p: [number, number]) => toLonLat(inside, p)
      const floors = Array.from({ length: Math.max(1, inside.floors) }, (_, f) => f)
      const ring = openK >= 0 && bld ? bld.rings[openK] : null
      if (ring) layers.push(new SolidPolygonLayer({
        id: 'slabs', data: floors, getPolygon: (f: number) => ring.map(p => [p[0], p[1], f * (inside.storey_m + GAP)]) as any, extruded: false,
        getFillColor: [...surf, 200], parameters: { depthWriteEnabled: false },
      }))
      const rects: { path: number[][]; kind: string; n: number; beds: number }[] = []
      for (const h of inside.homes) {
        const zf = (z: number) => z + h.floor * GAP
        rects.push({ path: [...h.shape.corners, h.shape.corners[0]].map(c => [...ll(c), zf(h.shape.z) + 0.05]), kind: 'home', n: 0, beds: h.beds })
        for (const r of h.rooms) {
          if (!r.shape) continue
          const zr = r.shape.z + h.floor * GAP
          rects.push({ path: [...r.shape.corners, r.shape.corners[0]].map(c => [...ll(c), zr + 0.06]), kind: 'room', n: r.people.length, beds: r.beds })
        }
      }
      layers.push(new PathLayer({
        id: 'rooms', data: rects, getPath: (d: any) => d.path, widthUnits: 'pixels',
        getWidth: (d: any) => (d.kind === 'home' ? 1.8 : 1), getColor: (d: any) => (d.kind === 'home' ? [...text, 200] : [...muted, d.n > d.beds ? 255 : 170]),
      }))
      if (zoom >= 18.5) layers.push(new TextLayer({
        id: 'unit-labels', data: inside.homes.filter(h => h.label), getText: (h: any) => h.label.replace(/^Bldg \S+ /, ''),
        getPosition: (h: any) => { const c = h.living.corners; return [...ll([(c[0][0] + c[2][0]) / 2, (c[0][1] + c[2][1]) / 2]), h.shape.z + h.floor * GAP + 0.3] },
        getSize: 11, getColor: [...text, 220], fontFamily: 'system-ui, sans-serif', billboard: true, background: true, getBackgroundColor: [...surf, 200],
        backgroundPadding: [3, 1],
      }))
    }
    if (prec) {
      layers.push(new ScatterplotLayer({
        id: 'people', data: pIdx, getPosition: (i: number) => [prec.lon[i], prec.lat[i], zOf(i)],
        billboard: true, radiusUnits: 'meters', getRadius: (i: number) => (chosen && chosen[i] ? 0.75 : 0.6), radiusMinPixels: 1.8, radiusMaxPixels: 10,
        getFillColor: (i: number) => { const c = colorOf(i, prec) ?? muted; return [c[0], c[1], c[2], chosen ? (chosen[i] ? 245 : 30) : 220] },
        stroked: true, getLineColor: [...surf, 220], lineWidthMinPixels: 0.5, lineWidthMaxPixels: 1.2,
        parameters: view3d && xray ? { depthCompare: 'always' } : {},
        pickable: true, autoHighlight: true, highlightColor: [255, 255, 255, 230],
        transitions: { getPosition: { duration: gliding ? Math.max(200, (pace * 1000) / 5 * 0.85) : 700 } },
        updateTriggers: { getFillColor: [colorOf, chosen, prec], getRadius: [chosen], getPosition: [prec, open] },
        onHover: (info: any) => onHover?.(info.object === undefined || info.object === null ? null : { x: info.x, y: info.y, i: info.object, p: prec }),
        onClick: (info: any) => { if (info.object !== undefined && info.object !== null) onPerson?.(info.object) },
      }))
      if (focus !== null && focus !== undefined && focus < prec.n && !Number.isNaN(prec.lon[focus])) {
        layers.push(new ScatterplotLayer({
          id: 'focus', data: [focus], getPosition: (i: number) => [prec.lon[i], prec.lat[i], zOf(i)], billboard: true, getRadius: 11, radiusUnits: 'pixels',
          filled: false, stroked: true, getLineColor: [...text, 255], lineWidthMinPixels: 2, parameters: { depthCompare: 'always' },
          updateTriggers: { getPosition: [prec, open] },
        }))
      }
    }
    if (labels && names.length && zoom >= 15.3) {
      const big = names.filter(nm => zoom >= 16.6 || ['campus', 'dorm', 'apartments', 'sports', 'church', 'civic'].includes(nm.kind))
      layers.push(new TextLayer({
        id: 'names', data: big, getText: (d: Named) => d.name, getPosition: (d: Named) => [d.lon, d.lat, view3d ? (bld && bld.byId.has(d.id) ? bld.height[bld.byId.get(d.id)!] + 2 : 8) : 0],
        getSize: 11.5, getColor: [...text, 210], fontFamily: 'system-ui, sans-serif', fontWeight: 600, billboard: true,
        outlineWidth: 2, outlineColor: [...surf, 230], fontSettings: { sdf: true, fontSize: 64, buffer: 6 }, characterSet: 'auto',
        collisionEnabled: true, getCollisionPriority: (d: Named) => d.floors, extensions: [],
        parameters: { depthCompare: 'always' },
      }))
    }
    overlay.current.setProps({ layers })
  }, [geo, bld, bCore, bFlat, prec, pIdx, colorOf, chosen, focus, view3d, xray, dark, inside, openK, zoom, labels, names, gliding, pace])

  const shown = gliding && glide !== null ? `${BLOCK_NAMES[glide]} (playing the day as time runs)` : prec ? (prec.block >= 0 && prec.block < 5 ? BLOCK_NAMES[prec.block] : '') : ''
  return (
    <div className="lm">
      <div className="lm-map" ref={el} />
      <div className="lm-bar">
        <div className="seg">
          <button className={!view3d ? 'on' : ''} onClick={() => setOpts({ ...opts, view3d: false })} title="Flat, from above">2D</button>
          <button className={view3d ? 'on' : ''} onClick={() => setOpts({ ...opts, view3d: true })} title="Tilted, buildings at their real heights (drag with the right mouse button or Ctrl to turn and tilt)">3D</button>
        </div>
        {view3d && <button className={`btn small ${xray ? 'primary' : ''}`} onClick={() => setOpts({ ...opts, xray: !xray })} title="See-through walls: watch people inside buildings">See inside</button>}
        <select value={String(when)} onChange={e => setOpts({ ...opts, when: e.target.value === 'now' ? 'now' : Number(e.target.value) })} title="Which moment to show">
          <option value="now">Now</option>
          {BLOCK_NAMES.map((b, k) => <option key={b} value={k}>{b} of the last day</option>)}
        </select>
        {children}
      </div>
      {open !== null && <BuildingCard d={inside} onClose={() => setOpen(null)} onPerson={onPerson} />}
      <div className="lm-when">{prec ? <>{new Date(prec.date + 'T12:00:00').toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric' })}{shown ? ` · ${shown}` : ''}{running && refresh !== 'live' && !gliding ? ' · updates ' + (refreshKey(refresh, status).startsWith('d:') ? 'once a day' : 'when paused') : ''}</> : null}</div>
      {err && !prec && <div className="lm-over small">{err.includes('404') ? 'Run time forward a little and people appear.' : err}</div>}
      {!prec && !err && <div className="lm-over small muted">Placing people…</div>}
    </div>
  )
}

/** The opened building: its floors, the homes on each, their bedrooms and who sleeps in each; who is inside now. */
function BuildingCard({ d, onClose, onPerson }: { d: BuildingInside | null; onClose: () => void; onPerson?: (i: number) => void }) {
  const [floor, setFloor] = useState<number | 'all'>('all')
  if (!d) return <div className="lm-card"><div className="lm-card-h"><b>Opening the building…</b><button className="bx-icon" onClick={onClose} aria-label="Close">✕</button></div></div>
  const byFloor = new Map<number, typeof d.homes>()
  for (const h of d.homes) byFloor.set(h.floor, [...(byFloor.get(h.floor) ?? []), h])
  const fl = [...byFloor.keys()].sort((a, b) => a - b)
  const shownHomes = floor === 'all' ? d.homes : byFloor.get(floor) ?? []
  const people = d.homes.reduce((s, h) => s + h.rooms.reduce((t, r) => t + r.people.length, 0), 0)
  const ord = (f: number) => (f === 0 ? 'Ground floor' : `Floor ${f + 1}`)
  return (
    <div className="lm-card">
      <div className="lm-card-h">
        <div><b>{d.name ?? `A ${d.kind === 'other' ? 'building' : d.kind}`}</b>
          <small>{d.floors} floor{d.floors === 1 ? '' : 's'} · {Math.round(d.area_m2 * 10.764).toLocaleString()} sq ft footprint{d.homes.length ? ` · ${d.homes.length} home${d.homes.length === 1 ? '' : 's'}, ${people} living here` : ''}</small></div>
        <button className="bx-icon" onClick={onClose} aria-label="Close" title="Close the building">✕</button>
      </div>
      <div className="lm-card-b">
        {d.n_inside_now > 0 && <><div className="bx-h">Inside right now ({d.n_inside_now})</div>
          <div className="lm-chips">{d.inside_now.slice(0, 40).map(p => <button key={p.id} onClick={() => onPerson?.(p.id)} title={`${ord(p.floor)} · ${p.doing.replace(/_/g, ' ')}`}>{p.name}<small> {p.doing.replace(/_/g, ' ')}</small></button>)}
            {d.n_inside_now > 40 && <span className="muted small">and {d.n_inside_now - 40} more</span>}</div></>}
        {fl.length > 1 && <div className="seg small-seg" style={{ margin: '8px 0 4px' }}>
          <button className={floor === 'all' ? 'on' : ''} onClick={() => setFloor('all')}>All</button>
          {fl.map(f => <button key={f} className={floor === f ? 'on' : ''} onClick={() => setFloor(f)}>{f + 1}</button>)}
        </div>}
        {shownHomes.length === 0 && d.homes.length === 0 && <p className="small muted">Nobody lives here (it isn't one of the simulated homes).</p>}
        {shownHomes.slice(0, 120).map(h => (
          <div key={h.unit} className="lm-home">
            <div className="lm-home-h"><b>{h.label || h.kind}</b><small>{ord(h.floor)} · {h.kind} · {h.rooms.length} bedroom{h.rooms.length === 1 ? '' : 's'}, {h.beds} bed{h.beds === 1 ? '' : 's'}</small></div>
            {h.rooms.map((r, k) => (
              <div key={r.room} className={`lm-room ${r.people.length > r.beds ? 'crowded' : ''}`}>
                <span className="lm-room-n">Room {k + 1}<small>{r.beds === 1 ? 'private' : `${r.beds} beds`}</small></span>
                <span className="lm-room-p">{r.people.length ? r.people.map(p => <button key={p.id} onClick={() => onPerson?.(p.id)}>{p.name}</button>) : <i className="muted">empty</i>}</span>
              </div>
            ))}
          </div>
        ))}
        {shownHomes.length > 120 && <p className="small muted">{shownHomes.length - 120} more homes; pick a floor.</p>}
      </div>
    </div>
  )
}
