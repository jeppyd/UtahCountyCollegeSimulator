// The field catalog: every person field the model tracks, sorted into friendly drawers, with
// plain-language formatting. Used by the explorer, the palette, the butterfly scan and life pages.
import { fmt } from './analysis'
import type { Registry, VarSpec } from './store'

export type Drawer = { id: string; label: string; icon: string; blurb: string }

export const DRAWERS: Drawer[] = [
  { id: 'feelings', label: 'Feelings', icon: 'heart', blurb: 'Mood, loneliness, stress, belonging and the other states that rise and fall day to day' },
  { id: 'social', label: 'Friends & social life', icon: 'people', blurb: 'How many friends, how close, how much time together' },
  { id: 'dating', label: 'Dating & romance', icon: 'romance', blurb: 'Relationship status, dates, apps, breakups, satisfaction' },
  { id: 'looking', label: 'What they look for', icon: 'spark', blurb: 'Date ideas they like and what matters in a partner' },
  { id: 'faith', label: 'Faith', icon: 'faith', blurb: 'Belief, attendance, identity, missions, temple, other faiths' },
  { id: 'values', label: 'Values & intimacy', icon: 'scale', blurb: 'Politics, family plans, chastity, kissing and more' },
  { id: 'school', label: 'School', icon: 'school', blurb: 'School, year, major area, GPA, study habits' },
  { id: 'work', label: 'Work & money', icon: 'money', blurb: 'Jobs, hours, wages, savings, debt, family support' },
  { id: 'home', label: 'Home & neighborhood', icon: 'places', blurb: 'Where they live, rent, commute, neighborhood' },
  { id: 'habits', label: 'Habits & interests', icon: 'coffee', blurb: 'Sleep, workouts, social media, coffee, hobbies' },
  { id: 'personality', label: 'Personality', icon: 'mask', blurb: 'The Big Five and other stable traits' },
  { id: 'background', label: 'Background & body', icon: 'id', blurb: 'Age, sex, origin, family, height and looks' },
  { id: 'now', label: 'Right now', icon: 'clock', blurb: 'What they are doing at this hour' },
]

const FEELINGS = new Set(['mood', 'stress', 'loneliness', 'anxiety', 'belonging', 'self_esteem', 'guilt', 'fatigue', 'purpose', 'financial_stress',
  'academic_pressure', 'romantic_longing', 'life_satisfaction', 'mh_anxiety', 'mh_depression', 'mh_adhd', 'depressive_episode', 'future_confidence'])
const SOCIAL = new Set(['n_friends', 'n_groups', 'n_close_friends', 'n_acquaintances', 'degree', 'new_friends_90d', 'social_hours_week',
  'close_contact_hours', 'roommate_cohesion', 'ward_belonging', 'social_events_month'])
const LOOKING = new Set(['imp_spirituality', 'imp_physical', 'imp_personality', 'imp_shared_interests', 'prefers_rm', 'min_height_req',
  'max_older', 'max_younger', 'picky'])
const SCHOOL = new Set(['school', 'enrolled', 'class_standing', 'credits_done', 'credits_term', 'study_area', 'college', 'gpa', 'gpa_term',
  'academic_standing', 'study_hours', 'class_attendance', 'homework_early', 'cheats_school', 'graduated'])
const HOME = new Set(['rent', 'rent_burden', 'city', 'neighborhood', 'living', 'dist_campus_km', 'commute_min'])
const NOW = new Set(['activity_now', 'ill'])

export function drawerOf(v: VarSpec): string {
  const id = v.id
  if (NOW.has(id)) return 'now'
  if (FEELINGS.has(id)) return 'feelings'
  if (SOCIAL.has(id)) return 'social'
  if (LOOKING.has(id) || v.domain === 'preferences_dates') return 'looking'
  if (HOME.has(id)) return 'home'
  if (SCHOOL.has(id)) return 'school'
  switch (v.domain) {
    case 'dating': return 'dating'
    case 'religion': return 'faith'
    case 'values_sexuality': return 'values'
    case 'academics_work': return 'work'
    case 'habits_interests': return 'habits'
    case 'personality': return 'personality'
    case 'demographics': return 'background'
    case 'social_emotion': return 'social'
  }
  return 'background'
}

/** Person fields worth browsing: chartable, not internal ids or coordinates. */
export function browsable(reg: Registry): VarSpec[] {
  return Object.values(reg.variables).filter(v => v.entity === 'person' && v.dtype !== 'str' && (v.flags ?? []).includes('chart') && !v.id.endsWith('_id'))
}

export function catalog(reg: Registry): { drawer: Drawer; fields: VarSpec[] }[] {
  const by: Record<string, VarSpec[]> = {}
  for (const v of browsable(reg)) (by[drawerOf(v)] ??= []).push(v)
  return DRAWERS.filter(d => by[d.id]?.length).map(d => ({ drawer: d, fields: by[d.id].sort((a, b) => a.label.localeCompare(b.label)) }))
}

