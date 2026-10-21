// Speed: how long each simulated day took on this computer, which parts of the model took the time, and why some days
// are slower (Sunday night's weekly updates, the end of a month, a growing world). The chart is one bar per day, split
// by the biggest systems; the table below says where the time went over the last week. Save a debug bundle from here.
import { useMemo } from 'react'
import { api, type PerfDay } from '../../api'
import { axisStyle, cssVar, EChart, tokens } from '../../components'
import { useAsync } from '../../game'
import { Busy, Empty, Problem } from '../../kit/Bits'
import { useStore } from '../../store'
import { PanelOptions } from '../panel'
import type { PanelProps, ToolDef } from '../registry'

const TOP = 5                         // systems drawn on their own; the rest fold into "everything else"
export const secs = (s: number | null | undefined) => (s === null || s === undefined ? '—' : s < 10 ? `${s.toFixed(2)} s` : `${Math.round(s)} s`)
const mb = (m: number | null | undefined) => (!m ? '—' : m >= 1024 ? `${(m / 1024).toFixed(1)} GB` : `${Math.round(m)} MB`)
const pct = (x: number) => `${Math.round(100 * x)}%`

function SpeedTool({ opts, setOpts }: PanelProps) {
  const perfDay = useStore(s => s.status?.perf?.day)
  const hasWorld = useStore(s => !!s.status?.has_world)
  const world: 'base' | 'alt' = opts.world ?? 'base'
  const r = useAsync(() => api.perf(), [perfDay, hasWorld])
  const d = r.data
  const rows: PerfDay[] = d?.days ?? []
  const sysOf = (x: PerfDay) => (world === 'alt' ? x.alt_systems ?? {} : x.systems)

  // the systems that take the most time over the days shown, in a fixed order (colors follow the system)
  const top = useMemo(() => {
    const tot: Record<string, number> = {}
    for (const x of rows) for (const [k, v] of Object.entries(sysOf(x))) tot[k] = (tot[k] ?? 0) + v
    return Object.entries(tot).sort((a, b) => b[1] - a[1]).slice(0, TOP).map(([k]) => k)
  }, [rows, world])
  const week = useMemo(() => {
    const last = rows.slice(-7)
    const tot: Record<string, number> = {}
    for (const x of last) for (const [k, v] of Object.entries(sysOf(x))) tot[k] = (tot[k] ?? 0) + v / last.length
    const all = Object.values(tot).reduce((a, b) => a + b, 0)
    return { all, list: Object.entries(tot).sort((a, b) => b[1] - a[1]) }
  }, [rows, world])

  const option = useMemo(() => {
    if (!rows.length || !d) return null
    const t = tokens()
    const words = d.system_words
    const labels = rows.map(x => `${x.weekday} ${x.date.slice(5)}`)
    const color = [...top.map((_, k) => cssVar(`--s${k + 1}`)), cssVar('--text-muted')]
    const series = [...top, '_other'].map((k, j) => ({
      name: k === '_other' ? 'everything else' : words[k] ?? k, type: 'bar', stack: 'day', barMaxWidth: 18,
      itemStyle: { color: color[j], borderColor: t.surface, borderWidth: rows.length < 80 ? 1 : 0 },
      emphasis: { focus: 'series' },
      data: rows.map(x => {
        const s = sysOf(x)
        if (k !== '_other') return +(s[k] ?? 0).toFixed(4)
        return +Object.entries(s).filter(([n]) => !top.includes(n)).reduce((a, [, v]) => a + v, 0).toFixed(4)
      }),
    }))
    return {
      grid: { left: 40, right: 12, top: 50, bottom: 26 },
      legend: { top: 0, left: 0, itemWidth: 10, itemHeight: 10, textStyle: { color: t.text2, fontSize: 11 } },
      tooltip: {
        trigger: 'axis', axisPointer: { type: 'shadow' },
        formatter: (ps: any[]) => {
          const x = rows[ps[0].dataIndex]
          const tot = Object.values(sysOf(x)).reduce((a, b) => a + b, 0)
          const lines = ps.filter(p => p.value > 0).sort((a, b) => b.value - a.value)
            .map(p => `${p.marker}${p.seriesName}: ${secs(p.value)}`).join('<br/>')
          const per = x.periodic.map(p => d.periodic_words[p]).filter(Boolean)
          return `<b>${x.weekday} ${x.date}</b> · ${secs(tot)} for the ${world === 'alt' ? 'What-if' : 'Original'} world` +
            (world === 'base' && x.alt_s ? `<br/><span style="color:${t.muted}">What-if: ${secs(x.alt_s)}${x.parallel ? ' (on a second core, at the same time)' : ''}</span>` : '') +
            (per.length ? `<br/><span style="color:${t.muted}">${per.join('<br/>')}</span>` : '') + `<br/>${lines}`
        },
      },
      xAxis: { type: 'category', data: labels, ...axisStyle(), axisLabel: { ...axisStyle().axisLabel, hideOverlap: true } },
      yAxis: { type: 'value', ...axisStyle(), axisLabel: { ...axisStyle().axisLabel, formatter: (v: number) => `${v.toFixed(v < 1 ? 1 : 0)} s` } },
      series,
    }
  }, [rows, top, world, d])

  if (r.error && !d) return <Problem error={r.error} />
  if (!d) return <Busy what="Reading the timings" />
  const s = d.summary
  if (!rows.length) return <Empty title="No days timed yet">Run time forward (even one day) and every simulated day's time shows up here.</Empty>
  const last = rows[rows.length - 1]
  return (
    <div className="bk bsp">
      <PanelOptions>
        {d.has_alt && (
          <div className="seg">
            <button className={world === 'base' ? 'on' : ''} onClick={() => setOpts({ ...opts, world: 'base' })}>Original</button>
            <button className={world === 'alt' ? 'on' : ''} onClick={() => setOpts({ ...opts, world: 'alt' })}>What-if</button>
          </div>
        )}
        <a className="btn small" href={api.debugBundleUrl} download title="A zip of versions, settings, timings and logs to attach to a bug report (no people, no survey data)">Save debug bundle</a>
      </PanelOptions>
      <div className="bsp-tiles">
        <div><small>Last day</small><b className="tabular">{secs(last.wall_s)}</b><span>{last.weekday} {last.date}{last.alt_s ? ` · both worlds` : ''}</span></div>
        <div><small>Usual (last 7 days)</small><b className="tabular">{secs(s.mean7_s)}</b><span>{s.days_per_min ? `about ${Math.round(s.days_per_min)} days a minute` : ''}</span></div>
        <div><small>Memory</small><b className="tabular">{mb(last.rss_mb)}</b><span>{last.cpu_pct !== null ? `${Math.round(last.cpu_pct)}% of one core${last.parallel ? ' + a second core for the What-if' : ''}` : ''}</span></div>
      </div>
      {s.why_last && <div className="bx-note"><b>Why the last day took {secs(last.wall_s)}:</b> {s.why_last}.</div>}
      {s.trend && s.trend >= 1.25 && <div className="bx-note">Days now take {s.trend.toFixed(1)}× as long as in the first week timed: the world's records (plans, messages, memories) keep growing, and every part of the model reads more of them.</div>}
      {last.pace > 0 && <div className="bx-note">Time is running at a slow speed on purpose (at least {last.pace} s per day); these numbers are the work alone, without the waiting.</div>}
      {option && <EChart option={option} height={210} />}
      <div className="bx-h">Where the time went, last 7 days ({secs(week.all)} a day{world === 'alt' ? ', What-if world' : ''})</div>
      <table className="bsp-table">
        <tbody>
          {week.list.slice(0, 12).map(([k, v]) => (
            <tr key={k}>
              <td>{d.system_words[k] ?? k}<small> {k}</small></td>
              <td className="tabular">{secs(v)}</td>
              <td className="bsp-bar"><i style={{ width: pct(v / (week.list[0]?.[1] || 1)) }} /></td>
              <td className="tabular muted">{pct(v / (week.all || 1))}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="bx-note">Times are measured on this computer while the model runs; the browser's drawing isn't included. Slower days are normal on Sunday nights (weekly updates) and the last day of each month.</div>
    </div>
  )
}

export const tool: ToolDef = {
  id: 'speed',
  label: 'Speed',
  icon: 'clock',
  hint: 'How long each simulated day takes on this computer, which parts of the model take the time, and why some days are slower.',
  group: 'world',
  order: 90,
  component: SpeedTool,
  size: { w: 6, h: 8 },
}
