// What-if: change the world, let both universes run, and follow the butterfly effect — which fields moved,
// which events became more or less common, whose lives diverged, which couples and places changed, and why.
import { useMemo, useState } from 'react'
import { api, STATIC } from '../../api'
import { axisStyle, cssVar, Decomposition, EChart, Evidence, tokens, VarPicker } from '../../components'
import { browsable, catalog, DRAWERS, drawerOf, fdelta, fpair, fval, pctStr, polarity, pretty, sizeWord } from '../../fields'
import { CatIcon, DeltaChip, G, Spark, UBadge, uColor, useAsync, whatifKey } from '../../game'
import { timeCtl } from '../../hud'
import { useStore } from '../../store'
import { ChangeBuilder } from './Change'

const TABS = [['overview', 'Overview', 'butterfly'], ['fields', 'All fields', 'explore'], ['events', 'Events', 'events'], ['lives', 'Lives', 'people'],
  ['relationships', 'Relationships', 'rings'], ['places', 'Places', 'places'], ['why', 'Why', 'link']] as const
const STATES = ['loneliness', 'mood', 'stress', 'belonging', 'romantic_longing', 'financial_stress', 'academic_pressure', 'guilt', 'self_esteem', 'purpose', 'fatigue', 'anxiety']

export default function WhatIf({ tab, preset }: { tab?: string; preset?: string }) {
  const { status } = useStore()
  if (!status.has_alt) return <Setup preset={preset ?? (tab && tab !== 'overview' ? tab : undefined)} />
  return <Butterfly tab={tab ?? 'overview'} />
}

function Setup({ preset }: { preset?: string }) {
  return (
    <div className="page">
      <div className="whatif-hero">
        <div className="wh-wings">{G.butterfly}</div>
        <div>
          <div className="eyebrow">What if…?</div>
          <h1>Change one thing. Watch two worlds drift apart.</h1>
          <p>Pick a change below. The world splits in two: the <UBadge u="base" /> world carries on untouched, the <UBadge u="alt" /> world gets your change. Both roll exactly the same dice, so every difference you see — a different roommate, a first date that never happened, a wedding moved up a year — is the butterfly effect of your change.</p>
        </div>
      </div>
      <ChangeBuilder preset={preset} inline />
    </div>
  )
}

function Butterfly({ tab }: { tab: string }) {
  const { status, dataVersion, setRoute, openDrawer, refreshStatus, presets } = useStore()
  const c = useAsync(() => api.compare(), [dataVersion], { key: whatifKey(status, 'compare') })
  const f = useAsync(() => api.compareFields(), [dataVersion], { key: whatifKey(status, 'fields') })
  const running = status.job?.state === 'running'
  const since = status.day - (status.fork_day ?? status.day)
  const d = status.divergence?.any_state_diff ?? 0
  const names = [...new Set<string>((status.alt_interventions ?? []).map((i: any) => i.name ?? presets?.[i.id]?.name ?? i.id ?? `${i.target} ${i.op} ${i.value}`))]
  const forkDate = new Date(status.date + 'T12:00:00'); forkDate.setDate(forkDate.getDate() - since)
  return (
    <div className="page">
      <div className="bf-head">
        <div className="bf-wings" style={{ ['--d' as any]: Math.min(1, Math.sqrt(d)) }}>{G.butterfly}</div>
        <div className="bf-title">
          <div className="eyebrow">The butterfly effect · split {forkDate.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })} · {since} days ago</div>
          <h1>{names.length ? names.join(' + ') : 'Your change'}</h1>
          <div className="row" style={{ marginTop: 6 }}>
            <span className="bf-pct"><b className="tabular">{(100 * d).toFixed(d < 0.1 ? 1 : 0)}%</b> of lives differ</span>
            <span className="small muted">· {(f.data as any)?.n?.toLocaleString() ?? '…'} people in both worlds</span>
          </div>
        </div>
        <div className="bf-actions">
          {!STATIC && <>
            {running ? <button className="btn" onClick={() => timeCtl.pause()}>{G.pause} Pause</button> : <>
              <button className="btn" onClick={() => timeCtl.step({ days: 7 })}>Run 1 week</button>
              <button className="btn" onClick={() => timeCtl.step({ days: 30 })}>Run 1 month</button>
              <button className="btn" onClick={() => timeCtl.step({ days: 112 })}>Run 1 semester</button>
            </>}
            <button className="btn" onClick={() => openDrawer({})}>{G.plus} Change more</button>
            <button className="btn ghost" onClick={async () => { if (confirm('Discard the What-if world and go back to one world?')) { await api.unfork(); await refreshStatus() } }}>End experiment</button>
          </>}
        </div>
      </div>
      <div className="tabs" style={{ marginBottom: 14 }}>
        {TABS.map(([k, l, i]) => <button key={k} className={tab === k ? 'on' : ''} onClick={() => setRoute(['whatif', k])}>{G[i]} {l}</button>)}
      </div>
      {running && <div className="banner live-dot">Both worlds are running ({status.job?.total >= 3000 ? `+${status.job?.progress ?? 0} days` : `day ${status.job?.progress ?? 0} of ${status.job?.total}`}). These comparisons refresh every few seconds as they go.</div>}
      {since > 0 && d === 0 && <div className="banner">No lives differ yet. Some changes only act on a schedule: rent and bills are settled on the 1st of the month, tuition at the start of a term, moves when leases end. Until your change touches someone, the two worlds stay identical.</div>}
      {!running && since === 0 && <div className="banner">The worlds have only just split. Run time forward (▶ in the top bar, or the buttons above) and watch them drift apart.</div>}
      {tab === 'overview' && <Overview c={c.data} f={f.data} cErr={c.error} />}
      {tab === 'fields' && <AllFields f={f.data} err={f.error} />}
      {tab === 'events' && <EventsDiff c={c.data} err={c.error} />}
      {tab === 'lives' && <Lives />}
      {tab === 'relationships' && <Rel />}
      {tab === 'places' && <PlacesDiff />}
      {tab === 'why' && <Why c={c.data} err={c.error} />}
    </div>
  )
}

