// Map: the living map of Provo and Orem. Everyone where the simulation puts them — in their bedroom on the right floor,
// at the table of their date, in their seat at the game — among real buildings at their real heights (tilt for 3D,
// "See inside" to watch people through the walls, click a building to open it floor by floor). Everyone is one color
// until you pick any field to paint by (categories in distinct colors, numbers as a ramp, a fade or a threshold; see
// mapPaint.tsx); the selection is drawn strong and everyone else faint; click a dot to focus that person, or drag a box
// to select everyone inside it.
import { useCallback, useMemo, useRef, useState } from 'react'
import type maplibregl from 'maplibre-gl'
import { cohortMask } from '../../analysis'
import { type Column } from '../../api'
import { cssVar, hexRgb, VarPicker } from '../../components'
import { fval, pretty } from '../../fields'
import { useAsync } from '../../game'
import { usePersonName } from '../../kit/RefChip'
import { CLAY, LivingMap, type LivingOpts } from '../../map/LivingMap'
import { type Precise, type Refresh, REFRESH_WORDS } from '../../map/data'
import { loadColumns, useLens, useStore } from '../../store'
import { useLayout } from '../layout'
import { PanelOptions } from '../panel'
import type { PanelProps, ToolDef } from '../registry'
import { focusItem, subjectPerson } from '../sel'
import { type Paint, PaintLegend, painter, type Rgba } from './mapPaint'

