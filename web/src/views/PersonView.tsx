// A life, not a row: who this person is, how they feel and why, their people, school and work, faith,
// money and home, their story, how they got here, and the life they live in the other world.
import { useEffect, useMemo, useState } from 'react'
import { fmt } from '../analysis'
import { api, STATIC } from '../api'
import { axisStyle, cssVar, Decomposition, DOMAIN_LABEL, EChart, Evidence, Loading, PersonLink, tokens } from '../components'
import { fval, polarity, pretty } from '../fields'
import { CatIcon, G, Meter, UBadge, uColor, useAsync, whatifKey } from '../game'
import { CyGraph } from '../graph'
import { useLens, useStore } from '../store'
import { CATEGORY_LABEL, FollowButton, Story, useAdvanced } from '../ui'
import { InnerLife } from './InnerLife'
import { Ruler } from '../kit/Ruler'
import { Val } from '../kit/Val'

const FEEL = ['mood', 'loneliness', 'stress', 'anxiety', 'belonging', 'self_esteem', 'purpose', 'guilt', 'fatigue', 'financial_stress', 'academic_pressure', 'romantic_longing']
const BIG5 = ['extraversion', 'agreeableness', 'conscientiousness', 'neuroticism', 'openness', 'sensation_seeking', 'self_control', 'attachment_anxiety', 'attachment_avoidance', 'social_anxiety', 'rejection_sensitivity', 'conformity', 'empathy']
const FAITH = ['faith_belief', 'faith_certainty', 'religious_identity', 'institutional_trust', 'orthodoxy', 'moral_autonomy', 'practice_habit', 'attend_rate', 'private_practice', 'family_expectation', 'perceived_norm', 'chastity_commitment', 'own_religiosity', 'outsider']
const SCHOOL = ['school', 'enrolled', 'class_standing', 'study_area', 'college', 'gpa', 'gpa_term', 'academic_standing', 'credits_done', 'credits_term', 'study_hours', 'class_attendance', 'graduated']
const WORK = ['employed', 'job_type', 'work_hours', 'wage', 'monthly_income', 'parental_support', 'savings', 'debt', 'owns_car', 'summer_sales']
const HOME = ['living', 'rent', 'rent_burden', 'city', 'neighborhood', 'dist_campus_km', 'commute_min', 'roommate_cohesion']
const DATING = ['rel_status', 'dates_30d', 'dates_total', 'n_relationships', 'n_breakups', 'app_user', 'app_hours', 'dating_motivation', 'relationship_satisfaction', 'relationship_commitment', 'wants_relationship']
const TABS: [string, string, string][] = [['now', 'Now', 'sun'], ['inner', 'Inner life', 'mind'], ['people', 'Their people', 'rings'], ['feel', 'Feelings', 'heart'], ['school', 'School & work', 'school'],
  ['faith', 'Faith', 'faith'], ['money', 'Money & home', 'key'], ['story', 'Story', 'book'], ['history', 'History', 'trend'], ['other', 'Other life', 'butterfly'], ['all', 'Everything', 'id']]