// ------------------------------------------------------------------ overview
function Overview({ c, f, cErr }: { c: any; f: any; cErr: string }) {
  const { status, dataVersion, registry, setRoute } = useStore()
  const ppl = useAsync(() => api.comparePeople(6), [dataVersion], { key: whatifKey(status, 'people6') })
  const rel = useAsync(() => api.compareRelationships(), [dataVersion], { key: whatifKey(status, 'relationships') })
  const divOpt = useMemo(() => {
    if (!c?.divergence?.length) return null
    const ax = axisStyle(), t = tokens()
    const start = new Date(status.date + 'T12:00:00'); start.setDate(start.getDate() - status.day)
    const toDate = (day: number) => { const x = new Date(start); x.setDate(x.getDate() + day); return x.toISOString().slice(0, 10) }
    const keys: [string, string, string][] = [['any_state_diff', 'Lives that differ', '--u-alt'], ['friendship_jaccard_distance', 'Friendships that differ', '--s3'], ['diff_rel_status', 'Different relationship status', '--s5'], ['diff_unit_id', 'Living somewhere else', '--s1']]
    return {
      grid: { left: 8, right: 16, top: 30, bottom: 4, containLabel: true }, legend: { top: 0, textStyle: { color: t.text2, fontSize: 11 } },
      tooltip: { trigger: 'axis', valueFormatter: (v: number) => pctStr(v) },
      xAxis: { type: 'time', ...ax, splitLine: { show: false } },
      yAxis: { type: 'value', ...ax, axisLabel: { ...ax.axisLabel, formatter: (v: number) => `${Math.round(100 * v)}%` } },
      series: keys.map(([k, l, col], j) => ({ name: l, type: 'line', showSymbol: false, smooth: 0.2, lineStyle: { width: j === 0 ? 3 : 1.8, color: cssVar(col) }, itemStyle: { color: cssVar(col) }, areaStyle: j === 0 ? { color: cssVar(col), opacity: 0.08 } : undefined, data: c.divergence.map((x: any) => [toDate(x.day), x[k]]) })),
    }
  }, [c])
  const top = useMemo(() => f ? Object.entries(f.fields).map(([id, r]: any) => ({ id, ...r })).filter(r => registry!.variables[r.id]).sort((a: any, b: any) => Math.abs(b.effect) - Math.abs(a.effect)).slice(0, 8) : [], [f])
  const evs = (c?.events ?? []).filter((e: any) => e.base + e.alt >= 8 && Math.abs(e.rel) >= 0.05 && e.type !== 'intervention_exposure').slice(0, 7)
  const r: any = rel.data
  return (
    <>
      <PlansCard />
      <div className="grid" style={{ gridTemplateColumns: 'minmax(0, 3fr) minmax(0, 2fr)' }}>
        <div className="card">
          <h3>How far apart the worlds have drifted</h3>
          <p className="hint">Share of people whose life differs between the worlds, day by day. Small differences spread: a missed first date changes who meets whom next.</p>
          {divOpt ? <EChart option={divOpt} height={240} /> : <div className="empty small">{c ? 'Run time forward to see the worlds drift apart.' : cErr || 'Loading the comparison…'}</div>}
        </div>
        <div className="card">
          <div className="card-head"><div><h3>Lives that changed most</h3><p className="hint">Same person, two lives. Open one to see where their roads forked.</p></div><button className="btn small" onClick={() => setRoute(['whatif', 'lives'])}>All</button></div>
          {ppl.data ? ((ppl.data as any).people.length ? (ppl.data as any).people.slice(0, 6).map((p: any) => <LifeRow key={p.id} p={p} />) : <div className="empty small">No lives differ yet.</div>) : <div className="empty small">{ppl.error || 'Finding them…'}</div>}
        </div>
      </div>
      <div className="section-title"><h2>What changed most</h2><button className="btn small" onClick={() => setRoute(['whatif', 'fields'])}>Scan every field →</button></div>
      <div className="grid g4">
        {top.map((r: any) => <ChangeCard key={r.id} r={r} />)}
      </div>
      <div className="grid g2" style={{ marginTop: 14 }}>
        <div className="card">
          <div className="card-head"><div><h3>Things that happened more or less often</h3><p className="hint">Life events since the split.</p></div><button className="btn small" onClick={() => setRoute(['whatif', 'events'])}>All</button></div>
          {evs.length === 0 && <div className="empty small">{c ? 'No clear differences yet. Run longer.' : cErr || 'Counting…'}</div>}
          {evs.map((e: any) => <EventDiffRow key={e.type} e={e} />)}
        </div>
        <div className="card">
          <div className="card-head"><div><h3>Love and friendship, rewritten</h3><p className="hint">Couples and friendships that exist in only one of the two worlds.</p></div><button className="btn small" onClick={() => setRoute(['whatif', 'relationships'])}>Details</button></div>
          {r ? (
            <div className="kpis">
              <div className="kpi"><span className="k-label"><UBadge u="alt" /> new couples</span><span className="k-val tabular">{r.couples.only_alt}</span><span className="k-sub">only in the What-if</span></div>
              <div className="kpi"><span className="k-label"><UBadge u="base" /> lost couples</span><span className="k-val tabular">{r.couples.only_base}</span><span className="k-sub">only in the Original</span></div>
              <div className="kpi"><span className="k-label">Same couple, other stage</span><span className="k-val tabular">{r.couples.changed_status}</span><span className="k-sub">e.g. engaged vs dating</span></div>
              <div className="kpi"><span className="k-label">Friendships that differ</span><span className="k-val tabular">{(r.friendships.only_alt + r.friendships.only_base).toLocaleString()}</span><span className="k-sub">{r.friendships.only_alt.toLocaleString()} new · {r.friendships.only_base.toLocaleString()} never formed</span></div>
            </div>
          ) : <div className="empty small">{rel.error || 'Counting…'}</div>}
        </div>
      </div>
    </>
  )
}

