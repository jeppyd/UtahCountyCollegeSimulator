// The workbench: a shelf of raw tools and an empty bench you lay them out on. Tools share one selection (people or a
// group, a time window, a focused item); a panel can be pinned to keep showing what it shows now. Nothing is laid out
// for you: the layout is yours and is saved for this world.
import { Component, memo, useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState, type ReactNode, type PointerEvent as RPointerEvent } from 'react'
import { G } from '../game'
import { RefMenuHost, usePersonName } from '../kit/RefChip'
import { useWorldDays, dayWords } from '../kit/Bits'
import { useStore, worldKey } from '../store'
import { COLS, MIN_H, MIN_W, settle, useLayout, type Panel } from './layout'
import { PanelSlot } from './panel'
import { allTools, getTool, type ToolDef, type ToolGroup } from './registry'
import { describeSel } from './sel'
import { SelectionBar } from './SelectionBar'
import { useBench, type Selection } from './selection'
import './bench.css'
import './tools.css'

const GAP = 12, ROW = 60
const GROUPS: { id: ToolGroup; label: string }[] = [
  { id: 'see', label: 'Look' }, { id: 'people', label: 'People and lives' }, { id: 'places', label: 'Places and occasions' },
  { id: 'trace', label: 'Causes and chains' }, { id: 'world', label: 'Change and compare' }, { id: 'talk', label: 'Talk' },
]
const DRAG_TYPE = 'application/x-ucsim-tool'

type Box = { x: number; y: number; w: number; h: number }
type Drag = { id: string; mode: 'move' | 'resize'; sx: number; sy: number; b0: Box; box: Box; dx: number; dy: number }

export default function Bench() {
  const status = useStore(s => s.status)
  const world = worldKey(status)
  const { panels, load, add, place, flash } = useLayout()
  useEffect(() => { load(world) }, [world])
  const grid = useRef<HTMLDivElement>(null)
  const [W, setW] = useState(1000)
  useLayoutEffect(() => {
    if (!grid.current) return
    const ro = new ResizeObserver(() => setW(grid.current?.clientWidth ?? 1000))
    ro.observe(grid.current)
    setW(grid.current.clientWidth)
    return () => ro.disconnect()
  }, [])
  const colW = Math.max(20, (W - GAP * (COLS - 1)) / COLS)
  const px = (b: Box) => ({ left: b.x * (colW + GAP), top: b.y * (ROW + GAP), width: b.w * colW + (b.w - 1) * GAP, height: b.h * ROW + (b.h - 1) * GAP })

  // ---- moving and resizing with the pointer (snap to the grid; the others make room)
  const [drag, setDrag] = useState<Drag | null>(null)
  const dragRef = useRef<Drag | null>(null)
  dragRef.current = drag
  const startDrag = useCallback((id: string, mode: 'move' | 'resize', e: RPointerEvent) => {
    const p = useLayout.getState().panels.find(q => q.id === id)
    if (!p || e.button !== 0) return
    e.preventDefault()
    const b0 = { x: p.x, y: p.y, w: p.w, h: p.h }
    setDrag({ id, mode, sx: e.clientX, sy: e.clientY, b0, box: b0, dx: 0, dy: 0 })
  }, [])
  useEffect(() => {
    if (!drag) return
    const move = (e: PointerEvent) => {
      const d = dragRef.current
      if (!d) return
      const dx = e.clientX - d.sx, dy = e.clientY - d.sy
      const cx = colW + GAP, cy = ROW + GAP
      const box = d.mode === 'move'
        ? { ...d.b0, x: Math.max(0, Math.min(COLS - d.b0.w, Math.round(d.b0.x + dx / cx))), y: Math.max(0, Math.round(d.b0.y + dy / cy)) }
        : { ...d.b0, w: Math.max(MIN_W, Math.min(COLS - d.b0.x, Math.round(d.b0.w + dx / cx))), h: Math.max(MIN_H, Math.round(d.b0.h + dy / cy)) }
      setDrag({ ...d, dx, dy, box })
    }
    const up = () => {
      const d = dragRef.current
      if (d && (d.box.x !== d.b0.x || d.box.y !== d.b0.y || d.box.w !== d.b0.w || d.box.h !== d.b0.h)) place(d.id, d.box)
      setDrag(null)
    }
    window.addEventListener('pointermove', move)
    window.addEventListener('pointerup', up, { once: true })
    return () => { window.removeEventListener('pointermove', move); window.removeEventListener('pointerup', up) }
  }, [!!drag, colW])

  // while dragging, the others settle around where the panel would land
  const shown: Panel[] = useMemo(() => {
    if (!drag) return panels
    return settle(panels.map(p => (p.id === drag.id ? { ...p, ...drag.box } : p)), drag.id)
  }, [panels, drag?.box.x, drag?.box.y, drag?.box.w, drag?.box.h, drag?.id])
  const bottom = shown.reduce((m, p) => Math.max(m, p.y + p.h), 0)

  // ---- dropping a tool from the shelf
  const [dropAt, setDropAt] = useState<Box | null>(null)
  const cellAt = (e: React.DragEvent, tool?: ToolDef) => {
    const r = grid.current!.getBoundingClientRect()
    const w = Math.min(COLS, tool?.size?.w ?? 6), h = tool?.size?.h ?? 6
    const x = Math.max(0, Math.min(COLS - w, Math.round((e.clientX - r.left) / (colW + GAP) - w / 2)))
    const y = Math.max(0, Math.round((e.clientY - r.top) / (ROW + GAP) - 0.5))
    return { x, y, w, h }
  }
  const dragTool = useRef<string | null>(null)

  return (
    <div className="bench">
      <Shelf onDragTool={t => { dragTool.current = t }} />
      <section className="bench-main">
        <SelectionBar />
        <div ref={grid} className={`bench-grid ${drag ? 'dragging' : ''}`} style={{ height: Math.max(bottom + 6, 10) * (ROW + GAP) }}
          onDragOver={e => { if (e.dataTransfer.types.includes(DRAG_TYPE)) { e.preventDefault(); setDropAt(cellAt(e, getTool(dragTool.current ?? ''))) } }}
          onDragLeave={e => { if (e.target === grid.current) setDropAt(null) }}
          onDrop={e => {
            const id = e.dataTransfer.getData(DRAG_TYPE)
            setDropAt(null)
            if (!id || !getTool(id)) return
            e.preventDefault()
            const c = cellAt(e, getTool(id))
            add(id, { x: c.x, y: c.y })
          }}>
          {!panels.length && <EmptyBench />}
          {drag && <div className="bench-ghost" style={px(drag.box)} />}
          {dropAt && <div className="bench-ghost drop" style={px(dropAt)} />}
          {shown.map(p => {
            const d = drag?.id === p.id ? drag : null
            const base = px(d ? d.b0 : p)
            const style = d
              ? (d.mode === 'move' ? { ...base, transform: `translate(${d.dx}px, ${d.dy}px)` } : { ...base, width: Math.max(80, base.width + d.dx), height: Math.max(80, base.height + d.dy) })
              : base
            return <PanelView key={p.id} p={p} style={style} lifted={!!d} flash={flash === p.id} startDrag={startDrag} />
          })}
        </div>
      </section>
      <RefMenuHost />
    </div>
  )
}

