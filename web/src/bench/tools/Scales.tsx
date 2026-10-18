// Scales: a glossary of what every number means. Each field, grouped by area, with its ruler (anchor words from lowest
// to highest, where people sit today) and its units; search by name or by words. Click a field for its whole scale card
// and to focus it (Measure follows).
import { useMemo, useState, type MouseEvent } from 'react'
import { DOMAIN_LABEL } from '../../components'
import { Empty } from '../../kit/Bits'
import { Ruler } from '../../kit/Ruler'
import { ScaleCard } from '../../kit/Val'
import { useStore, type VarSpec } from '../../store'
import { PanelOptions } from '../panel'
import type { PanelProps, ToolDef } from '../registry'
import { focusItem } from '../sel'

const OPEN_FIRST = ['social_emotion', 'emotion', 'inner_life', 'religion', 'romance']

function Row({ s, on, pick }: { s: VarSpec; on: boolean; pick: (e: MouseEvent) => void }) {
  return (
    <div className={`bsc-row ${on ? 'on' : ''}`} onClick={pick} title={s.desc}>
      <div className="bsc-name"><b>{s.label}</b><small>{s.scale?.unit ?? ''}</small></div>
      <Ruler v={s.id} variant="full" />
    </div>
  )
}

function ScalesTool({ sel, setSel }: PanelProps) {
  const reg = useStore(s => s.registry)
  const [q, setQ] = useState('')
  const [open, setOpen] = useState<Record<string, boolean>>({})
  const [card, setCard] = useState<{ v: string; x: number; y: number } | null>(null)
  const groups = useMemo(() => {
    if (!reg) return []
    const ql = q.trim().toLowerCase()
    const m = new Map<string, VarSpec[]>()
    for (const s of Object.values(reg.variables)) {
      if (s.entity !== 'person' || !s.scale || s.dtype === 'cat' || s.dtype === 'bool') continue
      if (ql) {
        const hay = `${s.label} ${s.id} ${s.desc ?? ''} ${(s.scale.anchors ?? []).map(a => a.label).join(' ')}`.toLowerCase()
        if (!ql.split(/\s+/).every(w => hay.includes(w))) continue
      }
      const list = m.get(s.domain) ?? []
      list.push(s)
      m.set(s.domain, list)
    }
    return [...m.entries()].sort((a, b) => (OPEN_FIRST.indexOf(b[0]) + 1 || -1) - (OPEN_FIRST.indexOf(a[0]) + 1 || -1) || a[0].localeCompare(b[0]))
      .map(([d, list]) => [d, list.sort((a, b) => a.label.localeCompare(b.label))] as const)
  }, [reg, q])
  if (!reg) return null
  const focused = sel.item?.kind === 'var' ? String(sel.item.id) : null
  const n = groups.reduce((k, [, l]) => k + l.length, 0)
  const isOpen = (d: string, k: number) => open[d] ?? (!!q.trim() || k < 2)
  return (
    <div className="bk">
      <PanelOptions>
        <input type="search" placeholder="Find a field or words" value={q} onChange={e => setQ(e.target.value)} style={{ width: 160 }} />
      </PanelOptions>
      <div className="bx-note">{n.toLocaleString()} fields. Each ruler runs from the lowest to the highest value with words along it; the band is
        where the middle half of people are today, the whiskers the 10th–90th percentile, the tick the median. Click a field for how it is measured.</div>
      {n === 0 && <Empty title="No field matches">Try other words.</Empty>}
      {groups.map(([d, list], k) => (
        <div key={d} className="bsc-group">
          <button className="bsc-h" onClick={() => setOpen({ ...open, [d]: !isOpen(d, k) })}>
            <span>{isOpen(d, k) ? '▾' : '▸'}</span> {DOMAIN_LABEL[d] ?? d.replace(/_/g, ' ')} <small>{list.length}</small>
          </button>
          {isOpen(d, k) && list.map(s => (
            <Row key={s.id} s={s} on={focused === s.id} pick={e => {
              focusItem(setSel, { kind: 'var', id: s.id, label: s.label })
              setCard({ v: s.id, x: e.clientX, y: e.clientY })
            }} />
          ))}
        </div>
      ))}
      {card && <ScaleCard v={card.v} at={{ x: card.x, y: card.y }} onClose={() => setCard(null)} />}
    </div>
  )
}

export const tool: ToolDef = {
  id: 'scales',
  label: 'Scales',
  icon: 'scale',
  hint: 'What every number means: each field’s range in words and where people sit on it today; searchable.',
  group: 'see',
  order: 40,
  component: ScalesTool,
  size: { w: 5, h: 8 },
}
