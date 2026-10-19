// "Describe it": type any What-if in plain language, tag the exact people, places and groups you mean, and an LLM
// (Claude through your Claude Code login, Codex through ChatGPT, or a local model) reads the model's lever catalog,
// checks its plan against the live world, and hands back a plan you can inspect, trim and run.
import { BACKEND_NAME, useAiSetup, useAiStatus } from '../../kit/AiSetup'
import { useEffect, useMemo, useRef, useState } from 'react'
import { api, STATIC } from '../../api'
import { G, useAsync } from '../../game'
import { timeCtl, useOutside } from '../../hud'
import { AskMsg, Mention, useStore, worldKey } from '../../store'

const EXAMPLES = [
  'The Church announces that alcohol is now permitted',
  'BYU revokes its beard ban',
  'Helaman Halls catches fire and burns down',
  'A snowstorm shuts down Provo for a week',
  'A wildly popular new dating app takes over campus',
  'Every UVU student gets free counseling',
  'Rent near BYU doubles overnight',
  'Pickleball becomes an obsession in Orem',
]
const KIND_ICON: Record<string, string> = {
  person: 'id', complex: 'home', venue: 'places', venue_type: 'places', ward: 'faith', employer: 'work', club: 'people', team: 'people',
  institute: 'school', congregation: 'faith', major: 'school', neighborhood: 'map', city: 'map', school: 'school', field: 'explore',
  event: 'events', rule: 'link', preset: 'butterfly',
}
const KIND_FILTERS: [string, string, string[]][] = [
  ['all', 'Anything', []], ['people', 'People', ['person']],
  ['places', 'Places', ['complex', 'venue', 'venue_type', 'neighborhood', 'city', 'school']],
  ['groups', 'Groups', ['ward', 'club', 'team', 'institute', 'congregation', 'employer', 'major']],
  ['concepts', 'Model', ['field', 'event', 'rule', 'preset']],
]
const DURATIONS: [number, string][] = [[0, 'just split'], [7, '1 week'], [30, '1 month'], [112, '1 semester'], [365, '1 year']]
const STEP_ICON: Record<string, string> = { start: 'spark', tool: 'search', found: 'link', note: 'mind', think: 'mind', fix: 'gear', done: 'spark' }

// ------------------------------------------------------------------ background polling (survives closing the drawer)
const polling = new Set<string>()
async function poll(at: number, job: string) {
  if (polling.has(job)) return
  polling.add(job)
  const { updateMsg } = useStore.getState()
  try {
    for (;;) {
      let v: any
      try { v = await api.whatifJob(job) } catch (e: any) {
        if (String(e?.message ?? e).includes('404')) { updateMsg(at, { state: 'error', error: 'The simulator restarted while this was being worked on. Send it again.' }); break }
        await new Promise(r => setTimeout(r, 2000)); continue
      }
      updateMsg(at, { state: v.state, steps: v.steps, elapsed: v.elapsed, backend: v.backend })
      if (v.state === 'done') {
        const r = v.result
        updateMsg(at, { text: r.plan.reply, plan: r.plan, receipt: r.receipt, errors: r.errors, warnings: r.warnings, ok: r.ok, planId: r.plan_id,
          include: r.plan.changes.map(() => true) })
        useStore.getState().toast({ kind: 'info', title: 'Your What-if plan is ready', body: r.plan.title, route: ['whatif'], ttl: 6000 })
        break
      }
      if (v.state === 'error' || v.state === 'cancelled') { updateMsg(at, { error: v.error === 'cancelled' ? 'Stopped.' : v.error }); break }
      await new Promise(r => setTimeout(r, 900))
    }
  } finally { polling.delete(job) }
}

const sending = new Set<number>()   // assistant messages whose compile request is still in flight (no job id yet)

