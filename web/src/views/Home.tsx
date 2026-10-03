import { useEffect, useMemo, useRef, useState } from 'react'
import { fmt, pct } from '../analysis'
import { api, STATIC } from '../api'
import { cssVar, Icons, Loading } from '../components'
import { Cond, useStore } from '../store'
import { CATEGORY_LABEL, FollowButton, Sparkline, Story } from '../ui'

// ---------------------------------------------------------------- curated questions
type Q = { q: string; how: string; cohort?: Cond[]; route: string[] }
const QUESTIONS: Record<string, Q[]> = {
  'Dating & marriage': [
    { q: 'How do people move from single to married?', how: 'Follow everyone\'s relationship status between two dates', route: ['flows', 'rel_status'] },
    { q: 'Does church activity change how often singles date?', how: 'Dates per month for singles, split by church activity', cohort: [{ var: 'rel_status', op: 'in', value: ['single', 'talking'] }], route: ['explore', 'dates_30d', '', 'activity'] },
    { q: 'Are returned missionaries more likely to be married?', how: 'Cross-tab of mission status by relationship status', route: ['crosstab', 'mission_status', 'rel_status'] },
    { q: 'How do couples meet?', how: 'Where every romantic relationship began', route: ['dashboard', 'origins'] },
  ],
  'Faith': [
    { q: 'Who is drifting from church activity?', how: 'Flows between active, less active and inactive over time', route: ['flows', 'activity'] },
    { q: 'How does belief relate to attendance?', how: 'Each dot is a person: belief vs. how often they attend', route: ['explore', 'faith_belief', 'attend_rate'] },
    { q: 'What is life like during a faith crisis?', how: 'People currently in a crisis: mood, and what drives it', cohort: [{ var: 'faith_crisis', op: 'eq', value: true }], route: ['explore', 'mood'] },
  ],
  'Friends & wellbeing': [
    { q: 'Who is lonely, and why?', how: 'The loneliest 20%, what makes them lonely, and example lives', cohort: [{ var: 'loneliness', op: 'quantile_ge', value: 0.8 }], route: ['explore', 'loneliness'] },
    { q: 'Which apartment complexes are the loneliest?', how: 'Complexes on the map, colored by average loneliness', route: ['map', 'complexes:loneliness'] },
    { q: 'Do introverts have fewer close friends?', how: 'Extraversion vs. number of close friends', route: ['explore', 'extraversion', 'n_close_friends'] },
    { q: 'What does a breakup do to someone?', how: 'People broken up with in the last 90 days: their mood and why', cohort: [{ recent_event: 'breakup_received', days: 90 }], route: ['explore', 'mood'] },
  ],
  'Money & housing': [
    { q: 'Who is struggling financially?', how: 'Financial stress by school', route: ['explore', 'financial_stress', '', 'school'] },
    { q: 'Where is rent the biggest burden?', how: 'Homes on the map, colored by share of income going to rent', route: ['map', 'homes:rent_burden'] },
    { q: 'How do people\'s living situations change?', how: 'Flows between dorms, apartments, married housing and home', route: ['flows', 'living'] },
  ],
  'What if…?': [
    { q: 'What if rent rose 20%?', how: 'Split the world and compare', route: ['lab', 'rent_up_20'] },
    { q: 'What if coffee were allowed?', how: 'Split the world and compare', route: ['lab', 'coffee_permitted'] },
    { q: 'What if a new dating app took off?', how: 'Split the world and compare', route: ['lab', 'new_dating_app'] },
    { q: 'What if fewer people served missions?', how: 'Split the world and compare', route: ['lab', 'mission_participation_minus_15'] },
  ],
}

