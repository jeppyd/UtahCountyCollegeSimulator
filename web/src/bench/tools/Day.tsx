// Day: one person's day on a clock — classes, shifts, church and clubs, the occasions they were part of, and the free
// stretches in between (the four parts of the day the model simulates are shaded). Step through days with the arrows.
import { benchApi } from '../../api'
import { useAsync } from '../../game'
import { Busy, Empty, Problem, useWidth, useWorldDays } from '../../kit/Bits'
import { RefChip, usePersonName } from '../../kit/RefChip'
import { useLens, useStore } from '../../store'
import { PanelOptions } from '../panel'
import type { PanelProps, ToolDef } from '../registry'
import { focusItem, subjectPerson } from '../sel'

const T0 = 7 * 60, T1 = 24 * 60
const KIND_C: Record<string, string> = { class: '--s4', work: '--s2', shift: '--s2', church: '--s7', fhe: '--s7', club: '--s6' }

function DayTool({ sel, setSel, opts, setOpts }: PanelProps) {
  const u = useLens().u
  const dataVersion = useStore(s => s.dataVersion)
  const { today } = useWorldDays()
  const name = usePersonName(u)
  const who = subjectPerson(sel)
  const day: number | undefined = opts.day   // undefined = today, following the clock
  const [wrap, w] = useWidth<HTMLDivElement>()
  const data = useAsync(() => (who === null ? Promise.resolve(null) : benchApi.day(who, day, u)), [who, day, u, dataVersion])

  if (who === null) return <Empty title="Nobody selected">Select someone to see their day.</Empty>
  if (data.error && !data.data) return <Problem error={data.error} />
  if (!data.data) return <Busy what="Reading their day" />
  const d = data.data
  const L = 8, W = Math.max(260, w), X = (m: number) => L + ((Math.max(T0, Math.min(T1, m)) - T0) / (T1 - T0)) * (W - 2 * L)
  // the same class can be listed twice (two meetings recorded for a section); show it once
  const seen = new Set<string>()
  const commits = (d.commitments as any[]).filter(c => { const k = `${c.what}:${c.start}`; if (seen.has(k)) return false; seen.add(k); return true })
  const rows: { y: number; items: any[] }[] = []
  const place = (it: any) => {
    let r = rows.find(r => r.items.every(o => o.end <= it.start || o.start >= it.end))
    if (!r) { r = { y: 34 + rows.length * 30, items: [] }; rows.push(r) }
    r.items.push(it)
    return r.y
  }
  const bars = [
    ...commits.map(c => ({ ...c, label: c.what, sub: c.time, color: `var(${KIND_C[c.kind] ?? '--text-muted'})`, occ: null })),
    ...(d.occasions as any[]).map(o => ({ start: o.start, end: o.end, label: o.name ?? o.kind_label, sub: `${o.time}${o.attended === false ? ' · didn’t go' : ''}`, color: 'var(--s5)', occ: o })),
  ].sort((a, b) => a.start - b.start).map(b => ({ ...b, y: place(b) }))
  const H = 34 + Math.max(1, rows.length) * 30 + 26
  const hours = [8, 10, 12, 14, 16, 18, 20, 22]
  const hh = (h: number) => `${h % 12 || 12}${h < 12 ? ' am' : ' pm'}`
  const at = day ?? d.day

  return (
    <div className="bk" ref={wrap}>
      <PanelOptions>
        <button className="btn small ghost" onClick={() => setOpts({ ...opts, day: Math.max(0, at - 1) })} title="The day before">‹</button>
        <button className="btn small ghost" onClick={() => setOpts({ ...opts, day: undefined })} disabled={day === undefined} title="Back to today">today</button>
        <button className="btn small ghost" onClick={() => setOpts({ ...opts, day: Math.min(today, at + 1) })} disabled={at >= today} title="The next day">›</button>
      </PanelOptions>
      <div className="bk-title"><h4><RefChip r={{ kind: 'person', id: who, label: name(who), u }} plain /></h4><span className="bk-sub">{d.weekday}, {d.date}{day === undefined ? ' (today)' : ''}</span></div>
      <svg width={W} height={H} style={{ display: 'block' }}>
        {(d.blocks as any[]).map((b, k) => (
          <g key={b.block}>
            <rect className={`bd-block ${k % 2 ? 'alt' : ''}`} x={X(b.start)} y={14} width={X(b.end) - X(b.start)} height={H - 34} rx={6} />
            <text className="bd-sub" x={X(b.start) + 4} y={H - 8}>{b.label.split(' · ')[0]}</text>
          </g>
        ))}
        {hours.map(h => <g key={h} className="bd-axis"><line x1={X(h * 60)} x2={X(h * 60)} y1={14} y2={H - 20} stroke="var(--grid)" /><text x={X(h * 60) + 2} y={10}>{hh(h)}</text></g>)}
        {(d.free as any[]).map((f, k) => f.end - f.start >= 30 && <rect key={k} className="bd-free" x={X(f.start)} y={22} width={X(f.end) - X(f.start)} height={6} rx={3}><title>{`free ${f.label}`}</title></rect>)}
        {bars.map((b, k) => (
          <g key={k} style={{ cursor: b.occ ? 'pointer' : 'default' }}
            onClick={() => b.occ && focusItem(setSel, { kind: 'occasion', id: b.occ.id, label: b.label, u })}>
            <title>{`${b.label}: ${b.sub}${b.occ?.place ? ` at ${b.occ.place}` : ''}`}</title>
            <rect className="bd-bar" x={X(b.start)} y={b.y} width={Math.max(4, X(b.end) - X(b.start))} height={24} fill={b.color} opacity={b.occ?.attended === false ? 0.25 : 0.4} />
            {X(b.end) - X(b.start) > 44 && <text className="bd-label" x={X(b.start) + 5} y={b.y + 11}>{b.label}</text>}
            {X(b.end) - X(b.start) > 44 && <text className="bd-sub" x={X(b.start) + 5} y={b.y + 21}>{b.sub}</text>}
          </g>
        ))}
      </svg>
      <div className="bx-note">Dashed lines are free time; bars are commitments and occasions (click an occasion to open it).
        The model decides things in the four shaded parts of the day.</div>
    </div>
  )
}

export const tool: ToolDef = {
  id: 'day',
  label: 'Day',
  icon: 'clock',
  hint: "One person's day on a clock: classes, shifts, church, occasions and free time.",
  group: 'people',
  order: 25,
  component: DayTool,
  size: { w: 6, h: 4 },
  needs: ['people'],
}
