# Mechanism registry

Generated from `ucsim/config/mechanisms/*.yaml` and `events.yaml` by `scripts/gen_catalogs.py` — do not edit by hand.

185 mechanisms. Evidence: **observed** 0, **empirical** 18, **literature** 68, **calibrated** 33, **extrapolated** 0, **structural** 7, **hypothetical** 45, **speculative** 14.

Every parameter can be overridden per run (`ParamSet`), targeted by an intervention (`target_type: param`) or swept.

## Evidence levels

- **observed** — Directly observed in relevant data
- **empirical** — Empirically estimated from data (survey copula / tables)
- **literature** — Supported by established theory or replicated research
- **calibrated** — Chosen to reproduce observed population patterns
- **extrapolated** — Applied from another population
- **structural** — A plausible structural assumption: a modeling form chosen for coherence, not a measured effect
- **hypothetical** — Reasonable but insufficiently evidenced
- **speculative** — Frontier: exploratory mechanism with weak or contested evidence

## coping

### `appraisal.relevance` — Events matter more when they touch what you care about

*Evidence: literature · timescale: daily · delay: none*

- **Target**: `mood`, `stress`, `loneliness`, `self_esteem`, `belonging`
- **Inputs**: `cares_connection`, `cares_partnership`, `cares_achievement`, `cares_security`, `cares_faith`, `cares_health`
- **Form**: every emotional effect of an event × ((0.5 + cares_m)/(0.5 + mean cares_m))^strength, m = the concern the event touches (its category or `motive`)
- **Parameters**: `strength` = 1.0 (range 0.0–1.5)
- **Notes**: The same rejection hurts more for someone who badly wants a partner; a failed exam hits harder for someone who cares about grades.
- *Ref*: Lazarus & Folkman (1984): primary appraisal — goal relevance
- *Ref*: Scherer (2001): relevance check in component process appraisal

### `appraisal.coping_potential` — Feeling able to cope softens what hurts

*Evidence: literature · timescale: daily · delay: none*

- **Target**: `mood`, `stress`, `loneliness`, `self_esteem`
- **Inputs**: `perceived_support`, `self_esteem`, `stress`
- **Form**: harmful effects × exp(−strength·(coping potential − 0.55)); coping potential = 0.5·perceived support + 0.3·self-esteem + 0.2·(1 − stress)
- **Parameters**: `strength` = 1.0 (range 0.0–2.0)
- *Ref*: Lazarus & Folkman (1984): secondary appraisal — resources to cope
- *Ref*: Cohen & Wills (1985): buffering

### `coping.need` — When strain calls for coping

*Evidence: structural · timescale: daily · delay: none*

- **Target**: `coping_need`
- **Inputs**: `stress`, `mood`, `loneliness`, `anxiety`
- **Form**: need = clip((0.6·(stress − θs)⁺ + 0.8·(θm − mood)⁺ + 0.5·(loneliness − θl)⁺ + 0.4·(anxiety − 0.55)⁺)/0.25, 0, 1)
- **Parameters**: `stress` = 0.55 (range 0.45–0.65); `mood` = 0.4 (range 0.33–0.47); `loneliness` = 0.58 (range 0.48–0.68)

### `coping.episode` — Coping episodes start and end

*Evidence: structural · timescale: daily · delay: none*

- **Target**: `coping_strategy`
- **Inputs**: `coping_need`
- **Form**: start when the 2-day EWMA of need > on; end after 3 days below off, or after 35 days unresolved
- **Parameters**: `on` = 0.4 (range 0.25–0.55); `off` = 0.15 (range 0.05–0.25)

### `coping.choice` — Choosing how to cope

*Evidence: literature · timescale: daily · delay: none*

- **Target**: `coping_strategy`
- **Inputs**: `extraversion`, `agreeableness`, `attachment_avoidance`, `perceived_support`, `n_close_friends`, `conscientiousness`, `self_eff_academic`, `cares_faith`, `faith_belief`, `religious_identity`, `own_religiosity`, `sensation_seeking`, `cares_health`, `cares_fun`, `neuroticism`, `social_anxiety`, `expect_social`
- **Form**: Gumbel-max over strategies: support (E, A, low avoidance, perceived support; needs someone close), active (C, controllable stressor, confidence), religious (faith × belief), distraction (sensation seeking, fitness, fun), withdrawal (N, social anxiety, avoidance, low expected warmth); + learned × what has worked before
- **Parameters**: `learned` = 1.5 (range 0.5–3.0); `withdrawal_base` = -0.9 (range -1.8–0.0); `support_base` = 0.3 (range -0.5–1.0)
- *Ref*: Skinner, Edge, Altman & Sherwood (2003): families of coping
- *Ref*: Carver, Scheier & Weintraub (1989): COPE
- *Ref*: Connor-Smith & Flachsbart (2007): personality and coping (meta-analysis)

### `coping.relief` — Relief each strategy brings

*Evidence: hypothetical · timescale: daily · delay: none*

- **Target**: `coping_relief`
- **Inputs**: `coping_strategy`, `support_actual`, `academic_pressure`, `financial_stress`, `faith_belief`, `own_religiosity`
- **Form**: daily relief: support = s·(0.2 + 0.8·actual support)·(1 if they connected today else 0.3); active = a·progress on the stressor; religious = r·belief; distraction = d·(did something); withdrawal = w; coping_relief = EWMA (half-life ≈4 days)
- **Parameters**: `scale` = 1.0 (range 0.5–1.5); `support` = 0.6 (range 0.3–0.9); `active` = 0.55 (range 0.3–0.8); `religious` = 0.5 (range 0.2–0.8); `distraction` = 0.4 (range 0.2–0.6); `withdrawal` = 0.15 (range 0.05–0.3)
- **Notes**: Ranked support ≈ active > religious > distraction > withdrawal on immediate relief, but support pays off only if supportive people are actually there.
- *Ref*: Ano & Vasconcelles (2005): positive religious coping ↔ better adjustment (49 studies)
- *Ref*: Penley, Tomaka & Wiebe (2002): problem-focused vs avoidant coping and health outcomes (meta-analysis)
- *Ref*: Holahan & Moos (1987): avoidance coping predicts later distress

### `coping.learning` — Learning what works

*Evidence: hypothetical · timescale: daily · delay: none*

- **Target**: `coping_strategy`
- **Inputs**: `coping_need`, `coping_relief`
- **Form**: at the end of an episode: V_strategy ← V + α·(outcome − V), outcome = 0.5 + 0.8·(need at start − need now) + 0.6·(relief − 0.15)
- **Parameters**: `alpha` = 0.3 (range 0.1–0.5)
- **Notes**: An isolated person who seeks support and finds no one learns to stop trying — the loneliness loop emerges from experience.
- *Ref*: Rescorla & Wagner (1972)

### `coping.behavior` — Coping changes what people do

*Evidence: hypothetical · timescale: daily · delay: none*

- **Target**: `activity_now`, `study_hours`, `class_attendance`, `attend_rate`, `work_hours`
- **Inputs**: `coping_strategy`
- **Form**: support: +visiting friends, ×(1 + 1.2k) reaching out; withdrawal: +home, −visits, −outings, ÷(1 + 0.8k) reaching out, −0.6 class-attendance logit, −2 h study; distraction: +gym, outdoors, venues; active: +campus and +3 h study (school strain), job search and hours (money strain); religious: +0.6 church-attendance logit
- **Parameters**: `strength` = 1.0 (range 0.3–1.8)

### `memory.forgetting` — Memories fade (unless rehearsed)

*Evidence: literature · timescale: daily · delay: none*

- **Target**: `n_memories`
- **Inputs**: `rumination`
- **Form**: strength = importance·(1 + 0.5·rehearsals)·(1 + age/7 days)^−decay; weekly prune below 0.07, at most 40 per person; core memories (importance ≥ 0.8) kept
- **Parameters**: `decay` = 0.5 (range 0.3–0.8)
- *Ref*: Wixted & Ebbesen (1991): power-law forgetting
- *Ref*: Anderson & Schooler (1991): ACT-R base-level activation
- *Ref*: Park et al. (2023): Generative Agents — recency × importance × relevance retrieval

### `memory.tone` — How the remembered past colors life judgments

*Evidence: literature · timescale: daily · delay: none*

- **Target**: `life_satisfaction`
- **Inputs**: `memory_tone`
- **Form**: life satisfaction += 0.6·memory tone (monthly composite)
- *Ref*: Schwarz & Strack (1999): life-satisfaction judgments are built from what comes to mind
- *Ref*: Kahneman (1999): the remembering self

## culture

### `culture.inertia` — Place cultures form from residents and outlast them

*Evidence: structural · timescale: daily · delay: none*

- **Target**: `home_social_culture`, `home_faith_culture`
- **Inputs**: `attend_rate`, `service_attend`, `roommate_cohesion`, `coffee`, `alcohol`, `rel_status`, `ward_belonging`, `ward_activity_rate`; other inputs: hosted gathering counts, visits
- **Form**: weekly: culture ← (1 − r)·culture + r·(what residents did this week); apartment sociability = log(1 + 3·gatherings + visits)/√residents; complex = mean of its apartments plus observance, coffee/alcohol share, married share; ward = mean belonging and activity; empty apartments keep their reputation
- **Parameters**: `unit` = 0.2 (range 0.1–0.4); `complex` = 0.08 (range 0.03–0.2); `ward` = 0.1 (range 0.03–0.25)
- *Ref*: Schneider (1987): the people make the place — attraction–selection–attrition
- *Ref*: Harrison & Carroll (1991): cultural transmission in organizations with turnover

### `culture.feedback` — Cultures shape the people who live in them

*Evidence: hypothetical · timescale: daily · delay: none*

- **Target**: `activity_now`, `perceived_norm`, `unit_id`, `ward_belonging`
- **Inputs**: `home_social_culture`, `home_faith_culture`
- **Form**: hosting × exp(h·apartment sociability z); invitation acceptance and hanging out around the complex + r·complex sociability z; attendance norm = (1 − n)·(friends + ward) + n·complex observance; housing choice + s·fit (−2·|observance gap| − 0.4·|sociability z − extraversion z|); ward belonging + w·(ward warmth − mean)
- **Parameters**: `hosting` = 0.3 (range 0.0–0.6); `reputation` = 0.25 (range 0.0–0.5); `norm` = 0.2 (range 0.0–0.4); `sorting` = 1.0 (range 0.0–2.0); `ward_warmth` = 2.0 (range 0.0–4.0)
- **Notes**: Closes the micro–meso–macro loop: residents make a complex social or devout, the reputation changes who visits and who moves in, newcomers adopt its norms, and the culture evolves again. Strengths are hypothetical; set any to 0 to switch that feedback off and compare.
- *Ref*: Cialdini, Reno & Kallgren (1990): descriptive norms of a setting guide behavior
- *Ref*: Selection and influence in residential settings (e.g. Kandel 1978; Steglich, Snijders & Pearson 2010)

## emotion

### `fatigue.setpoint` — Fatigue baseline

*Evidence: calibrated · timescale: daily · delay: none*

- **Target**: `fatigue`
- **Inputs**: —
- **Form**: 0.22

### `fatigue.sleep` — Sleep deficit → fatigue

*Evidence: literature · timescale: daily · delay: none*

- **Target**: `fatigue`
- **Inputs**: `sleep_hours`
- **Form**: β·clip(7.5 − sleep, 0, 4)/3
- **Parameters**: `beta` = 0.25 (range 0.1–0.4)
- *Ref*: Sleep restriction and daytime fatigue (well established)

### `fatigue.workload` — Overload (work + study + class) → fatigue

*Evidence: hypothetical · timescale: daily · delay: none*

- **Target**: `fatigue`
- **Inputs**: `work_hours`, `study_hours`, `credits_term`
- **Form**: β·clip((work + study + 2.5·credits − 45)/40, 0, 1)
- **Parameters**: `beta` = 0.35 (range 0.15–0.5)

### `fatigue.children` — Young children → fatigue

*Evidence: literature · timescale: daily · delay: none*

- **Target**: `fatigue`
- **Inputs**: `children`
- **Form**: 0.08·min(children,3)/3

### `financial_stress.setpoint` — Financial stress baseline

*Evidence: calibrated · timescale: daily · delay: none*

- **Target**: `financial_stress`
- **Inputs**: —
- **Form**: 0.05

### `financial_stress.buffer` — Savings buffer → financial stress (non-linear)

*Evidence: literature · timescale: daily · delay: none*

- **Target**: `financial_stress`
- **Inputs**: `savings`, `monthly_income`, `rent`
- **Form**: β·logistic((1.5 − savings/monthly expenses)/0.6) — manageable with a buffer, steep below ~1 month
- **Parameters**: `beta` = 0.6 (range 0.3–0.9)
- *Ref*: Financial-strain research: liquidity buffers matter more than income levels (general finding)

### `financial_stress.debt` — Debt → financial stress

*Evidence: literature · timescale: daily · delay: none*

- **Target**: `financial_stress`
- **Inputs**: `debt`
- **Form**: β·clip(debt/30000, 0, 1)
- **Parameters**: `beta` = 0.15 (range 0.05–0.3)

### `financial_stress.rent_burden` — Rent burden → financial stress

*Evidence: literature · timescale: daily · delay: none*

- **Target**: `financial_stress`
- **Inputs**: `rent_burden`
- **Form**: β·clip(rent/income − 0.4, 0, 1)
- **Parameters**: `beta` = 0.3 (range 0.1–0.5)
- *Ref*: HUD cost-burden convention (>30–40% of income)

### `academic_pressure.load` — Credit load → academic pressure

*Evidence: calibrated · timescale: daily · delay: none*

- **Target**: `academic_pressure`
- **Inputs**: `credits_term`
- **Form**: β·credits/15 while enrolled in term
- **Parameters**: `beta` = 0.25 (range 0.1–0.4)

### `academic_pressure.exams` — Midterms/finals → academic pressure

*Evidence: calibrated · timescale: daily · delay: none*

- **Target**: `academic_pressure`
- **Inputs**: —; other inputs: calendar
- **Form**: β during exam weeks
- **Parameters**: `beta` = 0.25 (range 0.1–0.4)

### `academic_pressure.gpa_gap` — Low GPA → academic pressure

*Evidence: hypothetical · timescale: daily · delay: none*

