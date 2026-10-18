// <Val v="loneliness" value={0.62} />: a number that can explain itself. It shows the value (and, if asked, its words
// or a small inline ruler); clicking it opens the ScaleCard: the whole ruler with the value marked, what the field is,
// its units, how the model measures it and how sure we are.
import { useEffect, useRef, useState, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { fval } from '../fields'
import { useStore } from '../store'
import { Ruler, useValueWords } from './Ruler'
import { useDist, useScale } from './scales'
import './scales.css'

export function ScaleCard({ v, value, onClose, at }: { v: string; value?: number | null; onClose: () => void; at: { x: number; y: number } }) {
  const reg = useStore(s => s.registry)
  const spec = reg?.variables[v]
  const sc = useScale(v)
  const d = useDist(v)
  const box = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const down = (e: MouseEvent) => { if (box.current && !box.current.contains(e.target as Node)) onClose() }
    const key = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    setTimeout(() => document.addEventListener('mousedown', down), 0)
    document.addEventListener('keydown', key)
    return () => { document.removeEventListener('mousedown', down); document.removeEventListener('keydown', key) }
  }, [onClose])
  if (!spec) return null
  const W = 380
  const left = Math.max(8, Math.min(at.x - 20, window.innerWidth - W - 8))
  const below = at.y + 300 < window.innerHeight
  return createPortal(
    <div className="scalecard card" ref={box} role="dialog" aria-label={`${spec.label}: what the numbers mean`}
      style={{ left, width: W, ...(below ? { top: at.y + 6 } : { bottom: window.innerHeight - at.y + 26 }) }}>
      <div className="scalecard-h"><b>{spec.label}</b>{sc?.unit && <span>{sc.unit}</span>}</div>
      {spec.desc && <p>{spec.desc}</p>}
      {sc ? <Ruler v={v} value={value} dist={d} /> : <p className="muted">No scale for this field.</p>}
      {d && <div className="scalecard-n">The band is the middle half of {d.n.toLocaleString()} people today; the whiskers reach the 10th and 90th percentiles; the tick is the median.</div>}
      {sc?.how && <><div className="scalecard-k">How it is measured</div><p>{sc.how}</p></>}
      {sc?.note && <p className="muted">{sc.note}</p>}
      <div className="scalecard-k">How sure we are</div>
      <p>{reg?.evidence_levels[spec.evidence] ? <><b>{spec.evidence}</b>: {reg.evidence_levels[spec.evidence]}</> : spec.evidence}</p>
    </div>, document.body)
}

/** A value with its scale one click away. `show`: just the number, the number and its words, or an inline ruler. */
export function Val({ v, value, show = 'num', children }: { v: string; value: number | null | undefined; show?: 'num' | 'words' | 'ruler'; children?: ReactNode }) {
  const spec = useStore(s => s.registry?.variables[v])
  const sc = useScale(v)
  const d = useDist(show === 'num' ? undefined : v)
  const vw = useValueWords(v, value, d)
  const [open, setOpen] = useState<{ x: number; y: number } | null>(null)
  if (!sc) return <>{children ?? fval(spec, value)}</>
  return (
    <>
      <button type="button" className={`val val-${show}`} title={`${vw.num}${vw.words ? ` · ${vw.words}` : ''}${vw.pct ? ` · ${vw.pct}` : ''} — click for the scale`}
        onClick={e => { e.stopPropagation(); const r = e.currentTarget.getBoundingClientRect(); setOpen(open ? null : { x: r.left, y: r.bottom }) }}>
        {children ?? <span className="val-n">{vw.num}</span>}
        {show === 'words' && vw.words && <span className="val-w">{vw.words}</span>}
        {show === 'ruler' && <span className="val-r"><Ruler v={v} value={value} variant="inline" dist={d} /></span>}
      </button>
      {open && <ScaleCard v={v} value={value} at={open} onClose={() => setOpen(null)} />}
    </>
  )
}
