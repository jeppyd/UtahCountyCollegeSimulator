// The living map: real buildings at their real heights (tilt to see them in 3D), and everyone at the exact spot the
// simulation puts them — in their bedroom on the right floor, side by side at a dinner table, seated in the stadium.
// Walls can be made see-through to watch people inside; click a building to open it up floor by floor (a dollhouse);
// click a person to focus them. While time runs, people glide through each day's morning, afternoon, evening, late
// evening and night at the slower speeds, and the map updates once a day (at the evening) at top speed.
import { MapboxOverlay } from '@deck.gl/mapbox'
import { GeoJsonLayer, PathLayer, ScatterplotLayer, SolidPolygonLayer, TextLayer } from '@deck.gl/layers'
import { CollisionFilterExtension } from '@deck.gl/extensions'
import maplibregl from 'maplibre-gl'
import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { api, STATIC, type Universe } from '../api'
import { cssVar, hexRgb } from '../components'
import { useStore } from '../store'
import { type BuildingInside, type Buildings, type NowOccasions, type NowPerson, type Precise, type Refresh, clock, KINDS, loadBuilding, loadBuildings3d, loadCore, loadNowOccasions, loadNowPerson, loadPrecise, refreshKey, toLonLat } from './data'

const CENTER: [number, number] = [-111.672, 40.262]
// the simulated day runs hour by hour from 6 am to 6 am (the small hours belong to the night before)
export const BLOCK_NAMES = ['6 am', '7 am', '8 am', '9 am', '10 am', '11 am', '12 pm', '1 pm', '2 pm', '3 pm', '4 pm', '5 pm', '6 pm', '7 pm', '8 pm', '9 pm', '10 pm', '11 pm', '12 am', '1 am', '2 am', '3 am', '4 am', '5 am']
const collide = new CollisionFilterExtension()   // labels that would overlap give way to the more important one
const GAP = 5            // metres added between floors when a building is opened up
let geoCache: Promise<{ roads: any; cities: any }> | null = null
const loadGeo = () => (geoCache ??= Promise.all([
  fetch(api.geo('roads.json')).then(r => r.json()).catch(() => null),
  fetch(api.geo('cities.json')).then(r => r.json()).catch(() => null),
]).then(([roads, cities]) => ({ roads, cities })))
// the map underneath (the base style): plain ground with the bundled roads (works offline), OpenFreeMap street maps,
// or aerial photos. Street maps drop their own flat buildings, since ours stand on top; offline, any style falls back to
// the plain ground and the bundled roads.
export type MapStyle = 'plain' | 'streets' | 'bright' | 'satellite' | 'satellite-sharp' | 'hybrid' | 'topo'
export const MAP_STYLES: { id: MapStyle; label: string; title: string }[] = [
  { id: 'plain', label: 'Plain', title: 'Plain ground and the bundled roads, no internet needed' },
  { id: 'streets', label: 'Streets', title: 'A quiet street map: street and place names, parks, water (OpenFreeMap; clay or your theme colors)' },
  { id: 'bright', label: 'Bright streets', title: 'A colorful street map: green parks, blue water, road colors, shops and places (OpenFreeMap)' },
  { id: 'satellite', label: 'Satellite', title: 'Aerial photos of the valley (USGS National Map, public domain; sharpest up to street level)' },
  { id: 'satellite-sharp', label: 'Satellite (sharper)', title: 'Sharper aerial photos, good close in (Esri World Imagery; free for personal use)' },
  { id: 'hybrid', label: 'Satellite + labels', title: 'The sharper aerial photos with street and place names on top' },
  { id: 'topo', label: 'Topo', title: 'The USGS topographic map: contours, trails, the mountains (public domain)' },
]
export const styleOf = (o: LivingOpts): MapStyle => o.style ?? ((o.basemap ?? !STATIC) ? 'streets' : 'plain')
const BLANK = (bg: string): any => ({ version: 8, sources: {}, layers: [{ id: 'bg', type: 'background', paint: { 'background-color': bg } }] })
const IMAGERY: Record<string, { tiles: string; maxzoom: number; attribution: string }> = {
  usgs: { tiles: 'https://basemap.nationalmap.gov/arcgis/rest/services/USGSImageryOnly/MapServer/tile/{z}/{y}/{x}', maxzoom: 16,
    attribution: 'Imagery: <a href="https://www.usgs.gov/programs/national-geospatial-program/national-map">USGS The National Map</a>, USDA NAIP' },
  esri: { tiles: 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', maxzoom: 19,
    attribution: 'Imagery &copy; Esri, Maxar, Earthstar Geographics, and the GIS User Community' },
  topo: { tiles: 'https://basemap.nationalmap.gov/arcgis/rest/services/USGSTopo/MapServer/tile/{z}/{y}/{x}', maxzoom: 16,
    attribution: 'Map: <a href="https://www.usgs.gov/programs/national-geospatial-program/national-map">USGS The National Map</a>' },
}
const fetchJson = (url: string) => fetch(url).then(r => { if (!r.ok) throw new Error(String(r.status)); return r.json() })
// one tile over Provo, to learn whether the imagery can be reached before swapping the bundled roads for it
const probe = (src: string) => fetch(IMAGERY[src].tiles.replace('{z}', '12').replace('{y}', '1547').replace('{x}', '777'), { mode: 'no-cors' })
const noBuildings = (st: any) => st.layers.filter((l: any) => !l.id.startsWith('building'))
const raster = (src: string, extra: any = null): any => ({
  version: 8, ...(extra ? { glyphs: extra.glyphs, sprite: extra.sprite } : {}),
  sources: { ...(extra?.sources ?? {}), [src]: { type: 'raster', tiles: [IMAGERY[src].tiles], tileSize: 256, maxzoom: IMAGERY[src].maxzoom, attribution: IMAGERY[src].attribution } },
  layers: [{ id: 'bg', type: 'background', paint: { 'background-color': '#55594f' } }, { id: src, type: 'raster', source: src, paint: { 'raster-fade-duration': 150 } },
    ...(extra ? extra.layers : [])],
})
const styleCache: Record<string, Promise<any>> = {}
const loadStyle = (key: string): Promise<any> => (styleCache[key] ??= (() => {
  const ofm = (name: string) => fetchJson(`https://tiles.openfreemap.org/styles/${name}`)
  if (key === 'satellite') return probe('usgs').then(() => raster('usgs'))
  if (key === 'satellite-sharp') return probe('esri').then(() => raster('esri'))
  if (key === 'topo') return probe('topo').then(() => raster('topo'))
  // aerial photos with the street map's names on top (its labels and road shields only)
  if (key === 'hybrid') return Promise.all([probe('esri'), ofm('liberty')]).then(([, st]) => raster('esri', {
    ...st, layers: st.layers.filter((l: any) => l.type === 'symbol' && !l.id.startsWith('road_one_way') && !l.id.startsWith('poi_')),
  }))
  if (key === 'bright') return ofm('liberty').then(st => ({ ...st, layers: noBuildings(st) }))
  return ofm(key === 'dark' ? 'dark' : 'positron').then(st => ({ ...st, layers: noBuildings(st)
    .map((l: any) => (key === 'clay' && l.type === 'background' ? { ...l, paint: { ...l.paint, 'background-color': CLAY['--map-bg'] } } : l)) }))
})())
const BOUNDS: [number, number][] = [[-112.0, 40.0], [-111.4, 40.0], [-111.4, 40.55], [-112.0, 40.55]]
// the clay look (docs/concepts, "City · architectural clay"): warm off-white ground, one pale clay for every building,
// fine gray lines; the map keeps it whatever the app's theme
export const CLAY: Record<string, string> = {
  '--map-bg': '#ecebe6', '--map-road': '#cfccc3', '--map-bldg': '#dedbd2', '--map-clay': '#d9d3c5', '--map-edge': '#a29b8d',
  '--map-dot': '#2f5d9a', '--text-muted': '#8a8578', '--surface-1': '#fbfaf7', '--text-primary': '#2b2a27',
}
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
  basemap?: boolean         // (older saved maps) the street map on or off; style replaces it
  style?: MapStyle          // the map underneath: plain, street maps, satellite, topo
  pins?: boolean            // occasions happening now, as pins
  daylight?: boolean        // light by the time of day (evening glow, dark night with lit homes)
  look?: 'clay' | 'theme'   // the clay look (default) or the app's light/dark colors
}
export type LivingProps = {
  u: Universe
  opts: LivingOpts
  setOpts: (o: LivingOpts) => void
  /** color of person i (rgb, or rgba to set how strongly they show), given the positions frame */
  colorOf: (i: number, p: Precise) => [number, number, number] | [number, number, number, number] | null
  /** 1 = chosen (drawn strong), 0 = faint; null = everyone the same */
  chosen?: Uint8Array | null
  focus?: number | null
  onPerson?: (i: number) => void
  /** the person card was closed (the parent drops its focus on them) */
  onCardClose?: (i: number) => void
  /** an occasion was picked (a pin, a card) */
  onOccasion?: (id: number, label: string) => void
  onHover?: (h: { x: number; y: number; i: number; p: Precise } | null) => void
  /** extra controls drawn in the corner */
  children?: ReactNode
  /** the map instance, for tools layered on top (drag-a-box) */
  mapRef?: React.MutableRefObject<maplibregl.Map | null>
  /** the positions frame shown (for the parent's legend, box selection and tooltips) */
  onFrame?: (p: Precise | null) => void
}

