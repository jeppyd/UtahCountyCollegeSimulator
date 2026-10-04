import { useEffect, useMemo, useState } from 'react'
import { fmt } from '../analysis'
import { api } from '../api'
import { cssVar, Evidence, Loading, VarPicker } from '../components'
import { CyGraph } from '../graph'
import { useStore } from '../store'
import { PageHeader } from '../ui'

const EV_VAR: Record<string, string> = { observed: '--ev-observed', empirical: '--ev-empirical', literature: '--ev-literature', calibrated: '--ev-calibrated', extrapolated: '--ev-extrapolated', hypothetical: '--ev-hypothetical' }

export default function CausalWeb({ focus }: { focus?: string }) {
  const { registry, dataVersion, status, setRoute } = useStore()
  const [g, setG] = useState<any>(null)
  const [root, setRoot] = useState(focus ?? 'loneliness')
  const [depth, setDepth] = useState(2)
  const [dir, setDir] = useState<'up' | 'down' | 'both'>('up')
  const [showEvents, setShowEvents] = useState(true)
  const [sel, setSel] = useState<any>(null)
  useEffect(() => { if (focus) setRoot(focus) }, [focus])
  useEffect(() => { (status.has_alt ? api.compare().catch(() => null) : Promise.resolve(null)).then(() => api.causalGraph()).then(setG).catch(() => {}) }, [dataVersion, status.has_alt])
  const elements = useMemo(() => {
    if (!g) return []
    const inE = new Map<string, any[]>(), outE = new Map<string, any[]>()
    for (const e of g.edges) { (inE.get(e.target) ?? inE.set(e.target, []).get(e.target)!).push(e); (outE.get(e.source) ?? outE.set(e.source, []).get(e.source)!).push(e) }
    const nodeById = new Map(g.nodes.map((n: any) => [n.id, n]))
    const keep = new Set<string>([root])
    const level = new Map<string, number>([[root, 0]])
    const keepEdges = new Set<any>()
    const walk = (start: string, up: boolean) => {
      let frontier = [start]
      // each "level" = variable → mechanism → variable (two hops)
      for (let d = 0; d < depth * 2; d++) {
        const next: string[] = []
        for (const id of frontier) {
          for (const e of (up ? inE.get(id) : outE.get(id)) ?? []) {
            const other = up ? e.source : e.target
            const node: any = nodeById.get(other)
            if (!node) continue
            if (node.kind === 'event' && !showEvents) continue
            keepEdges.add(e)
            if (!keep.has(other)) { keep.add(other); level.set(other, d + 1); next.push(other) }
          }
        }
        frontier = next
      }
    }
    if (dir !== 'down') walk(root, true)
    if (dir !== 'up') walk(root, false)
    const maxD = Math.max(1e-6, ...[...keep].map(id => Math.abs((nodeById.get(id) as any)?.delta ?? 0)))
    const nodes = [...keep].map(id => {
      const n: any = nodeById.get(id)
      const d = n.delta ?? 0
      const color = n.kind === 'mechanism' ? cssVar(EV_VAR[n.evidence] ?? '--ev-calibrated') : n.kind === 'event' ? cssVar('--s5') : id === root ? cssVar('--s2') : cssVar('--surface-3')
      return { data: { id, level: level.get(id) ?? 0, label: n.label.length > 34 ? n.label.slice(0, 32) + '…' : n.label, kind: n.kind, color, size: n.kind === 'variable' ? 26 + (status.has_alt ? 26 * Math.abs(d) / maxD : 0) : n.kind === 'mechanism' ? 16 + (status.has_alt ? 22 * Math.abs(d) / maxD : 0) : 12, raw: n } }
    })
    const edges = [...keepEdges].map((e: any, k) => ({ data: { id: 'e' + k, source: e.source, target: e.target, width: 1.4, color: cssVar('--axis') } }))
    return [...nodes, ...edges]
  }, [g, root, depth, dir, showEvents])
  const style = useMemo(() => [
    { selector: 'node[kind = "variable"]', style: { shape: 'round-rectangle', 'border-color': cssVar('--axis'), 'border-width': 1.5, 'font-size': 11, 'font-weight': 600, 'min-zoomed-font-size': 4 } },
    { selector: 'node[kind = "mechanism"], node[kind = "event"]', style: { 'font-size': 8, 'min-zoomed-font-size': 6 } },
    { selector: 'node[kind = "mechanism"]', style: { shape: 'diamond' } },
    { selector: 'node[kind = "event"]', style: { shape: 'triangle' } },
    { selector: 'edge', style: { 'curve-style': 'bezier', 'target-arrow-shape': 'triangle', 'target-arrow-color': cssVar('--axis'), 'arrow-scale': 0.8 } },
  ], [g])
  if (!g) return <Loading what="Assembling the causal web" />
  const raw = sel?.raw
  return (
    <div className="page">
      <PageHeader id="causal" eyebrow="What if?" title="Cause & effect"
        sub="What affects what in the model. Measures (boxes) feed rules (diamonds) that change other measures; events (triangles) push feelings for a while."
        tips={['Pick a measure to center on. "Causes" shows what drives it; "consequences" shows what it drives. Depth adds more steps.', 'Click a node to read it. Diamonds are colored by how well-supported the rule is.', 'After a what-if experiment, bigger nodes moved more, so you can see where the change traveled.']} />
      <div className="card">
        <div className="row" style={{ marginBottom: 10 }}>
          <span className="small muted">Focus</span><VarPicker value={root} onChange={setRoot} />
          <div className="seg">{(['up', 'down', 'both'] as const).map(k => <button key={k} className={dir === k ? 'on' : ''} onClick={() => setDir(k)}>{k === 'up' ? 'causes ↑' : k === 'down' ? 'consequences ↓' : 'both'}</button>)}</div>
          <label className="inline small">depth <input type="range" min={1} max={4} value={depth} onChange={e => setDepth(Number(e.target.value))} /> {depth}</label>
          <label className="inline small"><input type="checkbox" checked={showEvents} onChange={e => setShowEvents(e.target.checked)} />events</label>
          <span className="spacer" />
          <span className="row small">{Object.keys(EV_VAR).map(k => <Evidence key={k} level={k} />)}</span>
        </div>
        <div className="grid" style={{ gridTemplateColumns: 'minmax(0,1fr) 320px' }}>
          <CyGraph elements={elements} style={style} height={600} layout={{ name: 'concentric', concentric: (n: any) => 100 - n.data('level'), levelWidth: () => 1, minNodeSpacing: 18, spacingFactor: 0.9, animate: false }}
            onTap={(id, data) => setSel(data)} />
          <div className="card" style={{ boxShadow: 'none' }}>
            {!raw && <div className="muted small">Click a node for details. Click a variable twice (or use "focus") to re-center the web on it.</div>}
            {raw && (
              <>
                <div className="row"><b>{raw.label}</b>{raw.evidence && <Evidence level={raw.evidence} />}</div>
                <div className="small muted">{raw.kind}{raw.domain ? ` · ${raw.domain}` : ''}{raw.system ? ` · ${raw.system}` : ''}</div>
                {raw.delta !== null && raw.delta !== undefined && <div className="small" style={{ marginTop: 6 }}>Δ in intervention universe: <b>{fmt(raw.delta, 4)}</b>{raw.kind === 'variable' ? ' sd' : ''}</div>}
                {raw.kind === 'mechanism' && registry!.mechanisms[raw.id] && <MechBrief m={registry!.mechanisms[raw.id]} />}
                {raw.kind === 'variable' && registry!.variables[raw.id] && <p className="small">{registry!.variables[raw.id].desc}</p>}
                <div className="row" style={{ marginTop: 8 }}>
                  {raw.kind === 'variable' && <><button className="btn small" onClick={() => setRoot(raw.id)}>Focus here</button><button className="btn small" onClick={() => setRoute(['variables', raw.id])}>Variable page</button></>}
                  {raw.kind === 'mechanism' && <button className="btn small" onClick={() => setRoute(['mechanisms', raw.id])}>Mechanism page</button>}
                </div>
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

export function MechBrief({ m }: { m: any }) {
  return (
    <div className="small" style={{ marginTop: 6 }}>
      {m.desc && <p>{m.desc}</p>}
      <div><b>Form</b>: <span className="secondary">{m.form}</span></div>
      {Object.keys(m.params ?? {}).length > 0 && <div style={{ marginTop: 4 }}><b>Parameters</b>: {Object.entries(m.params).map(([k, v]: any) => <span key={k} className="pill" style={{ margin: 2 }}>{k} = {v.value}{v.range ? ` [${v.range.join('–')}]` : ''}</span>)}</div>}
      {m.refs?.length > 0 && <div style={{ marginTop: 4 }}><b>Evidence</b>: {m.refs.map((r: string) => <div key={r} className="secondary">• {r}</div>)}</div>}
    </div>
  )
}
