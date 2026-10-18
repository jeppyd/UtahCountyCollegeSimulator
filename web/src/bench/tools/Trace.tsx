// Trace: what led to the focused item and what it led to, laid out in time (left → right) with one lane per person.
// Every shape is a ledger row (an event, a decision, an occasion, a feeling at a moment, a relationship, a place) and
// every curve a recorded link with its words; nothing is summarized away. Click a shape to read it, follow it or ask
// for more of its causes; click a name to select or trace that person.
import { useEffect, useId, useMemo, useRef, useState, type MouseEvent as RMouseEvent } from 'react'
import { api, traceApi, type TraceGraph, type TraceLink, type TraceNode, type TraceRef } from '../../api'
import { useAsync } from '../../game'
import { DecisionCard } from '../../kit/DecisionCard'
import { clockLabel, dayLabel, gapWords, refString, TRACEABLE } from '../../kit/traceRefs'
import '../../kit/trace.css'
import { useLens, useStore } from '../../store'
import type { PanelProps, ToolDef } from '../registry'
import type { Ref, RefKind } from '../selection'

type Kind = 'event' | 'decision' | 'occasion' | 'state' | 'tie' | 'person' | 'place' | 'other'
const KINDS: { k: Kind; label: string }[] = [
  { k: 'event', label: 'Events' }, { k: 'decision', label: 'Decisions' }, { k: 'occasion', label: 'Occasions' },
  { k: 'state', label: 'Feelings' }, { k: 'tie', label: 'Relationships' }, { k: 'person', label: 'People' },
  { k: 'place', label: 'Places' },
]
const KIND_WORD: Record<Kind, string> = {
  event: 'Event', decision: 'Decision', occasion: 'Occasion', state: 'Feeling or state', tie: 'Relationship',
  person: 'Person', place: 'Place', other: 'Other',
}
// link kinds → style class and the plain words of the legend
const LINK: Record<string, { cls: string; label: string }> = {
  caused: { cls: 'caused', label: 'led to' },
  decided_by: { cls: 'decided', label: 'a choice behind it' },
  factor: { cls: 'factor', label: 'a reason in a choice' },
  contributed: { cls: 'contrib', label: 'played a part' },
  met_at: { cls: 'met', label: 'where they met' },
  introduced: { cls: 'met', label: 'brought them together' },
  attended: { cls: 'attended', label: 'was there' },
  led_to: { cls: 'ledto', label: 'what they set out to do' },
  bridge: { cls: 'bridge', label: 'through a hidden step' },
}
const kindOf = (n: TraceNode): Kind => (['event', 'decision', 'occasion', 'state', 'tie', 'person', 'place'].includes(n.kind) ? n.kind as Kind : 'other')

const LABEL_W = 150, AXIS_H = 40, ROW_H = 34, LANE_PAD = 8, OTHER = -1

// ---------------------------------------------------------------- layout: time columns × person lanes
type Pos = { x: number; y: number; lane: number }
type Lane = { id: number; name: string; y: number; h: number; root: boolean }
type Tick = { x: number; w: number; label: string; gap?: string; gx?: number; day: number }
type Layout = { pos: Map<string, Pos>; lanes: Lane[]; width: number; height: number; ticks: Tick[] }

function layout(nodes: TraceNode[], links: TraceLink[], lanesIn: TraceGraph['lanes'], colW: number, start: string): Layout {
  const dayOf = (n: TraceNode) => (n.day < 0 ? -1 : n.day)          // everything before the story shares one column
  const days = [...new Set(nodes.map(dayOf))].sort((a, b) => a - b)
  const col = dayColumns(nodes, links, dayOf)
  const width0 = new Map<number, number>()
  for (const n of nodes) width0.set(dayOf(n), Math.max(width0.get(dayOf(n)) ?? 0, col.get(n.key)! + 1))
  const ticks: Tick[] = []
  let x = LABEL_W + 18
  const gx = new Map<number, number>()
  days.forEach((d, i) => {
    let gapLabel: string | undefined, gapX: number | undefined
    if (i > 0) {
      const dd = d - days[i - 1]
      const gap = 16 + Math.min(40, 9 * Math.log2(1 + Math.max(0, dd)))
      if (dd > 1 || days[i - 1] < 0) { gapLabel = days[i - 1] < 0 ? '' : gapWords(dd); gapX = x + gap / 2 - 6 }
      x += gap
    }
    gx.set(d, x)
    const w = (width0.get(d) ?? 1) * colW
    ticks.push({ x, w, label: dayLabel(start, d), gap: gapLabel, gx: gapX, day: d })
    x += w
  })
  // lanes: the people who have something of their own here (the root's first), then everything else
  const has = new Set<number>()
  const laneOf = new Map<string, number>()
  const known = new Set(lanesIn.map(l => l.id))
  for (const n of nodes) {
    const l = n.lane !== null && known.has(n.lane) ? n.lane : n.people.find(p => known.has(p)) ?? OTHER
    laneOf.set(n.key, l)
    has.add(l)
  }
  const order = lanesIn.filter(l => has.has(l.id))
  // stack what shares a cell (same lane, day and column), earliest first
  const sorted = [...nodes].sort((a, b) => (a.minute ?? 0) - (b.minute ?? 0) || b.weight - a.weight || a.key.localeCompare(b.key))
  const slot = new Map<string, number>(), rows = new Map<number, number>(), cell = new Map<string, number>()
  for (const n of sorted) {
    const l = laneOf.get(n.key)!
    const ck = `${l}|${dayOf(n)}|${col.get(n.key)}`
    const k = cell.get(ck) ?? 0
    cell.set(ck, k + 1)
    slot.set(n.key, k)
    rows.set(l, Math.max(rows.get(l) ?? 0, k + 1))
  }
  const lanes: Lane[] = []
  let y = AXIS_H
  const add = (id: number, name: string, root: boolean) => {
    const h = Math.max(1, rows.get(id) ?? 1) * ROW_H + 2 * LANE_PAD
    lanes.push({ id, name, y, h, root })
    y += h
  }
  order.forEach(l => add(l.id, l.name, l.root))
  if (has.has(OTHER)) add(OTHER, 'Places & other', false)
  const laneY = new Map(lanes.map(l => [l.id, l.y]))
  const pos = new Map<string, Pos>()
  for (const n of nodes) {
    const l = laneOf.get(n.key)!
    pos.set(n.key, {
      x: gx.get(dayOf(n))! + col.get(n.key)! * colW + 14,
      y: laneY.get(l)! + LANE_PAD + slot.get(n.key)! * ROW_H + ROW_H / 2, lane: l,
    })
  }
  return { pos, lanes, width: x + 40, height: y + 10, ticks }
}