function kindColor(kind: number, base: [number, number, number], dark: boolean, clay: boolean): [number, number, number] {
  if (clay) return base
  const k = KINDS[kind] ?? 'other'
  const tint: Record<string, string> = { campus: '--s1', school: '--s1', church: '--s7', commercial: '--s4', office: '--s4', dorm: '--s3', apartments: '--s3', civic: '--s1', sports: '--s6' }
  const t = tint[k]
  if (!t) return base
  const c = hexRgb(cssVar(t))
  const a = dark ? 0.22 : 0.16
  return [0, 1, 2].map(j => Math.round(base[j] * (1 - a) + c[j] * a)) as [number, number, number]
}

type Tone = 'day' | 'evening' | 'night'
type FloorRing = { k: number; path: number[][] }
type Busy = { id: number; name: string; lon: number; lat: number; kind: string; floors: number; n: number; h: number }
/** A color under the light of the moment: unchanged by day, warmer in the evening, dark blue at night (and a warm glow
 *  for a building with people inside at night). */
function shade(c: [number, number, number], tone: Tone, glow: boolean): [number, number, number] {
  if (tone === 'day') return c
  const mix = (a: number[], b: number[], t: number) => a.map((x, j) => Math.round(x * (1 - t) + b[j] * t)) as [number, number, number]
  if (tone === 'evening') return mix(c, [236, 170, 110], 0.14)
  if (glow) return mix(c, [255, 196, 110], 0.55)
  return mix(c, [24, 32, 52], 0.45)
}

