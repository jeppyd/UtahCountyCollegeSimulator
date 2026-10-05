"""The lever catalog: every knob a compiled What-if may turn, with what it does, its bounds and its pitfalls.

The same tables drive (1) the Markdown catalog the LLM reads, (2) the validator that checks the LLM's plan, and
(3) the receipt the user sees. Nothing here is free text the engine trusts: the validator enforces it.
"""
from __future__ import annotations

from ..engine.interventions import (ADOPTABLE, CHOICE_OPTIONS, INJECTABLE, MOTIVES, OFFSET_CHANNELS, STATES,
                                    VISITED_VTYPES)

# world key -> (type, lo, hi, what it does, timing). Only keys the engine reads every day are allowed.
WORLD_LEVERS: dict[str, tuple[str, float, float, str, str]] = {
    "coffee_permitted": ("bool", 0, 1, "Church permits coffee (Word of Wisdom): removes the coffee prohibition from adoption, guilt and temple-recommend eligibility; members who want to start may.", "weekly adoption, nightly guilt"),
    "alcohol_permitted": ("bool", 0, 1, "Church permits alcohol: removes the alcohol prohibition from adoption, guilt, quitting and temple-recommend eligibility; belief-based abstention remains a personal choice.", "weekly adoption, nightly guilt"),
    "contracted_housing_required": ("bool", 0, 1, "BYU requires single first-year undergrads to live in BYU-contracted housing (true today).", "only when people move: leases turn over Apr 30 and Aug 20, plus arrivals"),
    "contracted_housing_all_years": ("bool", 0, 1, "Extends the contracted-housing rule to every single BYU undergrad (the pre-2022 rule).", "only when people move"),
    "interfaith_welcome": ("float", 0, 1, "How actively campuses and wards welcome people of other faiths and none: lowers non-members' outsider feeling, raises their club joining.", "weekly"),
    "marriage_norm": ("float", 0.05, 3, "Cultural pressure to marry young (1 = today): dating motivation, engagement hazard, longing, how much partnership matters.", "daily/weekly"),
    "men_initiate_norm": ("float", -1, 3, "How strongly asking out is expected of men (1 = today, 0 = symmetric, negative = women ask more).", "daily"),
    "church_attendance_norm": ("float", 0.05, 4, "Multiplier on the odds of LDS Sunday attendance (log-odds += ln value).", "from next Sunday"),
    "mission_norm": ("float", 0.05, 4, "Multiplier on the odds of a mission call (log-odds += ln value).", "monthly calls; departures 75–115 days later"),
    "app_appeal": ("float", 0.05, 5, "Dating-app appeal: app match rate and app adoption.", "daily matches, weekly adoption"),
    "unemployment": ("float", 0.005, 0.3, "Utah County unemployment rate (0.032 today): job loss and job finding.", "month end"),
    "wage_index": ("float", 0.3, 3, "Multiplier on earned income.", "month end"),
    "tuition_byu": ("float", 0, 30000, "BYU tuition per semester in USD (3500 today); a monthly expense for enrolled BYU students.", "month end"),
    "tuition_uvu": ("float", 0, 30000, "UVU tuition per semester in USD (3100 today).", "month end"),
    "rent_shock": ("float", 0.3, 3, "Exogenous rent multiplier on top of the market (1 = today).", "month end budgets; movers compare prices immediately"),
    "housing_supply_index": ("float", 1, 2, "Target housing stock relative to today (new apartments get built, ≤4% per month); values below 1 do nothing.", "monthly construction"),
    "enrollment_index": ("float", 0.5, 2, "Size of the incoming cohorts relative to today.", "only on Aug 20 (the yearly cohort)"),
    "temp_delta": ("float", -25, 25, "Temperature shift in °F on every day: outdoor appeal and outdoor dates.", "daily"),
}

