// Timeline: what happened over time. For a few selected people (up to 30) a row each, with their events as dots; for
// a bigger group or everyone, how many events of each kind happened each day. Drag across it to set the time window
// every tool shares (double-click to clear); click a dot to focus that event.
import { useMemo, useState, type PointerEvent } from 'react'
import { benchApi, type BenchEvent } from '../../api'
import { useAsync } from '../../game'
import { Busy, CAT_ORDER, catLabel, catVar, CatDot, dayWords, Problem, useWidth, useWorldDays } from '../../kit/Bits'
import { usePersonName } from '../../kit/RefChip'
import { useLens, useStore } from '../../store'
import { PanelOptions } from '../panel'
import type { PanelProps, ToolDef } from '../registry'
import { focusItem, hasGroup, selGroup, selPeople } from '../sel'

const MAX_ROWS = 30
const LEFT = 120, ROW = 18, DENS_H = 150

function TimelineTool({ sel, setSel, opts, setOpts }: PanelProps) {
  const u = useLens().u
  const dataVersion = useStore(s => s.dataVersion)
  const { start, today } = useWorldDays()
  const name = usePersonName(u)
  const big: boolean = opts.big ?? false
  const [wrap, w] = useWidth<HTMLDivElement>()
  const [drag, setDrag] = useState<[number, number] | null>(null)
  const [tip, setTip] = useState<{ x: number; y: number; t: string; s: string } | null>(null)
  const ppl = selPeople(sel)
  const rowsMode = ppl.length > 0 && ppl.length <= MAX_ROWS && !sel.filter?.length
  const g = selGroup(sel)
  const minSalience = big ? 0.6 : 0

  const data = useAsync(async () => {
    if (rowsMode) {
      const r = await benchApi.events({ people: ppl, limit: 5000, order: 'old', minSalience }, u)
      return { rows: r.events, dens: null }
    }
    return { rows: null, dens: await benchApi.density({ ...g, minSalience }, u) }
  }, [rowsMode, ppl.join(','), JSON.stringify(g), big, u, dataVersion], { key: `bench-tl:${u}:${ppl.join(',')}:${JSON.stringify(g)}:${big}` })

  const d = data.data
  const byPerson = useMemo(() => {
    const m = new Map<number, BenchEvent[]>()
    if (!d?.rows) return m
    ppl.forEach(i => m.set(i, []))
    for (const e of d.rows) {
      m.get(e.a)?.push(e)
      if (e.b !== null && e.b !== e.a) m.get(e.b)?.push(e)
    }
    return m
  }, [d, ppl.join(',')])

  const d0 = d?.dens ? d.dens.days[0] ?? 0 : Math.min(0, ...(d?.rows ?? []).map(e => e.day))
  const d1 = Math.max(today, d0 + 1)
  const plotW = Math.max(120, w - LEFT - 8)
  const X = (day: number) => LEFT + ((day - d0) / Math.max(1, d1 - d0 + 1)) * plotW
  const dayAt = (x: number) => Math.max(d0, Math.min(d1, Math.floor(d0 + ((x - LEFT) / plotW) * (d1 - d0 + 1))))
  const ptX = (ev: PointerEvent) => ev.clientX - (ev.currentTarget as SVGElement).getBoundingClientRect().left
  const win = drag ?? sel.time ?? null
  const focusId = sel.item?.kind === 'event' ? Number(sel.item.id) : null
  const H = rowsMode ? 18 + ppl.length * ROW + 6 : 18 + DENS_H + 4
  const ticks: number[] = []
  const step = Math.max(7, Math.ceil((d1 - d0) / Math.max(2, Math.floor(plotW / 90)) / 7) * 7)
  for (let t = d0; t <= d1; t += step) ticks.push(t)

  // stacked daily counts by category (bigger groups)
  const stacks = useMemo(() => {
    if (!d?.dens) return null
    const cats = CAT_ORDER.filter(c => d.dens!.cats.includes(c)).concat(d.dens.cats.filter(c => !CAT_ORDER.includes(c)))
    const tot = d.dens.days.map((_, k) => cats.reduce((s, c) => s + (d.dens!.counts[c][k] ?? 0), 0))
    return { cats, tot, max: Math.max(1, ...tot) }
  }, [d])

  return (
    <div className="blane" style={{ height: '100%' }}>
      <PanelOptions>
        <label className="bt-row" title="Only events that matter more to a life (first dates, breakups, moves…)">
          <input type="checkbox" checked={big} onChange={e => setOpts({ ...opts, big: e.target.checked })} /> big ones
        </label>
      </PanelOptions>
      {data.error && !d && <Problem error={data.error} />}
      {!d && !data.error && <Busy what="Reading the record" />}
      {d && (
        <>
          <div className="bx-note">
            {rowsMode ? `A row for each selected person (${ppl.length}).`
              : `${hasGroup(sel) ? `The ${(d.dens?.n_people ?? 0).toLocaleString()} selected people` : 'Everyone'}: events per day by kind${ppl.length > MAX_ROWS ? ` (more than ${MAX_ROWS} people, so counts instead of rows)` : ''}.`}
            {' '}Drag across to set the time window{sel.time ? `; now ${dayWords(start, sel.time[0])} – ${dayWords(start, sel.time[1])} (double-click to clear)` : ''}.
          </div>
          {stacks && (
            <div className="bx-legend">
              {stacks.cats.map(c => <span key={c}><CatDot c={c} />{catLabel(c)}</span>)}
            </div>
          )}
          <div className="blane-svg-wrap" ref={wrap}>
            <svg width={w} height={H} style={{ display: 'block', touchAction: 'none' }}
              onPointerDown={e => { if (ptX(e) > LEFT) { (e.currentTarget as SVGElement).setPointerCapture(e.pointerId); const dd = dayAt(ptX(e)); setDrag([dd, dd]) } }}
              onPointerMove={e => drag && setDrag([drag[0], dayAt(ptX(e))])}
              onPointerUp={() => {
                if (drag) { const a = Math.min(...drag), b = Math.max(...drag); if (b > a) setSel({ time: [a, b] }); setDrag(null) }
              }}
              onDoubleClick={() => setSel({ time: undefined })}>
              {ticks.map(t => (
                <g key={t} className="bd-axis">
                  <line x1={X(t)} x2={X(t)} y1={12} y2={H} stroke="var(--grid)" />
                  <text x={X(t) + 3} y={10}>{dayWords(start, t)}</text>
                </g>
              ))}
              {win && <rect x={X(Math.min(...win))} width={Math.max(2, X(Math.max(...win) + 1) - X(Math.min(...win)))} y={12} height={H - 12}
                fill="var(--accent)" opacity={0.08} pointerEvents="none" />}
              {rowsMode && ppl.map((i, k) => {
                const y = 18 + k * ROW + ROW / 2
                return (
                  <g key={i}>
                    <text x={0} y={y + 4} className="bd-label" style={{ cursor: 'pointer', pointerEvents: 'auto' }}
                      onPointerDown={ev => ev.stopPropagation()}
                      onClick={() => focusItem(setSel, { kind: 'person', id: i, label: name(i) })}>{name(i).slice(0, 18)}</text>
                    <line x1={LEFT} x2={LEFT + plotW} y1={y} y2={y} stroke="var(--grid)" />
                    {(byPerson.get(i) ?? []).map(e => (
                      <circle key={e.id} cx={X(e.day + e.block / 4 + 0.12)} cy={y} r={2 + 3.5 * e.salience} fill={catVar(e.category)}
                        stroke={focusId === e.id ? 'var(--text-primary)' : 'none'} strokeWidth={2} opacity={0.35 + 0.65 * e.salience}
                        style={{ cursor: 'pointer' }} onPointerDown={ev => ev.stopPropagation()}
                        onClick={() => focusItem(setSel, { kind: 'event', id: e.id, label: e.label, u })}
                        onMouseEnter={ev => setTip({ x: ev.clientX, y: ev.clientY, t: e.label + (e.b_name && e.b !== i ? ` · with ${e.b_name}` : e.b !== null && e.b === i ? ` · with ${e.a_name}` : ''), s: dayWords(start, e.day, true) })}
                        onMouseLeave={() => setTip(null)} />
                    ))}
                  </g>
                )
              })}
              {stacks && d.dens!.days.map((day, k) => {
                let y = 18 + DENS_H
                const bw = Math.max(1, X(day + 1) - X(day) - 1)
                return (
                  <g key={day} onMouseEnter={ev => setTip({ x: ev.clientX, y: ev.clientY, t: `${stacks.tot[k].toLocaleString()} events`, s: dayWords(start, day, true) })} onMouseLeave={() => setTip(null)}>
                    {stacks.cats.map(c => {
                      const v = d.dens!.counts[c][k] ?? 0
                      if (!v) return null
                      const h = (v / stacks.max) * DENS_H
                      y -= h
                      return <rect key={c} x={X(day)} y={y} width={bw} height={h} fill={catVar(c)} opacity={0.8} />
                    })}
                  </g>
                )
              })}
              {stacks && <text x={0} y={30} className="bd-sub">{stacks.max.toLocaleString()} a day</text>}
            </svg>
          </div>
        </>
      )}
      {tip && <div className="bx-tip" style={{ left: tip.x + 12, top: tip.y + 12 }}><b>{tip.t}</b><br /><small>{tip.s}</small></div>}
    </div>
  )
}

export const tool: ToolDef = {
  id: 'timeline',
  label: 'Timeline',
  icon: 'clock',
  hint: 'Events over time for the selected people (a row each) or for a whole group; drag across it to set the time window.',
  group: 'see',
  order: 20,
  component: TimelineTool,
  size: { w: 8, h: 5 },
}