/** Columns within each day: a cause sits left of what it caused. Same-day links can form cycles (a feeling is both a
 *  cause of a choice and an effect of what the choice led to), so the back edges of a depth-first walk that visits
 *  causes before consequences are set aside, and the rest are layered by longest path. */
function dayColumns(nodes: TraceNode[], links: TraceLink[], dayOf: (n: TraceNode) => number) {
  const steps = stepsFromRoot(nodes, links)
  const day = new Map(nodes.map(n => [n.key, dayOf(n)]))
  const out = new Map<string, string[]>()
  for (const L of links) {
    if (day.get(L.source) === undefined || day.get(L.source) !== day.get(L.target) || L.source === L.target) continue
    (out.get(L.source) ?? out.set(L.source, []).get(L.source)!).push(L.target)
  }
  const order = [...nodes].sort((a, b) => steps.get(a.key)! - steps.get(b.key)! || (a.minute ?? 0) - (b.minute ?? 0) || a.key.localeCompare(b.key))
  const state = new Map<string, number>()          // 1 = on the current path, 2 = done
  const kept = new Map<string, string[]>()
  const indeg = new Map<string, number>(nodes.map(n => [n.key, 0]))
  for (const start of order) {
    if (state.has(start.key)) continue
    const stack: [string, number][] = [[start.key, 0]]
    state.set(start.key, 1)
    while (stack.length) {
      const top = stack[stack.length - 1]
      const nb = out.get(top[0]) ?? []
      if (top[1] >= nb.length) { state.set(top[0], 2); stack.pop(); continue }
      const m = nb[top[1]++]
      if (state.get(m) === 1) continue                 // a back edge: drawing it as a loop is enough
      ;(kept.get(top[0]) ?? kept.set(top[0], []).get(top[0])!).push(m)
      indeg.set(m, (indeg.get(m) ?? 0) + 1)
      if (!state.has(m)) { state.set(m, 1); stack.push([m, 0]) }
    }
  }
  const col = new Map<string, number>(nodes.map(n => [n.key, 0]))
  const queue = order.map(n => n.key).filter(k => !indeg.get(k))
  while (queue.length) {
    const k = queue.shift()!
    for (const m of kept.get(k) ?? []) {
      col.set(m, Math.max(col.get(m)!, col.get(k)! + 1))
      indeg.set(m, indeg.get(m)! - 1)
      if (!indeg.get(m)) queue.push(m)
    }
  }
  return col
}

/** Signed steps from the root: causes negative (walking links backward), consequences positive (forward). Items that
 *  came in through an expansion are measured from the root too, so the layout stays one story. */
function stepsFromRoot(nodes: TraceNode[], links: TraceLink[]) {
  const into = new Map<string, string[]>(), out = new Map<string, string[]>()
  for (const L of links) {
    (into.get(L.target) ?? into.set(L.target, []).get(L.target)!).push(L.source);
    (out.get(L.source) ?? out.set(L.source, []).get(L.source)!).push(L.target)
  }
  const roots = nodes.filter(n => n.root).map(n => n.key)
  const seen = new Map<string, number>(roots.map(k => [k, 0]))
  for (const [adj, sign] of [[into, -1], [out, 1]] as const) {
    let frontier = [...roots], d = 0
    while (frontier.length) {
      d++
      const next: string[] = []
      for (const k of frontier) for (const m of adj.get(k) ?? []) if (!seen.has(m)) { seen.set(m, sign * d); next.push(m) }
      frontier = next
    }
  }
  // anything not reachable from the root keeps the server's own measure
  for (const n of nodes) if (!seen.has(n.key)) seen.set(n.key, n.depth ?? 0)
  return seen
}

