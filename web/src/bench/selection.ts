// The workbench's one shared selection: a set of people (or a filter), a time window and a focused item.
// Every tool reads it and can change it; tools may also pin their own copy (see Bench.tsx).
import { create } from 'zustand'
import type { Cond } from '../store'

export type RefKind = 'person' | 'event' | 'decision' | 'occasion' | 'tie' | 'place' | 'var' | 'institution' | 'thread'
  | 'calendar' | 'state' | 'trip'
/** A pointer to anything in the world. `id` is a number for people, events, decisions and occasions; a string otherwise
 *  (a tie is "lo-hi", a place is "complex:12" / "ward:3" / "unit:88" / "venue:5", a var is its field id). */
export type Ref = { kind: RefKind; id: string | number; label?: string; u?: 'base' | 'alt' }
export type Selection = { people?: number[]; filter?: Cond[]; time?: [number, number]; item?: Ref }

export const refKey = (r: Ref) => `${r.kind}:${r.id}`

type BenchState = {
  sel: Selection
  history: Selection[]
  setSel: (s: Partial<Selection>) => void
  /** Focus an item (what Trace, Life, Place… show). Selecting a person also makes them the selected people. */
  focus: (r: Ref) => void
  addPeople: (ids: number[]) => void
  clear: () => void
  back: () => void
}

export const useBench = create<BenchState>((set, get) => ({
  sel: {},
  history: [],
  setSel: (s) => set({ sel: { ...get().sel, ...s }, history: [...get().history.slice(-30), get().sel] }),
  focus: (r) => {
    const cur = get().sel
    const next: Selection = { ...cur, item: r }
    if (r.kind === 'person') next.people = [Number(r.id)]
    set({ sel: next, history: [...get().history.slice(-30), cur] })
  },
  addPeople: (ids) => {
    const cur = get().sel
    const have = new Set(cur.people ?? [])
    ids.forEach(i => have.add(i))
    set({ sel: { ...cur, people: [...have] }, history: [...get().history.slice(-30), cur] })
  },
  clear: () => set({ sel: {}, history: [...get().history.slice(-30), get().sel] }),
  back: () => { const h = get().history; if (h.length) set({ sel: h[h.length - 1], history: h.slice(0, -1) }) },
}))
