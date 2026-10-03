# Model assumptions

The model is a laboratory for "what tends to happen, to whom, and why" — not a forecast of any
individual. Every behavioral relationship is a registered mechanism with an evidence label; this file
collects the structural assumptions that are *not* a single mechanism.

## Scope & population

- In scope: BYU daytime students, an in-scope subset of UVU students (≈15k of ≈45k — excluding
  concurrent-enrollment, online-only and distant commuters), non-student young adults, spouses,
  faculty/staff and community members (bishops, employers, family) who structure student life.
- Default scale 0.3 (≈18k agents). Counts in the UI are per simulated agent unless stated as scaled.
- Synthetic people are new draws; names are deterministic hashes of the agent index.

## Synthesis

1. **Skeleton** (sex → religion/LDS → activity → mission → age → origin, politics, orientation, income …)
   from smoothed CPTs with back-off; married share calibrated per school with an odds tilt (survey BYU 12%
   vs institutional ≈25%); UVU activity tilted toward less active (survey over-represents active members).
2. **Survey blocks** (one Gaussian copula per survey, fitted within sex on normal scores) are chained:
   each block is sampled conditional on the bridge variables already known. **Assumption: variables from
   different surveys are conditionally independent given the bridge variables.** Known cross-survey links
   from the literature (e.g. extraversion ↔ social activity) are added explicitly.
3. **Personality**: Big Five from a multivariate normal with published intercorrelations, tilted toward
   survey proxies (extraversion, conscientiousness); additional traits (attachment, rejection
   sensitivity, social anxiety) as correlated normals. All z-scores clipped to ±3.5.
4. **Faith is multidimensional**: belief, certainty, identity, institutional trust, orthodoxy, moral
   autonomy, private devotion, family expectation, perceived norms and attendance are separate variables
   that move under different mechanisms (attendance ≠ belief ≠ identity).
5. **Sexuality and dating** are probabilistic tendencies (orientation, chastity commitment, attraction
   preferences, initiation norms), represented respectfully for aggregate study only.
6. **Structure**: households fill real dwellings (single-sex student apartments, BYU contracted housing,
   married housing, family homes); wards are formed geographically by type (BYU YSA ≈180, YSA ≈150, married
   student ≈170, family ≈220 members); FHE groups within wards; employers from real work sites; an initial
   friendship network seeded by roommates, wards, prior friends, with ages and stages drawn by type.

## Dynamics (high level)

- **Opportunity before compatibility**: people only meet through co-presence (apartment, class section,
  ward, FHE, work, gym, venue, gathering, app). Encounter valence depends on similarity, pair chemistry
  (a symmetric hash), mood and context; familiarity follows ACT-R activation with forgetting.
- **Friendship** advances by accumulated leisure hours and liking (Hall 2019 thresholds) with hysteresis;
  gatherings hosted in apartments create triadic closure; lonely people either approach or withdraw
  depending on traits (Cacioppo).
- **Romance**: directed attraction with idiosyncratic spark; asks follow the men-initiate norm (adjustable);
  dates update attraction by date quality; talking → DTR → dating → engagement → wedding with stage-specific
  hazards (engagement faster for active LDS couples, slower for young men who have not served missions);
  breakups follow Rusbult commitment; couples date ≈1–2×/week, married couples ≈ weekly.
- **Emotion** states are composed of mechanism terms, decaying event effects and AR(1) noise, then
  clipped. Depression has onset/remission hazards. Mood spreads weakly through close ties.
- **Faith**: attendance habits, uncertainty-gated peer influence on belief, spiritual experiences and
  challenges, crisis onset with renew / nuanced / disaffiliate outcomes, activity hysteresis, temple
  recommend; practices (temple, scripture) track current activity.
- **Norms** spread by complex contagion (coffee, alcohol, pickleball, dating apps) with quit hazards.
- **Economy & housing**: budgets from wages, parental support, scholarships, loans; hardship events;
  UrbanSim-style choice among sampled housing alternatives at lease turnover with a friends-in-complex
  term; vacancy-driven rents and construction.
- **Lifecourse**: annual cohorts (Aug 20), returned missionaries through the year, mission calls and
  departures (men 24 / women 18 months, ≈8% early return), graduation and dropout, summer exodus of single
  students, fertility.

## Things deliberately left out (first iteration)

Explicit LLM-driven agent cognition; dorm room assignment details; individual class schedules beyond
section co-presence; detailed transit; non-LDS religious communities beyond affiliation; long-distance
relationships; social media as a network.

## Interpreting results

- Rows labeled *hypothetical* or *extrapolated* drive some outcomes; check the evidence badges on the
  causal path before trusting a scenario result.
- Use paired universes (same seed) or Monte Carlo with paired differences for intervention effects;
  single-run differences include butterfly effects that can be large for individuals and small on average.
- See `VALIDATION.md` for where the model currently disagrees with the surveys.
