// Chains: the valley's chain reactions. Which kinds of events led to which (through recorded causes), which choices
// produced them, and the reasons that most often tipped each choice — for everyone or the selected people, in a time
// window. Click a flow to see real instances (each opens in Trace); click a kind of event to center on it.
import { useMemo, useState } from 'react'
import { traceApi, type Universe } from '../../api'
import { cssVar, EChart } from '../../components'
import { useAsync } from '../../game'
import { DecisionCard } from '../../kit/DecisionCard'
import { dayLabel } from '../../kit/traceRefs'
import '../../kit/trace.css'
import { useLens, useStore } from '../../store'
import type { PanelProps, ToolDef } from '../registry'

const CAT_VAR: Record<string, string> = {
  romance: '--s5', sexuality: '--s5', social: '--s3', religion: '--s7', academics: '--s4', work: '--s2', family: '--s2',
  health: '--s8', housing: '--s1', habits: '--s6', coping: '--s8', plans: '--s4', intervention: '--s2',
}
const WINDOWS: { k: string; label: string; days?: number }[] = [
  { k: '14', label: 'Last 2 weeks', days: 14 }, { k: '60', label: 'Last 2 months', days: 60 },
  { k: 'all', label: 'The whole story' }, { k: 'sel', label: 'Selected time' },
]

type Flow = {
  source: string; target: string; value: number; kind: string; from_label: string; to_label: string
  examples: { event: number; from?: number; decision?: number; day: number; label: string; from_label?: string }[]
}

