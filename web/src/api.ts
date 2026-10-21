// Data access layer. Live mode talks to the FastAPI server; static mode (published demo)
// reads pre-exported files under ./data/ with the same shapes.
declare const __STATIC__: boolean
export const STATIC: boolean = typeof __STATIC__ !== 'undefined' && __STATIC__

export type Universe = 'base' | 'alt'
export type Column = { id: string; data: Float32Array | Uint8Array | Int32Array; categories?: string[]; bool?: boolean; meta?: any }

// A request that hangs (a stalled server, a sleeping laptop) fails with a message instead of spinning forever.
async function j<T = any>(url: string, init?: RequestInit, timeoutMs = 120000): Promise<T> {
  const ctl = new AbortController()
  const t = setTimeout(() => ctl.abort(), timeoutMs)
  try {
    const r = await fetch(url, { ...init, signal: ctl.signal })
    if (!r.ok) {
      const txt = await r.text()
      let msg = txt.slice(0, 200)
      try { msg = JSON.parse(txt).detail ?? msg } catch { /* not JSON */ }
      throw new Error(r.status === 409 ? msg : `${r.status} ${url}: ${msg}`)
    }
    return await r.json()
  } catch (e: any) {
    if (e?.name === 'AbortError') throw new Error(`The simulator did not answer within ${Math.round(timeoutMs / 1000)} s (${url.replace(/\?.*/, '')})`)
    throw e
  } finally { clearTimeout(t) }
}
const post = (url: string, body: any) => j(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })

// ---------------------------------------------------------------- trace: causes, consequences, decisions (routes_trace.py)
export type TraceRef = { kind: string; id: string | number }
export type TraceNode = {
  key: string; kind: string; ref: TraceRef; day: number; block: number | null; minute: number | null
  people: number[]; lane: number | null; label: string; type: string; category: string; weight: number
  depth: number; more_back: number; more_fwd: number; timeless?: boolean; root?: boolean; seed?: boolean; detail: any
}
export type TraceLink = { source: string; target: string; kind: string; weight: number | null; words: string }
export type TraceGraph = {
  root: string; nodes: TraceNode[]; links: TraceLink[]; lanes: { id: number; name: string; n: number; root: boolean }[]
  range: [number, number]; today: number; start_date: string; notes: string[]
  cut: { back: number; fwd: number; cap_hits: number; max_nodes: number; fanout: number }
}
export type DecisionFactor = {
  factor: string; label: string; words: string; value: number; constraint: boolean; kind: string
  ref?: TraceRef; ref_label?: string
}
export type DecisionDetail = {
  id: number; kind: string; label: string; units: string; units_words?: string; day: number; date?: string; block: number
  agent: number; agent_name?: string; other: number | null; other_name?: string; outcome: string | number
  outcomes?: string[]; positive?: string | null; prob: number | null; base: number; total: number
  occasion: number | null; factors: DecisionFactor[]; events?: { id: number; label: string; day: number }[]
}
const liveOnly = () => { if (STATIC) throw new Error('Tracing needs the live simulator (it is not part of the static demo).') }
export const traceApi = {
  async trace(ref: string, u: Universe = 'base', dir: 'back' | 'fwd' | 'both' = 'both', depth = 3, maxNodes = 80, fanout = 8): Promise<TraceGraph> {
    liveOnly()
    return j(`/api/trace?ref=${encodeURIComponent(ref)}&u=${u}&dir=${dir}&depth=${depth}&max_nodes=${maxNodes}&fanout=${fanout}`)
  },
  async chains(o: { u?: Universe; since?: number; until?: number; filter?: any[]; people?: number[]; root?: string; maxLinks?: number; contexts?: boolean }): Promise<any> {
    liveOnly()
    const q = new URLSearchParams({ u: o.u ?? 'base', max_links: String(o.maxLinks ?? 40) })
    if (o.since !== undefined) q.set('since', String(o.since))
    if (o.until !== undefined) q.set('until', String(o.until))
    if (o.filter?.length) q.set('filter', JSON.stringify(o.filter.length === 1 ? o.filter[0] : { and: o.filter }))
    if (o.people?.length) q.set('people', o.people.join(','))
    if (o.root) q.set('root', o.root)
    if (o.contexts === false) q.set('contexts', 'false')
    return j(`/api/trace/chains?${q}`)
  },
  async decision(id: number, u: Universe = 'base'): Promise<DecisionDetail> { liveOnly(); return j(`/api/decision/${id}?u=${u}`) },
  async personDecisions(i: number, u: Universe = 'base', since?: number): Promise<any> {
    liveOnly()
    return j(`/api/person/${i}/decisions?u=${u}${since !== undefined ? `&since=${since}` : ''}`)
  },
}

