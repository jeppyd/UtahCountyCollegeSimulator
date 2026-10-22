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
import { catRgb } from '../kit/Bits'
import { type BuildingInside, type Buildings, type NowOccasions, type NowPerson, type Precise, type Refresh, clock, KINDS, loadBuilding, loadBuildings3d, loadCore, loadNowOccasions, loadNowPerson, loadPrecise, refreshKey, toLonLat } from './data'

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
  pins?: boolean            // occasions happening now, as pins
  daylight?: boolean        // light by the time of day (evening glow, dark night with lit homes)
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

function kindColor(kind: number, base: [number, number, number], dark: boolean): [number, number, number] {
  const k = KINDS[kind] ?? 'other'
  const tint: Record<string, string> = { campus: '--s1', school: '--s1', church: '--s7', commercial: '--s4', office: '--s4', dorm: '--s3', apartments: '--s3', civic: '--s1', sports: '--s6' }
  const t = tint[k]
  if (!t) return base
  const c = hexRgb(cssVar(t))
  const a = dark ? 0.22 : 0.16
  return [0, 1, 2].map(j => Math.round(base[j] * (1 - a) + c[j] * a)) as [number, number, number]
}

type Tone = 'day' | 'evening' | 'night'
/** A color under the light of the moment: unchanged by day, warmer in the evening, dark blue at night (and a warm glow
 *  for a building with people inside at night). */
function shade(c: [number, number, number], tone: Tone, glow: boolean): [number, number, number] {
  if (tone === 'day') return c
  const mix = (a: number[], b: number[], t: number) => a.map((x, j) => Math.round(x * (1 - t) + b[j] * t)) as [number, number, number]
  if (tone === 'evening') return mix(c, [236, 170, 110], 0.14)
  if (glow) return mix(c, [255, 196, 110], 0.55)
  return mix(c, [24, 32, 52], 0.62)
}

