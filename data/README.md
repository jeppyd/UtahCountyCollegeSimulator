# data/

* `raw/` — **gitignored.** Drop the raw LDStats survey exports here
  (`provostats.json`, `college-life.json`, `dating.json`, `culture-lifestyle.json`).
  These contain real respondents and must never be committed.
* `derived/` — gitignored respondent-level harmonized tables (local only).
* `external/` — gitignored downloads (ACS, OSM, UGRC, LODES) fetched by `scripts/fetch_*.py`.

Only *aggregate* statistics derived from the raw files are committed, under
`ucsim/priors/` (see `scripts/build_priors.py` and docs/DATA_SOURCES.md).
