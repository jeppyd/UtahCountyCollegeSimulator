"""Composed emotional/wellbeing states with exact additive attribution.

Each state s = clip(Σ_k term_k + Σ transient event effects + AR(1) noise).
Every term is a registered mechanism ("<state>.<term>"), and its current value is stored
per agent, so "why is this person lonely?" is answered by reading the decomposition and
then following each term's inputs (and each effect's source event) backwards.
"""
from __future__ import annotations

import numpy as np
from scipy.special import expit


STATE_ORDER = ["fatigue", "financial_stress", "academic_pressure", "romantic_longing", "stress", "loneliness",
               "belonging", "anxiety", "self_esteem", "guilt", "purpose", "mood"]
RANGE = {s: (0.0, 1.0) for s in STATE_ORDER}


class Emotion:
    def __init__(self, sim):
        self.sim = sim
        self.contrib: dict[str, dict[str, np.ndarray]] = {}
        self.transient: dict[str, np.ndarray] = {}

    def init(self):
        P = self.sim.w.P
        for s in STATE_ORDER:
            P.add_internal(f"ar_{s}", np.float32, 0.0)
        P.add_internal("sleep_base", np.float32, 7.0)
        P.internal["sleep_base"][: P.n] = P["sleep_hours"]
        P.add_internal("friends_mood", np.float32, 0.5)
        P.add_internal("last_date_day", np.int32, -60)
        P.add_internal("mood_8w", np.float32, 0.55)
        # warm start: neutral states then a few settling iterations
        for s in STATE_ORDER:
            P[s] = 0.3 if s != "mood" else 0.55
        P["ward_belonging"] = 0.5
        P["close_contact_hours"] = 8.0 * np.exp(0.2 * self.sim.z("extraversion"))
        P["social_hours_week"] = 15.0
        self.weekly()
        for _ in range(4):
            self.daily(settle=True)
        P.internal["mood_8w"][: P.n] = P["mood"]
        self._equilibrium_episodes()

    def _hazards(self):
        """Weekly onset and remission probabilities of a depressive episode (mental_health.depression)."""
        sim, P = self.sim, self.sim.w.P
        n = P.n
        m8 = P.internal["mood_8w"][:n]
        onset = expit(-7.9 + 14.0 * np.clip(0.42 - m8, 0, None) + 0.9 * P["mh_depression"] + 0.35 * sim.z("neuroticism")
                      + 2.0 * np.clip(P["loneliness"] - 0.5, 0, None))
        remit = 0.09 + 0.3 * np.clip(m8 - 0.4, 0, None)
        return onset, remit

    def _equilibrium_episodes(self):
        """Start each person in an episode with their stationary probability onset/(onset + remission),
        instead of everyone well: a cold start made prevalence climb for months (scripts/accounting.py)."""
        P = self.sim.w.P
        onset, remit = self._hazards()
        p_stat = onset / np.maximum(onset + remit, 1e-9)
        u = np.random.default_rng([self.sim.w.seed, 909]).random(P.n)
        P["depressive_episode"] = P["present"] & (u < p_stat)

    def p(self, name):
        return self.sim.p(name)

    # ------------------------------------------------------------------ term definitions
    def terms(self, s: str) -> dict[str, np.ndarray]:
        sim, w = self.sim, self.sim.w
        P, env = w.P, w.env
        p = self.p
        z = sim.z
        n = P.n
        in_rel = P.isin("rel_status", ["dating", "engaged", "married"])
        married = P.is_("rel_status", "married")
        single = P.isin("rel_status", ["single", "divorced"])
        enrolled = P["enrolled"] & np.where(P["school"] == 1, bool(env.get("term_BYU")), bool(env.get("term_UVU")))
        active = P.is_("activity", "active")
        T: dict[str, np.ndarray] = {}
        if s == "fatigue":
            T["setpoint"] = np.full(n, 0.22)
            T["sleep"] = p("fatigue.sleep.beta") * np.clip(7.5 - P["sleep_hours"], 0, 4) / 3
            load = P["work_hours"] + P["study_hours"] + 2.5 * P["credits_term"] * enrolled
            T["workload"] = p("fatigue.workload.beta") * np.clip((load - 45) / 40, 0, 1)
            T["children"] = 0.08 * np.minimum(P["children"], 3) / 3
        elif s == "financial_stress":
            exp_ = self.sim.systems["economy"].expenses
            if len(exp_) < n:
                exp_ = np.r_[exp_, np.full(n - len(exp_), 1500.0)]
            exp_ = np.maximum(exp_[:n], 300)
            buffer = P["savings"] / exp_
            T["buffer"] = p("financial_stress.buffer.beta") * expit((1.5 - buffer) / 0.6)
            T["debt"] = p("financial_stress.debt.beta") * np.clip(P["debt"] / 30000, 0, 1)
            T["rent_burden"] = p("financial_stress.rent_burden.beta") * np.clip(P["rent_burden"] - 0.4, 0, 1)
            T["setpoint"] = np.full(n, 0.05)
        elif s == "academic_pressure":
            prog = np.where(P["school"] == 1, env.get("term_progress_BYU", np.nan), env.get("term_progress_UVU", np.nan))
            exams = np.where(P["school"] == 1, env.get("exam_week_BYU", False), env.get("exam_week_UVU", False))
            T["load"] = enrolled * p("academic_pressure.load.beta") * P["credits_term"] / 15
            T["exams"] = enrolled * p("academic_pressure.exams.beta") * exams
            gpa = np.nan_to_num(P["gpa"], nan=3.3)
            T["gpa_gap"] = enrolled * p("academic_pressure.gpa_gap.beta") * np.clip(3.4 - gpa, 0, 1.5) / 1.5 * (1 + 0.3 * z("conscientiousness"))
            T["standing"] = enrolled * 0.15 * P.isin("academic_standing", ["warning", "probation"])
            del prog
        elif s == "romantic_longing":
            age = P["age"]
            lds_norm = active * np.clip((age - 20.5) / 3, 0, 1.2) * env["marriage_norm"]
            days_since = w.day - P.internal["last_date_day"][:n]
            T["wants"] = single * p("romantic_longing.wants.beta") * np.clip((P["wants_relationship"] - 1.5) / 2.5, 0, 1)
            T["marriage_norm"] = single * p("romantic_longing.marriage_norm.beta") * lds_norm
            T["drought"] = single * p("romantic_longing.drought.beta") * np.clip(days_since / 90, 0, 1)
            T["talking"] = -0.15 * P.is_("rel_status", "talking")
        elif s == "stress":
            T["setpoint"] = 0.16 + p("stress.setpoint.neuroticism") * z("neuroticism")
            T["academic"] = p("stress.academic.beta") * P["academic_pressure"]
            T["financial"] = p("stress.financial.beta") * P["financial_stress"]
            T["fatigue"] = p("stress.fatigue.beta") * P["fatigue"]
            sat = np.nan_to_num(P["relationship_satisfaction"], nan=0.6)
            T["relationship"] = in_rel * p("stress.relationship.beta") * np.clip(0.6 - sat, 0, 0.6)
            T["faith_crisis"] = p("stress.faith_crisis.beta") * P["faith_crisis"]
            T["minority_stress"] = p("stress.minority_stress.beta") * P["lgbtq_tension"] * (P["activity"] >= 2)
            # stress buffering: believing support is there blunts what the stressors do (Cohen & Wills 1985)
            load = T["academic"] + T["financial"] + T["relationship"] + T["faith_crisis"]
            T["support_buffer"] = -p("stress.support_buffer.beta") * (P["perceived_support"] - 0.35) * load
            T["coping"] = -p("stress.coping.beta") * P["coping_relief"]
        elif s == "loneliness":
            need = p("loneliness.contact_deficit.need_hours") * np.exp(p("loneliness.contact_deficit.extraversion") * z("extraversion"))
            contact = P["close_contact_hours"]
            T["setpoint"] = 0.43 + p("loneliness.setpoint.neuroticism") * z("neuroticism") + 0.025 * z("social_anxiety")
            T["contact_deficit"] = p("loneliness.contact_deficit.beta") * np.clip((need - contact) / need, -1, 1)
            T["close_friends"] = -p("loneliness.close_friends.beta") * np.log1p(P["n_close_friends"]) / np.log(6)
            # loneliness is *perceived* isolation: the support people believe they have matters beyond the count
            T["perceived_support"] = -p("loneliness.perceived_support.beta") * (P["perceived_support"] - 0.45)
            T["coping"] = -p("loneliness.coping.beta") * P["coping_relief"] * (P["coping_strategy"] == 1)
            T["partner"] = -p("loneliness.partner.beta") * (in_rel.astype(float) + 0.4 * married)
            T["ward"] = -p("loneliness.ward.beta") * (P["ward_belonging"] - 0.5) * (P["activity"] >= 2)
            T["roommates"] = -p("loneliness.roommates.beta") * (P["roommate_cohesion"] - 0.5)
            T["romantic"] = p("loneliness.romantic.beta") * P["romantic_longing"]
            T["outsider"] = p("loneliness.outsider.beta") * P["outsider"]
        elif s == "belonging":
            T["setpoint"] = np.full(n, 0.5)
            T["ward"] = p("belonging.ward.beta") * (P["ward_belonging"] - 0.5) * (P["activity"] >= 2)
            T["friends"] = p("belonging.friends.beta") * (np.log1p(P["n_friends"]) / np.log(15) - 0.5)
            T["roommates"] = 0.15 * (P["roommate_cohesion"] - 0.5)
            T["loneliness"] = -0.3 * (P["loneliness"] - 0.3)
            T["outsider"] = -p("belonging.outsider.beta") * P["outsider"]
            T["congregation"] = p("belonging.congregation.beta") * (P["service_attend"] - 0.3) * (P["congregation_id"] >= 0)
        elif s == "anxiety":
            T["setpoint"] = 0.18 + p("anxiety.setpoint.neuroticism") * z("neuroticism") + 0.12 * P["mh_anxiety"]
            T["stress"] = p("anxiety.stress.beta") * (P["stress"] - 0.25)
            T["social"] = 0.04 * z("social_anxiety")
        elif s == "self_esteem":
            T["setpoint"] = 0.55 - p("self_esteem.setpoint.neuroticism") * z("neuroticism") + 0.03 * z("extraversion")
            T["rejection"] = -p("self_esteem.rejection.beta") * np.log1p(P["rejections_recent"])
            T["dating_success"] = single * p("self_esteem.dating_success.beta") * np.clip(P["dates_30d"] / 4, 0, 1)
            T["relationship"] = 0.06 * in_rel
            gpa = np.nan_to_num(P["gpa"], nan=3.3)
            T["academic"] = enrolled * 0.06 * np.clip((gpa - 3.3) / 0.7, -1, 1)
        elif s == "guilt":
            not_permitted = 0.0 if env["coffee_permitted"] else 1.0
            ortho = P["orthodoxy"] * (1 - P["moral_autonomy"]) * P["lds_member"]
            T["setpoint"] = np.full(n, 0.03)
            T["word_of_wisdom"] = p("guilt.word_of_wisdom.beta") * ortho * (np.minimum(P["coffee"], 2) / 2 * not_permitted + np.minimum(P["alcohol"], 2) / 2)
            T["chastity"] = p("guilt.chastity.beta") * P["premarital_sex_current"] * P["chastity_commitment"]
            T["porn_incongruence"] = p("guilt.porn_incongruence.beta") * P["porn_incongruence"]
        elif s == "purpose":
            T["setpoint"] = 0.48 + 0.04 * z("conscientiousness")
            T["religion"] = p("purpose.religion.beta") * (P["religious_identity"] * P["faith_belief"] - 0.4)
            T["progress"] = p("purpose.progress.beta") * (enrolled & P.is_("academic_standing", "good") | (~P["enrolled"] & P["employed"]))
            T["family"] = 0.06 * married + 0.05 * (P["children"] > 0)
        elif s == "mood":
            T["setpoint"] = 0.55 + p("mood.setpoint.extraversion") * z("extraversion") - p("mood.setpoint.neuroticism") * z("neuroticism")
            T["loneliness"] = -p("mood.loneliness.beta") * (P["loneliness"] - 0.3)
            T["stress"] = -p("mood.stress.beta") * (P["stress"] - 0.3)
            sat = np.nan_to_num(P["relationship_satisfaction"], nan=0.5)
            T["relationship"] = in_rel * p("mood.relationship.beta") * (sat - 0.5)
            T["purpose"] = p("mood.purpose.beta") * (P["purpose"] - 0.5)
            T["sleep"] = -p("mood.sleep.beta") * np.clip(7 - P["sleep_hours"], 0, 4) / 3
            T["exercise"] = p("mood.exercise.beta") * np.clip(P["workouts_week"], 0, 7) / 7
            month = w.date.month
            T["season"] = np.full(n, -p("mood.season.beta") * (month in (12, 1, 2)))
            T["contagion"] = p("mood.contagion.beta") * (P.internal["friends_mood"][:n] - 0.55)
            T["guilt"] = -p("mood.guilt.beta") * P["guilt"]
            T["financial"] = -p("mood.financial.beta") * P["financial_stress"]
            T["depression"] = -0.15 * P["depressive_episode"]
            T["coping"] = p("mood.coping.beta") * P["coping_relief"]
            # rumination keeps recent negative memories active (memory.py; Nolen-Hoeksema 2000)
            load = P.internal["neg_load"][:n] if "neg_load" in P.internal else np.zeros(n)
            T["rumination"] = -p("mood.rumination.beta") * P["rumination"] * np.clip(load, 0, 3) / 3
        return T

    # ------------------------------------------------------------------ daily
    def daily(self, settle: bool = False):
        sim, w = self.sim, self.sim.w
        P = w.P
        n = P.n
        day = w.day
        # social contact EWMA (hours/week)
        if not settle:
            a = 1 / 7
            P["social_hours_week"] = (1 - a) * P["social_hours_week"] + a * 7 * P.internal["hours_today"][:n]
            P["close_contact_hours"] = (1 - a) * P["close_contact_hours"] + a * 7 * P.internal["close_hours_today"][:n]
            P.internal["hours_today"][:n] = 0
            P.internal["close_hours_today"][:n] = 0
            # sleep responds to stress, exams and new babies
            base = P.internal["sleep_base"][:n]
            noise = sim.streams.normal("sleep", day, n) * 0.5
            newborn = P.internal["newborn_until"][:n] > day if "newborn_until" in P.internal else np.zeros(n, bool)
            P["sleep_hours"] = np.clip(base - 0.9 * np.clip(P["stress"] - 0.35, 0, None) - 1.2 * newborn + noise, 3.5, 11)
            dated = P["activity_now"] == 7
            P.internal["last_date_day"][:n][dated] = day
        totals = sim.effects.totals(day, n) if not settle else {s: np.zeros(n) for s in STATE_ORDER}
        self.transient = totals
        phi = 0.8
        eps = sim.streams.normal("emotion_noise", day, n * len(STATE_ORDER)).reshape(len(STATE_ORDER), n)
        for k, s in enumerate(STATE_ORDER):
            T = self.terms(s)
            base = np.zeros(n)
            for v in T.values():
                base = base + v
            ar = P.internal[f"ar_{s}"][:n]
            ar = phi * ar + 0.025 * eps[k]
            P.internal[f"ar_{s}"][:n] = ar
            val = base + totals[s] + ar
            lo, hi = RANGE[s]
            P[s] = np.clip(val, lo, hi).astype(np.float32)
            self.contrib[s] = {k_: np.asarray(v, dtype=np.float32) for k_, v in T.items()}

    # ------------------------------------------------------------------ weekly
    def weekly(self):
        sim, w = self.sim, self.sim.w
        P, E = w.P, w.E
        n = P.n
        net = sim.systems["network"]
        fm, den = net.neighbor_mean(P["mood"].astype(np.float64), min_stage=3)
        P.internal["friends_mood"][:n] = np.where(den > 0, fm, P["mood"])
        # ward belonging: ward friends, attendance, fit (belief), LGBTQ tension
        lo, hi = E.endpoints()
        ward = P["ward_id"]
        same = (ward[lo] >= 0) & (ward[lo] == ward[hi]) & (E["stage"] >= 2)
        wf = np.bincount(np.r_[lo[same], hi[same]], minlength=n)
        cul = sim.systems.get("culture")
        warmth = cul.ward_warmth_dev(ward) if cul is not None and "culture" in w.meta else 0.0
        target = expit(-1.0 + 0.6 * np.log1p(wf) + 1.6 * (P["attend_rate"] - 0.5) + 1.0 * (P["faith_belief"] - 0.6)
                       - 1.5 * P["lgbtq_tension"] + 0.3 * sim.z("extraversion") + sim.p("culture.feedback.ward_warmth") * warmth)
        P["ward_belonging"] = (0.6 * P["ward_belonging"] + 0.4 * np.where(ward >= 0, target, 0.3)).astype(np.float32)
        P.internal["mood_8w"][:n] = 0.88 * P.internal["mood_8w"][:n] + 0.12 * P["mood"]
        # depressive episodes: onset rises steeply when sustained mood is low (threshold non-linearity)
        u = sim.u("depress")
        onset, remit = self._hazards()
        start = P["present"] & ~P["depressive_episode"] & (u < onset)
        stop = P["depressive_episode"] & (u < remit)
        if start.any():
            P.cols["depressive_episode"][np.where(start)[0]] = True
            sim.emit("depressive_episode_start", np.where(start)[0], mech="mental_health.depression")
        if stop.any():
            P.cols["depressive_episode"][np.where(stop)[0]] = False
            sim.emit("depressive_episode_end", np.where(stop)[0], mech="mental_health.depression")

    def monthly(self):
        P = self.sim.w.P
        rel = np.nan_to_num(P["relationship_satisfaction"], nan=0.5)
        ls = 10 * (0.4 * P["mood"] + 0.2 * P["purpose"] + 0.15 * (1 - P["financial_stress"]) + 0.15 * rel + 0.1 * (1 - P["loneliness"]))
        ls = ls + 0.6 * P["memory_tone"]   # the remembered past colors the judgment (memory.tone)
        P["life_satisfaction"] = np.where(P["life_satisfaction"] > 0, 0.7 * P["life_satisfaction"] + 0.3 * ls, ls).astype(np.float32)
