// Shared UX pieces: page headers with "how to use" help, story sentences, sparklines, follow buttons,
// plain-language effect sizes, and the simple/advanced switch.
import { ReactNode, useState } from 'react'
import { PersonLink } from './components'
import { useStore } from './store'

// ---------------------------------------------------------------- page header
export function PageHeader({ id, title, sub, tips, actions, eyebrow }: {
  id: string; title: ReactNode; sub?: ReactNode; tips?: ReactNode[]; actions?: ReactNode; eyebrow?: string
}) {
  const key = `ucsim-help-${id}`
  const [open, setOpen] = useState<boolean>(() => { try { return localStorage.getItem(key) !== 'closed' } catch { return true } })
  const toggle = () => { const v = !open; setOpen(v); try { localStorage.setItem(key, v ? 'open' : 'closed') } catch { /* ignore */ } }
  return (
    <header className="page-head">
      <div className="page-head-row">
        <div style={{ minWidth: 0 }}>
          {eyebrow && <div className="eyebrow">{eyebrow}</div>}
          <h1>{title}</h1>
          {sub && <p className="sub">{sub}</p>}
        </div>
        <div className="row" style={{ flex: 'none' }}>
          {actions}
          {tips && tips.length > 0 && <button className={`btn small help-btn ${open ? 'on' : ''}`} onClick={toggle} aria-expanded={open}>? How to use</button>}
        </div>
      </div>
      {open && tips && tips.length > 0 && (
        <ol className="help-tips">{tips.map((t, k) => <li key={k}>{t}</li>)}</ol>
      )}
    </header>
  )
}

// ---------------------------------------------------------------- simple / advanced
export function useAdvanced() { return useStore(s => s.mode) === 'advanced' }
export function Advanced({ children }: { children: ReactNode }) { return useAdvanced() ? <>{children}</> : null }

// ---------------------------------------------------------------- stories
/** Turn an event record into a sentence with clickable names, using the registry's story template. */
export function Story({ e, me }: { e: any; me?: number }) {
  const reg = useStore(s => s.registry)
  const tpl: string = reg?.events?.[e.type]?.story || `{a}: ${String(e.label ?? e.type).toLowerCase()}`
  const parts = tpl.split(/(\{a\}|\{b\})/)
  return (
    <>
      {parts.map((p, k) => {
        if (p === '{a}') return e.a === me ? <b key={k}>{e.a_name ?? 'They'}</b> : <PersonLink key={k} id={e.a} name={e.a_name} />
        if (p === '{b}') return e.b === null || e.b === undefined ? <span key={k}>someone</span> : e.b === me ? <b key={k}>{e.b_name}</b> : <PersonLink key={k} id={e.b} name={e.b_name} />
        return <span key={k}>{p}</span>
      })}
    </>
  )
}

export const CATEGORY_LABEL: Record<string, string> = {
  social: 'Friendship', romance: 'Dating & romance', religion: 'Faith', academics: 'School', work: 'Work & money',
  family: 'Family', health: 'Health', housing: 'Housing & moves', habits: 'Habits', sexuality: 'Intimacy', intervention: 'What-if',
}

// ---------------------------------------------------------------- numbers in words
/** Plain-language size of a standardized difference (Cohen-style thresholds). */
export function effectWord(sd: number) {
  const a = Math.abs(sd)
  if (a < 0.02) return 'no real change'
  if (a < 0.1) return 'a tiny change'
  if (a < 0.3) return 'a small change'
  if (a < 0.6) return 'a moderate change'
  return 'a large change'
}

export function Sparkline({ values, width = 120, height = 32, color = 'var(--accent)' }: { values: number[]; width?: number; height?: number; color?: string }) {
  const v = values.filter(x => Number.isFinite(x))
  if (v.length < 2) return <svg width={width} height={height} />
  const lo = Math.min(...v), hi = Math.max(...v), span = hi - lo || 1
  const pts = v.map((x, k) => [(k / (v.length - 1)) * (width - 4) + 2, height - 3 - ((x - lo) / span) * (height - 6)])
  const d = pts.map((p, k) => `${k ? 'L' : 'M'}${p[0].toFixed(1)},${p[1].toFixed(1)}`).join('')
  const last = pts[pts.length - 1]
  return (
    <svg width={width} height={height} aria-hidden="true" style={{ display: 'block' }}>
      <path d={`${d}L${last[0]},${height}L2,${height}Z`} fill={color} opacity={0.1} />
      <path d={d} fill="none" stroke={color} strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
      <circle cx={last[0]} cy={last[1]} r={3} fill={color} />
    </svg>
  )
}

// ---------------------------------------------------------------- following
export function FollowButton({ id, small }: { id: number; small?: boolean }) {
  const { toggleFollow, following, status } = useStore()
  void following; void status // re-render when either changes
  const on = useStore.getState().followed().includes(id)
  return (
    <button className={`btn ${small ? 'small' : ''} ${on ? 'following' : ''}`} onClick={e => { e.stopPropagation(); toggleFollow(id) }}
      title={on ? 'Stop following' : 'Follow this person: they appear on Home and in People → Following'}>
      {on ? '★ Following' : '☆ Follow'}
    </button>
  )
}

// ---------------------------------------------------------------- glossary terms
export const GLOSSARY: [string, string][] = [
  ['YSA ward', 'A congregation for young single adults (18–30). Most single students attend one near where they live; BYU has its own "BYU YSA" wards.'],
  ['Family / married-student ward', 'Congregations for married couples and families. Married students usually attend married-student wards.'],
  ['FHE group', 'Family Home Evening group: a small weekly group within a YSA ward, usually neighbors from the same complex. A big source of new friends and first dates.'],
  ['RM', 'Returned missionary: someone who has completed a mission (typically 2 years for men, 18 months for women).'],
  ['Early return', 'Coming home from a mission before the planned end, for health or other reasons.'],
  ['DTR', '"Define the relationship" — the conversation where two people agree to be exclusive.'],
  ['Talking', 'The pre-dating stage: mutual interest and regular contact, but not yet exclusive.'],
  ['NCMO', '"Non-committal make-out": kissing without dating or commitment.'],
  ['Honor Code', 'BYU\'s code of conduct (chastity, no alcohol/coffee/tea, dress and grooming, housing rules).'],
  ['Contracted housing', 'BYU-approved housing that enforces Honor Code rules; single BYU students are required to live in it.'],
  ['Temple recommend', 'A card showing a member is living Church standards; needed to attend the temple.'],
  ['Activity', 'How involved a member is: active (attends most weeks), less active, inactive, or not a member.'],
  ['Faith crisis', 'A period of serious doubt. In the model it resolves three ways: renewed faith, a more nuanced faith, or leaving the Church.'],
  ['Institute', 'Weekday religion classes for young adults near campuses (UVU students especially).'],
  ['Kyhv Peak', 'A mountain overlook above Provo, formerly called Squaw Peak; a well-known make-out spot.'],
  ['Cohort', 'Any group of people you pick with filters (e.g. "single BYU women, 18–23"). It follows you to every page.'],
  ['What-if world', 'A copy of the world where one thing is changed. It shares the same random dice as the original, so differences come from the change.'],
  ['Mechanism', 'A rule of the model: how one thing affects another (e.g. "close friends reduce loneliness"), with a strength and an evidence label.'],
]
