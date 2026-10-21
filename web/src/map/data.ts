// The living map's data: real building footprints with heights (geo/buildings3d.bin), everyone's precise position
// (in their room, at their table, in their seat: /api/positions/precise) and the inside of one building.
import { api, decodePack, fetchBytes, STATIC, type Universe } from '../api'

export const KINDS = ['other', 'house', 'townhouse', 'apartments', 'dorm', 'mobile', 'campus', 'school', 'church', 'commercial',
  'office', 'industrial', 'civic', 'sports', 'parking', 'minor'] as const
export type Buildings = {
  n: number
  ids: Int32Array
  height: Float32Array        // metres
  floors: Uint8Array
  kind: Uint8Array
  /** polygon k is rings[k]: [lon, lat][] (open ring) */
  rings: [number, number][][]
  byId: Map<number, number>
}

let bCache: Promise<Buildings> | null = null
/** Decode web/public/geo/buildings3d.bin (format in ucsim/geo/buildings.py write_web). */
export function loadBuildings3d(): Promise<Buildings> {
  bCache ??= fetchBytes(api.geo('buildings3d.bin')).then(buf => {
    const dv = new DataView(buf)
    const magic = String.fromCharCode(dv.getUint8(0), dv.getUint8(1), dv.getUint8(2), dv.getUint8(3))
    if (magic !== 'UB3D') throw new Error('unexpected building file')
    const n = dv.getInt32(6, true)
    const lon0 = dv.getFloat64(10, true), lat0 = dv.getFloat64(18, true)
    let off = 26
    const ids = new Int32Array(n), height = new Float32Array(n), floors = new Uint8Array(n), kind = new Uint8Array(n)
    const rings: [number, number][][] = new Array(n)
    const byId = new Map<number, number>()
    for (let k = 0; k < n; k++) {
      ids[k] = dv.getInt32(off, true); height[k] = dv.getUint16(off + 4, true) / 10; floors[k] = dv.getUint8(off + 6); kind[k] = dv.getUint8(off + 7)
      const m = dv.getUint16(off + 8, true)
      let x = dv.getInt32(off + 10, true), y = dv.getInt32(off + 14, true)
      off += 18
      const ring: [number, number][] = new Array(m)
      ring[0] = [lon0 + x / 1e6, lat0 + y / 1e6]
      for (let j = 1; j < m; j++) { x += dv.getInt16(off, true); y += dv.getInt16(off + 2, true); off += 4; ring[j] = [lon0 + x / 1e6, lat0 + y / 1e6] }
      rings[k] = ring
      byId.set(ids[k], k)
    }
    return { n, ids, height, floors, kind, rings, byId }
  })
  return bCache
}

export type Precise = {
  n: number
  lon: Float64Array; lat: Float64Array; z: Float32Array
  building: Int32Array; floor: Uint8Array
  act: Uint8Array; actNames: string[]
  ctx: Uint8Array; ctxNames: string[]
  place: Int32Array
  day: number; hour: number; block: number; date: string; blockWords: string
}

export async function loadPrecise(u: Universe, block: 'now' | number = 'now'): Promise<Precise> {
  const cols = decodePack(await fetchBytes(`/api/positions/precise?u=${u}&block=${block}`))
  const x = cols.x.data as Float32Array, y = cols.y.data as Float32Array
  const [lo0, la0] = cols.x.meta.origin as [number, number]
  const [kx, ky] = cols.x.meta.m_per_deg as [number, number]
  const n = x.length
  const lon = new Float64Array(n), lat = new Float64Array(n)
  for (let i = 0; i < n; i++) { lon[i] = lo0 + x[i] / kx; lat[i] = la0 + y[i] / ky }
  const fr = cols.frame.data as Int32Array
  return {
    n, lon, lat, z: cols.z.data as Float32Array, building: cols.building.data as Int32Array, floor: cols.floor.data as Uint8Array,
    act: cols.act.data as Uint8Array, actNames: cols.act.categories ?? [], ctx: cols.ctx.data as Uint8Array, ctxNames: cols.ctx.categories ?? [],
    place: cols.place.data as Int32Array, day: fr[0], hour: fr[1], block: fr[2], date: cols.frame.meta.date, blockWords: cols.frame.meta.block_words,
  }
}

export type Rect = { corners: [number, number][]; z: number }
export type BuildingInside = {
  building: number; name: string | null; kind: string; floors: number; area_m2: number
  origin: [number, number]; m_per_deg: [number, number]; storey_m: number
  homes: { unit: number; label: string; floor: number; complex: string | null; beds: number; kind: string; shape: Rect; living: Rect
    rooms: { room: number; beds: number; shape: Rect | null; people: { id: number; name: string }[] }[] }[]
  inside_now: { id: number; name: string; floor: number; doing: string }[]
  n_inside_now: number
  when: { day: number; hour: number; date: string }
}
export async function loadBuilding(b: number, u: Universe): Promise<BuildingInside> {
  const r = await fetch(`/api/building/${b}?u=${u}`)
  if (!r.ok) throw new Error(`${r.status} building ${b}`)
  return r.json()
}
/** Metres from the origin to lon/lat. */
export const toLonLat = (d: { origin: [number, number]; m_per_deg: [number, number] }, p: [number, number]): [number, number] =>
  [d.origin[0] + p[0] / d.m_per_deg[0], d.origin[1] + p[1] / d.m_per_deg[1]]

/** How often the map redraws people while time runs: frozen (only when paused), once per simulated day, or after
 *  every part of the day. 'auto' = every part of the day at the slower speeds, once a day at top speed. */
export type Refresh = 'auto' | 'paused' | 'daily' | 'live'
export const REFRESH_WORDS: Record<Refresh, string> = {
  auto: 'Automatic: every part of the day at speeds 1–2, once a day at top speed',
  live: 'After every part of the day (morning, afternoon, evening, late evening, night)',
  daily: 'Once per simulated day',
  paused: 'Only when time is paused',
}
/** A key that changes exactly when the map should fetch new positions. */
export function refreshKey(policy: Refresh, status: any): string {
  const running = status?.job?.state === 'running'
  const day = status?.day ?? 0, hour = status?.hour ?? 0
  const pace = status?.job?.pace ?? 0
  const eff = policy === 'auto' ? (running && pace === 0 ? 'daily' : 'live') : policy
  if (!running) return `idle:${day}:${hour}`
  if (eff === 'paused') return 'running'
  if (eff === 'daily') return `d:${day}`
  return `h:${day}:${hour}:${status?.perf?.day ?? ''}`
}
export const LIVE = !STATIC

const coreCache = new Map<string, Promise<Set<number>>>()
/** Ids of the buildings people use in this world (drawn standing in 3D; the rest are drawn flat). */
export function loadCore(u: Universe, version: number): Promise<Set<number>> {
  const k = `${u}:${version}`
  if (!coreCache.has(k)) {
    coreCache.clear()
    coreCache.set(k, fetchBytes(`/api/buildings/core?u=${u}`).then(b => new Set(Array.from(new Int32Array(b)))).catch(() => new Set<number>()))
  }
  return coreCache.get(k)!
}
