# Development log

## Iteration 1

**Decisions with the project owner**
- Survey privacy: aggregates only. Raw survey JSON stays in gitignored `data/raw/`; only smoothed
  statistics with small-cell (<10) suppression are committed.
- Runtime: Python engine + FastAPI + React workstation run locally; a static snapshot is published for sharing.
- Geography: real UGRC layers (network opened for the fetch), OSM geocodes for named complexes.

**Build order**: survey ingestion & priors → registries → geography & housing stock → population synthesis →
engine core (state stores, clock, streams, events, effects) → behavioral systems → interventions & paired
universes → analysis/API → workstation → tests, validation, docs, static export.

**Calibration notes (hand-tuned, recorded for the formal calibration to come)**
- First pass formed relationships far too fast → raised attraction thresholds, lowered DTR probability,
  added fizzle/ghosting and breakup hazards.
- Close friendships collapsed without deliberate contact → added `encounter.friend_contact` and stage hysteresis.
- Loneliness pinned at 0 → contact-need model with a setpoint (0.43) and need ≈16 h/week of close contact.
- Mood/depression too volatile → AR(1) noise and recalibrated onset/remission.
- Financial hardship too common → scholarships, loans, parental help; hardship at most once per 180 days.
- Excess graduations → credits capped at 119 for continuing students; initial engaged couples got wedding dates.
- Activity churn → hysteresis bands on church activity transitions.
- Validation round 1 (one-year run) found: couple dates colliding on the same day and none for married
  couples (dates/month far below the survey for couples) → distinct-day scheduler and weekly date nights;
  temple/scripture practice ignoring activity → `faith.practices`; BYU work hours pooled with UVU →
  per-school rescale; too many missions and some teen grooms → age-past-peak mission penalty and a
  young-man engagement penalty.
- Validation round 2: student work hours ratcheted up all year (financial strain added hours and jobs but
  nothing removed them) → hours fall back toward each person's starting preference once strain eases, and
  students only job-hunt under real strain. New arrivals had never been assigned scholarships → fixed.

**Bugs found by tests**
- Seed network inserted friend ties that duplicated partner ties → duplicate keys broke the sorted-key
  invariant (and a negative Jaccard distance). Fixed by filtering existing keys; invariant now tested.
- Synthesized/rescaled values escaped declared ranges → registry-driven clamp after synthesis and every day.
- `age_at_marriage` defaulted to 0 for never-married people → NaN fill.
- 67 mechanism inputs referenced edge/world variables by bare name, breaking causal-web links → registry
  resolver (`edge.*`, `world.*`, aliases) with free-text inputs moved to `context`.

**UI checks**: every route rendered in headless Chromium with no console errors; the network view
switched to snowball sampling (clusters instead of stars) and the causal web to a concentric layout.

## Iteration 2

**Decisions with the project owner**: main uses are what-if experiments, research questions and following
individual lives; a guided Home; priorities are flows over time and a richer life model; a Simple/Advanced
language switch; more real-world detail (complex names and locations, real majors, physical traits). The
LLM layer stays deferred.

**What changed**
- UX: guided Home ("this week in Provo", vital signs, question gallery, people to follow), Field guide
  (layers, what a person is made of, how relationships and feelings work, time, evidence, glossary),
  task-based navigation, page headers with how-to tips, plain-language event stories, Follow, what-if wizard
  with plain-language results and saved experiments, network tie-type filter.
- Flows: `engine/systems/history.py` snapshots categorical and numeric state every 14 days; Sankey and
  transition tables; `transition` cohort condition; cohort-vs-everyone trajectories.
- Real-world detail: OSM outlines + BYU's official contracted list (address-matched) name ~200 complexes;
  Provo/Orem official neighborhoods; BYU 2025-26 and UVU catalog majors; height/weight/BMI/build/hair/eyes
  (attractiveness now tied to fitness and BMI); the Kyhv Peak overlook uses its current name.
- Life model: clubs, intramural teams and institute classes as weekly contexts (new tie types and
  "where they met" origins).

