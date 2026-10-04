import { MapboxOverlay } from '@deck.gl/mapbox'
import { GeoJsonLayer, LineLayer, PolygonLayer, ScatterplotLayer, SolidPolygonLayer } from '@deck.gl/layers'
import maplibregl from 'maplibre-gl'
import { useEffect, useMemo, useRef, useState } from 'react'
import { cohortMask, fmt, quantile } from '../analysis'
import { api, Column, fetchBytes, STATIC } from '../api'
import { CohortBar, cssVar, divColor, hexRgb, seqColor, VarPicker } from '../components'
import { nameOf } from '../names'
import { loadColumns, useStore } from '../store'

const BLANK_STYLE = (bg: string): any => ({ version: 8, sources: {}, layers: [{ id: 'bg', type: 'background', paint: { 'background-color': bg } }] })
const CENTER: [number, number] = [-111.672, 40.262]

let buildingsCache: Promise<any[]> | null = null
function loadBuildings(): Promise<any[]> {
  if (!buildingsCache) buildingsCache = fetchBytes(api.geo('buildings.bin')).then(buf => {
    const dv = new DataView(buf)
    const n = dv.getInt32(0, true)
    const lon0 = dv.getFloat64(4, true), lat0 = dv.getFloat64(12, true)
    let off = 20
    const out: any[] = new Array(n)
    for (let k = 0; k < n; k++) {
      const m = dv.getInt32(off, true); off += 4
      const ring = new Array(m)
      for (let j = 0; j < m; j++) { ring[j] = [lon0 + dv.getInt32(off, true) / 1e5, lat0 + dv.getInt32(off + 4, true) / 1e5]; off += 8 }
      out[k] = ring
    }
    return out
  })
  return buildingsCache
}

type Mode = 'people' | 'homes' | 'complexes' | 'wards' | 'day' | 'months'
const MODE_LABEL: Record<Mode, string> = { people: 'Right now', homes: 'Homes', complexes: 'Complexes', wards: 'Wards', day: '▶ A day', months: '▶ Over months' }
// measures exported for the read-only snapshot's months replay (keep in sync with scripts/export_static.py)
const STATIC_FRAME_VARS = ['rel_status', 'activity', 'living', 'affiliation', 'loneliness', 'faith_belief', 'outsider']
const DAY_LABELS = ['8 am · classes and work', '1 pm · afternoon', '6 pm · evenings out', 'Night · home']
const MODE_HINT: Record<Mode, string> = {
  day: 'Replays the last full simulated day: watch everyone glide from home to class and work, out for the evening, and home again. Colors show what each person is doing.',
  months: 'Replays the weeks so far, one snapshot every two weeks: homes colored by the measure you pick. Watch couples move in together, faith shift, loneliness spread or ease.',
  people: 'Each dot is a person, where they are at this hour (class, work, church, a date…). Step the clock by an hour to watch them move.',
  homes: 'Each dot is a person at home. Color by any measure to see neighborhoods differ; your group is highlighted.',
  complexes: 'Each circle is an apartment complex or dorm, sized by residents and colored by their average. Click one to open it.',
  wards: 'Each circle is a congregation (ward) at its meetinghouse, colored by its members\' average. Click one to open it.',
}

