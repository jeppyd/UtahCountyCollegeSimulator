# Provo–Orem Social Simulator: Project Guide

Everything someone needs to know to use, understand, maintain and extend this project, plus where it could
go next. Companion documents: `ARCHITECTURE.md` (internals), `MECHANISMS.md` and `VARIABLE_CATALOG.md`
(generated catalogs of every rule and measure), `DATA_SOURCES.md`, `MODEL_ASSUMPTIONS.md`, `VALIDATION.md`,
`ROADMAP.md`, `DEVELOPMENT_LOG.md`.

---

## 1. What this is

A **living model of college social life in Provo and Orem, Utah**. Several thousand to sixty thousand
synthetic people (BYU and UVU students, their spouses, young single adults, faculty, staff and neighbors)
live in the real housing stock, go to class, work, church, clubs and the gym, meet each other in those
places, make friends, date, marry, doubt, believe, struggle with money, feel lonely or connected, serve
missions, graduate and move away. Every meaningful change is recorded as an event with the rule that
caused it and the event that led to it, so any outcome can be traced back to its causes.

It is built as **the engine of a professional social simulation with the interface of a simulation game**.
The normal experience is a loop: *wonder "what if…?" → change something → let time run → watch the world
react → notice something → click it → follow the chain → compare the other world → change something
else.* The research tools are all still there, one layer down.

| Use | Where in the app | Example |
|---|---|---|
| **What-if experiments** | What if…? (anywhere), What-if | "If rent rose 20%, what happens to dating and loneliness over a semester, and to whom?" |
| **Exploring the data** | Explore (every field), Places, Relationships, Events | "How is loneliness spread out, how has it changed, and who is loneliest?" |
| **Following individual lives** | People, a person's page, Follow, Pin | "Why is this person lonely? What would their life look like in the other world?" |
| **Research** | Research desk | Cross-tabs, flows, cause & effect, Monte Carlo, sweeps, validation |

Design principles that run through everything:

- **Evidence-labelled.** Each of the 340 measures and 171 rules carries an evidence level (*observed*,
  *empirical*, *literature*, *calibrated*, *extrapolated*, *structural*, *hypothetical*, *speculative*). Hypothetical rules are allowed
  (this is an exploratory instrument) but are never hidden.
- **Explainable.** Feelings are sums of named terms; events carry causes; differences between worlds are
  attributed to the rules that produced them.
- **Privacy-preserving.** The surveys that ground the population are used only as aggregate statistics with
  small cells suppressed. Raw responses stay outside the repository; nobody in the model is a real person.
- **Real places.** Homes, complexes, meetinghouses, congregations, restaurants, parks, campuses and
  neighborhoods come from public map data.

---

## 2. Getting started

**Windows, no setup.** Download `ProvoOremSimulator-Setup.exe` from the repository's latest release,
install, and launch from the Start menu. Every push to the branch rebuilds and self-tests the installer in
GitHub Actions (`.github/workflows/windows-app.yml`); releases are tagged `app-v0.1.<run>`.

**From source** (Windows, macOS, Linux; Python ≥ 3.10 and Node 18+):

```bash
git clone https://github.com/jeppyd/UtahCountyCollegeSimulator.git
cd UtahCountyCollegeSimulator && pip install -e .
cd web && npm install && npm run build && cd ..
python -m ucsim.api.server            # open http://127.0.0.1:8000
```

The title screen builds a world: pick a **size** (share of the real community: Quick ≈ 3k people, Standard
≈ 9k, Detailed ≈ 18k, Full ≈ 60k), a **world number** (the random seed: the same number always gives the
same people and history) and warm-up days. Settings (the gear) rebuilds later.