- **Target**: `academic_pressure`
- **Inputs**: `gpa`, `conscientiousness`
- **Form**: β·clip(3.4 − GPA, 0, 1.5)/1.5·(1 + 0.3·C)
- **Parameters**: `beta` = 0.2 (range 0.05–0.35)

### `academic_pressure.standing` — Warning/probation → pressure

*Evidence: calibrated · timescale: daily · delay: none*

- **Target**: `academic_pressure`
- **Inputs**: `academic_standing`
- **Form**: 0.15

### `romantic_longing.wants` — Wanting a relationship → longing (single)

*Evidence: empirical · timescale: daily · delay: none*

- **Target**: `romantic_longing`
- **Inputs**: `wants_relationship`, `rel_status`
- **Form**: β·clip((wants − 1.5)/2.5, 0, 1) if single
- **Parameters**: `beta` = 0.3 (range 0.1–0.5)
- *Ref*: Dating survey: 'I want to be in a romantic relationship' (most agree)

### `romantic_longing.marriage_norm` — Age-graded marriage norm → longing (active LDS singles)

*Evidence: hypothetical · timescale: daily · delay: none*

- **Target**: `romantic_longing`
- **Inputs**: `age`, `activity`, `world.marriage_norm`
- **Form**: β·active·clip((age − 20.5)/3, 0, 1.2)·norm
- **Parameters**: `beta` = 0.25 (range 0.05–0.45)

### `romantic_longing.drought` — Time since last date → longing

*Evidence: hypothetical · timescale: daily · delay: none*

- **Target**: `romantic_longing`
- **Inputs**: `dates_30d`
- **Form**: β·clip(days since last date / 90, 0, 1)
- **Parameters**: `beta` = 0.2 (range 0.05–0.35)

### `romantic_longing.talking` — Mutual interest relieves longing

*Evidence: hypothetical · timescale: daily · delay: none*

- **Target**: `romantic_longing`
- **Inputs**: `rel_status`
- **Form**: −0.15 if talking

### `stress.setpoint` — Neuroticism → stress set-point

*Evidence: literature · timescale: daily · delay: none*

- **Target**: `stress`
- **Inputs**: `neuroticism`
- **Form**: 0.16 + β·N
- **Parameters**: `neuroticism` = 0.07 (range 0.03–0.12)

### `stress.academic` — Academic pressure → stress

*Evidence: literature · timescale: daily · delay: none*

- **Target**: `stress`
- **Inputs**: `academic_pressure`
- **Form**: β·academic_pressure
- **Parameters**: `beta` = 0.35 (range 0.15–0.5)

### `stress.financial` — Financial stress → stress

*Evidence: literature · timescale: daily · delay: none*

- **Target**: `stress`
- **Inputs**: `financial_stress`
- **Form**: β·financial_stress
- **Parameters**: `beta` = 0.3 (range 0.1–0.5)

### `stress.fatigue` — Fatigue → stress

*Evidence: literature · timescale: daily · delay: none*

- **Target**: `stress`
- **Inputs**: `fatigue`
- **Form**: β·fatigue
- **Parameters**: `beta` = 0.2 (range 0.05–0.35)

### `stress.relationship` — Unsatisfying relationship → stress

*Evidence: literature · timescale: daily · delay: none*

- **Target**: `stress`
- **Inputs**: `relationship_satisfaction`
- **Form**: β·clip(0.6 − satisfaction, 0, 0.6) if partnered
- **Parameters**: `beta` = 0.4 (range 0.15–0.6)

### `stress.faith_crisis` — Faith crisis → stress

*Evidence: empirical · timescale: daily · delay: none*

- **Target**: `stress`
- **Inputs**: `faith_crisis`
- **Form**: β if in crisis
- **Parameters**: `beta` = 0.12 (range 0.04–0.2)

### `stress.minority_stress` — LGBTQ–faith tension → stress (active members)

*Evidence: literature · timescale: daily · delay: none*

- **Target**: `stress`
- **Inputs**: `lgbtq_tension`, `activity`
- **Form**: β·tension·[less active or active]
- **Parameters**: `beta` = 0.25 (range 0.1–0.4)
- *Ref*: Meyer (2003) Psychol Bull: minority stress model

### `stress.support_buffer` — Perceived support buffers stressors

*Evidence: literature · timescale: daily · delay: none*

- **Target**: `stress`
- **Inputs**: `perceived_support`, `academic_pressure`, `financial_stress`, `relationship_satisfaction`, `faith_crisis`
- **Form**: −β·(perceived support − 0.35)·(academic + financial + relationship + faith-crisis terms)
- **Parameters**: `beta` = 0.5 (range 0.2–0.9)
- **Notes**: An interaction, not a main effect — someone with no stressors gains nothing; someone under strain who feels backed gains a lot.
- *Ref*: Cohen & Wills (1985): the stress-buffering hypothesis — support matters most under stress
- *Ref*: Perceived (not received) support carries the buffering effect (Lakey & Orehek 2011)

### `stress.coping` — Coping relief lowers stress

*Evidence: hypothetical · timescale: daily · delay: none*

- **Target**: `stress`
- **Inputs**: `coping_relief`
- **Form**: −β·coping relief
- **Parameters**: `beta` = 0.15 (range 0.05–0.3)
- *Ref*: See coping.relief for how relief is earned

### `loneliness.setpoint` — Trait loneliness set-point

*Evidence: literature · timescale: daily · delay: none*

- **Target**: `loneliness`
- **Inputs**: `neuroticism`, `social_anxiety`
- **Form**: 0.43 + β·N + 0.025·SA
- **Parameters**: `neuroticism` = 0.05 (range 0.02–0.1)

### `loneliness.contact_deficit` — Close contact below one's own need → loneliness

*Evidence: literature · timescale: daily · delay: none*

- **Target**: `loneliness`
- **Inputs**: `close_contact_hours`, `extraversion`
- **Moderators**: `extraversion`
- **Form**: β·clip((need − contact)/need, −1, 1), need = need_hours·exp(βE·E)
- **Parameters**: `beta` = 0.22 (range 0.1–0.4); `need_hours` = 16 (range 8–24); `extraversion` = 0.25 (range 0.0–0.5)
- **Notes**: Extraverts need more contact, so a highly social person can still feel lonely.
- *Ref*: Loneliness as perceived (not objective) isolation — Cacioppo & Hawkley (2009)

### `loneliness.close_friends` — Close friends buffer loneliness

*Evidence: literature · timescale: daily · delay: none*

- **Target**: `loneliness`
- **Inputs**: `n_close_friends`
- **Form**: −β·log(1+n_close)/log 6
- **Parameters**: `beta` = 0.05 (range 0.02–0.12)
- **Notes**: Lowered from 0.07 when the perceived-support term took over part of what close friends do for loneliness.

### `loneliness.coping` — Being supported through a hard time eases loneliness

*Evidence: hypothetical · timescale: daily · delay: none*

- **Target**: `loneliness`
- **Inputs**: `coping_relief`, `coping_strategy`
- **Form**: −β·coping relief while coping by seeking support
- **Parameters**: `beta` = 0.1 (range 0.03–0.2)

### `loneliness.perceived_support` — Believing support is there eases loneliness

*Evidence: literature · timescale: daily · delay: none*

- **Target**: `loneliness`
- **Inputs**: `perceived_support`
- **Form**: −β·(perceived support − 0.45)
- **Parameters**: `beta` = 0.12 (range 0.05–0.25)
- *Ref*: Loneliness is perceived social isolation, distinct from network size (Hawkley & Cacioppo 2010)
- *Ref*: Perceived support predicts wellbeing better than received support (Uchino 2009)

### `loneliness.partner` — Partner buffers loneliness

*Evidence: literature · timescale: daily · delay: none*

- **Target**: `loneliness`
- **Inputs**: `rel_status`
- **Form**: −β·(partnered + 0.4·married)
- **Parameters**: `beta` = 0.07 (range 0.03–0.15)

### `loneliness.ward` — Ward belonging buffers loneliness (attenders)

*Evidence: hypothetical · timescale: daily · delay: none*

- **Target**: `loneliness`
- **Inputs**: `ward_belonging`, `activity`
- **Form**: −β·(ward_belonging − 0.5)
- **Parameters**: `beta` = 0.15 (range 0.05–0.3)

### `loneliness.roommates` — Roommate cohesion buffers loneliness

*Evidence: hypothetical · timescale: daily · delay: none*

- **Target**: `loneliness`
- **Inputs**: `roommate_cohesion`
- **Form**: −β·(cohesion − 0.5)
- **Parameters**: `beta` = 0.15 (range 0.05–0.3)

### `loneliness.romantic` — Romantic longing → loneliness

*Evidence: hypothetical · timescale: daily · delay: none*

- **Target**: `loneliness`
- **Inputs**: `romantic_longing`
- **Form**: β·romantic_longing
- **Parameters**: `beta` = 0.12 (range 0.03–0.25)

### `loneliness.outsider` — Religious-outsider feeling → loneliness

*Evidence: hypothetical · timescale: daily · delay: none*

- **Target**: `loneliness`
- **Inputs**: `outsider`
- **Form**: β·outsider
- **Parameters**: `beta` = 0.1 (range 0.03–0.2)

### `belonging.setpoint` — Belonging baseline

*Evidence: calibrated · timescale: daily · delay: none*

- **Target**: `belonging`
- **Inputs**: —
- **Form**: 0.5

### `belonging.outsider` — Religious-outsider feeling → lower belonging

*Evidence: hypothetical · timescale: daily · delay: none*

- **Target**: `belonging`
- **Inputs**: `outsider`
- **Form**: −β·outsider
- **Parameters**: `beta` = 0.15 (range 0.05–0.3)

### `belonging.congregation` — Own congregation → belonging (non-LDS)

*Evidence: hypothetical · timescale: daily · delay: none*

- **Target**: `belonging`
- **Inputs**: `service_attend`, `congregation_id`
- **Form**: β·(service_attend − 0.3) for those with a congregation
- **Parameters**: `beta` = 0.2 (range 0.05–0.4)

### `belonging.ward` — Ward belonging → overall belonging

*Evidence: hypothetical · timescale: daily · delay: none*

- **Target**: `belonging`
- **Inputs**: `ward_belonging`
- **Form**: β·(ward_belonging − 0.5) for attenders
- **Parameters**: `beta` = 0.3 (range 0.1–0.5)

### `belonging.friends` — Friends → belonging

*Evidence: literature · timescale: daily · delay: none*

- **Target**: `belonging`
- **Inputs**: `n_friends`
- **Form**: β·(log(1+friends)/log 15 − 0.5)
- **Parameters**: `beta` = 0.3 (range 0.1–0.5)

### `belonging.roommates` — Roommates → belonging

*Evidence: hypothetical · timescale: daily · delay: none*

- **Target**: `belonging`
- **Inputs**: `roommate_cohesion`
- **Form**: 0.15·(cohesion − 0.5)

### `belonging.loneliness` — Loneliness erodes belonging

*Evidence: literature · timescale: daily · delay: none*

- **Target**: `belonging`
- **Inputs**: `loneliness`
- **Form**: −0.3·(loneliness − 0.3)

### `anxiety.setpoint` — Trait anxiety set-point

*Evidence: empirical · timescale: daily · delay: none*

- **Target**: `anxiety`
- **Inputs**: `neuroticism`, `mh_anxiety`
- **Form**: 0.18 + β·N + 0.12·anxiety condition
- **Parameters**: `neuroticism` = 0.08 (range 0.03–0.12)
- *Ref*: College Life & Dating surveys: self-reported anxiety prevalence

### `anxiety.stress` — Stress → anxiety

*Evidence: literature · timescale: daily · delay: none*

- **Target**: `anxiety`
- **Inputs**: `stress`
- **Form**: β·(stress − 0.25)
- **Parameters**: `beta` = 0.5 (range 0.2–0.8)

### `anxiety.social` — Social anxiety → anxiety

*Evidence: literature · timescale: daily · delay: none*

- **Target**: `anxiety`
- **Inputs**: `social_anxiety`
- **Form**: 0.04·SA

### `self_esteem.setpoint` — Self-esteem set-point

*Evidence: literature · timescale: daily · delay: none*

- **Target**: `self_esteem`
- **Inputs**: `neuroticism`, `extraversion`
- **Form**: 0.55 − β·N + 0.03·E
- **Parameters**: `neuroticism` = 0.07 (range 0.03–0.12)

### `self_esteem.rejection` — Recent rejections lower confidence

*Evidence: literature · timescale: daily · delay: none*

- **Target**: `self_esteem`
- **Inputs**: `rejections_recent`
- **Form**: −β·log(1 + recent rejections)
- **Parameters**: `beta` = 0.12 (range 0.04–0.2)

### `self_esteem.dating_success` — Dating success raises confidence (singles)

*Evidence: hypothetical · timescale: daily · delay: none*

- **Target**: `self_esteem`
- **Inputs**: `dates_30d`
- **Form**: β·clip(dates_30d/4, 0, 1)
- **Parameters**: `beta` = 0.1 (range 0.03–0.2)

### `self_esteem.relationship` — Being in a relationship → confidence

*Evidence: hypothetical · timescale: daily · delay: none*

- **Target**: `self_esteem`
- **Inputs**: `rel_status`
- **Form**: 0.06

### `self_esteem.academic` — Grades → confidence (students)

*Evidence: hypothetical · timescale: daily · delay: none*

- **Target**: `self_esteem`
- **Inputs**: `gpa`
- **Form**: 0.06·clip((GPA−3.3)/0.7, −1, 1)

### `guilt.setpoint` — Guilt baseline

*Evidence: calibrated · timescale: daily · delay: none*

- **Target**: `guilt`
- **Inputs**: —
- **Form**: 0.03

### `guilt.word_of_wisdom` — Word of Wisdom violations → guilt (in proportion to own orthodoxy)

*Evidence: hypothetical · timescale: daily · delay: none*

- **Target**: `guilt`
- **Inputs**: `coffee`, `alcohol`, `orthodoxy`, `moral_autonomy`, `world.coffee_permitted`
- **Form**: β·orthodoxy·(1 − autonomy)·member·(coffee·[not permitted] + alcohol)
- **Parameters**: `beta` = 0.3 (range 0.1–0.5)

