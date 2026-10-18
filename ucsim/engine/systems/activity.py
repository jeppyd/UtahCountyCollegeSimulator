"""Daily activity patterns: where each agent is in each block of the day.

The day has four blocks (engine/clock.py: morning, afternoon, evening, late evening). Commitments take precedence:
Sunday meetings, class, work shifts with clock times, the occasions people said yes to (dinners, parties, dates,
dances — systems/occasions.py), FHE, ward activities, clubs. A shift and an occasion that share a block are settled by
minutes: whichever fills more of the block is where the person is. Free time is allocated by a random-utility
choice whose utilities depend on traits, habits, drives, weather and day of week. Loneliness pushes some people toward
company (approach) and others toward withdrawal (Cacioppo & Hawkley 2009) depending on extraversion, social anxiety
and neuroticism. An evening is two blocks, and people mostly stay with what they started (a visit, an outing).
"""
from __future__ import annotations

import numpy as np
from scipy.spatial import cKDTree
from scipy.special import expit

from .. import clock
from ..state import CTX_ID

BYU = (-111.6493, 40.2500)
UVU = (-111.7129, 40.2773)
ACT = ["home", "class", "work", "church", "campus", "gym", "gathering", "date", "venue", "outdoors",
       "ward_activity", "away", "club"]
A = {k: i for i, k in enumerate(ACT)}
NONE = 255
OPTIONS = ("home", "campus", "gym", "eating out", "outdoors", "dancing", "visiting friends", "around the complex")
# shift start times (minutes) and their shares: students fit work around classes (afternoons, evenings, Saturdays);
# others mostly work weekday days (hypothetical shares; Utah County has few Sunday shifts)
_STU_START = (np.array([12, 13, 14, 15, 16, 17, 18]) * 60, [0.1, 0.15, 0.2, 0.15, 0.2, 0.12, 0.08])
_FT_START = (np.array([7, 8, 9, 10]) * 60, [0.15, 0.45, 0.3, 0.1])
_PT_START = (np.array([8, 9, 11, 13, 16, 17]) * 60, [0.2, 0.25, 0.15, 0.15, 0.15, 0.1])
_SAT_STU = (np.array([9, 10, 12, 16]) * 60, [0.3, 0.25, 0.2, 0.25])
_SAT_OTHER = (np.array([8, 9, 10]) * 60, [0.4, 0.4, 0.2])
_SUN = (np.array([10, 12]) * 60, [0.6, 0.4])
LATEST_END = 23 * 60


