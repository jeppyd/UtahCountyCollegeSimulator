import { useEffect, useMemo, useState } from 'react'
import { fmt } from '../analysis'
import { api } from '../api'
import { axisStyle, EChart, Loading, series, tokens } from '../components'
import { useStore } from '../store'
import { PageHeader } from '../ui'

const TABLE_LABEL: Record<string, string> = {
  married_share_acs: 'Share married, by age and sex (Census, Provo + Orem)',
  married_share_institutional: 'Share of enrolled students who are married (BYU, UVU)',
  dates_month_by_sex_rel_activity: 'Dates per month, by relationship stage and church activity',
  dates_month_by_sex_age: 'Dates per month, by age (survey mix of singles and couples)',
  married_share_by_age_sex: 'Share married, by age (dating-survey respondents)',
  n_relationships_by_sex_age: 'Relationships so far, by age',
  n_kissed_by_sex_age: 'People kissed so far, by age',
  gpa_by_school_sex: 'GPA, by school and sex',
  sleep_by_school: 'Hours of sleep, by school',
  work_hours_by_school: 'Work hours per week, by school',
  social_events_by_sex_rel: 'Social events per month, by relationship stage',
  app_hours_by_sex_rel: 'Dating-app hours per week',
  social_media_hours_by_sex: 'Social-media hours per day',
  coffee_by_activity: 'Drinks coffee, by church activity',
  alcohol_by_activity: 'Drinks alcohol, by church activity',
  temple_per_year_by_activity: 'Temple visits per year, by church activity',
  scripture_minutes_by_activity: 'Scripture minutes per day, by church activity',
}
const KIND: Record<string, { label: string; hint: string }> = {
  benchmark: { label: 'Census', hint: 'Official statistics: the strongest test' },
  emergent: { label: 'Behavior', hint: 'Produced by the simulated behavior, compared with the surveys' },
  input: { label: 'Starting values', hint: 'Synthesized from the surveys; checks the population builder and later drift' },
  diagnostic: { label: 'Not scored', hint: 'Survey cells known to be biased (the dating surveys over-sample singles)' },
}
const STATUS: Record<string, { icon: string; label: string; color: string }> = {
  pass: { icon: '✓', label: 'matches', color: 'var(--good, #1baf7a)' },
  warn: { icon: '~', label: 'close', color: 'var(--warning, #eab308)' },
  fail: { icon: '✕', label: 'off', color: 'var(--critical, #e34948)' },
}
const STAB: [string, string, (x: number) => string][] = [
  ['byu_students_full_scale', 'BYU students (full scale)', x => Math.round(x).toLocaleString()],
  ['uvu_students_full_scale', 'UVU students in scope', x => Math.round(x).toLocaleString()],
  ['married_share_students', 'Students married', x => `${(100 * x).toFixed(1)}%`],
  ['dating_or_engaged_students', 'Students dating or engaged', x => `${(100 * x).toFixed(1)}%`],
  ['dates_per_month_singles', 'Dates per month (singles)', x => x.toFixed(2)],
  ['friends', 'Friends per person', x => x.toFixed(1)],
  ['loneliness', 'Loneliness (0–1)', x => x.toFixed(3)],
  ['active_share_lds', 'Members who are active', x => `${(100 * x).toFixed(1)}%`],
  ['non_lds_share', 'Not LDS', x => `${(100 * x).toFixed(1)}%`],
]

