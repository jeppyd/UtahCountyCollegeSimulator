import { useEffect, useMemo, useState } from 'react'
import { fmt } from '../analysis'
import { api } from '../api'
import { cssVar, Decomposition, DOMAIN_LABEL, Evidence, Loading, PersonLink } from '../components'
import { CyGraph } from '../graph'
import { useStore } from '../store'
import { CATEGORY_LABEL, FollowButton, Story, useAdvanced } from '../ui'

const STATES = ['mood', 'loneliness', 'stress', 'anxiety', 'belonging', 'self_esteem', 'purpose', 'guilt', 'fatigue', 'financial_stress', 'academic_pressure', 'romantic_longing']
const BIG5 = ['extraversion', 'agreeableness', 'conscientiousness', 'neuroticism', 'openness', 'sensation_seeking', 'self_control', 'attachment_anxiety', 'attachment_avoidance', 'social_anxiety', 'rejection_sensitivity', 'conformity', 'empathy']
const FAITH = ['faith_belief', 'faith_certainty', 'religious_identity', 'institutional_trust', 'orthodoxy', 'moral_autonomy', 'practice_habit', 'attend_rate', 'private_practice', 'family_expectation', 'perceived_norm', 'chastity_commitment']
const TABS = [['story', 'Life story'], ['feel', 'Feelings & why'], ['rel', 'Relationships'], ['faith', 'Faith & beliefs'], ['pers', 'Personality'], ['all', 'Everything']] as const
type Tab = typeof TABS[number][0]