class Activity:
    def __init__(self, sim):
        self.sim = sim

    def init(self):
        sim, w = self.sim, self.sim.w
        P = w.P
        rng = np.random.default_rng([w.seed, 404])
        v = w.venues
        self.v_lon = v["lon"].to_numpy().astype(float)
        self.v_lat = v["lat"].to_numpy().astype(float)
        self.v_type = v["vtype"].to_numpy()
        self.v_name = v["name"].to_list()
        self._build_trees()
        # campus "buildings" used as class locations
        self.bldg = {1: np.c_[BYU[0] + rng.normal(0, 0.0028, 40), BYU[1] + rng.normal(0, 0.0022, 40)],
                     2: np.c_[UVU[0] + rng.normal(0, 0.0022, 24), UVU[1] + rng.normal(0, 0.0018, 24)]}
        P.add_internal("shift_mask", np.uint32, 0)              # blocks a shift fills (bit clock.slot(wd, b))
        P.add_internal("shift_start", np.int16, -1, shape=(7,))  # per weekday, minutes after midnight (−1: no shift)
        P.add_internal("shift_end", np.int16, -1, shape=(7,))
        self.assign_shifts(np.arange(P.n))
        # FHE group meeting location: the first women's unit in the group (else first member)
        fhe = P.internal["fhe_group"][: P.n]
        ng = int(fhe.max()) + 1 if len(fhe) else 0
        self.fhe_loc = np.zeros((max(ng, 1), 2))
        for g in range(ng):
            mem = np.where(fhe == g)[0]
            if len(mem):
                fem = mem[P["sex"][mem] == P.code("sex", "F")]
                j = fem[0] if len(fem) else mem[0]
                self.fhe_loc[g] = (P["home_lon"][j], P["home_lat"][j])
        self.ctype = np.full(P.n, NONE, np.uint8)
        self.cid = np.full(P.n, -1, np.int64)
        self.ctx_share = np.ones(P.n, np.float32)
        self.gathering_units: set = set()       # apartments where friends dropped by this block
        self.host_of_unit: dict = {}            # kept for Encounters.apply (hosted occasions set introducers there)
        self.hosts_today = np.empty(0, np.int64)
        self._prev = None                       # previous block's (choice, ctype, cid, act) for evening continuity

    def _build_trees(self):
        self.trees = {}
        groups = {"food": ["restaurant", "cafe", "soda_shop", "dessert"], "gym": ["gym"],
                  "outdoors": ["park", "trailhead", "overlook"], "dance": ["dance"],
                  "date_fun": ["cinema_theatre", "museum", "recreation", "stadium", "dessert", "soda_shop"]}
        self.empty_groups = set()
        for g, types in groups.items():
            idx = np.where(np.isin(self.v_type, types))[0]
            if not len(idx):      # every venue of this kind closed by a What-if
                self.empty_groups.add(g)
                continue
            self.trees[g] = (cKDTree(np.c_[self.v_lon[idx] * 0.763, self.v_lat[idx]]), idx)

    def add_venue(self, spec: dict):
        """Intervention hook: a new business opens."""
        w = self.sim.w
        import polars as pl
        row = pl.DataFrame([{"venue_id": len(self.v_lon), "name": spec.get("name", "New venue"), "vtype": spec["vtype"],
                             "lon": float(spec["lon"]), "lat": float(spec["lat"]), "src": "intervention", "city": spec.get("city", "Provo")}])
        w.venues = pl.concat([w.venues, row.cast(w.venues.schema)], how="vertical")
        self.v_lon = np.append(self.v_lon, float(spec["lon"]))
        self.v_lat = np.append(self.v_lat, float(spec["lat"]))
        self.v_type = np.append(self.v_type, spec["vtype"])
        self.v_name.append(spec.get("name", "New venue"))
        self._build_trees()

    def nearest(self, group: str, lon, lat, k: int, pick: np.ndarray) -> np.ndarray:
        if group not in self.trees:   # closed out: the nearest open alternative
            group = next(g for g in ("food", "date_fun", "outdoors", "gym", "dance") if g in self.trees)
        tree, idx = self.trees[group]
        k = min(k, len(idx))
        _, nn = tree.query(np.c_[np.asarray(lon) * 0.763, lat], k=k)
        nn = np.atleast_2d(nn)
        if nn.shape[0] != len(pick):
            nn = nn.reshape(len(pick), -1)
        col = np.minimum((pick * nn.shape[1]).astype(int), nn.shape[1] - 1)
        return idx[nn[np.arange(len(pick)), col]]

    # ------------------------------------------------------------------ work shifts (clock times)
    def assign_shifts(self, ids: np.ndarray):
        """A weekly shift pattern from usual work hours: which weekdays, start and end minutes.

        Students take afternoon/evening/Saturday shifts that start after their last class of the day; others work
        weekday days (full-time five days, part-time 3–7 hour shifts); about 5% of workers have a Sunday shift.
        The blocks a shift fills (`shift_mask`) are derived from the minutes."""
        sim = self.sim
        P = sim.w.P
        ids = np.atleast_1d(np.asarray(ids, np.int64))
        if not len(ids):
            return
        rng = sim.streams.gen("shift_assign", sim.w.day, int(ids[0]) % 100003)
        k = len(ids)
        hours = np.clip(np.nan_to_num(P["work_hours"][ids].astype(np.float64)), 0, 70)
        student = P["enrolled"][ids].astype(bool)
        full = ~student & (hours >= 30)
        per = np.where(full, hours / 5.0, np.clip(rng.normal(np.where(student, 4.5, 5.0), 0.8), 3.0, 7.0))
        ndays = np.where(full, 5, np.clip(np.round(hours / per), 1, 6))
        ndays = np.where(hours > 0.5, ndays, 0).astype(int)
        per = np.where(ndays > 0, np.minimum(hours / np.maximum(ndays, 1), 12.0), 0.0)
        pref = np.zeros((k, 7))
        pref[:, 5] = np.where(student, 0.2, -1.5)
        pref[:, 6] = np.where(rng.random(k) < 0.05, 3.0, -50.0)
        pref[full, :5] += 5.0
        key = pref + rng.gumbel(size=(k, 7))
        rank = np.argsort(np.argsort(-key, axis=1), axis=1)
        works = rank < ndays[:, None]

        def draw(spec, size):
            vals, pr = spec
            return vals[rng.choice(len(vals), size=size, p=pr)]
        start = np.where(student[:, None], draw(_STU_START, (k, 7)),
                         np.where(full[:, None], draw(_FT_START, (k, 7)), draw(_PT_START, (k, 7))))
        start[:, 5] = np.where(student, draw(_SAT_STU, k), draw(_SAT_OTHER, k))
        start[:, 6] = draw(_SUN, k)
        start = np.maximum(start, np.where(student[:, None], self._after_classes(ids), 0))
        start = (start + 14) // 15 * 15
        end = start + np.round(per[:, None] * 4) * 15
        end = np.minimum(end, LATEST_END)
        works &= (end - start) >= 90
        P.internal["shift_start"][ids] = np.where(works, start, -1).astype(np.int16)
        P.internal["shift_end"][ids] = np.where(works, end, -1).astype(np.int16)
        self._shift_mask(ids)

    def _after_classes(self, ids: np.ndarray) -> np.ndarray:
        """Earliest shift start per weekday for students: 15 minutes after the block of their last class that day."""
        acad = self.sim.systems.get("academics")
        out = np.zeros((len(ids), 7), np.int64)
        if acad is None or not len(acad.sec_days) or acad.stu_secs.shape[0] <= int(ids.max()):
            return out
        secs = acad.stu_secs[ids]
        valid = secs >= 0
        s = np.maximum(secs, 0)
        days, blk = acad.sec_days[s], acad.sec_block[s].astype(np.int64)
        for wd in range(5):
            meets = valid & ((days & np.uint8(1 << wd)) > 0)
            last = np.where(meets, blk, -1).max(axis=1)
            out[:, wd] = np.where(last >= 0, clock.END[np.maximum(last, 0)] + 15, 0)
        return out

    def _shift_mask(self, ids: np.ndarray):
        P = self.sim.w.P
        s = P.internal["shift_start"][ids].astype(np.int32)
        e = P.internal["shift_end"][ids].astype(np.int32)
        m = np.zeros(len(ids), np.uint32)
        for b in range(clock.N_BLOCKS):
            mins = np.where(s >= 0, np.clip(np.minimum(e, clock.END[b]) - np.maximum(s, clock.START[b]), 0, None), 0)
            fill = mins >= min(120, 0.5 * (clock.END[b] - clock.START[b]))
            for wd in range(7):
                m |= np.where(fill[:, wd], np.uint32(1 << int(clock.slot(wd, b))), np.uint32(0))
        P.internal["shift_mask"][ids] = m

    def shift_minutes(self, b: int, wd: int) -> np.ndarray:
        """Minutes of each person's shift inside block b today (0 without a shift or a job)."""
        P = self.sim.w.P
        n = P.n
        s = P.internal["shift_start"][:n, wd].astype(np.int32)
        e = P.internal["shift_end"][:n, wd].astype(np.int32)
        mins = np.clip(np.minimum(e, clock.END[b]) - np.maximum(s, clock.START[b]), 0, None)
        return np.where((s >= 0) & P["employed"], mins, 0)

    # ------------------------------------------------------------------ main
    def choose(self, b: int):
        sim, w = self.sim, self.sim.w
        P, env = w.P, w.env
        n = P.n
        wd = env["weekday"]
        p = sim.p
        present = P["present"]
        ctype = np.full(n, NONE, np.uint8)
        cid = np.full(n, -1, np.int64)
        act = np.full(n, A["away"], np.uint8)
        share = np.full(n, clock.LEGACY_SHARE[b], np.float32)   # how much of the block (in old-block units) they spend there
        unit = P["unit_id"]
        home_ok = present & (unit >= 0)
        ctype[home_ok] = CTX_ID["unit"]
        cid[home_ok] = unit[home_ok]
        act[home_ok] = A["home"]
        busy = ~present.copy()
        u = sim.u(f"activity{b}")
        occ = sim.systems["occasions"]
        plan = occ.block_plan(b)          # who is expected at which occasion in this block (dates, dinners, dances…)
        # ---- church (Sunday morning)
        if wd == 6 and b == 0:
            att = sim.systems["faith"].attending_today & present & ~busy
            ctype[att] = CTX_ID["ward"]
            cid[att] = P["ward_id"][att]
            act[att] = A["church"]
            share[att] = 1.0
            busy |= att
            oth = sim.systems["faith"].attending_other & present & ~busy
            ctype[oth] = CTX_ID["congregation"]
            cid[oth] = P["congregation_id"][oth]
            act[oth] = A["church"]
            share[oth] = 1.0
            busy |= oth
        # ---- class
        acad = sim.systems["academics"]
        if wd < 5 and not env["holiday"]:
            sec_now = acad.section_now(wd, b)
            in_class = (sec_now >= 0) & present & ~busy & ~P["ill"]
            p_att = expit(p("activity.class_attendance.base") + p("activity.class_attendance.conscientiousness") * sim.z("conscientiousness")
                          - p("activity.class_attendance.fatigue") * P["fatigue"] + 0.8 * P["academic_pressure"] - 0.6 * P["depressive_episode"]
                          + sim.systems["coping"].attend_bias())
            go = in_class & (u < p_att)
            ctype[go] = CTX_ID["class"]
            cid[go] = sec_now[go]
            act[go] = A["class"]
            share[go] = 1.0
            busy |= go
            acad.record_attendance(in_class, go)
        # ---- work shifts and occasions: whichever fills more of this block
        occ_min = np.zeros(n, np.int32)
        if len(plan["person"]):
            np.maximum.at(occ_min, plan["person"], plan["minutes"])
        shift_min = self.shift_minutes(b, wd)
        blen = int(clock.END[b] - clock.START[b])
        on_shift = ((shift_min >= min(120, 0.5 * blen)) & (shift_min >= occ_min) & present & ~busy & P["employed"]
                    & ~P["ill"] & (not env["holiday"]))
        ctype[on_shift] = CTX_ID["work"]
        cid[on_shift] = P["employer_id"][on_shift]
        act[on_shift] = A["work"]
        share[on_shift] = clock.LEGACY_SHARE[b] * np.minimum(shift_min[on_shift] / blen, 1.0)
        busy |= on_shift
        if len(plan["person"]):
            pp = plan["person"]
            ok = ~busy[pp] & (plan["minutes"] >= occ_min[pp])
            ok[ok] &= ~np.r_[False, (pp[ok][1:] == pp[ok][:-1])]          # one occasion per person per block
            pp = pp[ok]
            ctype[pp] = plan["ctx"][ok]
            cid[pp] = plan["occ"][ok]
            act[pp] = plan["act"][ok]
            share[pp] = plan["share"][ok]
            busy[pp] = True
            occ.mark_present(b, pp, plan["occ"][ok], plan["arrive"][ok])
        # ---- FHE (Monday evening ~7 pm) and ward activities (weeknights ~7 pm)
        if b == 2 and (env["term_BYU"] or env["term_UVU"]):
            fhe = P.internal["fhe_group"][:n]
            if wd == 0:
                go = (fhe >= 0) & present & ~busy & (u < P["ward_activity_rate"] * p("activity.fhe.attend_mult"))
                ctype[go] = CTX_ID["fhe"]
                cid[go] = fhe[go]
                act[go] = A["ward_activity"]
                share[go] = 1.0
                busy |= go
            elif wd in (1, 2, 3):
                ward = P["ward_id"]
                go = (ward >= 0) & ((ward % 3) + 1 == wd) & present & ~busy & (u < P["ward_activity_rate"] * p("activity.ward_activity.attend_mult"))
                ctype[go] = CTX_ID["ward"]
                cid[go] = ward[go]
                act[go] = A["ward_activity"]
                share[go] = 1.0
                busy |= go
        # ---- clubs, intramural teams and institute classes (weekly, in term, at their meeting times)
        if b >= 1:
            free_now = present & ~busy
            met = sim.systems["groups"].meeting(b, wd, free_now, sim.u("group_attend"))
            for (gids, gid), name in zip(met, ("team", "club", "institute")):
                ctype[gids] = CTX_ID[name]
                cid[gids] = gid
                act[gids] = A["class"] if name == "institute" else A["club"]
                share[gids] = 1.0
                busy[gids] = True
        # ---- free time
        self.gathering_units = set()
        self.host_of_unit = {}
        free = present & ~busy
        self.last_choice = np.full(n, 255, np.uint8)
        if free.any():
            self._discretionary(free, b, wd, ctype, cid, act)
        # household members at home (and friends who dropped by) join a home occasion held in their unit
        occ.walk_ins(b, ctype, cid, act, share)
        # people continuing an evening outing are not starting a new one (outings and workouts counted once)
        fresh = None
        if b == clock.EVENING[-1] and self._prev is not None and len(self._prev[1]) == n:
            fresh = ~((self._prev[1] == ctype) & (self._prev[2] == cid) & (self._prev[3] == act))
        self._prev = (self.last_choice.copy(), ctype.copy(), cid.copy(), act.copy())
        self.ctype, self.cid, self.ctx_share = ctype, cid, share
        P["activity_now"] = act
        sim.systems["mind"].observe_block(act, ctype, fresh=fresh, social=occ.social_now(ctype, cid))
        rt = sim.systems.get("routine")
        if rt is not None:
            rt.observe(b, wd, free, self.last_choice)
        self._locate(ctype, cid, act)
        self._keep_frame(b)

    def _keep_frame(self, b: int):
        """Positions at each block of the day (and at night), kept for the map's day replay."""
        P = self.sim.w.P
        if not hasattr(self, "frames_today"):
            self.frames_today, self.day_frames = {}, {}
        self.frames_today[b] = (P["loc_lon"].astype(np.float32), P["loc_lat"].astype(np.float32),
                                P["activity_now"].astype(np.uint8))

    def night(self):
        """End of day: everyone present goes home to sleep (keeps the map honest between days)."""
        P = self.sim.w.P
        n = P.n
        unit = P["unit_id"]
        home = P["present"] & (unit >= 0)
        ctype = np.full(n, NONE, np.uint8)
        cid = np.full(n, -1, np.int64)
        act = np.full(n, A["away"], np.uint8)
        ctype[home], cid[home], act[home] = CTX_ID["unit"], unit[home], A["home"]
        P["activity_now"] = act
        self._locate(ctype, cid, act)
        self._keep_frame(clock.N_BLOCKS)
        if len(self.frames_today) == clock.N_BLOCKS + 1:
            self.day_frames = {"day": self.sim.w.day, **self.frames_today}
        self.frames_today = {}
        self._prev = None

    def _drives(self):
        """(approach, withdraw, style): the connection drive split into reaching out vs pulling back (mind.social_pull)."""
        return self.sim.systems["mind"].social_pull()

    # ------------------------------------------------------------------ free time
    def _utilities(self, idx: np.ndarray, b: int, wd: int, explain: bool = False):
        """Free-time option utilities (k × 8) for `idx` in block b; with `explain`, also the terms that were summed,
        as {term: (label, k × 8 contribution)}."""
        sim, w = self.sim, self.sim.w
        P, env, p = w.P, w.env, sim.p
        k = len(idx)
        terms: dict[str, tuple[str, np.ndarray]] = {}
        U = np.full((k, 8), -9.0)
        avail = np.zeros((k, 8), bool)

        def add(name, label, col, val, where=None):
            v = np.broadcast_to(np.asarray(val, np.float64), (k,))
            if where is not None:
                v = np.where(where, v, 0.0)
            U[:, col] += v
            if explain:
                if name not in terms:
                    terms[name] = (label, np.zeros((k, 8)))
                terms[name][1][:, col] += v

        def open_(col, where=True):
            m = np.broadcast_to(np.asarray(where, bool), (k,))
            avail[:, col] |= m
            U[m, col] = np.where(U[m, col] <= -8.5, 0.0, U[m, col])
            return m

        appr, withdraw, _ = self._drives()
        appr, withdraw = appr[idx], withdraw[idx]
        E = sim.z("extraversion")[idx]
        weekend = 1.0 if wd >= 4 else 0.0
        enrolled = P["enrolled"][idx]
        in_term = np.where(P["school"][idx] == 1, bool(env["term_BYU"]), bool(env["term_UVU"]))
        married = P.is_("rel_status", "married")[idx]
        late = b == 3
        # habit/trait bases plus the person's current drives (mind.choice): rest pulls home, achievement to campus,
        # fitness to the gym, fun to venues and the outdoors, connection to friends
        d = {m: P[f"drive_{m}"][idx] for m in ("rest", "achievement", "health", "fun", "partnership")}
        wgt = {m: p(f"mind.choice.{m}") for m in d}
        open_(0)
        add("base", "how much people stay in", 0, p("activity.choice.home"))
        add("rest", "needs rest", 0, wgt["rest"] * d["rest"])
        add("withdraw", "pulling back from people", 0, p("activity.choice.withdraw") * withdraw)
        add("married", "married (home life)", 0, 0.6 * married)
        add("children", "has children", 0, 0.3 * (P["children"][idx] > 0))
        if b == 0:
            add("morning", "mornings at home", 0, 0.6)
        add("ill", "sick", 0, 0.8 * P["ill"][idx])
        if b < 2:
            m = open_(1, enrolled & in_term)
            add("base", "studying on campus", 1, 0.5, m)
            add("achievement", "school & career drive", 1, wgt["achievement"] * d["achievement"], m)
            add("conscientious", "conscientiousness", 1, 0.3 * sim.z("conscientiousness")[idx], m)
            add("far", "lives far from campus", 1, -0.25 * (P["dist_campus_km"][idx] > 3), m)
        open_(2)
        add("habit", "workout habit", 2, -2.3 + np.log(P["workouts_week"][idx] + 0.3))
        add("time", "time of day", 2, {0: 0.4, 1: -0.3, 2: 0.4, 3: -0.6}[b])
        add("health", "fitness drive", 2, wgt["health"] * d["health"])
        if b >= 1:
            open_(3)
            add("base", "eating out", 3, -1.6 + 0.5 * np.log1p(P.internal["eat_out_month"][idx] + 3 * P["soda_shop_week"][idx]))
            add("approach", "wants company", 3, p("activity.choice.approach") * 0.6 * appr)
            add("weekend", "weekend", 3, 0.3 * weekend)
            add("fun", "fun drive", 3, wgt["fun"] * 0.6 * d["fun"])
            open_(4)
            add("base", "loves the outdoors", 4, -2.6 + 1.0 * P["hikes"][idx] + 0.4 * P["outdoors"][idx])
            add("weather", "the weather", 4, 1.6 * env["outdoor_appeal"])
            add("weekend", "weekend", 4, 0.6 * weekend)
            add("fun", "fun drive", 4, wgt["fun"] * d["fun"] + 0.5 * wgt["health"] * d["health"])
            if late:
                add("dark", "it's dark out", 4, -0.8)
            has_f = P["n_friends"][idx] > 0
            m = open_(6, has_f)
            add("base", "dropping by a friend's place", 6, -1.2, m)
            add("approach", "wants company", 6, p("activity.choice.approach") * appr, m)
            add("extraversion", "outgoing", 6, 0.35 * E, m)
            add("weekend", "weekend", 6, 0.5 * weekend, m)
            add("married", "married (home life)", 6, -0.5 * married, m)
        if b >= 2:
            m = open_(7, P["complex_id"][idx] >= 0)
            add("base", "hanging out around the complex", 7, -2.0, m)
            add("extraversion", "outgoing", 7, 0.4 * E, m)
            add("approach", "wants company", 7, 0.5 * appr, m)
            add("culture", "a social complex", 7, p("culture.feedback.reputation") * sim.systems["culture"].complex_social_z(P["complex_id"][idx]), m)
        # dances are planned events now (open occasions in systems/occasions.py), not a free-time option
        for name, label, bias in (("routine", "habit (what they usually do then)", "routine"), ("coping", "coping with a hard stretch", "coping"),
                                  ("intention", "an intention (meeting people)", "plans")):
            s = sim.systems.get(bias)
            if s is None:
                continue
            B = s.bonus(idx, wd, b) if bias == "routine" else s.choice_bias(idx)
            B = np.where(avail, B, 0.0)
            U += B
            if explain:
                terms[name] = (label, B)
        wb = sim.whatif.choice_bias(idx)          # a What-if's nudges on free-time choices, only on options that exist
        if not np.isscalar(wb):
            wb = np.where(avail, wb, 0.0)
            U += wb
            if explain:
                terms["whatif"] = ("the What-if's nudge", wb)
        # an evening is mostly one thing: carry on with what the early evening started
        if late and self._prev is not None and len(self._prev[0]) >= int(idx.max(initial=-1)) + 1:
            pc = self._prev[0][idx]
            cont = (pc != NONE) & (pc < 8)
            if cont.any():
                C = np.zeros((k, 8))
                C[np.where(cont)[0], pc[cont]] = p("occasions.evening.continue")
                C = np.where(avail, C, 0.0)
                U += C
                if explain:
                    terms["continue"] = ("carrying on with the evening", C)
        for col, grp in ((3, "food"), (4, "outdoors")):
            if grp in self.empty_groups:
                U[:, col] = -9
                avail[:, col] = False
        if "gym" in self.empty_groups:
            U[~enrolled, 2] = -9
            avail[~enrolled, 2] = False
        U[~avail] = -9.0
        return (U, avail, terms) if explain else U

    def _discretionary(self, free, b, wd, ctype, cid, act):
        sim, w = self.sim, self.sim.w
        P = w.P
        idx = np.where(free)[0]
        U = self._utilities(idx, b, wd)
        g = sim.streams.gen(f"disc{b}", w.day).gumbel(size=(P.n, 8))[idx]
        choice = np.argmax(U + g, axis=1)
        self.last_choice[idx] = choice
        pick = sim.u(f"pick{b}")[idx]
        hl, ht = P["home_lon"][idx], P["home_lat"][idx]
        # carrying on: same venue, the same friend's place (late evening)
        prev = self._prev if (b == clock.EVENING[-1] and self._prev is not None and len(self._prev[0]) == P.n) else None
        same = (prev[0][idx] == choice) & (prev[2][idx] >= 0) if prev is not None else np.zeros(len(idx), bool)
        # campus
        m = choice == 1
        ctype[idx[m]] = CTX_ID["campus"]
        cid[idx[m]] = P["school"][idx[m]]
        act[idx[m]] = A["campus"]
        # gym: students use campus gym, others nearest commercial gym
        m = choice == 2
        if m.any():
            gi = idx[m]
            stud = P["enrolled"][gi]
            ctype[gi] = CTX_ID["gym"]
            near = self.nearest("gym", hl[m], ht[m], 3, pick[m])
            cid[gi] = np.where(stud, 100000 + P["school"][gi].astype(np.int64), near)
            act[gi] = A["gym"]
        for code, group, ctxname, actname in ((3, "food", "venue", "venue"), (4, "outdoors", "outdoors", "outdoors")):
            m = choice == code
            if m.any():
                vi = self.nearest(group, hl[m], ht[m], 6, pick[m])
                ctype[idx[m]] = CTX_ID[ctxname]
                cid[idx[m]] = np.where(same[m] & (prev[1][idx[m]] == CTX_ID[ctxname]), prev[2][idx[m]], vi) if prev is not None else vi
                act[idx[m]] = A[actname]
        # visit a friend (joins the friend's household context -> meets their roommates)
        m = choice == 6
        if m.any():
            net = self.sim.systems["network"]
            vis = idx[m]
            friend = net.random_neighbor(vis, pick[m], min_stage=2)
            ok = friend >= 0
            ok[ok] &= P["present"][friend[ok]] & (P["unit_id"][friend[ok]] >= 0)
            dest = np.where(ok, P["unit_id"][np.maximum(friend, 0)], -1)
            stay = same[m] & (prev[1][vis] == CTX_ID["unit"]) & (prev[2][vis] != P["unit_id"][vis]) if prev is not None else np.zeros(len(vis), bool)
            if prev is not None:
                dest = np.where(stay, prev[2][vis], dest)
            ok |= stay
            vis, dest = vis[ok], dest[ok]
            ctype[vis] = CTX_ID["unit"]
            cid[vis] = dest
            act[vis] = A["gathering"]
            self.gathering_units.update(dest.tolist())
            new_visit = ~stay[ok]
            sim.systems["culture"].observe_visits(dest[new_visit])
        m = choice == 7
        ctype[idx[m]] = CTX_ID["complex"]
        cid[idx[m]] = P["complex_id"][idx[m]]
        act[idx[m]] = A["home"]

    def explain_choice(self, i: int, b: int | None = None) -> dict:
        """One person's free-time options now, each utility broken into the terms that were summed. Routine choices
        are not logged; this is computed on demand from the person's current state (and says so)."""
        sim, w = self.sim, self.sim.w
        P = w.P
        b = int(clock.block_of(w.hour * 60)) if b is None else int(b)
        b = min(max(b, 0), clock.N_BLOCKS - 1)
        wd = int(w.env["weekday"])
        idx = np.array([int(i)], np.int64)
        U, avail, terms = self._utilities(idx, b, wd, explain=True)
        u = np.where(avail[0], U[0], -np.inf)
        ex = np.exp(u - u[avail[0]].max()) if avail[0].any() else np.zeros(8)
        prob = ex / ex.sum() if ex.sum() > 0 else ex
        opts = []
        for c, label in enumerate(OPTIONS):
            tl = [{"term": t, "label": lab, "value": round(float(M[0, c]), 3)} for t, (lab, M) in terms.items() if abs(M[0, c]) > 1e-9]
            opts.append({"option": c, "label": label, "available": bool(avail[0, c]),
                         "utility": round(float(U[0, c]), 3) if avail[0, c] else None, "prob": round(float(prob[c]), 3),
                         "terms": sorted(tl, key=lambda r: -abs(r["value"])),
                         "note": "dances are planned events (see the day's occasions)" if c == 5 else None})
        commit = sim.systems["occasions"].committed_at(int(i), b)
        return {"person": int(i), "day": int(w.day), "block": b, "block_label": clock.BLOCK_LABELS[b], "computed_now": True,
                "note": "Free-time choices aren't logged one by one; this is what the model computes for this person right now "
                        "(the actual pick adds a random draw, so the most likely option doesn't always win).",
                "committed": commit, "options": sorted(opts, key=lambda r: (not r["available"], -(r["utility"] or -99)))}

    # ------------------------------------------------------------------ places
    def _locate(self, ctype, cid, act):
        sim, w = self.sim, self.sim.w
        P = w.P
        U = w.units
        n = P.n
        lon = np.full(n, np.nan)
        lat = np.full(n, np.nan)
        m = ctype == CTX_ID["unit"]
        lon[m], lat[m] = U.lon[cid[m]], U.lat[cid[m]]
        m = ctype == CTX_ID["class"]
        if m.any():
            sec = sim.systems["academics"]
            b = sec.sec_bldg[cid[m]]
            sch = sec.sec_school[cid[m]]
            for s in (1, 2):
                mm = sch == s
                pts = self.bldg[s][b[mm] % len(self.bldg[s])]
                ii = np.where(m)[0][mm]
                lon[ii], lat[ii] = pts[:, 0], pts[:, 1]
        m = ctype == CTX_ID["ward"]
        lon[m], lat[m] = w.wards["lon"][cid[m]], w.wards["lat"][cid[m]]
        m = ctype == CTX_ID["fhe"]
        lon[m], lat[m] = self.fhe_loc[cid[m], 0], self.fhe_loc[cid[m], 1]
        m = ctype == CTX_ID["work"]
        lon[m], lat[m] = w.employers["lon"][cid[m]], w.employers["lat"][cid[m]]
        for name in ("venue", "outdoors", "dance"):
            m = ctype == CTX_ID[name]
            lon[m], lat[m] = self.v_lon[cid[m]], self.v_lat[cid[m]]
        m = ctype == CTX_ID["campus"]
        lon[m] = np.where(cid[m] == 1, BYU[0], UVU[0])
        lat[m] = np.where(cid[m] == 1, BYU[1], UVU[1])
        m = ctype == CTX_ID["gym"]
        if m.any():
            gc = cid[m]
            camp = gc >= 100000
            gl = np.where(camp, np.where(gc - 100000 == 1, BYU[0] - 0.003, UVU[0]), self.v_lon[np.minimum(gc, len(self.v_lon) - 1)])
            gt = np.where(camp, np.where(gc - 100000 == 1, BYU[1] + 0.002, UVU[1]), self.v_lat[np.minimum(gc, len(self.v_lat) - 1)])
            lon[m], lat[m] = gl, gt
        m = ctype == CTX_ID["complex"]
        if m.any():
            cx = w.complexes
            lon[m] = cx["lon"].to_numpy()[cid[m]]
            lat[m] = cx["lat"].to_numpy()[cid[m]]
        m = ctype == CTX_ID["congregation"]
        if m.any():
            lon[m], lat[m] = w.congregations["lon"][cid[m]], w.congregations["lat"][cid[m]]
        for name in ("club", "team", "institute"):
            m = ctype == CTX_ID[name]
            if m.any():
                lon[m], lat[m] = w.groups["lon"][cid[m]], w.groups["lat"][cid[m]]
        m = (ctype == CTX_ID["date"]) | (ctype == CTX_ID["occasion"])
        if m.any():
            O = sim.book.occ
            pos = np.maximum(O.pos(cid[m]), 0)
            lon[m], lat[m] = O.cols["lon"][pos], O.cols["lat"][pos]
        jit = sim.streams.normal("locjit", w.day, n * 2, block=int(act.sum() % 7)).reshape(2, n) * 0.00025
        P["loc_lon"] = np.where(np.isfinite(lon), lon + jit[0], np.nan)
        P["loc_lat"] = np.where(np.isfinite(lat), lat + jit[1], np.nan)
