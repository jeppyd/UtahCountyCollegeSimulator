"""Life course: aging, cohorts, missions, summer exodus, graduation/departure, fertility, life events."""
from __future__ import annotations

import numpy as np
from scipy.special import expit

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
                         ("prev_role", np.uint8, 0)):
            P.add_internal(c, dt, f)
        P["birth_day"] = (-(P["age"] * 365.25)).astype(np.int32)
        self._serving_pool()

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
        return ids

    def _serving_pool(self):
        """Missionaries currently serving who will return to BYU/UVU during the next two years."""
        sim, w = self.sim, self.sim.w
        P = w.P
        cfg = w.cfg
        n = int(round(cfg["flows"]["byu_rm_returners"] * w.scale * 0.55 * 2))
        if n <= 0:
            return
        rng = np.random.default_rng([w.seed, 501])
        men = rng.random(n) < 0.68
        sex = np.where(men, "M", "F")
        age = np.where(men, rng.uniform(18.6, 20.6, n), rng.uniform(19.2, 21.0, n))
        ids = self._new_people("byu_student", n, "BYU", {"sex": sex, "age": age, "rel": np.full(n, "single"),
                                                          "lds": np.ones(n, int), "activity": np.full(n, 2)},
                               arrive_days=np.full(n, -1))
        P.cols["mission_status"][ids] = P.code("mission_status", "serving")
        months = np.where(men, 24, 18)
        ret = (rng.uniform(0, 1, n) * months * 30.4).astype(int) + 1
        P.internal["mission_return_day"][ids] = ret
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
        nb = int(round(cfg["byu_freshmen"] * s))
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
        nu = int(round(cfg["uvu_new_students"] * s))
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

    def _arrive(self, ids, event="arrival", cause=None):
        sim, w = self.sim, self.sim.w
        P = w.P
        if len(ids) == 0:
            return
        P.cols["present"][ids] = True
        need_home = ids[P["unit_id"][ids] < 0]
        if len(need_home):
            sim.systems["housing"].place(need_home, reason="")
        self._fhe_for(ids)
        sim.emit(event, ids, cause=cause, mech="lifecourse.arrival")

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
                    self._arrive(idx, event=ev)
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
            sim.emit("illness", ids, mech="lifecourse.illness")
        well = P["ill"] & (P["ill_until"] <= day)
        P.cols["ill"][np.where(well)[0]] = False
        # births
        due = np.where(P["pregnant"] & (P["due_day"] == day))[0]
        if len(due):
            P.cols["pregnant"][due] = False
            P.cols["children"][due] = np.minimum(P["children"][due] + 1, 12)
            P.internal["newborn_until"][due] = day + 120
            mothers = due[P.is_("sex", "F")[due]]
            sim.emit("birth", due, mech="lifecourse.fertility")
            drop = mothers[P["enrolled"][mothers] & (sim.u("birth_drop")[mothers] < 0.3)]
            if len(drop):
                P.cols["enrolled"][drop] = False
                sim.emit("dropout", drop, mech="lifecourse.fertility")

    def _summer_exodus(self):
        sim, w = self.sim, self.sim.w
        P = w.P
        n = P.n
        cand = P["present"] & (P["school"] == 1) & ~P.is_("rel_status", "married") & ~P["family_local"] & \
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
        sim.systems["romance"].handle_departure(ids)
        # close friends feel the absence
        lo, hi = E.endpoints()
        m = (E["stage"] >= 3)
        for x, y in ((lo, hi), (hi, lo)):
            sel = m & np.isin(x, ids) & P["present"][y]
            if sel.any():
                sim.emit("friend_left_on_mission", y[sel], b=x[sel], mech="lifecourse.mission",
                         ev={"closeness": E["closeness"][sel]})
        ev = sim.emit("mission_departure", ids, mech="lifecourse.mission")
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
        del ev

    def _leave(self, ids):
        sim, w = self.sim, self.sim.w
        P = w.P
        sim.systems["romance"].handle_departure(ids)
        housing = sim.systems["housing"]
        for i in ids:
            u = P["unit_id"][i]
            if u >= 0:
                housing.occ[u] -= 1
            P.cols["unit_id"][i] = -1
        P.cols["present"][ids] = False
        P.cols["departure_day"][ids] = w.day
        sim.emit("left_area", ids, mech="lifecourse.departure")

    def after_graduation(self, ids, events):
        sim, w = self.sim, self.sim.w
        P = w.P
        p_leave = np.where(P["school"][ids] == 1, 0.62, 0.42)
        p_leave = p_leave - 0.25 * P["family_local"][ids]
        leave = sim.u("grad_leave")[ids] < p_leave
        lv = ids[leave]
        P.internal["leave_day"][lv] = w.day + 20 + (sim.u("grad_leave_d")[lv] * 70).astype(int)
        # spouses leave with them
        sp = P["partner_id"][lv]
        sp = sp[(sp >= 0)]
        P.internal["leave_day"][sp] = np.maximum(P.internal["leave_day"][sp], w.day + 25)
        stay = ids[~leave]
        P.cols["role"][stay] = P.code("role", "young_adult")
        del events

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
        h = expit(p("lifecourse.mission.base") + np.where(male, p("lifecourse.mission.male"), 0)
                  + p("lifecourse.mission.belief") * (P["faith_belief"] - 0.7) + 1.2 * (P["activity"] == 3)
                  + p("lifecourse.mission.family") * P["family_expectation"] + 0.8 * P["religious_identity"]
                  + 2.0 * age_peak + np.log(env["mission_norm"] + 1e-9) - 0.6 * P.is_("rel_status", "dating")
                  - 1.5 * np.maximum(age - np.where(male, 19.8, 21.5), 0))  # those who haven't gone by then mostly won't
        call = elig & (P["activity"] == 3) & (sim.u("mission_call") < h)
        if call.any():
            ids = np.where(call)[0]
            P.internal["depart_day_planned"][ids] = day + 75 + (sim.u("mtc")[ids] * 40).astype(int)
            sim.emit("mission_call", ids, mech="lifecourse.mission")
        # ---- fertility
        fem = P.is_("sex", "F") & P.is_("rel_status", "married") & ~P["pregnant"] & (age < 43) & P["present"]
        mm = np.maximum((day - P["married_day"]) / 30.4, 0)
        recent_birth = P.internal["newborn_until"][:n] > day - 150
        hf = expit(p("lifecourse.fertility.base") + 0.25 * (P["kids_wanted"] - 3) - 0.55 * P["children"]
                   + 0.06 * np.minimum(mm, 24) - p("lifecourse.fertility.student") * P["enrolled"]
                   - 0.8 * P["financial_stress"] + 0.5 * (P["activity"] == 3) - 0.08 * np.clip(age - 30, 0, None))
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
            sim.emit("pregnancy", ids, mech="lifecourse.fertility")
            if has.any():
                sim.emit("pregnancy", sp[has], mech="lifecourse.fertility")
        # ---- other life events
        pres = P["present"]
        for etype, rate, mask in (("family_crisis", p("lifecourse.events.family_crisis"), pres),
                                  ("death_in_family", p("lifecourse.events.death"), pres),
                                  ("car_accident", p("lifecourse.events.car_accident"), pres & P["owns_car"])):
            hit = mask & (sim.u(etype) < rate)
            if hit.any():
                sim.emit(etype, np.where(hit)[0], mech="lifecourse.events")
