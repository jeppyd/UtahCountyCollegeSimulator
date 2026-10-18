# Workstreams: shared rules

Each file here is a self-contained spec for one piece of iteration 6. The contract they share is
[`docs/EVOLUTION.md`](../EVOLUTION.md); who is doing what right now is in [`docs/HANDOFF.md`](../HANDOFF.md).

**The owner's goals** (use them for judgment calls): a deep, realistic simulation of BYU/UVU social life in
Provo–Orem whose connections are easy to *see* — anyone can pick anything and trace why it happened and what it led
to, for one life or the whole valley. Realism is taken seriously (evidence labels, plausible magnitudes, no invented
precision). The owner is not a software engineer: every user-facing word is plain language, and visuals must be
clear and beautiful.

## Rules for every workstream

1. **Setup.** `pip install -e ".[dev]"`; for the web app `cd web && npm ci && npm run build` (TypeScript strict).
   Read `docs/EVOLUTION.md`, `docs/ARCHITECTURE.md`, `docs/MIND.md`, `ucsim/engine/ledger.py`,
   `ucsim/engine/clock.py`, `ucsim/engine/sim.py` and the code you touch first.
2. **Determinism and paired worlds.** New randomness only from `sim.streams.gen("<a new unique stream name>", day,
   block)` or `sim.u("<new name>")`; never reuse an existing stream name for new draws; never numpy's global random
   state or Python's `random`. Recording (ledgers, logs) never draws random numbers. Interventions use their own
   streams.
3. **Evidence.** Mechanism parameters go in `ucsim/config/mechanisms/*.yaml` (value, range, evidence label, refs);
   person variables in `ucsim/config/variables/*.yaml`; event types in `ucsim/config/events/<nn>_<area>.yaml`
   (with a plain `story` template); decision kinds, every factor declared with plain words, in
   `ucsim/config/decisions/<nn>_<area>.yaml`; occasion kinds in `ucsim/config/occasions/<nn>_<area>.yaml`.
   Be honest about evidence (hypothetical where it is).
4. **Provenance.** A meaningful choice is recorded with `sim.decisions.record(...)` (the actual terms that were
   summed, constraints as masks) and events get `decision=` / `causes=` in `sim.emit`.
5. **Performance.** Vectorized NumPy; no per-person Python loops. Report seconds per simulated day at scale 0.15
   (≈30 days) before and after; the owner runs the full world (scale 1.0, ~60k people).
6. **API.** New endpoints go in a new `ucsim/api/routes_<area>.py` defining `router = APIRouter()` (included
   automatically). Handlers import lazily (`from .server import WS, jresp`) and hold `WS.lock` while reading a world.
7. **Workbench tools.** A file `web/src/bench/tools/<Name>.tsx` exporting `tool: ToolDef` (see
   `web/src/bench/registry.ts`) registers itself; use `useBench` (`web/src/bench/selection.ts`) for the shared
   selection; shared small components go in `web/src/kit/`. Light and dark themes.
8. **Tests.** pytest tests in `tests/test_<area>.py` on small worlds (scale 0.02–0.05); the full suite
   (`python -m pytest -q`) must pass before you hand off.
9. **Privacy — non-negotiable.** Survey responses never enter the repository: raw exports live only in
   `data/raw/` (gitignored, supplied by the owner), only aggregates with **≥ 10 respondents per cell** are committed,
   free-text answers and contact details are never read into the model. `tests/test_no_raw_survey_data.py` guards
   this and must keep passing.
10. **Style.** Match the surrounding code (concise docstrings explaining why, similar comment density). No heavy new
    dependencies without a reason.
11. **Commit early and often** (WIP commits are fine) and push to the working branch, so an agent that runs out of
    usage never strands work. Never commit `web/node_modules`. Commit messages end with the attribution lines your
    tool normally adds.
