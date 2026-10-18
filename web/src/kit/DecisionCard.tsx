// One recorded decision, read back: what was being decided, what came out and how likely the model thought it was,
// and the reasons as diverging bars (the model's own terms, not an interpretation). Hard limits show as "couldn't".
import { traceApi, type DecisionDetail, type DecisionFactor, type TraceRef, type Universe } from '../api'
import { useAsync } from '../game'
import { dayLabel } from './traceRefs'
import './trace.css'

const nice = (s: unknown) => String(s ?? '').replace(/_/g, ' ')
/** "a 34% chance", "less than a 1% chance" */
const chanceWords = (p: number | null | undefined) => (p === null || p === undefined || !Number.isFinite(p) ? null
  : p < 0.01 ? 'less than a 1% chance' : p > 0.99 ? 'more than a 99% chance' : `a ${Math.round(p * 100)}% chance`)

/** Which way the bars point: right = toward this outcome. Yes/no choices have a "positive" outcome; a choice among
 *  options records the chosen option's terms, so right = toward what was chosen. */
function orientation(d: DecisionDetail) {
  const outcome = nice(d.outcome)
  if (d.units === 'utility' || d.units === 'log') return { right: `toward “${outcome}”`, left: 'away from it', happenedIsRight: true }
  const pos = d.positive ? nice(d.positive) : outcome
  const others = (d.outcomes ?? []).map(nice).filter(o => o !== pos)
  const left = others.length === 1 ? `toward “${others[0]}”` : `against “${pos}”`
  return { right: `toward “${pos}”`, left, happenedIsRight: pos === outcome }
}

export function DecisionCard({ id, u = 'base', data, onRef, startDate, compact = false }: {
  id?: number; u?: Universe; data?: DecisionDetail
  /** open what a factor points at (a person, an event, a feeling…) — e.g. trace it */
  onRef?: (r: TraceRef, label?: string) => void
  startDate?: string; compact?: boolean
}) {
  const fetched = useAsync(() => (data || id === undefined ? Promise.resolve(null) : traceApi.decision(id, u)), [id, u, !!data], false)
  const d = data ?? fetched.data
  if (!d) {
    if (fetched.error) return <div className="dc dc-empty">{fetched.error}</div>
    return <div className="dc dc-empty">Loading the decision…</div>
  }
  const cons = d.factors.filter(f => f.constraint)
  const terms = d.factors.filter(f => !f.constraint)
  const chance = d.units === 'probability'
  const o = orientation(d)
  const scale = Math.max(0.5, ...terms.map(f => Math.abs(f.value)))
  const p = chanceWords(d.prob)
  return (
    <div className={`dc${compact ? ' dc-compact' : ''}`}>
      <div className="dc-head">
        <div className="dc-q">{d.label}</div>
        <div className="dc-who">
          {d.agent_name ?? `Person ${d.agent}`}
          {d.other !== null && d.other !== undefined && <> · about {d.other_name ?? `person ${d.other}`}</>}
          <span className="muted"> · {d.date ? new Date(d.date + 'T12:00:00').toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' }) : dayLabel(startDate, d.day)}</span>
        </div>
        <div className="dc-out">
          <span className="dc-outcome">→ {nice(d.outcome)}</span>
          {p && <span className="muted">the model gave this {p}</span>}
        </div>
      </div>
      {cons.length > 0 && (
        <div className="dc-cons">
          {cons.map(f => <span key={f.factor} className="dc-couldnt" title={f.label}>couldn't: {f.words || f.label}</span>)}
        </div>
      )}
      {chance && !terms.length ? (
        <p className="dc-note">Left to chance: the model gives everyone in this situation the same {p ?? 'small chance'}, so nothing
          about this person made it more or less likely.</p>
      ) : terms.length ? (
        <>
          <div className="dc-axis"><span>◀ {o.left}</span><span>{o.right} ▶</span></div>
          <div className="dc-rows">
            {terms.map(f => <FactorRow key={f.factor} f={f} scale={scale} happenedIsRight={o.happenedIsRight} onRef={onRef} />)}
          </div>
          {!compact && (
            <p className="dc-note">
              Each bar is one term the model added up ({d.units_words ?? d.units}); the starting point was {fmtV(d.base)} and the
              total {fmtV(d.total)}. Only the {d.factors.length < 6 ? '' : 'six '}largest terms are kept.
            </p>
          )}
        </>
      ) : <p className="dc-note">No reasons were recorded for this choice beyond how common it is.</p>}
      {!compact && d.events && d.events.length > 0 && (
        <div className="dc-led">
          <div className="dc-led-h">What it led to</div>
          {d.events.map(e => (
            <button key={e.id} className="dc-ev" onClick={() => onRef?.({ kind: 'event', id: e.id }, e.label)} disabled={!onRef}>{e.label}</button>
          ))}
        </div>
      )}
    </div>
  )
}

const fmtV = (v: number) => (v >= 0 ? '+' : '−') + Math.abs(v).toFixed(2)

function FactorRow({ f, scale, happenedIsRight, onRef }: { f: DecisionFactor; scale: number; happenedIsRight: boolean; onRef?: (r: TraceRef, label?: string) => void }) {
  const W = 120, H = 14, mid = W / 2
  const len = Math.max(1.5, (Math.abs(f.value) / scale) * (mid - 2))
  const right = f.value >= 0
  // toward what actually happened (solid) or holding it back (soft)
  const toward = right === happenedIsRight
  const mult = f.kind === 'multiplier'
  return (
    <div className="dc-row" title={`${f.label}: ${fmtV(f.value)}${mult ? ' (log of a multiplier on the chance)' : ''}`}>
      <div className="dc-words">
        <b>{f.words || f.label}</b>
        {f.words && f.words !== f.label && <small>{f.label}</small>}
        {f.ref && f.ref_label && (
          <button className="dc-ref" onClick={() => onRef?.(f.ref!, f.ref_label)} disabled={!onRef} title="Trace this">{f.ref_label}</button>
        )}
      </div>
      <svg width={W} height={H} className="dc-bar" aria-hidden="true">
        <line x1={mid} x2={mid} y1={0} y2={H} className="dc-zero" />
        <rect x={right ? mid : mid - len} y={2} width={len} height={H - 4} rx={2} className={toward ? 'dc-toward' : 'dc-against'} />
      </svg>
      <span className="dc-val tabular">{fmtV(f.value)}</span>
    </div>
  )
}
