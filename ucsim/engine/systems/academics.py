"""Academic life: terms, class sections (shared contexts), study time, grades, graduation."""
from __future__ import annotations

import numpy as np
from scipy.special import expit

MWF = 0b10101
TTH = 0b01010


class Academics:
    def __init__(self, sim):
        self.sim = sim
        self.stu_secs = np.full((0, 5), -1, np.int64)
        self.sec_school = np.zeros(0, np.int8)
        self.sec_days = np.zeros(0, np.uint8)
        self.sec_block = np.zeros(0, np.int8)
        self.sec_bldg = np.zeros(0, np.int16)
        self.sec_area = np.zeros(0, np.int16)

    def init(self):
        P = self.sim.w.P
        P.add_internal("sched_count", np.float32, 0.0)
        P.add_internal("attend_count", np.float32, 0.0)
        P.add_internal("summer_away", np.bool_, False)
        P["study_hours"] = np.where(P["enrolled"], 12 + 4 * self.sim.z("conscientiousness"), 0).clip(0, 50)
        P["class_attendance"] = np.where(P["enrolled"], 0.85, 0)
        for school in ("BYU", "UVU"):
            if self.sim.cal.term(school, self.sim.w.day):
                self.start_term(school, initial=True)

    # ------------------------------------------------------------------ sections
    def start_term(self, school: str, initial: bool = False):
        sim, w = self.sim, self.sim.w
        P = w.P
        n = P.n
        code = P.code("school", school)
        term = sim.cal.term(school, w.day)
        rng = np.random.default_rng([w.seed, 77, w.day, code])
        # who enrolls this term
        stud = (P["school"] == code) & P["present"] & ~P["graduated"] & np.isin(P["role"], [P.code("role", "byu_student"), P.code("role", "uvu_student")])
        stud &= P["mission_status"] != P.code("mission_status", "serving")
        if term in ("Spring", "Summer") and school == "BYU":
            stud &= sim.u("ss_enroll")[:n] < 0.55
        if term == "Summer" and school == "UVU":
            stud &= sim.u("ss_enroll")[:n] < 0.35
        P.cols["enrolled"][np.where((P["school"] == code) & ~stud & P["enrolled"])[0]] = False
        P.cols["enrolled"][np.where(stud)[0]] = True
        ids = np.where(stud)[0]
        if self.stu_secs.shape[0] < P.cap:
            grown = np.full((P.cap, 5), -1, np.int64)
            grown[: self.stu_secs.shape[0]] = self.stu_secs
            self.stu_secs = grown
        # drop old sections for this school
        keep = self.sec_school != code
        if len(keep):
            remap = np.full(len(keep), -1, np.int64)
            remap[keep] = np.arange(keep.sum())
            self.stu_secs = np.where(self.stu_secs >= 0, remap[np.maximum(self.stu_secs, 0)], -1)
        self.sec_school, self.sec_days = self.sec_school[keep], self.sec_days[keep]
        self.sec_block, self.sec_bldg, self.sec_area = self.sec_block[keep], self.sec_bldg[keep], self.sec_area[keep]
        self.stu_secs[ids] = -1
        if len(ids) == 0:
            return
        short = term in ("Spring", "Summer")
        part_time = P["credits_term"][ids] < 10
        credits = np.where(short, rng.integers(3, 8, len(ids)), np.where(part_time, rng.integers(6, 11, len(ids)), rng.integers(12, 17, len(ids))))
        # married students and parents usually carry lighter loads (work, family)
        married = P.is_("rel_status", "married")[ids]
        kids = P["children"][ids] > 0
        credits = np.where(~short & married, np.minimum(credits, rng.integers(9, 15, len(ids))), credits)
        credits = np.where(~short & kids, np.minimum(credits, rng.integers(6, 13, len(ids))), credits)
        P.cols["credits_term"][ids] = credits
        n_cls = np.clip(np.round(credits / 3.3), 1, 5).astype(int)
        n_ge = np.minimum(np.where(P["class_standing"][ids] <= P.code("class_standing", "sophomore"), 2, 1), n_cls)
        n_major = n_cls - n_ge
        # GE sections: large lectures mixing majors; major sections: by study area, smaller
        new_school, new_days, new_block, new_bldg, new_area = [], [], [], [], []
        base = len(self.sec_school)

        def make_sections(members_slots, size, area):
            nonlocal base
            m = len(members_slots)
            k = max(1, int(np.ceil(m / size)))
            perm = rng.permutation(m)
            sec_ids = base + (np.arange(m) % k)[np.argsort(perm)]
            for _ in range(k):
                new_school.append(code)
                new_days.append(MWF if rng.random() < 0.55 else TTH)
                r = rng.random()
                new_block.append(0 if r < 0.5 else (1 if r < 0.92 else 2))
                new_bldg.append(int(rng.integers(0, 40)))
                new_area.append(area)
            base += k
            return sec_ids

        # GE: each student fills n_ge GE slots
        ge_people = np.repeat(ids, n_ge)
        ge_slot = np.concatenate([np.arange(k) for k in n_ge]) if len(n_ge) else np.zeros(0, int)
        if len(ge_people):
            secs = make_sections(ge_people, 90, -1)
            for person, slot, s in zip(ge_people, ge_slot, secs):
                self.stu_secs[person, slot] = s
        area = P["study_area"][ids]
        for a in np.unique(area):
            sel = area == a
            people = np.repeat(ids[sel], n_major[sel])
            slots = np.concatenate([np.arange(g, g + k) for g, k in zip(n_ge[sel], n_major[sel])]) if sel.any() else np.zeros(0, int)
            if len(people) == 0:
                continue
            secs = make_sections(people, 32, int(a))
            for person, slot, s in zip(people, slots, secs):
                if slot < 5:
                    self.stu_secs[person, slot] = s
        self.sec_school = np.r_[self.sec_school, np.array(new_school, np.int8)]
        self.sec_days = np.r_[self.sec_days, np.array(new_days, np.uint8)]
        self.sec_block = np.r_[self.sec_block, np.array(new_block, np.int8)]
        self.sec_bldg = np.r_[self.sec_bldg, np.array(new_bldg, np.int16)]
        self.sec_area = np.r_[self.sec_area, np.array(new_area, np.int16)]
        P.internal["sched_count"][ids] = 0
        P.internal["attend_count"][ids] = 0
        if not initial:
            sim.emit("term_started", ids, mech="academics.term")

    def section_now(self, wd: int, b: int) -> np.ndarray:
        P = self.sim.w.P
        n = P.n
        if self.stu_secs.shape[0] < n:
            grown = np.full((P.cap, 5), -1, np.int64)
            grown[: self.stu_secs.shape[0]] = self.stu_secs
            self.stu_secs = grown
        secs = self.stu_secs[:n]
        out = np.full(n, -1, np.int64)
        if len(self.sec_days) == 0:
            return out
        bit = np.uint8(1 << wd)
        enrolled = P["enrolled"]
        for k in range(5):
            s = secs[:, k]
            valid = s >= 0
            ss = np.maximum(s, 0)
            hit = valid & ((self.sec_days[ss] & bit) > 0) & (self.sec_block[ss] == b) & enrolled
            out = np.where((out < 0) & hit, s, out)
        # only during a term for that school
        env = self.sim.w.env
        in_term = np.where(P["school"] == 1, bool(env.get("term_BYU")), bool(env.get("term_UVU")))
        return np.where(in_term, out, -1)

    def record_attendance(self, scheduled: np.ndarray, attended: np.ndarray):
        P = self.sim.w.P
        P.internal["sched_count"][: P.n] += scheduled
        P.internal["attend_count"][: P.n] += attended

    # ------------------------------------------------------------------ daily / weekly / term end
    def daily(self):
        sim, w = self.sim, self.sim.w
        for school in ("BYU", "UVU"):
            if sim.cal.term_end(school, w.day):
                self.end_term(school)
            if sim.cal.term_start(school, w.day) and w.day > 0:
                self.start_term(school)

    def weekly(self):
        sim, w = self.sim, self.sim.w
        P, p = w.P, sim.p
        n = P.n
        sc = P.internal["sched_count"][:n]
        P["class_attendance"] = np.where(sc > 0, P.internal["attend_count"][:n] / np.maximum(sc, 1), P["class_attendance"]).astype(np.float32)
        env = w.env
        in_term = np.where(P["school"] == 1, bool(env.get("term_BYU")), bool(env.get("term_UVU"))) & P["enrolled"]
        target = (p("academics.study.base") + 0.75 * P["credits_term"] + p("academics.study.conscientiousness") * sim.z("conscientiousness")
                  + 8 * P["academic_pressure"] - p("academics.study.work_crowdout") * np.clip(P["work_hours"] - 10, 0, None)
                  - 6 * P["depressive_episode"] - 4 * P["fatigue"] - 0.08 * np.clip(P["social_hours_week"] - 20, 0, None)
                  - 3 * (P["children"] > 0) + p("mind.self_efficacy.study") * (P["self_eff_academic"] - 0.5))
        plans = sim.systems.get("plans")
        if plans is not None:
            target = target + plans.study_boost()
        cop = sim.systems.get("coping")
        if cop is not None:
            target = target + cop.study_bias()
        P["study_hours"] = np.where(in_term, np.clip(0.6 * P["study_hours"] + 0.4 * target, 0, 60), 0).astype(np.float32)

    def end_term(self, school: str):
        sim, w = self.sim, self.sim.w
        P, p = w.P, sim.p
        code = P.code("school", school)
        ids = np.where((P["school"] == code) & P["enrolled"] & P["present"])[0]
        if len(ids) == 0:
            return
        rng = np.random.default_rng([w.seed, 78, w.day, code])
        g = (p("academics.gpa.base") + p("academics.gpa.ability") * sim.z("academic_ability")[ids]
             + p("academics.gpa.conscientiousness") * sim.z("conscientiousness")[ids]
             + p("academics.gpa.study") * (P["study_hours"][ids] - 18) + 0.8 * (P["class_attendance"][ids] - 0.85)
             - 0.35 * P["fatigue"][ids] - 0.3 * P["depressive_episode"][ids] - 0.15 * P["stress"][ids]
             + 0.05 * (P["sleep_hours"][ids] - 7) + p("academics.gpa.noise") * rng.standard_normal(len(ids)))
        g = np.clip(g, 0, 4)
        cred = P["credits_term"][ids]
        prev = np.nan_to_num(P["gpa"][ids], nan=g)
        done = P["credits_done"][ids]
        new_gpa = (prev * done + g * cred) / np.maximum(done + cred, 1)
        P.cols["gpa_term"][ids] = g
        P.cols["gpa"][ids] = new_gpa
        sim.systems["mind"].learn_grades(ids, g)
        passed = cred * np.clip((g - 0.7) / 1.3, 0, 1)
        P.cols["credits_done"][ids] = done + passed
        st = np.where(new_gpa < 2.0, "probation", np.where(g < 2.0, "warning", "good"))
        old_prob = P.is_("academic_standing", "probation")[ids]
        P.cols["academic_standing"][ids] = P.codes("academic_standing", st)
        fail = g < 1.9
        succ = g >= 3.85
        if fail.any():
            sim.emit("exam_failure", ids[fail], value=g[fail], mech="academics.gpa")
        if succ.any():
            sim.emit("academic_success", ids[succ], value=g[succ], mech="academics.gpa")
        newprob = (st == "probation") & ~old_prob
        if newprob.any():
            sim.emit("academic_probation", ids[newprob], mech="academics.gpa")
        # class standing from credits
        cd = P["credits_done"][ids]
        grad_student = P.is_("class_standing", "graduate")[ids]
        stand = np.where(grad_student, "graduate", np.where(cd < 30, "freshman", np.where(cd < 60, "sophomore", np.where(cd < 90, "junior", "senior"))))
        P.cols["class_standing"][ids] = P.codes("class_standing", stand)
        # major change (early students)
        mc = (cd < 70) & (rng.random(len(ids)) < 0.035)
        if mc.any():
            areas = len(P.specs["study_area"].categories)
            P.cols["study_area"][ids[mc]] = rng.integers(0, areas - 1, mc.sum())
            sim.emit("major_change", ids[mc], mech="academics.term")
        # graduation
        # programs need 120-145 credits (majors, minors, retakes); a fixed per-person requirement spreads graduations out
        need = 120 + 25 * ((ids * 0.6180339887) % 1.0)
        grad = ((cd >= need) & ~grad_student) | (grad_student & (rng.random(len(ids)) < 0.22))
        if grad.any():
            gi = ids[grad]
            P.cols["graduated"][gi] = True
            P.cols["enrolled"][gi] = False
            P.cols["grad_day"][gi] = w.day
            ev = sim.emit("graduation", gi, mech="academics.term")
            sim.systems["lifecourse"].after_graduation(gi, ev)
        # dropout hazard
        fin = P["financial_stress"][ids]
        h = expit(p("academics.dropout.base") + (0.9 if school == "UVU" else 0) + 1.6 * (new_gpa < 2.0) + 1.2 * np.clip(fin - 0.5, 0, None)
                  + 0.8 * (P["children"][ids] > 0) * P.is_("sex", "F")[ids]
                  - p("mind.self_efficacy.dropout") * (P["self_eff_academic"][ids] - 0.5))
        drop = ~grad & (rng.random(len(ids)) < h)
        if drop.any():
            di = ids[drop]
            P.cols["enrolled"][di] = False
            P.cols["role"][di] = P.code("role", "young_adult")
            sim.emit("dropout", di, mech="academics.dropout")
            sim.systems["lifecourse"].schedule_stay(di)
