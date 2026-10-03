# Provo–Orem Social Simulator

A spatial, evidence-grounded, event-driven social microsimulation of the BYU/UVU college ecosystem in
Provo and Orem, Utah — with an analysis workstation for exploring who meets whom, how friendships,
dating, faith, emotions, housing and money interact, and what changes under interventions.

Thousands of synthetic students, spouses, young adults, faculty and neighbors live in real Provo/Orem
housing, go to class, work, church, the gym and dates, and meet each other through shared places. Every
meaningful change is an event with a mechanism and a causal parent, so any outcome can be traced back.

> All people in the model are synthetic. Survey data is used only as aggregate statistics with small cells
> suppressed; raw responses are never committed or shown.

## Quick start

**Windows, no setup:** download `ProvoOremSimulator-Setup.exe` from the
[latest release](https://github.com/jeppyd/UtahCountyCollegeSimulator/releases/latest), double-click it, and
start the simulator from the desktop or Start-menu shortcut. Windows may warn that the app isn't signed:
choose **More info → Run anyway**. Every push rebuilds and self-tests the installer
(`.github/workflows/windows-app.yml`).

**From source** (any OS) needs Python ≥ 3.10, Git and Node.js 18+ (for the web UI). Works on Windows, macOS and Linux.

```bash
git clone https://github.com/jeppyd/UtahCountyCollegeSimulator.git
cd UtahCountyCollegeSimulator
git checkout claude/serene-bohr-cyvzxl        # until this branch is merged
pip install -e .
cd web
npm install
npm run build
cd ..
python -m ucsim.api.server        # then open http://127.0.0.1:8000
```

The browser opens on **Create a world**: pick the population scale (the share of the real BYU/UVU
community to simulate — 0.15 ≈ 9k people, 1.0 ≈ 60k), a random seed and warm-up days. The **World** button
in the top bar rebuilds at another scale any time. For scripts, `--scale 0.3 --seed 1 --warmup 14` builds a
world at startup instead. For UI development run `npm run dev` in `web/` (proxies to the API on :8000).

Rebuilding inputs (not needed to run — derived files are committed):

```bash
python scripts/fetch_geodata.py && python -m ucsim.geo.build_world     # UGRC layers → housing stock & venues
python -m ucsim.ingest.priors                                          # data/raw/*.json → aggregate priors
```

## Using it

- **Clock**: step +1 hour … +1 year or run until a date (top bar).
- **Cohort bar**: filter by any variable (or recent events, household composition); the cohort follows you across views.
- **Map**: people where they are right now, homes, complexes and wards colored by any variable; diff mode between universes.
- **People → Person**: each feeling decomposed into mechanism terms and recent events ("why"), goals, faith dimensions, ego network, life timeline, and the counterfactual life in the intervention universe.
- **Explore / Cross-tabs**: distributions, scatter + regression, χ² and Cramér's V, drill into any bar.
- **Events**: the log with causal chains (ancestors and consequences).
- **Scenario lab**: queue presets or custom interventions (world / mechanism parameter / agent / new venue), branch a paired universe, compare outcomes with exact mechanism attribution, run Monte Carlo and parameter sweeps.
- **Causal web, Variables, Mechanisms**: the model's structure with evidence levels on every node.

## Programmatic use

```python
from ucsim.engine.runner import new_simulation, fork, divergence
from ucsim.analysis.explain import compare_universes

base = new_simulation(scale=0.15, seed=1).run_days(30)
alt = fork(base, [{"preset": "rent_up_20"}])
for _ in range(120):
    base.step_day(); alt.step_day()
print(divergence(base, alt))
print(compare_universes(base, alt)["states"]["financial_stress"])
```

## Repository

| Path | Contents |
|---|---|
| `ucsim/config/` | YAML registries: variables, mechanisms, events, world, intervention presets |
| `ucsim/ingest/` | survey specs and aggregate-prior builder |
| `ucsim/population/` | synthesis (CPTs, copulas, structure, network) |
| `ucsim/geo/` | geography build and derived housing/venue tables |
| `ucsim/engine/` | state stores, clock, systems, interventions, runner |
| `ucsim/analysis/`, `ucsim/api/` | query DSL, explanations, FastAPI server |
| `web/` | React workstation |
| `scripts/` | validation, static export, catalog generation, geodata |
| `tests/` | pytest suite (`python -m pytest`) |
| `docs/` | [ARCHITECTURE](docs/ARCHITECTURE.md) · [DATA_SOURCES](docs/DATA_SOURCES.md) · [MODEL_ASSUMPTIONS](docs/MODEL_ASSUMPTIONS.md) · [VARIABLE_CATALOG](docs/VARIABLE_CATALOG.md) · [MECHANISMS](docs/MECHANISMS.md) · [VALIDATION](docs/VALIDATION.md) · [ROADMAP](docs/ROADMAP.md) · [DEVELOPMENT_LOG](docs/DEVELOPMENT_LOG.md) |

## Status

First solid iteration: the full vertical slice runs end to end, with 38 tests and a one-year validation
report. Calibration is hand-tuned so far; see `docs/VALIDATION.md` for where the model and surveys still
disagree and `docs/ROADMAP.md` for what is next.
