import { useEffect, useMemo, useState } from 'react'
import { fmt, pct, values } from '../analysis'
import { api } from '../api'
import { axisStyle, EChart, PersonLink, series as seriesColor, Tile, tokens } from '../components'
import { loadColumns, useStore } from '../store'

const SERIES: [string, string][] = [
  ['loneliness', 'Loneliness'], ['mood', 'Mood (happiness)'], ['stress', 'Stress'], ['dates_30d', 'Dates in last 30 days'],
  ['attend_rate', 'Sacrament attendance rate'], ['faith_belief', 'Belief in doctrine'], ['rel_status=married', 'Married share'],
  ['rel_status=dating', 'In an exclusive relationship'], ['financial_stress', 'Financial stress'], ['romantic_longing', 'Romantic longing'],
  ['depressive_episode', 'In a depressive episode'], ['coffee', 'Coffee use (0–3)'],
]

export function dayToDate(start: string, day: number) {
  const d = new Date(start + 'T12:00:00')
  d.setDate(d.getDate() + day)
  return d.toISOString().slice(0, 10)
}

export function TSChart({ data, v, label, height = 170, startDate, forkDay }: { data: any; v: string; label: string; height?: number; startDate: string; forkDay?: number | null }) {
  const opt = useMemo(() => {
    const t = tokens()
    const ax = axisStyle()
    const base = data?.base
    if (!base || !base[v]) return null
    const series: any[] = [{ name: 'Baseline', type: 'line', showSymbol: false, lineStyle: { width: 2 }, data: base.day.map((d: number, k: number) => [dayToDate(startDate, d), base[v][k]]) }]
    if (data.alt && data.alt[v]) series.push({ name: 'Intervention', type: 'line', showSymbol: false, lineStyle: { width: 2 }, data: data.alt.day.map((d: number, k: number) => [dayToDate(startDate, d), data.alt[v][k]]) })
    if (forkDay !== null && forkDay !== undefined && data.alt) series[0].markLine = { symbol: 'none', silent: true, lineStyle: { color: t.muted, type: 'solid', width: 1 }, label: { formatter: 'fork', color: t.muted, fontSize: 10 }, data: [{ xAxis: dayToDate(startDate, forkDay) }] }
    return {
      grid: { left: 44, right: 12, top: series.length > 1 ? 28 : 14, bottom: 22 },
      legend: series.length > 1 ? { top: 0, right: 0, textStyle: { color: t.text2, fontSize: 11 }, icon: 'roundRect', itemHeight: 3, itemWidth: 14 } : undefined,
      tooltip: { trigger: 'axis', valueFormatter: (x: number) => fmt(x, 3) },
      xAxis: { type: 'time', ...ax, splitLine: { show: false } },
      yAxis: { type: 'value', scale: true, ...ax },
      series,
    }
  }, [data, v, startDate, forkDay])
  return (
    <div className="card">
      <h3>{label}</h3>
      {opt ? <EChart option={opt} height={height} /> : <div className="empty small">no data yet — advance the clock</div>}
    </div>
  )
}

