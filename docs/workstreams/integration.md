# Workstream: Integration, validation and polish

> Status: docs/HANDOFF.md. Rules: README.md.

After each builder finishes: privacy check (no raw survey rows, every committed survey cell ≥ 10, no emails), review
the diff, merge into the working branch (time-occasions before the others that depend on it), resolve conflicts
(romance.py, encounters.py, sim.py, activity.py and validation files are shared), run `python -m pytest -q` and
`cd web && npm run build`, push. Then:
1. Full-scale check (scale 1.0, ~60k people): seconds per day (was 1.6 s before iteration 6), memory, any errors over
   ~60 simulated days; optimize the hot spots (encounters, recorder) if it regressed badly.
2. Validation: `python scripts/validate.py` at scale 0.15 for a year; compare to docs/VALIDATION.md; recalibrate the
   few parameters that moved (`scripts/calibrate.py`); regenerate docs/VALIDATION.md, VARIABLE_CATALOG.md and
   MECHANISMS.md with their scripts.
3. Workbench completeness: every new system has a tool (Occasion/scene view, Chats, Institution, US map, Calendar,
   Trace, Chains, Scales, Ask, Interview); everything clickable everywhere (RefChip); screenshots of a realistic
   session; the in-app guide updated.
4. Adversarial review of the merged work (correctness, determinism of paired worlds, privacy, performance, honesty of
   labels), fix what it finds.
5. Docs: README "What's new", PROJECT_GUIDE, ARCHITECTURE, ODD updated for iteration 6.