function linkPath(a: Pos, b: Pos) {
  const x1 = a.x + 9, x2 = b.x - 9
  if (x2 - x1 > 14) {
    const dx = (x2 - x1) * 0.5
    return `M${x1},${a.y} C${x1 + dx},${a.y} ${x2 - dx},${b.y} ${x2},${b.y}`
  }
  // the same column, or backwards in time (a relationship's first day, a place): a loop over the top
  const top = Math.min(a.y, b.y) - 22 - Math.min(40, Math.abs(a.y - b.y) * 0.2)
  return `M${a.x + 6},${a.y - 6} C${a.x + 46},${top} ${b.x - 46},${top} ${b.x - 6},${b.y - 6}`
}

// ---------------------------------------------------------------- shapes
function Shape({ n, laneName }: { n: TraceNode; laneName?: string }) {
  const k = kindOf(n)
  const r = k === 'event' ? 4.5 + 3.5 * Math.max(0, Math.min(1, n.weight)) : 6.5
  switch (k) {
    case 'event': return <circle r={r} className="ts ts-event" />
    case 'decision': return <rect x={-5.2} y={-5.2} width={10.4} height={10.4} transform="rotate(45)" className="ts ts-decision" />
    case 'occasion': return <rect x={-10} y={-6} width={20} height={12} rx={6} className="ts ts-occasion" />
    case 'state': return (
      <g className="ts ts-state">
        <rect x={-6.5} y={-6.5} width={13} height={13} rx={3} />
        <path d="M-4,1.5 C-2,-3 0,-3 1,0 C2,3 3.5,3 4.5,-1.5" />
      </g>
    )
    case 'tie': return <g className="ts ts-tie"><circle cx={-3.6} r={4.6} /><circle cx={3.6} r={4.6} /></g>
    case 'person': {
      const nm = laneName ?? n.label
      const ini = nm.split(/\s+/).map(w => w[0]).join('').slice(0, 2)
      return <g className="ts ts-person"><circle r={8} /><text y={3.2} textAnchor="middle">{ini}</text></g>
    }
    case 'place': return <path className="ts ts-place" d="M0,8 L-5.6,-0.5 A6.6,6.6 0 1 1 5.6,-0.5 Z" />
    default: return <circle r={4.5} className="ts ts-other" />
  }
}

const cap = (s: string) => (s ? s[0].toUpperCase() + s.slice(1) : s)
/** A node's line without the lane's own name in front ("asked Emma out" in Logan's lane). */
function shortLabel(n: TraceNode, laneName?: string) {
  let s = n.label
  if (kindOf(n) === 'person') return laneName === n.label ? '' : s       // a person in their own lane needs no label
  if (laneName) {
    // in Ann's lane, "Ann asked Ben out" reads "Asked Ben out" and "Ann and Ben became friends" "…and Ben became friends"
    for (const p of [laneName + "'s ", laneName + ': ', laneName + ' ']) {
      if (!s.startsWith(p)) continue
      s = s.slice(p.length)
      return s.startsWith('and ') ? '…' + s : cap(s)
    }
  }
  return cap(s)
}
const clip = (s: string, k: number) => (s.length > k ? s.slice(0, Math.max(1, k - 1)) + '…' : s)
const when = (n: TraceNode, start: string) =>
  (n.timeless ? '' : dayLabel(start, n.day, { weekday: 'short', month: 'short', day: 'numeric', year: 'numeric' }) + (n.minute !== null && n.kind !== 'tie' ? `, ${clockLabel(n.minute)}` : ''))

// ---------------------------------------------------------------- the tool
type Expansion = { nodes: Map<string, TraceNode>; links: TraceLink[]; done: Set<string> }
const emptyExp = (): Expansion => ({ nodes: new Map(), links: [], done: new Set() })

