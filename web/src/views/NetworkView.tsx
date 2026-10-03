import { useEffect, useMemo, useState } from 'react'
import { fmt, histogram, values, useCohortData } from '../analysis'
import { api } from '../api'
import { axisStyle, CohortBar, cssVar, EChart, Loading } from '../components'
import { CyGraph } from '../graph'
import { useStore } from '../store'

const COLOR_BY: Record<string, { label: string; cats: string[] }> = {
  activity: { label: 'Church activity', cats: ['non member', 'inactive', 'less active', 'active'] },
  school: { label: 'School', cats: ['none', 'BYU', 'UVU'] },
  sex: { label: 'Sex', cats: ['F', 'M'] },
  rel: { label: 'Relationship', cats: ['single', 'talking', 'dating', 'engaged', 'married', 'divorced'] },
}

export default function NetworkView() {
  const { cohort, universe, dataVersion, setRoute } = useStore()
  const [g, setG] = useState<any>(null)
  const [by, setBy] = useState('activity')
  const [maxN, setMaxN] = useState(600)
  const [stage, setStage] = useState(3)
  const deg = useCohortData(['n_friends', 'n_close_friends', 'degree'])
  useEffect(() => {
    setG(null)
    api.networkSample(cohort.length ? { and: cohort } : null, stage, maxN, universe).then(setG).catch(() => setG({ nodes: [], edges: [] }))
  }, [JSON.stringify(cohort), universe, dataVersion, maxN, stage])
  const { elements, homophily } = useMemo(() => {
    if (!g) return { elements: [], homophily: null }
    const pal = [1, 2, 3, 4, 5, 6].map(k => cssVar(`--s${k}`))
    const d = new Map<number, number>()
    for (const e of g.edges) { d.set(e.s, (d.get(e.s) ?? 0) + 1); d.set(e.t, (d.get(e.t) ?? 0) + 1) }
    const nodeAttr = new Map(g.nodes.map((n: any) => [n.id, n]))
    const nodes = g.nodes.map((n: any) => ({ data: { id: String(n.id), label: '', size: 6 + 2.2 * Math.sqrt(d.get(n.id) ?? 0), color: pal[(n[by] ?? 0) % pal.length] } }))
    const edges = g.edges.map((e: any, k: number) => ({ data: { id: 'e' + k, source: String(e.s), target: String(e.t), width: e.stage >= 4 ? 1.6 : 0.8, color: cssVar('--axis') } }))
    // homophily: share of ties within the same category vs. expected under random mixing
    const counts = new Map<number, number>()
    for (const n of g.nodes) counts.set(n[by], (counts.get(n[by]) ?? 0) + 1)
    const N = g.nodes.length
    let expected = 0
    for (const c of counts.values()) expected += (c / N) ** 2
    let same = 0
    for (const e of g.edges) if ((nodeAttr.get(e.s) as any)?.[by] === (nodeAttr.get(e.t) as any)?.[by]) same++
    return { elements: [...nodes, ...edges], homophily: { observed: same / (g.edges.length || 1), expected } }
  }, [g, by])
  const degOpt = useMemo(() => {
    if (!deg.mask || !deg.cols.n_friends) return null
    const v = values(deg.cols.n_friends, deg.mask)
    const h = histogram(v, 30)
    const ax = axisStyle()
    return { grid: { left: 44, right: 10, top: 10, bottom: 28 }, tooltip: { trigger: 'axis' }, xAxis: { type: 'category', data: h.edges.slice(0, -1).map(e => fmt(e, 0)), name: 'friends', ...ax }, yAxis: { type: 'value', ...ax }, series: [{ type: 'bar', barCategoryGap: '8%', data: h.counts, itemStyle: { borderRadius: [3, 3, 0, 0] } }] }
  }, [deg])
  return (
    <div className="page">
      <h1>Social network</h1>
      <p className="sub">A sample of the friendship graph among the current cohort (ties at friend level or above). Clusters form around apartments, wards, classes and FHE groups; bridges connect them. Click a node to open the person.</p>
      <CohortBar n={deg.n} />
      <div className="grid" style={{ gridTemplateColumns: 'minmax(0,1fr) 300px' }}>
        <div className="card">
          <div className="row" style={{ marginBottom: 8 }}>
            <span className="small muted">Color by</span>
            <div className="seg">{Object.entries(COLOR_BY).map(([k, v]) => <button key={k} className={by === k ? 'on' : ''} onClick={() => setBy(k)}>{v.label}</button>)}</div>
            <select value={stage} onChange={e => setStage(Number(e.target.value))}><option value={2}>casual friends+</option><option value={3}>friends+</option><option value={4}>close friends</option></select>
            <select value={maxN} onChange={e => setMaxN(Number(e.target.value))}>{[300, 600, 1000, 1500].map(n => <option key={n} value={n}>{n} nodes</option>)}</select>
          </div>
          {g ? <CyGraph elements={elements} height={620} layout={{ name: 'cose', animate: false, nodeRepulsion: 6000, idealEdgeLength: 30, numIter: 600, randomize: true }} onTap={id => setRoute(['person', id])} /> : <Loading what="Sampling the network" />}
          <div className="row small" style={{ marginTop: 8 }}>{COLOR_BY[by].cats.map((c, k) => <span key={c} className="row"><span className="dot" style={{ background: `var(--s${k + 1})` }} />{c}</span>)}</div>
        </div>
        <div className="grid" style={{ alignContent: 'start' }}>
          <div className="card"><h3>Homophily</h3><p className="hint">Share of sampled ties connecting people in the same {COLOR_BY[by].label.toLowerCase()} category, vs. random mixing.</p>
            {homophily && <><div className="tile"><div className="value tabular">{(100 * homophily.observed).toFixed(1)}%</div><div className="delta">expected {(100 * homophily.expected).toFixed(1)}% if random</div></div></>}</div>
          <div className="card"><h3>Friends per person</h3><p className="hint">Degree distribution (friend ties) for the cohort.</p>{degOpt && <EChart option={degOpt} height={200} />}</div>
        </div>
      </div>
    </div>
  )
}