const VITALS: { v: string; label: string; group?: string; fmt: (x: number) => string; good: 'up' | 'down' | null; route: string[] }[] = [
  { v: 'loneliness', label: 'Loneliness', fmt: x => fmt(x, 2), good: 'down', route: ['variables', 'loneliness'] },
  { v: 'mood', label: 'Happiness', fmt: x => fmt(x, 2), good: 'up', route: ['variables', 'mood'] },
  { v: 'dates_30d', label: 'Dates per month (singles)', group: 'single', fmt: x => fmt(x, 1), good: null, route: ['variables', 'dates_30d'] },
  { v: 'rel_status=married', label: 'Married', fmt: x => pct(x), good: null, route: ['flows', 'rel_status'] },
  { v: 'attend_rate', label: 'Church attendance', fmt: x => pct(x), good: null, route: ['flows', 'activity'] },
  { v: 'financial_stress', label: 'Money stress', fmt: x => fmt(x, 2), good: 'down', route: ['variables', 'financial_stress'] },
  { v: 'depressive_episode', label: 'In a depressive episode', fmt: x => pct(x), good: 'down', route: ['variables', 'depressive_episode'] },
]

const WEEK_KEYS: [string, string][] = [
  ['first_date', 'first dates'], ['relationship_started', 'new couples'], ['engaged', 'engagements'], ['wedding', 'weddings (people)'],
  ['breakup_received', 'breakups'], ['new_friend', 'new friendships'], ['faith_crisis_start', 'faith crises'], ['mission_departure', 'mission departures'],
  ['graduation', 'graduations'], ['birth', 'babies'],
]

const AVATAR = ['--s1', '--s2', '--s3', '--s7', '--s5', '--s4']