export default function Overview() {
  const { status, dataVersion, universe, setRoute } = useStore()
  const [ts, setTs] = useState<any>(null)
  const [tiles, setTiles] = useState<any>(null)
  const [feed, setFeed] = useState<any[]>([])
  const [acts, setActs] = useState<any>(null)
  const [origins, setOrigins] = useState<any>(null)
  const startDate = useMemo(() => dayToDate(status.date, -status.day), [status.date, status.day])
  useEffect(() => {
    api.timeseries(SERIES.map(s => s[0])).then(setTs).catch(() => {})
    api.events({ min_salience: 0.75, limit: 30, u: universe }).then(r => setFeed(r.events)).catch(() => {})
    api.origins(false, universe).then(setOrigins).catch(() => {})
    ;(async () => {
      const c = await loadColumns(['present', 'rel_status', 'dates_30d', 'loneliness', 'activity', 'n_friends', 'activity_now', 'lds_member', 'mood'], universe)
      const pres = c.present.data as Uint8Array
      const n = pres.length
      let P = 0, married = 0, single = 0, dates = 0, lon = 0, active = 0, lds = 0, fr = 0, mood = 0
      const st = c.rel_status, cats = st.categories!
      const mi = cats.indexOf('married'), si = cats.indexOf('single'), ti = cats.indexOf('talking')
      const ac = c.activity.categories!.indexOf('active')
      const actCounts = new Array(c.activity_now.categories!.length).fill(0)
      for (let i = 0; i < n; i++) {
        if (!pres[i]) continue
        P++
        if (st.data[i] === mi) married++
        if (st.data[i] === si || st.data[i] === ti) { single++; dates += c.dates_30d.data[i] }
        lon += c.loneliness.data[i]; mood += c.mood.data[i]
        if (c.lds_member.data[i]) { lds++; if (c.activity.data[i] === ac) active++ }
        fr += c.n_friends.data[i]
        actCounts[c.activity_now.data[i]]++
      }
      setTiles({ P, married: married / P, dates: dates / Math.max(single, 1), lon: lon / P, active: active / Math.max(lds, 1), fr: fr / P, mood: mood / P })
      setActs({ cats: c.activity_now.categories, counts: actCounts, P })
    })().catch(() => {})
  }, [dataVersion, universe])

  const actOpt = useMemo(() => {
    if (!acts) return null
    const ax = axisStyle()
    const order = acts.counts.map((v: number, k: number) => [acts.cats[k], v]).filter((r: any) => r[1] > 0 && r[0] !== 'away').sort((a: any, b: any) => b[1] - a[1])
    return {
      grid: { left: 110, right: 40, top: 6, bottom: 6 },
      tooltip: { trigger: 'item', formatter: (p: any) => `${p.name}: ${p.value.toLocaleString()} (${(100 * p.value / acts.P).toFixed(1)}%)` },
      xAxis: { type: 'value', show: false },
      yAxis: { type: 'category', inverse: true, data: order.map((r: any) => r[0].replace('_', ' ')), ...ax, axisLine: { show: false } },
      series: [{ type: 'bar', barWidth: 14, data: order.map((r: any) => r[1]), itemStyle: { borderRadius: [0, 4, 4, 0] }, label: { show: true, position: 'right', color: tokens().text2, fontSize: 11, formatter: (p: any) => p.value.toLocaleString() } }],
    }
  }, [acts])

  const origOpt = useMemo(() => {
    if (!origins) return null
    const ax = axisStyle()
    const rows = Object.entries(origins).filter(([k]) => k !== 'preexisting').sort((a: any, b: any) => b[1] - a[1]) as [string, number][]
    return {
      grid: { left: 90, right: 40, top: 6, bottom: 6 },
      tooltip: { trigger: 'item' },
      xAxis: { type: 'value', show: false },
      yAxis: { type: 'category', inverse: true, data: rows.map(r => r[0]), ...ax, axisLine: { show: false } },
      series: [{ type: 'bar', barWidth: 14, data: rows.map(r => r[1]), itemStyle: { color: seriesColor(2), borderRadius: [0, 4, 4, 0] }, label: { show: true, position: 'right', color: tokens().text2, fontSize: 11 } }],
    }
  }, [origins])

  return (
    <div className="page">
      <h1>A living synthetic society</h1>
      <p className="sub">
        {status.present?.toLocaleString()} simulated students, spouses, young adults, faculty and neighbors living in real Provo and Orem housing,
        meeting in classes, wards, FHE groups, apartments, workplaces and on apps. Every number below emerges from individual behavior —
        click anything to see who and why.
      </p>
      {tiles && (
        <div className="grid g6" style={{ marginBottom: 14 }}>
          <Tile label="People present" value={tiles.P.toLocaleString()} />
          <Tile label="Married" value={pct(tiles.married)} />
          <Tile label="Dates / month (singles)" value={fmt(tiles.dates, 2)} />
          <Tile label="Mean loneliness (0–1)" value={fmt(tiles.lon, 3)} />
          <Tile label="Active among members" value={pct(tiles.active)} />
          <Tile label="Friends per person" value={fmt(tiles.fr, 1)} />
        </div>
      )}
      <div className="grid g3">
        {SERIES.map(([v, l]) => <TSChart key={v} data={ts} v={v} label={l} startDate={startDate} forkDay={status.fork_day} />)}
      </div>
      <div className="grid g3" style={{ marginTop: 14 }}>
        <div className="card">
          <h3>Right now</h3>
          <p className="hint">What everyone is doing in the current block of the day.</p>
          {actOpt && <EChart option={actOpt} height={260} />}
        </div>
        <div className="card">
          <h3>Where new relationships began</h3>
          <p className="hint">Meeting context of every tie formed during the simulation (friends and acquaintances).</p>
          {origOpt && <EChart option={origOpt} height={260} />}
        </div>
        <div className="card">
          <div className="card-head"><div><h3>Life events</h3><p className="hint">Recent salient moments. Click a person.</p></div>
            <button className="btn small" onClick={() => setRoute(['events'])}>All events</button></div>
          <div className="scroll" style={{ maxHeight: 260 }}>
            {feed.map(e => (
              <div key={e.id} className="small" style={{ padding: '4px 0', borderBottom: '1px solid var(--grid)' }}>
                <span className="muted tabular">{e.date}</span> · <PersonLink id={e.a} name={e.a_name} /> — {e.label.toLowerCase()}
                {e.b_name && <> · <PersonLink id={e.b} name={e.b_name} /></>}
              </div>
            ))}
            {!feed.length && <div className="empty small">Advance the clock to watch lives unfold.</div>}
          </div>
        </div>
      </div>
    </div>
  )
}
