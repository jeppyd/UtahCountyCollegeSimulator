# Data sources

## Surveys (aggregate use only)

Four local online surveys supplied by the project owner (ProvoStats/LDStats audiences), each with 300+ responses:

| Survey | Used for |
|---|---|
| ProvoStats | demographics, religion & activity, missions, politics, orientation, origin, income, personality proxies, dating & relationship history |
| College Life | housing cost & type, roommates, work hours, sleep, GPA, study, social events, eating out, majors/study areas |
| Dating | dating frequency, asks, first-date preferences, apps, kissing/NCMO, DTR and engagement timing, where couples met |
| Culture & Lifestyle | temple & scripture practice, coffee/alcohol, social media, faith crisis experience, ideal family size, culture items |

**Privacy boundary.** Raw files live only in `data/raw/` (gitignored) on the owner's machine.
`python -m ucsim.ingest.priors` turns them into `ucsim/priors/survey_priors.json`, which contains only:
smoothed conditional probability tables, marginal quantile grids (1–99), within-sex correlation matrices
(nearest-PD), and group summaries (mean/median/IQR/share) — every cell with fewer than **10** respondents is
suppressed or backed off to a coarser group, and sample sizes are reported as bands (`10-29`, `30-99`, …).
No respondent row, free-text answer, timestamp or identifier is stored, and synthetic agents are new draws
from these distributions, never copies of respondents. A test (`tests/test_analysis_api.py`) guards that the
committed priors contain no long arrays.

**Known biases.** Convenience samples that over-represent BYU, active Latter-day Saints, single students
and survey-engaged people. Correction: margins that matter for structure (married share by school, UVU
religious mix, activity) are calibrated to institutional targets at synthesis time (odds tilts), and cross-
survey linkage uses only shared bridge variables (sex, religion, activity, age, school proxy) — see
`MODEL_ASSUMPTIONS.md`.

## Institutional & market figures (`ucsim/config/world.yaml`)

Approximate, labeled `(approx)` or `(assumption)` in the file: BYU daytime enrollment (~33.5k), share
married (~25%), LDS share; in-scope UVU population (15k of ~45k) and its married/LDS shares; incoming
cohorts and returned-missionary flows; mission ages and lengths (Church policy since 2012); tuition;
calendar terms; lease turnover dates; climate normals; unemployment and wage index. These should be
replaced with official figures where available (see `ROADMAP.md`).

## Geography

| Source | Layers | License |
|---|---|---|
| Utah Geospatial Resource Center (UGRC / SGID) | parcels (Utah County LIR), building footprints, address points, places of worship, parks, roads, municipal boundaries, higher-ed campuses, trailheads | public / open |
| OpenStreetMap via Nominatim | geocodes for named apartment complexes (cached in `ucsim/geo/complex_geocodes.json`) | ODbL |
| OpenFreeMap | optional basemap tiles in the browser | ODbL / OSM |

`scripts/fetch_geodata.py` downloads the UGRC layers for the bounding box (−111.775, 40.170, −111.570, 40.360);
`ucsim/geo/build_world.py` derives 63k dwellings (house / small multi-family / apartment / mobile home),
533 complexes (38 named and geocoded, plus BYU's Helaman & Heritage Halls, Wymount and Wyview), 151 LDS
meetinghouses and 712 venues (restaurants, cafés, soda & dessert shops, parks, gyms, theaters, trailheads,
dance venues…). Web layers (roads, city outlines, building footprints) are committed under `web/public/geo/`.

## Literature

Mechanism forms and starting parameter values cite published work in each mechanism's `refs`
(see `MECHANISMS.md`), e.g. Hall (2019) on hours to friendship, Petrov (2006) ACT-R activation, Centola &
Macy (2007) complex contagion, Rusbult's investment model, Joel/Eastwick/Finkel on idiosyncratic attraction,
Cacioppo & Hawkley on loneliness, Lally et al. (2010) habit formation, Grubbs on moral incongruence,
Fowler & Christakis on emotional contagion.
