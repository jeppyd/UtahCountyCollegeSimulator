// Ask the world: a question in plain words, answered only from facts the simulator looks up (who matches, which
// places rank highest, how many events, why a feeling is what it is). Every sentence is checked against those
// facts; people, places and events in the answer are chips you can click. Uses your own model login.
import { useAiSetup } from '../../kit/AiSetup'
import { useState } from 'react'
import { talkApi, type TalkStatus } from '../../api'
import { useAsync } from '../../game'
import { Answer, Steps, useTalkJob } from '../../kit/Answer'
import { Problem } from '../../kit/Bits'
import { useLens } from '../../store'
import { PanelOptions } from '../panel'
import type { PanelProps, ToolDef } from '../registry'
import { selPeople } from '../sel'

const EXAMPLES = ['Which apartment complexes are loneliest?', 'How many breakups happened this month?',
  'Why are UVU students stressed?', 'Who are the loneliest BYU freshmen?']
export const BACKENDS: [string, string][] = [['auto', 'Automatic'], ['claude', 'Claude (subscription)'], ['anthropic', 'Claude (API key)'],
  ['codex', 'ChatGPT (subscription)'], ['openai_api', 'ChatGPT (API key)'], ['openai', 'Model on this computer']]

export function BackendPick({ feature }: { feature: 'ask' | 'interview' | 'narrate' | 'dialogue' }) {
  const [v, setV] = useState(0)
  const st = useAsync<TalkStatus>(() => talkApi.status(), [v])
  const s = st.data
  if (!s) return null
  const key = `${feature}_backend` as const
  return (
    <select style={{ maxWidth: 130 }} value={s.settings[key]} title={`Now using: ${s.using[feature]} (recommended: ${s.recommended[feature] === 'openai' ? 'a model on this computer' : 'Claude'})`}
      onChange={e => e.target.value === '__setup' ? useAiSetup.getState().show() : talkApi.settings({ [key]: e.target.value }).then(() => setV(v + 1))}>
      {BACKENDS.map(([k, w]) => <option key={k} value={k} disabled={k !== 'auto' && !s.available[k]}>{w}{k !== 'auto' && !s.available[k] ? ' (not set up)' : ''}</option>)}
      {(feature === 'dialogue' || feature === 'narrate') && <option value="off">Off (plain wording)</option>}
      <option value="__setup">Connect an AI…</option>
    </select>
  )
}

function AskTool({ sel }: PanelProps) {
  const u = useLens().u
  const [q, setQ] = useState('')
  const t = useTalkJob()
  const mentions = [...(sel.item ? [{ kind: sel.item.kind, id: sel.item.id, label: sel.item.label }] : []),
    ...selPeople(sel).slice(0, 4).filter(i => !(sel.item?.kind === 'person' && Number(sel.item.id) === i)).map(i => ({ kind: 'person', id: i }))]
  const go = (text = q) => { if (text.trim()) { setQ(text); t.run(() => talkApi.ask(text.trim(), mentions, u)) } }
  const res = t.job?.result
  return (
    <div className="bk">
      <PanelOptions><BackendPick feature="ask" /></PanelOptions>
      <div className="ta-ask">
        <textarea value={q} placeholder="Ask anything about this world…" onChange={e => setQ(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); go() } }} />
        {t.busy ? <button onClick={t.cancel}>Stop</button> : <button onClick={() => go()} disabled={!q.trim()}>Ask</button>}
      </div>
      {!t.job && !t.error && (
        <div className="ta-examples">{EXAMPLES.map(x => <button key={x} onClick={() => go(x)}>{x}</button>)}</div>
      )}
      {mentions.length > 0 && !t.job && <div className="bx-note">The question is asked with what you have selected in mind.</div>}
      {t.error && <Problem error={t.error} />}
      {t.job && t.busy && <Steps job={t.job} />}
      {t.job?.state === 'error' && <Problem error={t.job.error ?? 'Something went wrong'} />}
      {t.job?.state === 'cancelled' && <div className="bx-note">Stopped.</div>}
      {res && <Answer res={res} />}
      {res?.tools_used && <div className="ta-foot">Looked up: {res.tools_used.map(x => x.tool.replace(/_/g, ' ') + (x.error ? ' (failed)' : '')).join(', ')}</div>}
    </div>
  )
}

export const tool: ToolDef = {
  id: 'ask',
  label: 'Ask the world',
  icon: 'search',
  hint: 'Ask a question in plain words; the answer comes only from facts the simulator looks up, with every sentence checked.',
  group: 'talk',
  order: 10,
  component: AskTool,
  size: { w: 5, h: 7 },
}
