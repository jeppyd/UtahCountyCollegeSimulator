# Variable catalog

Generated from `ucsim/config/variables/*.yaml` by `scripts/gen_catalogs.py` — do not edit by hand.

296 variables. Evidence levels: **observed** 11, **empirical** 123, **literature** 32, **calibrated** 102, **extrapolated** 7, **hypothetical** 21.

Columns: id · label · type (categories or range) · kind · update cadence · evidence · source · description.

## complex · places_world

| id | label | type | kind | update | evidence | source | description |
|---|---|---|---|---|---|---|---|
| `complex.name` | Name | str | attribute | static | calibrated |  |  |
| `complex.lon` | Longitude | f4 | attribute | static | calibrated |  |  |
| `complex.lat` | Latitude | f4 | attribute | static | calibrated |  |  |
| `complex.units` | Units | i4 | attribute | static | calibrated |  |  |
| `complex.beds` | Beds | i4 | attribute | static | calibrated |  |  |
| `complex.kind` | Kind | cat: byu_dorm, byu_contracted, uvu_area, married, general_apartments, houses, family_neighborhood | attribute | static | calibrated |  |  |
| `complex.location_quality` | Location precision | cat: approximate, synthetic, osm | attribute | static | calibrated |  | How the coordinates were obtained. |

## edge · edges

| id | label | type | kind | update | evidence | source | description |
|---|---|---|---|---|---|---|---|
| `edge.familiarity` | Familiarity (activation) | f4 [-10, 5] | state | event | literature |  | ACT-R base-level activation of the person in the other's memory, B = ln(Σ t_j^−d), computed with Petrov's (2006) hybrid approximation from the interaction count, first and last contact. Drives recognition and the chance of re-interacting. |
| `edge.liking` | Liking | f4 [-1, 1] | state | event | literature |  | Affective evaluation, an exponentially weighted average of interaction valence (reinforcement-affect model). |
| `edge.closeness` | Closeness | f4 [0, 1] | state | event | literature |  | Grows with leisure hours and self-disclosure (liking), decays without contact. |
| `edge.trust` | Trust | f4 [0, 1] | state | event | literature |  | Grows slowly with positive interactions; damaged by conflict, betrayal (cheating) and ghosting. |
| `edge.conflict` | Conflict | f4 [0, 1] | state | event | literature |  | Recent negative interactions (decays). |
| `edge.attraction_lh` | Attraction (lower→higher id) | f4 [-1, 1] | state | event | literature |  | Directed romantic attraction of the lower-id person toward the higher-id person. |
| `edge.attraction_hl` | Attraction (higher→lower id) | f4 [-1, 1] | state | event | literature |  |  |
| `edge.hours` | Hours together | f4 [0, 10000] (hours) | state | event | literature |  | Cumulative interaction hours. |
| `edge.hours_leisure` | Leisure-equivalent hours | f4 [0, 10000] (hours) | state | event | literature |  | Hours weighted by context (leisure 1.0, ward 0.6, class/work 0.3) — friendship forms faster in leisure settings (Hall 2019). |
| `edge.n_interactions` | Interactions | i4 [0, 100000] | state | event | literature |  |  |
| `edge.first_day` | First met (day) | i4 | state | event | literature |  |  |
| `edge.last_day` | Last contact (day) | i4 | state | event | literature |  |  |
| `edge.stage` | Tie stage | u1 [0, 4] | state | event | literature |  |  |
| `edge.flags` | Tie type flags | u4 | state | event | literature |  | Bitmask: roommate, classmate, coworker, ward, fhe, family, dated, romantic, ex, spouse, kissed, ncmo, sexual, app_match, introduced. |
| `edge.origin_ctx` | Where they met | u1 | state | event | literature |  | Context type of first meeting (unit, complex, class, ward, fhe, work, gym, venue, gathering, campus, app, date, family). |
| `edge.origin_place` | Place of first meeting | i4 | state | event | literature |  |  |
| `edge.introducer` | Introduced by | i4 | state | event | literature |  | Mutual friend who hosted the gathering where they met (-1 if none) — triadic closure provenance. |
| `edge.dates` | Dates together | i2 [0, 1000] | state | event | literature |  |  |
| `edge.chemistry` | Pair chemistry | f4 [-3, 3] | state | event | hypothetical |  | Persistent pair-specific compatibility, deterministic in the pair ids and seed (identical across paired universes). |

## person · academics_work

