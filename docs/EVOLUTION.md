# Iteration 6: a world you can trace

**Goal.** A deeper simulation whose connections you can *see*: pick anything (a person, a dinner, a breakup, a
number) and follow what led to it and what it led to, at the level of one life or the whole valley. The interface
becomes a **workbench** of raw tools you lay out yourself instead of pre-built dashboards.

This document is the contract the iteration's pieces share. Each section names the module that owns it, the data it
keeps and the interface other pieces may rely on.

---

## 1. Ledgers: decisions, causes, occasions (`ucsim/engine/ledger.py`, done)

Every simulation has three ledgers next to the event log. Recording never draws random numbers, so it never
changes the world.

* `sim.decisions` (**DecisionLog**): one row per recorded choice, with the largest factor contributions (K = 6)
  on the choice's own scale, hard constraints (stored as ±99 → "couldn't", not "didn't want to"), the probability of
  the outcome that happened, and links from factors to the event, occasion or person they refer to.
  ```python
  did = sim.decisions.record("attend_occasion", day, agents, outcome,            # outcome: index or label
                             {"close_organizer": c1, "tired": c2, ...},           # contributions (coef × value)
                             base=b0, prob=p, occasion=occ, block=b, other=organizer,
                             refs={"close_organizer": ("person", organizer)},
                             constraints={"conflict": mask})
  sim.emit("...", agents, decision=did, causes=[("occasion", occ, 1.0)])
  ```
  Kinds, outcomes and factor words live in `config/decisions/*.yaml` (one file per system: `NN_<system>.yaml`).
  Every factor a system passes must be declared there; tests enforce it.
* `sim.causes` (**CauseLinks**): typed causes of an event beyond its single `cause` parent:
  `event / decision / occasion / person / tie / state / calendar / action / institution / message / trip / place`.
  Pass them through `sim.emit(..., causes=[(kind, refs, weight), ...])`. A `tie` ref is an EdgeStore key.
* `sim.book` (**OccasionBook**): occasions (a planned thing with a day, start minute, duration, place, organizer,
  capacity, series, origin), invitations (who, by whom, channel, thread, sent/seen/decided days, response,
  decision id, attended, arrival minute, ride) and recurring series. An occasion that happened is a **scene**:
  encounters report counts of conversations, first meetings and conflicts (`book.note_scene`) and first meetings
  there record `origin_ctx = CTX_ID["occasion"]`, `origin_place = occasion id` on the new edge.
  Kinds live in `config/occasions/*.yaml` (fields documented in `00_core.yaml`).
* Thinning: full detail for `sim.detail_days` (120); older rows survive only if they led to a salient event, belong
  to an occasion where something happened, or were attended (`Simulation.thin_ledgers`, weekly).

## 2. Time: four blocks, minutes for plans (`ucsim/engine/clock.py`)

`clock.BLOCKS`: morning 8:00–12:30, afternoon 12:30–17:30, evening 17:30–20:15, late evening 20:15–23:30. Systems
resolve behavior per block; occasions, shifts and travel are in minutes. Use `clock.EVENING` instead of `b == 2`,
`clock.slot(wd, b)` for weekly slots (28), `clock.overlap(start, dur, b)` to weight what happens in a block.
Per-block rates and durations calibrated on the old five-hour evening are scaled by block length.

## 3. Occasions, invitations, time windows (`systems/occasions.py`) — option B

* Engine-made occasions replace the old "gathering" draw: hosts decide (decision `host_occasion`), pick a kind and a
  start time, invite through a channel (in person, text, group chat), invitees notice (or not), decide
  (`attend_occasion`, with feasibility: commitments that day, travel time, how late they'd be), and attend in the
  blocks the occasion overlaps. Dates, dances, club socials and calendar events are occasions too.
* Commitments: class sections (block times), shifts with start/end minutes (`P.internal["shift_start"/"shift_end"]`
  per weekday), accepted occasions. `occasions.free_window(i, day)` and `occasions.can_make(i, occ)` answer "could
  they get there, and how late".
* Social actions (user): intervention atoms `{"target_type": "social", "action": ..., ...}` lowered in
  `engine/interventions.py` and compiled by the What-if layer. Actions: `invite`, `series` (recurring dinner, study
  group), `reschedule`, `introduce`, `ride`, `reach_out`, `job_offer`. Two modes: **editor** (arrange the
  opportunity; people still decide) and **as a person** (`"as": person id`: only people they know, only when they're
  free, only what they can afford; a validator explains refusals).
* Probes: `activity.explain_choice(i, b)` returns the free-time option utilities broken into terms for a person now
  (routine choices are not logged; this computes them on demand and says so).

## 4. Travel (`ucsim/geo/travel.py`)

Zones (Provo/Orem neighborhoods, the two campuses, outer zones), zone-to-zone minutes by mode (walk, bike, car incl.
parking, UTA transit from the GTFS feed by weekday class and time of day; no transit on Sundays) precomputed by
`scripts/build_travel.py` into `ucsim/geo/data/travel.npz` with the feed version. Interface:
```python
tm = sim.travel                                    # geo.travel.TravelModel, built once per world
zone = tm.zone_of(lon, lat)                        # vectorized
minutes, mode = tm.trip(people, dest_lon, dest_lat, weekday, minute, ride=None)   # best available mode per person
```
Modes depend on `owns_car`, an offered ride, transit service at that hour, walking distance. Snow (`env["snow_in"]`)
slows walking and driving.

## 5. Calendar and weather (`ucsim/engine/calendar_real.py`, `config/calendar/`)

Real dated items for 2026–27 (BYU/UVU terms, finals, holidays, BYU home football, devotionals/forums, General
Conference, homecoming, move-in, Stadium of Fire…) with a `basis` of `real` (official source URL), `rule` (a
recurring rule applied in other years) or `hypothetical`. Weather: daily Provo observations for a chosen weather year
(public-domain NOAA station data, committed as a small CSV with its retrieval date) mapped onto simulated dates.
Environment flags: `env["calendar_items"]`, `env["snow_in"]`, `env["precip_in"]`, `env["tmax_f"]`, `env["tmin_f"]`,
`env["no_class"]`, `env["finals_BYU"]`… Calendar items that people attend become open occasions with an `audience`.

## 6. Messaging and group chats (`systems/messaging.py`) — wave 2

Threads (apartment, friend groups, clubs, wards, family, direct), structured messages (invite, reply, check-in, news,
plan change), attention (who sees what, when), replies and silence with interpretations (rejection-sensitive people
read silence as being ignored). Who-knows-what about salient events (`KnowledgeStore`), with source and day. No
generated text inside the simulation.

## 7. Institutions (`systems/institutions.py`) — wave 2

Clubs, wards (activities, the bishop's limited interview hours), counseling services (capacity, waitlists,
eligibility), employers (openings by season, summer sales recruiting, schedule flexibility and shift swaps),
complexes (resident events). Each has capacity, budget, hours, eligibility, priorities and response delays; decisions
and adaptations are recorded as institution decisions and events.

## 8. Family and home states (`systems/family.py`) — wave 2

Each person's home state and metro, parents and siblings as lightweight kin records (closeness, contact, support,
expectations, their own life events), trips home (weekends within driving range, Thanksgiving, Christmas, summer)
and family visits to Provo, costs and travel time. A national map shows where people are from and where they are now.

