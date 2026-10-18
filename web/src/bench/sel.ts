// Small helpers over the shared selection (selection.ts holds the contract; these only read it).
import type { Universe } from '../api'
import { condLabel } from '../components'
import type { Registry } from '../store'
import type { Ref, Selection } from './selection'

/** The one person a single-person tool shows: the focused person, else the first selected one. */
export function subjectPerson(sel: Selection): number | null {
  if (sel.item?.kind === 'person' && Number.isFinite(Number(sel.item.id))) return Number(sel.item.id)
  return sel.people?.length ? sel.people[0] : null
}

/** Focus something through a panel's own setSel, the way the bench's focus() does (a person also becomes the
 *  selected people). */
export function focusVia(setSel: (s: Partial<Selection>) => void, r: Ref) {
  setSel(r.kind === 'person' ? { item: r, people: [Number(r.id)] } : { item: r })
}

/** Point at something without changing who is selected (clicking a row in a list of the selection keeps the list). */
export function focusItem(setSel: (s: Partial<Selection>) => void, r: Ref) { setSel({ item: r }) }

/** The people a tool about people shows: the selected ones, else the focused person. */
export function selPeople(sel: Selection): number[] {
  if (sel.people?.length) return sel.people
  const p = sel.item?.kind === 'person' ? Number(sel.item.id) : NaN
  return Number.isFinite(p) ? [p] : []
}

/** The world a panel reads: the one its focused item (an event, an occasion…) came from, else the lens. People are the
 *  same people in both worlds, so tools about people follow the lens. */
export const worldOf = (sel: Selection, lensU: Universe): Universe => sel.item?.u ?? lensU

/** The selection as the server's group description (ids and/or filter conditions). */
export function selGroup(sel: Selection): { people?: number[]; filter?: any[] } {
  return { people: sel.people?.length ? sel.people : undefined, filter: sel.filter?.length ? sel.filter : undefined }
}
export const hasGroup = (sel: Selection) => !!(sel.people?.length || sel.filter?.length)

/** A stable key for what a selection asks for (for caching and effect deps). */
export const selKey = (sel: Selection) => JSON.stringify([sel.people ?? null, sel.filter ?? null, sel.time ?? null, sel.item ?? null])

/** Plain words for a selection ("Maya Johnson", "3 people", "Lonely (top 20%)", with the time window). */
export function describeSel(sel: Selection, name: (i: number) => string, reg: Registry | null, dayWords?: (d: number) => string): string {
  const bits: string[] = []
  if (sel.item && sel.item.kind !== 'person') bits.push(sel.item.label ?? `${sel.item.kind} ${sel.item.id}`)
  if (sel.people?.length === 1) bits.push(name(sel.people[0]))
  else if (sel.people?.length) bits.push(`${sel.people.length.toLocaleString()} people`)
  else if (sel.item?.kind === 'person') bits.push(sel.item.label ?? name(Number(sel.item.id)))
  if (sel.filter?.length) bits.push(sel.filter.map(c => condLabel(c, reg)).join(' · '))
  if (sel.time && dayWords) bits.push(`${dayWords(sel.time[0])} – ${dayWords(sel.time[1])}`)
  return bits.join(', ') || 'nothing yet'
}