function ChainsTool({ sel, setSel, opts, setOpts }: PanelProps) {
  const lens = useLens()
  const reg = useStore(s => s.registry)
  const today: number | undefined = useStore(s => s.status?.day)
  const dataVersion = useStore(s => s.dataVersion)
  const set = (o: Record<string, any>) => setOpts({ ...opts, ...o })
  const win: string = opts.window ?? (sel.time ? 'sel' : '60')
  const root: string = opts.root ?? ''
  const maxLinks: number = opts.max ?? 30
  const cohortOn: boolean = opts.cohort ?? true
  const u: Universe = lens.u
  const people = cohortOn ? sel.people : undefined
  const filter = cohortOn && !sel.people?.length ? sel.filter : undefined
  const w = WINDOWS.find(x => x.k === win) ?? WINDOWS[1]
  const [since, until] = win === 'sel' && sel.time ? sel.time
    : win === 'all' ? [0, today] : [today !== undefined && w.days ? Math.max(0, today - w.days) : undefined, today]
  const got = useAsync(() => traceApi.chains({ u, since, until, people, filter, root: root || undefined, maxLinks }),
    [u, since, until, (people ?? []).join(','), JSON.stringify(filter ?? []), root, maxLinks, dataVersion], true)
  const [flow, setFlow] = useState<number | null>(null)
  const [reason, setReason] = useState<number | null>(null)
  const [openDec, setOpenDec] = useState<number | null>(null)
  const c = got.data

  const option = useMemo(() => {
    if (!c) return null
    const typeOf = (id: string) => id.split(':')[1]?.split('|')[0] ?? ''
    const color = (id: string, kind: string) => {
      if (kind === 'decision') return cssVar('--text-muted')
      const cat = reg?.events?.[typeOf(id)]?.category
      return cssVar(CAT_VAR[cat] ?? '--accent')
    }
    const text = cssVar('--text-primary')
    return {
      tooltip: {
        trigger: 'item', confine: true,
        formatter: (p: any) => (p.dataType === 'edge'
          ? `${p.data.from_label} → ${p.data.to_label}<br/><b>${p.data.value.toLocaleString()}</b> times · click for examples`
          : `${p.data.label}<br/><b>${(p.data.n ?? 0).toLocaleString()}</b>`),
      },
      series: [{
        type: 'sankey', left: 8, right: 150, top: 10, bottom: 10, nodeWidth: 12, nodeGap: 9, layoutIterations: 48,
        emphasis: { focus: 'adjacency' }, draggable: false,
        label: { color: text, fontSize: 11.5, formatter: (p: any) => (p.data.kind === 'decision' ? '◆ ' : '') + p.data.label },
        lineStyle: { color: 'gradient', opacity: 0.32, curveness: 0.5 },
        data: c.nodes.map((n: any) => ({ name: n.id, label: n.label, kind: n.kind, n: n.n, itemStyle: { color: color(n.id, n.kind), borderWidth: 0 } })),
        links: c.links.map((L: Flow, i: number) => ({ source: L.source, target: L.target, value: L.value, i, from_label: L.from_label, to_label: L.to_label,
          lineStyle: i === flow ? { opacity: 0.75 } : undefined })),
      }],
    }
  }, [c, flow, reg])

  if (got.error && !c) return <div className="tr-empty"><b>Chains need the live simulator.</b> {got.error}</div>
  if (!c) return <div className="tr-empty">Counting what led to what…</div>
  const F: Flow | null = flow !== null ? c.links[flow] ?? null : null
  const types = reg ? Object.values(reg.events).sort((a: any, b: any) => a.label.localeCompare(b.label)) : []
  const sideN = Math.max(...['from', 'to', 'root'].map(s => c.nodes.filter((n: any) => n.side === s).length), 1)
  const height = Math.max(280, Math.min(900, sideN * 26 + 30))
  const onChart = (p: any) => {
    if (p.dataType === 'edge') { setFlow(p.data.i); return }
    if (p.dataType === 'node' && p.data.kind === 'event') {
      const t = String(p.data.name).split(':')[1]?.split('|')[0]
      if (t) { set({ root: t === root ? '' : t }); setFlow(null) }
    } else if (p.dataType === 'node' && p.data.kind === 'decision') {
      const [, kind, outcome] = String(p.data.name).split('|')[0].split(':')
      const k = c.reasons.findIndex((r: any) => r.decision === kind && r.outcome === outcome)
      if (k >= 0) setReason(k)
    }
  }
  const who = people?.length ? `${people.length.toLocaleString()} selected ${people.length === 1 ? 'person' : 'people'}`
    : filter?.length ? 'the selected group' : 'everyone'
  return (
    <div className="ch">
      <div className="ch-bar">
        <div className="seg small-seg" role="group" aria-label="Time window">
          {WINDOWS.filter(x => x.k !== 'sel' || sel.time).map(x => (
            <button key={x.k} className={win === x.k ? 'on' : ''} onClick={() => { set({ window: x.k }); setFlow(null) }}>{x.label}</button>
          ))}
        </div>
        <select value={root} onChange={e => { set({ root: e.target.value }); setFlow(null) }} aria-label="Center on a kind of event">
          <option value="">All kinds of events</option>
          {types.map((t: any) => <option key={t.id} value={t.id}>Around: {t.label}</option>)}
        </select>
        {(sel.people?.length || sel.filter?.length) ? (
          <label className="ch-sum"><input type="checkbox" checked={cohortOn} onChange={e => set({ cohort: e.target.checked })} /> only the selected people</label>
        ) : null}
        <select value={maxLinks} onChange={e => set({ max: Number(e.target.value) })} aria-label="How many flows">
          {[15, 30, 60, 120].map(k => <option key={k} value={k}>{k} largest flows</option>)}
        </select>
        {got.loading && <span className="muted ch-sum">updating…</span>}
      </div>
      <div className="ch-sum">
        {c.events.toLocaleString()} events by {who}, {dayLabel(c.start_date, c.window[0], { month: 'short', day: 'numeric' })} –{' '}
        {dayLabel(c.start_date, c.window[1], { month: 'short', day: 'numeric', year: 'numeric' })}
        {c.root_label ? <> · centered on <b>{c.root_label}</b> <button className="btn ghost small" onClick={() => set({ root: '' })}>show all</button></> : null}
      </div>
      <div className="ch-grid">
        <div className="ch-flow">
          {c.links.length ? (option && <EChart option={option} height={height} onClick={onChart} />)
            : <div className="tr-empty">No recorded links between events in this window{c.root_label ? ` around “${c.root_label}”` : ''}.</div>}
          <div className="ch-cut">{c.notes.join(' ')}</div>
        </div>
        <div className="ch-side">
          {F ? (
            <div>
              <div className="ch-h">{F.from_label} → {F.to_label}: {F.value.toLocaleString()} times</div>
              <div className="ch-ex">
                {F.examples.map(x => (
                  <button key={x.event} onClick={() => setSel({ item: { kind: 'event', id: x.event, label: x.label, u } })} title="Open in Trace">
                    {x.from_label && <span className="muted">{x.from_label} →<br /></span>}
                    {x.label} <span className="muted">· {dayLabel(c.start_date, x.day)}</span>
                  </button>
                ))}
              </div>
              <p className="ch-cut">The latest {F.examples.length} of {F.value.toLocaleString()}; click one to trace it.</p>
            </div>
          ) : <p className="ch-cut">Click a flow to see real instances of it, or a kind of event to center on it.</p>}
          <div>
            <div className="ch-h">Why people chose what they chose</div>
            {c.reasons.slice(0, 12).map((r: any, i: number) => (
              <Reason key={`${r.decision}:${r.outcome}`} r={r} open={reason === i} onToggle={() => setReason(reason === i ? null : i)}
                onDecision={id => setOpenDec(openDec === id ? null : id)} openDec={openDec} u={u} startDate={c.start_date}
                onTrace={(kind, id) => setSel({ item: { kind, id, u } })} />
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}

function Reason({ r, open, onToggle, onDecision, openDec, u, startDate, onTrace }: {
  r: any; open: boolean; onToggle: () => void; onDecision: (id: number) => void; openDec: number | null; u: Universe; startDate: string
  onTrace: (kind: 'event' | 'decision' | 'person' | 'var' | 'place' | 'tie', id: string | number) => void
}) {
  const colors = [1, 3, 4, 7, 5, 2].map(k => `var(--s${k})`)
  return (
    <div className="ch-reason" style={{ marginBottom: 6 }}>
      <button className="ch-rs" onClick={onToggle} aria-expanded={open}>{r.sentence}</button>
      <div className="ch-shares" aria-hidden="true">
        {r.top.map((t: any, k: number) => <span key={k} style={{ width: `${t.share * 100}%`, background: t.factor ? colors[k % colors.length] : 'var(--axis)' }} title={`${t.words}: ${Math.round(t.share * 100)}%`} />)}
      </div>
      {open && (
        <>
          <div className="ch-top">
            {r.top.map((t: any, k: number) => (
              <span key={k} style={{ display: 'contents' }}>
                <span><i style={{ background: t.factor ? colors[k % colors.length] : 'var(--axis)' }} />{t.words}{t.factor && t.label !== t.words ? <span className="muted"> ({t.label})</span> : null}</span>
                <span className="tabular" style={{ textAlign: 'right' }}>{Math.round(t.share * 100)}%</span>
              </span>
            ))}
          </div>
          <div className="ch-ex">
            <span className="muted" style={{ fontSize: 11 }}>Recent examples:</span>
            {r.examples.map((x: { id: number; day: number; who: string; about: string | null; top: string | null }) => (
              <div key={x.id}>
                <button onClick={() => onDecision(x.id)} style={{ width: '100%' }} aria-expanded={openDec === x.id}>
                  {x.who}{x.about ? <span className="muted"> about {x.about}</span> : null}
                  {x.top ? <> — {x.top}</> : null} <span className="muted">· {dayLabel(startDate, x.day)} {openDec === x.id ? '▾' : '▸'}</span>
                </button>
                {openDec === x.id && (
                  <div style={{ padding: '8px 4px' }}>
                    <DecisionCard id={x.id} u={u} startDate={startDate} onRef={ref => onTrace(ref.kind === 'state' ? 'var' : ref.kind as any, ref.id)} />
                    <button className="btn small" style={{ marginTop: 6 }} onClick={() => onTrace('decision', x.id)}>Trace this decision</button>
                  </div>
                )}
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  )
}

export const tool: ToolDef = {
  id: 'chains',
  label: 'Chains',
  icon: 'network',
  hint: 'Chain reactions across the valley: which kinds of events led to which, the choices behind them and their most common reasons.',
  group: 'trace',
  order: 20,
  component: ChainsTool,
  size: { w: 12, h: 9 },
}
