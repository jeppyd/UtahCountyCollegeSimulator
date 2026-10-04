// The field pane: every field the model tracks, in friendly drawers, searchable, with live values
// (and Original → What-if changes in Compare).
import { useEffect, useMemo, useState } from 'react'
import { catalog, favg, fdelta, isCat, pctStr, polarity, sizeWord } from '../../fields'
import { DeltaChip, G } from '../../game'
import { useStore, VarSpec } from '../../store'

export type FieldSummary = Record<string, any>

export function summaryText(spec: VarSpec, s: any): string {
  if (!s) return '—'
  if (s.kind === 'cat') { const top = s.top; return top ? `${String(top).replace(/_/g, ' ')} ${pctStr(s.shares?.[top] ?? 0, 0)}` : '—' }
  if (s.kind === 'bool') return pctStr(s.share ?? NaN, s.share < 0.1 ? 1 : 0)
  return favg(spec, s.mean)
}

export function FieldPane({ value, onPick, summary, tracked, compare }: {
  value: string; onPick: (v: string) => void; summary: FieldSummary | null; tracked: { weekly: Set<string>; person: Set<string> }; compare: any | null
}) {
  const reg = useStore(s => s.registry)!
  const cats = useMemo(() => catalog(reg), [reg])
  const [q, setQ] = useState('')
  const [filter, setFilter] = useState<'all' | 'changed' | 'history'>('all')
  const [sortBy, setSortBy] = useState<'name' | 'change'>('name')
  const [open, setOpen] = useState<Record<string, boolean>>(() => ({ feelings: true }))
  const selDrawer = cats.find(c => c.fields.some(f => f.id === value))?.drawer.id
  useEffect(() => { if (selDrawer) setOpen(o => ({ ...o, [selDrawer]: true })) }, [selDrawer])
  useEffect(() => { if (compare) setSortBy('change'); else { setSortBy('name'); if (filter === 'changed') setFilter('all') } }, [!!compare])
  const ql = q.trim().toLowerCase()
  const eff = (id: string) => Math.abs(compare?.fields?.[id]?.effect ?? 0)
  const shown = cats.map(c => {
    let fs = c.fields.filter(f => !ql || f.label.toLowerCase().includes(ql) || f.id.includes(ql) || (f.desc ?? '').toLowerCase().includes(ql))
    if (filter === 'changed') fs = fs.filter(f => eff(f.id) >= 0.02 || (compare?.fields?.[f.id]?.changed_share ?? 0) >= 0.02)
    if (filter === 'history') fs = fs.filter(f => tracked.person.has(f.id))
    if (sortBy === 'change' && compare) fs = [...fs].sort((a, b) => eff(b.id) - eff(a.id))
    return { ...c, fields: fs }
  }).filter(c => c.fields.length)
  const total = shown.reduce((s, c) => s + c.fields.length, 0)
  return (
    <aside className="fpane">
      <div className="fp-search">{G.search}<input type="search" value={q} onChange={e => setQ(e.target.value)} placeholder={`Search ${cats.reduce((s, c) => s + c.fields.length, 0)} fields`} aria-label="Search fields" /></div>
      <div className="fp-filters">
        <button className={`chip ${filter === 'all' ? 'on' : ''}`} onClick={() => setFilter('all')}>All</button>
        <button className={`chip ${filter === 'history' ? 'on' : ''}`} onClick={() => setFilter('history')} title="Fields kept for every person every two weeks: follow groups and people over time">{G.clock} Per-person history</button>
        {compare && <button className={`chip ${filter === 'changed' ? 'on' : ''}`} onClick={() => setFilter('changed')} title="Only fields that differ between the Original and the What-if">{G.butterfly} Changed</button>}
        {compare && <button className="chip" onClick={() => setSortBy(sortBy === 'name' ? 'change' : 'name')} title="Sort fields">{sortBy === 'name' ? 'A–Z' : 'Biggest change'}</button>}
      </div>
      <div className="fp-list">
        {shown.map(({ drawer, fields }) => {
          const isOpen = !!ql || filter !== 'all' || open[drawer.id]
          return (
            <div key={drawer.id} className="fp-drawer">
              <button className="fp-dhead" onClick={() => setOpen({ ...open, [drawer.id]: !open[drawer.id] })} aria-expanded={isOpen} title={drawer.blurb}>
                <span className="fp-dicon">{G[drawer.icon]}</span><b>{drawer.label}</b><span className="muted small">{fields.length}</span>
                <span className={`fp-chev ${isOpen ? 'open' : ''}`}>{G.chevron}</span>
              </button>
              {isOpen && fields.map(f => {
                const c = compare?.fields?.[f.id]
                return (
                  <button key={f.id} className={`fp-field ${value === f.id ? 'on' : ''}`} onClick={() => onPick(f.id)} title={f.desc ?? f.label}>
                    <span className="fp-name">{f.label}{tracked.person.has(f.id) && <i className="fp-dot" title="Per-person history kept" />}</span>
                    {c ? <FieldDelta f={f} c={c} /> : <span className="fp-val tabular">{summaryText(f, summary?.[f.id])}</span>}
                  </button>
                )
              })}
            </div>
          )
        })}
        {!total && <div className="empty small">No field matches “{q}”.</div>}
      </div>
    </aside>
  )
}

function FieldDelta({ f, c }: { f: VarSpec; c: any }) {
  if (Math.abs(c.effect ?? 0) < 0.005 && (c.changed_share ?? 0) < 0.005) return <span className="fp-val muted small">same</span>
  const title = `${sizeWord(c.effect)} change (standardized ${c.effect.toFixed(3)}); ${(100 * c.changed_share).toFixed(1)}% of people differ`
  if (c.kind === 'cat') return <DeltaChip d={c.top_delta} text={`${String(c.top).replace(/_/g, ' ')} ${fdelta(f, c.top_delta, true)}`} title={title} />
  if (c.kind === 'bool') return <DeltaChip d={c.delta} text={fdelta(f, c.delta, true)} polarity={polarity(f.id)} title={title} />
  return <DeltaChip d={c.delta} text={fdelta(f, c.delta)} polarity={polarity(f.id)} title={title} />
}

export { isCat }