**Calibration notes**
- Dating couples broke up ~20%/month → breakup base −2.0 → −2.8 (~10%/month).
- Survey ages skew young, so 42% of BYU singles were freshmen → credits re-banded to the published class mix.
- Contracted housing applied to all undergrads → first-year only (BYU policy since 2022); a what-if restores
  the old rule.
- Four-year run: BYU enrollment settled at ~60% of target (half of the re-banded seniors graduated in
  December; intake was fixed) → per-person credit requirement (120-135) and an admissions controller
  (BYU fills to its cap; UVU closes half the gap). Ties to people who left for good are now forgotten.
- Asking-out base −4.0 → −4.5 after clubs added new meeting places (dates per month drifted up).

**Bugs found**: Heritage Court (a south-Provo complex) matched "Heritage Halls" by first word; BYU students
placed in "food retail" jobs at intramural fields; boolean masks over preallocated columns in the groups
system; weddings listed twice in the Home feed.

## Iteration 3

**Decisions with the project owner**: next priority is trustworthy numbers; model non-LDS students in
depth; map playback; make time simple to follow; then a final polish pass and a full project write-up.

**What changed**
- Trust: ACS 2020–24 married share by age/sex for Provo + Orem as the main benchmark; survey rows that are
  composition-biased (by-age married share and by-age dating rates from singles-heavy samples) reclassified
  as diagnostic; `scripts/calibrate.py` (coordinate search over 8 parameters, 2 seeds, common random
  numbers; loss 1.40 → 1.21) with values written back to the rule files; `scripts/stability.py`; in-app
  Model check page reading `ucsim/config/validation.json` and `stability.json`.
- Religious diversity: affiliation, own religiosity, real congregations (UGRC + OSM), service attendance,
  congregation contexts and ties, faith/secular student groups, outsider feeling (loneliness and belonging
  terms), missionary contact, lessons and baptism, ex-members' affiliation, interfaith dating friction, two
  new what-ifs (missionary outreach, interfaith welcome).
- Time: Play/Pause with Watch/Fast pace (server-side pacing), Jump menu, academic-year ribbon (terms,
  breaks, today, what-if split; click to run), map replays ("A day" from per-block frames; "Over months"
  from history snapshots that now include home locations).
- Couple dates per week by stage became calibratable parameters (`romance.couple_time`).
- Four-year check findings and fixes: (1) the married share of students halved over four years; married
  students were mostly seniors (credits had been assigned partly by age), so they graduated out together, and
  every newcomer was single. Fixes: married newcomers now arrive with a spouse and share a home (before, a
  quarter of married people had no spouse in the world), each fall brings new graduate students and older
  transfers (mostly married), programs need 120–145 credits, married students and parents carry lighter
  loads, and engagement was raised (the first calibration had lowered it to fit Census rows for ages 25–34,
  which compare different populations and are now unscored). (2) Starting friend counts (an assumed 9 per
  returning student) were above what the dynamics sustain (~5), so early numbers fell; the start now uses 6.
  (3) BYU enrollment overshot its cap by year four; the intake now counts missionaries and returned
  missionaries due during the school year.

**Bugs found**: playback race between replay modes (clamped); a crashing view could blank the app (error
boundary added); `pkill -f` in a shell matched its own command line (use ps/awk).

## Iteration 4 — the game interface

**Ask**: keep the engine and its depth, but make it feel like a simulation game rather than a research
workstation: Power-BI-level access to every field, presented like a game; Original vs What-if central and
switchable everywhere; a landing page that feels alive; people as lives; research tools as deeper layers.

**What changed**
- Engine/server: the recorder now keeps weekly aggregates of every chartable field (means or category
  shares for seven standard groups, percentiles for everyone), so any field can be followed over time in
  both worlds. New analysis modules `butterfly.py` (every field Original vs What-if with a common effect
  size — Cohen's d for numbers, h for shares — and the share of people whose own value differs; diverged
  lives ranked by one-world-only events and changed life states; one person's two lives with the first
  fork in their road and its cause chain; couples and friendships in only one world; places) and `fields.py`
  (summaries, timelines, person history, the pulse, couples). Endpoints for all of these, plus
  `POST /api/fork/add` (more changes to a running What-if), `after_id` on events (live news), and
  `filter_world` on cohort timelines (follow the same people into the other world).
