# Notices and attribution

## Map and place data

- **OpenStreetMap**: geocodes and outlines of named apartment complexes, some places of worship, and the
  UGRC "Open Source Places" layer used for venues are derived from OpenStreetMap data,
  © OpenStreetMap contributors, available under the Open Database License (ODbL 1.0,
  https://opendatacommons.org/licenses/odbl/). The derived files are `ucsim/geo/complex_geocodes.json`,
  `ucsim/geo/data/complexes.parquet`, `ucsim/geo/data/congregations.json` and `ucsim/geo/data/venues.parquet`.
- **Utah Geospatial Resource Center (UGRC / SGID)**: parcels (Utah County LIR), building footprints, address
  points, places of worship, parks, roads, municipal boundaries, campuses and trailheads; public data from the
  State of Utah.
- **Overture Maps Foundation**: building footprints, heights and names (`ucsim/geo/data/buildings.parquet`,
  `web/public/geo/buildings3d.bin`, `web/public/geo/building_names.json`) come from the Overture Maps buildings
  theme, which combines OpenStreetMap (© OpenStreetMap contributors, ODbL 1.0), Esri Community Maps and Microsoft
  building footprints; released under ODbL 1.0 (https://docs.overturemaps.org/attribution/). Places (shops,
  restaurants; not yet used) are CDLA-Permissive-2.0.
- **BYU Housing** published facts (buildings, floors, layouts, rents) behind `ucsim/config/places/flagship.yaml`;
  each value cites its page.
- **Utah Transit Authority (UTA)**: travel times by transit are derived from UTA's public GTFS schedule feed
  (https://gtfsfeed.rideuta.com/GTFS.zip). The feed itself is not included in this repository. UTA's terms of use
  were listed at http://developer.rideuta.com/TermsOfUse.aspx (no longer reachable when checked on 2026-10-20).
- **Provo City and Orem City GIS** open data where noted in `docs/DATA_SOURCES.md`.
- **Basemap tiles** (optional, in the browser): OpenFreeMap, © OpenStreetMap contributors.

## Surveys

The simulation is calibrated to aggregate statistics from four local surveys run by the project owner. No
survey responses are included in this repository; see the privacy boundary in `docs/DATA_SOURCES.md`.

## People

Every person in the simulation is synthetic: generated from distributions, with generated names. Any
resemblance to real people is coincidental.