# person-variable persistence classes (verified against the engine's write sites)
IDENTITY = {"sex", "orientation", "ethnicity", "origin_region"}
COMPUTED = {*(f"drive_{m}" for m in MOTIVES), "sat_fun", "sat_health", "top_priority", "dating_motivation", "coping_need", "age",
            "activity_now", "loc_lon", "loc_lat", "perceived_support", "perceived_friend_belief", "perceived_norm", "support_actual",
            "friend_belief_actual", "porn_incongruence", "relationship_commitment", "routine_strength", "class_attendance",
            "n_friends", "n_close_friends", "n_acquaintances", "degree", "new_friends_90d", "roommate_cohesion", "n_memories",
            "memory_tone", "home_social_culture", "home_faith_culture", "activity", "monthly_income", "rent_burden",
            "dist_campus_km", "commute_min", "class_standing", "n_groups"}
INERT = {"family_structure", "parents_divorced", "weight_lb", "bmi", "body_build", "hair_color", "eye_color", "raised_lds",
         "garments", "plans_to_leave", "traditional_roles", "att_gay_marriage_legal", "expects_ssm_change",
         "supports_women_priesthood", "future_confidence", "men_first_move", "imp_personality", "mh_adhd", "tea", "r_movies",
         "reading", "cooking", "arts", "swiftie", "major_id", "college", "homework_early", "cheats_school", "enroll_day", "languages"}
SMOOTHED = {"service_attend", "outsider", "attend_rate", "rejections_recent", "dates_30d", "relationship_satisfaction",
            "social_hours_week", "close_contact_hours", "ward_belonging", "life_satisfaction", "study_hours", "coping_relief",
            "social_events_month", *(f"cares_{m}" for m in MOTIVES)}
ANCHORED = {"sleep_hours", "temple_per_year", "scripture_minutes", "work_hours"}
STOCK = {"savings", "debt", "gpa", "wage", "parental_support", "owns_car"}
LEARNED = {"faith_belief", "faith_certainty", "religious_identity", "practice_habit", "own_religiosity", "orthodoxy",
           "moral_autonomy", "institutional_trust", "chastity_commitment", "expect_accept", "expect_social", "self_eff_academic",
           "coffee", "alcohol", "pickleball", "app_user", "app_hours"}
# read by the engine only as population z-scores: an "everyone" shift washes out within a week — target a subgroup
Z_RELATIVE = {"extraversion", "conscientiousness", "neuroticism", "agreeableness", "openness", "sensation_seeking",
              "social_anxiety", "self_control"}
# smoothed/anchored variables have a better lever: the nudge channel that drives them
BETTER_CHANNEL = {"attend_rate": "attend", "service_attend": "attend", "sleep_hours": "sleep", "study_hours": "study",
                  "dates_30d": "dating", **{f"cares_{m}": f"cares:{m}" for m in MOTIVES}}


def persistence(v) -> str:
    vid = v.id
    if vid in IDENTITY:
        return "identity"
    if vid in STATES:
        return "composed"
    if vid in COMPUTED:
        return "computed"
    if vid in INERT:
        return "inert"
    if vid in SMOOTHED:
        return "smoothed"
    if vid in ANCHORED:
        return "anchored"
    if vid in STOCK:
        return "stock"
    if vid in LEARNED:
        return "learned"
    if v.derived or v.kind == "derived" or v.update == "hourly":
        return "computed"
    if v.dtype in ("cat", "i4", "i2", "str") or v.kind in ("structural", "history") or v.update == "event":
        return "structural"
    if v.kind in ("trait", "preference", "belief", "habit", "attribute"):
        return "stable"
    return "learned"


TRAIT_OK = ("stable", "learned", "stock", "anchored", "smoothed")


def person_vars(reg):
    return [v for v in reg.variables.values() if getattr(v, "entity", "person") == "person" and "." not in v.id]


def trait_class(reg, vid: str) -> str | None:
    v = reg.variables.get(vid)
    return persistence(v) if v is not None else None


