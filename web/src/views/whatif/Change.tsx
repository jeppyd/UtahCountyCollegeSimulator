// "Change the world": pick ideas, pull levers, or change a group of people; then split the world (or add
// to the What-if world that already exists) and run. Used by the drawer (anywhere) and the What-if page.
import { useEffect, useMemo, useState } from 'react'
import { api, STATIC } from '../../api'
import { fmt } from '../../analysis'
import { condLabel, VarPicker } from '../../components'
import { G } from '../../game'
import { timeCtl } from '../../hud'
import { useStore } from '../../store'

export const THEMES: [string, string[]][] = [
  ['Money & housing', ['rent_up_20', 'tuition_up_20', 'construction_30', 'recession', 'contracted_housing_removed', 'contracted_housing_all_years', 'transit_improved', 'enrollment_up_20']],
  ['Dating & marriage', ['new_dating_app', 'women_ask_more', 'marriage_norm_weaker', 'new_dance_hall']],
  ['Faith & culture', ['coffee_permitted', 'church_attendance_decline', 'mission_participation_minus_15', 'missionary_outreach', 'interfaith_welcome', 'pickleball_craze', 'stronger_peer_influence']],
  ['Weather', ['warmer_plus_5f']],
]

type Lever = { target: string; label: string; group: string; kind: 'mul' | 'set' | 'add' | 'bool'; min?: number; max?: number; step?: number; unit?: string; hint: string }
const LEVERS: Lever[] = [
  { target: 'rent_shock', label: 'Rent', group: 'Money & housing', kind: 'mul', min: 0.6, max: 1.6, step: 0.05, hint: 'Market rents for every unit' },
  { target: 'tuition_byu', label: 'BYU tuition', group: 'Money & housing', kind: 'mul', min: 0.5, max: 2, step: 0.05, hint: 'Per-semester tuition at BYU' },
  { target: 'tuition_uvu', label: 'UVU tuition', group: 'Money & housing', kind: 'mul', min: 0.5, max: 2, step: 0.05, hint: 'Per-semester tuition at UVU' },
  { target: 'wage_index', label: 'Wages', group: 'Money & housing', kind: 'mul', min: 0.7, max: 1.5, step: 0.05, hint: 'Pay for student and local jobs' },
  { target: 'unemployment', label: 'Unemployment rate', group: 'Money & housing', kind: 'set', min: 0.01, max: 0.15, step: 0.005, unit: '%', hint: 'Share of job seekers who cannot find work' },
  { target: 'housing_supply_index', label: 'Housing supply', group: 'Money & housing', kind: 'mul', min: 0.7, max: 1.6, step: 0.05, hint: 'Near-campus apartments available' },
  { target: 'enrollment_index', label: 'Incoming students', group: 'Money & housing', kind: 'mul', min: 0.6, max: 1.6, step: 0.05, hint: 'Size of each new class of students' },
  { target: 'transit_quality', label: 'Transit quality', group: 'Money & housing', kind: 'mul', min: 0.5, max: 2, step: 0.1, hint: 'UVX and FrontRunner service' },
  { target: 'app_appeal', label: 'Dating-app appeal', group: 'Dating & social life', kind: 'mul', min: 0.3, max: 2.5, step: 0.1, hint: 'How many people use apps and how much' },
  { target: 'men_initiate_norm', label: 'Expectation that men ask', group: 'Dating & social life', kind: 'mul', min: 0.2, max: 1.8, step: 0.1, hint: 'Lower it and women ask more often' },
  { target: 'marriage_norm', label: 'Pressure to marry young', group: 'Dating & social life', kind: 'mul', min: 0.3, max: 1.8, step: 0.1, hint: 'Cultural push toward early engagement' },
  { target: 'social_media_intensity', label: 'Social media intensity', group: 'Dating & social life', kind: 'mul', min: 0.3, max: 2, step: 0.1, hint: 'Hours online and comparison effects' },
  { target: 'church_attendance_norm', label: 'Church attendance norm', group: 'Faith', kind: 'mul', min: 0.5, max: 1.5, step: 0.05, hint: 'How expected weekly attendance is' },
  { target: 'mission_norm', label: 'Mission participation', group: 'Faith', kind: 'mul', min: 0.3, max: 1.6, step: 0.05, hint: 'How likely young members are to leave on missions' },
  { target: 'interfaith_welcome', label: 'Interfaith welcome', group: 'Faith', kind: 'set', min: 0, max: 1, step: 0.1, hint: 'How actively campuses and wards welcome people of other faiths' },
  { target: 'coffee_permitted', label: 'Coffee permitted by the church', group: 'Faith', kind: 'bool', hint: 'A hypothetical change to the Word of Wisdom norm' },
  { target: 'contracted_housing_required', label: 'BYU contracted-housing rule', group: 'Rules & weather', kind: 'bool', hint: 'Single first-year BYU students must live in approved housing' },
  { target: 'contracted_housing_all_years', label: 'Contracted housing for all years', group: 'Rules & weather', kind: 'bool', hint: 'The pre-2022 rule: every single undergraduate' },
  { target: 'temp_delta', label: 'Temperature', group: 'Rules & weather', kind: 'add', min: -10, max: 10, step: 1, unit: '°F', hint: 'Shift every daily high' },
]
const DURATIONS: [number, string][] = [[0, 'just split'], [7, '1 week'], [30, '1 month'], [112, '1 semester'], [365, '1 year']]

