// Live news: as time runs, the biggest moments of the day pop up (engagements, weddings, baptisms,
// faith crises, graduations…), plus milestones as the What-if world drifts away from the Original.
import { useEffect, useRef } from 'react'
import { api, STATIC } from './api'
import { pairs } from './fields'
import { CatIcon, G, UBadge } from './game'
import { useLens, useStore } from './store'
import { Story } from './ui'

const MILESTONES = [0.01, 0.05, 0.1, 0.25, 0.5]

export function NewsWatcher() {
  const { dataVersion, status, news, toast, followed } = useStore()
  const { u } = useLens()
  const last = useRef<Record<string, number>>({})
  const lastShown = useRef(0)
  const milestone = useRef(-1)
  const forkKey = useRef<string>('')
  useEffect(() => {
    if (STATIC || !status) return
    const k = `${status.world_id}:${u}`
    let alive = true
    ;(async () => {
      if (last.current[k] === undefined) {
        const r = await api.events({ u, limit: 1 })
        last.current[k] = r.events?.[0]?.id ?? -1
        return
      }
      if (!news) { const r = await api.events({ u, limit: 1 }); last.current[k] = r.events?.[0]?.id ?? last.current[k]; return }
      const r = await api.events({ u, after_id: last.current[k], min_salience: 0.5, limit: 300 })
      if (!alive || !r.events?.length) return
      last.current[k] = Math.max(last.current[k], ...r.events.map((e: any) => e.id))
      const mine = new Set(followed())
      const seen = new Set<string>()
      const evs = r.events.filter((e: any) => {
        const key = e.b == null ? `${e.id}` : `${e.type}|${e.day}|${Math.min(e.a, e.b)}|${Math.max(e.a, e.b)}`
        if (seen.has(key)) return false
        seen.add(key)
        return mine.has(e.a) || mine.has(e.b) || e.salience >= 0.85
      })
      const now = performance.now()
      if (!evs.length || now - lastShown.current < 2200) return
      lastShown.current = now
      const pick = [...evs.filter((e: any) => mine.has(e.a) || mine.has(e.b)), ...evs.sort((a: any, b: any) => b.salience - a.salience)]
      const used = new Set<number>()
      let shown = 0
      for (const e of pick) {
        if (used.has(e.id) || shown >= 2) continue
        used.add(e.id)
        shown++
        const followedOne = mine.has(e.a) || mine.has(e.b)
        toast({ kind: 'event', title: e.label, body: JSON.stringify(e), category: e.category, route: ['person', String(followedOne && mine.has(e.b) ? e.b : e.a)], ttl: followedOne ? 10000 : 6500 })
      }
    })().catch(() => {})
    return () => { alive = false }
  }, [dataVersion, u])
  // the worlds drifting apart
  useEffect(() => {
    if (!status?.has_alt) { milestone.current = -1; forkKey.current = ''; return }
    const v = status.divergence?.any_state_diff ?? 0
    let m = -1
    MILESTONES.forEach((t, k) => { if (v >= t) m = k })
    const fk = `${status.world_id}:${status.fork_day}`
    if (fk !== forkKey.current) { forkKey.current = fk; milestone.current = m; return }   // no fanfare for where we start
    if (m > milestone.current) {
      if (news) toast({ kind: 'world', title: `The worlds are drifting apart: ${Math.round(100 * MILESTONES[m])}% of lives now differ`, body: 'Open the butterfly view to see who, where and why.', route: ['whatif'], ttl: 9000 })
      milestone.current = m
    }
  }, [status?.divergence?.any_state_diff, status?.has_alt])
  return null
}

const RECAP: [string, string][] = [['first_date', 'first dates'], ['relationship_started', 'new exclusive couples'], ['engaged', 'engagements'], ['wedding', 'weddings'],
  ['breakup_received', 'breakups'], ['new_friend', 'new friendships'], ['baptized', 'baptisms'], ['faith_crisis_start', 'faith crises'],
  ['mission_departure', 'mission departures'], ['graduation', 'graduations'], ['birth', 'babies'], ['moved', 'moves'], ['job_loss', 'jobs lost']]

