"""Turn harmonized respondent tables into *aggregate* priors (committed to git).

Privacy design
--------------
* Only aggregates leave this module: smoothed conditional probability tables,
  coarse quantile tables (1st..99th percentile; extreme tails are never stored),
  rank-correlation matrices, and summary targets.
* Cells with fewer than K_MIN respondents are never stored on their own; they are
  replaced by a smoothed back-off to a coarser cell.
* No free text, no respondent ids, no timestamps are carried over.

Statistical design
------------------
* Skeleton attributes use sequential conditional probability tables (a Bayesian-
  network-style synthesis) with hierarchical Dirichlet smoothing.
* Domain attributes from each survey are modelled with a Gaussian copula:
  within-sex normal scores, pairwise-complete Pearson correlation of the scores,
  projected to the nearest positive-definite correlation matrix.  Synthesis
  samples domain variables conditional on whatever the agent already has
  (bridge variables), which is the classical statistical-matching setup with an
  explicit conditional-independence assumption across surveys.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import numpy as np
import polars as pl
from scipy.stats import norm

from .surveys import load_all

K_MIN = 10          # minimum respondents for a stored cell
CORR_MIN_N = 30     # minimum pairwise n for a stored correlation
QGRID = np.round(np.linspace(0.01, 0.99, 99), 4)
PRIORS_DIR = Path(__file__).resolve().parents[1] / "priors"


# ----------------------------------------------------------------------------- helpers
def age_band(age):
    if age is None:
        return None
    a = float(age)
    if a < 20:
        return "18-19"
    if a < 22:
        return "20-21"
    if a < 24:
        return "22-23"
    if a < 27:
        return "24-26"
    if a < 31:
        return "27-30"
    return "31+"


def _with_bands(df: pl.DataFrame) -> pl.DataFrame:
    return df.with_columns(age_band=pl.col("age").map_elements(age_band, return_dtype=pl.Utf8))


def cpt(df: pl.DataFrame, target: str, given: list[str], levels: list, alpha: float = 8.0) -> dict:
    """Hierarchically smoothed P(target | given...) with back-off to shorter conditioning sets."""
    d = df.filter(pl.col(target).is_not_null())
    for g in given:
        d = d.filter(pl.col(g).is_not_null())
    lv = list(levels)

    def dist(sub: pl.DataFrame) -> np.ndarray:
        vc = dict(sub[target].value_counts().iter_rows())
        return np.array([vc.get(l, 0) for l in lv], dtype=float)

    root_counts = dist(d)
    root = (root_counts + 0.5) / (root_counts.sum() + 0.5 * len(lv))
    tables = {"": [round(float(x), 5) for x in root]}
    prev = {"": root}
    for depth in range(1, len(given) + 1):
        gs = given[:depth]
        cur = {}
        for keyvals, sub in d.group_by(gs):
            keyvals = keyvals if isinstance(keyvals, tuple) else (keyvals,)
            parent_key = "|".join(str(k) for k in keyvals[:-1])
            parent = prev.get(parent_key, root)
            counts = dist(sub)
            n = counts.sum()
            p = (counts + alpha * parent) / (n + alpha)
            key = "|".join(str(k) for k in keyvals)
            cur[key] = p
            if n >= K_MIN:
                tables[key] = [round(float(x), 5) for x in p]
        prev = cur
    return {"target": target, "given": given, "levels": lv, "table": tables}


def quantiles(x: np.ndarray) -> list[float]:
    x = x[np.isfinite(x)]
    if len(x) < K_MIN:
        return []
    return [round(float(v), 3) for v in np.quantile(x, QGRID, method="inverted_cdf")]


def num_cpt(df: pl.DataFrame, target: str, given: list[str]) -> dict:
    """Quantile tables of a numeric target by conditioning cells (with back-off)."""
    d = df.filter(pl.col(target).is_not_null())
    tables = {"": quantiles(d[target].to_numpy().astype(float))}
    for depth in range(1, len(given) + 1):
        gs = given[:depth]
        sub_d = d
        for g in gs:
            sub_d = sub_d.filter(pl.col(g).is_not_null())
        for keyvals, sub in sub_d.group_by(gs):
            keyvals = keyvals if isinstance(keyvals, tuple) else (keyvals,)
            if sub.height >= max(K_MIN, 25):
                tables["|".join(str(k) for k in keyvals)] = quantiles(sub[target].to_numpy().astype(float))
    return {"target": target, "given": given, "qgrid": [float(q) for q in QGRID], "table": tables}


def _normal_scores(x: np.ndarray) -> np.ndarray:
    """Mid-rank normal scores; NaN preserved."""
    out = np.full(len(x), np.nan)
    m = np.isfinite(x)
    if m.sum() < 3:
        return out
    from scipy.stats import rankdata
    r = rankdata(x[m], method="average")
    out[m] = norm.ppf((r - 0.5) / m.sum())
    return out


def nearest_corr(a: np.ndarray, eps: float = 1e-4) -> np.ndarray:
    """Project a symmetric matrix to the nearest correlation matrix (eigenvalue clipping)."""
    a = (a + a.T) / 2
    for _ in range(50):
        w, v = np.linalg.eigh(a)
        if w.min() >= eps:
            break
        w = np.clip(w, eps, None)
        a = v @ np.diag(w) @ v.T
        d = np.sqrt(np.diag(a))
        a = a / np.outer(d, d)
    np.fill_diagonal(a, 1.0)
    return a


def copula_block(df: pl.DataFrame, name: str, variables: dict[str, str], description: str) -> dict:
    """variables: name -> kind ('num' | 'ord' | 'bin').  Marginals are stored per sex."""
    df = df.filter(pl.col("sex").is_in(["M", "F"]))
    names = [v for v in variables if v in df.columns]
    scores = np.full((df.height, len(names)), np.nan)
    marginals = {}
    sexes = df["sex"].to_numpy()
    for j, v in enumerate(names):
        col = df[v].cast(pl.Float64).to_numpy()
        marg = {"kind": variables[v]}
        for s in ("M", "F"):
            m = sexes == s
            xs = col[m]
            scores[m, j] = _normal_scores(xs)
            xs = xs[np.isfinite(xs)]
            if variables[v] == "num":
                q = quantiles(xs)
                marg[s] = q if q else None
            else:
                if len(xs) >= K_MIN:
                    vals, cnt = np.unique(xs.astype(int), return_counts=True)
                    k = int(np.nanmax(df[v].cast(pl.Float64).to_numpy())) + 1
                    probs = np.zeros(k)
                    probs[vals] = cnt
                    marg[s] = [round(float(p), 5) for p in (probs + 0.25) / (probs.sum() + 0.25 * k)]
                else:
                    marg[s] = None
            marg[f"n_{s}"] = int(len(xs)) if len(xs) >= K_MIN else 0
        # fall back to the other sex's marginal when one is missing (e.g. sex-specific items)
        if marg["M"] is None and marg["F"] is not None:
            marg["M"] = marg["F"]
        if marg["F"] is None and marg["M"] is not None:
            marg["F"] = marg["M"]
        marginals[v] = marg
    keep = [j for j, v in enumerate(names) if marginals[v]["M"] is not None]
    names = [names[j] for j in keep]
    scores = scores[:, keep]
    k = len(names)
    corr = np.eye(k)
    nmat = np.zeros((k, k), dtype=int)
    for i in range(k):
        for j in range(i + 1, k):
            m = np.isfinite(scores[:, i]) & np.isfinite(scores[:, j])
            n = int(m.sum())
            nmat[i, j] = nmat[j, i] = n
            if n >= CORR_MIN_N:
                a, b = scores[m, i], scores[m, j]
                if a.std() > 0 and b.std() > 0:
                    r = float(np.corrcoef(a, b)[0, 1])
                    # shrink toward 0 for small n (James-Stein-like)
                    corr[i, j] = corr[j, i] = r * (n / (n + 20))
    corr = nearest_corr(corr)
    return {
        "name": name,
        "description": description,
        "variables": names,
        "marginals": {v: marginals[v] for v in names},
        "corr": [[round(float(x), 4) for x in row] for row in corr],
        "n_respondents": int(df.height),
        "min_pair_n": int(nmat[np.triu_indices(k, 1)].min()) if k > 1 else 0,
    }


def summarize(df: pl.DataFrame, var: str, by: list[str]) -> list[dict]:
    """Group summaries for validation targets (cells with n < K_MIN suppressed)."""
    d = df.filter(pl.col(var).is_not_null())
    for b in by:
        d = d.filter(pl.col(b).is_not_null())
    rows = []
    for keyvals, sub in d.group_by(by):
        keyvals = keyvals if isinstance(keyvals, tuple) else (keyvals,)
        if sub.height < K_MIN:
            continue
        x = sub[var].cast(pl.Float64).to_numpy()
        rows.append({**{b: k for b, k in zip(by, keyvals)}, "n_band": _nband(sub.height),
                     "mean": round(float(x.mean()), 3), "median": round(float(np.median(x)), 3),
                     "p25": round(float(np.quantile(x, 0.25)), 3), "p75": round(float(np.quantile(x, 0.75)), 3),
                     "share_pos": round(float((x > 0).mean()), 3)})
    return sorted(rows, key=lambda r: tuple(str(r[b]) for b in by))


def _nband(n: int) -> str:
    return "10-29" if n < 30 else "30-99" if n < 100 else "100-299" if n < 300 else "300+"


def counts_table(df: pl.DataFrame, col: str, min_count: int = 5, by: str | None = None) -> dict:
    d = df.filter(pl.col(col).is_not_null())
    if by is None:
        vc = d[col].value_counts().sort("count", descending=True)
        tot = d.height
        return {r[0]: round(r[1] / tot, 5) for r in vc.iter_rows() if r[1] >= min_count}
    out = {}
    for keyvals, sub in d.group_by(by):
        kv = keyvals[0] if isinstance(keyvals, tuple) else keyvals
        if sub.height >= 30:
            out[str(kv)] = counts_table(sub, col, min_count)
    return out


# ----------------------------------------------------------------------------- build
def build(write: bool = True) -> dict:
    frames = load_all(write=True)
    ps = _with_bands(frames["provostats"])
    cl = _with_bands(frames["college-life"])
    dt = _with_bands(frames["dating"])
    cu = _with_bands(frames["culture-lifestyle"])
    # Restrict to the target ecosystem: young adults (17-40).
    def scope(df):
        return df.filter((pl.col("age") >= 17) & (pl.col("age") <= 40) & pl.col("sex").is_in(["M", "F"]))
    ps, cl, dt, cu = scope(ps), scope(cl), scope(dt), scope(cu)
    ps_local = ps.filter(pl.col("local") == 1)
    ps_students = ps_local.filter(pl.col("school_proxy").is_in(["BYU", "UVU"]))

    skeleton = {
        "rel": cpt(ps_local.filter(pl.col("school_proxy").is_not_null()), "rel",
                   ["school_proxy", "sex", "age_band"], ["single", "dating", "engaged", "married", "divorced"]),
        "lds": cpt(ps_local, "lds", ["school_proxy"], [0, 1]),
        "activity": cpt(ps_local.filter(pl.col("lds") == 1), "activity", ["school_proxy", "sex", "rel"], [0, 1, 2]),
        "mission": cpt(ps_local.filter(pl.col("lds") == 1), "mission", ["sex", "activity", "age_band"], [0, 1]),
        "politics": cpt(ps_local, "politics", ["lds", "activity", "sex"], [0, 1, 2, 3, 4]),
        "orientation": cpt(ps_local, "orientation", ["sex"], ["straight", "bi", "gay", "asexual", "other"]),
        "origin_utah": cpt(ps_local.filter(pl.col("origin").is_not_null()), "origin_utah", ["school_proxy"], [0, 1]),
        "parent_income": cpt(ps_local, "parent_income", ["origin_utah"], list(range(12))),
        "ethnicity": cpt(ps_local, "ethnicity", ["school_proxy"],
                         ["White", "Hispanic", "Asian", "Black or African American",
                          "Native Hawaiian or Pacific Islander", "American Indian or Alaska Native", "Other"]),
        "age": num_cpt(ps_students, "age", ["school_proxy", "sex", "rel"]),
        "age_nonstudent": num_cpt(ps_local.filter(pl.col("school_proxy").is_in(["none", "other"])), "age", ["sex"]),
    }

    blocks = {}
    blocks["provostats"] = copula_block(ps_local, "provostats", {
        "age": "num", "rel_level": "ord", "activity": "ord", "lds": "bin", "mission": "bin", "politics": "ord",
        "origin_utah": "bin", "parent_income": "ord",
        "languages": "num", "soda_shop_per_week": "num", "owns_car": "bin", "support_teachings": "ord",
        "gpa": "num", "work_hours": "num", "sleep_hours": "num", "social_events_month": "num",
        "workouts_week": "num", "n_kissed": "num", "dates_month": "num", "n_relationships": "num",
        "n_ncmo": "num", "n_sex_partners": "num", "app_hours_week": "num", "ncmo_interest": "ord",
        "kiss_first_date_ok": "ord", "initiates_touch": "ord", "accepts_all_first_dates": "ord",
        "height_in": "num", "weight_lb": "num", "min_height_req": "num", "summer_sales": "bin",
        "app_mutual": "bin", "app_hinge": "bin", "app_tinder": "bin", "app_bumble": "bin",
        "squaw_peak_makeout": "bin", "ever_cheated": "bin", "ever_cheated_on": "bin",
        "mission_obedience": "num", "mission_foreign": "bin", "waiting_missionary": "bin",
        "club_intramural": "bin", "club_choir": "bin", "apps_in_class": "ord",
    }, "ProvoStats (n~2k, Provo/Orem): dating behaviour, sexual history, habits, academics, mission")

    blocks["college_life"] = copula_block(cl, "college_life", {
        "age": "num", "rel_level": "ord", "lds": "bin", "mission": "bin", "politics": "ord",
        "extraversion_10": "num", "social_media_hours": "num", "housing_cost": "num", "exercise_days": "num",
        "wage": "num", "eat_out_month": "num", "mh_anxiety": "bin", "mh_depression": "bin", "mh_adhd": "bin",
        "mh_ocd": "bin", "mh_eating": "bin", "mental_health_rating": "ord", "dancing_freq": "ord",
        "dance_if_known": "ord", "future_confidence": "ord", "cheats_school": "ord", "homework_early": "bin",
        "uses_chatgpt": "bin", "pp_insurance": "bin", "pp_car": "bin", "pp_tuition": "bin", "pp_rent": "bin",
        "debt_student": "bin", "debt_car": "bin", "debt_cc": "bin", "invests_ira": "bin", "hiked_y": "num",
        "countries_visited": "num", "n_kissed": "num", "swiftie": "bin", "has_gym": "bin",
        "hob_tv": "bin", "hob_reading": "bin", "hob_hiking": "bin", "hob_cooking": "bin", "hob_camping": "bin",
        "hob_sports": "bin", "hob_travel": "bin", "hob_gaming": "bin", "hob_instruments": "bin", "hob_art": "bin",
        "hob_dancing": "bin", "hob_singing": "bin", "hob_climbing": "bin", "hob_photo": "bin",
        "hob_volunteer": "bin", "hob_writing": "bin", "hob_computers": "bin",
        "att_gay_marriage_legal": "ord", "att_trans_bathroom": "ord", "att_gun_control": "ord",
        "att_abortion_any": "ord", "att_border_control": "ord", "live_parents": "bin",
        "racism_experienced": "ord", "sexism_experienced": "ord",
    }, "College Life (n~550): personality, mental health, finances, hobbies, attitudes, campus habits")

    blocks["dating"] = copula_block(dt, "dating", {
        "age": "num", "rel_level": "ord", "activity": "ord", "lds": "bin", "mission": "bin", "politics": "ord",
        "origin_utah": "bin", "n_kissed": "num", "n_ncmo": "num", "n_sex_partners": "num", "dates_month": "num",
        "n_relationships": "num", "height_in": "num", "min_height_req": "num",
        "ideal_months_to_engagement": "num", "kids_wanted": "num", "max_older_years": "num",
        "max_younger_years": "num", "app_ever": "bin", "app_use_mutual": "ord", "app_use_tinder": "ord",
        "app_use_hinge": "ord", "app_use_bumble": "ord", "ask_pref_phone": "ord", "ask_pref_text": "ord",
        "ask_pref_in_person": "ord", "wants_relationship": "ord", "asks_for_numbers": "ord",
        "gives_number": "ord", "picky": "ord", "scared_initiate_kiss": "ord", "men_first_move": "ord",
        "swipes_on_pictures": "ord", "dates_for_food": "ord", "rank_physical": "num", "rank_intelligence": "num",
        "rank_personality": "num", "rank_shared_interests": "num", "rank_emotional_iq": "num",
        "rank_spirituality": "num", "pt_spiritual": "ord", "pt_athletic": "ord", "pt_ambitious": "ord",
        "pt_funny": "ord", "pt_intelligent": "ord", "pt_musical": "ord", "date_in_ward": "ord",
        "date_foreign_rm": "ord", "date_divorced": "ord", "likes_msg_ncmo_invite": "ord",
        "appfor_ncmo": "bin", "appfor_ltr": "bin", "mh_anxiety": "bin", "mh_depression": "bin",
        **{f"fd_{n}": "ord" for n in ["board_games", "restaurant", "concert", "hike", "ice_cream", "ice_skating",
                                       "cook_together", "makeout", "movie_theater", "movie_apartment", "museum",
                                       "picnic", "pickleball", "rock_climbing", "soda_shop", "spikeball",
                                       "sports_game", "stargazing", "video_games", "gym", "fast_food",
                                       "painting", "sledding"]},
    }, "Dating (n~900, Utah): dating attitudes, partner preferences, app use, date preferences")

    blocks["culture"] = copula_block(cu, "culture", {
        "age": "num", "rel_level": "ord", "activity": "ord", "lds": "bin", "mission": "bin", "politics": "ord",
        "origin_utah": "bin", "n_kissed": "num", "n_relationships": "num",
        "convert": "bin", "temple_recommend": "bin", "believes_all_doctrine": "ord", "struggled_faith": "ord",
        "self_conscious_appearance": "ord", "expects_ssm_policy_change": "ord", "tattoos_wrong": "ord",
        "history_struggle": "ord", "supports_women_priesthood": "ord", "plural_marriage_divine": "ord",
        "priesthood_ban_prejudice": "ord", "r_movies_wrong": "ord", "plans_to_leave": "ord",
        "traditional_roles": "ord", "modest_ok_bikini": "ord", "modest_ok_short_shorts": "ord",
        "freq_alcohol": "ord", "freq_tea": "ord", "freq_coffee": "ord", "freq_r_movies": "ord", "freq_vape": "ord",
        "hs_relationship": "bin", "dated_before_16": "bin", "first_kiss_age": "num", "parents_divorced": "bin",
        "mh_anxiety": "bin", "mh_depression": "bin", "bishop_youth": "ord", "bishop_adult": "ord",
        "bishop_experience": "ord", "marriage_satisfaction": "ord", "scripture_minutes": "num",
        "prayers_per_day": "num", "temple_per_year": "num", "children": "num", "efy_count": "num",
        "attend_sacrament": "ord", "attend_second_hour": "ord", "does_ministering": "ord", "studies_cfm": "ord",
        "does_family_history": "ord", "attends_ward_activities": "ord", "sabbath_social_media": "ord",
        "garments": "ord", "wants_tattoo": "ord", "faith_crisis_now": "ord", "swearing_ok": "ord",
        "divorce_if_spouse_left": "ord", "prefers_rm": "ord", "positive_dating_utah": "ord",
        "moral_autonomy": "ord", "lgbtq_hard_to_reconcile": "ord", "lgbtq_safe_at_church": "ord",
    }, "Culture & Lifestyle (n~840): multidimensional LDS religiosity, practice, norms, history")

    # ---- validation / calibration targets (aggregate summaries) ----
    targets = {
        "dates_month_by_sex_rel_activity": summarize(ps_local, "dates_month", ["sex", "rel", "activity"]),
        "dates_month_by_sex_age": summarize(ps_local.filter(pl.col("rel") == "single"), "dates_month", ["sex", "age_band"]),
        "n_kissed_by_sex_age": summarize(ps_local, "n_kissed", ["sex", "age_band"]),
        "n_kissed_by_activity": summarize(ps_local, "n_kissed", ["activity"]),
        "n_ncmo_by_sex_activity": summarize(ps_local, "n_ncmo", ["sex", "activity"]),
        "n_sex_partners_by_rel_activity": summarize(ps_local, "n_sex_partners", ["rel", "activity"]),
        "n_relationships_by_sex_age": summarize(ps_local, "n_relationships", ["sex", "age_band"]),
        "social_events_by_sex_rel": summarize(ps_local, "social_events_month", ["sex", "rel"]),
        "work_hours_by_school": summarize(ps_students, "work_hours", ["school_proxy"]),
        "sleep_by_school": summarize(ps_students, "sleep_hours", ["school_proxy"]),
        "gpa_by_school_sex": summarize(ps_students, "gpa", ["school_proxy", "sex"]),
        "married_share_by_age_sex": summarize(ps_local.with_columns(m=(pl.col("rel") == "married").cast(pl.Int64)), "m", ["sex", "age_band"]),
        "married_share_by_school": summarize(ps_students.with_columns(m=(pl.col("rel") == "married").cast(pl.Int64)), "m", ["school_proxy"]),
        "age_at_marriage": summarize(dt.with_columns(all=pl.lit("all")), "age_at_marriage", ["sex"]),
        "months_dated_spouse_dating_survey": summarize(dt.with_columns(all=pl.lit("all")), "months_dated_spouse", ["all"]),
        "months_dated_spouse_culture_survey": summarize(cu.with_columns(all=pl.lit("all")), "months_dated_spouse", ["all"]),
        "ideal_months_to_engagement": summarize(dt, "ideal_months_to_engagement", ["sex"]),
        "kids_wanted_by_activity": summarize(dt, "kids_wanted", ["activity"]),
        "housing_cost_by_rel": summarize(cl.filter(pl.col("local") == 1), "housing_cost", ["rel"]),
        "social_media_hours_by_sex": summarize(cl, "social_media_hours", ["sex"]),
        "temple_per_year_by_activity": summarize(cu, "temple_per_year", ["activity"]),
        "scripture_minutes_by_activity": summarize(cu, "scripture_minutes", ["activity"]),
        "app_hours_by_sex_rel": summarize(ps_local, "app_hours_week", ["sex", "rel"]),
        "faith_crisis_by_activity": summarize(cu, "faith_crisis_now", ["activity"]),
        "coffee_by_activity": summarize(cu, "freq_coffee", ["activity"]),
        "alcohol_by_activity": summarize(cu, "freq_alcohol", ["activity"]),
    }

    tables = {
        "complexes": counts_table(ps_local, "complex", min_count=5),
        "complexes_by_school": counts_table(ps_local.filter(pl.col("school_proxy").is_in(["BYU", "UVU"])), "complex", 5, by="school_proxy"),
        "met_spouse": counts_table(ps_local, "met_spouse", 5),
        "study_area": counts_table(pl.concat([cl.select("study_area", "school_proxy"), dt.select("study_area", "school_proxy")]), "study_area", 5, by="school_proxy"),
        "majors_byu": counts_table(ps_local, "major_byu", 5),
        "majors_uvu": counts_table(ps_local, "major_uvu", 3),
        "origin_state": counts_table(ps_local, "origin", 10),
        "mission_place": counts_table(ps_local, "mission_place", 8),
        "dance_venues": {v: round(float(cl[v].mean()), 4) for v in cl.columns if v.startswith("venue_") and cl[v].drop_nulls().len() >= K_MIN},
        "dance_reasons": {v: round(float(cl[v].mean()), 4) for v in cl.columns if v.startswith("dr_")},
        "first_date_pref_mean_by_sex": {
            s: {c: round(float(dt.filter(pl.col("sex") == s)[c].mean()), 3) for c in dt.columns if c.startswith("fd_")}
            for s in ("M", "F")},
        "partner_trait_importance_by_sex": {
            s: {c: round(float(dt.filter(pl.col("sex") == s)[c].mean()), 3) for c in dt.columns if c.startswith("pt_")}
            for s in ("M", "F")},
        "dealbreakers_women_on_men": {c: round(float(ps_local[c].mean()), 4) for c in ps_local.columns if c.startswith("sl_") and c.endswith(("_w", "shorter", "gun", "gamer", "shirtless", "fishing", "moustache"))},
        "dealbreakers_men_on_women": {c: round(float(ps_local[c].mean()), 4) for c in ("sl_high_maint", "sl_not_active", "sl_politics", "sl_taller", "sl_bikini", "sl_music")},
        "ghosting_reasons": {c: round(float(dt[c].mean()), 4) for c in dt.columns if c.startswith("ghost_")},
    }

    priors = {
        "meta": {
            "built": str(date.today()),
            "k_min": K_MIN,
            "note": "Aggregate statistics only. Derived from convenience samples (LDStats/ProvoStats followers); "
                    "calibrated against institutional targets at synthesis time. Never contains respondent-level data.",
            "sources": {k: {"title": v, "n_band": _nband(n)} for k, v, n in [
                ("provostats", "ProvoStats", ps.height), ("college-life", "College Life", cl.height),
                ("dating", "Dating", dt.height), ("culture-lifestyle", "Culture & Lifestyle", cu.height)]},
        },
        "skeleton": skeleton,
        "blocks": blocks,
        "targets": targets,
        "tables": tables,
    }
    if write:
        PRIORS_DIR.mkdir(parents=True, exist_ok=True)
        (PRIORS_DIR / "survey_priors.json").write_text(json.dumps(priors, indent=1, default=_json_default), encoding="utf-8")
    return priors


def _json_default(o):
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return float(o)
    raise TypeError(type(o))


if __name__ == "__main__":
    p = build()
    for name, b in p["blocks"].items():
        print(name, len(b["variables"]), "vars; min pair n", b["min_pair_n"])
