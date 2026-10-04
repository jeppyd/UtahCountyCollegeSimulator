import { useEffect, useMemo, useState } from 'react'
import { fmt, groupsOf, histogram, isCategorical, pearson, regress, summary, useCohortData, values } from '../analysis'
import { api, STATIC } from '../api'
import { axisStyle, CohortBar, condLabel, Decomposition, EChart, Evidence, Loading, PersonLink, series, tokens, VarPicker } from '../components'
import { Cond, useStore } from '../store'
import { Advanced, PageHeader, useAdvanced } from '../ui'

export default function Explore({ x0, y0, g0 }: { x0?: string; y0?: string; g0?: string }) {
  const { registry, addCond, status } = useStore()
  const adv = useAdvanced()
  const [x, setX] = useState(x0 || 'loneliness')
  const [y, setY] = useState(y0 || '')
  const [g, setG] = useState(g0 || '')
  useEffect(() => { if (x0) setX(x0); setY(y0 || ''); setG(g0 || '') }, [x0, y0, g0])
  const [compareU, setCompareU] = useState(false)
  const vars = [x, y, g].filter(Boolean)
  const data = useCohortData(vars)
  const alt = useCohortData(vars, { universe: 'alt', ignoreCohort: false, enabled: !!status?.has_alt })
  const sx = registry!.variables[x], sy = y ? registry!.variables[y] : undefined, sg = g ? registry!.variables[g] : undefined

  const chart = useMemo(() => {
    if (!data.mask || !data.cols[x]) return null
    const ax = axisStyle()
    const t = tokens()
    const mask = data.mask
    const cx = data.cols[x]
    // ------ categorical X
    if (isCategorical(sx) && !y) {
      const gx = groupsOf(sx, cx, mask)
      const groups = sg && data.cols[g] ? groupsOf(sg, data.cols[g], mask, 4) : null
      const serie: any[] = []
      const mk = (m: Uint8Array | null, codeG: Int16Array | null, gi: number) => {
        const cnt = new Array(gx.labels.length).fill(0)
        let tot = 0
        for (let i = 0; i < gx.code.length; i++) { if (!m || !m[i]) continue; if (codeG && codeG[i] !== gi) continue; if (gx.code[i] < 0) continue; cnt[gx.code[i]]++; tot++ }
        return cnt.map(c => (tot ? c / tot : 0))
      }
      if (groups) groups.labels.slice(0, 6).forEach((lab, k) => serie.push({ name: lab, type: 'bar', barMaxWidth: 24, data: mk(mask, groups.code, k), itemStyle: { borderRadius: [4, 4, 0, 0] } }))
      else serie.push({ name: 'Baseline', type: 'bar', barMaxWidth: 24, data: mk(mask, null, 0), itemStyle: { borderRadius: [4, 4, 0, 0] } })
      if (compareU && !groups && alt.mask && alt.cols[x]) {
        const ga = groupsOf(sx, alt.cols[x], alt.mask)
        const cnt = new Array(gx.labels.length).fill(0); let tot = 0
        for (let i = 0; i < ga.code.length; i++) if (alt.mask[i] && ga.code[i] >= 0) { cnt[ga.code[i]]++; tot++ }
        serie.push({ name: 'Intervention', type: 'bar', barMaxWidth: 24, data: cnt.map(c => c / (tot || 1)), itemStyle: { borderRadius: [4, 4, 0, 0] } })
      }
      return {
        kind: 'bar',
        option: {
          grid: { left: 50, right: 16, top: serie.length > 1 ? 34 : 14, bottom: 60 },
          legend: serie.length > 1 ? { top: 0, textStyle: { color: t.text2 } } : undefined,
          tooltip: { trigger: 'axis', valueFormatter: (v: number) => (100 * v).toFixed(1) + '%' },
          xAxis: { type: 'category', data: gx.labels, ...ax, axisLabel: { ...ax.axisLabel, rotate: gx.labels.length > 6 ? 30 : 0 } },
          yAxis: { type: 'value', ...ax, axisLabel: { ...ax.axisLabel, formatter: (v: number) => (100 * v).toFixed(0) + '%' } },
          series: serie,
        },
        click: (p: any) => {
          const label = gx.labels[p.dataIndex]
          if (sx.dtype === 'cat') addCond({ var: x, op: 'eq', value: sx.categories![p.dataIndex] })
          else if (sx.dtype === 'bool') addCond({ var: x, op: 'eq', value: p.dataIndex === 1 })
          else addCond({ var: x, op: 'eq', value: Number(label), label: `${sx.label} = ${label}` } as Cond)
        },
      }
    }
    // ------ numeric X, no Y
    if (!y) {
      const vx = values(cx, mask)
      if (!vx.length) return null
      const lo = Math.min(...vx), hi = Math.max(...vx)
      if (sg && data.cols[g]) {
        const gg = groupsOf(sg, data.cols[g], mask, 5)
        const boxes: any[] = [], labels: string[] = []
        gg.labels.slice(0, 8).forEach((lab, k) => {
          const vv: number[] = []
          for (let i = 0; i < gg.code.length; i++) if (mask[i] && gg.code[i] === k && !Number.isNaN(cx.data[i])) vv.push(cx.data[i] as number)
          if (vv.length < 3) return
          const s = summary(vv)
          boxes.push([s.p10, s.q1, s.median, s.q3, s.p90]); labels.push(`${lab} (n=${vv.length})`)
        })
        return {
          kind: 'box', option: {
            grid: { left: 60, right: 16, top: 14, bottom: 60 },
            tooltip: { trigger: 'item', formatter: (p: any) => `${p.name}<br/>p10 ${fmt(p.data[1])} · Q1 ${fmt(p.data[2])}<br/>median ${fmt(p.data[3])}<br/>Q3 ${fmt(p.data[4])} · p90 ${fmt(p.data[5])}` },
            xAxis: { type: 'category', data: labels, ...ax, axisLabel: { ...ax.axisLabel, rotate: labels.length > 4 ? 25 : 0 } },
            yAxis: { type: 'value', scale: true, name: sx.label, ...ax },
            series: [{ type: 'boxplot', data: boxes, itemStyle: { color: series(0) + '33', borderColor: series(0), borderWidth: 1.5 }, boxWidth: [8, 28] }],
          },
        }
      }
      const h = histogram(vx, 30, [lo, hi])
      const serie: any[] = [{ name: 'Baseline', type: 'bar', barCategoryGap: '8%', data: h.counts.map(c => c / vx.length), itemStyle: { borderRadius: [3, 3, 0, 0] } }]
      if (compareU && alt.mask && alt.cols[x]) {
        const va = values(alt.cols[x], alt.mask)
        const ha = histogram(va, h.counts.length, [lo, hi + (h.ints ? 0 : 0)])
        serie.push({ name: 'Intervention', type: 'line', step: 'middle', showSymbol: false, lineStyle: { width: 2 }, data: ha.counts.map(c => c / (va.length || 1)) })
      }
      const labs = h.edges.slice(0, -1).map((e, k) => (h.ints ? String(Math.round(e)) : `${fmt(e)}–${fmt(h.edges[k + 1])}`))
      return {
        kind: 'hist', stats: summary(vx),
        option: {
          grid: { left: 50, right: 16, top: serie.length > 1 ? 34 : 14, bottom: 40 },
          legend: serie.length > 1 ? { top: 0, textStyle: { color: t.text2 } } : undefined,
          tooltip: { trigger: 'axis', valueFormatter: (v: number) => (100 * v).toFixed(1) + '%' },
          xAxis: { type: 'category', data: labs, ...ax, name: sx.units ?? '', nameLocation: 'end' },
          yAxis: { type: 'value', ...ax, axisLabel: { ...ax.axisLabel, formatter: (v: number) => (100 * v).toFixed(0) + '%' } },
          series: serie,
        },
        click: (p: any) => addCond({ var: x, op: 'between', value: [h.edges[p.dataIndex], h.edges[p.dataIndex + 1]] }),
      }
    }
    // ------ Y given
    const cy = data.cols[y]
    if (!cy) return null
    if (isCategorical(sx) && !isCategorical(sy)) {
      const gx = groupsOf(sx, cx, mask)
      const rows = gx.labels.map((lab, k) => {
        const vv: number[] = []
        for (let i = 0; i < gx.code.length; i++) if (mask[i] && gx.code[i] === k && !Number.isNaN(cy.data[i])) vv.push(cy.data[i] as number)
        const s = summary(vv)
        return { lab, n: vv.length, m: s.mean, se: s.sd / Math.sqrt(Math.max(vv.length, 1)) }
      }).filter(r => r.n > 0)
      return {
        kind: 'means', rows, option: {
          grid: { left: 60, right: 16, top: 14, bottom: 60 },
          tooltip: { trigger: 'axis', formatter: (ps: any) => { const r = rows[ps[0].dataIndex]; return `${r.lab}<br/>mean ${fmt(r.m, 3)} ± ${fmt(1.96 * r.se, 3)}<br/>n = ${r.n}` } },
          xAxis: { type: 'category', data: rows.map(r => r.lab), ...ax, axisLabel: { ...ax.axisLabel, rotate: rows.length > 6 ? 30 : 0 } },
          yAxis: { type: 'value', scale: true, name: `mean ${sy!.label}`, ...ax },
          series: [
            { type: 'bar', barMaxWidth: 24, data: rows.map(r => r.m), itemStyle: { borderRadius: [4, 4, 0, 0] } },
            { type: 'custom', renderItem: (params: any, api: any) => { const k = params.dataIndex; const r = rows[k]; const xx = api.coord([k, r.m + 1.96 * r.se]); const yy = api.coord([k, r.m - 1.96 * r.se]); return { type: 'line', shape: { x1: xx[0], y1: xx[1], x2: yy[0], y2: yy[1] }, style: { stroke: t.text2, lineWidth: 1.5 } } }, data: rows.map(r => r.m), z: 10 },
          ],
        },
      }
    }
    // numeric × numeric scatter
    const idx: number[] = []
    for (let i = 0; i < mask.length; i++) if (mask[i] && !Number.isNaN(cx.data[i]) && !Number.isNaN(cy.data[i])) idx.push(i)
    const step = Math.max(1, Math.floor(idx.length / 4000))
    const sample = idx.filter((_, k) => k % step === 0)
    const xs = idx.map(i => cx.data[i] as number), ys = idx.map(i => cy.data[i] as number)
    const fit = regress(xs, ys)
    const r = pearson(cx.data, cy.data, mask)
    const lo = Math.min(...xs), hi = Math.max(...xs)
    const jitter = (v: number, spec: any) => (spec?.dtype?.startsWith('i') || spec?.dtype === 'u1' ? v + (Math.random() - 0.5) * 0.4 : v)
    return {
      kind: 'scatter', fit, r,
      option: {
        grid: { left: 56, right: 16, top: 14, bottom: 44 },
        tooltip: { trigger: 'item', formatter: (p: any) => p.seriesType === 'scatter' ? `#${p.data[2]}<br/>${sx.label}: ${fmt(p.data[0], 3)}<br/>${sy!.label}: ${fmt(p.data[1], 3)}` : '' },
        xAxis: { type: 'value', scale: true, name: sx.label, nameLocation: 'middle', nameGap: 28, ...ax },
        yAxis: { type: 'value', scale: true, name: sy!.label, ...ax },
        series: [
          { type: 'scatter', symbolSize: 5, data: sample.map(i => [jitter(cx.data[i] as number, sx), jitter(cy.data[i] as number, sy), i]), itemStyle: { opacity: 0.45 } },
          { type: 'line', showSymbol: false, data: [[lo, fit.intercept + fit.slope * lo], [hi, fit.intercept + fit.slope * hi]], lineStyle: { width: 2, color: series(1) } },
        ],
      },
      click: (p: any) => p.data?.[2] !== undefined && useStore.getState().setRoute(['person', String(p.data[2])]),
    }
  }, [data, alt, x, y, g, compareU])

  return (
    <div className="page">
      <PageHeader id="explore" eyebrow="Ask questions" title="Explore a measure"
        sub="See how any measure is spread across people, split it by groups, or relate it to a second measure."
        tips={[
          <>Choose a <b>measure</b>. Add <b>split by</b> to compare groups (e.g. loneliness by school), or <b>vs</b> to relate two measures (each dot is a person).</>,
          'Click a bar to narrow your group to those people. Click a dot to open that person.',
          <>With a group selected, the <b>Why is this group different?</b> panel breaks the gap into the model's forces and shows example lives.</>,
          'Patterns here are associations inside the simulation. For causes, use the Why panel, a person\'s page, or Cause & effect.',
        ]} />
      <CohortBar n={data.n} />
      <div className="card">
        <div className="row" style={{ marginBottom: 10 }}>
          <span className="small muted">Variable</span><VarPicker value={x} onChange={setX} filter={v => !!v.chartable} />
          <span className="small muted">vs</span><VarPicker value={y} onChange={setY} filter={v => !!v.chartable && v.dtype !== 'cat' && v.dtype !== 'bool'} allowEmpty placeholder="(nothing)" />
          <span className="small muted">split by</span><VarPicker value={g} onChange={setG} filter={v => !!v.filterable} allowEmpty placeholder="(no split)" />
          {status.has_alt && <label className="inline small"><input type="checkbox" checked={compareU} onChange={e => setCompareU(e.target.checked)} />overlay intervention universe</label>}
        </div>
        <div className="row small" style={{ marginBottom: 6 }}>
          <b>{sx?.label}</b>{sx?.units && <span className="muted">({sx.units})</span>}<Evidence level={sx?.evidence} />
          <span className="muted">{sx?.desc}</span>
        </div>
        {chart ? <EChart option={chart.option} height={380} onClick={chart.click} /> : <div className="empty">No data for this selection.</div>}
        {chart?.kind === 'hist' && chart.stats && (
          <>
            <p className="small secondary" style={{ margin: '8px 0 0' }}>Average <b>{fmt(chart.stats.mean, 2)}</b>{sx?.units ? ` ${sx.units}` : ''}; the middle half of people fall between <b>{fmt(chart.stats.q1, 2)}</b> and <b>{fmt(chart.stats.q3, 2)}</b> ({chart.stats.n.toLocaleString()} people).</p>
            <Advanced><div className="row small tabular" style={{ marginTop: 8 }}>
              {(['n', 'mean', 'sd', 'p10', 'q1', 'median', 'q3', 'p90'] as const).map(k => <span key={k} className="pill">{k} {fmt((chart.stats as any)[k], 3)}</span>)}
            </div></Advanced>
          </>
        )}
        {chart?.kind === 'scatter' && !adv && (
          <p className="small secondary" style={{ margin: '8px 0 0' }}>{strength(chart.r!.r)} ({chart.r!.r >= 0 ? 'higher' : 'lower'} {sx?.label.toLowerCase()} tends to go with {chart.r!.r >= 0 ? 'higher' : 'lower'} {sy?.label.toLowerCase()}; correlation {fmt(chart.r!.r, 2)}). This is an association, not proof of cause.</p>
        )}
        {chart?.kind === 'scatter' && adv && (
          <div className="row small tabular" style={{ marginTop: 8 }}>
            <span className="pill">Pearson r = {fmt(chart.r!.r, 3)}</span><span className="pill">slope {fmt(chart.fit!.slope, 4)}</span>
            <span className="pill">R² {fmt(chart.fit!.r2, 3)}</span><span className="pill">n = {chart.r!.n.toLocaleString()}</span>
            <span className="muted">Simulated association — not a causal estimate. Use the causal web and person "why" panels for mechanisms.</span>
          </div>
        )}
        {chart?.kind === 'means' && <div className="small muted" style={{ marginTop: 6 }}>Bars show group averages; the thin lines show 95% uncertainty.</div>}
      </div>
      <WhyPanel v={x} />
    </div>
  )
}

