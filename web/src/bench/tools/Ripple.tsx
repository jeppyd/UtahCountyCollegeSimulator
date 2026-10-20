// Ripple: what the focused moment led to — a tree of sentences in time order ("…which led to…"), following the same
// recorded links as Trace: plans carried out, answers given, dates, introductions, friendships. Click a line to focus
// it (and see its Why); "Follow" starts the ripple from there.
import { benchApi } from '../../api'
import { useAsync } from '../../game'
import { Busy, Empty, Problem } from '../../kit/Bits'
import { useLens } from '../../store'
import { PanelOptions } from '../panel'
import type { PanelProps, ToolDef } from '../registry'
import { worldOf } from '../sel'

const OK = new Set(['event', 'decision', 'occasion'])

function RippleTool({ sel, setSel, opts, setOpts }: PanelProps) {
  const u = worldOf(sel, useLens().u)
  const it = sel.item
  const depth: number = opts.depth ?? 6
  const ref = it && OK.has(it.kind) ? `${it.kind}:${it.id}` : null
  const d = useAsync(() => (ref ? benchApi.ripple(ref, u, depth) : Promise.resolve(null)), [ref, u, depth], { key: `bench-ripple:${u}:${ref}:${depth}` })
  if (!ref) return <Empty title="Focus a moment">Click an event in Story, Life, Events or Trace to see the chain of what it led to.</Empty>
  if (d.error) return <Problem error={d.error} />
  const r = d.data
  if (!r) return <Busy what="Following what it led to" />
  const focus = (key: string, label: string) => {
    const [kind, id] = [key.slice(0, key.indexOf(':')), key.slice(key.indexOf(':') + 1)]
    if (OK.has(kind)) setSel({ item: { kind: kind as any, id: Number(id), label, u } })
  }
  return (
    <div className="bk ripple">
      <PanelOptions>
        <div className="seg">{[3, 6, 8].map(k => <button key={k} className={depth === k ? 'on' : ''} onClick={() => setOpts({ ...opts, depth: k })}>{k} steps</button>)}</div>
      </PanelOptions>
      {r.steps.length <= 1 && <div className="bx-note">Nothing recorded follows from this yet (or it is still to come — run time forward).</div>}
      <div className="ripple-tree">
        {r.steps.map((s, k) => (
          <div key={s.key} className={`ripple-step click ${s.key === r.root ? 'root' : ''}`} style={{ paddingLeft: 14 * s.level }}
            onClick={() => focus(s.key, s.text)}>
            {k > 0 && <span className="ripple-via">{s.via ? `${s.via} → ` : 'which led to → '}</span>}
            <span className="when">{s.date?.slice(5)}</span> {s.text}
          </div>
        ))}
      </div>
      {r.notes.map((n, k) => <div key={k} className="bx-note">{n}</div>)}
    </div>
  )
}

export const tool: ToolDef = {
  id: 'ripple',
  label: 'Ripple',
  icon: 'butterfly',
  hint: 'What the focused moment led to, as a chain of plain sentences in time order.',
  group: 'trace',
  order: 14,
  component: RippleTool,
  size: { w: 6, h: 6 },
  needs: ['item'],
}
