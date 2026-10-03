import { ReactNode, useEffect, useMemo } from 'react'
import { Evidence } from '../components'
import { useStore } from '../store'
import { GLOSSARY, PageHeader } from '../ui'

const SECTIONS: [string, string][] = [
  ['idea', 'The big idea'], ['layers', 'Layers of the world'], ['person', 'What a person is made of'],
  ['relationships', 'How relationships form'], ['feelings', 'How feelings work'], ['time', 'How time works'],
  ['whatif', 'What-if experiments'], ['evidence', 'How sure are we?'], ['where', 'Where to go for what'], ['glossary', 'Glossary'],
]

// person-variable "kinds" in the registry, in the order of how fast they change
const KINDS: { kind: string; title: string; speed: string; body: string }[] = [
  { kind: 'attribute', title: 'Background', speed: 'fixed', body: 'Who someone is and where they come from: age, sex, home region, family structure, parents\' income, height.' },
  { kind: 'trait', title: 'Personality', speed: 'very slow', body: 'Big Five plus traits that matter here: rejection sensitivity, attachment style, social anxiety, conformity, sensation seeking.' },
  { kind: 'belief', title: 'Beliefs & values', speed: 'months', body: 'Faith in many separate dimensions (belief, certainty, identity, trust, orthodoxy), politics, family expectations, perceived norms.' },
  { kind: 'preference', title: 'Preferences', speed: 'slow', body: 'What people want and are comfortable with in dating, partners and dates: from height preferences to whether a first-date kiss is okay.' },
  { kind: 'structural', title: 'Circumstances', speed: 'events', body: 'Where life has put them: school, major, job, housing, ward, relationship status, mission status, children.' },
  { kind: 'habit', title: 'Habits', speed: 'weeks', body: 'What they regularly do: church attendance, scripture, temple, dating, apps, exercise, sleep, coffee, social media.' },
  { kind: 'state', title: 'Feelings & states', speed: 'daily', body: 'How they feel right now: happiness, loneliness, stress, anxiety, belonging, self-esteem, romantic longing, money stress.' },
  { kind: 'history', title: 'Life history', speed: 'accumulates', body: 'Running tallies of their life so far: relationships, breakups, kisses, dates, bishop meetings, age at marriage.' },
]