type Q = { key: string; name: string; spec: any }
type Saved = { name: string; queue: Q[]; days: number }
const SAVED_KEY = 'ucsim-saved-experiments-v2'
const loadSaved = (): Saved[] => { try { return JSON.parse(localStorage.getItem(SAVED_KEY) ?? '[]') } catch { return [] } }
const storeSaved = (s: Saved[]) => { try { localStorage.setItem(SAVED_KEY, JSON.stringify(s)) } catch { /* private mode */ } }

function leverName(l: Lever, v: number | boolean) {
  if (l.kind === 'bool') return `${l.label}: ${v ? 'yes' : 'no'}`
  if (l.kind === 'mul') { const p = Math.round(((v as number) - 1) * 100); return `${l.label} ${p >= 0 ? '+' : '−'}${Math.abs(p)}%` }
  if (l.kind === 'add') return `${l.label} ${(v as number) >= 0 ? '+' : '−'}${Math.abs(v as number)}${l.unit ?? ''}`
  return `${l.label} = ${l.unit === '%' ? `${((v as number) * 100).toFixed(1)}%` : fmt(v as number, 2)}`
}

export function ChangeBuilder({ preset, onDone, inline = false }: { preset?: string; onDone?: () => void; inline?: boolean }) {
  const { presets, status, refreshStatus, setRoute, setLens, mode, registry } = useStore()
  const hasAlt = !!status.has_alt
  const [tab, setTab] = useState<'ideas' | 'levers' | 'people'>('ideas')
  const [queue, setQueue] = useState<Q[]>(() => (preset && presets?.[preset] ? [{ key: `p:${preset}`, name: presets[preset].name, spec: { preset } }] : []))
  const [days, setDays] = useState(30)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const [saved, setSaved] = useState<Saved[]>(loadSaved)
  useEffect(() => { if (preset && presets?.[preset] && !queue.some(q => q.key === `p:${preset}`)) setQueue(q => [...q, { key: `p:${preset}`, name: presets[preset].name, spec: { preset } }]) }, [preset])
  const togglePreset = (id: string) => setQueue(queue.some(q => q.key === `p:${id}`) ? queue.filter(q => q.key !== `p:${id}`) : [...queue, { key: `p:${id}`, name: presets[id].name, spec: { preset: id } }])
  const setLever = (l: Lever, v: number | boolean | null) => {
    const key = `l:${l.target}`
    const rest = queue.filter(q => q.key !== key)
    if (v === null) { setQueue(rest); return }
    const op = l.kind === 'bool' ? 'set' : l.kind
    setQueue([...rest, { key, name: leverName(l, v), spec: { target_type: 'world', target: l.target, op, value: v, name: leverName(l, v) } }])
  }
  const run = async (how: 'split' | 'add') => {
    setBusy(true); setErr('')
    try {
      const specs = queue.map(q => q.spec)
      // if time is running, pause it first so the split happens on a finished day and the new run can start
      if (useStore.getState().status?.job?.state === 'running') { await api.cancel(); await timeCtl.waitIdle() }
      if (how === 'add') await api.forkAdd(specs)
      else await api.fork(specs)
      setQueue([])
      await refreshStatus()
      setLens('compare')
      setRoute(['whatif'])
      if (days > 0) await timeCtl.step({ days })
      onDone?.()
    } catch (e: any) { setErr(String(e.message ?? e)) }
    setBusy(false)
  }
  const keep = (s: Saved[]) => { setSaved(s); storeSaved(s) }
  const listed = new Set(THEMES.flatMap(t => t[1]))
  const others = Object.keys(presets ?? {}).filter(k => !listed.has(k))
  const groups = [...new Set(LEVERS.map(l => l.group))]
  return (
    <div className={`change ${inline ? 'inline' : ''}`}>
      {saved.length > 0 && (
        <div className="row small" style={{ marginBottom: 10 }}>
          <span className="muted">Saved:</span>
          {saved.map(s => (
            <span key={s.name} className="cond">
              <button style={{ color: 'var(--accent)', fontWeight: 600 }} onClick={() => { setQueue(s.queue); setDays(s.days) }} title="Load these changes">{s.name}</button>
              <button onClick={() => keep(saved.filter(x => x.name !== s.name))} aria-label={`delete ${s.name}`}>×</button>
            </span>
          ))}
        </div>
      )}
      <div className="tabs">
        <button className={tab === 'ideas' ? 'on' : ''} onClick={() => setTab('ideas')}>{G.spark} Ideas</button>
        <button className={tab === 'levers' ? 'on' : ''} onClick={() => setTab('levers')}>{G.gear} Levers</button>
        <button className={tab === 'people' ? 'on' : ''} onClick={() => setTab('people')}>{G.people} People & rules</button>
      </div>
      {tab === 'ideas' && (
        <div className="change-body">
          {[...THEMES, ...(others.length ? [['Other', others] as [string, string[]]] : [])].map(([theme, ids]) => (
            <div key={theme} className="idea-group">
              <div className="ig-title">{theme}</div>
              <div className="ideas">{ids.filter(id => presets?.[id]).map(id => {
                const p = presets[id], on = queue.some(q => q.key === `p:${id}`)
                return (
                  <button key={id} className={`idea ${on ? 'on' : ''}`} onClick={() => togglePreset(id)} disabled={STATIC} aria-pressed={on} title={p.description}>
                    <span className="idea-check">{on ? '✓' : '+'}</span>
                    <span className="idea-text"><b>{p.name}</b><small>{p.description}</small><span className={`conf ${p.confidence}`} title="How defensible the size of this effect is">{p.confidence}</span></span>
                  </button>
                )
              })}</div>
            </div>
          ))}
        </div>
      )}
      {tab === 'levers' && (
        <div className="change-body">
          <p className="small muted" style={{ marginTop: 0 }}>Move a lever and it joins your change. People respond through the model's rules; how sure we are about each response is shown in the Rules and Cause & effect pages.</p>
          {groups.map(g => (
            <div key={g} className="idea-group">
              <div className="ig-title">{g}</div>
              {LEVERS.filter(l => l.group === g).map(l => <LeverRow key={l.target} l={l} now={status.env?.[l.target]} q={queue.find(q => q.key === `l:${l.target}`)} onChange={v => setLever(l, v)} desc={registry?.variables[l.target]?.desc} />)}
            </div>
          ))}
        </div>
      )}
      {tab === 'people' && <PeopleChange onAdd={q => setQueue([...queue, q])} advanced={mode === 'advanced'} />}
      <div className="change-foot">
        <div className="cf-queue">
          {queue.length ? queue.map(q => <span key={q.key} className="cond">{q.name}<button onClick={() => setQueue(queue.filter(x => x.key !== q.key))} aria-label="remove">×</button></span>)
            : <span className="small muted">Pick an idea or move a lever.</span>}
        </div>
        <div className="row">
          <span className="small muted">then run</span>
          <div className="seg small-seg">{DURATIONS.map(([d, l]) => <button key={d} className={days === d ? 'on' : ''} onClick={() => setDays(d)}>{l}</button>)}</div>
          <span className="spacer" />
          {queue.length > 0 && <button className="btn small ghost" onClick={() => { const name = queue.map(q => q.name).join(' + ').slice(0, 80); keep([{ name, queue, days }, ...saved.filter(s => s.name !== name)].slice(0, 20)) }} title="Remember this combination">Save</button>}
          {hasAlt && <button className="btn" disabled={!queue.length || busy || STATIC} onClick={() => run('add')} title="Keep the current What-if world and add these changes from today">Add to What-if</button>}
          <button className="btn primary big" disabled={!queue.length || busy || STATIC} onClick={() => run('split')} title={hasAlt ? 'Replace the What-if world with a fresh copy of the Original plus these changes' : 'Copy the world; the copy gets your change'}>
            {busy ? 'Splitting…' : hasAlt ? 'Start a new What-if ▶' : 'Split the world ▶'}
          </button>
        </div>
        {status.day < 14 && !hasAlt && <p className="small muted" style={{ margin: '6px 0 0' }}>Tip: the world is only {status.day} days old; friendships and dating need a few weeks to get going, so effects show more clearly after a couple of weeks.</p>}
        {err && <div className="banner" style={{ marginTop: 8 }}>{err}</div>}
        {STATIC && <p className="small muted" style={{ margin: '6px 0 0' }}>Making changes needs the installed app.</p>}
      </div>
    </div>
  )
}