export function LivingMap({ u, opts, setOpts, colorOf, chosen, focus, onPerson, onOccasion, onHover, children, mapRef, onFrame }: LivingProps) {
  const status = useStore(s => s.status)
  const theme = useStore(s => s.theme)
  const dataVersion = useStore(s => s.dataVersion)
  const dark = theme === 'dark' || (theme === 'auto' && window.matchMedia('(prefers-color-scheme: dark)').matches)
  const view3d = opts.view3d ?? true, xray = opts.xray ?? true, refresh: Refresh = opts.refresh ?? 'auto'
  const when = opts.when ?? 'now', labels = opts.labels ?? true, pins = opts.pins ?? true
  const [card, setCard] = useState<number | null>(null)              // the person whose card is open
  const [follow, setFollow] = useState<number | null>(null)          // the person the camera stays on
  const [occs, setOccs] = useState<NowOccasions | null>(null)
  const [list, setList] = useState(false)                            // the 'right now' list
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
  // light by the time of day shown: a warm evening, a dark night with homes lit from within
  const daylight = opts.daylight ?? true
  const shownBlock = glide ?? prec?.block ?? -1        // glide is set only while gliding
  const tone: Tone = !daylight ? 'day' : shownBlock === 2 ? 'evening' : shownBlock >= 3 ? 'night' : 'day'
  const lit = useMemo(() => {
    if (tone !== 'night' || !prec) return null
    const s2 = new Set<number>()
    for (let i = 0; i < prec.n; i++) if (prec.building[i] >= 0) s2.add(prec.building[i])
    return s2
  }, [tone, prec])
  useEffect(() => {
    if (!ready) return
    const bg = hexRgb(cssVar('--map-bg'))
    const c = tone === 'day' ? bg : shade(bg, tone, false)
    map.current?.setPaintProperty('bg', 'background-color', `rgb(${c.join(',')})`)
  }, [theme, ready, tone])
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
          const c = shade(kindColor(bld.kind[k], base, dark), tone, lit?.has(bld.ids[k]) ?? false)
          return [c[0], c[1], c[2], view3d && xray ? (tone === 'night' && lit?.has(bld.ids[k]) ? 170 : 120) : 235]
        },
        material: { ambient: 0.6, diffuse: 0.55, shininess: 6, specularColor: [40, 40, 40] },
        parameters: view3d && xray ? { depthWriteEnabled: false } : {},
        pickable: true, autoHighlight: true, highlightColor: [...accent, 70],
        onClick: (info: any) => { if (info.object !== undefined && info.object !== null) openBuilding(bld.ids[info.object]) },
        updateTriggers: { getFillColor: [view3d, xray, dark, openK, tone, lit], getElevation: [openK] },
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
      // bedrooms tinted by who sleeps there (empty rooms plain; a crowded room warmer)
      const accent2 = hexRgb(cssVar('--s1')), warm = hexRgb(cssVar('--s2'))
      layers.push(new SolidPolygonLayer({
        id: 'room-fill', data: rects.filter(r => r.kind === 'room'), getPolygon: (d: any) => d.path.slice(0, 4) as any, extruded: false,
        getFillColor: (d: any) => (d.n === 0 ? [...muted, 25] : d.n > d.beds ? [...warm, 90] : [...accent2, 30 + 25 * Math.min(d.n, 3)]),
        parameters: { depthWriteEnabled: false },
      }))
      if (ring) layers.push(new TextLayer({
        id: 'floor-labels', data: floors, getText: (f: number) => (f === 0 ? 'Ground' : `Floor ${f + 1}`),
        getPosition: (f: number) => [ring[0][0], ring[0][1], f * (inside.storey_m + GAP) + 0.4], getSize: 12, getColor: [...text, 230],
        fontFamily: 'system-ui, sans-serif', fontWeight: 650, billboard: true, background: true, getBackgroundColor: [...surf, 220], backgroundPadding: [4, 2],
        getTextAnchor: 'end', getPixelOffset: [-8, 0], parameters: { depthCompare: 'always' },
      }))
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
    if (pins && occs) {
      const big = occs.occasions.filter(o => o.n >= (zoom >= 16 ? 2 : zoom >= 14.5 ? 4 : 12))
      layers.push(new ScatterplotLayer({
        id: 'pins', data: big, getPosition: (o: any) => [o.lon, o.lat, 0.2], getRadius: (o: any) => 4 + 2.2 * Math.sqrt(o.n), radiusUnits: 'pixels',
        filled: true, getFillColor: (o: any) => [...catRgb(o.category), 50], stroked: true, getLineColor: (o: any) => [...catRgb(o.category), 230], lineWidthMinPixels: 2,
        pickable: true, parameters: { depthCompare: 'always' },
        onClick: (info: any) => { if (info.object) onOccasion?.(info.object.id, info.object.name ?? info.object.label) },
        onHover: (info: any) => onHover?.(null),
      }))
      layers.push(new TextLayer({
        id: 'pin-labels', data: big.filter(o => o.n >= (zoom >= 16.5 ? 2 : 8)).slice(0, 300),
        getText: (o: any) => `${o.name ?? o.label} · ${o.n}`, getPosition: (o: any) => [o.lon, o.lat, 0.3],
        getPixelOffset: (o: any) => [0, -(8 + 2.2 * Math.sqrt(o.n))], getSize: 11, getColor: [...text, 230], fontFamily: 'system-ui, sans-serif', fontWeight: 600,
        billboard: true, outlineWidth: 2, outlineColor: [...surf, 240], fontSettings: { sdf: true, fontSize: 64, buffer: 6 }, characterSet: 'auto',
        parameters: { depthCompare: 'always' }, getTextAnchor: 'middle', getAlignmentBaseline: 'bottom',
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
  }, [tone, lit, occs, pins, geo, bld, bCore, bFlat, prec, pIdx, colorOf, chosen, focus, view3d, xray, dark, inside, openK, zoom, labels, names, gliding, pace])

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
        <button className={`btn small ${list ? 'primary' : ''}`} onClick={() => setList(!list)} disabled={!occs} title="Everything happening at this moment: dates, dinners, parties, games…">Right now{occs ? ` · ${occs.occasions.length}` : ''}</button>
        <label className="inline small lm-chk"><input type="checkbox" checked={pins} onChange={e => setOpts({ ...opts, pins: e.target.checked })} />pins</label>
        <label className="inline small lm-chk" title="Light by the time of day: a warm evening, a dark night with homes lit from within"><input type="checkbox" checked={daylight} onChange={e => setOpts({ ...opts, daylight: e.target.checked })} />light</label>
        {children}
      </div>
      {open !== null && <BuildingCard d={inside} onClose={() => setOpen(null)} onPerson={pickPerson} />}
      {card !== null && <NowCard i={card} u={u} k={`${prec?.day}:${prec?.block}`} onClose={() => { setCard(null); setFollow(null) }} onPerson={pickPerson} onOccasion={onOccasion}
        following={follow === card} onFollow={() => setFollow(follow === card ? null : card)}
        onBuilding={b => openBuilding(b)} />}
      {list && occs && <RightNow d={occs} onClose={() => setList(false)} onPick={o => { flyTo(o.lon, o.lat); onOccasion?.(o.id, o.name ?? o.label) }} />}
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
          <div className="lm-now-doing">{d.present ? d.doing[0].toUpperCase() + d.doing.slice(1) : 'Away from Provo'}{d.block >= 0 && d.block < 5 ? <small> · {BLOCK_NAMES[d.block].toLowerCase()}</small> : null}</div>
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
function RightNow({ d, onClose, onPick }: { d: NowOccasions; onClose: () => void; onPick: (o: NowOccasions['occasions'][number]) => void }) {
  const [kind, setKind] = useState<string | null>(null)
  const rows = kind ? d.occasions.filter(o => o.label === kind) : d.occasions
  return (
    <div className="lm-card lm-list">
      <div className="lm-card-h">
        <div><b>Right now</b><small>{new Date(d.date + 'T12:00:00').toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric' })}{d.block >= 0 && d.block < 5 ? ` · ${BLOCK_NAMES[d.block].toLowerCase()}` : ''} · {d.occasions.length} occasions, {d.occasions.reduce((s, o) => s + o.n, 0).toLocaleString()} people</small></div>
        <button className="bx-icon" onClick={onClose} aria-label="Close">✕</button>
      </div>
      <div className="lm-card-b">
        <div className="lm-kinds">
          <button className={kind === null ? 'on' : ''} onClick={() => setKind(null)}>Everything</button>
          {d.counts.map(c => <button key={c.label} className={kind === c.label ? 'on' : ''} onClick={() => setKind(c.label)}><i className="bx-catdot" style={{ background: `rgb(${catRgb(c.category).join(',')})` }} />{c.label}<small> {c.occasions} · {c.people} people</small></button>)}
        </div>
        {rows.slice(0, 150).map(o => (
          <button key={o.id} className="lm-occ-row" onClick={() => onPick(o)}>
            <i className="bx-catdot" style={{ background: `rgb(${catRgb(o.category).join(',')})` }} />
            <span>{o.name ?? o.label}</span><small>{clock(o.start)}–{clock(o.start + o.dur)} · {o.n} {o.n === 1 ? 'person' : 'people'}</small>
          </button>
        ))}
      </div>
    </div>
  )
}
