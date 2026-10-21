import { useEffect, useState } from 'react'
import { api, type PerfEstimate } from '../api'
import { G } from '../game'
import { useStore } from '../store'

// Starting population at scale 1 ≈ 60k (students, spouses, young adults, faculty/staff, community).
const PER_UNIT = 60000
// Rule of thumb before this computer has run a world: single-core seconds per day at full scale early on, and how much
// slower days get once the world's records fill up (measured over a semester; see the Speed tool for this computer).
const SEC_PER_DAY_PER_UNIT = 1.8
const LATER_FACTOR = 1.3

const PRESETS: { scale: number; label: string; hint: string }[] = [
  { scale: 0.05, label: 'Quick', hint: 'try things out' },
  { scale: 0.15, label: 'Standard', hint: 'most analysis' },
  { scale: 0.3, label: 'Detailed', hint: 'richer networks' },
  { scale: 1.0, label: 'Full', hint: 'real population size' },
]

/** Time estimates: measured on this computer when a world of a similar size ran here before, else a rule of thumb. */
function estimate(scale: number, warmup: number, m?: PerfEstimate | null) {
  const people = Math.round((scale * PER_UNIT) / 100) * 100
  const measured = !!m?.measured && !!m.early_s
  const early = measured ? m!.early_s! : scale * SEC_PER_DAY_PER_UNIT
  const later = measured && m!.later_s ? m!.later_s : early * LATER_FACTOR
  const build = (measured && m!.build_s ? m!.build_s : 2 + 12 * scale) + warmup * early
  const fmtS = (s: number) => (s < 90 ? `${Math.max(1, Math.round(s))} s` : s < 5400 ? `${Math.round(s / 60)} min` : `${(s / 3600).toFixed(1)} h`)
  const fmtD = (s: number) => (s < 1 ? s.toFixed(2) : s < 10 ? s.toFixed(1) : String(Math.round(s)))
  return {
    people, measured, from: m?.from_scale,
    perDay: Math.abs(later - early) / early < 0.15 ? `${fmtD(early)} s` : `${fmtD(early)}–${fmtD(later)} s`,
    build: fmtS(build), year: fmtS(365 * (early + later) / 2),
  }
}

export function WorldForm({ onDone, compact }: { onDone?: () => void; compact?: boolean }) {
  const { status, refreshStatus } = useStore()
  const [scale, setScale] = useState<number>(status?.scale ?? 0.15)
  const [seed, setSeed] = useState<number>(status?.seed ?? 1)
  const [warmup, setWarmup] = useState(14)
  const [err, setErr] = useState('')
  const [confirm, setConfirm] = useState(false)
  const [measured, setMeasured] = useState<PerfEstimate | null>(null)
  useEffect(() => {
    let alive = true
    const t = window.setTimeout(() => api.perfEstimate(scale).then(m => { if (alive) setMeasured(m) }).catch(() => {}), 150)
    return () => { alive = false; window.clearTimeout(t) }
  }, [scale])
  const e = estimate(scale, warmup, measured)
  const hasWorld = !!status?.has_world
  const busy = status?.job?.state === 'running' || status?.job?.state === 'building'

  const build = async () => {
    if (hasWorld && !confirm) { setConfirm(true); return }
    setErr('')
    try {
      await api.newWorld(scale, seed, warmup)
      await refreshStatus()
      onDone?.()
    } catch (x: any) { setErr(String(x.message ?? x)) }
  }

  return (
    <div className="world-form">
      <div>
        <label className="small muted" htmlFor="world-scale">How big a world?</label>
        <div className={compact ? 'seg' : 'size-cards'} style={{ marginTop: 6, flexWrap: 'wrap' }}>
          {PRESETS.map(p => (
            <button key={p.scale} className={`${compact ? '' : 'size-card'} ${Math.abs(scale - p.scale) < 1e-9 ? 'on' : ''}`} onClick={() => setScale(p.scale)} title={p.hint}>
              {compact ? <>{p.label} <span className="muted">{p.scale}</span></> : <><b>{p.label}</b><span className="tabular">≈{(Math.round((p.scale * PER_UNIT) / 100) * 100).toLocaleString()} people</span><small>{p.hint}</small></>}
            </button>
          ))}
        </div>
        <div className="row" style={{ marginTop: 8 }}>
          <input id="world-scale" type="range" min={0.02} max={1} step={0.01} value={scale} onChange={x => setScale(Number(x.target.value))} style={{ flex: 1 }} />
          <input type="number" min={0.02} max={1} step={0.01} value={scale} onChange={x => setScale(Math.min(1, Math.max(0.02, Number(x.target.value) || 0.02)))} style={{ width: 76 }} aria-label="Scale" />
        </div>
        <p className="hint">Scale is the share of the real BYU/UVU community that gets simulated. Housing, wards and venues are always the real ones; fewer people means sparser neighborhoods and faster runs.</p>
      </div>
      <div className="grid" style={{ gridTemplateColumns: compact ? '1fr 1fr' : 'repeat(4, minmax(0, 1fr))', gap: 10 }}>
        <div className="tile"><div className="small muted">People</div><div className="value tabular">≈{e.people.toLocaleString()}</div></div>
        <div className="tile"><div className="small muted">Per simulated day</div><div className="value tabular">≈{e.perDay}</div></div>
        <div className="tile"><div className="small muted">One simulated year</div><div className="value tabular">≈{e.year}</div></div>
        <div className="tile"><div className="small muted">Ready in</div><div className="value tabular">≈{e.build}</div></div>
      </div>
      <p className="hint" style={{ marginTop: -4 }}>{e.measured
        ? `Measured on this computer (from a world of scale ${e.from} that ran here). Days take longer later in a world's life, and about twice as long with a What-if world beside it.`
        : 'A rule of thumb until this computer has run a world; after that, these numbers come from how fast it actually ran. A What-if world beside it roughly doubles the time.'}</p>
      <div className="row" style={{ gap: 16, flexWrap: 'wrap' }}>
        <label className="inline small" htmlFor="world-seed">World number
          <input id="world-seed" type="number" value={seed} onChange={x => setSeed(Math.max(0, Math.floor(Number(x.target.value) || 0)))} style={{ width: 90 }} />
          <button className="btn small" onClick={() => setSeed(1 + Math.floor(Math.random() * 99999))} title="Roll a new world">🎲 Roll</button>
        </label>
        <label className="inline small" htmlFor="world-warmup">Warm-up
          <select id="world-warmup" value={warmup} onChange={x => setWarmup(Number(x.target.value))}>
            {[0, 7, 14, 30].map(d => <option key={d} value={d}>{d === 0 ? 'none' : `${d} days`}</option>)}
          </select>
        </label>
      </div>
      <p className="hint">The same world number and size always produce the same people and the same history. Warm-up lets friendships and dating get going before you start watching (the year begins Aug 24, the first day of fall semester).</p>
      {confirm && hasWorld && <div className="pill" style={{ color: 'var(--warning-text, var(--text-primary))' }}>This replaces the current world{status?.has_alt ? ' and its intervention universe' : ''}. Click again to confirm.</div>}
      {err && <div className="pill" style={{ color: 'var(--critical)' }}>{err}</div>}
      <div className="row">
        <button className={`btn primary ${compact ? '' : 'big'}`} disabled={busy} onClick={build}>{hasWorld ? (confirm ? 'Replace world' : 'Build new world') : 'Create the world ▶'}</button>
        {onDone && <button className="btn" onClick={onDone}>Cancel</button>}
        {busy && <span className="small muted">The simulator is busy; pause it first.</span>}
      </div>
    </div>
  )
}

