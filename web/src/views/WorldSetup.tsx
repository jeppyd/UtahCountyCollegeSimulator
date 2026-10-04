import { useState } from 'react'
import { api } from '../api'
import { useStore } from '../store'

// Starting population at scale 1 ≈ 60k (students, spouses, young adults, faculty/staff, community).
const PER_UNIT = 60000
// Rough single-core cost; real speed depends on the machine and grows a little as relationships accumulate.
const SEC_PER_DAY_PER_UNIT = 1.8

const PRESETS: { scale: number; label: string; hint: string }[] = [
  { scale: 0.05, label: 'Quick', hint: 'try things out' },
  { scale: 0.15, label: 'Standard', hint: 'most analysis' },
  { scale: 0.3, label: 'Detailed', hint: 'richer networks' },
  { scale: 1.0, label: 'Full', hint: 'real population size' },
]

function estimate(scale: number, warmup: number) {
  const people = Math.round((scale * PER_UNIT) / 100) * 100
  const perDay = scale * SEC_PER_DAY_PER_UNIT
  const build = 2 + 12 * scale + warmup * perDay
  const fmtS = (s: number) => (s < 90 ? `${Math.max(1, Math.round(s))} s` : `${Math.round(s / 60)} min`)
  return { people, perDay: perDay < 1 ? `${perDay.toFixed(2)} s` : fmtS(perDay), build: fmtS(build), year: fmtS(365 * perDay) }
}

export function WorldForm({ onDone, compact }: { onDone?: () => void; compact?: boolean }) {
  const { status, refreshStatus } = useStore()
  const [scale, setScale] = useState<number>(status?.scale ?? 0.15)
  const [seed, setSeed] = useState<number>(status?.seed ?? 1)
  const [warmup, setWarmup] = useState(14)
  const [err, setErr] = useState('')
  const [confirm, setConfirm] = useState(false)
  const e = estimate(scale, warmup)
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
        <label className="small muted" htmlFor="world-scale">Population scale</label>
        <div className="seg" style={{ marginTop: 6, flexWrap: 'wrap' }}>
          {PRESETS.map(p => (
            <button key={p.scale} className={Math.abs(scale - p.scale) < 1e-9 ? 'on' : ''} onClick={() => setScale(p.scale)} title={p.hint}>
              {p.label} <span className="muted">{p.scale}</span>
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
      <div className="row" style={{ gap: 16, flexWrap: 'wrap' }}>
        <label className="inline small" htmlFor="world-seed">Random seed
          <input id="world-seed" type="number" value={seed} onChange={x => setSeed(Math.max(0, Math.floor(Number(x.target.value) || 0)))} style={{ width: 90 }} />
          <button className="btn small" onClick={() => setSeed(1 + Math.floor(Math.random() * 99999))}>New</button>
        </label>
        <label className="inline small" htmlFor="world-warmup">Warm-up
          <select id="world-warmup" value={warmup} onChange={x => setWarmup(Number(x.target.value))}>
            {[0, 7, 14, 30].map(d => <option key={d} value={d}>{d === 0 ? 'none' : `${d} days`}</option>)}
          </select>
        </label>
      </div>
      <p className="hint">The same seed and scale always produce the same people and the same history. Warm-up lets friendships and dating get going before you start watching (the run begins Aug 24, the start of fall semester).</p>
      {confirm && hasWorld && <div className="pill" style={{ color: 'var(--warning-text, var(--text-primary))' }}>This replaces the current world{status?.has_alt ? ' and its intervention universe' : ''}. Click again to confirm.</div>}
      {err && <div className="pill" style={{ color: 'var(--critical)' }}>{err}</div>}
      <div className="row">
        <button className="btn primary" disabled={busy} onClick={build}>{hasWorld ? (confirm ? 'Replace world' : 'Build new world') : 'Build world'}</button>
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
    <div className="setup-page">
      <div className="card">
        <h1 style={{ marginTop: 0 }}>Create a world</h1>
        <p className="sub">Synthesize a population of students, spouses, young adults, faculty and neighbors in real Provo and Orem housing. You can rebuild at a different scale any time from the top bar.</p>
        {job.state === 'error' && <div className="pill" style={{ color: 'var(--critical)', marginBottom: 10 }}>Last build failed: {job.error}</div>}
        <WorldForm />
      </div>
    </div>
  )
}

export function BuildingProgress() {
  const { status } = useStore()
  const job = status?.job ?? {}
  const pct = job.phase === 'warming up' ? (100 * (job.progress ?? 0)) / (job.total || 1) : 8
  return (
    <div className="empty">
      <div>{job.phase === 'warming up' ? `Warming up: day ${job.progress} of ${job.total}` : `Synthesizing ${Math.round(((job.scale ?? 0) * PER_UNIT) / 100) * 100 || ''} people…`}</div>
      <div className="progress" style={{ margin: '12px auto' }}><i style={{ width: `${pct}%` }} /></div>
      <div className="small">scale {job.scale} · seed {job.seed}</div>
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
