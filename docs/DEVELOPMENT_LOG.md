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
