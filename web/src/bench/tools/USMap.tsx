// US map: where people's families live. Each state is shaded by how many people here come from it, or by how many of
// them are home there right now — let time run through Thanksgiving or Christmas to watch the exodus and the return.
// Click a state to select its people. With one person selected, their home, family and trips home are shown below.
import { useState } from 'react'
import { famApi } from '../../api'
import { useAsync } from '../../game'
import { Busy, dayWords, Problem, useWorldDays } from '../../kit/Bits'
import { RefChip } from '../../kit/RefChip'
import { useLens, useStore } from '../../store'
import { PanelOptions } from '../panel'
import type { PanelProps, ToolDef } from '../registry'
import { focusItem, subjectPerson } from '../sel'
import '../../kit/talk.css'

const REASON_WORDS: Record<string, string> = { weekend: 'a weekend at home', thanksgiving: 'Thanksgiving', christmas: 'Christmas', wedding: "a sibling's wedding",
  mission: 'a mission farewell or homecoming', illness: 'a parent who was ill', funeral: 'a funeral', baby: 'a new baby in the family' }
const REL_WORDS: Record<string, string> = { mother: 'Mother', father: 'Father', sibling: 'Sibling', grandparent: 'Grandparent' }

function Family({ i, setSel }: { i: number; setSel: PanelProps['setSel'] }) {
  const u = useLens().u
  const v = useStore(s => s.dataVersion)
  const { start } = useWorldDays()
  const d = useAsync(() => famApi.person(i, u), [i, u, v])
  if (!d.data) return null
  const x = d.data
  return (
    <div className="in-sec">
      <div className="ta-who"><RefChip r={{ kind: 'person', id: i, u }} />
        <span>family {x.home_state === 'International' ? 'abroad' : <>in <b>{x.home_state}</b></>}
          {x.home_state !== 'International' ? ` · ${x.drive_hours < 1 ? 'close by' : `${x.drive_hours.toFixed(0)} h by car`}${x.flies ? ' (they fly)' : ''}` : ''}
          {` · ${x.closeness > 0.7 ? 'very close' : x.closeness > 0.45 ? 'close' : 'not very close'} to them`}{x.away ? ` · home now, back ${dayWords(start, x.returns)}` : ''}</span></div>
      <div className="ta-chips" style={{ marginBottom: 6 }}>
        {x.kin.map((k, n) => <span key={n} className="ta-kind">{REL_WORDS[k.rel]} {k.age}{!k.alive ? ' (died)' : k.on_mission ? ' (on a mission)' : k.ill ? ' (ill)' : ''}</span>)}
      </div>
      {x.trips.length === 0 ? <div className="bx-note">No trips home yet.</div> :
        <div className="bk-list">{x.trips.map((t, n) => (
          <div key={n} className="bk-li click" onClick={() => focusItem(setSel, { kind: 'event', id: t.event, u })}>
            <span className="when">{dayWords(start, t.depart)}</span>
            <span className="grow">home for {REASON_WORDS[t.reason] ?? t.reason}, back {dayWords(start, t.return)}{t.fly ? ' · flew' : ''}{t.with_partner !== null ? ' · with their spouse' : ''}</span>
          </div>))}</div>}
    </div>
  )
}

function USMapTool({ sel, setSel, opts, setOpts }: PanelProps) {
  const u = useLens().u
  const v = useStore(s => s.dataVersion)
  const mode: 'from' | 'home' = opts.mode ?? 'from'
  const geo = useAsync(() => famApi.geo(), [])
  const st = useAsync(() => famApi.states(u), [u, v])
  const [hover, setHover] = useState<string | null>(null)
  const who = subjectPerson(sel)
  if (geo.error || st.error) return <Problem error={geo.error || st.error} />
  if (!geo.data || !st.data) return <Busy what="Drawing the map" />
  const by = new Map(st.data.states.map(s => [s.state, s]))
  const val = (name: string) => { const s = by.get(name); return s ? (mode === 'from' ? s.from : s.at_home) : 0 }
  const max = Math.max(1, ...geo.data.states.map(s => val(s.name)))
  const intl = by.get('International')
  const h = hover ? by.get(hover) : null
  const pick = (name: string) => famApi.state(name, u, mode === 'home' ? 'home' : 'all').then(r => setSel({ people: r.people, item: undefined }))
  return (
    <div className="bk">
      <PanelOptions>
        <select value={mode} onChange={e => setOpts({ ...opts, mode: e.target.value })}>
          <option value="from">Where people are from</option><option value="home">Who is home right now</option>
        </select>
      </PanelOptions>
      <div className="bx-note">{st.data.date}: {st.data.away.toLocaleString()} of {st.data.total.toLocaleString()} people are home with family right now
        {intl ? ` · ${intl.from} from abroad` : ''}. Click a state to select its people.</div>
      <svg viewBox={`0 0 ${geo.data.width} ${geo.data.height}`} className="us-map" role="img" aria-label="Map of the United States">
        {geo.data.states.map(s => {
          const x = val(s.name)
          const t = x ? Math.sqrt(x / max) : 0
          return (
            <path key={s.abbr} d={s.d} className={`us-st ${hover === s.name ? 'on' : ''} ${x ? 'has' : ''}`} style={{ fillOpacity: x ? 0.12 + 0.88 * t : 1 }}
              onMouseEnter={() => setHover(s.name)} onMouseLeave={() => setHover(null)} onClick={() => x && pick(s.name)}>
              <title>{s.name}</title>
            </path>
          )
        })}
        {geo.data.states.filter(s => val(s.name) >= max * 0.08).map(s => (
          <text key={s.abbr} x={s.cx} y={s.cy} className="us-lab">{val(s.name).toLocaleString()}</text>
        ))}
      </svg>
      <div className="bx-note" style={{ minHeight: 18 }}>{h ? `${h.state}: ${h.from.toLocaleString()} people from here · ${h.in_provo.toLocaleString()} in Provo–Orem now · ${h.at_home.toLocaleString()} home there now` : hover ? `${hover}: nobody from here` : ' '}</div>
      {who !== null && <Family i={who} setSel={setSel} />}
      <div className="ta-foot">State outlines: US Census Bureau (public domain), via us-atlas.</div>
    </div>
  )
}

export const tool: ToolDef = {
  id: 'usmap',
  label: 'US map',
  icon: 'globe',
  hint: 'Where families live, state by state, and who is home right now (watch Thanksgiving and Christmas); a selected person’s family and trips home.',
  group: 'places',
  order: 50,
  component: USMapTool,
  size: { w: 6, h: 8 },
}
