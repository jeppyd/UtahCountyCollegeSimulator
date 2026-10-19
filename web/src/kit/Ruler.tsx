// The ruler: a field's scale drawn as a track from its lowest to its highest value, with anchor words along it, where
// people sit today (the middle half as a band, the 10th–90th percentiles as whiskers, the median as a tick) and,
// optionally, one value marked with what it means: "0.62 · lonely most days · higher than 78% of people".
// `inline` is one quiet line for tables and person pages; `full` writes out every anchor.
import { fval } from '../fields'
import { useStore } from '../store'
import { useWidth } from './Bits'
import { anchorWords, pctOf, pctWords, pos, useDist, useScale, viewOf, type Anchor, type Dist, type Scale } from './scales'
import './scales.css'

/** The anchors to draw: the scale's own, else its answer levels spread evenly, else its two ends. */
export function anchorsOf(sc: Scale, d?: Dist | null): Anchor[] {
  if (sc.anchors?.length) return sc.anchors
  const [lo, hi] = viewOf(sc, d)
  if (sc.levels?.length) return sc.levels.map((l, k) => ({ at: lo + (k / Math.max(1, sc.levels!.length - 1)) * (hi - lo), label: l }))
  return [{ at: lo, label: sc.low ?? String(lo) }, { at: hi, label: sc.high ?? String(hi) }]
}

/** A value in words: the number, its anchor words and where it sits among people. */
export function useValueWords(v: string, x: number | null | undefined, d?: Dist | null): { num: string; words: string; pct: string } {
  const spec = useStore(s => s.registry?.variables[v])
  const sc = useScale(v)
  if (x === null || x === undefined || !Number.isFinite(x)) return { num: '—', words: '', pct: '' }
  return { num: fval(spec, x), words: anchorWords(sc, x), pct: pctWords(pctOf(d, x)) }
}

export function Ruler({ v, value, variant = 'full', caption = true, dist }: {
  v: string; value?: number | null; variant?: 'inline' | 'full'; caption?: boolean; dist?: Dist | null
}) {
  const sc = useScale(v)
  const spec = useStore(s => s.registry?.variables[v])
  const live = useDist(dist === undefined ? v : undefined)
  const d = dist === undefined ? live : dist
  const [wrap, w] = useWidth<HTMLDivElement>(variant === 'inline' ? 160 : 420)
  const vw = useValueWords(v, value, d)
  if (!sc) return null
  const inline = variant === 'inline'
  const L = 6, R = 6, W = Math.max(80, w), X = (x: number) => L + pos(x, sc, d) * (W - L - R)
  const ty = inline ? 9 : 24
  const anchors = anchorsOf(sc, d)
  const has = value !== null && value !== undefined && Number.isFinite(value)
  // labels: as many characters as fit between neighbouring anchors; the full words on hover
  const xs = anchors.map(a => X(a.at))
  const room = (k: number) => {
    const left = k === 0 ? xs[k] - L : (xs[k] - xs[k - 1]) / 2
    const right = k === xs.length - 1 ? W - R - xs[k] : (xs[k + 1] - xs[k]) / 2
    return k === 0 ? right * 2 : k === xs.length - 1 ? left * 2 : Math.min(left, right) * 2
  }
  const fit = (s: string, px: number) => { const n = Math.max(3, Math.floor(px / 6.2)); return s.length <= n ? s : s.slice(0, n - 1).trimEnd() + '…' }
  const hist = !inline && d?.hist
  const hmax = hist ? Math.max(...d!.hist!.counts, 1) : 1

  return (
    <div className={`ruler ${inline ? 'inline' : 'full'}`} ref={wrap}>
      <svg width={W} height={inline ? 18 : 64} role="img" aria-label={`${v} scale${has ? `: ${vw.num}, ${vw.words}` : ''}`}>
        {hist && d!.hist!.counts.map((c, k) => {
          const x0 = X(d!.hist!.edges[k]), x1 = X(d!.hist!.edges[k + 1])
          const h = (c / hmax) * 14
          return <rect key={k} className="ruler-hist" x={x0} y={ty - 5 - h} width={Math.max(0.5, x1 - x0 - 0.5)} height={h} />
        })}
        <line className="ruler-track" x1={L} x2={W - R} y1={ty} y2={ty} />
        {anchors.map((a, k) => <line key={k} className="ruler-tick" x1={xs[k]} x2={xs[k]} y1={ty - 3} y2={ty + 3} />)}
        {d && <>
          <line className="ruler-whisk" x1={X(d.p10)} x2={X(d.p90)} y1={ty} y2={ty} />
          <rect className="ruler-band" x={X(d.p25)} y={ty - 3.5} width={Math.max(2, X(d.p75) - X(d.p25))} height={7} rx={3.5}>
            <title>{`The middle half of people: ${fval(spec, d.p25)} to ${fval(spec, d.p75)} (10th–90th percentile: ${fval(spec, d.p10)} to ${fval(spec, d.p90)})`}</title>
          </rect>
          <line className="ruler-med" x1={X(d.p50)} x2={X(d.p50)} y1={ty - 5} y2={ty + 5}><title>{`Median: ${fval(spec, d.p50)}`}</title></line>
        </>}
        {!inline && anchors.map((a, k) => (
          <text key={k} className="ruler-word" x={xs[k]} y={ty + 16 + (anchors.length > 3 && k % 2 ? 12 : 0)}
            textAnchor={k === 0 ? 'start' : k === anchors.length - 1 ? 'end' : 'middle'}>
            <title>{`${fval(spec, a.at)}: ${a.label}${a.more ? ` — ${a.more}` : ''}`}</title>
            {fit(a.label, anchors.length > 3 ? room(k) * 1.8 : room(k))}
          </text>
        ))}
        {has && <g className="ruler-mark" transform={`translate(${X(value!)}, ${ty})`}>
          <circle r={inline ? 4 : 5} /><title>{`${vw.num} · ${vw.words}${vw.pct ? ` · ${vw.pct}` : ''}`}</title>
        </g>}
      </svg>
      {has && caption && !inline && (
        <div className="ruler-cap"><b>{vw.num}</b>{vw.words && <> · {vw.words}</>}{vw.pct && <span> · {vw.pct}</span>}</div>
      )}
    </div>
  )
}