function strength(r: number) {
  const a = Math.abs(r)
  return a < 0.1 ? 'Essentially no relationship' : a < 0.3 ? 'A weak relationship' : a < 0.5 ? 'A moderate relationship' : 'A strong relationship'
}

/** "Why is this group different?" — the cohort's gap from everyone, split into the model's forces, plus example lives. */
function WhyPanel({ v }: { v: string }) {
  const { cohort, universe, dataVersion, registry } = useStore()
  const [res, setRes] = useState<any>(null)
  const [err, setErr] = useState('')
  const spec = registry!.variables[v]
  useEffect(() => {
    if (!cohort.length || STATIC) return
    setRes(null); setErr('')
    api.cohortExplain({ and: cohort }, v, universe).then(setRes).catch(e => setErr(String(e.message ?? e)))
  }, [v, JSON.stringify(cohort), universe, dataVersion])
  if (!cohort.length || STATIC) return null
  const gap = res ? res.cohort_mean - res.population_mean : 0
  return (
    <div className="card" style={{ marginTop: 14 }}>
      <h3>Why is this group different?</h3>
      <p className="hint">Your group: {cohort.map(c => condLabel(c, registry)).join(' · ')}</p>
      {err && <div className="banner">{err}</div>}
      {!res && !err && <Loading what="Tracing causes" />}
      {res && (
        <div className="grid g2">
          <div>
            <p className="small" style={{ marginTop: 0 }}>Average {spec?.label.toLowerCase()} is <b>{fmt(res.cohort_mean, 3)}</b> in this group vs <b>{fmt(res.population_mean, 3)}</b> for everyone ({gap >= 0 ? '+' : ''}{fmt(gap, 3)}).</p>
            {res.terms ? (
              <>
                <div className="small muted" style={{ marginBottom: 6 }}>Forces that make the difference (group minus everyone):</div>
                <Decomposition rows={res.terms.slice(0, 8).map((t: any) => ({ label: t.label, value: t.gap, evidence: t.evidence ?? undefined }))} />
                <p className="small muted">Red bars push {spec?.label.toLowerCase()} up for this group, blue bars push it down. Open <a href={`#/causal/${v}`}>Cause & effect</a> to see what drives each force.</p>
              </>
            ) : <p className="small muted">This measure isn't built from separate forces, so the model can't split the gap. Try a feeling like loneliness, happiness or stress.</p>}
          </div>
          <div>
            <div className="small muted" style={{ marginBottom: 6 }}>Example lives from this group, from lowest to highest:</div>
            {(res.representatives ?? []).map((r: any) => (
              <div key={r.role} className="row small" style={{ padding: '4px 0', borderBottom: '1px solid var(--grid)' }}>
                <span className="muted" style={{ width: 70 }}>{r.role}</span><PersonLink id={r.id} name={r.name} /><span className="spacer" /><span className="tabular">{fmt(r.value, 3)}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