// The plain-language What-ifs behind this world: what was asked, what the model predicted, and how it's going.
function PlansCard() {
  const { status, dataVersion, setRoute } = useStore()
  const pl = useAsync(() => api.whatifPlans(), [dataVersion], { key: whatifKey(status, 'plans') })
  const plans: any[] = (pl.data as any) ?? []
  if (!plans.length) return null
  const STATUS: Record<string, [string, string]> = { 'as predicted': ['ok', '✓ as predicted'], opposite: ['bad', '✕ the opposite'], 'too early': ['wait', '… too early to tell'], moved: ['ok', '✓ moved'] }
  return (
    <div className="card plans-card">
      {plans.map(p => (
        <div key={p.plan_id} className="pl-one">
          <div className="card-head"><div>
            <div className="eyebrow">{G.mind} Your What-if{p.applied_day != null ? ` · from day ${p.applied_day}` : ''}</div>
            <h3 style={{ margin: '2px 0' }}>{p.title}</h3>
            {p.request && <p className="small secondary" style={{ margin: 0 }}>“{p.request}”</p>}
          </div></div>
          <div className="grid g2" style={{ marginTop: 8 }}>
            <div>
              <b className="small">Its predictions vs. the simulation</b>
              {p.expectations?.length ? <ul className="pl-exp">{p.expectations.map((e: any, i: number) => {
                const [cls, txt] = e.status ? STATUS[e.status] ?? ['wait', e.status] : ['wait', 'not measurable']
                return <li key={i}><span className={`pl-st ${cls}`}>{txt}</span> {e.text}{e.effect != null && <span className="small muted tabular"> ({e.base?.toFixed(2)} → {e.alt?.toFixed(2)}, {e.effect >= 0 ? '+' : ''}{e.effect.toFixed(2)} SD, {e.n} people)</span>}</li>
              })}</ul> : <p className="small muted">No predictions.</p>}
            </div>
            <div>
              <b className="small">What it changed</b>
              <ul className="pl-reach small">{(p.reach ?? []).map((r: any, i: number) => (
                <li key={i}>{r.label}{r.reached != null ? <span className="muted"> · reached {r.reached.toLocaleString()}</span> : null}
                  {r.practice?.history?.length > 1 && <span className="pl-prac"><Spark a={r.practice.history.map((h: any) => h.share)} width={120} height={22} color="var(--u-alt)" /><b className="tabular">{(100 * r.practice.history[r.practice.history.length - 1].share).toFixed(1)}%</b> have taken it up</span>}
                </li>))}</ul>
              {p.not_modeled?.length > 0 && <p className="small muted" style={{ margin: '4px 0 0' }}>Not in the model: {p.not_modeled.map((x: any) => x.aspect).join('; ')}.</p>}
            </div>
          </div>
        </div>
      ))}
      <div className="row" style={{ marginTop: 6 }}><span className="spacer" /><button className="btn small" onClick={() => useStore.getState().openDrawer({ tab: 'ask' })}>{G.mind} Add more in plain language</button></div>
    </div>
  )
}