/** After a time skip (a week or more), a recap of what happened while time flew. */
export function RecapWatcher() {
  const { status, toast, news } = useStore()
  const { u, hasAlt } = useLens()
  const start = useRef<{ day: number; div: number | null; total: number } | null>(null)
  const state = status?.job?.state
  useEffect(() => {
    if (STATIC || !status) return
    if (state === 'running' && !start.current) start.current = { day: status.day - (status.job?.progress ?? 0), div: status.divergence?.any_state_diff ?? null, total: status.job?.total ?? 0 }
    if (state !== 'running' && start.current) {
      const s0 = start.current
      start.current = null
      const days = status.day - s0.day
      if (days < 7 || !news) return
      api.eventsSummary(u, s0.day).then((sum: any) => {
        const rows = RECAP.map(([k, l]) => { const r = sum.types?.find((x: any) => x.type === k); const n = r ? pairs(k, r.count) : 0; return { k, l, n, c: r?.category } }).filter(r => r.n > 0).slice(0, 8)
        const d1 = status.divergence?.any_state_diff ?? null
        toast({ kind: 'recap', title: `${days} days went by`, body: JSON.stringify({ rows, from: s0.day, to: status.day, date0: dateOf(status, s0.day), date1: status.date, div: hasAlt && d1 !== null ? [s0.div, d1] : null, u }), route: ['world'], ttl: 15000 })
      }).catch(() => {})
    }
  }, [state, status?.day])
  return null
}
const dateOf = (status: any, day: number) => { const d = new Date(status.date + 'T12:00:00'); d.setDate(d.getDate() - (status.day - day)); return d.toISOString().slice(0, 10) }

export function Toasts() {
  const { toasts, dismiss, setRoute } = useStore()
  const { u, hasAlt } = useLens()
  if (!toasts.length) return null
  return (
    <div className="toasts" aria-live="polite">
      {toasts.map(t => {
        const e = t.kind === 'event' && t.body ? JSON.parse(t.body) : null
        if (t.kind === 'recap' && t.body) {
          const r = JSON.parse(t.body)
          const fd = (x: string) => new Date(x + 'T12:00:00').toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
          return (
            <div key={t.id} className="toast recap" onClick={() => { if (t.route) setRoute(t.route); dismiss(t.id) }} role="button" tabIndex={0}>
              <div className="t-body">
                <div className="t-meta small">While time flew · {fd(r.date0)} → {fd(r.date1)}{hasAlt && <> · <UBadge u={r.u} /></>}</div>
                <b>{t.title}</b>
                <div className="recap-grid">{r.rows.map((x: any) => <span key={x.k}><CatIcon c={x.c} /><b className="tabular">{x.n.toLocaleString()}</b> {x.l}</span>)}</div>
                {r.div && <div className="small" style={{ marginTop: 6 }}>{G.butterfly} Lives that differ: <b className="tabular">{r.div[0] === null ? '—' : `${(100 * r.div[0]).toFixed(1)}%`}</b> → <b className="tabular u-alt-t">{(100 * r.div[1]).toFixed(1)}%</b></div>}
              </div>
              <button className="t-x" onClick={ev => { ev.stopPropagation(); dismiss(t.id) }} aria-label="Dismiss">{G.close}</button>
            </div>
          )
        }
        return (
          <div key={t.id} className={`toast ${t.kind}`} onClick={() => { if (t.route) setRoute(t.route); dismiss(t.id) }} role="button" tabIndex={0}>
            {e ? <CatIcon c={t.category} /> : <span className="caticon c-intervention">{G.butterfly}</span>}
            <div className="t-body">
              {e ? <>
                <div className="t-meta small">{new Date(e.date + 'T12:00:00').toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric' })}{hasAlt && <> · <UBadge u={u} /></>}</div>
                <div className="t-story"><Story e={e} /></div>
              </> : <><b>{t.title}</b>{t.body && <div className="small secondary">{t.body}</div>}</>}
            </div>
            <button className="t-x" onClick={ev => { ev.stopPropagation(); dismiss(t.id) }} aria-label="Dismiss">{G.close}</button>
          </div>
        )
      })}
    </div>
  )
}