export default function PersonView({ id }: { id: number }) {
  const { universe, dataVersion, registry, setRoute } = useStore()
  const adv = useAdvanced()
  const [p, setP] = useState<any>(null)
  const [err, setErr] = useState<string | null>(null)
  const [why, setWhy] = useState('loneliness')
  const [tab, setTab] = useState<Tab>('story')
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
  const first = p.name.split(' ')[0]
  const w = p.why[why]
  const ties = (p.network?.edges ?? []).filter((e: any) => !e.alter_tie).slice(0, 30)
  const Bar = ({ v, z = false, onClick, on }: { v: any; z?: boolean; onClick?: () => void; on?: boolean }) => {
    if (!v || v.value === null || v.value === undefined) return null
    const x = Number(v.value)
    const pctW = z ? Math.min(100, Math.abs(x) / 3 * 50) : Math.max(0, Math.min(1, x)) * 100
    return (
      <div className="decomp" onClick={onClick} style={{ gridTemplateColumns: '170px 1fr 44px', cursor: onClick ? 'pointer' : undefined, background: on ? 'var(--surface-2)' : undefined, borderRadius: 6 }}>
        <div>{v.label}</div>
        <div className="bar">{z && <span className="zero" />}<i style={{ left: z ? (x >= 0 ? '50%' : `${50 - pctW}%`) : 0, width: `${Math.max(pctW, 0.8)}%`, background: 'var(--s1)' }} /></div>
        <div className="tabular small" style={{ textAlign: 'right' }}>{fmt(x, 2)}</div>
      </div>
    )
  }
  const pill = (k: string) => vals[k] && vals[k].value !== null && vals[k].value !== 'none' && <span className="pill">{vals[k].label}: <b>{String(vals[k].value).replace(/_/g, ' ')}</b></span>
  const initials = p.name.split(' ').map((s: string) => s[0]).join('')
  return (
    <div className="page">
      <div className="row" style={{ alignItems: 'center', flexWrap: 'nowrap', marginBottom: 6 }}>
        <span className="avatar" style={{ width: 48, height: 48, fontSize: 17, background: 'var(--s1)' }}>{initials}</span>
        <div style={{ minWidth: 0, flex: 1 }}>
          <div className="eyebrow">Synthetic person #{p.id}</div>
          <h1 style={{ margin: 0, fontSize: 24 }}>{p.name}</h1>
        </div>
        <FollowButton id={p.id} />
        <button className="btn" onClick={() => setRoute(['map', 'homes:activity'])}>Map</button>
      </div>
      <p className="sub" style={{ fontSize: 15, marginTop: 6 }}><Summary p={p} vals={vals} first={first} /></p>
      {p.looks && <p className="small secondary" style={{ margin: '-8px 0 12px' }}>{looks(p.looks)}</p>}
      <div className="row" style={{ marginBottom: 14 }}>
        {pill('school')}{pill('class_standing')}
        {p.major && <span className="pill">Major: <b>{p.major}</b></span>}
        {p.college && p.college !== 'none' && <span className="pill">{p.college}</span>}
        {pill('job_type')}{pill('origin_region')}
        {p.home?.complex && <span className="pill">Home: <b>{p.home.complex}</b></span>}
        {vals.neighborhood && vals.neighborhood.value !== 'Other' && <span className="pill">Neighborhood: <b>{vals.neighborhood.value}</b></span>}
        {p.ward && <span className="pill">Ward: <a href={`#/places/ward/${p.ward.id}`}>{p.ward.kind.replace(/_/g, ' ')} #{p.ward.id}</a></span>}
        {p.employer && <span className="pill">Works at: <b>{p.employer.name}</b></span>}
        {(p.groups ?? []).map((g: any) => <span key={g.kind} className="pill">{g.label}: <b>{g.name}</b></span>)}
        {p.partner && <span className="pill">Partner: <PersonLink id={p.partner.id} name={p.partner.name} /></span>}
        {p.roommates?.length > 0 && <span className="pill">Lives with: {p.roommates.slice(0, 4).map((r: any, k: number) => <span key={r.id}>{k ? ', ' : ''}<PersonLink id={r.id} name={r.name.split(' ')[0]} /></span>)}{p.roommates.length > 4 ? ` +${p.roommates.length - 4}` : ''}</span>}
      </div>

      {p.counterfactual && <Counterfactual cf={p.counterfactual} first={first} />}

      <div className="seg" role="tablist" style={{ marginBottom: 14, flexWrap: 'wrap' }}>
        {TABS.map(([k, l]) => <button key={k} role="tab" aria-selected={tab === k} className={tab === k ? 'on' : ''} onClick={() => setTab(k)}>{l}</button>)}
      </div>

      {tab === 'story' && (
        <div className="grid" style={{ gridTemplateColumns: 'minmax(0, 3fr) minmax(0, 2fr)' }}>
          <div className="card">
            <h3>{first}'s story so far</h3>
            <p className="hint">The memorable moments, newest first. Click "why?" to follow an event's chain of causes.</p>
            <div className="scroll" style={{ maxHeight: 620 }}>
              <div className="timeline">
                {[...p.timeline].reverse().map((e: any) => (
                  <div key={e.id} className={`tl-item ${e.category}`}>
                    <div className="tl-date">{new Date(e.date + 'T12:00:00').toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })} · {CATEGORY_LABEL[e.category] ?? e.category}{adv && e.mechanism ? <> · <span className="muted">{e.mechanism}</span></> : null}</div>
                    <Story e={e} me={p.id} /> <a className="small" href={`#/events/${e.id}`}>why?</a>
                  </div>
                ))}
                {!p.timeline.length && <div className="muted small">Nothing memorable yet. Run time forward.</div>}
              </div>
            </div>
          </div>
          <div className="grid" style={{ alignContent: 'start' }}>
            <div className="card">
              <h3>How {first} feels right now</h3>
              <p className="hint">0 = not at all, 1 = extremely. Click one to see why.</p>
              {['mood', 'loneliness', 'stress', 'belonging', 'financial_stress', 'romantic_longing'].map(s => vals[s] && <Bar key={s} v={vals[s]} onClick={() => { setWhy(s); setTab('feel') }} />)}
            </div>
            <div className="card">
              <h3>What {first} wants right now</h3>
              <div className="row">{p.goals.map((g: any) => <span key={g.goal} className="pill">{g.goal}{adv && <span className="muted tabular"> {fmt(g.intensity, 2)}</span>}</span>)}
                {!p.goals.length && <span className="muted small">Nothing pressing.</span>}</div>
            </div>
          </div>
        </div>
      )}

      {tab === 'feel' && (
        <div className="grid" style={{ gridTemplateColumns: 'minmax(0, 2fr) minmax(0, 3fr)' }}>
          <div className="card">
            <h3>Feelings</h3>
            <p className="hint">Each feeling is built from forces in the model plus fading effects of recent events. Click one.</p>
            {STATES.map(s => vals[s] && <Bar key={s} v={vals[s]} on={why === s} onClick={() => setWhy(s)} />)}
          </div>
          <div className="card">
            <h3>Why is {first}'s {registry?.variables[why]?.label.toLowerCase()} {fmt(w.value, 2)}?</h3>
            <p className="hint">Red bars raise it, blue bars lower it. Labels name the model's rules{adv ? ' (with evidence level)' : ''} and the recent events whose effects are still fading.</p>
            <Decomposition rows={[
              ...w.terms.map((t: any) => ({ label: t.label, value: t.value, evidence: adv ? t.evidence : undefined, title: t.mechanism })),
              ...w.events.slice(0, 8).map((e: any) => ({ label: `${e.event?.label ?? 'event'} (${e.event?.date ?? ''})`, value: e.value })),
              { label: 'Day-to-day ups and downs', value: w.noise },
            ]} />
            {w.events.length > 0 && (
              <div className="small" style={{ marginTop: 10 }}>
                Follow an event's causes: {w.events.slice(0, 4).map((e: any) => e.event && <a key={e.event.id} href={`#/events/${e.event.id}`} style={{ marginRight: 10 }}>{e.event.label}</a>)}
              </div>
            )}
          </div>
        </div>
      )}

      {tab === 'rel' && (
        <div className="grid g2">
          <div className="card">
            <h3>{first}'s circle</h3>
            <p className="hint">Strongest ties. Pink lines are romantic; green are friends; thicker means closer. Click someone to open them.</p>
            <CyGraph elements={egoEls} height={380} onTap={(nid) => setRoute(['person', nid])} />
          </div>
          <div className="card">
            <h3>Everyone {first} knows well</h3>
            <div className="scroll" style={{ maxHeight: 420 }}>
              <table className="data">
                <thead><tr><th>Person</th><th>Relationship</th><th className="num">Closeness</th><th>How they met</th></tr></thead>
                <tbody>{ties.map((e: any) => (
                  <tr key={e.target}><td><PersonLink id={e.target} name={e.name} /></td><td className="small">{['stranger', 'acquaintance', 'casual friend', 'friend', 'close friend'][e.stage]}{e.types.filter((t: string) => !['preexisting', 'ward', 'classmate'].includes(t)).map((t: string) => ` · ${t.replace(/_/g, ' ')}`)}</td>
                    <td className="num">{fmt(e.closeness, 2)}</td><td className="small">{e.met}{e.introducer !== null && e.introducer !== undefined ? <> via <PersonLink id={e.introducer} /></> : ''}</td></tr>
                ))}</tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {tab === 'faith' && (
        <div className="grid g2">
          <div className="card"><h3>Faith has many dimensions</h3><p className="hint">Belief, attendance, identity and trust can move separately: someone can attend without certainty, or believe without attending.</p>{FAITH.map(k => <Bar key={k} v={vals[k]} />)}</div>
          <div className="card"><h3>Values & practices</h3>
            {['politics', 'traditional_roles', 'lgbtq_tension', 'coffee', 'alcohol', 'porn_use', 'scripture_minutes', 'temple_per_year', 'temple_recommend', 'mission_status'].map(k => vals[k] && (
              <div key={k} className="row small" style={{ padding: '4px 0', borderBottom: '1px solid var(--grid)' }}><span style={{ flex: 1 }}>{vals[k].label}</span><b>{typeof vals[k].value === 'number' ? fmt(vals[k].value, 2) : String(vals[k].value).replace(/_/g, ' ')}</b></div>
            ))}
          </div>
        </div>
      )}

      {tab === 'pers' && (
        <div className="card"><h3>Personality</h3><p className="hint">Compared with everyone else: the center line is average; bars to the right are above average.</p>
          <div className="grid g2">{[BIG5.slice(0, 7), BIG5.slice(7)].map((ks, k) => <div key={k}>{ks.map(x => <Bar key={x} v={vals[x]} z />)}</div>)}</div></div>
      )}

      {tab === 'all' && (
        <div className="card">
          <h3>Everything the model tracks about {first}</h3>
          <p className="hint">{Object.values(p.domains).reduce((s: number, d: any) => s + d.length, 0)} measures, grouped by area. Click a name to learn what it means.</p>
          <div className="grid g2">
            {Object.entries(p.domains).map(([d, vs]: any) => (
              <details key={d} open={d === 'demographics'}>
                <summary style={{ cursor: 'pointer', padding: '6px 0', fontWeight: 600 }}>{DOMAIN_LABEL[d] ?? d} <span className="muted small">({vs.length})</span></summary>
                <table className="data"><tbody>{vs.map((v: any) => (
                  <tr key={v.id}><td><a href={`#/variables/${v.id}`}>{v.label}</a></td><td className="num">{v.value === null ? '—' : typeof v.value === 'number' ? fmt(v.value, 2) : String(v.value).replace(/_/g, ' ')}{v.units && typeof v.value === 'number' ? <span className="muted small"> {v.units}</span> : ''}</td>{adv && <td><Evidence level={v.evidence} /></td>}</tr>
                ))}</tbody></table>
              </details>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

function looks(l: any) {
  const ft = Math.floor(l.height_in / 12), inch = Math.round(l.height_in - 12 * ft)
  const bits = [`${ft}′${inch === 12 ? 11 : inch}″`]
  if (l.weight_lb) bits.push(`${Math.round(l.weight_lb)} lb`)
  if (l.build) bits.push(`${l.build} build`)
  if (l.hair) bits.push(`${String(l.hair).replace('_', ' ')} hair`)
  if (l.eyes) bits.push(`${l.eyes} eyes`)
  return bits.join(' · ')
}

/** A few plain sentences about who this person is and how they're doing. */
function Summary({ p, vals, first }: { p: any; vals: Record<string, any>; first: string }) {
  const v = (k: string) => vals[k]?.value
  const level = (x: number, words: [string, string, string]) => (x < 0.33 ? words[0] : x < 0.6 ? words[1] : words[2])
  const parts: string[] = [`${p.headline.charAt(0).toUpperCase()}${p.headline.slice(1)}.`]
  const nf = v('n_friends'), nc = v('n_close_friends')
  if (typeof nf === 'number') parts.push(`${first} has ${nf} friend${nf === 1 ? '' : 's'}${typeof nc === 'number' ? ` (${nc} close)` : ''}.`)
  if (typeof v('mood') === 'number' && typeof v('loneliness') === 'number') {
    parts.push(`Lately ${first} has been ${level(v('mood'), ['unhappy', 'doing okay', 'happy'])} and ${level(v('loneliness'), ['rarely lonely', 'sometimes lonely', 'often lonely'])}${typeof v('stress') === 'number' && v('stress') > 0.55 ? ', and under a lot of stress' : ''}.`)
  }
  if (v('faith_crisis') === true || v('faith_crisis') === 'True' || v('faith_crisis') === 1) parts.push(`${first} is going through a faith crisis.`)
  return <>{parts.join(' ')} Right now: <b>{String(p.now.activity).replace(/_/g, ' ')}</b>.</>
}

function Counterfactual({ cf, first }: { cf: any; first: string }) {
  return (
    <div className="card" style={{ marginBottom: 14, borderColor: 'var(--accent)' }}>
      <h3>{first} in the what-if world</h3>
      <p className="hint">Same person, same dice, from the split on day {cf.fork_day}. Every difference is a consequence of the change, directly or through other people.</p>
      {cf.diffs.length === 0 ? <div className="muted small">No differences yet for {first}.</div> : (
        <div className="grid g2">
          <table className="data"><thead><tr><th>Measure</th><th>Original</th><th>What-if</th></tr></thead>
            <tbody>{cf.diffs.slice(0, 16).map((d: any) => <tr key={d.id}><td>{d.label}</td><td>{typeof d.base === 'number' ? fmt(d.base, 3) : String(d.base)}</td><td><b>{typeof d.alt === 'number' ? fmt(d.alt, 3) : String(d.alt)}</b></td></tr>)}</tbody></table>
          <div className="grid g2 small">
            <div><b>Original life since the split</b>{cf.base_events.slice(-10).map((e: any) => <div key={e.id}>{e.date} · {e.label}</div>)}</div>
            <div><b>What-if life since the split</b>{cf.alt_events.slice(-10).map((e: any) => <div key={e.id}>{e.date} · {e.label}</div>)}</div>
          </div>
        </div>
      )}
    </div>
  )
}
