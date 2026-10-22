"""Academic life: terms, class sections (shared contexts), study time, grades, graduation."""
from __future__ import annotations

import numpy as np
from scipy.special import expit

from .. import clock
from ..provenance import chance, link, pick, state_ref

MWF = 0b10101
TTH = 0b01010
SEC_FIELDS = {"sec_school": (np.int8, 0), "sec_days": (np.uint8, 0), "sec_block": (np.int8, 0), "sec_bldg": (np.int16, 0),
              "sec_area": (np.int16, -1), "sec_room": (np.int32, -1), "sec_start": (np.int16, -1), "sec_end": (np.int16, -1),
              "sec_lon": (np.float64, np.nan), "sec_lat": (np.float64, np.nan), "sec_floor": (np.int8, -1),
              "sec_place": (np.int32, -1), "sec_course": (object, ""), "sec_where": (object, "")}

_REAL: dict = {}


def real_schedule(term: str | None, areas: list, school: str = "BYU") -> dict | None:
    """A school's real sections for a term (ucsim/geo/schedule.py: BYU Fall and Winter, UVU Fall; the 2026–27 schedule
    stands in for every year) as arrays, with each BYU room matched to the floor plans' classrooms and each point to its
    building; None for other terms or when the schedule file is absent (then sections are drawn). area_code: the study
    area's index, −1 university-wide courses, −2 religion."""
    if term is None:
        return None
    key = (school, term)
    if key not in _REAL:
        import polars as pl

        from ...geo import schedule
        from .. import places
        D = schedule.load(school)
        if D is not None:
            D = D.filter(pl.col("term") == term)
        if D is None or D.height == 0:
            _REAL[key] = None
            return None
        R = places.classrooms(1 if school == "BYU" else 2) if places.available() else None
        rooms = {(c, str(r)): i for i, (c, r) in enumerate(zip(R["code"], R["room"]))} if R is not None else {}
        code_of = {a: i for i, a in enumerate(areas)} | {"religion": -2}
        out = {c: D[c].to_numpy() for c in ("level", "credits", "enrollment", "days", "start", "end", "lon", "lat")}
        out["floor"] = D["floor"].to_numpy().astype(np.int8)
        out["area_code"] = np.array([code_of.get(a, -1) for a in D["area"].to_list()], np.int16)
        out["room_row"] = np.array([rooms.get((b, r), -1) for b, r in zip(D["building"].to_list(), D["room"].to_list())], np.int32)
        out["course"] = np.array([f"{d} {c}" for d, c in zip(D["dept"].to_list(), D["catalog"].to_list())], object)
        out["where"] = np.array([f"{b} {r}" for b, r in zip(D["building"].to_list(), D["room"].to_list())], object)
        place = np.full(D.height, -1, np.int32)
        if places.available():                        # the package's room centroid, moved inside its building
            out["lon"], out["lat"], b = places.settle(out["lon"], out["lat"])
            place = np.asarray(b, np.int32)
        if R is not None:                             # a floor-plan room: its building, floor and spot
            has = out["room_row"] >= 0
            rr = out["room_row"][has]
            place[has], out["floor"][has] = R["building"][rr], R["floor"][rr]
            out["lon"][has], out["lat"][has] = R["lon"][rr], R["lat"][rr]
        out["place"] = place
        _REAL[key] = out
    return _REAL[key]