| id | label | type | kind | update | evidence | source | description |
|---|---|---|---|---|---|---|---|
| `school` | School | cat: none, BYU, UVU | structural | event | calibrated |  | Institution currently enrolled at (or most recently, for those on mission/break). |
| `enrolled` | Enrolled this term | bool | structural | event | calibrated |  |  |
| `class_standing` | Class standing | cat: none, freshman, sophomore, junior, senior, graduate | structural | semester | calibrated |  |  |
| `credits_done` | Credits completed | f4 [0, 200] (credits) | structural | semester | calibrated |  |  |
| `credits_term` | Credits this term | f4 [0, 20] (credits) | structural | semester | calibrated |  |  |
| `study_area` | Area of study | cat: Business, Health Sciences, Engineering & Tech, Social Sciences, Natural Sciences, Education, Fine Arts, Humanities, Math & Stats, Communications, Law & Policy, Agriculture & Environment, Undeclared | structural | semester | empirical | college-life, dating |  |
| `major_id` | Major (id) | i2 | structural | semester | observed | BYU majors list 2025-26, UVU academic catalog | Index into the majors catalog; shown by name on profiles. |
| `college` | College | cat: none, Marriott School of Business, Fulton College of Engineering, College of Computational, Mathematical & Physical Sciences, College of Nursing, College of Life Sciences, College of Humanities, Kennedy Center for International Studies, College of Family, Home & Social Sciences, College of Fine Arts & Communications, McKay School of Education, University Advisement Center, Woodbury School of Business, Smith College of Engineering & Technology, School of Education, College of Health & Public Service, College of Science, School of the Arts, University College, College of Humanities & Social Sciences | structural | semester | observed | BYU majors list 2025-26, UVU academic catalog | The college or school of the person's major (real BYU and UVU colleges). |
| `gpa` | GPA (cumulative) | f4 [0, 4] | structural | semester | empirical | provostats |  |
| `gpa_term` | GPA (last term) | f4 [0, 4] | structural | semester | calibrated |  |  |
| `academic_standing` | Academic standing | cat: good, warning, probation, suspended | structural | semester | calibrated |  |  |
| `study_hours` | Study hours / week | f4 [0, 60] (hours/week) | habit | weekly | calibrated |  |  |
| `class_attendance` | Class attendance rate | f4 [0, 1] | habit | weekly | calibrated |  |  |
| `homework_early` | Finishes homework early | bool | habit | static | empirical | college-life |  |
| `cheats_school` | Academic dishonesty frequency | f4 [0, 4] | habit | static | empirical | college-life |  |
| `graduated` | Graduated (in simulation) | bool | structural | event | calibrated |  |  |
| `enroll_day` | First enrollment day | i4 | structural | semester | calibrated |  |  |
| `grad_day` | Graduation day | i4 | structural | event | calibrated |  |  |
| `employed` | Employed | bool | structural | event | calibrated |  |  |
| `employer_id` | Employer | i4 | structural | event | calibrated |  |  |
| `job_type` | Job type | cat: none, campus, food_retail, tech, health, office, sales, trades, teaching, faculty, staff | structural | event | calibrated |  |  |
| `work_hours` | Work hours / week | f4 [0, 70] (hours/week) | structural | semester | empirical | provostats |  |
| `wage` | Hourly wage | f4 [0, 120] (USD/hour) | structural | semester | empirical | college-life |  |
| `monthly_income` | Monthly income (all sources) | f4 [0, 20000] (USD/month) | structural | monthly | calibrated |  |  |
| `parental_support` | Parental support / month | f4 [0, 5000] (USD/month) | structural | semester | calibrated | college-life, provostats | Money from parents (rent/tuition/insurance/car), conditioned on parental income and the College Life "parents pay for" items. |
| `savings` | Savings | f4 [-50000, 200000] (USD) | structural | monthly | calibrated |  |  |
| `debt` | Debt | f4 [0, 300000] (USD) | structural | monthly | calibrated |  |  |
| `rent` | Rent share | f4 [0, 4000] (USD/month) | structural | event | calibrated | college-life |  |
| `rent_burden` | Rent burden | f4 [0, 3] (share of income) | structural | monthly | calibrated |  |  |
| `owns_car` | Owns a car | bool | structural | event | empirical | provostats |  |
| `commute_min` | Commute (minutes) | f4 [0, 90] (minutes) | structural | event | calibrated |  |  |
| `summer_sales` | Has done summer sales | bool | history | event | empirical | provostats |  |
| `ill` | Currently ill | bool | state | event | calibrated |  |  |
| `ill_until` | Illness end day | i4 | structural | semester | calibrated |  |  |
| `home_lon` | Home longitude | f4 | attribute | event | calibrated |  |  |
| `home_lat` | Home latitude | f4 | attribute | event | calibrated |  |  |
| `city` | City of residence | cat: Provo, Orem, Other Utah County | structural | event | calibrated |  |  |
| `neighborhood` | Neighborhood | cat: Other, Brickyard, Carterville, Dixon, Downtown, East Bay, Edgemont, Foothills, Fort Utah, Franklin, Franklin South, Grandview North, Grandview South, Indian Hills, Joaquin, Lakeview North, Lakeview South, Lakewood, Maeser, North Park, North Timpview, Oak Hills, Pleasant View, Provo Bay, Provost, Provost South, Riverbottoms, Rivergrove, Riverside, Rock Canyon, Sherwood Hills, Spring Creek, Sunset, Timp, University, Wasatch, Aspen, Canyon View, Cascade, Cherry Hill, Geneva Heights, Heatheridge, Hillcrest, Lakeridge, Lakeview, Northridge, Orchard (Orem East), Orem North, Orem Park, Orem South, Sharon, Sharon Park, Stonewood, Suncrest, Sunset Heights East, Sunset Heights West, Timpview, Windsor | structural | event | observed | Provo City and Orem City official neighborhood boundaries (scripts/fetch_neighborhoods.py) | Official Provo or Orem neighborhood of the person's home (Other = outside both cities' neighborhood maps). |
| `complex_id` | Housing complex / building | i4 | structural | event | calibrated |  |  |
| `living` | Living situation | cat: dorm, contracted, apartment, house_share, with_parents, married_housing, family_home | structural | event | calibrated |  |  |
| `dist_campus_km` | Distance to campus | f4 [0, 40] (km) | structural | event | calibrated |  |  |
| `loc_lon` | Current longitude | f4 | state | hourly | calibrated |  |  |
| `loc_lat` | Current latitude | f4 | state | hourly | calibrated |  |  |
| `activity_now` | Current activity | cat: home, class, work, church, campus, gym, gathering, date, venue, outdoors, ward_activity, away, club | state | hourly | calibrated |  |  |

## person · dating