export const isCat = (v?: VarSpec) => !!v && (v.dtype === 'cat' || v.dtype === 'bool')
export const pretty = (s: any) => String(s).replace(/_/g, ' ')

const MONEY = /usd|\$|dollar/i
/** A value of this field, formatted the way a person would say it. */
export function fval(v: VarSpec | undefined, x: any, digits = 2): string {
  if (x === null || x === undefined || (typeof x === 'number' && Number.isNaN(x))) return '—'
  if (!v) return typeof x === 'number' ? fmt(x, digits) : pretty(x)
  if (v.dtype === 'bool') return typeof x === 'number' ? (x ? 'yes' : 'no') : x ? 'yes' : 'no'
  if (v.dtype === 'cat') return typeof x === 'number' ? pretty(v.categories?.[x] ?? x) : pretty(x)
  if (typeof x !== 'number') return pretty(x)
  if (v.ordinal && Number.isInteger(x) && v.ordinal[x]) return pretty(v.ordinal[x])
  if (MONEY.test(v.units ?? '')) return `$${Math.round(x).toLocaleString()}`
  if (v.id === 'gpa' || v.id === 'gpa_term') return x.toFixed(2)
  if (v.id === 'age') return x.toFixed(1)
  if (v.dtype !== 'f4' && v.dtype !== 'f8') return Math.abs(x) >= 1000 ? Math.round(x).toLocaleString() : String(Math.round(x * 10) / 10)
  return fmt(x, digits)
}

/** An average of this field: means of whole-number fields keep their decimals. */
export function favg(v: VarSpec | undefined, x: any, digits = 2): string {
  if (!v || v.dtype === 'f4' || v.dtype === 'f8' || isCat(v) || typeof x !== 'number' || (v.ordinal && Number.isInteger(x))) return fval(v, x, digits)
  if (Number.isNaN(x)) return '—'
  if (MONEY.test(v.units ?? '')) return `$${Math.round(x).toLocaleString()}`
  const a = Math.abs(x)
  return a >= 100 ? Math.round(x).toLocaleString() : x.toFixed(a >= 10 ? 1 : digits)
}

/** Two averages side by side (Original, What-if), with enough digits that a real difference shows. */
export function fpair(v: VarSpec | undefined, a: number, b: number): [string, string] {
  let sa = favg(v, a), sb = favg(v, b)
  for (let d = 3; d <= 4 && sa === sb && a !== b && typeof a === 'number' && Math.abs(a) < 100; d++) { sa = favg(v, a, d); sb = favg(v, b, d) }
  return [sa, sb]
}

/** A difference in this field (What-if − Original), signed. */
export function fdelta(v: VarSpec | undefined, d: number, share = false): string {
  if (d === null || d === undefined || Number.isNaN(d)) return '—'
  const s = d > 0 ? '+' : d < 0 ? '−' : '±'
  const a = Math.abs(d)
  if (share) return `${s}${(100 * a).toFixed(a < 0.001 ? 2 : 1)} pts`
  if (v && MONEY.test(v.units ?? '')) return `${s}$${Math.round(a).toLocaleString()}`
  return `${s}${a >= 100 ? Math.round(a).toLocaleString() : a >= 1 ? a.toFixed(2) : a.toPrecision(2)}`
}

export const pctStr = (p: number, d = 1) => (p === null || p === undefined || Number.isNaN(p) ? '—' : `${(100 * p).toFixed(d)}%`)

/** Plain words for a standardized change (Cohen's d or h). */
export function sizeWord(e: number) {
  const a = Math.abs(e)
  if (a < 0.02) return 'no real change'
  if (a < 0.1) return 'tiny'
  if (a < 0.3) return 'small'
  if (a < 0.6) return 'moderate'
  return 'large'
}

/** Is a higher value of this field generally good, bad or neither? (for coloring only, never for claims) */
const GOOD_UP = new Set(['mood', 'belonging', 'self_esteem', 'purpose', 'life_satisfaction', 'n_friends', 'n_close_friends', 'gpa', 'savings',
  'relationship_satisfaction', 'ward_belonging', 'roommate_cohesion', 'sleep_hours', 'future_confidence'])
const GOOD_DOWN = new Set(['loneliness', 'stress', 'anxiety', 'guilt', 'fatigue', 'financial_stress', 'academic_pressure', 'depressive_episode',
  'rent_burden', 'debt', 'outsider', 'rejections_recent'])
export function polarity(id: string): 1 | -1 | 0 { return GOOD_UP.has(id) ? 1 : GOOD_DOWN.has(id) ? -1 : 0 }

/** Standard groups recorded over time (keep in sync with ucsim/engine/systems/recorder.py). */
export const GROUPS: [string, string][] = [['all', 'Everyone'], ['BYU', 'BYU students'], ['UVU', 'UVU students'], ['F', 'Women'], ['M', 'Men'], ['single', 'Singles'], ['married', 'Married']]

/** Fields people most often split by. */
export const SPLITS = ['school', 'sex', 'rel_status', 'activity', 'class_standing', 'affiliation', 'living', 'role', 'mission_status', 'employed', 'city', 'study_area']
