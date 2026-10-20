// Story: one person's life read as chapters — a sentence per notable moment, with the top reasons behind it and each
// reason's share of the push. Repeats are folded ("3 times"). Click a sentence to focus it (Why, Trace and Ripple
// follow); the shared time window narrows the story.
import { useState } from 'react'
import { benchApi } from '../../api'
import { useAsync } from '../../game'
import { Busy, CatDot, Empty, Problem } from '../../kit/Bits'
import { pct } from '../../kit/ShareBar'
import { useLens, useStore } from '../../store'
import { PanelOptions } from '../panel'
import type { PanelProps, ToolDef } from '../registry'
import { focusItem, subjectPerson } from '../sel'

function StoryTool({ sel, setSel, opts, setOpts }: PanelProps) {
  const u = useLens().u
  const dataVersion = useStore(s => s.dataVersion)
  const who = subjectPerson(sel)
  const reasons: boolean = opts.reasons ?? true
  const [shut, setShut] = useState<Record<string, boolean>>({})
  const d = useAsync(() => (who == null ? Promise.resolve(null) : benchApi.story(who, u, sel.time)),
    [who, u, sel.time?.[0], sel.time?.[1], Math.floor(dataVersion / 4)], { key: `bench-story:${u}:${who}` })
  if (who == null) return <Empty title="Pick a person">Select someone (in People, the map or anywhere a name shows) to read their story.</Empty>
  if (d.error) return <Problem error={d.error} />
  const s = d.data
  if (!s) return <Busy what="Writing their story" />
  const focusId = sel.item?.kind === 'event' ? Number(sel.item.id) : null
  return (
    <div className="bk story">
      <PanelOptions>
        <label className="bt-row" style={{ whiteSpace: "nowrap", gap: 4 }}><input type="checkbox" checked={reasons} onChange={e => setOpts({ ...opts, reasons: e.target.checked })} /> show reasons</label>
      </PanelOptions>
      <div className="bk-why"><b>{s.name}</b> <span className="bx-note">{s.n_events.toLocaleString()} notable moments{sel.time ? ' in the chosen window' : ''}</span></div>
      {!s.chapters.length && <Empty title="Nothing notable yet">Run time forward, or widen the time window.</Empty>}
      {[...s.chapters].reverse().map(c => {
        const k = `${c.start}:${c.title}`
        const closed = shut[k] ?? false
        return (
          <section key={k} className="story-ch">
            <h4 className="click" onClick={() => setShut({ ...shut, [k]: !closed })}>{closed ? '▸' : '▾'} {c.title} <span className="bx-note">{c.lines.length}</span></h4>
            {!closed && c.lines.map(l => (
              <p key={l.event} className={`story-line click ${focusId === l.event ? 'on' : ''}`}
                onClick={() => focusItem(setSel, { kind: 'event', id: l.event, label: l.text, u })}>
                <span className="when">{l.date.slice(5)}</span>
                <CatDot c={l.category} />
                <span>
                  {l.text}{l.times > 1 ? ` (${l.times} times)` : ''}.
                  {reasons && l.reasons.length > 0 && (
                    <span className="story-why"> Mostly {l.reasons.map((r, j) => (
                      <span key={j}>{j ? (j === l.reasons.length - 1 ? ' and ' : ', ') : ''}{r.words} <b>{pct(r.share)}</b></span>
                    ))}{l.chance != null ? <span className="bx-note"> · chance {pct(l.chance)}</span> : null}</span>
                  )}
                </span>
              </p>
            ))}
          </section>
        )
      })}
      <div className="bx-note">{s.note} Reasons are the model's, inside this simulated world.</div>
    </div>
  )
}

export const tool: ToolDef = {
  id: 'story',
  label: 'Story',
  icon: 'book',
  hint: "One person's life as chapters of plain sentences, each with the reasons behind it and their share of the push.",
  group: 'people',
  order: 15,
  component: StoryTool,
  size: { w: 6, h: 8 },
  needs: ['people'],
}