export function LivingMap({ u, opts, setOpts, colorOf, chosen, focus, onPerson, onCardClose, onOccasion, onHover, children, mapRef, onFrame }: LivingProps) {
  const status = useStore(s => s.status)
  const theme = useStore(s => s.theme)
  const dataVersion = useStore(s => s.dataVersion)
  const look = opts.look ?? 'clay', isClay = look === 'clay'
  const dark = !isClay && (theme === 'dark' || (theme === 'auto' && window.matchMedia('(prefers-color-scheme: dark)').matches))
  const mv = (name: string) => (isClay && CLAY[name] ? CLAY[name] : cssVar(name))      // a map color in the current look
  const view3d = opts.view3d ?? true, xray = opts.xray ?? true, refresh: Refresh = opts.refresh ?? 'auto'
  const when = opts.when ?? 'now', labels = opts.labels ?? true, pins = opts.pins ?? true, style = styleOf(opts)
  const [card, setCard] = useState<number | null>(null)              // the person whose card is open
  const [follow, setFollow] = useState<number | null>(null)          // the person the camera stays on
  const [occs, setOccs] = useState<NowOccasions | null>(null)
  const [list, setList] = useState(false)                            // the 'right now' list
  const [pinKind, setPinKind] = useState<string | null>(null)       // the kind of occasion picked there (its pins stand out)
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
  const [pick, setPick] = useState<number | 'all'>('all')          // the floor picked in the opened building
  const [sep, setSep] = useState(true)                              // the opened building's floors pulled apart
  const [streets, setStreets] = useState(false)                     // a base style loaded (else the bundled roads)

  // ---- the map
  useEffect(() => {
    if (!el.current) return
    const m = new maplibregl.Map({
      container: el.current, style: BLANK(mv('--map-bg')),
      center: CENTER, zoom: 13, pitch: view3d ? 50 : 0, bearing: view3d ? -18 : 0, maxPitch: 75, attributionControl: { compact: true },
    })
    m.on('error', () => { /* tile errors (offline) are non-fatal */ })
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
  // light by the time of day shown: a warm evening, a dark night with homes lit from within
  const daylight = opts.daylight ?? true
  const shownBlock = glide ?? prec?.block ?? -1        // glide is set only while gliding
  // dusk from 5 pm (and the hour before dawn), dark from 8 pm to 6 am
  const tone: Tone = !daylight || shownBlock < 0 ? 'day' : shownBlock >= 14 ? 'night' : shownBlock >= 11 || shownBlock === 0 ? 'evening' : 'day'
  const lit = useMemo(() => {
    if (tone !== 'night' || !prec) return null
    const s2 = new Set<number>()
    for (let i = 0; i < prec.n; i++) if (prec.building[i] >= 0) s2.add(prec.building[i])
    return s2
  }, [tone, prec])
  useEffect(() => {
    const m = map.current
    if (!m || !ready) return
    let alive = true
    if (style === 'plain') { setStreets(false); m.setStyle(BLANK(mv('--map-bg')), { diff: false }); return }
    const st = style !== 'streets' ? style : isClay ? 'clay' : dark ? 'dark' : 'light'
    loadStyle(st).then(js => { if (alive && map.current) { map.current.setStyle(js, { diff: false }); setStreets(true) } })
      .catch(() => {
        delete styleCache[st]
        if (alive && map.current) { setStreets(false); map.current.setStyle(BLANK(mv('--map-bg')), { diff: false }) }
      })
    return () => { alive = false }
  }, [ready, style, dark, isClay])
  useEffect(() => {
    const m = map.current
    if (!m || !ready || streets) return
    const bg = hexRgb(mv('--map-bg'))
    const c = tone === 'day' ? bg : shade(bg, tone, false)
    const paint = () => { if (m.getLayer('bg')) m.setPaintProperty('bg', 'background-color', `rgb(${c.join(',')})`) }
    if (m.isStyleLoaded()) paint(); else m.once('styledata', paint)
  }, [theme, ready, tone, streets, isClay])
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
    if (ks.length > 30) for (const old of ks.slice(0, ks.length - 30)) delete frames.current[old]
    return frames.current[k]
  }
  useEffect(() => {
    if (gliding) return
    let alive = true
    get(when).then(p => { if (alive) { setPrec(p); setErr('') } }).catch(e => { if (alive) setErr(String(e.message ?? e)) })
    return () => { alive = false }
  }, [u, when, key, dataVersion, gliding])
  // while time runs at a slower speed: play the day just finished, hour by hour, over the time a day takes
  useEffect(() => {
    if (!gliding) { setGlide(null); return }
    let alive = true
    const timers: number[] = []
    Promise.all(BLOCK_NAMES.map((_, b) => get(b))).then(fs => {
      if (!alive) return
      const step = Math.max(120, (pace * 1000) / BLOCK_NAMES.length)
      fs.forEach((f, b) => timers.push(window.setTimeout(() => { if (alive) { setPrec(f); setGlide(b) } }, b * step)))
    }).catch(() => {})
    return () => { alive = false; timers.forEach(t => window.clearTimeout(t)) }
  }, [gliding, status?.perf?.day, u])
  useEffect(() => { onFrame?.(prec) }, [prec])
  // following someone: the camera glides to them whenever the positions change
  useEffect(() => {
    if (follow === null || !prec || !map.current || follow >= prec.n || Number.isNaN(prec.lon[follow])) return
    map.current.easeTo({ center: [prec.lon[follow], prec.lat[follow]], zoom: Math.max(map.current.getZoom(), 17.5), duration: 800 })
  }, [follow, prec])
  useEffect(() => { loadCore(u, dataVersion).then(setCore) }, [u, dataVersion])
  // occasions happening at the moment shown (pins, the 'right now' list)
  useEffect(() => {
    if (!prec) { setOccs(null); return }
    let alive = true
    loadNowOccasions(u, when !== 'now' ? when : gliding && glide !== null ? glide : 'now').then(d => { if (alive) setOccs(d) }).catch(() => {})
    return () => { alive = false }
  }, [u, prec?.day, prec?.block, when, glide])
  const pickPerson = (i: number) => { setCard(i); onPerson?.(i) }
  const flyTo = (lon: number, lat: number, z = 18) => map.current?.flyTo({ center: [lon, lat], zoom: Math.max(map.current.getZoom(), z), duration: 900 })

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
  const floorRings = useMemo(() => {
    const out: FloorRing[] = []
    if (!bld) return out
    for (const k of bCore) {
      const f = bld.floors[k], h = bld.height[k]
      if (f < 2 || h <= 0) continue
      const r = bld.rings[k]
      for (let j = 1; j < f; j++) {
        const z = (h * j) / f
        out.push({ k, path: [...r, r[0]].map(p => [p[0], p[1], z]) })
      }
    }
    return out
  }, [bld, bCore])
  const busy = useMemo(() => {
    if (!prec || !names.length) return [] as Busy[]
    const n = new Map<number, number>()
    for (let i = 0; i < prec.n; i++) { const b = prec.building[i]; if (b >= 0) n.set(b, (n.get(b) ?? 0) + 1) }
    // the buildings of one complex ("Heritage Halls Building 4", "… Building 7") are one label from afar
    const g = new Map<string, Busy>()
    for (const nm of names) {
      const k = n.get(nm.id) ?? 0
      if (!k) continue
      const key = nm.name.replace(/\s+(Building|Bldg\.?)\s+\S+$/i, '')
      const h = bld?.byId.has(nm.id) ? bld.height[bld.byId.get(nm.id)!] : 8
      const b = g.get(key)
      if (!b) { g.set(key, { ...nm, name: key, n: k, h }); continue }
      b.lon = (b.lon * b.n + nm.lon * k) / (b.n + k); b.lat = (b.lat * b.n + nm.lat * k) / (b.n + k)
      b.n += k; b.h = Math.max(b.h, h)
    }
    return [...g.values()].sort((a, b) => b.n - a.n)
  }, [prec, names, bld])
  const pIdx = useMemo(() => {
    if (!prec) return []
    // people filtered out by the coloring (alpha 0) are left off the map; strong dots are drawn last, so the faint
    // ones never cover them
    const out: number[] = []
    const key = new Float32Array(prec.n)
    for (let i = 0; i < prec.n; i++) {
      if (Number.isNaN(prec.lon[i])) continue
      const a = colorOf(i, prec)?.[3] ?? 220
      if (a === 0) continue
      key[i] = (chosen ? chosen[i] * 1000 : 0) + a
      out.push(i)
    }
    out.sort((x, y) => key[x] - key[y] || x - y)
    return out
  }, [prec, chosen, colorOf])
  const openK = open !== null && bld ? bld.byId.get(open) ?? -1 : -1
  const gap = sep ? GAP : 0
  const zOf = (i: number) => {
    const p = prec!
    return p.z[i] + (open !== null && p.building[i] === open ? p.floor[i] * gap : 0)
  }
  useEffect(() => { setPick('all') }, [open])
  const lastPrec = useRef<Precise | null>(null)                    // the frame drawn last (to tell time moving from a redraw)
  useEffect(() => {
    if (!overlay.current) return
    const timeMoved = lastPrec.current !== prec          // a new positions frame since the last draw
    const layers: any[] = []
    const muted = hexRgb(mv('--text-muted')), road = hexRgb(mv('--map-road')), base = hexRgb(mv('--map-bldg'))
    const surf = hexRgb(mv('--surface-1')), text = hexRgb(mv('--text-primary')), accent = hexRgb(cssVar('--accent'))
    const clay = hexRgb(mv('--map-clay')), edge = hexRgb(mv('--map-edge'))
    // evening and night over the street map: a tint (the plain ground is shaded directly)
    if (streets && tone !== 'day') layers.push(new SolidPolygonLayer({
      id: 'tint', data: [BOUNDS], getPolygon: (d: any) => d, getFillColor: tone === 'night' ? [12, 18, 40, dark ? 90 : 120] : [236, 150, 80, 28],
      parameters: { depthWriteEnabled: false },
    }))
    if (geo?.cities && !streets) layers.push(new GeoJsonLayer({ id: 'cities', data: geo.cities, stroked: true, filled: false, getLineColor: [...muted, 80], lineWidthMinPixels: 1 }))
    if (geo?.roads && !streets) layers.push(new GeoJsonLayer({ id: 'roads', data: geo.roads, stroked: true, filled: false, getLineColor: [...road, 255], getLineWidth: (f: any) => (f.properties.c === 1 ? 2 : 0.9), lineWidthUnits: 'pixels' }))
    if (bld && zoom >= 13.5) layers.push(new SolidPolygonLayer({
      id: 'bflat', data: bFlat, getPolygon: (k: number) => bld.rings[k], extruded: false,
      getFillColor: dark ? [...clay, streets ? 120 : 150] : [...base, streets ? 160 : 230], pickable: false, parameters: { depthWriteEnabled: false },
    }))
    if (bld) {
      layers.push(new SolidPolygonLayer({
        id: 'b3d', data: bCore, getPolygon: (k: number) => bld.rings[k], extruded: view3d, wireframe: view3d && zoom >= 14.5,
        getLineColor: (k: number) => (k === openK ? [0, 0, 0, 0] : [...edge, view3d && xray ? 150 : 200]),
        getElevation: (k: number) => (k === openK ? 0 : bld.height[k]),
        getFillColor: (k: number) => {
          if (k === openK) return [0, 0, 0, 0]
          const c = shade(kindColor(bld.kind[k], clay, dark, isClay), tone, lit?.has(bld.ids[k]) ?? false)
          return [c[0], c[1], c[2], view3d && xray ? (tone === 'night' && lit?.has(bld.ids[k]) ? 170 : 120) : 235]
        },
        material: { ambient: 0.6, diffuse: 0.55, shininess: 6, specularColor: [40, 40, 40] },
        parameters: view3d && xray ? { depthWriteEnabled: false } : {},
        pickable: true, autoHighlight: true, highlightColor: [...accent, 70],
        onClick: (info: any) => { if (info.object !== undefined && info.object !== null) openBuilding(bld.ids[info.object]) },
        updateTriggers: { getFillColor: [view3d, xray, dark, openK, tone, lit], getElevation: [openK], getLineColor: [openK, view3d, xray, dark] },
      }))
      // each storey drawn as a thin line round the walls, so floors read without opening the building
      if (view3d && zoom >= 15.5 && floorRings.length) layers.push(new PathLayer({
        id: 'storeys', data: floorRings, getPath: (d: FloorRing) => d.path as any, widthUnits: 'pixels', getWidth: 1,
        getColor: (d: FloorRing) => (d.k === openK ? [0, 0, 0, 0] : [...edge, xray ? 80 : dark ? 120 : 150]),
        updateTriggers: { getColor: [openK, dark, xray] },
      }))
    }
    // the opened building: its floors, apartments and bedrooms
    if (inside) {
      const ll = (p: [number, number]) => toLonLat(inside, p)
      const floors = Array.from({ length: Math.max(1, inside.floors) }, (_, f) => f)
      const ring = openK >= 0 && bld ? bld.rings[openK] : null
      if (ring) layers.push(new SolidPolygonLayer({
        id: 'slabs', data: floors, getPolygon: (f: number) => ring.map(p => [p[0], p[1], f * (inside.storey_m + gap)]) as any, extruded: false,
        getFillColor: (f: number) => (pick === f ? [...accent, 110] : [...surf, pick === 'all' ? 200 : 90]), parameters: { depthWriteEnabled: false },
        updateTriggers: { getFillColor: [pick], getPolygon: [gap] },
      }))
      const rects: { path: number[][]; kind: string; n: number; beds: number }[] = []
      for (const h of inside.homes) {
        const zf = (z: number) => z + h.floor * gap
        rects.push({ path: [...h.shape.corners, h.shape.corners[0]].map(c => [...ll(c), zf(h.shape.z) + 0.05]), kind: 'home', n: 0, beds: h.beds })
        for (const r of h.rooms) {
          if (!r.shape) continue
          const zr = r.shape.z + h.floor * gap
          rects.push({ path: [...r.shape.corners, r.shape.corners[0]].map(c => [...ll(c), zr + 0.06]), kind: 'room', n: r.people.length, beds: r.beds })
        }
      }
      // bedrooms tinted by who sleeps there (empty rooms plain; a crowded room warmer)
      const accent2 = hexRgb(cssVar('--s1')), warm = hexRgb(cssVar('--s2'))
      layers.push(new SolidPolygonLayer({
        id: 'room-fill', data: rects.filter(r => r.kind === 'room'), getPolygon: (d: any) => d.path.slice(0, 4) as any, extruded: false,
        getFillColor: (d: any) => (d.n === 0 ? [...muted, 25] : d.n > d.beds ? [...warm, 90] : [...accent2, 30 + 25 * Math.min(d.n, 3)]),
        parameters: { depthWriteEnabled: false },
      }))
      if (ring) layers.push(new TextLayer({
        id: 'floor-labels', data: floors, getText: (f: number) => (f === 0 ? 'Ground' : `Floor ${f + 1}`),
        getPosition: (f: number) => [ring[0][0], ring[0][1], f * (inside.storey_m + gap) + 0.4], getSize: 12, getColor: [...text, 230],
        fontFamily: 'system-ui, sans-serif', fontWeight: 650, billboard: true, background: true, getBackgroundColor: [...surf, 220], backgroundPadding: [4, 2],
        getTextAnchor: 'end', getPixelOffset: [-8, 0], parameters: { depthCompare: 'always' },
      }))
      layers.push(new PathLayer({
        id: 'rooms', data: rects, getPath: (d: any) => d.path, widthUnits: 'pixels',
        getWidth: (d: any) => (d.kind === 'home' ? 1.8 : 1), getColor: (d: any) => (d.kind === 'home' ? [...text, 200] : [...muted, d.n > d.beds ? 255 : 170]),
      }))
      if (zoom >= 18.5) layers.push(new TextLayer({
        id: 'unit-labels', data: inside.homes.filter(h => h.label), getText: (h: any) => h.label.replace(/^Bldg \S+ /, ''),
        getPosition: (h: any) => { const c = h.living.corners; return [...ll([(c[0][0] + c[2][0]) / 2, (c[0][1] + c[2][1]) / 2]), h.shape.z + h.floor * gap + 0.3] },
        getSize: 11, getColor: [...text, 220], fontFamily: 'system-ui, sans-serif', billboard: true, background: true, getBackgroundColor: [...surf, 200],
        backgroundPadding: [3, 1],
      }))
    }
    if (pins && occs) {
      const pinRgb = text
      const big = occs.occasions.filter(o => o.n >= (zoom >= 16 ? 2 : zoom >= 14.5 ? 4 : 12))
      layers.push(new ScatterplotLayer({
        id: 'pins', data: big, getPosition: (o: any) => [o.lon, o.lat, 0.2], getRadius: (o: any) => 4 + 2.2 * Math.sqrt(o.n), radiusUnits: 'pixels',
        filled: true, getFillColor: (o: any) => [...pinRgb, pinKind && o.label !== pinKind ? 12 : 50], stroked: true,
        getLineColor: (o: any) => (pinKind && o.label !== pinKind ? [...pinRgb, 60] : [...(pinKind ? accent : pinRgb), 230]), lineWidthMinPixels: 2,
        updateTriggers: { getFillColor: [pinKind, isClay, dark], getLineColor: [pinKind, isClay, dark] },
        pickable: true, parameters: { depthCompare: 'always' },
        onClick: (info: any) => { if (info.object) onOccasion?.(info.object.id, info.object.name ?? info.object.label) },
        onHover: (info: any) => onHover?.(null),
      }))
      if (labels) layers.push(new TextLayer({
        id: 'pin-labels', data: big.filter(o => (!pinKind || o.label === pinKind) && o.n >= (zoom >= 16.5 ? 2 : 8)).slice(0, 300),
        getText: (o: any) => `${o.name ?? o.label} · ${o.n}`, getPosition: (o: any) => [o.lon, o.lat, 0.3],
        getPixelOffset: (o: any) => [0, -(8 + 2.2 * Math.sqrt(o.n))], getSize: 11, getColor: [...text, 230], fontFamily: 'system-ui, sans-serif', fontWeight: 600,
        billboard: true, outlineWidth: 2, outlineColor: [...surf, 240], fontSettings: { sdf: true, fontSize: 64, buffer: 6 }, characterSet: 'auto',
        parameters: { depthCompare: 'always' }, getTextAnchor: 'middle', getAlignmentBaseline: 'bottom',
        collisionEnabled: true, getCollisionPriority: (o: any) => o.n, extensions: [collide], collisionTestProps: { sizeScale: 1.4 },
      }))
    }
    if (prec) {
      layers.push(new ScatterplotLayer({
        id: 'people', data: pIdx, getPosition: (i: number) => [prec.lon[i], prec.lat[i], zOf(i)],
        billboard: true, radiusUnits: 'meters', getRadius: (i: number) => (chosen && chosen[i] ? 0.75 : 0.6), radiusMinPixels: 1.8, radiusMaxPixels: 10,
        getFillColor: (i: number) => { const c = colorOf(i, prec) ?? muted; return [c[0], c[1], c[2], chosen ? (chosen[i] ? Math.max(c[3] ?? 245, 120) : 30) : c[3] ?? 220] },
        stroked: true, getLineColor: (i: number) => [...surf, Math.min(220, colorOf(i, prec)?.[3] ?? 220)], lineWidthMinPixels: 0.5, lineWidthMaxPixels: 1.2,
        parameters: view3d && xray ? { depthCompare: 'always' } : {},
        pickable: true, autoHighlight: true, highlightColor: [255, 255, 255, 230],
        // people glide only when time moved them; a change of coloring or selection redraws them in place
        transitions: timeMoved ? { getPosition: { duration: gliding ? Math.max(200, (pace * 1000) / 5 * 0.85) : 700 } } : {},
        updateTriggers: { getFillColor: [colorOf, chosen, prec], getLineColor: [colorOf, prec], getRadius: [chosen], getPosition: [prec, open] },
        onHover: (info: any) => onHover?.(info.object === undefined || info.object === null ? null : { x: info.x, y: info.y, i: info.object, p: prec }),
        onClick: (info: any) => { if (info.object !== undefined && info.object !== null) pickPerson(info.object) },
      }))
      if (focus !== null && focus !== undefined && focus < prec.n && !Number.isNaN(prec.lon[focus])) {
        layers.push(new ScatterplotLayer({
          id: 'focus', data: [focus], getPosition: (i: number) => [prec.lon[i], prec.lat[i], zOf(i)], billboard: true, getRadius: 11, radiusUnits: 'pixels',
          filled: false, stroked: true, getLineColor: [...text, 255], lineWidthMinPixels: 2, parameters: { depthCompare: 'always' },
          updateTriggers: { getPosition: [prec, open] },
        }))
      }
    }
    // from afar: the busiest named places, with how many people are inside right now
    if (labels && busy.length && zoom < 15.3 && zoom >= 13) layers.push(new TextLayer({
      id: 'busy', data: busy.filter(b => b.n >= (zoom >= 14 ? 15 : 60)).slice(0, zoom >= 14 ? 40 : 12), getText: (b: Busy) => `${b.name} · ${b.n}`,
      getPosition: (b: Busy) => [b.lon, b.lat, view3d ? b.h + 2 : 0], getSize: 11.5, getColor: [...text, 225], fontFamily: 'system-ui, sans-serif', fontWeight: 600,
      billboard: true, outlineWidth: 2, outlineColor: [...surf, 235], fontSettings: { sdf: true, fontSize: 64, buffer: 6 }, characterSet: 'auto',
      collisionEnabled: true, getCollisionPriority: (b: Busy) => b.n, extensions: [collide], collisionTestProps: { sizeScale: 1.6 },
      parameters: { depthCompare: 'always' },
    }))
    if (labels && names.length && zoom >= 15.3) {
      const big = names.filter(nm => zoom >= 16.6 || ['campus', 'dorm', 'apartments', 'sports', 'church', 'civic'].includes(nm.kind))
      layers.push(new TextLayer({
        id: 'names', data: big, getText: (d: Named) => d.name, getPosition: (d: Named) => [d.lon, d.lat, view3d ? (bld && bld.byId.has(d.id) ? bld.height[bld.byId.get(d.id)!] + 2 : 8) : 0],
        getSize: 11.5, getColor: [...text, 210], fontFamily: 'system-ui, sans-serif', fontWeight: 600, billboard: true,
        outlineWidth: 2, outlineColor: [...surf, 230], fontSettings: { sdf: true, fontSize: 64, buffer: 6 }, characterSet: 'auto',
        collisionEnabled: true, getCollisionPriority: (d: Named) => d.floors, extensions: [collide], collisionTestProps: { sizeScale: 1.4 },
        parameters: { depthCompare: 'always' },
      }))
    }
    overlay.current.setProps({ layers })
    lastPrec.current = prec
  }, [tone, lit, occs, pins, pinKind, geo, bld, bCore, bFlat, floorRings, prec, pIdx, colorOf, chosen, focus, view3d, xray, dark, inside, openK, zoom, labels, names, gliding, pace, streets, busy, pick, gap, isClay])

  const shown = gliding && glide !== null ? `${BLOCK_NAMES[glide]} (playing the day as time runs)` : prec ? (prec.block >= 0 && prec.block < BLOCK_NAMES.length ? BLOCK_NAMES[prec.block] : '') : ''
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
        <button className={`btn small ${list ? 'primary' : ''}`} onClick={() => setList(!list)} disabled={!occs} title="Everything happening at this moment: dates, dinners, parties, games…">Right now{occs ? ` · ${occs.occasions.length}` : ''}</button>
        <label className="inline small lm-chk"><input type="checkbox" checked={pins} onChange={e => setOpts({ ...opts, pins: e.target.checked })} />pins</label>
        <label className="inline small lm-chk" title="Place and building names (from afar, the busiest places with how many people are there)"><input type="checkbox" checked={labels} onChange={e => setOpts({ ...opts, labels: e.target.checked })} />labels</label>
        <select value={style} onChange={e => setOpts({ ...opts, style: e.target.value as MapStyle })} title="The map underneath: plain ground, street maps, satellite photos or topo (all but plain need the internet)">
          {MAP_STYLES.map(s => <option key={s.id} value={s.id} title={s.title}>{s.label}</option>)}
        </select>
        <label className="inline small lm-chk" title="The clay look: warm ground and pale clay buildings, whatever the app's theme (off: the app's light or dark colors)"><input type="checkbox" checked={isClay} onChange={e => setOpts({ ...opts, look: e.target.checked ? 'clay' : 'theme' })} />clay</label>
        <label className="inline small lm-chk" title="Light by the time of day: a warm evening, a dark night with homes lit from within"><input type="checkbox" checked={daylight} onChange={e => setOpts({ ...opts, daylight: e.target.checked })} />light</label>
        {children}
      </div>
      {open !== null && <BuildingCard d={inside} onClose={() => setOpen(null)} onPerson={pickPerson} floor={pick} setFloor={setPick} sep={sep} setSep={setSep} />}
      {card !== null && <NowCard i={card} u={u} k={`${prec?.day}:${prec?.block}`} onClose={() => { setCard(null); setFollow(null); onCardClose?.(card) }} onPerson={pickPerson} onOccasion={onOccasion}
        following={follow === card} onFollow={() => setFollow(follow === card ? null : card)}
        onBuilding={b => openBuilding(b)} />}
      {list && occs && <RightNow d={occs} kind={pinKind} setKind={setPinKind} onClose={() => { setList(false); setPinKind(null) }} onPick={o => { flyTo(o.lon, o.lat); onOccasion?.(o.id, o.name ?? o.label) }} />}
      <div className="lm-when">{prec ? <>{new Date(prec.date + 'T12:00:00').toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric' })}{shown ? ` · ${shown}` : ''}{running && refresh !== 'live' && !gliding ? ' · updates ' + (refreshKey(refresh, status).startsWith('d:') ? 'once a day' : 'when paused') : ''}</> : null}</div>
      {err && !prec && <div className="lm-over small">{err.includes('404') ? 'Run time forward a little and people appear.' : err}</div>}
      {!prec && !err && <div className="lm-over small muted">Placing people…</div>}
    </div>
  )
}

/** The opened building: its floors, the homes on each, their bedrooms and who sleeps in each; who is inside now. */
function BuildingCard({ d, onClose, onPerson, floor, setFloor, sep, setSep }: {
  d: BuildingInside | null; onClose: () => void; onPerson?: (i: number) => void
  floor: number | 'all'; setFloor: (f: number | 'all') => void; sep: boolean; setSep: (b: boolean) => void
}) {
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
        {fl.length > 1 && <div className="row" style={{ margin: '8px 0 4px', gap: 8, alignItems: 'center' }}>
          <div className="seg small-seg" title="Pick a floor: it lights up on the map">
            <button className={floor === 'all' ? 'on' : ''} onClick={() => setFloor('all')}>All</button>
            {fl.map(f => <button key={f} className={floor === f ? 'on' : ''} onClick={() => setFloor(f)}>{f + 1}</button>)}
          </div>
          <label className="inline small" title="Pull the floors apart to see each one, or stack them as they stand"><input type="checkbox" checked={sep} onChange={e => setSep(e.target.checked)} />separate floors</label>
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

/** One person at this moment: what they are doing and where, the occasion and why they came, who they're with and
 *  how they know them, and what's on their mind (every line from the model's own state). */
const ordinal = (n: number) => `${n}${n % 100 >= 11 && n % 100 <= 13 ? 'th' : ['th', 'st', 'nd', 'rd'][n % 10] ?? 'th'}`
const pct = (p: number) => `${Math.round(100 * p)}%`
const TRIP: Record<string, string> = { walk: 'Walked', bike: 'Biked', car: 'Drove', transit: 'Took the bus', ride: 'Got a ride' }

/** How they were invited, what pulled them there and what held them back (the decision's own factors), how they got
 *  there. */
function WhyCame({ me, onPerson }: { me: NonNullable<NonNullable<NowPerson['occasion']>['me']>; onPerson: (i: number) => void }) {
  const close = me.prob !== null && me.prob > 0.35 && me.prob < 0.65
  return (
    <div className="lm-why small">
      {me.inviter && <div>{me.role === 'walked in' ? 'Walked in' : <>Invited by <button className="lm-link" onClick={() => onPerson(me.inviter!.id)}>{me.inviter.name}</button>{me.channel ? ` (${me.channel})` : ''}</>}</div>}
      {me.for.length > 0 && <div><span className="lm-pro">Why they came:</span> {me.for.join(', ')}</div>}
      {me.against.length > 0 && <div><span className="lm-con">Almost didn't:</span> {me.against.join(', ')}{close ? ` — a close call (${pct(me.prob!)} likely)` : ''}</div>}
      {(me.trip_minutes !== null || me.arrive) && <div className="muted">{me.trip_mode ? `${TRIP[me.trip_mode] ?? `Came by ${me.trip_mode}`}${me.trip_minutes ? ` ${me.trip_minutes} min` : ''}` : ''}{me.ride ? `, a ride from ${me.ride}` : ''}{me.arrive ? ` · arrived ${me.arrive}${me.late_minutes && me.late_minutes >= 5 ? ` (${me.late_minutes} min late)` : ''}` : ''}</div>}
    </div>
  )
}

function NowCard({ i, u, k, onClose, onPerson, onOccasion, onBuilding, following, onFollow }: { i: number; u: Universe; k: string; onClose: () => void
  onPerson: (i: number) => void; onOccasion?: (id: number, label: string) => void; onBuilding: (b: number) => void
  following: boolean; onFollow: () => void }) {
  const [d, setD] = useState<NowPerson | null>(null)
  const [err, setErr] = useState('')
  useEffect(() => {
    let alive = true
    setErr('')
    loadNowPerson(i, u).then(x => { if (alive) setD(x) }).catch(e => { if (alive) setErr(String(e.message ?? e)) })
    return () => { alive = false }
  }, [i, u, k])
  return (
    <div className="lm-card lm-now">
      <div className="lm-card-h">
        <div><b>{d?.name ?? '…'}</b><small>{d?.headline ?? ''}</small></div>
        <button className="bx-icon" onClick={onClose} aria-label="Close">✕</button>
      </div>
      <div className="lm-card-b">
        {err && <p className="small">{err}</p>}
        {d && <>
          <div className="lm-now-doing">{d.present ? d.doing[0].toUpperCase() + d.doing.slice(1) : 'Away from Provo'}{d.block >= 0 && d.block < BLOCK_NAMES.length ? <small> · {BLOCK_NAMES[d.block]}</small> : null}</div>
          {d.place.words && <div className="small">{d.place.words}{d.place.building !== null && <> · <button className="lm-link" onClick={() => onBuilding(d.place.building!)}>open the building</button></>}</div>}
          {d.occasion && (
            <div className="lm-occ">
              <button className="lm-link" onClick={() => onOccasion?.(d.occasion!.id, d.occasion!.name ?? d.occasion!.kind_label)}><b>{d.occasion.name ?? d.occasion.kind_label}</b></button>
              <small> · {d.occasion.time} · {d.occasion.n_people} {d.occasion.n_people === 1 ? 'person' : 'people'}</small>
              {d.occasion.organizer && <div className="small muted">{d.occasion.organizer.id === d.id ? 'They organized it' : <>Organized by <button className="lm-link" onClick={() => onPerson(d.occasion!.organizer!.id)}>{d.occasion.organizer.name}</button></>}{d.occasion.how ? ` (${d.occasion.how})` : ''}</div>}
              {d.date_info && <div className="small" style={{ marginTop: 3 }}>With <button className="lm-link" onClick={() => onPerson(d.date_info!.with.id)}>{d.date_info.with.name}</button>
                {' · '}{d.date_info.nth === 1 ? 'their first date' : `their ${ordinal(d.date_info.nth)} date`}{d.date_info.asked_by ? ` · ${d.date_info.asked_by}` : ''} · {d.date_info.status}</div>}
              {d.occasion.me && d.occasion.me.role !== 'organizer' && <WhyCame me={d.occasion.me} onPerson={onPerson} />}
            </div>
          )}
          {d.n_with > 0 && <><div className="bx-h">With {d.n_with} {d.n_with === 1 ? 'person' : 'people'}{d.n_with > 1 ? `, ${d.n_known} they know` : ''}</div>
            <div className="lm-with">{d.with.map(w => <button key={w.id} onClick={() => onPerson(w.id)}><span>{w.name}</span><small>{w.tie}</small></button>)}
              {d.n_with > d.with.length && <span className="small muted">and {d.n_with - d.with.length} more</span>}</div></>}
          {d.mind.length > 0 && <><div className="bx-h">On their mind</div>
            <ul className="lm-mind">{d.mind.map((m, k2) => <li key={k2} title={`From: ${m.from}`}>{m.text}</li>)}</ul></>}
          <div className="row" style={{ gap: 6, marginTop: 8 }}>
            <button className={`btn small ${following ? 'primary' : ''}`} onClick={onFollow} title="Keep the map on this person as time runs">{following ? 'Following' : 'Follow'}</button>
          </div>
          <p className="bx-note">Every line comes from the simulation's own state for this person at this moment; nothing here is written by an AI.</p>
        </>}
      </div>
    </div>
  )
}

/** Everything happening at this moment, by kind; click one to go there. */
function RightNow({ d, kind, setKind, onClose, onPick }: { d: NowOccasions; kind: string | null; setKind: (k: string | null) => void; onClose: () => void; onPick: (o: NowOccasions['occasions'][number]) => void }) {
  const rows = kind ? d.occasions.filter(o => o.label === kind) : d.occasions
  return (
    <div className="lm-card lm-list">
      <div className="lm-card-h">
        <div><b>Right now</b><small>{new Date(d.date + 'T12:00:00').toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric' })}{d.block >= 0 && d.block < BLOCK_NAMES.length ? ` · ${BLOCK_NAMES[d.block]}` : ''} · {d.occasions.length} occasions, {d.occasions.reduce((s, o) => s + o.n, 0).toLocaleString()} people</small></div>
        <button className="bx-icon" onClick={onClose} aria-label="Close">✕</button>
      </div>
      <div className="lm-card-b">
        <div className="lm-kinds">
          <button className={kind === null ? 'on' : ''} onClick={() => setKind(null)}>Everything</button>
          {d.counts.map(c => <button key={c.label} className={kind === c.label ? 'on' : ''} onClick={() => setKind(kind === c.label ? null : c.label)} title="Show only these on the map">{c.label}<small> {c.occasions} · {c.people} people</small></button>)}
        </div>
        {rows.slice(0, 150).map(o => (
          <button key={o.id} className="lm-occ-row" onClick={() => onPick(o)}>
            <span>{o.name ?? o.label}</span><small>{clock(o.start)}–{clock(o.start + o.dur)} · {o.n} {o.n === 1 ? 'person' : 'people'}</small>
          </button>
        ))}
      </div>
    </div>
  )
}
