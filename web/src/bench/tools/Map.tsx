// Map: everyone as a dot, where they are in the part of the day the model last simulated (or at home), colored by
// any field. The selection is drawn strong and everyone else faint; click a dot to focus that person, or drag a box to
// select everyone inside it.
import { MapboxOverlay } from '@deck.gl/mapbox'
import { GeoJsonLayer, ScatterplotLayer } from '@deck.gl/layers'
import maplibregl from 'maplibre-gl'
import { useEffect, useMemo, useRef, useState } from 'react'
import { cohortMask, quantile } from '../../analysis'
import { api, type Column } from '../../api'
import { cssVar, hexRgb, seqColor, VarPicker } from '../../components'
import { fval, pretty } from '../../fields'
import { useAsync } from '../../game'
import { Busy, dayWords, Problem, useWorldDays } from '../../kit/Bits'
import { usePersonName } from '../../kit/RefChip'
import { loadColumns, useLens, useStore } from '../../store'
import { PanelOptions } from '../panel'
import type { PanelProps, ToolDef } from '../registry'
import { focusItem, subjectPerson } from '../sel'

const CENTER: [number, number] = [-111.672, 40.262]
const BLOCKS: [number, number, string][] = [[8 * 60, 12 * 60 + 30, 'morning'], [12 * 60 + 30, 17 * 60 + 30, 'afternoon'], [17 * 60 + 30, 20 * 60 + 15, 'evening'], [20 * 60 + 15, 23 * 60 + 30, 'late evening']]
let geoCache: Promise<{ roads: any; cities: any }> | null = null
const loadGeo = () => (geoCache ??= Promise.all([
  fetch(api.geo('roads.json')).then(r => r.json()).catch(() => null),
  fetch(api.geo('cities.json')).then(r => r.json()).catch(() => null),
]).then(([roads, cities]) => ({ roads, cities })))

/** Which part of the day a clock hour falls in, in words, and what the dots mean then. */
function momentWords(hour: number | undefined) {
  if (hour === undefined) return ''
  const m = hour * 60
  const b = BLOCKS.find(([s, e]) => m >= s && m < e)
  if (b) return `the ${b[2]}`
  return m < BLOCKS[0][0] ? 'before the day starts (most people at home)' : 'the night (people at home)'
}