function MapTool({ sel, setSel, opts, setOpts }: PanelProps) {
  const u = useLens().u
  const dataVersion = useStore(s => s.dataVersion)
  const theme = useStore(s => s.theme)
  const reg = useStore(s => s.registry)!
  const name = usePersonName(u)
  const colorBy: string = opts.color ?? 'none'          // everyone the same until a field is picked to color by
  const live: LivingOpts = opts.live ?? { when: opts.mode === 'home' ? 4 : 'now' }
  const set = (o: Record<string, any>) => setOpts({ ...opts, ...o })
  const mapRef = useRef<maplibregl.Map | null>(null)
  const [prec, setPrec] = useState<Precise | null>(null)
  const [hover, setHover] = useState<{ x: number; y: number; i: number; p: Precise } | null>(null)
  const [boxing, setBoxing] = useState(false)
  const [box, setBox] = useState<{ x0: number; y0: number; x1: number; y1: number } | null>(null)

  // ---- the color field and who is selected
  const field = useAsync(async () => (colorBy === 'activity_now' || colorBy === 'none' ? null : { v: colorBy, col: (await loadColumns([colorBy], u))[colorBy] as Column }),
    [u, colorBy, dataVersion], { key: `bench-map:${u}:${colorBy}` })
  const group = useAsync(async () => (sel.filter?.length ? (await cohortMask(sel.filter, u)).mask : null), [JSON.stringify(sel.filter ?? []), u, dataVersion])
  const n = prec?.n ?? 0
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

  const paint: Paint = opts.paint?.[colorBy] ?? {}         // how this field shows, remembered per field
  const setPaint = (p: Paint) => set({ paint: { ...(opts.paint ?? {}), [colorBy]: p } })
  const base = hexRgb((live.look ?? 'clay') === 'clay' ? CLAY['--map-dot'] : cssVar('--map-dot'))
  const color = useMemo(() => {
    const other = hexRgb(cssVar('--text-muted'))
    if (colorBy === 'none') { const one: Rgba = [...base, 220]; return { fn: () => one, legend: null } }
    const col: Column | null = colorBy === 'activity_now'
      ? (prec ? { id: 'activity_now', data: prec.act, categories: prec.actNames } : null)
      : field.data?.v === colorBy ? field.data.col : null
    if (!col) return null
    return painter(col, reg.variables[colorBy], paint, base, other)
  }, [colorBy, field.data, colorBy === 'activity_now' ? prec : null, theme, live.look, JSON.stringify(paint)])

  const colorOf = useCallback((i: number) => color?.fn(i) ?? null, [color])

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
    const m = mapRef.current
    if (!box || !m || !prec) { setBox(null); return }
    const ids: number[] = []
    if (Math.abs(box.x1 - box.x0) > 4 && Math.abs(box.y1 - box.y0) > 4) {
      const x0 = Math.min(box.x0, box.x1), x1 = Math.max(box.x0, box.x1), y0 = Math.min(box.y0, box.y1), y1 = Math.max(box.y0, box.y1)
      for (let i = 0; i < prec.n; i++) {
        if (Number.isNaN(prec.lon[i]) || (group.data && !group.data[i])) continue
        const pt = m.project([prec.lon[i], prec.lat[i]])
        if (pt.x >= x0 && pt.x <= x1 && pt.y >= y0 && pt.y <= y1) ids.push(i)
      }
      setSel({ people: ids.slice(0, 20000), item: undefined })
    }
    setBox(null); setBoxing(false)
  }

  const spec = reg.variables[colorBy]
  const nSel = chosen ? chosen.reduce((s, x) => s + x, 0) : 0
  const hv = hover
  const refresh: Refresh = live.refresh ?? 'auto'
  return (
    <div className="bm">
      <PanelOptions>
        <select value={refresh} onChange={e => set({ live: { ...live, refresh: e.target.value as Refresh } })} title="How often people move on the map while time runs">
          {(Object.keys(REFRESH_WORDS) as Refresh[]).map(k => <option key={k} value={k} title={REFRESH_WORDS[k]}>{k === 'auto' ? 'Updates: automatic' : k === 'live' ? 'Updates: every part of the day' : k === 'daily' ? 'Updates: once a day' : 'Updates: when paused'}</option>)}
        </select>
      </PanelOptions>
      <LivingMap u={u} opts={live} setOpts={o => set({ live: o })} colorOf={colorOf} chosen={chosen} focus={focus}
        onPerson={i => { if (!boxing) focusItem(setSel, { kind: 'person', id: i, label: name(i) }) }} onHover={setHover} mapRef={mapRef} onFrame={setPrec}
        onOccasion={(id, label) => { focusItem(setSel, { kind: 'occasion', id, label, u }); useLayout.getState().ensure('occasion') }}>
        <VarPicker value={colorBy === 'none' ? '' : colorBy} onChange={v => set({ color: v || 'none' })} filter={s => s.id !== 'activity_now' && s.id !== 'rel_status'} placeholder="Color: none (everyone the same)" allowEmpty
          lead={[['activity_now', "Color: what they're doing"], ...(reg.variables.rel_status ? [['rel_status', 'Color: relationship status'] as [string, string]] : [])]} />
        <button className={`btn small ${boxing ? 'primary' : ''}`} onClick={() => setBoxing(!boxing)} title="Drag a rectangle on the map to select everyone inside it">{boxing ? 'Drag a box…' : '▭ Select an area'}</button>
      </LivingMap>
      {(boxing || box) && (
        <div className="bm-boxer" onPointerDown={boxStart} onPointerMove={boxMove} onPointerUp={boxEnd}>
          {box && <div className="bm-box" style={{ left: Math.min(box.x0, box.x1), top: Math.min(box.y0, box.y1), width: Math.abs(box.x1 - box.x0), height: Math.abs(box.y1 - box.y0) }} />}
        </div>
      )}
      {nSel > 0 && <div className="bm-note"><b>{nSel.toLocaleString()}</b> selected</div>}
      {color?.legend && <PaintLegend title={colorBy === 'activity_now' ? "What they're doing" : spec?.label ?? colorBy} spec={spec} legend={color.legend} paint={paint} setPaint={setPaint} base={base} />}
      {hv && (
        <div className="bm-tip" style={{ left: hv.x + 12, top: hv.y + 12 }}>
          <b>{name(hv.i)}</b><br />
          {field.data?.v === colorBy && <>{spec?.label}: {fval(spec, field.data.col.categories ? field.data.col.categories[field.data.col.data[hv.i]] : field.data.col.data[hv.i])}<br /></>}
          <small>{pretty(hv.p.actNames[hv.p.act[hv.i]] ?? '')}{hv.p.floor[hv.i] > 0 ? ` · floor ${hv.p.floor[hv.i] + 1}` : ''} · click to focus</small>
        </div>
      )}
    </div>
  )
}

export const tool: ToolDef = {
  id: 'map',
  label: 'Map',
  icon: 'map',
  hint: 'The living map: everyone in their room, at their table or in their seat, among real buildings in 3D; click a building to open it, a dot to focus, drag a box to select.',
  group: 'see',
  order: 10,
  component: MapTool,
  size: { w: 7, h: 8 },
}