- Web: new shell (HUD, world navigation, research desk, palette, toasts, recaps, keys), World, Explore,
  What-if (change builder + butterfly view), Relationships, life pages; Map, Places, Events, People and
  Vital signs follow the lens; title and loading screens; the guide gained "How to play".

**Decisions**: Original is blue and What-if orange everywhere (the CVD-safe pair already used for series
1 and 2). In Compare, a filter picks people in the Original and follows the same people into the What-if
(each world's own "top 20%" would compare different people). Group averages are drawn as dots with
uncertainty bars on a zoomed axis rather than bars that hide differences. Two-person events (dates,
engagements, weddings, friendships) are logged once per person; counts shown as pairs divide by two.

**Bugs found**: chart colors given as CSS variables render gray in canvas charts (resolve them first); the
living map's first animation frame could start before its clock (negative time); talking couples had no
start day, so the newest-first list put them first; headlines could be flooded by one event type (now a few
of each type and category).

### Fix: runs stalling the What-if pages

**Report**: after making a What-if change and running a semester, the comparison tabs never loaded, the
app seemed stuck, and the run appeared to stop.

**Cause**: the run thread released and immediately re-took the workspace lock every simulated day, and
Python's lock let it win almost every time, so each page request waited for the entire run (69 s for a
semester at the Standard size, minutes at Full). Those stuck requests also filled the browser's six
connections, so the clock and the Pause button stopped updating. Smaller races made it worse: two quick
clicks could start two runs; Play could give up waiting for a pause after 5 s and leave time stopped; a
split made while time was playing failed to start its run.

**Fix**: a first-come-first-served lock, the clock and Pause served outside the queue, a single job slot
claimed atomically, throttled refreshes during runs, one request per view in flight, request timeouts,
memoized comparisons, visible errors (which world, which day) and a paused-after-N-days recap.
`tests/test_timeline_jobs.py` covers fairness, mid-run reads, double starts, pause and a failing run.
Measured: during a semester run every What-if tab loads in under 1.5 s and the clock keeps moving.


## Iteration 5 — inner lives, place cultures, accounting and uncertainty

**Ask**: push the model toward a richly grounded artificial Provo/Orem whose people have biographies rather than
states — a richer bridge between state and behavior (perception, memory, needs and priorities, expectations,
plans and routines, appraisal and coping, learning), relationships as histories, groups with cultures and
micro → meso → macro → micro loops — while staying inspectable, evidence-labelled, fast at population scale,
demographically coherent over years, and honest about uncertainty. No LLM agents.

