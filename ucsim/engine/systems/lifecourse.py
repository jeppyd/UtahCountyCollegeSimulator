"""Life course: aging, cohorts, missions, summer exodus, graduation/departure, fertility, life events."""
from __future__ import annotations

import numpy as np
from scipy.special import expit

from ..provenance import chance, latest_event, link, place_ref, state_ref
from ..state import CTX_ID, Tie

from ...population.synth import Synthesizer


class LifeCourse:
    def __init__(self, sim):
        self.sim = sim

    def init(self):
        sim, w = self.sim, self.sim.w
        P = w.P
        for c, dt, f in (("arrive_day", np.int32, -1), ("depart_day_planned", np.int32, -1),
                         ("mission_return_day", np.int32, -1), ("mission_early", np.bool_, False),
                         ("summer_return", np.int32, -1), ("leave_day", np.int32, -1), ("newborn_until", np.int32, -1),
                         ("prev_role", np.uint8, 0),
                         # provenance: the events and decisions behind what is scheduled (bookkeeping only)
                         ("mission_call_ev", np.int64, -1), ("mission_dep_ev", np.int64, -1), ("leave_cause", np.int64, -1),
                         ("pregnancy_ev", np.int64, -1)):
            P.add_internal(c, dt, f)
        P["birth_day"] = (-(P["age"] * 365.25)).astype(np.int32)
        self._serving_pool()
        # the starting non-student young adults are part-way through their stay (exponential: memoryless)
        ya = np.where(P.is_("role", "young_adult") & P["present"] & (P.internal["leave_day"][: P.n] < 0))[0]
        self.schedule_stay(ya)

    def schedule_stay(self, ids: np.ndarray):
        """Non-students (graduates who stay, dropouts, young adults) leave after an exponential stay."""
        sim, w = self.sim, self.sim.w
        P = w.P
        ids = ids[P.internal["leave_day"][ids] < 0]
        if len(ids) == 0:
            return
        mean_days = 365.25 * sim.p("lifecourse.stay.young_adult_years")
        u = np.clip(sim.u("stay_len")[ids], 1e-6, 1 - 1e-6)
        P.internal["leave_day"][ids] = w.day + 30 + (-np.log(u) * mean_days).astype(int)

    # ------------------------------------------------------------------ cohorts
    def _synth(self, tag: int) -> Synthesizer:
        w = self.sim.w
        return Synthesizer(w.reg, w.scale, seed=w.seed * 1000 + tag)

    def _new_people(self, role, n, school, extra, arrive_days):
        sim, w = self.sim, self.sim.w
        P = w.P
        if n <= 0:
            return np.empty(0, np.int64)
        sy = self._synth(int(w.day) * 10 + {"byu_student": 1, "uvu_student": 2}.get(role, 3) + int(extra.get("_tag", 0)))
        extra = {k: v for k, v in extra.items() if k != "_tag"}
        ids = sy.people(P, role, n, school, extra=extra)
        if "temple_pref" in P.internal:
            sim.systems["faith"].init_practices(ids)
        if "work_pref" in P.internal:
            sim.systems["economy"].assign_scholarships(ids)
        P.cols["present"][ids] = False
        P.internal["arrive_day"][ids] = arrive_days
        P.cols["arrival_day"][ids] = arrive_days
        P.cols["birth_day"][ids] = (w.day - P["age"][ids] * 365.25).astype(np.int32)
        P.cols["unit_id"][ids] = -1
        P.cols["ward_id"][ids] = -1
        P.cols["partner_id"][ids] = -1
        P.internal["fhe_group"][ids] = -1
        P.cols["mood"][ids] = 0.55
        P.cols["ward_belonging"][ids] = 0.45
        P.cols["close_contact_hours"][ids] = 4.0
        P.cols["social_hours_week"][ids] = 8.0
        P.internal["sleep_base"][ids] = P["sleep_hours"][ids]
        P.internal["attend_prob"][ids] = P["attend_rate"][ids]
        P.internal["last_date_day"][ids] = w.day - 30
        if role != "spouse":
            self._spouses_for(ids)
        return ids

    def _spouses_for(self, ids):
        """Married newcomers arrive with their spouse (a non-student "spouse" agent), as in the starting world."""
        sim, w = self.sim, self.sim.w
        P, E = w.P, w.E
        mar = ids[P.is_("rel_status", "married")[ids] & (P["partner_id"][ids] < 0)]
        if len(mar) == 0:
            return
        rng = np.random.default_rng([w.seed, 503, w.day, int(mar[0])])
        k = len(mar)
        male = P.is_("sex", "M")[mar]
        gay = P["orientation"][mar] == P.code("orientation", "gay")
        sp_male = np.where(gay, male, ~male)
        sp_age = np.clip(P["age"][mar] + np.where(sp_male, 1.2, -1.2) + rng.normal(0, 1.5, k), 18.5, 45)
        act = np.maximum(P["activity"][mar].astype(int) - 1, 0)
        spouses = self._new_people("spouse", k, "none", {
            "sex": np.where(sp_male, "M", "F"), "age": sp_age, "rel": np.full(k, "married"),
            "lds": (P["lds_member"][mar] & (rng.random(k) < 0.96)).astype(int), "activity": act},
            arrive_days=P.internal["arrive_day"][mar])
        P.cols["enrolled"][spouses] = False
        P.cols["class_standing"][spouses] = 0
        P.cols["partner_id"][mar], P.cols["partner_id"][spouses] = spouses, mar
        wed = w.day - (rng.uniform(1, 30, k) * 30.4).astype(int)
        start = wed - (rng.uniform(7, 14, k) * 30.4).astype(int)
        for x in (mar, spouses):
            P.cols["married_day"][x] = wed
            P.cols["rel_start_day"][x] = start
            P.cols["engaged_day"][x] = wed - (rng.uniform(2, 5, k) * 30.4).astype(int)
            P.cols["age_at_marriage"][x] = P["age"][x] - (w.day - wed) / 365.25
        keys = E.make_keys(mar, spouses)
        idx = E.upsert(keys)
        E.cols["flags"][idx] |= np.uint32(Tie.SPOUSE | Tie.ROMANTIC | Tie.DATED | Tie.KISSED | Tie.PREEXISTING)
        E.cols["stage"][idx] = 4
        for col, mu in (("liking", 0.75), ("closeness", 0.8), ("trust", 0.75), ("att_lh", 0.7), ("att_hl", 0.7)):
            E.cols[col][idx] = np.clip(rng.normal(mu, 0.1, k), 0, 1)
        E.cols["origin_ctx"][idx] = CTX_ID["preexisting"]
        E.cols["first_day"][idx] = start
        E.cols["last_day"][idx] = w.day

    def _serving_pool(self):
        """Missionaries from this ecosystem who are serving when the run starts.

        Sized to the flow equilibrium of the call hazard (config `mission.serving_pool`, see
        scripts/accounting.py): a pool smaller than calls/yr × mean service made the serving stock
        double over the first two years. Return days are spread uniformly over the service length."""
        sim, w = self.sim, self.sim.w
        P = w.P
        cfg = w.cfg
        mcfg = cfg["mission"]
        total = mcfg.get("serving_pool", cfg["flows"]["byu_rm_returners"] * 0.55 * 2)
        mix = mcfg.get("serving_pool_school_mix", {"BYU": 1.0})
        rng = np.random.default_rng([w.seed, 501])
        for k, (school, share) in enumerate(mix.items()):
            n = int(round(total * share * w.scale))
            if n <= 0:
                continue
            role = {"BYU": "byu_student", "UVU": "uvu_student"}.get(school, "young_adult")
            men = rng.random(n) < mcfg.get("serving_pool_male_share", 0.68)
            sex = np.where(men, "M", "F")
            age = np.where(men, rng.uniform(18.6, 20.6, n), rng.uniform(19.2, 21.0, n))
            ids = self._new_people(role, n, school, {"sex": sex, "age": age, "rel": np.full(n, "single"),
                                                     "lds": np.ones(n, int), "activity": np.full(n, 2), "_tag": 5 + k},
                                   arrive_days=np.full(n, -1))
            P.cols["mission_status"][ids] = P.code("mission_status", "serving")
            months = np.where(men, mcfg["male_months"], mcfg["female_months"])
            ret = (rng.uniform(0, 1, n) * months * 30.4).astype(int) + 1
            P.internal["mission_return_day"][ids] = ret
            if role != "young_adult":
                P.cols["class_standing"][ids] = np.where(rng.random(n) < 0.6, P.code("class_standing", "freshman"), P.code("class_standing", "sophomore"))
                P.cols["credits_done"][ids] = np.where(P["class_standing"][ids] == P.code("class_standing", "freshman"), rng.uniform(0, 28, n), rng.uniform(30, 55, n))
            P.cols["enrolled"][ids] = False
            P.cols["n_kissed"][ids] = np.minimum(P["n_kissed"][ids], rng.integers(0, 4, n))

    def _annual_cohort(self):
        sim, w = self.sim, self.sim.w
        P = w.P
        cfg = w.cfg["flows"]
        s = w.scale * w.env.get("enrollment_index", 1.0)
        rng = np.random.default_rng([w.seed, 502, w.day])
        # Admissions: BYU's enrollment is capped by its board, so the incoming class fills the gap to the
        # target; UVU (open enrollment) closes only half of any gap. Keeps multi-year runs at realistic size.
        pop = w.cfg["population"]
        # new graduate students and older transfers (mostly married, arriving with spouses)
        ng = int(round(cfg.get("byu_grad_and_transfer", 0) * s))
        if ng:
            grad = rng.random(ng) < 0.7
            ids_g = self._new_people("byu_student", ng, "BYU", {
                "age": np.where(grad, rng.uniform(23, 30, ng), rng.uniform(21, 25, ng)),
                "rel": np.where(rng.random(ng) < np.where(grad, 0.65, 0.45), "married", "single"),
                "lds": (rng.random(ng) < 0.97).astype(int), "activity": np.full(ng, 2), "_tag": 4},
                arrive_days=w.day + rng.integers(0, 4, ng))
            P.cols["class_standing"][ids_g] = np.where(grad[: len(ids_g)], P.code("class_standing", "graduate"), P.code("class_standing", "junior"))
            P.cols["credits_done"][ids_g] = np.where(grad[: len(ids_g)], 0, rng.uniform(60, 89, len(ids_g)))
            P.cols["mission_status"][ids_g] = np.where(P.is_("sex", "M")[ids_g] & (rng.random(len(ids_g)) < 0.75),
                                                       P.code("mission_status", "returned"), P["mission_status"][ids_g])
        nb = self._intake("BYU", cfg["byu_freshmen"] * s, pop["byu"]["students"] * s, 1.0)
        nu = self._intake("UVU", cfg["uvu_new_students"] * s, pop["uvu"]["students"] * s, 0.5)
        women = rng.random(nb) < 0.5
        rm_men = ~women & (rng.random(nb) < 0.32)
        age = np.where(women, rng.uniform(17.9, 18.9, nb), np.where(rm_men, rng.uniform(20.5, 21.5, nb), rng.uniform(17.9, 18.9, nb)))
        ids = self._new_people("byu_student", nb, "BYU",
                               {"sex": np.where(women, "F", "M"), "age": age, "rel": np.full(nb, "single"), "_tag": 1},
                               arrive_days=w.day + rng.integers(0, 4, nb))
        P.cols["class_standing"][ids] = P.code("class_standing", "freshman")
        P.cols["credits_done"][ids] = 0
        P.cols["mission_status"][ids] = np.where(rm_men[: len(ids)], P.code("mission_status", "returned"), P.code("mission_status", "none"))
        P.cols["n_kissed"][ids] = np.minimum(P["n_kissed"][ids], rng.integers(0, 6, len(ids)))
        P.cols["n_sex_partners"][ids] = np.where(rng.random(len(ids)) < 0.9, 0, P["n_sex_partners"][ids])
        ids2 = self._new_people("uvu_student", nu, "UVU", {"age": rng.uniform(17.9, 22, nu), "_tag": 2},
                                arrive_days=w.day + rng.integers(0, 4, nu))
        P.cols["class_standing"][ids2] = P.code("class_standing", "freshman")
        P.cols["credits_done"][ids2] = 0
        # external RMs (served from elsewhere) arriving through the year
        nr = int(round(cfg["byu_rm_returners"] * w.scale * 0.45))
        men = rng.random(nr) < 0.68
        ids3 = self._new_people("byu_student", nr, "BYU",
                                {"sex": np.where(men, "M", "F"), "age": np.where(men, rng.uniform(20.4, 21.6, nr), rng.uniform(20.8, 21.8, nr)),
                                 "rel": np.full(nr, "single"), "lds": np.ones(nr, int), "activity": np.full(nr, 2), "_tag": 3},
                                arrive_days=w.day + rng.integers(0, 365, nr))
        P.cols["mission_status"][ids3] = P.code("mission_status", "returned")
        P.cols["class_standing"][ids3] = P.code("class_standing", "freshman")
        P.cols["credits_done"][ids3] = rng.uniform(0, 30, nr)
        sim.systems["activity"].assign_shifts(np.r_[ids, ids2, ids3])

    def _intake(self, school: str, base: float, target: float, gain: float) -> int:
        """Size of this fall's new class: the configured flow, adjusted toward the enrollment target."""
        w = self.sim.w
        P, day = w.P, w.day
        n = P.n
        role = P.code("role", "byu_student" if school == "BYU" else "uvu_student")
        mine = (P["role"] == role) & (P["school"] == P.code("school", school)) & ~P["graduated"] & (P["departure_day"] < 0)
        serving = P.is_("mission_status", "serving")
        # project the fall census (late October, ~65 days after intake): continuing students, missionaries
        # home by then and returned missionaries scheduled to arrive by then. A longer horizon over-counted
        # people who arrive after the census; a shorter one let year-round mission returns push BYU past its cap.
        horizon = day + 65
        back_by_fall = serving & (P.internal["mission_return_day"][:n] <= horizon)
        arriving = ~P["present"] & (P.internal["arrive_day"][:n] >= day) & (P.internal["arrive_day"][:n] <= horizon)
        # students away for the summer come back around the intake day; they are continuing students
        summer = ~P["present"] & P.internal["summer_away"][:n] & (P.internal["summer_return"][:n] >= 0) & \
            (P.internal["summer_return"][:n] <= horizon)
        continuing = int((mine & ((P["present"] & ~serving) | back_by_fall | (arriving & ~serving) | summer)).sum())
        want = base + gain * (target - continuing - base)
        return int(round(np.clip(want, 0.5 * base, 2.0 * base)))

    def _arrive(self, ids, event="arrival", cause=None, decision=None):
        sim, w = self.sim, self.sim.w
        P = w.P
        if len(ids) == 0:
            return
        P.cols["present"][ids] = True
        need_home = ids[P["unit_id"][ids] < 0]
        if len(need_home):
            # married couples arriving together share a home; everyone else finds a bed
            partner = P["partner_id"][need_home]
            together = P.is_("rel_status", "married")[need_home] & (partner >= 0) & np.isin(partner, need_home)
            for a in need_home[together & (need_home < np.where(partner >= 0, partner, -1))]:
                sim.systems["housing"].place(np.array([a, P["partner_id"][a]]), married=True, reason="")
            if (~together).any():
                sim.systems["housing"].place(need_home[~together], reason="")
        self._fhe_for(ids)
        mind = sim.systems.get("mind")
        if mind is not None and "mind_ready" in P.internal:   # an inner life from day one (cares, expectations)
            fresh = ids[~P.internal["mind_ready"][ids]]
            if len(fresh):
                mind.setup(fresh)
        if cause is None and event != "arrival":
            cause = P.internal["mission_dep_ev"][ids]
        ev = sim.emit(event, ids, cause=cause, mech="lifecourse.arrival", decision=decision)
        if event == "arrival":
            # why they came: to study (this fall's intake at BYU or UVU), or with a spouse who did
            student = P.isin("role", ["byu_student", "uvu_student"])[ids]
            link(sim, ev[student], "place", place_ref(CTX_ID["campus"], P["school"][ids][student]), 1.0, "came_to_study")
            spouse = P.is_("role", "spouse")[ids]
            link(sim, ev[spouse], "person", P["partner_id"][ids][spouse], 1.0, "moved_with")

    def _fhe_for(self, ids):
        """Newcomers join the FHE group of someone in their unit/complex if one exists."""
        w = self.sim.w
        P = w.P
        fhe = P.internal["fhe_group"]
        cx = P["complex_id"]
        for i in ids:
            if P["ward_id"][i] < 0:
                continue
            mates = np.where((P["unit_id"] == P["unit_id"][i]) & (fhe[: P.n] >= 0))[0]
            if len(mates) == 0:
                mates = np.where((cx == cx[i]) & (cx[i] >= 0) & (fhe[: P.n] >= 0) & (P["ward_id"] == P["ward_id"][i]))[0]
            if len(mates):
                fhe[i] = fhe[mates[0]]

    # ------------------------------------------------------------------ daily
    def daily(self):
        sim, w = self.sim, self.sim.w
        P, cal = w.P, sim.cal
        day = w.day
        n = P.n
        P["age"] = ((day - P["birth_day"]) / 365.25).astype(np.float32)
        d = cal.date(day)
        if d.month == 8 and d.day == 20 and day > 0:
            self._annual_cohort()
            n = P.n
        arrive = np.where(~P["present"] & (P.internal["arrive_day"][:n] == day) & (P["departure_day"] < 0))[0]
        arrive = arrive[P["mission_status"][arrive] != P.code("mission_status", "serving")]
        if len(arrive):
            self._arrive(arrive)
        # mission returns
        ret = np.where((P.internal["mission_return_day"][:n] == day) & P.is_("mission_status", "serving"))[0]
        if len(ret):
            early = P.internal["mission_early"][ret]
            P.cols["mission_status"][ret] = np.where(early, P.code("mission_status", "early_returned"), P.code("mission_status", "returned"))
            P.cols["languages"][ret] = np.where(P["mission_foreign"][ret], np.minimum(P["languages"][ret] + 1, 6), P["languages"][ret])
            P.cols["role"][ret] = np.where(P["role"][ret] == P.code("role", "young_adult"), P.code("role", "byu_student"), P["role"][ret])
            P.cols["rejections_recent"][ret] = 0
            P.internal["last_date_day"][ret] = day - 400
            for idx, ev in ((ret[~early], "mission_return"), (ret[early], "early_return")):
                if len(idx):
                    # coming home early (or not) is a flat share of missionaries in the model: the honest reason is
                    # chance; the mission's own start is the parent when it happened within the story
                    rate = w.cfg["mission"]["early_return_rate"]
                    did = chance(sim, "mission_length", idx, rate if ev == "early_return" else 1 - rate,
                                 "early" if ev == "early_return" else "full")
                    self._arrive(idx, event=ev, decision=did)
            wait = np.where(P["waiting_for_missionary"])[0]
            for x in wait:
                if P["partner_id"][x] >= 0 and P["partner_id"][x] in set(ret.tolist()):
                    P.cols["waiting_for_missionary"][x] = False
        # mission departures (scheduled at call)
        dep = np.where((P.internal["depart_day_planned"][:n] == day) & P["present"])[0]
        if len(dep):
            self._depart_mission(dep)
        # leaving the area
        leave = np.where((P.internal["leave_day"][:n] == day) & P["present"])[0]
        if len(leave):
            self._leave(leave)
        # summer exodus / return (BYU singles, some UVU)
        if cal.date(day - 1) and cal.term_end("BYU", day - 1) == "Winter":
            self._summer_exodus()
        back = np.where(~P["present"] & (P.internal["summer_return"][:n] == day))[0]
        if len(back):
            P.cols["present"][back] = True
            P.internal["summer_return"][back] = -1
            P.internal["summer_away"][back] = False
        # illness
        u = sim.u("illness")
        sick = P["present"] & ~P["ill"] & (u < sim.p("lifecourse.illness.rate"))
        if sick.any():
            ids = np.where(sick)[0]
            P.cols["ill"][ids] = True
            P.cols["ill_until"][ids] = day + 2 + (sim.u("ill_len")[ids] * 5).astype(int)
            sim.emit("illness", ids, mech="lifecourse.illness",
                     decision=chance(sim, "life_risk", ids, sim.p("lifecourse.illness.rate")))
        well = P["ill"] & (P["ill_until"] <= day)
        P.cols["ill"][np.where(well)[0]] = False
        # births
        due = np.where(P["pregnant"] & (P["due_day"] == day))[0]
        if len(due):
            P.cols["pregnant"][due] = False
            P.cols["children"][due] = np.minimum(P["children"][due] + 1, 12)
            P.internal["newborn_until"][due] = day + 120
            mothers = due[P.is_("sex", "F")[due]]
            bev = sim.emit("birth", due, mech="lifecourse.fertility", cause=P.internal["pregnancy_ev"][due])
            dm = P["enrolled"][mothers] & (sim.u("birth_drop")[mothers] < 0.3)
            drop = mothers[dm]
            if len(drop):
                P.cols["enrolled"][drop] = False
                sim.emit("dropout", drop, mech="lifecourse.fertility", cause=bev[np.isin(due, mothers)][dm])

    def _summer_exodus(self):
        sim, w = self.sim, self.sim.w
        P = w.P
        n = P.n
        cand = P["present"] & (P["school"] == 1) & ~P.isin("rel_status", ["married", "engaged"]) & ~P["family_local"] & \
            P.isin("class_standing", ["freshman", "sophomore", "junior", "senior"])
        go = cand & (sim.u("summer") < 1 - w.cfg["calendar"]["spring_summer_presence"])
        ids = np.where(go)[0]
        if len(ids) == 0:
            return
        P.cols["present"][ids] = False
        P.internal["summer_away"][ids] = True
        from datetime import date
        d = sim.cal.date(w.day)
        fall = (date(d.year, 8, 20) - sim.cal.start).days
        P.internal["summer_return"][ids] = fall + (sim.u("summer_back")[ids] * 4).astype(int) - 2
        summer_sales = ids[P.is_("sex", "M")[ids] & (sim.u("sales")[ids] < 0.12)]
        P.cols["summer_sales"][summer_sales] = True
        del n

    def _depart_mission(self, ids):
        sim, w = self.sim, self.sim.w
        P, E = w.P, w.E
        day = w.day
        leavers, brk = sim.systems["romance"].handle_departure(ids)
        # close friends feel the absence
        lo, hi = E.endpoints()
        m = (E["stage"] >= 3)
        missed = []
        for x, y in ((lo, hi), (hi, lo)):
            sel = m & np.isin(x, ids) & P["present"][y]
            if sel.any():
                fe = sim.emit("friend_left_on_mission", y[sel], b=x[sel], mech="lifecourse.mission",
                              ev={"closeness": E["closeness"][sel]})
                missed.append((fe, x[sel]))
        ev = sim.emit("mission_departure", ids, mech="lifecourse.mission", cause=P.internal["mission_call_ev"][ids])
        P.internal["mission_dep_ev"][ids] = ev
        # the friends' loss and any breakup point at this departure (logged just before it, on the same day)
        self._link_to(brk, leavers, ids, ev, "left")
        for fe, who in missed:
            self._link_to(fe, who, ids, ev, "friend_left")
        P.cols["present"][ids] = False
        P.cols["enrolled"][ids] = False
        P.cols["mission_status"][ids] = P.code("mission_status", "serving")
        months = np.where(P.is_("sex", "M")[ids], w.cfg["mission"]["male_months"], w.cfg["mission"]["female_months"])
        early = sim.u("early_return")[ids] < w.cfg["mission"]["early_return_rate"]
        length = np.where(early, (30 + sim.u("early_len")[ids] * 300).astype(int), (months * 30.4).astype(int))
        P.internal["mission_return_day"][ids] = day + length
        P.internal["mission_early"][ids] = early
        P.cols["mission_foreign"][ids] = sim.u("foreign")[ids] < 0.45
        housing = sim.systems["housing"]
        for i in ids:
            u = P["unit_id"][i]
            if u >= 0:
                housing.occ[u] -= 1
            P.cols["unit_id"][i] = -1

    def _link_to(self, events, people, ids, dep_ev, role_name: str):
        """Typed causes: each event (about `people`) points at the departure event of that person (ids ↔ dep_ev)."""
        events = np.asarray(events, np.int64)
        if not len(events):
            return
        o = np.argsort(ids)
        k = np.clip(np.searchsorted(ids[o], people), 0, len(ids) - 1)
        hit = ids[o][k] == people
        link(self.sim, events[hit], "event", dep_ev[o][k[hit]], 1.0, role_name)

    def _leave(self, ids):
        sim, w = self.sim, self.sim.w
        P = w.P
        # married couples move together: wait while the spouse is still enrolled, otherwise take them along
        part = P["partner_id"][ids]
        married = P.is_("rel_status", "married")[ids] & (part >= 0)
        sp = np.where(married, part, 0)
        wait = married & P["present"][sp] & P["enrolled"][sp] & ~P["enrolled"][ids]
        if wait.any():
            P.internal["leave_day"][ids[wait]] = w.day + 120
            ids = ids[~wait]
            married, sp = married[~wait], sp[~wait]
        along = sp[married & P["present"][sp]]
        along = along[~np.isin(along, ids)]
        n_own = len(ids)
        if len(along):
            P.internal["leave_day"][along] = -1
            ids = np.r_[ids, along]
        if len(ids) == 0:
            return
        leavers, brk = sim.systems["romance"].handle_departure(ids)
        housing = sim.systems["housing"]
        for i in ids:
            u = P["unit_id"][i]
            if u >= 0:
                housing.occ[u] -= 1
            P.cols["unit_id"][i] = -1
        P.cols["present"][ids] = False
        P.cols["departure_day"][ids] = w.day
        # why now: graduates decided at graduation (the share who move on), spouses go along, and everyone else's
        # stay simply ran its course (an exponential stay of a few years: the day itself is chance)
        own = ids[:n_own]
        grad = P.internal["leave_cause"][own]
        g = grad >= 0
        # a spouse leaving with a graduate carries the graduate's graduation as the cause
        g[g] &= sim.log["a"][grad[g]] == own[g]
        followers = (grad >= 0) & ~g
        did = np.full(len(ids), -1, np.int64)
        if g.any():
            gi = own[g]
            base = np.where(P["school"][gi] == 1, 0.62, 0.42)
            fam = -0.25 * P["family_local"][gi]
            did[np.flatnonzero(g)] = sim.decisions.record("leave_after_graduating", w.day, gi, "leaves",
                                                          {"family_local": fam}, base=base, prob=base + fam)
        stay = ~g & ~followers
        if stay.any():
            did[np.flatnonzero(stay)] = chance(sim, "end_of_stay", own[stay],
                                               1.0 / (365.25 * sim.p("lifecourse.stay.young_adult_years")), "left")
        cause = np.r_[grad, np.full(len(ids) - n_own, -1, np.int64)]
        ev = sim.emit("left_area", ids, mech="lifecourse.departure", cause=np.where(cause >= 0, cause, -1),
                      decision=np.where(did >= 0, did, -1))
        if len(ids) > n_own:
            link(sim, ev[n_own:], "person", P["partner_id"][ids[n_own:]], 1.0, "moved_with")
        link(sim, ev[:n_own][followers], "person", P["partner_id"][own[followers]], 1.0, "moved_with")
        self._link_to(brk, leavers, ids, ev, "left")

    def after_graduation(self, ids, events):
        sim, w = self.sim, self.sim.w
        P = w.P
        p_leave = np.where(P["school"][ids] == 1, 0.62, 0.42)
        p_leave = p_leave - 0.25 * P["family_local"][ids]
        leave = sim.u("grad_leave")[ids] < p_leave
        lv = ids[leave]
        P.internal["leave_day"][lv] = w.day + 20 + (sim.u("grad_leave_d")[lv] * 70).astype(int)
        P.internal["leave_cause"][lv] = np.broadcast_to(np.asarray(events, np.int64), (len(ids),))[leave]
        # spouses leave with them
        sp = P["partner_id"][lv]
        has = sp >= 0
        sp = sp[has]
        P.internal["leave_day"][sp] = np.maximum(P.internal["leave_day"][sp], w.day + 25)
        P.internal["leave_cause"][sp] = P.internal["leave_cause"][lv[has]]
        stay = ids[~leave]
        P.cols["role"][stay] = P.code("role", "young_adult")
        self.schedule_stay(stay)

    # ------------------------------------------------------------------ monthly
    def monthly(self):
        sim, w = self.sim, self.sim.w
        P, p, env = w.P, sim.p, w.env
        n = P.n
        day = w.day
        age = P["age"]
        male = P.is_("sex", "M")
        # ---- missions
        planned = P.internal["depart_day_planned"][:n] > day
        elig = (P["present"] & P["lds_member"] & P.is_("mission_status", "none") & ~planned &
                P.isin("rel_status", ["single", "talking", "dating"]) & (age >= np.where(male, 18.0, 19.0)) & (age < 25.5))
        age_peak = np.where(male, np.exp(-((age - 18.9) / 1.0) ** 2), np.exp(-((age - 20.0) / 1.5) ** 2))
        T = {"male": np.where(male, p("lifecourse.mission.male"), 0), "belief": p("lifecourse.mission.belief") * (P["faith_belief"] - 0.7),
             "active": 1.2 * (P["activity"] == 3), "family": p("lifecourse.mission.family") * P["family_expectation"],
             "identity": 0.8 * P["religious_identity"], "age": 2.0 * age_peak, "norm": np.log(env["mission_norm"] + 1e-9),
             "dating": 0.6 * P.is_("rel_status", "dating"),
             "too_old": 1.5 * np.maximum(age - np.where(male, 19.8, 21.5), 0)}  # those who haven't gone by then mostly won't
        h = expit(p("lifecourse.mission.base") + T["male"] + T["belief"] + T["active"] + T["family"] + T["identity"]
                  + T["age"] + T["norm"] - T["dating"] - T["too_old"])
        call = elig & (P["activity"] == 3) & (sim.u("mission_call") < h)
        if call.any():
            ids = np.where(call)[0]
            P.internal["depart_day_planned"][ids] = day + 75 + (sim.u("mtc")[ids] * 40).astype(int)
            rec = {k_: (v[ids] if np.ndim(v) else np.full(len(ids), v)) for k_, v in T.items()}
            rec["dating"], rec["too_old"] = -rec["dating"], -rec["too_old"]
            did = sim.decisions.record("mission_call", day, ids, "called", rec, base=p("lifecourse.mission.base"), prob=h[ids],
                                       refs={"belief": ("state", state_ref(sim, "faith_belief", ids))})
            P.internal["mission_call_ev"][ids] = sim.emit("mission_call", ids, mech="lifecourse.mission", decision=did)
        # ---- fertility
        fem = P.is_("sex", "F") & P.is_("rel_status", "married") & ~P["pregnant"] & (age < 43) & P["present"]
        mm = np.maximum((day - P["married_day"]) / 30.4, 0)
        recent_birth = P.internal["newborn_until"][:n] > day - 150
        TF = {"kids_wanted": 0.25 * (P["kids_wanted"] - 3), "children": 0.55 * P["children"], "marriage_length": 0.06 * np.minimum(mm, 24),
              "student": p("lifecourse.fertility.student") * P["enrolled"], "money": 0.8 * P["financial_stress"],
              "active": 0.5 * (P["activity"] == 3), "age": 0.08 * np.clip(age - 30, 0, None)}
        hf = expit(p("lifecourse.fertility.base") + TF["kids_wanted"] - TF["children"] + TF["marriage_length"] - TF["student"]
                   - TF["money"] + TF["active"] - TF["age"])
        conceive = fem & ~recent_birth & (sim.u("conceive") < hf)
        if conceive.any():
            ids = np.where(conceive)[0]
            due = day + 270
            P.cols["pregnant"][ids] = True
            P.cols["due_day"][ids] = due
            sp = P["partner_id"][ids]
            has = sp >= 0
            P.cols["pregnant"][sp[has]] = True
            P.cols["due_day"][sp[has]] = due
            rec = {k_: v[ids].astype(np.float64) for k_, v in TF.items()}
            for k_ in ("children", "student", "money", "age"):
                rec[k_] = -rec[k_]
            did = sim.decisions.record("conceive", day, ids, "pregnant", rec, base=p("lifecourse.fertility.base"), prob=hf[ids],
                                       other=np.where(has, sp, -1))
            ev = sim.emit("pregnancy", ids, mech="lifecourse.fertility", decision=did)
            P.internal["pregnancy_ev"][ids] = ev
            if has.any():
                ev2 = sim.emit("pregnancy", sp[has], mech="lifecourse.fertility", cause=ev[has])
                P.internal["pregnancy_ev"][sp[has]] = ev2
        # ---- other life events
        pres = P["present"]
        for etype, rate, mask in (("family_crisis", p("lifecourse.events.family_crisis"), pres),
                                  ("death_in_family", p("lifecourse.events.death"), pres),
                                  ("car_accident", p("lifecourse.events.car_accident"), pres & P["owns_car"])):
            hit = mask & (sim.u(etype) < rate)
            if hit.any():
                ids = np.where(hit)[0]
                sim.emit(etype, ids, mech="lifecourse.events", decision=chance(sim, "life_risk", ids, rate))