function MapTool({ sel, setSel, opts, setOpts }: PanelProps) {
  const lens = useLens()
  const u = lens.u   // people are the same in both worlds; the lens says which world to show
  const dataVersion = useStore(s => s.dataVersion)
  const status = useStore(s => s.status)
  const theme = useStore(s => s.theme)
  const reg = useStore(s => s.registry)!
  const name = usePersonName(u)
  const { start } = useWorldDays()
  const mode: 'now' | 'home' = opts.mode ?? 'now'
  const colorBy: string = opts.color ?? 'activity_now'
  const set = (o: Record<string, any>) => setOpts({ ...opts, ...o })

  const el = useRef<HTMLDivElement>(null)
  const map = useRef<maplibregl.Map | null>(null)
  const overlay = useRef<MapboxOverlay | null>(null)
  const [ready, setReady] = useState(false)
  const [geo, setGeo] = useState<{ roads: any; cities: any } | null>(null)
  const [hover, setHover] = useState<{ x: number; y: number; i: number } | null>(null)
  const [boxing, setBoxing] = useState(false)
  const [box, setBox] = useState<{ x0: number; y0: number; x1: number; y1: number } | null>(null)

  useEffect(() => {
    if (!el.current) return
    const m = new maplibregl.Map({ container: el.current, style: { version: 8, sources: {}, layers: [{ id: 'bg', type: 'background', paint: { 'background-color': cssVar('--map-bg') } }] } as any,
      center: CENTER, zoom: 11.6, attributionControl: false, dragRotate: false, pitchWithRotate: false })
    m.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-right')
    const ov = new MapboxOverlay({ interleaved: false, layers: [] })
    m.addControl(ov as any)
    map.current = m; overlay.current = ov
    m.on('load', () => setReady(true))
    const ro = new ResizeObserver(() => m.resize())
    ro.observe(el.current)
    loadGeo().then(setGeo)
    return () => { ro.disconnect(); m.remove(); map.current = null; overlay.current = null }
  }, [])
  useEffect(() => { if (ready) map.current?.setPaintProperty('bg', 'background-color', cssVar('--map-bg')) }, [theme, ready])

  // ---- data: positions, the color field, who is selected
  const data = useAsync(async () => {
    const pos = await api.positions(u, mode)
    const cols = colorBy === 'activity_now' ? {} : await loadColumns([colorBy], u)
    const col: Column | undefined = colorBy === 'activity_now' ? pos.activity_now : cols[colorBy]
    return { lon: pos.lon.data as Float32Array, lat: pos.lat.data as Float32Array, act: pos.activity_now, col }
  }, [u, mode, colorBy, dataVersion], { key: `bench-map:${u}:${mode}:${colorBy}` })
  const group = useAsync(async () => (sel.filter?.length ? (await cohortMask(sel.filter, u)).mask : null), [JSON.stringify(sel.filter ?? []), u, dataVersion])
  const d = data.data
  const n = d?.lon.length ?? 0
  const chosen = useMemo(() => {
    if (!n) return null
    const ids = sel.people ?? []
    if (!ids.length && !group.data) return null
    const m = new Uint8Array(n)
    if (ids.length) for (const i of ids) { if (i < n) m[i] = 1 }
    else if (group.data) for (let i = 0; i < n; i++) m[i] = group.data[i]
    if (ids.length && group.data) for (let i = 0; i < n; i++) m[i] &= group.data[i]
    return m
  }, [n, sel.people, group.data])
  const focus = subjectPerson(sel)

  const color = useMemo(() => {
    const col = d?.col
    if (!col) return null
    const spec = reg.variables[colorBy]
    if (col.categories || col.bool) {
      const cats = col.categories ?? ['no', 'yes']
      const pal = [1, 2, 3, 4, 5, 6, 7, 8].map(k => hexRgb(cssVar(`--s${k}`)))
      const other = hexRgb(cssVar('--text-muted'))
      return { fn: (i: number) => (col.data[i] < 8 ? pal[col.data[i]] : other), legend: { kind: 'cat' as const, cats: cats.slice(0, 8).map(pretty), more: cats.length > 8 } }
    }
    const vals: number[] = []
    for (let i = 0; i < col.data.length; i += Math.max(1, Math.floor(col.data.length / 20000))) if (!Number.isNaN(col.data[i])) vals.push(col.data[i])
    vals.sort((a, b) => a - b)
    const lo = quantile(vals, 0.02), hi = quantile(vals, 0.98)
    return { fn: (i: number) => seqColor(((col.data[i] as number) - lo) / ((hi - lo) || 1)), legend: { kind: 'seq' as const, lo, hi, low: spec?.scale?.low, high: spec?.scale?.high } }
  }, [d, colorBy, theme])

  // ---- layers
  useEffect(() => {
    if (!overlay.current) return
    const layers: any[] = []
    const road = hexRgb(cssVar('--map-road')), muted = hexRgb(cssVar('--text-muted'))
    if (geo?.cities) layers.push(new GeoJsonLayer({ id: 'cities', data: geo.cities, stroked: true, filled: false, getLineColor: [...muted, 80], lineWidthMinPixels: 1 }))
    if (geo?.roads) layers.push(new GeoJsonLayer({ id: 'roads', data: geo.roads, stroked: true, filled: false, getLineColor: [...road, 255], getLineWidth: (f: any) => (f.properties.c === 1 ? 1.8 : 0.8), lineWidthUnits: 'pixels' }))
    if (d && color) {
      const idx: number[] = []
      for (let i = 0; i < n; i++) if (!Number.isNaN(d.lon[i])) idx.push(i)
      if (chosen) idx.sort((a, b) => chosen[a] - chosen[b])            // the selection drawn on top
      layers.push(new ScatterplotLayer({
        id: 'people', data: idx, getPosition: (i: number) => [d.lon[i], d.lat[i]],
        getRadius: (i: number) => (chosen && chosen[i] ? 7 : 4.5), radiusUnits: 'meters', radiusMinPixels: 1.5, radiusMaxPixels: 8,
        getFillColor: (i: number) => { const c = color.fn(i); return [c[0], c[1], c[2], chosen ? (chosen[i] ? 240 : 26) : 190] },
        stroked: !!chosen, getLineColor: (i: number) => (chosen && chosen[i] ? [255, 255, 255, 200] : [0, 0, 0, 0]), lineWidthMinPixels: 0.6,
        pickable: true, autoHighlight: true, highlightColor: [255, 255, 255, 230],
        updateTriggers: { getFillColor: [color, chosen], getRadius: [chosen], getLineColor: [chosen] },
        onHover: (info: any) => setHover(info.object === undefined || info.object === null ? null : { x: info.x, y: info.y, i: info.object }),
        onClick: (info: any) => { if (info.object !== undefined && !boxing) focusItem(setSel, { kind: 'person', id: info.object, label: name(info.object) }) },
      }))
      if (focus !== null && focus < n && !Number.isNaN(d.lon[focus])) {
        layers.push(new ScatterplotLayer({ id: 'focus', data: [focus], getPosition: (i: number) => [d.lon[i], d.lat[i]], getRadius: 11, radiusUnits: 'pixels',
          filled: false, stroked: true, getLineColor: [...hexRgb(cssVar('--text-primary')), 255], lineWidthMinPixels: 2 }))
      }
    }
    overlay.current.setProps({ layers })
  }, [geo, d, color, chosen, focus, boxing, ready])

  // ---- drag a box to select
  const boxStart = (e: React.PointerEvent) => {
    const r = (e.currentTarget as HTMLElement).getBoundingClientRect()
    ;(e.currentTarget as HTMLElement).setPointerCapture(e.pointerId)
    setBox({ x0: e.clientX - r.left, y0: e.clientY - r.top, x1: e.clientX - r.left, y1: e.clientY - r.top })
  }
  const boxMove = (e: React.PointerEvent) => {
    if (!box) return
    const r = (e.currentTarget as HTMLElement).getBoundingClientRect()
    setBox({ ...box, x1: e.clientX - r.left, y1: e.clientY - r.top })
  }
  const boxEnd = () => {
    if (!box || !map.current || !d) { setBox(null); return }
    const a = map.current.unproject([Math.min(box.x0, box.x1), Math.min(box.y0, box.y1)])
    const b = map.current.unproject([Math.max(box.x0, box.x1), Math.max(box.y0, box.y1)])
    const ids: number[] = []
    if (Math.abs(box.x1 - box.x0) > 4 && Math.abs(box.y1 - box.y0) > 4) {
      for (let i = 0; i < n; i++) {
        const lo = d.lon[i], la = d.lat[i]
        if (lo >= a.lng && lo <= b.lng && la <= a.lat && la >= b.lat && (!group.data || group.data[i])) ids.push(i)
      }
      setSel({ people: ids.slice(0, 20000), item: undefined })
    }
    setBox(null); setBoxing(false)
  }

  const hh = status?.hour !== undefined ? `${((status.hour + 11) % 12) + 1} ${status.hour >= 12 ? 'pm' : 'am'}` : ''
  const moment = mode === 'home'
    ? 'Each dot is a person at home.'
    : `${dayWords(start, status?.day ?? 0, true)}, ${hh}: where each person is in ${momentWords(status?.hour)}. The model places people a few times a day, so dots jump between parts of the day rather than move continuously.`
  const hv = hover && d ? hover : null
  const spec = reg.variables[colorBy]
  const nSel = chosen ? chosen.reduce((s, x) => s + x, 0) : 0
  return (
    <div className="bm">
      <PanelOptions>
        <div className="seg">
          <button className={mode === 'now' ? 'on' : ''} onClick={() => set({ mode: 'now' })} title="Where people are in the latest part of the day">Now</button>
          <button className={mode === 'home' ? 'on' : ''} onClick={() => set({ mode: 'home' })} title="Where people live">Homes</button>
        </div>
        <VarPicker value={colorBy === 'activity_now' ? '' : colorBy} onChange={v => set({ color: v || 'activity_now' })} filter={s => !!s.mappable} placeholder="Color: what they're doing" allowEmpty />
      </PanelOptions>
      <div className="bm-map" ref={el} />
      {(boxing || box) && (
        <div className="bm-boxer" onPointerDown={boxStart} onPointerMove={boxMove} onPointerUp={boxEnd}>
          {box && <div className="bm-box" style={{ left: Math.min(box.x0, box.x1), top: Math.min(box.y0, box.y1), width: Math.abs(box.x1 - box.x0), height: Math.abs(box.y1 - box.y0) }} />}
        </div>
      )}
      <div className="bm-tools">
        <button className={`btn small ${boxing ? 'primary' : ''}`} onClick={() => setBoxing(!boxing)} title="Drag a rectangle on the map to select everyone inside it">{boxing ? 'Drag a box…' : '▭ Select an area'}</button>
      </div>
      <div className="bm-note">{moment}{nSel > 0 && <> · <b>{nSel.toLocaleString()}</b> selected</>}</div>
      {color && (
        <div className="bm-legend">
          <b>{colorBy === 'activity_now' ? "What they're doing" : spec?.label ?? colorBy}</b>
          {color.legend.kind === 'cat'
            ? <div className="bx-legend">{color.legend.cats.map((c, k) => <span key={c}><i className="bx-catdot" style={{ background: `var(--s${k + 1})` }} />{c}</span>)}{color.legend.more && <span><i className="bx-catdot" style={{ background: 'var(--text-muted)' }} />other</span>}</div>
            : <div className="bm-ramp"><span>{fval(spec, color.legend.lo)}{color.legend.low ? ` · ${color.legend.low}` : ''}</span><i /><span>{fval(spec, color.legend.hi)}{color.legend.high ? ` · ${color.legend.high}` : ''}</span></div>}
        </div>
      )}
      {hv && d && (
        <div className="bm-tip" style={{ left: hv.x + 12, top: hv.y + 12 }}>
          <b>{name(hv.i)}</b><br />
          {d.col && colorBy !== 'activity_now' && <>{spec?.label}: {fval(spec, d.col.categories ? d.col.categories[d.col.data[hv.i]] : d.col.data[hv.i])}<br /></>}
          <small>{mode === 'now' ? `now: ${pretty(d.act.categories?.[d.act.data[hv.i]] ?? '')}` : 'at home'} · click to focus</small>
        </div>
      )}
      {data.error && !d && <div className="bm-over"><Problem error={data.error} /></div>}
      {!d && !data.error && <div className="bm-over"><Busy what="Placing people" /></div>}
    </div>
  )
}

export const tool: ToolDef = {
  id: 'map',
  label: 'Map',
  icon: 'map',
  hint: 'Everyone as a dot, where they are now or at home, colored by any field; click a dot to focus, drag a box to select.',
  group: 'see',
  order: 10,
  component: MapTool,
  size: { w: 6, h: 7 },
}