| id | label | type | kind | update | evidence | source | description |
|---|---|---|---|---|---|---|---|
| `rel_status` | Relationship status | cat: single, talking, dating, engaged, married, divorced | structural | event | calibrated | provostats, institutional targets | "talking" = mutually interested and going on dates; "dating" = exclusive (post-DTR). |
| `partner_id` | Partner | i4 [0, 4] | structural | event | empirical | dating |  |
| `rel_start_day` | Relationship start day | i4 [0, 4] | structural | event | empirical | dating |  |
| `engaged_day` | Engagement day | i4 [0, 4] | preference | event | empirical | dating |  |
| `married_day` | Wedding day | i4 [0, 4] | preference | event | empirical | dating |  |
| `age_at_marriage` | Age at marriage | f4 [17, 60] (years) | history | event | empirical | dating | Age at (first) marriage, if married. NaN if never married. |
| `n_relationships` | Exclusive relationships (lifetime) | i2 [0, 25] | history | event | empirical | provostats |  |
| `n_breakups` | Breakups (in simulation) | i2 [0, 25] | history | event | calibrated | dating |  |
| `dating_propensity` | Dating propensity | f4 [0, 30] (dates/month) | trait | static | empirical | provostats | Baseline dates per month when single, from reported dating frequency. |
| `dates_30d` | Dates (last 30 days) | f4 [0, 30] (dates) | habit | daily | calibrated | dating |  |
| `dates_total` | Dates (in simulation) | i2 [0, 500] | history | event | calibrated | dating |  |
| `first_dates_total` | First dates (in simulation) | i2 [0, 300] | history | event | calibrated | dating |  |
| `rejections_recent` | Recent rejections (decaying) | f4 [0, 10] | state | daily | hypothetical | dating | Exponentially decaying count of recent romantic rejections; feeds dating confidence non-linearly. |
| `app_user` | Uses dating apps | bool [0, 4] | habit | monthly | empirical | dating, provostats |  |
| `app_hours` | Dating-app hours / week | f4 [0, 30] (hours/week) | habit | monthly | empirical | provostats |  |
| `app_mutual` | Uses Mutual | bool [0, 4] | habit | monthly | empirical | provostats |  |
| `accepts_first_dates` | Accepts every first date | f4 [0, 4] | preference | static | empirical | provostats |  |
| `men_first_move` | Men should make the first move | f4 [0, 4] | preference | static | empirical | dating |  |
| `picky` | Picky | f4 [0, 4] | preference | static | empirical | dating |  |
| `wants_relationship` | Wants a relationship | f4 [0, 4] | preference | static | empirical | dating |  |
| `asks_for_numbers` | Asks for numbers | f4 [0, 4] | preference | static | empirical | dating |  |
| `scared_initiate_kiss` | Scared to initiate a kiss | f4 [0, 4] | preference | static | empirical | dating |  |
| `min_height_req` | Minimum partner height | f4 [56, 78] (inches) | preference | static | empirical | provostats, dating | Minimum height required in a male partner (women attracted to men). |
| `max_older` | Max years older to date | f4 [0, 30] (years) | preference | static | empirical | dating |  |
| `max_younger` | Max years younger to date | f4 [0, 30] (years) | preference | static | empirical | dating |  |
| `imp_spirituality` | Importance of partner spirituality | f4 [0, 5] | preference | static | empirical | dating | Importance rank of spirituality/faithfulness among six partner qualities (5 = top). |
| `imp_physical` | Importance of physical attractiveness | f4 [0, 5] | preference | static | empirical | dating |  |
| `imp_personality` | Importance of personality/humor | f4 [0, 5] | preference | static | empirical | dating |  |
| `imp_shared_interests` | Importance of shared interests | f4 [0, 5] | preference | static | empirical | dating | Ranked LOWEST on average of six partner qualities — the empirical basis for shared hobbies only nudging compatibility. |
| `prefers_rm` | Prefers returned missionaries | f4 [0, 4] | preference | static | empirical | dating |  |
| `waiting_for_missionary` | Waiting for a missionary | bool [0, 4] | structural | event | empirical | provostats | In a relationship with someone currently serving a mission. |
| `dating_motivation` | Dating motivation | f4 [0, 1] | state | daily | calibrated | dating | Current drive to pursue dating (wants relationship, age/marriage norms, RM status, confidence, longing, availability). |
| `relationship_satisfaction` | Relationship satisfaction | f4 [0, 1] | state | weekly | empirical | culture-lifestyle | Satisfaction in current exclusive relationship/marriage (NaN when none). |
| `relationship_commitment` | Relationship commitment | f4 [0, 1] | state | weekly | literature | dating | Rusbult investment-model commitment (satisfaction + investment − alternatives). |

## person · demographics

| id | label | type | kind | update | evidence | source | description |
|---|---|---|---|---|---|---|---|
| `age` | Age | f4 [16, 75] (years) | attribute | daily | empirical | provostats | Age in years, derived from birth day and simulation date. |
| `birth_day` | Birth day (sim day index) | i4 | attribute | static | observed |  | Day index of birth relative to simulation start (negative). |
| `sex` | Sex | cat: F, M | attribute | static | observed | provostats, institutional targets | Sex (survey item "What is your sex?"). Respondents outside M/F were too few for a stable model and are not represented in v1 — a known limitation. |
| `orientation` | Sexual orientation | cat: straight, bi, gay, asexual, other | attribute | static | empirical | provostats | Self-identified sexual orientation; drives the romantic-attraction compatibility mask. |
| `ethnicity` | Ethnicity | cat: White, Hispanic, Asian, Black, Pacific Islander, Native American, Other | attribute | static | empirical | provostats | Self-described ethnicity. Used only for homophily/composition analysis; no behavioral rules key on it except a weak, adjustable dating-homophily term. |
| `origin_region` | Home region | cat: Utah, Mountain West, West Coast, Other US, International | attribute | static | empirical | provostats, dating, culture-lifestyle | Where the person grew up ("homeland"). |
| `parent_income` | Parental income (childhood SES) | u1 [0, 11] | attribute | static | empirical | provostats | Parents' annual income bracket — proxy for childhood socioeconomic background; shapes parental financial support. |
| `family_structure` | Family of origin | cat: nuclear, blended, single_parent, other | attribute | static | empirical | college-life, culture-lifestyle | Family structure growing up. |
| `parents_divorced` | Parents divorced | bool | attribute | static | empirical | culture-lifestyle |  |
| `family_local` | Family lives in Utah County | bool | attribute | static | calibrated |  | Parents live locally (Utah-raised students more likely); enables weekend family visits, living at home, family religious expectation. |
| `languages` | Languages spoken | u1 [1, 6] | attribute | static | empirical | provostats |  |
| `height_in` | Height | f4 [56, 82] (inches) | attribute | static | empirical | provostats, dating | Height. Matters because many women report a minimum-height requirement for partners (Dating & ProvoStats surveys). |
| `weight_lb` | Weight | f4 [80, 420] (lb) | attribute | static | extrapolated | CDC NHANES adult BMI distributions (approximate), Utah adult obesity below the US average | Body weight. Derived from BMI and height. |
| `bmi` | Body-mass index | f4 [15, 55] (kg/m²) | attribute | static | extrapolated | CDC NHANES (approximate) | Body-mass index. Feeds weakly into perceived attractiveness (see attractiveness). |
| `body_build` | Build | cat: slender, average, athletic, heavier | attribute | static | hypothetical |  | Plain-language body type for profiles and filters. |
| `hair_color` | Hair color | cat: black, dark_brown, light_brown, blonde, red, gray | attribute | static | extrapolated |  | Descriptive only; does not drive behavior in the model. |
| `eye_color` | Eye color | cat: brown, hazel, green, blue, gray | attribute | static | extrapolated |  | Descriptive only; does not drive behavior in the model. |
| `role` | Primary role | cat: byu_student, uvu_student, young_adult, spouse, faculty, staff, community | attribute | event | calibrated |  | Primary structural role in the ecosystem. |
| `present` | Present in Provo/Orem | bool | attribute | event | observed |  | True while the person is physically part of the simulated area (false before arrival, while serving a mission, after leaving). |
| `arrival_day` | Arrival day | i4 | attribute | static | observed |  | Day the person enters the simulated area (pre-generated cohorts arrive on schedule). |
| `departure_day` | Departure day | i4 | attribute | event | observed |  | Day the person left the area permanently (graduation, move away), -1 if never. |
| `household_id` | Household | i4 | attribute | event | observed |  | Household identifier (roommates or family). |
| `unit_id` | Housing unit | i4 | attribute | event | observed |  |  |
| `children` | Children | u1 [0, 10] | structural | event | calibrated | culture-lifestyle, external fertility literature | Number of children (children are household attributes, not agents, in v1). |
| `pregnant` | Pregnant (household) | bool | attribute | event | calibrated |  | Expecting a child (set for both spouses in a married couple). |
| `due_day` | Due day | i4 | attribute | static | observed |  |  |

