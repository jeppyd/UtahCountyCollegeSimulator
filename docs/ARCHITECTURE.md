# Architecture

A spatial, event-driven social microsimulation of the BYU/UVU ecosystem in Provo–Orem, with an
analysis workstation on top. Python engine → FastAPI → React/TypeScript.

```
surveys (raw, gitignored) ──► ucsim/ingest ──► ucsim/priors/survey_priors.json   (aggregates only)
UGRC + OSM geography ──────► ucsim/geo ─────► ucsim/geo/data/*.parquet, web/public/geo/*
YAML registries ───────────► ucsim/registry.py  (variables · mechanisms · events · parameters)
                                   │
                ucsim/population  (synthesis: skeleton CPTs → copulas → structure → network)
                                   │
                ucsim/engine      (World state + Simulation clock + 13 systems + interventions)
                                   │
                ucsim/analysis    (cohort DSL, attribution, provenance, profiles)
                                   │
                ucsim/api         (FastAPI; binary columnar transport)  ──►  web/ (workstation)
                scripts/          (validation, static export, catalogs, geodata)
```

## Data model

| Store | What | Notes |
|---|---|---|
| `PersonTable` (`engine/state.py`) | one NumPy column per registered person variable (+ internal columns) | built from the registry; categorical = uint8 codes; grows by doubling when agents arrive |
| `EdgeStore` | undirected relationships keyed `(lo<<32)\|hi`, sorted | columns for familiarity, liking, closeness, trust, conflict, directed attraction (`att_lh`, `att_hl`), hours, stage, tie flags (roommate, ward, dated, spouse, ex…), origin context/place, introducer |
| `EventLog` (`engine/core.py`) | append-only columnar log | type, day, block, a, b, place, value, **cause** (parent event id), **mech** (mechanism id) |
| `Effects` | decaying event effects on states | magnitude, start, half-life, source event; summed per agent per day |
| `World` | P, E, housing units, complexes, wards, employers, venues, meetinghouses, environment, calendar; `meta["culture"]` (place cultures) |  |
| `MemoryStore` (`engine/memory.py`) | episodic memory: person, event pointer, other person, valence, importance, rehearsals | power-law forgetting, per-person cap (40), core memories kept; retrieval by recency × importance × relevance |
| Plan ledger (`systems/plans.py`) | weekly intentions: person, kind, target, start, due, status, reason, motivating drive | pruned to active + recent per person |
| Routines (`systems/routine.py`) | per person × 21 weekly slots: habitual option and habit strength | two dense arrays |

Edges also carry the *perceived* side of romance (`bel_lh`, `bel_hl`: what each believes the other feels) and
relationship history (`disclosure`, `support`, `hurt`, `shared`).

Registries (`ucsim/config/`) are the single source of truth for variables, mechanisms, event types and
intervention presets (counts in `docs/VARIABLE_CATALOG.md` and `docs/MECHANISMS.md`). Each variable/mechanism has
an evidence label (observed · empirical · literature · calibrated · extrapolated · structural · hypothetical ·
speculative) that the UI always shows. Mechanism parameters live in a per-run `ParamSet` so interventions/sweeps
never mutate the registry; parameters may declare a distribution (`dist: triangular | uniform | choice`) and
structural switches (`structural: true`) used by uncertainty ensembles.

## Time

Days are split into phases: `start@6 → block0@8 → block1@13 → block2@18 → end@23`.