// ---------------------------------------------------------------- workbench: events for a selection, venues (routes_bench.py),
// occasions, a person's day and social actions (routes_occasions.py, routes_act.py)
export type BenchEvent = {
  id: number; day: number; block: number; type: string; label: string; category: string; salience: number; value: number
  a: number; a_name: string | null; b: number | null; b_name: string | null; cause: number | null; decision: number | null; place: number | null
}
export type BenchSel = { people?: number[]; filter?: any[]; since?: number; until?: number }
const selQuery = (s: BenchSel, q: URLSearchParams) => {
  if (s.people?.length) q.set('people', s.people.join(','))
  if (s.filter?.length) q.set('filter', JSON.stringify(s.filter))
  if (s.since !== undefined) q.set('since', String(s.since))
  if (s.until !== undefined) q.set('until', String(s.until))
  return q
}
const benchOnly = () => { if (STATIC) throw new Error('The workbench needs the live simulator (it is not part of the static demo).') }
// ---------------------------------------------------------------- talk: Ask the world and Interviews (routes_talk.py)
export type TalkRef = { kind: string; id: string | number; name?: string }
export type TalkClaim = { id: string; kind: 'fact' | 'perception' | 'cause' | 'measurement' | 'belief'; subject: TalkRef; text: string; refs: TalkRef[]; value?: number; band?: string; share?: number }
export type TalkSentence = { text: string; claims: string[]; ok: boolean; reasons: string[]; refs: TalkRef[] }
export type TalkResult = {
  sentences: TalkSentence[]; removed: { text: string; reasons: string[] }[]; repaired: boolean; claims: TalkClaim[]; refs: TalkRef[]
  backend: string; seconds: number; question: string; u: Universe
  tools_used?: { tool: string; args: any; facts?: number; error?: string }[]
  person?: TalkRef; differs?: { what: string; believed: number; actual: number; gap: number; words: string; note?: string }[]
  sensitive_included?: boolean
}
export type TalkJob = { id: string; kind: string; state: 'queued' | 'running' | 'done' | 'error' | 'cancelled'; steps: { t: number; kind: string; text: string }[]
  result: TalkResult | null; error: string | null; backend: string; elapsed: number }
export type TalkStatus = { settings: { ask_backend: string; interview_backend: string; sensitive: boolean }; using: Record<'ask' | 'interview', string>
  available: Record<string, boolean>; local_model: string | null; recommended: Record<'ask' | 'interview', string> }
export const talkApi = {
  status: (): Promise<TalkStatus> => j('/api/talk/status'),
  settings: (s: Partial<TalkStatus['settings']>) => post('/api/talk/settings', s),
  ask: (question: string, mentions: { kind: string; id: string | number; label?: string }[], u: Universe = 'base'): Promise<{ job: string }> =>
    post('/api/talk/ask', { question, mentions, u }),
  interview: (i: number, question: string, history: { q: string; a: string }[], u: Universe = 'base'): Promise<{ job: string }> =>
    post(`/api/talk/interview/${i}`, { question, history, u }),
  poll: (job: string): Promise<TalkJob> => j(`/api/talk/ask/${job}`),
  cancel: (job: string): Promise<TalkJob> => post(`/api/talk/ask/${job}/cancel`, {}),
  differs: (i: number, u: Universe = 'base'): Promise<NonNullable<TalkResult['differs']>> => j(`/api/talk/differs/${i}?u=${u}`),
}

// ---------------------------------------------------------------- messaging (routes_messaging.py)
export type MsgAct = { id: number; day: number; date: string; kind: string; words: string; thread: number; sender: number; sender_name: string | null
  to: number | null; to_name: string | null; replied_day: number | null; event: number | null; read_as?: string
  occasion?: { id: number; label: string; day: number } | null; news?: any }
