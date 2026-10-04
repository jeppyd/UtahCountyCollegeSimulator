// Data access layer. Live mode talks to the FastAPI server; static mode (published demo)
// reads pre-exported files under ./data/ with the same shapes.
declare const __STATIC__: boolean
export const STATIC: boolean = typeof __STATIC__ !== 'undefined' && __STATIC__

export type Universe = 'base' | 'alt'
export type Column = { id: string; data: Float32Array | Uint8Array | Int32Array; categories?: string[]; bool?: boolean; meta?: any }

async function j<T = any>(url: string, init?: RequestInit): Promise<T> {
  const r = await fetch(url, init)
  if (!r.ok) throw new Error(`${r.status} ${url}: ${(await r.text()).slice(0, 200)}`)
  return r.json()
}
const post = (url: string, body: any) => j(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })

export function decodePack(buf: ArrayBuffer): Record<string, Column> {
  const dv = new DataView(buf)
  const hlen = dv.getUint32(0, true)
  const header = JSON.parse(new TextDecoder().decode(new Uint8Array(buf, 4, hlen)))
  const base = 4 + hlen
  const out: Record<string, Column> = {}
  for (const c of header.columns) {
    const off = base + c.offset
    let data: Float32Array | Uint8Array | Int32Array
    if (c.dtype === 'f32') data = new Float32Array(buf.slice(off, off + c.length * 4))
    else if (c.dtype === 'i32') data = new Int32Array(buf.slice(off, off + c.length * 4))
    else data = new Uint8Array(buf.slice(off, off + c.length))
    out[c.id] = { id: c.id, data, categories: c.categories, bool: c.bool, meta: c }
  }
  return out
}

// Static hosts may refuse raw binary files, so the static export ships each .bin as base64 text (.bin.txt).
export async function fetchBytes(url: string): Promise<ArrayBuffer> {
  if (STATIC && url.endsWith('.bin')) {
    const r = await fetch(url + '.txt')
    if (!r.ok) throw new Error(`${r.status} ${url}`)
    const s = atob((await r.text()).trim())
    const out = new Uint8Array(s.length)
    for (let i = 0; i < s.length; i++) out[i] = s.charCodeAt(i)
    return out.buffer
  }
  const r = await fetch(url)
  if (!r.ok) throw new Error(`${r.status} ${url}`)
  return r.arrayBuffer()
}

async function bin(url: string) {
  return decodePack(await fetchBytes(url))
}

// ---------------------------------------------------------------- static helpers
const D = './data'
let staticIndex: any = null
async function sindex() {
  if (!staticIndex) staticIndex = await j(`${D}/index.json`)
  return staticIndex
}
const bundleCache = new Map<string, Promise<Record<string, Column>>>()
function bundle(path: string) {
  if (!bundleCache.has(path)) bundleCache.set(path, bin(path))
  return bundleCache.get(path)!
}

