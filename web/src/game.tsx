// Game-layer building blocks: the world lens (Original / What-if / Compare), universe badges, the
// divergence meter, life meters, icons, sparklines and a tiny async hook.
import { ReactNode, useEffect, useRef, useState } from 'react'
import { cssVar } from './components'
import { Lens, useLens, useStore } from './store'

// ---------------------------------------------------------------- universes
export const U_LABEL: Record<string, string> = { base: 'Original', alt: 'What-if', compare: 'Compare' }
export const uColor = (u: 'base' | 'alt') => cssVar(u === 'base' ? '--u-base' : '--u-alt')

export function UBadge({ u, children }: { u: 'base' | 'alt'; children?: ReactNode }) {
  return <span className={`ubadge ${u}`}><i />{children ?? U_LABEL[u]}</span>
}

export function LensSwitch({ compact = false }: { compact?: boolean }) {
  const { lens, hasAlt } = useLens()
  const setLens = useStore(s => s.setLens)
  const openDrawer = useStore(s => s.openDrawer)
  if (!hasAlt) {
    return (
      <button className="btn whatif-cta" onClick={() => openDrawer({})} title="Split the world in two and change something in one of them">
        {G.butterfly}<span>{compact ? 'What if…' : 'What if…?'}</span>
      </button>
    )
  }
  const opts: [Lens, string, string][] = [['base', 'Original', 'The world as it was (key 1)'], ['alt', 'What-if', 'The world with your change (key 2)'], ['compare', 'Compare', 'Both worlds side by side (key 3)']]
  return (
    <div className="lens" role="radiogroup" aria-label="Which world to show">
      {opts.map(([k, l, t]) => (
        <button key={k} role="radio" aria-checked={lens === k} className={`${k} ${lens === k ? 'on' : ''}`} onClick={() => setLens(k)} title={t}>
          <i />{compact ? l.slice(0, 4) : l}
        </button>
      ))}
    </div>
  )
}

/** How far apart the worlds have drifted: share of people whose lives differ visibly. */
export function DivergenceMeter({ onClick }: { onClick?: () => void }) {
  const status = useStore(s => s.status)
  const d = status?.divergence
  if (!status?.has_alt) return null
  const v = d?.any_state_diff ?? 0
  return (
    <button className="divmeter" onClick={onClick} title="Share of people living a noticeably different life in the What-if world (relationship, home, church activity or mood)">
      <span className="dm-icon">{G.butterfly}</span>
      <span className="dm-bar"><i style={{ width: `${Math.min(100, 100 * Math.sqrt(v))}%` }} /></span>
      <b className="tabular">{(100 * v).toFixed(v < 0.1 ? 1 : 0)}%</b>
      <span className="dm-lab">lives differ</span>
    </button>
  )
}

// ---------------------------------------------------------------- meters & numbers
/** A life bar (0–1), colored by whether higher is better, worse or neither. */
export function Meter({ label, value, alt, polarity = 0, onClick, active, hint }: {
  label: string; value: number | null | undefined; alt?: number | null; polarity?: 1 | -1 | 0; onClick?: () => void; active?: boolean; hint?: string
}) {
  const v = value === null || value === undefined || Number.isNaN(value) ? null : Math.max(0, Math.min(1, value))
  const a = alt === null || alt === undefined || Number.isNaN(alt as number) ? null : Math.max(0, Math.min(1, alt as number))
  const tone = v === null || polarity === 0 ? 'neutral' : (polarity > 0 ? v : 1 - v) >= 0.55 ? 'good' : (polarity > 0 ? v : 1 - v) <= 0.35 ? 'bad' : 'mid'
  return (
    <div className={`meter ${onClick ? 'click' : ''} ${active ? 'on' : ''}`} onClick={onClick} title={hint} role={onClick ? 'button' : undefined}>
      <span className="m-label">{label}</span>
      <span className={`m-track ${tone}`}>
        {v !== null && <i style={{ width: `${100 * v}%` }} />}
        {a !== null && <b className="m-alt" style={{ left: `${100 * a}%` }} title={`What-if: ${a.toFixed(2)}`} />}
      </span>
      <span className="m-val tabular">{v === null ? '—' : v.toFixed(2)}{a !== null && <small className="m-altv"> → {a.toFixed(2)}</small>}</span>
    </div>
  )
}

/** A number that counts up/down briefly when it changes. */
export function Ticker({ value, format = (x: number) => Math.round(x).toLocaleString() }: { value: number; format?: (x: number) => string }) {
  const [shown, setShown] = useState(value)
  const from = useRef(value)
  useEffect(() => {
    const a = from.current, b = value
    if (a === b) return
    const t0 = performance.now()
    let raf = 0
    const tick = (t: number) => {
      const k = Math.min(1, (t - t0) / 600)
      const e = 1 - (1 - k) ** 3
      setShown(a + (b - a) * e)
      if (k < 1) raf = requestAnimationFrame(tick)
      else from.current = b
    }
    raf = requestAnimationFrame(tick)
    return () => { cancelAnimationFrame(raf); from.current = b }
  }, [value])
  return <>{format(shown)}</>
}