export function AskPanel({ onDone }: { onDone?: () => void }) {
  const { ask, setAsk, status } = useStore()
  const hasAlt = !!status.has_alt
  const [mode, setMode] = useState<'new' | 'add'>(hasAlt ? 'add' : 'new')
  useEffect(() => setMode(hasAlt ? 'add' : 'new'), [hasAlt])
  const st = useAiStatus()
  const showSetup = useAiSetup(s => s.show)
  const endRef = useRef<HTMLDivElement>(null)
  const busy = ask.msgs.some(m => m.state === 'queued' || m.state === 'running')
  // resume watching jobs that were running before a reload or a drawer close
  useEffect(() => {
    for (const m of ask.msgs) {
      if (m.state !== 'running' && m.state !== 'queued') continue
      if (m.job) poll(m.at, m.job)
      else if (!sending.has(m.at)) useStore.getState().updateMsg(m.at, { state: 'error', error: 'Interrupted before it started. Send it again.' })
    }
  }, [])
  // a different world clears the conversation (its tags would point at other people and places)
  const wk = worldKey(status)
  useEffect(() => { if (status?.seed != null && ask.world !== wk) setAsk({}) }, [wk])
  useEffect(() => { endRef.current?.scrollIntoView({ block: 'nearest' }) }, [ask.msgs.length, ask.msgs[ask.msgs.length - 1]?.steps?.length])

  const send = async (text: string) => {
    const t = text.trim()
    const cur = useStore.getState().ask
    if (!t || cur.msgs.some(m => m.state === 'queued' || m.state === 'running')) return
    const mentions = cur.mentions
    const at = Date.now()
    const history = cur.msgs.flatMap((m): any[] => m.role === 'user' ? [{ role: 'user', text: m.text }]
      : m.plan ? [{ role: 'assistant', plan: m.plan }] : m.text ? [{ role: 'assistant', text: m.text }] : [])
    setAsk(a => ({ msgs: [...a.msgs, { role: 'user', text: t, mentions, at }, { role: 'assistant', text: '', at: at + 1, state: 'queued', steps: [] }], draft: '' }))
    sending.add(at + 1)
    try {
      const { job } = await api.whatifCompile({ text: t, mentions, history, mode })
      useStore.getState().updateMsg(at + 1, { job, state: 'running' })
      poll(at + 1, job)
    } catch (e: any) { useStore.getState().updateMsg(at + 1, { state: 'error', error: String(e?.message ?? e) }) }
    finally { sending.delete(at + 1) }
  }
  const s: any = st.data
  const ready = s?.ready
  const backendName = s ? BACKEND_NAME[s.settings?.backend] ?? '' : ''
  return (
    <div className="ask">
      <div className="ask-head">
        <div className="ask-title"><b>Describe your What-if</b><span className="small muted">Plain language. Tag the exact people and places you mean with @.</span></div>
        <span className="spacer" />
        {s && <button className={`pill ask-backend ${ready ? 'ok' : 'warn'}`} onClick={showSetup} title="Which model turns your words into changes">
          <i className="dot" />{backendName}{s.settings?.backend === 'claude' && s.settings?.claude_model ? ` · ${s.settings.claude_model}` : ''}{ready ? '' : ' · set up'}
        </button>}
        <button className="btn ghost small" onClick={showSetup} aria-label="Model settings">{G.gear}</button>
        {ask.msgs.length > 0 && <button className="btn ghost small" disabled={busy} onClick={() => setAsk({ msgs: [], mentions: [] })} title="Start a new conversation">New idea</button>}
      </div>
      {s && !ready && !ask.msgs.length && (
        <div className="ask-setup card flat">
          <b className="small">Connect an AI first</b>
          <p className="small muted" style={{ margin: '4px 0 8px' }}>Turning plain words into changes needs an AI model: Claude, ChatGPT, or a free model on this computer. A short guided setup walks you through it, no technical knowledge needed.</p>
          <button className="btn primary small" onClick={showSetup}>Set up an AI</button>
        </div>
      )}
      <div className="ask-thread">
        {ask.msgs.length === 0 && (
          <div className="ask-empty">
            <div className="ask-hero">{G.butterfly}<div><b>What would happen if…</b><p className="small muted">Anything at all. The model reads every lever the simulation has (policies, norms, places, events, people's traits), picks the ones your idea really touches, and shows you exactly what it will change before anything runs.</p></div></div>
            <div className="chips">{EXAMPLES.map(e => <button key={e} className="chip" disabled={STATIC} onClick={() => setAsk({ draft: e })}>{e}</button>)}</div>
          </div>
        )}
        {ask.msgs.map(m => m.role === 'user' ? <UserMsg key={m.at} m={m} /> : <ClaudeMsg key={m.at} m={m} mode={mode} onDone={onDone} onRetry={() => {
          const i = ask.msgs.findIndex(x => x.at === m.at); const u = ask.msgs[i - 1]
          if (u) { setAsk(a => ({ msgs: a.msgs.filter(x => x.at !== m.at && x.at !== u.at), mentions: u.mentions ?? [] })); window.setTimeout(() => send(u.text), 0) }
        }} />)}
        <div ref={endRef} />
      </div>
      {hasAlt && (
        <div className="row small" style={{ padding: '0 16px' }}>
          <div className="seg small-seg">
            <button className={mode === 'add' ? 'on' : ''} onClick={() => setMode('add')} title="Keep the running What-if and add these changes from today">Add to this What-if</button>
            <button className={mode === 'new' ? 'on' : ''} onClick={() => setMode('new')} title="Start over from the Original">Start a fresh What-if</button>
          </div>
        </div>
      )}
      <Composer onSend={send} busy={busy} refining={ask.msgs.some(m => m.plan)} mode={mode} />
      {STATIC && <p className="small muted" style={{ margin: '0 16px 12px' }}>Describing What-ifs needs the installed app.</p>}
    </div>
  )
}

function UserMsg({ m }: { m: AskMsg }) {
  return (
    <div className="ask-msg user">
      <div className="bubble">{m.text}
        {!!m.mentions?.length && <div className="ask-tags">{m.mentions.map(x => <span key={x.ref} className="tag">{G[KIND_ICON[x.kind] ?? 'link']}{x.label}</span>)}</div>}
      </div>
    </div>
  )
}

function ClaudeMsg({ m, mode, onDone, onRetry }: { m: AskMsg; mode: 'new' | 'add'; onDone?: () => void; onRetry: () => void }) {
  const running = m.state === 'queued' || m.state === 'running'
  const who = m.backend === 'codex' ? 'Codex' : m.backend === 'openai' ? 'Local model' : 'Claude'
  return (
    <div className="ask-msg claude">
      <div className="avatar-c">{G.butterfly}</div>
      <div className="bubble">
        {(running || (!!m.steps?.length && !m.plan)) && <Steps m={m} running={running} />}
        {running && m.job && <button className="btn ghost small" onClick={() => api.whatifCancel(m.job!)}>Stop</button>}
        {m.error && <div className="banner">{m.error} <button className="btn small" onClick={onRetry}>Try again</button></div>}
        {m.plan && <>
          <p className="ask-reply">{m.plan.reply}</p>
          <details className="ask-steps-done"><summary className="small muted">How {who} worked it out · {m.steps?.length ?? 0} steps · {Math.round(m.elapsed ?? 0)} s</summary><Steps m={m} running={false} /></details>
          <PlanCard m={m} mode={mode} onDone={onDone} />
        </>}
      </div>
    </div>
  )
}

function Steps({ m, running }: { m: AskMsg; running: boolean }) {
  const steps = (m.steps ?? []).filter(s => s.kind !== 'think' || running)
  return (
    <ol className={`ask-steps ${running ? 'live' : ''}`}>
      {steps.map((s, i) => (
        <li key={i} className={`k-${s.kind}`}><span className="si">{G[STEP_ICON[s.kind] ?? 'spark']}</span><span className="st">{s.text}</span><span className="sm tabular">{s.t.toFixed(0)}s</span></li>
      ))}
      {running && <li className="k-wait"><span className="si live-dot" /><span className="st muted">{steps.length ? 'Thinking…' : 'Starting…'}</span></li>}
    </ol>
  )
}

const KIND_LABEL: Record<string, string> = { world: 'Rule', nudge: 'Nudge', event: 'Event', shock: 'Event', trait: 'People', param: 'Mechanism', close: 'Closure', place: 'Place', practice: 'Spreads', venue: 'New place' }

function PlanCard({ m, mode, onDone }: { m: AskMsg; mode: 'new' | 'add'; onDone?: () => void }) {
  const { status, updateMsg, refreshStatus, setLens, setRoute } = useStore()
  const [days, setDays] = useState(30)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const [json, setJson] = useState(false)
  const p = m.plan
  const include: boolean[] = m.include ?? p.changes.map(() => true)
  const rows: any[] = m.receipt ?? []
  const okRows = rows.filter(r => r.ok)
  const n = include.filter(Boolean).length
  const apply = async (how: 'new' | 'add') => {
    setBusy(true); setErr('')
    try {
      if (useStore.getState().status?.job?.state === 'running') { await api.cancel(); await timeCtl.waitIdle() }
      await api.whatifApply({ plan: p, plan_id: m.planId, mode: how, include })
      updateMsg(m.at, { applied: how })
      await refreshStatus()
      setLens('compare')
      setRoute(['whatif', 'overview'])
      if (days > 0) await timeCtl.step({ days })
      onDone?.()
    } catch (e: any) { setErr(String(e?.message ?? e)) }
    setBusy(false)
  }
  return (
    <div className="plan">
      <div className="plan-head">
        <div><div className="eyebrow">The plan</div><b className="plan-title">{p.title}</b></div>
        <span className="spacer" />
        <span className={`conf ${p.confidence === 'high' ? 'plausible' : p.confidence === 'low' ? 'speculative' : 'hypothetical'}`} title="How confident the model is that these levers capture your idea">{p.confidence} fit</span>
        <span className="ev speculative" title="Compiled What-ifs are your scenario: treat effect sizes as speculative">speculative</span>
      </div>
      <div className="plan-changes">
        {okRows.map((r, k) => {
          const on = include[k]
          return (
            <label key={k} className={`pchange ${on ? 'on' : ''}`}>
              <input type="checkbox" checked={on} disabled={!!m.applied} onChange={e => updateMsg(m.at, { include: include.map((x, j) => (j === k ? e.target.checked : x)) })} />
              <div className="pc-main">
                <div className="row" style={{ gap: 6 }}><span className={`pc-kind k-${r.kind}`}>{KIND_LABEL[r.kind] ?? r.kind}</span><b>{r.label}</b></div>
                <div className="small">{r.summary}</div>
                <div className="small muted">{r.who !== 'everyone' || r.n != null ? <>For <b>{r.who}</b>{r.n != null && r.n >= 0 ? <> · {r.n.toLocaleString()} {r.n === 1 ? 'person' : 'people'} now</> : null} · </> : null}{r.when}</div>
                {r.why && <div className="small secondary pc-why">{r.why}</div>}
                {r.warnings?.map((w: string, i: number) => <div key={i} className="small pc-warn">⚠ {w}</div>)}
              </div>
            </label>
          )
        })}
        {rows.filter(r => !r.ok).map((r, k) => <div key={`x${k}`} className="pchange bad"><div className="pc-main"><b>{r.label}</b>{r.errors?.map((e: string, i: number) => <div key={i} className="small pc-err">✕ {e}</div>)}</div></div>)}
      </div>
      {(p.not_modeled?.length > 0 || p.assumptions?.length > 0 || p.expectations?.length > 0) && (
        <div className="plan-notes">
          {p.expectations?.length > 0 && <details open><summary><b className="small">What it expects to happen</b></summary><ul className="small">{p.expectations.map((e: any, i: number) => <li key={i}><span className={`dir ${e.direction}`}>{e.direction === 'up' ? '↑' : e.direction === 'down' ? '↓' : '?'}</span> {e.text}</li>)}</ul>
            <p className="small muted" style={{ margin: 0 }}>Run it and the What-if page checks these predictions against the simulation.</p></details>}
          {p.not_modeled?.length > 0 && <details><summary><b className="small">Not in the model ({p.not_modeled.length})</b></summary><ul className="small">{p.not_modeled.map((x: any, i: number) => <li key={i}><b>{x.aspect}</b>: {x.approximation}</li>)}</ul></details>}
          {p.assumptions?.length > 0 && <details><summary><b className="small">Assumptions ({p.assumptions.length})</b></summary><ul className="small">{p.assumptions.map((x: string, i: number) => <li key={i}>{x}</li>)}</ul></details>}
          {p.questions?.length > 0 && <div className="small"><b>Worth deciding:</b> {p.questions.join(' · ')}</div>}
        </div>
      )}
      {m.applied ? (
        <div className="small plan-applied">✓ {m.applied === 'add' ? 'Added to the What-if' : 'The world split with this plan'}. <button className="linkish" onClick={() => setRoute(['whatif', 'overview'])}>See the butterfly effect →</button></div>
      ) : (
        <div className="plan-foot">
          <span className="small muted">then run</span>
          <div className="seg small-seg">{DURATIONS.map(([d, l]) => <button key={d} className={days === d ? 'on' : ''} onClick={() => setDays(d)}>{l}</button>)}</div>
          <span className="spacer" />
          <button className="btn ghost small" onClick={() => setJson(!json)}>{json ? 'Hide' : 'JSON'}</button>
          {status.has_alt && <button className="btn" disabled={!n || busy || STATIC} onClick={() => apply(mode === 'add' ? 'add' : 'new')}>{mode === 'add' ? 'Add to What-if' : 'Start a new What-if'}</button>}
          <button className="btn primary big" disabled={!n || busy || STATIC} onClick={() => apply(status.has_alt && mode === 'add' ? 'add' : 'new')}>{busy ? 'Applying…' : status.has_alt ? (mode === 'add' ? 'Add & run ▶' : 'Split again ▶') : 'Split the world ▶'}</button>
        </div>
      )}
      {json && <pre className="plan-json">{JSON.stringify(p, null, 1)}</pre>}
      {err && <div className="banner">{err}</div>}
    </div>
  )
}

// ------------------------------------------------------------------ composer with @-mentions
function Composer({ onSend, busy, refining, mode }: { onSend: (t: string) => void; busy: boolean; refining: boolean; mode: 'new' | 'add' }) {
  const { ask, setAsk, addMention, removeMention } = useStore()
  const ta = useRef<HTMLTextAreaElement>(null)
  const [pick, setPick] = useState<null | { start: number; q: string }>(null)   // start = index of '@' (-1: opened by button)
  const [kind, setKind] = useState('all')
  const [found, setFound] = useState<{ key: string; rows: any[] }>({ key: '', rows: [] })
  const [sel, setSel] = useState(0)
  const wrap = useRef<HTMLDivElement>(null)
  useOutside(wrap, () => setPick(null))
  const kinds = useMemo(() => KIND_FILTERS.find(k => k[0] === kind)?.[2] ?? [], [kind])
  const qkey = pick ? `${pick.q}|${kind}|${mode}` : ''
  const current = found.key === qkey
  const hits = current ? found.rows : []
  useEffect(() => {
    if (!pick) return
    let live = true      // a slower answer to an earlier query must not replace this one
    const t = window.setTimeout(() => api.entities(pick.q, kinds, 10, mode)
      .then(r => { if (live) { setFound({ key: qkey, rows: r as any[] }); setSel(0) } })
      .catch(() => { if (live) setFound({ key: qkey, rows: [] }) }), 140)
    return () => { live = false; window.clearTimeout(t) }
  }, [qkey])
  const onChange = (v: string) => {
    setAsk({ draft: v })
    const caret = ta.current?.selectionStart ?? v.length
    const before = v.slice(0, caret)
    const i = before.lastIndexOf('@')
    if (i >= 0 && (i === 0 || /\s|\(/.test(before[i - 1])) && !/\n/.test(before.slice(i)) && before.length - i <= 40) setPick({ start: i, q: before.slice(i + 1) })
    else if (pick && pick.start >= 0) setPick(null)
  }
  const choose = (r: any) => {
    const m: Mention = { ref: r.ref, kind: r.kind, label: r.label, sub: r.sub, n: r.n }
    addMention(m)
    if (pick && pick.start >= 0) {
      const v = ask.draft
      setAsk({ draft: v.slice(0, pick.start) + r.label + ' ' + v.slice(pick.start + 1 + pick.q.length) })
    }
    setPick(null)
    window.setTimeout(() => ta.current?.focus(), 0)
  }
  const onKey = (e: React.KeyboardEvent) => {
    if (e.nativeEvent.isComposing || e.keyCode === 229) return       // the IME is still composing a word
    if (pick) {
      if (hits.length && e.key === 'ArrowDown') { e.preventDefault(); setSel((sel + 1) % hits.length); return }
      if (hits.length && e.key === 'ArrowUp') { e.preventDefault(); setSel((sel - 1 + hits.length) % hits.length); return }
      if (e.key === 'Enter' || e.key === 'Tab') {      // picks a result for what's typed now; never sends while the picker is open
        e.preventDefault()
        if (hits[sel]) choose(hits[sel])
        else if (e.key === 'Enter') setPick(null)
        return
      }
    }
    if (e.key === 'Escape' && pick) { e.preventDefault(); e.stopPropagation(); setPick(null); return }
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); onSend(ask.draft) }
  }
  return (
    <div className="ask-composer" ref={wrap}>
      {ask.mentions.length > 0 && (
        <div className="ask-tags">{ask.mentions.map(m => <span key={m.ref} className="tag" title={m.sub}>{G[KIND_ICON[m.kind] ?? 'link']}{m.label}<button onClick={() => removeMention(m.ref)} aria-label={`remove ${m.label}`}>×</button></span>)}</div>
      )}
      <div className="ask-input">
        <textarea ref={ta} rows={2} value={ask.draft} disabled={STATIC} placeholder={refining ? 'Refine it: "make it stronger", "only freshmen", "also close the Creamery"… or describe a new idea' : 'What if… (type @ to tag a person, place, ward, club, major, rule…)'}
          onChange={e => onChange(e.target.value)} onKeyDown={onKey} aria-label="Describe your What-if" />
        <div className="ask-actions">
          <button className="btn ghost small" disabled={STATIC} onClick={() => { setPick(pick ? null : { start: -1, q: '' }); window.setTimeout(() => (document.querySelector('.ask-picker input') as HTMLInputElement)?.focus(), 0) }} title="Tag something in the world">{G.at} Tag</button>
          <button className="btn primary" disabled={busy || !ask.draft.trim() || STATIC} onClick={() => onSend(ask.draft)}>{G.send} {busy ? 'Thinking…' : 'Send'}</button>
        </div>
      </div>
      {pick && (
        <div className="ask-picker">
          <div className="row" style={{ gap: 6 }}>
            {pick.start < 0 && <input autoFocus type="search" placeholder="Search people, places, groups, rules…" value={pick.q}
              onChange={e => setPick({ start: -1, q: e.target.value })} onKeyDown={onKey} style={{ flex: 1, minWidth: 160 }} />}
            <div className="seg small-seg">{KIND_FILTERS.map(([k, l]) => <button key={k} className={kind === k ? 'on' : ''} onMouseDown={e => e.preventDefault()} onClick={() => setKind(k)}>{l}</button>)}</div>
          </div>
          <div className="ask-hits">
            {hits.length === 0 && <div className="small muted" style={{ padding: 8 }}>{!current ? 'Searching…' : pick.q ? 'Nothing matches yet.' : 'Start typing a name.'}</div>}
            {hits.map((r, i) => (
              <button key={r.ref} className={`pal-item ${i === sel ? 'on' : ''}`} onMouseDown={e => e.preventDefault()} onClick={() => choose(r)} onMouseEnter={() => setSel(i)}>
                <span className="pal-icon">{G[KIND_ICON[r.kind] ?? 'link']}</span>
                <span className="pal-text"><b>{r.label}</b><small>{r.sub}</small></span>
                <span className="pal-kind">{r.kind.replace('_', ' ')}</span>
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

// ------------------------------------------------------------------ setup