export default function PersonView({ id, tab: tab0 }: { id: number; tab?: string }) {
  const { dataVersion, registry, setRoute, togglePin, isPinned, pins, useInWhatIf } = useStore()
  const { u, compare, hasAlt } = useLens()
  const [why, setWhy] = useState('loneliness')
  const tab = tab0 && TABS.some(t => t[0] === tab0) && (tab0 !== 'other' || hasAlt) ? tab0 : 'now'
  const P = useAsync(() => api.person(id, compare ? 'base' : u), [id, u, compare, dataVersion])
  const PA = useAsync(() => (compare ? api.person(id, 'alt') : Promise.resolve(null)), [id, compare, dataVersion])
  const pop = useAsync(() => api.fieldsSummary(compare ? 'base' : u), [u, compare, dataVersion])
  const p: any = P.data, pa: any = PA.data
  const vals = useMemo(() => flat(p), [p])
  const valsA = useMemo(() => flat(pa), [pa])
  void pins
  if (P.error) return <div className="page"><div className="empty">{P.error}</div></div>
  if (!p) return <Loading what="Reading this life" />
  const first = p.name.split(' ')[0]
  const go = (t: string) => setRoute(['person', String(id), t])
  const initials = p.name.split(' ').map((s: string) => s[0]).join('')
  const pinned = isPinned({ kind: 'person', id })
  const sex = vals.sex?.value
  return (
    <div className="page life">
      <div className="life-head">
        <span className="avatar xl" style={{ background: `var(--s${(id % 7) + 1})` }}>{initials}</span>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div className="eyebrow">Synthetic person #{p.id}{hasAlt && !compare && <> · <UBadge u={u} /></>}{compare && <> · <UBadge u="base" /> with <UBadge u="alt" /> markers</>}</div>
          <h1>{p.name}</h1>
          <p className="lh-sub"><Summary p={p} vals={vals} first={first} /></p>
          {p.looks && <p className="small secondary" style={{ margin: '2px 0 0' }}>{looks(p.looks)}</p>}
        </div>
        <div className="row" style={{ flex: 'none', alignSelf: 'flex-start' }}>
          <FollowButton id={p.id} />
          <button className={`btn ${pinned ? 'following' : ''}`} onClick={() => togglePin({ kind: 'person', id, name: p.name })} title="Pin to your board">{G.pin} {pinned ? 'Pinned' : 'Pin'}</button>
          <button className="btn" onClick={() => setRoute(['map', 'homes:activity'])}>{G.map} Map</button>
          {!STATIC && <button className="btn" onClick={() => useInWhatIf({ ref: `person:${p.id}`, kind: 'person', label: p.name, sub: `#${p.id}`, n: 1 })} title="Tag this person in a What-if">{G.butterfly} What if…</button>}
        </div>
      </div>
      <div className="life-pills">
        <span className="pill now-pill">{G.clock} right now: <b>{pretty(p.now.activity)}</b></span>
        {pill(vals, 'school')}{pill(vals, 'class_standing')}
        {vals.affiliation && vals.affiliation.value !== 'Latter-day Saint' && <span className="pill">Faith: <b>{vals.affiliation.value === 'Nonreligious' ? 'not religious' : vals.affiliation.value}</b></span>}
        {p.major && <span className="pill">Major: <b>{p.major}</b></span>}
        {p.home?.complex && <span className="pill">Home: <b>{p.home.complex}</b></span>}
        {p.partner && <span className="pill">Partner: <PersonLink id={p.partner.id} name={p.partner.name} /></span>}
        {p.employer && <span className="pill">Works at: <b>{p.employer.name}</b></span>}
        {sex !== undefined && null}
      </div>
      {hasAlt && p.counterfactual && tab !== 'other' && lifeDiffs(p, registry).length > 0 && (
        <button className="other-life-banner" onClick={() => go('other')}>
          <span className="olb-icon">{G.butterfly}</span>
          <span><b>{first} lives a different life in the What-if world.</b> {lifeDiffs(p, registry).slice(0, 3).map((d: any) => `${d.label.toLowerCase()}: ${d.b} → ${d.a}`).join(' · ')}</span>
          <span className="olb-go">See both lives →</span>
        </button>
      )}
      <div className="tabs" style={{ marginBottom: 14 }}>
        {TABS.filter(t => t[0] !== 'other' || hasAlt).map(([k, l, i]) => <button key={k} className={tab === k ? 'on' : ''} onClick={() => go(k)}>{G[i]} {l}</button>)}
      </div>

      {tab === 'now' && (
        <div className="grid" style={{ gridTemplateColumns: 'minmax(0, 3fr) minmax(0, 2fr)' }}>
          <div className="grid" style={{ alignContent: 'start' }}>
            <div className="card">
              <h3>How {first} is doing</h3>
              <p className="hint">0 = not at all, 1 = extremely. Click one to see why.{compare ? ' Orange marks show the What-if world.' : ''}</p>
              {['mood', 'loneliness', 'stress', 'belonging', 'purpose', 'financial_stress', 'romantic_longing'].map(s => vals[s] && <Meter key={s} label={vals[s].label} value={vals[s].value} alt={compare ? valsA[s]?.value : undefined} polarity={polarity(s)} onClick={() => { setWhy(s); go('feel') }} />)}
            </div>
            <div className="card">
              <h3>Lately</h3>
              <Timeline events={[...p.timeline].reverse().slice(0, 8)} me={p.id} />
              {p.timeline.length > 8 && <button className="linkish small" onClick={() => go('story')}>The whole story ({p.timeline.length} moments) →</button>}
            </div>
          </div>
          <div className="grid" style={{ alignContent: 'start' }}>
            <div className="card">
              <h3>What {first} wants right now</h3>
              <div className="goals">{p.goals.map((g: any) => <span key={g.goal} className="goal"><i style={{ width: `${100 * g.intensity}%` }} />{g.goal}</span>)}
                {!p.goals.length && <span className="muted small">Nothing pressing.</span>}</div>
            </div>
            <div className="card">
              <h3>At a glance</h3>
              <div className="kpis compact">
                {['n_friends', 'n_close_friends', 'dates_30d', 'gpa', 'work_hours', 'rent'].filter(k => vals[k] && vals[k].value !== null).map(k => (
                  <div key={k} className="kpi click" onClick={() => setRoute(['explore', k])}><span className="k-label">{vals[k].label}</span><span className="k-val tabular"><Val v={k} value={vals[k].value} />{compare && valsA[k] && valsA[k].value !== vals[k].value ? <small className="u-alt-t"> → {fval(registry!.variables[k], valsA[k].value)}</small> : null}</span><Standing v={k} x={vals[k].value} pop={pop.data} /></div>
                ))}
              </div>
            </div>
            <div className="card">
              <h3>Where they belong</h3>
              <div className="belong">
                {p.ward && <div><span className="b-k">Ward</span><a href={`#/places/ward/${p.ward.id}`}>{pretty(p.ward.kind)} #{p.ward.id}</a></div>}
                {p.congregation && <div><span className="b-k">Congregation</span>{p.congregation}</div>}
                {(p.groups ?? []).map((g: any) => <div key={g.kind}><span className="b-k">{g.label}</span>{g.name}</div>)}
                {vals.neighborhood && vals.neighborhood.value !== 'Other' && <div><span className="b-k">Neighborhood</span>{vals.neighborhood.value}</div>}
                {p.roommates?.length > 0 && <div><span className="b-k">Lives with</span>{p.roommates.slice(0, 5).map((r: any, k: number) => <span key={r.id}>{k ? ', ' : ''}<PersonLink id={r.id} name={r.name.split(' ')[0]} /></span>)}{p.roommates.length > 5 ? ` +${p.roommates.length - 5}` : ''}</div>}
              </div>
            </div>
          </div>
        </div>
      )}

      {tab === 'inner' && <InnerLife id={id} first={first} />}
      {tab === 'people' && <TheirPeople p={p} first={first} />}

      {tab === 'feel' && (
        <div className="grid" style={{ gridTemplateColumns: 'minmax(0, 2fr) minmax(0, 3fr)' }}>
          <div className="card">
            <h3>Feelings</h3>
            <p className="hint">Each is built from forces in the model plus the fading effects of recent events. Click one.</p>
            {FEEL.map(s => vals[s] && <Meter key={s} label={vals[s].label} value={vals[s].value} alt={compare ? valsA[s]?.value : undefined} polarity={polarity(s)} active={why === s} onClick={() => setWhy(s)} />)}
          </div>
          <WhyCard p={p} why={why} first={first} />
        </div>
      )}

      {tab === 'school' && <FieldCards groups={[['School', SCHOOL], ['Work', WORK], ['Dating', DATING]]} vals={vals} valsA={compare ? valsA : null} pop={pop.data} />}
      {tab === 'faith' && (
        <div className="grid g2">
          <div className="card"><h3>Faith has many dimensions</h3><p className="hint">Belief, attendance, identity and trust can move separately: someone can attend without certainty, or believe without attending.</p>
            {FAITH.map(k => vals[k] && typeof vals[k].value === 'number' && <Meter key={k} label={vals[k].label} value={vals[k].value} alt={compare ? valsA[k]?.value : undefined} />)}</div>
          <FieldCards groups={[['Practices & values', ['affiliation', 'activity', 'lds_member', 'converted', 'investigating', 'mission_status', 'temple_recommend', 'temple_per_year', 'scripture_minutes', 'service_attend', 'faith_crisis', 'politics', 'traditional_roles', 'lgbtq_tension', 'coffee', 'alcohol']]]} vals={vals} valsA={compare ? valsA : null} pop={pop.data} single />
        </div>
      )}
      {tab === 'money' && (
        <>
          <FieldCards groups={[['Home', HOME], ['Money', ['monthly_income', 'parental_support', 'savings', 'debt', 'financial_stress', 'wage', 'work_hours']]]} vals={vals} valsA={compare ? valsA : null} pop={pop.data} />
          {p.home && <div className="card" style={{ marginTop: 14 }}><h3>{first}'s home</h3><p className="small">{p.home.complex ?? 'A private rental'} · {pretty(p.home.living)} · rent ${Math.round(p.home.rent).toLocaleString()}/month{p.roommates?.length ? ` · ${p.roommates.length} roommate${p.roommates.length > 1 ? 's' : ''}` : ''}</p></div>}
        </>
      )}
      {tab === 'story' && (
        <div className="card">
          <h3>{first}'s story so far</h3>
          <p className="hint">The memorable moments, newest first. “Why?” follows an event's chain of causes.</p>
          <Timeline events={[...p.timeline].reverse()} me={p.id} />
        </div>
      )}
      {tab === 'history' && <History id={id} first={first} />}
      {tab === 'other' && <OtherLife id={id} first={first} />}
      {tab === 'all' && <Everything p={p} pa={compare ? pa : null} first={first} />}
    </div>
  )
}

/** The counterfactual differences worth a headline: named partners, then chartable fields (no raw ids or day numbers). */
function lifeDiffs(p: any, registry: any) {
  const out: { label: string; b: string; a: string }[] = []
  const cf = p.counterfactual
  for (const d of cf?.diffs ?? []) {
    const spec = registry?.variables[d.id]
    if (d.id === 'partner_id') continue
    if (!spec || !(spec.flags ?? []).includes('chart') || d.id.endsWith('_id') || d.id.endsWith('_day')) continue
    out.push({ label: d.label, b: typeof d.base === 'number' ? fval(spec, d.base) : pretty(d.base), a: typeof d.alt === 'number' ? fval(spec, d.alt) : pretty(d.alt) })
  }
  const rank = (l: string) => (/relationship status|living|activity|employed|partner/i.test(l) ? 0 : 1)
  return out.sort((x, y) => rank(x.label) - rank(y.label))
}

function flat(p: any) {
  const m: Record<string, any> = {}
  if (p) for (const d of Object.values(p.domains) as any[]) for (const v of d) m[v.id] = v
  return m
}
const pill = (vals: Record<string, any>, k: string) => vals[k] && vals[k].value !== null && vals[k].value !== 'none' && <span className="pill">{vals[k].label}: <b>{pretty(vals[k].value)}</b></span>

/** Where a value stands among everyone (approximate percentile from the population's quartiles). */
function Standing({ v, x, pop }: { v: string; x: any; pop: any }) {
  const s = pop?.fields?.[v]
  if (!s || s.kind !== 'num' || typeof x !== 'number' || s.p10 === undefined) return null
  const pts: [number, number][] = [[s.min, 0], [s.p10, 10], [s.p25, 25], [s.p50, 50], [s.p75, 75], [s.p90, 90], [s.max, 100]]
  let q = 50
  for (let k = 0; k < pts.length - 1; k++) {
    const [a, pa] = pts[k], [b, pb] = pts[k + 1]
    if (x >= a && x <= b) { q = b > a ? pa + ((x - a) / (b - a)) * (pb - pa) : (pa + pb) / 2; break }
    if (x > b) q = pb
  }
  const word = q >= 90 ? 'top 10%' : q >= 75 ? 'top quarter' : q <= 10 ? 'bottom 10%' : q <= 25 ? 'bottom quarter' : 'middle'
  return <span className="k-sub" title={`About ${Math.round(q)}th percentile among everyone`}><span className="standing"><i style={{ left: `${q}%` }} /></span> {word}</span>
}

function FieldCards({ groups, vals, valsA, pop, single }: { groups: [string, string[]][]; vals: Record<string, any>; valsA: Record<string, any> | null; pop: any; single?: boolean }) {
  const { registry, setRoute } = useStore()
  return (
    <div className={single ? '' : 'grid g2'}>
      {groups.map(([title, keys]) => (
        <div key={title} className="card">
          <h3>{title}</h3>
          <table className="data"><tbody>{keys.filter(k => vals[k]).map(k => {
            const spec = registry!.variables[k], x = vals[k].value, xa = valsA?.[k]?.value
            const diff = valsA && xa !== undefined && xa !== x
            return (
              <tr key={k} className="click" onClick={() => setRoute(['explore', k])}>
                <td>{vals[k].label}</td>
                <td className="num tabular"><b>{typeof x === 'number' ? <Val v={k} value={x} show="words" /> : fval(spec, x)}</b>{diff ? <span className="u-alt-t"> → {fval(spec, xa)}</span> : null}{vals[k].units && typeof x === 'number' && !/usd|\$/i.test(vals[k].units) ? <span className="muted small"> {vals[k].units}</span> : null}</td>
                <td style={{ width: 140 }}>{spec?.scale && typeof x === 'number' ? <Ruler v={k} value={x} variant="inline" /> : <Standing v={k} x={x} pop={pop} />}</td>
              </tr>)
          })}</tbody></table>
        </div>
      ))}
    </div>
  )
}

function Timeline({ events, me }: { events: any[]; me: number }) {
  const adv = useAdvanced()
  if (!events.length) return <div className="muted small">Nothing memorable yet. Let time run.</div>
  return (
    <div className="life-tl">
      {events.map(e => (
        <div key={e.id} className="ltl">
          <CatIcon c={e.category} />
          <div className="ltl-body">
            <div className="small muted">{new Date(e.date + 'T12:00:00').toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })} · {CATEGORY_LABEL[e.category] ?? e.category}{adv && e.mechanism ? ` · ${e.mechanism}` : ''}{e.only_here ? ' · only in this world' : ''}</div>
            <div><Story e={e} me={me} /> <a className="small" href={`#/events/${e.id}`}>why?</a></div>
          </div>
        </div>
      ))}
    </div>
  )
}

