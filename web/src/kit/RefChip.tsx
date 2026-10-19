// A clickable pointer to anything in the world (a person, an event, a night out, a place, a number…). Every workbench
// tool shows entities through RefChip, so anything can be picked anywhere: click it to select it, add it to the
// selection, trace it, or open it in the tool made for it.
import { useEffect, useRef, type ReactNode } from 'react'
import { create } from 'zustand'
import { api, type Universe } from '../api'
import { getTool } from '../bench/registry'
import { useLayout } from '../bench/layout'
import { useBench, type Ref, type RefKind } from '../bench/selection'
import { G } from '../game'
import { nameOf } from '../names'
import { useStore } from '../store'
import { refString } from './traceRefs'

// ---------------------------------------------------------------- names
// Display names are synthetic and computed from the person's number and sex (names.ts), so one small column per world
// is all it takes to name anyone.
const useSexCols = create<{ cols: Record<string, ArrayLike<number>> }>(() => ({ cols: {} }))
const asked = new Set<string>()
function sexKey(u: Universe) { const s = useStore.getState().status; return `${s?.world_id ?? '?'}:${u}:${s?.agents ?? 0}` }
function askSex(u: Universe) {
  const k = sexKey(u)
  if (asked.has(k)) return
  asked.add(k)
  api.columns(['sex'], u).then(c => { if (c.sex) useSexCols.setState(s => ({ cols: { ...s.cols, [k]: c.sex.data } })) })
    .catch(() => asked.delete(k))
}
/** A function that names people (re-renders once names are loaded). */
export function usePersonName(u: Universe = 'base'): (i: number) => string {
  const status = useStore(s => s.status)
  const k = `${status?.world_id ?? '?'}:${u}:${status?.agents ?? 0}`
  const col = useSexCols(s => s.cols[k])
  useEffect(() => { if (!col) askSex(u) }, [k, !!col])
  return (i: number) => (col && i >= 0 && i < col.length ? nameOf(i, col[i]) : `Person ${i}`)
}

// ---------------------------------------------------------------- what each kind is, and the tool that opens it
export const KIND_ICON: Record<string, string> = {
  person: 'people', event: 'events', decision: 'scale', occasion: 'coffee', tie: 'rings', place: 'places', var: 'explore',
  institution: 'places', thread: 'send', calendar: 'clock', state: 'heart', trip: 'map',
}
const KIND_WORD: Record<string, string> = {
  person: 'Person', event: 'Event', decision: 'Decision', occasion: 'Occasion', tie: 'Relationship', place: 'Place',
  var: 'Measure', institution: 'Institution', thread: 'Conversation', calendar: 'Calendar', state: 'Feeling', trip: 'Trip',
}
/** The tool made for each kind of thing (used only when that tool exists on the shelf). */
export const NATURAL: Partial<Record<RefKind, string>> = {
  person: 'life', occasion: 'occasion', place: 'place', institution: 'institution', tie: 'ties', var: 'measure',
  calendar: 'calendar', thread: 'chats', event: 'timeline', decision: 'trace', state: 'measure', trip: 'day',
}

// ---------------------------------------------------------------- the menu (one for the whole bench)
type MenuState = { open: { r: Ref; x: number; y: number } | null; show: (r: Ref, el: HTMLElement) => void; hide: () => void }
export const useRefMenu = create<MenuState>(set => ({
  open: null,
  show: (r, el) => { const b = el.getBoundingClientRect(); set({ open: { r, x: b.left, y: b.bottom + 4 } }) },
  hide: () => set({ open: null }),
}))

/** Focus a ref for the whole bench and open the tool for it (or point at the one already open). */
export function openRef(r: Ref, tool?: string) {
  useBench.getState().focus(r)
  if (tool && getTool(tool)) useLayout.getState().ensure(tool)
}

