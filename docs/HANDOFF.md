# Handoff: iteration 6 ("a world you can trace")

Several AI agents take turns on this work as each runs out of usage. **This file is the baton.** Read it first, claim
your work, keep it current, and leave it accurate when you stop. The design contract is
[`docs/EVOLUTION.md`](EVOLUTION.md); each piece of work has a spec in [`docs/workstreams/`](workstreams/) and shared
rules in [`docs/workstreams/README.md`](workstreams/README.md).

## Start here (every agent, every session)

1. `git fetch origin && git checkout claude/festive-archimedes-1llpw1 && git pull` — this is the working branch.
   **Never push to or merge into `main`**: every merge into main builds and publishes the owner's Windows release.
2. Read this file, then `docs/workstreams/README.md` (rules — privacy rules are non-negotiable), then
   `docs/EVOLUTION.md` and the spec of the workstream you'll take.
3. **Claim** before coding: put your name/tool, the date and the workstream in *Who is working now* below; commit and
   push that edit. Don't take a workstream someone else holds unless their claim is older than 12 hours with no new
   commits (then note that you took it over).
4. Work in small steps; **commit and push often** (WIP commits are fine), so running out of usage never strands work.
5. **Before you stop** (or when your usage is getting low): update the *Status board*, append a *Session log* entry
   (what you did, what's half-done and exactly where, what's next, anything surprising), remove your claim, run the
   tests if you can, commit and push. If tests fail, say which and why in the log.

## Who is working now

| Agent | Since (UTC) | Workstream | Notes |
|---|---|---|---|
| Claude Code (cloud session) | 2026-10-18 17:23 | time-occasions, provenance-trace | Two builders finishing in a cloud container; their in-progress code is on branches `wip/time-occasions` and `wip/provenance` (not yet on GitHub — see *Open questions*). Don't start these two. |

## The goal in one paragraph

A deep, realistic simulation of BYU/UVU social life in Provo–Orem whose connections you can *see*: pick anything (a
person, a dinner, a breakup, a number) and follow what led to it and what it led to, for one life or the whole valley.
The interface becomes a **workbench** of raw tools the owner lays out freely (no pre-built dashboards); every
number shows its scale in words; decisions carry their reasons; occasions (dinners, dates, games) have times, travel
and invitations; the world gains a real Provo calendar, weather, messaging, institutions and families back home.

## Owner decisions (don't relitigate)

- Time and plans: **option B** — planned things have start times and lengths; people check commitments, travel and
  lateness; rides change feasibility; social actions (invite, introduce, ride, study group, recurring dinner,
  reschedule, reach out, job offer) as **world editor** and **as a person** (limited to whom they know, time, money).
- **Full world** (scale 1.0, ~60k people) is the target; optimize along the way.
- **No savable worlds** for now; **no starting cast / "run until"** for now.
- Wanted: calendar + weather; decision records, scenes, Why/Trace; Ask the world + interviews with wording checks
  (the owner has a GPU for a local model and a Claude Pro login — local for interviews, Claude for Ask, choosable);
  messaging/group chats; institutions; family with a broad **US map of home states** (going home for holidays and
  weekends); readable **scales** for every number; a **simpler interface** of raw, assemblable tools.
- **LDS Sexuality Survey**: incorporate (plan in `docs/workstreams/sexuality-survey.md`), **including the five
  dating "dealbreaker" items**; positions, toys, oral-sex endings and birth-control specifics stay out; sensitive
  fields stay out of interviews by default.
- **Only aggregates** (cells ≥ 10) from any survey ever go to GitHub. Raw exports stay in `data/raw/` on the owner's
  machine (and the cloud container). The owner reviews proposals from the survey audit before additions.
- The paused "LLM-invented variables" idea stays paused.

## Status board