| Cadence | Systems |
|---|---|
| start of day | environment, lifecourse (arrivals/departures), academics, groups, faith (Sunday attendance), romance.plan_day |
| each block | activity choice (obligations → Gumbel-max discretionary choice over habit/trait bases, drives, routine, coping and intention biases), encounters in shared contexts (beliefs, disclosure, shared experiences, learned warmth); evening dates & NCMOs |
| end of day | friend contact (reconnecting, support seeking, introductions), romance.daily, **mind** (fulfilment → drives), **coping**, **plans** (kept/abandoned/lapsed), emotion.daily, norms, housing, night, clamp, recorder, history |
| weekly (Sun) | network (closeness from time, liking, disclosure, shared experiences, hurt; repair; forgetting), **mind** (importance drift, perceived support and friends' belief, memory pruning), **culture**, faith, norms contagion, romance, **plans** (form intentions), **routine**, academics, emotion |
| monthly | economy, housing market, lifecourse (missions, fertility), life satisfaction |
| per term / yearly | GPA & graduation, annual cohorts (Aug 20), summer exodus, lease cycle |

`advance_hours` runs phases as the clock passes their hour, so the map can be stepped hour by hour.

## Systems (`engine/systems/`)

environment · housing · activity · network · academics · encounters · economy · romance · faith · norms ·
**mind · coping · plans · routine · culture** · emotion · lifecourse · recorder · history. Each reads/writes the
shared columns and emits events with mechanism ids. The five new systems are the inner life and the meso layer
(`docs/MIND.md`): behavior reads drives, expectations and perceptions instead of raw feelings.

`Simulation.emit` appraises every event (relevance to what the person cares about; coping potential), scales its
registered emotional effects accordingly, and lays down a memory.

**Emotional states are composed, not stored**: `state = clip(Σ mechanism terms + Σ decaying event effects + AR(1) noise)`.
The terms are kept per agent, which makes "why is this person lonely?" an exact decomposition rather than a
post-hoc explanation, and makes universe comparisons additive.

## Randomness, universes and experiments

`Streams` derives a generator from `(seed, stream name, day, block)`, and `pair_normal` hashes agent pairs
(chemistry, spark). Two universes with the same seed therefore consume **common random numbers**:
`fork()` deep-copies a running simulation and attaches interventions, so any divergence is caused by the
intervention or its butterfly effects. `compare_universes` decomposes Δstate into Δmechanism terms;
`divergence` tracks state/network distance; `monte_carlo` and `sweep` run seeds/values in a process pool
with paired differences.

Interventions (`engine/interventions.py`) are JSON: `world` (environment variables), `param` (mechanism
parameters), `agent` (a filtered population, logged as exposure events) and `venue` (new places), with
start day, ramp and duration.

## Analysis & API

- `analysis/query.py` — cohort filter DSL (and/or/not, comparisons, quantiles, recent events, household composition).
- `analysis/explain.py` — event chains/descendants, per-person state decomposition, cohort attribution, universe comparison, most-affected people.
- `analysis/person.py` — profiles and deterministic synthetic names.
- `analysis/butterfly.py` — Original vs What-if: every chartable field (means/shares, a common effect size,
  share of people individually different, difference over time from the weekly aggregates), events matched
  across worlds by (person, day, type, other person), diverged lives, one person's two lives and the first
  fork's cause chain, couples/friendships in only one world, per-place differences.
- `analysis/inner.py` — one person's inner life (motives and drives, beliefs vs reality, memories, intentions,
  coping, lessons, routine, footprint), read-only.
- `analysis/fields.py` — field summaries and weekly timelines, one person's two-weekly history, the "pulse"
  (what people did in each block of the last day, the week's events, diversified headlines, four-week
  movers, featured lives), couples.
- `api/server.py` — ~60 endpoints; columns travel as a packed binary format (`pack_columns` ↔ `web/src/api.ts:decodePack`), so the browser filters and charts ~10–50k agents client-side.
  Runs and world builds happen on a background thread, one at a time (`Workspace.start_job` claims the slot
  before the thread starts). The run takes the workspace lock once per simulated day; the lock is a FIFO
  `FairLock`, so page requests queued during a day are answered before the next day starts (a plain lock let
  the run re-take it every day and pages waited for the whole run). `/api/status` and `/api/cancel` run on the
  event loop without the lock, so the clock and Pause always respond. Comparisons are memoized until either
  world moves; a run that fails records which world and day in `last_job` and stops, and the What-if catches
  up on the next run if it was left a day behind. In the browser, pages reload at most every 2.5 s while time
  runs and at once when it stops; `useAsync` keeps one request per view in flight; requests time out.

## Workstation (`web/`)

React 18 + zustand + ECharts + deck.gl/MapLibre + Cytoscape, skinned as a simulation game. The store's
`lens` ('base' | 'alt' | 'compare') decides which universe every view loads (`useLens()`); compare-aware
views load both and overlay them (Original blue, What-if orange). The shell (`hud.tsx`, `nav.ts`,
`palette.tsx`, `toasts.tsx`) provides the clock, speeds (`timeCtl`), lens, butterfly meter, search, news and
recaps. World areas: World, Map, People/Person, Relationships, Places, Events, What-if (`views/whatif/`),
Explore (`views/explore/`, driven by the field catalog in `fields.ts`); the research desk keeps Vital signs,
Flows, Cross-tabs, Cause & effect, Experiments, Model check, Data dictionary, Rules and Evidence. The filter
(cohort) persists across views; in Compare it is evaluated in the Original and applied to the same people in
the What-if.
`npm run build:static` + `scripts/export_static.py` produce a static snapshot (no server) for sharing.

## Validation, accounting and uncertainty

- `scripts/validate.py` — survey/Census rows, pattern rows (structure), held-out tables, longitudinal section
  (`analysis/panel.py`: within- vs between-person cross-lagged effects).
- `scripts/accounting.py` / `analysis/accounting.py` — stocks, logged flows, balance residuals, hazards and
  Little's-law equilibria between same-day checkpoints each year.
- `scripts/uncertainty.py` / `engine/uncertainty.py` / `POST /api/uncertainty` — Latin-hypercube parameter draws
  scaled by evidence, paired What-if runs per (draw, seed), stochastic vs parametric variance, sign robustness,
  parameter attribution (≥ 12 draws).
- `scripts/calibrate.py` — coordinate search over selected parameters on two seeds; held-out tables excluded.

## Performance (scale 0.15 ≈ 9–11k agents, one core)

Build ≈1.8 s; ≈0.23 s per simulated day including the recorder and the inner-life systems (see
`docs/VALIDATION.md` for the per-system breakdown). Edge inserts merge sorted runs in O(n). Full scale (≈60k
agents) is ≈1.5–2 s/day; Monte Carlo and uncertainty ensembles parallelize across processes.
