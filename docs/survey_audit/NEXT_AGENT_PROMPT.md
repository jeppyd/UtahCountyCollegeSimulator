# Prompt for the agent who takes over the survey audit

Copy everything below the line into a new Claude Code session on this repository.

---

You are continuing the **survey-followups** workstream of the Provo–Orem Social Simulator
(repo jeppyd/UtahCountyCollegeSimulator, branch `claude/festive-archimedes-1llpw1`).

1. Follow CLAUDE.md / AGENTS.md and `docs/HANDOFF.md` (claim the workstream in "Who is working now"; work on a
   branch `wip/survey-followups`; commit and push often; never push to or merge into `main`).
2. Read `docs/workstreams/survey-followups.md` (the audit's goals and the CSV caveats) and
   `docs/survey_audit/inventory.md` (step 1: every column of the four surveys, how many answered it, and which model
   variable reads it; blank = never read).
3. **The raw survey files.** They are private and never go to GitHub. If `data/raw/` doesn't have `provostats.csv`,
   `college-life.csv`, `dating.csv` and `culture-lifestyle.csv`, ask the owner to upload the four Qualtrics CSV
   exports (June 29, 2025) and copy them to exactly those names. Never print, commit or quote individual
   responses; only aggregates with at least 10 respondents per cell may be written anywhere. `tests/test_no_raw_survey_data.py`
   must pass.
4. **Step 2 — judge the never-read questions.** For each substantive never-read column (ignore free text, contact
   details, trivia), compute aggregates (shares, means by sex / school / church activity where every cell ≥ 10) and
   decide **add / consider / leave out**: add only what would change behaviour in the model or can serve as a
   validation target. Give extra attention to: waiting for a missionary, mission details and obedience, roommate
   situation, dancing habits and what would make people go, racism/sexism experiences, family structure,
   mental-health self-ratings (OCD, eating), post-graduation plans, academic honesty, clubs (intramurals, choir),
   having been cheated on, College Life's "How many…" counts, confidence about the future, extraversion self-rating,
   dating-app use by app (Mutual, Hinge, Tinder, Bumble) and what each is used for, ask preferences (text / phone /
   in person), dating in one's own ward, ministering, attending the second hour, family history, Sabbath
   social-media use, LGBTQ members' sense of safety at church.
5. **Step 3 — under-used items** (the second audit in the workstream file): items the model reads at start-up but
   never lets drive a mechanism, and within-survey correlations the synthesis doesn't carry.
6. Write the findings as `docs/survey_audit/findings.md`: a short add / consider / leave-out list with the aggregate
   evidence. The owner reviews it before anything is added to the model. Don't silently rebuild the existing priors
   (the CSVs reproduce only ~73% of the committed aggregates; see the workstream file).
7. Before handing off: `python -m pytest -q` (includes the privacy test and the speed budget); update the HANDOFF
   status board and session log; give the owner a short plain-language summary.

Context the owner already gave (from the previous session): they want new layers that are realistic, interesting
and relevant. The recommended ones were ward life (callings, ministering), reputation / word of mouth, missions in
people's lives (waiting for a missionary, returned missionaries), roommates and apartment life, dating apps in
detail, health basics (sleep, exercise, screens), belonging when you're different (handle sensitively; keep out of
AI interviews by default), and campus events and clubs. The audit should say which survey questions support each.
