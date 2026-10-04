# ODD description

The Overview, Design concepts and Details protocol (Grimm et al. 2006, 2010, 2020) is the standard way to
describe an agent-based model so it can be understood, criticized and replicated. Mechanism-level detail (every
rule with its parameters, ranges, evidence and references) is generated into `docs/MECHANISMS.md` and
`docs/VARIABLE_CATALOG.md` from the registries in `ucsim/config/`; this document is the map.

## 1. Purpose and patterns

**Purpose.** To explore how social life in the BYU/UVU college ecosystem of Provo and Orem, Utah — friendship,
dating and marriage, faith, wellbeing, school, work, money and housing — emerges from many constrained,
heterogeneous people living in real places, and how it would differ under changes to that world (what-if
experiments with paired counterfactual universes). It is an explanatory and exploratory instrument, not a
forecast of real individuals.

**Patterns used to evaluate it** (pattern-oriented modeling; `scripts/validate.py`, `docs/VALIDATION.md`):
married share by age and sex (Census ACS, Provo + Orem); BYU/UVU enrollment and married shares; survey
distributions of dating frequency by relationship stage and church activity, social events, GPA, sleep, work
hours, coffee/alcohol, temple and scripture practice by activity; structural signatures — perceived vs actual
support correlation, friendship-network clustering, the share of intentions carried out, wedding seasonality,
the liking gap, the direction of pluralistic ignorance, depression prevalence; within- vs between-person
longitudinal structure; multi-year stability of major stocks and their stock-flow accounting
(`scripts/stability.py`, `scripts/accounting.py`). Some survey tables are held out of calibration.

## 2. Entities, state variables and scales

| Entity | State (registry) | Notes |
|---|---|---|
| **Person** | ~320 variables (`config/variables/*.yaml`): demographics, personality, religion (multidimensional), values, dating preferences, habits, school, work, money, housing; composed feelings; **inner life** — motives and drives, expectations, perceived support and friends' belief, coping, intentions, routine strength, memory summary, home culture | Columnar `PersonTable`; between-person (slow) and within-person (fast) parts kept separate |
| **Relationship** (pair) | familiarity, liking, closeness, trust, conflict, directed attraction, **believed interest** (each direction), hours, stage, tie flags, origin and introducer, dates, **disclosure, support, hurt, shared experiences** | Sparse sorted `EdgeStore`; only pairs who have met |
| **Memory** (person × event) | event pointer, other person, valence, importance, rehearsals | `MemoryStore`, pruned (≤ 40 per person; core memories kept) |
| **Intention** | person, kind, target, start, due, status, reason, motivating drive | Plan ledger (pruned) |
| **Routine** | per person × 21 weekly slots: habitual option, habit strength | Two dense arrays |
| **Places** | housing units (real dwellings), complexes, wards, meetinghouses, congregations, venues, campuses, class sections, employers, clubs/teams/institute classes, neighborhoods | From UGRC/OSM/city GIS; cultures for units, complexes, wards |
| **World** | economy, rents, tuition, calendar, weather, norms (marriage, men-initiate, attendance, coffee…) | `env` dict; interventions change it |
| **Event** | type, day, block, persons, place, value, **cause** (parent event), **mechanism** | Append-only `EventLog`: the causal record |

**Scales.** Space: real coordinates for Provo/Orem. Time: days with three activity blocks (8am, 1pm, 6pm) and
night; weekly, monthly, term and yearly processes. Population: scale 1.0 ≈ 60k people (BYU ~35k students, an
in-scope 16k of UVU, young adults, spouses, faculty/staff, community); typical runs use 0.05–0.3.

## 3. Process overview and scheduling

Each day (`engine/sim.py`):

