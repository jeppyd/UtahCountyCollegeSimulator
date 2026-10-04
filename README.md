# Provo–Orem Social Simulator

A spatial, evidence-grounded, event-driven social microsimulation of the BYU/UVU college ecosystem in
Provo and Orem, Utah. The engine of a professional social simulation; the interface of a simulation
game: change something about the world, let time run, watch the Original and the What-if worlds drift
apart, and follow the butterfly effect down to individual lives.

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

The browser opens on the title screen: pick how big a world (the share of the real BYU/UVU community to
simulate — Standard ≈ 9k people, Full ≈ 60k), a world number and warm-up days, then **Create the world**.
Settings (the gear, top right) rebuilds at another size any time. For scripts, `--scale 0.3 --seed 1 --warmup 14` builds a
world at startup instead. For UI development run `npm run dev` in `web/` (proxies to the API on :8000).

Rebuilding inputs (not needed to run — derived files are committed):

```bash
python scripts/fetch_geodata.py && python -m ucsim.geo.build_world     # UGRC layers → housing stock & venues
python -m ucsim.ingest.priors                                          # data/raw/*.json → aggregate priors
```

## Using it

It plays like a simulation game. The world opens on **World**: a living map of everyone moving through
yesterday, the headlines, this week's counts, what's moving, lives worth following and your pinned board.
The top bar has the clock (the sky follows the time of day), **⏸ ▶ ▶▶ ▶▶▶** speeds (Space plays and pauses),
**+1d / +1w / Jump ▾**, the **Original / What-if / Compare** switch, the butterfly meter (how many lives
differ between the worlds) and **Search anything** (`/` or `Ctrl K`). Big moments pop up as news while time
runs, and a recap appears after every time skip.

| I want to… | Go to |
|---|---|
| see what's happening now | **World** (news, the week, trends, the two worlds); **Map** (people now or at home, colored by anything; replay a day or the months) |
| follow individual lives | **People** → a person: feelings and why, their people, school and work, faith, money and home, story, history, and their other life in the What-if |
| see couples and friendships | **Relationships** (couples, the friendship network, how people meet, couples that exist in only one world) |
| look at places and events | **Places** (complexes, wards, schools) and **Events** (every event, with its chain of causes) |
| change the world | **What if…?** (top bar or anywhere): ideas, levers (rent, tuition, wages, dating apps, marriage pressure, missions, coffee…), or nudges to a group of people or a rule |
| follow the butterfly effect | **What-if**: how far the worlds drifted, every field side by side, events more or less common, lives that diverged, couples and places that changed, and why |
| browse every field the model tracks | **Explore**: 217 fields in friendly drawers; each one now, over time, by group, against another field, the people behind it, and what drives it; pin it to your board |
| go deeper | **Research desk**: vital signs, flows, cross-tabs, cause & effect, Monte Carlo and sweeps, model check, data dictionary, rules, evidence |

The in-app **How it works** page explains the controls and the model in plain language. The full guide to the project (use, model, code, data, validation, vision and ideas) is
[docs/PROJECT_GUIDE.md](docs/PROJECT_GUIDE.md).

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
| `web/` | React app (game shell, explorer, butterfly views, research desk) |
| `scripts/` | validation, calibration, stability, static export, catalog generation, data builders |
| `tests/` | pytest suite (`python -m pytest`) |
| `docs/` | [PROJECT_GUIDE](docs/PROJECT_GUIDE.md) · [ARCHITECTURE](docs/ARCHITECTURE.md) · [DATA_SOURCES](docs/DATA_SOURCES.md) · [MODEL_ASSUMPTIONS](docs/MODEL_ASSUMPTIONS.md) · [VARIABLE_CATALOG](docs/VARIABLE_CATALOG.md) · [MECHANISMS](docs/MECHANISMS.md) · [VALIDATION](docs/VALIDATION.md) · [ROADMAP](docs/ROADMAP.md) · [DEVELOPMENT_LOG](docs/DEVELOPMENT_LOG.md) |

## Status

Near-final: the full model runs end to end with a game-style interface (world lens, butterfly views, field
explorer, live news), real Provo/Orem places, religious diversity, map replays, an automated calibration loop
against the Census and surveys, and a four-year stability check.
See the in-app **Model check** (or `docs/VALIDATION.md`) for how well it matches real data and
`docs/ROADMAP.md` for what is next. The natural-language (LLM) layer is deliberately deferred.