**Read-only snapshot.** Dropped on 2026-10-21 (the owner's decision): the app always runs with its simulator. Old `STATIC` branches in the web code are inert and will be removed.

---

## 3. Using the app

### The shell
- **The clock** (top left): date, time of day (the sky turns to night) and place in the semester; it glows
  green while time runs.
- **Speeds**: **⏸ ▶ ▶▶ ▶▶▶** (pause; about a day per 1.4 s; about two days a second; as fast as possible).
  **+1d**, **+1w** and **Jump ▾** (an hour, a month, a semester, a year, four years, a date).
- **The world lens**: once a What-if world exists, **Original / What-if / Compare** decides what every page
  shows. Compare puts the worlds side by side (Original blue, What-if orange) everywhere: charts overlay both,
  tables gain a second column, people pages show both lives.
- **The butterfly meter**: the share of people whose lives differ between the worlds; click for the What-if page.
- **Search anything** (`/` or `Ctrl K`): every field, person, place, event type, what-if idea, page and action.
- **What if…?** (or Change more): the drawer for changing the world, from anywhere.
- **Calendar ribbon** under the top bar: semesters and breaks, today, the past (hatched), the split (dashed).
  Click a future date to run there.
- **News pop-ups**: the biggest moments appear as time runs (followed people first); after any jump of a
  week or more a **recap** card sums up what happened, including how far the worlds drifted. Toggle in settings.
- **The filter** ("Showing: …") on Explore, People, Map and Relationships: a group of people that follows you
  across pages until cleared. In Compare, the filter picks people in the Original and follows the same people
  into the What-if.
- **Keys**: Space play/pause, 1/2/3 lens, `.` +1 day, `>` +1 week, `/` search, Esc close.
- **Settings** (gear): theme, news pop-ups, **research details** (formulas, evidence labels and parameters
  inside pages), build a new world.

### The world (places you can go)
| Area | What it answers |
|---|---|
| **World** | The landing page: a living map of everyone moving through yesterday (8am → 1pm → 6pm → night, colored by activity), headlines (a few of each kind), what people did in each part of the day, this week's counts (pairs counted once), what's moving (biggest four-week changes), the two worlds (or one-click what-ifs), your pinned board, lives worth following, curiosities. |
| **Map** | People now or at home colored by any field; complexes and wards; neighborhoods, venues and congregations; ▶ replay a day or the months. In Compare, each person is colored by how much their own value differs between the worlds. |
| **People / a person** | Search, sort, follow, pin. A person is a life: *Now* (meters for how they're doing, what they want, standing among everyone, where they belong), *Their people* (ego network, how they met), *Feelings* (each split into its causes), *School & work*, *Faith*, *Money & home*, *Story*, *History* (two-weekly life strips and trajectories, both worlds), *Other life* (both headlines, the first fork in their road with its chain of causes, what differs now, friends gained and lost, both lives since the split), *Everything*. |
| **Relationships** | Couples by stage (newest first, how they met), the friendship network, how people meet and what holds friendships together; in Compare, couples and friendships that exist in only one world. |
| **Places / Events** | Places ranked by any field, with profiles; in Compare, where the What-if changed things most. Every event type with counts in both worlds and a readable story log with "why?" chains. |
| **What-if** | Without a What-if world: the change builder. With one: the butterfly view — *Overview* (drift over time, lives that changed most, biggest changes, events, couples), *All fields* (every field side by side, ranked by a standardized shift or by how many people changed, with a line of the difference since the split), *Events*, *Lives*, *Relationships*, *Places*, *Why* (each feeling's change split into rules, and the rules doing the most work). |
| **Explore** | The field pane: 217 fields in 13 drawers (Feelings, Friends & social life, Dating & romance, What they look for, Faith, Values & intimacy, School, Work & money, Home & neighborhood, Habits & interests, Personality, Background & body, Right now), searchable, with live values or Original → What-if changes. For the chosen field: key numbers, *Right now* (distribution), *Over time* (weekly for any field and group; your filter's own trajectory for the 41 fields kept per person), the butterfly person by person, *Compare groups*, *Relate to another field*, *The people behind it*, *What drives it* (rules in and out, with evidence, and events that shift it), and "why is your group different?". Pin any field to your board. |
| **Research desk** | Vital signs, flows over time, cross-tabs, cause & effect, experiments (Monte Carlo and sweeps), model check, data dictionary, rules, evidence & sources. |
| **How it works** | How to play, then the model in plain language: layers, what a person is made of, relationships, feelings, faith, time, what-ifs, how sure we are, where to go for what, glossary. |

### Changing the world
The drawer has three tabs. **Ideas**: 20 ready-made scenarios grouped by theme, each with a confidence label.
**Levers**: sliders for world settings (rent, tuition at each school, wages, unemployment, housing supply,
incoming students, transit, dating-app appeal, the expectation that men ask, pressure to marry young, social
media, church attendance norm, mission participation, interfaith welcome, coffee, the contracted-housing rules,
temperature). **People & rules**: nudge a field for a group of people once (e.g. raise belief for lonely
freshmen), or make one of the model's rules stronger or weaker. Pick how long to run, then **Split the world**.
With a What-if running you can **Add to What-if** (more changes from today) or **Start a new What-if**.

## 4. The model

### 4.0 Inner lives (iteration 5)
Between who someone is and what they do sits a mind (`docs/MIND.md`): eight concerns weighted by personality,
values and situation; drives (importance × how unmet each feels) that compete for effort; expectations learned
from experience (a yes when asking someone out, the warmth of people); academic confidence from grades;
perception that can be wrong (the support they believe they have, what friends really believe, whether a crush
likes them back); episodic memory with forgetting and rumination; appraisal of events by relevance and coping
potential; coping episodes with learned strategies; weekly intentions with a ledger of what was kept, dropped
and why; weekly routines. Relationships carry history (confiding, support, hurt and repair, shared experiences),
friends introduce friends, and apartments, complexes and wards develop cultures that shape who lives there next.
Open any person's **Inner life** tab to read it.

### 4.1 Layers
World (economy, rents, tuition, calendar, weather, cultural norms) → Places (real homes, complexes,
meetinghouses, congregations, venues, campuses, neighborhoods) → Groups (households, wards and FHE groups,
class sections, workplaces, clubs, intramural teams, institute classes, congregations, gatherings, dating
apps) → Relationships (one record per pair who have met) → People (243 measures each) → Events (66 kinds)
→ Rules (133 mechanisms connecting them).

### 4.2 People
Built in `ucsim/population`: a skeleton of demographics drawn from survey cross-tabulations, then traits,
beliefs, habits and preferences from Gaussian copulas fitted to the survey aggregates, then structure
(homes, roommates, wards, FHE groups, classes, jobs, majors, clubs) and a seeded friendship network.
Physical traits (height, weight, BMI, build, hair and eye color) follow published distributions;
attractiveness relates to fitness and build. Class years and enrollment are re-banded to the published
BYU/UVU shapes because the surveys skew young.

### 4.3 Daily life and meeting people
Each day has three activity blocks (8am, 1pm, 6pm) plus night. Obligations come first (class, work shifts,
Sunday meetings, congregations, FHE on Monday, ward activities, clubs, teams, institute, dates,
gatherings), then free time is chosen by a random-utility model shaped by personality, habits, mood,
loneliness (which makes some people seek company and others withdraw), weather and day of week. People who
share a place have chances to interact; who they talk to depends on familiarity (ACT-R memory activation),
liking, similarity and attraction.

### 4.4 Friendship
Interactions build familiarity, liking, closeness and hours together. Stages follow Hall (2019): roughly 50
hours to a casual friend, 90 to a friend, 200 to a close friend, with hysteresis so ties don't flicker.
Gatherings in apartments introduce friends of friends (triadic closure, with the introducer recorded).
Ties fade without contact and are forgotten when memory decays.

### 4.5 Romance
Directed, partly idiosyncratic attraction (looks, age and height preferences, religiosity fit, shared
interests, personality, chemistry). Someone has to ask (the men-ask norm is adjustable); dates go well or
badly and update attraction both ways; first kisses, "talking", DTR, engagement and marriage each have
their own odds shaped by commitment (Rusbult's investment model), faith compatibility, age, money,
timing and the marriage norm. Breakups, ghosting, NCMOs, apps, infidelity, premarital sex and bishop
confessions are modeled with their emotional effects.

### 4.6 Faith and religious diversity
For Latter-day Saints, faith is many dimensions: belief, certainty, identity, institutional trust,
orthodoxy, private devotion, and attendance as a habit. Friends and wards pull belief toward theirs (more
when certainty is low); spiritual experiences and challenges move it; guilt from broken standards leads to
behavior change or belief change (dissonance); crises resolve into renewal, nuance or leaving. About 30% of
UVU students and a few percent of BYU students are not LDS: Catholic, Protestant, other Christian, Muslim,
other faiths or none. Religious non-members attend real Provo/Orem congregations; anyone outside the LDS
mainstream can feel like a religious outsider (stronger with mostly-LDS friends and roommates, at BYU, or
after being pitched; weaker with like-minded friends and a faith or secular community). LDS friends and
partners invite some to meet the missionaries; about 2–3% of non-members a year are baptized.

### 4.7 Feelings
Loneliness, mood, stress, belonging, anxiety, self-esteem, guilt, purpose, romantic longing, financial
stress, academic pressure and fatigue are each a weighted sum of named terms (e.g. loneliness = setpoint +
contact deficit − close friends − partner − ward belonging − roommates + romantic longing + religious
outsider) plus decaying effects of recent events. Every term is stored per person, which is what the
"why" panels show. Depressive episodes start and end with thresholds on sustained mood.

### 4.8 School, work, money, housing, life course
Class sections by area, attendance, study time and GPA; majors from the real catalogs; graduation by
credits; dropout. Jobs, wages, hours that respond to financial strain, scholarships, parental help, savings.
Rents, leases turning over in April and August, moves with friends, BYU's first-year contracted-housing
rule, married housing. Missions (calls, departures, returns, early returns), arrivals of each fall's class
(BYU fills to its enrollment cap), new graduate students and transfers (mostly married, arriving with a
spouse), pregnancies and births, family crises, illness, leaving the area. Married students and parents
take lighter course loads; programs need 120–145 credits.

### 4.9 Interventions and paired worlds
A what-if copies the entire world. Both copies share the same random numbers, so they stay identical
except for the change, and every later difference spreads from it through friendships, dates and moves.
Interventions can set or scale a world variable, change a rule's parameter, change some people's
measures, or open a new venue. Results are attributed to rules by comparing per-term contributions.
Monte Carlo repeats an experiment across seeds; sweeps try a range of strengths.

### 4.10 History and replay
Every two weeks the history system snapshots key categorical and numeric measures plus where people live.
This powers Flows over time, transition groups ("went from single to married since September"), cohort
trajectories, and the map's "Over months" replay. The activity system keeps the last full day's positions
for the "A day" replay.

---

## 5. Data, privacy and evidence

| Source | Used for |
|---|---|
| Four Provo student surveys (ProvoStats, College Life, Culture & Lifestyle, Dating) | Aggregate distributions, copulas and targets only; cells under 10 suppressed; raw files gitignored (`data/raw/`) |
| U.S. Census ACS 2020–24 (Provo + Orem, table B12002) | Married share by age and sex: the main external benchmark |
| BYU and UVU fall 2025 enrollment; published class mix | Population size and structure |
| BYU Off-Campus Housing 2026–27 contracted list | Named contracted complexes, matched to address points |
| Utah UGRC (parcels, buildings, address points, places of worship, parks, roads, campuses, trailheads) | Housing stock, meetinghouses, congregations, venues, map layers |
| OpenStreetMap (Overpass, Nominatim) | Complex names and outlines, congregations, venues |
| Provo City and Orem City GIS | 57 official neighborhood names and boundaries |
| BYU 2025–26 majors list; UVU academic catalog | Majors and colleges |
| Published research | Mechanism forms and starting parameters (see `refs` on each rule) |

---

## 6. Trust: validation and calibration

`scripts/validate.py` simulates a year and compares the world with external data (validation report:
`docs/VALIDATION.md`; in-app: Model check). Row types: **Census benchmarks** (strongest), **behavior**
rows that emerge from simulated decisions, **starting values** synthesized from the surveys, and
**diagnostic** rows known to be biased (the dating surveys over-sample singles; their by-age married shares
and by-age dating rates mix compositions) which are shown but not scored.

`scripts/calibrate.py` tunes the most influential parameters (asking out, kissing, couple time by stage,
engagement, breakups, job search) by coordinate search on two seeds with common random numbers, minimizing
the weighted misfit (Census rows weighted 3×), and writes the chosen values back into the rule files.
`scripts/stability.py` runs four years and reports drift.

**Latest results** (one-year run at scale 0.15, iteration 5; details in `docs/VALIDATION.md` and the Model check page):

| Checks | Match | Close | Off |
|---|---|---|---|
| Census and institutional benchmarks (married share at 18–24; BYU and UVU married shares) | 6 | 0 | 0 |
| Behavior (benchmarks + rows that emerge from simulated decisions) | 34 | 11 | 2 |
| Survey tables held out of calibration | 10 | 2 | 0 |
| All scored rows (including starting values and pattern rows) | 50 | 21 | 5 |

Since iteration 5, social events are a realized count rather than a copied survey value (so they now miss
honestly), and pattern rows check structure: perceived vs actual support (r ≈ .49, literature ≈ .35–.5),
friendship clustering (.16), the share of intentions carried out (.66 vs ~.5), the liking gap and the direction
of pluralistic ignorance. The four-year check keeps enrollment near target, loneliness, depression and
missionaries steady (`scripts/accounting.py` balances stocks and flows), and the married share of students near
17–20% (institutional ≈25%).

**Known gaps.** Lifetime "people kissed" counts drift above the survey (they only grow); the married share
of students settles a little low over several years; Census bands from age 25 compare different populations
(the model leaves out most single working residents) and are not scored; several mechanisms remain
hypothetical (labelled). The calibration fits one year at a time.

---

## 7. Code structure

```
ucsim/                      Python package
  registry.py               loads the YAML registries; ParamSet (per-run parameter values)
  config/                   the model as data
    variables/*.yaml        296 measures (person, edge, unit, complex, world) with ranges, evidence, sources
    mechanisms/*.yaml       133 rules: label, target, sources, formula, parameters (value + range), evidence, refs
    events.yaml             66 event kinds: label, story template, salience, emotional effects
    interventions.yaml      20 what-if presets
    world.yaml              population sizes, class mix, flows, calendar, climate, economy, tuition, history
    majors.yaml             BYU and UVU majors by college (scripts/build_majors.py)
    sources/                ACS benchmark, UVU catalog extract
    validation.json, stability.json   latest check results (written by scripts)
  ingest/                   survey → aggregate priors (raw data never committed)
  priors/                   survey_priors.json (aggregates only)
  geo/                      build_world.py (UGRC + OSM → dwellings, complexes, venues), osm_housing.py,
                            neighborhoods.py, data/*.parquet|json (committed derived data)
  population/               build.py (world assembly), synth.py (people), structure.py (housing, wards,
                            jobs, network), majors.py, sampling.py
  engine/
    state.py                PersonTable, EdgeStore, contexts (CTX), tie flags
    core.py                 Calendar, random streams, EventLog, Effects
    world.py                World dataclass
    sim.py                  Simulation: day phases, system order, clamps
    runner.py               new_simulation, fork (paired worlds), divergence, Monte Carlo, sweeps
    interventions.py        intervention manager
    systems/                environment, lifecourse, academics, activity, groups, encounters, network,
                            romance, emotion, faith, norms, economy, housing, recorder, history
  analysis/                 query.py (cohort DSL incl. transitions), explain.py (attribution, ego nets,
                            goals), person.py (profiles), butterfly.py (Original vs What-if: every field,
                            diverged lives, one person's two lives, couples/friendships, places),
                            fields.py (field summaries and timelines, person history, the pulse, couples)
  api/server.py             FastAPI app: ~60 endpoints, binary columnar transport for large arrays
  app.py                    desktop launcher (pywebview window, free port, self-test)
web/                        React + TypeScript (Vite)
  src/App.tsx               shell: HUD, world navigation + research desk, routes, keys, error boundary
  src/hud.tsx               clock/sky, speeds, jumps, world lens, butterfly meter, settings; timeCtl
  src/game.tsx, game.css    game building blocks: lens switch, universe badges, meters, sparklines, icons
  src/fields.ts             the field catalog: drawers, formatting (values, averages, deltas), pair events
  src/palette.tsx           search anything (Ctrl K)
  src/toasts.tsx            live news, divergence milestones, time-skip recaps
  src/nav.ts                the places of the world and the research desk
  src/time.tsx              the calendar ribbon
  src/store.ts              zustand store (route, lens, filter, follows, pins, toasts, caches)
  src/api.ts                API client
  src/ui.tsx, components.tsx, analysis.ts, graph.tsx, names.ts
  src/views/                World, MapView, People, PersonView, Relationships, Places, Events,
                            whatif/ (Change builder + drawer, WhatIf butterfly view), explore/ (FieldPane,
                            FieldCanvas, FieldExplorer), research pages (Overview, Flows, Crosstab,
                            CausalWeb, Experiments, ModelCheck, Variables, Mechanisms, About), Guide,
                            WorldSetup (title and loading screens)
scripts/                    validate, calibrate, stability, gen_catalogs, fetch_* /
                            build_* data builders
tests/                      pytest: engine, population, interventions, analysis/API/privacy, realism,
                            butterfly (game-layer reads and endpoints)
packaging/                  PyInstaller spec, Inno Setup installer, icon
.github/workflows/          Windows installer build + self-test + release
docs/                       this guide and the other references
```

### How a day runs
`Simulation.step_day()` runs phases: **start** (environment, life course, academics, groups, faith,
romance planning) → three **blocks** (activity choice → encounters; evening romance) → **end of day**
(friend contact, romance, emotions, norms; weekly systems on Sunday night; monthly systems on the last day
of the month; housing; night positions; clamps; recorder; history snapshot).

### Extending the model
- **Add a measure**: declare it in `config/variables/*.yaml` (dtype, range, kind, evidence, description);
  it becomes a column automatically and appears in the dictionary, filters, charts and map.
- **Add a rule**: declare it in `config/mechanisms/*.yaml` with parameters and evidence, read the
  parameters with `sim.p("rule.param")` in a system, and (for feelings) return a named term so the "why"
  panel can show it.
- **Add an event**: declare it in `config/events.yaml` with a story template and effects; emit it with
  `sim.emit(...)`, passing a cause and mechanism.
- **Add a what-if**: add a preset to `config/interventions.yaml`; it appears in the lab.
- After changes: `pytest`, `python scripts/validate.py`, `python scripts/gen_catalogs.py`.

### Testing and release
`pytest` (about 50 tests, under a minute) covers determinism, invariants, interventions, the cohort
language, the API, privacy guards and the realism checks. CI builds the Windows installer and runs a
packaged self-test.

---

## 8. Reflection and vision

**What works well.** The core idea (a shared, explainable world where opportunity structure drives social
life) holds up: lives look plausible, patterns emerge that nobody scripted (friendship clusters by
complex and ward, dating waves after arrivals, the summer exodus), and every number can be opened up to its
causes. The registries make the model inspectable and editable without reading the code, and paired worlds
give what-if results a clean counterfactual. Grounding in real geography and institutions makes it feel
like Provo.

**Where it is thin.**
1. *Calibration breadth.* The fit covers a year and a handful of parameters; many rules sit at
   literature-based or hypothetical values. Survey targets come from convenience samples.
2. *Uncertainty.* A single run is one possible future. Monte Carlo exists but isn't the default view of a
   what-if result.
3. *People outside the student world.* Non-student residents, families and employers are sketched, not
   modeled.
4. *Social media and phones.* Group chats, Instagram and comparison are a big part of student social life
   and are only represented as hours and app use.
5. *Scale and speed.* Full scale (60k) runs but slowly in the UI; long experiments at high scale need
   patience.

**The vision.** A trustworthy "flight simulator" for college social life: administrators, ward leaders,
housing managers, researchers and students themselves could try ideas (a new housing rule, a dating event,
a mental-health program, a club fair) and see plausible consequences, with honest uncertainty and every
claim traceable to evidence.

### Done in iteration 5
Inner lives (motives, drives, expectations, perception, memory, appraisal, coping, intentions, routines),
relationship histories, place cultures, stock-flow accounting and drift fixes, pattern-oriented and longitudinal
validation with held-out tables, uncertainty ensembles separating chance from assumptions, an ODD description.

### Quick wins (high value, low effort)
1. **Uncertainty by default in the What-if view**: the ensemble machinery exists (Experiments → How sure?); run
   it automatically after a what-if and show ranges on the change cards and the all-fields scan.
2. **Calibrate more parameters on a schedule** (friendship formation, loneliness setpoint, faith influence)
   and add the four-year drift to the calibration loss.
3. **Two filters at once**: compare two groups on the same chart (e.g. BYU vs UVU, LDS vs not) in Explore.
4. **Export**: one-click CSV/PNG for every chart, and a printable "report" of your pinned board with notes.
5. **Saved worlds**: save and reload a whole world and its what-if from the UI.
6. **Per-person history for more fields**: snapshots are kept for 41 fields; a compact store (8-bit
   quantized) could cover all 217, so any filter could be followed over time.
7. **Hourly map scrubber**: show the 8am/1pm/6pm/night frames as named stops on the "A day" slider.
8. **Real employers**: replace generic "Tech/office" employers with named large employers near each site.

(Done in the game-interface pass: search everywhere, pinned boards, the all-fields comparison, the
person-level counterfactual with its first fork, time-skip recaps.)

### Creative ideas for the future
- **Narrated lives** (the deferred LLM layer): a person's year written as a short story from their event
  chain; "interview" a synthetic person about why they did something, grounded strictly in their record.
- **Ask in plain English**: "What happens to loneliness if every complex had a weekly game night?" compiled
  into the existing intervention and cohort schemas, with the plan shown before it runs.
- **Seasons of Provo**: special events that matter locally (BYU football Saturdays, Stadium of Fire, General
  Conference weekends, the first snow at Sundance, finals week) as calendar-driven shocks.
- **Policy sandboxes**: an "administrator mode" for housing offices or ward councils with budgets and
  trade-offs; a "student mode" game where you guide one person through four years.
- **Challenges**: goals to reach with as few changes as possible ("cut loneliness among freshmen by a tenth
  without raising rent burden"), scored by the butterfly view, with a leaderboard of strategies.
- **A third world**: fork the What-if again to compare two policies against the same Original.
- **Dating-app lab**: different matching algorithms and their effects on who meets whom.
- **Network epidemiology**: illness or ideas spreading through co-presence and friendship, visible on the map.
- **Mental-health programs**: peer support, counseling capacity, and outreach targeting tested as what-ifs.
- **A public, anonymized "Provo pulse"**: compare the simulation to periodic real survey waves to keep it honest.
- **Multiplayer classroom**: a sociology class runs competing interventions on the same world and compares.
