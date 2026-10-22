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
(nearest-PD), group summaries (mean/median/IQR/share) and one-way frequency tables (majors, complexes, mission
places, origin states): every cell with fewer than **10** respondents is suppressed, pooled or backed off to a coarser
group. Group summaries report their sample sizes as bands (`10-29`, `30-99`, …); each survey's total and each
question's number of answers by sex (all 90 or more) are exact.
No respondent row, free-text answer, timestamp or identifier is stored, and synthetic agents are new draws
from these distributions, never copies of respondents. A test (`tests/test_analysis_api.py`) guards that the
committed priors contain no long arrays.

**Known biases.** Convenience samples that over-represent BYU, active Latter-day Saints, single students
and survey-engaged people. Correction: margins that matter for structure (married share by school, UVU
religious mix, activity) are calibrated to institutional targets at synthesis time (odds tilts), and cross-
survey linkage uses only shared bridge variables (sex, religion, activity, age, school proxy) — see
`MODEL_ASSUMPTIONS.md`.

### The LDS Sexuality Survey (June 2025)

A fifth survey from the owner (LDStats audience; 1,641 responses, an Excel export). `python -m ucsim.ingest.sexuality`
reads `data/raw/lds-sexuality_2025-06-29.xlsx` in place and adds only its own sections to
`ucsim/priors/survey_priors.json` (`blocks.lds_sexuality`, `targets.lds_sex_*`, `tables.lds_sex_*`,
`meta.sources["lds-sexuality"]`); the other four surveys' sections are left exactly as they were.

* **Scope:** ages 18–35, men and women: **1,411 respondents** (50% women; 46% single, 19% in a relationship, 4%
  engaged, 31% married; 86% active, 12% less active, 2% inactive members; 77% from Utah).
