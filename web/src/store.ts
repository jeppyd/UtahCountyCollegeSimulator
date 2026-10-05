import { create } from 'zustand'
import { api, Column, STATIC, Universe } from './api'

export type Cond = {
  var?: string; op?: string; value?: any
  recent_event?: string; days?: number
  household?: Cond; share?: string
  transition?: { var: string; from?: string[]; to?: string[]; d0?: number; d1?: number }
  label?: string
}

export type VarSpec = {
  id: string; entity: string; domain: string; label: string; dtype: string; kind: string; units?: string
  range?: number[]; categories?: string[]; ordinal?: string[]; update: string; desc?: string; init?: string
  source?: string[]; evidence: string; flags?: string[]; filterable?: boolean; chartable?: boolean; mappable?: boolean
  intervenable?: boolean; group?: string
}

export type Registry = {
  evidence_levels: Record<string, string>
  variables: Record<string, VarSpec>
  mechanisms: Record<string, any>
  events: Record<string, any>
}

export type Mode = 'simple' | 'advanced'
/** Which world every page shows: the Original, the What-if, or both side by side. */
export type Lens = 'base' | 'alt' | 'compare'
export type Pin = { kind: 'field'; var: string; group?: string } | { kind: 'person'; id: number; name?: string }
export type Toast = { id: number; kind: 'event' | 'world' | 'info' | 'recap'; title: string; body?: string; category?: string; route?: string[]; ttl?: number }

function load<T>(key: string, fallback: T): T {
  try { const v = localStorage.getItem(key); return v === null ? fallback : JSON.parse(v) } catch { return fallback }
}
function save(key: string, v: any) {
  try { localStorage.setItem(key, JSON.stringify(v)) } catch { /* private mode */ }
}

type State = {
  registry: Registry | null
  mode: Mode
  following: Record<string, number[]>
  pins: Record<string, Pin[]>
  setMode: (m: Mode) => void
  toggleFollow: (id: number) => void
  followed: () => number[]
  togglePin: (p: Pin) => void
  pinned: () => Pin[]
  isPinned: (p: Pin) => boolean
  status: any
  presets: any
  route: string[]
  lens: Lens
  universe: Universe
  cohort: Cond[]
  theme: 'auto' | 'light' | 'dark'
  dataVersion: number
  colCache: Map<string, Column>
  palette: boolean
  drawer: null | { tab?: string; preset?: string }
  toasts: Toast[]
  news: boolean
  setRoute: (r: string[]) => void
  setLens: (l: Lens) => void
  setUniverse: (u: Universe) => void
  addCond: (c: Cond) => void
  removeCond: (i: number) => void
  setCohort: (c: Cond[]) => void
  setTheme: (t: 'auto' | 'light' | 'dark') => void
  refreshStatus: () => Promise<any>
  bump: () => void
  setPalette: (v: boolean) => void
  openDrawer: (d: null | { tab?: string; preset?: string }) => void
  toast: (t: Omit<Toast, 'id'>) => void
  dismiss: (id: number) => void
  setNews: (v: boolean) => void
}

