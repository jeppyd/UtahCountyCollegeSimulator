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

## Religious diversity (iteration 3)

- Non-LDS affiliation shares (Catholic, Protestant, other Christian, Muslim, other faith, nonreligious) are
  assumptions informed by Utah-wide surveys: about half of non-LDS young adults nonreligious, Hispanic
  students leaning Catholic, about 35% of non-members raised LDS (mostly nonreligious now).
- Religious non-members attend the nearest real congregation of their tradition (UGRC + OSM); Muslim
  students meet through a student association (no mosque appears in the public layers for the area).
- The religious-outsider feeling, missionary contact and conversion rules are hypothetical; conversion is
  tuned to about 2–3% of non-members per year.
- Same-sex engagement is strongly reduced while either partner is an active member (Church policy).

## The inner life and place cultures (iteration 5)

Details and references: `docs/MIND.md`; every rule is in `config/mechanisms/07_mind.yaml`–`10_culture.yaml`.

- **Eight concerns** (friends, partnership, school/career, money, faith, rest, fun, fitness) are a structural
  choice. Their importance comes from survey-grounded traits and circumstances with assumed weights; it drifts
  weekly (10% toward its target) so priorities follow identity and life stage.
- **Felt fulfilment** reads existing composed feelings (1 − loneliness, 1 − financial stress, …) except fun and
  fitness, which compare recent outings and gym visits with the person's own appetite. Drives = importance ×
  unmet. Drive weights in free-time choice were set so their average pull matches the direct terms they replaced.
- **Expectations** are learned by prediction error from the person's own outcomes; starting values come from
  traits. **Academic confidence** follows class rank of term grades and affects GPA only through effort.
- **Perception**: perceived support blends actual support (weight `reality`) with a stable personal lens and
  trait biases (target correlation with actual ≈ .4); doubters conceal toward the local norm unless they have
  confided; romantic interest is read from noisy signals with projection (35%), a liking gap with strangers and
  male over-perception. Magnitudes are hypothetical; directions follow the literature.
- **Appraisal** scales registered event effects by relevance (importance of the concern the event's category
  touches) and, for harmful effects, by coping potential; both factors average ≈ 1 so population means of event
  effects are preserved.
- **Coping** episodes start when strain stays past tolerance (about a quarter of people are coping at a given
  time, ~3 episodes per person per year at the current thresholds — an assumption, not a measured rate).
  Relief magnitudes are hypothetical, ordered support ≈ active > religious > distraction > withdrawal.
- **Intentions** form weekly when a drive is strong enough; about half are carried out (calibrated to Sheeran
  2002's "about half"). **Routines** strengthen by α = 0.12 per repetition of a weekly slot.
- **Memory** keeps salient events (salience ≥ 0.3) with power-law forgetting (d = 0.5), at most 40 per person.
- **Place cultures** have inertia (apartment 20%/week, complex 8%, ward 10%); their feedbacks (hosting,
  reputation, norms, housing sorting, ward warmth) are hypothetical in strength and can each be switched off by
  setting the parameter to 0.

## Demography and accounting (iteration 5)

- Non-student young adults (graduates who stay, dropouts) leave after an exponential stay with mean 1.6 years,
  chosen so that stock stays near its configured size; real durations are not measured here.
- The serving-missionary pool at the start equals the flow equilibrium of the call hazard (≈10.5k full scale);
  call rates themselves follow ProvoStats mission-service shares (high for women, as the survey reports).
- BYU's admissions controller projects the late-October census, counting students away for the summer.
- Student weddings move to the next break with probability 0.7 (assumption: local practice).
- The starting friendship network re-wires 60% of seeded ties to friends of friends (clustering ≈ .14 at the
  start, rising with dynamics), with slightly more seeded ties so friend counts are unchanged.
