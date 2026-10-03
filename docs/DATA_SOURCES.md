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

Fall 2025 headcounts: BYU 37,337 (modeled 35,000 daytime, in-residence) and UVU 48,670 (16,000 in scope).
Class mix follows the published shape (BYU ~17% freshmen, 33% seniors, 9% graduate). Contracted housing:
BYU's rule covers single undergraduates' first two semesters only (since fall 2022).
Approximate, labeled `(approx)` or `(assumption)` in the file: share
married (~25%), LDS share; UVU married/LDS shares; incoming
cohorts and returned-missionary flows; mission ages and lengths (Church policy since 2012); tuition;
calendar terms; lease turnover dates; climate normals; unemployment and wage index. These should be
replaced with official figures where available (see `ROADMAP.md`).

## Geography

| Source | Layers | License |
|---|---|---|
| Utah Geospatial Resource Center (UGRC / SGID) | parcels (Utah County LIR), building footprints, address points, places of worship, parks, roads, municipal boundaries, higher-ed campuses, trailheads | public / open |
| OpenStreetMap via Nominatim | geocodes for named apartment complexes (cached in `ucsim/geo/complex_geocodes.json`) | ODbL |
| OpenStreetMap via Overpass | named apartment / dormitory / residential outlines (`scripts/fetch_osm_housing.py`) | ODbL |
| BYU Off-Campus Housing | 2026-27 Contracted Housing List: property names, sizes, addresses (`ucsim/geo/byu_contracted_2026_27.csv`; phone numbers not stored) | public listing |
| Provo City GIS (ComDev/Neighborhoods) and Orem City GIS (Neighborhoods) | official neighborhood names and outlines only (`scripts/fetch_neighborhoods.py`) | public |
| BYU University Advisement, "Majors List by Colleges & Departments 2025-2026"; UVU academic catalog (catalog.uvu.edu/programs) | majors and colleges (`scripts/build_majors.py` → `ucsim/config/majors.yaml`) | public |
| OpenFreeMap | optional basemap tiles in the browser | ODbL / OSM |

`scripts/fetch_geodata.py` downloads the UGRC layers for the bounding box (−111.775, 40.170, −111.570, 40.360);
`ucsim/geo/build_world.py` derives 63k dwellings (house / small multi-family / apartment / mobile home),
~590 complexes (~200 with real names: BYU's contracted list matched to UGRC address points, OSM outlines
containing the parcels, and survey geocodes; plus Helaman & Heritage Halls, Wymount and Wyview), 151 LDS
meetinghouses and 712 venues (restaurants, cafés, soda & dessert shops, parks, gyms, theaters, trailheads,
dance venues…). Web layers (roads, city outlines, building footprints) are committed under `web/public/geo/`.

## Literature

Mechanism forms and starting parameter values cite published work in each mechanism's `refs`
(see `MECHANISMS.md`), e.g. Hall (2019) on hours to friendship, Petrov (2006) ACT-R activation, Centola &
Macy (2007) complex contagion, Rusbult's investment model, Joel/Eastwick/Finkel on idiosyncratic attraction,
Cacioppo & Hawkley on loneliness, Lally et al. (2010) habit formation, Grubbs on moral incongruence,
Fowler & Christakis on emotional contagion.
