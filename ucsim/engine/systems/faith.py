"""Religious life: practice, belief, certainty, identity, crises and their resolution.

* Attendance is a habit (Lally et al. 2010) whose probability combines belief, identity,
  habit strength, the perceived local norm (roommates/friends/ward), family expectation,
  and frictions (Sunday work, fatigue, stress).
* Belief moves by closeness-weighted social influence whose strength rises as certainty
  falls ("friend influence matters more when someone is uncertain"), by spiritual
  experiences and faith challenges, and by belief–behavior dissonance: persistent guilt
  either resolves through behavior change/repentance or through belief change, depending
  on identity, certainty and moral autonomy (Festinger-style dissonance; hypothetical form).
* Faith crises resolve into renewal, nuanced continuation, or disaffiliation.
* Non-members: Catholic, Protestant and other believers attend real congregations in Provo/Orem;
  everyone outside the LDS mainstream can feel like a religious outsider (softened by friends who
  share their outlook and by a faith or secular community); LDS friends and partners invite some to
  meet the missionaries, and a few are baptized.
"""
from __future__ import annotations

import numpy as np
from scipy.special import expit

from ..provenance import chance, latest_event, link, pick, softmax_prob, state_ref


class Faith:
    def __init__(self, sim):
        self.sim = sim
        self.attending_today = np.zeros(0, bool)
        self.attending_other = np.zeros(0, bool)

    def init(self):
        P = self.sim.w.P
        P.add_internal("attend_prob", np.float32, 0.0)
        P.add_internal("crisis_start", np.int32, -1)
        P.add_internal("guilt_weeks", np.int16, 0)
        P.add_internal("works_sunday", np.bool_, False)
        P.internal["attend_prob"][: P.n] = P["attend_rate"]
        if "shift_start" in P.internal:      # a Sunday shift during the morning meetings
            s, e = P.internal["shift_start"][: P.n, 6].astype(np.int32), P.internal["shift_end"][: P.n, 6].astype(np.int32)
            P.internal["works_sunday"][: P.n] = (s >= 0) & (s < 12 * 60) & (e > 9 * 60)
        self.attending_today = np.zeros(P.n, bool)
        self.attending_other = np.zeros(P.n, bool)
        w = self.sim.w
        if not getattr(w, "congregations", None):
            from ...population.build import load_congregations
            w.congregations = load_congregations()
        P.add_internal("other_attend_prob", np.float32, 0.0)
        P.add_internal("investigate_start", np.int32, -1)
        P.add_internal("missionary_day", np.int32, -10_000)
        self.find_congregations(np.where(P["present"])[0], emit=False)
        P.internal["other_attend_prob"][: P.n] = P["service_attend"]
        self._norms()
        P.add_internal("temple_pref", np.float32, 0.0)
        P.add_internal("scripture_pref", np.float32, 0.0)
        self.init_practices(np.arange(P.n))

    def meeting_start(self, ids) -> np.ndarray:
        """Minute each person's Sunday meeting starts: wards meet in two-hour blocks at 9, 10:30, noon or 1:30 (spread
        over the wards sharing a building); other congregations at 10."""
        P = self.sim.w.P
        ids = np.asarray(ids, np.int64)
        ward = P["ward_id"][ids].astype(np.int64)
        times = np.array([9 * 60, 10 * 60 + 30, 12 * 60, 13 * 60 + 30], np.int64)
        return np.where(P["lds_member"][ids] & (ward >= 0), times[np.maximum(ward, 0) % 4], 10 * 60)

    def init_practices(self, ids):
        """Store sampled practice levels as preferences and set current practice from activity."""
        P = self.sim.w.P
        P.internal["temple_pref"][ids] = P["temple_per_year"][ids]
        P.internal["scripture_pref"][ids] = P["scripture_minutes"][ids]
        self.practices(ids, rate=1.0)

    def practices(self, ids, rate: float | None = None):
        P, p = self.sim.w.P, self.sim.p
        r = p("faith.practices.adjust_rate") if rate is None else rate
        act = P["activity"][ids]
        f = np.select([act == 3, act == 2, act == 1], [1.0, p("faith.practices.less_active_factor"), p("faith.practices.inactive_factor")], 0.0)
        f = f * P["lds_member"][ids]
        g = np.where(P["temple_recommend"][ids], 1.0, 0.15)
        t = P["temple_per_year"][ids]
        sc = P["scripture_minutes"][ids]
        P.cols["temple_per_year"][ids] = t + r * (P.internal["temple_pref"][ids] * f * g - t)
        P.cols["scripture_minutes"][ids] = sc + r * (P.internal["scripture_pref"][ids] * f - sc)

    def daily(self):
        sim, w = self.sim, self.sim.w
        P = w.P
        n = P.n
        if w.env["weekday"] != 6:
            self.attending_today = np.zeros(n, bool)
            self.attending_other = np.zeros(n, bool)
            return
        other = ~P["lds_member"] & P["present"] & (P["congregation_id"] >= 0)
        self.attending_other = other & (sim.u("church_other") < P.internal["other_attend_prob"][:n])
        P["service_attend"] = np.where(other, 0.88 * P["service_attend"] + 0.12 * self.attending_other,
                                       P["service_attend"]).astype(np.float32)
        u = sim.u("church")
        conf = w.env["conference"]
        prob = P.internal["attend_prob"][:n] * (0.0 if conf else 1.0)
        # not taking the sacrament for a while: some stay home so nobody sees them pass the tray
        shy = P.internal["church_shy"][:n] if "church_shy" in P.internal else None
        if shy is not None and shy.any():
            prob = np.where(shy, prob * sim.p("institutions.bishop.skip_attend"), prob)
        att = P["lds_member"] & P["present"] & (P["ward_id"] >= 0) & (u < prob)
        self.attending_today = att
        members = P["lds_member"] & P["present"]
        if conf:  # General Conference weekend: watched at home; attendance rate unchanged
            return
        a = 0.12
        rate = P["attend_rate"]
        P["attend_rate"] = np.where(members, (1 - a) * rate + a * att, rate).astype(np.float32)
        h = P["practice_habit"]
        lr = sim.p("faith.habit.learning_rate")
        P["practice_habit"] = np.where(members, np.where(att, h + lr * (1 - h), h * (1 - lr * 0.4)), h).astype(np.float32)

    def _plan_bias(self):
        plans = self.sim.systems.get("plans")
        return plans.church_boost() if plans is not None else 0.0

    def _norms(self):
        sim, w = self.sim, self.sim.w
        P = w.P
        net = sim.systems["network"]
        n = P.n
        friend_norm, den = net.neighbor_mean(P["attend_rate"].astype(np.float64), min_stage=2)
        friend_belief, _ = net.neighbor_mean(P["faith_belief"].astype(np.float64), min_stage=2)
        ward = P["ward_id"]
        wn = np.zeros(int(ward.max()) + 2)
        wc = np.zeros_like(wn)
        mm = ward >= 0
        np.add.at(wn, ward[mm], P["attend_rate"][mm])
        np.add.at(wc, ward[mm], 1)
        ward_mean = np.where(ward >= 0, wn[np.maximum(ward, 0)] / np.maximum(wc[np.maximum(ward, 0)], 1), 0.3)
        has = den > 0
        norm = np.where(has, 0.65 * np.nan_to_num(friend_norm) + 0.35 * ward_mean, ward_mean)
        # where people live carries its own norm: a devout complex raises it, a secular one lowers it (culture.feedback.norm)
        cul = sim.systems.get("culture")
        if cul is not None and "culture" in w.meta:
            cr = cul.complex_relig(P["complex_id"])
            wn = sim.p("culture.feedback.norm")
            norm = np.where(np.isfinite(cr), (1 - wn) * norm + wn * np.nan_to_num(cr), norm)
        P["perceived_norm"] = norm.astype(np.float32)
        # influence works through what people *perceive* their friends believe (mind.pluralistic_ignorance)
        perceived = P["perceived_friend_belief"]
        self.friend_belief = np.where(has, np.where(perceived > 0, perceived, np.nan_to_num(friend_belief)), P["faith_belief"])
        del n

    def weekly(self):
        sim, w = self.sim, self.sim.w
        P, p = w.P, sim.p
        n = P.n
        day = w.day
        self._norms()
        lds = P["lds_member"] & P["present"]
        belief = P["faith_belief"].astype(np.float64)
        cert = P["faith_certainty"].astype(np.float64)
        ident = P["religious_identity"].astype(np.float64)
        # ---- attendance probability for next Sunday, term by term (added in the model's order; subtracted terms
        # are kept positive here and recorded with their sign)
        T = {"belief": p("faith.attend.belief") * (belief - 0.6), "identity": p("faith.attend.identity") * (ident - 0.5),
             "habit": p("faith.attend.habit") * (P["practice_habit"] - 0.5), "norm": p("faith.attend.norm") * (P["perceived_norm"] - 0.5),
             "family": p("faith.attend.family") * P["family_expectation"],
             "stress": p("faith.attend.stress") * np.clip(P["stress"] - 0.3, 0, None), "fatigue": 0.8 * P["fatigue"],
             "sunday_work": 2.0 * P.internal["works_sunday"][:n], "world": np.log(w.env["church_attendance_norm"] + 1e-9),
             "crisis": 1.0 * P["faith_crisis"], "coping": sim.systems["coping"].church_bias(), "intention": self._plan_bias(),
             "nudge": sim.nudge("attend")}
        ap = expit(p("faith.attend.base") + T["belief"] + T["identity"] + T["habit"] + T["norm"] + T["family"] - T["stress"]
                   - T["fatigue"] - T["sunday_work"] + T["world"] - T["crisis"] + T["coping"] + T["intention"] + T["nudge"])
        P.internal["attend_prob"][:n] = np.where(lds, ap, 0)
        self._track_attendance_terms(T, lds)
        # ---- events: spiritual experiences & faith challenges
        u1, u2 = sim.u("spirit"), sim.u("challenge")
        h_sp = p("faith.spiritual.rate") * (0.3 + P["private_practice"] + 0.5 * P["attend_rate"]) * belief
        sp = lds & (u1 < h_sp)
        TC = {"openness": 0.35 * sim.z("openness"), "social_media": 0.15 * np.log1p(P["social_media_hours"]),
              "history": 0.8 * P["history_struggle"] / 4, "lgbtq": 1.2 * P["lgbtq_tension"], "certainty": 0.8 * (cert - 0.6)}
        h_ch = p("faith.challenge.rate") * np.exp(TC["openness"] + TC["social_media"] + TC["history"] + TC["lgbtq"] - TC["certainty"])
        ch = lds & (u2 < h_ch)
        D = sim.decisions
        if sp.any():
            ids = np.where(sp)[0]
            did = D.record("spiritual_experience", day, ids, "happened",
                           {"practice": np.log(0.3 + P["private_practice"][ids] + 0.5 * P["attend_rate"][ids]),
                            "belief": np.log(np.maximum(belief[ids], 1e-6))},
                           base=float(np.log(p("faith.spiritual.rate"))), prob=h_sp[ids])
            sim.emit("spiritual_experience", ids, mech="faith.spiritual", decision=did)
        if ch.any():
            ids = np.where(ch)[0]
            rec = pick(TC, ids)
            rec["certainty"] = -rec["certainty"]
            did = D.record("faith_challenge", day, ids, "happened", rec, base=float(np.log(p("faith.challenge.rate"))),
                           prob=h_ch[ids], refs={"certainty": ("state", state_ref(sim, "faith_certainty", ids))})
            sim.emit("faith_challenge", ids, mech="faith.challenge", decision=did)
        # ---- belief update
        susc = p("faith.influence.base") * (1 - cert) * np.exp(0.3 * sim.z("conformity"))
        gap = self.friend_belief - belief
        if p("faith.influence.form") >= 0.5:
            # alternative form — bounded confidence (Hegselmann & Krause 2002): views far from one's own barely move it
            susc = susc * np.where(np.abs(gap) <= p("faith.influence.bound"), 1.0, 0.2)
        d_social = susc * gap
        d_events = 0.03 * sp - p("faith.challenge.belief_hit") * ch * (1 - cert)
        # dissonance: persistent guilt over standards → belief erosion for low-identity/high-autonomy agents,
        # otherwise behavior change (handled in norms) and repentance (romance)
        guilty = P["guilt"] > 0.3
        gw = np.where(guilty, P.internal["guilt_weeks"][:n] + 1, np.maximum(P.internal["guilt_weeks"][:n] - 1, 0))
        P.internal["guilt_weeks"][:n] = np.minimum(gw, 500)
        d_dis = -p("faith.dissonance.belief_shift") * (gw >= 4) * P["guilt"] * (1 - ident) * (0.5 + P["moral_autonomy"])
        noise = 0.004 * sim.streams.normal("belief_noise", day, n)
        new_b = np.clip(belief + d_social + d_events + d_dis + noise, 0.01, 0.99)
        P["faith_belief"] = np.where(lds, new_b, belief).astype(np.float32)
        # certainty: experiences up, challenges/disagreement down, slow pull toward belief-consistent level
        d_c = 0.04 * sp - p("faith.challenge.certainty_hit") * ch - 0.05 * np.abs(self.friend_belief - belief) + 0.01 * (new_b - cert)
        P["faith_certainty"] = np.where(lds, np.clip(cert + d_c, 0.02, 0.99), cert).astype(np.float32)
        # identity follows practice slowly
        P["religious_identity"] = np.where(lds, np.clip(ident + 0.01 * (P["attend_rate"] - ident) + 0.005 * (new_b - ident), 0.01, 0.99), ident).astype(np.float32)
        # ---- activity category from attendance
        old = P["activity"].copy()
        rate = P["attend_rate"]
        # hysteresis bands: active ↔ less active at 0.55/0.65, less active ↔ inactive at 0.10/0.20
        new = old.copy()
        new = np.where((old == 3) & (rate < 0.55), 2, new)
        new = np.where((old == 2) & (rate > 0.65), 3, new)
        new = np.where((old == 2) & (rate < 0.10), 1, new)
        new = np.where((old == 1) & (rate > 0.20), 2, new)
        new = np.where(P["lds_member"], np.maximum(new, 1), 0).astype(np.uint8)
        P["activity"] = np.where(P["present"], new, old).astype(np.uint8)
        stopped = P["present"] & (old >= 2) & (new == 1)
        back = P["present"] & (old <= 2) & (old >= 1) & (new == 3)
        if stopped.any():
            ids = np.where(stopped)[0]
            sim.emit("stopped_attending", ids, mech="faith.attend", decision=self._attendance_change(ids, 0, ap))
        if back.any():
            ids = np.where(back)[0]
            ev = sim.emit("returned_to_activity", ids, mech="faith.attend", decision=self._attendance_change(ids, 1, ap))
            plans = sim.systems.get("plans")
            if plans is not None:
                link(sim, ev, "event", plans.formed_event(ids, "return_to_church"), 0.6, "intention")
        # temple recommend gained/lost
        # a practice the Church permits no longer costs a recommend
        clean = (((P["coffee"] == 0) | bool(w.env.get("coffee_permitted"))) & ((P["alcohol"] == 0) | bool(w.env.get("alcohol_permitted")))
                 & ~P["premarital_sex_current"])
        eligible = P["lds_member"] & (P["activity"] == 3) & (P["faith_belief"] > 0.6) & clean & (P["age"] >= 18)
        if "recommend_hold_until" in P.internal:            # not while the bishop is holding it back
            eligible &= P.internal["recommend_hold_until"][: P.n] < 0
        gain = eligible & ~P["temple_recommend"] & (sim.u("tr") < 0.03)
        lose = P["temple_recommend"] & (~clean | (P["activity"] < 3)) & (sim.u("tr2") < 0.2)
        P.cols["temple_recommend"][np.where(gain)[0]] = True
        P.cols["temple_recommend"][np.where(lose)[0]] = False
        self.practices(np.where(P["present"])[0])
        self.weekly_other()

    # ------------------------------------------------------------------ non-members
    def crisis(self):
        """Faith crises begin and resolve on each person's own day of the week (a weekly chance)."""
        sim, w = self.sim, self.sim.w
        P, p = w.P, sim.p
        n = P.n
        day = w.day
        lds = P["lds_member"] & P["present"]
        belief = P["faith_belief"].astype(np.float64)
        ident = P["religious_identity"].astype(np.float64)
        gw = P.internal["guilt_weeks"][:n]
        crisis = P["faith_crisis"]
        turn = sim.my_turn(np.arange(n))
        on = turn & lds & ~crisis & (P["faith_certainty"] < p("faith.crisis.certainty_threshold")) & (sim.u("crisis_on") < p("faith.crisis.onset_rate"))
        if on.any():
            ids = np.where(on)[0]
            P.cols["faith_crisis"][ids] = True
            P.internal["crisis_start"][ids] = day
            P.cols["struggled_faith"][ids] = True
            ev = sim.emit("faith_crisis_start", ids, mech="faith.crisis")
            self._why_crisis(ev, ids, gw[ids], belief[ids])
        dur = day - P.internal["crisis_start"][:n]
        res = turn & lds & crisis & (dur > 60) & (sim.u("crisis_res") < p("faith.crisis.resolution_rate"))
        if res.any():
            ids = np.where(res)[0]
            fam = P["family_expectation"][ids]
            # each outcome's utility term by term ("_base" = the option's constant)
            O = [{"identity": 1.5 * ident[ids], "norm": 1.0 * P["perceived_norm"][ids], "family": 0.8 * fam,
                  "trust": 0.8 * P["institutional_trust"][ids]},
                 {"_base": 0.8, "identity": 1.0 * ident[ids], "autonomy": 0.6 * P["moral_autonomy"][ids]},
                 {"_base": p("faith.crisis.leave_bias"), "belief_lost": 1.4 * (1 - P["faith_belief"][ids]),
                  "autonomy": 1.0 * P["moral_autonomy"][ids], "lgbtq": 1.5 * P["lgbtq_tension"][ids],
                  "norm_low": 0.8 * (1 - P["perceived_norm"][ids]), "family": -(1.0 * fam)}]
            u_renew = O[0]["identity"] + O[0]["norm"] + O[0]["family"] + O[0]["trust"]
            u_nuance = O[1]["_base"] + O[1]["identity"] + O[1]["autonomy"]
            u_leave = (O[2]["_base"] + O[2]["belief_lost"] + O[2]["autonomy"] + O[2]["lgbtq"] + O[2]["norm_low"] - 1.0 * fam)
            g = sim.streams.gen("crisis_outcome", day).gumbel(size=(len(ids), 3))
            Uo = np.c_[u_renew, u_nuance, u_leave]
            outcome = np.argmax(Uo + g, axis=1)
            cause = self._last_event(ids, "faith_crisis_start")
            did = self._record_options("crisis_outcome", ids, outcome, O, Uo)
            P.cols["faith_crisis"][ids] = False
            r = ids[outcome == 0]
            if len(r):
                P.cols["faith_belief"][r] = np.clip(P["faith_belief"][r] + 0.15, 0, 0.99)
                P.cols["faith_certainty"][r] = np.clip(P["faith_certainty"][r] + 0.3, 0, 0.95)
                sim.emit("faith_renewed", r, cause=cause[outcome == 0], mech="faith.crisis", decision=did[outcome == 0])
            nu = ids[outcome == 1]
            if len(nu):
                P.cols["faith_certainty"][nu] = 0.5
                P.cols["orthodoxy"][nu] = np.clip(P["orthodoxy"][nu] - 0.12, 0, 1)
                P.cols["moral_autonomy"][nu] = np.clip(P["moral_autonomy"][nu] + 0.1, 0, 1)
                sim.emit("faith_nuanced", nu, cause=cause[outcome == 1], mech="faith.crisis", decision=did[outcome == 1])
            lv = ids[outcome == 2]
            if len(lv):
                P.cols["religious_identity"][lv] = np.clip(P["religious_identity"][lv] - 0.45, 0.01, 1)
                P.cols["faith_belief"][lv] = np.clip(P["faith_belief"][lv] - 0.3, 0.01, 1)
                P.cols["practice_habit"][lv] *= 0.4
                P.cols["chastity_commitment"][lv] = np.clip(P["chastity_commitment"][lv] - 0.25, 0, 1)
                P.cols["temple_recommend"][lv] = False
                resign = sim.u("resign")[lv] < 0.2
                P.cols["lds_member"][lv[resign]] = False
                gone = lv[resign]
                if len(gone):
                    alt = sim.u("new_affiliation")[gone]
                    P.cols["affiliation"][gone] = np.where(alt < 0.85, P.code("affiliation", "Nonreligious"),
                                                           np.where(alt < 0.95, P.code("affiliation", "Protestant"),
                                                                    P.code("affiliation", "Other faith")))
                    P.cols["ward_id"][gone] = -1
                dis = sim.emit("disaffiliated", lv, cause=cause[outcome == 2], mech="faith.crisis", decision=did[outcome == 2])
                if len(gone):
                    sim.emit("resigned_membership", gone, cause=dis[resign], mech="faith.crisis")

    def find_congregations(self, ids: np.ndarray, emit: bool = True):
        """Religious non-members without a congregation pick one of the nearest of their tradition."""
        sim, w = self.sim, self.sim.w
        P, C = w.P, w.congregations
        if not len(C.get("name", [])) or len(ids) == 0:
            return
        caff = np.array(C["affiliation"])
        aff = P["affiliation"][ids]
        need = ids[~P["lds_member"][ids] & (P["congregation_id"][ids] < 0) & (P["own_religiosity"][ids] > 0.3)
                   & ~np.isin(aff, [P.code("affiliation", "Nonreligious"), P.code("affiliation", "Muslim")])]
        if len(need) == 0:
            return
        rng = sim.streams.gen("congregation", w.day, int(need[0]) % 997)
        cats = P.specs["affiliation"].categories
        joined = []
        for i in need:
            same = np.where(caff == cats[int(P["affiliation"][i])])[0]
            if len(same) == 0:
                same = np.where(caff == "Protestant")[0] if cats[int(P["affiliation"][i])] == "Other Christian" else same
            if len(same) == 0:
                continue
            d = np.hypot((C["lon"][same] - P["home_lon"][i]) * 85, (C["lat"][same] - P["home_lat"][i]) * 111)
            near = same[np.argsort(d)[:3]]
            pr = np.array([0.6, 0.25, 0.15][: len(near)])
            P.cols["congregation_id"][i] = int(rng.choice(near, p=pr / pr.sum()))
            joined.append(i)
        if emit and joined:
            joined = np.array(joined)
            # finding a congregation follows arriving or moving (or starting the story without one)
            sim.emit("joined_congregation", joined, mech="faith.other_attend",
                     cause=latest_event(sim, joined, ("arrival", "moved", "mission_return", "early_return"), w.day - 400))

    def weekly_other(self):
        sim, w = self.sim, self.sim.w
        P, p, E = w.P, sim.p, w.E
        n = P.n
        day = w.day
        pres = P["present"]
        non = ~P["lds_member"] & pres
        # newcomers and movers find a congregation; attendance probability for next week
        self.find_congregations(np.where(non & (P["congregation_id"] < 0) & (P["own_religiosity"] > 0.3))[0])
        ap = expit(p("faith.other_attend.base") + p("faith.other_attend.religiosity") * (P["own_religiosity"] - 0.5)
                   + p("faith.other_attend.habit") * (P["service_attend"] - 0.4) - 0.8 * P["fatigue"]
                   - 0.6 * np.clip(P["stress"] - 0.3, 0, None))
        P.internal["other_attend_prob"][:n] = np.where(non & (P["congregation_id"] >= 0), ap, 0)
        # own religiosity drifts slowly toward practice (and slightly downward for the unattached)
        orl = P["own_religiosity"]
        P["own_religiosity"] = np.where(non & (P["affiliation"] != P.code("affiliation", "Nonreligious")),
                                        np.clip(orl + 0.01 * (P["service_attend"] - orl) - 0.0005, 0.02, 0.99), orl).astype(np.float32)
        # ---- outsider feeling: non-members and members who have stepped away
        lo, hi = E.endpoints()
        fr = E["stage"] >= 2
        lds = P["lds_member"] & (P["activity"] >= 2)
        cnt = np.bincount(np.r_[lo[fr], hi[fr]], minlength=n).astype(float)
        lds_cnt = np.bincount(np.r_[lo[fr & lds[hi]], hi[fr & lds[lo]]], minlength=n).astype(float)
        share = np.where(cnt > 0, lds_cnt / np.maximum(cnt, 1), 0.5)
        close = E["stage"] >= 3
        outside = ~lds
        kin = np.zeros(n, bool)
        kin[lo[close & outside[hi]]] = True
        kin[hi[close & outside[lo]]] = True
        unit = P["unit_id"]
        um = (unit >= 0) & pres
        u_tot = np.bincount(unit[um], minlength=len(w.units)).astype(float)
        u_lds = np.bincount(unit[um & lds], minlength=len(w.units)).astype(float)
        mates = np.where(unit >= 0, (u_lds[np.maximum(unit, 0)] - lds) / np.maximum(u_tot[np.maximum(unit, 0)] - 1, 1), 0)
        community = (P["congregation_id"] >= 0) & (P["service_attend"] > 0.3)
        if "club_id" in P and w.groups:
            fc = np.asarray(w.groups.get("faith", np.full(len(w.groups["kind"]), "")), dtype=object)
            cl = P["club_id"]
            community |= (cl >= 0) & (fc[np.maximum(cl, 0)] != "")
        pitched = (day - P.internal["missionary_day"][:n]) < 120
        target = np.clip(0.12 + 0.35 * share + 0.15 * mates + 0.12 * (P["school"] == 1) + 0.15 * pitched
                         - 0.2 * kin - 0.15 * community - 0.1 * w.env.get("interfaith_welcome", 0.0), 0, 1)
        wgt = p("faith.outsider.weight")
        P["outsider"] = np.where(outside & pres, (1 - wgt) * P["outsider"] + wgt * target, 0).astype(np.float32)
        # ---- missionary contact (non-members with believing LDS close friends or an LDS partner)
        believing = P["lds_member"] & (P["faith_belief"] > 0.6) & (P["activity"] >= 2)
        bf = np.bincount(np.r_[lo[close & believing[hi]], hi[close & believing[lo]]], minlength=n).astype(float)
        partner = P["partner_id"]
        lds_partner = (partner >= 0) & P["lds_member"][np.maximum(partner, 0)]
        cand = non & ~P["investigating"] & (P["age"] >= 16) & ((day - P.internal["missionary_day"][:n]) > 365)
        h = p("faith.missionary_contact.rate") * (bf + 3 * lds_partner) * np.exp(0.3 * sim.z("openness") - 1.5 * P["own_religiosity"])
        start = cand & (sim.u("missionaries") < h)
        if start.any():
            ids = np.where(start)[0]
            P.cols["investigating"][ids] = True
            P.internal["investigate_start"][ids] = day
            P.internal["missionary_day"][ids] = day
            # who brought it about: an LDS partner, else their closest believing friend
            closest = self._closest(ids, lo, hi, close, E["closeness"], believing)
            inviter = np.where(lds_partner[ids], partner[ids], closest)
            did = sim.decisions.record("met_missionaries", day, ids, "started",
                                       {"friends": np.log(bf[ids] + 3 * lds_partner[ids]), "openness": 0.3 * sim.z("openness")[ids],
                                        "religiosity": -1.5 * P["own_religiosity"][ids]},
                                       base=float(np.log(p("faith.missionary_contact.rate"))), prob=h[ids],
                                       other=inviter, refs={"friends": ("person", inviter)})
            ev = sim.emit("met_missionaries", ids, mech="faith.missionary_contact", decision=did)
            link(sim, ev, "person", inviter, 1.0, "invited_by")
        # ---- lessons: baptism or stopping
        inv = P["investigating"] & pres & ~P["lds_member"]
        if inv.any():
            dating_lds = lds_partner & P.isin("rel_status", ["dating", "engaged", "married"])
            hb = expit(p("faith.conversion.base") + 2.0 * dating_lds + 1.5 * share - 2.0 * P["own_religiosity"])
            weeks = (day - P.internal["investigate_start"][:n]) / 7
            bap = inv & (weeks >= 3) & (sim.u("baptism") < hb)
            stop = inv & ~bap & (sim.u("stop_lessons") < 0.08)
            if bap.any():
                ids = np.where(bap)[0]
                did = sim.decisions.record("baptism", day, ids, "baptized",
                                           {"dating_lds": 2.0 * dating_lds[ids], "friends": 1.5 * share[ids],
                                            "religiosity": -2.0 * P["own_religiosity"][ids]},
                                           base=p("faith.conversion.base"), prob=hb[ids])
                self.baptize(ids, decision=did)
            if stop.any():
                ids = np.where(stop)[0]
                P.cols["investigating"][ids] = False
                did = chance(sim, "stop_lessons", ids, 0.08, "stopped")
                sim.emit("stopped_investigating", ids, mech="faith.missionary_contact", decision=did,
                         cause=self._last_event(ids, "met_missionaries"))

    @staticmethod
    def _closest(ids: np.ndarray, lo: np.ndarray, hi: np.ndarray, mask: np.ndarray, weight: np.ndarray,
                 other_ok: np.ndarray) -> np.ndarray:
        """For each person in ids, the closest other end (by `weight`) of their ties in `mask` for whom other_ok
        holds (−1 if none)."""
        a = np.r_[lo[mask], hi[mask]]
        b = np.r_[hi[mask], lo[mask]]
        wt = np.r_[weight[mask], weight[mask]]
        out = np.full(len(ids), -1, np.int64)
        sel = np.isin(a, ids) & other_ok[b] if len(a) else np.zeros(0, bool)
        a, b, wt = a[sel], b[sel], wt[sel]
        if not len(a):
            return out
        order = np.lexsort((-wt, a))
        a, b = a[order], b[order]
        first = np.r_[True, a[1:] != a[:-1]]
        af, bf = a[first], b[first]
        k = np.clip(np.searchsorted(af, ids), 0, len(af) - 1)
        hit = af[k] == ids
        out[hit] = bf[k[hit]]
        return out

    def baptize(self, ids: np.ndarray, decision=None):
        sim, w = self.sim, self.sim.w
        P = w.P
        cause = self._last_event(ids, "met_missionaries")
        P.cols["lds_member"][ids] = True
        P.cols["converted"][ids] = True
        P.cols["investigating"][ids] = False
        P.cols["affiliation"][ids] = P.code("affiliation", "Latter-day Saint")
        P.cols["congregation_id"][ids] = -1
        P.cols["activity"][ids] = P.code("activity", "active")
        P.cols["attend_rate"][ids] = 0.8
        P.internal["attend_prob"][ids] = 0.85
        P.cols["practice_habit"][ids] = np.maximum(P["practice_habit"][ids], 0.35)
        P.cols["faith_belief"][ids] = np.maximum(P["faith_belief"][ids], 0.72)
        P.cols["faith_certainty"][ids] = np.maximum(P["faith_certainty"][ids], 0.55)
        P.cols["religious_identity"][ids] = np.maximum(P["religious_identity"][ids], 0.45)
        P.cols["orthodoxy"][ids] = np.maximum(P["orthodoxy"][ids], 0.55)
        P.cols["outsider"][ids] = 0.1
        sim.systems["housing"]._assign_ward(ids)
        sim.systems["lifecourse"]._fhe_for(ids)
        sim.emit("baptized", ids, cause=cause, mech="faith.conversion", decision=decision)

    # ------------------------------------------------------------------ provenance
    # the weekly attendance log-odds terms, with their sign (subtracted terms count negative)
    ATT_TERMS = ("belief", "identity", "habit", "norm", "family", "stress", "fatigue", "sunday_work", "crisis", "coping",
                 "intention", "whatif")
    _ATT_SIGN = {"stress": -1.0, "fatigue": -1.0, "sunday_work": -1.0, "crisis": -1.0}

    def _track_attendance_terms(self, T: dict, lds: np.ndarray):
        """Keep each member's recent (about three weeks) and usual (about three months) value of every attendance
        term, so a change in how often they go can be explained by what moved. Bookkeeping only."""
        P = self.sim.w.P
        n = P.n
        fresh = "att_fast_belief" not in P.internal
        for f in self.ATT_TERMS:
            for kind in ("fast", "slow"):
                P.add_internal(f"att_{kind}_{f}", np.float32, 0.0)
        P.add_internal("att_ready", np.bool_, False)
        ready = P.internal["att_ready"][:n] & (not fresh)
        for f in self.ATT_TERMS:
            v = (T["world"] + T["nudge"]) if f == "whatif" else self._ATT_SIGN.get(f, 1.0) * T[f]
            v = np.broadcast_to(np.asarray(v, np.float32), (n,))
            for kind, a in (("fast", 0.35), ("slow", 0.08)):
                col = P.internal[f"att_{kind}_{f}"][:n]
                col[:] = np.where(lds, np.where(ready, (1 - a) * col + a * v, v), col)
        P.internal["att_ready"][:n] |= lds

    def _attendance_change(self, ids: np.ndarray, outcome: int, ap: np.ndarray) -> np.ndarray:
        """Why someone started going less (0) or more (1): each term's recent value minus its usual, on the log-odds
        scale; the usual is the base, so the factors add up to the recent chance of going."""
        sim = self.sim
        P = sim.w.P
        F, usual = {}, np.full(len(ids), sim.p("faith.attend.base"))
        for f in self.ATT_TERMS:
            fast, slow = P.internal[f"att_fast_{f}"][ids], P.internal[f"att_slow_{f}"][ids]
            F[f] = fast - slow
            usual = usual + slow
        day = sim.w.day
        plans = sim.systems.get("plans")
        refs = {"crisis": ("event", latest_event(sim, ids, ("faith_crisis_start", "faith_renewed", "faith_nuanced"), day - 200)),
                "coping": ("event", np.where(P["coping_strategy"][ids] > 0, P.internal["cope_event"][ids], -1)),
                "sunday_work": ("event", latest_event(sim, ids, ("job_found", "job_lost", "quit_job"), day - 120)),
                "norm": ("event", latest_event(sim, ids, ("moved", "arrival"), day - 120)),
                "belief": ("event", latest_event(sim, ids, ("faith_challenge", "spiritual_experience"), day - 120)),
                "stress": ("state", state_ref(sim, "stress", ids)), "fatigue": ("state", state_ref(sim, "fatigue", ids))}
        if plans is not None:
            refs["intention"] = ("event", plans.formed_event(ids, "return_to_church"))
        p_now = ap[ids] if outcome else 1 - ap[ids]
        return sim.decisions.record("church_attendance", day, ids, outcome, F, base=usual, prob=p_now, refs=refs)

    def _why_crisis(self, ev: np.ndarray, ids: np.ndarray, guilt_weeks: np.ndarray, belief: np.ndarray):
        """A faith crisis begins when certainty has fallen below a threshold (then a weekly chance). What wore it
        down: the latest challenge to their faith, how unsure they were, friends who believe differently, and guilt
        over living against their standards (dissonance)."""
        sim, P, p = self.sim, self.sim.w.P, self.sim.p
        day = sim.w.day
        link(sim, ev, "event", latest_event(sim, ids, ("faith_challenge",), day - 365), 0.8, "challenge")
        thr = p("faith.crisis.certainty_threshold")
        link(sim, ev, "state", state_ref(sim, "faith_certainty", ids), np.clip((thr - P["faith_certainty"][ids]) / max(thr, 1e-6), 0.05, 1),
             "certainty")
        gap = np.abs(np.asarray(self.friend_belief)[ids] - belief)
        m = gap > 0.1
        link(sim, ev[m], "state", state_ref(sim, "perceived_friend_belief", ids[m]), np.clip(gap[m], 0, 1), "friends_differ")
        m = guilt_weeks >= 4
        link(sim, ev[m], "state", state_ref(sim, "guilt", ids[m]), P["guilt"][ids][m], "dissonance")
        link(sim, ev[m], "event", latest_event(sim, ids[m], ("premarital_sex", "started_coffee", "started_drinking"), day - 365),
             0.5, "dissonance")

    def _record_options(self, kind: str, ids: np.ndarray, choice: np.ndarray, O: list[dict], U: np.ndarray) -> np.ndarray:
        """Record a choice among options: the chosen option's terms ("_base" = its constant) and its softmax
        probability (Gumbel-max choice)."""
        sim = self.sim
        k = len(ids)
        names = sorted({f for o in O for f in o if f != "_base"})
        F = {f: np.zeros(k) for f in names}
        base = np.zeros(k)
        for j, o in enumerate(O):
            sel = choice == j
            for f, v in o.items():
                vv = np.broadcast_to(np.asarray(v, np.float64), (k,))[sel]
                if f == "_base":
                    base[sel] = vv
                else:
                    F[f][sel] = vv
        return sim.decisions.record(kind, sim.w.day, ids, choice, F, base=base, prob=softmax_prob(U, choice))

    def _last_event(self, ids: np.ndarray, etype: str) -> np.ndarray:
        log = self.sim.log
        code = self.sim.reg.event_ids[etype]
        m = log["type"] == code
        ev_ids = np.where(m)[0]
        agents = log["a"][m]
        out = np.full(len(ids), -1, np.int64)
        if len(ev_ids):
            last = {}
            for e, a in zip(ev_ids, agents):
                last[int(a)] = int(e)
            out = np.array([last.get(int(i), -1) for i in ids], dtype=np.int64)
        return out
