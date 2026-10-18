// Ties: the selected people's relationships. Each selected person sits in the middle (or on an inner ring when several
// are selected); the people they know sit around them, closer ones nearer, colored by how they met. Click anyone to
// focus them; the list below names every tie.
import { useMemo } from 'react'
import { api } from '../../api'
import { useAsync } from '../../game'
import { Busy, Empty, Problem, useWidth } from '../../kit/Bits'
import { RefChip } from '../../kit/RefChip'
import { useLens, useStore } from '../../store'
import { PanelOptions } from '../panel'
import type { PanelProps, ToolDef } from '../registry'
import { focusItem, selPeople } from '../sel'

const MAX_EGOS = 8
const STAGE = ['stranger', 'acquaintance', 'casual friend', 'friend', 'close friend']
const KIND: Record<string, [string, string]> = {
  romantic: ['--s5', 'romantic'], dated: ['--s5', 'dated'], kissed: ['--s5', 'kissed'], roommate: ['--s6', 'roommate'],
  ward: ['--s7', 'ward'], fhe: ['--s7', 'FHE group'], classmate: ['--s4', 'class'], coworker: ['--s2', 'work'],
  introduced: ['--s3', 'introduced'], preexisting: ['--s8', 'knew before'],
}
const ORDER = ['romantic', 'dated', 'kissed', 'roommate', 'ward', 'fhe', 'classmate', 'coworker', 'introduced', 'preexisting']
const kindOf = (types: string[]) => ORDER.find(k => types.includes(k)) ?? types[0] ?? 'other'
const kindVar = (k: string) => `var(${KIND[k]?.[0] ?? '--text-muted'})`

type Edge = { source: number; target: number; stage: number; closeness: number; types: string[]; hours: number }

