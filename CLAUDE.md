# Instructions for Claude Code (same as AGENTS.md)

Several agents take turns on this project. Before doing anything else:

1. Work on branch `claude/festive-archimedes-1llpw1` (`git fetch origin && git checkout claude/festive-archimedes-1llpw1 && git pull`). Never push to or merge into `main` (a merge into main publishes the owner's Windows release).
2. Read [`docs/HANDOFF.md`](docs/HANDOFF.md) — who is working on what, the status board, the owner's decisions, and the session log — and follow its protocol: claim a workstream before coding, commit and push often, and update the status board and session log before you stop.
3. Follow [`docs/workstreams/README.md`](docs/workstreams/README.md) (shared rules) and the spec of your workstream in `docs/workstreams/`. The design contract is [`docs/EVOLUTION.md`](docs/EVOLUTION.md).

Non-negotiable: survey responses never enter the repository. Raw exports live only in `data/raw/` (gitignored); only aggregates with at least 10 respondents per cell are committed; `tests/test_no_raw_survey_data.py` must pass.

Run `python -m pytest -q` (and `cd web && npm run build` for web changes) before handing off; it includes a speed budget (`python scripts/perf.py` shows timings; see docs/workstreams/README.md).
