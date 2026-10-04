import { ReactNode, useEffect, useMemo } from 'react'
import { Evidence } from '../components'
import { G, UBadge } from '../game'
import { useStore } from '../store'
import { GLOSSARY, PageHeader } from '../ui'

const SECTIONS: [string, string][] = [
  ['play', 'How to play'], ['idea', 'The big idea'], ['layers', 'Layers of the world'], ['person', 'What a person is made of'],
  ['relationships', 'How relationships form'], ['feelings', 'How feelings work'], ['mind', 'Inner lives'], ['places', 'Places with a culture'],
  ['faith', 'Faith & religious diversity'], ['time', 'How time works'],
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
  const { registry, status, setRoute, openDrawer } = useStore()
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
      <PageHeader id="guide" eyebrow="How it works" title="How to play, and how this world works"
        sub="A short tour: the controls, the places you can go, what is being simulated, how the pieces fit together, and how sure we are about each part." />
      <div className="guide">
        <nav className="guide-toc" aria-label="Guide sections">
          {SECTIONS.map(([id, t]) => <a key={id} href={`#/guide/${id}`} onClick={e => { e.preventDefault(); document.getElementById(id)?.scrollIntoView({ behavior: 'smooth' }) }}>{t}</a>)}
        </nav>
        <div>
          <Sec id="play" title="How to play" lede="A serious social simulation underneath; a simulation game in your hands. The whole game is one loop:">
            <div className="loop" style={{ marginBottom: 14 }}>
              {['Wonder “what if…?”', 'Change something', 'Let time run', 'Watch the world react', 'Notice something', 'Click it', 'Follow the chain', 'Compare the other world', 'Change something else'].map((s, k, a) => [
                <span key={s} className="step">{s}</span>, k < a.length - 1 ? <span key={s + 'a'} className="arrow">→</span> : null])}
            </div>
            <div className="grid g2">
              <div className="card">
                <h3>The top bar</h3>
                <dl className="dl">
                  <dt>{G.sun} The clock</dt><dd>Today's date in the simulation, the time of day (the sky turns to night) and where we are in the semester. A green glow means time is running.</dd>
                  <dt>⏸ ▶ ▶▶ ▶▶▶</dt><dd>Pause, or run at speed 1 (about a day every second and a half, slow enough to read the news), speed 2, or speed 3 (as fast as your computer allows). <b>+1d</b>, <b>+1w</b> and <b>Jump ▾</b> step by a day, a week, a month, a semester, a year or to a date.</dd>
                  <dt><UBadge u="base" /> <UBadge u="alt" /> Compare</dt><dd>Once you have made a change there are two worlds. This switch decides which one every page shows: the Original, the What-if, or both side by side (Compare).</dd>
                  <dt>{G.butterfly} The butterfly meter</dt><dd>How many lives differ between the two worlds right now. Click it for the full butterfly view.</dd>
                  <dt>{G.search} Search anything</dt><dd>Every field, person, place, event type, what-if idea, page and action. Press <span className="kbd">/</span> or <span className="kbd">Ctrl K</span>.</dd>
                </dl>
              </div>
              <div className="card">
                <h3>The places you can go</h3>
                <dl className="dl">
                  <dt>{G.globe} World</dt><dd>The living home page: a map of everyone moving through yesterday, the headlines, this week's counts, what's moving, lives to follow, your pinned board, and the two worlds.</dd>
                  <dt>{G.map} Map</dt><dd>Everyone where they are, or at home colored by anything; replay a day or the months; in Compare, color each person by how different their life is.</dd>
                  <dt>{G.people} People</dt><dd>Find, sort and follow individuals. Each person is a life: feelings and why, their people, school and work, faith, money and home, their story, their history, and their other life in the What-if.</dd>
                  <dt>{G.rings} Relationships</dt><dd>Couples, the friendship network, how people meet, and the couples that exist in only one world.</dd>
                  <dt>{G.places} Places · {G.events} Events</dt><dd>Complexes, wards and schools by the people in them; and every event with its chain of causes.</dd>
                  <dt>{G.butterfly} What-if</dt><dd>Change the world and follow the butterfly: every field that moved, events more or less common, lives that diverged, couples, places, and the rules behind it.</dd>
                  <dt>{G.explore} Explore</dt><dd>All {Object.values(reg.variables).filter(v => v.entity === 'person' && (v.flags ?? []).includes('chart')).length} fields in friendly drawers. Click one: right now, over time, by group, against another field, the people behind it, and what drives it. <b>Pin</b> it to your board.</dd>
                  <dt>{G.desk} Research desk</dt><dd>The deeper layers: vital-sign trends, flows, cross-tabs, cause & effect, Monte Carlo and sweeps, model check, data dictionary, rules and sources.</dd>
                </dl>
              </div>
            </div>
            <div className="card" style={{ marginTop: 12 }}>
              <h3>Handy keys</h3>
              <p className="small secondary" style={{ margin: 0 }}><span className="kbd">Space</span> play / pause · <span className="kbd">1</span> Original · <span className="kbd">2</span> What-if · <span className="kbd">3</span> Compare · <span className="kbd">.</span> +1 day · <span className="kbd">&gt;</span> +1 week · <span className="kbd">/</span> search · <span className="kbd">Esc</span> close. Your <b>filter</b> (“Showing: …”) follows you across pages until you clear it. Settings (the gear) holds the theme, news pop-ups and research details.</p>
              <div className="row" style={{ marginTop: 10 }}>
                <button className="btn primary" onClick={() => openDrawer({})}>{G.butterfly} Make your first change</button>
                <button className="btn" onClick={() => setRoute(['explore', 'loneliness'])}>{G.explore} Browse every field</button>
                <button className="btn" onClick={() => setRoute(['world'])}>{G.globe} Back to the world</button>
              </div>
            </div>
          </Sec>

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
                body="Real Provo/Orem streets and buildings: about 63,000 homes and 590 apartment complexes (about 200 with their real names from OpenStreetMap and BYU's contracted-housing list, plus the dorms and married housing), 151 LDS meetinghouses, 712 restaurants, parks, gyms, theaters and trailheads, plus the BYU and UVU campuses." />
              <Layer c="--s7" name="Groups" small="where people meet" go={() => setRoute(['places'])}
                body="Households and roommates, wards and FHE groups, class sections, workplaces, clubs, intramural teams, institute classes, gatherings in apartments, and dating apps. Being in the same group is how people get the chance to meet." />
              <Layer c="--s3" name="Relationships" small={`${n('edge')} measures per tie`} go={() => setRoute(['relationships'])}
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
              <p className="small secondary">People who share a place (apartment, class, ward, FHE group, job, club, intramural team, institute class, gym, a party) bump into each other. Each encounter builds familiarity, which fades if they stop seeing each other. Similarity, personality, mood and a bit of chemistry make each meeting go well or badly. Enough good hours together turns acquaintances into friends: research suggests about 50 hours for a casual friend and 200+ for a close friend.</p>
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

          <Sec id="mind" title="Inner lives" lede="Between who someone is and what they do sits a mind: what they care about, what they expect, what they believe about others, what they remember, how they cope and what they are trying to do. Open any person's Inner life tab.">
            <div className="grid g2">
              <div className="card">
                <h3>From state to behavior, step by step</h3>
                <ul className="small secondary" style={{ paddingLeft: 18, margin: '6px 0 0' }}>
                  <li><b>Cares:</b> eight concerns (friends, love, school or career, money, faith, rest, fun, fitness), weighted by personality, values and situation. They shift slowly.</li>
                  <li><b>Drives:</b> how much a concern matters × how unmet it feels. Drives compete: money worries and exams pull effort away from dating and fun.</li>
                  <li><b>Expectations:</b> learned from experience — a run of rejections lowers the expected chance of a yes, which makes asking less likely; cold gatherings teach people to expect less warmth.</li>
                  <li><b>Perception:</b> people act on what they believe, which can be wrong — the support they think they have, what their friends really believe, whether a crush likes them back.</li>
                  <li><b>Plans and routines:</b> weekly intentions (ask someone out, reconnect with a friend, study more…) that are carried out about half the time, and free-time habits that settle into a weekly shape.</li>
                </ul>
              </div>
              <div className="card">
                <h3>When life gets hard</h3>
                <ul className="small secondary" style={{ paddingLeft: 18, margin: '6px 0 0' }}>
                  <li>An event is <b>appraised</b>: it hits harder when it touches something the person cares about, and when they feel little support.</li>
                  <li>If strain stays high they <b>cope</b> — reaching out, tackling the problem, turning to faith, keeping busy, or pulling back — depending on temperament, what is available and what has worked for them before.</li>
                  <li>Coping changes behavior, and its relief depends on what actually happens: reaching out helps only if friends are there. People learn which ways of coping work for them.</li>
                  <li><b>Memory</b> keeps the important moments; memories fade unless re-lived, and rumination re-lives the painful ones.</li>
                </ul>
              </div>
            </div>
          </Sec>

          <Sec id="places" title="Places with a culture" lede="Apartments, complexes and wards develop cultures from the people in them — and those cultures shape the next people.">
            <div className="card">
              <p className="small secondary" style={{ margin: 0 }}>A complex where residents host game nights becomes known as social; friends drop by more, invitations there get accepted more, and outgoing movers choose it at the next lease turnover. A devout complex raises the attendance norm residents perceive; a warm ward brings newcomers in faster. Cultures have memory, so they outlast the people who built them. That loop — people shape places, places shape people — runs on its own. See any complex's culture under Places.</p>
            </div>
          </Sec>

          <Sec id="faith" title="Faith & religious diversity" lede="Most people here are Latter-day Saints, but not everyone: about 30% of UVU students and a few percent at BYU belong to another faith or none.">
            <div className="grid g2">
              <div className="card">
                <h3>Latter-day Saints</h3>
                <p className="small secondary" style={{ marginTop: 0 }}>Faith is many separate things: belief, certainty, identity, trust in leaders, orthodoxy, private devotion and church attendance (a habit). Friends and wards pull belief toward theirs, more so when someone is unsure. Spiritual experiences and challenges shift it; a faith crisis can end in renewal, a nuanced faith, or leaving. Activity (active, less active, inactive) follows attendance.</p>
              </div>
              <div className="card">
                <h3>Other faiths and none</h3>
                <p className="small secondary" style={{ marginTop: 0 }}>Catholic, Protestant and other believers attend real Provo and Orem congregations and meet people there; nonreligious students may join a secular student group. Anyone outside the LDS mainstream can feel like a <b>religious outsider</b>, more so with mostly-LDS friends and roommates or after being invited to meet the missionaries, less so with friends who share their outlook. LDS friends and partners invite some to take the missionary lessons; a few are baptized (about 2–3% of non-members a year).</p>
              </div>
            </div>
            <div className="row" style={{ marginTop: 10 }}>
              <button className="btn small" onClick={() => setRoute(['explore', 'belonging', 'affiliation'])}>Belonging by affiliation</button>
              <button className="btn small" onClick={() => setRoute(['flows', 'activity'])}>Who drifts from activity</button>
              <button className="btn small" onClick={() => openDrawer({ preset: 'interfaith_welcome' })}>What-if: interfaith welcome</button>
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
            <div className="card" style={{ marginTop: 12 }}>
              <h3>Using time</h3>
              <dl className="dl">
                <dt>⏸ ▶ ▶▶ ▶▶▶</dt><dd>Top bar. Pause, or run day after day at speed 1 (slow enough to read the news as it pops up), 2, or 3 (as fast as your computer allows). <span className="kbd">Space</span> toggles.</dd>
                <dt>+1d, +1w, Jump ▾</dt><dd>Move time in fixed steps: an hour (watch the map move), a day, a week, a month, a semester, a year, four years, or to a date you pick.</dd>
                <dt>The calendar ribbon</dt><dd>The strip under the top bar is this academic year: shaded blocks are semesters and terms, the blue line is today, hatched means already happened, and a dashed line marks where a what-if world split off. Click any future date to run to it.</dd>
                <dt>Replays on the map</dt><dd><b>▶ A day</b> replays the last full day: everyone glides from home to class and work, out for the evening, and home. <b>▶ Over months</b> replays the two-week snapshots, coloring homes by any tracked measure, so you can watch couples move in together or loneliness ease.</dd>
                <dt>Looking back</dt><dd>Nothing is rewound. Every field has an <b>Over time</b> chart in Explore (weekly averages for everyone and standard groups; two-weekly snapshots of every person for key fields), each person has a <b>History</b> tab, and Flows show who changed between two dates.</dd>
              </dl>
              <p className="small muted" style={{ marginBottom: 0 }}>The world starts on Aug 24, the first day of fall semester at BYU and UVU.</p>
              <div className="row" style={{ marginTop: 8 }}><button className="btn small primary" onClick={() => setRoute(['map', 'day'])}>Replay a day on the map</button><button className="btn small" onClick={() => setRoute(['flows'])}>Flows over time</button></div>
            </div>
          </Sec>

          <Sec id="whatif" title="What-if experiments" lede="When you change something, the simulator copies the whole world: the Original keeps going as-is, and the What-if copy gets the change.">
            <div className="grid g2">
              <div className="card">
                <h3>Two worlds, same dice</h3>
                <p className="small secondary" style={{ marginTop: 0 }}>Both copies use the same "dice" (random numbers), so at first they stay identical except for the change. Small differences then spread through friendships, dates and moves: the butterfly effect. Because every person exists in both worlds, the simulator can show not just how averages moved, but exactly whose lives changed, and why.</p>
                <p className="small secondary" style={{ marginBottom: 0 }}>Changes come three ways: <b>Ideas</b> (ready-made scenarios with a confidence label), <b>Levers</b> (rent, tuition, wages, dating-app appeal, marriage pressure, mission participation, coffee, housing rules, weather…), and <b>People & rules</b> (nudge a group of people, or make one of the model's rules stronger or weaker). You can keep adding changes to the What-if world as it runs.</p>
              </div>
              <div className="card">
                <h3>Following the butterfly</h3>
                <dl className="dl">
                  <dt>Overview</dt><dd>How far the worlds have drifted, the biggest changes, events, and lives.</dd>
                  <dt>All fields</dt><dd>Every field side by side, ranked by how much it shifted (a standardized size) or by how many people changed.</dd>
                  <dt>Lives</dt><dd>The people whose lives diverged most. Open one to see the first fork in their road and the chain of causes behind it.</dd>
                  <dt>Relationships · Places</dt><dd>Couples and friendships that exist in only one world; complexes, wards and neighborhoods that changed.</dd>
                  <dt>Why</dt><dd>Each feeling's change split exactly into the model's rules, with evidence labels.</dd>
                </dl>
              </div>
            </div>
            <p className="small secondary">One run is one possible future. <b>Research desk → Experiments</b> repeats an experiment with different dice (Monte Carlo) to show the range of outcomes, and sweeps a setting across a range of strengths.</p>
            <div className="row"><button className="btn primary" onClick={() => openDrawer({})}>{G.butterfly} Try one now</button></div>
          </Sec>

          <Sec id="evidence" title="How sure are we?" lede="Every rule and measure carries a label saying how well-grounded it is. Hypothetical rules are allowed (this is a playground) but they're always marked.">
            <div className="card">
              <table className="data"><tbody>{Object.entries(reg.evidence_levels).map(([k, d]) => (
                <tr key={k}><td style={{ width: 130 }}><Evidence level={k} /></td><td className="small secondary">{d}</td><td className="small muted tabular" style={{ width: 80 }}>{mechCount[k] ?? 0} rules</td></tr>))}</tbody></table>
              <p className="small muted">The people are synthetic, built from aggregate patterns in four local surveys (never individual responses) plus published research. Results describe this model, not predictions about real people.</p>
              <p className="small secondary" style={{ marginBottom: 0 }}>The model is checked against real data: the Census (who is married at each age in Provo and Orem), BYU and UVU enrollment, and dozens of survey patterns (dates per month, habits, faith practices). Key settings were tuned automatically to fit those checks. <a href="#/modelcheck" onClick={e => { e.preventDefault(); setRoute(['modelcheck']) }}>See the Model check →</a></p>
            </div>
          </Sec>

          <Sec id="where" title="Where to go for what">
            <div className="card">
              <dl className="dl">
                {([
                  ['"What\'s going on?"', 'The World page shows the news, the week, what\'s moving and the two worlds; Vital signs (research desk) charts the big trends.', 'world'],
                  ['"Where?"', 'The Map colors people, homes, complexes and wards by any measure, and replays a day or the months so far.', 'map'],
                  ['"Who, specifically?"', 'People lets you search, sort and follow individuals; each person page is a whole life, with the why behind each feeling.', 'people'],
                  ['"What does the model track, and how is it spread out?"', 'Explore: every field in friendly drawers, with its distribution, history, groups, related fields, people and drivers.', 'explore'],
                  ['"Who is with whom?"', 'Relationships: couples, the friendship network and how people meet.', 'relationships'],
                  ['"How does X differ by Y?"', 'Cross-tabs (research desk): survey-style tables; click any cell to see those people.', 'crosstab'],
                  ['"How do people change over time?"', 'Flows over time: who moved from one state to another, and their stories.', 'flows'],
                  ['"What happened and what caused it?"', 'Events: counts, the most consequential events, and causal chains.', 'events'],
                  ['"What would happen if…?"', 'What-if: change something, let both worlds run, and follow the butterfly effect.', 'whatif'],
                  ['"What affects what?"', 'Cause & effect: the web of rules connecting every measure.', 'causal'],
                  ['"Can I trust these numbers?"', 'Model check: how the simulation compares with the Census and the surveys, and whether it stays steady for years.', 'modelcheck'],
                ] as [string, string, string][]).map(([q, a, r]) => [<dt key={q}>{q}</dt>, <dd key={q + 'd'}>{a} <a href={`#/${r}`} onClick={e => { e.preventDefault(); setRoute([r]) }}>Open →</a></dd>])}
              </dl>
              <p className="small muted" style={{ marginBottom: 0 }}><b>Your filter follows you.</b> When you narrow to a group of people (“Showing: single BYU women…”), every page shows just them until you clear it. <b>Research details</b> (in settings) shows formulas, evidence labels and parameters inside pages.</p>
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