function TiesTool({ sel, setSel, opts, setOpts }: PanelProps) {
  const u = useLens().u
  const dataVersion = useStore(s => s.dataVersion)
  // a focused tie shows its two people; otherwise the selected people
  const tie = sel.item?.kind === 'tie' ? String(sel.item.id).split('-').map(Number).filter(Number.isFinite) : []
  const egos = (tie.length === 2 ? tie : selPeople(sel)).slice(0, MAX_EGOS)
  const minStage: number = opts.minStage ?? 2
  const [wrap, w] = useWidth<HTMLDivElement>(400)

  const data = useAsync(() => Promise.all(egos.map(i => api.personNetwork(i, u))),
    [egos.join(','), u, dataVersion], { key: `bench-ties:${u}:${egos.join(',')}` })

  const g = useMemo(() => {
    if (!data.data) return null
    const nodes = new Map<number, any>()
    const edges = new Map<string, Edge>()
    const egoSet = new Set(egos)
    for (const net of data.data) {
      for (const nd of net.nodes) nodes.set(nd.id, { ...nodes.get(nd.id), ...nd })
      for (const e of net.edges as Edge[]) {
        if (!egoSet.has(e.source) && !egoSet.has(e.target)) continue   // only ties of the selected people
        if (e.stage < minStage && !e.types.includes('romantic')) continue
        const k = e.source < e.target ? `${e.source}-${e.target}` : `${e.target}-${e.source}`
        edges.set(k, e)
      }
    }
    const linked = new Set<number>(egos)
    edges.forEach(e => { linked.add(e.source); linked.add(e.target) })
    // closeness to the nearest selected person decides the ring
    const close = new Map<number, number>()
    const kind = new Map<number, string>()
    edges.forEach(e => {
      const o = egoSet.has(e.source) ? e.target : e.source
      if (egoSet.has(o)) return
      if ((close.get(o) ?? -1) < e.closeness) { close.set(o, e.closeness); kind.set(o, kindOf(e.types)) }
    })
    return { nodes, edges: [...edges.values()], others: [...linked].filter(i => !egoSet.has(i)), close, kind }
  }, [data.data, minStage, egos.join(',')])

  if (!egos.length) return <Empty title="Nobody selected">Select someone on the Map or in People to see who they know.</Empty>
  if (data.error && !g) return <Problem error={data.error} />
  if (!g) return <Busy what="Reading their ties" />

  const W = Math.max(240, w), H = Math.max(240, Math.min(W * 0.75, 420))
  const cx = W / 2, cy = H / 2, R = Math.min(W, H) / 2 - 26
  const pos = new Map<number, [number, number]>()
  egos.forEach((i, k) => {
    if (egos.length === 1) pos.set(i, [cx, cy])
    else { const a = (k / egos.length) * 2 * Math.PI; pos.set(i, [cx + R * 0.22 * Math.cos(a), cy + R * 0.22 * Math.sin(a)]) }
  })
  const others = [...g.others].sort((a, b) => ORDER.indexOf(g.kind.get(a) ?? '') - ORDER.indexOf(g.kind.get(b) ?? '') || a - b)
  others.forEach((i, k) => {
    const a = (k / Math.max(1, others.length)) * 2 * Math.PI - Math.PI / 2
    const r = R * (0.42 + 0.58 * (1 - (g.close.get(i) ?? 0)))
    pos.set(i, [cx + r * Math.cos(a), cy + r * Math.sin(a)])
  })
  const kinds = ORDER.filter(k => [...g.kind.values()].includes(k))
  const focus = sel.item?.kind === 'person' ? Number(sel.item.id) : null
  const nm = (i: number) => g.nodes.get(i)?.name ?? `#${i}`
  const rows = [...g.edges].sort((a, b) => b.closeness - a.closeness)

  return (
    <div className="bti" ref={wrap}>
      <PanelOptions>
        <select value={minStage} onChange={e => setOpts({ ...opts, minStage: Number(e.target.value) })} title="Which ties to show">
          <option value={1}>acquaintances and closer</option>
          <option value={2}>casual friends and closer</option>
          <option value={3}>friends and closer</option>
          <option value={4}>close friends only</option>
        </select>
      </PanelOptions>
      <div className="bx-legend">{kinds.map(k => <span key={k}><i className="bx-catdot" style={{ background: kindVar(k) }} />{KIND[k]?.[1] ?? k}</span>)}</div>
      <div className="bti-canvas">
        <svg width={W} height={H} style={{ display: 'block' }}>
          {g.edges.map(e => {
            const a = pos.get(e.source), b = pos.get(e.target)
            if (!a || !b) return null
            return <line key={`${e.source}-${e.target}`} x1={a[0]} y1={a[1]} x2={b[0]} y2={b[1]} stroke={kindVar(kindOf(e.types))}
              strokeWidth={0.6 + 2.4 * e.closeness} opacity={0.25 + 0.5 * e.closeness} />
          })}
          {[...pos.entries()].map(([i, [x, y]]) => {
            const ego = egos.includes(i)
            return (
              <g key={i} className="bti-node" onClick={() => focusItem(setSel, { kind: 'person', id: i, label: nm(i) })}>
                <title>{nm(i)}</title>
                <circle cx={x} cy={y} r={ego ? 9 : 5} fill={ego ? 'var(--accent)' : kindVar(g.kind.get(i) ?? '')}
                  stroke={focus === i ? 'var(--text-primary)' : 'var(--surface-1)'} strokeWidth={focus === i ? 2.5 : 1} />
                {(ego || others.length <= 24) && <text x={x} y={y + (ego ? 21 : 15)} textAnchor="middle">{nm(i).split(' ')[0]}</text>}
              </g>
            )
          })}
        </svg>
        {g.edges.length === 0 && <div className="bx-note">No ties at this level yet; try showing acquaintances.</div>}
      </div>
      <div className="bti-list">
        {rows.slice(0, 80).map(e => (
          <div key={`${e.source}-${e.target}`} className="bti-row">
            <span className="bt-row" style={{ gap: 4 }}>
              {egos.length > 1 && <><RefChip r={{ kind: 'person', id: e.source, label: nm(e.source), u }} plain /> ·</>}
              {(() => { const o = egos.length > 1 || e.source !== egos[0] ? (egos.length > 1 ? e.target : e.source) : e.target
                return <RefChip r={{ kind: 'person', id: o, label: nm(o), u }} plain /> })()}
            </span>
            <small>{STAGE[e.stage] ?? ''}</small>
            <RefChip r={{ kind: 'tie', id: `${Math.min(e.source, e.target)}-${Math.max(e.source, e.target)}`, label: KIND[kindOf(e.types)]?.[1] ?? 'tie', u }}
              sub={`${Math.round(e.hours)} h`} title="This tie: click to trace where their time together came from" />
          </div>
        ))}
      </div>
    </div>
  )
}

export const tool: ToolDef = {
  id: 'ties',
  label: 'Ties',
  icon: 'network',
  hint: 'Who the selected people know, closer ones nearer, colored by how they met; click anyone to focus them.',
  group: 'people',
  order: 30,
  component: TiesTool,
  size: { w: 5, h: 7 },
  needs: ['people'],
}
