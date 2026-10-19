// Interview: talk with the selected person. They answer in the first person from what they know about their own
// life — how they feel, what they believe, how they see the people around them, what they remember — and nothing
// else; every sentence is checked. Interviewing changes nothing in the world. "Where their view differs from
// what's true" is computed by the simulator, not by the model.
import { useEffect, useState } from 'react'
import { talkApi, type TalkResult } from '../../api'
import { useAsync } from '../../game'
import { Answer, Steps, useTalkJob } from '../../kit/Answer'
import { Empty, Problem } from '../../kit/Bits'
import { RefChip, usePersonName } from '../../kit/RefChip'
import { useLens } from '../../store'
import { PanelOptions } from '../panel'
import type { PanelProps, ToolDef } from '../registry'
import { subjectPerson } from '../sel'
import { BackendPick } from './Ask'

const STARTERS = ['How are you doing lately?', 'Who do you feel closest to?', 'What has been on your mind?', 'How do you feel about your faith?']

function InterviewTool({ sel, opts, setOpts }: PanelProps) {
  const lens = useLens()
  const u = opts.whatif && lens.hasAlt ? 'alt' : 'base'
  const who = subjectPerson(sel)
  const name = usePersonName(u)
  const [q, setQ] = useState('')
  const [turns, setTurns] = useState<{ q: string; res: TalkResult }[]>([])
  const t = useTalkJob()
  const showDiff: boolean = opts.differs ?? false
  useEffect(() => { setTurns([]); t.reset() }, [who, u])
  useEffect(() => {
    const r = t.job?.result
    if (t.job?.state === 'done' && r) { setTurns(ts => [...ts, { q: r.question, res: r }]); setQ('') }
  }, [t.job?.state])
  const diff = useAsync(() => (showDiff && who !== null ? talkApi.differs(who, u) : Promise.resolve(null)), [showDiff, who, u])

  if (who === null) return <Empty title="Nobody selected">Select a person to talk with them.</Empty>
  const history = turns.map(x => ({ q: x.q, a: x.res.sentences.map(s => s.text).join(' ') }))
  const go = (text = q) => { if (text.trim()) t.run(() => talkApi.interview(who, text.trim(), history, u)) }
  return (
    <div className="bk">
      <PanelOptions>
        <BackendPick feature="interview" />
        <label className="bt-row" style={{ gap: 4, whiteSpace: 'nowrap', flexWrap: 'nowrap' }} title="Computed by the simulator from what they believe and what is true">
          <input type="checkbox" checked={showDiff} onChange={e => setOpts({ ...opts, differs: e.target.checked })} /> view vs. truth
        </label>
        {lens.hasAlt && <label className="bt-row" style={{ gap: 4, whiteSpace: 'nowrap', flexWrap: 'nowrap' }} title="Talk with the same person in the What-if world">
          <input type="checkbox" checked={!!opts.whatif} onChange={e => setOpts({ ...opts, whatif: e.target.checked })} /> in the What-if
        </label>}
      </PanelOptions>
      <div className="ta-who">Talking with <RefChip r={{ kind: 'person', id: who, label: name(who), u }} />{u === 'alt' ? ' in the What-if world' : ''}. Nothing you ask changes their life.</div>
      {showDiff && diff.data && (
        <div className="ta-differs">
          {diff.data.length === 0 ? 'Their view of their support, friends and abilities is about right.' : (
            <ul>{diff.data.map(d => <li key={d.what}><b>{d.what}:</b> {d.words.toLowerCase()} (they think {d.believed.toFixed(2)}; it is {d.actual.toFixed(2)})</li>)}</ul>
          )}
        </div>
      )}
      {turns.map((x, k) => <div key={k} className="ta-turn"><div className="ta-q">You: {x.q}</div><Answer res={x.res} firstPerson /></div>)}
      {turns.length === 0 && !t.job && <div className="ta-examples">{STARTERS.map(x => <button key={x} onClick={() => { setQ(x); go(x) }}>{x}</button>)}</div>}
      {t.error && <Problem error={t.error} />}
      {t.job && t.busy && <Steps job={t.job} />}
      {t.job?.state === 'error' && <Problem error={t.job.error ?? 'Something went wrong'} />}
      <div className="ta-ask">
        <textarea value={q} placeholder={`Ask ${name(who).split(' ')[0]} something…`} onChange={e => setQ(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); go() } }} />
        {t.busy ? <button onClick={t.cancel}>Stop</button> : <button onClick={() => go()} disabled={!q.trim()}>Ask</button>}
      </div>
    </div>
  )
}

export const tool: ToolDef = {
  id: 'interview',
  label: 'Interview',
  icon: 'mind',
  hint: 'Talk with the selected person: they answer from what they know about their own life, and every sentence is checked.',
  group: 'talk',
  order: 20,
  component: InterviewTool,
  size: { w: 5, h: 8 },
  needs: ['people'],
}