## 9. The LDS Sexuality Survey (aggregate use only)

Added as a fifth survey (1,641 respondents, June 2025). Only aggregates with cells under 10 suppressed enter
`ucsim/priors/survey_priors.json`; free-text answers are never read into the model. Used for the physical-intimacy
boundaries by relationship stage, kissing/NCMO/relationship counts and first-kiss ages (benchmarks, some held out),
sex drive, porn and masturbation patterns with moral incongruence, confession to a bishop, and married couples'
satisfaction and desire differences. These fields stay out of interview dossiers by default.

## 10. Talking to the world (`ucsim/llm/talk/`)

* **Facts first.** Code builds a fact sheet of typed claims (id, subject, predicate, value, evidence refs, kind:
  fact / perception / cause / measurement / quote-of-belief). A model only phrases claims; it returns sentences with
  the claim ids they use.
* **Checking the wording.** Every sentence must cite claims; numbers, names and places must appear in the cited
  claims; causal words ("because", "led to", "so") need a cause claim (a decision factor that carried weight, a
  cause link, or a decomposition share above a threshold); feeling words must match the level band of the cited
  state; a first-person interview may only cite what that person perceives. Failing sentences get one repair round,
  then are dropped with the reason shown. The checker is measured by seeding wrong statements.
* **Ask the world** runs fixed query tools (find people/places by filter, rank by a measure, event counts, most
  affected, why a number changed) and answers with clickable people, places and events.
* **Interviews** are observational (they never change the world). Backends: a local model (recommended for
  interviews: fast and private) or Claude Code / Codex on the user's subscription (recommended for Ask).

## 11. Scales (`ucsim/scales.py`, `web/src/components/Ruler.tsx`)

Every numeric field gets anchors in words along its range (not only the two ends), its units, and the live
population distribution (median, middle half, 10th–90th percentile). A ruler shows a value against those anchors
and the population, everywhere a value appears; a Scales glossary lists them all.

## 12. The workbench (`web/src/bench/`)

The app opens on an empty bench and a shelf of raw tools. You add tools, size and arrange them; the layout is saved.
Every tool reads and writes one **selection**: a set of people (or a filter), a time window, and a focused item (a
`Ref`). Clicking anything (a dot, a name, an event, a bar) offers to *select*, *add to selection* or *trace*.
```ts
type Ref = { kind: 'person'|'event'|'decision'|'occasion'|'tie'|'place'|'var'|'institution'|'thread'|'calendar'; id: string|number; label?: string }
type Selection = { people?: number[]; filter?: Cond[]; time?: [number, number]; item?: Ref }
registerTool({ id, label, icon, hint, component: (props: { sel: Selection; setSel; panel }) => JSX.Element })
```
Tools: Map, People, Life (one person's lanes), Timeline, **Trace** (causes and consequences of the focused item,
laid out on a time axis with a lane per person), **Chains** (population-level chain reactions: which kinds of events
and reasons lead to which), Measure (any field over time, by group, with its ruler), Ties, Place, Occasion, Calendar,
US map, Chats, Institution, Ask, Interview, Compare. The old pages stay reachable under *Classic views*.

## 13. Trace (`ucsim/analysis/trace.py`, `/api/trace*`)

`GET /api/trace?ref=event:123&dir=back|fwd|both&depth=4` → `{nodes, links, lanes, range}`: nodes are events,
decisions, occasions, calendar items, actions and states; links are typed (`caused`, `decided_by`, `factor`,
`attended`, `met_at`, `introduced`, `contributed`), weighted, with words. `GET /api/trace/chains?since&until&filter`
→ population flows between event types and from decision factors to outcomes. `GET /api/decision/{id}`,
`GET /api/occasion/{id}` (the scene: who was invited, who came and why, who met whom), `GET /api/person/{i}/day`.
