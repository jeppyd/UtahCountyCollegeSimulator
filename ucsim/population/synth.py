"""Synthetic population for the BYU/UVU ecosystem.

Pipeline (all vectorized):
  1. role counts from world.yaml targets × scale
  2. skeleton attributes via smoothed CPTs (ProvoStats), calibrated with odds tilts to
     institutional targets (married share, LDS share, activity at UVU)
  3. survey domain blocks via Gaussian-copula conditional sampling, chained so that later
     blocks condition on every variable already assigned (statistical matching; the
     cross-survey conditional-independence assumption is explicit and documented)
  4. latent traits (Big Five etc.) from a literature MVN, tilted toward survey proxies
  5. derived multidimensional faith constructs
  6. structural circumstances (school, standing, work, finances)
Couples, housing, wards, jobs and the seed network are built in sibling modules.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import yaml
from scipy.special import expit, ndtri

from ..engine.state import PersonTable
from ..registry import Registry
from . import majors
from .sampling import copulas, skeleton

WORLD_CFG = Path(__file__).resolve().parents[1] / "config" / "world.yaml"

AGE_BANDS = np.array([20, 22, 24, 27, 31])
AGE_BAND_LABELS = np.array(["18-19", "20-21", "22-23", "24-26", "27-30", "31+"])
REL_LEVELS = ["single", "dating", "engaged", "married", "divorced"]
REL_LEVEL_NUM = {"single": 0, "dating": 1, "engaged": 2, "married": 3, "divorced": 0}

# Big Five intercorrelations (order E, A, C, N, O); rounded-down values in the spirit of the
# van der Linden et al. (2010) meta-analysis.
B5_CORR = np.array([
    [1.00, 0.15, 0.15, -0.25, 0.25],
    [0.15, 1.00, 0.30, -0.25, 0.15],
    [0.15, 0.30, 1.00, -0.30, 0.05],
    [-0.25, -0.25, -0.30, 1.00, -0.10],
    [0.25, 0.15, 0.05, -0.10, 1.00],
])

STUDY_AREA_MAP = {
    "Business and Management": "Business", "Health Sciences": "Health Sciences",
    "Engineering and Technology": "Engineering & Tech", "Social Sciences": "Social Sciences",
    "Natural Sciences": "Natural Sciences", "Education": "Education", "Fine Arts": "Fine Arts",
    "Humanities": "Humanities", "Mathematics and Statistics": "Math & Stats",
    "Communication and Media Studies": "Communications", "Law and Legal Studies": "Law & Policy",
    "Agricultural Sciences": "Agriculture & Environment", "Environmental Studies": "Agriculture & Environment",
    "Other": "Undeclared", "Interdisciplinary Studies": "Undeclared",
}


def load_world_cfg() -> dict:
    return yaml.safe_load(WORLD_CFG.read_text(encoding="utf-8"))


def age_band(age: np.ndarray) -> np.ndarray:
    return AGE_BAND_LABELS[np.searchsorted(AGE_BANDS, age, side="right")]


def zscore(x: np.ndarray) -> np.ndarray:
    x = np.asarray(x, dtype=float)
    m = np.nanmean(x)
    s = np.nanstd(x) or 1.0
    out = (x - m) / s
    return np.where(np.isfinite(out), out, 0.0)


def rank_z(x: np.ndarray, rng) -> np.ndarray:
    """Rank-based normal scores with random tie breaking (NaN -> random draw)."""
    x = np.asarray(x, dtype=float)
    n = len(x)
    jitter = rng.uniform(0, 1e-6, n)
    ok = np.isfinite(x)
    out = rng.standard_normal(n)
    if ok.sum() > 2:
        r = np.argsort(np.argsort(x[ok] + jitter[ok]))
        out[ok] = ndtri((r + 0.5) / ok.sum())
    return out


class Synthesizer:
    def __init__(self, registry: Registry, scale: float, seed: int):
        self.reg = registry
        self.scale = scale
        self.rng = np.random.default_rng([seed, 7001])
        self.cfg = load_world_cfg()
        self.sk = skeleton()
        self.cop = copulas()

    # ------------------------------------------------------------------ public
    def people(self, P: PersonTable, role: str, n: int, school: str, extra: dict | None = None) -> np.ndarray:
        """Create n agents of a role and fill all person-level attributes."""
        if n <= 0:
            return np.array([], dtype=np.int64)
        ids = P.allocate(n)
        cfg = self.cfg["population"]
        rng = self.rng
        extra = extra or {}
        # ---------------- sex
        male_share = {"BYU": cfg["byu"]["male_share"], "UVU": cfg["uvu"]["male_share"]}.get(school, 0.5)
        if role in ("faculty",):
            male_share = 0.68
        if role in ("staff", "community"):
            male_share = 0.5
        sex = np.where(rng.random(n) < male_share, "M", "F")
        if "sex" in extra:
            sex = np.asarray(extra["sex"])
        # ---------------- age & relationship status
        sk_school = {"BYU": "BYU", "UVU": "UVU"}.get(school, "other")
        if role in ("byu_student", "uvu_student"):
            age0 = self.sk["age"].sample(rng, {"school_proxy": np.full(n, sk_school), "sex": sex,
                                              "rel": np.full(n, "nan")}, n)
        elif role == "young_adult":
            age0 = self.sk["age_nonstudent"].sample(rng, {"sex": sex}, n)
            age0 = np.clip(age0, 18, 32)
        elif role == "faculty":
            age0 = rng.uniform(30, 68, n)
        elif role == "staff":
            age0 = rng.uniform(24, 64, n)
        elif role == "community":
            age0 = rng.uniform(30, 70, n)
        else:  # spouse
            age0 = np.asarray(extra.get("age", rng.uniform(19, 30, n)))
        age = np.clip(age0 + rng.uniform(-0.5, 0.5, n), 17.5, 75)
        if "age" in extra:
            age = np.asarray(extra["age"], dtype=float)
        if "rel" in extra:
            rel = np.asarray(extra["rel"])
        elif role in ("faculty", "community"):
            rel = np.where(rng.random(n) < 0.9, "married", "single")
        elif role == "staff":
            rel = np.where(rng.random(n) < 0.75, "married", "single")
        else:
            target = {"BYU": cfg["byu"]["married_share"], "UVU": cfg["uvu"]["married_share"]}.get(school, 0.30)
            rel = self._calibrated_rel(sk_school if role != "young_adult" else "none", sex, age, target, n)
        # married people skew older: nudge ages of married students up modestly
        if role in ("byu_student", "uvu_student") and "age" not in extra:
            age = np.where(rel == "married", np.maximum(age, rng.normal(23.5, 2.0, n)), age)
        # ---------------- religion skeleton
        lds_share = {"byu_student": cfg["byu"]["lds_share"], "uvu_student": cfg["uvu"]["lds_share"],
                     "young_adult": 0.78, "faculty": 0.97 if school == "BYU" else 0.78, "staff": 0.9,
                     "community": 0.88, "spouse": 0.93}[role]
        lds = (rng.random(n) < lds_share).astype(int)
        if "lds" in extra:
            lds = np.asarray(extra["lds"]).astype(int)
        tilt = None
        if role == "uvu_student":
            tilt = {2: cfg["uvu"]["active_tilt"]}
        elif role == "young_adult":
            tilt = {2: 0.5}
        elif role in ("faculty", "staff", "community") and school == "BYU":
            tilt = {2: 3.0}
        act = self.sk["activity"].sample(rng, {"school_proxy": np.full(n, sk_school if sk_school != "other" else "BYU"),
                                               "sex": sex, "rel": rel}, n, tilt=tilt)
        if role in ("byu_student",):  # ecclesiastical endorsement: inactive students rare at BYU
            act = np.where((act == 0) & (rng.random(n) < 0.7), 1, act)
        if "activity" in extra:
            act = np.asarray(extra["activity"])
        act = np.where(lds == 1, act, -1)
        ab = age_band(age)
        mission = np.zeros(n, dtype=int)
        m_lds = lds == 1
        if m_lds.any():
            mission[m_lds] = self.sk["mission"].sample(
                rng, {"sex": sex[m_lds], "activity": act[m_lds], "age_band": ab[m_lds]}, int(m_lds.sum()))
        # mission timing realism: very young men cannot be RMs yet
        mission = np.where((sex == "M") & (age < 20.5), 0, mission)
        mission = np.where((sex == "F") & (age < 20.3), 0, mission)
        politics = self.sk["politics"].sample(rng, {"lds": lds, "activity": np.where(act < 0, "nan", act).astype(str),
                                                   "sex": sex}, n)
        orient = np.array(self.sk["orientation"].levels)[self.sk["orientation"].sample(rng, {"sex": sex}, n)]
        origin_utah = self.sk["origin_utah"].sample(rng, {"school_proxy": np.full(n, sk_school)}, n)
        parent_income = self.sk["parent_income"].sample(rng, {"origin_utah": origin_utah}, n)
        eth_levels = ["White", "Hispanic", "Asian", "Black", "Pacific Islander", "Native American", "Other"]
        eth = self.sk["ethnicity"].sample(rng, {"school_proxy": np.full(n, sk_school)}, n,
                                          tilt={"Hispanic": 1.6, "Asian": 1.3} if school == "UVU" else None)

        # ---------------- survey copula blocks (chained)
        known = {
            "age": age, "rel_level": np.array([REL_LEVEL_NUM[r] for r in rel], dtype=float),
            "activity": np.where(act >= 0, act, np.nan).astype(float), "lds": lds.astype(float),
            "mission": np.where(lds == 1, mission, np.nan).astype(float), "politics": politics.astype(float),
            "origin_utah": origin_utah.astype(float), "parent_income": parent_income.astype(float),
        }
        ps = self.cop["provostats"].sample(rng, sex, known, self.cop["provostats"].vars)
        for k in ("n_kissed", "n_ncmo", "n_sex_partners", "dates_month", "n_relationships", "height_in",
                  "min_height_req", "gpa", "work_hours", "sleep_hours"):
            known[k] = ps[k]
        dt = self.cop["dating"].sample(rng, sex, known, self.cop["dating"].vars)
        known.update({"app_ever": dt["app_ever"], "mh_anxiety": dt["mh_anxiety"], "mh_depression": dt["mh_depression"]})
        cl = self.cop["college_life"].sample(rng, sex, known, self.cop["college_life"].vars)
        cu = self.cop["culture"].sample(rng, sex, known, self.cop["culture"].vars)

        S = {}  # column -> values for ids

        def put(col, val):
            S[col] = val

        put("age", age.astype(np.float32))
        put("sex", P.codes("sex", sex))
        put("orientation", P.codes("orientation", orient))
        put("ethnicity", eth.astype(np.uint8))
        region = np.where(origin_utah == 1, "Utah",
                          rng.choice(["Mountain West", "West Coast", "Other US", "International"], n, p=[0.36, 0.30, 0.28, 0.06]))
        put("origin_region", P.codes("origin_region", region))
        put("parent_income", parent_income.astype(np.uint8))
        put("politics", politics.astype(np.uint8))
        put("lds_member", lds.astype(bool))
        put("languages", np.clip(np.nan_to_num(ps["languages"], nan=1), 1, 6).astype(np.uint8))
        put("height_in", np.nan_to_num(ps["height_in"], nan=np.where(sex == "M", 70.5, 65.0)).astype(np.float32))
        put("family_local", (origin_utah == 1) & (rng.random(n) < 0.55))
        fam = np.where(np.nan_to_num(cu["parents_divorced"]) > 0.5, "blended", "nuclear")
        fam = np.where((fam == "blended") & (rng.random(n) < 0.3), "single_parent", fam)
        put("family_structure", P.codes("family_structure", fam))
        put("parents_divorced", np.nan_to_num(cu["parents_divorced"]) > 0.5)

        # ---------------- personality (MVN + survey proxies)
        L = np.linalg.cholesky(B5_CORR)
        Z = rng.standard_normal((n, 5)) @ L.T
        ex10 = rank_z(cl["extraversion_10"], rng)
        E = 0.75 * ex10 + 0.66 * Z[:, 0]
        n_proxy = zscore(-np.nan_to_num(cl["mental_health_rating"], nan=2) + 0.8 * np.nan_to_num(cl["mh_anxiety"])
                         + 0.8 * np.nan_to_num(cl["mh_depression"]))
        N = 0.75 * Z[:, 3] + 0.55 * n_proxy - 0.15 * E
        c_proxy = zscore(np.nan_to_num(cl["homework_early"]) - 0.4 * np.nan_to_num(cl["cheats_school"])
                         + 0.5 * zscore(np.nan_to_num(ps["gpa"], nan=3.4)))
        C = 0.8 * Z[:, 2] + 0.45 * c_proxy
        o_proxy = zscore(-politics + 0.6 * np.nan_to_num(cl["hob_art"]) + 0.4 * np.nan_to_num(cl["hob_reading"]))
        O = 0.85 * Z[:, 4] + 0.4 * o_proxy
        A = Z[:, 1]
        E, A, C, N, O = (zscore(v) for v in (E, A, C, N, O))
        e = lambda: rng.standard_normal(n)  # noqa: E731
        put("extraversion", E)
        put("agreeableness", A)
        put("conscientiousness", C)
        put("neuroticism", N)
        put("openness", O)
        ncmo_i = np.nan_to_num(ps["ncmo_interest"], nan=1.0)
        put("sensation_seeking", zscore(0.3 * E - 0.25 * C + 0.35 * zscore(ncmo_i) + 0.8 * e()))
        put("self_control", zscore(0.6 * C - 0.2 * N + 0.75 * e()))
        att_anx = zscore(0.4 * N + 0.9 * e())
        put("attachment_anxiety", att_anx)
        put("attachment_avoidance", zscore(-0.3 * A - 0.2 * E + 0.9 * e()))
        scared = zscore(np.nan_to_num(dt["scared_initiate_kiss"], nan=2.5))
        put("rejection_sensitivity", zscore(0.45 * N + 0.3 * att_anx + 0.2 * scared + 0.75 * e()))
        put("social_anxiety", zscore(-0.45 * E + 0.4 * N + 0.75 * e()))
        put("conformity", zscore(0.3 * A + 0.2 * C - 0.3 * O + 0.85 * e()))
        put("empathy", zscore(0.6 * A + 0.8 * e()))
        workouts = np.nan_to_num(ps["workouts_week"], nan=3)
        # ---------------- body & appearance (approximate population distributions; see 01_demographics.yaml)
        male = sex == "M"
        med = np.where(male, 24.5, 23.0) + np.where(male, 0.15, 0.18) * np.clip(age - 20, 0, 40) - 0.3 * (np.clip(workouts, 0, 7) - 3)
        bmi = np.clip(med * np.exp(rng.normal(0, 0.14, n)), 16, 52)
        h_m = S["height_in"] * 0.0254
        put("bmi", bmi.astype(np.float32))
        put("weight_lb", (bmi * h_m ** 2 * 2.20462).astype(np.float32))
        build = np.select([bmi < 20.5, (workouts >= 4) & (bmi < 27), bmi >= 28], ["slender", "athletic", "heavier"], "average")
        put("body_build", P.codes("body_build", build))
        white = eth == 0
        hair = np.where(white, rng.choice(["black", "dark_brown", "light_brown", "blonde", "red"], n, p=[0.08, 0.33, 0.29, 0.24, 0.06]),
                        rng.choice(["black", "dark_brown", "light_brown"], n, p=[0.62, 0.33, 0.05]))
        hair = np.where((age > 40) & (rng.random(n) < np.clip((age - 40) / 30, 0, 0.8)), "gray", hair)
        put("hair_color", P.codes("hair_color", hair))
        eyes = np.where(white, rng.choice(["brown", "hazel", "green", "blue", "gray"], n, p=[0.27, 0.18, 0.13, 0.38, 0.04]),
                        rng.choice(["brown", "hazel", "green", "blue", "gray"], n, p=[0.84, 0.10, 0.03, 0.02, 0.01]))
        put("eye_color", P.codes("eye_color", eyes))
        # perceived attractiveness: mostly idiosyncratic, a little exercise, and lower far from a typical weight
        bmi_dev = np.abs(bmi - np.where(male, 24.0, 22.0)) / 4.0
        put("attractiveness", zscore(0.15 * zscore(workouts) - 0.25 * bmi_dev + e()))
        gpa = np.clip(np.nan_to_num(ps["gpa"], nan=3.4), 1.0, 4.0)
        put("academic_ability", zscore(zscore(gpa) - 0.35 * C + 0.15 * zscore(np.nan_to_num(ps["work_hours"], nan=15)) + 0.6 * e()))
        put("social_skill", zscore(0.4 * E + 0.3 * A - 0.3 * S["social_anxiety"] + 0.8 * e()))

        # ---------------- values, sexuality, dating
        put("traditional_roles", np.nan_to_num(cu["traditional_roles"], nan=2).astype(np.float32))
        put("att_gay_marriage_legal", np.nan_to_num(cl["att_gay_marriage_legal"], nan=2.5).astype(np.float32))
        put("expects_ssm_change", np.nan_to_num(cu["expects_ssm_policy_change"], nan=1).astype(np.float32))
        put("supports_women_priesthood", np.nan_to_num(cu["supports_women_priesthood"], nan=1).astype(np.float32))
        put("kids_wanted", np.nan_to_num(dt["kids_wanted"], nan=3.5).astype(np.float32))
        put("ideal_months_engaged", np.nan_to_num(dt["ideal_months_to_engagement"], nan=9).astype(np.float32))
        put("future_confidence", np.nan_to_num(cl["future_confidence"], nan=2).astype(np.float32))
        put("ncmo_interest", ncmo_i.astype(np.float32))
        put("kiss_first_date_ok", np.nan_to_num(ps["kiss_first_date_ok"], nan=2).astype(np.float32))
        put("n_kissed", np.round(np.nan_to_num(ps["n_kissed"], nan=3)).astype(np.int16))
        put("n_ncmo", np.round(np.nan_to_num(ps["n_ncmo"], nan=0)).astype(np.int16))
        put("n_sex_partners", np.round(np.nan_to_num(ps["n_sex_partners"], nan=0)).astype(np.int16))
        put("made_out_kyhv_peak", np.nan_to_num(ps["squaw_peak_makeout"]) > 0.5)
        put("ever_cheated", np.nan_to_num(ps["ever_cheated"]) > 0.5)
        put("ever_cheated_on", np.nan_to_num(ps["ever_cheated_on"]) > 0.5)
        put("n_relationships", np.round(np.nan_to_num(ps["n_relationships"], nan=1)).astype(np.int16))
        put("dating_propensity", np.clip(np.nan_to_num(ps["dates_month"], nan=2), 0, 20).astype(np.float32))
        app_ever = np.nan_to_num(dt["app_ever"], nan=0.6) > 0.5
        app_h = np.nan_to_num(ps["app_hours_week"], nan=0)
        partnered = np.isin(rel, ["dating", "engaged", "married"])
        put("app_user", ~partnered & app_ever & ((app_h > 0) | (rng.random(n) < 0.15)))
        put("app_hours", np.where(S["app_user"], np.maximum(app_h, 0.5), 0).astype(np.float32))
        put("app_mutual", S["app_user"] & ((np.nan_to_num(ps["app_mutual"]) > 0.5) | (lds == 1) & (rng.random(n) < 0.6)))
        put("accepts_first_dates", np.nan_to_num(ps["accepts_all_first_dates"], nan=2.5).astype(np.float32))
        for col, src in (("men_first_move", "men_first_move"), ("picky", "picky"), ("wants_relationship", "wants_relationship"),
                         ("asks_for_numbers", "asks_for_numbers"), ("scared_initiate_kiss", "scared_initiate_kiss")):
            put(col, np.nan_to_num(dt[src], nan=2).astype(np.float32))
        put("min_height_req", np.nan_to_num(ps["min_height_req"], nan=68).astype(np.float32))
        put("max_older", np.nan_to_num(dt["max_older_years"], nan=5).astype(np.float32))
        put("max_younger", np.nan_to_num(dt["max_younger_years"], nan=3).astype(np.float32))
        for col, src in (("imp_spirituality", "rank_spirituality"), ("imp_physical", "rank_physical"),
                         ("imp_personality", "rank_personality"), ("imp_shared_interests", "rank_shared_interests")):
            put(col, (6 - np.nan_to_num(dt[src], nan=3.5)).astype(np.float32))
        put("prefers_rm", np.nan_to_num(dt["date_foreign_rm"], nan=2.5).astype(np.float32))
        for fd in ("ice_cream", "restaurant", "hike", "board_games", "cook_together", "movie_theater", "movie_apartment",
                   "concert", "museum", "picnic", "pickleball", "rock_climbing", "soda_shop", "sports_game",
                   "stargazing", "video_games", "gym", "makeout"):
            put(f"fd_{fd}", np.clip(np.round(np.nan_to_num(dt[f"fd_{fd}"], nan=2)), 0, 4).astype(np.uint8))

        # ---------------- habits & interests
        put("sleep_hours", np.clip(np.nan_to_num(ps["sleep_hours"], nan=7), 4, 10).astype(np.float32))
        put("workouts_week", np.clip(workouts, 0, 10).astype(np.float32))
        put("social_media_hours", np.clip(np.nan_to_num(cl["social_media_hours"], nan=2.5), 0, 10).astype(np.float32))
        put("soda_shop_week", np.clip(np.nan_to_num(ps["soda_shop_per_week"], nan=0), 0, 10).astype(np.float32))
        put("social_events_month", np.clip(np.nan_to_num(ps["social_events_month"], nan=5), 0, 30).astype(np.float32))
        for col, src in (("coffee", "freq_coffee"), ("tea", "freq_tea"), ("alcohol", "freq_alcohol"), ("r_movies", "freq_r_movies")):
            put(col, np.clip(np.round(np.nan_to_num(cu[src], nan=0)), 0, 3).astype(np.uint8))
        put("dancing", np.clip(np.round(np.nan_to_num(cl["dancing_freq"], nan=0)), 0, 3).astype(np.uint8))
        b = lambda k: np.nan_to_num(cl[k]) > 0.5  # noqa: E731
        put("hikes", b("hob_hiking"))
        put("gaming", b("hob_gaming"))
        put("sports", b("hob_sports"))
        put("music_maker", b("hob_instruments") | b("hob_singing"))
        put("reading", b("hob_reading"))
        put("cooking", b("hob_cooking"))
        put("outdoors", b("hob_camping") | b("hob_climbing"))
        put("arts", b("hob_art") | b("hob_photo") | b("hob_writing"))
        put("swiftie", b("swiftie"))
        put("pickleball", rng.random(n) < 0.04)
        put("mh_anxiety", b("mh_anxiety"))
        put("mh_depression", b("mh_depression"))
        put("mh_adhd", b("mh_adhd"))
        put("homework_early", b("homework_early"))
        put("cheats_school", np.nan_to_num(cl["cheats_school"], nan=1).astype(np.float32))

        # ---------------- faith constructs (members); non-members get low/neutral values
        actn = np.where(act >= 0, act / 2.0, 0.0)
        bel_items = (0.5 * np.nan_to_num(cu["believes_all_doctrine"], nan=3) / 4
                     + 0.3 * np.nan_to_num(ps["support_teachings"], nan=2.5) / 3
                     + 0.2 * (1 - np.nan_to_num(cu["plans_to_leave"], nan=0) / 4))
        belief = np.clip(bel_items + 0.05 * e(), 0.02, 0.99)
        belief = np.where(lds == 1, belief, np.clip(rng.beta(1.5, 6, n), 0.01, 0.9))
        put("faith_belief", belief.astype(np.float32))
        struggle = np.nan_to_num(cu["struggled_faith"], nan=2) / 4
        hist = np.nan_to_num(cu["history_struggle"], nan=1)
        crisis_item = np.nan_to_num(cu["faith_crisis_now"], nan=0)
        certainty = np.clip(0.95 - 0.25 * struggle - 0.2 * hist / 4 - 0.3 * crisis_item / 4 + 0.15 * (belief - 0.7)
                            + 0.06 * e(), 0.05, 0.98)
        put("faith_certainty", certainty.astype(np.float32))
        put("history_struggle", hist.astype(np.float32))
        put("struggled_faith", struggle > 0.55)
        put("faith_crisis", (lds == 1) & (crisis_item >= 3) & (rng.random(n) < 0.75))
        put("plans_to_leave", np.nan_to_num(cu["plans_to_leave"], nan=0).astype(np.float32))
        garments = np.clip(np.round(np.nan_to_num(cu["garments"], nan=0)), 0, 4)
        tr = (np.nan_to_num(cu["temple_recommend"]) > 0.5) & (lds == 1) & (act == 2)
        efy = np.nan_to_num(cu["efy_count"], nan=1)
        ex_member = (lds != 1) & (rng.random(n) < 0.35)     # many Utah County non-members were raised LDS (assumption)
        put("raised_lds", ((lds == 1) & ~(np.nan_to_num(cu["convert"]) > 0.5)) | ex_member)
        # ---------------- religious affiliation of non-members (assumption informed by Utah-wide surveys)
        AFF = ["Catholic", "Protestant", "Other Christian", "Muslim", "Other faith", "Nonreligious"]
        mix = {0: [0.15, 0.25, 0.05, 0.02, 0.03, 0.50],    # White / default
               1: [0.55, 0.15, 0.05, 0.00, 0.00, 0.25],    # Hispanic
               2: [0.10, 0.20, 0.00, 0.05, 0.20, 0.45],    # Asian
               3: [0.10, 0.45, 0.00, 0.10, 0.00, 0.35],    # Black
               4: [0.20, 0.30, 0.15, 0.00, 0.00, 0.35]}    # Pacific Islander
        aff = np.full(n, "Latter-day Saint", dtype=object)
        for i in np.where(lds != 1)[0]:
            if ex_member[i]:
                aff[i] = rng.choice(AFF, p=[0.03, 0.10, 0.04, 0.0, 0.03, 0.80])
            else:
                pr = np.array(mix.get(int(eth[i]), mix[0]), float)
                if region[i] == "International":
                    pr[3] += 0.08
                aff[i] = rng.choice(AFF, p=pr / pr.sum())
        put("affiliation", P.codes("affiliation", aff))
        religious = (lds != 1) & (aff != "Nonreligious")
        own = np.where(religious, rng.beta(3, 2.5, n), np.where(lds != 1, rng.beta(1, 12, n), 0.0))
        put("own_religiosity", own.astype(np.float32))
        put("service_attend", np.where(religious, np.clip(own * rng.uniform(0.3, 1.0, n), 0, 1), 0.0).astype(np.float32))
        endowed = (lds == 1) & ((mission == 1) | (rel == "married") | (age > 26))
        put("garments", np.where(endowed, garments, 0).astype(np.uint8))
        put("temple_recommend", tr)
        put("temple_per_year", np.where(lds == 1, np.nan_to_num(cu["temple_per_year"], nan=6), 0).astype(np.float32))
        put("scripture_minutes", np.where(lds == 1, np.nan_to_num(cu["scripture_minutes"], nan=5), 0).astype(np.float32))
        prayers = np.nan_to_num(cu["prayers_per_day"], nan=1)
        put("private_practice", np.where(lds == 1, np.clip(0.5 * np.minimum(prayers, 5) / 5
                                                             + 0.5 * np.minimum(S["scripture_minutes"], 30) / 30, 0, 1), 0.02).astype(np.float32))
        identity = np.clip(0.35 * actn + 0.2 * garments / 4 + 0.15 * tr + 0.1 * np.minimum(efy, 3) / 3
                           + 0.1 * mission + 0.1 * belief + 0.06 * e(), 0.02, 0.99)
        put("religious_identity", np.where(lds == 1, identity, 0.03).astype(np.float32))
        trust = np.clip(0.45 * np.nan_to_num(ps["support_teachings"], nan=2.5) / 3
                        + 0.3 * np.nan_to_num(cu["bishop_experience"], nan=3) / 4
                        + 0.25 * (1 - np.nan_to_num(cu["expects_ssm_policy_change"], nan=1) / 4) + 0.05 * e(), 0.02, 0.99)
        put("institutional_trust", np.where(lds == 1, trust, 0.2).astype(np.float32))
        orth = np.clip(np.mean([np.nan_to_num(cu["plural_marriage_divine"], nan=3) / 4,
                                1 - np.nan_to_num(cu["supports_women_priesthood"], nan=1) / 4,
                                1 - np.nan_to_num(cu["expects_ssm_policy_change"], nan=1) / 4,
                                np.nan_to_num(cu["r_movies_wrong"], nan=1) / 4,
                                np.nan_to_num(cu["traditional_roles"], nan=2) / 4], axis=0) + 0.04 * e(), 0.02, 0.99)
        put("orthodoxy", np.where(lds == 1, orth, 0.15).astype(np.float32))
        put("moral_autonomy", np.clip(np.nan_to_num(cu["moral_autonomy"], nan=1.5) / 4 + 0.04 * e(), 0, 1).astype(np.float32))
        attend_item = np.nan_to_num(cu["attend_sacrament"], nan=3)
        lo_b = np.select([act == 2, act == 1, act == 0], [0.62, 0.16, 0.0], 0.0)
        hi_b = np.select([act == 2, act == 1, act == 0], [1.0, 0.58, 0.12], 0.0)
        att_rate = np.clip(np.array([0.05, 0.35, 0.75, 0.95])[np.clip(attend_item.astype(int), 0, 3)] + 0.08 * e(), lo_b, hi_b)
        put("attend_rate", np.where(lds == 1, att_rate, 0).astype(np.float32))
        put("practice_habit", np.where(lds == 1, np.clip(att_rate * 0.9 + 0.1 * e() * 0.5, 0, 1), 0).astype(np.float32))
        put("ward_activity_rate", np.where(lds == 1, np.clip(np.nan_to_num(cu["attends_ward_activities"], nan=1.5) / 3
                                                               * (0.5 + 0.5 * att_rate) + 0.05 * e(), 0.02, 0.98), 0.0).astype(np.float32))
        put("activity", np.where(lds == 1, act + 1, 0).astype(np.uint8))
        fam_exp = np.clip(0.4 * S["raised_lds"] + 0.2 * origin_utah + 0.15 * np.minimum(efy, 3) / 3
                          + 0.2 * S["family_local"] - 0.1 * S["parents_divorced"] + 0.05 * e(), 0, 1)
        put("family_expectation", np.where(lds == 1, fam_exp, 0.05).astype(np.float32))
        nonstraight = orient != "straight"
        put("lgbtq_tension", np.where((lds == 1) & nonstraight,
                                      np.clip(np.nan_to_num(cu["lgbtq_hard_to_reconcile"], nan=2) / 4 + 0.15 * e(), 0, 1), 0).astype(np.float32))
        put("bishop_meetings", np.clip(np.round(np.nan_to_num(cu["bishop_adult"], nan=0) * 1.3), 0, 6).astype(np.uint8))
        chast = np.clip(0.35 * orth + 0.3 * actn + 0.25 * (1 - ncmo_i / 4) + 0.1 * belief + 0.05 * e(), 0, 1)
        put("chastity_commitment", np.where(lds == 1, chast, np.clip(0.2 + 0.1 * e(), 0, 1)).astype(np.float32))
        # Pornography: NOT in the supplied surveys — broad literature prevalence, lowered by commitment (extrapolated).
        base_any = np.where(sex == "M", 0.6, 0.22)
        p_any = expit(np.log(base_any / (1 - base_any)) - 2.0 * (S["chastity_commitment"] - 0.5) + 0.3 * S["sensation_seeking"])
        any_use = rng.random(n) < p_any
        freq = np.where(any_use, rng.choice([1, 2, 3], n, p=[0.45, 0.33, 0.22]), 0)
        freq = np.where((sex == "M") & any_use & (rng.random(n) < 0.25), np.maximum(freq, 2), freq)
        put("porn_use", freq.astype(np.uint8))
        mission_status = np.where(mission == 1, np.where(rng.random(n) < 0.06, "early_returned", "returned"), "none")
        put("mission_status", P.codes("mission_status", mission_status))
        put("mission_foreign", (mission == 1) & (np.nan_to_num(ps["mission_foreign"], nan=0.5) > 0.5))

        # ---------------- relationship status & history
        rel_status = np.array([{"single": "single", "dating": "dating", "engaged": "engaged", "married": "married",
                                "divorced": "divorced"}[r] for r in rel], dtype=object)
        put("rel_status", P.codes("rel_status", rel_status))
        put("relationship_satisfaction", np.where(rel == "married",
                                                  np.clip(np.nan_to_num(cu["marriage_satisfaction"], nan=3.5) / 4 + 0.05 * e(), 0, 1),
                                                  np.where(np.isin(rel, ["dating", "engaged"]), np.clip(0.75 + 0.1 * e(), 0, 1), np.nan)).astype(np.float32))
        kids = np.where(rel == "married", np.clip(np.round(np.nan_to_num(cu["children"], nan=0) * np.clip((age - 21) / 6, 0, 1)), 0, 8), 0)
        put("children", kids.astype(np.uint8))

        # ---------------- schooling & work
        put("school", P.codes("school", np.full(n, school if school in ("BYU", "UVU") else "none")))
        is_student = role in ("byu_student", "uvu_student")
        put("enrolled", np.full(n, is_student))
        areas = self._study_areas(school, n) if is_student else np.full(n, "Undeclared")
        put("study_area", P.codes("study_area", areas))
        if is_student and school in ("BYU", "UVU"):
            mid = majors.sample(rng, school, areas)
            cat = majors.catalog()
            put("major_id", mid)
            put("college", P.codes("college", [cat[m]["college"] if m >= 0 else "none" for m in mid]))
        else:
            put("major_id", np.full(n, -1, np.int16))
            put("college", P.codes("college", np.full(n, "none")))
        put("gpa", (gpa if is_student else np.full(n, np.nan)).astype(np.float32))
        put("gpa_term", (gpa if is_student else np.full(n, np.nan)).astype(np.float32))
        mission_years = np.where(mission == 1, np.where(sex == "M", 2.0, 1.5), 0.0)
        yrs_school = np.clip(age - 18.3 - mission_years + rng.normal(0, 0.4, n), 0, 8)
        part_time = (school == "UVU") & (rng.random(n) < 0.35)
        credits = np.clip(yrs_school * np.where(part_time, 17, 24) + rng.normal(0, 8, n), 0, 119)
        grad = (age > 24) & (rng.random(n) < (self.cfg["population"]["byu"]["grad_share"] * 2.2 if school == "BYU" else 0.05))
        mix = self.cfg["population"].get(str(school).lower(), {}).get("class_mix") if is_student else None
        if mix and n >= 50:
            # The survey sample skews young; rank people by age-implied progress and re-band credits so the
            # class mix matches the school's published enrollment by class.
            order = np.argsort(credits + 6 * age + rng.normal(0, 4, n))
            q = np.empty(n)
            q[order] = (np.arange(n) + 0.5) / n
            cum = np.cumsum([mix[k] for k in ("freshman", "sophomore", "junior", "senior")])
            cum = cum / (cum[-1] + mix.get("graduate", 0))
            grad = q > cum[-1]
            band = np.searchsorted(cum, q)
            lo = np.r_[0, cum][np.minimum(band, 3)]
            hi = cum[np.minimum(band, 3)]
            credits = np.clip(30 * (np.minimum(band, 3) + (q - lo) / np.maximum(hi - lo, 1e-9)), 0, 119)
        standing = np.select([~np.full(n, is_student), grad, credits < 30, credits < 60, credits < 90],
                             ["none", "graduate", "freshman", "sophomore", "junior"], "senior")
        put("class_standing", P.codes("class_standing", standing))
        put("credits_done", np.where(is_student, credits, 0).astype(np.float32))
        put("credits_term", np.where(is_student, np.where(part_time, rng.integers(6, 11, n), rng.integers(12, 17, n)), 0).astype(np.float32))
        put("academic_standing", P.codes("academic_standing", np.where(gpa < 2.0, "probation", np.where(gpa < 2.3, "warning", "good"))))
        wh = np.clip(np.nan_to_num(ps["work_hours"], nan=15), 0, 60)
        if is_student and wh.mean() > 0:
            # the copula pools schools; rescale to the survey's per-school mean (BYU students work less than UVU)
            from .sampling import load_priors
            tgt = {r["school_proxy"]: r["mean"] for r in load_priors()["targets"]["work_hours_by_school"]}.get(school)
            if tgt:
                wh = np.clip(wh * tgt / wh.mean(), 0, 60)
        if role in ("young_adult", "staff"):
            wh = np.where(rng.random(n) < 0.9, np.clip(rng.normal(38, 6, n), 20, 55), 0)
        elif role == "faculty":
            wh = np.clip(rng.normal(48, 6, n), 35, 65)
        elif role == "community":
            wh = np.where(rng.random(n) < 0.75, np.clip(rng.normal(40, 7, n), 15, 60), 0)
        elif role == "spouse":
            wh = np.where(rng.random(n) < 0.7, np.clip(rng.normal(30, 10, n), 8, 50), 0)
        put("work_hours", wh.astype(np.float32))
        put("employed", wh > 0)
        wage = np.clip(np.nan_to_num(cl["wage"], nan=15), 8, 60)
        wage = np.where(wage < 9, 13 + rng.normal(0, 2, n), wage)
        if role == "faculty":
            wage = rng.normal(48, 12, n)
        elif role in ("staff", "community"):
            wage = np.clip(rng.lognormal(np.log(26), 0.35, n), 15, 90)
        elif role == "young_adult":
            wage = np.clip(rng.lognormal(np.log(20), 0.35, n), 12, 70)
        put("wage", wage.astype(np.float32))
        put("summer_sales", (sex == "M") & (np.nan_to_num(ps["summer_sales"]) > 0.5))
        put("owns_car", np.nan_to_num(ps["owns_car"], nan=0.75) > 0.5)
        # Parental support from "parents pay for" items and parental income
        inc_mult = np.clip(0.4 + parent_income / 9, 0.4, 1.7)
        pp = (np.nan_to_num(cl["pp_tuition"]) * 300 + np.nan_to_num(cl["pp_rent"]) * 450
              + np.nan_to_num(cl["pp_insurance"]) * 120 + np.nan_to_num(cl["pp_car"]) * 150) * inc_mult
        pp = np.where((rel == "married") | (age > 26) | ~np.full(n, role in ("byu_student", "uvu_student", "young_adult")), pp * 0.25, pp)
        put("parental_support", pp.astype(np.float32))
        # students start the fall with summer/mission-fund savings; older people with more
        sav = np.clip(rng.lognormal(np.log(2500 + 150 * np.maximum(age - 18, 0) ** 1.6), 0.8, n), 0, 4e5)
        put("savings", sav.astype(np.float32))
        debt = (np.nan_to_num(cl["debt_student"]) * rng.uniform(3000, 25000, n)
                + np.nan_to_num(cl["debt_car"]) * rng.uniform(3000, 18000, n)
                + np.nan_to_num(cl["debt_cc"]) * rng.uniform(300, 4000, n))
        put("debt", debt.astype(np.float32))
        put("role", P.codes("role", np.full(n, role)))
        put("present", np.ones(n, dtype=bool))

        # internal: housing budget preference (survey housing cost), eat-out frequency
        P.add_internal("budget_pref", np.float32, 500.0)
        P.add_internal("eat_out_month", np.float32, 6.0)
        P.add_internal("live_parents_pref", np.bool_, False)
        S_int = {"budget_pref": np.clip(np.nan_to_num(cl["housing_cost"], nan=520), 0, 2500),
                 "eat_out_month": np.clip(np.nan_to_num(cl["eat_out_month"], nan=6), 0, 40),
                 "live_parents_pref": np.nan_to_num(cl["live_parents"]) > 0.5}

        for col, val in S.items():
            spec = P.specs.get(col)
            if spec is not None and spec.range and spec.dtype in ("f4", "f8"):
                val = np.clip(val, *spec.range)  # keep sampled tails inside the registry's declared support
            P.cols[col][ids] = val
        for col, val in S_int.items():
            P.internal[col][ids] = val
        return ids

    # ------------------------------------------------------------------ helpers
    def _calibrated_rel(self, school_key, sex, age, target_married, n):
        rel_cpt = self.sk["rel"]
        ab = age_band(age)
        cond = {"school_proxy": np.full(n, school_key), "sex": sex, "age_band": ab}
        # bisection on married odds multiplier using a probe sample
        lo, hi = 0.5, 12.0
        probe = np.random.default_rng(int(self.rng.integers(1 << 30)))
        for _ in range(14):
            mid = (lo + hi) / 2
            r = rel_cpt.sample(probe, cond, n, tilt={"married": mid, "engaged": np.sqrt(mid)})
            share = np.mean(r == rel_cpt.levels.index("married"))
            if share < target_married:
                lo = mid
            else:
                hi = mid
        mult = (lo + hi) / 2
        r = rel_cpt.sample(self.rng, cond, n, tilt={"married": mult, "engaged": np.sqrt(mult)})
        return np.array(rel_cpt.levels, dtype=object)[r]

    def _study_areas(self, school, n):
        from .sampling import load_priors
        tab = load_priors()["tables"]["study_area"].get(school) or load_priors()["tables"]["study_area"]["BYU"]
        names = [STUDY_AREA_MAP.get(k, "Undeclared") for k in tab]
        p = np.array(list(tab.values()), dtype=float)
        p /= p.sum()
        return np.array(names, dtype=object)[self.rng.choice(len(p), n, p=p)]
