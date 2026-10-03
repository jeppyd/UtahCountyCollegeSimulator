import { MapboxOverlay } from '@deck.gl/mapbox'
import { GeoJsonLayer, LineLayer, ScatterplotLayer, SolidPolygonLayer } from '@deck.gl/layers'
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

type Mode = 'people' | 'homes' | 'complexes' | 'wards'

export default function MapView() {
  const { universe, dataVersion, cohort, status, setRoute, theme } = useStore()
  const el = useRef<HTMLDivElement>(null)
  const map = useRef<maplibregl.Map | null>(null)
  const overlay = useRef<MapboxOverlay | null>(null)
  const [mode, setMode] = useState<Mode>('people')
  const [colorBy, setColorBy] = useState('activity_now')
  const [diff, setDiff] = useState(false)
  const [basemap, setBasemap] = useState(!STATIC)
  const [showRoads, setShowRoads] = useState(true)
  const [showBldg, setShowBldg] = useState(true)
  const [showVenues, setShowVenues] = useState(false)
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
      } else {
        const v = colorBy === 'activity_now' ? 'loneliness' : colorBy
        const rows = mode === 'complexes' ? await api.complexes(v, universe) : await api.wards(v, universe)
        if (alive) setPlaces(rows)
      }
    })().catch(e => console.warn(e))
    return () => { alive = false }
  }, [mode, colorBy, universe, dataVersion, JSON.stringify(cohort), diff])

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
  }, [buildings, roads, cities, venues, pts, colorFn, places, mode, showRoads, showBldg, showVenues, highlight, ego, basemap, cohort.length])

  const legend = colorFn?.legend
  return (
    <div className="mapwrap">
      <div ref={el} style={{ position: 'absolute', inset: 0, background: 'var(--map-bg)' }} />
      <div className="card map-panel">
        <h3>Map</h3>
        <p className="hint">Real Provo/Orem geography (UGRC address points, parcels & footprints). Each dot is a synthetic person.</p>
        <div className="seg" style={{ marginBottom: 8 }}>
          {(['people', 'homes', 'complexes', 'wards'] as Mode[]).map(m => <button key={m} className={mode === m ? 'on' : ''} onClick={() => setMode(m)}>{m === 'people' ? 'Now' : m[0].toUpperCase() + m.slice(1)}</button>)}
        </div>
        <div style={{ marginBottom: 8 }}>
          <div className="small muted">Color by</div>
          {mode === 'people' || mode === 'homes' ? (
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
        <p className="hint" style={{ marginTop: 8 }}>Step the clock by hours to watch people move between homes, classes, work, church and evenings out.</p>
      </div>
      {legend && (mode === 'people' || mode === 'homes') && (
        <div className="card map-legend small">
          {legend.kind === 'cat' && legend.cats!.map((c: string, k: number) => <div key={c} className="row"><span className="dot" style={{ background: `var(--s${k + 1})` }} />{c.replace(/_/g, ' ')}</div>)}
          {legend.kind === 'cat' && legend.more && <div className="row"><span className="dot" style={{ background: 'var(--text-muted)' }} />other</div>}
          {legend.kind === 'seq' && <><div style={{ height: 10, borderRadius: 3, background: 'linear-gradient(90deg,#cde2fb,#9ec5f4,#6da7ec,#3987e5,#256abf,#184f95,#0d366b)' }} /><div className="row tabular" style={{ justifyContent: 'space-between' }}><span>{fmt(legend.lo, 2)}</span><span>{reg.variables[colorBy]?.label}</span><span>{fmt(legend.hi, 2)}</span></div></>}
          {legend.kind === 'div' && <><div style={{ height: 10, borderRadius: 3, background: 'linear-gradient(90deg,#2a78d6,#d9d8d2,#e34948)' }} /><div className="row tabular" style={{ justifyContent: 'space-between' }}><span>−{fmt(legend.m, 2)}</span><span>intervention − baseline</span><span>+{fmt(legend.m, 2)}</span></div></>}
        </div>
      )}
      {hover && <div className="tooltip" style={{ left: hover.x + 12, top: hover.y + 12 }} dangerouslySetInnerHTML={{ __html: hover.html }} />}
    </div>
  )
}