export default function ModelCheck() {
  const { setRoute } = useStore()
  const [d, setD] = useState<any>(null)
  const [err, setErr] = useState('')
  const [kind, setKind] = useState<string>('all')
  useEffect(() => { api.validation().then(setD).catch(e => setErr(String(e.message ?? e))) }, [])
  const v = d?.validation
  const rows: any[] = v?.rows ?? []
  const groups = useMemo(() => {
    const out: Record<string, any[]> = {}
    for (const r of rows) if (kind === 'all' || r.kind === kind) (out[r.table] ??= []).push(r)
    return out
  }, [rows, kind])
  const acs = rows.filter(r => r.table === 'married_share_acs')
  const acsOpt = useMemo(() => {
    if (!acs.length) return null
    const ax = axisStyle(), tk = tokens()
    const cats = acs.map(r => r.group.replace('sex=', '').replace(', age=', ' · '))
    return {
      grid: { left: 44, right: 12, top: 30, bottom: 30 },
      legend: { top: 0, textStyle: { color: tk.text2 } },
      tooltip: { trigger: 'axis', valueFormatter: (x: number) => `${(100 * x).toFixed(1)}%` },
      xAxis: { type: 'category', data: cats, ...ax },
      yAxis: { type: 'value', max: 1, axisLabel: { formatter: (x: number) => `${Math.round(100 * x)}%`, color: tk.muted }, splitLine: { lineStyle: { color: tk.grid } } },
      series: [
        { name: 'Census (ACS 2020–24)', type: 'bar', barGap: '8%', barWidth: 12, data: acs.map(r => r.target), itemStyle: { color: series(6), borderRadius: [4, 4, 0, 0] } },
        { name: 'Simulation', type: 'bar', barWidth: 12, data: acs.map(r => r.sim), itemStyle: { color: series(0), borderRadius: [4, 4, 0, 0] } },
      ],
    }
  }, [acs.length])
  const st = d?.stability
  if (err) return <div className="page"><div className="banner">{err}</div></div>
  if (!d) return <Loading what="Reading the latest checks" />
  const c = v?.summary?.counts ?? {}, cb = v?.summary?.counts_benchmark ?? {}, ce = v?.summary?.counts_behavior ?? {}
  return (
    <div className="page">
      <PageHeader id="modelcheck" eyebrow="The model" title="How trustworthy are the numbers?"
        sub="Every so often the simulation is run for a year and its results are compared with real data: the Census for marriage, and the student surveys for dating, friendships, faith and habits. This page shows how well it matches, where it doesn't, and whether it stays steady over four years."
        tips={[
          'Census rows are the strongest test: official counts of how many people in Provo and Orem are married at each age.',
          '"Behavior" rows come out of the simulated decisions (dates, events, habits) rather than being set at the start; those are the real test of the rules.',
          'A row can miss because the model is wrong or because the survey was a skewed sample (e.g. dating surveys over-sample singles). The "Not scored" rows are known to be skewed.',
          'Numbers labelled hypothetical in the data dictionary or rules come from reasoning, not data; treat what-if results that hinge on them as illustrations.',
        ]} />
      {!v ? <div className="banner">No validation report yet. Run <span className="kbd">python scripts/validate.py</span>.</div> : (
        <>
          <div className="grid g4" style={{ marginBottom: 14 }}>
            <div className="card tile"><div className="label">Census benchmarks</div><div className="value">{cb.pass ?? 0} / {(cb.pass ?? 0) + (cb.warn ?? 0) + (cb.fail ?? 0)}</div><div className="small muted">match within tolerance</div></div>
            <div className="card tile"><div className="label">Behavior checks</div><div className="value">{ce.pass ?? 0} ✓ · {ce.warn ?? 0} ~ · {ce.fail ?? 0} ✕</div><div className="small muted">match · close · off</div></div>
            <div className="card tile"><div className="label">All scored checks</div><div className="value">{c.pass ?? 0} ✓ · {c.warn ?? 0} ~ · {c.fail ?? 0} ✕</div><div className="small muted">{rows.filter(r => r.kind === 'diagnostic').length} more shown but not scored</div></div>
            <div className="card tile"><div className="label">Last checked</div><div className="value" style={{ fontSize: 18 }}>{v.summary.generated}</div><div className="small muted">simulated to {v.summary.date} · scale {v.summary.scale}</div></div>
          </div>
          {acsOpt && (
            <div className="card" style={{ marginBottom: 14 }}>
              <h3>Who is married, by age: simulation vs Census</h3>
              <p className="hint">Share of Provo and Orem residents who are married (ACS 2020–24 five-year estimates) next to everyone living in the simulated world at the same ages. From 25 on, most real residents are non-students the model doesn't include, so those bars compare different populations and aren't scored.</p>
              <EChart option={acsOpt} height={260} />
            </div>
          )}
          <div className="card" style={{ marginBottom: 14 }}>
            <div className="row" style={{ marginBottom: 8 }}>
              <h3 style={{ margin: 0, flex: 1 }}>Every check</h3>
              <div className="seg small-seg">
                <button className={kind === 'all' ? 'on' : ''} onClick={() => setKind('all')}>All</button>
                {Object.entries(KIND).map(([k, x]) => <button key={k} className={kind === k ? 'on' : ''} title={x.hint} onClick={() => setKind(k)}>{x.label}</button>)}
              </div>
            </div>
            {Object.entries(groups).map(([table, rs]) => (
              <details key={table} className="check-group" open={rs.some(r => r.status === 'fail' && r.kind !== 'diagnostic')}>
                <summary>
                  <b>{TABLE_LABEL[table] ?? table}</b>
                  <span className="small muted"> · {KIND[rs[0].kind]?.label}</span>
                  <span className="spacer" />
                  {(['pass', 'warn', 'fail'] as const).map(s => { const n = rs.filter(r => r.status === s).length; const muted = rs.every(r => r.kind === 'diagnostic'); return n ? <span key={s} className="pill" style={{ color: muted ? 'var(--text-muted)' : STATUS[s].color }}>{STATUS[s].icon} {n}</span> : null })}
                </summary>
                <table className="data small">
                  <thead><tr><th>group</th><th className="num">real data</th><th className="num">simulation</th><th className="num">allowed gap</th><th>result</th></tr></thead>
                  <tbody>{rs.map((r: any) => (
                    <tr key={r.group}><td>{r.group.replace(/_/g, ' ')}</td><td className="num tabular">{fmt(r.target, 3)}</td><td className="num tabular">{fmt(r.sim, 3)}</td>
                      <td className="num tabular muted">±{fmt(r.tol, 2)}</td>
                      <td>{r.kind === 'diagnostic' ? <span className="muted">not scored</span> : <span style={{ color: STATUS[r.status]?.color, fontWeight: 600 }}>{STATUS[r.status]?.icon} {STATUS[r.status]?.label ?? r.status}</span>}</td></tr>
                  ))}</tbody>
                </table>
              </details>
            ))}
          </div>
        </>
      )}
      <div className="card" style={{ marginBottom: 14 }}>
        <h3>Does it stay steady over four years?</h3>
        {!st ? <p className="hint">No four-year check yet. Run <span className="kbd">python scripts/stability.py</span>.</p> : (
          <>
            <p className="hint">The same world run for {st.years} years (scale {st.scale}). Snapshots in late October and early March each year. Big numbers should wobble with the calendar but not drift away.</p>
            <div style={{ overflowX: 'auto' }}>
              <table className="data small">
                <thead><tr><th>measure</th>{st.rows.map((r: any) => <th key={r.day} className="num">{new Date(r.date + 'T12:00:00').toLocaleDateString(undefined, { month: 'short', year: '2-digit' })}</th>)}<th className="num">change, first → last year</th></tr></thead>
                <tbody>{STAB.map(([k, label, f]) => (
                  <tr key={k}><td>{label}</td>{st.rows.map((r: any) => <td key={r.day} className="num tabular">{f(r[k])}</td>)}<td className="num tabular"><b>{(st.drift_first_to_last_year[k] >= 0 ? '+' : '') + f(st.drift_first_to_last_year[k]).replace('%', ' pts').replace(/^(\d)/, '$1')}</b></td></tr>
                ))}</tbody>
              </table>
            </div>
          </>
        )}
      </div>
      <div className="card">
        <h3>Where the numbers come from</h3>
        <p className="small secondary">Population and behavior are built from four Provo student surveys (only aggregate statistics are used), the Census, BYU and UVU enrollment figures, BYU's official contracted-housing list, real map data (Utah's UGRC, OpenStreetMap, Provo and Orem city GIS) and published research. Each rule and measure carries an evidence label.</p>
        <div className="row"><button className="btn small" onClick={() => setRoute(['about'])}>Evidence & sources</button><button className="btn small" onClick={() => setRoute(['guide', 'evidence'])}>Field guide: how sure are we?</button></div>
      </div>
    </div>
  )
}