export function DeltaChip({ d, text, polarity = 0, title }: { d: number; text: string; polarity?: 1 | -1 | 0; title?: string }) {
  const dir = Math.abs(d) < 1e-12 ? 'flat' : d > 0 ? 'up' : 'down'
  const tone = polarity === 0 || dir === 'flat' ? '' : (d > 0) === (polarity > 0) ? 'better' : 'worse'
  return <span className={`dchip ${dir} ${tone}`} title={title}>{dir === 'up' ? '▲' : dir === 'down' ? '▼' : '•'} {text}</span>
}

/** Small line: one or two series (Original solid, What-if orange), optional split marker. */
export function Spark({ a, b, width = 110, height = 30, mark, color }: { a: (number | null)[]; b?: (number | null)[]; width?: number; height?: number; mark?: number; color?: string }) {
  const all = [...a, ...(b ?? [])].filter((x): x is number => x !== null && Number.isFinite(x))
  if (all.length < 2) return <svg width={width} height={height} aria-hidden="true" />
  const lo = Math.min(...all), hi = Math.max(...all), span = hi - lo || Math.abs(hi) || 1
  const n = Math.max(a.length, b?.length ?? 0)
  const X = (k: number) => 2 + (k / Math.max(1, n - 1)) * (width - 4)
  const Y = (x: number) => height - 3 - ((x - lo) / span) * (height - 6)
  const path = (s: (number | null)[]) => {
    let d = '', pen = false
    s.forEach((x, k) => { if (x === null || !Number.isFinite(x)) { pen = false; return } d += `${pen ? 'L' : 'M'}${X(k).toFixed(1)},${Y(x).toFixed(1)}`; pen = true })
    return d
  }
  return (
    <svg width={width} height={height} aria-hidden="true" className="spark">
      {mark !== undefined && mark >= 0 && <line x1={X(mark)} x2={X(mark)} y1={0} y2={height} className="spark-mark" />}
      <path d={path(a)} fill="none" stroke={color ?? 'var(--u-base)'} strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
      {b && <path d={path(b)} fill="none" stroke="var(--u-alt)" strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />}
    </svg>
  )
}

// ---------------------------------------------------------------- async
export function useAsync<T>(fn: () => Promise<T>, deps: any[], keepOld = true): { data: T | null; error: string; loading: boolean } {
  const [st, setSt] = useState<{ data: T | null; error: string; loading: boolean }>({ data: null, error: '', loading: true })
  useEffect(() => {
    let alive = true
    setSt(s => ({ data: keepOld ? s.data : null, error: '', loading: true }))
    fn().then(d => { if (alive) setSt({ data: d, error: '', loading: false }) })
      .catch(e => { if (alive) setSt({ data: null, error: String(e?.message ?? e), loading: false }) })
    return () => { alive = false }
  }, deps)
  return st
}

