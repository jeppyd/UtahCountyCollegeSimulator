// Place: one place as a whole — an apartment complex, a ward, a workplace, a school or a venue (a café, a park, a dance
// hall): who lives or goes there, what they're like, its culture over time and what happens there. It shows the
// focused place, else the ward of the selected person.
import { api, benchApi } from '../../api'
import { fval } from '../../fields'
import { Spark, useAsync } from '../../game'
import { Busy, dayWords, Empty, Problem, useWorldDays } from '../../kit/Bits'
import { RefChip } from '../../kit/RefChip'
import { useLens, useStore } from '../../store'
import type { PanelProps, ToolDef } from '../registry'
import type { Ref } from '../selection'
import { focusItem, subjectPerson } from '../sel'

const KIND_WORD: Record<string, string> = { complex: 'Apartment complex', ward: 'Ward', employer: 'Workplace', school: 'School', unit: 'Home', venue: 'Venue' }
const COMPOSITION = ['rel_status', 'activity', 'school', 'role', 'sex']
const STATS = ['age', 'mood', 'loneliness', 'belonging', 'faith_belief', 'n_friends', 'dates_30d']

/** "ward:3" → ['ward', 3] */
function parsePlace(r: Ref | undefined): [string, number] | null {
  if (!r || (r.kind !== 'place' && r.kind !== 'institution')) return null
  const m = /^([a-z_]+):(\d+)$/.exec(String(r.id))
  return m ? [m[1], Number(m[2])] : null
}

function Bars({ counts, total }: { counts: Record<string, number>; total: number }) {
  const rows = Object.entries(counts).sort((a, b) => b[1] - a[1]).slice(0, 6)
  return (
    <div className="bk-bars">
      {rows.map(([k, n]) => (
        <div key={k} className="bk-bar"><span>{k.replace(/_/g, ' ')}</span><span className="t"><i style={{ width: `${(n / (total || 1)) * 100}%` }} /></span><span>{Math.round((n / (total || 1)) * 100)}%</span></div>
      ))}
    </div>
  )
}