**Evaluation before building.** The engine was fast and explainable, but most subsystems mapped state straight
to action; agents were omniscient (asks used the other's true attraction; norms were true means); nothing
experienced changed later expectations; concerns did not compete; hard times had direct consequences; nobody
intended anything. The four-year check showed unexplained drift in major stocks.

**What changed** (design and evidence in `docs/MIND.md`; ODD description in `docs/ODD.md`)
- *Accounting first* (`analysis/accounting.py`, `scripts/accounting.py`): stocks, logged flows, residuals,
  hazards and Little's-law equilibria between same-day checkpoints each year. Findings and fixes:
  (1) the present population grew ~10%/year because graduates who stayed and dropouts never left → an
  exponential stay for non-student young adults, calibrated to hold that stock, with couples moving together;
  (2) the serving-missionary pool started at half its flow equilibrium and doubled over two years → sized to the
  equilibrium; (3) the admissions controller ran while half of single undergrads were flagged away for summer
  and admitted a double BYU class every fall (freshmen tripled, married share diluted from 25% to 11%) → it now
  projects the October census counting summer returners; (4) depressive episodes started at zero and climbed
  for months → each person starts at their stationary probability; (5) Church membership exits are logged
  (`resigned_membership`) so the stock balances.
- *Mind*: motives and drives, learned expectations, academic confidence, perceived support, pluralistic
  ignorance (only doubt is concealed), believed romantic interest per tie; behavior reads them.
- *Memory, appraisal and coping*: structured episodic memory with forgetting and rumination; appraisal in
  `Simulation.emit`; coping episodes with learned strategies that change behavior.
- *Plans and routines*: weekly intentions with a ledger (kept / abandoned / lapsed, with reasons); slot routines.
- *Relationships and cultures*: disclosure, support, hurt and repair, shared experiences, introductions; apartment,
  complex and ward cultures with inertia feeding hosting, reputation, norms, housing sorting and ward warmth.
- *Validation*: pattern rows, held-out tables, courtship timing, a within- vs between-person longitudinal section;
  social events are now a realized count (they were a static survey value scored as "emergent").
- *Uncertainty*: evidence-scaled parameter ensembles with an alternative mechanism form (bounded-confidence faith
  influence), stochastic vs parametric variance, sign robustness, attribution only with enough draws and a multiple-comparison threshold (a 12-draw showcase listed spurious "drivers" before this).
- *Experience*: Inner life tab, place cultures, uncertainty panel, accounting and patterns in Model check, guide
  sections; new What-if presets (open conversations about doubt, peer support, complex game nights, rumination
  skills).

**Bugs found along the way**
- Friend contact and gatherings indexed edges through the weekly adjacency's edge indices, which go stale as
  ties are inserted mid-week (wrong closeness used to pick whom to see) → looked up by key.
- A wedding scheduled while a partner was away silently never happened and the couple stayed engaged
  indefinitely → it moves a week (or the engagement ends if a partner left for good); engaged students no longer
  leave for the summer.
- The seeded starting network had clustering ≈ .01 (friends drawn uniformly within 180-person wards and whole
  majors) → seeding with triadic closure (≈ .14).
- Symmetric "concealment" made devout members understate belief and reversed the sign of pluralistic ignorance.
- Weekly importance updates could leave drives above importance until the next day → drives recomputed.
- The agent-intervention test counted absent people (exposed when the missionary pool grew).

**Performance**: 0.18 → ≈0.23 s per simulated day at ~10k agents, after rewriting edge inserts as an O(n) merge.

**Calibration** (`scripts/calibrate.py`, 14 parameters incl. social events, work hours, support perception and
clustering; holdouts excluded; 2 seeds, 2 rounds, loss 1.109 → 0.988): `romance.kiss.base` −2.6 → −3.23,
`romance.breakup.base` −2.8 → −2.22, `mind.perceived_support.reality` 0.25 → 0.125. A third round was stopped:
round 2 found no improvement and smaller steps were within seed noise.

**Results** (one year at scale 0.15): Census benchmarks 6/6; behavior 34 pass · 11 warn · 2 fail; held-out tables
10 · 2 · 0; all scored rows 50 · 21 · 5 (previous release 50 · 20 · 3 of three fewer rows, with social events
scored by construction). Patterns: perceived vs actual support r = .49; friendship clustering .16 (was ≈ .01 at
the start); intentions carried out .66; liking gap −.06; doubters do not underestimate friends' belief; depressive
episodes 6%. Four-year drift (first → last year): serving missionaries −73 (was +374), depression +1.4 pts (was
+4.3), friends −1.1 (was −1.4), married share of students −6.4 pts (was −8.5), loneliness ±0; active share of
members +6.4 pts (was +4.9). Accounting: people present +2–4%/yr (was +9–13%), missionary and depression stocks
balanced.

**Known gaps carried forward**: married share of enrolled students still settles low over years; BYU work hours
drift up ~1.5 h over the winter (pre-existing); realized social events below the survey for singles; courtship
faster than the surveys' typical 6–8 months; intentions carried out somewhat more often than the ~50% benchmark;
the active share of members creeps up over four years.
