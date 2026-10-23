# Handoff: iteration 6 ("a world you can trace")

Several AI agents take turns on this work as each runs out of usage. **This file is the baton.** Read it first, claim
your work, keep it current, and leave it accurate when you stop. The design contract is
[`docs/EVOLUTION.md`](EVOLUTION.md); each piece of work has a spec in [`docs/workstreams/`](workstreams/) and shared
rules in [`docs/workstreams/README.md`](workstreams/README.md).

## Start here (every agent, every session)

1. `git fetch origin && git checkout claude/festive-archimedes-1llpw1 && git pull` — this is the working branch.
   **Never push to or merge into `main`**: every merge into main builds and publishes the owner's Windows release.
2. Read this file, then `docs/workstreams/README.md` (rules — privacy rules are non-negotiable), then
   `docs/EVOLUTION.md` and the spec of the workstream you'll take.
3. **Claim** before coding: put your name/tool, the date and the workstream in *Who is working now* below; commit and
   push that edit. Don't take a workstream someone else holds unless the relay rule below allows it.
4. Work in small steps; **commit and push often** (WIP commits are fine), so running out of usage never strands work.
   Unfinished work goes to a `wip/<workstream>` branch on GitHub (`git push origin HEAD:refs/heads/wip/<workstream>`);
   finished, tested work is merged into the working branch.
   **Relay rule:** if the agent holding a workstream has stopped (its `wip/<workstream>` branch hasn't moved for 2 hours,
   or the owner says it ran out of usage), you may continue it: merge the working branch and `origin/wip/<workstream>`,
   keep pushing to the same `wip/` branch, and write in *Who is working now* and the session log that you took it over.
   The first agent resumes from your pushes the same way.
5. **Before you stop** (or when your usage is getting low): update the *Status board*, append a *Session log* entry
   (what you did, what's half-done and exactly where, what's next, anything surprising), remove your claim, run the
   tests if you can, commit and push. If tests fail, say which and why in the log.

## Who is working now

| Agent | Since (UTC) | Workstream | Notes |
|---|---|---|---|
| Claude Code (cloud session, branch `claude/clever-wright-3fh95g`) | 2026-10-22 | living-map (sync check, real places, floor plans) | Owner-directed: precise places, rooms, 3D buildings, click-to-inspect. Spec coming in docs/workstreams/living-map.md. |

## The goal in one paragraph

A deep, realistic simulation of BYU/UVU social life in Provo–Orem whose connections you can *see*: pick anything (a
person, a dinner, a breakup, a number) and follow what led to it and what it led to, for one life or the whole valley.
The interface becomes a **workbench** of raw tools the owner lays out freely (no pre-built dashboards); every
number shows its scale in words; decisions carry their reasons; occasions (dinners, dates, games) have times, travel
and invitations; the world gains a real Provo calendar, weather, messaging, institutions and families back home.

## Owner decisions (don't relitigate)

- Time and plans: **option B** — planned things have start times and lengths; people check commitments, travel and
  lateness; rides change feasibility; social actions (invite, introduce, ride, study group, recurring dinner,
  reschedule, reach out, job offer) as **world editor** and **as a person** (limited to whom they know, time, money).
- **Full world** (scale 1.0, ~60k people) is the target; optimize along the way.
- **No savable worlds** for now; **no starting cast / "run until"** for now.
- Wanted: calendar + weather; decision records, scenes, Why/Trace; Ask the world + interviews with wording checks
  (the owner has a GPU for a local model and a Claude Pro login — local for interviews, Claude for Ask, choosable);
  messaging/group chats; institutions; family with a broad **US map of home states** (going home for holidays and
  weekends); readable **scales** for every number; a **simpler interface** of raw, assemblable tools.
- **LDS Sexuality Survey**: incorporate (plan in `docs/workstreams/sexuality-survey.md`), **including the five
  dating "dealbreaker" items**; positions, toys, oral-sex endings and birth-control specifics stay out; sensitive
  fields stay out of interviews by default.
- **Only aggregates** (cells ≥ 10) from any survey ever go to GitHub. Raw exports stay in `data/raw/` on the owner's
  machine (and the cloud container). The owner reviews proposals from the survey audit before additions.
- The paused "LLM-invented variables" idea stays paused.

## Status board