export default function Home() {
  const { status, dataVersion, universe, setRoute, setCohort, followed, following, registry } = useStore()
  const [ts, setTs] = useState<any>(null)
  const [week, setWeek] = useState<any>(null)
  const [stories, setStories] = useState<any[] | null>(null)
  const [featured, setFeatured] = useState<any[] | null>(null)
  const [mine, setMine] = useState<any[]>([])
  const [theme, setTheme] = useState(Object.keys(QUESTIONS)[0])
  const ids = followed()
  useEffect(() => {
    api.timeseries([...new Set(VITALS.map(v => v.v))]).then(setTs).catch(() => setTs({}))
    api.timeseries(['dates_30d'], 'single').then(d => setTs((t: any) => ({ ...(t ?? {}), single: d }))).catch(() => {})
    api.eventsSummary(universe, Math.max(0, status.day - 7)).then(setWeek).catch(() => setWeek(null))
    api.events({ min_salience: 0.85, limit: 20, u: universe }).then(r => {
      // a wedding is logged once per spouse; show each pair once
      const seen = new Set<string>()
      setStories(r.events.filter((e: any) => {
        const k = e.b == null ? `${e.id}` : `${e.type}|${e.day}|${Math.min(e.a, e.b)}|${Math.max(e.a, e.b)}`
        if (seen.has(k)) return false
        seen.add(k)
        return true
      }).slice(0, 10))
    }).catch(() => setStories([]))
    api.featured(universe).then(setFeatured).catch(() => setFeatured([]))
  }, [dataVersion, universe])
  useEffect(() => { api.brief(ids, universe).then(setMine).catch(() => setMine([])) }, [dataVersion, universe, JSON.stringify(following)])

  const t = status.totals ?? {}
  const date = new Date(status.date + 'T12:00:00')
  const fresh = status.day < 7
  const go = (q: Q) => { setCohort(q.cohort ?? []); setRoute(q.route) }

  return (
    <div className="page">
      <section className="card hero">
        <RoadSilhouette />
        <div className="eyebrow">{status.season}</div>
        <h1>Provo & Orem, {date.toLocaleDateString(undefined, { weekday: 'long', month: 'long', day: 'numeric', year: 'numeric' })}</h1>
        <p>
          <b>{status.present?.toLocaleString()}</b> synthetic students, spouses, young adults, faculty and neighbors live here, in real Provo and Orem housing.
          {' '}So far they have made <b>{(t.new_friend ?? 0).toLocaleString()}</b> new friends, gone on <b>{(t.first_date ?? 0).toLocaleString()}</b> first dates,
          {' '}formed <b>{(t.relationship_started ?? 0).toLocaleString()}</b> couples and celebrated <b>{Math.round((t.wedding ?? 0) / 2).toLocaleString()}</b> weddings.
        </p>
        {fresh && !STATIC && <p><b>This world just started.</b> Press <span className="kbd">+1 week</span> at the top to watch it come alive, or read the field guide first.</p>}
        <div className="row">
          <button className="btn primary" onClick={() => setRoute(['guide'])}>How this world works (5 min)</button>
          <button className="btn" onClick={() => setRoute(['dashboard'])}>Vital signs</button>
          <button className="btn" onClick={() => setRoute(['map'])}>Open the map</button>
        </div>
      </section>

      <div className="grid g3 doors">
        <button className="card door" onClick={() => setRoute(['lab'])}>
          <span className="door-icon">{Icons.lab}</span>
          <h3>Try a what-if</h3>
          <p>Change one thing about Provo (rent, coffee, a new dating app, fewer missions) and watch two versions of the world drift apart. Then see why.</p>
          <span className="door-go">Open the what-if lab →</span>
        </button>
        <button className="card door" onClick={() => document.getElementById('questions')?.scrollIntoView({ behavior: 'smooth' })}>
          <span className="door-icon">{Icons.explore}</span>
          <h3>Ask a question</h3>
          <p>Pick a group of people and see how they compare, how they change over time, and which forces in the model drive it.</p>
          <span className="door-go">Browse questions ↓</span>
        </button>
        <button className="card door" onClick={() => setRoute(['people'])}>
          <span className="door-icon">{Icons.people}</span>
          <h3>Follow a life</h3>
          <p>Meet individual people: their friends, dates, faith, money and feelings, with a "why" behind every number. Follow them as time runs.</p>
          <span className="door-go">Meet people →</span>
        </button>
      </div>

      <div className="grid g2" style={{ marginTop: 14 }}>
        <div className="card">
          <div className="card-head"><div><h3>This week in Provo</h3><p className="hint">What happened in the last 7 simulated days.</p></div>
            <button className="btn small" onClick={() => setRoute(['events'])}>All life events</button></div>
          {week && <div className="week-counts">{WEEK_KEYS.map(([k, l]) => { const r = week.types?.find((x: any) => x.type === k); return r?.count ? <span key={k} className="pill tabular"><b>{r.count.toLocaleString()}</b>&nbsp;{l}</span> : null })}</div>}
          {stories === null ? <Loading what="Reading the news" /> : stories.length === 0 ? <div className="empty small">Nothing big yet. Run time forward to see lives unfold.</div> : (
            <div className="scroll" style={{ maxHeight: 300 }}>
              {stories.map(e => <div key={e.id} className="story"><span className="when tabular">{shortDate(e.date)}</span><Story e={e} /></div>)}
            </div>
          )}
        </div>
        <div className="card">
          <div className="card-head"><div><h3>Vital signs</h3><p className="hint">Population averages over time. The change is versus 30 days ago; click one to dig in.</p></div>
            <button className="btn small" onClick={() => setRoute(['dashboard'])}>All trends</button></div>
          {VITALS.map(v => <Vital key={v.v + (v.group ?? '')} spec={v} data={v.group ? ts?.[v.group]?.base : ts?.base} onClick={() => setRoute(v.route)} />)}
        </div>
      </div>

      <div className="section-title" id="questions"><h2>Questions to explore</h2><span className="small muted">Each one opens the right view with the right group already selected.</span></div>
      <div className="seg qtabs">{Object.keys(QUESTIONS).map(k => <button key={k} className={theme === k ? 'on' : ''} onClick={() => setTheme(k)}>{k}</button>)}</div>
      <div className="grid g4">
        {QUESTIONS[theme].map(q => (
          <button key={q.q} className="card qcard" onClick={() => go(q)}>
            <b>{q.q}</b><span>{q.how}</span><span className="qgo">{q.route[0] === 'lab' ? 'Set up the experiment →' : 'Show me →'}</span>
          </button>
        ))}
      </div>

      {ids.length > 0 && (
        <>
          <div className="section-title"><h2>People you follow</h2><button className="btn small" onClick={() => setRoute(['people'])}>Manage</button></div>
          <div className="grid g3">{mine.map((p, k) => <PersonCard key={p.id} p={p} k={k} />)}</div>
        </>
      )}

      <div className="section-title"><h2>Lives worth following</h2><span className="small muted">People with the most eventful last 30 days, across different parts of life.</span></div>
      {featured === null ? <Loading what="Finding stories" /> : featured.length === 0 ? <div className="empty small">Run time forward and interesting lives will appear here.</div> : (
        <div className="grid g3">{featured.map((p, k) => <PersonCard key={p.id} p={p} k={k} theme={p.theme} />)}</div>
      )}
      {registry && <p className="small muted" style={{ marginTop: 24 }}>Everyone here is synthetic: generated from aggregate survey patterns, never real respondents. Numbers are what this model produces, not forecasts about real people.</p>}
    </div>
  )
}

