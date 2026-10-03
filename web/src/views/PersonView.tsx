import { useEffect, useMemo, useState } from 'react'
import { fmt } from '../analysis'
import { api } from '../api'
import { cssVar, Decomposition, DOMAIN_LABEL, Evidence, Loading, PersonLink } from '../components'
import { CyGraph } from '../graph'
import { useStore } from '../store'

const STATES = ['mood', 'loneliness', 'stress', 'anxiety', 'belonging', 'self_esteem', 'purpose', 'guilt', 'fatigue', 'financial_stress', 'academic_pressure', 'romantic_longing']
const BIG5 = ['extraversion', 'agreeableness', 'conscientiousness', 'neuroticism', 'openness', 'sensation_seeking', 'self_control', 'attachment_anxiety', 'attachment_avoidance', 'social_anxiety', 'rejection_sensitivity', 'conformity', 'empathy']
const FAITH = ['faith_belief', 'faith_certainty', 'religious_identity', 'institutional_trust', 'orthodoxy', 'moral_autonomy', 'practice_habit', 'attend_rate', 'private_practice', 'family_expectation', 'perceived_norm', 'chastity_commitment']

export default function PersonView({ id }: { id: number }) {
  const { universe, dataVersion, registry, setRoute } = useStore()
  const [p, setP] = useState<any>(null)
  const [err, setErr] = useState<string | null>(null)
  const [why, setWhy] = useState('loneliness')
  useEffect(() => {
    setErr(null)
    api.person(id, universe).then(setP).catch(e => setErr(String(e.message ?? e)))
  }, [id, universe, dataVersion])
  const vals = useMemo(() => {
    const m: Record<string, any> = {}
    if (p) for (const d of Object.values(p.domains) as any[]) for (const v of d) m[v.id] = v
    return m
  }, [p])
  const egoEls = useMemo(() => {
    if (!p?.network) return []
    const s8 = cssVar('--s8'), s5 = cssVar('--s5'), s1 = cssVar('--s1'), s3 = cssVar('--s3'), muted = cssVar('--axis')
    const nodes = p.network.nodes.map((nd: any) => ({ data: { id: String(nd.id), label: nd.ego ? p.name.split(' ')[0] : '', size: nd.ego ? 26 : 12, color: nd.ego ? s8 : s1 } }))
    const ids = new Set(nodes.map((n: any) => n.data.id))
    const edges = p.network.edges.filter((e: any) => ids.has(String(e.source)) && ids.has(String(e.target))).map((e: any, k: number) => ({
      data: { id: 'e' + k, source: String(e.source), target: String(e.target), width: e.alter_tie ? 0.7 : 1 + 2.5 * (e.closeness ?? 0.2),
        color: e.types?.includes('romantic') || e.types?.includes('spouse') ? s5 : e.alter_tie ? muted : e.stage >= 3 ? s3 : muted },
    }))
    return [...nodes, ...edges]
  }, [p])
  if (err) return <div className="page"><div className="empty">{err}</div></div>
  if (!p) return <Loading what="Reading this life" />
  const w = p.why[why]
  const ties = (p.network?.edges ?? []).filter((e: any) => !e.alter_tie).slice(0, 25)
  const Bar = ({ v, z = false }: { v: any; z?: boolean }) => {
    if (!v || v.value === null || v.value === undefined) return null
    const x = Number(v.value)
    const pctW = z ? Math.min(100, Math.abs(x) / 3 * 50) : Math.max(0, Math.min(1, x)) * 100
    return (
      <div className="decomp" style={{ gridTemplateColumns: '170px 1fr 44px' }}>
        <div>{v.label}</div>
        <div className="bar">{z && <span className="zero" />}<i style={{ left: z ? (x >= 0 ? '50%' : `${50 - pctW}%`) : 0, width: `${Math.max(pctW, 0.8)}%`, background: 'var(--s1)' }} /></div>
        <div className="tabular small" style={{ textAlign: 'right' }}>{fmt(x, 2)}</div>
      </div>
    )
  }
  const pill = (k: string) => vals[k] && <span className="pill">{vals[k].label}: <b>{String(vals[k].value).replace(/_/g, ' ')}</b></span>
  return (
    <div className="page">
      <div className="row" style={{ alignItems: 'baseline' }}>
        <h1 style={{ marginRight: 8 }}>{p.name}</h1>
        <span className="muted">#{p.id} · synthetic person</span>
        <span className="spacer" />
        <button className="btn small" onClick={() => setRoute(['map'])}>See on map</button>
      </div>
      <p className="sub">{p.headline}. Right now: <b>{String(p.now.activity).replace(/_/g, ' ')}</b>.</p>
      <div className="row" style={{ marginBottom: 14 }}>
        {pill('school')}{pill('class_standing')}{pill('study_area')}{pill('job_type')}{pill('origin_region')}
        {p.home?.complex && <span className="pill">Home: <b>{p.home.complex}</b></span>}
        {p.ward && <span className="pill">Ward: <a href={`#/places/ward/${p.ward.id}`}>{p.ward.kind.replace(/_/g, ' ')} #{p.ward.id}</a></span>}
        {p.employer && <span className="pill">Works: <b>{p.employer.name}</b></span>}
        {p.partner && <span className="pill">Partner: <PersonLink id={p.partner.id} name={p.partner.name} /></span>}
      </div>

      {p.counterfactual && <Counterfactual cf={p.counterfactual} />}

      <div className="grid g3">
        <div className="card">
          <h3>How they feel — and why</h3>
          <p className="hint">Each state is an exact sum of mechanism terms plus decaying effects of past events. Click a state.</p>
          {STATES.map(s => vals[s] && (
            <div key={s} onClick={() => setWhy(s)} style={{ cursor: 'pointer', borderRadius: 6, background: why === s ? 'var(--surface-2)' : undefined }}><Bar v={vals[s]} /></div>
          ))}
        </div>
        <div className="card" style={{ gridColumn: 'span 2' }}>
          <h3>Why is {p.name.split(' ')[0]}’s {registry?.variables[why]?.label.toLowerCase()} {fmt(w.value, 2)}?</h3>
          <p className="hint">Mechanism terms (with evidence level) and the recent events still echoing. Red raises, blue lowers.</p>
          <Decomposition rows={[
            ...w.terms.map((t: any) => ({ label: t.label, value: t.value, evidence: t.evidence, title: t.mechanism })),
            ...w.events.slice(0, 8).map((e: any) => ({ label: `${e.event?.label ?? 'event'} (${e.event?.date ?? ''})`, value: e.value })),
            { label: 'Day-to-day noise', value: w.noise },
          ]} />
          {w.events.length > 0 && (
            <div className="small" style={{ marginTop: 10 }}>
              Trace an event's causes: {w.events.slice(0, 4).map((e: any) => e.event && <a key={e.event.id} href={`#/events/${e.event.id}`} style={{ marginRight: 10 }}>{e.event.label}</a>)}
            </div>
          )}
          <div className="row" style={{ marginTop: 12 }}>
            <b className="small">Current goals</b>
            {p.goals.map((g: any) => <span key={g.goal} className="pill">{g.goal} <span className="muted tabular">{fmt(g.intensity, 2)}</span></span>)}
            {!p.goals.length && <span className="muted small">none pressing</span>}
          </div>
        </div>
      </div>

      <div className="grid g3" style={{ marginTop: 14 }}>
        <div className="card"><h3>Personality</h3><p className="hint">z-scores relative to the population</p>{BIG5.map(k => <Bar key={k} v={vals[k]} z />)}</div>
        <div className="card"><h3>Faith — many dimensions</h3><p className="hint">belief ≠ attendance ≠ identity ≠ trust</p>{FAITH.map(k => <Bar key={k} v={vals[k]} />)}</div>
        <div className="card">
          <h3>Relationships</h3>
          <p className="hint">Strongest ties; pink edges in the graph are romantic.</p>
          <CyGraph elements={egoEls} height={230} onTap={(nid) => setRoute(['person', nid])} />
          <div className="scroll" style={{ maxHeight: 200, marginTop: 8 }}>
            <table className="data">
              <thead><tr><th>Person</th><th>Tie</th><th className="num">Close</th><th>Met</th></tr></thead>
              <tbody>{ties.map((e: any) => (
                <tr key={e.target}><td><PersonLink id={e.target} /></td><td className="small">{['stranger', 'acquaintance', 'casual friend', 'friend', 'close friend'][e.stage]}{e.types.filter((t: string) => !['preexisting', 'ward', 'classmate'].includes(t)).map((t: string) => ` · ${t}`)}</td>
                  <td className="num">{fmt(e.closeness, 2)}</td><td className="small">{e.met}{e.introducer !== null && e.introducer !== undefined ? <> via <PersonLink id={e.introducer} /></> : ''}</td></tr>
              ))}</tbody>
            </table>
          </div>
        </div>
      </div>

      <div className="grid g2" style={{ marginTop: 14 }}>
        <div className="card">
          <h3>Life story</h3>
          <p className="hint">Salient events in the simulation (newest first). Click an event to follow its causal chain.</p>
          <div className="scroll" style={{ maxHeight: 520 }}>
            <div className="timeline">
              {[...p.timeline].reverse().map((e: any) => (
                <div key={e.id} className={`tl-item ${e.category}`}>
                  <div className="tl-date">{e.date}{e.mechanism && <> · <span className="muted">{e.mechanism}</span></>}</div>
                  <a href={`#/events/${e.id}`}>{e.label}</a>{e.b !== null && e.b_name && <> — <PersonLink id={e.b} name={e.b_name} /></>}
                </div>
              ))}
              {!p.timeline.length && <div className="muted small">Nothing salient yet. Advance the clock.</div>}
            </div>
          </div>
        </div>
        <div className="card">
          <h3>Everything we model about this person</h3>
          <p className="hint">{Object.values(p.domains).reduce((s: number, d: any) => s + d.length, 0)} variables from the registry, with their evidence level.</p>
          <div className="scroll" style={{ maxHeight: 520 }}>
            {Object.entries(p.domains).map(([d, vs]: any) => (
              <details key={d} open={d === 'demographics'}>
                <summary style={{ cursor: 'pointer', padding: '6px 0', fontWeight: 600 }}>{DOMAIN_LABEL[d] ?? d} <span className="muted small">({vs.length})</span></summary>
                <table className="data"><tbody>{vs.map((v: any) => (
                  <tr key={v.id}><td><a href={`#/variables/${v.id}`}>{v.label}</a></td><td className="num">{v.value === null ? '—' : typeof v.value === 'number' ? fmt(v.value, 2) : String(v.value).replace(/_/g, ' ')}{v.units && typeof v.value === 'number' ? <span className="muted small"> {v.units}</span> : ''}</td><td><Evidence level={v.evidence} /></td></tr>
                ))}</tbody></table>
              </details>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}

function Counterfactual({ cf }: { cf: any }) {
  return (
    <div className="card" style={{ marginBottom: 14, borderColor: 'var(--accent)' }}>
      <h3>In the intervention universe…</h3>
      <p className="hint">Same person, same random numbers, from the fork on day {cf.fork_day}. Differences are consequences of the intervention (directly or through others).</p>
      {cf.diffs.length === 0 ? <div className="muted small">No differences yet for this person.</div> : (
        <div className="grid g2">
          <table className="data"><thead><tr><th>Variable</th><th>Baseline</th><th>Intervention</th></tr></thead>
            <tbody>{cf.diffs.slice(0, 16).map((d: any) => <tr key={d.id}><td>{d.label}</td><td>{typeof d.base === 'number' ? fmt(d.base, 3) : String(d.base)}</td><td><b>{typeof d.alt === 'number' ? fmt(d.alt, 3) : String(d.alt)}</b></td></tr>)}</tbody></table>
          <div className="grid g2 small">
            <div><b>Baseline life since fork</b>{cf.base_events.slice(-10).map((e: any) => <div key={e.id}>{e.date} · {e.label}</div>)}</div>
            <div><b>Intervention life since fork</b>{cf.alt_events.slice(-10).map((e: any) => <div key={e.id}>{e.date} · {e.label}</div>)}</div>
          </div>
        </div>
      )}
    </div>
  )
}