| Workstream | State | Where the code is | Next step |
|---|---|---|---|
| Foundation: ledgers (decisions, causes, occasions), 4-block clock, travel interface, contracts, auto-registered routers and workbench tools, CSV survey loader, privacy guard test | **done** | working branch | — |
| [time-occasions](workstreams/time-occasions.md) (option B) | **done, merged** | working branch | open issues below |
| [provenance-trace](workstreams/provenance-trace.md) | **done, merged** | working branch | open issues below |
| [workbench](workstreams/workbench.md) | **done, merged** | working branch | open issues below |
| [scales](workstreams/scales.md) | **done, merged** | working branch | — |
| [sexuality-survey](workstreams/sexuality-survey.md) (+ dealbreakers) | **done, merged** | working branch | open issues below |
| [calendar-weather](workstreams/calendar-weather.md) | **done, merged** | working branch | open issues below |
| [talk](workstreams/talk.md) (Ask + interviews) | **done, merged** | working branch | open issues below |
| [travel](workstreams/travel.md) | **done** | working branch | merged 2026-10-20 (wip/travel) |
| [messaging](workstreams/messaging.md) (wave 2) | **done, merged** | working branch | open issues below |
| [institutions](workstreams/institutions.md) (wave 2) | **done, merged** | working branch | open issues below |
| [family-homes](workstreams/family-homes.md) (wave 2) | **done, merged** | working branch | open issues below |
| Real class schedules (`geo/schedule.py`, academics `_real_sections`) | BYU Fall/Winter, UVU Fall and Spring 2027 **merged** (#28) | branch `claude/project-thread-2pvunp` | BYU Spring/Summer and UVU Summer when published; cross-listed sections share a room |
| Valley home, scenes, make it happen (design review, [DESIGN_REVIEW.md](DESIGN_REVIEW.md)) | **merged (#26, round 2 #29)** | branch `claude/project-thread-q87n1i` | world events as verbs; stagger the remaining Sunday systems; recalibrate |
| [conversations](workstreams/conversations.md): phones, dating apps, listening in, perspectives, developing stories, model wording | **PR open** (not merged) | branch `claude/project-thread-v1aefl` | owner review; first real runs of model wording (only tested with a fake model) |
| Map: paint by any field (owner-directed, 2026-10-23) | **PR open** (not merged) | branch `claude/project-thread-54extr` | owner review |
| Menstrual cycle (owner-directed, 2026-10-23) | in review | branch `claude/project-thread-tlb20b` | owner tuning after play |
| [survey-followups](workstreams/survey-followups.md) | audits designed, interrupted | — | needs the raw survey files in `data/raw/` |
| [integration](workstreams/integration.md) | ongoing | — | after each merge |
| living-map (owner-directed, 2026-10-21) | in progress | `claude/clever-wright-3fh95g` | speed/logs, buildings, bedrooms, 3D map, cards, bedroom-mates done; 2026-10-22: sync check (99.6%+), real places in the backend, Heritage + Wyview + classrooms from BYU plans; next: Wymount/Riviera/LISR plans, elevation, then dashboards |

Time-occasions and provenance-trace are merged, so everything in wave 1 can proceed. Wave 2 (messaging,
institutions, family-homes) can start now too, but coordinate: they touch the same systems as the running builders.

**Known open issues after the merge** (for integration):
- Full world is **2.28 s per simulated day** (was 1.6): encounters 0.83 s (the fourth block), activity 0.36, recorder
  0.34, romance 0.24, occasions 0.23. Ledgers at full scale grow ~20k decisions and ~20k invitations a day; with
  120 days of full detail that is a few hundred MB — reduce `sim.detail_days` or compact before long full-scale runs.
- Cause coverage on the merged code: 99% of events, 95% of salient ones (`scripts/provenance_coverage.py`); gaps:
  `ghosted`, `ncmo`, `premarital_sex` (the sexuality builder's romance functions), `illness`, `app_match`.
- Social events per month now match ProvoStats for singles (≈ 8); engaged students run high (≈ 6.5 vs 4.8); the
  couple-time strengths were fitted to these rows, so they are no longer an independent check. Student loneliness fell
  0.30 → 0.26 as social life rose (no loneliness validation row exists).
- `scripts/validate.py` wasn't re-run end to end (it rewrites docs/VALIDATION.md); do that in integration.
- Placeholders for wave 2: `occasions.deliver(inv_ids, channel)` (messaging), `occasions.shift_flex(people, day)`
  (employer flexibility). No workbench tool for occasions yet (endpoints exist: /api/occasion/{id}, /api/occasions,
  /api/person/{i}/day, /api/person/{i}/choice, /api/act/check, /api/act).
- Builders' worktrees may start from `main`: merge the working branch first.
- Calendar: BYU fall classes really begin Wed Sep 2, 2026 (the world still starts Aug 24, so BYU students are between
  terms for the first nine days; UVU starts Aug 19). Football kickoff times are real except Baylor and Cincinnati (TBA);
  Homecoming week, UVU spring break and Stadium of Fire 2027 are estimates. Conference watching is not an occasion
  (faith.py already skips ward meetings on conference weekends). Only BYU students attend calendar football games
  (no community fans). Weather removed the old random "weather" draw, so run outputs differ from before.
  `travel_home_likely` is in env and on items for the family-homes builder.
- Workbench: Life/Measure history is every two weeks (coarse). `/api/person/{i}/day` lists some class meetings twice (the Day tool de-duplicates). The
  DecisionCard shows "Person 1005" instead of a name for the agent. Bench panels are placed at the first free spot,
  so the order tools are added decides the layout.
- Sexuality survey (validation at scale 0.15, 200 days, seed 1): premarital sex among unmarried **less-active and
  inactive** students runs low (0.27 vs 0.50; 0.41 vs 0.67 — both failed before too; the stock comes from ProvoStats);
  the ladder makes fewer couples start having sex than the old weekly hazard did (142 vs 226 events), while active
  members stay a little high (0.21 vs 0.16). Held-out NCMO/kissing rows: less-active men run high (6.5 vs 2.5 NCMO
  partners; 15 vs 9 kissed) — a ProvoStats-vs-LDS-Sexuality disagreement in the starting values. Breakups +13%
  (dealbreakers end ~9% of them; reaction and reveal rates are hypothetical). Non-members' limits, masturbation and
  dealbreakers are drawn as the survey's inactive members. `scripts/validate.py` has the new rows but wasn't re-run
  end to end (docs/VALIDATION.md unchanged). No workbench/UI work for intimacy yet beyond the generic field views.
- Talk: never run against a real model in this container (no claude CLI or local server here) — everything is tested
  on a scripted stand-in; the owner's first real runs may show prompt/schema issues (the Claude path reuses
  backends.run_claude with a per-feature pack dir in ~/.ucsim/talk_<feature>/; Codex returns `args_json` unpacked to
  `args`, both handled). The checker's 100% catch / 0% false-alarm on tests/data/talk_cases.json is on the set it was
  tuned against (floor in the test: ≥ 90% / ≤ 10%); real answers will be harder — add the misses you see as cases.
  Name checks know only the synthetic name lists and the fact sheet's own names. Ask's lookups are a fixed list;
  "why a number changed" is the current decomposition plus the change since a recent history snapshot.
- Messaging: all magnitudes are hypothetical (no survey covers texting). Friend-group chats come from weekly label
  propagation on the close-friend graph; new groups keep forming (~10 a week per 2,400 people after the first month).
  News tracks ~20 kinds of salient life events (faith crisis, depression and probation are mostly kept private);
  knowledge, acts and old memberships thin after `sim.detail_days`. No family chats yet (family-homes will add kin).
  Invitations sent "to a group chat" only stay group-chat when inviter and invitee share a chat (else they become
  texts). Cost 0.028 s/day at scale 0.15 (≈ 7%); full scale not measured.
- Institutions: capacities, budgets and turnout bases are hypothetical (counseling sessions/week approximate, not
  BYU/UVU figures); they are mechanism parameters, so What-ifs can change them. Not done from the spec: a conditional
  "if attendance falls below X then…" intervention atom, employer hiring as an employer-side decision, splitting
  overcrowded clubs (they cap instead), temple-recommend interviews as their own queue (they're a fixed share of the
  bishop's slots). A swapped shift is dropped from occasions' feasibility, but activity still places the person at
  work during it. Bishop waits are rare at current confession rates. Member-only events (clubs, wards, complexes)
  raised occasions' cost: scale 0.15 is ~0.43 s/day with everything on (was ~0.39 before institutions).
- Family: trip rates, kin hazards and costs are hypothetical, tuned to plausible shares (a given Saturday ~3–4% of
  students are home; Thanksgiving ~60%, Christmas ~74%); people whose family is in Utah County never "travel". While
  on a trip `present` is off and the internal `trip_away` is on — code that loops over present people skips them,
  messaging keeps their chats; the What-if `_scope` (interventions.py) evaluates over present people only (the
  practice-share test now compares people who are here). Home states use ProvoStats' origin-state shares within
  each origin region (no published enrollment-by-state figures were sourced). Not done from the spec: childcare help
  from local grandparents, money from home beyond the existing parental_support, a "trip" chip kind (trips open
  their went_home event). The US map is SVG from us-atlas' Albers states (public-domain Census outlines) in
  web/public/geo/us_states.json.

## Open questions for the owner

(none open — 2026-10-18: the owner approved pushing work-in-progress branches `wip/<workstream>` to GitHub.)

**Note:** the owner merged pull request #9 into `main` on 2026-10-18 (everything up to commit 7853b67: the foundation,
time-occasions and provenance-trace). Agents still never push to or merge into `main`; the owner does that.

## Environment notes

- Raw survey exports (`data/raw/*.csv`, `*.xlsx`) are gitignored; if a workstream needs them and they're missing,
  ask the owner. Never copy them elsewhere or print respondent rows.
- The CSV exports don't reproduce the committed survey aggregates exactly (some multi-select items, College Life
  completes): don't rebuild existing priors; add new sections only (see `docs/workstreams/survey-followups.md`).
- Measured 2026-10-20 (after the speed pass): scale 0.15 ≈ 0.4 s per simulated day, full scale ≈ 1.8 s per day per
  world (one core; a What-if doubles it). Before iteration 6 it was 0.23 / 1.6 s with far fewer systems.
- LLM features use the owner's own logins (Claude Code CLI, Codex CLI, or a local OpenAI-compatible server such as LM
  Studio); see docs/WHATIF_LLM.md. Tests never call a real model.

## Session log (newest first)

### 2026-10-23 (3) — Claude Code (cloud session) — map: paint by any field
- Map tool (`bench/tools/Map.tsx`, new `bench/tools/mapPaint.tsx`): everyone one color until a field is picked; the
  picker now lists every person field (not only `map`-flagged ones) and sits in the map's own bar, so the Valley home
  map has it too (its panel options were hidden under the map). Categories get distinct colors (series colors up to 8,
  evenly spread hues beyond, so no repeats or "other"), with counts; click categories to show only some. Numbers:
  Colors (ramp), Fade (one color, higher solid, lower see-through) or Threshold (at least / at most / between /
  outside, slider plus number, with how many people match); "lower values strongest" flips ramp and fade. Settings
  are remembered per field in the panel options (`opts.paint[field]`).
- `LivingMap` takes rgba from `colorOf` (alpha sets how strongly a dot shows; strong dots draw on top). Occasion pins
  are one color; picking a kind in the Right now list makes its pins stand out and fades the rest.
- Next: owner review; maybe a searchable field picker if the 280-entry dropdown feels long.

### 2026-10-23 (2) — Claude Code (cloud session) — conversation layers: phones, dating apps, listening in
- Spec and audit: `docs/workstreams/conversations.md` (keep/extend/add map, schema, research-engine decisions).
- Engine (`engine/systems/social.py`, system `social`, mechanisms `21_social.yaml`, decisions/events `55_social.yaml`):
  a semantic exchange log (act, topic, intent, what was said or withheld, tie and moods as of then), readings, beliefs
  with evidence and revision (capped, fading), concerns (unanswered, left out, promises, app waits) that later
  choices clarify, repair, keep, miss or let go, and dating-app threads (opener, replies, chat, ask, yes/no, fade,
  ghost) that feed the existing date queue. Wired into occasions (why a no was given, promises, invite penalty),
  messaging (late replies, check-ins, silences read from history, disclosures with selective sharing), encounters
  (captured talk, raising a concern in person) and romance (app matches now go through app threads).
  New randomness only from new stream names (keyed per pair); recording draws none. Run outputs differ from before.
- Dating integrity fixes: a pair's first date happens once (two asks used to queue two "first" dates); an app thread
  stops ("offline") when the pair already went out or has a date coming another way.
- Views (`analysis/phone.py`, `analysis/dialogue.py`, `analysis/stories.py`, `api/routes_phone.py`): inbox, DMs (the
  same lines from both phones), group chats limited to membership with chatter summarized, app threads with the
  self-presented profile, listening in (appends by exchange id), perspectives (both sides and what came of it), and
  developing stories (observational, labelled not representative). Partner texts in scenes now use the same lines.
- Model wording (`llm/talk/dialogue.py`, prompt `talk_dialogue.md`): plan → model → semantic checker → one repair →
  structured wording for what still fails; cache by (lineage, content, schema); bounded deduplicated queue, never
  holds the world lock while waiting. Settings: "Words of texts and conversations" (local recommended, or Off).
- UI: Their phone and Listen in on the focused person, a Developing tab in the valley, a Phone workbench tool, model
  routing in Connect an AI. Checked in light and dark.
- Measured (scale 0.15, 30 days, seed 1; same machine): 0.272 → 0.288 s/day (social 0.009, its capture hook in
  encounters ~0.014); pickle 115.5 → 124.3 MB; 39k exchanges, 8k readings, 1.4k beliefs, 134 app matches → 35 dates
  set on the app + 16 taken offline (old fixed conversion 0.35; now ≈ 0.38 overall). Speed budget 0.88×.