function ChangeCard({ r }: { r: any }) {
  const { registry, setRoute, setLens } = useStore()
  const spec = registry!.variables[r.id]
  const drawer = DRAWERS.find(d => d.id === drawerOf(spec))
  const pol = polarity(r.id)
  return (
    <button className="card change-tile" onClick={() => { setLens('compare'); setRoute(['explore', r.id]) }}>
      <span className="ct-top"><span className="ct-drawer">{G[drawer?.icon ?? 'explore']}</span><span className="small muted">{drawer?.label}</span></span>
      <b className="ct-name">{spec.label}</b>
      {r.kind === 'cat' ? (
        <span className="ct-val"><span className="u-base-t">{pctStr(r.base[r.top])}</span> → <span className="u-alt-t">{pctStr(r.alt[r.top])}</span> <span className="small muted">{pretty(r.top)}</span></span>
      ) : r.kind === 'bool' ? (
        <span className="ct-val"><span className="u-base-t">{pctStr(r.base)}</span> → <span className="u-alt-t">{pctStr(r.alt)}</span></span>
      ) : (
        <span className="ct-val"><span className="u-base-t">{fpair(spec, r.base, r.alt)[0]}</span> → <span className="u-alt-t">{fpair(spec, r.base, r.alt)[1]}</span></span>
      )}
      <span className="row" style={{ gap: 6 }}>
        <DeltaChip d={r.kind === 'cat' ? r.top_delta : r.delta} text={sizeWord(r.effect)} polarity={r.kind === 'cat' ? 0 : pol} />
        <span className="small muted">{pctStr(r.changed_share, 0)} of people differ</span>
      </span>
      {r.spark?.length > 1 && <Spark a={r.spark} width={180} height={28} color="var(--u-alt)" />}
    </button>
  )
}

function EventDiffRow({ e }: { e: any }) {
  const setRoute = useStore(s => s.setRoute)
  const reg = useStore(s => s.registry)!
  const cat = reg.events[e.type]?.category
  const m = Math.max(e.base, e.alt, 1)
  return (
    <div className="evd" onClick={() => setRoute(['events', 'type', e.type])} role="button">
      <CatIcon c={cat} />
      <div className="evd-main">
        <div className="row" style={{ gap: 6 }}><b className="small">{e.label}</b><span className="spacer" /><b className={`tabular small ${e.delta > 0 ? 'u-alt-t' : 'u-base-t'}`}>{e.rel > 0 ? '+' : ''}{(100 * e.rel).toFixed(0)}%</b></div>
        <div className="evd-bars"><i className="b" style={{ width: `${(100 * e.base) / m}%` }} /><i className="a" style={{ width: `${(100 * e.alt) / m}%` }} /></div>
        <div className="small muted tabular">{e.base.toLocaleString()} → {e.alt.toLocaleString()}</div>
      </div>
    </div>
  )
}

function LifeRow({ p }: { p: any }) {
  const setRoute = useStore(s => s.setRoute)
  return (
    <div className="liferow" onClick={() => setRoute(['person', String(p.id), 'other'])} role="button">
      <span className="avatar sm" style={{ background: `var(--s${(p.id % 7) + 1})` }}>{p.name.split(' ').map((s: string) => s[0]).join('')}</span>
      <div style={{ minWidth: 0, flex: 1 }}>
        <b className="small">{p.name}</b>
        <div className="small lr-diffs">{p.diffs.slice(0, 2).map((d: any) => <span key={d.var}>{d.label.toLowerCase()}: <span className="u-base-t">{String(d.base)}</span> → <span className="u-alt-t">{String(d.alt)}</span></span>)}
          {!p.diffs.length && <span className="muted">{p.events_only_alt + p.events_only_base} events differ</span>}</div>
      </div>
      <span className="small muted tabular">{p.events_only_base + p.events_only_alt} events</span>
    </div>
  )
}

