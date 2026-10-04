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

Three kinds of use, all in one app:

| Use | Where in the app | Example |
|---|---|---|
| **What-if experiments** | What-if lab | "If rent rose 20%, what happens to dating and loneliness over a semester?" |
| **Research questions** | Explore a measure, Compare groups, Flows over time, Places | "Do clubs and intramurals make students less lonely?" |
| **Following individual lives** | People, a person's page, Follow | "Why is this person lonely? What happened to them this year?" |

Design principles that run through everything:

- **Evidence-labelled.** Each of the 296 measures and 133 rules carries an evidence level (*observed*,
  *empirical*, *literature*, *calibrated*, *extrapolated*, *hypothetical*). Hypothetical rules are allowed
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

The first screen builds a world: pick a **scale** (share of the real community: 0.05 ≈ 3k people for quick
looks, 0.15 ≈ 9k, 0.3 ≈ 18k, 1.0 ≈ 60k), a seed, and warm-up days. Use **World ⚙** later to rebuild.

**Read-only snapshot.** `scripts/export_static.py` exports a pre-run world (with a what-if branch) as a
static site that runs in any browser, including the published demo page. Running time needs the app.

---

## 3. Using the app

### The shell
- **Top bar**: date and place in the academic year; **▶ Play / ⏸ Pause** with a **Watch** pace (about one
  simulated day per second) or **Fast**; **+1 week**; **Jump ▾** (+1 hour, day, month, semester, year,
  four years, or run until a date); the **Original / What-if** switch when a what-if world exists; world
  settings; theme.
- **Calendar ribbon** under the top bar: this academic year's semesters, terms and breaks, today (blue line),
  what has already happened (hatched), and where a what-if world split off (dashed line). Click any future
  date to run there, normally or at the watchable pace.
- **Simple / Advanced** (bottom left): Simple hides expert tools (rules list, custom interventions, Monte
  Carlo, sweeps, raw tables) and uses plain language throughout.
- **Cohort bar** on analysis pages: a group of people (e.g. "single UVU women 20–23 who broke up in the last
  90 days") that follows you from page to page until cleared.

### Pages
| Page | What it answers |
|---|---|
| **Home** | What happened this week (story feed), vital signs with trends, a gallery of ready-made questions, people you follow, lives worth following. |
| **Field guide** | How the world works, in plain language: layers, what a person is made of, how relationships, feelings and faith work, how time works and how to use it, what-if experiments, how sure we are, where to go for what, glossary. |
| **Vital signs** | Population trends over time for both worlds; what people are doing right now; where friendships and romances began. |
| **Map** | People where they are right now; homes, complexes and wards colored by any measure; neighborhoods, venues and congregations; difference between worlds. **▶ A day** replays the last full day (8am, 1pm, 6pm, night); **▶ Over months** replays the two-week snapshots with homes colored by any tracked measure. |
| **Friend network** | A sampled friendship graph, colored by church activity, school, sex or relationship; filter by tie type (roommates, classmates, ward, clubs, teams, institute, congregation, couples); same-group mixing (homophily). |
| **People / Person** | Search and follow people. A person page tells their story (events with "why?" chains), how they feel and why (each feeling split into its causes), relationships, faith, personality, physical description, major, home and neighborhood, clubs, congregation, and how their life differs in the what-if world. |
| **Life events** | Every event with counts, filters and causal chains (what led to it, what followed). |
| **Explore a measure** | Distribution of any measure, split by a group, or plotted against another; "Why is this group different?" breaks a gap into the model's forces with example lives. |
| **Compare groups** | Survey-style cross-tabs with strength of association; click a cell to make those people your group. |
| **Flows over time** | Sankey diagrams of who moved between states (single → dating → married; active → less active; affiliations; living situations) and the trajectories of today's group. Pick a band to study exactly those people. |
| **Places** | Complexes and wards ranked by any measure; profiles of each place: who lives there, how connected they are, what happened there. |
| **What-if lab** | Three steps: choose changes (presets grouped by theme, or custom ones in Advanced), how long to watch, then see what changed in plain language with the rules responsible and the people most affected. Save combinations to rerun. Advanced: many runs (Monte Carlo) and parameter sweeps. |
| **Cause & effect** | The web of rules connecting every measure. |
| **Model check** | How the simulation compares with the Census and the surveys, row by row, and whether it stays steady over four years. |
| **Data dictionary / Rules / Evidence & sources** | Every measure and rule with its definition, formula, parameters, evidence and references; data sources and limitations. |

---

## 4. The model

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

**Latest results** (one-year run at scale 0.15; details in `docs/VALIDATION.md` and the Model check page):

| Checks | Match | Close | Off |
|---|---|---|---|
| Census and institutional benchmarks (married share at 18–24; BYU and UVU married shares) | 4 | 2 | 0 |
| Behavior (benchmarks + rows that emerge from simulated decisions) | 35 | 12 | 0 |
| All scored rows (including starting values) | 50 | 20 | 3 |

The four-year check keeps BYU fall enrollment within about 8% of its cap, loneliness and close friends
steady, and the married share of students near 20% (the institutional figure is about 25%).

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
                            goals), person.py (profiles)
  api/server.py             FastAPI app: ~45 endpoints, binary columnar transport for large arrays
  app.py                    desktop launcher (pywebview window, free port, self-test)