function LeverRow({ l, now, q, onChange, desc }: { l: Lever; now: any; q?: Q; onChange: (v: number | boolean | null) => void; desc?: string }) {
  const neutral = l.kind === 'mul' ? 1 : l.kind === 'add' ? 0 : l.kind === 'bool' ? !!now : Number(now ?? 0)
  const v = q ? q.spec.value : neutral
  const show = (x: any) => l.kind === 'bool' ? (x ? 'yes' : 'no') : l.kind === 'mul' ? `${x >= 1 ? '+' : '−'}${Math.abs(Math.round((x - 1) * 100))}%` : l.kind === 'add' ? `${x >= 0 ? '+' : '−'}${Math.abs(x)}${l.unit ?? ''}` : l.unit === '%' ? `${(x * 100).toFixed(1)}%` : fmt(x, 2)
  const nowTxt = now === undefined || now === null ? '' : typeof now === 'boolean' ? (now ? 'yes' : 'no') : l.unit === '%' ? `${(now * 100).toFixed(1)}%` : l.target.startsWith('tuition') ? `$${Math.round(now).toLocaleString()}` : l.kind === 'mul' ? `×${Number(now).toFixed(2)}` : l.kind === 'add' ? `${now >= 0 ? '+' : ''}${fmt(now, 1)}${l.unit ?? ''}` : fmt(now, 2)
  return (
    <div className={`lever ${q ? 'moved' : ''}`} title={desc ?? l.hint}>
      <div className="lv-name"><b>{l.label}</b><small>{l.hint}{nowTxt ? ` · now ${nowTxt}` : ''}</small></div>
      {l.kind === 'bool' ? (
        <div className="seg small-seg">
          <button className={!v ? 'on' : ''} onClick={() => onChange(!!now === false ? null : false)}>no</button>
          <button className={v ? 'on' : ''} onClick={() => onChange(!!now === true ? null : true)}>yes</button>
        </div>
      ) : (
        <input type="range" min={l.min} max={l.max} step={l.step} value={v} disabled={STATIC}
          onChange={e => { const x = Number(e.target.value); onChange(Math.abs(x - (neutral as number)) < 1e-9 ? null : x) }} aria-label={l.label} />
      )}
      <span className="lv-val tabular">{show(v)}</span>
      {q && <button className="btn ghost small" onClick={() => onChange(null)} aria-label="Reset">↺</button>}
    </div>
  )
}

