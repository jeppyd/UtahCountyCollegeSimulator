// Why: the share of the push behind the focused event or choice — each reason's part of the total push the model
// recorded (the decision's own terms, or the weights of an event's recorded causes), largest first, with what pushed
// the other way and the chance it had. Click a reason to focus it.
import { benchApi, type WhyItem } from '../../api'
import { useAsync } from '../../game'
import { Busy, Empty, Problem } from '../../kit/Bits'
import { pct, ShareBar } from '../../kit/ShareBar'
import { useLens } from '../../store'
import type { RefKind } from '../selection'
import type { PanelProps, ToolDef } from '../registry'
import { worldOf } from '../sel'

const OK = new Set(['event', 'decision', 'var', 'state'])

export function pickRef(setSel: PanelProps['setSel'], w: WhyItem, u: 'base' | 'alt') {
  const r = w.ref
  if (!r || r.kind == null) return
  const kind = (r.kind === 'state' ? 'var' : r.kind) as RefKind
  const num = ['event', 'decision', 'occasion', 'person'].includes(kind)
  setSel({ item: { kind, id: num ? Number(r.id) : r.id, label: w.ref_label ?? w.label, u } })
}

function WhyTool({ sel, setSel }: PanelProps) {
  const u = worldOf(sel, useLens().u)
  const it = sel.item
  const ref = it && OK.has(it.kind) ? `${it.kind}:${it.id}` : null
  const d = useAsync(() => (ref ? benchApi.why(ref, u) : Promise.resolve(null)), [ref, u], { key: `bench-why:${u}:${ref}` })
  if (!ref) return <Empty title="Focus an event or a choice">Click something in Story, Life, Trace or Events to see what pushed it and by how much.</Empty>
  if (d.error) return <Problem error={d.error} />
  const w = d.data
  if (!w) return <Busy what="Reading the reasons" />
  return (
    <div className="bk">
      <div className="bk-why">
        <b>{w.title}</b>
        <div className="bx-note">
          {w.date}{w.by ? ` · ${w.by}'s choice` : ''}{w.outcome ? ` · decided: ${w.outcome}` : ''}{w.chance != null ? ` · the chance it had: ${pct(w.chance)}` : ''}
        </div>
      </div>
      {(w.after?.length ?? 0) > 0 && (
        <div className="bk-why">It followed from: {w.after!.map((a, k) => (
          <span key={k} className="click" style={{ textDecoration: 'underline dotted' }}
            onClick={() => pickRef(setSel, { label: a.label, words: a.label, share: 0, value: 0, ref: a.ref, ref_label: a.label }, u)}>{k ? '; ' : ''}{a.label}</span>
        ))}</div>
      )}
      {w.constraint
        ? <div className="bk-why"><b>It couldn't go otherwise:</b> {w.constraint.words}</div>
        : !w.toward.length && w.against.length > 0 && w.chance != null
          ? <div className="bk-why">Nothing recorded pushed toward this: it happened against the odds (the model gave it {pct(w.chance)}). What pushed the other way:</div>
          : null}
      {!w.constraint && Boolean(w.toward.length || w.against.length || !w.after?.length) && <ShareBar toward={w.toward} against={w.against} onPick={x => pickRef(setSel, x, u)} />}
      <div className="bx-note">
        {w.note ?? 'Each reason\'s share is its part of the total push the model recorded for this choice; the base rate (how often anyone does this) is left out.'}
        {' '}These are the reasons inside this simulated world, not proof of real-world cause.
      </div>
    </div>
  )
}

export const tool: ToolDef = {
  id: 'why',
  label: 'Why',
  icon: 'scale',
  hint: 'The share of the push behind the focused event or choice: each reason as a part of the whole, largest first.',
  group: 'trace',
  order: 12,
  component: WhyTool,
  size: { w: 5, h: 5 },
  needs: ['item'],
}
