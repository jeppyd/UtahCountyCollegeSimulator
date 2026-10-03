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
        mask = P.internal["shift_mask"][: P.n] if "shift_mask" in P.internal else np.zeros(P.n, np.uint32)
        P.internal["works_sunday"][: P.n] = (mask & np.uint32(1 << 18)) > 0
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
        P["perceived_norm"] = norm.astype(np.float32)
        self.friend_belief = np.where(has, np.nan_to_num(friend_belief), P["faith_belief"])
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
        # ---- attendance probability for next Sunday
        ap = expit(p("faith.attend.base") + p("faith.attend.belief") * (belief - 0.6) + p("faith.attend.identity") * (ident - 0.5)
                   + p("faith.attend.habit") * (P["practice_habit"] - 0.5) + p("faith.attend.norm") * (P["perceived_norm"] - 0.5)
                   + p("faith.attend.family") * P["family_expectation"] - p("faith.attend.stress") * np.clip(P["stress"] - 0.3, 0, None)
                   - 0.8 * P["fatigue"] - 2.0 * P.internal["works_sunday"][:n] + np.log(w.env["church_attendance_norm"] + 1e-9)
                   - 1.0 * P["faith_crisis"])
        P.internal["attend_prob"][:n] = np.where(lds, ap, 0)
        # ---- events: spiritual experiences & faith challenges
        u1, u2 = sim.u("spirit"), sim.u("challenge")
        h_sp = p("faith.spiritual.rate") * (0.3 + P["private_practice"] + 0.5 * P["attend_rate"]) * belief
        sp = lds & (u1 < h_sp)
        h_ch = p("faith.challenge.rate") * np.exp(0.35 * sim.z("openness") + 0.15 * np.log1p(P["social_media_hours"])
                                                   + 0.8 * P["history_struggle"] / 4 + 1.2 * P["lgbtq_tension"]
                                                   - 0.8 * (cert - 0.6))
        ch = lds & (u2 < h_ch)
        if sp.any():
            sim.emit("spiritual_experience", np.where(sp)[0], mech="faith.spiritual")
        if ch.any():
            sim.emit("faith_challenge", np.where(ch)[0], mech="faith.challenge")
        # ---- belief update
        susc = p("faith.influence.base") * (1 - cert) * np.exp(0.3 * sim.z("conformity"))
        d_social = susc * (self.friend_belief - belief)
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
        # ---- faith crisis onset & resolution
        crisis = P["faith_crisis"]
        on = lds & ~crisis & (P["faith_certainty"] < p("faith.crisis.certainty_threshold")) & (sim.u("crisis_on") < p("faith.crisis.onset_rate"))
        if on.any():
            ids = np.where(on)[0]
            P.cols["faith_crisis"][ids] = True
            P.internal["crisis_start"][ids] = day
            P.cols["struggled_faith"][ids] = True
            sim.emit("faith_crisis_start", ids, mech="faith.crisis")
        dur = day - P.internal["crisis_start"][:n]
        res = lds & crisis & (dur > 60) & (sim.u("crisis_res") < p("faith.crisis.resolution_rate"))
        if res.any():
            ids = np.where(res)[0]
            fam = P["family_expectation"][ids]
            u_renew = 1.5 * ident[ids] + 1.0 * P["perceived_norm"][ids] + 0.8 * fam + 0.8 * P["institutional_trust"][ids]
            u_nuance = 0.8 + 1.0 * ident[ids] + 0.6 * P["moral_autonomy"][ids]
            u_leave = (p("faith.crisis.leave_bias") + 1.4 * (1 - P["faith_belief"][ids]) + 1.0 * P["moral_autonomy"][ids]
                       + 1.5 * P["lgbtq_tension"][ids] + 0.8 * (1 - P["perceived_norm"][ids]) - 1.0 * fam)
            g = sim.streams.gen("crisis_outcome", day).gumbel(size=(len(ids), 3))
            outcome = np.argmax(np.c_[u_renew, u_nuance, u_leave] + g, axis=1)
            cause = self._last_event(ids, "faith_crisis_start")
            P.cols["faith_crisis"][ids] = False
            r = ids[outcome == 0]
            if len(r):
                P.cols["faith_belief"][r] = np.clip(P["faith_belief"][r] + 0.15, 0, 0.99)
                P.cols["faith_certainty"][r] = np.clip(P["faith_certainty"][r] + 0.3, 0, 0.95)
                sim.emit("faith_renewed", r, cause=cause[outcome == 0], mech="faith.crisis")
            nu = ids[outcome == 1]
            if len(nu):
                P.cols["faith_certainty"][nu] = 0.5
                P.cols["orthodoxy"][nu] = np.clip(P["orthodoxy"][nu] - 0.12, 0, 1)
                P.cols["moral_autonomy"][nu] = np.clip(P["moral_autonomy"][nu] + 0.1, 0, 1)
                sim.emit("faith_nuanced", nu, cause=cause[outcome == 1], mech="faith.crisis")
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
                sim.emit("disaffiliated", lv, cause=cause[outcome == 2], mech="faith.crisis")
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
            sim.emit("stopped_attending", np.where(stopped)[0], mech="faith.attend")
        if back.any():
            sim.emit("returned_to_activity", np.where(back)[0], mech="faith.attend")
        # temple recommend gained/lost
        clean = (P["coffee"] == 0) & (P["alcohol"] == 0) & ~P["premarital_sex_current"]
        eligible = P["lds_member"] & (P["activity"] == 3) & (P["faith_belief"] > 0.6) & clean & (P["age"] >= 18)
        gain = eligible & ~P["temple_recommend"] & (sim.u("tr") < 0.03)
        lose = P["temple_recommend"] & (~clean | (P["activity"] < 3)) & (sim.u("tr2") < 0.2)
        P.cols["temple_recommend"][np.where(gain)[0]] = True
        P.cols["temple_recommend"][np.where(lose)[0]] = False
        self.practices(np.where(P["present"])[0])
        self.weekly_other()

    # ------------------------------------------------------------------ non-members
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
            sim.emit("joined_congregation", np.array(joined), mech="faith.other_attend")

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
            sim.emit("met_missionaries", ids, mech="faith.missionary_contact")
        # ---- lessons: baptism or stopping
        inv = P["investigating"] & pres & ~P["lds_member"]
        if inv.any():
            dating_lds = lds_partner & P.isin("rel_status", ["dating", "engaged", "married"])
            hb = expit(p("faith.conversion.base") + 2.0 * dating_lds + 1.5 * share - 2.0 * P["own_religiosity"])
            weeks = (day - P.internal["investigate_start"][:n]) / 7
            bap = inv & (weeks >= 3) & (sim.u("baptism") < hb)
            stop = inv & ~bap & (sim.u("stop_lessons") < 0.08)
            if bap.any():
                self.baptize(np.where(bap)[0])
            if stop.any():
                ids = np.where(stop)[0]
                P.cols["investigating"][ids] = False
                sim.emit("stopped_investigating", ids, mech="faith.missionary_contact")

    def baptize(self, ids: np.ndarray):
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
        sim.emit("baptized", ids, cause=cause, mech="faith.conversion")

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