export default function Guide({ section }: { section?: string }) {
  const { registry, status, setRoute } = useStore()
  const reg = registry!
  useEffect(() => { if (section) document.getElementById(section)?.scrollIntoView() }, [section])
  const vars = useMemo(() => Object.values(reg.variables), [reg])
  const person = vars.filter(v => v.entity === 'person')
  const mechCount: Record<string, number> = {}
  for (const m of Object.values(reg.mechanisms) as any[]) mechCount[m.evidence] = (mechCount[m.evidence] ?? 0) + 1
  const n = (e: string) => vars.filter(v => v.entity === e).length
  const chip = (id: string) => reg.variables[id] ? <button key={id} className="chip" onClick={() => setRoute(['variables', id])}>{reg.variables[id].label}</button> : null
  return (
    <div className="page">
      <PageHeader id="guide" eyebrow="Field guide" title="How this world works"
        sub="A five-minute tour of what is being simulated, how the pieces fit together, and where to go in the app for each kind of question." />
      <div className="guide">
        <nav className="guide-toc" aria-label="Guide sections">
          {SECTIONS.map(([id, t]) => <a key={id} href={`#/guide/${id}`} onClick={e => { e.preventDefault(); document.getElementById(id)?.scrollIntoView({ behavior: 'smooth' }) }}>{t}</a>)}
        </nav>
        <div>
          <Sec id="idea" title="The big idea">
            <p className="lede">This is a miniature Provo and Orem. About {status.present?.toLocaleString()} synthetic people live in real apartments and houses, go to class, work and church, meet each other, date, marry, doubt, believe, struggle with money and feel lonely or connected. Nothing is scripted: the patterns you see come from individual people following the model's rules.</p>
            <p className="lede">You can change something about their world, run time forward, and trace any result back to the people and the reasons behind it:</p>
            <div className="loop">
              {['Change something', 'Run time', 'See what happened', 'Ask why', 'See to whom', 'Check the evidence'].map((s, k, a) => [
                <span key={s} className="step">{s}</span>, k < a.length - 1 ? <span key={s + 'a'} className="arrow">→</span> : null])}
            </div>
          </Sec>

          <Sec id="layers" title="Layers of the world" lede="Everything in the simulation lives in one of these layers. Higher layers set the conditions; lower layers are where behavior happens; events and rules connect them.">
            <div className="layers">
              <Layer c="--s4" name="World" small={`${n('world')} measures`} go={() => setRoute(['variables'])}
                body="Economy, unemployment, rents and housing supply, tuition, the academic calendar, weather, and cultural norms (mission norm, men-ask norm, church attendance norm, whether coffee is allowed). What-if experiments mostly change things here." />
              <Layer c="--s2" name="Places" small="real geography" go={() => setRoute(['map'])}
                body="Real Provo/Orem streets and buildings: about 63,000 homes, 533 apartment complexes (dorms, contracted student housing, married housing), 151 LDS meetinghouses, 712 restaurants, parks, gyms, theaters and trailheads, plus the BYU and UVU campuses." />
              <Layer c="--s7" name="Groups" small="where people meet" go={() => setRoute(['places'])}
                body="Households and roommates, wards and FHE groups, class sections, workplaces, gatherings in apartments, and dating apps. Being in the same group is how people get the chance to meet." />
              <Layer c="--s3" name="Relationships" small={`${n('edge')} measures per tie`} go={() => setRoute(['network'])}
                body="Every pair who has met is a tie with its own history: familiarity, liking, closeness, trust, conflict, attraction in each direction, hours together, how and where they met, and who introduced them." />
              <Layer c="--s1" name="People" small={`${person.length} measures each`} go={() => setRoute(['people'])}
                body="Each person has a background, personality, beliefs, habits, circumstances, feelings and a life history (see below). People are not stereotypes: an active member can doubt, a drinker can believe, an extravert can be lonely." />
              <Layer c="--s5" name="Events" small={`${Object.keys(reg.events).length} kinds`} go={() => setRoute(['events'])}
                body="Things that happen to people (first dates, breakups, faith crises, job losses, graduations). Each event remembers what caused it, so chains like FHE group → first date → DTR → engagement can be traced." />
              <Layer c="--s8" name="Rules" small={`${Object.keys(reg.mechanisms).length} rules`} go={() => setRoute(['mechanisms'])}
                body="The model's mechanisms: how one thing affects another (close friends reduce loneliness; a breakup raises distress that fades over weeks). Each has a strength you can change and an evidence label." />
            </div>
          </Sec>

          <Sec id="person" title="What a person is made of" lede={`Each person carries ${person.length} measures, grouped by kind and by how fast they change. Click any example to open it in the data dictionary.`}>
            <div className="kinds">
              {KINDS.map(k => {
                const list = person.filter(v => v.kind === k.kind)
                return (
                  <div key={k.kind} className="card kind-card">
                    <div className="k-speed">changes: {k.speed} · {list.length} measures</div>
                    <h3 style={{ margin: '2px 0 4px' }}>{k.title}</h3>
                    <div className="small secondary">{k.body}</div>
                    <div className="chips">{list.slice(0, 7).map(v => chip(v.id))}</div>
                  </div>
                )
              })}
            </div>
          </Sec>

          <Sec id="relationships" title="How relationships form" lede="Compatibility matters only once people actually meet. Opportunity comes first.">
            <div className="card" style={{ marginBottom: 10 }}>
              <h3>Friendship</h3>
              <p className="small secondary">People who share a place (apartment, class, ward, FHE group, job, gym, a party) bump into each other. Each encounter builds familiarity, which fades if they stop seeing each other. Similarity, personality, mood and a bit of chemistry make each meeting go well or badly. Enough good hours together turns acquaintances into friends: research suggests about 50 hours for a casual friend and 200+ for a close friend.</p>
              <div className="ladder"><span className="rung">same place</span>→<span className="rung">acquaintance</span>→<span className="rung">casual friend</span>→<span className="rung">friend</span>→<span className="rung">close friend</span></div>
            </div>
            <div className="card">
              <h3>Romance</h3>
              <p className="small secondary">Attraction is directed (A can like B more than B likes A) and partly idiosyncratic. Someone has to ask (the men-ask norm is adjustable); dates go well or badly and update attraction both ways. Couples move through stages, and each step has its own odds, shaped by commitment, faith compatibility, age, money and timing. Breakups follow when satisfaction and commitment fall.</p>
              <div className="ladder"><span className="rung">crush</span>→<span className="rung">ask out</span>→<span className="rung">first date</span>→<span className="rung">talking</span>→<span className="rung">DTR (exclusive)</span>→<span className="rung">engaged</span>→<span className="rung">married</span></div>
            </div>
          </Sec>

          <Sec id="feelings" title="How feelings work" lede="Every feeling is a sum you can open up: open any person and click a feeling to see its parts.">
            <div className="grid g2">
              <div className="card">
                <h3>Feeling = baseline + forces + ripples + noise</h3>
                <ul className="small secondary" style={{ paddingLeft: 18, margin: '6px 0 0' }}>
                  <li><b>Baseline:</b> each person's personal set-point (a neurotic person's stress sits higher).</li>
                  <li><b>Forces:</b> the rules acting right now: close friends lower loneliness, money trouble raises stress, a happy relationship lifts mood.</li>
                  <li><b>Ripples:</b> events leave effects that fade over days or weeks (a breakup hurts most at first, then less), and they hit some people harder than others.</li>
                  <li><b>Noise:</b> ordinary day-to-day ups and downs.</li>
                </ul>
              </div>
              <div className="card"><h3>An event's ripple fades over time</h3><p className="hint">Example: a breakup's effect on mood, with a 3-week half-life.</p><Decay /></div>
            </div>
          </Sec>

          <Sec id="time" title="How time works" lede="Each system updates on its natural rhythm. Not everything changes every hour.">
            <div className="ribbon">
              <div><b>Hours</b>Each day has a morning (8am), afternoon (1pm) and evening (6pm) block: class, work, church, gym, dates, parties. People move on the map.</div>
              <div><b>Days</b>Feelings update every night; friends reach out; dates happen; sleep and fatigue shift.</div>
              <div><b>Weeks</b>On Sunday nights friendships level up or fade, faith and church habits update, couples progress or break up.</div>
              <div><b>Months</b>Money and jobs, rent and moves, mission calls, babies, life satisfaction.</div>
              <div><b>Semesters</b>Grades, academic standing, graduation, majors, lease turnover in April and August.</div>
              <div><b>Years</b>New freshmen arrive Aug 20; summer sends many singles home; missionaries leave and return.</div>
            </div>
            <p className="small muted" style={{ marginTop: 8 }}>The world starts on Aug 24, the first day of fall semester. Use the Run buttons at the top to move time forward.</p>
          </Sec>

          <Sec id="whatif" title="What-if experiments" lede="When you change something, the simulator copies the whole world: the original keeps going as-is, and the copy gets the change.">
            <div className="card">
              <p className="small secondary" style={{ marginTop: 0 }}>Both copies use the same "dice" (random numbers), so at first they stay identical except for the change. Small differences then spread through friendships, dates and moves: the butterfly effect. Comparing the two worlds tells you what the change caused, and the attribution panel splits each difference into the rules that produced it.</p>
              <p className="small secondary" style={{ marginBottom: 0 }}>One run is one possible future. In Advanced mode, <b>Many runs</b> repeats an experiment with different dice to show the range of outcomes, and <b>Sweeps</b> tries a range of strengths (e.g. rent +0%, +10%, +20%, +30%).</p>
              <div className="row" style={{ marginTop: 10 }}><button className="btn primary" onClick={() => setRoute(['lab'])}>Try one now</button></div>
            </div>
          </Sec>

          <Sec id="evidence" title="How sure are we?" lede="Every rule and measure carries a label saying how well-grounded it is. Hypothetical rules are allowed (this is a playground) but they're always marked.">
            <div className="card">
              <table className="data"><tbody>{Object.entries(reg.evidence_levels).map(([k, d]) => (
                <tr key={k}><td style={{ width: 130 }}><Evidence level={k} /></td><td className="small secondary">{d}</td><td className="small muted tabular" style={{ width: 80 }}>{mechCount[k] ?? 0} rules</td></tr>))}</tbody></table>
              <p className="small muted" style={{ marginBottom: 0 }}>The people are synthetic, built from aggregate patterns in four local surveys (never individual responses) plus published research. Results describe this model, not predictions about real people.</p>
            </div>
          </Sec>

          <Sec id="where" title="Where to go for what">
            <div className="card">
              <dl className="dl">
                {([
                  ['"What\'s going on?"', 'Home and Vital signs show the big picture and trends.', 'dashboard'],
                  ['"Where?"', 'The Map colors people, homes, complexes and wards by any measure.', 'map'],
                  ['"Who, specifically?"', 'People lets you search, sort and follow individuals; each person page explains their feelings.', 'people'],
                  ['"How is this measure spread out?"', 'Explore a measure: distribution, split by groups, relate two measures, and "why" for your group.', 'explore'],
                  ['"How does X differ by Y?"', 'Compare groups: survey-style cross-tabs; click any cell to see those people.', 'crosstab'],
                  ['"How do people change over time?"', 'Flows over time: who moved from one state to another, and their stories.', 'flows'],
                  ['"What happened and what caused it?"', 'Life events: counts, the most consequential events, and causal chains.', 'events'],
                  ['"What would happen if…?"', 'What-if lab: change something and compare two worlds.', 'lab'],
                  ['"What affects what?"', 'Cause & effect: the web of rules connecting every measure.', 'causal'],
                ] as [string, string, string][]).map(([q, a, r]) => [<dt key={q}>{q}</dt>, <dd key={q + 'd'}>{a} <a href={`#/${r}`} onClick={e => { e.preventDefault(); setRoute([r]) }}>Open →</a></dd>])}
              </dl>
              <p className="small muted" style={{ marginBottom: 0 }}><b>Your group follows you.</b> When you pick a group of people (a "cohort"), every page shows just them until you clear it. <b>Simple / Advanced</b> (bottom left) shows or hides the expert tools.</p>
            </div>
          </Sec>

          <Sec id="glossary" title="Glossary">
            <div className="card"><dl className="dl">{GLOSSARY.map(([t, d]) => [<dt key={t}>{t}</dt>, <dd key={t + 'd'}>{d}</dd>])}</dl></div>
          </Sec>
        </div>
      </div>
    </div>
  )
}

