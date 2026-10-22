// The World: the landing page. A living map of yesterday, the news, what's moving, lives to follow,
// your pinned board, the two worlds, and things to try.
import { useEffect, useMemo, useRef, useState } from 'react'
import { api, STATIC } from '../api'
import { cssVar } from '../components'
import { DRAWERS, drawerOf, favg, fdelta, fpair, pairs, pctStr, polarity, pretty, sizeWord } from '../fields'
import { CatIcon, DeltaChip, G, Spark, Ticker, UBadge, useAsync, whatifKey } from '../game'
import { timeCtl } from '../hud'
import { Cond, Pin, useLens, useStore } from '../store'
import { CATEGORY_LABEL, FollowButton, Story } from '../ui'

const BLOCK_LABEL = ['8 am · classes and work', '1 pm · afternoon', '6 pm · evenings out', 'Night · home']
const WEEK_KEYS: [string, string, string][] = [
  ['first_date', 'first dates', 'romance'], ['relationship_started', 'new exclusive couples', 'romance'], ['engaged', 'engagements', 'romance'], ['wedding', 'weddings', 'family'],
  ['breakup_received', 'breakups', 'romance'], ['new_friend', 'new friendships', 'social'], ['close_friend', 'close friendships', 'social'], ['baptized', 'baptisms', 'religion'],
  ['faith_crisis_start', 'faith crises', 'religion'], ['mission_departure', 'mission departures', 'religion'], ['graduation', 'graduations', 'academics'], ['birth', 'babies', 'family'],
  ['moved', 'moves', 'housing'], ['job_loss', 'jobs lost', 'work'],
]
const QUICK_TRY = ['rent_up_20', 'new_dating_app', 'coffee_permitted', 'marriage_norm_weaker', 'mission_participation_minus_15', 'interfaith_welcome']

type Q = { q: string; how: string; cohort?: Cond[]; route: string[] }
const CURIOSITIES: Q[] = [
  { q: 'Who is lonely, and why?', how: 'The loneliest 20%, the forces behind it, and example lives', cohort: [{ var: 'loneliness', op: 'quantile_ge', value: 0.8 }], route: ['explore', 'loneliness'] },
  { q: 'How do couples meet?', how: 'Where every romance began', route: ['relationships'] },
  { q: 'Does church activity change how often singles date?', how: 'Dates per month for singles, by activity', cohort: [{ var: 'rel_status', op: 'in', value: ['single', 'talking'] }], route: ['explore', 'dates_30d', 'activity'] },
  { q: 'What is life like for students of other faiths?', how: 'Belonging by religious affiliation', route: ['explore', 'belonging', 'affiliation'] },
  { q: 'Which apartment complexes are loneliest?', how: 'Complexes on the map, colored by loneliness', route: ['map', 'complexes:loneliness'] },
  { q: 'Who is struggling financially?', how: 'Money stress by school and situation', route: ['explore', 'financial_stress', 'living'] },
  { q: 'Who is drifting from church activity?', how: 'Flows between active, less active and inactive', route: ['flows', 'activity'] },
  { q: 'What does a breakup do to someone?', how: 'People broken up with in the last 90 days', cohort: [{ recent_event: 'breakup_received', days: 90 }], route: ['explore', 'mood'] },
]

