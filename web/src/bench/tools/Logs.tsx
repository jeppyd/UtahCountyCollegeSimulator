// Logs: what the simulator has been doing and anything that went wrong, newest at the bottom: worlds built, runs
// started and stopped, unusually slow days and why, pages that failed or took long, errors with their details. Filter
// by how serious, search the words, copy them, or save a debug bundle to attach to a bug report.
import { useEffect, useMemo, useRef, useState } from 'react'
import { api, type LogLine } from '../../api'
import { Empty, Problem } from '../../kit/Bits'
import { useStore } from '../../store'
import { PanelOptions } from '../panel'
import type { PanelProps, ToolDef } from '../registry'

const LEVELS: [string, string][] = [['info', 'Everything'], ['warning', 'Warnings'], ['error', 'Errors']]
const KEEP = 2000

function LogsTool({ opts, setOpts }: PanelProps) {
  const level: string = opts.level ?? 'info'
  const running = useStore(s => s.status?.job?.state === 'running')
  const [lines, setLines] = useState<LogLine[]>([])
  const [err, setErr] = useState('')
  const [q, setQ] = useState('')
  const [open, setOpen] = useState<Record<number, boolean>>({})
  const next = useRef(-1)
  const box = useRef<HTMLDivElement>(null)
  const stick = useRef(true)

  useEffect(() => {
    let alive = true
    next.current = -1
    setLines([])
    const pull = async () => {
      try {
        const r = await api.logs(next.current, level)
        if (!alive) return
        setErr('')
        if (r.lines.length) setLines(old => [...old, ...r.lines].slice(-KEEP))
        next.current = Math.max(next.current, r.next - 1)
      } catch (e: any) { if (alive) setErr(String(e?.message ?? e)) }
    }
    pull()
    const t = window.setInterval(pull, running ? 1500 : 4000)
    return () => { alive = false; window.clearInterval(t) }
  }, [level, running])
  useEffect(() => { if (stick.current && box.current) box.current.scrollTop = box.current.scrollHeight }, [lines])

  const shown = useMemo(() => {
    const words = q.trim().toLowerCase().split(/\s+/).filter(Boolean)
    return words.length ? lines.filter(l => words.every(w => `${l.msg} ${l.source}`.toLowerCase().includes(w))) : lines
  }, [lines, q])
  const copy = () => navigator.clipboard?.writeText(shown.map(l => `${new Date(l.t * 1000).toLocaleString()} ${l.level.toUpperCase()} ${l.source}: ${l.msg}`).join('\n'))

  return (
    <div className="bk blg">
      <PanelOptions>
        <div className="seg">{LEVELS.map(([k, l]) => <button key={k} className={level === k ? 'on' : ''} onClick={() => setOpts({ ...opts, level: k })}>{l}</button>)}</div>
        <input type="search" placeholder="Find words" value={q} onChange={e => setQ(e.target.value)} style={{ width: 130 }} />
        <button className="btn small" onClick={copy} disabled={!shown.length} title="Copy the lines shown">Copy</button>
        <a className="btn small" href={api.debugBundleUrl} download title="A zip of versions, settings, timings and logs to attach to a bug report (no people, no survey data)">Save debug bundle</a>
      </PanelOptions>
      {err && !lines.length && <Problem error={err} />}
      {!err && !shown.length && <Empty title={lines.length ? 'Nothing matches' : 'Nothing logged yet'}>{lines.length ? 'Try other words.' : level === 'info' ? 'Build a world or run time and what happens shows up here.' : 'No problems so far.'}</Empty>}
      <div className="blg-list" ref={box} onScroll={e => { const el = e.currentTarget; stick.current = el.scrollHeight - el.scrollTop - el.clientHeight < 30 }}>
        {shown.map(l => {
          const [first, ...rest] = l.msg.split('\n')
          return (
            <div key={l.id} className={`blg-row ${l.level}`}>
              <time className="tabular">{new Date(l.t * 1000).toLocaleTimeString()}</time>
              <span className="blg-lv">{l.level === 'info' ? '' : l.level}</span>
              <span className="blg-msg">
                {first}{l.source !== 'simulator' && <small> · {l.source}</small>}
                {rest.length > 0 && <button className="blg-more" onClick={() => setOpen({ ...open, [l.id]: !open[l.id] })}>{open[l.id] ? 'hide details' : 'details'}</button>}
                {open[l.id] && <pre>{rest.join('\n')}</pre>}
              </span>
            </div>
          )
        })}
      </div>
      <div className="bx-note">Also saved on this computer in the app's <code>logs</code> folder (kept to about 8 MB).</div>
    </div>
  )
}

export const tool: ToolDef = {
  id: 'logs',
  label: 'Logs',
  icon: 'book',
  hint: 'What the simulator has been doing and anything that went wrong: runs, slow days and why, failed pages, errors with details.',
  group: 'world',
  order: 91,
  component: LogsTool,
  size: { w: 6, h: 7 },
}
