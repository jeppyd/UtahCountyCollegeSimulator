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
   push that edit. Don't take a workstream someone else holds unless the relay rule below allows it.
4. Work in small steps; **commit and push often** (WIP commits are fine), so running out of usage never strands work.
   Unfinished work goes to a `wip/<workstream>` branch on GitHub (`git push origin HEAD:refs/heads/wip/<workstream>`);
   finished, tested work is merged into the working branch.
   **Relay rule:** if the agent holding a workstream has stopped (its `wip/<workstream>` branch hasn't moved for 2 hours,
   or the owner says it ran out of usage), you may continue it: merge the working branch and `origin/wip/<workstream>`,
   keep pushing to the same `wip/` branch, and write in *Who is working now* and the session log that you took it over.
   The first agent resumes from your pushes the same way.
5. **Before you stop** (or when your usage is getting low): update the *Status board*, append a *Session log* entry
   (what you did, what's half-done and exactly where, what's next, anything surprising), remove your claim, run the
   tests if you can, commit and push. If tests fail, say which and why in the log.

## Who is working now

| Agent | Since (UTC) | Workstream | Notes |
|---|---|---|---|
| Claude Code (cloud session) | 2026-10-18 22:27 | workbench, scales, sexuality-survey, calendar-weather, talk, travel | Six builders, two at a time in this order; each pushes its progress to `wip/<workstream>`. When they stop on usage limits, the relay rule below applies. |

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
| [time-occasions](workstreams/time-occasions.md) (option B) | **done, merged** | working branch | open issues below |
| [provenance-trace](workstreams/provenance-trace.md) | **done, merged** | working branch | open issues below |
| [workbench](workstreams/workbench.md) | in progress (cloud session) | — | also add an Occasion/scene tool on /api/occasion |
| [scales](workstreams/scales.md) | in progress (cloud session) | — | can start any time |
| [sexuality-survey](workstreams/sexuality-survey.md) (+ dealbreakers) | in progress (cloud session) | — | needs the raw xlsx in `data/raw/` (owner supplies) |
| [calendar-weather](workstreams/calendar-weather.md) | in progress (cloud session) | — | after time-occasions is merged |
| [talk](workstreams/talk.md) (Ask + interviews) | in progress (cloud session) | — | after provenance-trace is merged |
| [travel](workstreams/travel.md) | in progress (cloud session) | — | can start any time (keeps `ucsim/geo/travel.py`'s interface) |
| [messaging](workstreams/messaging.md) (wave 2) | not started | — | after time-occasions |
| [institutions](workstreams/institutions.md) (wave 2) | not started | — | after time-occasions + provenance |
| [family-homes](workstreams/family-homes.md) (wave 2) | not started | — | after calendar-weather |
| [survey-followups](workstreams/survey-followups.md) | audits designed, interrupted | — | needs the raw survey files in `data/raw/` |
| [integration](workstreams/integration.md) | ongoing | — | after each merge |

Time-occasions and provenance-trace are merged, so everything in wave 1 can proceed. Wave 2 (messaging,
institutions, family-homes) can start now too, but coordinate: they touch the same systems as the running builders.

**Known open issues after the merge** (for integration):
- Full world is **2.28 s per simulated day** (was 1.6): encounters 0.83 s (the fourth block), activity 0.36, recorder
  0.34, romance 0.24, occasions 0.23. Ledgers at full scale grow ~20k decisions and ~20k invitations a day; with
  120 days of full detail that is a few hundred MB — reduce `sim.detail_days` or compact before long full-scale runs.
- Cause coverage on the merged code: 99% of events, 95% of salient ones (`scripts/provenance_coverage.py`); gaps:
  `ghosted`, `ncmo`, `premarital_sex` (the sexuality builder's romance functions), `illness`, `app_match`.
- Social events per month now match ProvoStats for singles (≈ 8); engaged students run high (≈ 6.5 vs 4.8); the
  couple-time strengths were fitted to these rows, so they are no longer an independent check. Student loneliness fell
  0.30 → 0.26 as social life rose (no loneliness validation row exists).
- `scripts/validate.py` wasn't re-run end to end (it rewrites docs/VALIDATION.md); do that in integration.
- Placeholders for wave 2: `occasions.deliver(inv_ids, channel)` (messaging), `occasions.shift_flex(people, day)`
  (employer flexibility). No workbench tool for occasions yet (endpoints exist: /api/occasion/{id}, /api/occasions,
  /api/person/{i}/day, /api/person/{i}/choice, /api/act/check, /api/act).
- Builders' worktrees may start from `main`: merge the working branch first.

## Open questions for the owner

(none open — 2026-10-18: the owner approved pushing work-in-progress branches `wip/<workstream>` to GitHub.)

## Environment notes

- Raw survey exports (`data/raw/*.csv`, `*.xlsx`) are gitignored; if a workstream needs them and they're missing,
  ask the owner. Never copy them elsewhere or print respondent rows.
- The CSV exports don't reproduce the committed survey aggregates exactly (some multi-select items, College Life
  completes): don't rebuild existing priors; add new sections only (see `docs/workstreams/survey-followups.md`).
- Measured before iteration 6: scale 0.15 ≈ 0.23 s per simulated day, full scale ≈ 1.6 s per day (one core).
- LLM features use the owner's own logins (Claude Code CLI, Codex CLI, or a local OpenAI-compatible server such as LM
  Studio); see docs/WHATIF_LLM.md. Tests never call a real model.

## Session log (newest first)

### 2026-10-18 (night) — Claude Code (cloud session)
- The six remaining wave-1 builders were stopped by usage limits within minutes (no progress); restarted at 22:27 UTC
  with work-in-progress pushed to `wip/<workstream>` branches (owner approved). Added the relay rule above.

### 2026-10-18 (evening) — Claude Code (cloud session)
- Merged **time-occasions** (four-block day; shifts with clock times; occasions with hosting, invitations, noticing,
  feasibility with travel and lateness, attendance, no-shows, walk-ins; dates and dances as occasions; weekly
  traditions that pass to housemates or end; social actions as editor and as a person; explain_choice; endpoints) and
  **provenance-trace** (decisions with factors across romance, friendship, plans, coping, economy, housing, faith,
  life course, academics; typed causes; tie "where their time together accrued"; scene counts; the trace engine and
  chains; Trace and Chains tools; DecisionCard). One trivial conflict (faith.py imports). 168 tests pass; web build
  passes; coverage 99%; full scale 2.28 s/day.
- Launched the remaining six wave-1 builders.

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
