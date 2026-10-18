# Workstream: Survey follow-ups and audit

> Status: docs/HANDOFF.md. Rules: README.md (privacy rules are non-negotiable).

1. **Dealbreakers** (approved by the owner) — part of `sexuality-survey.md` §2b if not already done there.
2. **Audit of all five surveys** for items and relationships left on the table. Two audits were designed (they were
   interrupted by usage limits before finishing):
   - Items the model reads but under-uses (spec items harmonized but unused; starting values that should also drive a
     mechanism or be validation targets; relationships between variables the model lacks — e.g. cross-survey links only
     through bridge variables, within-survey correlations not carried into synthesis).
   - Questions never read into the model (the raw CSV exports of the four original surveys are in `data/raw/` on the
     owner's machine: provostats, college-life, dating, culture-lifestyle). Ignore free text, contact details and
     trivia; judge substantive items (summer sales, mission details, roommate situation, dancing habits and what would
     make people go, racism/sexism experiences, family structure, mental-health self-rating, post-graduation plans,
     academic honesty, clubs, "waiting for a missionary", having been cheated on, College Life's "How many…" counts,
     confidence about the future, extraversion self-rating…).
   Output: a short add / consider / leave-out list for the owner with the aggregate evidence (cells ≥ 10). Only add
   what changes behavior or can be validated.
3. **Note on the CSV exports**: re-reading them reproduces ~73% of the committed aggregates exactly; some multi-select
   items count about twice as many answers as the JSON exports the priors were built from, and College Life has 35
   more complete responses. Do **not** silently rebuild the existing priors; add new sections only, or rebuild
   deliberately with a full validation pass.