## person · habits_interests

| id | label | type | kind | update | evidence | source | description |
|---|---|---|---|---|---|---|---|
| `sleep_hours` | Sleep (hours/night) | f4 [3, 12] (hours) | habit | daily | empirical | provostats |  |
| `workouts_week` | Workouts / week | f4 [0, 14] | habit | weekly | empirical | provostats |  |
| `social_media_hours` | Social media (hours/day) | f4 [0, 14] | habit | weekly | empirical | college-life |  |
| `soda_shop_week` | Soda-shop visits / week | f4 [0, 14] | habit | weekly | empirical | provostats | Swig/Sodalicious-type dirty-soda shop visits — a Utah County social ritual and casual date venue. |
| `social_events_month` | Social events / month (propensity) | f4 [0, 40] | habit | weekly | empirical | provostats |  |
| `coffee` | Coffee use | u1 [0, 3] | habit | monthly | empirical | culture-lifestyle | Coffee consumption (prohibited by the Word of Wisdom as currently taught). Peer-influenced; a canonical intervention target. |
| `tea` | Tea use | u1 [0, 3] | habit | monthly | empirical | culture-lifestyle |  |
| `alcohol` | Alcohol use | u1 [0, 3] | habit | monthly | empirical | culture-lifestyle |  |
| `r_movies` | R-rated movies | u1 [0, 3] | habit | monthly | empirical | culture-lifestyle |  |
| `dancing` | Goes dancing | u1 [0, 3] | habit | weekly | empirical | college-life | Country/latin social dancing (e.g., Peak Nights, Tippin' Point, Grove Station) — a major singles mixing context. |
| `hikes` | Hiking | bool | habit | static | empirical | college-life |  |
| `gaming` | Video gaming | bool | habit | static | empirical | college-life |  |
| `sports` | Sports | bool | habit | static | empirical | college-life |  |
| `music_maker` | Plays music / sings | bool | habit | static | empirical | college-life |  |
| `reading` | Reading | bool | habit | static | empirical | college-life |  |
| `cooking` | Cooking/baking | bool | habit | static | empirical | college-life |  |
| `outdoors` | Camping/climbing | bool | habit | static | empirical | college-life |  |
| `arts` | Art/photo/writing | bool | habit | static | empirical | college-life |  |
| `swiftie` | Swiftie | bool | habit | static | empirical | college-life, dating |  |
| `pickleball` | Plays pickleball | bool | habit | weekly | hypothetical |  | Example diffusing cultural practice (complex contagion through friend networks). Seeded small at start. |

## person · personality

| id | label | type | kind | update | evidence | source | description |
|---|---|---|---|---|---|---|---|
| `extraversion` | Extraversion | f4 [-3.5, 3.5] (z) | trait | yearly | empirical | college-life, van der Linden et al. 2010 | Big Five extraversion — sociability, assertiveness, positive emotionality. Raises the *need* for social contact as well as the rate of initiating it, so extraverts can still be lonely. |
| `agreeableness` | Agreeableness | f4 [-3.5, 3.5] (z) | trait | yearly | literature |  | Warmth, cooperation, trust. Raises interaction valence and lowers conflict. |
| `conscientiousness` | Conscientiousness | f4 [-3.5, 3.5] (z) | trait | yearly | literature | college-life, provostats | Organization, diligence, self-discipline. Drives study, class attendance, GPA, habit persistence. |
| `neuroticism` | Neuroticism | f4 [-3.5, 3.5] (z) | trait | yearly | literature | college-life | Negative emotionality. Raises baseline stress/anxiety and amplifies negative life-event effects. |
| `openness` | Openness | f4 [-3.5, 3.5] (z) | trait | yearly | literature |  | Openness to experience. Linked to liberal attitudes and to belief change susceptibility. |
| `sensation_seeking` | Sensation seeking | f4 [-3.5, 3.5] (z) | trait | yearly | empirical | provostats | Novelty/thrill seeking. Raises risky romantic/sexual behavior and NCMO propensity. |
| `self_control` | Self-control | f4 [-3.5, 3.5] (z) | trait | yearly | literature |  | Ability to align behavior with goals; moderates belief–behavior discrepancy. |
| `rejection_sensitivity` | Rejection sensitivity | f4 [-3.5, 3.5] (z) | trait | yearly | literature | dating | Anxious expectation of rejection; lowers asking-out rates and amplifies rejection effects. |
| `attachment_anxiety` | Attachment anxiety | f4 [-3.5, 3.5] (z) | trait | yearly | literature |  | Fear of abandonment in close relationships. Amplifies breakup distress (Sbarra 2006). |
| `attachment_avoidance` | Attachment avoidance | f4 [-3.5, 3.5] (z) | trait | yearly | literature |  | Discomfort with closeness. Slows relationship progression; dampens breakup distress. |
| `social_anxiety` | Social anxiety | f4 [-3.5, 3.5] (z) | trait | yearly | literature |  | Fear of social evaluation. Lowers interaction initiation and raises the withdrawal response to loneliness. |
| `conformity` | Conformity | f4 [-3.5, 3.5] (z) | trait | yearly | hypothetical |  | Susceptibility to perceived norms (peer influence weight). |
| `empathy` | Empathy | f4 [-3.5, 3.5] (z) | trait | yearly | literature |  | Emotional attunement; raises friendship closeness growth and emotional contagion. |
| `attractiveness` | Physical attractiveness (as perceived by others) | f4 [-3.5, 3.5] (z) | trait | yearly | hypothetical |  | Latent mate-appeal component shared across observers. Most romantic attraction in the model is pair-specific (idiosyncratic), consistent with evidence that desire is poorly predicted by individual traits (Joel, Eastwick & Finkel 2017). |
| `academic_ability` | Academic ability | f4 [-3.5, 3.5] (z) | trait | yearly | calibrated | provostats | Latent academic aptitude used in GPA production. |
| `social_skill` | Social skill | f4 [-3.5, 3.5] (z) | trait | yearly | hypothetical |  | Skill at making interactions go well; raises interaction valence. |

## person · preferences_dates

| id | label | type | kind | update | evidence | source | description |
|---|---|---|---|---|---|---|---|
| `fd_ice_cream` | First date pref: ice cream | u1 [0, 4] | preference | static | empirical | dating |  |
| `fd_restaurant` | First date pref: restaurant | u1 [0, 4] | preference | static | empirical | dating |  |
| `fd_hike` | First date pref: hike | u1 [0, 4] | preference | static | empirical | dating |  |
| `fd_board_games` | First date pref: board games | u1 [0, 4] | preference | static | empirical | dating |  |
| `fd_cook_together` | First date pref: cook together | u1 [0, 4] | preference | static | empirical | dating |  |
| `fd_movie_theater` | First date pref: movie theater | u1 [0, 4] | preference | static | empirical | dating |  |
| `fd_movie_apartment` | First date pref: movie at apartment | u1 [0, 4] | preference | static | empirical | dating |  |
| `fd_concert` | First date pref: concert | u1 [0, 4] | preference | static | empirical | dating |  |
| `fd_museum` | First date pref: museum | u1 [0, 4] | preference | static | empirical | dating |  |
| `fd_picnic` | First date pref: picnic | u1 [0, 4] | preference | static | empirical | dating |  |
| `fd_pickleball` | First date pref: pickleball | u1 [0, 4] | preference | static | empirical | dating |  |
| `fd_rock_climbing` | First date pref: rock climbing | u1 [0, 4] | preference | static | empirical | dating |  |
| `fd_soda_shop` | First date pref: soda shop | u1 [0, 4] | preference | static | empirical | dating |  |
| `fd_sports_game` | First date pref: sports game | u1 [0, 4] | preference | static | empirical | dating |  |
| `fd_stargazing` | First date pref: stargazing | u1 [0, 4] | preference | static | empirical | dating |  |
| `fd_video_games` | First date pref: video games | u1 [0, 4] | preference | static | empirical | dating |  |
| `fd_gym` | First date pref: gym workout | u1 [0, 4] | preference | static | empirical | dating |  |
| `fd_makeout` | First date pref: make out | u1 [0, 4] | preference | static | empirical | dating |  |

## person · religion

| id | label | type | kind | update | evidence | source | description |
|---|---|---|---|---|---|---|---|
| `lds_member` | LDS member | bool [0, 1] | attribute | event | calibrated | provostats, institutional targets | Current membership in The Church of Jesus Christ of Latter-day Saints. |
| `raised_lds` | Raised LDS | bool [0, 1] | attribute | static | empirical | culture-lifestyle |  |
| `affiliation` | Religious affiliation | cat: Latter-day Saint, Catholic, Protestant, Other Christian, Muslim, Other faith, Nonreligious | attribute | event | extrapolated | assumption informed by PRRI American Values Atlas (Utah) | Current religious identity. Non-LDS shares are assumptions informed by Utah-wide surveys (about half of non-LDS young adults nonreligious); Hispanic students lean Catholic; former members mostly nonreligious. |
| `own_religiosity` | Importance of own faith (non-LDS) | f4 [0, 1] | belief | weekly | hypothetical | culture-lifestyle | How much a non-LDS person's own religion matters to them (0 for the nonreligious). Drives service attendance and interfaith dating friction. |
| `congregation_id` | Congregation (non-LDS) | i4 [0, 1] | state | event | empirical | culture-lifestyle | Non-LDS congregation the person attends (-1 none): real Catholic, Protestant and other congregations from UGRC and OpenStreetMap. |
| `service_attend` | Attends own services (8-wk) | f4 [0, 1] | habit | weekly | hypothetical | culture-lifestyle | Rolling share of weeks a non-LDS person attended their own congregation. |
| `outsider` | Feels like a religious outsider | f4 [0, 1] | state | weekly | hypothetical | culture-lifestyle | Feeling of being outside Utah County's LDS mainstream: rises with mostly-LDS friends and roommates and with being proselytized; falls with friends who share one's outlook and a faith or secular community. Applies to non-members and to members who have stepped away. |
| `investigating` | Meeting with missionaries | bool [0, 1] | state | event | hypothetical | culture-lifestyle | A non-member currently taking the missionary lessons (usually introduced by LDS friends or a partner). |
| `converted` | Joined the Church here | bool [0, 1] | history | event | hypothetical | culture-lifestyle | Baptized during the simulation. |
| `activity` | Church activity | cat: non_member, inactive, less_active, active | habit | weekly | empirical | provostats | Activity category derived from the rolling sacrament-attendance rate (≥0.6 active, ≥0.15 less active). |
| `faith_belief` | Belief in doctrine | f4 [0, 1] | belief | weekly | empirical | culture-lifestyle, provostats | Strength of belief in core church doctrine (latent). Updated weekly by social influence, spiritual experiences, faith challenges and belief–behavior dissonance. |
| `faith_certainty` | Religious certainty | f4 [0, 1] | belief | weekly | calibrated | culture-lifestyle | Confidence in one's beliefs (distinct from belief level). Low certainty increases susceptibility to social influence. |
| `religious_identity` | Religious identity strength | f4 [0, 1] | belief | weekly | calibrated | culture-lifestyle | How central being a Latter-day Saint is to self-concept; slows disaffiliation even when belief falls ("physically in, mentally out" pathway). |
| `institutional_trust` | Institutional trust | f4 [0, 1] | belief | weekly | calibrated | culture-lifestyle | Trust in church leadership/institutions. Moved by policy announcements and bishop experiences. |
| `orthodoxy` | Doctrinal orthodoxy | f4 [0, 1] | belief | weekly | empirical | culture-lifestyle | Composite agreement with specific teachings (plural marriage divine, no women's priesthood, no expected same-sex-marriage policy change, R-movies wrong). |
| `moral_autonomy` | Moral autonomy | f4 [0, 1] | belief | weekly | empirical | culture-lifestyle | Agreement that it is okay to break church standards if it feels internally acceptable. Moderates guilt and the dissonance pathway. |
| `practice_habit` | Practice habit strength | f4 [0, 1] | habit | weekly | literature | culture-lifestyle | Automaticity of weekly church attendance (habit formation, Lally et al. 2010). Grows with repetition, decays slowly with absence. |
| `attend_rate` | Sacrament attendance (8-wk) | f4 [0, 1] | habit | weekly | empirical | culture-lifestyle | Rolling share of Sundays attended (8-week EWMA). |
| `private_practice` | Private devotion | f4 [0, 1] | habit | weekly | empirical | culture-lifestyle | Composite of prayer and personal scripture study frequency. |
| `scripture_minutes` | Scripture study (min/day) | f4 [0, 120] (minutes/day) | habit | weekly | empirical | culture-lifestyle |  |
| `temple_recommend` | Temple recommend | bool [0, 1] | attribute | event | empirical | culture-lifestyle |  |
| `temple_per_year` | Temple visits / year | f4 [0, 150] (visits/year) | habit | weekly | empirical | culture-lifestyle |  |
| `garments` | Garment wearing (endowed) | u1 [0, 4] | habit | weekly | empirical | culture-lifestyle |  |
| `ward_activity_rate` | Ward-activity participation | f4 [0, 1] | habit | weekly | empirical | culture-lifestyle | Probability of attending ward activities/FHE when available. |
| `mission_status` | Mission status | cat: none, serving, returned, early_returned | structural | event | empirical | provostats | Full-time mission status. Serving missionaries leave the area (men 24 months, women 18 months). |
| `mission_foreign` | Served foreign mission | bool [0, 1] | attribute | event | empirical | provostats |  |
| `faith_crisis` | In faith crisis | bool [0, 1] | state | event | empirical | culture-lifestyle | Currently experiencing a faith crisis (onset when certainty is low and belief is falling; resolves into renewal, nuanced continuation, or disaffiliation). |
| `struggled_faith` | Has struggled with faith | bool [0, 1] | history | event | empirical | culture-lifestyle |  |
| `history_struggle` | Church-history struggle | f4 [0, 1] | belief | weekly | empirical | culture-lifestyle | Difficulty reconciling church history with faith. |
| `lgbtq_tension` | LGBTQ–faith tension | f4 [0, 1] | belief | weekly | empirical | culture-lifestyle | Difficulty reconciling sexual-minority identity with faith (sexual-minority members only); a minority-stress pathway (Meyer 2003). |
| `family_expectation` | Family religious expectation | f4 [0, 1] | belief | weekly | hypothetical | culture-lifestyle | Perceived expectation from family to remain active (higher for Utah-raised, raised-LDS, local family). |
| `perceived_norm` | Perceived religiosity norm | f4 [0, 1] | belief | weekly | literature | culture-lifestyle | Closeness-weighted mean attendance of one's network (roommates, friends, ward) — the local norm the person perceives. |
| `bishop_meetings` | Adult repentance meetings | u1 [0, 10] | history | event | empirical | culture-lifestyle | Count of adult meetings with a bishop as part of a repentance process. |
| `ward_id` | Ward | i4 [0, 1] | structural | event | empirical | culture-lifestyle |  |
| `plans_to_leave` | Plans to leave church | f4 [0, 4] | belief | weekly | empirical | culture-lifestyle |  |

## person · social_emotion

| id | label | type | kind | update | evidence | source | description |
|---|---|---|---|---|---|---|---|
| `n_friends` | Friends | i2 [0, 200] | derived | weekly | calibrated |  | Ties at stage ≥ friend (accumulated ~80+ leisure-equivalent hours with mutual liking; after Hall 2019). |
| `n_groups` | Clubs, teams & classes joined | u1 [0, 3] | state | semester | calibrated |  | How many weekly groups the person belongs to: a campus club, an intramural team, an institute class (0-3). |
| `club_id` | Club | i4 [0, 1] | state | semester | calibrated |  | Campus club the person attends weekly (-1 none). Joining depends on extraversion and conscientiousness; less likely when married, parenting or working long hours. |
| `team_id` | Intramural team | i4 [0, 1] | state | semester | calibrated |  | Intramural sports team (-1 none). BYU intramurals are large (~20% of students); fitness and extraversion raise joining. |
| `institute_class` | Institute class | i4 [0, 1] | state | semester | hypothetical |  | Weekly Institute of Religion class at the Orem Institute next to UVU (-1 none): UVU Latter-day Saint students and young single adults. BYU students take religion classes on campus instead. |
| `n_close_friends` | Close friends | i2 [0, 50] | derived | weekly | calibrated |  | Ties at stage close friend (~200+ hours, high closeness). |
| `n_acquaintances` | Acquaintances | i2 [0, 2000] | derived | weekly | calibrated |  |  |
| `degree` | Network degree | i2 [0, 3000] | derived | weekly | calibrated |  | Number of people the person recognizes (any tie with activation above threshold). |
| `new_friends_90d` | New friends (90 days) | i2 [0, 50] | derived | weekly | calibrated |  |  |
| `social_hours_week` | Social hours / week | f4 [0, 80] (hours/week) | derived | daily | calibrated |  | Exponentially smoothed weekly hours of social interaction (all contexts). |
| `close_contact_hours` | Close-contact hours / week | f4 [0, 60] (hours/week) | derived | daily | calibrated |  | Smoothed weekly hours with friends, partner and well-liked roommates — the input to loneliness. |
| `roommate_cohesion` | Roommate cohesion | f4 [0, 1] | derived | weekly | calibrated |  | Mean liking among co-resident household members. |
| `ward_belonging` | Ward belonging | f4 [0, 1] | state | weekly | calibrated |  | Sense of belonging in one's congregation (ward friends, attendance, callings, fit). |
| `mood` | Mood (happiness) | f4 [0, 1] | state | daily | calibrated |  | Daily positive affect. Composed of a trait set-point plus mechanism terms (loneliness, stress, relationships, purpose, sleep, contagion…) plus decaying event effects plus AR(1) noise. |
| `stress` | Stress | f4 [0, 1] | state | daily | calibrated |  |  |
| `loneliness` | Loneliness | f4 [0, 1] | state | daily | calibrated |  | Perceived social isolation — a function of contact relative to one's own need, not of contact alone. |
| `anxiety` | Anxiety | f4 [0, 1] | state | daily | calibrated |  |  |
| `belonging` | Belonging | f4 [0, 1] | state | daily | calibrated |  |  |
| `self_esteem` | Confidence / self-esteem | f4 [0, 1] | state | daily | calibrated |  |  |
| `guilt` | Guilt | f4 [0, 1] | state | daily | calibrated |  | Moral/religious guilt; rises with standard violations in proportion to the person's own commitment, falls with repentance or belief change. |
| `fatigue` | Fatigue | f4 [0, 1] | state | daily | calibrated |  |  |
| `purpose` | Sense of purpose | f4 [0, 1] | state | daily | calibrated |  |  |
| `financial_stress` | Financial stress | f4 [0, 1] | state | daily | calibrated |  | Non-linear in savings buffer (manageable at moderate strain, sharply worse below ~1 month of expenses). |
| `academic_pressure` | Academic pressure | f4 [0, 1] | state | daily | calibrated |  |  |
| `romantic_longing` | Romantic longing | f4 [0, 1] | state | daily | hypothetical |  | Unmet desire for romance/intimacy (single and wanting a relationship; rises with age-graded marriage norms). Captures what the brief calls romantic/sexual frustration. Hypothetical construct. |
| `life_satisfaction` | Life satisfaction | f4 [0, 10] | state | monthly | calibrated |  | Slow-moving evaluative wellbeing (monthly average of mood, purpose, relationship and financial security). |
| `mh_anxiety` | Anxiety (self-reported condition) | bool [0, 1] | attribute | static | empirical | college-life, dating |  |
| `mh_depression` | Depression (self-reported condition) | bool [0, 1] | attribute | static | empirical | college-life, dating |  |
| `mh_adhd` | ADHD (self-reported) | bool [0, 1] | attribute | static | empirical | college-life |  |
| `depressive_episode` | Depressive episode | bool [0, 1] | state | event | hypothetical |  | Currently in a depressive episode (onset hazard rises steeply with sustained low mood and high loneliness/stress, moderated by vulnerability). |

## person · values_sexuality

| id | label | type | kind | update | evidence | source | description |
|---|---|---|---|---|---|---|---|
| `politics` | Political orientation | u1 [0, 4] | belief | yearly | empirical | provostats |  |
| `traditional_roles` | Traditional gender roles | f4 [0, 4] | belief | yearly | empirical | culture-lifestyle | Agreement that, where possible, wives stay home with kids and husbands provide. |
| `att_gay_marriage_legal` | Supports legal same-sex marriage | f4 [0, 4] | belief | yearly | empirical | college-life |  |
| `expects_ssm_change` | Expects church SSM policy change | f4 [0, 4] | belief | yearly | empirical | culture-lifestyle |  |
| `supports_women_priesthood` | Supports women holding priesthood | f4 [0, 4] | belief | yearly | empirical | culture-lifestyle |  |
| `kids_wanted` | Children wanted | f4 [0, 12] (children) | belief | yearly | empirical | dating |  |
| `ideal_months_engaged` | Ideal months dating before engagement | f4 [0, 60] (months) | belief | yearly | empirical | dating |  |
| `future_confidence` | Confidence in society's future | f4 [0, 4] | belief | yearly | empirical | college-life |  |
| `chastity_commitment` | Chastity commitment | f4 [0, 1] | belief | yearly | calibrated |  | Personal commitment to the law of chastity (latent; derived from orthodoxy, activity, modesty norms). |
| `ncmo_interest` | Interest in NCMOs | f4 [0, 4] | preference | yearly | empirical | provostats | "I am interested in having NCMOs" (non-committal make-outs). |
| `kiss_first_date_ok` | OK kissing on a first date | f4 [0, 4] | preference | yearly | empirical | provostats |  |
| `n_kissed` | People kissed (lifetime) | i2 [0, 150] (people) | history | event | empirical | provostats |  |
| `n_ncmo` | NCMO partners (lifetime) | i2 [0, 150] (people) | history | event | empirical | provostats |  |
| `n_sex_partners` | Sexual partners (lifetime) | i2 [0, 60] (people) | history | event | empirical | provostats |  |
| `premarital_sex_current` | Sexually active (unmarried relationship) | bool [0, 4] | state | event | calibrated |  | Currently sexually active in an unmarried relationship. |
| `porn_use` | Pornography use | u1 [0, 3] | habit | monthly | extrapolated |  | Pornography-use frequency. NOT measured in the supplied surveys — initialized from broad literature prevalence by sex and adjusted by religiosity; treat as extrapolated. |
| `porn_incongruence` | Moral incongruence (porn) | f4 [0, 1] | state | weekly | literature |  | Distress from use that conflicts with one's moral beliefs (moral incongruence model; Grubbs et al. 2019). Feeds guilt and faith dissonance. |
| `made_out_kyhv_peak` | Made out at Kyhv Peak | bool [0, 4] | history | event | empirical | provostats | A Provo cultural landmark (the overlook was renamed Kyhv Peak in 2022). ~14% of ProvoStats respondents said yes. |
| `ever_cheated` | Has cheated on a partner | bool [0, 4] | history | event | empirical | provostats |  |
| `ever_cheated_on` | Has been cheated on | bool [0, 4] | history | event | empirical | provostats |  |

## unit · places_world

| id | label | type | kind | update | evidence | source | description |
|---|---|---|---|---|---|---|---|
| `unit.rent_total` | Unit rent | f4 [0, 6000] (USD/month) | attribute | event | calibrated |  | Monthly rent for the unit (per-bed for contracted/dorm housing). |
| `unit.capacity` | Capacity (beds) | u1 [1, 12] | attribute | event | calibrated |  |  |
| `unit.occupancy` | Occupants | u1 [0, 12] | attribute | event | calibrated |  |  |
| `unit.contracted` | BYU-contracted | bool | attribute | event | calibrated |  | Approved BYU Contracted Housing (single undergrads must live in contracted housing unless with parents/relatives; units are single-sex). |
| `unit.sex_restriction` | Sex restriction | cat: none, F, M | attribute | event | calibrated |  |  |
| `unit.married_only` | Married housing | bool | attribute | event | calibrated |  |  |
| `unit.unit_type` | Unit type | cat: dorm, apartment, house_room, married_apartment, family_home | attribute | event | calibrated |  |  |

## world · places_world

| id | label | type | kind | update | evidence | source | description |
|---|---|---|---|---|---|---|---|
| `world.temp_f` | Daily high temperature | f4 (°F) | state | daily | extrapolated |  | Provo climate normals by month (approximate) + noise; intervention target. |
| `world.unemployment` | Unemployment rate (Utah County) | f4 (rate) | state | monthly | calibrated |  | Starts near Utah's low pre-2025 level (~3%); recession interventions raise it. |
| `world.wage_index` | Wage index | f4 | state | monthly | calibrated |  |  |
| `world.rent_index` | Rent index | f4 | state | monthly | calibrated |  | Market rent multiplier (1.0 = start); adjusts to vacancy. |
| `world.housing_supply_index` | Housing supply index | f4 | state | monthly | calibrated |  |  |
| `world.tuition_byu` | BYU tuition (LDS undergrad) | f4 (USD/semester) | state | yearly | calibrated |  | ≈$3.5k/semester for LDS undergraduates (approximate; verify against BYU's current schedule). |
| `world.tuition_uvu` | UVU tuition (resident) | f4 (USD/semester) | state | yearly | calibrated |  | ≈$3k/semester full-time resident (approximate). |
| `world.app_appeal` | Dating-app appeal multiplier | f4 | state | daily | calibrated |  | Scales app adoption/engagement (e.g. a new app takes off). |
| `world.coffee_permitted` | Coffee permitted by church | bool | state | daily | hypothetical |  | Word of Wisdom norm switch (hypothetical intervention). |
| `world.contracted_housing_required` | BYU contracted-housing requirement | bool | state | daily | calibrated |  | Single first-year BYU undergraduates must live on campus or in BYU-contracted housing (BYU policy since fall 2022: first two semesters only). |
| `world.interfaith_welcome` | Interfaith welcome initiative | f4 | state | daily | hypothetical |  | 0-1: how actively campuses and wards welcome people of other faiths and none (lowers the religious-outsider feeling). |
| `world.contracted_housing_all_years` | Contracted housing for all years (pre-2022 rule) | bool | state | daily | hypothetical |  | When true, the requirement covers every single BYU undergraduate, as it did before fall 2022. |
| `world.mission_norm` | Mission participation norm | f4 | state | daily | calibrated |  | Multiplier on mission-departure hazard. |
| `world.men_initiate_norm` | Men-ask norm strength | f4 | state | daily | calibrated |  | How strongly dating initiation is expected of men. |
| `world.church_attendance_norm` | Church attendance norm multiplier | f4 | state | daily | calibrated |  |  |
| `world.transit_quality` | Transit quality (UVX/FrontRunner) | f4 | state | daily | calibrated |  |  |
| `world.marriage_norm` | Early-marriage norm strength | f4 | state | daily | hypothetical |  | Multiplier on the cultural pressure to marry young (intervention target). |
| `world.rent_shock` | Rent shock multiplier | f4 | state | daily | calibrated |  | Exogenous rent multiplier on top of the vacancy-driven rent index. |
| `world.enrollment_index` | Enrollment index | f4 | state | daily | calibrated |  | Multiplier on incoming cohort size. |
| `world.social_media_intensity` | Social media intensity | f4 | state | daily | hypothetical |  | Multiplier on social-media hours and comparison effects. |