### `guilt.chastity` — Premarital sex → guilt (in proportion to chastity commitment)

*Evidence: hypothetical · timescale: daily · delay: none*

- **Target**: `guilt`
- **Inputs**: `premarital_sex_current`, `chastity_commitment`
- **Form**: β·active·commitment
- **Parameters**: `beta` = 0.35 (range 0.1–0.6)

### `guilt.porn_incongruence` — Moral incongruence → guilt

*Evidence: literature · timescale: daily · delay: none*

- **Target**: `guilt`
- **Inputs**: `porn_incongruence`
- **Form**: β·incongruence
- **Parameters**: `beta` = 0.3 (range 0.1–0.5)
- *Ref*: Grubbs, Perry, Wilt & Reid (2019) Arch Sex Behav: pornography problems due to moral incongruence

### `purpose.setpoint` — Purpose baseline

*Evidence: calibrated · timescale: daily · delay: none*

- **Target**: `purpose`
- **Inputs**: `conscientiousness`
- **Form**: 0.48 + 0.04·C

### `purpose.religion` — Faith & identity → purpose

*Evidence: literature · timescale: daily · delay: none*

- **Target**: `purpose`
- **Inputs**: `religious_identity`, `faith_belief`
- **Form**: β·(identity·belief − 0.4)
- **Parameters**: `beta` = 0.3 (range 0.1–0.5)

### `purpose.progress` — Making progress (school/work) → purpose

*Evidence: hypothetical · timescale: daily · delay: none*

- **Target**: `purpose`
- **Inputs**: `enrolled`, `academic_standing`, `employed`
- **Form**: β·[enrolled in good standing or employed non-student]
- **Parameters**: `beta` = 0.08 (range 0.02–0.15)

### `purpose.family` — Marriage & children → purpose

*Evidence: literature · timescale: daily · delay: none*

- **Target**: `purpose`
- **Inputs**: `rel_status`, `children`
- **Form**: 0.06·married + 0.05·[children>0]

### `mood.setpoint` — Happiness set-point (personality)

*Evidence: literature · timescale: daily · delay: none*

- **Target**: `mood`
- **Inputs**: `extraversion`, `neuroticism`
- **Form**: 0.55 + βE·E − βN·N
- **Parameters**: `extraversion` = 0.05 (range 0.02–0.08); `neuroticism` = 0.07 (range 0.03–0.1)
- *Ref*: Steel, Schmidt & Shultz (2008) Psychol Bull: personality and subjective well-being

### `mood.loneliness` — Loneliness → lower mood

*Evidence: literature · timescale: daily · delay: none*

- **Target**: `mood`
- **Inputs**: `loneliness`
- **Form**: −β·(loneliness − 0.3)
- **Parameters**: `beta` = 0.35 (range 0.15–0.5)

### `mood.stress` — Stress → lower mood

*Evidence: literature · timescale: daily · delay: none*

- **Target**: `mood`
- **Inputs**: `stress`
- **Form**: −β·(stress − 0.3)
- **Parameters**: `beta` = 0.3 (range 0.1–0.5)

### `mood.relationship` — Relationship satisfaction → mood

*Evidence: literature · timescale: daily · delay: none*

- **Target**: `mood`
- **Inputs**: `relationship_satisfaction`
- **Form**: β·(satisfaction − 0.5) if partnered
- **Parameters**: `beta` = 0.2 (range 0.05–0.35)

### `mood.purpose` — Purpose → mood

*Evidence: literature · timescale: daily · delay: none*

- **Target**: `mood`
- **Inputs**: `purpose`
- **Form**: β·(purpose − 0.5)
- **Parameters**: `beta` = 0.25 (range 0.1–0.4)

### `mood.sleep` — Short sleep → lower mood

*Evidence: literature · timescale: daily · delay: none*

- **Target**: `mood`
- **Inputs**: `sleep_hours`
- **Form**: −β·clip(7 − sleep, 0, 4)/3
- **Parameters**: `beta` = 0.1 (range 0.03–0.2)

### `mood.exercise` — Exercise → mood

*Evidence: literature · timescale: daily · delay: none*

- **Target**: `mood`
- **Inputs**: `workouts_week`
- **Form**: β·clip(workouts, 0, 7)/7
- **Parameters**: `beta` = 0.05 (range 0.0–0.1)

### `mood.season` — Winter → slightly lower mood

*Evidence: hypothetical · timescale: daily · delay: none*

- **Target**: `mood`
- **Inputs**: —; other inputs: calendar
- **Form**: −β in Dec–Feb
- **Parameters**: `beta` = 0.03 (range 0.0–0.06)
- **Notes**: Small seasonal effect; seasonal affective patterns vary greatly between people.

### `mood.contagion` — Emotional contagion from friends

*Evidence: literature · timescale: daily · delay: none*

