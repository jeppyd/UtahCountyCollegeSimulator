# Workstream: Family and home states (wave 2)

> Status: docs/HANDOFF.md. Rules: README.md. Contract: docs/EVOLUTION.md §8. Needs `calendar-weather` (holidays,
> travel_home_likely) and `time-occasions` merged.

The owner asked for "light simulation of what happens for those at home: going home for holidays, or to see family on
a weekend — not mapped in detail, just a broad map of 'here are the people in these states'".

1. **Home.** Each person gets a home state (and a metro point) consistent with `origin_region` (BYU/UVU students by
   state: use the ProvoStats origin-state table in `ucsim/priors/survey_priors.json` → tables.origin_state, plus
   published BYU/UVU enrollment-by-state figures if you can source them; UVU is mostly Utah). Distance and travel
   time home (drive within ~12 h, otherwise fly; cost).
2. **Kin records** (lightweight, off-map): parents (married/divorced per `family_structure`, `parents_divorced`),
   siblings (count, ages, some at BYU/UVU too), grandparents; closeness, contact frequency, financial support
   (`parental_support` exists), religious expectation (`family_expectation` exists), and their own life events
   (sibling weddings, mission farewells/homecomings, births, illness, a death in the family — `family_crisis` and
   `death_in_family` exist) that pull people home.
3. **Trips.** Weekend trips home for people within driving range; Thanksgiving and Christmas (most leave; far-away or
   working students may stay — they host or join "Friendsgiving" occasions); spring/summer (the existing summer
   exodus); family visits to Provo (football games, Conference weekend, graduation). Trips are decisions (factors:
   distance, cost, closeness, obligations such as shifts or exams, a partner's family — married couples alternate
   families). While away a person is not present in Provo; at home they get family contact (support, pressure,
   homesickness on return). Record trips (`Trip` ledger: person, depart, return, destination state, reason, mode).
4. **Obligations both ways**: childcare help from local grandparents for student parents, money from home, caregiving
   for a sick parent, family emergencies.
5. API `routes_family.py`: a person's family and trips; counts by home state now (in Provo vs at home). Workbench tool
   `USMap.tsx`: a national map of states (public-domain Census cartographic boundaries; a small simplified GeoJSON
   committed under web/public/geo/) shaded by how many people are from each state and how many are there right now;
   play the calendar to watch the Thanksgiving/Christmas exodus and return; click a state to select its people.
6. Tests: home-state shares match the table, holiday departures/returns, trips are recorded with reasons, determinism.