function parseHash(): string[] {
  const h = window.location.hash.replace(/^#\/?/, '')
  return h ? h.split('/').map(decodeURIComponent) : ['world']
}

let toastId = 1
let statusInflight: Promise<any> | null = null
let lastBump = 0
const LIVE_REFRESH_MS = 2500
const pinKey = (p: Pin) => (p.kind === 'field' ? `f:${p.var}:${p.group ?? ''}` : `p:${p.id}`)

export const useStore = create<State>((set, get) => ({
  registry: null,
  mode: load<Mode>('ucsim-mode', 'simple'),
  following: load<Record<string, number[]>>('ucsim-following', {}),
  pins: load<Record<string, Pin[]>>('ucsim-pins', {}),
  setMode: (m) => { save('ucsim-mode', m); set({ mode: m }) },
  // followed people and pins are remembered per world (scale + seed), since ids belong to one synthesized world
  toggleFollow: (id) => {
    const key = worldKey(get().status)
    const cur = get().following[key] ?? []
    const next = { ...get().following, [key]: cur.includes(id) ? cur.filter(x => x !== id) : [...cur, id] }
    save('ucsim-following', next)
    set({ following: next })
  },
  followed: () => get().following[worldKey(get().status)] ?? [],
  togglePin: (p) => {
    const key = worldKey(get().status)
    const cur = get().pins[key] ?? []
    const k = pinKey(p)
    const next = { ...get().pins, [key]: cur.some(x => pinKey(x) === k) ? cur.filter(x => pinKey(x) !== k) : [...cur, p] }
    save('ucsim-pins', next)
    set({ pins: next })
  },
  pinned: () => get().pins[worldKey(get().status)] ?? [],
  isPinned: (p) => (get().pins[worldKey(get().status)] ?? []).some(x => pinKey(x) === pinKey(p)),
  status: null,
  presets: null,
  route: parseHash(),
  lens: 'base',
  universe: 'base',
  cohort: [],
  theme: (() => { try { return (localStorage.getItem('ucsim-theme') as any) || 'auto' } catch { return 'auto' } })(),
  dataVersion: 0,
  colCache: new Map(),
  palette: false,
  drawer: null,
  toasts: [],
  news: load<boolean>('ucsim-news', true),
  setRoute: (r) => { window.location.hash = '/' + r.map(encodeURIComponent).join('/'); set({ route: r }); document.querySelector('.main')?.scrollTo(0, 0) },
  setLens: (l) => set({ lens: l, universe: l === 'alt' ? 'alt' : 'base' }),
  setUniverse: (u) => get().setLens(u),
  addCond: (c) => set({ cohort: [...get().cohort, c] }),
  removeCond: (i) => set({ cohort: get().cohort.filter((_, k) => k !== i) }),
  setCohort: (c) => set({ cohort: c }),
  setTheme: (t) => {
    try { localStorage.setItem('ucsim-theme', t) } catch { /* private mode */ }
    if (t === 'auto') document.documentElement.removeAttribute('data-theme')
    else document.documentElement.setAttribute('data-theme', t)
    set({ theme: t })
  },
  refreshStatus: () => {
    // one status request at a time: callers that ask while one is in flight share its answer
    if (statusInflight) return statusInflight
    statusInflight = (async () => {
      const raw = await api.status()
      const prev = get().status
      // A status read that raced a simulated day comes back partial: keep the last full picture, update the job
      const s = raw.partial && prev?.day != null && prev.world_id === raw.world_id && prev.has_alt === raw.has_alt
        ? { ...prev, job: raw.job, last_job: raw.last_job } : raw
      const structural = !prev || prev.world_id !== s.world_id || prev.has_alt !== s.has_alt || prev.agents !== s.agents
        || prev.job?.state !== s.job?.state || prev.fork_day !== s.fork_day
        || JSON.stringify(prev.alt_interventions ?? []) !== JSON.stringify(s.alt_interventions ?? [])
      const moved = !!prev && (prev.day !== s.day || prev.hour !== s.hour)
      set({ status: s })
      // While time runs, pages reload their data every few seconds rather than every simulated day, so requests never
      // pile up behind the run; when the run ends (a job-state change) they reload at once.
      const now = Date.now()
      if (structural || (moved && (s.job?.state !== 'running' || now - lastBump >= LIVE_REFRESH_MS))) {
        lastBump = now
        set({ colCache: new Map(), dataVersion: get().dataVersion + 1 })
      }
      if (!s.has_alt && get().lens !== 'base') get().setLens('base')
      if (s.has_alt && ((prev && !prev.has_alt) || (!prev && STATIC))) get().setLens('compare')   // a fresh what-if (or the snapshot): show both worlds
      return s
    })().finally(() => { statusInflight = null })
    return statusInflight
  },
  bump: () => set({ colCache: new Map(), dataVersion: get().dataVersion + 1 }),
  setPalette: (v) => set({ palette: v }),
  openDrawer: (d) => set({ drawer: d }),
  toast: (t) => {
    const id = toastId++
    set({ toasts: [...get().toasts, { ...t, id }].slice(-3) })
    setTimeout(() => get().dismiss(id), t.ttl ?? 7000)
  },
  dismiss: (id) => set({ toasts: get().toasts.filter(t => t.id !== id) }),
  setNews: (v) => { save('ucsim-news', v); set({ news: v }) },
}))

window.addEventListener('hashchange', () => useStore.setState({ route: parseHash() }))

export async function loadColumns(vars: string[], u: Universe): Promise<Record<string, Column>> {
  const { colCache } = useStore.getState()
  const need = vars.filter(v => !colCache.has(`${u}:${v}`))
  if (need.length) {
    const got = await api.columns(need, u)
    for (const [k, c] of Object.entries(got)) colCache.set(`${u}:${k}`, c)
  }
  const out: Record<string, Column> = {}
  for (const v of vars) { const c = colCache.get(`${u}:${v}`); if (c) out[v] = c }
  return out
}

/** The current world lens: which universe to load data from, and whether to show both. */
export function useLens() {
  const lens = useStore(s => s.lens)
  const hasAlt = useStore(s => !!s.status?.has_alt)
  const l: Lens = hasAlt ? lens : 'base'
  return { lens: l, u: (l === 'alt' ? 'alt' : 'base') as Universe, compare: l === 'compare', hasAlt }
}

export const isStatic = STATIC

export function worldKey(status: any) { return `${status?.scale ?? '?'}-${status?.seed ?? '?'}` }