export const api = {
  async status() { return STATIC ? j(`${D}/status.json`) : j('/api/status') },
  async registry() { return STATIC ? j(`${D}/registry.json`) : j('/api/registry') },
  async presets() { return STATIC ? j(`${D}/presets.json`) : j('/api/interventions/presets') },

  async columns(vars: string[], u: Universe = 'base'): Promise<Record<string, Column>> {
    if (!vars.length) return {}
    if (STATIC) {
      const idx = await sindex()
      const out: Record<string, Column> = {}
      const files = new Set<string>()
      for (const v of vars) if (idx.columns[v]) files.add(idx.columns[v])
      for (const f of files) {
        const b = await bundle(`${D}/cols/${u}/${f}`)
        for (const v of vars) if (b[v]) out[v] = b[v]
      }
      return out
    }
    return bin(`/api/columns?vars=${encodeURIComponent(vars.join(','))}&u=${u}`)
  },
  async positions(u: Universe = 'base', mode: 'now' | 'home' = 'now') {
    return STATIC ? bin(`${D}/positions_${u}_${mode}.bin`) : bin(`/api/positions?u=${u}&mode=${mode}`)
  },
  async person(id: number, u: Universe = 'base') {
    if (STATIC) {
      const idx = await sindex()
      const shard = idx.people[String(id)]
      if (shard === undefined) throw new Error('This person is not included in the static demo export')
      const s = await j(`${D}/people/${shard}.json`)
      return s[String(id)]
    }
    return j(`/api/person/${id}?u=${u}`)
  },
  async personNetwork(id: number, u: Universe = 'base') {
    if (STATIC) { const p = await api.person(id, u); return p.network_full ?? p.network }
    return j(`/api/person/${id}/network?u=${u}`)
  },
  async staticPeople(): Promise<number[]> {
    if (!STATIC) return []
    const idx = await sindex()
    return Object.keys(idx.people).map(Number)
  },
  async events(params: Record<string, any> = {}) {
    if (STATIC) {
      const all = await j(`${D}/events.json`)
      let ev = all.events as any[]
      if (params.type) { const ts = String(params.type).split(','); ev = ev.filter(e => ts.includes(e.type)) }
      if (params.agent !== undefined && params.agent >= 0) ev = ev.filter(e => e.a === params.agent || e.b === params.agent)
      if (params.min_salience) ev = ev.filter(e => e.salience >= params.min_salience)
      const off = params.offset ?? 0, lim = params.limit ?? 200
      return { total: ev.length, events: ev.slice(off, off + lim) }
    }
    const q = new URLSearchParams(Object.entries(params).map(([k, v]) => [k, String(v)]))
    return j(`/api/events?${q}`)
  },
  async eventsSummary(u: Universe = 'base', since?: number) { return STATIC ? j(`${D}/events_summary_${u}.json`) : j(`/api/events/summary?u=${u}${since !== undefined ? `&since=${since}` : ''}`) },
  async featured(u: Universe = 'base') {
    if (STATIC) { try { return await j(`${D}/featured_${u}.json`) } catch { return [] } }
    return j(`/api/people/featured?u=${u}`)
  },
  async brief(ids: number[], u: Universe = 'base') {
    if (!ids.length) return []
    if (STATIC) {
      const out: any[] = []
      for (const id of ids) { try { const p = await api.person(id, u); out.push({ id, name: p.name, headline: p.headline, present: true, events: (p.timeline ?? []).slice(-3).reverse() }) } catch { /* not exported */ } }
      return out
    }
    return j(`/api/people/brief?ids=${ids.join(',')}&u=${u}`)
  },
  async event(id: number) {
    if (STATIC) {
      const all = await j(`${D}/events.json`)
      const e = (all.events as any[]).find(x => x.id === id)
      if (!e) throw new Error('event not in static export')
      return { event: e, ancestors: e.ancestors ?? [], descendants: e.descendants ?? [] }
    }
    return j(`/api/event/${id}`)
  },
  async timeseries(vars: string[], group = 'all') {
    if (STATIC) {
      const t = await j(`${D}/timeseries.json`)
      const out: any = {}
      for (const u of ['base', 'alt']) {
        const g = t[u]?.[group]
        if (!g) continue
        out[u] = { day: g.day }
        for (const v of vars) if (g[v]) out[u][v] = g[v]
      }
      return out
    }
    return j(`/api/timeseries?vars=${encodeURIComponent(vars.join(','))}&group=${group}`)
  },
  async timeseriesColumns(): Promise<string[]> {
    if (STATIC) { const t = await j(`${D}/timeseries.json`); return t.columns }
    return j('/api/timeseries/columns')
  },
  async terms(state: string, group = 'all') {
    if (STATIC) { const t = await j(`${D}/terms.json`); const out: any = {}; for (const u of ['base', 'alt']) { const g = t[u]?.[group]; if (g) { out[u] = { day: g.day }; for (const k of Object.keys(g)) if (k.startsWith(state + '.')) out[u][k] = g[k] } } return out }
    return j(`/api/terms?state=${state}&group=${group}`)
  },
  async compare() { return STATIC ? j(`${D}/compare.json`) : j('/api/compare') },
  async causalGraph() { return STATIC ? j(`${D}/causal_graph.json`) : j('/api/causal_graph') },
  async complexes(variable: string, u: Universe = 'base') {
    if (STATIC) {
      const c = await j(`${D}/complexes_${u}.json`)
      return (c.rows as any[]).map(r => ({ ...r, mean: r.means[variable] ?? null }))
    }
    return j(`/api/places/complexes?var=${variable}&u=${u}`)
  },
  async wards(variable: string, u: Universe = 'base') {
    if (STATIC) { const c = await j(`${D}/wards_${u}.json`); return (c.rows as any[]).map(r => ({ ...r, mean: r.means[variable] ?? null })) }
    return j(`/api/places/wards?var=${variable}&u=${u}`)
  },
  async venues() { return STATIC ? j(`${D}/venues.json`) : j('/api/places/venues') },
  async institution(kind: string, id: number, u: Universe = 'base') {
    if (STATIC) { const all = await j(`${D}/institutions_${u}.json`); const r = all[`${kind}:${id}`]; if (!r) throw new Error('not in static export'); return r }
    return j(`/api/institution/${kind}/${id}?u=${u}`)
  },
  async networkSample(filter: any | null, minStage = 3, maxNodes = 1500, u: Universe = 'base', tie = '') {
    if (STATIC) return j(`${D}/network_sample_${u}.json`)
    return j(`/api/network/sample?u=${u}&min_stage=${minStage}&max_nodes=${maxNodes}&tie=${tie}&filter=${encodeURIComponent(filter ? JSON.stringify(filter) : '')}`)
  },
  async origins(romantic = false, u: Universe = 'base') {
    if (STATIC) return j(`${D}/origins_${romantic ? 'romantic' : 'friends'}_${u}.json`)
    return j(`/api/relationship_origins?u=${u}&romantic=${romantic}`)
  },
  async cohortExplain(filter: any, variable: string, u: Universe = 'base') {
    if (STATIC) throw new Error('static')
    return post('/api/cohort/explain', { filter, var: variable, u })
  },
  async historyInfo(u: Universe = 'base') { return STATIC ? j(`${D}/history_info_${u}.json`) : j(`/api/history/info?u=${u}`) },
  async flows(body: any) {
    if (STATIC) { const all = await j(`${D}/flows_${body.u ?? 'base'}.json`); const f = all[body.var]; if (!f) throw new Error('not in static export'); return f }
    return post('/api/flows', body)
  },
  async cohortTimeline(body: any) {
    if (STATIC) throw new Error('Group trajectories need the app (not available in the read-only snapshot)')
    return post('/api/cohort_timeline', body)
  },
  async cohortServer(filter: any, u: Universe = 'base') { return post('/api/cohort/count', { filter, u, max_ids: 1e9 }) },
  async step(body: any) { return post('/api/step', body) },
  async cancel() { return post('/api/cancel', {}) },
  async validation() { return STATIC ? j(`${D}/validation.json`) : j('/api/validation') },
  async calendar() { return STATIC ? j(`${D}/calendar.json`) : j('/api/calendar') },
  async dayFrames(u: Universe = 'base') { return STATIC ? bin(`${D}/day_frames_${u}.bin`) : bin(`/api/positions/day?u=${u}`) },
  async historyFrames(variable: string, u: Universe = 'base') {
    return STATIC ? bin(`${D}/history_frames_${u}_${variable}.bin`) : bin(`/api/history/frames?u=${u}&var=${variable}`)
  },
  async fork(interventions: any[]) { return post('/api/fork', { interventions }) },
  async unfork() { return j('/api/fork', { method: 'DELETE' }) },
  async newWorld(scale: number, seed: number, warmup = 0) { return post('/api/world', { scale, seed, warmup }) },
  async montecarloStart(body: any) { return post('/api/montecarlo', body) },
  async montecarlo() { return STATIC ? j(`${D}/montecarlo.json`) : j('/api/montecarlo') },
  async sweepStart(body: any) { return post('/api/sweep', body) },
  async sweep() { return STATIC ? j(`${D}/sweep.json`) : j('/api/sweep') },
  async save(notes: string) { return post('/api/save', { notes }) },
  geo(name: string) { return STATIC ? `./geo/${name}` : `/geo/${name}` },
}