export default function World() {
  const { status, dataVersion, setRoute, setCohort, followed, following, registry, presets, openDrawer } = useStore()
  const { u, compare, hasAlt } = useLens()
  const pulse = useAsync(() => api.pulse(u), [u, dataVersion])
  const pulseAlt = useAsync(() => (compare ? api.pulse('alt') : Promise.resolve(null)), [compare, dataVersion])
  const p: any = pulse.data
  const trendVars = (p?.trends ?? []).filter((t: any) => t.kind === 'num').map((t: any) => t.var)
  const ts = useAsync(() => (trendVars.length ? api.timeseries(trendVars) : Promise.resolve(null)), [trendVars.join(','), dataVersion])
  const ids = followed()
  const mine = useAsync(() => (ids.length ? api.brief(ids, u) : Promise.resolve([])), [JSON.stringify(following), u, dataVersion])
  const t = status.totals ?? {}
  const running = status.job?.state === 'running'
  const date = new Date(status.date + 'T12:00:00')
  return (
    <div className="page world">
      {/* the valley is the live app's home, with the living map and the story; the overview keeps the numbers */}
      <section className={`world-hero card ${STATIC ? '' : 'plain'}`}>
        {STATIC && <LivingMap />}
        <div className="wh-overlay">
          <div className="eyebrow">{status.season}</div>
          <h1>{date.toLocaleDateString(undefined, { weekday: 'long', month: 'long', day: 'numeric', year: 'numeric' })}</h1>
          <p><b><Ticker value={status.present ?? 0} /></b> synthetic students, spouses, young adults and neighbors live in real Provo and Orem housing.
            So far: <b><Ticker value={pairs('new_friend', t.new_friend ?? 0)} /></b> new friendships, <b><Ticker value={pairs('first_date', t.first_date ?? 0)} /></b> first dates, <b><Ticker value={pairs('relationship_started', t.relationship_started ?? 0)} /></b> new exclusive couples and <b><Ticker value={pairs('wedding', t.wedding ?? 0)} /></b> weddings.</p>
          <div className="row">
            {!STATIC && (running
              ? <button className="btn big" onClick={() => timeCtl.pause()}>{G.pause} Pause time</button>
              : <button className="btn primary big" onClick={() => timeCtl.play()}>{G.play} Let time run</button>)}
            <button className="btn big" onClick={() => setRoute(['map', 'day'])}>{G.map} Watch a day on the map</button>
            {!hasAlt && !STATIC && <button className="btn big whatif-cta" onClick={() => openDrawer({})}>{G.butterfly} What if…?</button>}
          </div>
          {status.day < 7 && !STATIC && <p className="small" style={{ marginTop: 10 }}>This world just started. Press <b>Let time run</b> (or Space) and watch lives unfold; the news pops up as it happens.</p>}
        </div>
      </section>

      <div className={`world-grid ${STATIC ? '' : 'plain'}`}>
        {STATIC && <div className="card">
          <div className="card-head"><div><h3>{G.events} Headlines</h3><p className="hint">The biggest moments lately. Click a name to open that life.</p></div><button className="btn small" onClick={() => setRoute(['events'])}>All events</button></div>
          {compare ? (
            <div className="two-u">
              <div className="u-col card flat"><UBadge u="base" /><Headlines list={p?.headlines} /></div>
              <div className="u-col card flat alt"><UBadge u="alt" /><Headlines list={(pulseAlt.data as any)?.headlines} /></div>
            </div>
          ) : <Headlines list={p?.headlines} />}
        </div>}
        <div className={STATIC ? 'grid' : 'grid g2'} style={{ alignContent: 'start' }}>
          <TwoWorlds />
          <div className="card">
            <h3>{G.clock} A day in Provo</h3>
            <p className="hint">{p?.day_blocks_date ? `Where everyone was on ${new Date(p.day_blocks_date + 'T12:00:00').toLocaleDateString(undefined, { weekday: 'long', month: 'short', day: 'numeric' })}.` : 'Run a day to see what people do.'}</p>
            {(p?.day_blocks ?? []).slice(0, 3).map((b: any) => <DayBlock key={b.block} b={b} />)}
          </div>
        </div>
      </div>

      <div className="section-title"><h2>This week</h2><span className="small muted">Life events in the last 7 days{hasAlt && !compare ? ` · ${u === 'alt' ? 'What-if' : 'Original'} world` : compare ? ' · Original → What-if' : ''}</span></div>
      <div className="week-board">
        {WEEK_KEYS.map(([k, l, c]) => {
          const n = pairs(k, p?.week?.find((r: any) => r.type === k)?.count ?? 0)
          const na = compare ? pairs(k, (pulseAlt.data as any)?.week?.find((r: any) => r.type === k)?.count ?? 0) : null
          if (!n && !na) return null
          return (
            <button key={k} className="wk" onClick={() => setRoute(['events', 'type', k])}>
              <CatIcon c={c} />
              <span className="wk-n tabular"><Ticker value={n} />{na !== null && na !== n ? <small className="u-alt-t"> → {na}</small> : null}</span>
              <span className="wk-l">{l}</span>
            </button>
          )
        })}
        {p && !WEEK_KEYS.some(([k]) => p.week?.some((r: any) => r.type === k && r.count)) && <div className="empty small">A quiet week. Run time forward.</div>}
      </div>

      <div className="section-title"><h2>What's moving</h2><span className="small muted">Biggest changes over the last four weeks, everyone{hasAlt ? ` · ${u === 'alt' ? 'What-if' : 'Original'}` : ''}. Click to explore.</span></div>
      <div className="grid g4">
        {(p?.trends ?? []).slice(0, 8).map((tr: any) => <TrendCard key={tr.label} tr={tr} ts={ts.data} />)}
        {p && !p.trends?.length && <div className="card empty small">Trends appear after a few days of simulated time.</div>}
      </div>

      <Board />

      {(ids.length > 0 || (p?.featured ?? []).length > 0) && (
        <>
          <div className="section-title"><h2>{ids.length ? 'People you follow' : 'Lives worth following'}</h2><span className="small muted">{ids.length ? 'Their latest, every time you run.' : 'The most eventful lives of the last 30 days, across different parts of life.'}</span></div>
          <div className="grid g3">
            {(ids.length ? (mine.data as any[]) ?? [] : []).map((x: any, k: number) => <PersonCard key={x.id} p={x} k={k} />)}
            {(p?.featured ?? []).slice(0, ids.length ? 3 : 6).map((x: any, k: number) => <PersonCard key={`f${x.id}`} p={x} k={k + 2} theme={x.theme} />)}
          </div>
        </>
      )}

      {!hasAlt && !STATIC && presets && (
        <>
          <div className="section-title"><h2>One-click what-ifs</h2><span className="small muted">Split the world, run a month, and see what changes. Or open “What if…?” to build your own.</span></div>
          <div className="grid g3">{QUICK_TRY.filter(k => presets[k]).map(k => <QuickTry key={k} id={k} />)}</div>
        </>
      )}

      <div className="section-title"><h2>Curiosities</h2><span className="small muted">Each opens the right view with the right group selected.</span></div>
      <div className="grid g4">
        {CURIOSITIES.map(q => (
          <button key={q.q} className="card qcard" onClick={() => { setCohort(q.cohort ?? []); setRoute(q.route) }}>
            <b>{q.q}</b><span>{q.how}</span><span className="qgo">Show me →</span>
          </button>
        ))}
      </div>
      {registry && <p className="small muted" style={{ marginTop: 24 }}>Everyone here is synthetic: generated from aggregate survey patterns, never real respondents. Numbers are what this model produces, not forecasts about real people. See Research desk → Model check for how well it matches real data.</p>}
    </div>
  )
}

