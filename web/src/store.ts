import { create } from 'zustand'
import { api, Column, STATIC, Universe } from './api'

export type Cond = {
  var?: string; op?: string; value?: any
  recent_event?: string; days?: number
  household?: Cond; share?: string
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

type State = {
  registry: Registry | null
  status: any
  presets: any
  route: string[]
  universe: Universe
  cohort: Cond[]
  theme: 'auto' | 'light' | 'dark'
  dataVersion: number
  colCache: Map<string, Column>
  setRoute: (r: string[]) => void
  setUniverse: (u: Universe) => void
  addCond: (c: Cond) => void
  removeCond: (i: number) => void
  setCohort: (c: Cond[]) => void
  setTheme: (t: 'auto' | 'light' | 'dark') => void
  refreshStatus: () => Promise<any>
  bump: () => void
}

function parseHash(): string[] {
  const h = window.location.hash.replace(/^#\/?/, '')
  return h ? h.split('/') : ['overview']
}

export const useStore = create<State>((set, get) => ({
  registry: null,
  status: null,
  presets: null,
  route: parseHash(),
  universe: 'base',
  cohort: [],
  theme: (() => { try { return (localStorage.getItem('ucsim-theme') as any) || 'auto' } catch { return 'auto' } })(),
  dataVersion: 0,
  colCache: new Map(),
  setRoute: (r) => { window.location.hash = '/' + r.join('/'); set({ route: r }) },
  setUniverse: (u) => set({ universe: u }),
  addCond: (c) => set({ cohort: [...get().cohort, c] }),
  removeCond: (i) => set({ cohort: get().cohort.filter((_, k) => k !== i) }),
  setCohort: (c) => set({ cohort: c }),
  setTheme: (t) => {
    try { localStorage.setItem('ucsim-theme', t) } catch { /* private mode */ }
    if (t === 'auto') document.documentElement.removeAttribute('data-theme')
    else document.documentElement.setAttribute('data-theme', t)
    set({ theme: t })
  },
  refreshStatus: async () => {
    const s = await api.status()
    const prev = get().status
    const changed = !prev || prev.world_id !== s.world_id || prev.day !== s.day || prev.hour !== s.hour || prev.has_alt !== s.has_alt || prev.agents !== s.agents
    set({ status: s })
    if (changed) set({ colCache: new Map(), dataVersion: get().dataVersion + 1 })
    if (!s.has_alt && get().universe === 'alt') set({ universe: 'base' })
    return s
  },
  bump: () => set({ colCache: new Map(), dataVersion: get().dataVersion + 1 }),
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

export const isStatic = STATIC