function PlaceTool({ sel, setSel }: PanelProps) {
  const u = useLens().u
  const dataVersion = useStore(s => s.dataVersion)
  const reg = useStore(s => s.registry)!
  const { start } = useWorldDays()
  const who = subjectPerson(sel)
  const focused = parsePlace(sel.item)

  const data = useAsync(async () => {
    let p = focused
    if (!p && who !== null) { const per = await api.person(who, u); if (per?.ward?.id !== undefined) p = ['ward', per.ward.id] }
    if (!p) return null
    const [kind, id] = p
    return { kind, id, d: kind === 'venue' ? await benchApi.venue(id, u) : await api.institution(kind, id, u) }
  }, [focused?.join(':'), who, u, dataVersion], { key: `bench-place:${u}:${focused?.join(':')}:${who}` })

  if (!focused && who === null) return <Empty title="No place chosen">Click a place anywhere on the bench, or select a person to see their ward.</Empty>
  if (data.error && !data.data) return <Problem error={data.error} />
  if (!data.data) return data.loading ? <Busy what="Reading the place" /> : <Empty title="No place to show">This person has no ward on record.</Empty>
  const { kind, id, d } = data.data
  const me: Ref = { kind: 'place', id: `${kind}:${id}`, label: d.name, u }

  if (kind === 'venue') return (
    <div className="bk">
      <div className="bk-title"><h4>{d.name}</h4><span className="bk-pill">{String(d.vtype).replace(/_/g, ' ')}</span></div>
      <div className="bk-facts"><span><b>{d.n_occasions.toLocaleString()}</b> occasions held here</span><span><b>{d.n_events.toLocaleString()}</b> events recorded here</span></div>
      <div className="bx-note">{d.note}</div>
      {d.event_counts.length > 0 && <><div className="bx-h">What happens here</div><Bars counts={Object.fromEntries(d.event_counts.map((r: any) => [r.label, r.count]))} total={d.n_events} /></>}
      {d.occasions.length > 0 && <div className="bx-h">Recent occasions</div>}
      <div className="bk-list">
        {d.occasions.slice(0, 20).map((o: any) => (
          <div key={o.id} className="bk-li click" onClick={() => focusItem(setSel, { kind: 'occasion', id: o.id, label: o.label ?? o.kind, u })}>
            <span className="when">{dayWords(start, o.day)}</span>
            <span className="grow"><RefChip r={{ kind: 'occasion', id: o.id, label: o.label ?? o.kind, u }} plain />{o.n_attended !== undefined && <span className="bk-pill">{o.n_attended} came</span>}</span>
          </div>
        ))}
      </div>
      {d.events.length > 0 && <div className="bx-h">Recent events here</div>}
      <div className="bk-list">
        {d.events.slice(0, 20).map((e: any) => (
          <div key={e.id} className="bk-li click" onClick={() => focusItem(setSel, { kind: 'event', id: e.id, label: e.label, u })}>
            <span className="when">{dayWords(start, e.day)}</span>
            <span className="grow"><RefChip r={{ kind: 'event', id: e.id, label: e.label, u }} plain /><RefChip r={{ kind: 'person', id: e.a, label: e.a_name, u }} />{e.b !== null && <RefChip r={{ kind: 'person', id: e.b, label: e.b_name, u }} />}</span>
          </div>
        ))}
      </div>
    </div>
  )

  const total = Object.values(d.composition?.sex ?? {}).reduce((s: number, x: any) => s + x, 0) as number || d.n
  const hist: any[] = d.culture?.history ?? []
  const cultureKeys = Object.keys(d.culture ?? {}).filter(k => typeof d.culture[k] === 'number' && !k.endsWith('_z') && !k.endsWith('_vs_average'))
  return (
    <div className="bk">
      <div className="bk-title">
        <h4>{d.name}</h4><span className="bk-pill">{KIND_WORD[kind] ?? kind}</span>
        {!focused && <span className="bx-note">the ward of the selected person</span>}
        {!focused && <button className="bk-more" onClick={() => focusItem(setSel, me)}>keep showing this place</button>}
      </div>
      <div className="bk-facts">
        <span><b>{d.n.toLocaleString()}</b> {kind === 'complex' || kind === 'unit' ? 'living here' : 'members'}</span>
        {d.friend_ties_inside !== undefined && <span><b>{d.friend_ties_inside.toLocaleString()}</b> friendships inside</span>}
        {STATS.filter(s => d.stats?.[s] !== null && d.stats?.[s] !== undefined && reg.variables[s]).map(s => (
          <span key={s} title={reg.variables[s].desc}>{reg.variables[s].label}: <b>{fval(reg.variables[s], d.stats[s])}</b></span>
        ))}
      </div>
      {d.n === 0 && <div className="bx-note">Nobody lives or goes here right now.</div>}
      {cultureKeys.length > 0 && (
        <>
          <div className="bx-h">Culture</div>
          <div className="bk-facts">
            {cultureKeys.map(k => (
              <span key={k}>{k.replace(/_/g, ' ')}: <b>{d.culture[k].toFixed(2)}</b>
                {hist.length > 1 && hist[0][k] !== undefined && <Spark a={hist.map(h => h[k])} width={60} height={16} />}</span>
            ))}
          </div>
          <div className="bx-note">Culture numbers run 0 to 1 (higher = more of it); the small lines show how it changed.</div>
        </>
      )}
      {d.n > 0 && COMPOSITION.filter(c => d.composition?.[c] && Object.keys(d.composition[c]).length).map(c => (
        <div key={c}><div className="bx-h">{reg.variables[c]?.label ?? c}</div><Bars counts={d.composition[c]} total={total} /></div>
      ))}
      {d.recent_events?.length > 0 && (
        <>
          <div className="bx-h">What happens to people here (recent)</div>
          <Bars counts={Object.fromEntries(d.recent_events.slice(0, 6).map((r: any) => [r.label, r.count]))} total={Math.max(...d.recent_events.map((r: any) => r.count))} />
        </>
      )}
      {d.members?.length > 0 && (
        <>
          <div className="bx-h">People here</div>
          <div className="bk-chips">
            {d.members.slice(0, 40).map((m: any) => <RefChip key={m.id} r={{ kind: 'person', id: m.id, label: m.name, u }} />)}
            {d.members.length > 40 && <span className="bx-note">and {(d.members.length - 40).toLocaleString()} more</span>}
          </div>
          <button className="bk-more" onClick={() => setSel({ people: d.members.map((m: any) => m.id) })}>Select everyone here</button>
        </>
      )}
    </div>
  )
}

export const tool: ToolDef = {
  id: 'place',
  label: 'Place',
  icon: 'places',
  hint: 'A complex, ward, workplace or venue as a whole: who is there, what they are like, its culture and what happens there.',
  group: 'places',
  order: 10,
  component: PlaceTool,
  size: { w: 4, h: 7 },
}