class Academics:
    def __init__(self, sim):
        self.sim = sim
        self.stu_secs = np.full((0, 5), -1, np.int64)
        self.sec_school = np.zeros(0, np.int8)
        self.sec_days = np.zeros(0, np.uint8)
        self.sec_block = np.zeros(0, np.int8)
        self.sec_bldg = np.zeros(0, np.int16)
        self.sec_area = np.zeros(0, np.int16)
        self.sec_room = np.zeros(0, np.int32)          # classroom (row of places.classrooms()), −1: none known
        # real sections (BYU and UVU class schedules, geo/schedule.py); drawn ones have start −1, no point, no course
        self.sec_start = np.zeros(0, np.int16)         # clock minutes
        self.sec_end = np.zeros(0, np.int16)
        self.sec_lon = np.zeros(0, np.float64)
        self.sec_lat = np.zeros(0, np.float64)
        self.sec_floor = np.zeros(0, np.int8)          # −1: not known
        self.sec_place = np.zeros(0, np.int32)         # building (engine/places.py row), −1: not known
        self.sec_course = np.zeros(0, object)          # "A HTG 100"
        self.sec_where = np.zeros(0, object)           # "KMBL 250"

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
    def start_term(self, school: str, initial: bool = False, term: str | None = None):
        """Enroll the school's students and give them sections; `term` (Fall, Winter…) defaults to today's."""
        sim, w = self.sim, self.sim.w
        P = w.P
        n = P.n
        code = P.code("school", school)
        term = term or sim.cal.term(school, w.day)
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
        for f, (dt, fill) in SEC_FIELDS.items():
            a = getattr(self, f)
            setattr(self, f, a[keep] if len(a) == len(keep) else np.full(int(keep.sum()), fill, dt))
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
        S = real_schedule(term, list(P.specs["study_area"].categories), school)
        if S is not None:                             # real courses, rooms and times (BYU Fall and Winter, UVU Fall)
            self._real_sections(S, ids, credits, n_ge, rng, code)
            P.internal["sched_count"][ids] = 0
            P.internal["attend_count"][ids] = 0
            if not initial:
                sim.emit("term_started", ids, mech="academics.term")
            return
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
        k = len(new_school)
        self._append({"sec_school": new_school, "sec_days": new_days, "sec_block": new_block, "sec_bldg": new_bldg,
                      "sec_area": new_area}, k)
        self.sec_room[base - k:] = self._rooms_for(np.arange(base - k, base), code)
        P.internal["sched_count"][ids] = 0
        P.internal["attend_count"][ids] = 0
        if not initial:
            sim.emit("term_started", ids, mech="academics.term")

    def _append(self, cols: dict, k: int):
        """Add k sections: the given columns, every other section field at its 'not known' value."""
        for f, (dt, fill) in SEC_FIELDS.items():
            new = np.asarray(cols[f], dt) if f in cols else np.full(k, fill, dt)
            setattr(self, f, np.r_[getattr(self, f), new] if dt is not object else np.concatenate([getattr(self, f), new]))

    def _real_sections(self, S: dict, ids: np.ndarray, credits: np.ndarray, n_ge: np.ndarray, rng, code: int):
        """Students take their school's real sections (geo/schedule.py): as many as their credits fill at the
        schedule's mean credits a seat (BYU 2.5: labs and one- and two-credit classes count; at most five);
        undergraduates a religion class at the schedule's rate (BYU: religion's share of seats × their classes, about
        two in three take one; UVU has none), n_ge general-education classes (100- and 200-level courses of any
        department; UVU's 1000s and 2000s) and the rest in their study area;
        graduate students their area's 500-level and up. Sections are drawn in proportion to their real
        enrollment until the simulated students fill them at real class sizes (so a small world has fewer sections,
        not emptier ones), and the students are shuffled into the seats. A class that clashes with one already on the
        student's schedule is swapped for another drawn section of the same kind, or dropped."""
        P = self.sim.w.P
        areas = list(P.specs["study_area"].categories)
        enr = S["enrollment"].astype(np.float64)
        rel, ge = S["area_code"] == -2, (S["level"] < 300) & (S["area_code"] != -2)
        pools = [np.flatnonzero(rel), np.flatnonzero(ge)]            # pool 0 religion, 1 GE, 2+2a area a, 3+2a its graduate
        for a in range(len(areas)):
            m = S["area_code"] == a
            pools.append(np.flatnonzero(m) if m.any() else pools[1])
            g = m & (S["level"] >= 500)
            pools.append(np.flatnonzero(g) if g.any() else pools[-1])
        n = len(ids)
        grad = P.is_("class_standing", "graduate")[ids]
        area = P["study_area"][ids].astype(np.int64)
        n_cls = np.clip(np.round(credits / (S["credits"] * enr).sum() * enr.sum()), 1, 5).astype(np.int64)
        k = np.arange(5)[None, :]
        rel_share = enr[rel].sum() / enr.sum()
        n_rel = np.where(~grad & (n_cls >= 2) & (rng.random(n) < rel_share * n_cls), 1, 0)[:, None]
        n_ge_ = np.where(grad, 0, np.minimum(n_ge, n_cls - n_rel[:, 0]))[:, None]
        kind = np.where(k < n_rel, 0, np.where(k < n_rel + n_ge_, 1, 2 + 2 * area[:, None] + grad[:, None]))
        kind = np.where(k < n_cls[:, None], kind, -1)
        A = np.full((n, 5), -1, np.int64)                             # real section row per (student, slot)
        drawn = {}
        for pid in np.unique(kind[kind >= 0]):
            r, c = np.nonzero(kind == pid)
            rows = pools[int(pid)]
            if not len(rows):
                continue
            w = enr[rows]
            order = rows[np.argsort(-rng.random(len(rows)) ** (1 / w))]
            cum = np.cumsum(enr[order])
            take = order[: int(np.searchsorted(cum, len(r))) + 1]
            cap = enr[take].astype(np.int64) * max(1, int(np.ceil(len(r) / cum[-1])))
            seats = np.repeat(take, cap)[: len(r)]
            A[r, c] = seats[rng.permutation(len(r))]
            drawn[int(pid)] = take
        st, en, dy = S["start"].astype(np.int64), S["end"].astype(np.int64), S["days"].astype(np.int64)

        def clash(i, j, row):
            o = A[i, :j]
            o = o[o >= 0]
            return bool(((o == row) | (((dy[o] & dy[row]) > 0) & (st[o] < en[row]) & (st[row] < en[o]))).any())

        for j in range(1, 5):                                         # clashes: swap, else drop
            a, o = A[:, j:j + 1], A[:, :j]
            ok = (a >= 0) & (o >= 0)
            sa, so = np.maximum(a, 0), np.maximum(o, 0)
            bad = (ok & ((o == a) | (((dy[so] & dy[sa]) > 0) & (st[so] < en[sa]) & (st[sa] < en[so])))).any(axis=1)
            for i in np.flatnonzero(bad):
                cand = drawn[int(kind[i, j])]
                for row in cand[rng.integers(0, len(cand), 8)]:
                    if not clash(i, j, row):
                        A[i, j] = row
                        break
                else:
                    A[i, j] = -1
        used, inv = np.unique(A[A >= 0], return_inverse=True)
        base = len(self.sec_school)
        stu = np.full((n, 5), -1, np.int64)
        stu[A >= 0] = base + inv
        self.stu_secs[ids] = stu
        start = S["start"][used]
        self._append({"sec_school": np.full(len(used), code), "sec_days": S["days"][used],
                      "sec_block": clock.block_of(np.maximum(start, clock.DAY_START)), "sec_bldg": np.zeros(len(used)),
                      "sec_area": np.maximum(S["area_code"][used], -1), "sec_room": S["room_row"][used],
                      "sec_start": start, "sec_end": S["end"][used], "sec_lon": S["lon"][used], "sec_lat": S["lat"][used],
                      "sec_floor": S["floor"][used], "sec_place": S["place"][used], "sec_course": S["course"][used],
                      "sec_where": S["where"][used]}, len(used))

    def _rooms_for(self, secs: np.ndarray, school: int) -> np.ndarray:
        """A real classroom for each new section (BYU floor plans; engine/places.py): in a building of its study area
        (general education anywhere), seats for everyone enrolled, the snuggest such room free at that hour; −1 when
        none fits or there are no plans (the section then meets in its campus building's slot)."""
        from .. import places
        out = np.full(len(secs), -1, np.int32)
        R = places.classrooms(school) if places.available() else None
        if R is None or not len(R["seats"]) or not len(secs):
            return out
        size = np.zeros(len(secs), np.int64)
        held = self.stu_secs[self.stu_secs >= 0]
        cnt = np.bincount(held, minlength=int(secs.max()) + 1)
        size = cnt[secs]
        areas = self.sim.w.P.specs["study_area"].categories if hasattr(self.sim.w.P.specs["study_area"], "categories") else []
        seats = R["seats"].astype(np.int64)
        pools = {k: np.asarray(v, np.int64) for k, v in R["by_area"].items()}
        everything = np.asarray(R["all"], np.int64)
        busy: dict = {}                               # (days, block) → rooms taken at that hour this term
        for j in np.lexsort((secs, -size)):           # the biggest sections choose first
            s_ = int(secs[j])
            a = int(self.sec_area[s_])
            pref = pools.get(areas[a] if 0 <= a < len(areas) else "general", pools["general"])
            slot = (int(self.sec_days[s_]), int(self.sec_block[s_]))
            taken = busy.setdefault(slot, np.zeros(len(seats), bool))
            for pool in (pref, pools["general"], everything):
                ok = pool[(seats[pool] >= size[j]) & ~taken[pool]]
                if len(ok):
                    r = int(ok[np.lexsort(((ok * 2654435761 + s_) % 997, seats[ok]))[0]])
                    out[j] = r
                    taken[r] = True
                    break
        return out

    def section_point(self, secs: np.ndarray):
        """Where each section meets: (lon, lat, floor, building) — its floor-plan classroom, else a real section's room
        (the schedule's point and floor), else its campus building's anchor."""
        from .. import places
        act = self.sim.systems["activity"]
        secs = np.asarray(secs, np.int64)
        sch = self.sec_school[secs]
        sb = self.sec_bldg[secs].astype(np.int64)
        lon, lat = np.zeros(len(secs)), np.zeros(len(secs))
        floor = np.zeros(len(secs), np.int64)
        bld = np.full(len(secs), -1, np.int64)
        for s_ in (1, 2):
            m = sch == s_
            if m.any():
                pts = act.bldg[s_]
                lon[m], lat[m] = pts[sb[m] % len(pts), 0], pts[sb[m] % len(pts), 1]
                bld[m] = act.bldg_id[s_][sb[m] % len(act.bldg_id[s_])]
        if len(self.sec_place) > int(secs.max(initial=-1)):      # a real section's room, inside its building
            real = self.sec_place[secs] >= 0
            lon[real], lat[real] = self.sec_lon[secs[real]], self.sec_lat[secs[real]]
            floor[real], bld[real] = self.sec_floor[secs[real]], self.sec_place[secs[real]]
        rm = self.sec_room[secs] if len(self.sec_room) > int(secs.max(initial=-1)) else np.full(len(secs), -1)
        has = rm >= 0
        if has.any() and places.available():
            R = places.classrooms(1)
            lon[has], lat[has] = R["lon"][rm[has]], R["lat"][rm[has]]
            floor[has], bld[has] = R["floor"][rm[has]], R["building"][rm[has]]
        return lon, lat, floor, bld

    def floor_known(self, secs: np.ndarray) -> np.ndarray:
        """Whether a section's floor is known (a floor-plan room, or a real section's room)."""
        secs = np.asarray(secs, np.int64)
        if len(self.sec_room) <= int(secs.max(initial=-1)):
            return np.zeros(len(secs), bool)
        return (self.sec_room[secs] >= 0) | (self.sec_place[secs] >= 0)

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
                  - 3 * (P["children"] > 0) + p("mind.self_efficacy.study") * (P["self_eff_academic"] - 0.5)
                  - p("academics.study.ability") * sim.z("academic_ability"))      # the struggling put in more hours
        plans = sim.systems.get("plans")
        if plans is not None:
            target = target + plans.study_boost()
        cop = sim.systems.get("coping")
        if cop is not None:
            target = target + cop.study_bias()
        target = target + sim.nudge("study")
        P["study_hours"] = np.where(in_term, np.clip(0.6 * P["study_hours"] + 0.4 * target, 0, 60), 0).astype(np.float32)

    def _record_grades(self, ids, TG: dict, keep: np.ndarray, g: np.ndarray) -> np.ndarray:
        """Record the grade-point terms of the students whose term was remarkable (failed, excellent, probation);
        returns decision ids aligned with `ids` (−1 for the rest). Bookkeeping only."""
        sim = self.sim
        out = np.full(len(ids), -1, np.int64)
        if not keep.any():
            return out
        rec = pick(TG, keep)
        for k in ("fatigue", "depression", "stress"):
            rec[k] = -rec[k]
        out[keep] = sim.decisions.record("term_grades", sim.w.day, ids[keep], np.where(g[keep] >= 3.0, 1, 0), rec,
                                         base=sim.p("academics.gpa.base"),
                                         refs={"study": ("state", state_ref(sim, "study_hours", ids[keep])),
                                               "depression": ("state", state_ref(sim, "depressive_episode", ids[keep]))})
        return out

    def end_term(self, school: str):
        sim, w = self.sim, self.sim.w
        P, p = w.P, sim.p
        code = P.code("school", school)
        ids = np.where((P["school"] == code) & P["enrolled"] & P["present"])[0]
        if len(ids) == 0:
            return
        rng = np.random.default_rng([w.seed, 78, w.day, code])
        # the term's grade points, term by term (added in the model's order; subtracted terms are kept positive here
        # and recorded with their sign): the record behind a failed or an excellent term
        TG = {"ability": p("academics.gpa.ability") * sim.z("academic_ability")[ids],
              "conscientiousness": p("academics.gpa.conscientiousness") * sim.z("conscientiousness")[ids],
              "study": p("academics.gpa.study") * (P["study_hours"][ids] - 18), "attendance": 0.8 * (P["class_attendance"][ids] - 0.85),
              "fatigue": 0.35 * P["fatigue"][ids], "depression": 0.3 * P["depressive_episode"][ids], "stress": 0.15 * P["stress"][ids],
              "sleep": 0.05 * (P["sleep_hours"][ids] - 7), "luck": p("academics.gpa.noise") * rng.standard_normal(len(ids))}
        g = (p("academics.gpa.base") + TG["ability"] + TG["conscientiousness"] + TG["study"] + TG["attendance"]
             - TG["fatigue"] - TG["depression"] - TG["stress"] + TG["sleep"] + TG["luck"])
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
        newprob = (st == "probation") & ~old_prob
        did = self._record_grades(ids, TG, fail | succ | newprob, g)
        if fail.any():
            sim.emit("exam_failure", ids[fail], value=g[fail], mech="academics.gpa", decision=did[fail])
        if succ.any():
            sim.emit("academic_success", ids[succ], value=g[succ], mech="academics.gpa", decision=did[succ])
        if newprob.any():
            sim.emit("academic_probation", ids[newprob], mech="academics.gpa", decision=did[newprob])
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
            sim.emit("major_change", ids[mc], mech="academics.term", decision=chance(sim, "change_major", ids[mc], 0.035, "changed"))
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
            # undergraduates finish when their credits reach their program's requirement; graduate students' finishing
            # is a flat chance each term in the model
            g_st = grad_student[grad]
            link(sim, ev[~g_st], "state", state_ref(sim, "credits_done", gi[~g_st]), 1.0, "enough_credits")
            if g_st.any():
                link(sim, ev[g_st], "decision", chance(sim, "finish_degree", gi[g_st], 0.22, "finished"), 1.0, "chance")
            sim.systems["lifecourse"].after_graduation(gi, ev)
        # dropout hazard
        fin = P["financial_stress"][ids]
        # the log-odds term by term (added in the model's order; the subtracted term is kept positive here)
        T = {"school": 0.9 if school == "UVU" else 0, "grades": 1.6 * (new_gpa < 2.0), "money": 1.2 * np.clip(fin - 0.5, 0, None),
             "children": 0.8 * (P["children"][ids] > 0) * P.is_("sex", "F")[ids],
             "self_efficacy": p("mind.self_efficacy.dropout") * (P["self_eff_academic"][ids] - 0.5)}
        h = expit(p("academics.dropout.base") + T["school"] + T["grades"] + T["money"] + T["children"] - T["self_efficacy"])
        drop = ~grad & (rng.random(len(ids)) < h)
        if drop.any():
            di = ids[drop]
            P.cols["enrolled"][di] = False
            P.cols["role"][di] = P.code("role", "young_adult")
            rec = pick(T, drop)
            rec["school"] = np.full(len(di), float(T["school"]))
            rec["self_efficacy"] = -rec["self_efficacy"]
            did = sim.decisions.record("drop_out", w.day, di, "dropped_out", rec, base=p("academics.dropout.base"), prob=h[drop],
                                       refs={"money": ("state", state_ref(sim, "financial_stress", di)),
                                             "grades": ("state", state_ref(sim, "gpa", di))})
            sim.emit("dropout", di, mech="academics.dropout", decision=did)
            sim.systems["lifecourse"].schedule_stay(di)
