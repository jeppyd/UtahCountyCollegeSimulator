// The share of the push behind something, as one bar split into its reasons (the largest first) with their words.
// Shares are the model's own terms: each reason's part of the total push it recorded.
import type { WhyItem } from '../api'

const TONES = ['var(--u-base)', 'var(--u-alt)', 'var(--s3)', 'var(--s4, #b38bd6)', 'var(--s5, #e0a458)']

export const pct = (x: number) => `${Math.round(100 * x)}%`

export function ShareBar({ toward, against = [], onPick }: { toward: WhyItem[]; against?: WhyItem[]; onPick?: (w: WhyItem) => void }) {
  const all = [...toward, ...against]
  if (!all.length) return <div className="bx-note">Nothing recorded behind this.</div>
  const top = toward.slice(0, 5)
  const rest = toward.slice(5).reduce((a, w) => a + w.share, 0)
  const vs = against.reduce((a, w) => a + w.share, 0)
  return (
    <div className="sh">
      <div className="sh-bar" role="img" aria-label="share of the push">
        {top.map((w, k) => <i key={k} style={{ width: pct(w.share), background: TONES[k % TONES.length] }} title={`${w.words}: ${pct(w.share)}`} />)}
        {rest > 0 && <i style={{ width: pct(rest), background: 'var(--text-muted)' }} title={`other reasons: ${pct(rest)}`} />}
        {vs > 0 && <i className="sh-vs" style={{ width: pct(vs) }} title={`pushed the other way: ${pct(vs)}`} />}
      </div>
      <ul className="sh-list">
        {top.map((w, k) => (
          <li key={k} className={onPick && w.ref ? 'click' : ''} onClick={() => onPick && w.ref && onPick(w)}>
            <i style={{ background: TONES[k % TONES.length] }} /><b>{pct(w.share)}</b> {w.words}
          </li>
        ))}
        {rest > 0 && <li><i style={{ background: 'var(--text-muted)' }} /><b>{pct(rest)}</b> {toward.length - 5} smaller reasons</li>}
        {against.slice(0, 4).map((w, k) => (
          <li key={`a${k}`} className={`sh-against ${onPick && w.ref ? 'click' : ''}`} onClick={() => onPick && w.ref && onPick(w)}>
            <i className="sh-vs" /><b>{pct(w.share)}</b> against: {w.words}
          </li>
        ))}
      </ul>
    </div>
  )
}