- **Target**: `mood`
- **Inputs**: `mood`
- **Form**: β·(closeness-weighted friends' mood − 0.55), updated weekly
- **Parameters**: `beta` = 0.15 (range 0.0–0.3)
- *Ref*: Fowler & Christakis (2008) BMJ: happiness spreads in social networks
- *Ref*: Hatfield, Cacioppo & Rapson (1993): emotional contagion

### `mood.guilt` — Guilt → lower mood

*Evidence: literature · timescale: daily · delay: none*

- **Target**: `mood`
- **Inputs**: `guilt`
- **Form**: −β·guilt
- **Parameters**: `beta` = 0.2 (range 0.05–0.35)

### `mood.financial` — Financial stress → lower mood

*Evidence: literature · timescale: daily · delay: none*

- **Target**: `mood`
- **Inputs**: `financial_stress`
- **Form**: −β·financial_stress
- **Parameters**: `beta` = 0.1 (range 0.03–0.2)

### `mood.depression` — Depressive episode → lower mood

*Evidence: literature · timescale: daily · delay: none*

- **Target**: `mood`
- **Inputs**: `depressive_episode`
- **Form**: −0.15

### `mood.coping` — Coping relief lifts mood

*Evidence: hypothetical · timescale: daily · delay: none*

- **Target**: `mood`
- **Inputs**: `coping_relief`
- **Form**: β·coping relief
- **Parameters**: `beta` = 0.12 (range 0.04–0.25)

### `mood.rumination` — Rumination prolongs low mood

*Evidence: literature · timescale: daily · delay: none*

- **Target**: `mood`
- **Inputs**: `rumination`, `n_memories`
- **Form**: −β·rumination·clip(negative memory load, 0, 3)/3 — load = Σ strength of negative memories from the last 60 days, kept high by rehearsal
- **Parameters**: `beta` = 0.1 (range 0.03–0.2)
- *Ref*: Nolen-Hoeksema (2000): rumination predicts onset and duration of depressed mood
- *Ref*: Watkins (2008): constructive and unconstructive repetitive thought

### `mental_health.depression` — Depressive episode onset/remission

*Evidence: hypothetical · timescale: daily · delay: none*

- **Target**: `depressive_episode`
- **Inputs**: `mood`, `loneliness`, `mh_depression`, `neuroticism`
- **Form**: weekly onset = logistic(−7.9 + 14·max(0, 0.42 − 8-week mood) + 1.0·history + 0.35·N + 1.5·max(0, loneliness − 0.5)); remission = 0.09 + 0.3·max(0, mood8 − 0.4)
- **Notes**: Threshold non-linearity — sustained low mood matters disproportionately.

## life

### `academics.term` — Terms, sections and enrollment

*Evidence: calibrated · timescale: daily · delay: none*

- **Target**: `enrolled`, `credits_term`
- **Inputs**: `present`; other inputs: calendar
- **Form**: At term start: enroll present students (≈55% of BYU singles in spring/summer); GE lectures (~90) + major sections (~32) as shared contexts

### `academics.study` — Weekly study hours

*Evidence: hypothetical · timescale: daily · delay: none*

- **Target**: `study_hours`
- **Inputs**: `credits_term`, `conscientiousness`, `academic_pressure`, `work_hours`, `depressive_episode`, `fatigue`, `social_hours_week`, `children`
- **Form**: target = base + 0.75·credits + βC·C + 8·pressure − βw·(work−10)⁺ − 6·depressed − 4·fatigue − 0.08·(social−20)⁺ − 3·[children]
- **Parameters**: `base` = 4.0 (range 0–8); `conscientiousness` = 3.0 (range 1–5); `work_crowdout` = 0.25 (range 0.05–0.5)
- **Notes**: Time is finite — work and social life crowd out study (and through it GPA).

### `academics.gpa` — Term GPA production

*Evidence: calibrated · timescale: daily · delay: none*

- **Target**: `gpa`, `gpa_term`
- **Inputs**: `academic_ability`, `conscientiousness`, `study_hours`, `class_attendance`, `fatigue`, `depressive_episode`, `stress`, `sleep_hours`
- **Form**: GPA = clip(base + βa·ability + βC·C + βs·(study−18) + 0.8·(attendance−0.85) − 0.35·fatigue − 0.3·depressed − 0.15·stress + 0.05·(sleep−7) + ε, 0, 4)
- **Parameters**: `base` = 3.45 (range 3.0–3.7); `ability` = 0.3 (range 0.15–0.45); `conscientiousness` = 0.2 (range 0.05–0.35); `study` = 0.015 (range 0.005–0.03); `noise` = 0.3 (range 0.15–0.45)
- *Ref*: ProvoStats: GPA distribution by school and sex
- *Ref*: Okano et al. (2019) npj Sci Learn: sleep and academic performance

### `academics.dropout` — Leaving school

*Evidence: calibrated · timescale: daily · delay: none*

- **Target**: `enrolled`
- **Inputs**: `gpa`, `financial_stress`, `children`
- **Form**: per term h = logistic(base + 0.9·UVU + 1.6·[GPA<2] + 1.2·(fin stress−0.5)⁺ + 0.8·[mother of young children])
- **Parameters**: `base` = -4.5 (range -5.5–-3.5)

### `economy.budget` — Monthly household budget

*Evidence: calibrated · timescale: daily · delay: none*

- **Target**: `savings`, `debt`, `monthly_income`, `rent_burden`
- **Inputs**: `wage`, `work_hours`, `parental_support`, `rent`, `world.tuition_byu`, `world.tuition_uvu`, `dates_30d`, `children`, `owns_car`
- **Form**: income (pooled for couples) − (rent + tuition/4 + food + car + dating + children + other) → savings; shortfalls become debt
- *Ref*: College Life: housing cost, wages, 'parents pay for' items, debts

### `economy.job_loss` — Job loss hazard

*Evidence: calibrated · timescale: daily · delay: none*

- **Target**: `employed`
- **Inputs**: `world.unemployment`
- **Form**: monthly h = base·(unemployment/0.032)^1.5
- **Parameters**: `base` = 0.01 (range 0.004–0.02)

### `economy.job_find` — Job finding

*Evidence: calibrated · timescale: daily · delay: none*

- **Target**: `employed`
- **Inputs**: `financial_stress`, `world.unemployment`
- **Form**: monthly, for job seekers (students with fin stress > 0.5; non-students always): h = logistic(base + 2·(fin stress − 0.4))·(0.032/unemployment)^0.8
- **Parameters**: `base` = -0.5 (range -2.0–0.0)

### `economy.work_more` — Financial strain → more work hours

*Evidence: hypothetical · timescale: daily · delay: none*

- **Target**: `work_hours`
- **Inputs**: `financial_stress`
- **Form**: monthly: students with fin stress > threshold add 3 h/week (cap 32); with fin stress < threshold − 0.25 and above their preferred hours, drop 2 h/week
- **Parameters**: `threshold` = 0.7 (range 0.4–0.85)

### `housing.move` — Moving at lease turnover

*Evidence: calibrated · timescale: daily · delay: none*

- **Target**: `unit_id`
- **Inputs**: `roommate_cohesion`, `rent_burden`, `living`, `openness`
- **Form**: P(move) = logistic(base − 2·(cohesion−0.5) + 1.2·(rent burden−0.5)⁺ + 0.8·dorm + 0.3·O) at Apr 30 / Aug 20
- **Parameters**: `base` = -0.6 (range -1.5–0.3)

### `housing.choice` — Residential location choice

*Evidence: literature · timescale: daily · delay: none*

- **Target**: `unit_id`, `complex_id`, `ward_id`
- **Inputs**: `rent`, `world.contracted_housing_required`; other inputs: budget, distance to campus, friends in complex, quality
- **Form**: MNL over 25 sampled vacant eligible units: U = −βr·rent/budget − βd·km + βf·log(1+friends there) + 0.8·quality + Gumbel
- **Parameters**: `rent` = 2.0 (range 1.0–3.5); `distance` = 0.9 (range 0.3–1.5); `friends` = 0.8 (range 0.2–1.5)
- *Ref*: McFadden (1978): estimation with sampled alternatives
- *Ref*: UrbanSim household location choice models (Waddell 2002)

### `housing.market` — Rent responds to vacancy

*Evidence: calibrated · timescale: daily · delay: none*

- **Target**: `world.rent_index`
- **Inputs**: `world.housing_supply_index`; other inputs: vacancy
- **Form**: monthly rent × (1 + β·(0.06 − vacancy))
- **Parameters**: `rent_response` = 0.15 (range 0.05–0.4)

### `lifecourse.arrival` — Cohort arrivals

*Evidence: calibrated · timescale: daily · delay: none*

- **Target**: `present`
- **Inputs**: `world.enrollment_index`; other inputs: flows
- **Form**: Freshmen and new UVU students arrive at fall start; returned missionaries arrive through the year

### `lifecourse.departure` — Leaving the area

*Evidence: calibrated · timescale: daily · delay: none*

- **Target**: `present`
- **Inputs**: `graduated`, `family_local`
- **Form**: after graduation P(leave) ≈ 0.62 BYU / 0.42 UVU, −0.25 if family local

### `lifecourse.stay` — How long non-students stay in the college scene

*Evidence: calibrated · timescale: daily · delay: none*

- **Target**: `present`
- **Inputs**: `role`, `rel_status`
- **Form**: graduates who stay, dropouts and young adults leave after an exponential stay (mean = years); married couples leave together, and wait while a spouse is still enrolled
- **Parameters**: `young_adult_years` = 1.6 (range 0.8–3.0)
- **Notes**: Holds the non-student young-adult stock near its configured size (inflow from graduates who stay and dropouts ≈ outflow). Without it that stock grew ~10% a year with no exit (see scripts/accounting.py). Real residence durations for post-college young adults in Provo/Orem are not measured here; the value is chosen for stock balance.

### `lifecourse.illness` — Short illnesses

*Evidence: calibrated · timescale: daily · delay: none*

- **Target**: `ill`
- **Inputs**: —
- **Form**: daily P = rate; 2–7 days
- **Parameters**: `rate` = 0.006 (range 0.003–0.012)

### `lifecourse.mission` — Mission service

*Evidence: calibrated · timescale: daily · delay: none*

- **Target**: `mission_status`
- **Inputs**: `sex`, `age`, `faith_belief`, `activity`, `family_expectation`, `religious_identity`, `world.mission_norm`
- **Form**: monthly P(call) = logistic(base + βm·male + βb·(belief−0.7) + 1.2·active + βf·family + 0.8·identity + 2·age peak − 1.5·years past the usual age + log(mission_norm)); departure ~3 months later; men 24, women 18 months; ~8% return early
- **Parameters**: `base` = -7.0 (range -8–-5); `male` = 1.6 (range 0.8–2.4); `belief` = 3.0 (range 1.5–4.5); `family` = 1.0 (range 0.3–1.8)
- *Ref*: ProvoStats: mission service by sex, activity and age
- *Ref*: Church policy since 2012: men from 18 (24 months), women from 19 (18 months)

### `lifecourse.fertility` — Fertility (married couples)

*Evidence: calibrated · timescale: daily · delay: none*

- **Target**: `pregnant`, `children`
- **Inputs**: `kids_wanted`, `children`, `married_day`, `enrolled`, `financial_stress`, `activity`, `age`
- **Form**: monthly P(conceive) = logistic(base + 0.25·(wanted−3) − 0.55·children + 0.06·months married − βs·student − 0.8·fin stress + 0.5·active − 0.08·(age−30)⁺)
- **Parameters**: `base` = -3.3 (range -4.5–-2.0); `student` = 0.8 (range 0.2–1.4)
- *Ref*: Dating survey: desired number of children (median 4)
- *Ref*: Culture & Lifestyle: children by age among married respondents

### `lifecourse.events` — Background life events

*Evidence: calibrated · timescale: daily · delay: none*

- **Target**: `stress`, `mood`, `financial_stress`
- **Inputs**: —
- **Form**: monthly hazards: family crisis, death in family, car accident (car owners)
- **Parameters**: `family_crisis` = 0.006 (range 0.002–0.012); `death` = 0.0015 (range 0.0005–0.003); `car_accident` = 0.008 (range 0.003–0.015)
- *Ref*: College Life: ~1/3 report ≥1 at-fault car accident

### `economy.quit` — Students quit jobs to focus on school

*Evidence: calibrated · timescale: daily · delay: none*

- **Target**: `employed`
- **Inputs**: `financial_stress`, `academic_pressure`
- **Form**: monthly P(quit) = base·(1 + 2·academic pressure) for employed students with financial stress < 0.3
- **Parameters**: `base` = 0.05 (range 0.01–0.12)
- **Notes**: Balances job-taking under financial strain so student work hours stay near the survey levels over a year.

## mind

### `mind.importance` — What matters to someone (motive importance)

*Evidence: structural · timescale: daily · delay: none*

- **Target**: `cares_connection`, `cares_partnership`, `cares_achievement`, `cares_security`, `cares_faith`, `cares_rest`, `cares_fun`, `cares_health`
- **Inputs**: `extraversion`, `agreeableness`, `attachment_anxiety`, `attachment_avoidance`, `social_events_month`, `wants_relationship`, `activity`, `age`, `rel_status`, `conscientiousness`, `academic_ability`, `enrolled`, `parent_income`, `children`, `neuroticism`, `religious_identity`, `faith_belief`, `own_religiosity`, `sensation_seeking`, `openness`, `workouts_week`, `sports`, `world.marriage_norm`
- **Form**: cares_m = logistic(trait/value/circumstance index_m); weekly drift toward the target at rate `drift` (priorities change when identity or circumstances do)
- **Parameters**: `marriage_norm` = 1.0 (range 0.4–1.6); `drift` = 0.1 (range 0.03–0.25)
- **Notes**: Eight concerns rather than hundreds of direct arrows. Weights are a structural assumption; their inputs are the survey-grounded traits.
- *Ref*: Deci & Ryan (2000): self-determination theory — relatedness, competence, autonomy
- *Ref*: Kenrick et al. (2010): fundamental social motives
- *Ref*: Schwartz (1992): value priorities are stable but shift with life stage

### `mind.drive` — Drives and the top priority (importance × unmet)

*Evidence: structural · timescale: daily · delay: none*

- **Target**: `drive_connection`, `drive_partnership`, `drive_achievement`, `drive_security`, `drive_faith`, `drive_rest`, `drive_fun`, `drive_health`, `top_priority`, `sat_fun`, `sat_health`
- **Inputs**: `loneliness`, `romantic_longing`, `relationship_satisfaction`, `academic_pressure`, `self_eff_academic`, `financial_stress`, `guilt`, `religious_identity`, `attend_rate`, `private_practice`, `own_religiosity`, `service_attend`, `outsider`, `fatigue`
- **Form**: drive_m = cares_m × (1 − felt fulfilment_m); fulfilment reads the felt state (1 − loneliness, 1 − financial stress, …) or recent experience (outings, workouts vs appetite)
- **Notes**: The shared currency that lets subsystems compete — money worries and coursework pull effort away from dating and fun through the same drives.
- *Ref*: Cacioppo & Hawkley (2009): loneliness as an aversive signal that motivates reconnection (a 'social hunger')
- *Ref*: Homeostatic need models (e.g. Hull; Berridge 2004 on wanting)

### `mind.choice` — Drives steer free-time choices

*Evidence: calibrated · timescale: daily · delay: none*

- **Target**: `activity_now`
- **Inputs**: `drive_connection`, `drive_partnership`, `drive_achievement`, `drive_rest`, `drive_fun`, `drive_health`, `expect_social`, `coping_strategy`, `routine_strength`
- **Form**: U(option) = habit/trait base + Σ_m w_m·drive_m·gain(option, m) + routine bonus + coping bias + Gumbel noise; gains: home→rest, campus→achievement, gym→health, venue/outdoors→fun, dance→partnership+fun, visiting a friend→connection (scaled by expected warmth)
- **Parameters**: `rest` = 2.0 (range 1.0–3.0); `achievement` = 2.4 (range 1.2–3.6); `health` = 1.0 (range 0.4–2.0); `fun` = 1.2 (range 0.4–2.0); `partnership` = 1.6 (range 0.6–2.6)
- *Ref*: McFadden (1974): random-utility choice
- *Ref*: Replaces direct state terms (1.2·fatigue, 1.3·academic pressure, 0.8·romantic longing) with drives

### `mind.expect_accept` — Learning what to expect when asking someone out

*Evidence: literature · timescale: daily · delay: none*

- **Target**: `expect_accept`
- **Inputs**: `attractiveness`, `rejection_sensitivity`, `extraversion`
- **Form**: after each ask: V ← V + α·(accepted − V); after a no, α × (1 + β_rs·max(0, z_RS))
- **Parameters**: `alpha` = 0.15 (range 0.05–0.3); `rs_asymmetry` = 0.6 (range 0.0–1.2)
- **Notes**: Replaces the direct 'recent rejections × rejection sensitivity → fewer asks' term; a run of rejections now works through a learned, inspectable expectation.
- *Ref*: Rescorla & Wagner (1972): prediction-error learning
- *Ref*: Downey & Feldman (1996): rejection sensitivity — anxious expectation of rejection

### `mind.expect_social` — Learning how warm people are

*Evidence: literature · timescale: daily · delay: none*

- **Target**: `expect_social`
- **Inputs**: `extraversion`, `social_anxiety`, `neuroticism`
- **Form**: daily, from interactions in social settings: V ← V + α·min(n,4)/4·(½ + ½·tanh(mean valence) − V); bad moments weigh (1 + β·max(0, z_SA)) more
- **Parameters**: `alpha` = 0.05 (range 0.01–0.12); `threat_bias` = 0.5 (range 0.0–1.0)
- *Ref*: Cacioppo & Hawkley (2009): loneliness heightens attention to social threat
- *Ref*: Clark & Wells (1995): social anxiety and threat-biased processing

### `mind.self_efficacy` — Academic confidence from mastery experiences

*Evidence: literature · timescale: daily · delay: none*

- **Target**: `self_eff_academic`
- **Inputs**: `academic_ability`, `conscientiousness`, `neuroticism`, `gpa`, `gpa_term`
- **Form**: at term end: eff ← eff + α·(class rank of term GPA − eff) − 0.02·z_N; study target += β_s·(eff − 0.5); dropout logit −= β_d·(eff − 0.5)
- **Parameters**: `alpha` = 0.25 (range 0.1–0.4); `study` = 4.0 (range 1.0–7.0); `dropout` = 1.2 (range 0.4–2.0)
- **Notes**: Effects on GPA run only through effort (study hours), so confidence and ability are not double counted.
- *Ref*: Bandura (1997): mastery experiences are the strongest source of self-efficacy
- *Ref*: Multon, Brown & Lent (1991): self-efficacy ↔ performance r≈.38, persistence r≈.34

### `mind.perceived_support` — Support people believe they have

*Evidence: literature · timescale: daily · delay: none*

- **Target**: `perceived_support`
- **Inputs**: `support_actual`, `neuroticism`, `attachment_anxiety`, `loneliness`
- **Form**: perceived = logistic(r·logit(actual) + (1 − r)·0.4 − β_N·z_N − β_A·z_attach_anx − β_L·(loneliness − 0.33) + β_lens·personal lens)
- **Parameters**: `reality` = 0.125 (range 0.1–0.6); `neuroticism` = 0.35 (range 0.1–0.6); `attachment` = 0.3 (range 0.1–0.5); `loneliness` = 1.0 (range 0.3–2.0); `lens` = 0.8 (range 0.3–1.3)
- **Notes**: The personal lens and trait biases are set so perceived and actual support correlate around .35–.5 (checked in validation).
- *Ref*: Haber, Cohen, Lucas & Baltes (2007): received vs perceived support r = .35 (23 studies)
- *Ref*: Lakey & Drew (1997): perceived support reflects the perceiver as much as the network

### `mind.pluralistic_ignorance` — Concealed doubt and misread norms

*Evidence: literature · timescale: daily · delay: none*

- **Target**: `perceived_friend_belief`, `friend_belief_actual`
- **Inputs**: `faith_belief`, `moral_autonomy`, `perceived_norm`, `edge.closeness`
- **Form**: expressed = belief + λ·(1 − autonomy)·max(0, local pressure − belief) for members (only doubt is concealed); perceived friends' belief = Σ closeness·(disclosure·belief + (1 − disclosure)·expressed) / Σ closeness
- **Parameters**: `concealment` = 0.5 (range 0.0–0.9)
- **Notes**: Doubters see more devotion around them than exists, so faith influence (which reads the perceived figure) props up the norm; confiding in close friends dissolves the illusion.
- *Ref*: Prentice & Miller (1993): students misjudge peers' private attitudes toward a visible norm
- *Ref*: Miller & McFarland (1987): pluralistic ignorance
- *Ref*: Noelle-Neumann (1974): spiral of silence

### `mind.romantic_perception` — Reading whether someone is interested

*Evidence: literature · timescale: daily · delay: none*

- **Target**: `edge.attraction_lh`
- **Inputs**: `social_anxiety`, `sex`; other inputs: n_inter
- **Form**: read = (1 − π)·(actual + noise·0.35·e^{0.3·z_SA}) + π·own attraction − gap·e^{−interactions/8} + male over-perception; belief ← belief + η·(read − belief) each interaction; a yes, no, kiss or date reveals much more
- **Parameters**: `projection` = 0.35 (range 0.1–0.6); `liking_gap` = 0.12 (range 0.0–0.25); `male_overperception` = 0.08 (range 0.0–0.2); `learning_rate` = 0.08 (range 0.03–0.2); `date_reveal` = 0.5 (range 0.2–0.8); `ask_weight` = 1.2 (range 0.4–2.0)
- **Notes**: Asking out now depends on believed interest, so crushes can be unrequited (believed yes, actual no) and connections missed (mutual interest that neither believes). Magnitudes are hypothetical; directions follow the literature.
- *Ref*: Boothby, Cooney, Sandstrom & Clark (2018): the liking gap after conversations
- *Ref*: Haselton & Buss (2000); Perilloux, Easton & Buss (2012): men over-perceive women's sexual interest
- *Ref*: Lemay, Clark & Feeney (2007): projection of one's own feelings onto partners

## norms

### `norms.contagion` — Complex contagion of practices

*Evidence: literature · timescale: daily · delay: none*

- **Target**: `coffee`, `alcohol`, `pickleball`, `app_user`
- **Inputs**: —; other inputs: friends' adoption
- **Form**: peer term = βp·log(1+k)·clip(k/threshold, 0, 1) + 0.8·share, k = adopting friends
- **Parameters**: `peer` = 0.8 (range 0.2–1.5); `threshold` = 2 (range 1–4)
- *Ref*: Centola & Macy (2007) AJS: complex contagions and the weakness of long ties
- *Ref*: Centola (2010) Science: spread of behavior in an online network experiment

### `norms.coffee` — Coffee adoption

*Evidence: hypothetical · timescale: daily · delay: none*

- **Target**: `coffee`
- **Inputs**: `orthodoxy`, `chastity_commitment`, `faith_belief`, `moral_autonomy`, `sensation_seeking`, `world.coffee_permitted`
- **Form**: weekly h = 0.05·logistic(base − βpro·orthodoxy·active·(1−permitted)·(1+commitment) + 0.8·(1−belief) + 0.6·autonomy + 0.2·SS + βperm·permitted·member + peer)
- **Parameters**: `base` = -5.0 (range -6.5–-3.5); `prohibition` = 3.0 (range 1.5–4.5); `permitted_boost` = 2.5 (range 0.5–4.0)
- **Notes**: The canonical "coffee is now permitted" intervention flips `coffee_permitted`, removing the prohibition term and the guilt associated with coffee.
- *Ref*: Culture & Lifestyle: coffee frequency by activity (≈83% never)

### `norms.alcohol` — Alcohol adoption

*Evidence: hypothetical · timescale: daily · delay: none*

- **Target**: `alcohol`
- **Inputs**: `orthodoxy`, `faith_belief`, `moral_autonomy`, `sensation_seeking`, `age`
- **Form**: weekly h = 0.05·logistic(base − 2.5·orthodoxy·active·(1 − permitted) − 1.2·belief·member + permitted_boost·permitted·member + 0.6·autonomy + 0.4·SS + 0.4·[21+] + peer)
- **Parameters**: `base` = -5.0 (range -6.5–-3.5); `permitted_boost` = 1.0 (range 0.3–2.5)

### `norms.pickleball` — Pickleball craze (example cultural diffusion)

*Evidence: hypothetical · timescale: daily · delay: none*

- **Target**: `pickleball`
- **Inputs**: `sports`, `extraversion`, `hikes`
- **Form**: weekly h = 0.05·logistic(base + 0.8·sports + 0.3·E + 0.3·hikes + peer)
- **Parameters**: `base` = -4.5 (range -6–-3)

### `norms.app` — Dating-app adoption

*Evidence: calibrated · timescale: daily · delay: none*

- **Target**: `app_user`
- **Inputs**: `dating_motivation`, `picky`, `world.app_appeal`
- **Form**: weekly h = 0.05·logistic(base + 1.5·motivation + log(app_appeal) + 0.3·picky + peer)
- **Parameters**: `base` = -3.0 (range -4.5–-1.5)

### `norms.quit` — Quitting a practice to resolve guilt

*Evidence: hypothetical · timescale: daily · delay: none*

- **Target**: `coffee`, `alcohol`
- **Inputs**: `guilt`, `orthodoxy`
- **Form**: weekly P(quit) = β·guilt·orthodoxy·[active member]
- **Parameters**: `guilt` = 0.15 (range 0.05–0.3)

## plans

### `plans.formation` — Forming a weekly intention

*Evidence: structural · timescale: daily · delay: none*

- **Target**: `intention`
- **Inputs**: `drive_partnership`, `drive_connection`, `drive_achievement`, `drive_security`, `drive_faith`, `expect_accept`, `n_friends`, `gpa`, `employed`, `attend_rate`, `cares_faith`
- **Form**: weekly, for people without one: score per intention (ask out = partnership drive × crush attraction × (0.5 + expected yes); reconnect = connection drive × closeness of the closest friend unseen for 2+ weeks; meet people = connection drive × few friends; study more = achievement drive (more with GPA < 3); find work = security drive if not employed; return to church = faith drive if attendance lapsed); form the best if score > threshold
- **Parameters**: `threshold` = 0.12 (range 0.06–0.25)
- *Ref*: Rao & Georgeff (1995): BDI agents — desires become committed intentions
- *Ref*: Ajzen (1991): intentions as the proximal cause of behavior

### `plans.execution` — Acting on an intention (the intention–behavior gap)

*Evidence: literature · timescale: daily · delay: none*

- **Target**: `dates_30d`, `study_hours`, `attend_rate`, `employed`, `social_events_month`
- **Inputs**: `intention`, `conscientiousness`, `self_control`
- **Form**: follow-through = logistic(0.4 + 0.5·z_C + 0.4·z_self-control); boosts × follow-through: ask logit +ask (toward the intended person), study +study h, church logit +church, meeting people: venues/dances/complex/visits and invitation acceptance; job search for 'find work'; reconnecting picks the intended friend 70% × follow-through
- **Parameters**: `ask` = 1.2 (range 0.4–2.0); `study` = 3.0 (range 1.0–5.0); `church` = 0.8 (range 0.2–1.4); `meet` = 1.0 (range 0.3–1.6)
- **Notes**: Calibrated so roughly half of intentions are carried out within their window (see the plan ledger summary in validation).
- *Ref*: Sheeran (2002): intentions explain a modest share of behavior; 'inclined abstainers' drive the gap
- *Ref*: Sheeran & Webb (2016): the intention–behavior gap
- *Ref*: Gollwitzer (1999): implementation intentions

### `plans.reconsider` — Why plans change

*Evidence: structural · timescale: daily · delay: none*

- **Target**: `intention`
- **Inputs**: `rel_status`, `present`, `drive_partnership`, `drive_connection`, `drive_achievement`, `drive_security`, `drive_faith`
- **Form**: kept when the behavior happens; abandoned when the target is gone (the crush started dating someone, a friend moved) or priorities shifted (this drive fell under half its strength and another is 2.5× larger); lapsed when the window (10–35 days) passes
- *Ref*: Bratman (1987): intentions are stable but open to reconsideration when circumstances change

### `routine.habit` — Weekly routines and habit strength

*Evidence: literature · timescale: daily · delay: none*

- **Target**: `routine_strength`, `activity_now`
- **Inputs**: `activity_now`
- **Form**: per weekly slot: same option → s ← s + α(1 − s); different → s ← s(1 − 1.5α), switch when s < 0.15; utility of the habitual option += weight·s
- **Parameters**: `alpha` = 0.12 (range 0.05–0.25); `weight` = 0.8 (range 0.2–1.5)
- **Notes**: A slot met once a week plateaus after ~15–20 repetitions (≈4 months), slower than a daily habit.
- *Ref*: Lally, van Jaarsveld, Potts & Wardle (2010): median 66 days (18–254) to habit plateau
- *Ref*: Wood & Neal (2007): habits are cued by context and bypass deliberation
- *Ref*: MATSim (Horni, Nagel & Axhausen 2016): agents keep and reuse daily plans

## religion

### `faith.attend` — Sunday attendance

*Evidence: empirical · timescale: daily · delay: none*

- **Target**: `attend_rate`, `activity`
- **Inputs**: `faith_belief`, `religious_identity`, `practice_habit`, `perceived_norm`, `family_expectation`, `stress`, `fatigue`, `world.church_attendance_norm`
- **Form**: P(attend) = logistic(base + βb·(belief−0.6) + βi·(identity−0.5) + βh·(habit−0.5) + βn·(norm−0.5) + βf·family − βs·(stress−0.3)⁺ − 0.8·fatigue − 2·Sunday work − crisis)
- **Parameters**: `base` = -0.45 (range -1.5–0.5); `belief` = 3.0 (range 1.5–4.5); `identity` = 2.0 (range 1.0–3.0); `habit` = 2.0 (range 1.0–3.0); `norm` = 1.0 (range 0.3–2.0); `family` = 0.8 (range 0.2–1.4); `stress` = 1.5 (range 0.5–2.5)
- **Notes**: Activity category (active / less active / inactive) is derived from the resulting 8-week attendance rate.
- *Ref*: Culture & Lifestyle: sacrament attendance by belief/identity items
- *Ref*: ProvoStats: activity by school, sex, relationship

### `faith.habit` — Attendance habit formation

*Evidence: literature · timescale: daily · delay: none*

- **Target**: `practice_habit`
- **Inputs**: `attend_rate`
- **Form**: attend: h ← h + α(1−h); miss: h ← h(1 − 0.4α)
- **Parameters**: `learning_rate` = 0.06 (range 0.02–0.12)
- *Ref*: Lally, van Jaarsveld, Potts & Wardle (2010) EJSP: habit automaticity grows asymptotically (median ~66 days)

### `faith.practices` — Private & temple practice follow activity

*Evidence: empirical · timescale: daily · delay: none*

- **Target**: `temple_per_year`, `scripture_minutes`
- **Inputs**: `activity`, `temple_recommend`
- **Form**: weekly: x ← x + r·(pref·f(activity)·g(recommend) − x); f = 1 active, f_less, f_inactive, 0 non-member; g = 1 with recommend else 0.15 (temple only)
- **Parameters**: `less_active_factor` = 0.5 (range 0.3–0.7); `inactive_factor` = 0.05 (range 0.0–0.15); `adjust_rate` = 0.08 (range 0.03–0.2)
- **Notes**: Each person keeps a personal preference level (sampled from the culture survey); what they actually do tracks their current activity, so a faith transition shows up in practices over weeks.
- *Ref*: Culture & Lifestyle survey: temple visits/year 17.1 (active) vs 3.4 (less active) vs 0.25 (inactive); scripture minutes/day 10.7 vs 2.4 vs 0

### `faith.influence` — Social influence on belief (uncertainty-gated)

*Evidence: literature · timescale: daily · delay: none*

- **Target**: `faith_belief`
- **Inputs**: `perceived_friend_belief`, `faith_certainty`, `conformity`
- **Moderators**: `faith_certainty`, `conformity`
- **Form**: Δbelief = β·(1 − certainty)·exp(0.3·conformity)·(what they perceive friends believe − belief), weekly (perception per mind.pluralistic_ignorance); alternative form (form = 1): bounded confidence — the pull drops to 20% when the gap exceeds `bound`
- **Parameters**: `base` = 0.03 (range 0.0–0.08); `form` = 0 (range 0–1); `bound` = 0.3 (range 0.15–0.5)
- **Notes**: Model uncertainty, not just parameter uncertainty: assimilation (form 0, default) and bounded confidence (form 1) are both defensible; uncertainty ensembles draw the form so conclusions that depend on it are flagged.
- *Ref*: DeGroot-type opinion dynamics; uncertainty increases susceptibility to influence (general social-influence finding)
- *Ref*: Hegselmann & Krause (2002): bounded-confidence opinion dynamics (the alternative form)

### `faith.spiritual` — Spiritual experiences

*Evidence: hypothetical · timescale: daily · delay: none*

- **Target**: `faith_belief`, `faith_certainty`, `purpose`
- **Inputs**: `private_practice`, `attend_rate`, `faith_belief`
- **Form**: weekly P = rate·(0.3 + private practice + 0.5·attendance)·belief
- **Parameters**: `rate` = 0.03 (range 0.01–0.06)

### `faith.challenge` — Faith challenges (history, policy, online content)

*Evidence: empirical · timescale: daily · delay: none*

- **Target**: `faith_belief`, `faith_certainty`
- **Inputs**: `openness`, `social_media_hours`, `history_struggle`, `lgbtq_tension`, `faith_certainty`
- **Form**: weekly P = rate·exp(0.35·O + 0.15·log(1+social media h) + 0.8·history/4 + 1.2·LGBTQ tension − 0.8·(certainty−0.6)); belief −= hit·(1−certainty), certainty −= hit
- **Parameters**: `rate` = 0.006 (range 0.002–0.015); `belief_hit` = 0.04 (range 0.01–0.08); `certainty_hit` = 0.06 (range 0.02–0.12)
- *Ref*: Culture & Lifestyle: ~76% report having struggled with faith; church-history difficulty common among those who left

### `faith.dissonance` — Belief–behavior dissonance → belief change

*Evidence: hypothetical · timescale: daily · delay: none*

- **Target**: `faith_belief`
- **Inputs**: `guilt`, `religious_identity`, `moral_autonomy`
- **Form**: after ≥4 weeks of guilt>0.3: Δbelief = −β·guilt·(1 − identity)·(0.5 + autonomy)
- **Parameters**: `belief_shift` = 0.01 (range 0.0–0.03)
- **Notes**: The alternative resolutions (quitting the behavior; repentance) are in norms.quit and romance.confession, so different people take different paths.
- *Ref*: Festinger (1957): cognitive dissonance — resolved by changing behavior or belief

### `faith.crisis` — Faith crisis onset & resolution

*Evidence: hypothetical · timescale: daily · delay: none*

- **Target**: `faith_crisis`, `faith_belief`, `religious_identity`, `lds_member`
- **Inputs**: `faith_certainty`, `religious_identity`, `perceived_norm`, `family_expectation`, `institutional_trust`, `moral_autonomy`, `lgbtq_tension`
- **Form**: onset: certainty < threshold → weekly P(onset); resolution after ≥60 days: weekly P(resolve); outcome = argmax(renew, nuanced, leave utilities + Gumbel)
- **Parameters**: `certainty_threshold` = 0.3 (range 0.2–0.45); `onset_rate` = 0.05 (range 0.01–0.1); `resolution_rate` = 0.03 (range 0.01–0.06); `leave_bias` = -0.3 (range -1.5–1.0)
- *Ref*: Culture & Lifestyle: ~18% agree they are currently in a faith crisis; ranked reasons for leaving (doctrine, policy, history)

### `faith.other_attend` — Non-LDS service attendance

*Evidence: hypothetical · timescale: daily · delay: none*

- **Target**: `service_attend`
- **Inputs**: `own_religiosity`, `service_attend`, `stress`, `fatigue`
- **Form**: P(attend this week) = logistic(base + βr·(own religiosity − 0.5) + βh·(service_attend − 0.4) − 0.8·fatigue − 0.6·(stress − 0.3)⁺); religious non-LDS find the nearest congregation of their tradition
- **Parameters**: `base` = -0.6 (range -1.5–0.3); `religiosity` = 3.0 (range 1.5–4.5); `habit` = 2.0 (range 1.0–3.0)
- **Notes**: Catholic, Protestant and other congregations are real places in Provo/Orem; attenders meet each other there like LDS ward members do.

### `faith.outsider` — Religious-outsider feeling

*Evidence: hypothetical · timescale: daily · delay: none*

- **Target**: `outsider`
- **Inputs**: `school`; other inputs: lds friends share, lds roommates share, being proselytized, faith or secular community
- **Form**: target = 0.12 + 0.35·LDS share of friends + 0.15·LDS share of roommates + 0.12·[BYU] + 0.15·[recently met missionaries] − 0.2·[a close friend who shares one's outlook] − 0.15·[own congregation or faith/secular club]; weekly EWMA
- **Parameters**: `weight` = 0.25 (range 0.1–0.5)
- *Ref*: Minority-religion students in religiously homogeneous campuses report lower belonging (e.g., Bowman & Small 2012)

### `faith.missionary_contact` — Invited to meet the missionaries

*Evidence: hypothetical · timescale: daily · delay: none*

- **Target**: `investigating`
- **Inputs**: `own_religiosity`, `openness`; other inputs: LDS close friends, LDS partner
- **Form**: weekly h = rate·(LDS close friends with belief > 0.6 + 3·[dating an LDS member])·exp(0.3·openness − 1.5·own religiosity); lessons stop at 8%/week
- **Parameters**: `rate` = 0.0008 (range 0.0003–0.003)

### `faith.conversion` — Baptism (conversion)

*Evidence: hypothetical · timescale: daily · delay: none*

- **Target**: `lds_member`
- **Inputs**: `investigating`, `own_religiosity`; other inputs: LDS partner, LDS friend share
- **Form**: weekly h = logistic(base + 2·[dating/engaged to an LDS member] + 1.5·LDS friend share − 2·own religiosity) while investigating (≈2–3% of non-members per year overall)
- **Parameters**: `base` = -5.0 (range -6.5–-3.5)
- **Notes**: New converts start active with moderate belief and join a ward; their own path afterwards follows the same faith dynamics as everyone else.

## romance

### `romance.attraction` — Initial romantic attraction

*Evidence: empirical · timescale: daily · delay: none*

- **Target**: `edge.attraction_lh`, `edge.attraction_hl`
- **Inputs**: `attractiveness`, `imp_physical`, `age`, `max_older`, `max_younger`, `height_in`, `min_height_req`, `activity`, `imp_spirituality`, `mission_status`, `prefers_rm`, `hikes`, `music_maker`, `sports`, `gaming`, `ethnicity`, `agreeableness`, `social_skill`
- **Form**: a(i→j) = tanh((spark_shared + spark_directed + looks + age_fit + height_fit + religiosity_fit + RM_bonus + shared_interests + ethnic_homophily + personality + base)/1.5); 0 if orientation-incompatible
- **Parameters**: `base` = -0.1 (range -0.5–0.3); `spark_shared` = 0.55 (range 0.3–0.8); `spark_directed` = 0.45 (range 0.2–0.7); `looks` = 0.3 (range 0.1–0.5); `age_fit` = 0.35 (range 0.1–0.6); `height` = 0.4 (range 0.1–0.8); `religiosity_fit` = 0.8 (range 0.3–1.4); `rm_bonus` = 0.25 (range 0.0–0.5); `shared_interests` = 0.08 (range 0.0–0.2); `ethnic_homophily` = 0.1 (range 0.0–0.3); `personality` = 0.15 (range 0.0–0.3); `interaction_update` = 0.03 (range 0.01–0.06)
- **Notes**: Most attraction is pair-specific "spark"; shared hobbies barely matter — consistent with the survey's ranking and with machine-learning evidence.
- *Ref*: Dating survey (n≈900): age-gap limits, partner-trait rankings (shared interests ranked last), RM preferences
- *Ref*: ProvoStats: women's minimum partner height; 'not active' as a swipe-left dealbreaker
- *Ref*: Joel, Eastwick & Finkel (2017) Psychol Sci: romantic desire is largely idiosyncratic and hard to predict from traits

### `romance.motivation` — Dating motivation

*Evidence: hypothetical · timescale: daily · delay: none*

- **Target**: `dating_motivation`
- **Inputs**: `wants_relationship`, `drive_partnership`, `age`, `activity`, `mission_status`, `extraversion`, `depressive_episode`, `drive_achievement`, `drive_security`, `drive_rest`
- **Form**: m = logistic(base + βw·wants + βl·partnership drive/0.55 + βn·marriage_norm·age_norm·active + 0.4·recent RM + 0.25·E − 0.8·depressed − βc·(achievement + security + rest drives)/0.55)
- **Parameters**: `base` = -0.5 (range -1.5–0.5); `wants` = 1.0 (range 0.4–1.6); `longing` = 1.5 (range 0.5–2.5); `marriage_norm` = 1.0 (range 0.3–1.8); `competing` = 0.4 (range 0.1–0.9)
- **Notes**: Encodes the strong LDS young-adult marriage norm (returned missionaries are expected to date toward marriage). Longing enters through the partnership drive (how much a partner matters × how much they miss one), and coursework, money and exhaustion compete through their drives instead of separate direct terms.

### `romance.ask` — Asking someone out

*Evidence: empirical · timescale: daily · delay: none*

- **Target**: `dates_30d`
- **Inputs**: `edge.attraction_lh`, `dating_motivation`, `self_esteem`, `expect_accept`, `sex`, `dating_propensity`, `asks_for_numbers`
- **Form**: P/day = logistic(base + βa·attraction + βm·motivation + βc·confidence + βe·(logit expected yes − logit 0.6) + βb·(believed interest − 0.15) ± βmale·norm + βp·log(propensity)) × weekday factor
- **Parameters**: `base` = -4 (range -5.5–-2.5); `attraction` = 2.5 (range 1–4); `motivation` = 1.5 (range 0.5–2.5); `confidence` = 1.0 (range 0.3–2.0); `expectation` = 0.6 (range 0.2–1.2); `male` = 1.0 (range 0.3–1.8); `propensity` = 0.6 (range 0.2–1.0); `min_attraction` = 0.25 (range 0.1–0.4)
- **Notes**: People ask when they are attracted, motivated and expect a yes — from their learned expectation (mind.expect_accept) and their read of the other's interest (mind.romantic_perception), not the other's true feelings. Rejection works through the expectation it teaches.
- *Ref*: Dating survey: most agree men should make the first move
- *Ref*: ProvoStats: dates per month by sex/relationship/activity

### `romance.accept` — Accepting a date

*Evidence: empirical · timescale: daily · delay: none*

- **Target**: `dates_30d`
- **Inputs**: `edge.attraction_lh`, `accepts_first_dates`, `dating_motivation`, `picky`, `rel_status`
- **Form**: P = logistic(base + βa·attraction + βp·politeness(first dates) + βm·motivation − βk·picky − 3·taken)
- **Parameters**: `base` = 1.0 (range 0.0–2.0); `attraction` = 2.0 (range 1.0–3.0); `politeness` = 1.2 (range 0.4–2.0); `motivation` = 0.8 (range 0.3–1.5); `picky` = 0.4 (range 0.0–0.8)
- *Ref*: ProvoStats: 'I accept every first date I'm asked on, just to be polite' — majority agree

### `romance.app` — Dating-app matching

*Evidence: empirical · timescale: daily · delay: none*

- **Target**: `dates_30d`
- **Inputs**: `app_user`, `app_hours`, `app_mutual`, `attractiveness`, `world.app_appeal`
- **Form**: daily match attempt rate = rate × appeal × hours/7; choose best of 10 random seekers on photos + attraction; mutual like → date with P(conversion)
- **Parameters**: `rate` = 0.03 (range 0.01–0.06); `photo_weight` = 0.4 (range 0.1–0.8); `date_conversion` = 0.35 (range 0.15–0.6)
- **Notes**: Apps create romantic opportunity that bypasses physical propinquity; the canonical intervention target "a new dating app becomes popular".
- *Ref*: ProvoStats: ~1/3 of respondents use dating apps (Mutual most common)
- *Ref*: Dating survey: swiping mostly on pictures

### `romance.date` — Date quality and attraction update

*Evidence: empirical · timescale: daily · delay: none*

- **Target**: `edge.attraction_lh`, `edge.attraction_hl`
- **Inputs**: `edge.chemistry`, `social_skill`, `mood`; other inputs: first-date preferences
- **Form**: q = βs·spark + βp·mean(date-type preference) + 0.25·skill + 0.3·(mood sum−1) + ε; attraction += η·(q + 0.3·directed spark)
- **Parameters**: `spark` = 0.45 (range 0.2–0.7); `preference` = 0.3 (range 0.0–0.6); `attraction_update` = 0.07 (range 0.03–0.15)
- *Ref*: Dating survey: ratings of 32 first-date types (ice cream best, gym workout worst)

### `romance.kiss` — Kissing on dates

*Evidence: empirical · timescale: daily · delay: none*

- **Target**: `n_kissed`
- **Inputs**: `edge.attraction_lh`, `edge.dates`, `kiss_first_date_ok`, `scared_initiate_kiss`, `sensation_seeking`
- **Form**: P(first kiss with partner) = logistic(base + βa·min attraction + 0.6·log(dates) + βok·first-date OK − 0.3·scared + 0.3·SS)
- **Parameters**: `base` = -3.23 (range -4–-1.5); `attraction` = 3.0 (range 1.5–4.5); `first_date_ok` = 0.8 (range 0.2–1.4)
- *Ref*: ProvoStats: people kissed by age; 'OK kissing on the first date'
- *Ref*: Dating survey: 'scared to initiate a kiss'

### `romance.ncmo` — Non-committal make-outs

*Evidence: empirical · timescale: daily · delay: none*

- **Target**: `n_ncmo`
- **Inputs**: `ncmo_interest`, `sensation_seeking`, `chastity_commitment`, `edge.attraction_lh`
- **Form**: At gatherings/dances among mutually attracted singles: P = logistic(base + βi·interest + 0.5·SS − βc·(chastity−0.5) + 2·attraction + 0.4·dance)
- **Parameters**: `base` = -1.6 (range -3.5–0); `interest` = 0.9 (range 0.3–1.5); `chastity` = 3.0 (range 1.0–5.0)
- *Ref*: ProvoStats: NCMO counts and interest by sex and church activity

### `romance.progress` — Talking → DTR

*Evidence: calibrated · timescale: daily · delay: none*

- **Target**: `rel_status`
- **Inputs**: `edge.attraction_lh`, `edge.dates`
- **Form**: talking after ≥2 dates with mutual attraction > t; exclusive (DTR) after ≥ n dates and 2+ weeks with mutual attraction > d
- **Parameters**: `talk_threshold` = 0.5 (range 0.3–0.65); `dtr_dates` = 6 (range 3–10); `dtr_threshold` = 0.65 (range 0.45–0.8)

### `romance.ghosting` — Ghosting after one-sided first dates

*Evidence: empirical · timescale: daily · delay: none*

- **Target**: `self_esteem`
- **Inputs**: `edge.attraction_lh`
- **Form**: after a first date where interest is one-sided, P(ghosting) = rate
- **Parameters**: `rate` = 0.35 (range 0.1–0.6)
- *Ref*: Dating survey: ghosting reasons (forgetting, losing interest, avoiding awkwardness)

### `romance.relationship` — Relationship satisfaction

*Evidence: literature · timescale: daily · delay: none*

- **Target**: `relationship_satisfaction`
- **Inputs**: `edge.attraction_lh`, `edge.chemistry`, `faith_belief`, `activity`, `edge.conflict`, `stress`, `agreeableness`
- **Form**: target = logistic(base + 0.9·mean attraction + 0.35·chemistry − βm·religious mismatch − 1.2·conflict − 0.8·(stress−0.3) + 0.2·A); sat ← sat + 0.25·(target − sat)
- **Parameters**: `sat_base` = 0.3 (range -0.5–1.0); `religious_mismatch` = 1.5 (range 0.5–2.5)
- *Ref*: Neff & Karney: external stress spills over into relationship quality

### `romance.breakup` — Breakup / divorce hazard

*Evidence: literature · timescale: daily · delay: none*

- **Target**: `rel_status`
- **Inputs**: `relationship_commitment`, `edge.conflict`; other inputs: religious mismatch
- **Form**: weekly h = logistic(base − βc·commitment + βm·mismatch + 1.5·conflict); ×0.25 engaged; ×married_mult married. Initiator = less-attracted partner.
- **Parameters**: `base` = -2.22 (range -3.8–-1.5); `commitment` = 3.5 (range 2.0–5.0); `religious_mismatch` = 2.0 (range 0.5–3.0); `married_mult` = 0.03 (range 0.01–0.08)
- *Ref*: Rusbult (1980, 1983): investment model of commitment

### `romance.couple_time` — Couple dates per week by stage

*Evidence: calibrated · timescale: daily · delay: none*

- **Target**: `dates_30d`
- **Inputs**: `rel_status`
- **Form**: dates scheduled each week = ⌊rate⌋ + Bernoulli(rate − ⌊rate⌋), on distinct days
- **Parameters**: `talking` = 0.8 (range 0.3–1.5); `dating` = 1.45 (range 0.8–2.2); `engaged` = 1.58 (range 0.8–3.0); `married` = 1.07 (range 0.5–1.4)
- *Ref*: Dating survey: dates per month by relationship stage and church activity

### `romance.engage` — Engagement & wedding timing

*Evidence: empirical · timescale: daily · delay: none*

- **Target**: `rel_status`, `age_at_marriage`
- **Inputs**: `relationship_commitment`, `ideal_months_engaged`, `activity`, `age`, `financial_stress`, `mission_status`
- **Form**: weekly h = logistic(base + βc·commitment + βt·clip((months − ideal)/4) + βa·both active LDS·marriage_norm + age term − 1.8·[man under 20] − 1.2·[LDS man under 21.5 who has not served] − 0.8·financial stress − 1.2·mismatch − 3·[same-sex couple with an active member]); wedding 2.5–4.5 months later for active LDS couples
- **Parameters**: `base` = -5.8 (range -8.0–-4.5); `commitment` = 3.0 (range 1.5–4.5); `timing` = 0.8 (range 0.3–1.5); `active_lds` = 1.2 (range 0.4–2.0)
- *Ref*: Dating & Culture surveys: months dated before engagement (median ≈ 6–8), age at marriage (median ≈ 22)

### `romance.sex` — Premarital sexual activity

*Evidence: empirical · timescale: daily · delay: none*

- **Target**: `n_sex_partners`
- **Inputs**: `chastity_commitment`, `rel_status`, `sensation_seeking`, `self_control`, `living`
- **Form**: weekly h for exclusive unmarried couples = logistic(base + βc·(0.5 − min chastity) + 0.6·engaged + 0.3·log(1+months) + 0.4·SS − 0.5·self-control − 0.4·both in contracted housing)
- **Parameters**: `base` = -5.5 (range -7–-4); `chastity` = 6.0 (range 3–9)
- **Notes**: Belief–behavior discrepancy is explicitly allowed; consequences flow through guilt, repentance or belief change.
- *Ref*: ProvoStats/Dating surveys: sexual partners by relationship status and church activity

### `romance.confession` — Repentance (meeting with a bishop)

*Evidence: empirical · timescale: daily · delay: none*

- **Target**: `guilt`, `temple_recommend`, `chastity_commitment`
- **Inputs**: `religious_identity`, `guilt`, `moral_autonomy`
- **Form**: P(confess within weeks) = logistic(base + 2·identity + 1.5·guilt − 1.2·autonomy) for members with commitment > 0.35
- **Parameters**: `base` = -1.5 (range -3–0)
- *Ref*: Culture & Lifestyle: adult repentance meetings and bishop-experience ratings

### `romance.wedding` — Student weddings fall between semesters

*Evidence: hypothetical · timescale: daily · delay: none*

- **Target**: `married_day`
- **Inputs**: `enrolled`, `engaged_day`
- **Form**: at engagement, with probability break_share a student couple's wedding moves to the next break (late April–August or Christmas) starting within 75 days of the date they would otherwise pick, on a Saturday in its first month
- **Parameters**: `break_share` = 0.7 (range 0.4–0.9)
- **Notes**: Gives weddings the seasonal rhythm of a student town (summer and Christmas peaks) instead of an even spread.
- *Ref*: BYU academic calendar; local practice of marrying between semesters (assumption, not measured here)

## social

### `activity.choice` — Free-time activity choice

*Evidence: calibrated · timescale: block · delay: none*

- **Target**: `activity_now`
- **Inputs**: `fatigue`, `loneliness`, `academic_pressure`, `workouts_week`, `hikes`, `dancing`, `romantic_longing`, `world.temp_f`
- **Form**: Random-utility (Gumbel-max) choice among home / campus / gym / venue / outdoors / dance / visit friend / complex commons; utilities linear in traits, habits and states.
- **Parameters**: `home` = 0.0 (range -0.5–0.5); `withdraw` = 2.5 (range 1.0–4.0); `approach` = 1.8 (range 0.8–3.0)
- **Notes**: Daily/weekly spatial activity patterns built from obligations plus discretionary choice; the source of spatial opportunity.

### `activity.loneliness_response` — Loneliness → approach vs. withdrawal

*Evidence: literature · timescale: daily · delay: none*

- **Target**: `activity_now`
- **Inputs**: `loneliness`, `extraversion`, `social_anxiety`, `neuroticism`
- **Moderators**: `extraversion`, `social_anxiety`, `neuroticism`
- **Form**: approach_share = logistic(b0 + βE·E − βSA·SA − βN·N); loneliness × approach_share raises social choices, loneliness × (1−approach_share) raises staying home.
- **Parameters**: `base` = 0.0 (range -1–1); `extraversion` = 1.0 (range 0.4–1.6); `social_anxiety` = 0.9 (range 0.4–1.5); `neuroticism` = 0.5 (range 0.0–1.0)
- **Notes**: Creates heterogeneous feedback loops — loneliness → withdrawal → fewer encounters → more loneliness for some; loneliness → seeking company → new friends for others.
- *Ref*: Cacioppo & Hawkley (2009) Trends Cogn Sci: loneliness heightens social-threat vigilance and can become self-reinforcing

### `activity.class_attendance` — Class attendance

*Evidence: calibrated · timescale: daily · delay: none*

- **Target**: `class_attendance`
- **Inputs**: `conscientiousness`, `fatigue`, `academic_pressure`, `depressive_episode`
- **Form**: P(attend) = logistic(base + βC·C − βF·fatigue + 0.8·pressure − 0.6·depressed)
- **Parameters**: `base` = 2.2 (range 1.5–3.0); `conscientiousness` = 0.4 (range 0.1–0.8); `fatigue` = 2.0 (range 0.8–3.0)

### `activity.fhe` — FHE group participation

*Evidence: calibrated · timescale: daily · delay: none*

- **Target**: `activity_now`
- **Inputs**: `ward_activity_rate`
- **Form**: Monday evening: P = ward_activity_rate × mult (YSA wards; FHE groups pair a men's and a women's apartment)
- **Parameters**: `attend_mult` = 0.85 (range 0.5–1.0)
- **Applicability**: BYU/YSA wards

### `activity.ward_activity` — Ward activity participation

*Evidence: empirical · timescale: daily · delay: none*

- **Target**: `activity_now`
- **Inputs**: `ward_activity_rate`
- **Form**: One weekday evening per ward: P = ward_activity_rate × mult
- **Parameters**: `attend_mult` = 0.5 (range 0.2–0.9)
- *Ref*: Culture & Lifestyle survey: frequency of attending ward-sponsored activities

### `activity.gathering` — Hosting & attending get-togethers

*Evidence: calibrated · timescale: daily · delay: none*

- **Target**: `activity_now`
- **Inputs**: `extraversion`, `loneliness`, `n_friends`, `fatigue`
- **Form**: P(host) = base[weekday] × exp(0.6·E + 0.8·approach) × [friends≥2]; invitees ~ Poisson(k) friends weighted by closeness, accept = logistic(a + 2·closeness + 0.4·E − 1.5·fatigue + 0.8·approach)
- **Parameters**: `host_weekday` = 0.012 (range 0.005–0.03); `host_friday` = 0.04 (range 0.02–0.08); `host_saturday` = 0.05 (range 0.02–0.1); `host_sunday` = 0.025 (range 0.01–0.05); `invites` = 5 (range 2–9); `accept_base` = -0.5 (range -1.5–0.5)
- **Notes**: Gatherings are hosted in apartments, so friends of the host meet the host's roommates and each other — the engine of triadic closure.
- *Ref*: Calibrated toward ProvoStats 'social events per month' (median ~6)

### `encounter.rate` — Interaction attempts by context

*Evidence: calibrated · timescale: daily · delay: none*

- **Target**: `social_hours_week`
- **Inputs**: `activity_now`
- **Form**: Attempts per person per block ~ Poisson(rate[context] × sociability)
- **Parameters**: `unit` = 1.6 (range 0.8–2.5); `complex` = 0.3 (range 0.1–0.6); `class` = 0.6 (range 0.2–1.2); `ward` = 1.2 (range 0.5–2.0); `fhe` = 2.0 (range 1.0–3.0); `work` = 1.0 (range 0.4–1.6); `gym` = 0.15 (range 0.05–0.4); `venue` = 0.12 (range 0.05–0.3); `gathering` = 2.5 (range 1.5–4.0); `campus` = 0.12 (range 0.05–0.3); `dance` = 1.2 (range 0.5–2.0); `outdoors` = 0.2 (range 0.05–0.5); `club` = 1.1 (range 0.5–1.8); `team` = 1.6 (range 0.8–2.4); `institute` = 0.8 (range 0.3–1.4); `congregation` = 1.0 (range 0.4–1.6)
- **Notes**: Opportunity structure — whom a person can meet depends on where they are.
- *Ref*: Festinger, Schachter & Back (1950): propinquity in student housing
- *Ref*: Kossinets & Watts (2006) Science: shared foci (classes) drive tie formation

### `encounter.sociability` — Sociability multiplier

*Evidence: literature · timescale: daily · delay: none*

- **Target**: `social_hours_week`
- **Inputs**: `extraversion`, `social_anxiety`, `fatigue`, `loneliness`
- **Form**: mult = exp(βE·E − βSA·max(SA,0) + 0.4·approach) × (1 − 0.5·fatigue)
- **Parameters**: `extraversion` = 0.3 (range 0.1–0.5); `social_anxiety` = 0.25 (range 0.0–0.5)

### `encounter.choice` — Partner choice within a context

*Evidence: literature · timescale: daily · delay: none*

- **Target**: `edge.liking`
- **Inputs**: `edge.familiarity`, `edge.liking`, `edge.attraction_lh`, `age`, `school`, `activity`, `politics`, `study_area`
- **Form**: Among 3 randomly encountered co-present people, choose argmax(β_fam·σ(B+1) + β_like·liking + β_sim·similarity + β_attr·attraction(if seeking) + Gumbel)
- **Parameters**: `familiarity` = 1.5 (range 0.5–2.5); `liking` = 1.2 (range 0.4–2.0); `similarity` = 0.8 (range 0.2–1.4); `attraction` = 1.0 (range 0.3–2.0)
- *Ref*: McPherson, Smith-Lovin & Cook (2001) Annu Rev Sociol: homophily
- *Ref*: Zajonc (1968): mere exposure
- *Ref*: Anderson & Lebiere (1998): ACT-R base-level activation

### `encounter.valence` — Interaction quality

*Evidence: hypothetical · timescale: daily · delay: none*

- **Target**: `edge.liking`
- **Inputs**: `edge.chemistry`, `agreeableness`, `social_skill`, `mood`, `edge.liking`; other inputs: similarity
- **Form**: v = base + βc·chemistry + βA·mean(A) + βS·mean(skill) + βm·(mood_i+mood_j−1) + βsim·sim + βl·liking + ε
- **Parameters**: `base` = 0.25 (range 0.0–0.5); `chemistry` = 0.35 (range 0.1–0.6); `agreeableness` = 0.15 (range 0.0–0.3); `social_skill` = 0.15 (range 0.0–0.3); `mood` = 0.4 (range 0.1–0.8); `similarity` = 0.2 (range 0.0–0.5); `liking` = 0.5 (range 0.2–0.8); `noise` = 0.6 (range 0.3–0.9)
- **Notes**: Pair chemistry is persistent and pair-specific, so two similar people can still clash and dissimilar people can click.

### `network.liking` — Liking learns from interactions

*Evidence: literature · timescale: daily · delay: none*

- **Target**: `edge.liking`
- **Inputs**: `edge.n_interactions`
- **Form**: liking ← liking + (1−(1−α)^k)·(tanh(mean valence) − liking)
- **Parameters**: `learning_rate` = 0.12 (range 0.05–0.25)
- *Ref*: Reinforcement-affect model of attraction (Byrne)

### `network.stage` — Friendship stages from time together

*Evidence: literature · timescale: daily · delay: none*

- **Target**: `n_friends`
- **Inputs**: `edge.hours_leisure`, `edge.liking`, `edge.closeness`
- **Form**: casual ≥ 0.55·k·50 h & liking>0.1; friend ≥ 0.55·k·90 h & liking>0.25 & closeness≥0.3; close ≥ 0.55·k·200 h & liking>0.4 & closeness≥0.5 (leisure-weighted hours)
- **Parameters**: `hours_scale` = 1.0 (range 0.5–1.6)
- *Ref*: Hall (2019) J Soc Pers Relat 36(4): ~50 h casual friend, ~90 h friend, >200 h close friend

### `network.closeness` — Closeness growth and decay

*Evidence: literature · timescale: daily · delay: none*

- **Target**: `edge.closeness`
- **Inputs**: `edge.hours_leisure`, `edge.liking`, `edge.last_day`
- **Form**: with contact: c ← c + g·(target − c); without contact for 2+ weeks: c ← c·exp(−7/τ)
- **Parameters**: `growth` = 0.15 (range 0.05–0.3); `decay_days` = 240 (range 90–500)
- *Ref*: Roberts & Dunbar (2011): emotional closeness declines without contact

### `network.forget` — Forgetting weak ties

*Evidence: literature · timescale: daily · delay: none*

- **Target**: `degree`
- **Inputs**: `edge.familiarity`
- **Form**: drop unflagged acquaintance edges when ACT-R activation < threshold
- **Parameters**: `activation` = -3.4 (range -4.5–-2.8)
- *Ref*: Petrov (2006) ICCM: efficient approximation of ACT-R base-level learning

### `encounter.friend_contact` — Deliberate contact with friends

*Evidence: literature · timescale: daily · delay: none*

- **Target**: `close_contact_hours`, `edge.closeness`
- **Inputs**: `extraversion`, `loneliness`, `n_friends`, `edge.closeness`
- **Form**: contacts/day ~ Poisson(rate·exp(0.25·E + 0.6·approach)·(0.6 if married)); friend chosen by closeness (best of 2); in person if <4 km (60%) else mostly remote
- **Parameters**: `rate` = 0.35 (range 0.1–0.7)
- *Ref*: Roberts & Dunbar (2011) Pers Relat: communication frequency sustains emotional closeness
- *Ref*: Kalmijn (2003) Soc Networks: partners/marriage reduce time with friends (dyadic withdrawal)

### `relationship.history` — Relationships are histories, not scores

*Evidence: literature · timescale: daily · delay: none*

- **Target**: `edge.closeness`
- **Inputs**: `edge.disclosure`, `edge.shared`, `edge.hurt`, `edge.liking`, `edge.hours_leisure`
- **Form**: weekly closeness target = 0.12·log(1 + leisure h/10) + 0.35·liking⁺ + β_d·disclosure + β_s·log(1 + shared experiences) − β_h·hurt
- **Parameters**: `disclosure` = 0.15 (range 0.05–0.3); `shared` = 0.02 (range 0.0–0.05); `hurt` = 0.3 (range 0.1–0.6)
- *Ref*: Laurenceau, Barrett & Pietromonaco (1998): intimacy grows from disclosure and perceived responsiveness
- *Ref*: Altman & Taylor (1973): social penetration
- *Ref*: Aron et al. (2000): shared novel activities and closeness

### `relationship.disclosure` — Confiding deepens with closeness and warmth

*Evidence: literature · timescale: daily · delay: none*

- **Target**: `edge.disclosure`
- **Inputs**: `edge.closeness`, `edge.stage`
- **Form**: after warm interactions between friends: d ← d + rate·tanh(valence)·closeness·(1 − d); support-seeking adds more; fades 1%/week without contact
- **Parameters**: `rate` = 0.02 (range 0.005–0.05)
- **Notes**: Disclosure also decides what friends see of each other's real beliefs (mind.pluralistic_ignorance).
- *Ref*: Collins & Miller (1994): disclosure and liking (meta-analysis)

### `relationship.hurt` — Hurt and repair

*Evidence: hypothetical · timescale: daily · delay: none*

- **Target**: `edge.hurt`
- **Inputs**: `edge.liking`
- **Form**: a serious conflict adds +conflict; betrayal (discovered cheating) sets 1; a breakup leaves 0.5 (0.2 for fizzled talking); weekly ×(1 − repair) with warm contact, ×0.98 without; hurt lowers closeness, makes planned get-togethers fall through (60%·hurt) and raises breakup risk (+1.5·hurt)
- **Parameters**: `conflict` = 0.25 (range 0.1–0.5); `repair` = 0.12 (range 0.04–0.25)
- *Ref*: Gottman & Levenson (2000): repair attempts and relationship stability
- *Ref*: Fincham (2000): forgiveness as gradual reduction of hurt-motivated avoidance

### `relationship.introductions` — Friends bring friends (triadic closure)

*Evidence: literature · timescale: daily · delay: none*

- **Target**: `edge.introducer`
- **Inputs**: `edge.stage`
- **Form**: an in-person hangout includes a random friend of the friend with probability rate; the meeting is an interaction with the introducer recorded
- **Parameters**: `rate` = 0.15 (range 0.05–0.5)
- *Ref*: Kossinets & Watts (2006): triadic closure in an evolving university network
- *Ref*: Snijders, van de Bunt & Steglich (2010): transitivity in stochastic actor-oriented models

## whatif

### `whatif.inject` — What-if event (your scenario)

*Evidence: speculative · timescale: daily · delay: none*

- **Target**: `mood`, `stress`, `loneliness`, `anxiety`, `belonging`, `self_esteem`, `guilt`, `fatigue`, `purpose`, `financial_stress`, `academic_pressure`, `romantic_longing`
- **Inputs**: —
- **Form**: an exogenous event injected into a cohort by a What-if; registered or custom effects, appraised and remembered like any other event
- **Notes**: Everything downstream (coping, memories, behavior) is the model's own response.

### `whatif.practice` — What-if practice spreading

*Evidence: speculative · timescale: daily · delay: none*

- **Target**: `mood`
- **Inputs**: `n_friends`
- **Form**: weekly h = 0.05·logistic(base + Σ w·z(trait) + peer·(complex contagion) + nudge); quit hazard; feelings while adopted

### `mood.intervention` — What-if nudge on mood

*Evidence: speculative · timescale: daily · delay: none*

- **Target**: `mood`
- **Inputs**: —
- **Form**: persistent offset × ramp × [in the What-if's population]

### `stress.intervention` — What-if nudge on stress

*Evidence: speculative · timescale: daily · delay: none*

- **Target**: `stress`
- **Inputs**: —
- **Form**: persistent offset × ramp × [in the What-if's population]

### `loneliness.intervention` — What-if nudge on loneliness

*Evidence: speculative · timescale: daily · delay: none*

- **Target**: `loneliness`
- **Inputs**: —
- **Form**: persistent offset × ramp × [in the What-if's population]

### `anxiety.intervention` — What-if nudge on anxiety

*Evidence: speculative · timescale: daily · delay: none*

- **Target**: `anxiety`
- **Inputs**: —
- **Form**: persistent offset × ramp × [in the What-if's population]

### `belonging.intervention` — What-if nudge on belonging

*Evidence: speculative · timescale: daily · delay: none*

- **Target**: `belonging`
- **Inputs**: —
- **Form**: persistent offset × ramp × [in the What-if's population]

### `self_esteem.intervention` — What-if nudge on self esteem

*Evidence: speculative · timescale: daily · delay: none*

- **Target**: `self_esteem`
- **Inputs**: —
- **Form**: persistent offset × ramp × [in the What-if's population]

### `guilt.intervention` — What-if nudge on guilt

*Evidence: speculative · timescale: daily · delay: none*

- **Target**: `guilt`
- **Inputs**: —
- **Form**: persistent offset × ramp × [in the What-if's population]

### `fatigue.intervention` — What-if nudge on fatigue

*Evidence: speculative · timescale: daily · delay: none*

- **Target**: `fatigue`
- **Inputs**: —
- **Form**: persistent offset × ramp × [in the What-if's population]

### `purpose.intervention` — What-if nudge on purpose

*Evidence: speculative · timescale: daily · delay: none*

- **Target**: `purpose`
- **Inputs**: —
- **Form**: persistent offset × ramp × [in the What-if's population]

### `financial_stress.intervention` — What-if nudge on financial stress

*Evidence: speculative · timescale: daily · delay: none*

- **Target**: `financial_stress`
- **Inputs**: —
- **Form**: persistent offset × ramp × [in the What-if's population]

### `academic_pressure.intervention` — What-if nudge on academic pressure

*Evidence: speculative · timescale: daily · delay: none*

- **Target**: `academic_pressure`
- **Inputs**: —
- **Form**: persistent offset × ramp × [in the What-if's population]

### `romantic_longing.intervention` — What-if nudge on romantic longing

*Evidence: speculative · timescale: daily · delay: none*

- **Target**: `romantic_longing`
- **Inputs**: —
- **Form**: persistent offset × ramp × [in the What-if's population]

## Event types

Events push states with decaying effects (half-life in days) and carry causal parent links.

| event | category | salience | effects (var: magnitude, half-life d) | evidence |
|---|---|---|---|---|
| `new_friend` Became friends | social | 0.55 | loneliness: -0.03, 20; belonging: +0.03, 20 | literature |
| `close_friend` Became close friends | social | 0.7 | loneliness: -0.05, 45; mood: +0.03, 20 | literature |
| `friendship_faded` Close friendship faded | social | 0.55 | loneliness: +0.03, 25 | hypothetical |
| `conflict` Interpersonal conflict | social | 0.4 | stress: +0.06, 4; mood: -0.05, 3 | literature |
| `coping_started` Started coping with a hard time | coping | 0.4 |  | structural |
| `coping_ended` A hard stretch eased | coping | 0.35 |  | structural |
| `hosted_gathering` Hosted a get-together | social | 0.35 | belonging: +0.03, 6; mood: +0.02, 2 | hypothetical |
| `asked_out` Asked someone out | romance | 0.3 |  | calibrated |
| `rejected` Romantic rejection | romance | 0.5 | self_esteem: -0.05, 7; mood: -0.05, 4 | literature |
| `first_date` First date | romance | 0.45 | mood: +0.04, 3; romantic_longing: -0.05, 10 | calibrated |
| `date` Date | romance | 0.2 | mood: +0.03, 2; romantic_longing: -0.04, 7 | calibrated |
| `first_kiss_with` Kissed someone new | romance | 0.6 | mood: +0.06, 5; romantic_longing: -0.08, 14; guilt: +0.02, 5 | hypothetical |
| `first_kiss_ever` First kiss ever | romance | 0.9 | mood: +0.1, 10; self_esteem: +0.06, 30 | hypothetical |
| `ncmo` NCMO (non-committal make-out) | romance | 0.55 | mood: +0.04, 2; guilt: +0.07, 7; romantic_longing: +0.02, 7 | hypothetical |
| `kyhv_peak` Made out at Kyhv Peak | romance | 0.65 | mood: +0.05, 3 | observed |
| `talking_started` Started "talking" (mutual interest) | romance | 0.45 | mood: +0.04, 7; romantic_longing: -0.1, 20 | calibrated |
| `relationship_started` Became exclusive (DTR) | romance | 0.85 | mood: +0.08, 21; loneliness: -0.08, 30; romantic_longing: -0.2, 60; self_esteem: +0.04, 30 | literature |
| `breakup_initiated` Ended a relationship | romance | 0.85 | mood: -0.06, 10; guilt: +0.04, 10; stress: +0.04, 7 | literature |
| `breakup_received` Was broken up with | romance | 0.9 | mood: -0.16, 21; loneliness: +0.12, 28; self_esteem: -0.08, 30; romantic_longing: +0.12, 45; stress: +0.06, 10 | literature |
| `engaged` Got engaged | romance | 0.95 | mood: +0.12, 30; purpose: +0.08, 60; stress: +0.04, 40; financial_stress: +0.03, 60 | literature |
| `wedding` Married | romance | 1.0 | mood: +0.14, 120; loneliness: -0.12, 180; romantic_longing: -0.3, 365; purpose: +0.08, 365 | literature |
| `premarital_sex` Premarital sexual activity began | sexuality | 0.85 | guilt: +0.22, 45; anxiety: +0.06, 21; mood: +0.03, 5 | hypothetical |
| `bishop_confession` Met with bishop (repentance) | religion | 0.75 | guilt: -0.15, 30; stress: +0.05, 7; belonging: +0.03, 20 | empirical |
| `ghosted` Was ghosted | romance | 0.35 | self_esteem: -0.03, 5 | empirical |
| `app_match` Matched on a dating app | romance | 0.15 | self_esteem: +0.01, 2 | calibrated |
| `cheating` Cheated on partner | romance | 0.9 | guilt: +0.18, 60 | empirical |
| `pregnancy` Pregnancy announced | family | 0.95 | mood: +0.08, 60; purpose: +0.1, 180; financial_stress: +0.05, 120; fatigue: +0.06, 90 | literature |
| `birth` Child born | family | 1.0 | mood: +0.1, 30; fatigue: +0.22, 120; stress: +0.08, 120; purpose: +0.12, 365; financial_stress: +0.06, 180 | literature |
| `family_crisis` Family crisis back home | family | 0.75 | stress: +0.12, 21; mood: -0.08, 14 | hypothetical |
| `death_in_family` Death in the family | family | 0.95 | mood: -0.18, 45; stress: +0.1, 30; purpose: +0.04, 90 | literature |
| `spiritual_experience` Spiritual experience | religion | 0.6 | purpose: +0.06, 30; mood: +0.04, 7 | hypothetical |
| `faith_challenge` Encountered a faith challenge | religion | 0.55 | anxiety: +0.04, 14; stress: +0.03, 10 | empirical |
| `faith_crisis_start` Faith crisis began | religion | 0.95 | stress: +0.12, 60; purpose: -0.1, 90; anxiety: +0.08, 60; belonging: -0.06, 90 | empirical |
| `faith_renewed` Faith crisis resolved — renewed faith | religion | 0.9 | purpose: +0.1, 90; mood: +0.05, 30 | hypothetical |
| `faith_nuanced` Faith crisis resolved — stayed with nuanced faith | religion | 0.85 | stress: -0.05, 30 | hypothetical |
| `met_missionaries` Started meeting with the missionaries | religion | 0.7 | purpose: +0.03, 30 | hypothetical |
| `baptized` Was baptized | religion | 1.0 | belonging: +0.1, 90; purpose: +0.08, 120; mood: +0.06, 30 | hypothetical |
| `stopped_investigating` Stopped the missionary lessons | religion | 0.5 |  | hypothetical |
| `joined_congregation` Found a congregation | religion | 0.6 | belonging: +0.05, 60 | hypothetical |
| `disaffiliated` Left the Church | religion | 1.0 | stress: +0.08, 90; belonging: -0.08, 120; guilt: -0.06, 60; purpose: -0.04, 120 | hypothetical |
| `resigned_membership` Removed name from Church records | religion | 0.6 |  | hypothetical |
| `stopped_attending` Stopped attending church | religion | 0.75 | belonging: -0.05, 60 | calibrated |
| `returned_to_activity` Returned to church activity | religion | 0.75 | belonging: +0.06, 60; purpose: +0.04, 60 | calibrated |
| `mission_call` Received mission call | religion | 0.9 | purpose: +0.1, 60; mood: +0.08, 14 | calibrated |
| `mission_departure` Left on a mission | religion | 1.0 |  | calibrated |
| `friend_left_on_mission` Friend left on a mission | social | 0.4 | loneliness: +0.03, 30 | hypothetical |
| `mission_return` Returned from mission | religion | 1.0 | purpose: +0.05, 60; loneliness: +0.1, 45; romantic_longing: +0.15, 120; stress: +0.06, 30 | hypothetical |
| `early_return` Returned early from mission | religion | 1.0 | mood: -0.12, 90; self_esteem: -0.1, 120; stress: +0.1, 60 | literature |
| `exam_failure` Bombed an exam / failed a class | academics | 0.55 | academic_pressure: +0.1, 21; self_esteem: -0.05, 21; mood: -0.06, 7 | literature |
| `academic_success` Strong semester (Dean's-list level) | academics | 0.55 | self_esteem: +0.05, 45; purpose: +0.04, 45 | literature |
| `academic_probation` Placed on academic probation | academics | 0.8 | academic_pressure: +0.15, 60; stress: +0.08, 45; self_esteem: -0.06, 60 | calibrated |
| `major_change` Changed major | academics | 0.6 | purpose: +0.03, 60 | calibrated |
| `graduation` Graduated | academics | 1.0 | purpose: +0.08, 90; mood: +0.08, 21; stress: +0.05, 60 | literature |
| `dropout` Left school | academics | 0.9 | purpose: -0.06, 90; stress: +0.05, 45 | calibrated |
| `term_started` New semester began | academics | 0.1 | academic_pressure: +0.05, 20 | calibrated |
| `job_found` Got a job | work | 0.6 | financial_stress: -0.08, 60; purpose: +0.03, 30 | literature |
| `quit_job` Quit a job to focus on school | work | 0.4 | stress: -0.02, 14 | hypothetical |
| `job_lost` Lost job | work | 0.85 | financial_stress: +0.15, 60; mood: -0.08, 30; self_esteem: -0.06, 45 | literature |
| `financial_hardship` Ran out of money | work | 0.75 | stress: +0.08, 30 | calibrated |
| `moved` Moved | housing | 0.65 | stress: +0.05, 10; loneliness: +0.05, 21; belonging: -0.04, 30 | literature |
| `arrival` Arrived in Provo/Orem | housing | 0.9 | loneliness: +0.12, 30; stress: +0.06, 21 | literature |
| `left_area` Left Provo/Orem | housing | 1.0 |  | calibrated |
| `illness` Got sick | health | 0.25 | fatigue: +0.2, 3; mood: -0.05, 3 | calibrated |
| `car_accident` Car accident | health | 0.6 | stress: +0.1, 14; financial_stress: +0.08, 60 | empirical |
| `depressive_episode_start` Depressive episode began | health | 0.9 | mood: -0.15, 60; fatigue: +0.1, 60; purpose: -0.08, 60 | hypothetical |
| `depressive_episode_end` Depressive episode eased | health | 0.7 |  | hypothetical |
| `adopted_practice` Adopted a practice | habits | 0.35 |  | literature |
| `started_coffee` Started drinking coffee | habits | 0.55 | guilt: +0.05, 20 | hypothetical |
| `started_drinking` Started drinking alcohol | habits | 0.65 | guilt: +0.08, 30 | hypothetical |
| `intervention_exposure` Affected by an intervention | intervention | 0.5 |  | calibrated |
| `plan_abandoned` Gave up on a plan | plans | 0.3 | mood: -0.01, 3 | structural |
| `whatif_shock` Felt a what-if | intervention | 0.5 |  | speculative |
| `whatif_practice` Took up a new practice | intervention | 0.25 |  | speculative |