# ---------------------------------------------------------------------- Markdown catalog for the LLM
def _rng(v) -> str:
    if v.dtype == "bool":
        return "true/false"
    if v.dtype == "cat":
        return "categories " + "|".join(v.categories or [])
    if v.range:
        return f"[{v.range[0]}, {v.range[1]}]"
    return ""


def catalog_markdown(reg, sim=None) -> str:
    """The full lever catalog (stable for a given registry; world-specific facts go in the request context)."""
    L = []
    a = L.append
    a("# UCSim lever catalog\n")
    a("Every change you propose must use one of the kinds below with exactly these ids. Anything not listed does not exist in the model.\n")
    a("## 1. kind `world`: policy switches, norms, prices, weather\n")
    a("Re-applied every day while active and reverted when `duration_days` ends. Ops: `set` (required for true/false), `mul`, `add`.\n")
    a("| target | type | allowed | what it does | when it bites |\n|---|---|---|---|---|")
    for k, (t, lo, hi, what, when) in WORLD_LEVERS.items():
        a(f"| `{k}` | {t} | {'true/false' if t == 'bool' else f'{lo}–{hi}'} | {what} | {when} |")
    a("\nNot levers (do not use): `rent_index` (market-driven), `transit_quality` (no behavior reads it), `social_media_intensity` (unused), and any calendar/derived key (`temp_f`, `holiday`, `term_*`).\n")

    a("## 2. kind `nudge`: a persistent push on a feeling or behavior for a group\n")
    a("Active from `start_offset_days` for `duration_days` (or forever), ramped over `ramp_days`, applied to everyone matching `who` (re-checked weekly, so newcomers count). `value` is added to the channel. Use when no structural lever exists or a direct psychological effect is the point (\"students feel safer\", \"dating feels more fun\").\n")
    a("| target (channel) | units | sensible |value| | what it moves |\n|---|---|---|---|")
    for ch, (units, bound, what) in OFFSET_CHANNELS.items():
        typical = {"state": "0.01 small · 0.03 noticeable · 0.06 strong · 0.1 extreme", "logit": "0.2 small · 0.5 noticeable · 1 strong · 2 extreme",
                   "utility": "0.3 small · 0.8 noticeable · 1.5 strong · 3 near-certain", "hours": "0.5 small · 1 noticeable · 2 strong"}[units]
        a(f"| `{ch}` | {units} (max {bound}) | {typical} | {what} |")
    a("\nFeelings are composed every night from their drivers; a nudge of 0.03 is about one standard deviation of day-to-day noise. Positive on `stress`/`loneliness`/`anxiety`/`guilt`/`fatigue` means worse. Free-time options: " + ", ".join(f"`choice:{o}`" for o in CHOICE_OPTIONS) + ". Practices with an adoption channel: " + ", ".join(f"`adopt:{k}`" for k in ADOPTABLE) + ".\n")

    a("## 3. kind `event`: inject a real event type into a group (an impulse)\n")
    a("Each person picked gets the event: appraisal by what they care about, feelings with the event's own half-lives, a memory, possibly a coping episode. `share` picks a stable random fraction; `severity` scales every effect (0.25–4); `repeat_every_days` repeats it while active.\n")
    a("| target | label | effects (var ±mag / half-life days) |\n|---|---|---|")
    for e in INJECTABLE:
        spec = reg.events[e]
        eff = ", ".join(f"{x['var']} {x['mag']:+g}/{x['half_life']}" for x in spec.effects)
        a(f"| `{e}` | {spec.label} | {eff} |")
    a("\n## 4. kind `shock`: a custom event with your own label and effects\n")
    a("For things the model has no event for (a fire, a viral video, a tragedy, a concert, a scandal, an announcement). Give `event_label` (≤ 40 chars), `story` (uses `{a}` for the person, e.g. \"{a} lost their home in the Helaman Halls fire\"), `motive` (the concern it touches: " + ", ".join(MOTIVES) + "), `valence` (−1 awful … +1 wonderful), `salience` (0.3 barely remembered … 0.85 unforgettable; avoid ≥0.8 for big groups), and 1–6 `effects` on feelings (" + ", ".join(STATES) + ").\n")
    a("Strength ladder per effect (|mag|, half-life days): tiny 0.01–0.02/2–5 (being ghosted) · small 0.03–0.05/4–20 (a conflict) · medium 0.06–0.10/7–60 (a failed exam, a new job) · large 0.10–0.16/21–90 (a family crisis, losing a job) · extreme 0.16–0.30/45–365 (a breakup, a death in the family, a wedding). |mag| ≤ 0.3.\n")

    a("## 5. kind `trait`: change who people are (once, permanently)\n")
    a("Applied once at the start to everyone matching `who`, clipped to the variable's range; the model's own dynamics carry it from there. Ops `set`/`add`/`mul`. Integer and true/false variables take `set` with a valid value. Only these variables may be targeted:\n")
    groups: dict[str, list[str]] = {}
    for v in person_vars(reg):
        cls = persistence(v)
        if cls not in TRAIT_OK or v.dtype in ("cat", "str"):
            continue
        note = ""
        if v.id in Z_RELATIVE:
            note = " — relative (read as a z-score): only a subgroup shift lasts"
        if v.id in BETTER_CHANNEL:
            note += f" — prefer nudge `{BETTER_CHANNEL[v.id]}`"
        if cls == "smoothed":
            note += " — decays back within weeks"
        groups.setdefault(cls, []).append(f"`{v.id}` {v.label} ({v.dtype} {_rng(v)}){note}")
    titles = {"stable": "Stable traits, values, habits and preferences (persist)", "learned": "Learned beliefs, habits and expectations (persist, then keep evolving)",
              "stock": "Stocks (persist; monthly or term flows keep running)", "anchored": "Anchored (relax back toward a hidden personal anchor)",
              "smoothed": "Smoothed (a pulse that decays)"}
    for cls in TRAIT_OK:
        if cls in groups:
            a(f"\n**{titles[cls]}**: " + "; ".join(groups[cls]) + ".")
    a("\nNever target: composed feelings (use a nudge), computed quantities, structural states (relationship status, membership, school, home, job, ward — the model has no safe direct switch; use events, nudges, closures or world levers), identity, or variables no mechanism reads (" + ", ".join(sorted(INERT)) + ").\n")

    a("## 6. kind `param`: a mechanism parameter (affects everyone)\n")
    a("`target` = `<mechanism id>.<param>`; ops `set`/`mul`/`add`; re-applied daily, reverted at the end of `duration_days`. Stay inside the listed range unless the scenario truly is extreme (say so). Evidence: observed > empirical > literature > calibrated > extrapolated > structural > hypothetical > speculative.\n")
    by_sys: dict[str, list] = {}
    for mid, m in reg.mechanisms.items():
        if m.system == "whatif" or not m.params:
            continue
        by_sys.setdefault(m.system, []).append((mid, m))
    for sysname, items in by_sys.items():
        a(f"\n### {sysname}")
        for mid, m in items:
            ps = []
            for pn, spec in m.params.items():
                if spec.get("structural"):
                    continue
                r = spec.get("range")
                ps.append(f"`{pn}`={spec['value']}" + (f" [{r[0]}, {r[1]}]" if r else ""))
            if not ps:
                continue
            form = (m.form or "").replace("\n", " ")
            form = form if len(form) <= 170 else form[:167] + "…"
            a(f"- `{mid}` — {m.label} ({m.evidence}). {form} Params: " + ", ".join(ps))

    a("\n## 7. kind `close`: close a place (reopens when `duration_days` ends)\n")
    a("`target` = `complex:<id>` (every unit closes; residents — including those away for the summer — are rehoused under the housing rules: contracted housing first for freshmen, same-sex units only, couples together), `venue:<id>` (one venue), or `venue_type:<type>` (every venue of a type, e.g. all gyms; people pick another option instead). Visited venue types: " + ", ".join(VISITED_VTYPES) + ". Bars and libraries exist but nobody visits them in the model.\n")
    a("## 8. kind `place`: change a housing complex\n")
    a("`target` = `complex:<id>`; `attr` = `rent` (op `mul`, 0.3–3; current residents' rent updates), `beds` (op `mul`, 0–3: capacity per unit), `quality` (op `add`, −1…1: how attractive to movers), or `contracted` (op `set`, true/false: BYU-contracted status).\n")
    a("## 9. kind `practice`: a new behavior that spreads through friendships\n")
    a("For things that catch on (\"beards become common at BYU\", \"cold plunges\", \"everyone gets a dog\"). Give `practice_label` (e.g. \"Wearing a beard\"), `who` = who can adopt (e.g. men), `seed_share` (0–0.5 adopt at the start), `base` (weekly adoption log-odds before friends: −6 rare … −3 eager), `traits` (list of {var, weight}: numeric person variables, read as z-scores, weights −1…1), `peer` (0–3: how contagious, 1 = like coffee), `quit` (weekly quit chance, 0–0.1), and `effects_while` (feelings while adopted: list of {var, value} with |value| ≤ 0.1). Its adoption curve is shown on the What-if page.\n")
    a("## 10. kind `venue`: a new business opens\n")
    a("`venue` = {name, vtype (one of the visited types), lon, lat} inside Provo/Orem (lon −111.80…−111.60, lat 40.20…40.35). BYU is at (−111.649, 40.250), UVU at (−111.713, 40.277). People nearby start choosing it; this reroutes some nearby outings (butterfly effects).\n")

    a("## 11. `who`: population filters\n")
    a("""A JSON filter (omit or null = everyone present):
- `{"var": "school", "op": "eq", "value": "BYU"}` — categorical by exact label; bool vars take true/false
- `{"and": [f, …]}`, `{"or": [f, …]}`, `{"not": f}`
- ops: eq, ne, lt, le, gt, ge, between ([lo, hi]), in / notin (lists), quantile_ge / quantile_le (top/bottom share of everyone present)
- `{"ids": [12, 40]}` specific people · `{"friends_of": f, "min_stage": 3}` people with a friendship (3 friend, 4 close) to anyone in f, f excluded · `{"share": 0.3, "of": f}` a stable random 30% of f · `{"recent_event": "breakup_received", "days": 90}` · `{"all": true}`
- place links: `complex_id`, `ward_id`, `employer_id`, `club_id`, `team_id`, `institute_class`, `congregation_id`, `major_id` (eq the entity id); `neighborhood`, `city` (labels)
- students: `{"and": [{"var": "school", "op": "eq", "value": "BYU"}, {"var": "enrolled", "op": "eq", "value": true}]}`. In May–August most BYU single undergrads are away, so cohorts shrink in summer.
""")
    a("Categorical variables and their exact labels:")
    for v in person_vars(reg):
        if v.dtype == "cat" and v.categories and len(v.categories) <= 70:
            a(f"- `{v.id}`: " + " | ".join(v.categories))
    a("\nUseful numeric and true/false filter variables: " + ", ".join(f"`{v.id}`" for v in person_vars(reg)
                                                                  if v.dtype in ("bool", "f4", "u1", "i2") and "filter" in (v.flags or []))[:6000])

    from ..engine.interventions import load_presets
    a("\n## 12. Ready-made What-ifs (patterns you can reuse or extend)\n")
    for pid, pr in load_presets().items():
        parts = pr.get("parts") or [pr]
        atoms = "; ".join(f"{q.get('target_type')} {q.get('target', '')} {q.get('op', '')} {q.get('value', '') if not isinstance(q.get('value'), dict) else ''}".strip() for q in parts)
        a(f"- `{pid}` — {pr.get('name')}: {atoms}")
    return "\n".join(L) + "\n"