// ---------------------------------------------------------------- the shelf
function Shelf({ onDragTool }: { onDragTool: (t: string | null) => void }) {
  const [closed, setClosed] = useState<boolean>(() => { try { return localStorage.getItem('ucsim-shelf') === 'closed' } catch { return false } })
  const add = useLayout(s => s.add)
  const panels = useLayout(s => s.panels)
  const clearAll = useLayout(s => s.clearAll)
  const tools = allTools()
  const toggle = () => { const v = !closed; setClosed(v); try { localStorage.setItem('ucsim-shelf', v ? 'closed' : 'open') } catch { /* private */ } }
  return (
    <aside className={`shelf ${closed ? 'closed' : ''}`} aria-label="Tools">
      <div className="shelf-head">
        {!closed && <b>Tools</b>}
        <button className="bx-icon" onClick={toggle} title={closed ? 'Show the tool shelf' : 'Fold the shelf away'} aria-label="Toggle the shelf">
          <span style={{ display: 'inline-flex', transform: closed ? 'none' : 'rotate(180deg)' }}>{G.chevron}</span>
        </button>
      </div>
      {!closed && <p className="shelf-guide">Click a tool or drag it onto the bench. All tools share one selection.</p>}
      <div className="shelf-list">
        {GROUPS.map(g => {
          const ts = tools.filter(t => t.group === g.id)
          if (!ts.length) return null
          return (
            <div key={g.id} className="shelf-group">
              {!closed && <div className="shelf-g">{g.label}</div>}
              {ts.map(t => (
                <button key={t.id} className="shelf-tool" draggable title={closed ? `${t.label}: ${t.hint}` : 'Click to add, or drag onto the bench'}
                  onClick={() => add(t.id)}
                  onDragStart={e => { e.dataTransfer.setData(DRAG_TYPE, t.id); e.dataTransfer.effectAllowed = 'copy'; onDragTool(t.id) }}
                  onDragEnd={() => onDragTool(null)}>
                  <span className="shelf-i">{G[t.icon] ?? G.spark}</span>
                  {!closed && <span className="shelf-t"><b>{t.label}</b><small>{t.hint}</small></span>}
                </button>
              ))}
            </div>
          )
        })}
      </div>
      {!closed && panels.length > 0 && (
        <button className="shelf-clear" onClick={() => { if (window.confirm('Take every tool off the bench? (The world is not changed.)')) clearAll() }}>Clear the bench</button>
      )}
    </aside>
  )
}

