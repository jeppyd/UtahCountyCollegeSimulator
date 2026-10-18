// The bench's layout: which tools are open, where (a 12-column grid of ~60 px rows), their own settings and, for a
// pinned panel, the selection it is frozen to. Saved per world in localStorage, since ids belong to one world.
import { create } from 'zustand'
import { getTool } from './registry'
import type { Selection } from './selection'

export type Panel = { id: string; tool: string; x: number; y: number; w: number; h: number; opts: Record<string, any>; pin?: Selection | null }
export const COLS = 12
export const MIN_W = 3, MIN_H = 3

const storeKey = (world: string) => `ucsim-bench-v1:${world}`
function read(world: string): Panel[] {
  try {
    const v = JSON.parse(localStorage.getItem(storeKey(world)) ?? '[]')
    return Array.isArray(v) ? v.filter(p => p && typeof p.tool === 'string' && Number.isFinite(p.x)) : []
  } catch { return [] }
}
function write(world: string, panels: Panel[]) {
  try { localStorage.setItem(storeKey(world), JSON.stringify(panels)) } catch { /* private mode or full */ }
}

export const collide = (a: Panel, b: Panel) => a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h

/** Settle panels on the grid: `fixed` (the one being moved) keeps its spot; every other panel rises as far as it can
 *  and moves down past whatever it would overlap (the vertical gravity of most tiling layouts, so no holes are left). */
export function settle(panels: Panel[], fixed?: string): Panel[] {
  const order = [...panels].sort((a, b) => (a.id === fixed ? -1 : b.id === fixed ? 1 : a.y - b.y || a.x - b.x))
  const out: Panel[] = []
  for (const p of order) {
    const q = { ...p, w: Math.max(MIN_W, Math.min(COLS, p.w)), h: Math.max(MIN_H, p.h) }
    q.x = Math.max(0, Math.min(COLS - q.w, q.x))
    q.y = Math.max(0, q.y)
    if (p.id !== fixed) {
      while (q.y > 0 && !out.some(o => collide({ ...q, y: q.y - 1 }, o))) q.y--
      while (out.some(o => collide(q, o))) q.y++
    }
    out.push(q)
  }
  return out
}

/** The first spot (top to bottom, left to right) where a w×h panel fits. */
export function freeSpot(panels: Panel[], w: number, h: number): { x: number; y: number } {
  for (let y = 0; y < 400; y++) for (let x = 0; x + w <= COLS; x++) {
    const probe = { id: '', tool: '', x, y, w, h, opts: {} }
    if (!panels.some(p => collide(probe, p))) return { x, y }
  }
  return { x: 0, y: panels.reduce((m, p) => Math.max(m, p.y + p.h), 0) }
}

let seq = 0
const newId = () => `p${Date.now().toString(36)}${(seq++).toString(36)}`

type LayoutState = {
  world: string
  panels: Panel[]
  /** a panel to draw attention to for a moment (just added, or already open when asked for) */
  flash: string | null
  load: (world: string) => void
  add: (tool: string, at?: { x: number; y: number }, opts?: Record<string, any>) => string
  place: (id: string, box: { x: number; y: number; w: number; h: number }) => void
  setOpts: (id: string, opts: Record<string, any>) => void
  setPin: (id: string, pin: Selection | null) => void
  duplicate: (id: string) => void
  remove: (id: string) => void
  clearAll: () => void
  /** Open a tool that follows the selection unless one is already open (then point at it). */
  ensure: (tool: string) => void
}

export const useLayout = create<LayoutState>((set, get) => {
  const commit = (panels: Panel[], flash?: string | null) => {
    write(get().world, panels)
    set(flash === undefined ? { panels } : { panels, flash })
    if (flash) setTimeout(() => { if (get().flash === flash) set({ flash: null }) }, 1400)
  }
  return {
    world: '',
    panels: [],
    flash: null,
    load: (world) => { if (world !== get().world) set({ world, panels: settle(read(world)), flash: null }) },
    add: (tool, at, opts) => {
      const t = getTool(tool)
      const w = Math.min(COLS, t?.size?.w ?? 6), h = t?.size?.h ?? 6
      const ps = get().panels
      const spot = at ? { x: Math.max(0, Math.min(COLS - w, at.x)), y: Math.max(0, at.y) } : freeSpot(ps, w, h)
      const id = newId()
      commit(settle([...ps, { id, tool, ...spot, w, h, opts: opts ?? {} }], id), id)
      return id
    },
    place: (id, box) => {
      const ps = get().panels.map(p => (p.id === id ? { ...p, ...box } : p))
      commit(settle(settle(ps, id)))
    },
    setOpts: (id, opts) => commit(get().panels.map(p => (p.id === id ? { ...p, opts } : p))),
    setPin: (id, pin) => commit(get().panels.map(p => (p.id === id ? { ...p, pin } : p))),
    duplicate: (id) => {
      const src = get().panels.find(p => p.id === id)
      if (!src) return
      const nid = newId()
      const right = src.x + 2 * src.w <= COLS
      const copy = { ...src, id: nid, x: right ? src.x + src.w : src.x, y: right ? src.y : src.y + src.h, opts: { ...src.opts } }
      commit(settle([...get().panels, copy], nid), nid)
    },
    remove: (id) => commit(settle(get().panels.filter(p => p.id !== id))),
    clearAll: () => commit([]),
    ensure: (tool) => {
      const open = get().panels.find(p => p.tool === tool && !p.pin)
      if (open) { set({ flash: open.id }); setTimeout(() => { if (get().flash === open.id) set({ flash: null }) }, 1400); return }
      get().add(tool)
    },
  }
})