export function RefMenuHost() {
  const open = useRefMenu(s => s.open)
  const hide = useRefMenu(s => s.hide)
  const box = useRef<HTMLDivElement>(null)
  const sel = useBench(s => s.sel)
  const name = usePersonName(open?.r.u ?? 'base')
  useEffect(() => {
    if (!open) return
    const down = (e: MouseEvent) => { if (box.current && !box.current.contains(e.target as Node)) hide() }
    const key = (e: KeyboardEvent) => { if (e.key === 'Escape') hide() }
    const t = setTimeout(() => document.addEventListener('mousedown', down), 0)
    document.addEventListener('keydown', key)
    return () => { clearTimeout(t); document.removeEventListener('mousedown', down); document.removeEventListener('keydown', key) }
  }, [open])
  if (!open) return null
  const { r } = open
  const label = refLabel(r, name)
  const isPerson = r.kind === 'person'
  const first = isPerson ? label.split(' ')[0] : ''
  const inSel = isPerson && (sel.people ?? []).includes(Number(r.id))
  const traceable = refString(r, r.kind === 'var' || r.kind === 'state' ? sel.people : undefined) !== null
  const nat = NATURAL[r.kind]
  const natTool = nat && nat !== 'trace' ? getTool(nat) : undefined
  const go = (f: () => void) => () => { f(); hide() }
  const left = Math.min(open.x, window.innerWidth - 250), top = Math.min(open.y, window.innerHeight - 220)
  return (
    <div ref={box} className="refmenu" style={{ left, top }} role="menu">
      <div className="refmenu-h"><span className="refmenu-k">{KIND_WORD[r.kind] ?? r.kind}</span><b>{label}</b></div>
      <button role="menuitem" onClick={go(() => openRef(r))}>{G.pin}<span>{isPerson ? `Select ${first}` : 'Focus on this'}</span></button>
      {isPerson && !inSel && (
        <button role="menuitem" onClick={go(() => useBench.getState().addPeople([Number(r.id)]))}>{G.plus}<span>Add to the selection</span></button>
      )}
      {traceable && (
        <button role="menuitem" onClick={go(() => openRef(r, 'trace'))}>{G.link}<span>Trace: what led to it and what it led to</span></button>
      )}
      {natTool && (
        <button role="menuitem" onClick={go(() => openRef(r, natTool.id))}>{G[natTool.icon] ?? G.chevron}<span>Open in {natTool.label}</span></button>
      )}
      {isPerson && (
        <button role="menuitem" className="refmenu-quiet" onClick={go(() => useStore.getState().setRoute(['person', String(r.id)]))}>{G.id}<span>Their full page (classic view)</span></button>
      )}
    </div>
  )
}

export function refLabel(r: Ref, name: (i: number) => string) {
  if (r.label) return r.label
  if (r.kind === 'person') return name(Number(r.id))
  return `${KIND_WORD[r.kind] ?? r.kind} ${r.id}`
}

/** A pointer to anything: an icon, a name, and on click the menu above. `plain` draws it as a link inside text. */
export function RefChip({ r, plain = false, sub, title, children, className = '' }: {
  r: Ref; plain?: boolean; sub?: ReactNode; title?: string; children?: ReactNode; className?: string
}) {
  const name = usePersonName(r.u ?? 'base')
  const show = useRefMenu(s => s.show)
  const focused = useBench(s => s.sel.item)
  const on = focused && focused.kind === r.kind && String(focused.id) === String(r.id)
  const label = children ?? refLabel(r, name)
  return (
    <button type="button" className={`refchip ${plain ? 'plain' : ''} k-${r.kind} ${on ? 'on' : ''} ${className}`}
      title={title ?? `${KIND_WORD[r.kind] ?? r.kind}: click to select, trace or open`}
      onClick={e => { e.stopPropagation(); show(r, e.currentTarget) }}>
      {!plain && <span className="refchip-i">{G[KIND_ICON[r.kind] ?? 'events']}</span>}
      <span className="refchip-l">{label}</span>
      {sub && <small className="refchip-s">{sub}</small>}
    </button>
  )
}