* **Used for:** sex drive; the relationship stage at which each of four tiers of physical intimacy is acceptable
  (touching / under clothes / naked / sex; each tier is the median of the survey's "When is this acceptable?" items);
  sex education at home; shame about sexuality ("my feelings toward sexuality have been negatively impacted by
  negative cultural messages"); porn use and masturbation in the last year; having addressed porn or masturbation
  with a bishop; the five dating dealbreakers; married people's satisfaction with their sex life and marriage and
  the desire gap with their spouse. A Gaussian-copula block bridged to ProvoStats by age, relationship stage,
  activity, mission and the kissing/NCMO/relationship/sexual-partner counts. Church members' porn use now comes
  from this survey (it was a literature extrapolation); non-members are drawn as the survey's inactive members.
* **Targets** (scripts/validate.py): kissing, NCMO and relationship counts by sex, age and activity (held out — an
  independent check of what ProvoStats seeds); premarital sex among the unmarried by activity; porn use by sex and
  activity; talking to a bishop by sex; married sexual and marital satisfaction.
* **Left out on purpose:** City, College and every free-text answer (fantasy, favourite activity, wildest place,
  "anything else", every "Other – Text"), the extra sheets (Fantasy, Favorites, Location, Dropdowns), birth control,
  positions, toys and how oral sex ends (the owner's decision), the moral-wrongness-in-marriage and "wish you could"
  items. These columns are never read (`ucsim/ingest/survey_spec.py` lists the only ones that are).
* **Privacy:** the same boundary as above; in addition, answer levels held by fewer than 10 people (per sex) are
  pooled into the neighbouring level before any marginal is stored. `tests/test_sexuality_priors.py` checks it.
* **Biases:** self-selected LDStats followers willing to answer an explicit survey; a broad age range (the ingest
  keeps 18–35); mostly Utah and mostly active members, so less-active and inactive cells are small (10–29 or 30–99)
  and non-members are extrapolated. About a quarter of respondents stop before the attitude and dealbreaker pages.

### The Psych 308 class survey (BYU, 2020) — checks only
- 947 BYU students in Psych 308 (statistics for psychology), March 17 – December 14, 2020: 98% Latter-day Saints,
  64% women, a third freshmen, 37% psychology majors, median age 21. Raw export `data/raw/psych308_2020.xlsx` (never
  committed); `python -m ucsim.ingest.psych308` writes aggregates only (cells ≥ 10; no free text, ids or timestamps)
  to `ucsim/config/sources/psych308_2020.json`; `ucsim/analysis/psych308_check.py` compares the model (validate.py).
- Every response came during the COVID-19 pandemic. Stable measures (family background, missions, marriage age,
  attitudes, religiosity) are held-out checks; 2020 levels of dating, sleep, screen time, work, GPA and life
  satisfaction are diagnostics only; within-person associations (Spearman) are pattern checks of mechanisms.
- Not used for starting values (yet): nothing in the model was tuned to it.

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
| UGRC places of worship + OpenStreetMap places of worship | 21 non-LDS congregations (Catholic, Protestant, other Christian, other faiths) (`scripts/build_congregations.py` → `ucsim/geo/data/congregations.json`) | public / ODbL |
| U.S. Census Bureau ACS 2020–2024 5-year, table B12002, Provo + Orem (via Census Reporter API) | married share by age and sex: the main external benchmark (`ucsim/config/sources/acs_married_share_provo_orem.json`) | public |
| BYU University Advisement, "Majors List by Colleges & Departments 2025-2026"; UVU academic catalog (catalog.uvu.edu/programs) | majors and colleges (`scripts/build_majors.py` → `ucsim/config/majors.yaml`) | public |
| OpenFreeMap | optional basemap tiles in the browser | ODbL / OSM |

`scripts/fetch_geodata.py` downloads the UGRC layers for the bounding box (−111.775, 40.170, −111.570, 40.360);
`ucsim/geo/build_world.py` derives 63k dwellings (house / small multi-family / apartment / mobile home),
~590 complexes (~200 with real names: BYU's contracted list matched to UGRC address points, OSM outlines
containing the parcels, and survey geocodes; plus Helaman & Heritage Halls, Wymount and Wyview), 151 LDS
meetinghouses and 712 venues (restaurants, cafés, soda & dessert shops, parks, gyms, theaters, trailheads,
dance venues…). Web layers (roads, city outlines, building footprints) are committed under `web/public/geo/`.

### Buildings, floors and bedrooms (`scripts/fetch_overture.py`, `ucsim/geo/buildings.py`, `ucsim/geo/homes.py`)
- Overture Maps buildings (release 2026-09-23): 76,013 footprints in Provo/Orem; heights for ~70% (mostly lidar).
  Floors: the mapped `building:levels` (871), the county parcel's FLOORS_CNT when the parcel centroid is inside
  the footprint (4,095), height ÷ 3.2 m (49,645), else 1 (2 for apartments) — recorded per row in `floors_src`.
- Homes on floors: each dwelling's address point → the footprint it is in (else the nearest within 25 m; houses
  are matched one to a footprint); floor from the apartment number ("Apt 204" → 2nd floor) for 3,750 homes, else
  spread over the building's floors in address order.
- Flagship complexes (`ucsim/config/places/flagship.yaml`): Helaman, Heritage, Wymount, Wyview and Riviera from
  BYU Housing's pages (2026–27) and Wikipedia's list of BYU residence halls; Heritage's apartments are the county's
  real unit addresses (825 E Heritage Dr, Bldg n Apt fwnn). Layout shares, which halls are men's or women's, and
  which half of Wyview is family housing are estimates (marked `estimate`).
- Bedrooms elsewhere are a rule (`population/structure.py` `default_bedrooms`, hypothetical).
- Shapes (`ucsim/geo/shapes.py`): each footprint's smallest rectangle and its wings (rectangles inside it); centroids
  computed relative to the first vertex (computing them in raw degrees put them a median 71 m off).
- **BYU Facilities Planning floor plans** (pf.byu.edu, behind BYU login; downloaded and supplied by the owner,
  2026-10-22). The PDFs stay in `data/external/floorplans/` (never committed — the repository is public); only
  derived summaries are: `geo/data/plan_units.parquet` (Heritage Halls: building, floor, apartment number, beds per
  bedroom, apartment centre to 1 m) and `geo/data/classrooms.parquet` (BYU rooms whose plan prints a seating
  capacity: building, floor, room number, seats, centre to 1 m). Read from the Revit exports' text
  (`ucsim/geo/floorplans.py`); each sheet placed on its footprint by turning and shifting it until its room labels
  fall inside the outline (scale from the sheet). Wyview's counts (12/18 apartments a building, one three-bedroom
  a floor) and Helaman's (~38–40 double rooms a floor, 3 floors) were read off the plans into flagship.yaml.
- **BYU class schedule and room data** (owner-supplied package `byu-campus-data-01.zip`, collected 2026-10-22 from
  BYU's public class schedule, commtech.byu.edu/noauth/classSchedule, and BYU's public ArcGIS layers; terms Fall 2026
  and Winter 2027). The package stays in `data/external/byu_campus/` (never committed: it carries instructor names).
  `python -m ucsim.geo.schedule` writes the derived, name-free tables: `geo/data/byu_schedule.parquet` (in-person
  sections: department, course number, level, credits, enrollment, the main meeting's days, start, end, room,
  floor, point and seats) and `geo/data/byu_occupancy.parquet` (mean scheduled student presence per building,
  weekday and simulation block, for checks). Departments map to study areas in
  `ucsim/config/places/byu_departments.yaml` (judgment, by college). Enrollment is a collection-time snapshot
  (Winter's provisional). The 2026–27 schedule stands in for every year; Spring and Summer sections are still drawn.
- Campus places (`ucsim/config/places/campus.yaml`): teaching buildings, hangout spots, gyms, study and events
  buildings for BYU and UVU, BYU building codes → names, and which buildings each study area's classes use
  (judgment from department locations; weights rough).

### Travel times (`scripts/build_travel.py` → `ucsim/geo/data/travel.npz`)

| Source | Used for | License / terms |
|---|---|---|
| UGRC UtahRoads (SGID), all drivable classes with speed limits and one-ways (`scripts/fetch_geodata.py roads_net`) | the street graph: walking/biking km (no freeways or ramps), driving minutes off-peak and at the evening peak | public / open |
| Utah Transit Authority GTFS feed (https://gtfsfeed.rideuta.com/GTFS.zip; feed version 2026 AUG_20261008, 2026-08-16 to 2026-12-05, downloaded 2026-10-20) | door-to-door transit minutes between zones on a weekday, Saturday and Sunday at 8:00, 12:30, 17:30 and 20:30 | UTA's terms: the Mobility Database lists http://developer.rideuta.com/TermsOfUse.aspx, which no longer resolves; the feed is not redistributed here, only derived minutes, with attribution |
| Daily Universe (2017, 2021) | BYU parking: ~7,049 Y-lot spaces, lots 10+ minutes' walk from the heart of campus, 15–20 minutes hunting for a spot on bad days | news (cited for the labelled parking assumptions) |

73 zones: the 57 official Provo/Orem neighborhoods, BYU and UVU campus, and 14 outer areas where people live or go;
a ~170 m raster maps any point to its zone. In the feed, UVX (830X) runs weekdays and Saturdays and not on Sundays;
on Sundays only routes 850 (State Street) and 871 serve the area. Labelled assumptions (not data): driving speed =
limit × a class factor for signals and turns, evening-peak factors, parking minutes at the destination (BYU 9,
UVU 6, downtown 3, else 1.5), a parking hassle and a transit-wait penalty that only affect the mode choice, 12% of
people without a car bike, and snow slowing every mode. With them, on a Tuesday at 8:00 about 45% of BYU students
walk to campus, 30% ride transit and 22% drive; at UVU 75% drive.

## Literature

Mechanism forms and starting parameter values cite published work in each mechanism's `refs`
(see `MECHANISMS.md`), e.g. Hall (2019) on hours to friendship, Petrov (2006) ACT-R activation, Centola &
Macy (2007) complex contagion, Rusbult's investment model, Joel/Eastwick/Finkel on idiosyncratic attraction,
Cacioppo & Hawkley on loneliness, Lally et al. (2010) habit formation, Grubbs on moral incongruence,
Fowler & Christakis on emotional contagion.
