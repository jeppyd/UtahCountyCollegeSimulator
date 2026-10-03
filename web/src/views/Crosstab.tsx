import { useMemo, useState } from 'react'
import { crosstab, fmt, groupsOf, useCohortData } from '../analysis'
import { CohortBar, Evidence, VarPicker } from '../components'
import { Cond, useStore } from '../store'

export default function Crosstab() {
  const { registry, setCohort, cohort, setRoute } = useStore()
  const [r, setR] = useState('activity')
  const [c, setC] = useState('rel_status')
  const [norm, setNorm] = useState<'row' | 'col' | 'total' | 'count'>('row')
  const [bins, setBins] = useState(5)
  const data = useCohortData([r, c])
  const sr = registry!.variables[r], sc = registry!.variables[c]
  const tab = useMemo(() => {
    if (!data.mask || !data.cols[r] || !data.cols[c]) return null
    const gr = groupsOf(sr, data.cols[r], data.mask, bins)
    const gc = groupsOf(sc, data.cols[c], data.mask, bins)
    return { gr, gc, ...crosstab(gr, gc, data.mask) }
  }, [data, r, c, bins])
  const drill = (a: number, b: number) => {
    const conds: Cond[] = []
    for (const [spec, code, v, gg] of [[sr, a, r, tab!.gr], [sc, b, c, tab!.gc]] as const) {
      if (spec.dtype === 'cat') conds.push({ var: v, op: 'eq', value: spec.categories![code] })
      else if (spec.dtype === 'bool') conds.push({ var: v, op: 'eq', value: code === 1 })
      else {
        const lab = gg.labels[code]
        const num = Number(lab)
        if (!Number.isNaN(num)) conds.push({ var: v, op: 'eq', value: num, label: `${spec.label} = ${lab}` })
        else {
          // quantile bin: reconstruct numeric bounds from label text
          const m = lab.match(/^< (.+)$/), m2 = lab.match(/^≥ (.+)$/), m3 = lab.match(/^(.+)–(.+)$/)
          if (m) conds.push({ var: v, op: 'lt', value: Number(m[1]) })
          else if (m2) conds.push({ var: v, op: 'ge', value: Number(m2[1]) })
          else if (m3) conds.push({ var: v, op: 'between', value: [Number(m3[1]), Number(m3[2])] })
        }
      }
    }
    setCohort([...cohort, ...conds])
    setRoute(['people'])
  }
  const cellVal = (a: number, b: number) => {
    if (!tab) return 0
    const n = tab.counts[a][b]
    return norm === 'row' ? n / (tab.rowT[a] || 1) : norm === 'col' ? n / (tab.colT[b] || 1) : norm === 'total' ? n / (tab.total || 1) : n
  }
  const maxV = tab ? Math.max(...tab.counts.flatMap((row, a) => row.map((_, b) => cellVal(a, b)))) : 1
  return (
    <div className="page">
      <h1>Cross-tabs</h1>
      <p className="sub">Survey-style cross-tabulation of any two variables (numeric ones are binned into quantiles). Shading is proportional to the cell value; click a cell to open those people.</p>
      <CohortBar n={data.n} />
      <div className="card">
        <div className="row" style={{ marginBottom: 10 }}>
          <span className="small muted">Rows</span><VarPicker value={r} onChange={setR} filter={v => !!v.filterable} />
          <span className="small muted">Columns</span><VarPicker value={c} onChange={setC} filter={v => !!v.filterable} />
          <div className="seg">{(['row', 'col', 'total', 'count'] as const).map(k => <button key={k} className={norm === k ? 'on' : ''} onClick={() => setNorm(k)}>{k === 'count' ? 'counts' : `${k} %`}</button>)}</div>
          <label className="inline small">bins <input type="number" min={2} max={10} value={bins} onChange={e => setBins(Number(e.target.value))} style={{ width: 56 }} /></label>
        </div>
        <div className="row small" style={{ marginBottom: 8 }}><Evidence level={sr?.evidence} /><span className="muted">{sr?.label}</span>×<Evidence level={sc?.evidence} /><span className="muted">{sc?.label}</span></div>
        {tab && (
          <div style={{ overflowX: 'auto' }}>
            <table className="data" style={{ width: 'auto', minWidth: '60%' }}>
              <thead><tr><th>{sr.label} ↓ / {sc.label} →</th>{tab.gc.labels.map((l, b) => <th key={b} className="num">{l}</th>)}<th className="num">Total</th></tr></thead>
              <tbody>
                {tab.gr.labels.map((l, a) => tab.rowT[a] > 0 && (
                  <tr key={a}><th style={{ position: 'static' }}>{l}</th>
                    {tab.gc.labels.map((_, b) => {
                      const v = cellVal(a, b)
                      return <td key={b} className="num" style={{ cursor: 'pointer', background: `rgba(42,120,214,${0.06 + 0.5 * v / (maxV || 1)})` }} title={`${tab.counts[a][b]} people`} onClick={() => drill(a, b)}>
                        {norm === 'count' ? tab.counts[a][b].toLocaleString() : (100 * v).toFixed(1) + '%'}</td>
                    })}
                    <td className="num muted">{tab.rowT[a].toLocaleString()}</td></tr>
                ))}
                <tr><th style={{ position: 'static' }}>Total</th>{tab.colT.map((t, b) => <td key={b} className="num muted">{t.toLocaleString()}</td>)}<td className="num"><b>{tab.total.toLocaleString()}</b></td></tr>
              </tbody>
            </table>
            <div className="row small tabular" style={{ marginTop: 10 }}>
              <span className="pill">χ² = {fmt(tab.chi2, 1)} (df {tab.dof})</span>
              <span className="pill">p ≈ {tab.p < 0.0001 ? '< 0.0001' : fmt(tab.p, 4)}</span>
              <span className="pill">Cramér's V = {fmt(tab.cramer, 3)}</span>
              <span className="muted">Large simulated N makes tiny differences "significant"; focus on effect size.</span>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