function shortDate(d: string) { return new Date(d + 'T12:00:00').toLocaleDateString(undefined, { month: 'short', day: 'numeric' }) }

function Vital({ spec, data, onClick }: { spec: typeof VITALS[number]; data: any; onClick: () => void }) {
  const vals: number[] = data?.[spec.v] ?? []
  const days: number[] = data?.day ?? []
  const now = vals[vals.length - 1]
  let then: number | undefined
  if (days.length) { const target = days[days.length - 1] - 30; const k = days.findIndex(d => d >= target); then = k >= 0 ? vals[k] : undefined }
  const d = now !== undefined && then !== undefined ? now - then : undefined
  const better = d === undefined || spec.good === null || Math.abs(d) < 1e-9 ? null : (spec.good === 'up') === d > 0
  return (
    <div className="vital" onClick={onClick} role="button" tabIndex={0} onKeyDown={e => { if (e.key === 'Enter') onClick() }}>
      <div><div style={{ fontWeight: 600 }}>{spec.label}</div><div className="v-delta" style={{ textAlign: 'left' }}>{d === undefined ? 'trend appears as time runs' : `${d >= 0 ? '▲' : '▼'} ${spec.fmt(Math.abs(d))} in 30 days${better === null ? '' : better ? ' · better' : ' · worse'}`}</div></div>
      <Sparkline values={vals.slice(-90)} color={better === false ? 'var(--serious)' : 'var(--accent)'} />
      <div className="v-val tabular">{now === undefined ? '—' : spec.fmt(now)}</div>
    </div>
  )
}

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
      <div>{(p.events ?? []).slice(0, 3).map((e: any) => <div key={e.id} className="story" style={{ padding: '4px 0' }}><span className="when tabular">{shortDate(e.date)}</span><Story e={e} me={p.id} /></div>)}
        {!(p.events ?? []).length && <div className="small muted">Nothing notable yet.</div>}</div>
    </div>
  )
}

/** Faint street map of Provo–Orem behind the hero, drawn from the real road network. */
function RoadSilhouette() {
  const ref = useRef<HTMLCanvasElement>(null)
  const theme = useStore(s => s.theme)
  const [roads, setRoads] = useState<any>(null)
  useEffect(() => { fetch(api.geo('roads.json')).then(r => r.json()).then(setRoads).catch(() => {}) }, [])
  const draw = useMemo(() => () => {
    const c = ref.current
    if (!c || !roads) return
    const W = c.clientWidth, H = c.clientHeight, dpr = window.devicePixelRatio || 1
    c.width = W * dpr; c.height = H * dpr
    const g = c.getContext('2d')!
    g.scale(dpr, dpr)
    const lon0 = -111.775, lon1 = -111.57, lat0 = 40.17, lat1 = 40.36
    const kx = Math.cos((40.27 * Math.PI) / 180)
    const s = Math.max(W / ((lon1 - lon0) * kx), H / (lat1 - lat0))
    const ox = (W - (lon1 - lon0) * kx * s) / 2, oy = (H - (lat1 - lat0) * s) / 2
    g.strokeStyle = cssVar('--text-muted')
    for (const f of roads.features) {
      const major = f.properties.c === 1
      g.globalAlpha = major ? 0.5 : 0.22
      g.lineWidth = major ? 1.3 : 0.6
      g.beginPath()
      f.geometry.coordinates.forEach(([x, y]: number[], k: number) => {
        const px = ox + (x - lon0) * kx * s, py = oy + (lat1 - y) * s
        k ? g.lineTo(px, py) : g.moveTo(px, py)
      })
      g.stroke()
    }
  }, [roads])
  useEffect(() => { draw() }, [draw, theme])
  return <canvas ref={ref} className="hero-map" aria-hidden="true" />
}