function Headlines({ list }: { list?: any[] }) {
  if (!list) return <div className="empty small">Reading the news…</div>
  if (!list.length) return <div className="empty small">Nothing big yet. Let time run.</div>
  return (
    <div className="headlines">
      {list.slice(0, 12).map(e => (
        <div key={e.id} className="hl">
          <CatIcon c={e.category} />
          <div className="hl-body"><div className="hl-when small muted">{new Date(e.date + 'T12:00:00').toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric' })} · {CATEGORY_LABEL[e.category] ?? e.category}</div><Story e={e} /></div>
        </div>
      ))}
    </div>
  )
}

function DayBlock({ b }: { b: any }) {
  const total = b.doing.reduce((s: number, r: any) => s + r.n, 0) || 1
  const top = b.doing.slice(0, 6)
  return (
    <div className="dayblock">
      <div className="db-label small"><b>{b.block}</b></div>
      <div className="db-bar">{top.map((r: any, k: number) => <i key={r.activity} style={{ width: `${(100 * r.n) / total}%`, background: `var(--s${(k % 8) + 1})` }} title={`${pretty(r.activity)}: ${r.n.toLocaleString()}`} />)}</div>
      <div className="db-legend small">{top.slice(0, 4).map((r: any, k: number) => <span key={r.activity}><span className="dot" style={{ background: `var(--s${(k % 8) + 1})` }} />{pretty(r.activity)} <span className="muted tabular">{r.n.toLocaleString()}</span></span>)}</div>
    </div>
  )
}

function TrendCard({ tr, ts }: { tr: any; ts: any }) {
  const { registry, setRoute } = useStore()
  const { u } = useLens()
  const spec = registry!.variables[tr.var]
  const series = tr.kind === 'num' ? (ts?.[u]?.[tr.var] ?? ts?.base?.[tr.var] ?? []).slice(-60) : []
  const pol = polarity(tr.var) * (tr.cat && ['married', 'dating', 'engaged', 'active'].includes(tr.cat) ? 0 : 1) as 1 | -1 | 0
  return (
    <button className="card trend" onClick={() => setRoute(['explore', tr.var])}>
      <span className="small muted">{DRAWERS.find(d => d.id === drawerOf(spec))?.label}</span>
      <b>{tr.label}</b>
      <span className="tr-val tabular">{tr.kind === 'share' ? pctStr(tr.now) : favg(spec, tr.now)}</span>
      <span className="row" style={{ gap: 6 }}><DeltaChip d={tr.delta} text={tr.kind === 'share' ? fdelta(spec, tr.delta, true) : fdelta(spec, tr.delta)} polarity={pol} /><span className="small muted">{sizeWord(tr.effect)} · {tr.days} days</span></span>
      {series.length > 1 && <Spark a={series} width={200} height={30} color={u === 'alt' ? 'var(--u-alt)' : 'var(--u-base)'} />}
    </button>
  )
}

function TwoWorlds() {
  const { status, dataVersion, setRoute, registry, presets, openDrawer } = useStore()
  const f = useAsync(() => (status.has_alt ? api.compareFields() : Promise.resolve(null)), [status.has_alt, dataVersion], { key: status.has_alt ? whatifKey(status, 'fields') : undefined })
  if (!status.has_alt) {
    return (
      <div className="card twoworlds empty-tw">
        <div className="tw-wings">{G.butterfly}</div>
        <h3>One world, for now</h3>
        <p className="small secondary">Split it in two and change something in one copy: rent, coffee, a dating app, mission age… Both copies roll the same dice, so every difference is your butterfly effect.</p>
        {!STATIC && <button className="btn primary" onClick={() => openDrawer({})}>{G.butterfly} What if…?</button>}
      </div>
    )
  }
  const d = status.divergence?.any_state_diff ?? 0
  const top = f.data ? Object.entries((f.data as any).fields).map(([id, r]: any) => ({ id, ...r })).filter(r => registry!.variables[r.id]).sort((a: any, b: any) => Math.abs(b.effect) - Math.abs(a.effect)).slice(0, 4) : []
  const names = [...new Set<string>((status.alt_interventions ?? []).map((i: any) => i.name ?? presets?.[i.id]?.name ?? i.id))]
  return (
    <div className="card twoworlds">
      <div className="row" style={{ flexWrap: 'nowrap' }}>
        <div className="tw-wings small-w">{G.butterfly}</div>
        <div style={{ flex: 1, minWidth: 0 }}><h3>Two worlds</h3><div className="small secondary">{names.join(' + ')}</div></div>
        <div className="tw-pct"><b className="tabular">{(100 * d).toFixed(d < 0.1 ? 1 : 0)}%</b><span className="small muted">lives differ</span></div>
      </div>
      <div className="tw-list">
        {top.map((r: any) => {
          const spec = registry!.variables[r.id]
          return (
            <button key={r.id} className="tw-row" onClick={() => { useStore.getState().setLens('compare'); setRoute(['explore', r.id]) }}>
              <span>{spec.label}</span>
              <span className="tabular small">{r.kind === 'num' ? <><span className="u-base-t">{fpair(spec, r.base, r.alt)[0]}</span> → <span className="u-alt-t">{fpair(spec, r.base, r.alt)[1]}</span></> : r.kind === 'bool' ? <><span className="u-base-t">{pctStr(r.base)}</span> → <span className="u-alt-t">{pctStr(r.alt)}</span></> : <>{pretty(r.top)} <span className="u-alt-t">{fdelta(spec, r.top_delta, true)}</span></>}</span>
            </button>
          )
        })}
      </div>
      <div className="row"><button className="btn primary small" onClick={() => setRoute(['whatif'])}>{G.butterfly} Follow the butterfly</button>{!STATIC && <button className="btn small" onClick={() => openDrawer({})}>Change more</button>}</div>
    </div>
  )
}

function QuickTry({ id }: { id: string }) {
  const { presets, refreshStatus, setRoute, setLens } = useStore()
  const [busy, setBusy] = useState(false)
  const p = presets[id]
  return (
    <div className="card quicktry">
      <div className="row" style={{ flexWrap: 'nowrap' }}><span className="qt-icon">{G.butterfly}</span><b style={{ flex: 1 }}>{p.name}</b><span className={`conf ${p.confidence}`}>{p.confidence}</span></div>
      <p className="small secondary">{p.description}</p>
      <button className="btn small primary" disabled={busy} onClick={async () => {
        setBusy(true)
        try { await api.fork([{ preset: id }]); await api.step({ days: 30 }); await refreshStatus(); setLens('compare'); setRoute(['whatif']) } finally { setBusy(false) }
      }}>{busy ? 'Splitting the world…' : '▶ Try it for a month'}</button>
    </div>
  )
}

/** Your board: pinned fields and people, live. */
function Board() {
  const { pinned, pins, setRoute, togglePin } = useStore()
  void pins
  const list = pinned()
  if (!list.length) return (
    <>
      <div className="section-title"><h2>Your board</h2><span className="small muted">Pin any field from Explore (or any person) and it lives here, updating as time runs.</span></div>
      <div className="card board-empty"><span className="es-icon">{G.pin}</span><div><b>Nothing pinned yet.</b><div className="small secondary">Open <button className="linkish" onClick={() => setRoute(['explore', 'loneliness'])}>Explore</button>, pick a field and press <b>Pin</b>. Build your own dashboard of the things you care about.</div></div></div>
    </>
  )
  return (
    <>
      <div className="section-title"><h2>Your board</h2><span className="small muted">Pinned fields and people, updated every time you run.</span></div>
      <div className="grid g4">{list.map((pn: Pin) => pn.kind === 'field' ? <PinnedField key={`f${pn.var}`} v={pn.var} onUnpin={() => togglePin(pn)} /> : <PinnedPerson key={`p${pn.id}`} id={pn.id} onUnpin={() => togglePin(pn)} />)}</div>
    </>
  )
}

function PinnedField({ v, onUnpin }: { v: string; onUnpin: () => void }) {
  const { registry, dataVersion, setRoute } = useStore()
  const { u, compare, hasAlt } = useLens()
  const spec = registry!.variables[v]
  const t = useAsync(() => api.fieldTimeline(v, 'all'), [v, dataVersion])
  const d: any = t.data
  if (!spec) return null
  const pickSeries = (src: any) => {
    if (!src) return []
    if (spec.dtype === 'cat') { const sh = src.shares ?? {}; const k = Object.keys(sh).sort((a, b) => (sh[b].at(-1) ?? 0) - (sh[a].at(-1) ?? 0))[0]; return { k, s: sh[k] ?? [] } }
    return { k: null, s: src.mean ?? [] }
  }
  const A: any = pickSeries(compare ? d?.base : d?.[u] ?? d?.base), B: any = compare ? pickSeries(d?.alt) : null
  const last = (s: any[]) => [...s].reverse().find(x => x !== null && x !== undefined)
  const now = last(A.s ?? []), nowB = B ? last(B.s ?? []) : undefined
  const show = (x: any) => (x === undefined ? '—' : spec.dtype === 'cat' || spec.dtype === 'bool' ? pctStr(x) : favg(spec, x))
  return (
    <div className="card pinned" onClick={() => setRoute(['explore', v])} role="button">
      <div className="row" style={{ flexWrap: 'nowrap' }}><span className="small muted" style={{ flex: 1 }}>{DRAWERS.find(x => x.id === drawerOf(spec))?.label}</span><button className="t-x" onClick={e => { e.stopPropagation(); onUnpin() }} aria-label="Unpin">{G.close}</button></div>
      <b>{spec.label}{A.k ? <span className="small muted"> · {pretty(A.k)}</span> : null}</b>
      <span className="tr-val tabular">{show(now)}{B && nowB !== undefined && <small className="u-alt-t"> → {show(nowB)}</small>}</span>
      <Spark a={(A.s ?? []).slice(-40)} b={B ? (B.s ?? []).slice(-40) : undefined} width={200} height={30} color={!compare && hasAlt && u === 'alt' ? 'var(--u-alt)' : undefined} />
    </div>
  )
}

function PinnedPerson({ id, onUnpin }: { id: number; onUnpin: () => void }) {
  const { dataVersion, setRoute } = useStore()
  const { u } = useLens()
  const b = useAsync(() => api.brief([id], u), [id, u, dataVersion])
  const p: any = (b.data as any)?.[0]
  return (
    <div className="card pinned" onClick={() => setRoute(['person', String(id)])} role="button">
      <div className="row" style={{ flexWrap: 'nowrap' }}><span className="small muted" style={{ flex: 1 }}>Person</span><button className="t-x" onClick={e => { e.stopPropagation(); onUnpin() }} aria-label="Unpin">{G.close}</button></div>
      <b>{p?.name ?? `#${id}`}</b>
      <span className="small secondary">{p?.headline ?? '…'}</span>
      {p?.events?.[0] && <span className="small"><Story e={p.events[0]} me={id} /></span>}
    </div>
  )
}

const AVATAR = ['--s1', '--s2', '--s3', '--s7', '--s5', '--s4']
function PersonCard({ p, k, theme }: { p: any; k: number; theme?: string }) {
  const setRoute = useStore(s => s.setRoute)
  const initials = p.name.split(' ').map((s: string) => s[0]).join('')
  return (
    <div className="card person-card" onClick={() => setRoute(['person', String(p.id)])}>
      <div className="row" style={{ flexWrap: 'nowrap' }}>
        <span className="avatar" style={{ background: `var(${AVATAR[k % AVATAR.length]})` }}>{initials}</span>
        <div style={{ minWidth: 0, flex: 1 }}><div className="pc-name">{p.name}</div><div className="pc-head">{p.headline}</div></div>
        <FollowButton id={p.id} small />
      </div>
      {theme && <span className="pill" style={{ alignSelf: 'flex-start' }}>{CATEGORY_LABEL[theme] ?? theme}</span>}
      {typeof p.mood === 'number' && <div className="pc-meters"><span>happiness <i style={{ width: `${100 * p.mood}%` }} /></span><span>loneliness <i className="lo" style={{ width: `${100 * p.loneliness}%` }} /></span></div>}
      <div>{(p.events ?? []).slice(0, 3).map((e: any) => <div key={e.id} className="story" style={{ padding: '4px 0' }}><span className="when tabular">{new Date(e.date + 'T12:00:00').toLocaleDateString(undefined, { month: 'short', day: 'numeric' })}</span><Story e={e} me={p.id} /></div>)}
        {!(p.events ?? []).length && <div className="small muted">Nothing notable yet.</div>}</div>
    </div>
  )
}

// ---------------------------------------------------------------- the living map
let roadsP: Promise<any> | null = null
const BOUNDS = { lon0: -111.775, lon1: -111.57, lat0: 40.17, lat1: 40.36 }

/** Everyone in Provo–Orem, gliding through yesterday: home → class/work → evening → home. */
function LivingMap() {
  const { dataVersion, theme } = useStore()
  const { u } = useLens()
  const ref = useRef<HTMLCanvasElement>(null)
  const [roads, setRoads] = useState<any>(null)
  const [frames, setFrames] = useState<any>(null)
  const [label, setLabel] = useState('')
  const [legend, setLegend] = useState<{ name: string; color: string; n: number }[]>([])
  useEffect(() => { if (!roadsP) roadsP = fetch(api.geo('roads.json')).then(r => r.json()); roadsP.then(setRoads).catch(() => {}) }, [])
  useEffect(() => { api.dayFrames(u).then(setFrames).catch(() => setFrames(null)) }, [u, dataVersion])
  const bg = useMemo(() => ({ key: 0 }), [roads, theme])
  useEffect(() => {
    const c = ref.current
    if (!c || !roads) return
    let raf = 0, alive = true
    let W = 0, H = 0, dpr = 1, s = 1, ox = 0, oy = 0
    const kx = Math.cos((40.27 * Math.PI) / 180)
    const off = document.createElement('canvas')
    const layout = () => {
      W = c.clientWidth; H = c.clientHeight; dpr = window.devicePixelRatio || 1
      c.width = W * dpr; c.height = H * dpr
      s = Math.max(W / ((BOUNDS.lon1 - BOUNDS.lon0) * kx), H / (BOUNDS.lat1 - BOUNDS.lat0)) * 1.02
      ox = (W - (BOUNDS.lon1 - BOUNDS.lon0) * kx * s) / 2; oy = (H - (BOUNDS.lat1 - BOUNDS.lat0) * s) / 2
      off.width = W * dpr; off.height = H * dpr
      const g = off.getContext('2d')!
      g.setTransform(dpr, 0, 0, dpr, 0, 0)
      g.clearRect(0, 0, W, H)
      g.strokeStyle = cssVar('--text-muted')
      for (const f of roads.features) {
        const major = f.properties.c === 1
        g.globalAlpha = major ? 0.42 : 0.16
        g.lineWidth = major ? 1.2 : 0.55
        g.beginPath()
        f.geometry.coordinates.forEach(([x, y]: number[], k: number) => { const px = ox + (x - BOUNDS.lon0) * kx * s, py = oy + (BOUNDS.lat1 - y) * s; k ? g.lineTo(px, py) : g.moveTo(px, py) })
        g.stroke()
      }
    }
    layout()
    const ro = new ResizeObserver(() => { layout(); if (reduced) draw(performance.now()) })
    ro.observe(c)
    const ctx = c.getContext('2d')!
    const pal = [1, 2, 3, 4, 5, 6, 7, 8].map(k => cssVar(`--s${k}`))
    const muted = cssVar('--text-muted')
    // order activity categories by how common they are at midday, so colors are stable and meaningful
    let cats: string[] = [], rank: number[] = [], n = 0
    if (frames?.act1) {
      cats = frames.act1.categories ?? []
      const cnt = new Array(cats.length).fill(0)
      const a1 = frames.act1.data
      for (let i = 0; i < a1.length; i++) if (!Number.isNaN(frames.lon1.data[i])) cnt[a1[i]]++
      const order = cats.map((_, k) => k).filter(k => cats[k] !== 'away').sort((a, b) => cnt[b] - cnt[a])
      rank = new Array(cats.length).fill(-1)
      order.forEach((k, j) => { if (j < 8) rank[k] = j })
      n = a1.length
      setLegend(order.slice(0, 6).map(k => ({ name: pretty(cats[k]), color: pal[rank[k]], n: cnt[k] })))
    }
    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    const t0 = performance.now()
    const HOLD = 1.5, GLIDE = 1.6, PER = HOLD + GLIDE
    let lastBlock = -1
    const draw = (now: number) => {
      if (!alive) return
      ctx.setTransform(1, 0, 0, 1, 0, 0)
      ctx.clearRect(0, 0, c.width, c.height)
      ctx.drawImage(off, 0, 0)
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
      if (frames?.lon0) {
        const el = reduced ? HOLD / 2 + PER : Math.max(0, (now - t0) / 1000)
        const cyc = el % (PER * 4)
        const k0 = Math.floor(cyc / PER), inBlock = cyc - k0 * PER
        const a = inBlock < HOLD ? 0 : (inBlock - HOLD) / GLIDE
        const e = a < 0.5 ? 2 * a * a : 1 - (-2 * a + 2) ** 2 / 2
        const k1 = (k0 + 1) % 4
        const L0 = frames[`lon${k0}`].data, A0 = frames[`lat${k0}`].data, L1 = frames[`lon${k1}`].data, A1 = frames[`lat${k1}`].data
        const act = frames[`act${a < 0.5 ? k0 : k1}`].data
        const blk = a < 0.5 ? k0 : k1
        if (blk !== lastBlock) { lastBlock = blk; setLabel(BLOCK_LABEL[blk]) }
        const r = Math.max(1.3, Math.min(2.4, W / 700))
        for (let i = 0; i < n; i++) {
          let x0 = L0[i], y0 = A0[i], x1 = L1[i], y1 = A1[i]
          if (Number.isNaN(x0)) { if (Number.isNaN(x1)) continue; x0 = x1; y0 = y1 }
          if (Number.isNaN(x1)) { x1 = x0; y1 = y0 }
          const lon = x0 + (x1 - x0) * e, lat = y0 + (y1 - y0) * e
          const px = ox + (lon - BOUNDS.lon0) * kx * s, py = oy + (BOUNDS.lat1 - lat) * s
          const rk = rank[act[i]]
          ctx.fillStyle = rk >= 0 ? pal[rk] : muted
          ctx.globalAlpha = rk >= 0 ? 0.78 : 0.35
          ctx.fillRect(px - r / 2, py - r / 2, r, r)
        }
        ctx.globalAlpha = 1
      }
      if (!reduced) raf = requestAnimationFrame(draw)
    }
    raf = requestAnimationFrame(draw)
    return () => { alive = false; cancelAnimationFrame(raf); ro.disconnect() }
  }, [roads, frames, bg])
  return (
    <div className="livingmap">
      <canvas ref={ref} aria-label="A living map of Provo and Orem" />
      {frames?.lon0 && <div className="lm-label"><span className="live-dot">{label}</span>{frames.day?.meta?.date && <span className="muted"> · {new Date(frames.day.meta.date + 'T12:00:00').toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric' })}</span>}</div>}
      {legend.length > 0 && <div className="lm-legend small">{legend.map(l => <span key={l.name}><span className="dot" style={{ background: l.color }} />{l.name}</span>)}</div>}
    </div>
  )
}