// ---------------------------------------------------------------- icons
const I = (d: string, extra?: ReactNode) => <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={d} />{extra}</svg>
export const G: Record<string, JSX.Element> = {
  globe: I('M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM3.6 9h16.8M3.6 15h16.8M12 3a14 14 0 0 1 0 18M12 3a14 14 0 0 0 0 18'),
  butterfly: I('M12 7v13M12 9c-1-3-4-5.5-7-5.5-1.5 0-2 1.3-1.6 3 .5 2.4 2.5 4 4.6 4.5-2 .6-3.3 2.2-3 4 .4 2 2.6 2.9 4.6 1.5 1.1-.8 2-2.2 2.4-3.5M12 9c1-3 4-5.5 7-5.5 1.5 0 2 1.3 1.6 3-.5 2.4-2.5 4-4.6 4.5 2 .6 3.3 2.2 3 4-.4 2-2.6 2.9-4.6 1.5-1.1-.8-2-2.2-2.4-3.5M10 4.5 12 7l2-2.5'),
  search: I('M11 18a7 7 0 1 0 0-14 7 7 0 0 0 0 14zM21 21l-4.3-4.3'),
  pin: I('M12 17v5M9 3h6l-1 6 3 3v2H7v-2l3-3z'),
  play: I('M7 4v16l13-8z'),
  pause: I('M7 4h4v16H7zM13 4h4v16h-4z'),
  fast: I('M4 5v14l8-7zM12 5v14l8-7z'),
  slow: I('M6 4v16l13-8z'),
  step: I('M5 5v14l9-7zM17 5v14'),
  heart: I('M12 20s-7-4.4-9.2-9C1.4 8 3 4.5 6.5 4.5c2 0 3.5 1.2 4.5 2.8h2c1-1.6 2.5-2.8 4.5-2.8 3.5 0 5.1 3.5 3.7 6.5C19 15.6 12 20 12 20z'),
  romance: I('M12 20s-7-4.4-9.2-9C1.4 8 3 4.5 6.5 4.5c2 0 3.5 1.2 4.5 2.8h2c1-1.6 2.5-2.8 4.5-2.8 3.5 0 5.1 3.5 3.7 6.5C19 15.6 12 20 12 20z'),
  people: I('M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM22 21v-2a4 4 0 0 0-3-3.9M16 3.1a4 4 0 0 1 0 7.8'),
  rings: I('M9 15a5 5 0 1 0 0-.01M15 15a5 5 0 1 0 0-.01M10 4l2 3 2-3'),
  spark: I('M12 3v4M12 17v4M3 12h4M17 12h4M6 6l2.5 2.5M15.5 15.5 18 18M6 18l2.5-2.5M15.5 8.5 18 6'),
  faith: I('M12 3v18M7 8h10M5 21h14'),
  scale: I('M12 3v18M5 7h14M5 7l-3 7a3 3 0 0 0 6 0zM19 7l-3 7a3 3 0 0 0 6 0zM8 21h8'),
  school: I('M2 9l10-5 10 5-10 5zM6 11v5c0 1.7 2.7 3 6 3s6-1.3 6-3v-5M22 9v6'),
  money: I('M3 6h18v12H3zM12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM6 9v.01M18 15v.01'),
  places: I('M3 21h18M5 21V7l7-4 7 4v14M9 21v-6h6v6'),
  coffee: I('M4 8h13v5a5 5 0 0 1-5 5H9a5 5 0 0 1-5-5zM17 9h1.5a2.5 2.5 0 0 1 0 5H17M7 2v3M11 2v3'),
  mask: I('M4 5h16v6a8 8 0 0 1-16 0zM8.5 10h.01M15.5 10h.01M9 14.5c1.7 1.3 4.3 1.3 6 0'),
  id: I('M3 5h18v14H3zM8 11a2 2 0 1 0 0-.01M5.5 16c.6-1.5 1.5-2.2 2.5-2.2s1.9.7 2.5 2.2M14 9h4M14 13h4'),
  clock: I('M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM12 7v5l3 2'),
  map: I('M9 4 3 6v14l6-2 6 2 6-2V4l-6 2-6-2zM9 4v14M15 6v14'),
  events: I('M13 2 4 14h7l-1 8 9-12h-7z'),
  explore: I('M3 3v18h18M7 15l4-4 3 3 5-6'),
  network: I('M5 6a2 2 0 1 0 0-.1M19 6a2 2 0 1 0 0-.1M12 19a2 2 0 1 0 0-.1M6.7 7.2l4.2 9.6M17.3 7.2l-4.2 9.6M7 6h10'),
  flask: I('M9 3h6M10 3v6L4 20h16L14 9V3'),
  book: I('M4 5a2 2 0 0 1 2-2h13v16H6a2 2 0 0 0-2 2zM4 5v16M8 7h7M8 11h5'),
  desk: I('M3 7h18M5 7v13M19 7v13M3 20h18M8 7V4h8v3M8 12h8'),
  gear: I('M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z'),
  sun: I('M12 17a5 5 0 1 0 0-10 5 5 0 0 0 0 10zM12 1v2M12 21v2M4.2 4.2l1.4 1.4M18.4 18.4l1.4 1.4M1 12h2M21 12h2M4.2 19.8l1.4-1.4M18.4 5.6l1.4-1.4'),
  moon: I('M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z'),
  trend: I('M3 17l6-6 4 4 8-8M15 7h6v6'),
  bell: I('M18 8a6 6 0 1 0-12 0c0 7-3 9-3 9h18s-3-2-3-9M13.7 21a2 2 0 0 1-3.4 0'),
  close: I('M18 6 6 18M6 6l12 12'),
  plus: I('M12 5v14M5 12h14'),
  chevron: I('M9 18l6-6-6-6'),
  link: I('M10 13a5 5 0 0 0 7.5.5l3-3a5 5 0 0 0-7-7l-1.7 1.7M14 11a5 5 0 0 0-7.5-.5l-3 3a5 5 0 0 0 7 7l1.7-1.7'),
  home: I('M3 11 12 3l9 8M5 10v10h5v-6h4v6h5V10'),
  work: I('M3 7h18v13H3zM8 7V4h8v3M3 12h18'),
  health: I('M3 12h4l3-8 4 16 3-8h4'),
  key: I('M15 7a4 4 0 1 0 0 .01M12.5 9.5 3 19v2h3v-2h2v-2h2l2.5-2.5'),
  family: I('M8 7a3 3 0 1 0 0-.01M17 9a2 2 0 1 0 0-.01M3 21v-3a5 5 0 0 1 10 0v3M14 21v-2a3 3 0 0 1 6 0v2'),
  lab: I('M9 3h6M10 3v6L4 20h16L14 9V3'),
}

/** Icon per event category. */
export const CAT_ICON: Record<string, string> = {
  social: 'people', romance: 'romance', religion: 'faith', academics: 'school', work: 'work', family: 'family', health: 'health',
  housing: 'key', habits: 'coffee', sexuality: 'heart', intervention: 'butterfly',
}
export function CatIcon({ c }: { c?: string }) {
  return <span className={`caticon c-${c ?? 'other'}`}>{G[CAT_ICON[c ?? ''] ?? 'events']}</span>
}

export const timeOfDay = (hour: number) => (hour < 6 || hour >= 21 ? 'night' : hour < 9 ? 'dawn' : hour < 17 ? 'day' : 'dusk')