- Tests: `tests/test_conversations.py` (the 14 acceptance checks, fake model only); full suite 334 passed.
  `scripts/sensitivity.py` is opt-in (needs SALib; not installed here, not run).
- Assumptions and limits: every social magnitude is hypothetical; ordinary talk is a sample (1 pair-block in 6, kept
  14 days); the model wording was never run against a real model here; the checker's patterns are English-only and
  conservative (it may reject harmless lines, which then keep the plain wording).

### 2026-10-23 (1) — Claude Code (cloud session) — menstrual cycle
- Owner asked for cycle mechanics (mood/drive depth, nuance to intimacy). New system `engine/systems/cycle.py`
  (runs at the start of each day), variables `config/variables/14_cycle.yaml` (cycle phase/day/length, sensitivity,
  hormonal birth control; sensitive, so interviews leave them out), mechanisms `config/mechanisms/21_cycle.yaml`.
- Effects are small and per-person on purpose (research: modest on average, large for a few): emotion terms
  `mood.cycle`, `fatigue.cycle`, `anxiety.cycle` (emotion.terms adds them when the system exists) and a `cycle`
  factor in the `intimacy_step` decision (fertile window up, period down). Birth control flattens to 0.3. All
  magnitudes hypothetical except the cycle clock (Bull 2019, Wilcox 1995). Per-person values come from the id
  (`hash_uniform`), the only stream is `cycle_jitter`. No events, no explicit content. Run outputs differ from before.
- Not touched: romance, appraisal, messaging (another thread is changing them).

### 2026-10-22 (7) — Claude Code (cloud session) — design review round 2: removals, noise, stagger, verbs, narration
- Removals in one revertible commit (Story/Ripple/Why tools; People page out of the live menus; Overview hero map and
  headlines); the flat map stays as "Neighborhood map" (unique: complex/ward coloring, replays). See DESIGN_REVIEW.md.
- Engine: `sim.my_turn(ids)` gives each person a weekday; `emotion.depression`, `faith.crisis`,
  `romance.couples_week`, `intimacy.couples_week` run daily for those whose day it is (was all Sunday). Depression
  minimum 14 days (`dep_start`). Coping start is a 0.3 daily chance above the threshold. `book.attend(count=)`;
  decliners at home don't bump `n_came`. Run outputs differ from before.
- Story: `time_with_family` folded into `went_home`; `WORK_NAMES` for employers; decisions `ncmo`, `ncmo_app`.
- Actions `ask_out`, `break_up`, `go_home`; `/api/act/undo` (one checkpoint, taken on every change in the Original);
  `/api/scene/narrate` (llm/talk/narrate.py, checked against beats; tests fake the model).
- Tests: 294 passed; web build passes.