function Sec({ id, title, lede, children }: { id: string; title: string; lede?: string; children: ReactNode }) {
  return <section id={id}><h2>{title}</h2>{lede && <p className="lede">{lede}</p>}{children}</section>
}

function Layer({ c, name, small, body, go }: { c: string; name: string; small: string; body: string; go: () => void }) {
  return (
    <div className="layer" style={{ ['--lc' as any]: `var(${c})` }}>
      <div className="l-name">{name}<small>{small}</small></div>
      <div className="l-body">{body}</div>
      <button className="btn small" onClick={go}>Explore</button>
    </div>
  )
}

/** Tiny illustrative decay curve (exponential with a 21-day half-life). */
function Decay() {
  const W = 320, H = 120, P = 26
  const pts = Array.from({ length: 61 }, (_, d) => [d, Math.pow(0.5, d / 21)])
  const x = (d: number) => P + (d / 60) * (W - P - 8), y = (v: number) => 8 + (1 - v) * (H - P - 8)
  return (
    <svg viewBox={`0 0 ${W} ${H}`} style={{ width: '100%', maxWidth: 420 }} role="img" aria-label="Exponential decay of an event's effect over 60 days">
      <line x1={P} y1={y(0)} x2={W - 8} y2={y(0)} stroke="var(--axis)" />
      <line x1={P} y1={8} x2={P} y2={y(0)} stroke="var(--axis)" />
      <path d={pts.map(([d, v], k) => `${k ? 'L' : 'M'}${x(d)},${y(v)}`).join('')} fill="none" stroke="var(--accent)" strokeWidth={2} />
      <circle cx={x(21)} cy={y(0.5)} r={4} fill="var(--accent)" />
      <text x={x(21) + 6} y={y(0.5) - 6} fontSize="10" fill="var(--text-secondary)">half gone after 3 weeks</text>
      {[0, 20, 40, 60].map(d => <text key={d} x={x(d)} y={H - 8} fontSize="10" fill="var(--text-muted)" textAnchor="middle">{d}d</text>)}
      <text x={4} y={y(1) + 4} fontSize="10" fill="var(--text-muted)">full</text>
    </svg>
  )
}