function EmptyBench() {
  return (
    <div className="bench-empty">
      <div className="bench-empty-in">
        <b>An empty bench.</b>
        <p>Take a tool from the shelf — click it, or drag it here — and arrange tools any way you like: move a panel by its title,
          resize it by its corner. Pick someone on the Map or in People and every tool follows; Trace shows what led to anything and what it led to.</p>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------- one panel
const PanelView = memo(function PanelView({ p, style, lifted, flash, startDrag }: {
  p: Panel; style: React.CSSProperties; lifted: boolean; flash: boolean
  startDrag: (id: string, mode: 'move' | 'resize', e: RPointerEvent) => void
}) {
  const tool = getTool(p.tool)
  const shared = useBench(s => (p.pin ? null : s.sel))
  const { setPin, setOpts, duplicate, remove } = useLayout.getState()
  const status = useStore(s => s.status)
  const reg = useStore(s => s.registry)
  const name = usePersonName()
  const { start } = useWorldDays()
  const [slot, setSlot] = useState<HTMLElement | null>(null)
  const el = useRef<HTMLDivElement>(null)
  const pinRef = useRef(p.pin)
  pinRef.current = p.pin
  useEffect(() => { if (flash) el.current?.scrollIntoView({ block: 'nearest', behavior: 'smooth' }) }, [flash])
  const sel: Selection = p.pin ?? shared ?? {}
  const setSel = useCallback((s: Partial<Selection>) => {
    if (pinRef.current) setPin(p.id, { ...pinRef.current, ...s })
    else useBench.getState().setSel(s)
  }, [p.id])
  const setO = useCallback((o: Record<string, any>) => setOpts(p.id, o), [p.id])
  const what = p.pin ? `pinned: ${describeSel(p.pin, name, reg, d => dayWords(start, d))}` : 'following the selection'
  const togglePin = () => setPin(p.id, p.pin ? null : { ...useBench.getState().sel })
  const grab = (e: RPointerEvent) => {
    const t = e.target as HTMLElement
    if (t.closest('button, input, select, textarea, a, label, .bp-opts')) return
    startDrag(p.id, 'move', e)
  }
  if (!tool) {
    return (
      <div className="bp" style={style}>
        <header className="bp-h" onPointerDown={grab}><span className="bp-name">A tool that is no longer on the shelf</span><span className="spacer" />
          <button className="bx-icon" onClick={() => remove(p.id)} title="Close">{G.close}</button></header>
        <div className="bp-body"><div className="bx-empty">“{p.tool}” isn't available in this version. Close this panel.</div></div>
      </div>
    )
  }
  return (
    <div ref={el} className={`bp ${lifted ? 'lifted' : ''} ${flash ? 'flash' : ''} ${p.pin ? 'pinned' : ''}`} style={style} data-tool={tool.id}>
      <header className="bp-h" onPointerDown={grab} title="Drag to move">
        <span className="bp-i">{G[tool.icon] ?? G.spark}</span>
        <span className="bp-name">{tool.label}</span>
        <span className={`bp-what ${p.pin ? 'on' : ''}`} title={what}>{what}</span>
        <span className="bp-opts" ref={setSlot} />
        <button className={`bx-icon ${p.pin ? 'on' : ''}`} onClick={togglePin} aria-pressed={!!p.pin}
          title={p.pin ? 'Unpin: follow the shared selection again' : 'Pin: keep showing what this shows now, whatever is selected next'}>{G.pin}</button>
        <button className="bx-icon" onClick={() => duplicate(p.id)} title="Duplicate this panel">{G.plus}</button>
        <button className="bx-icon" onClick={() => remove(p.id)} title="Close">{G.close}</button>
      </header>
      <div className="bp-body">
        <PanelSlot.Provider value={slot}>
          <PanelBoundary tool={tool.label}>
            <ToolBody C={tool.component} sel={sel} setSel={setSel} panelId={p.id} opts={p.opts} setOpts={setO} world={status?.world_id} />
          </PanelBoundary>
        </PanelSlot.Provider>
      </div>
      <div className="bp-resize" onPointerDown={e => startDrag(p.id, 'resize', e)} title="Drag to resize" />
    </div>
  )
})

/** The tool itself, re-rendered only when what it shows changes (not while other panels move). */
const ToolBody = memo(function ToolBody({ C, sel, setSel, panelId, opts, setOpts }: {
  C: ToolDef['component']; sel: Selection; setSel: (s: Partial<Selection>) => void; panelId: string
  opts: Record<string, any>; setOpts: (o: Record<string, any>) => void; world: any
}) {
  return <C sel={sel} setSel={setSel} panelId={panelId} opts={opts} setOpts={setOpts} />
})

/** One broken tool never blanks the bench. */
class PanelBoundary extends Component<{ tool: string; children: ReactNode }, { err: string | null }> {
  state = { err: null as string | null }
  static getDerivedStateFromError(e: any) { return { err: String(e?.message ?? e) } }
  componentDidCatch(e: any) { console.error(e) }
  render() {
    if (!this.state.err) return this.props.children
    return (
      <div className="bx-problem">
        {this.props.tool} hit a problem: {this.state.err}
        <div><button className="btn small" onClick={() => this.setState({ err: null })}>Try again</button></div>
      </div>
    )
  }
}