export type MsgThread = { id: number; kind: string; name: string; n: number; volume: number; muted: boolean; joined: number }
export const msgApi = {
  person: (i: number, u: Universe = 'base'): Promise<{ person: number; name: string; threads: MsgThread[]; acts: MsgAct[]; today: number }> =>
    j(`/api/messaging/person/${i}?u=${u}`),
  thread: (t: number, u: Universe = 'base'): Promise<{ id: number; kind: string; name: string; active: boolean; created_day: number; creator: number | null
    volume: number; members: { id: number; name: string; joined: number; left: number | null; muted: boolean }[]; acts: MsgAct[] }> =>
    j(`/api/messaging/thread/${t}?u=${u}`),
  news: (e: number, u: Universe = 'base'): Promise<{ event: any; knowers: { person: number; name: string; source: number; source_name: string | null; day: number; channel: string }[]; tracked: boolean }> =>
    j(`/api/messaging/news/${e}?u=${u}`),
}

// ---------------------------------------------------------------- institutions (routes_institutions.py)
export type InstRow = { id: number; kind: string; ref: number; name: string; capacity?: number; budget: number; hours: number; delay: number
  weekday: number; food: boolean; demand: number; served: number; waitlist: number; utilization: number }
export type InstPerson = { person: number; name: string; asked: number; crisis: boolean; waited?: number; sessions?: number }
export type InstDetail = InstRow & {
  history: { day: number; demand: number; served: number; waitlist: number; attended: number }[]
  decisions: { day: number; date: string; action: string; words: string; turnout: number; officer: number | null; officer_name: string | null; event: number | null; occasion: number | null }[]
  occasions: { id: number; day: number; date: string; label: string; came: number; status: string }[]
  members?: number; flexibility?: number
  queue?: { waiting: InstPerson[]; in_care: InstPerson[]; n_waiting: number; n_in_care: number; n_finished: number; n_gave_up: number; mean_wait_days: number | null }
}
export const instApi = {
  list: (u: Universe = 'base', kind = ''): Promise<InstRow[]> => j(`/api/institutions?u=${u}&kind=${kind}`),
  get: (id: number, u: Universe = 'base'): Promise<InstDetail> => j(`/api/institutions/${id}?u=${u}`),
  find: (kind: string, ref: number, u: Universe = 'base'): Promise<{ id: number }> => j(`/api/institutions/find?kind=${kind}&ref=${ref}&u=${u}`),
}

// ---------------------------------------------------------------- family and home states (routes_family.py)
export type FamState = { state: string; from: number; in_provo: number; at_home: number }
export type FamPerson = { person: number; home_state: string; drive_hours: number; flies: boolean; closeness: number; away: boolean; returns: number
  kin: { rel: string; age: number; alive: boolean; married: boolean; closeness: number; on_mission: boolean; ill: boolean }[]
  trips: { depart: number; return: number; reason: string; fly: boolean; decision: number; event: number; with_partner: number | null }[] }
export const famApi = {
  states: (u: Universe = 'base'): Promise<{ day: number; date: string; states: FamState[]; away: number; total: number }> => j(`/api/family/states?u=${u}`),
  state: (name: string, u: Universe = 'base', where = 'all'): Promise<{ state: string; people: number[]; n: number }> =>
    j(`/api/family/state/${encodeURIComponent(name)}?u=${u}&where=${where}`),
  person: (i: number, u: Universe = 'base'): Promise<FamPerson> => j(`/api/family/person/${i}?u=${u}`),
  geo: (): Promise<{ width: number; height: number; source: string; states: { name: string; abbr: string; d: string; cx: number; cy: number }[] }> => j(STATIC ? './geo/us_states.json' : '/geo/us_states.json'),
}

export type StoryReason = { words: string; share: number | null }
export type StoryLine = { after: string[]; by?: string | null; event: number; day: number; date: string; type: string; category: string; text: string; reasons: StoryReason[]
  because: string; chance: number | null; other: number | null; times: number; last_day: number; salience: number }
export type StoryResp = { person: number; name: string; chapters: { title: string; start: number; end: number; date: string; lines: StoryLine[] }[]; n_events: number; note: string }
export type WhyItem = { label: string; words: string; share: number; value: number; ref?: any; ref_label?: string }
export type WhyResp = { kind: string; ref: string; title: string; outcome?: string; chance: number | null; units: string; day: number | null; date: string | null
  toward: WhyItem[]; against: WhyItem[]; after?: { label: string; ref?: any; day?: number }[]; base?: number; constraint?: { label: string; words: string }; note?: string; decision?: number; other_name?: string; by?: string }