function WhyCard({ p, why, first }: { p: any; why: string; first: string }) {
  const { registry } = useStore()
  const adv = useAdvanced()
  const w = p.why[why]
  if (!w) return <div className="card">No breakdown for this feeling.</div>
  return (
    <div className="card">
      <h3>Why is {first}'s {registry?.variables[why]?.label.toLowerCase()} {fmt(w.value, 2)}?</h3>
      <p className="hint">Red raises it, blue lowers it: the model's rules{adv ? ' (with evidence level)' : ''} and the recent events whose effects are still fading.</p>
      <Decomposition rows={[
        ...w.terms.map((t: any) => ({ label: t.label, value: t.value, evidence: adv ? t.evidence : undefined, title: t.mechanism })),
        ...w.events.slice(0, 8).map((e: any) => ({ label: `${e.event?.label ?? 'event'} (${e.event?.date ?? ''})`, value: e.value })),
        { label: 'Day-to-day ups and downs', value: w.noise },
      ]} />
      {w.events.length > 0 && <div className="small" style={{ marginTop: 10 }}>Follow an event's causes: {w.events.slice(0, 4).map((e: any) => e.event && <a key={e.event.id} href={`#/events/${e.event.id}`} style={{ marginRight: 10 }}>{e.event.label}</a>)}</div>}
    </div>
  )
}

function TheirPeople({ p, first }: { p: any; first: string }) {
  const { setRoute } = useStore()
  const els = useMemo(() => {
    if (!p?.network) return []
    const s8 = cssVar('--s8'), s5 = cssVar('--s5'), s1 = cssVar('--s1'), s3 = cssVar('--s3'), muted = cssVar('--axis')
    const nodes = p.network.nodes.map((nd: any) => ({ data: { id: String(nd.id), label: nd.ego ? first : '', size: nd.ego ? 26 : 12, color: nd.ego ? s8 : s1 } }))
    const ids = new Set(nodes.map((n: any) => n.data.id))
    const edges = p.network.edges.filter((e: any) => ids.has(String(e.source)) && ids.has(String(e.target))).map((e: any, k: number) => ({
      data: { id: 'e' + k, source: String(e.source), target: String(e.target), width: e.alter_tie ? 0.7 : 1 + 2.5 * (e.closeness ?? 0.2),
        color: e.types?.includes('romantic') || e.types?.includes('spouse') ? s5 : e.alter_tie ? muted : e.stage >= 3 ? s3 : muted },
    }))
    return [...nodes, ...edges]
  }, [p])
  const ties = (p.network?.edges ?? []).filter((e: any) => !e.alter_tie).slice(0, 40)
  const STAGE = ['stranger', 'acquaintance', 'casual friend', 'friend', 'close friend']
  return (
    <div className="grid g2">
      <div className="card">
        <h3>{first}'s circle</h3>
        <p className="hint">Strongest ties. Pink lines are romantic, green are friends; thicker is closer. Click someone to open their life.</p>
        <CyGraph elements={els} height={420} onTap={nid => setRoute(['person', nid])} />
      </div>
      <div className="card">
        <h3>Everyone {first} knows well</h3>
        <div className="scroll" style={{ maxHeight: 460 }}>
          <table className="data">
            <thead><tr><th>Person</th><th>Relationship</th><th>Closeness</th><th>How they met</th></tr></thead>
            <tbody>{ties.map((e: any) => (
              <tr key={e.target}><td><PersonLink id={e.target} name={e.name} /></td>
                <td className="small">{STAGE[e.stage]}{e.types.filter((t: string) => !['preexisting', 'ward', 'classmate'].includes(t)).map((t: string) => ` · ${pretty(t)}`)}</td>
                <td><span className="closeness"><i style={{ width: `${100 * (e.closeness ?? 0)}%` }} /></span></td>
                <td className="small">{e.met}{e.introducer !== null && e.introducer !== undefined ? <> via <PersonLink id={e.introducer} /></> : ''}</td></tr>
            ))}</tbody>
          </table>
        </div>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------- history
const HIST_NUM = ['mood', 'loneliness', 'stress', 'belonging', 'n_friends', 'n_close_friends', 'dates_30d', 'faith_belief', 'attend_rate', 'financial_stress', 'gpa', 'life_satisfaction']
const HIST_CAT = ['rel_status', 'living', 'activity', 'school', 'enrolled', 'employed', 'mission_status', 'faith_crisis', 'depressive_episode', 'affiliation']

function History({ id, first }: { id: number; first: string }) {
  const { dataVersion, registry } = useStore()
  const { compare, hasAlt } = useLens()
  const h = useAsync(() => api.personHistory(id), [id, dataVersion])
  const d: any = h.data
  if (h.error) return <div className="card empty">{h.error}</div>
  if (!d) return <Loading what="Reading their history" />
  const both = hasAlt && d.alt
  const showAlt = both && compare
  const toDate = (s: string) => s
  return (
    <>
      <div className="card" style={{ marginBottom: 14 }}>
        <h3>{first}'s life, every two weeks</h3>
        <p className="hint">Each band shows what {first}'s situation was at each snapshot{showAlt ? '; the orange-edged band below is the What-if world' : both ? ' (switch the lens to Compare to see the What-if world too)' : ''}. Gaps mean they weren't in Provo–Orem (not yet arrived, on a mission, or moved away).</p>
        <div className="strips">
          {HIST_CAT.filter(v => d.base.cats[v]).map(v => (
            <div key={v} className="strip-row">
              <span className="strip-label small">{registry!.variables[v]?.label ?? v}</span>
              <div className="strip-col"><Strip vals={d.base.cats[v]} dates={d.base.dates} keys={stripKeys(d.base.cats[v], showAlt ? d.alt?.cats[v] : null)} />{showAlt && d.alt.cats[v] && <Strip vals={d.alt.cats[v]} dates={d.alt.dates} alt keys={stripKeys(d.base.cats[v], d.alt.cats[v])} />}</div>
            </div>
          ))}
        </div>
        <div className="strip-axis small muted"><span>{new Date(d.base.dates[0] + 'T12:00:00').toLocaleDateString(undefined, { month: 'short', year: 'numeric' })}</span><span>now</span></div>
      </div>
      <div className="grid g4">
        {HIST_NUM.filter(v => d.base.nums[v] && d.base.nums[v].some((x: any) => x !== null)).map(v => (
          <div key={v} className="card"><h3 className="small-h">{registry!.variables[v]?.label}</h3>
            <MiniLine a={d.base.nums[v]} b={showAlt ? d.alt?.nums[v] : undefined} dates={d.base.dates.map(toDate)} spec={registry!.variables[v]} fork={d.fork_day !== null && d.fork_day !== undefined ? d.base.days.findIndex((x: number) => x >= d.fork_day) : -1} /></div>
        ))}
      </div>
    </>
  )
}

const stripKeys = (a: any[], b?: any[] | null) => [...new Set([...a, ...(b ?? [])].filter(v => v !== null).map(String))]
function Strip({ vals, dates, alt, keys }: { vals: any[]; dates: string[]; alt?: boolean; keys: string[] }) {
  // collapse runs of the same value into segments
  const segs: { v: any; a: number; b: number }[] = []
  vals.forEach((v, k) => { const last = segs[segs.length - 1]; if (last && last.v === v) last.b = k; else segs.push({ v, a: k, b: k }) })
  const n = Math.max(1, vals.length - 1)
  return (
    <div className={`strip ${alt ? 'alt' : ''}`}>
      {segs.map((s, k) => {
        const left = (100 * s.a) / (n + 1), width = (100 * (s.b - s.a + 1)) / (n + 1)
        const idx = keys.indexOf(String(s.v))
        return <i key={k} title={`${s.v === null ? 'not here' : pretty(s.v)} · ${dates[s.a]} → ${dates[s.b]}`} className={s.v === null ? 'absent' : ''} style={{ left: `${left}%`, width: `${width}%`, background: s.v === null ? undefined : `color-mix(in srgb, var(--s${(idx % 8) + 1}) 55%, var(--surface-1))` }}>{width > 9 && s.v !== null ? pretty(s.v === true ? 'yes' : s.v === false ? 'no' : s.v) : ''}</i>
      })}
    </div>
  )
}

function MiniLine({ a, b, dates, spec, fork }: { a: (number | null)[]; b?: (number | null)[]; dates: string[]; spec: any; fork: number }) {
  const opt = useMemo(() => {
    const ax = axisStyle(), t = tokens()
    return {
      grid: { left: 4, right: 8, top: 8, bottom: 4, containLabel: true },
      tooltip: { trigger: 'axis', valueFormatter: (x: number) => (x === null || x === undefined ? '—' : fval(spec, x)) },
      xAxis: { type: 'category', data: dates, show: false }, yAxis: { type: 'value', scale: true, ...ax, splitNumber: 2 },
      series: [
        { name: 'Original', type: 'line', showSymbol: false, connectNulls: false, data: a, lineStyle: { width: 2, color: uColor('base') }, itemStyle: { color: uColor('base') },
          markLine: fork > 0 && b ? { symbol: 'none', silent: true, lineStyle: { color: t.muted, type: 'dashed' }, label: { show: false }, data: [{ xAxis: fork }] } : undefined },
        ...(b ? [{ name: 'What-if', type: 'line', showSymbol: false, data: b, lineStyle: { width: 2, color: uColor('alt') }, itemStyle: { color: uColor('alt') } }] : []),
      ],
    }
  }, [a, b, dates])
  return <EChart option={opt} height={110} />
}

// ---------------------------------------------------------------- the other life
function OtherLife({ id, first }: { id: number; first: string }) {
  const { status, dataVersion, registry, setRoute } = useStore()
  const c = useAsync(() => api.comparePerson(id), [id, dataVersion], { key: whatifKey(status, `person:${id}`) })
  const d: any = c.data
  if (c.error) return <div className="card empty">{c.error}</div>
  if (!d) return <Loading what="Comparing both lives" />
  const byDomain: Record<string, any[]> = {}
  for (const s of d.states) (byDomain[s.domain] ??= []).push(s)
  const Chain = ({ chain, u }: { chain: any[] | null; u: 'base' | 'alt' }) => {
    if (!chain) return <div className="small muted">Nothing happened only in the {u === 'alt' ? 'What-if' : 'Original'}.</div>
    const steps = [...chain].reverse()
    return (
      <div className="chain">
        {steps.map((e, k) => (
          <div key={e.id} className={`chain-step ${k === steps.length - 1 ? 'last' : ''}`}>
            <CatIcon c={e.category} />
            <div><div className="small muted">{new Date(e.date + 'T12:00:00').toLocaleDateString(undefined, { month: 'short', day: 'numeric' })}{e.mechanism ? ` · ${e.mechanism}` : ''}</div><Story e={e} me={id} /></div>
          </div>
        ))}
      </div>
    )
  }
  return (
    <>
      <div className="two-u" style={{ marginBottom: 14 }}>
        <div className="card u-col"><UBadge u="base" /><p className="other-head">{d.headline_base}</p>{d.partner_base && <div className="small">Partner: <PersonLink id={d.partner_base.id} name={d.partner_base.name} /></div>}<div className="small muted">{d.n_friends[0]} friends</div></div>
        <div className="card u-col alt"><UBadge u="alt" /><p className="other-head">{d.headline_alt}</p>{d.partner_alt && <div className="small">Partner: <PersonLink id={d.partner_alt.id} name={d.partner_alt.name} /></div>}<div className="small muted">{d.n_friends[1]} friends</div></div>
      </div>
      <div className="card" style={{ marginBottom: 14 }}>
        <h3>{G.butterfly} Where {first}'s road forked</h3>
        <p className="hint">The first memorable moment that happened in only one world, and the recorded chain of causes behind it. Often the fork starts with someone else: a friend who moved, a date who asked someone else.</p>
        <div className="two-u">
          <div className="u-col card flat"><div className="small" style={{ marginBottom: 6 }}><UBadge u="base" /> only in the Original</div><Chain chain={d.first_base} u="base" /></div>
          <div className="u-col card flat alt"><div className="small" style={{ marginBottom: 6 }}><UBadge u="alt" /> only in the What-if</div><Chain chain={d.first_alt} u="alt" /></div>
        </div>
      </div>
      <div className="grid g2" style={{ marginBottom: 14 }}>
        <div className="card">
          <h3>What's different now</h3>
          {d.states.length === 0 ? <div className="small muted">Nothing measurable differs yet.</div> : Object.entries(byDomain).map(([dom, rows]) => (
            <div key={dom} style={{ marginBottom: 8 }}><div className="small muted">{DOMAIN_LABEL[dom] ?? dom}</div>
              <table className="data"><tbody>{rows.map((s: any) => (
                <tr key={s.id} className="click" onClick={() => setRoute(['explore', s.id])}><td>{s.label}</td>
                  <td className="num tabular u-base-t">{typeof s.base === 'number' ? fval(registry!.variables[s.id], s.base) : pretty(s.base)}</td><td style={{ width: 16 }}>→</td>
                  <td className="tabular u-alt-t">{typeof s.alt === 'number' ? fval(registry!.variables[s.id], s.alt) : pretty(s.alt)}</td></tr>))}</tbody></table></div>
          ))}
        </div>
        <div className="card">
          <h3>Friends gained and lost</h3>
          <div className="two-u">
            <div><div className="small" style={{ marginBottom: 4 }}><UBadge u="alt" /> only in the What-if</div>{d.friends_gained.length ? d.friends_gained.slice(0, 12).map((f: any) => <div key={f.id} className="row small bf-flow"><PersonLink id={f.id} name={f.name} /><span className="spacer" /><span className="muted">{f.romantic ? 'romantic · ' : ''}{f.met}</span></div>) : <div className="small muted">None</div>}</div>
            <div><div className="small" style={{ marginBottom: 4 }}><UBadge u="base" /> only in the Original</div>{d.friends_lost.length ? d.friends_lost.slice(0, 12).map((f: any) => <div key={f.id} className="row small bf-flow"><PersonLink id={f.id} name={f.name} /><span className="spacer" /><span className="muted">{f.romantic ? 'romantic · ' : ''}{f.met}</span></div>) : <div className="small muted">None</div>}</div>
          </div>
        </div>
      </div>
      <div className="two-u">
        <div className="card u-col"><h3>Life since the split · Original</h3><Timeline events={[...d.life_base].reverse()} me={id} /></div>
        <div className="card u-col alt"><h3>Life since the split · What-if</h3><Timeline events={[...d.life_alt].reverse()} me={id} /></div>
      </div>
    </>
  )
}

function Everything({ p, pa, first }: { p: any; pa: any; first: string }) {
  const adv = useAdvanced()
  const A = flat(pa)
  return (
    <div className="card">
      <h3>Everything the model tracks about {first}</h3>
      <p className="hint">{Object.values(p.domains).reduce((s: number, d: any) => s + d.length, 0)} fields, grouped by area. Click a name to explore it across everyone.</p>
      <div className="grid g2">
        {Object.entries(p.domains).map(([d, vs]: any) => (
          <details key={d} open={d === 'demographics'} className="check-group">
            <summary><b>{DOMAIN_LABEL[d] ?? d}</b> <span className="muted small">({vs.length})</span></summary>
            <table className="data"><tbody>{vs.map((v: any) => {
              const alt = pa ? A[v.id]?.value : undefined
              return (
                <tr key={v.id}><td><a href={`#/explore/${v.id}`}>{v.label}</a></td>
                  <td className="num">{v.value === null ? '—' : typeof v.value === 'number' ? fmt(v.value, 2) : pretty(v.value)}{pa && alt !== undefined && alt !== v.value ? <span className="u-alt-t"> → {typeof alt === 'number' ? fmt(alt, 2) : pretty(alt)}</span> : null}{v.units && typeof v.value === 'number' ? <span className="muted small"> {v.units}</span> : ''}</td>
                  {adv && <td><Evidence level={v.evidence} /></td>}</tr>)
            })}</tbody></table>
          </details>
        ))}
      </div>
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
  if (v('faith_crisis') === true) parts.push(`${first} is going through a faith crisis.`)
  return <>{parts.join(' ')}</>
}

export { STATIC }
