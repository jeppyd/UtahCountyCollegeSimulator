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