1. **Start of day** — environment (calendar, weather, interventions), life course (arrivals, missions, leaving,
   births, illness), academics (term starts/ends), groups, faith (Sunday attendance), romance (today's dates).
2. **Three blocks** — activity choice: obligations first (class, work, church, FHE, clubs, dates, gatherings),
   then free time by random utility over habit and trait bases, **drives**, **routine habit**, **coping bias**
   and **intention bias**; encounters among co-present people (interaction valence, liking, closeness,
   **believed interest**, **shared experiences**, **disclosure**, learning the **warmth** of social settings);
   evening dates, kisses and NCMOs.
3. **End of day** — deliberate friend contact (reconnect intentions, support seeking, friends bringing friends);
   romance decisions (motivation from the partnership drive, asks from expected acceptance and believed
   interest); **mind** (experience → fulfilment → drives); **coping** (need, episodes, relief, rumination);
   **plans** (kept / abandoned / lapsed); emotions (composed of named terms + appraised event effects + noise);
   norms; housing (lease turnover with culture-fit sorting); recorder and history.
4. **Weekly (Sunday night)** — network stages, closeness from time/liking/disclosure/shared/hurt, repair,
   forgetting; **mind** (importance drift, perceived support, perceived friends' belief, memory pruning);
   **culture** (apartment/complex/ward cultures); faith (attendance probabilities, influence via perceived belief —
   assimilation or bounded confidence — crises); norms contagion; romance (crushes, couple dynamics, engagement,
   break-aware wedding dates, breakups); **plans** (form intentions); **routine** summary; academics; emotion
   (contagion, ward belonging with ward warmth, depression).
5. **Monthly / term / yearly** — economy, housing market, missions, fertility; grades and **confidence**,
   graduation, dropout; cohorts arrive each fall (admissions controller projects the October census).

Paired universes share random streams keyed by (seed, stream, day, block), so a What-if differs only through
its intervention and the butterfly effects that follow.

## 4. Design concepts

- **Basic principles.** Opportunity before preference (people only meet through shared places); relationships
  as histories; composed, decomposable feelings; a mind that mediates between state and behavior (motives →
  drives, learned expectations, perception that can be wrong, appraisal, coping, intentions, routines);
  cultures with memory. See `docs/MIND.md`.
- **Emergence.** Friend groups and network clustering, dating waves and seasonal weddings, apartment and complex
  cultures and residential sorting, loneliness loops (isolated people learn that reaching out does not help),
  pluralistic ignorance sustaining a norm, multi-year enrollment and marriage stocks.
- **Adaptation.** Free-time choice, dating motivation, asks, coping strategy, intentions and housing choice
  respond to drives, expectations and perceptions.
- **Objectives.** Eight concerns weighted by importance; drives (importance × unmet) are the implicit objective
  of discretionary choice. No global optimization.
- **Learning.** Prediction-error updating of expected acceptance and expected warmth; academic confidence from
  mastery experiences; coping strategy values from episode outcomes; habit strength per routine slot.
- **Prediction.** Implicit only: expectations are agents' predictions of outcomes.
- **Sensing.** Agents sense their own state, their ties (closeness, liking), what friends *express* (not what
  they believe, unless confided), a noisy read of others' romantic interest, local norms from friends, ward and
  complex, and place reputations. They do not see others' true attraction or the global state.
- **Interaction.** Encounters, dates, gatherings, introductions, influence on belief and practices, support in
  hard times, conflict and repair; indirect interaction through place cultures, housing markets and norms.
- **Stochasticity.** Keyed random streams (common random numbers across paired universes); persistent pair
  chemistry and personal lenses from hashed normals.
- **Collectives.** Households, wards and FHE groups, class sections, clubs/teams/institute classes,
  congregations, complexes — the latter three with evolving cultures.
- **Observation.** Event log with causal parents and mechanisms; per-person decompositions of every feeling;
  memories, intentions and coping episodes per person; daily and weekly aggregates; two-weekly per-person
  history; accounting; validation and uncertainty reports.

## 5. Initialization

A synthetic population from survey aggregates (CPTs and Gaussian copulas; small cells suppressed), placed in
real housing; wards, FHE groups, classes, jobs, clubs; a seeded friendship network drawn within shared foci with
triadic closure; couples paired; the serving-missionary pool sized to its flow equilibrium; depressive episodes
at each person's stationary probability; motives, expectations, perceived support and cultures computed from the
initial state. See `ucsim/population/` and `docs/MODEL_ASSUMPTIONS.md`.

## 6. Input data

Four Provo student surveys (aggregates only), Census ACS 2020–24, BYU/UVU enrollment and published class mix,
BYU's contracted-housing list, Utah UGRC, OpenStreetMap, Provo and Orem city GIS, BYU/UVU program catalogs, and
published research for mechanism forms and starting parameters (`docs/DATA_SOURCES.md`).

## 7. Submodels

Every submodel is a registered mechanism with a formula, parameters (value, range, optional distribution),
evidence level and references: `config/mechanisms/01_social.yaml` (encounters, friendship, relationship
history, introductions), `02_romance.yaml`, `03_emotion.yaml` (composed feelings incl. perceived support,
buffering, coping relief, rumination), `04_faith_norms.yaml` (incl. the bounded-confidence alternative),
`05_norms.yaml`, `06_life.yaml` (incl. how long non-students stay), `07_mind.yaml`, `08_coping.yaml`
(appraisal, coping, memory), `09_plans.yaml` (intentions, routines), `10_culture.yaml`. Generated catalog:
`docs/MECHANISMS.md`.

**Evidence levels**: observed, empirical, literature, calibrated, extrapolated, structural (a modeling form
chosen for coherence), hypothetical, speculative. Uncertainty ensembles vary parameters within bands that widen
as evidence weakens (`registry.EVIDENCE_SPREAD`) and draw alternative mechanism forms.
