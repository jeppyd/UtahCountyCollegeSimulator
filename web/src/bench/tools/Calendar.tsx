// Calendar: the Provo year as a strip of days — BYU's and UVU's terms and finals, holidays and breaks, dated events
// (football games, General Conference, devotionals…) and the weather each day replays (highs and lows, rain, snow).
// Real dates are solid, rule-based ones hollow, our estimates dashed. Click a day to set the time window; click an
// event to focus it.
import { useMemo, useState, type PointerEvent } from 'react'
import { benchApi } from '../../api'
import { useAsync } from '../../game'
import { Busy, dayWords, Problem, useWidth, useWorldDays } from '../../kit/Bits'
import { useLens, useStore } from '../../store'
import { PanelOptions } from '../panel'
import type { PanelProps, ToolDef } from '../registry'
import { focusItem } from '../sel'

const KIND_C: Record<string, string> = {
  football: '--s2', football_away: '--s2', conference: '--s7', devotional: '--s7', holiday: '--s1', break: '--s6',
  travel: '--s6', school: '--s4', festival: '--s5', basketball: '--s2', performance: '--s5',
}
const kc = (k: string) => `var(${KIND_C[k] ?? '--text-muted'})`
const BASIS: Record<string, string> = { real: 'published date', rule: 'recurring rule', hypothetical: 'our estimate' }
const LEFT = 64