| Workstream | State | Where the code is | Next step |
|---|---|---|---|
| Foundation: ledgers (decisions, causes, occasions), 4-block clock, travel interface, contracts, auto-registered routers and workbench tools, CSV survey loader, privacy guard test | **done** | working branch | — |
| [time-occasions](workstreams/time-occasions.md) (option B) | **almost done** | `wip/time-occasions` (10 WIP commits) | finishing in the cloud session: traditions, explain_choice, realism table, perf table |
| [provenance-trace](workstreams/provenance-trace.md) | **almost done** | `wip/provenance` (18 WIP commits) | finishing in the cloud session: coverage goal, polish |
| [workbench](workstreams/workbench.md) | not started | — | start after the two above are merged |
| [scales](workstreams/scales.md) | not started | — | can start any time |
| [sexuality-survey](workstreams/sexuality-survey.md) (+ dealbreakers) | not started | — | needs the raw xlsx in `data/raw/` (owner supplies) |
| [calendar-weather](workstreams/calendar-weather.md) | not started | — | after time-occasions is merged |
| [talk](workstreams/talk.md) (Ask + interviews) | not started | — | after provenance-trace is merged |
| [travel](workstreams/travel.md) | not started | — | can start any time (keeps `ucsim/geo/travel.py`'s interface) |
| [messaging](workstreams/messaging.md) (wave 2) | not started | — | after time-occasions |
| [institutions](workstreams/institutions.md) (wave 2) | not started | — | after time-occasions + provenance |
| [family-homes](workstreams/family-homes.md) (wave 2) | not started | — | after calendar-weather |
| [survey-followups](workstreams/survey-followups.md) | audits designed, interrupted | — | needs the raw survey files in `data/raw/` |
| [integration](workstreams/integration.md) | ongoing | — | after each merge |

Independent enough to run at the same time as others: **scales**, **travel**, **sexuality-survey**. Everything else
waits for time-occasions and provenance-trace to be merged (they change the day's structure and how reasons are
recorded).

## Open questions for the owner

1. May agents push work-in-progress branches (`wip/<workstream>`) to GitHub? Without that, half-finished work done in
   one agent's environment can't be picked up by another until it is merged into the working branch.

## Environment notes

- Raw survey exports (`data/raw/*.csv`, `*.xlsx`) are gitignored; if a workstream needs them and they're missing,
  ask the owner. Never copy them elsewhere or print respondent rows.
- The CSV exports don't reproduce the committed survey aggregates exactly (some multi-select items, College Life
  completes): don't rebuild existing priors; add new sections only (see `docs/workstreams/survey-followups.md`).
- Measured before iteration 6: scale 0.15 ≈ 0.23 s per simulated day, full scale ≈ 1.6 s per day (one core).
- LLM features use the owner's own logins (Claude Code CLI, Codex CLI, or a local OpenAI-compatible server such as LM
  Studio); see docs/WHATIF_LLM.md. Tests never call a real model.

## Session log (newest first)

### 2026-10-18 — Claude Code (cloud session)
- Assessed the project and proposed the iteration-6 plan (owner chose the directions above).
- Built the foundation on the working branch: `ucsim/engine/ledger.py` (DecisionLog, CauseLinks, OccasionBook with
  stable ids and thinning), `ucsim/engine/clock.py` (four blocks), `ucsim/geo/travel.py` (interface + straight-line
  fallback), registry loading of `config/decisions|occasions|events/*.yaml`, `sim.emit(decision=, causes=)`,
  auto-included `ucsim/api/routes_*.py`, the workbench registry/selection (`web/src/bench/`), the Qualtrics CSV survey
  loader, `tests/test_no_raw_survey_data.py`, and `docs/EVOLUTION.md`.
- Ran eight parallel builders; usage limits interrupted them three times. Progress kept for time-occasions and
  provenance-trace (on wip branches); the other six had not started meaningfully. The last few uncommitted edits of
  those two builders were lost once (they were told to redo anything half-done).
- Next: finish and merge those two, then run scales, travel and sexuality-survey alongside workbench, calendar-weather
  and talk; then wave 2 (messaging, institutions, family-homes), the survey audit and integration.
