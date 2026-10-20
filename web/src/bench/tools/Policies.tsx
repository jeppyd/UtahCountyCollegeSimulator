// Policies: BYU's and UVU's campus rules as published (Honor Code, ecclesiastical endorsement, housing, UVU's Student
// Code), each with its source and what the model does with it — and, for the Honor Code, what has happened in this
// world so far: reports, warnings, probations, suspensions, withdrawn endorsements and who left BYU.
import { useState } from 'react'
import { benchApi } from '../../api'
import { useAsync } from '../../game'
import { Busy, Problem } from '../../kit/Bits'
import { useLens, useStore } from '../../store'
import { PanelOptions } from '../panel'
import type { PanelProps, ToolDef } from '../registry'

const STATUS: Record<string, [string, string]> = {
  modelled: ['in the model', 'yes'], data: ['shown, not simulated', 'quiet'], not_binding: ['never binds in the model', 'quiet'],
}

function PoliciesTool({ setSel, opts, setOpts }: PanelProps) {
  const u = useLens().u
  const dataVersion = useStore(s => s.dataVersion)
  const school: string = opts.school ?? 'BYU'
  const [open, setOpen] = useState<string | null>(null)
  const data = useAsync(() => benchApi.policies(u), [u, Math.floor(dataVersion / 4)], { key: `bench-policies:${u}` })
  const d = data.data
  const show = (cond: any) => setSel({ filter: [cond], people: undefined })
  return (
    <div className="bk">
      <PanelOptions>
        <div className="seg">{['BYU', 'UVU'].map(s => <button key={s} className={school === s ? 'on' : ''} onClick={() => setOpts({ ...opts, school: s })}>{s}</button>)}</div>
      </PanelOptions>
      {data.error && !d && <Problem error={data.error} />}
      {!d && !data.error && <Busy what="Reading the policies" />}
      {d && school === 'BYU' && d.live && (
        <div className="bk-why">
          <b>The Honor Code in this world so far</b> <span className="bx-note">({d.live.days} days, {d.live.byu_students.toLocaleString()} BYU students now)</span>
          <div className="bk-facts">
            <span><b>{(d.live.events.honor_reported ?? 0).toLocaleString()}</b> reports</span>
            <span><b>{(d.live.events.honor_warning ?? 0).toLocaleString()}</b> warnings</span>
            <span><b>{(d.live.events.honor_probation ?? 0).toLocaleString()}</b> probations</span>
            <span><b>{(d.live.events.honor_suspended ?? 0).toLocaleString()}</b> suspensions</span>
            <span><b>{(d.live.events.endorsement_withdrawn ?? 0).toLocaleString()}</b> endorsements withdrawn</span>
            <span><b>{(d.live.events.left_byu ?? 0).toLocaleString()}</b> left BYU{d.live.totals ? ` (${d.live.totals.left.transferred_to_uvu} to UVU)` : ''}</span>
          </div>
          <div className="bk-chips">
            <button className="bk-more" onClick={() => show({ var: 'honor_standing', op: 'in', value: ['probation'] })}>Select students on probation ({d.live.standing.probation ?? 0})</button>
            <button className="bk-more" onClick={() => show({ var: 'honor_standing', op: 'in', value: ['warned'] })}>Select warned students ({d.live.standing.warned ?? 0})</button>
            <button className="bk-more" onClick={() => show({ recent_event: 'left_byu', days: 3650 })}>Select those who left BYU</button>
          </div>
          <div className="bx-note">Today's switches: enforcement ×{Number(d.switches.honor_enforcement ?? 1).toFixed(1)}, endorsement {d.switches.endorsement_required ? 'required' : 'not required'},
            contracted housing for first-years {d.switches.contracted_housing_required ? 'required' : 'not required'}. Change them as a What-if ("BYU stops enforcing the Honor Code", "BYU drops the endorsement requirement").</div>
        </div>
      )}
      <div className="bk-list">
        {d && (d.policies as any[]).filter(p => p.school === school).map(p => {
          const [word, cls] = STATUS[p.status] ?? [p.status, 'quiet']
          const on = open === p.id
          return (
            <div key={p.id} className="bk-li click" style={{ flexDirection: 'column', alignItems: 'stretch' }} onClick={() => setOpen(on ? null : p.id)}>
              <span className="grow" style={{ justifyContent: 'space-between' }}><b>{p.title}</b><span className={`bk-pill ${cls}`}>{word}</span></span>
              {on && (
                <div onClick={e => e.stopPropagation()} style={{ cursor: 'auto' }}>
                  <ul className="bk-sub" style={{ margin: '4px 0', paddingLeft: 18 }}>{p.rules.map((r: string, k: number) => <li key={k}>{r}</li>)}</ul>
                  {p.notes && <div className="bx-note"><b>In the model:</b> {p.notes}</div>}
                  {p.calibration && <div className="bx-note"><b>Numbers it is fitted to:</b> {p.calibration.join(' · ')}</div>}
                  <div className="bx-note">Version: {p.version} · <a href={p.source} target="_blank" rel="noreferrer">official source</a></div>
                </div>
              )}
            </div>
          )
        })}
      </div>
      <div className="bx-note">Summaries in plain words, retrieved October 2026; the linked pages are the binding text.</div>
    </div>
  )
}

export const tool: ToolDef = {
  id: 'policies',
  label: 'Policies',
  icon: 'book',
  hint: "BYU's and UVU's campus rules (Honor Code, endorsement, housing, UVU's Student Code) with sources, and what they're doing in this world.",
  group: 'world',
  order: 40,
  component: PoliciesTool,
  size: { w: 5, h: 8 },
}
