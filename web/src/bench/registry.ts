// The shelf of raw tools. Every file in ./tools/ that exports `tool` (or `tools`) is registered automatically,
// so adding a tool never means editing a shared list.
import type { ComponentType } from 'react'
import type { Selection } from './selection'

export type PanelProps = {
  /** the selection this panel shows (the shared one, or the panel's pinned copy) */
  sel: Selection
  /** change the selection this panel is bound to */
  setSel: (s: Partial<Selection>) => void
  panelId: string
  /** per-panel settings (which field, which mode…), saved with the layout */
  opts: Record<string, any>
  setOpts: (o: Record<string, any>) => void
}
export type ToolGroup = 'see' | 'trace' | 'people' | 'places' | 'talk' | 'world'
export type ToolDef = {
  id: string
  label: string
  /** a key of game.tsx's glyph set G */
  icon: string
  /** one sentence: what it shows and how to use it */
  hint: string
  group: ToolGroup
  order?: number
  component: ComponentType<PanelProps>
  /** grid cells (12 columns wide; rows of ~60 px) */
  size?: { w: number; h: number }
  /** what the tool needs from the selection to show something */
  needs?: ('people' | 'item' | 'time')[]
}

const TOOLS = new Map<string, ToolDef>()
export function registerTool(t: ToolDef) { TOOLS.set(t.id, t) }
export function getTool(id: string): ToolDef | undefined { return TOOLS.get(id) }
export function allTools(): ToolDef[] {
  return [...TOOLS.values()].sort((a, b) => (a.group === b.group ? (a.order ?? 50) - (b.order ?? 50) : a.group.localeCompare(b.group)))
}

const mods = import.meta.glob('./tools/*.tsx', { eager: true }) as Record<string, { tool?: ToolDef; tools?: ToolDef[] }>
for (const m of Object.values(mods)) {
  if (m.tool) registerTool(m.tool)
  m.tools?.forEach(registerTool)
}