function TraceTool({ sel, setSel, opts, setOpts }: PanelProps) {
  const lens = useLens()
  const dataVersion = useStore(s => s.dataVersion)
  const u = sel.item?.u ?? lens.u
  const ref = refString(sel.item, sel.people)
  const depth: number = opts.depth ?? 3
  const dir: 'back' | 'fwd' | 'both' = opts.dir ?? 'both'
  const hidden: Kind[] = opts.hide ?? []
  const compact: boolean = !!opts.compact
  const set = (o: Record<string, any>) => setOpts({ ...opts, ...o })
  const colW = compact ? 46 : 158

  const got = useAsync<TraceGraph | null>(() => (ref ? traceApi.trace(ref, u, dir, depth, 80, 8) : Promise.resolve(null)),
    [ref, u, dir, depth, dataVersion], { keepOld: false, key: ref ? `trace:${u}:${ref}:${dir}:${depth}` : undefined })
  const [exp, setExp] = useState<Expansion>(emptyExp)
  const [picked, setPicked] = useState<string | null>(null)
  const [hover, setHover] = useState<{ key?: string; link?: number; x: number; y: number } | null>(null)
  const [menu, setMenu] = useState<{ id: number; name: string; x: number; y: number } | null>(null)
  const [trail, setTrail] = useState<{ ref: Ref; label: string }[]>([])
  const [busy, setBusy] = useState('')
  useEffect(() => { setExp(emptyExp()); setPicked(null); setMenu(null) }, [ref, u])

  // the trail of things traced in this panel (breadcrumbs)
  const g = got.data
  useEffect(() => {
    if (!g || !sel.item) return
    const root = g.nodes.find(n => n.key === g.root)
    const label = root ? clip(root.label, 34) : sel.item.label ?? String(sel.item.id)
    setTrail(t => {
      const k = refString(sel.item, sel.people)
      const rest = t.filter(x => refString(x.ref) !== k)
      return [...rest, { ref: sel.item!, label }].slice(-6)
    })
  }, [g?.root])

  // the graph on screen: the trace plus whatever was expanded, minus hidden kinds (bridged through one hidden step)
  const view = useMemo(() => {
    if (!g) return null
    const all = new Map(g.nodes.map(n => [n.key, n]))
    exp.nodes.forEach((n, k) => { if (!all.has(k)) all.set(k, n) })
    const seen = new Set<string>()
    const links: TraceLink[] = []
    for (const L of [...g.links, ...exp.links]) {
      const k = `${L.source}>${L.target}`
      if (seen.has(k) || !all.has(L.source) || !all.has(L.target)) continue
      seen.add(k)
      links.push(L)
    }
    const hide = new Set(hidden)
    const show = (n?: TraceNode) => !!n && (n.root || !hide.has(kindOf(n)))
    const nodes = [...all.values()].filter(n => show(n))
    const vis = new Set(nodes.map(n => n.key))
    const out: TraceLink[] = links.filter(L => vis.has(L.source) && vis.has(L.target))
    if (hide.size) {
      const inn = new Map<string, TraceLink[]>(), outl = new Map<string, TraceLink[]>()
      for (const L of links) {
        if (!vis.has(L.target)) (outl.get(L.target) ?? outl.set(L.target, []).get(L.target)!).push(L)
        if (!vis.has(L.source)) (inn.get(L.source) ?? inn.set(L.source, []).get(L.source)!).push(L)
      }
      const have = new Set(out.map(L => `${L.source}>${L.target}`))
      for (const [h, ins] of outl) {
        const hn = all.get(h)!
        for (const a of ins) for (const b of inn.get(h) ?? []) {
          if (!vis.has(a.source) || !vis.has(b.target) || a.source === b.target) continue
          const k = `${a.source}>${b.target}`
          if (have.has(k)) continue
          have.add(k)
          out.push({ source: a.source, target: b.target, kind: 'bridge', weight: null, words: `through ${hn.label}` })
        }
      }
    }
    const lanes = [...g.lanes]
    const known = new Set(lanes.map(l => l.id))
    for (const n of nodes) if (n.kind === 'person' && n.lane !== null && !known.has(n.lane)) { lanes.push({ id: n.lane, name: n.label, n: 1, root: false }); known.add(n.lane) }
    return { nodes, links: out, lanes, L: layout(nodes, out, lanes, colW, g.start_date) }
  }, [g, exp, hidden.join(','), colW])

  const names = useMemo(() => new Map((view?.lanes ?? []).map(l => [l.id, l.name])), [view])
  const focus = (r: TraceRef | Ref, label?: string) => {
    const kind = (r.kind === 'state' ? 'var' : r.kind) as RefKind
    if (!TRACEABLE.has(kind)) return
    setSel({ item: { kind, id: r.id, label, u } })
  }
  const expand = async (n: TraceNode, d: 'back' | 'fwd') => {
    const rs = refString(n.ref)
    if (!rs) return
    setBusy(n.key)
    try {
      const more = await traceApi.trace(rs, u, d, 1, 40, 24)
      setExp(e => {
        const nodes = new Map(e.nodes)
        for (const m of more.nodes) if (!nodes.has(m.key)) nodes.set(m.key, { ...m, root: false })
        const done = new Set(e.done)
        done.add(`${n.key}|${d}`)
        return { nodes, links: [...e.links, ...more.links], done }
      })
    } catch { /* the node may have been thinned; nothing to add */ } finally { setBusy('') }
  }

  // ---- empty states
  if (!sel.item) return <Empty u={u} onPick={(id, name) => setSel({ item: { kind: 'person', id, label: name, u }, people: [id] })} />
  if (!ref) return <div className="tr-empty"><b>This can't be traced yet.</b> Pick an event, a decision, a person, a relationship or one person's feeling.</div>
  if (got.error && !g) return <div className="tr-empty"><b>Nothing to trace here.</b> {got.error}</div>
  if (!g || !view) return <div className="tr-empty">Following the links…</div>

  const { L } = view
  const pk = picked ? view.nodes.find(n => n.key === picked) ?? null : null
  const hoverNode = hover?.key ? view.nodes.find(n => n.key === hover.key) : undefined
  const hl = new Set<number>()
  const hk = hover?.key ?? picked
  if (hk) view.links.forEach((Lk, i) => { if (Lk.source === hk || Lk.target === hk) hl.add(i) })
  if (hover?.link !== undefined) hl.add(hover.link)
  const budget = Math.floor((colW - 30) / 6.4)

  return (
    <div className="tr" onClick={() => setMenu(null)}>
      <div className="tr-bar">
        <div className="tr-crumbs">
          {trail.map((t, i) => (
            <button key={i} className={`tr-crumb${i === trail.length - 1 ? ' on' : ''}`} onClick={() => setSel({ item: t.ref })} title={t.label}>{t.label}</button>
          ))}
        </div>
        <div className="seg small-seg" role="group" aria-label="Direction">
          {(['back', 'both', 'fwd'] as const).map(d => (
            <button key={d} className={dir === d ? 'on' : ''} onClick={() => set({ dir: d })}>{d === 'back' ? 'What led to it' : d === 'fwd' ? 'What it led to' : 'Both'}</button>
          ))}
        </div>
        <label className="tr-depth" title="How many steps to follow each way">
          Steps <input type="range" min={1} max={6} value={depth} onChange={e => set({ depth: Number(e.target.value) })} /> <b>{depth}</b>
        </label>
        <button className={`btn small${compact ? ' on' : ''}`} onClick={() => set({ compact: !compact })} title="Hide the words to fit more on screen">{compact ? 'Show words' : 'Dots only'}</button>
      </div>
      <div className="tr-kinds">
        {KINDS.map(({ k, label }) => {
          const off = hidden.includes(k)
          const n = view.nodes.filter(x => kindOf(x) === k).length + (off ? (g.nodes.filter(x => kindOf(x) === k).length) : 0)
          return (
            <button key={k} className={`tr-kind${off ? ' off' : ''}`} onClick={() => set({ hide: off ? hidden.filter(x => x !== k) : [...hidden, k] })}
              title={off ? `Show ${label.toLowerCase()}` : `Hide ${label.toLowerCase()} (links pass through them)`}>
              <svg width={18} height={18} viewBox="-9 -9 18 18" aria-hidden="true"><Shape n={{ kind: k, weight: 0.5, label: 'A B' } as TraceNode} /></svg>
              {label}{n ? <span className="muted"> {n}</span> : null}
            </button>
          )
        })}
        {got.loading && <span className="muted tr-loading">updating…</span>}
      </div>
      <div className="tr-body">
        <Canvas L={L} view={view} g={g} colW={colW} compact={compact} budget={budget} hl={hl} hk={hk} picked={picked} busy={busy}
          onPick={k => setPicked(k === picked ? null : k)} onHover={setHover} onExpand={expand}
          onLane={(id, name, x, y) => setMenu({ id, name, x, y })} />
        {pk && (
          <Inspector n={pk} g={g} view={view} names={names} u={u} onClose={() => setPicked(null)} onFocus={focus}
            onExpand={expand} onPick={setPicked} done={exp.done} busy={busy === pk.key}
            onPeople={ids => setSel({ people: ids })} />
        )}
      </div>
      <div className="tr-foot">
        <span className="tr-legend">
          {(['caused', 'decided_by', 'factor', 'contributed', 'met_at', 'led_to'] as const).map(k => (
            <span key={k}><svg width={22} height={8} aria-hidden="true"><line x1={1} x2={21} y1={4} y2={4} className={`tl tl-${LINK[k].cls}`} /></svg>{LINK[k].label}</span>
          ))}
        </span>
        {g.notes.map((t, i) => <span key={i} className="muted">{t}</span>)}
      </div>
      {hover && (hoverNode || hover.link !== undefined) && (
        <div className="tr-tip" style={{ left: hover.x + 14, top: hover.y + 12 }}>
          {hoverNode ? (
            <>
              <div className="tr-tip-k">{KIND_WORD[kindOf(hoverNode)]}{when(hoverNode, g.start_date) ? ` · ${when(hoverNode, g.start_date)}` : ''}</div>
              <div>{hoverNode.label}</div>
              {(hoverNode.more_back > 0 || hoverNode.more_fwd > 0) && (
                <div className="muted">{hoverNode.more_back > 0 ? `${hoverNode.more_back} more causes` : ''}{hoverNode.more_back > 0 && hoverNode.more_fwd > 0 ? ' · ' : ''}{hoverNode.more_fwd > 0 ? `${hoverNode.more_fwd} more consequences` : ''} not shown</div>
              )}
            </>
          ) : (() => {
            const Lk = view.links[hover.link!]
            const s = view.nodes.find(n => n.key === Lk.source), t = view.nodes.find(n => n.key === Lk.target)
            return (
              <>
                <div className="tr-tip-k">{LINK[Lk.kind]?.label ?? Lk.kind}{Lk.weight !== null ? ` · strength ${Lk.weight > 0 ? '+' : ''}${Lk.weight.toFixed(2)}` : ''}</div>
                {Lk.words && <div>{cap(Lk.words)}</div>}
                <div className="muted">{s ? clip(s.label, 60) : ''} → {t ? clip(t.label, 60) : ''}</div>
              </>
            )
          })()}
        </div>
      )}
      {menu && (
        <div className="tr-menu" style={{ left: menu.x, top: menu.y }} onClick={e => e.stopPropagation()}>
          <div className="tr-menu-h">{menu.name}</div>
          <button onClick={() => { setSel({ people: [menu.id] }); setMenu(null) }}>Select {menu.name.split(' ')[0]}</button>
          <button onClick={() => { setSel({ people: [...new Set([...(sel.people ?? []), menu.id])] }); setMenu(null) }}>Add to the selection</button>
          <button onClick={() => { setSel({ item: { kind: 'person', id: menu.id, label: menu.name, u } }); setMenu(null) }}>Trace {menu.name.split(' ')[0]}'s story</button>
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------- the drawing
function Canvas({ L, view, g, colW, compact, budget, hl, hk, picked, busy, onPick, onHover, onExpand, onLane }: {
  L: Layout; view: { nodes: TraceNode[]; links: TraceLink[] }; g: TraceGraph; colW: number; compact: boolean; budget: number
  hl: Set<number>; hk: string | null; picked: string | null; busy: string
  onPick: (k: string) => void; onHover: (h: { key?: string; link?: number; x: number; y: number } | null) => void
  onExpand: (n: TraceNode, d: 'back' | 'fwd') => void; onLane: (id: number, name: string, x: number, y: number) => void
}) {
  const uid = useId().replace(/[^a-zA-Z0-9]/g, '')
  const scroller = useRef<HTMLDivElement>(null)
  const lanesBox = useRef<HTMLDivElement>(null)
  const rootKey = g.root
  // open on the item itself
  useEffect(() => {
    const p = L.pos.get(rootKey), el = scroller.current
    // causes sit to the left, so keep more of the left in view
    if (p && el) el.scrollLeft = Math.max(0, p.x - el.clientWidth * 0.62)
  }, [rootKey])
  const at = (e: RMouseEvent) => {
    const box = (e.currentTarget as Element).closest('.tr')!.getBoundingClientRect()
    return { x: e.clientX - box.left, y: e.clientY - box.top }
  }
  const laneName = (id: number) => L.lanes.find(l => l.id === id)?.name
  const dim = hk !== null || hl.size > 0
  return (
    <div className="tr-canvas">
      <div className="tr-lanes" ref={lanesBox} style={{ width: LABEL_W }}>
        <div style={{ height: AXIS_H }} />
        {L.lanes.map(l => (
          <div key={l.id} className={`tr-lane-name${l.root ? ' root' : ''}`} style={{ height: l.h }}>
            {l.id === OTHER ? <span className="muted">{l.name}</span> : (
              <button onClick={e => { e.stopPropagation(); const b = (e.currentTarget.closest('.tr') as HTMLElement).getBoundingClientRect(); onLane(l.id, l.name, e.clientX - b.left, e.clientY - b.top) }}
                title={`${l.name}: select, add to the selection or trace their story`}>{l.name}</button>
            )}
          </div>
        ))}
      </div>
      <div className="tr-scroll" ref={scroller} onScroll={e => { if (lanesBox.current) lanesBox.current.scrollTop = (e.currentTarget as HTMLDivElement).scrollTop }}>
        {/* the dates stay in view while the lanes scroll */}
        <div className="tr-axis" style={{ width: L.width, height: AXIS_H, marginBottom: -AXIS_H }}>
          <svg width={L.width} height={AXIS_H} aria-hidden="true">
            {L.ticks.map(t => (
              <g key={t.day}>
                <text x={t.x + 3} y={16} className="tr-day">{compact && t.w < 70 ? dayLabel(g.start_date, t.day, { month: 'numeric', day: 'numeric' }) : t.label}</text>
                {t.gap && t.gx !== undefined && <text x={t.gx} y={31} className="tr-gap" textAnchor="middle">{t.gap}</text>}
              </g>
            ))}
          </svg>
        </div>
        <svg width={L.width} height={L.height} className="tr-svg" onMouseLeave={() => onHover(null)}>
          <defs>
            {[...new Set(Object.values(LINK).map(s => s.cls))].map(cls => (
              <marker key={cls} id={`a-${uid}-${cls}`} viewBox="0 0 8 8" refX={7} refY={4} markerWidth={7} markerHeight={7}
                markerUnits="userSpaceOnUse" orient="auto-start-reverse">
                <path d="M0,0.5 L7.5,4 L0,7.5 z" className={`tm tm-${cls}`} />
              </marker>
            ))}
          </defs>
          {/* lanes and day columns */}
          {L.lanes.map((l, i) => <rect key={l.id} x={0} y={l.y} width={L.width} height={l.h} className={`tr-band${i % 2 ? ' odd' : ''}${l.root ? ' root' : ''}`} />)}
          {L.ticks.map(t => <line key={t.day} x1={t.x} x2={t.x} y1={AXIS_H - 6} y2={L.height} className="tr-daygrid" />)}
          {g.today >= 0 && (() => {
            const t = L.ticks.find(x => x.day === g.today)
            return t ? <line x1={t.x + t.w - 4} x2={t.x + t.w - 4} y1={AXIS_H - 6} y2={L.height} className="tr-today" /> : null
          })()}
          {/* links */}
          {view.links.map((Lk, i) => {
            const a = L.pos.get(Lk.source), b = L.pos.get(Lk.target)
            if (!a || !b) return null
            const s = LINK[Lk.kind] ?? LINK.contributed
            const w = Lk.weight === null ? 1.4 : 1 + 2.2 * Math.min(1, Math.abs(Lk.weight))
            const d = linkPath(a, b)
            return (
              <g key={i} className={`tl-g${dim && !hl.has(i) ? ' dim' : ''}${hl.has(i) ? ' hot' : ''}`}>
                <path d={d} className={`tl tl-${s.cls}`} strokeWidth={w} markerEnd={`url(#a-${uid}-${s.cls})`} />
                <path d={d} className="tl-hit" onMouseMove={e => onHover({ link: i, ...at(e) })} onMouseLeave={() => onHover(null)} />
              </g>
            )
          })}
          {/* nodes */}
          {view.nodes.map(n => {
            const p = L.pos.get(n.key)
            if (!p) return null
            const ln = p.lane === OTHER ? undefined : laneName(p.lane)
            const on = n.key === picked
            const near = hk === n.key || view.links.some((Lk, i) => hl.has(i) && (Lk.source === n.key || Lk.target === n.key))
            return (
              <g key={n.key} transform={`translate(${p.x},${p.y})`} className={`tn c-${n.category}${n.root ? ' root' : ''}${on ? ' on' : ''}${dim && !near ? ' dim' : ''}`}
                onClick={e => { e.stopPropagation(); onPick(n.key) }} onMouseMove={e => onHover({ key: n.key, ...at(e) })} onMouseLeave={() => onHover(null)}>
                {(n.root || on) && <circle r={13} className="tn-halo" />}
                <Shape n={n} laneName={ln} />
                {!compact && <text x={kindOf(n) === 'occasion' ? 16 : 14} y={4} className="tn-label">{clip(shortLabel(n, ln), budget)}</text>}
                {n.more_back > 0 && (
                  <g className="tn-more" transform="translate(-22,-11)" onClick={e => { e.stopPropagation(); onExpand(n, 'back') }}>
                    <title>{`Show ${n.more_back} more causes`}</title>
                    <rect x={-9} y={-7} width={18} height={13} rx={6} /><text y={3} textAnchor="middle">+{n.more_back}</text>
                  </g>
                )}
                {n.more_fwd > 0 && (
                  <g className="tn-more" transform={compact ? 'translate(20,-11)' : 'translate(24,-14)'} onClick={e => { e.stopPropagation(); onExpand(n, 'fwd') }}>
                    <title>{`Show ${n.more_fwd} more consequences`}</title>
                    <rect x={-9} y={-7} width={18} height={13} rx={6} /><text y={3} textAnchor="middle">+{n.more_fwd}</text>
                  </g>
                )}
                {busy === n.key && <circle r={11} className="tn-busy" />}
              </g>
            )
          })}
        </svg>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------- reading one item
function Inspector({ n, g, view, names, u, onClose, onFocus, onExpand, onPick, onPeople, done, busy }: {
  n: TraceNode; g: TraceGraph; view: { nodes: TraceNode[]; links: TraceLink[] }; names: Map<number, string>; u: 'base' | 'alt'
  onClose: () => void; onFocus: (r: TraceRef, label?: string) => void; onExpand: (n: TraceNode, d: 'back' | 'fwd') => void
  onPick: (k: string) => void; onPeople: (ids: number[]) => void; done: Set<string>; busy: boolean
}) {
  const k = kindOf(n)
  const byKey = new Map(view.nodes.map(x => [x.key, x]))
  const ins = view.links.filter(L => L.target === n.key)
  const outs = view.links.filter(L => L.source === n.key)
  const d = n.detail ?? {}
  const who = n.people.map(p => names.get(p) ?? `person ${p}`)
  const canTrace = TRACEABLE.has(n.ref.kind) && !n.root
  return (
    <aside className="tr-insp" onClick={e => e.stopPropagation()}>
      <div className="tr-insp-h">
        <span className="tr-insp-k">{KIND_WORD[k]}{d.title && k !== 'decision' ? ` · ${d.title}` : ''}</span>
        <button className="btn ghost small" onClick={onClose} aria-label="Close">✕</button>
      </div>
      {k !== 'decision' && <div className="tr-insp-t">{n.label}</div>}
      {when(n, g.start_date) && <div className="muted small">{when(n, g.start_date)}</div>}
      {k === 'decision' ? (
        <DecisionCard id={Number(n.ref.id)} u={u} startDate={g.start_date} compact onRef={(r, label) => onFocus(r, label)} />
      ) : (
        <Facts n={n} names={names} />
      )}
      <div className="tr-insp-acts">
        {canTrace && <button className="btn small primary" onClick={() => onFocus(n.ref, n.label)}>Trace from here</button>}
        {n.more_back > 0 && !done.has(`${n.key}|back`) && <button className="btn small" disabled={busy} onClick={() => onExpand(n, 'back')}>{n.more_back} more causes</button>}
        {n.more_fwd > 0 && !done.has(`${n.key}|fwd`) && <button className="btn small" disabled={busy} onClick={() => onExpand(n, 'fwd')}>{n.more_fwd} more consequences</button>}
        {!n.more_back && !done.has(`${n.key}|back`) && !n.root && k !== 'person' && <button className="btn small" disabled={busy} onClick={() => onExpand(n, 'back')}>Its causes</button>}
        {n.people.length > 0 && <button className="btn small" onClick={() => onPeople(n.people)} title={who.join(', ')}>Select {n.people.length === 1 ? who[0].split(' ')[0] : `these ${n.people.length}`}</button>}
      </div>
      {ins.length > 0 && <LinkList title="Why — what led to it" links={ins} other={L => byKey.get(L.source)} onPick={onPick} />}
      {outs.length > 0 && <LinkList title="What it led to" links={outs} other={L => byKey.get(L.target)} onPick={onPick} />}
      {!ins.length && !outs.length && <p className="muted small">Nothing on screen links to this yet.</p>}
    </aside>
  )
}

function LinkList({ title, links, other, onPick }: { title: string; links: TraceLink[]; other: (L: TraceLink) => TraceNode | undefined; onPick: (k: string) => void }) {
  return (
    <div className="tr-links">
      <div className="tr-links-h">{title}</div>
      {links.map((L, i) => {
        const o = other(L)
        if (!o) return null
        return (
          <button key={i} className="tr-link" onClick={() => onPick(o.key)}>
            <svg width={16} height={8} aria-hidden="true"><line x1={1} x2={15} y1={4} y2={4} className={`tl tl-${(LINK[L.kind] ?? LINK.contributed).cls}`} /></svg>
            <span>
              <span className="tr-link-o">{o.label}</span>
              {L.words && <span className="muted"> — {L.words}{L.weight !== null && (L.kind === 'contributed' || L.kind === 'factor') ? ` (${L.weight > 0 ? '+' : ''}${L.weight.toFixed(2)})` : ''}</span>}
            </span>
          </button>
        )
      })}
    </div>
  )
}

function Facts({ n, names }: { n: TraceNode; names: Map<number, string> }) {
  const d = n.detail ?? {}
  const rows: [string, string][] = []
  const nm = (i: number | null | undefined) => (i === null || i === undefined ? '' : names.get(i) ?? `person ${i}`)
  switch (kindOf(n)) {
    case 'occasion':
      rows.push(['What happened', d.status ?? ''])
      if (d.invited) rows.push(['Invited', `${d.invited} (${d.said_yes ?? 0} said yes)`])
      rows.push(['Came', String(d.came ?? 0)])
      if (d.talks) rows.push(['Conversations', String(d.talks)])
      if (d.new_ties) rows.push(['People who met for the first time', String(d.new_ties)])
      if (d.conflicts) rows.push(['Falling-outs', String(d.conflicts)])
      break
    case 'tie':
      if (d.gone) { rows.push(['Now', 'no longer in touch']); break }
      rows.push(['Now', d.stage ?? ''])
      if (d.met) rows.push(['Met', d.met])
      if (d.introducer !== undefined) rows.push(['Introduced by', nm(d.introducer)])
      if (d.mostly) rows.push(['Time together mostly', `${d.mostly} (${Math.round((d.mostly_share ?? 0) * 100)}%)`])
      if (d.hours !== undefined) rows.push(['Hours together', String(d.hours)])
      if (d.closeness !== undefined) rows.push(['Closeness', `${d.closeness} of 1`])
      break
    case 'state':
      if (d.now !== null && d.now !== undefined) rows.push(['Today', String(d.now)])
      break
    case 'event':
      if (d.value !== undefined && d.value !== 0) rows.push(['Recorded value', String(d.value)])
      break
  }
  if (!rows.length) return null
  return <dl className="tr-facts">{rows.map(([a, b]) => <div key={a}><dt>{a}</dt><dd>{b}</dd></div>)}</dl>
}

function Empty({ u, onPick }: { u: 'base' | 'alt'; onPick: (id: number, name: string) => void }) {
  const [q, setQ] = useState('')
  const found = useAsync(() => (q.trim().length >= 2 ? api.searchPeople(q.trim(), u) : Promise.resolve([])), [q, u], false)
  return (
    <div className="tr-empty">
      <b>Trace shows what led to something and what it led to.</b>
      <p>Pick anything in another tool — a person, an event, a decision, a night out — and choose <i>Trace</i>, or start from a person:</p>
      <input type="search" placeholder="Find a person by name" value={q} onChange={e => setQ(e.target.value)} />
      <div className="tr-found">
        {(found.data ?? []).map((p: any) => <button key={p.id} className="chip" onClick={() => onPick(p.id, p.name)}>{p.name}</button>)}
      </div>
    </div>
  )
}

export const tool: ToolDef = {
  id: 'trace',
  label: 'Trace',
  icon: 'link',
  hint: 'What led to the focused item and what it led to, in time order with a lane per person. Click a shape to read it or follow it.',
  group: 'trace',
  order: 10,
  component: TraceTool,
  size: { w: 12, h: 8 },
  needs: ['item'],
}
