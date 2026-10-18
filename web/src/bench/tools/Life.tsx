// Life: one person's life on lanes over time — their situation (relationship, home, church activity) as bands, what
// happened to them as dots by kind, and a few feelings as lines. Click a dot to focus that event; drag across the
// lanes to set the time window every tool shares (double-click to clear it).
import { useMemo, useState, type PointerEvent } from 'react'
import { api, benchApi, type BenchEvent } from '../../api'
import { VarPicker } from '../../components'
import { G, useAsync } from '../../game'
import { Busy, CAT_ORDER, catLabel, catVar, dayWords, Empty, Problem, useWidth, useWorldDays } from '../../kit/Bits'
import { RefChip, usePersonName } from '../../kit/RefChip'
import { useLens, useStore } from '../../store'
import { PanelOptions } from '../panel'
import type { PanelProps, ToolDef } from '../registry'
import { focusItem, subjectPerson } from '../sel'

const BANDS = ['rel_status', 'living', 'activity', 'school']
const FEEL = ['mood', 'loneliness']
const LEFT = 118, BAND_H = 20, LANE_H = 20, FEEL_H = 34, GAP = 6
const PALETTE = ['--s1', '--s2', '--s3', '--s4', '--s5', '--s6', '--s7', '--s8']

/** Runs of equal values in a series sampled on `days` → [from, to, value] segments. */
function runs(days: number[], vals: string[], today: number): [number, number, string][] {
  const out: [number, number, string][] = []
  vals.forEach((v, k) => {
    const last = out[out.length - 1]
    if (last && last[2] === v) last[1] = days[k + 1] ?? today
    else out.push([days[k], days[k + 1] ?? today, v])
  })
  return out
}