export type RippleStep = { key: string; kind: string; text: string; day: number | null; date: string | null; parent: string | null; level: number; via: string; people: number[] }
export type RippleResp = { root: string; steps: RippleStep[]; longest: number; notes: string[]; cut: any }

export const benchApi = {
  async events(s: BenchSel & { cats?: string[]; types?: string[]; q?: string; minSalience?: number; place?: number; limit?: number; offset?: number; order?: 'new' | 'old' }, u: Universe = 'base'):
    Promise<{ total: number; events: BenchEvent[]; today: number; start_date: string; n_people: number | null }> {
    benchOnly()
    const q = selQuery(s, new URLSearchParams({ u, limit: String(s.limit ?? 300), offset: String(s.offset ?? 0), order: s.order ?? 'new' }))
    if (s.cats?.length) q.set('cats', s.cats.join(','))
    if (s.types?.length) q.set('types', s.types.join(','))
    if (s.q) q.set('q', s.q)
    if (s.minSalience) q.set('min_salience', String(s.minSalience))
    if (s.place !== undefined) q.set('place', String(s.place))
    return j(`/api/bench/events?${q}`)
  },
  async density(s: BenchSel & { minSalience?: number }, u: Universe = 'base'):
    Promise<{ days: number[]; cats: string[]; counts: Record<string, number[]>; total: number; n_people: number | null; start_date: string; today: number }> {
    benchOnly()
    const q = selQuery(s, new URLSearchParams({ u }))
    if (s.minSalience) q.set('min_salience', String(s.minSalience))
    return j(`/api/bench/density?${q}`)
  },
  async venue(id: number, u: Universe = 'base'): Promise<any> { benchOnly(); return j(`/api/bench/venue/${id}?u=${u}`) },
  async occasion(id: number, u: Universe = 'base'): Promise<any> { benchOnly(); return j(`/api/occasion/${id}?u=${u}`) },
  async occasions(o: { day?: number; kind?: string; person?: number; place?: number; limit?: number }, u: Universe = 'base'): Promise<any> {
    benchOnly()
    const q = new URLSearchParams({ u, limit: String(o.limit ?? 300) })
    for (const k of ['day', 'kind', 'person', 'place'] as const) if (o[k] !== undefined) q.set(k, String(o[k]))
    return j(`/api/occasions?${q}`)
  },
  async day(i: number, day?: number, u: Universe = 'base'): Promise<any> {
    benchOnly()
    return j(`/api/person/${i}/day?u=${u}${day !== undefined ? `&day=${day}` : ''}`)
  },
  async choice(i: number, block?: number, u: Universe = 'base'): Promise<any> {
    benchOnly()
    return j(`/api/person/${i}/choice?u=${u}${block !== undefined ? `&block=${block}` : ''}`)
  },
  async actCheck(action: any): Promise<any> { benchOnly(); return post('/api/act/check', action) },
  async act(action: any): Promise<any> { benchOnly(); return post('/api/act', action) },
  // the Provo calendar and the observed weather each day replays (routes_calendar.py)
  async calendarItems(frm: number, to: number, u: Universe = 'base'): Promise<any> { benchOnly(); return j(`/api/calendar/items?u=${u}&frm=${frm}&to=${to}`) },
  async policies(u: Universe = 'base'): Promise<any> { benchOnly(); return j(`/api/policies?u=${u}`) },
  // plain-language stories over the recorded causes (routes_story.py)
  async story(i: number, u: Universe = 'base', time?: [number, number]): Promise<StoryResp> {
    benchOnly()
    const q = new URLSearchParams({ u })
    if (time) { q.set('since', String(time[0])); q.set('until', String(time[1])) }
    return j(`/api/story/person/${i}?${q}`)
  },
  async why(ref: string, u: Universe = 'base'): Promise<WhyResp> { benchOnly(); return j(`/api/story/why?u=${u}&ref=${encodeURIComponent(ref)}`) },
  async ripple(ref: string, u: Universe = 'base', depth = 6): Promise<RippleResp> { benchOnly(); return j(`/api/story/ripple?u=${u}&depth=${depth}&ref=${encodeURIComponent(ref)}`) },
  async calendarWeather(frm: number, to: number, u: Universe = 'base'): Promise<any> { benchOnly(); return j(`/api/calendar/weather?u=${u}&frm=${frm}&to=${to}`) },
}

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
  async status() { return STATIC ? j(`${D}/status.json`) : j('/api/status', undefined, 15000) },
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
  async personInner(id: number, u: Universe = 'base') {
    if (STATIC) { const p = await api.person(id, u); if (!p.inner) throw new Error('The inner life is not included in the static demo export'); return p.inner }
    return j(`/api/person/${id}/inner?u=${u}`)
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
  async pace(pace: number): Promise<{ ok: boolean }> { return post('/api/pace', { pace }) },
  async validation() { return STATIC ? j(`${D}/validation.json`) : j('/api/validation') },
  async calendar() { return STATIC ? j(`${D}/calendar.json`) : j('/api/calendar') },
  async dayFrames(u: Universe = 'base') { return STATIC ? bin(`${D}/day_frames_${u}.bin`) : bin(`/api/positions/day?u=${u}`) },
  async historyFrames(variable: string, u: Universe = 'base') {
    return STATIC ? bin(`${D}/history_frames_${u}_${variable}.bin`) : bin(`/api/history/frames?u=${u}&var=${variable}`)
  },
  // ---- the game layer: fields, the butterfly comparison, the world's pulse
  async fieldsInfo() { return STATIC ? j(`${D}/fields_info.json`) : j('/api/fields/info') },
  async fieldsSummary(u: Universe = 'base') { return STATIC ? j(`${D}/fields_summary_${u}.json`) : j(`/api/fields/summary?u=${u}`) },
  async fieldTimeline(variable: string, group = 'all') {
    if (STATIC) {
      const all = await j(`${D}/field_timelines.json`)
      const out: any = { var: variable, group, fork_day: all.fork_day }
      for (const u of ['base', 'alt']) { const t = all[u]?.[group]?.[variable]; if (t) out[u] = { days: all[u].days, n: all[u][group].n, ...t } }
      if (!out.base) throw new Error('not recorded in the snapshot')
      return out
    }
    return j(`/api/fields/timeline?var=${variable}&group=${group}`)
  },
  async compareFields() { return STATIC ? j(`${D}/compare_fields.json`) : j('/api/compare/fields') },
  async comparePeople(k = 40) { return STATIC ? j(`${D}/compare_people.json`) : j(`/api/compare/people?k=${k}`) },
  async comparePerson(id: number) {
    if (STATIC) { const all = await j(`${D}/compare_person.json`); const r = all[String(id)]; if (!r) throw new Error('not included in the snapshot'); return r }
    return j(`/api/compare/person/${id}`)
  },
  async compareRelationships() { return STATIC ? j(`${D}/compare_relationships.json`) : j('/api/compare/relationships') },
  async comparePlaces(kind: string, variable: string) {
    if (STATIC) { const all = await j(`${D}/compare_places.json`); const r = all[`${kind}:${variable}`]; if (!r) throw new Error('not included in the snapshot'); return r }
    return j(`/api/compare/places?kind=${kind}&var=${variable}`)
  },
  async personHistory(id: number) {
    if (STATIC) { const p = await api.person(id, 'base'); if (!p.history) throw new Error('not included in the snapshot'); return p.history }
    return j(`/api/person/${id}/history`)
  },
  async pulse(u: Universe = 'base') { return STATIC ? j(`${D}/pulse_${u}.json`) : j(`/api/pulse?u=${u}`) },
  async relationships(u: Universe = 'base', status = '') {
    if (STATIC) { const r = await j(`${D}/relationships_${u}.json`); return status ? { ...r, couples: r.couples.filter((c: any) => c.status === status) } : r }
    return j(`/api/relationships?u=${u}&status=${status}&limit=80`)
  },
  async searchPeople(q: string, u: Universe = 'base') { return STATIC ? [] : j(`/api/people/search?q=${encodeURIComponent(q)}&u=${u}&limit=8`) },
  async forkAdd(interventions: any[]) { return post('/api/fork/add', { interventions }) },
  async fork(interventions: any[]) { return post('/api/fork', { interventions }) },
  async unfork() { return j('/api/fork', { method: 'DELETE' }) },
  // natural-language What-ifs (an LLM through your Claude/ChatGPT subscription or a local model)
  async entities(q: string, kinds: string[] = [], limit = 12, mode: 'new' | 'add' = 'new') { return STATIC ? [] : j(`/api/entities/search?q=${encodeURIComponent(q)}&kinds=${kinds.join(',')}&limit=${limit}&mode=${mode}`) },
  async updateCheck(force = false) { return STATIC ? null : j(`/api/update/check${force ? '?force=1' : ''}`, undefined, 20000) },
  async updateStatus() { return j('/api/update/status') },
  async updateInstall() { return post('/api/update/install', {}) },
  // speed and logs (routes_perf.py)
  async perf(sinceDay?: number) { return j<PerfReply>(`/api/perf${sinceDay !== undefined ? `?since_day=${sinceDay}` : ''}`, undefined, 20000) },
  async perfEstimate(scale: number) { return STATIC ? { measured: false } : j<PerfEstimate>(`/api/perf/estimate?scale=${scale}`, undefined, 10000) },
  async logs(since = -1, level = 'info') { return j<{ lines: LogLine[]; next: number }>(`/api/logs?since=${since}&level=${level}`, undefined, 20000) },
  debugBundleUrl: '/api/debug-bundle',
  async llmLoad(body: { url: string; model: string; context_length?: number; unload_others?: boolean }) { return j('/api/whatif/llm/load', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }, 900000) },   // loading a big model takes a while
  async llmModels(url: string) { return j(`/api/whatif/llm/models?url=${encodeURIComponent(url)}`, undefined, 15000) },
  async llmStatus(refresh = false) { return STATIC ? { ready: false, settings: {} } : j(`/api/whatif/llm/status${refresh ? '?refresh=1' : ''}`, undefined, 60000) },
  async llmSettings(body: any) { return post('/api/whatif/llm/settings', body) },
  async llmTest() { return post('/api/whatif/llm/test', {}) },
  async whatifCompile(body: any) { return post('/api/whatif/compile', body) },
  async whatifJob(id: string) { return j(`/api/whatif/compile/${id}`, undefined, 30000) },
  async whatifCancel(id: string) { return post(`/api/whatif/compile/${id}/cancel`, {}) },
  async whatifValidate(plan: any, mode: 'new' | 'add' = 'new') { return post('/api/whatif/validate', { plan, mode }) },
  async whatifApply(body: any) { return post('/api/whatif/apply', body) },
  async whatifPlans() { return STATIC ? j(`${D}/whatif_plans.json`).catch(() => []) : j('/api/whatif/plans') },
  async newWorld(scale: number, seed: number, warmup = 0) { return post('/api/world', { scale, seed, warmup }) },
  async uncertaintyStart(body: any) { return post('/api/uncertainty', body) },
  async uncertainty() { return STATIC ? j(`${D}/uncertainty.json`).catch(() => ({ state: 'none' })) : j('/api/uncertainty') },
  async montecarloStart(body: any) { return post('/api/montecarlo', body) },
  async montecarlo() { return STATIC ? j(`${D}/montecarlo.json`) : j('/api/montecarlo') },
  async sweepStart(body: any) { return post('/api/sweep', body) },
  async sweep() { return STATIC ? j(`${D}/sweep.json`) : j('/api/sweep') },
  async save(notes: string) { return post('/api/save', { notes }) },
  geo(name: string) { return STATIC ? `./geo/${name}` : `/geo/${name}` },
}

// ---------------------------------------------------------------- speed and logs (routes_perf.py, ucsim/telemetry.py)
export type PerfDay = {
  day: number; date: string; weekday: string; wall_s: number; base_s: number; alt_s: number | null; parallel: boolean
  cpu_pct: number | null; rss_mb: number | null; people: number; systems: Record<string, number>
  alt_systems: Record<string, number> | null; periodic: string[]; pace: number; t: number
}
export type PerfSummary = {
  n: number; world: any; last?: Partial<PerfDay>; mean7_s?: number; days_per_min?: number | null; why_last?: string; trend?: number
}
export type PerfReply = { summary: PerfSummary; days: PerfDay[]; system_words: Record<string, string>; periodic_words: Record<string, string>; has_alt: boolean; running: boolean }
export type PerfEstimate = { measured: boolean; from_scale?: number; updated?: string; early_s?: number; later_s?: number; build_s?: number }
export type LogLine = { id: number; t: number; level: string; source: string; msg: string }