// ------------------------------------------------------------------ all fields
function AllFields({ f, err }: { f: any; err: string }) {
  const { registry, setRoute, setLens } = useStore()
  const [q, setQ] = useState('')
  const [drawer, setDrawer] = useState('')
  const [kind, setKind] = useState<'all' | 'num' | 'cat'>('all')
  const [sort, setSort] = useState<'effect' | 'changed' | 'name'>('effect')
  const [hideSame, setHideSame] = useState(true)
  const rows = useMemo(() => {
    if (!f) return []
    const reg = registry!
    let out = browsable(reg).filter(v => f.fields[v.id]).map(v => ({ v, r: f.fields[v.id], d: drawerOf(v) }))
    const ql = q.trim().toLowerCase()
    if (ql) out = out.filter(x => x.v.label.toLowerCase().includes(ql) || x.v.id.includes(ql))
    if (drawer) out = out.filter(x => x.d === drawer)
    if (kind === 'num') out = out.filter(x => x.r.kind === 'num')
    if (kind === 'cat') out = out.filter(x => x.r.kind !== 'num')
    if (hideSame) out = out.filter(x => Math.abs(x.r.effect) >= 0.001 || x.r.changed_share >= 0.001)
    out.sort((a, b) => sort === 'name' ? a.v.label.localeCompare(b.v.label) : sort === 'changed' ? b.r.changed_share - a.r.changed_share : Math.abs(b.r.effect) - Math.abs(a.r.effect))
    return out
  }, [f, q, drawer, kind, sort, hideSame])
  if (!f) return <div className="empty">{err || 'Comparing every field…'}</div>
  const maxE = Math.max(0.05, ...rows.map(x => Math.abs(x.r.effect)))
  const cats = catalog(registry!)
  return (
    <div className="card">
      <div className="row" style={{ marginBottom: 10 }}>
        <input type="search" placeholder="Search fields" value={q} onChange={e => setQ(e.target.value)} style={{ width: 200 }} />
        <select value={drawer} onChange={e => setDrawer(e.target.value)}><option value="">All areas</option>{cats.map(c => <option key={c.drawer.id} value={c.drawer.id}>{c.drawer.label}</option>)}</select>
        <div className="seg small-seg">{(['all', 'num', 'cat'] as const).map(k => <button key={k} className={kind === k ? 'on' : ''} onClick={() => setKind(k)}>{k === 'all' ? 'All' : k === 'num' ? 'Numbers' : 'Categories'}</button>)}</div>
        <span className="small muted">sort</span>
        <div className="seg small-seg">
          <button className={sort === 'effect' ? 'on' : ''} onClick={() => setSort('effect')} title="Standardized change in the average or share">Biggest shift</button>
          <button className={sort === 'changed' ? 'on' : ''} onClick={() => setSort('changed')} title="Share of people whose own value differs">Most people changed</button>
          <button className={sort === 'name' ? 'on' : ''} onClick={() => setSort('name')}>A–Z</button>
        </div>
        <label className="inline small"><input type="checkbox" checked={hideSame} onChange={e => setHideSame(e.target.checked)} />hide unchanged</label>
        <span className="spacer" /><span className="small muted">{rows.length} fields</span>
      </div>
      <p className="hint" style={{ marginTop: -4 }}>Every field the model tracks, Original vs What-if, for the {f.n.toLocaleString()} people present in both. “Shift” is a standardized size (Cohen's d for numbers, h for shares: 0.2 small, 0.5 moderate); “people changed” counts individual lives even when averages cancel out. The line shows the difference over time since the split.</p>
      <div className="scroll" style={{ maxHeight: 'none' }}>
        <table className="data fieldscan">
          <thead><tr><th>Field</th><th className="num"><UBadge u="base" /></th><th className="num"><UBadge u="alt" /></th><th>Shift</th><th className="num">People changed</th><th>Since the split</th></tr></thead>
          <tbody>{rows.map(({ v, r }) => (
            <tr key={v.id} className="click" onClick={() => { setLens('compare'); setRoute(['explore', v.id]) }}>
              <td><b>{v.label}</b><div className="small muted">{DRAWERS.find(d => d.id === drawerOf(v))?.label}</div></td>
              {r.kind === 'cat' ? <>
                <td className="num tabular">{pctStr(r.base[r.top])}<div className="small muted">{pretty(r.top)}</div></td>
                <td className="num tabular">{pctStr(r.alt[r.top])}<div className="small muted">{fdelta(v, r.top_delta, true)}</div></td>
              </> : r.kind === 'bool' ? <>
                <td className="num tabular">{pctStr(r.base)}</td><td className="num tabular">{pctStr(r.alt)}<div className="small muted">{fdelta(v, r.delta, true)}</div></td>
              </> : <>
                <td className="num tabular">{fpair(v, r.base, r.alt)[0]}</td><td className="num tabular">{fpair(v, r.base, r.alt)[1]}<div className="small muted">{fdelta(v, r.delta)}</div></td>
              </>}
              <td style={{ minWidth: 150 }}><div className="effbar"><span className="zero" /><i className={r.effect >= 0 ? 'pos' : 'neg'} style={{ left: r.effect >= 0 ? '50%' : `${50 - 50 * Math.abs(r.effect) / maxE}%`, width: `${Math.max(0.6, 50 * Math.abs(r.effect) / maxE)}%` }} /></div><div className="small muted">{sizeWord(r.effect)} · {r.effect >= 0 ? '+' : ''}{r.effect.toFixed(3)}</div></td>
              <td className="num tabular">{pctStr(r.changed_share)}</td>
              <td>{r.spark?.length > 1 ? <Spark a={r.spark} width={120} height={26} color="var(--u-alt)" /> : <span className="small muted">—</span>}</td>
            </tr>
          ))}</tbody>
        </table>
      </div>
    </div>
  )
}

// ------------------------------------------------------------------ events
function EventsDiff({ c, err }: { c: any; err: string }) {
  const [minN, setMinN] = useState(5)
  if (!c) return <div className="empty">{err || 'Counting events in both worlds…'}</div>
  const evs = c.events.filter((e: any) => e.base + e.alt >= minN && e.type !== 'intervention_exposure')
  const more = evs.filter((e: any) => e.delta > 0).slice(0, 18), less = evs.filter((e: any) => e.delta < 0).slice(0, 18)
  return (
    <>
      <div className="row" style={{ marginBottom: 10 }}><span className="small muted">Every life event since the split, counted in both worlds (two-person events such as dates and weddings count once for each person). Hide rare events below</span><input type="number" min={1} value={minN} onChange={e => setMinN(Number(e.target.value))} style={{ width: 64 }} /><span className="small muted">occurrences.</span></div>
      <div className="grid g2">
        <div className="card"><h3><UBadge u="alt" /> More common in the What-if</h3>{more.length ? more.map((e: any) => <EventDiffRow key={e.type} e={e} />) : <div className="empty small">None yet.</div>}</div>
        <div className="card"><h3><UBadge u="base" /> Less common in the What-if</h3>{less.length ? less.map((e: any) => <EventDiffRow key={e.type} e={e} />) : <div className="empty small">None yet.</div>}</div>
      </div>
    </>
  )
}

// ------------------------------------------------------------------ lives
function Lives() {
  const { status, dataVersion, setRoute } = useStore()
  const p = useAsync(() => api.comparePeople(60), [dataVersion], { key: whatifKey(status, 'people60') })
  const d: any = p.data
  if (!d) return <div className="empty">{p.error || 'Finding the lives that diverged…'}</div>
  return (
    <>
      <div className="kpis" style={{ marginBottom: 14 }}>
        <div className="kpi"><span className="k-label">Lives that differ</span><span className="k-val tabular">{d.with_any_diff.toLocaleString()}</span><span className="k-sub">{pctStr(d.with_any_diff / (d.n || 1))} of {d.n.toLocaleString()} people</span></div>
        <div className="kpi"><span className="k-label">Different life events</span><span className="k-val tabular">{d.with_event_diff.toLocaleString()}</span><span className="k-sub">something happened in only one world</span></div>
        <div className="kpi"><span className="k-label">Different situation now</span><span className="k-val tabular">{d.with_state_diff.toLocaleString()}</span><span className="k-sub">partner, home, faith, work, school…</span></div>
        <div className="kpi"><span className="k-label">Feel noticeably different</span><span className="k-val tabular">{(d.with_feeling_diff ?? 0).toLocaleString()}</span><span className="k-sub">mood or loneliness moved</span></div>
      </div>
      <div className="lives-grid">
        {d.people.map((x: any) => (
          <div key={x.id} className="card life-card" onClick={() => setRoute(['person', String(x.id), 'other'])} role="button">
            <div className="row" style={{ flexWrap: 'nowrap' }}>
              <span className="avatar" style={{ background: `var(--s${(x.id % 7) + 1})` }}>{x.name.split(' ').map((s: string) => s[0]).join('')}</span>
              <div style={{ flex: 1, minWidth: 0 }}><b>{x.name}</b><div className="small muted">{x.events_only_base} events only in the Original · {x.events_only_alt} only in the What-if</div></div>
            </div>
            <div className="two-lines">
              <div><UBadge u="base" /> <span className="small">{x.headline_base}</span></div>
              <div><UBadge u="alt" /> <span className="small">{x.headline_alt}</span></div>
            </div>
            {x.diffs.length > 0 && <div className="small lc-diffs">{x.diffs.slice(0, 4).map((df: any) => <div key={df.var}>{df.label}: <span className="u-base-t">{String(df.base)}</span> → <span className="u-alt-t">{String(df.alt)}</span></div>)}</div>}
            {x.first_divergence && <div className="small muted">First fork in the road: {x.first_divergence.label.toLowerCase()} on {new Date(x.first_divergence.date + 'T12:00:00').toLocaleDateString(undefined, { month: 'short', day: 'numeric' })}, only in the {x.first_divergence.world === 'alt' ? 'What-if' : 'Original'}</div>}
          </div>
        ))}
      </div>
    </>
  )
}

// ------------------------------------------------------------------ relationships
function Rel() {
  const { status, dataVersion, setRoute } = useStore()
  const r = useAsync(() => api.compareRelationships(), [dataVersion], { key: whatifKey(status, 'relationships') })
  const d: any = r.data
  if (!d) return <div className="empty">{r.error || 'Comparing couples and friendships…'}</div>
  const ax = axisStyle(), t = tokens()
  const ctx = [...new Set([...Object.keys(d.friendships.only_alt_by_met), ...Object.keys(d.friendships.only_base_by_met)])].filter(k => k !== 'preexisting')
  const opt = ctx.length ? {
    grid: { left: 8, right: 16, top: 26, bottom: 4, containLabel: true }, legend: { top: 0, textStyle: { color: t.text2 } }, tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    yAxis: { type: 'category', inverse: true, data: ctx, ...ax }, xAxis: { type: 'value', ...ax },
    series: [{ name: 'Only in the What-if', type: 'bar', barMaxWidth: 12, data: ctx.map(k => d.friendships.only_alt_by_met[k] ?? 0), itemStyle: { color: uColor('alt'), borderRadius: [0, 4, 4, 0] } },
      { name: 'Only in the Original', type: 'bar', barMaxWidth: 12, data: ctx.map(k => d.friendships.only_base_by_met[k] ?? 0), itemStyle: { color: uColor('base'), borderRadius: [0, 4, 4, 0] } }],
  } : null
  const Couple = ({ c, u }: { c: any; u: 'base' | 'alt' }) => (
    <div className="row small bf-flow">
      <span className="dot" style={{ background: `var(--u-${u})` }} />
      <button className="linkish" onClick={() => setRoute(['person', String(c.a), 'other'])}>{c.a_name}</button> & <button className="linkish" onClick={() => setRoute(['person', String(c.b), 'other'])}>{c.b_name}</button>
      <span className="spacer" /><span className="muted">{c.status_base ? `${c.status_base} → ` : ''}{c.status}{c.met ? ` · met: ${c.met}` : ''}</span>
    </div>
  )
  return (
    <>
      <div className="kpis" style={{ marginBottom: 14 }}>
        <div className="kpi"><span className="k-label">Couples</span><span className="k-val tabular"><span className="u-base-t">{d.couples.base.toLocaleString()}</span> → <span className="u-alt-t">{d.couples.alt.toLocaleString()}</span></span><span className="k-sub">talking, dating, engaged or married</span></div>
        <div className="kpi"><span className="k-label">Couples only in the What-if</span><span className="k-val tabular">{d.couples.only_alt}</span><span className="k-sub">{Object.entries(d.couples.only_alt_by_status).map(([k, v]) => `${v} ${k}`).join(' · ') || '—'}</span></div>
        <div className="kpi"><span className="k-label">Couples only in the Original</span><span className="k-val tabular">{d.couples.only_base}</span><span className="k-sub">{Object.entries(d.couples.only_base_by_status).map(([k, v]) => `${v} ${k}`).join(' · ') || '—'}</span></div>
        <div className="kpi"><span className="k-label">Friendships</span><span className="k-val tabular"><span className="u-base-t">{d.friendships.base.toLocaleString()}</span> → <span className="u-alt-t">{d.friendships.alt.toLocaleString()}</span></span><span className="k-sub">{d.friendships.only_alt.toLocaleString()} new · {d.friendships.only_base.toLocaleString()} gone</span></div>
      </div>
      <div className="grid g2">
        <div className="card"><h3>Couples who only exist in one world</h3><p className="hint">Click a name to see both of that person's lives.</p>
          <div className="scroll" style={{ maxHeight: 420 }}>
            {d.couples.examples_alt.map((c: any) => <Couple key={`a${c.a}-${c.b}`} c={c} u="alt" />)}
            {d.couples.examples_base.map((c: any) => <Couple key={`b${c.a}-${c.b}`} c={c} u="base" />)}
            {d.couples.examples_changed.map((c: any) => <Couple key={`c${c.a}-${c.b}`} c={c} u="alt" />)}
            {!d.couples.examples_alt.length && !d.couples.examples_base.length && !d.couples.examples_changed.length && <div className="empty small">Every couple is the same in both worlds (so far).</div>}
          </div></div>
        <div className="card"><h3>Where the different friendships began</h3><p className="hint">Friendships (stage “friend” or closer) that exist in only one world, by where the two first met.</p>
          {opt ? <EChart option={opt} height={300} /> : <div className="empty small">No differences yet.</div>}
          <div className="small muted" style={{ marginTop: 6 }}>Closest new friendships: {d.friendships.examples_alt.slice(0, 4).map((x: any, k: number) => <span key={k}>{k ? ' · ' : ''}<button className="linkish" onClick={() => setRoute(['person', String(x.a), 'other'])}>{x.a_name}</button> & <button className="linkish" onClick={() => setRoute(['person', String(x.b), 'other'])}>{x.b_name}</button></span>)}</div>
        </div>
      </div>
    </>
  )
}

// ------------------------------------------------------------------ places
function PlacesDiff() {
  const { status, dataVersion, setRoute, registry } = useStore()
  const [kind, setKind] = useState('complex')
  const [v, setV] = useState('loneliness')
  const r = useAsync(() => api.comparePlaces(kind, v), [kind, v, dataVersion], { key: whatifKey(status, `places:${kind}:${v}`) })
  const rows: any[] = (r.data as any) ?? []
  const spec = registry!.variables[v]
  const m = Math.max(1e-6, ...rows.map(x => Math.abs(x.delta ?? 0)))
  return (
    <div className="card">
      <div className="row" style={{ marginBottom: 10 }}>
        <div className="seg small-seg">{[['complex', 'Apartment complexes'], ['ward', 'Wards'], ['neighborhood', 'Neighborhoods'], ['school', 'Schools']].map(([k, l]) => <button key={k} className={kind === k ? 'on' : ''} onClick={() => setKind(k)}>{l}</button>)}</div>
        <span className="small muted">compare by</span><VarPicker value={v} onChange={setV} filter={s => !!s.mappable && s.dtype !== 'cat'} />
        <span className="spacer" />
        {kind === 'complex' && <button className="btn small" onClick={() => setRoute(['map', `homes:${v}`])}>{G.map} See it on the map</button>}
      </div>
      <p className="hint">Average {spec?.label.toLowerCase()} of the people living in each place, in both worlds, biggest difference first. “Moved out” counts residents of the Original who live elsewhere in the What-if.</p>
      {!rows.length ? <div className="empty small">{r.error || (r.loading ? 'Comparing places…' : 'No places to compare.')}</div> : (
        <div className="scroll" style={{ maxHeight: 600 }}>
          <table className="data"><thead><tr><th>Place</th><th className="num"><UBadge u="base" /></th><th className="num"><UBadge u="alt" /></th><th style={{ width: '28%' }}>Difference</th><th className="num">Residents</th><th className="num">Moved out</th></tr></thead>
            <tbody>{rows.slice(0, 120).map(x => (
              <tr key={x.id} className={kind === 'complex' || kind === 'ward' || kind === 'school' ? 'click' : ''} onClick={() => (kind === 'complex' || kind === 'ward' || kind === 'school') && setRoute(['places', kind, String(x.id)])}>
                <td>{x.name}</td><td className="num tabular">{fpair(spec, x.base, x.alt)[0]}</td><td className="num tabular">{fpair(spec, x.base, x.alt)[1]}</td>
                <td><div className="effbar"><span className="zero" /><i className={(x.delta ?? 0) >= 0 ? 'pos' : 'neg'} style={{ left: (x.delta ?? 0) >= 0 ? '50%' : `${50 - 50 * Math.abs(x.delta ?? 0) / m}%`, width: `${Math.max(0.6, 50 * Math.abs(x.delta ?? 0) / m)}%` }} /></div><span className="small muted tabular">{fdelta(spec, x.delta ?? 0)}</span></td>
                <td className="num tabular">{x.n_base} → {x.n_alt}</td><td className="num tabular">{x.moved_out || ''}</td>
              </tr>))}</tbody></table>
        </div>
      )}
    </div>
  )
}

// ------------------------------------------------------------------ why
function Why({ c, err }: { c: any; err: string }) {
  const { registry, setRoute } = useStore()
  const [picked, setState] = useState('')
  if (!c) return <div className="empty">{err || 'Tracing causes…'}</div>
  const state = picked || STATES.reduce((best, s) => (Math.abs(c.states[s]?.delta ?? 0) > Math.abs(c.states[best]?.delta ?? 0) ? s : best), 'loneliness')
  const st = c.states[state]
  const mech = Object.entries(c.mechanisms ?? {}).map(([id, d]: any) => ({ id, d, m: registry!.mechanisms[id] })).filter(x => x.m && Math.abs(x.d) > 1e-5).sort((a, b) => Math.abs(b.d) - Math.abs(a.d)).slice(0, 14)
  return (
    <div className="grid g2">
      <div className="card">
        <div className="card-head"><div><h3>Why feelings changed</h3><p className="hint">The change in the average, split exactly into the model's forces. Red raises it, blue lowers it.</p></div>
          <select value={state} onChange={e => setState(e.target.value)} aria-label="Feeling">{STATES.map(s => <option key={s} value={s}>{registry!.variables[s]?.label}</option>)}</select></div>
        <p className="small">Average {registry!.variables[state]?.label.toLowerCase()}: {st ? <b>{st.delta >= 0 ? '+' : ''}{st.delta.toFixed(4)}</b> : '—'} in the What-if.</p>
        {st && <Decomposition rows={st.terms.slice(0, 10).map((t: any) => ({ label: t.mechanism ? (registry!.mechanisms[t.mechanism]?.label ?? t.term) : 'After-effects of events', value: t.delta, evidence: t.mechanism ? registry!.mechanisms[t.mechanism]?.evidence : undefined }))} />}
        <div className="row" style={{ marginTop: 10 }}><button className="btn small" onClick={() => setRoute(['causal', state])}>{G.link} Trace these forces in Cause & effect</button><button className="btn small" onClick={() => setRoute(['explore', state])}>{G.explore} Explore {registry!.variables[state]?.label.toLowerCase()}</button></div>
      </div>
      <div className="card">
        <h3>The rules doing the most work</h3>
        <p className="hint">Which rules of the model changed their push the most between the worlds (averaged over everyone). Each comes with an evidence label: how sure we are the rule is right.</p>
        {mech.map(x => (
          <div key={x.id} className="row small bf-flow" onClick={() => setRoute(['mechanisms', x.id])} style={{ cursor: 'pointer' }}>
            <span style={{ flex: 1 }}>{x.m.label}</span><Evidence level={x.m.evidence} /><b className="tabular" style={{ width: 70, textAlign: 'right' }}>{x.d >= 0 ? '+' : ''}{x.d.toFixed(4)}</b>
          </div>
        ))}
        {!mech.length && <div className="empty small">No rule has shifted yet.</div>}
        <p className="small muted" style={{ marginTop: 10 }}>For one person's chain of causes, open any life from the Lives tab: its “Other life” section shows the first fork in their road and what led to it.</p>
      </div>
    </div>
  )
}