export default function MapView({ initial }: { initial?: string }) {
  const { universe, dataVersion, cohort, status, setRoute, theme } = useStore()
  const el = useRef<HTMLDivElement>(null)
  const map = useRef<maplibregl.Map | null>(null)
  const overlay = useRef<MapboxOverlay | null>(null)
  // optional deep link "mode:variable", e.g. complexes:loneliness or homes:rent_burden
  const [m0, v0] = (initial ?? '').split(':')
  const MODES: Mode[] = ['people', 'homes', 'complexes', 'wards', 'day', 'months']
  const [mode, setMode] = useState<Mode>((MODES.includes(m0 as Mode) ? m0 : 'people') as Mode)
  const [colorBy, setColorBy] = useState(v0 || 'activity_now')
  useEffect(() => { if (m0 && MODES.includes(m0 as Mode)) setMode(m0 as Mode); if (v0) setColorBy(v0); if (m0 === 'day' || m0 === 'months') setPlaying(true) }, [initial])
  // ---- playback state ("a day" and "over months")
  const [pb, setPb] = useState<any>(null)
  const [pbErr, setPbErr] = useState('')
  const [t, setT] = useState(0)
  const [playing, setPlaying] = useState(false)
  const [speed, setSpeed] = useState(1)
  const [pbVar, setPbVar] = useState('rel_status')
  const [tracked, setTracked] = useState<{ cat: string[]; num: string[] }>({ cat: [], num: [] })
  const playback = mode === 'day' || mode === 'months'
  const [diff, setDiff] = useState(false)
  const [basemap, setBasemap] = useState(!STATIC)
  const [showRoads, setShowRoads] = useState(true)
  const [showBldg, setShowBldg] = useState(true)
  const [showVenues, setShowVenues] = useState(false)
  const [showNbhd, setShowNbhd] = useState(false)
  const [nbhds, setNbhds] = useState<any[]>([])
  const [highlight, setHighlight] = useState(true)
  const [buildings, setBuildings] = useState<any[] | null>(null)
  const [roads, setRoads] = useState<any>(null)
  const [cities, setCities] = useState<any>(null)
  const [venues, setVenues] = useState<any[]>([])
  const [pts, setPts] = useState<any>(null)
  const [places, setPlaces] = useState<any[]>([])
  const [hover, setHover] = useState<any>(null)
  const [selected, setSelected] = useState<number | null>(null)
  const [ego, setEgo] = useState<any[]>([])
  const reg = useStore(s => s.registry)!
  const dark = theme === 'dark' || (theme === 'auto' && window.matchMedia('(prefers-color-scheme: dark)').matches)

  // ---- map init
  useEffect(() => {
    if (!el.current) return
    const style = basemap ? `https://tiles.openfreemap.org/styles/${dark ? 'dark' : 'positron'}` : BLANK_STYLE(cssVar('--map-bg'))
    const m = new maplibregl.Map({ container: el.current, style, center: CENTER, zoom: 12.3, attributionControl: { compact: true } })
    m.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-right')
    m.on('error', () => { /* tile errors (offline) are non-fatal */ })
    const ov = new MapboxOverlay({ interleaved: false, layers: [] })
    m.addControl(ov as any)
    map.current = m
    overlay.current = ov
    return () => { m.remove(); map.current = null }
  }, [basemap, dark])

  // ---- static geography
  useEffect(() => {
    loadBuildings().then(setBuildings).catch(() => {})
    fetch(api.geo('roads.json')).then(r => r.json()).then(setRoads).catch(() => {})
    fetch(api.geo('cities.json')).then(r => r.json()).then(setCities).catch(() => {})
    fetch(api.geo('neighborhoods.json')).then(r => r.json()).then((d: any[]) => setNbhds(d.flatMap(n => n.rings.map((ring: any) => ({ name: n.name, city: n.city, ring }))))).catch(() => {})
    api.venues().then(setVenues).catch(() => {})
  }, [])

  // ---- agent data
  useEffect(() => {
    let alive = true
    ;(async () => {
      if (mode === 'people' || mode === 'homes') {
        const pos = await api.positions(universe, mode === 'people' ? 'now' : 'home')
        const varName = colorBy
        const cols = await loadColumns(['sex', varName], universe)
        let other: Column | null = null
        if (diff && status.has_alt) other = (await loadColumns([varName], universe === 'base' ? 'alt' : 'base'))[varName]
        const { mask } = await cohortMask(cohort, universe)
        if (!alive) return
        setPts({ lon: pos.lon.data, lat: pos.lat.data, act: pos.activity_now, col: varName === 'activity_now' ? pos.activity_now : cols[varName], other, sex: cols.sex, mask, varName })
      } else if (mode === 'complexes' || mode === 'wards') {
        const v = colorBy === 'activity_now' ? 'loneliness' : colorBy
        const rows = mode === 'complexes' ? await api.complexes(v, universe) : await api.wards(v, universe)
        if (alive) setPlaces(rows)
      }
    })().catch(e => console.warn(e))
    return () => { alive = false }
  }, [mode, colorBy, universe, dataVersion, JSON.stringify(cohort), diff])

  useEffect(() => {
    if (!playback) { setPb(null); setPlaying(false); return }
    let alive = true
    setPbErr('')
    ;(async () => {
      if (mode === 'day') {
        const f = await api.dayFrames(universe)
        const { mask } = await cohortMask(cohort, universe)
        if (alive) { setPb({ kind: 'day', f, K: 4, mask, date: f.day?.meta?.date }); setT(0) }
      } else {
        const info = await api.historyInfo(universe)
        if (alive) setTracked({ cat: info.categorical, num: info.numeric })
        const f = await api.historyFrames(pbVar, universe)
        const K = f.days.data.length
        const { mask } = await cohortMask(cohort, universe)
        let lo = 0, hi = 1
        const cats = f.v0?.categories ?? (f.v0?.bool ? ['no', 'yes'] : null)
        if (!cats) {
          const vals: number[] = []
          for (let k = 0; k < K; k += Math.max(1, Math.floor(K / 6))) { const d = f[`v${k}`].data; for (let i = 0; i < d.length; i += 7) if (!Number.isNaN(d[i])) vals.push(d[i]) }
          vals.sort((a, b) => a - b); lo = quantile(vals, 0.02); hi = quantile(vals, 0.98)
        }
        if (alive) { setPb({ kind: 'months', f, K, mask, dates: f.days.meta?.dates ?? [], cats, lo, hi }); setT(0) }
      }
    })().catch(e => { if (alive) { setPb(null); setPbErr(String(e.message ?? e).includes('404') ? 'Run at least one full day first, then come back.' : String(e.message ?? e)) } })
    return () => { alive = false }
  }, [mode, universe, dataVersion, pbVar, JSON.stringify(cohort)])
  useEffect(() => {
    if (!playing || !pb) return
    let raf = 0, last = performance.now()
    const tick = (now: number) => {
      const dt = Math.min(0.1, (now - last) / 1000); last = now
      setT(x => {
        const nx = Math.min(x, pb.K) + dt * speed * (pb.kind === 'day' ? 0.6 : 0.9)
        if (pb.kind === 'day') return nx >= pb.K ? 0 : nx
        if (nx >= pb.K - 1) { setPlaying(false); return pb.K - 1 }
        return nx
      })
      raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [playing, pb, speed])

  // ---- ego ties of the selected person
  useEffect(() => {
    if (selected === null) { setEgo([]); return }
    api.personNetwork(selected, universe).then(async net => {
      const pos = await api.positions(universe, 'home')
      const ties = net.edges.filter((e: any) => !e.alter_tie).map((e: any) => ({
        from: [pos.lon.data[selected], pos.lat.data[selected]], to: [pos.lon.data[e.target], pos.lat.data[e.target]],
        romantic: e.types.includes('romantic') || e.types.includes('spouse'), stage: e.stage,
      })).filter((t: any) => !Number.isNaN(t.to[0]))
      setEgo(ties)
    }).catch(() => setEgo([]))
  }, [selected, universe, dataVersion])

  // ---- color function
  const colorFn = useMemo(() => {
    if (!pts) return null
    const spec = reg.variables[pts.varName]
    const col: Column = pts.col
    if (diff && pts.other) {
      const a = col.data, b = pts.other.data
      const d: number[] = []
      for (let i = 0; i < a.length; i++) if (!Number.isNaN(a[i]) && !Number.isNaN(b[i])) d.push(Math.abs(b[i] - a[i]))
      const s = d.sort((x, y) => x - y)
      const m = quantile(s, 0.98) || 1
      const sign = universe === 'base' ? 1 : -1
      return { fn: (i: number) => divColor(sign * (b[i] - a[i]) / m), legend: { kind: 'div', m } }
    }
    if (col.categories || col.bool) {
      const cats = col.categories ?? ['no', 'yes']
      const pal = [1, 2, 3, 4, 5, 6, 7, 8].map(k => hexRgb(cssVar(`--s${k}`)))
      const other = hexRgb(cssVar('--text-muted'))
      return { fn: (i: number) => (col.data[i] < 8 ? pal[col.data[i]] : other), legend: { kind: 'cat', cats: cats.slice(0, 8), more: cats.length > 8 } }
    }
    const vals: number[] = []
    for (let i = 0; i < col.data.length; i++) if (!Number.isNaN(col.data[i])) vals.push(col.data[i])
    vals.sort((a, b) => a - b)
    const lo = quantile(vals, 0.02), hi = quantile(vals, 0.98)
    return { fn: (i: number) => seqColor(((col.data[i] as number) - lo) / ((hi - lo) || 1)), legend: { kind: 'seq', lo, hi, units: spec?.units } }
  }, [pts, diff, universe])

  // ---- layers
  useEffect(() => {
    if (!overlay.current) return
    const road = hexRgb(cssVar('--map-road')), bldg = hexRgb(cssVar('--map-bldg')), mutedC = hexRgb(cssVar('--text-muted'))
    const layers: any[] = []
    if (!basemap && cities) layers.push(new GeoJsonLayer({ id: 'cities', data: cities, stroked: true, filled: false, getLineColor: [...mutedC, 90], lineWidthMinPixels: 1 }))
    if (showBldg && buildings) layers.push(new SolidPolygonLayer({ id: 'bldg', data: buildings, getPolygon: (d: any) => d, getFillColor: [...bldg, basemap ? 120 : 255], pickable: false }))
    if (showRoads && roads && !basemap) layers.push(new GeoJsonLayer({ id: 'roads', data: roads, stroked: true, filled: false, getLineColor: [...road, 255], getLineWidth: (f: any) => (f.properties.c === 1 ? 2.2 : 1), lineWidthUnits: 'pixels' }))
    if (showNbhd && nbhds.length) layers.push(new PolygonLayer({ id: 'nbhd', data: nbhds, getPolygon: (d: any) => d.ring, stroked: true, filled: true, getFillColor: [...hexRgb(cssVar('--s1')), 14], getLineColor: [...hexRgb(cssVar('--s1')), 170], lineWidthMinPixels: 1.2, pickable: true, autoHighlight: true, highlightColor: [...hexRgb(cssVar('--s1')), 50], onHover: (i: any) => setHover(i.object ? { x: i.x, y: i.y, html: `<b>${i.object.name}</b><br/>${i.object.city} neighborhood` } : null) }))
    if (showVenues) layers.push(new ScatterplotLayer({ id: 'venues', data: venues, getPosition: (d: any) => [d.lon, d.lat], getRadius: 5, radiusUnits: 'pixels', getFillColor: [...hexRgb(cssVar('--s4')), 230], stroked: true, getLineColor: [255, 255, 255, 200], lineWidthMinPixels: 1, pickable: true, onHover: (i: any) => setHover(i.object ? { x: i.x, y: i.y, html: `<b>${i.object.name}</b><br/>${i.object.vtype.replace('_', ' ')}` } : null) }))
    if ((mode === 'people' || mode === 'homes') && pts && colorFn) {
      const idx: number[] = []
      for (let i = 0; i < pts.lon.length; i++) if (!Number.isNaN(pts.lon[i])) idx.push(i)
      const anyCohort = cohort.length > 0
      layers.push(new ScatterplotLayer({
        id: 'people', data: idx, getPosition: (i: number) => [pts.lon[i], pts.lat[i]],
        getRadius: (i: number) => (anyCohort && highlight && pts.mask[i] ? 7 : 5), radiusUnits: 'meters', radiusMinPixels: 1.6, radiusMaxPixels: 7,
        getFillColor: (i: number) => { const c = colorFn.fn(i); const a = anyCohort && highlight ? (pts.mask[i] ? 235 : 28) : 200; return [c[0], c[1], c[2], a] },
        pickable: true, autoHighlight: true, highlightColor: [255, 255, 255, 220],
        updateTriggers: { getFillColor: [colorFn, highlight, cohort.length, pts], getRadius: [highlight, cohort.length, pts] },
        onHover: (info: any) => {
          if (info.object === undefined || info.object === null) { setHover(null); return }
          const i = info.object
          const c: Column = pts.col
          const v = c.categories ? c.categories[c.data[i]] : c.bool ? (c.data[i] ? 'yes' : 'no') : fmt(c.data[i], 3)
          const act = pts.act.categories[pts.act.data[i]]
          setHover({ x: info.x, y: info.y, html: `<b>${nameOf(i, pts.sex.data[i])}</b> · #${i}<br/>${reg.variables[pts.varName]?.label ?? pts.varName}: ${String(v).replace('_', ' ')}<br/><span style="color:var(--text-muted)">now: ${act}</span>` })
        },
        onClick: (info: any) => { if (info.object !== undefined) setSelected(info.object) },
      }))
    }
    if (playback && pb) {
      const K = pb.K, f = pb.f
      const tt = Math.max(0, Math.min(t, pb.kind === 'day' ? K - 0.001 : K - 1))
      const k0 = Math.floor(tt) % K, k1 = pb.kind === 'day' ? (k0 + 1) % K : Math.min(k0 + 1, K - 1), a = tt - Math.floor(tt)
      const L0 = f[`lon${k0}`].data, A0 = f[`lat${k0}`].data, L1 = f[`lon${k1}`].data, A1 = f[`lat${k1}`].data
      const near = a < 0.5 ? k0 : k1
      const pal = [1, 2, 3, 4, 5, 6, 7, 8].map(k => hexRgb(cssVar(`--s${k}`)))
      const other = hexRgb(cssVar('--text-muted'))
      const col = pb.kind === 'day' ? f[`act${near}`].data : f[`v${near}`].data
      const color = (i: number): [number, number, number] => {
        if (pb.kind === 'day' || pb.cats) { const c = col[i]; return c < 8 ? pal[c] : other }
        return seqColor((col[i] - pb.lo) / ((pb.hi - pb.lo) || 1))
      }
      const idx: number[] = []
      for (let i = 0; i < L0.length; i++) if (!Number.isNaN(L0[i]) || !Number.isNaN(L1[i])) idx.push(i)
      const anyCohort = cohort.length > 0
      layers.push(new ScatterplotLayer({
        id: 'playback', data: idx,
        getPosition: (i: number) => {
          const x0 = L0[i], y0 = A0[i], x1 = L1[i], y1 = A1[i]
          if (Number.isNaN(x0)) return [x1, y1]
          if (Number.isNaN(x1)) return [x0, y0]
          return [x0 + (x1 - x0) * a, y0 + (y1 - y0) * a]
        },
        getRadius: 5, radiusUnits: 'meters', radiusMinPixels: 1.8, radiusMaxPixels: 6,
        getFillColor: (i: number) => { const c = color(i); return [c[0], c[1], c[2], anyCohort && highlight ? (pb.mask[i] ? 235 : 25) : 205] },
        updateTriggers: { getPosition: [t, pb], getFillColor: [near, pb, highlight, cohort.length] },
        pickable: true, onClick: (info: any) => { if (info.object !== undefined) setSelected(info.object) },
      }))
    }
    if ((mode === 'complexes' || mode === 'wards') && places.length) {
      const ms = places.map(p => p.mean).filter((v: any) => v !== null).sort((a: number, b: number) => a - b)
      const lo = quantile(ms, 0.05), hi = quantile(ms, 0.95)
      layers.push(new ScatterplotLayer({
        id: 'places', data: places, getPosition: (d: any) => [d.lon, d.lat], getRadius: (d: any) => 6 + 2.2 * Math.sqrt(d.n), radiusUnits: 'pixels',
        getFillColor: (d: any) => [...seqColor((d.mean - lo) / ((hi - lo) || 1)), 210], stroked: true, getLineColor: [255, 255, 255, 220], lineWidthMinPixels: 1.5,
        pickable: true, updateTriggers: { getFillColor: [places] },
        onHover: (info: any) => setHover(info.object ? { x: info.x, y: info.y, html: `<b>${info.object.name ?? info.object.kind?.replace('_', ' ') + ' ward #' + info.object.id}</b><br/>${info.object.n} residents · mean ${fmt(info.object.mean, 3)}` } : null),
        onClick: (info: any) => info.object && setRoute(['places', mode === 'complexes' ? 'complex' : 'ward', String(info.object.id)]),
      }))
    }
    if (ego.length) {
      layers.push(new LineLayer({ id: 'ego', data: ego, getSourcePosition: (d: any) => d.from, getTargetPosition: (d: any) => d.to, getColor: (d: any) => (d.romantic ? [...hexRgb(cssVar('--s5')), 255] : [...hexRgb(cssVar('--s7')), d.stage >= 3 ? 200 : 90]), getWidth: (d: any) => (d.romantic ? 3 : d.stage >= 4 ? 2 : 1), widthUnits: 'pixels' }))
    }
    overlay.current.setProps({ layers })
  }, [buildings, roads, cities, venues, pts, colorFn, places, mode, showRoads, showBldg, showVenues, showNbhd, nbhds, highlight, ego, basemap, cohort.length, pb, t])

  const legend = colorFn?.legend
  return (
    <div className="mapwrap">
      <div ref={el} style={{ position: 'absolute', inset: 0, background: 'var(--map-bg)' }} />
      <div className="card map-panel">
        <h3>Map of Provo & Orem</h3>
        <p className="hint">{MODE_HINT[mode]}</p>
        <div className="seg" style={{ marginBottom: 8 }}>
          {(['people', 'homes', 'complexes', 'wards'] as Mode[]).map(m => <button key={m} className={mode === m ? 'on' : ''} onClick={() => setMode(m)} title={MODE_HINT[m]}>{MODE_LABEL[m]}</button>)}
        </div>
        <div className="small muted">Play back</div>
        <div className="seg" style={{ marginBottom: 8 }}>
          {(['day', 'months'] as Mode[]).map(m => <button key={m} className={mode === m ? 'on' : ''} onClick={() => { setMode(m); setPlaying(true) }} title={MODE_HINT[m]}>{MODE_LABEL[m]}</button>)}
        </div>
        <div style={{ marginBottom: 8 }}>
          <div className="small muted">Color by</div>
          {mode === 'day' ? <div className="small">What each person is doing (see legend)</div> : mode === 'months' ? (
            <select value={pbVar} onChange={e => setPbVar(e.target.value)} style={{ width: '100%' }}>
              {[...tracked.cat, ...tracked.num].filter(v => !STATIC || STATIC_FRAME_VARS.includes(v)).map(v => <option key={v} value={v}>{reg.variables[v]?.label ?? v}</option>)}
            </select>
          ) : mode === 'people' || mode === 'homes' ? (
            <select value={colorBy} onChange={e => setColorBy(e.target.value)} style={{ width: '100%' }}>
              <option value="activity_now">Current activity</option>
              {Object.values(reg.variables).filter(v => v.entity === 'person' && v.mappable).sort((a, b) => a.label.localeCompare(b.label)).map(v => <option key={v.id} value={v.id}>{v.label}</option>)}
            </select>
          ) : (
            <VarPicker value={colorBy === 'activity_now' ? 'loneliness' : colorBy} onChange={setColorBy} filter={v => !!v.mappable && v.dtype !== 'cat'} />
          )}
        </div>
        {status.has_alt && (mode === 'people' || mode === 'homes') && colorBy !== 'activity_now' && (
          <label className="inline small"><input type="checkbox" checked={diff} onChange={e => setDiff(e.target.checked)} /> show intervention − baseline difference</label>
        )}
        <div className="row small" style={{ marginTop: 6 }}>
          <label className="inline"><input type="checkbox" checked={highlight} onChange={e => setHighlight(e.target.checked)} />highlight cohort</label>
          <label className="inline"><input type="checkbox" checked={basemap} onChange={e => setBasemap(e.target.checked)} />basemap</label>
          <label className="inline"><input type="checkbox" checked={showRoads} onChange={e => setShowRoads(e.target.checked)} />roads</label>
          <label className="inline"><input type="checkbox" checked={showBldg} onChange={e => setShowBldg(e.target.checked)} />buildings</label>
          <label className="inline"><input type="checkbox" checked={showVenues} onChange={e => setShowVenues(e.target.checked)} />venues</label>
          <label className="inline"><input type="checkbox" checked={showNbhd} onChange={e => setShowNbhd(e.target.checked)} />neighborhoods</label>
        </div>
        <div style={{ marginTop: 10 }}><CohortBar /></div>
        {selected !== null && (
          <div className="banner">
            Showing ties of <b>{pts ? nameOf(selected, pts.sex.data[selected]) : '#' + selected}</b> (pink = romantic).
            <div className="row" style={{ marginTop: 6 }}>
              <button className="btn small primary" onClick={() => setRoute(['person', String(selected)])}>Open life story</button>
              <button className="btn small" onClick={() => setSelected(null)}>Clear</button>
            </div>
          </div>
        )}
        {mode === 'people' && <p className="hint" style={{ marginTop: 8 }}>Use Jump ▾ → +1 hour to watch people move between homes, classes, work, church and evenings out, or press ▶ A day for a smooth replay.</p>}
      </div>
      {legend && (mode === 'people' || mode === 'homes') && (
        <div className="card map-legend small">
          {legend.kind === 'cat' && legend.cats!.map((c: string, k: number) => <div key={c} className="row"><span className="dot" style={{ background: `var(--s${k + 1})` }} />{c.replace(/_/g, ' ')}</div>)}
          {legend.kind === 'cat' && legend.more && <div className="row"><span className="dot" style={{ background: 'var(--text-muted)' }} />other</div>}
          {legend.kind === 'seq' && <><div style={{ height: 10, borderRadius: 3, background: 'linear-gradient(90deg,#cde2fb,#9ec5f4,#6da7ec,#3987e5,#256abf,#184f95,#0d366b)' }} /><div className="row tabular" style={{ justifyContent: 'space-between' }}><span>{fmt(legend.lo, 2)}</span><span>{reg.variables[colorBy]?.label}</span><span>{fmt(legend.hi, 2)}</span></div></>}
          {legend.kind === 'div' && <><div style={{ height: 10, borderRadius: 3, background: 'linear-gradient(90deg,#2a78d6,#d9d8d2,#e34948)' }} /><div className="row tabular" style={{ justifyContent: 'space-between' }}><span>−{fmt(legend.m, 2)}</span><span>intervention − baseline</span><span>+{fmt(legend.m, 2)}</span></div></>}
        </div>
      )}
      {playback && pb && (
        <div className="card map-legend small">
          {(pb.kind === 'day' ? pb.f.act0.categories : pb.cats ?? null)?.slice(0, 8).map((c: string, k: number) => <div key={c} className="row"><span className="dot" style={{ background: `var(--s${k + 1})` }} />{c.replace(/_/g, ' ')}</div>)}
          {pb.kind === 'months' && !pb.cats && <><div style={{ height: 10, borderRadius: 3, background: 'linear-gradient(90deg,#cde2fb,#9ec5f4,#6da7ec,#3987e5,#256abf,#184f95,#0d366b)' }} /><div className="row tabular" style={{ justifyContent: 'space-between' }}><span>{fmt(pb.lo, 2)}</span><span>{reg.variables[pbVar]?.label}</span><span>{fmt(pb.hi, 2)}</span></div></>}
        </div>
      )}
      {playback && (
        <div className="playback">
          <div className="card">
            {pbErr ? <div className="small">{pbErr}</div> : !pb ? <div className="small muted">Loading the replay…</div> : (
              <>
                <div className="pb-row">
                  <button className="btn small primary" onClick={() => setPlaying(!playing)} style={{ minWidth: 70 }}>{playing ? '⏸ Pause' : '▶ Play'}</button>
                  <span className="pb-label">{pb.kind === 'day' ? DAY_LABELS[Math.round(t) % 4] : new Date((pb.dates[Math.min(Math.round(t), pb.K - 1)] ?? pb.dates[0]) + 'T12:00:00').toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })}</span>
                  <input type="range" min={0} max={pb.kind === 'day' ? 3.99 : pb.K - 1} step={0.01} value={t} onChange={e => { setPlaying(false); setT(Number(e.target.value)) }} aria-label="Playback position" />
                  <div className="seg small-seg">{[0.5, 1, 2, 4].map(s => <button key={s} className={speed === s ? 'on' : ''} onClick={() => setSpeed(s)}>{s}×</button>)}</div>
                </div>
                <div className="small muted" style={{ marginTop: 4 }}>
                  {pb.kind === 'day' ? `Replaying ${pb.date ? new Date(pb.date + 'T12:00:00').toLocaleDateString(undefined, { weekday: 'long', month: 'long', day: 'numeric' }) : 'the last full day'}. Run time forward to replay a newer day.`
                    : `${pb.K} snapshots, every two weeks since the start. ${pb.K < 3 ? 'Run a few more weeks for a longer replay.' : 'Drag the slider to any date.'}`}
                </div>
              </>
            )}
          </div>
        </div>
      )}
      {hover && <div className="tooltip" style={{ left: hover.x + 12, top: hover.y + 12 }} dangerouslySetInnerHTML={{ __html: hover.html }} />}
    </div>
  )
}
