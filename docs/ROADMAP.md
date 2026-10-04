# Roadmap

## Iteration 1 — end-to-end vertical slice

Population → real geography & housing → characteristics → schedules → encounters → relationships →
events → emotion → behavior change → intervention → paired simulation → history → cohort filtering →
map → charts → causal explanation → individual drill-down. Registries with evidence labels, tests,
validation report, static demo.

## Iteration 2 — usability and real-world detail

Guided Home, Field guide, Simple/Advanced switch, task-based navigation, plain-language stories; flows over
time (14-day snapshots, Sankey, transition cohorts); what-if wizard with saved experiments; real complex
names (OSM + BYU contracted list), official neighborhoods, BYU/UVU majors, physical traits; clubs,
intramural teams and institute classes; first-year contracted-housing rule; admissions-driven enrollment
that stays stable over multi-year runs.

## Iteration 3 — trustworthy numbers, religious diversity, time and replay

Census benchmark and automated calibration (`scripts/calibrate.py`), four-year stability check, in-app
Model check; non-LDS affiliations, real congregations, faith/secular student groups, religious-outsider
feeling, missionary contact and conversion; Play/Pause with a watchable pace, academic-year ribbon,
map replays of a day and of the months so far; error boundary; project guide (`docs/PROJECT_GUIDE.md`).

## Iteration 4 (this release) — the game interface

Same engine and depth; the interface of a simulation game. HUD with a day/night clock, Sims-style speeds,
the Original / What-if / Compare lens on every page and a butterfly meter; World landing page with a
living map, headlines, week board, trends, pinned board and one-click what-ifs; Explore (every field in
friendly drawers: now, over time, by group, relate, people, drivers); What-if change builder (ideas,
levers, people and rule nudges; add to a running What-if) and butterfly view (all fields, events, lives,
relationships, places, why); person pages as lives with history strips and the other life's first fork;
Relationships area; search palette, live news, time-skip recaps, keyboard shortcuts; title and loading
screens; research tools moved to a Research desk. Server: weekly all-field aggregates and the comparison,
pulse, history and relationship endpoints.

## Still to do (from the master prompt)

- **LLM layer** (deliberately deferred): natural-language questions and what-ifs compiled to the existing
  JSON intervention/cohort schemas; narrated life stories.
- **Calibration**: formal simulated-method-of-moments fit; dating frequency and kissing counts drift above
  the survey over a year (see `VALIDATION.md`); married-share of 24-30 year olds (survey bias suspected).
- **Sensitivity mode**: Morris/Sobol screening across every parameter range; flag results driven by
  hypothetical mechanisms.
- **Backtesting** against administrative series (Utah County marriages by age, enrollment by term, rents).
- **External data**: Census ACS/LODES for non-student residents and commutes; official BYU/UVU class-level
  enrollment; real employer locations.
- **Model depth**: cohabitation, social media as a second network, non-LDS religious communities,
  family ties in Utah County, room-level dorm assignment.
- **Workstation**: side-by-side cohort comparison, report export, map time-lapse.

## Earlier backlog

**Calibration & validation**
- Simulated method of moments over mechanism parameter ranges (dating frequency by age/stage, DTR and
  engagement timing, breakup rates, friendship counts) with a held-out set of survey targets.
- Administrative targets: Utah County marriage counts by age, BYU/UVU enrollment flows by term, rent series,
  mission departures; replace `(approx)` figures in `world.yaml` with official numbers.
- Sensitivity report: Sobol/Morris screening across all parameter ranges; flag outcomes dominated by
  hypothetical mechanisms.

**Model depth**
- Class schedules (real course sections and buildings), study groups, TA/professor ties.
- Dorms/contracted housing room assignment; roommate matching services; subleasing.
- Richer family ties (parents and siblings in Utah County, Sunday dinners, family pressure events).
- Social media as a second network layer (follows, comparison, Instagram-official), group chats.
- Non-LDS communities (Catholic, evangelical, secular groups), interfaith dating dynamics.
- Health: exercise, sleep debt, illness spread through co-presence.
- Long-distance relationships and missionary letters; post-mission reentry.

**Experiments & tooling**
- Natural-language → intervention compiler (the JSON schema already exists).
- Scenario library with saved paired runs and shareable links; diffable run reports.
- GPU/numba kernels for encounters and network updates; full scale (≈60k) at < 0.5 s/day.
- Snapshot scrubbing (time slider over monthly snapshots) in every view.
- Multi-run comparison dashboards (distribution of effects across seeds per subgroup).

**Workstation**
- Saved cohorts, cohort comparison side-by-side, report builder/export (PNG/CSV/Markdown).
- Map time-lapse (hourly playback), flows between complexes, ward boundary polygons.
- Person life-story narrative generated from the event chain.