web/                        React + TypeScript (Vite)
  src/App.tsx               shell, navigation, routes, error boundary
  src/time.tsx              play/pause, jumps, calendar ribbon
  src/store.ts              zustand store (route, cohort, mode, follows, caches)
  src/api.ts                API client (+ static-snapshot fallbacks)
  src/ui.tsx, components.tsx, analysis.ts, graph.tsx, names.ts
  src/views/*.tsx           one file per page (Home, Guide, Overview, MapView, Flows, Lab, ModelCheck, …)
scripts/                    validate, calibrate, stability, export_static, gen_catalogs, fetch_* /
                            build_* data builders
tests/                      pytest: engine, population, interventions, analysis/API/privacy, realism
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
packaged self-test. `scripts/export_static.py` builds the read-only demo.

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

### Quick wins (high value, low effort)
1. **Uncertainty by default in the What-if lab**: run 4–8 seeds in the background after a what-if and show
   ranges on the change cards.
2. **Calibrate more parameters on a schedule** (friendship formation, loneliness setpoint, faith influence)
   and add the four-year drift to the calibration loss.
3. **Side-by-side groups**: compare two cohorts on the same chart (e.g. BYU vs UVU, LDS vs not).
4. **Export**: one-click CSV/PNG for every chart and a "report" page that assembles chosen charts with notes.
5. **Saved worlds**: save and reload a whole world and its what-if from the UI.
6. **Search everywhere**: a command palette to jump to any person, measure, place or question.
7. **Hourly map scrubber**: show the 8am/1pm/6pm/night frames as named stops on the "A day" slider.
8. **Real employers**: replace generic "Tech/office" employers with named large employers near each site.

### Creative ideas for the future
- **Narrated lives** (the deferred LLM layer): a person's year written as a short story from their event
  chain; "interview" a synthetic person about why they did something, grounded strictly in their record.
- **Ask in plain English**: "What happens to loneliness if every complex had a weekly game night?" compiled
  into the existing intervention and cohort schemas, with the plan shown before it runs.
- **Seasons of Provo**: special events that matter locally (BYU football Saturdays, Stadium of Fire, General
  Conference weekends, the first snow at Sundance, finals week) as calendar-driven shocks.
- **Policy sandboxes**: an "administrator mode" for housing offices or ward councils with budgets and
  trade-offs; a "student mode" game where you guide one person through four years.
- **Dating-app lab**: different matching algorithms and their effects on who meets whom.
- **Network epidemiology**: illness or ideas spreading through co-presence and friendship, visible on the map.
- **Mental-health programs**: peer support, counseling capacity, and outreach targeting tested as what-ifs.
- **A public, anonymized "Provo pulse"**: compare the simulation to periodic real survey waves to keep it honest.
- **Multiplayer classroom**: a sociology class runs competing interventions on the same world and compares.