### 2026-10-22 (6) — Claude Code (cloud session) — round 3 research: UVU Spring, Homecoming, women's games, complex sizes
- Owner supplied `provo-orem-round3-2026-10-22.zip` (answers to the research prompt in the project files). Unpack it
  outside the repo; copy its `uvu/` folder over `data/external/uvu_campus/` (with the first package's `uvu/` there)
  and run `python -m ucsim.geo.schedule`.
- **UVU Spring 2027 is real** (term 202720, 3,041 sections in 21 buildings). It was collected while registration was
  barely open (9% of seats), so enrollment = seats × Fall's fill for the course (`_fill_spring`), never below what's
  published. Five more buildings hold classes in both terms (Pope Science sits in the Science Building's outline,
  McKay Education, Health Professions, Digital Transformation, Nellesen): Fall went 2,673 → 3,127 sections. McKay
  Education and Nellesen footprints had no name; now named. Published storey counts raise buildings (none needed).
- **Calendar:** BYU's real Homecoming (Oct 6–10): the opening ceremony at 11:00 replaces that Tuesday's devotional;
  new occasion kinds `homecoming_event` (Light the Y, tailgate, s'mores; ~4–6% of BYU students) and
  `homecoming_dance` (Wilk ballroom, `ncmo: true`, ~4%); 44 women's soccer/volleyball/basketball home games
  (`womens_game`, ~2%); UVU spring break Mar 15–21 and Summer May 10 – Aug 13 are real now. Rates hypothetical.
- **Complexes:** The Green, Wolverine Crossing and Axis (UVU's biggest) had **no apartments** in the world: they came
  from survey geocodes with a guessed size and no address points (the county lists one point per building there).
  `config/places/complex_totals.yaml` + `python -m ucsim.geo.complex_totals` give them (and Alpine Village, Liberty
  Square) their published totals as `extra_units`, at the published beds per apartment (`beds_per_unit`, read in
  `population/structure.py`). Run outputs differ from before (new people housed, new occasions, RNG stream).
- **Not used:** LISR (BYU's current page: three shared bedrooms, one bath; the owner's plans say 24 two-bedroom
  apartments in four pods: still unresolved, and LISR isn't in the world), Helaman hall genders (nothing current
  published), Wymount (BYU says 240 apartments replaced, the city 354; which buildings are vacant is unknown),
  Riviera's mix by building, BYU Spring/Summer (not published yet), the one ward listing, county building records.
  Promenade Place, Village on the Parkway and the Village at South Campus aren't named complexes yet.

### 2026-10-22 (5) — Claude Code (cloud session) — design review: the valley home, scenes, make it happen
- Owner asked for a full evaluation as a game and freedom to rebuild. Write-up: [DESIGN_REVIEW.md](DESIGN_REVIEW.md)
  (what works, what's noise, duplicates, engine findings, proposed removals, ranked next steps). Nothing deleted.
- **The valley** is the new home (`web/src/views/valley/`, `analysis/valley.py`, `api/routes_valley.py`): followed
  people with their plans, the living map (Map tool unchanged), and a curated story with reasons on every moment.
- **Scenes** (`analysis/script.py`, `/api/scene/occasion/{id}`, `/api/scene/pair`): occasions, dates and two people's
  history as beats; events are recorded, the words are illustrative (deterministic by hash).
- **Make it happen in your own world**: `/api/act` takes `"world": "original"`; new editor-only `spark` action
  (attraction to someone they know; event `spark`, hypothetical).
- Nav: Valley · Workbench · What-if · More; World page is "Overview"; Logs/Speed under "Under the hood".
- Tests: tests/test_valley.py. Map code untouched (the 3D buildings thread owns it).

### 2026-10-22 (5) — Claude Code (cloud session) — map: clay look by default, dots one color until you color by a field

- Owner: dark mode not liked; wants the "City · architectural clay" concept look, and uniform dots with a color-by
  choice (activity, relationship status, any field). `LivingOpts.look` ('clay' default | 'theme'), `CLAY` colors in
  `web/src/map/LivingMap.tsx` (the map keeps them whatever the app theme; positron street map with a warm ground; one
  clay for every building). Map tool `opts.color` defaults to `'none'` (all dots `--map-dot`); the picker lists
  "what they're doing" and "relationship status" first (`VarPicker` gained `lead`).
- Offered next (owner to choose): sun shadows, OSM trees as clay shapes, horizon haze.

### 2026-10-22 (4) — Claude Code (cloud session) — living map: street map, clay buildings, floors; stale-page fix

- **Why the owner saw only dots:** the installed app showed a cached copy of an old page. The app window
  (pywebview/WebView2, persistent storage in `%LOCALAPPDATA%\ProvoOremSimulator\webview`) cached `index.html` (no
  Cache-Control) and the old hashed bundles stayed on disk after updating. Verified the 0.1.45 release itself
  contains the 3D map. Fix: `_cache_rules` middleware in `ucsim/api/server.py` (page + `/geo/*` no-cache, `/assets/*`
  immutable; test in `tests/test_updater.py`) and `[InstallDelete]` of `web\dist` in `packaging/installer.iss`.
  Workaround for an existing install: delete the `webview` folder once.
- **Living map (`web/src/map/LivingMap.tsx`):** the classic map's OpenFreeMap street map underneath (`streets`
  checkbox, `opts.basemap`, default on except STATIC; its flat buildings dropped; bundled roads when offline; evening/
  night tint as a deck layer); clay buildings (`--map-clay`, `--map-edge` tokens) with edges; a thin line per storey
  on standing buildings at zoom ≥ 15.5 in 3D; busiest named places labelled "name · people inside" when zoomed out;
  an opened building's floor picker lights that slab, and "separate floors" stacks or pulls apart the floors.
- Concept art: 4 of 9 images (dorm night, person card, right now, workbench) were never saved; notes survive.
- Next: hover card for a building; terrain/hillshade; trees/parks like the concept art; classic overlays (neighborhoods,
  venues, complexes/wards) as layers on the living map.

### 2026-10-22 (3) — Claude Code (cloud session) — UVU's real schedule, real game and devotional times
- Owner supplied `provo-orem-student-life-research-2026-10-21.zip` (public-source research: UVU's Fall 2026 class
  schedule, a 2026–27 events list, BYU housing notes for Wymount/Riviera/LISR/Helaman, 15 off-campus complexes with
  operator bed counts, floor-plan images, a field-level evidence ledger). Unpack it outside the repo; copy `uvu/` to
  `data/external/uvu_campus/` and run `python -m ucsim.geo.schedule` to rebuild `geo/data/uvu_schedule.parquet`.
- **UVU students take real Fall sections** (same path as BYU: `real_schedule(term, areas, school)`): 2,673 in-person
  sections in 17 buildings; UVU's 4-digit course numbers are divided by 10 so GE (< 300) and graduate (500+) rules
  carry over; no religion class. UVU buildings were mostly one guessed storey in the building layer; 12 now have the
  floors their rooms are on (room-number estimate, `uvu_floors`). UVU Spring keeps drawn sections. Tests:
  tests/test_uvu_schedule.py (real courses, no clashes, dots in their building on a real floor, no names).
- **Calendar:** real kickoff times for five home football games (Baylor, Cincinnati still TBA); the published Fall
  2026 devotional/forum dates (`published_weekly`, calendar_real; no devotional Nov 24; forums labelled); 32 men's
  basketball home games as occasions (`basketball_game` BYU at the Marriott Center, ~9% of students a game;
  `uvu_basketball_game` UVU at the UCCU Center, ~3%; both hypothetical rates); Christmas performances as items.
  Run outputs differ from before (new occasions).
- **Not used yet (next steps):** off-campus complex bed counts (Glenwood 1,160, Raintree 924, The Green 1,603,
  Wolverine Crossing 1,233, Axis 1,044, Liberty Square 808, Alpine Village 665, Village on the Parkway 432,
  Promenade Place 425; Village at South Campus 940 is a 2023 broker figure) could check or correct complexes.parquet's
  unit counts (Alpine Village has 34 units there; The Green 416). The package's "Promenade Place" is in Orem (875 S
  Geneva Rd), not the Provo "Promenade" in complexes.parquet. Housing notes conflict with the owner's plans on LISR
  (package: three bedrooms, one bath per apartment; plans: 24 two-bedroom apartments) — ask the owner. Riviera's
  apartment ranges give 137 apartments in buildings A–L. Women's basketball, soccer and volleyball games were left
  out (no occasion kinds). Plan images were not committed (operator copyright; repo is public).

### 2026-10-22 (2) — Claude Code (cloud session) — BYU's real class schedule
- Owner supplied `byu-campus-data-01.zip` (BYU's public class schedule, Fall 2026 + Winter 2027, with rooms, times,
  enrollment and 10-minute building occupancy). Unpack it to `data/external/byu_campus/` (ignored) and run
  `python -m ucsim.geo.schedule` to rebuild `geo/data/byu_schedule.parquet` and `byu_occupancy.parquet` (committed,
  no names: instructor names stay out of the repo).
- In Fall and Winter, BYU students now take **real sections** (`academics._real_sections`): number of classes from
  their credits at the schedule's 2.5 credits a seat (at most five), a religion class at the schedule's rate (about
  two in three), general education from 100/200-level courses, the rest from their study area's departments
  (`config/places/byu_departments.yaml`); graduate students 500-level and up. Sections are drawn by enrollment until
  the simulated students fill them at real sizes; clashing classes are swapped or dropped (none left). Each section
  keeps its real days, start and end (`activity.class_times`), room, floor and building; the person card says e.g.
  "A HTG 100 class in KMBL 250". UVU and BYU Spring/Summer keep drawn sections.
- Check (tests/test_class_schedule.py): simulated presence per building and block correlates 0.88 with BYU's
  occupancy numbers (scaled to the simulated students), at about 80% of the volume (the five-class cap, online
  sections). Smith Fieldhouse (activity classes) runs low.
- Next: UVU's schedule if it's public (asked in the treasure-hunt prompt); real Spring/Summer when a package has them.

### 2026-10-22 — Claude Code (cloud session) — dots in sync with the simulation; BYU floor plans
- Owner's priorities: (1) dots exactly where the simulation has people, (2) buildings like the real ones (floor
  plans, counts, shapes); visuals (furniture, textures) later; dashboards after; elevation welcome. Repo is public:
  BYU floor-plan PDFs stay in `data/external/floorplans/` (ignored); only derived summaries are committed.
- **Sync check** (`ucsim/analysis/sync_check.py`, tests/test_sync.py): per kind of place, the share of dots inside
  the building the simulation names, on a floor it has, groups together, none stacked. Was 64% (homes) and 0%
  (classes); now 99.6–99.9% overall, classes 100%.
- **Bugs found:** building centroids were computed in raw degrees (catastrophic cancellation: median 71 m off),
  which broke point-in-building lookups and mismatched ~60% of homes to buildings (`geo/buildings.centroid` fixed,
  homes rebuilt); the fitted box used the principal axis (45° on square houses) — now the true smallest rectangle,
  plus `wings` (L/U-shaped buildings as rectangles: `geo/shapes.py`).
- **Real places in the backend** (`ucsim/engine/places.py`, `config/places/campus.yaml`): every venue, workplace,
  meetinghouse, congregation, complex, group and calendar place is moved into its real building at world start
  (idempotent); classes meet in real teaching buildings, campus hangouts are real buildings (library, Wilk…) and
  their cid is the building (so who you run into depends on where you are), campus gyms are the Richards Building /
  Smith Fieldhouse, the stadium is the grandstand footprint. The map draws only what the backend says
  (`placement.seat_in_buildings`: a seat grid over the real footprint; strangers spread, groups together).
- **Floor plans (owner-supplied):** `ucsim/geo/floorplans.py` → `geo/data/plan_units.parquet` (Heritage: all 605
  apartments, 467 three-bedroom / 137 two-bedroom / 1, 3,356 beds, each placed on its footprint by fitting the
  labels to the outline) and `geo/data/classrooms.parquet` (466 BYU rooms with seat capacities in 33 buildings).
  Sections get the snuggest free room in their study area's buildings (`academics._rooms_for`); the card says "class
  in JKB 1102 (… 285 seats)". Wyview: 426 apartments = the address points; one 3-bedroom a floor (90) per the plans.
  Helaman: plans confirm ~38–40 double rooms a floor, 3 floors (May Hall has no plan). Buildings get the floors
  their apartments/classrooms are on (`homes.raise_floors`). Not yet used: Wymount (scans, no text), Riviera
  (labels partly vector), LISR (not in the world yet: 24 two-bedroom apartments in four pods), off-campus and
  "other" buildings, the stadium seating map, the campus map.
- **Psych 308 fixes (owner approved 1–3):** a lasting loneliness disposition (Boomsma 2005; β 0.2), contact deficit
  0.22→0.15, mood←neuroticism 0.07→0.05; the struggling study more (`academics.study.ability` 2.5), GPA←study
  0.015→0.012; extraversion → asking out (`romance.ask.extraversion` 1.0) and motivation 0.25→0.55. The check now
  attenuates the model's exact r by the survey measures' reliability (`RELIABILITY`, documented). Result: 13 of 16
  associations pass; warns: lonely~friends (−0.30 vs −0.13), religion~life sat, family~life sat. Life satisfaction
  level still low (5.9 vs 7.2) — not changed.
- Release run 42 (merge of PR #21) failed its Windows self-test: places.py imported pyarrow, which the packaged app
  excludes. Fixed (polars' read_parquet_schema); tests/test_packaged_imports.py now builds a world with pyarrow,
  duckdb and pandas blocked. **Runtime code must not import them** (build-time geo scripts may).

### 2026-10-21 (4) — Claude Code (cloud session) — a new survey: Psych 308 (BYU, 2020)
- The owner supplied a BYU class survey (947 students, all during COVID-19) and left inclusion to judgment. Used as
  checks, not inputs: `ucsim/ingest/psych308.py` (aggregates → config/sources/psych308_2020.json),
  `ucsim/analysis/psych308_check.py` (rows in validate.py: holdout levels, 2020 diagnostics, 16 associations),
  tests/test_psych308.py. 60 days at scale 0.15: family background, missions, marriage age, drinking, liberal share,
  singles' dates, sleep, GPA and 9 associations match; mismatches: loneliness far too tightly tied to close friends,
  dates and life satisfaction (and neuroticism to mood) — real students vary more; study hours → GPA too strong
  (+0.30 vs −0.06); extraversion → dates too weak; life satisfaction low (6.1 vs 7.2); conservative share and SSM
  attitudes disagree with ProvoStats/College Life (time and wording differences). Fixes proposed to the owner, not
  made (they touch calibrated mechanisms).
- Owner is downloading BYU floor-plan PDFs (pf.byu.edu, behind BYU login: the owner downloads; never share
  credentials; PDFs stay in data/external/).

### 2026-10-21 (3) — Claude Code (cloud session) — bedroom-mates, snapshot dropped, map polish
- Owner decisions: bedroom-mates matter (done: `housing.bedroom` in config/mechanisms/20_rooms.yaml, hypothetical:
  nightly lights-out talks at 0.6, friction only for clear tidiness/sleep mismatches; 40 days, scale 0.15, two seeds:
  matched bedroom-mates become close friends ~45% more often than apartment-mates, mismatched pairs sour); the
  read-only snapshot is **dropped** (export script and build mode removed; old `STATIC` branches in web code are inert,
  remove in a cleanup); the classic Map page stays as "Flat map (backup)"; polish before shops/errands. Helaman's
  men's/women's halls stay a guess; Wyview south = single, north = family (owner-confirmed). LISR: owner will send
  maps. Owner is collecting BYU floor-plan PDFs (to be uploaded as a zip into data/external/, never committed).
  Remind the owner later about 5–10 off-campus complexes to model exactly.
- Map polish: groups sharing a place point get their own table (no two people on one spot, even at full scale);
  homes without a footprint spread on a grid; person card: why they came (the decision's factors in words, how they
  were invited, travel and lateness), date details (which date, who asked, where they stand), Follow; opened
  buildings shade bedrooms by occupancy and label floors; light by time of day (warm evening, dark night with
  occupied buildings glowing). Full scale (73,667 people): placement 0.02–0.07 s, 1.2 MB per update, card 0.04 s.
- 269 tests pass.

### 2026-10-21 (2) — Claude Code (cloud session) — the living map
- Geography: `scripts/fetch_overture.py` (Overture buildings + places, public S3 through pyarrow) →
  `python -m ucsim.geo.buildings` (footprints, heights, floors, kinds, oriented boxes; web `buildings3d.bin` and
  `building_names.json`) → `python -m ucsim.geo.homes` (`homes.parquet`: every dwelling's building/floor/label;
  `flagship_units.parquet`: the halls' and family housing's units; `place_buildings.parquet`). Raw inputs in
  `data/external/` (gitignored); UGRC must be re-fetched first (`scripts/fetch_geodata.py`).
- Simulation: Units carry building, floor, label and bedrooms (`Units.set_rooms`; flagship layouts, else
  `default_bedrooms`); the halls and Wymount/Wyview are built from the rosters (real buildings and floors) instead
  of random points; Wyview's north half is family housing, the south half single students (estimate); Riviera is
  BYU-owned with its published layouts. `engine/rooms.py`: everyone sleeps in a room (spouse's; a close friend's
  with a free bed; else the emptiest), settled nightly inside housing.daily; no random draws. Activity no longer
  jitters positions (loc_lon/loc_lat are the place's own point) and keeps a compact snapshot per part of the day
  (`activity.snapshot`, `activity.day_snaps` for the last full day). **World outcomes differ from before.**
- `engine/placement.py` (display only): exact spots: beds in rooms, apartments laid along each building's long side,
  seats around a place (pairs, circles, sunflower crowds), classes in real campus buildings.
  `api/routes_placement.py`: `/api/positions/precise` (lock-free, `block=now|0–4`), `/api/building/{b}` (homes,
  bedrooms, who sleeps where, who's inside), `/api/buildings/core`, `/api/now/person/{i}` (analysis/now.py: doing,
  where, with whom and how they know them, the occasion and why, on their mind — model state only),
  `/api/now/occasions`.
- Web: `web/src/map/` (LivingMap, data): 2D/3D, only buildings people use stand (the rest flat: 1.3 → 28 fps in
  software rendering), See inside (x-ray), click a building to open it floor by floor, person cards, occasion pins,
  Right now list, refresh policy (auto: glide through the last day at speeds 1–2, once a day at top speed). The
  bench Map tool uses it; the classic Map page (views/MapView.tsx) does not yet.
- Not done: bedroom-mate effects on ties (waiting on the owner), LISR, shops/errands activity, per-unit offsets for
  homes without a footprint (a few stack), labels render thin in software GL.
- 268 tests pass (5 new in tests/test_living_map.py).

### 2026-10-21 (1) — Claude Code (cloud session) — speed tracker, logs, a messaging slowdown
- **Branch note:** this session works on `claude/clever-wright-3fh95g` (the session's assigned branch). Merging
  `claude/festive-archimedes-1llpw1` brought in commit 7c319cd (survey audit inventory), which **fails
  tests/test_no_raw_survey_data.py** (Qualtrics metadata column names, which the guard treats as raw-export
  signatures, in docs/survey_audit/inventory.md and scripts/survey_inventory.py; I saw no respondent values). It was reverted here
  (e6a0fbb) and left for the owner to decide; fix the guard hits on that branch before merging it anywhere.
- **Speed and logs** (`ucsim/telemetry.py`, `ucsim/api/routes_perf.py`): every simulated day is timed (overall, per
  system, per world, CPU share, memory) and kept (last 4,000 days); slow days say why (Sunday night's weekly updates,
  the end of a month, the two-weekly snapshot, or a system much slower than usual). `/api/perf`, `/api/perf/estimate`
  (per-computer history in `<data home>/speed_history.json` → the world-setup estimate), `/api/logs`,
  `/api/debug-bundle` (zip: versions, settings, timings, logs; no people). The `ucsim` logger goes to an in-memory
  logbook and, in the app or `python -m ucsim.api.server`, `<data home>/logs/ucsim.log` (2 MB × 3). Logged: worlds
  built, runs stopped, slow days, failed or slow (> 3 s) requests, errors with tracebacks. Web: a speed meter in the
  HUD (click: details, Speed tool, Logs, bundle), bench tools **Speed** and **Logs**. The HUD's z-index rose 6 → 12
  (its menus opened under the bench's sticky selection bar).
- **Messaging slowdown fixed**: `KnowledgeStore.add` re-sorted every who-knows-what key on each call (`np.union1d`);
  at scale 0.15 messaging grew 0.010 → 0.273 s/day over 140 days (nearly all of the "days get slower" drift). Now a
  sorted insert; bit-identical (60-day fingerprint matched). Scale 0.15 week means after the fix: 0.37 → 0.40–0.54 s
  (before: 0.40 → 0.75). The weekly Sunday-night day is ~2× a normal day (network/mind/culture weekly + messaging's
  friend-group detection).
- 263 tests pass (5 new in tests/test_telemetry.py).

### 2026-10-20 (7) — Claude Code (cloud session) — What-if on a second core, numba kernels
- **Second core** (`api/parallel.py`): during a run with a What-if, a persistent spawned worker steps the What-if
  while this process steps the Original, in lockstep; the shared lock is released while waiting, so pages answer
  mid-run. Pages read a copy of the What-if (`Workspace.alt` property), refreshed when someone asks for it (at most
  every max(8 s, 5 × hand-over)) and always when the run ends or pauses (divergence measured then). Changes to the
  What-if mid-run call `WS.take_alt()` first (fork/add, applying a plan in add mode, social actions); replacing it
  (`WS.alt = …`) drops the worker's copy. Hand-over only when it pays off (`parallel.worth_it`: days × measured
  What-if day ≥ 2.5 × two hand-overs; long runs only until measured); a world that can't be pickled stays in one
  process. `UCSIM_PARALLEL=0|1|force`. Results are bit-identical to one process (tests/test_parallel.py). Measured in
  this VM (memory first-touch is slow, two processes contend for memory bandwidth): stepping 1.4× faster at full scale,
  1.7× at scale 0.3; hand-overs 4–10 s here (expected well under that on a desktop), so 30-day full-scale runs gained
  ~12% end-to-end here and long "play" runs gain the most.
- Copies and pickles of PersonTable, EdgeStore, EventLog and ledger Tables carry used rows plus headroom
  (`__getstate__`): a full-scale world pickles to 302 MB (was 378), a fork takes ~0.4 s.
- **numba** (optional: `pip install .[fast]`, not in the Windows app yet — llvmlite adds ~50–80 MB): `engine/fast.py`
  label propagation for messaging's weekly friend-group detection (messaging 0.24 → 0.10 s/day at full scale), with a
  NumPy fallback giving identical labels (`UCSIM_NUMBA=0`; tests/test_fast.py). `romance._date_type` vectorized in
  NumPy with the same Gumbel draws (identical picks). Whole runs are bit-identical with and without numba.
- 258 tests pass.

### 2026-10-20 (6) — Claude Code (cloud session) — speed budget and occasions
- **Speed budget**: `ucsim/perf.py` (scale 0.1, seed 3, 2 warm-up + 5 timed days; times divided by a fixed NumPy
  calibration workload so budgets travel between machines), `config/perf_budget.json`, `scripts/perf.py` (print;
  `--update "why"` records), `tests/test_speed_budget.py` (a day ≤ 1.5× budget; each system ≤ 2.5× its own or 10% of
  the day; one retry; `UCSIM_SKIP_SPEED=1` skips). Rule added to docs/workstreams/README.md, AGENTS.md, CLAUDE.md.
- **Occasions**: `_resolve_open` checks every (person, event) pair of an evening in one `_feasible` call and works on
  pairs only (audiences are ~0.1% of people × events); the choice noise is now `Streams.keyed_uniform` keyed by
  (person, event kind·place·start) instead of a P.n × events Gumbel block — paired universes share it pair by pair even
  when their head-counts differ. Attendance at open events is unchanged within noise (3 seeds, 21 days: 5,911 vs
  5,904 visits). Occasions 0.60 → 0.23 s/day at full scale; **full scale 2.87 → 1.79 s/day** over the two passes.
- Budget re-recorded after this. Remaining at full scale (s/day): encounters 0.49, activity 0.30, occasions 0.23,
  messaging 0.23, recorder 0.15, romance 0.13. Not done: a separate process for the What-if world, numba.

### 2026-10-20 (5) — Claude Code (cloud session) — speed pass
- Profiled full scale (73.7k people, one world): 3.15 s/day before → **2.30 s/day** (same 6-day window: 2.87 → 2.30,
  −20%). Changes: `EdgeStore` rows are append-only with a separate sorted key index (`_sorted`, `_perm`), so adding
  ties no longer moves every column of 640k edges (`find`/`upsert` unchanged; `remove` rebuilds the index; row order is
  no longer key order — tests updated); `sim.z` keeps trait z-scores for the day (read-only arrays); `plans._resolve`
  cached per day; the recorder computes every group's means with one matrix product per field (identical to 1e-6).
  Results are deterministic but not bit-identical to before (edge row order changed).
- Where the rest goes (full scale, s/day): occasions 0.72 (≈350 small feasibility/commitment/travel calls a day),
  encounters 0.50, activity 0.32, messaging 0.21 (weekly community detection 0.6 s), recorder 0.15, romance 0.13.
- Options reported to the owner (not done): run the What-if world in its own process (≈2× when comparing), batch the
  per-occasion calls, numba for the remaining Python loops, a per-day speed budget test.

### 2026-10-20 (4) — Claude Code (cloud session) — travel
- `scripts/build_travel.py` → `ucsim/geo/data/travel.npz` (0.15 MB): 73 zones (57 official neighborhoods, BYU and UVU
  campus, 14 outer areas where people live or go) with a ~170 m raster; the UGRC street graph (new
  `fetch_geodata.py roads_net` layer with speed limits and one-ways; Dijkstra from dwelling-weighted zone centroids)
  for walking/biking km and driving minutes off-peak and at the 5:30 pm peak; UTA GTFS (feed 2026 AUG_20261008) on a
  weekday, Saturday and Sunday at 8:00/12:30/17:30/20:30 by a connection scan from six departure times in the hour
  (waiting included), walk ≤ 800 m to stops, ≤ 400 m transfers. UVX runs weekdays and Saturdays, not Sundays; on
  Sundays only routes 850 and 871 serve the area. The feed is not committed (NOTICE.md; UTA's terms URL no longer
  resolves).
- `geo/travel.py` keeps its interface (`trip()` → minutes, mode) and adds `zone_of`, `matrix`, `modes`: a trip keeps
  its own end points (straight km × the zone pair's street detour, the pair's driving minutes per km), plus parking at
  the destination (BYU 9 min, UVU 6, downtown 3); choice-only penalties for parking hassle (BYU 12) and transit waits
  (6; no bus under 1.2 km); 12% of people without a car bike; snow slows every mode. Tuesday 8:00 to campus: BYU 45%
  walk / 30% transit / 22% drive, UVU 75% drive. Occasion trips over 3 weeks: transit 8% (was 0), attendance and
  lateness ~unchanged; ~+0.04 s/day at scale 0.05. Falls back to the straight-line estimate without travel.npz.
- `/api/travel/zones`, `/api/travel/trip`; tests/test_travel.py; 250 tests pass. Fixed two tests whose assumptions the new times broke
  (test_butterfly cohort count now includes people away in the Original; test_social_actions' working student drives).
- Not done: a map layer of zones or isochrones in the web app; rides from friends still use car times.

### 2026-10-20 (3) — Claude Code (cloud session) — storytelling (Story, Why, Ripple)
- Owner asked for a plain-language storytelling layer over the recorded causes (no AI prose; "share of the push").
  New `analysis/story.py` + `api/routes_story.py` (`/api/story/person/{i}`, `/api/story/why`, `/api/story/ripple`),
  read-only over the same ledgers Trace walks:
  - **why**: for a recorded choice, each factor's share of the total push (|term| / Σ|terms|, base rate left out),
    split toward / against what happened, with the chance; for an event with no choice of its own, the weights of its
    recorded causes (tie, place, feeling); a sequence it simply followed (the ask before a date, the occasion) is
    listed as "after", not as a share; someone else's choice (an answer) gives that person's reasons; everything
    pushing the other way reads "against the odds".
  - **story**: chapters by month and turning point (move, relationship, engagement…), one sentence per notable event
    (salience ≥ 0.3) with its top reasons, repeats with the same person folded ("4 times").
  - **ripple**: the forward trace as a tree, each moment under the latest earlier moment it came from; ties reached
    by met_at/introduced become "X and Y met" lines, answers "X said yes"; an event at an occasion also follows the
    occasion (who met there and what that led to).
- Workbench tools Story (people), Why and Ripple (trace) — docs/img/story.png. `_Words.place` names wards with
  `ward_name`. 242 tests pass; web build passes.

### 2026-10-20 (2) — Claude Code (cloud session) — LDS tuning (owner's answers to the LDS audit)
- **Real Provo YSA wards** from the owner's PDFs (Provo YSA Apartment Listing by Ward 2026-27, On Campus Housing
  Assignments 2026-27; PDFs not committed — they list buildings, not people): `scripts/build_ysa_wards.py` geocodes
  the listed addresses on Provo's grid (fit to our complexes, RMSE 43 m) → `geo/data/ysa_wards.json` (569 rows, 168
  wards; 33 rows unplaced, mostly Oak Hills houses). `population/ysa_wards.py`: units near a listed building get its
  ward; at small scales neighbouring wards of one stake merge (≥ 60 members, `REAL_WARD_MIN`); names like
  "YSA Stake 3 · 35th Ward". Other wards get readable generic names ("Family ward 12"). `structure.ward_name()` is
  used everywhere a ward is named; movers join the real ward of their new building (housing._assign_ward). 66
  complexes known only by address now carry their listing name (name_src "ysa_listing").
- **Honor Code**: reports are rarer and quieter (owner: reporting is rare, anonymous, "snitching"), weighted toward
  same-sex romance and alcohol over coffee; ~0.4% of BYU students a year (the published 1.5–3.5% also covers
  cheating, dress etc.). The **endorsement** renews yearly on each student's own date (rates still hypothetical).
- **Bishops** (`institutions.counsel`, mechanism institutions.bishop): after a premarital-sex confession the temple
  recommend is held a few weeks (longer while still sexually active), often the sacrament too; some of those go to
  church less meanwhile. Ongoing issues (porn, masturbation, sex) get roughly monthly follow-ups (max 6). New
  masturbation talks (intimacy.bishop_masturbation; survey: 64% M / 19% F lifetime vs porn 71% / 17%). Events
  recommend_withheld, recommend_restored, bishop_followup, bishop_masturbation_talk.
- **Engagement length**: no survey item covers engagement → wedding (surveys have months dated before engagement,
  median 8, and ideal months to engagement, median 9–10). Active LDS couples now marry after 4–7 months (median ≈
  5½), one in five after ~3 (owner's judgment).
- **Sundays**: members (weighted by attendance) eat out and go out less, spend more time at friends' apartments and
  around the complex (activity.choice.sunday_out / sunday_hangout); a date that lands on Sunday moves to Monday 65% of
  the time (romance.date.sunday_keep).
- **NCMOs** now mostly start on apps (romance.ncmo app_rate/app_base: casual-minded app users match and meet in a
  parked car, an apartment or a quiet spot; event value = place); party/dance base lowered. Total ≈ unchanged
  (~2/3 via apps).
- **Speed buttons**: a speed change while time runs now just changes the pace (`POST /api/pace`, read every day)
  instead of stop-wait-restart; pause shows "pausing after this day…" at once; clicks are queued in order.
- Fixed: a marriage ending during world build left sexual_satisfaction set (romance._end now clears it).
- New `docs/BRAINSTORM_GUIDE.md` (owner request): every kind of building block in plain words plus an idea template.
- 240 tests pass; web build passes.

### 2026-10-20 — Claude Code (cloud session)
- **Campus policies** (owner request): researched BYU's and UVU's published policies and wrote them, with sources and
  versions, to `config/policies/campus.yaml` (CES Honor Code, Honor Code investigation process, amnesty, ecclesiastical
  endorsement, dress and grooming, two-semester housing rule, sex-separated housing, visiting hours; UVU Student Code
  of Conduct (Policy 541), drug-free campus, The Green first-year housing). Each says whether the model uses it.
- New system `engine/systems/honor.py`: weekly reports to the Honor Code Office for the behaviours the model simulates
  (coffee/tea, alcohol, premarital sex, same-sex dating; more often with roommates in contracted housing), the
  office's decision (warning / probation until the end of the next term / suspension / dismissal; `honor_outcome`
  decisions), many quit after a report; suspended students leave BYU (`after_byu`: transfer to UVU or stop). The
  endorsement: renewed each fall (bishops may decline for inactive members), withdrawn at once on resigned membership;
  no endorsement → no enrollment next term (rare exceptions). Variables honor_standing, endorsement, honor_reports;
  events 80_policy; mechanisms 19_policy; world switches honor_enforcement and endorsement_required; presets
  honor_code_not_enforced, honor_code_stricter, no_endorsement_requirement. `/api/policies`; Policies workbench tool
  (docs/img/policies.png). Calibration (scale 0.15, one year): 1.7% of BYU students reported a year (published
  1.5–3.5%); 71% warning, 25% probation, 3% suspension (>95% stay enrolled, as published); ~0.7% of BYU students a year
  lose their endorsement (no published number: hypothetical). Honor adds ~0.001 s/day. 234 tests pass; web build
  passes.
- Not modelled (no simulated behaviour to attach to): honesty, language, dress and grooming, the visiting-hours limit
  (the simulated day ends before midnight), the sexual-misconduct amnesty, UVU conduct cases.

### 2026-10-19 — Claude Code (cloud session)
- **AI setup** (owner request, outside the workstream list): checked the LLM wiring (What-if compiler with Claude Code,
  Codex and LM Studio/Ollama backends; tests pass) and made it easy to connect: a guided **Connect an AI** dialog
  (`web/src/kit/AiSetup.tsx`; top-bar pill, Settings menu, What-if panel) with Choose → Connect → Test. New backends
  `anthropic` (Claude API key, official `anthropic` SDK, refusal fallback, cached system prompt, structured output) and
  `openai_api` (OpenAI API key through the existing OpenAI-compatible loop). Keys are saved only in `~/.ucsim/llm.json`
  and never returned by the API. `POST /api/whatif/llm/test` does a one-word round trip and says what to fix. The old
  inline setup in Ask.tsx is replaced by the dialog. `anthropic` added to dependencies and the PyInstaller spec; package
  data now includes config/**/*.json and *.csv (the weather CSV was missing from pip installs). docs/AI_SETUP_GUIDE.md
  updated. Ask the world and Interviews (talk) also accept the two API-key backends. The real CLIs and API keys can't be exercised in the cloud container (tests use stand-ins). 228 tests pass;
  web build passes.
- Next: sexuality-survey once the owner supplies the xlsx.

### 2026-10-19 (5) — Claude Code (cloud session)
- Built and merged **family-homes**. `engine/systems/family.py`: home state and metro from origin_region and
  ProvoStats' origin-state table (Utah split by county; family_local → Utah County), drive hours (fly beyond 12 h),
  family closeness; kin records (parents, siblings — more in LDS families — and grandparents) with weekly life events
  (sibling weddings, missions and homecomings, new nieces/nephews, a parent's illness, a grandparent's death — which
  replaces lifecourse's random death_in_family) that pull close family home; trips (`trip_home` decisions: weekends
  within 5 h, Thanksgiving and Christmas from the calendar's travel days, family events; closeness, distance, cost,
  homesickness, shifts/exams, married couples alternate families) with a trip ledger; away = present off +
  `trip_away`; time with family on arrival, homesickness after; Friendsgiving for people who stay; family visits to
  Provo (more on game days and graduation). Messaging: family chats (news from home posted there), and people away
  keep their apartment chats. New variables (`12_family.yaml`: home_state, home_drive_hours, family_closeness,
  n_siblings, trips_home), mechanisms 17_family.yaml, occasion friendsgiving, decisions/events 70_family.yaml. API
  routes_family.py (/api/family/person/{i}, /states, /state/{name}); workbench tool USMap.tsx (states shaded by where
  people are from or who is home now; click a state to select its people; a person's family and trips) with
  web/public/geo/us_states.json; guide entry; screenshot docs/img/us-map.png. tests/test_family.py; adjusted three
  tests for trips and shift swaps (test_occasions date test pins a local family and firm shifts; test_whatif_llm
  practice share compares people present; test_intimacy threshold 0.7). 225 tests pass; web build passes.
- Next: travel; survey-followups needs the other surveys' raw CSVs in data/raw/; integration (re-run
  scripts/validate.py end to end, check full-scale speed).

### 2026-10-19 (4) — Claude Code (cloud session)
- Built and merged **institutions**. `engine/systems/institutions.py`: an institution table (clubs/teams/institute
  classes, wards, BYU CAPS and UVU counseling, employers, larger complexes) with capacity, budget, hours, delay and a
  weekly state/history; club socials every 4 weeks and officer adaptation after 3 low-turnout socials (add food /
  change night / recruit; cap when full) as institution decisions + `club_changed_plans` events; ward activities
  (food while the budget lasts) and quarterly service projects; complex resident events; the bishop's interview slots
  (`bishop_gate`, used by romance._confessions and intimacy's porn talks; `waiting_for_bishop`); counseling with
  `seek_counseling` decisions, weekly capacity, crisis-first waitlists, courses of sessions (coping relief), giving
  up; employer shift flexibility (`shift_flex`, used by occasions' commitments and shift_conflict) and seasonal
  openings (economy's job finding). Occasions: open occasions run by a group/ward/complex speak only to its members
  (`_org_members`). Config 16_institutions.yaml, occasions 40_institutions.yaml, decisions/events 60_institutions.yaml,
  role "organization". API routes_institutions.py (/api/institutions, /find, /{id}); workbench tool Institution.tsx
  (chart of demand vs served with waitlist, waiting list, decisions, events run); institution chips open it; guide
  entry; screenshot docs/img/institution.png. tests/test_institutions.py; test_occasions' firm-shift test now pins a
  firm shift. 219 tests pass; web build passes. Institutions cost ~1.4 ms/day at scale 0.04.
- Next: family-homes (and family chats in messaging).

### 2026-10-19 (3) — Claude Code (cloud session)
- Built and merged **messaging** (owner asked for messaging, institutions, family-homes next).
  `engine/systems/messaging.py`: threads (apartment, friend-group via weekly label propagation with matching/splits,
  club, team, ward; direct threads implicit), membership records and events (added/left/muted, group chat started;
  decisions add_to_chat, leave_chat), typed acts (invite, check-in, reply, silence, news, plan change), attention
  (`notice_prob`: phone checks, busy/muted chats, mentions — occasions.deliver now uses it, `assign_threads` routes
  group-chat invitations through a shared chat, `plan_change` on cancellations), check-ins with `reply_message`
  decisions and silences read by rejection sensitivity (felt_ignored: hurt on the tie, lower believed caring;
  assumed_busy), left_out with the occasion as cause plus the host's assumed_not_interested, and `KnowledgeStore`
  (person, event, source, day, channel) with `share_news` decisions, gossip along close ties and chat posts.
  Config 15_messaging.yaml, 50_messaging.yaml (decisions, events); role "unanswered". API routes_messaging.py
  (/api/messaging/person/{i}, thread/{t}, news/{event}); workbench tool Chats.tsx (a person's chats and messages, a
  chat, how news spread); guide entry; screenshot docs/img/chats.png. tests/test_messaging.py. 212 tests pass; web
  build passes.
- Next: institutions, then family-homes (add family chats to messaging there).

### 2026-10-19 (2) — Claude Code (cloud session)
- Built and merged **talk** (Ask the world + Interviews). `ucsim/llm/talk/`: `facts.py` (typed claims; the interview
  dossier — feelings, perceptions, closest ties as they see them, memories read without rehearsing, intentions,
  coping, the top reason for their own recent decisions — with sensitive fields and events left out by default;
  `view_vs_truth`; eight query tools: find_people, rank_places, event_counts, explain_feeling, why_changed,
  most_affected, person, trace), `check.py` (citations, numbers incl. spelled-out and percentages with hedges, names
  incl. invented synthetic names, causal wording incl. causal "since", feeling words → field value ranges and the
  person they're about, interview hidden-state rule), `llm.py` (per-feature backend in ~/.ucsim/talk.json: auto =
  local model for interviews when loaded; FAKE hook for tests), `jobs.py` (start/poll/cancel; check → one repair →
  drop with reasons; interview safety screen: self-harm methods, clinical advice, theology), `ask.py`,
  `interview.py` (also in the What-if world). Prompts `llm/prompts/talk_ask.md`, `talk_interview.md`. API
  `routes_talk.py` (/api/talk/status, settings, ask, ask/{job}, ask/{job}/cancel, interview/{i}, differs/{i}; the
  What-if local-only guard). Web: `kit/Answer.tsx` (+ useTalkJob, talk.css), workbench tools `Ask.tsx`,
  `Interview.tsx` (backend picker, "view vs. truth", What-if toggle), talkApi in api.ts, a Guide entry, a section in
  docs/WHATIF_LLM.md, screenshot docs/img/talk-ask-interview.png (scripted stand-in model).
  `tests/data/talk_cases.json` (73 seeded statements: 32 true, 41 false across wrong number/person/cause/intensity,
  hidden-state leak, uncited); `tests/test_talk.py` (evaluation floor, unit tests, Ask and Interview end to end through
  the API on a fake backend, interviews change nothing, sensitive fields out). 204 tests pass; web build passes.
- Next: travel, messaging, institutions, family-homes, survey-followups (needs the other surveys' raw CSVs),
  integration.

### 2026-10-19 — Claude Code (cloud session)
- The owner supplied the LDS Sexuality Survey (`data/raw/lds-sexuality_2025-06-29.xlsx`, gitignored), so
  **sexuality-survey** went before talk; built and merged it. `ucsim/ingest/sexuality.py` (`python -m
  ucsim.ingest.sexuality`, openpyxl in the new `ingest` extra) reads only the columns in
  `survey_spec.SEXUALITY_SPEC` (no free text, no birth control/positions/toys/oral endings, extra sheets never
  opened), keeps ages 18–35 (1,411 respondents), pools answer levels under 10 people, and writes only
  `blocks.lds_sexuality`, `targets.lds_sex_*`, `tables.lds_sex_*`, `meta.sources["lds-sexuality"]` (pure additions to
  survey_priors.json). New person variables (`config/variables/11_intimacy.yaml`, all `flags: [sensitive]`, as are
  porn_use, n_sex_partners, premarital_sex_current, n_ncmo, ever_cheated(_on), porn_incongruence): sex_drive,
  ok_stage_touch/underclothes/naked/sex, intimacy_level, sex_ed_home, sexual_shame, masturbation,
  talked_to_bishop_sexual, the five db_* dealbreakers, sexual_satisfaction, desire_gap. synth.py draws them from
  their own stream (`[seed, 7002]`, nobody else's draws changed); members' porn_use now comes from the survey.
  `engine/systems/intimacy.py` (weekly, after romance): the ladder with decisions `intimacy_step`, crossed lines
  (guilt, sometimes a bishop, conflict when one-sided), sex via `romance._sex(via_ladder=True)` (the old weekly
  hazard is bypassed while intimacy runs), married sex life → relationship satisfaction, porn talks with a bishop,
  dealbreakers revealed through the tie (decision `dealbreaker_reaction`, ending via `romance._end`). Romance edits:
  `_sex` (via_ladder, decision, returns events) and `_ncmo` (own limits lower NCMOs). Mechanisms
  `14_intimacy.yaml`, events/decisions `40_intimacy.yaml`, roles dealbreaker/brought_to_light/crossed, scales anchors.
  Validation rows in `scripts/validate.py` (SEX_CHECKS); before/after at 0.15 × 200 days: shared rows 62/27/14 →
  67/26/10 (pass/warn/fail), new rows 17/7/7; 0.50 → 0.53 s/day (intimacy 1 ms/day). Docs: DATA_SOURCES.md
  subsection, data/README.md. Tests: test_sexuality_priors.py, test_intimacy.py. 197 tests pass; web build passes.
- Next: talk (exclude sensitive fields), then travel, messaging, institutions, family-homes, survey-followups
  (the other surveys' raw CSVs aren't in this container), integration.

### 2026-10-18 (late night, 4) — Claude Code (cloud session)
- Built and merged **calendar-weather**: `config/calendar/2026_27.yaml` (BYU and UVU 2026–27 terms and finals,
  holidays, breaks, BYU home football, General Conference, Homecoming, Stadium of Fire…, each with basis real / rule /
  hypothetical and source URLs), `config/calendar/rules.yaml` (later years; reproduces UVU's published Summer 2028
  start; weekly devotionals), `engine/calendar_real.py`; core.Calendar now delegates (same method names) and gains
  in_finals, no_class, items_on. Weather: `config/sources/weather_provo_daily.csv` (+ .json) from NOAA GHCN-Daily
  station PROVO BYU 2015-08 → 2026-07 (the NCEI data-service API and Open-Meteo were unavailable; the station's
  static access file worked), `engine/weather.py` (weather year: latest by default, world.yaml `weather.year`,
  UCSIM_WEATHER_YEAR or env['weather_year']). Environment: tmax_f, tmin_f, precip_in, snow_in, snow_depth_in,
  weather_label, weather_penalty, calendar_items, no_class(_BYU/_UVU), finals_BYU/UVU; exam_week now uses the real
  finals. Mechanisms `13_weather.yaml`; occasions' attendance gains a `weather` factor. Calendar occasions
  (`config/occasions/30_calendar.yaml`: football_game, devotional, stadium_of_fire) are planned by
  Environment._calendar_occasions; ~24% of BYU students go to a home game. API routes_calendar.py; /api/calendar uses
  the real terms; Calendar workbench tool (docs/img/calendar-strip.png). Fixed kit/Bits useWidth (it measured nothing
  when the element appeared after loading). 188 tests pass; web build passes.
- Next: sexuality-survey (the owner will supply the raw xlsx in `data/raw/`), then talk, travel, messaging,
  institutions, family-homes, survey-followups, integration.

### 2026-10-18 (late night, 3) — Claude Code (cloud session)
- Finished **scales** (continued `wip/scales`, relay rule) and merged it: the backend (anchors, units, how-measured for
  every numeric person and tie field; /api/scales, /api/scales/value) was already done; added web/src/kit/scales.ts
  (scale types, axis, percentiles, batched cached distributions), kit/Ruler.tsx (full and inline rulers), kit/Val.tsx
  (`<Val v value>` and the ScaleCard popover), rulers on the person page (meters, at-a-glance, every field table),
  inner life (drives, rumination, routine), Explore's field pane (the group's ruler) and the Measure tool, and the
  Scales glossary workbench tool. VarSpec.scale's type now lists anchors/unit/how. Screenshots docs/img/scales-*.png.
  180 tests pass; web build passes.
- Next: calendar-weather, then sexuality-survey (needs the raw xlsx in `data/raw/`), talk, travel, messaging,
  institutions, family-homes, survey-followups, integration.

### 2026-10-18 (late night, 2) — Claude Code (cloud session)
- Took over and finished **workbench** (relay rule) and merged it: new tools Events, Life, Timeline, Measure, Ties,
  Place, Compare, Occasion, Day and Act (web/src/bench/tools/), `useWidth` in kit/Bits.tsx, a "The workbench" section
  in the guide, screenshots in docs/img/bench-*.png. `/api/cohort_timeline` takes `people` (hand-picked selection).
  Fixed: routes_occasions/routes_act imported `WS` from `.server`, which under `python -m ucsim.api.server` is a
  second, empty module (every occasion/day/act call said "universe 'base' not available"); they now use
  routes_trace._server. Map tool was blank (maplibre's CSS made its container 0 px tall); fixed. 173 tests pass; web
  build passes.
- Next: scales (continue `wip/scales`), then calendar-weather and the rest in the order below.

### 2026-10-18 (late night) — Claude Code (cloud session)
- Paused at the owner's request to save usage: multi-agent runs were too expensive. Two builders had pushed progress
  before the stop: `wip/workbench` and `wip/scales` (contents in the status board). Nothing else is in flight.
- **How to continue (cheaply):** one agent, one workstream at a time, in this order: workbench (continue
  `wip/workbench`) → scales (continue `wip/scales`) → calendar-weather → sexuality-survey (needs the raw xlsx in
  `data/raw/`) → talk → travel → messaging → institutions → family-homes → survey-followups (needs the raw CSVs) →
  integration. When a workstream is done: full tests + web build, merge it into the working branch, push, update this
  file.

### 2026-10-18 (night) — Claude Code (cloud session)
- The six remaining wave-1 builders were stopped by usage limits within minutes (no progress); restarted at 22:27 UTC
  with work-in-progress pushed to `wip/<workstream>` branches (owner approved). Added the relay rule above.

### 2026-10-18 (evening) — Claude Code (cloud session)
- Merged **time-occasions** (four-block day; shifts with clock times; occasions with hosting, invitations, noticing,
  feasibility with travel and lateness, attendance, no-shows, walk-ins; dates and dances as occasions; weekly
  traditions that pass to housemates or end; social actions as editor and as a person; explain_choice; endpoints) and
  **provenance-trace** (decisions with factors across romance, friendship, plans, coping, economy, housing, faith,
  life course, academics; typed causes; tie "where their time together accrued"; scene counts; the trace engine and
  chains; Trace and Chains tools; DecisionCard). One trivial conflict (faith.py imports). 168 tests pass; web build
  passes; coverage 99%; full scale 2.28 s/day.
- Launched the remaining six wave-1 builders.

### 2026-10-18 — Claude Code (cloud session)
- Assessed the project and proposed the iteration-6 plan (owner chose the directions above).
- Built the foundation on the working branch: `ucsim/engine/ledger.py` (DecisionLog, CauseLinks, OccasionBook with
  stable ids and thinning), `ucsim/engine/clock.py` (four blocks), `ucsim/geo/travel.py` (interface + straight-line
  fallback), registry loading of `config/decisions|occasions|events/*.yaml`, `sim.emit(decision=, causes=)`,
  auto-included `ucsim/api/routes_*.py`, the workbench registry/selection (`web/src/bench/`), the Qualtrics CSV survey
  loader, `tests/test_no_raw_survey_data.py`, and `docs/EVOLUTION.md`.
- Ran eight parallel builders; usage limits interrupted them three times. Progress kept for time-occasions and
  provenance-trace (on wip branches); the other six had not started meaningfully. The last few uncommitted edits of
  those two builders were lost once (they were told to redo anything half-done).
- Next: finish and merge those two, then run scales, travel and sexuality-survey alongside workbench, calendar-weather
  and talk; then wave 2 (messaging, institutions, family-homes), the survey audit and integration.
