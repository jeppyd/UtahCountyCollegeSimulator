// Search anything (Ctrl K or /): fields, people, places, pages, what-ifs, event types and actions.
import { useEffect, useMemo, useRef, useState } from 'react'
import { api, STATIC } from './api'
import { catalog } from './fields'
import { G } from './game'
import { timeCtl } from './hud'
import { NAV } from './nav'
import { useLens, useStore } from './store'

type Item = { kind: string; label: string; sub?: string; icon: string; run: () => void; key: string }

function subScore(q: string, s: string) {
  const i = s.toLowerCase().indexOf(q)
  return i < 0 ? 0 : i === 0 || /\W/.test(s[i - 1]) ? 40 : 25
}

function score(q: string, s: string) {
  const a = s.toLowerCase()
  if (!q) return 1
  if (a.startsWith(q)) return 100 - a.length / 100
  const i = a.indexOf(q)
  if (i > 0 && /\W/.test(a[i - 1])) return 80 - i / 100
  if (i >= 0) return 60 - i / 100
  // subsequence
  let k = 0
  for (const ch of a) if (ch === q[k]) k++
  return k === q.length ? 20 : 0
}

export function Palette() {
  const { palette, setPalette, registry, presets, setRoute, setLens, openDrawer, theme, setTheme, news, setNews } = useStore()
  const { hasAlt } = useLens()
  const [q, setQ] = useState('')
  const [sel, setSel] = useState(0)
  const [people, setPeople] = useState<any[]>([])
  const [complexes, setComplexes] = useState<any[]>([])
  const input = useRef<HTMLInputElement>(null)
  useEffect(() => { if (palette) { setQ(''); setSel(0); setTimeout(() => input.current?.focus(), 10) } }, [palette])
  useEffect(() => { if (palette && !complexes.length) api.complexes('age', 'base').then(setComplexes).catch(() => {}) }, [palette])
  useEffect(() => {
    if (!palette || STATIC || q.trim().length < 2) { setPeople([]); return }
    const t = setTimeout(() => api.searchPeople(q.trim()).then(setPeople).catch(() => setPeople([])), 160)
    return () => clearTimeout(t)
  }, [q, palette])
  const close = () => setPalette(false)
  const all = useMemo<Item[]>(() => {
    if (!registry) return []
    const go = (r: string[]) => () => { setRoute(r); close() }
    const out: Item[] = []
    for (const g of NAV) for (const n of g.items) out.push({ kind: 'Go to', label: n.label, sub: n.hint, icon: n.icon, run: go([n.id]), key: `nav:${n.id}` })
    const act = (label: string, sub: string, icon: string, fn: () => any) => out.push({ kind: 'Action', label, sub, icon, run: () => { close(); Promise.resolve().then(fn).catch((err: any) => useStore.getState().toast({ kind: 'info', title: String(err?.message ?? err), ttl: 6000 })) }, key: `act:${label}` })
    if (!STATIC) {
      act('Play', 'Run time at your last speed', 'play', () => timeCtl.play())
      act('Pause', 'Stop time', 'pause', () => timeCtl.pause())
      act('+1 day', 'Advance one day', 'step', () => timeCtl.step({ days: 1 }))
      act('+1 week', 'Advance one week', 'step', () => timeCtl.step({ days: 7 }))
      act('+1 month', 'Advance 30 days', 'step', () => timeCtl.step({ days: 30 }))
      act('+1 semester', 'Advance about 16 weeks', 'step', () => timeCtl.step({ days: 112 }))
      act('Make a change (what if…?)', 'Split the world and change something in one copy', 'butterfly', () => openDrawer({}))
    }
    if (hasAlt) {
      act('Show the Original world', 'Every page shows the world without your change', 'globe', () => setLens('base'))
      act('Show the What-if world', 'Every page shows the world with your change', 'butterfly', () => setLens('alt'))
      act('Compare both worlds', 'Pages show Original and What-if side by side', 'butterfly', () => setLens('compare'))
    }
    act(theme === 'dark' ? 'Light theme' : 'Dark theme', 'Switch colors', 'moon', () => setTheme(theme === 'dark' ? 'light' : 'dark'))
    act(news ? 'Mute news pop-ups' : 'Show news pop-ups', 'Big moments pop up as time runs', 'bell', () => setNews(!news))
    for (const { drawer, fields } of catalog(registry)) for (const f of fields)
      out.push({ kind: 'Field', label: f.label, sub: `${drawer.label}${f.desc ? ' · ' + f.desc : ''}`, icon: drawer.icon, run: go(['explore', f.id]), key: `f:${f.id}` })
    if (presets && !STATIC) for (const [id, p] of Object.entries(presets) as any)
      out.push({ kind: 'What if', label: p.name, sub: p.description, icon: 'butterfly', run: () => { close(); openDrawer({ preset: id }) }, key: `w:${id}` })
    for (const e of Object.values(registry.events) as any[])
      out.push({ kind: 'Event', label: e.label, sub: `Every “${e.label.toLowerCase()}” in the world`, icon: 'events', run: go(['events', 'type', e.id]), key: `e:${e.id}` })
    for (const c of complexes) out.push({ kind: 'Place', label: c.name, sub: `${(c.kind ?? '').replace(/_/g, ' ')} · ${c.n} residents`, icon: 'places', run: go(['places', 'complex', String(c.id)]), key: `c:${c.id}` })
    out.push({ kind: 'Place', label: 'BYU', sub: 'Brigham Young University', icon: 'school', run: go(['places', 'school', '1']), key: 'school:1' })
    out.push({ kind: 'Place', label: 'UVU', sub: 'Utah Valley University', icon: 'school', run: go(['places', 'school', '2']), key: 'school:2' })
    return out
  }, [registry, presets, complexes, hasAlt, theme, news])
  const items = useMemo(() => {
    const ql = q.trim().toLowerCase()
    const ppl: Item[] = people.map(p => ({ kind: 'Person', label: p.name, sub: `#${p.id}`, icon: 'people', run: () => { setRoute(['person', String(p.id)]); close() }, key: `p:${p.id}` }))
    if (!ql) return all.filter(i => i.kind === 'Go to' || i.kind === 'Action').slice(0, 40)
    return [...ppl, ...all].map(i => { const base = Math.max(score(ql, i.label), 0.6 * subScore(ql, i.sub ?? '')); return { i, s: base > 0 ? base + (i.kind === 'Field' ? 3 : i.kind === 'Go to' ? 4 : i.kind === 'Person' ? 5 : 0) : 0 } })
      .filter(x => x.s > 12).sort((a, b) => b.s - a.s).slice(0, 60).map(x => x.i)
  }, [q, all, people])
  useEffect(() => { setSel(0) }, [q])
  if (!palette) return null
  return (
    <div className="modal-backdrop pal-back" onMouseDown={close}>
      <div className="palette" role="dialog" aria-label="Search" onMouseDown={e => e.stopPropagation()}>
        <div className="pal-input">{G.search}
          <input ref={input} value={q} onChange={e => setQ(e.target.value)} placeholder="Search fields, people, places, what-ifs, events, pages…"
            onKeyDown={e => {
              if (e.key === 'Escape') close()
              if (e.key === 'ArrowDown') { e.preventDefault(); setSel(Math.min(items.length - 1, sel + 1)) }
              if (e.key === 'ArrowUp') { e.preventDefault(); setSel(Math.max(0, sel - 1)) }
              if (e.key === 'Enter' && items[sel]) items[sel].run()
            }} />
          <kbd>Esc</kbd>
        </div>
        <div className="pal-list">
          {items.map((it, k) => (
            <button key={it.key} className={`pal-item ${k === sel ? 'on' : ''}`} onMouseEnter={() => setSel(k)} onClick={() => it.run()}>
              <span className="pal-icon">{G[it.icon] ?? G.spark}</span>
              <span className="pal-text"><b>{it.label}</b>{it.sub && <small>{it.sub}</small>}</span>
              <span className="pal-kind">{it.kind}</span>
            </button>
          ))}
          {!items.length && <div className="empty small">Nothing matches “{q}”.</div>}
        </div>
        <div className="pal-foot small muted">↑↓ to move · Enter to open · {all.filter(i => i.kind === 'Field').length} fields, every event type, places and people are searchable</div>
      </div>
    </div>
  )
}