function CalendarTool({ sel, setSel, opts, setOpts }: PanelProps) {
  const u = useLens().u
  const dataVersion = useStore(s => s.dataVersion)
  const { start, today } = useWorldDays()
  const span: number = opts.span ?? 84
  const [wrap, w] = useWidth<HTMLDivElement>()
  const [tip, setTip] = useState<{ x: number; y: number; t: string; s: string } | null>(null)
  const [drag, setDrag] = useState<[number, number] | null>(null)
  // the year view runs August to July; shorter views start two weeks back
  const yearStart = (() => {
    if (!start) return today - 14
    const t = new Date(new Date(start + 'T12:00:00').getTime() + today * 864e5)
    const aug1 = new Date(t.getMonth() >= 7 ? t.getFullYear() : t.getFullYear() - 1, 7, 1, 12)
    return today - Math.round((t.getTime() - aug1.getTime()) / 864e5)
  })()
  const a = span >= 365 ? yearStart : today - 14, b = a + span
  const data = useAsync(async () => {
    const [it, wx] = await Promise.all([benchApi.calendarItems(a, b, u), benchApi.calendarWeather(a, b, u)])
    return { it, wx }
  }, [a, b, u, Math.floor(dataVersion / 4)], { key: `bench-cal:${u}:${a}:${b}` })

  const d = data.data
  const W = Math.max(300, w), plotW = W - LEFT - 8
  const X = (day: number) => LEFT + ((day - a) / (b - a + 1)) * plotW
  const dw = plotW / (b - a + 1)
  const dayAt = (x: number) => Math.max(a, Math.min(b, Math.floor(a + ((x - LEFT) / plotW) * (b - a + 1))))
  const ptX = (ev: PointerEvent) => ev.clientX - (ev.currentTarget as SVGElement).getBoundingClientRect().left
  const yT = 18, yI = 62, yW = 104, HW = 70, H = yW + HW + 22
  const temps = useMemo(() => {
    if (!d) return null
    const ds = d.wx.days as any[]
    const lo = Math.min(...ds.map(r => r.tmin_f)), hi = Math.max(...ds.map(r => r.tmax_f))
    return { ds, lo: Math.floor(lo / 10) * 10, hi: Math.ceil(hi / 10) * 10 }
  }, [d])
  const Y = (f: number) => temps ? yW + HW - ((f - temps.lo) / (temps.hi - temps.lo || 1)) * HW : 0
  const path = (k: 'tmax_f' | 'tmin_f') => temps!.ds.map((r, i) => `${i ? 'L' : 'M'}${(X(r.day) + dw / 2).toFixed(1)},${Y(r[k]).toFixed(1)}`).join('')
  const focused = sel.item?.kind === 'calendar' ? String(sel.item.id) : null
  const win = drag ?? sel.time ?? null
  // items in the strip: one-day items as markers; ranges (breaks, conference) as bars
  const items = (d?.it.items ?? []) as any[]
  const singles = items.filter(it => it.day === it.end_day && it.kind !== 'devotional')
  const ranges = items.filter(it => it.end_day > it.day)
  const devos = items.filter(it => it.kind === 'devotional')
  const upcoming = items.filter(it => it.end_day >= today && it.kind !== 'devotional').slice(0, 14)
  const weeks: number[] = []
  for (let x = a; x <= b; x++) if (start && new Date(new Date(start + 'T12:00:00').getTime() + x * 864e5).getDay() === 1) weeks.push(x)
  const ref = (it: any) => ({ kind: 'calendar' as const, id: `${it.id}@${it.start}`, label: it.label })

  return (
    <div className="bk">
      <PanelOptions>
        <div className="seg">
          {[[42, '6 weeks'], [84, '12 weeks'], [182, '6 months'], [365, 'year']].map(([n, l]) => (
            <button key={n} className={span === n ? 'on' : ''} onClick={() => setOpts({ ...opts, span: n })}>{l}</button>
          ))}
        </div>
      </PanelOptions>
      {data.error && !d && <Problem error={data.error} />}
      {!d && !data.error && <Busy what="Reading the calendar" />}
      {d && temps && (
        <>
          <div className="bx-note">
            Weather replays Provo's observed {d.wx.weather_year_label} (NOAA, station PROVO BYU). Solid markers are published dates,
            hollow ones follow a yearly rule, dashed ones are our estimates. Drag across days to set the time window.
          </div>
          <div ref={wrap}>
            <svg width={W} height={H} style={{ display: 'block', touchAction: 'none' }}
              onPointerDown={e => { if (ptX(e) > LEFT) { (e.currentTarget as SVGElement).setPointerCapture(e.pointerId); const x = dayAt(ptX(e)); setDrag([x, x]) } }}
              onPointerMove={e => drag && setDrag([drag[0], dayAt(ptX(e))])}
              onPointerUp={() => { if (drag) { setSel({ time: [Math.min(...drag), Math.max(...drag)] }); setDrag(null) } }}
              onDoubleClick={() => setSel({ time: undefined })}>
              {weeks.map(x => (
                <g key={x} className="bd-axis">
                  <line x1={X(x)} x2={X(x)} y1={12} y2={H - 16} stroke="var(--grid)" />
                  {dw * 7 > 34 && <text x={X(x) + 2} y={10}>{dayWords(start, x)}</text>}
                </g>
              ))}
              {span >= 182 && weeks.filter((_, k) => k % 4 === 0).map(x => <text key={`m${x}`} className="bd-sub" x={X(x) + 2} y={10}>{dayWords(start, x)}</text>)}
              {/* terms and finals */}
              {(['BYU', 'UVU'] as const).map((sc, k) => (
                <g key={sc}>
                  <text x={0} y={yT + 11 + k * 18} className="bd-sub" style={{ fontSize: 11 }}>{sc}</text>
                  {(d.it.terms as any[]).filter(t => t.school === sc).map(t => (
                    <g key={t.name + t.start}>
                      <rect x={X(Math.max(a, t.start))} y={yT + k * 18} width={Math.max(0, X(Math.min(b, t.classes_end) + 1) - X(Math.max(a, t.start)))} height={14} rx={3} fill="var(--s1)" opacity={0.2}>
                        <title>{`${sc} ${t.name}: classes ${dayWords(start, t.start)} – ${dayWords(start, t.classes_end)} (${BASIS[t.basis] ?? t.basis})`}</title>
                      </rect>
                      {t.finals_start <= b && t.end >= a && <rect x={X(Math.max(a, t.finals_start))} y={yT + k * 18} width={Math.max(2, X(Math.min(b, t.end) + 1) - X(Math.max(a, t.finals_start)))} height={14} rx={3} fill="var(--s5)" opacity={0.55}>
                        <title>{`${sc} ${t.name} finals: ${dayWords(start, t.finals_start)} – ${dayWords(start, t.end)}`}</title>
                      </rect>}
                      {X(Math.min(b, t.classes_end)) - X(Math.max(a, t.start)) > 60 && <text className="blane-seg-t" x={X(Math.max(a, t.start)) + 4} y={yT + 11 + k * 18}>{t.name}</text>}
                    </g>
                  ))}
                </g>
              ))}
              {/* breaks, holidays and dated items */}
              <text x={0} y={yI + 4} className="bd-sub" style={{ fontSize: 11 }}>Events</text>
              {ranges.map(it => (
                <rect key={it.id + it.start} x={X(Math.max(a, it.day))} y={yI + 10} width={Math.max(2, X(Math.min(b, it.end_day) + 1) - X(Math.max(a, it.day)))} height={6} rx={3}
                  fill={kc(it.kind)} opacity={0.5} strokeDasharray={it.basis === 'hypothetical' ? '3 2' : undefined} stroke={it.basis === 'real' ? 'none' : kc(it.kind)}
                  style={{ cursor: 'pointer' }} onPointerDown={e => e.stopPropagation()} onClick={() => focusItem(setSel, ref(it))}
                  onMouseEnter={e => setTip({ x: e.clientX, y: e.clientY, t: it.label, s: `${dayWords(start, it.day)} – ${dayWords(start, it.end_day)} · ${BASIS[it.basis]}` })} onMouseLeave={() => setTip(null)} />
              ))}
              {devos.map(it => <rect key={it.id} x={X(it.day) + dw * 0.3} y={yI + 22} width={Math.max(1.5, dw * 0.4)} height={5} fill={kc('devotional')} opacity={0.6}>
                <title>{`${it.label} · ${dayWords(start, it.day)} 11:05 am`}</title></rect>)}
              {singles.map(it => {
                const on = focused === `${it.id}@${it.start}`
                return (
                  <circle key={it.id + it.start} cx={X(it.day) + dw / 2} cy={yI} r={on ? 6.5 : 5}
                    fill={it.basis === 'real' ? kc(it.kind) : 'var(--surface-1)'} stroke={kc(it.kind)} strokeWidth={on ? 2.5 : 1.6}
                    strokeDasharray={it.basis === 'hypothetical' ? '2 2' : undefined} style={{ cursor: 'pointer' }}
                    onPointerDown={e => e.stopPropagation()} onClick={() => focusItem(setSel, ref(it))}
                    onMouseEnter={e => setTip({ x: e.clientX, y: e.clientY, t: it.label, s: `${dayWords(start, it.day, true)}${it.time ? ` · ${it.time}` : ''} · ${BASIS[it.basis]}` })}
                    onMouseLeave={() => setTip(null)} />
                )
              })}
              {/* weather */}
              <text x={0} y={yW + 10} className="bd-sub" style={{ fontSize: 11 }}>{temps.hi}°F</text>
              <text x={0} y={yW + HW} className="bd-sub" style={{ fontSize: 11 }}>{temps.lo}°F</text>
              <path d={path('tmax_f')} fill="none" stroke="var(--s2)" strokeWidth={1.4} />
              <path d={path('tmin_f')} fill="none" stroke="var(--s1)" strokeWidth={1.2} opacity={0.8} />
              {temps.ds.map(r => (r.snow_in > 0 || r.precip_in >= 0.05) && (
                <rect key={r.day} x={X(r.day) + dw * 0.15} width={Math.max(1.5, dw * 0.7)} y={yW + HW + 4} height={Math.min(14, 3 + (r.snow_in > 0 ? r.snow_in * 2.5 : r.precip_in * 20))}
                  fill={r.snow_in > 0 ? 'var(--text-secondary)' : 'var(--s1)'} opacity={r.snow_in > 0 ? 0.7 : 0.6}>
                  <title>{`${r.date}: ${r.label} · high ${r.tmax_f}°F, low ${r.tmin_f}°F${r.precip_in ? ` · ${r.precip_in} in rain/melt` : ''}${r.snow_in ? ` · ${r.snow_in} in snow` : ''}`}</title>
                </rect>
              ))}
              <rect x={LEFT} y={yW} width={plotW} height={HW} fill="transparent"
                onMouseMove={e => { const r = temps.ds[dayAt(e.clientX - (e.currentTarget.ownerSVGElement as SVGElement).getBoundingClientRect().left) - a]; if (r) setTip({ x: e.clientX, y: e.clientY, t: `${r.label}: ${r.tmax_f}° / ${r.tmin_f}°F`, s: `${dayWords(start, r.day, true)}${r.snow_depth_in ? ` · ${r.snow_depth_in} in on the ground` : ''}` }) }}
                onMouseLeave={() => setTip(null)} />
              {win && <rect x={X(Math.min(...win))} width={Math.max(2, X(Math.max(...win) + 1) - X(Math.min(...win)))} y={12} height={H - 28} fill="var(--accent)" opacity={0.08} pointerEvents="none" />}
              {today >= a && today <= b && <line x1={X(today) + dw / 2} x2={X(today) + dw / 2} y1={12} y2={H - 16} stroke="var(--accent)" strokeDasharray="2 3" />}
            </svg>
          </div>
          <div className="bx-legend">
            <span><i className="bx-catdot" style={{ background: 'var(--s1)', opacity: 0.35 }} />classes</span>
            <span><i className="bx-catdot" style={{ background: 'var(--s5)', opacity: 0.7 }} />finals</span>
            <span><i className="bx-catdot" style={{ background: 'var(--s2)' }} />daily high</span>
            <span><i className="bx-catdot" style={{ background: 'var(--s1)' }} />low · rain</span>
            <span><i className="bx-catdot" style={{ background: 'var(--text-secondary)' }} />snow</span>
          </div>
          <div className="bx-h">Coming up</div>
          <div className="bk-list">
            {upcoming.map(it => (
              <div key={it.id + it.start} className={`bk-li click ${focused === `${it.id}@${it.start}` ? 'on' : ''}`} onClick={() => focusItem(setSel, ref(it))}>
                <span className="when">{dayWords(start, it.day)}{it.end_day > it.day ? `–${dayWords(start, it.end_day).replace(/^[A-Za-z]+ /, '')}` : ''}</span>
                <i className="bx-catdot" style={{ background: kc(it.kind) }} />
                <span className="grow"><b>{it.label}</b>{it.time && <span className="bx-note">{it.time}</span>}{it.place && <span className="bx-note">{it.place.name}</span>}</span>
                <span className={`bk-pill ${it.basis === 'real' ? 'yes' : 'quiet'}`} title={it.note ?? ''}>{BASIS[it.basis]}</span>
                {it.source && <a className="bx-note" href={it.source} target="_blank" rel="noreferrer" onClick={e => e.stopPropagation()}>source</a>}
              </div>
            ))}
          </div>
        </>
      )}
      {tip && <div className="bx-tip" style={{ left: tip.x + 12, top: tip.y + 12 }}><b>{tip.t}</b><br /><small>{tip.s}</small></div>}
    </div>
  )
}

export const tool: ToolDef = {
  id: 'calendar',
  label: 'Calendar',
  icon: 'clock',
  hint: 'The Provo year: terms and finals, holidays, games and conference, and the weather each day; click a day to set the time window.',
  group: 'world',
  order: 10,
  component: CalendarTool,
  size: { w: 8, h: 7 },
}