function PeopleChange({ onAdd, advanced }: { onAdd: (q: Q) => void; advanced: boolean }) {
  const { status, cohort, registry } = useStore()
  const [tt, setTt] = useState<'agent' | 'param'>('agent')
  const params = useMemo(() => {
    const out: { key: string; label: string; value: number; ev: string }[] = []
    for (const m of Object.values(registry!.mechanisms) as any[]) for (const [p, s] of Object.entries(m.params ?? {}) as any) out.push({ key: `${m.id}.${p}`, label: `${m.label} — ${p}`, value: s.value, ev: m.evidence })
    return out.sort((a, b) => a.label.localeCompare(b.label))
  }, [registry])
  const [target, setTarget] = useState('faith_belief')
  const [param, setParam] = useState(params[0]?.key ?? '')
  const [op, setOp] = useState('add')
  const [value, setValue] = useState('0.1')
  const [onlyGroup, setOnlyGroup] = useState(true)
  const spec = registry!.variables[target]
  const add = () => {
    const v = Number(value)
    if (tt === 'agent') {
      const who = onlyGroup && cohort.length ? cohort.map(c => condLabel(c, registry)).join(', ') : 'everyone'
      const name = `${spec?.label ?? target} ${op === 'mul' ? '×' : op === 'add' ? (v >= 0 ? '+' : '') : '='}${value} for ${who}`
      const s: any = { target_type: 'agent', target, op, value: v, start_day: status.day, name }
      if (onlyGroup && cohort.length) s.population = { and: cohort }
      onAdd({ key: `a:${target}:${Date.now()}`, name, spec: s })
    } else {
      const p = params.find(x => x.key === param)
      const name = `Rule: ${p?.label ?? param} ${op === 'mul' ? '×' : op === 'add' ? '+' : '='}${value}`
      onAdd({ key: `r:${param}:${Date.now()}`, name, spec: { target_type: 'param', target: param, op, value: v, name } })
    }
  }
  return (
    <div className="change-body">
      <div className="seg small-seg" style={{ marginBottom: 10 }}>
        <button className={tt === 'agent' ? 'on' : ''} onClick={() => { setTt('agent'); setOp('add') }}>Change people</button>
        <button className={tt === 'param' ? 'on' : ''} onClick={() => { setTt('param'); setOp('mul') }}>Change a rule</button>
      </div>
      {tt === 'agent' ? (
        <>
          <p className="small muted" style={{ marginTop: 0 }}>Nudge something about a group of people once, today, and watch it ripple: e.g. raise belief for lonely freshmen, or lower stress for UVU students. The group is your current filter (set it on Explore or People).</p>
          <div className="row" style={{ marginBottom: 8 }}>
            <VarPicker value={target} onChange={setTarget} filter={v => !!v.intervenable && v.dtype !== 'cat' && v.dtype !== 'bool'} />
            <select value={op} onChange={e => setOp(e.target.value)}><option value="add">+ add</option><option value="mul">× multiply</option><option value="set">= set to</option></select>
            <input type="text" value={value} onChange={e => setValue(e.target.value)} style={{ width: 70 }} aria-label="Value" />
            {spec?.range && <span className="small muted">range {spec.range[0]}–{spec.range[1]}</span>}
          </div>
          <label className="inline small"><input type="checkbox" checked={onlyGroup} onChange={e => setOnlyGroup(e.target.checked)} />only {cohort.length ? cohort.map(c => condLabel(c, registry)).join(', ') : '(no filter set: everyone)'}</label>
        </>
      ) : (
        <>
          <p className="small muted" style={{ marginTop: 0 }}>Make one of the model's rules stronger or weaker: a sensitivity test. {advanced ? '' : 'Rule names and strengths are listed under Research desk → Rules.'}</p>
          <div className="row" style={{ marginBottom: 8 }}>
            <select value={param} onChange={e => setParam(e.target.value)} style={{ maxWidth: 360 }}>{params.map(p => <option key={p.key} value={p.key}>{p.label} ({fmt(p.value)})</option>)}</select>
            <select value={op} onChange={e => setOp(e.target.value)}><option value="mul">× multiply</option><option value="add">+ add</option><option value="set">= set</option></select>
            <input type="text" value={value} onChange={e => setValue(e.target.value)} style={{ width: 70 }} aria-label="Value" />
          </div>
        </>
      )}
      <button className="btn small" disabled={STATIC} onClick={add}>{G.plus} Add to my change</button>
    </div>
  )
}

/** The drawer version, available from anywhere (HUD "What if…?" button, palette, World page). */
export function ChangeDrawer() {
  const { drawer, openDrawer, status } = useStore()
  if (!drawer) return null
  return (
    <div className="drawer-back" onMouseDown={() => openDrawer(null)}>
      <aside className="drawer2" onMouseDown={e => e.stopPropagation()} role="dialog" aria-label="Change the world">
        <div className="d-head">
          <span className="d-icon">{G.butterfly}</span>
          <div style={{ flex: 1, minWidth: 0 }}>
            <h2>{status.has_alt ? 'Change the What-if world' : 'What if…?'}</h2>
            <p className="small secondary">{status.has_alt
              ? 'Add more changes to the What-if world from today, or start a fresh What-if from the Original.'
              : 'Pick a change. The world splits in two: the Original carries on untouched, the What-if gets your change. Both roll the same dice, so every difference is the butterfly effect of your change.'}</p>
          </div>
          <button className="btn ghost" onClick={() => openDrawer(null)} aria-label="Close">{G.close}</button>
        </div>
        <ChangeBuilder preset={drawer.preset} onDone={() => openDrawer(null)} />
      </aside>
    </div>
  )
}
