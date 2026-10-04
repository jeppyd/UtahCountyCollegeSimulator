// The inner life of one person: what they care about and what is pulling at them, what they believe (and how that
// differs from what is true), what they remember, what they were trying to do and why plans changed, how they cope,
// what they learned, the shape of their week and how they changed the world around them. Everything here is read
// from the simulation's state (mind, memory, coping, plans, routine and culture systems) — no generated text.
import { api } from '../api'
import { Loading, PersonLink } from '../components'
import { pretty } from '../fields'
import { CatIcon, useAsync } from '../game'
import { useLens, useStore } from '../store'
import { Story, useAdvanced } from '../ui'

const INTENT: Record<string, string> = {
  ask_out: 'Ask someone out', reconnect: 'Reconnect with a friend', meet_people: 'Meet new people', study_more: 'Study more',
  find_work: 'Find work', return_to_church: 'Get back to church', none: 'Nothing in particular',
}
const STRAT: Record<string, string> = {
  none: 'not coping with anything in particular', support: 'reaching out to people', active: 'tackling the problem head-on',
  religious: 'turning to faith', distraction: 'keeping busy (exercise, outings)', withdrawal: 'pulling back and staying in',
}
const STRAT_SHORT: Record<string, string> = { support: 'Reach out', active: 'Tackle it', religious: 'Faith', distraction: 'Keep busy', withdrawal: 'Pull back' }
const STATUS_TONE: Record<string, string> = { kept: 'good', abandoned: 'bad', lapsed: 'mid', active: 'neutral' }
const DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
const BLOCKS = ['morning', 'afternoon', 'evening']
const fmtDate = (d?: string) => (d ? new Date(d + 'T12:00:00').toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' }) : '')
const n2 = (x: any) => (x === null || x === undefined ? '—' : Number(x).toFixed(2))

export function InnerLife({ id, first }: { id: number; first: string }) {
  const { dataVersion, setRoute } = useStore()
  const { u, compare } = useLens()
  const adv = useAdvanced()
  const r = useAsync(() => api.personInner(id, compare ? 'base' : u), [id, u, compare, dataVersion])
  const d: any = r.data
  if (r.error) return <div className="card empty">{r.error}</div>
  if (!d) return <Loading what="Reading their inner life" />
  const top = d.motives[0]
  const activePlan = d.plans.find((p: any) => p.status === 'active')
  return (
    <div className="inner">
      <div className="grid" style={{ gridTemplateColumns: 'minmax(0, 3fr) minmax(0, 2fr)' }}>
        <div className="card">
          <h3>What {first} cares about — and what is pulling at them</h3>
          <p className="hint">The bar is how much each concern matters to {first} (from their personality, values and situation; it shifts slowly). The filled part is how fulfilled it feels right now. The gap between them, weighted by how much it matters, is the <b>drive</b> — it steers what {first} does with free time, whether they ask someone out, study or reach out. Sorted by drive.</p>
          <div className="motives">
            {d.motives.map((m: any) => (
              <div key={m.motive} className={`motive ${m.motive === top.motive ? 'top' : ''}`} title={`cares ${n2(m.cares)} · fulfilled ${n2(m.fulfilled)} · drive ${n2(m.drive)}`}>
                <span className="mo-label">{m.label}</span>
                <span className="mo-track"><i className="mo-cares" style={{ width: `${100 * (m.cares ?? 0)}%` }}><b style={{ width: `${100 * (m.fulfilled ?? 0)}%` }} /></i></span>
                <span className="mo-drive tabular">{n2(m.drive)}</span>
              </div>
            ))}
          </div>
          <p className="small" style={{ marginTop: 8 }}>Right now the strongest pull is <b>{top.label}</b>{top.cares_pct !== null ? <> — {first} cares about it more than {Math.round(100 * top.cares_pct)}% of people</> : null}.</p>
        </div>
        <div className="card">
          <h3>What {first} is trying to do</h3>
          {activePlan ? (
            <div className="plan-now"><span className="pill">{INTENT[activePlan.kind] ?? pretty(activePlan.kind)}</span>
              {activePlan.target !== null && <> · <PersonLink id={activePlan.target} name={activePlan.target_name} /></>}
              <div className="small muted">since day {activePlan.start}, for about {activePlan.due - activePlan.start} days · driven by {pretty(activePlan.motive)}</div>
            </div>
          ) : <p className="small muted">No particular intention this week.</p>}
          <p className="hint" style={{ marginTop: 10 }}>Intentions raise the odds of acting but often aren't carried out. {first} has followed through on {d.plans_kept} and dropped or let lapse {d.plans_abandoned}.</p>
          <table className="data"><tbody>
            {d.plans.filter((p: any) => p.status !== 'active').slice(0, 8).map((p: any, k: number) => (
              <tr key={k}>
                <td className="small">{INTENT[p.kind] ?? pretty(p.kind)}{p.target !== null ? <> · <PersonLink id={p.target} name={p.target_name?.split(' ')[0]} /></> : null}</td>
                <td><span className={`tag ${STATUS_TONE[p.status]}`}>{p.status}</span></td>
                <td className="small muted">{p.status === 'kept' ? (p.event_record ? <a href={`#/events/${p.event_record.id}`}>{p.event_record.label.toLowerCase()}</a> : 'did it') : p.reason}</td>
              </tr>))}
          </tbody></table>
        </div>
      </div>

      <div className="card" style={{ marginTop: 14 }}>
        <h3>What {first} believes — and what is actually true</h3>
        <p className="hint">People act on the world they believe they live in. These are the places where {first}'s picture and the simulation's ground truth come apart. Each row: what they believe (●) and what is true (○) on the same scale.</p>
        <table className="data beliefs">
          <thead><tr><th>About</th><th>Believes</th><th>Actually</th><th style={{ width: '32%' }} /><th>Why it matters</th></tr></thead>
          <tbody>{d.beliefs.map((b: any, k: number) => {
            const lo = b.what.startsWith('Whether') ? -1 : 0
            const pos = (x: number) => `${(100 * (x - lo)) / (1 - lo)}%`
            return (
              <tr key={k}>
                <td>{b.what}{b.other !== undefined && <> <PersonLink id={b.other} name="(open)" /></>}{b.own !== undefined && <div className="small muted">their own interest: {n2(b.own)}</div>}</td>
                <td className="num tabular"><b>{n2(b.believed)}</b></td>
                <td className="num tabular">{n2(b.actual)}</td>
                <td>{b.believed !== null && b.actual !== null && (
                  <span className="belief-track"><i className="bt-actual" style={{ left: pos(b.actual) }} /><i className="bt-believed" style={{ left: pos(b.believed) }} />
                    <span className="bt-gap" style={{ left: pos(Math.min(b.believed, b.actual)), width: `${(100 * Math.abs(b.believed - b.actual)) / (1 - lo)}%` }} /></span>)}</td>
                <td className="small muted">{b.note}</td>
              </tr>)
          })}</tbody>
        </table>
      </div>

      <div className="grid g2" style={{ marginTop: 14 }}>
        <div className="card">
          <h3>What {first} remembers</h3>
          <p className="hint">The memories still most available to {first}, by how recent, important and often re-lived they are. Memories fade unless rehearsed; very important ones stay for good. {d.memory.count} kept, overall tone {d.memory.tone !== null && d.memory.tone >= 0 ? 'more good than bad' : 'more bad than good'}.</p>
          <div className="memories">
            {d.memories.map((m: any) => (
              <div key={m.event.id} className="memory">
                <CatIcon c={m.event.category} />
                <div className="mem-body">
                  <div className="small muted">{fmtDate(m.event.date)}{m.core ? ' · a core memory' : ''}{m.rehearsed ? ` · re-lived ${m.rehearsed}×` : ''}</div>
                  <div><Story e={m.event} me={id} /> <a className="small" href={`#/events/${m.event.id}`}>why?</a></div>
                </div>
                <span className={`mem-val ${m.valence > 0.1 ? 'pos' : m.valence < -0.1 ? 'neg' : ''}`} title={`feeling ${n2(m.valence)} · strength ${n2(m.strength)}`}><i style={{ width: `${Math.min(100, 30 * (m.strength ?? 0))}%` }} /></span>
              </div>))}
            {!d.memories.length && <div className="small muted">Nothing memorable yet.</div>}
          </div>
        </div>
        <div className="card">
          <h3>How {first} copes</h3>
          {d.coping.strategy !== 'none'
            ? <p>Right now {first} is going through a hard stretch{d.coping.stressor ? <> (mostly <b>{pretty(d.coping.stressor)}</b>)</> : null} and is <b>{STRAT[d.coping.strategy]}</b>.</p>
            : <p className="small">{first} isn't in a hard stretch right now.</p>}
          <p className="hint">When strain stays high, people fall back on what their temperament favors and what has worked for them before. Bars: how well each way of coping has worked for {first} so far (learned from their own episodes; 0.5 = untested).</p>
          <div className="cope-learned">
            {Object.entries(d.coping.learned).map(([s, v]: any) => (
              <div key={s} className={`motive ${d.coping.strategy === s ? 'top' : ''}`}><span className="mo-label">{STRAT_SHORT[s]}</span>
                <span className="mo-track"><i className="mo-plain" style={{ width: `${100 * v}%` }} /></span><span className="mo-drive tabular">{n2(v)}</span></div>))}
          </div>
          <div className="small muted" style={{ margin: '6px 0' }}>Tendency to ruminate: {n2(d.coping.rumination)}{adv ? ` · need ${n2(d.coping.need)} · relief ${n2(d.coping.relief)}` : ''}</div>
          <div className="episodes">
            {d.coping.episodes.slice().reverse().slice(0, 6).map((e: any) => (
              <div key={e.id} className="small">{fmtDate(e.date)} · {e.type === 'coping_started'
                ? <>started {STRAT_SHORT[e.strategy]?.toLowerCase() ?? e.strategy}{e.trigger ? <> after <a href={`#/events/${e.trigger.id}`}>{e.trigger.label.toLowerCase()}</a></> : null}</>
                : <>came through it ({e.outcome >= 0.6 ? 'it helped' : e.outcome >= 0.45 ? 'mixed' : 'it did not help much'})</>}</div>))}
          </div>
        </div>
      </div>

      <div className="grid g2" style={{ marginTop: 14 }}>
        <div className="card">
          <h3>What {first} learned</h3>
          <p className="hint">Expectations that shifted most over {first}'s time here, and the memories formed while they shifted. Learning is gradual: each experience nudges what they expect next time.</p>
          {d.lessons.length ? d.lessons.map((l: any, k: number) => (
            <div key={k} className="lesson">
              <div><b>{l.direction === 'up' ? 'Came to expect more' : 'Came to expect less'}</b> about {l.about}: {n2(l.from)} → {n2(l.to)} <span className="small muted">(day {l.start_day} → {l.end_day})</span></div>
              {l.because.length > 0 && <div className="small">Around then: {l.because.map((e: any, j: number) => <span key={e.id}>{j ? ' · ' : ''}<a href={`#/events/${e.id}`}>{e.label.toLowerCase()}</a></span>)}</div>}
            </div>)) : <div className="small muted">Nothing has shifted much yet — let time run.</div>}
        </div>
        <div className="card">
          <h3>{first}'s week</h3>
          <p className="hint">Free time settles into routines: the same thing in the same slot week after week becomes habit (darker = more automatic). Class, work, church and dates are fixed commitments on top of this.</p>
          <table className="routine"><thead><tr><th />{DAYS.map(x => <th key={x}>{x}</th>)}</tr></thead>
            <tbody>{BLOCKS.map(b => (
              <tr key={b}><th className="small">{b}</th>{DAYS.map(day => {
                const s = d.routine.find((x: any) => x.day === day && x.block === b)
                return <td key={day} title={s ? `${s.activity} · habit ${n2(s.strength)}` : 'no routine'} style={{ background: s ? `color-mix(in srgb, var(--s3) ${Math.round(15 + 70 * s.strength)}%, var(--surface-1))` : undefined }}>{s ? s.activity.split(' ')[0] : ''}</td>
              })}</tr>))}</tbody></table>
          <div className="small muted" style={{ marginTop: 6 }}>How settled: {n2(d.routine_strength)}</div>
        </div>
      </div>

      <div className="card" style={{ marginTop: 14 }}>
        <h3>How {first} changed the world around them</h3>
        <div className="kpis compact footprint">
          <div className="kpi"><span className="k-label">People introduced to each other</span><span className="k-val tabular">{d.footprint.introductions}</span><span className="k-sub">{d.footprint.introductions_became_friends} became friends</span></div>
          <div className="kpi"><span className="k-label">Get-togethers hosted</span><span className="k-val tabular">{d.footprint.gatherings_hosted}</span></div>
          <div className="kpi"><span className="k-label">Friendships made here</span><span className="k-val tabular">{d.footprint.friends_made_here}</span></div>
          <div className="kpi"><span className="k-label">People they've supported or leaned on</span><span className="k-val tabular">{d.footprint.ties_with_support}</span></div>
          <div className="kpi click" onClick={() => setRoute(['explore', 'home_social_culture'])}><span className="k-label">Their apartment's social culture</span><span className="k-val tabular">{d.home_culture.sociability_z === null ? '—' : `${d.home_culture.sociability_z >= 0 ? '+' : ''}${n2(d.home_culture.sociability_z)} sd`}</span><span className="k-sub">vs other apartments</span></div>
          <div className="kpi click" onClick={() => setRoute(['explore', 'home_faith_culture'])}><span className="k-label">Their complex's observance</span><span className="k-val tabular">{n2(d.home_culture.observance)}</span></div>
        </div>
      </div>
    </div>
  )
}