export function WorldSetupPage() {
  const { status } = useStore()
  const job = status?.job ?? {}
  if (job.state === 'building') return <BuildingProgress />
  return (
    <div className="title-screen">
      <div className="ts-card">
        <div className="ts-logo">{G.butterfly}</div>
        <div className="eyebrow">Utah County College Social Simulator</div>
        <h1>Provo–Orem</h1>
        <p className="ts-sub">A living social world: students, spouses, young adults, faculty and neighbors in real Provo and Orem housing. They make friends, date, marry, doubt, believe, struggle with money and feel lonely or connected, one simulated day at a time. Then you change something, and watch two worlds drift apart.</p>
        {job.state === 'error' && <div className="pill" style={{ color: 'var(--critical)', marginBottom: 10 }}>Last build failed: {job.error}</div>}
        <WorldForm />
      </div>
    </div>
  )
}

// What the builder actually does, in order (ucsim/population/build.py) — shown while it works.
const STEPS = ['Laying out real Provo and Orem: homes, apartment complexes, dorms', 'Creating people from aggregate survey patterns (never real respondents)',
  'Matching couples and placing families', 'Moving people into homes and choosing roommates', 'Assigning wards, FHE groups, congregations and clubs',
  'Enrolling students at BYU and UVU, with real majors', 'Finding jobs', 'Seeding the friendships people arrive with']

export function BuildingProgress() {
  const { status } = useStore()
  const job = status?.job ?? {}
  const warming = job.phase === 'warming up'
  const [k, setK] = useState(0)
  useEffect(() => { if (warming) return; const t = setInterval(() => setK(x => Math.min(STEPS.length - 1, x + 1)), 1600); return () => clearInterval(t) }, [warming])
  const pct = warming ? 100 * (job.progress ?? 0) / (job.total || 1) : (100 * (k + 1)) / (STEPS.length + 1)
  return (
    <div className="title-screen">
      <div className="ts-card loading">
        <div className="boot-orbit"><i /><i /><i /></div>
        <h2>{warming ? `Letting the world settle in: day ${job.progress} of ${job.total}` : `Building a world of ≈${(Math.round(((job.scale ?? 0) * PER_UNIT) / 100) * 100).toLocaleString()} people`}</h2>
        <p className="ts-sub">{warming ? 'Classes start, roommates meet, wards gather, first dates happen' : STEPS[k]}…</p>
        <div className="ts-progress"><i style={{ width: `${pct}%` }} /></div>
        <div className="small muted">size {job.scale} · world #{job.seed}</div>
      </div>
    </div>
  )
}

export function WorldDialog({ onClose }: { onClose: () => void }) {
  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal card" role="dialog" aria-label="New world" onClick={e => e.stopPropagation()}>
        <div className="row" style={{ marginBottom: 8 }}><h2 style={{ margin: 0 }}>New world</h2><span className="spacer" /><button className="btn small" onClick={onClose} aria-label="Close">✕</button></div>
        <WorldForm onDone={onClose} compact />
      </div>
    </div>
  )
}
