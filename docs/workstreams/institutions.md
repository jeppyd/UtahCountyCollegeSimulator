# Workstream: Institutions with constraints (wave 2)

> Status: docs/HANDOFF.md. Rules: README.md. Contract: docs/EVOLUTION.md §7. Needs `time-occasions` and `provenance-trace` merged.

Give organizations capacities, budgets, hours, eligibility, priorities and response delays; let them run their own
events and adapt. Keep the owner-facing controls approachable: cost, capacity, access, and what happens when demand
exceeds supply.

1. `ucsim/engine/systems/institutions.py` with an institution table (kind, ref id, capacity, budget, weekly hours,
   eligibility as a query-DSL filter, priority rule, response delay, state: demand, served, waitlist, utilization).
2. **Clubs/teams/institute classes** (extend `systems/groups.py`): officers plan weekly meetings and occasional socials
   as occasions; attendance tracked; if attendance falls below a threshold for several weeks they adapt (change night,
   add food, recruit) — recorded as institution decisions; if crowded past capacity they cap or split.
3. **Wards**: an activities committee plans ward activities and service projects (occasions) within a modest budget;
   the bishop has limited interview hours per week, so confessions/temple-recommend/worthiness interviews wait (the
   existing `bishop_confession` pathway gets a queue and delays).
4. **Counseling services** (BYU CAPS, UVU's counseling center; new entities with locations): people in a depressive
   episode or high coping need may seek help (a decision); capacity × sessions/week, waitlists, eligibility (enrolled
   students), crisis priority; being seen brings relief through the coping system; waits are visible and traceable.
   Label capacity figures as approximate unless sourced.
5. **Employers**: openings by type and season (campus jobs at semester start, retail before Christmas, summer-sales
   recruiting in winter with summers away — `summer_sales` exists), schedule flexibility (whether a shift swap or time
   off is granted when an occasion conflicts: hook `occasions.shift_conflict`), hiring as a decision by the employer.
6. **Complexes**: management-run resident events (pool parties, free food) as open occasions for residents.
7. Conditional What-ifs reuse the same machinery ("if attendance falls below X, then…"): add an intervention atom for
   institution rules.
8. API `routes_institutions.py`; workbench tool `Institution.tsx` (capacity, demand, waitlist and decisions over time,
   who was served/turned away, clickable). Tests for queues, adaptation and determinism.