function LifeTool({ sel, setSel, opts, setOpts }: PanelProps) {
  const u = useLens().u
  const dataVersion = useStore(s => s.dataVersion)
  const reg = useStore(s => s.registry)!
  const { start, today } = useWorldDays()
  const name = usePersonName(u)
  const who = subjectPerson(sel)
  const feel: string[] = (opts.feel ?? FEEL).filter((f: string) => reg.variables[f])
  const set = (o: Record<string, any>) => setOpts({ ...opts, ...o })
  const [adding, setAdding] = useState(false)
  const [wrap, w] = useWidth<HTMLDivElement>()
  const [drag, setDrag] = useState<[number, number] | null>(null)
  const [tip, setTip] = useState<{ x: number; y: number; e: BenchEvent } | null>(null)

  const data = useAsync(async () => {
    if (who === null) return null
    const [hist, ev] = await Promise.all([
      api.personHistory(who).catch(() => null),
      benchApi.events({ people: [who], limit: 3000, order: 'old' }, u),
    ])
    return { h: hist?.[u] ?? hist?.base ?? null, ev: ev.events }
  }, [who, u, dataVersion], { key: `bench-life:${u}:${who}` })

  const d = data.data
  const lanes = useMemo(() => {
    if (!d) return []
    const have = new Set(d.ev.map(e => e.category))
    return CAT_ORDER.filter(c => have.has(c))
  }, [d])
  const bands = d?.h ? BANDS.filter(b => d.h.cats?.[b]) : []

  if (who === null) return <Empty title="Nobody selected">Select someone on the Map or in People to see their life here.</Empty>
  if (data.error && !d) return <Problem error={data.error} />
  if (!d) return <Busy what="Reading their life" />

  const d0 = Math.min(0, ...(d.h?.days ?? [0])), d1 = Math.max(today, 1)
  const plotW = Math.max(120, w - LEFT - 8)
  const X = (day: number) => LEFT + ((day - d0) / Math.max(1, d1 - d0)) * plotW
  const dayAt = (x: number) => Math.round(d0 + ((x - LEFT) / plotW) * (d1 - d0))
  const yBands = 18, yLanes = yBands + bands.length * (BAND_H + 2) + GAP, yFeel = yLanes + lanes.length * LANE_H + GAP
  const H = yFeel + feel.length * (FEEL_H + 4) + 4
  const ticks: number[] = []
  const step = Math.max(7, Math.ceil((d1 - d0) / Math.max(2, Math.floor(plotW / 90)) / 7) * 7)
  for (let t = d0; t <= d1; t += step) ticks.push(t)
  const win = drag ?? sel.time ?? null
  const ptX = (ev: PointerEvent) => ev.clientX - (ev.currentTarget as SVGElement).getBoundingClientRect().left
  const focusId = sel.item?.kind === 'event' ? Number(sel.item.id) : null

  return (
    <div className="blane" style={{ height: '100%' }}>
      <PanelOptions>
        <button className="btn small" onClick={() => setAdding(!adding)} title="Add a feeling or trait as a line">+ line</button>
      </PanelOptions>
      <div className="blane-head">
        <h4><RefChip r={{ kind: 'person', id: who, label: name(who), u }} plain /></h4>
        <span className="bx-note">
          {d.ev.length.toLocaleString()} events; situation and feelings are recorded every two weeks, so the bands and lines
          are coarse. Drag across the lanes to set the time window.
        </span>
      </div>
      {adding && (
        <div className="bt-row">
          <VarPicker value="" onChange={v => { if (v && !feel.includes(v)) set({ feel: [...feel, v] }); setAdding(false) }} placeholder="Pick a feeling or trait" />
          <button className="btn small ghost" onClick={() => setAdding(false)}>cancel</button>
        </div>
      )}
      <div className="blane-svg-wrap" ref={wrap}>
        <svg width={w} height={H} style={{ display: 'block', touchAction: 'none' }}
          onPointerDown={e => { if (ptX(e) > LEFT) { (e.currentTarget as SVGElement).setPointerCapture(e.pointerId); const dd = dayAt(ptX(e)); setDrag([dd, dd]) } }}
          onPointerMove={e => drag && setDrag([drag[0], dayAt(ptX(e))])}
          onPointerUp={() => {
            if (drag) {
              const [a, b] = [Math.max(d0, Math.min(...drag)), Math.min(d1, Math.max(...drag))]
              if (b - a >= 1) setSel({ time: [a, b] })
              setDrag(null)
            }
          }}
          onDoubleClick={() => setSel({ time: undefined })}>
          {ticks.map(t => (
            <g key={t} className="bd-axis">
              <line x1={X(t)} x2={X(t)} y1={12} y2={H} stroke="var(--grid)" />
              <text x={X(t) + 3} y={10}>{dayWords(start, t)}</text>
            </g>
          ))}
          {win && <rect x={X(Math.min(...win))} width={Math.max(2, X(Math.max(...win)) - X(Math.min(...win)))} y={12} height={H - 12}
            fill="var(--accent)" opacity={0.08} pointerEvents="none" />}
          <line x1={X(today)} x2={X(today)} y1={12} y2={H} stroke="var(--accent)" strokeDasharray="2 3" />
          {bands.map((b, k) => {
            const y = yBands + k * (BAND_H + 2)
            const levels: string[] = []
            return (
              <g key={b}>
                <text x={0} y={y + 14} className="bd-sub" style={{ fontSize: 11 }}>{reg.variables[b]?.label ?? b}</text>
                {runs(d.h.days, d.h.cats[b], today).map(([a, z, v], j) => {
                  if (!levels.includes(v)) levels.push(v)
                  const c = `var(${PALETTE[levels.indexOf(v) % PALETTE.length]})`
                  const x0 = X(a), x1 = Math.max(X(z), x0 + 2)
                  return (
                    <g key={j}>
                      <rect className="blane-seg" x={x0} y={y} width={x1 - x0} height={BAND_H} rx={4} fill={c} opacity={0.35}>
                        <title>{`${reg.variables[b]?.label ?? b}: ${v.replace(/_/g, ' ')} (${dayWords(start, a)} – ${dayWords(start, z)})`}</title>
                      </rect>
                      {x1 - x0 > 50 && <text className="blane-seg-t" x={x0 + 5} y={y + 14}>{v.replace(/_/g, ' ')}</text>}
                    </g>
                  )
                })}
              </g>
            )
          })}
          {lanes.map((c, k) => {
            const y = yLanes + k * LANE_H + LANE_H / 2
            return (
              <g key={c}>
                <text x={0} y={y + 4} className="bd-sub" style={{ fontSize: 11 }}>{catLabel(c)}</text>
                <line x1={LEFT} x2={LEFT + plotW} y1={y} y2={y} stroke="var(--grid)" />
                {d.ev.filter(e => e.category === c).map(e => (
                  <circle key={e.id} cx={X(e.day + e.block / 4 + 0.12)} cy={y} r={2.5 + 4 * e.salience}
                    fill={catVar(c)} stroke={focusId === e.id ? 'var(--text-primary)' : 'var(--surface-1)'} strokeWidth={focusId === e.id ? 2 : 1}
                    opacity={0.35 + 0.65 * e.salience} style={{ cursor: 'pointer' }}
                    onPointerDown={ev => ev.stopPropagation()}
                    onClick={() => focusItem(setSel, { kind: 'event', id: e.id, label: e.label, u })}
                    onMouseEnter={ev => setTip({ x: ev.clientX, y: ev.clientY, e })} onMouseLeave={() => setTip(null)} />
                ))}
              </g>
            )
          })}
          {feel.map((f, k) => {
            const y = yFeel + k * (FEEL_H + 4)
            const s: (number | null)[] = d.h?.nums?.[f] ?? []
            const vs = s.filter((x): x is number => x !== null && Number.isFinite(x))
            const sc = reg.variables[f]?.scale
            const lo = sc?.min ?? Math.min(0, ...vs), hi = sc?.max ?? Math.max(1, ...vs)
            const Y = (x: number) => y + FEEL_H - 3 - ((x - lo) / (hi - lo || 1)) * (FEEL_H - 6)
            let path = '', pen = false
            s.forEach((x, j) => { if (x === null || !Number.isFinite(x)) { pen = false; return } path += `${pen ? 'L' : 'M'}${X(d.h.days[j]).toFixed(1)},${Y(x).toFixed(1)}`; pen = true })
            const col = `var(${PALETTE[(k + 3) % PALETTE.length]})`
            return (
              <g key={f}>
                <text x={0} y={y + 14} className="bd-sub" style={{ fontSize: 11 }}>{reg.variables[f]?.label ?? f}</text>
                <text x={0} y={y + 27} className="bd-sub">{sc?.low ? `low = ${sc.low}` : ''}</text>
                <rect x={LEFT} y={y} width={plotW} height={FEEL_H} fill="var(--surface-2)" opacity={0.5} rx={4} />
                <path d={path} className="blane-feel" stroke={col} />
                {s.map((x, j) => x !== null && Number.isFinite(x) && (
                  <circle key={j} className="blane-feel-pt" cx={X(d.h.days[j])} cy={Y(x)} r={2.6} fill={col}>
                    <title>{`${reg.variables[f]?.label ?? f} on ${dayWords(start, d.h.days[j])}: ${x.toFixed(2)}`}</title>
                  </circle>
                ))}
                <g transform={`translate(${LEFT + plotW - 14}, ${y + 2})`} style={{ cursor: 'pointer' }}
                  onPointerDown={ev => ev.stopPropagation()} onClick={() => set({ feel: feel.filter(x => x !== f) })}>
                  <title>Remove this line</title>
                  <rect width={12} height={12} fill="transparent" />
                  <g style={{ color: 'var(--text-muted)' }} transform="scale(0.5)">{G.close}</g>
                </g>
              </g>
            )
          })}
        </svg>
        {lanes.length === 0 && <div className="bx-note">No events recorded for them yet.</div>}
      </div>
      {tip && (
        <div className="bx-tip" style={{ left: tip.x + 12, top: tip.y + 12 }}>
          <b>{tip.e.label}</b>{tip.e.b_name ? ` · with ${tip.e.b_name}` : ''}<br />
          <small>{dayWords(start, tip.e.day, true)} · click to focus and trace</small>
        </div>
      )}
    </div>
  )
}

export const tool: ToolDef = {
  id: 'life',
  label: 'Life',
  icon: 'id',
  hint: "One person's life on lanes: their situation, what happened to them and how they felt, over time.",
  group: 'people',
  order: 20,
  component: LifeTool,
  size: { w: 7, h: 6 },
  needs: ['people'],
}
