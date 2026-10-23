"""Hour-by-hour activity: where each person is in each hour of the day (engine/clock.py: 6 am to 6 am).

Each hour, people in bed stay there until something wakes them (engine/systems/sleep.py). Commitments come first:
Sunday meetings, class (attendance decided as each class starts), work shifts with clock times, the occasions people
said yes to (dinners, parties, dates, dances — systems/occasions.py), FHE, ward activities, clubs. A shift and an
occasion that share an hour are settled by minutes: whichever fills more of it is where the person is.

Everyone else makes a free-time choice, every hour, among staying in, campus, the gym, eating out, the outdoors, a
friend's place, the complex, time with a partner and going to bed. Utilities depend on traits, habits, drives,
weather and day of week (Loneliness pushes some toward company and others toward withdrawal: Cacioppo & Hawkley 2009),
plus a 24-hour curve per option — read later in the day for night owls and on Friday and Saturday nights — and a pull
to carry on with what they're already doing that fades once it has run its usual length. Nothing outside the
calendar's fixed events is tied to a time of day: the curves make a 3 am food run unlikely, not impossible, and the
same person who is in bed by 11 on a Tuesday can be out until 2 on a Friday with someone they like.

Some choices take two. Time with a partner needs both free and awake and the other willing; a visit goes to a friend
who is home and up; someone heading out for food, a hike or the gym may ask a partner or close friend along, who
comes if that beats their own plan (spontaneous plans, recorded after 10 pm). A class is skipped more often when
something else pulls hard right then; a guest staying in an opposite-sex BYU-contracted apartment after visiting
hours feels the rule against the night (and, with a partner, the heat of the moment) — a pull, not a rule.
"""
from __future__ import annotations

import numpy as np
from scipy.spatial import cKDTree
from scipy.special import expit

from .. import clock, places
from ..state import CTX_ID
from .sleep import curve

BYU = (-111.6493, 40.2500)
UVU = (-111.7129, 40.2773)
ACT = ["home", "class", "work", "church", "campus", "gym", "gathering", "date", "venue", "outdoors",
       "ward_activity", "away", "club", "sleep", "with_partner"]
A = {k: i for i, k in enumerate(ACT)}
NONE = 255
OPTIONS = ("home", "campus", "gym", "eating out", "outdoors", "dancing", "visiting friends", "around the complex",
           "going to bed", "with their partner")
NOPT = len(OPTIONS)
O_HOME, O_CAMPUS, O_GYM, O_FOOD, O_OUT, O_DANCE, O_VISIT, O_COMPLEX, O_SLEEP, O_PARTNER = range(NOPT)
LATEST_END = 23 * 60
# how long each outing usually lasts (hours): carrying on past it gets less appealing (0: no usual length)
USUAL_H = np.array([0.0, 2.5, 1.25, 1.25, 2.5, 2.0, 2.5, 1.5, 0.0, 3.0])
# Time of day: utility added to each option at each clock hour (index 0 = midnight … 23 = 11 pm), for a typical young
# adult on a weekday. Shapes follow when people do these things (American Time Use Survey; campus library and gym
# hours): mornings at home getting ready, campus through the day and into the evening, gyms early and after work,
# restaurants at lunch and dinner and little open after 1 am, friends' places and partners in the evening and late
# evening, the outdoors in daylight. Going-out options are read at (hour − shift·chronotype): a night owl's 11 pm is a
# typical person's 9:30. Interpolated between hours.
HOUR_CURVE = {
    O_HOME:    np.array([0.2, 0.2, 0.2, 0.2, 0.2, 0.3, 0.6, 0.6, 0.3, 0.0, 0.0, 0.0,
                         0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.1, 0.2]),
    O_CAMPUS:  np.array([-2.0, -2.0, -2.0, -2.0, -2.0, -2.0, -2.0, -0.5, -0.1, 0.2, 0.3, 0.3,
                         0.1, 0.2, 0.3, 0.3, 0.2, 0.0, -0.2, -0.3, -0.4, -0.6, -0.9, -1.3]),
    O_GYM:     np.array([-3.4, -3.4, -3.4, -3.4, -3.4, -1.4, -0.1, -0.1, -0.4, -0.5, -0.5, -0.4,
                         -0.4, -0.7, -0.7, -0.4, 0.0, 0.1, 0.0, -0.2, -0.5, -1.0, -1.6, -2.4]),
    # eating out: lunch and dinner peaks, a late-night food run; little in between
    O_FOOD:    np.array([-1.5, -2.1, -3.5, -4.0, -4.0, -3.5, -2.3, -1.9, -1.8, -1.9, -1.6, -0.6,
                         -0.1, -0.6, -1.4, -1.5, -1.1, -0.2, 0.0, -0.2, -0.5, -0.6, -0.9, -1.2]),
    O_OUT:     np.array([-2.4, -2.8, -3.2, -3.4, -3.4, -2.8, -1.8, -1.3, -1.0, -0.7, -0.6, -0.6,
                         -0.7, -0.7, -0.6, -0.6, -0.5, -0.5, -0.6, -0.8, -1.1, -1.4, -1.7, -2.0]),
    O_VISIT:   np.array([-1.4, -1.8, -2.4, -3.0, -3.5, -3.8, -4.0, -3.4, -2.8, -2.5, -2.3, -2.1,
                         -1.8, -1.7, -1.6, -1.5, -1.4, -1.2, -0.9, -0.7, -0.5, -0.4, -0.5, -0.9]),
    O_COMPLEX: np.array([-0.8, -1.3, -2.0, -2.6, -3.0, -3.0, -3.0, -2.6, -2.0, -1.6, -1.4, -1.2,
                         -1.0, -1.0, -0.9, -0.8, -0.6, -0.2, 0.1, 0.3, 0.4, 0.4, 0.2, -0.3]),
    O_PARTNER: np.array([0.0, -0.4, -1.0, -1.6, -2.2, -2.6, -3.0, -2.4, -1.8, -1.5, -1.3, -1.0,
                         -0.8, -0.7, -0.6, -0.5, -0.3, 0.0, 0.3, 0.5, 0.7, 0.8, 0.7, 0.4]),
}
SHIFTED = (O_FOOD, O_OUT, O_VISIT, O_COMPLEX, O_PARTNER)


def _wide(B, k: int) -> np.ndarray:
    """A k × 8 bias from another system (the options before sleep and partners existed) as k × NOPT."""
    B = np.asarray(B, np.float64)
    if B.ndim == 2 and B.shape[1] < NOPT:
        B = np.c_[B, np.zeros((B.shape[0], NOPT - B.shape[1]))]
    return np.broadcast_to(B, (k, NOPT))


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
        # class locations: a real teaching building per section building number (engine/places.py, campus.yaml)
        self.bldg = {1: np.c_[BYU[0] + rng.normal(0, 0.0028, 40), BYU[1] + rng.normal(0, 0.0022, 40)],
                     2: np.c_[UVU[0] + rng.normal(0, 0.0022, 24), UVU[1] + rng.normal(0, 0.0018, 24)]}
        self.bldg_id = {1: np.full(40, -1, np.int64), 2: np.full(24, -1, np.int64)}
        self.spots = {1: np.empty(0, np.int64), 2: np.empty(0, np.int64)}
        self.gyms = {1: np.empty(0, np.int64), 2: np.empty(0, np.int64)}
        if places.available():
            for s_ in (1, 2):
                c = places.campus(s_)
                if len(c["teaching"]):
                    self.bldg_id[s_] = c["teaching"]
                    self.bldg[s_] = np.array([places.anchor(int(b)) for b in c["teaching"]])
                self.spots[s_], self.gyms[s_] = c["spots"], c["gyms"]
        P.add_internal("shift_mask", np.uint32, 0)              # weekdays with a shift (bit = weekday)
        P.add_internal("dated_today", np.bool_, False)          # on a date at some hour today (emotion.daily reads it)
        P.add_internal("late_alone_h", np.float32, 0.0)         # late-night hours at a place with a partner (intimacy)
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
        self._prev = None                       # last hour's (choice, ctype, cid, act): what they're in the middle of
        self.cur_opt = np.full(P.n, NONE, np.uint8)       # the free-time option they're doing (NONE: not free last hour)
        self.cur_h = np.zeros(P.n, np.float32)           # hours they've been doing it
        self.class_sec = np.full(P.n, -1, np.int64)      # the class meeting they came to (attending it until it ends)
        self.together_h = np.zeros(P.n, np.float32)      # hours with their partner tonight, in a row
        self.past_curfew = np.zeros(P.n, bool)           # stayed past visiting hours tonight (recorded once)
        self.asleep_now = np.zeros(P.n, bool)

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
        if places.available() and spec.get("vtype") not in ("park", "trailhead", "overlook"):
            lo, la, _ = places.settle([float(spec["lon"])], [float(spec["lat"])])
            spec = {**spec, "lon": float(lo[0]), "lat": float(la[0])}
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
    def assign_shifts(self, ids: np.ndarray, stream: str = "shift_assign"):
        """A weekly shift pattern from usual work hours: which weekdays, start and end minutes.

        Students fit shifts into the gaps their classes leave (early-morning custodial shifts, between classes,
        afternoons, evenings until 10 pm, Saturdays); others work weekday days (full-time five days, part-time 3–7 hour
        shifts); about 5% of workers have a Sunday shift. The blocks a shift fills (`shift_mask`) follow from the
        minutes. Shares of start times are hypothetical. A user action passes a `stream` of its own."""
        sim = self.sim
        P = sim.w.P
        ids = np.atleast_1d(np.asarray(ids, np.int64))
        if not len(ids):
            return
        rng = sim.streams.gen(stream, sim.w.day, int(ids[0]) % 100003)
        k = len(ids)
        hours = np.clip(np.nan_to_num(P["work_hours"][ids].astype(np.float64)), 0, 70)
        student = P["enrolled"][ids].astype(bool)
        full = ~student & (hours >= 30)
        per = np.where(full, hours / 5.0, np.clip(rng.normal(np.where(student, 4.0, 5.0), 0.8), 2.5, 7.0))
        ndays = np.where(full, 5, np.clip(np.round(hours / per), 1, 6))
        ndays = np.where(hours > 0.5, ndays, 0).astype(int)
        per = np.where(ndays > 0, np.minimum(hours / np.maximum(ndays, 1), 12.0), 0.0)
        L = (np.round(per * 4) * 15).astype(np.int64)                    # shift length in minutes
        pref = np.zeros((k, 7))
        pref[:, 5] = np.where(student, 0.2, -1.5)
        pref[:, 6] = np.where(rng.random(k) < 0.05, 3.0, -50.0)
        pref[full, :5] += 5.0
        key = pref + rng.gumbel(size=(k, 7))
        rank = np.argsort(np.argsort(-key, axis=1), axis=1)
        works = rank < ndays[:, None]
        # candidate starts and how common each is (students / full-time / part-time / Saturday / Sunday)
        C = np.array([6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18]) * 60
        W = {"stu": [0.05, 0, 0.08, 0.05, 0.05, 0.05, 0.08, 0.1, 0.12, 0.12, 0.13, 0.11, 0.06],
             "ft": [0, 0.15, 0.45, 0.3, 0.1, 0, 0, 0, 0, 0, 0, 0, 0],
             "pt": [0, 0, 0.2, 0.25, 0.05, 0.1, 0.05, 0.1, 0.05, 0.05, 0.1, 0.05, 0],
             "sat_stu": [0, 0, 0.1, 0.25, 0.2, 0, 0.15, 0, 0, 0, 0.2, 0.1, 0], "sat": [0, 0.1, 0.4, 0.3, 0.2, 0, 0, 0, 0, 0, 0, 0, 0],
             "sun": [0, 0, 0, 0, 0.5, 0, 0.5, 0, 0, 0, 0, 0, 0]}
        logw = {kk: np.log(np.maximum(np.array(v, float), 1e-12)) for kk, v in W.items()}
        G = rng.gumbel(size=(k, 7, len(C)))
        base = np.where(student[:, None], logw["stu"], np.where(full[:, None], logw["ft"], logw["pt"]))      # k × C
        score = np.repeat(base[:, None, :], 7, axis=1)
        score[:, 5, :] = np.where(student[:, None], logw["sat_stu"], logw["sat"])
        score[:, 6, :] = logw["sun"]
        end_cap = np.where(student, 22 * 60, LATEST_END)
        cend = C[None, None, :] + L[:, None, None]
        score = np.where(cend <= end_cap[:, None, None], score, -np.inf)
        busy = self._class_busy(ids, L)                    # k × 7 × C: the shift would overlap a class
        score = np.where(busy, -np.inf, score)
        best = np.argmax(score + G, axis=2)
        okc = np.take_along_axis(score, best[..., None], axis=2)[..., 0] > -np.inf
        works &= okc
        start = C[best]
        end = np.minimum(start + L[:, None], LATEST_END)
        works &= (end - start) >= 90
        P.internal["shift_start"][ids] = np.where(works, start, -1).astype(np.int16)
        P.internal["shift_end"][ids] = np.where(works, end, -1).astype(np.int16)
        self._shift_mask(ids)

    def _class_busy(self, ids: np.ndarray, L: np.ndarray) -> np.ndarray:
        """For each person, weekday and candidate start (6 am … 6 pm): would a shift of L minutes overlap one of their
        classes (with 15 minutes to get between them)?"""
        P = self.sim.w.P
        C = np.array([6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18]) * 60
        out = np.zeros((len(ids), 7, len(C)), bool)
        acad = self.sim.systems.get("academics")
        if acad is None or not len(acad.sec_days) or acad.stu_secs.shape[0] <= int(ids.max()):
            return out
        secs = acad.stu_secs[ids]
        valid = (secs >= 0) & P["enrolled"][ids][:, None]
        s = np.maximum(secs, 0)
        days = acad.sec_days[s]
        cs, ce = self.class_times(s)
        for wd in range(5):
            meets = valid & ((days & np.uint8(1 << wd)) > 0)                        # k × 5
            st = C[None, :, None]
            en = st + L[:, None, None]
            hit = meets[:, None, :] & (cs[:, None, :] < en + 15) & (ce[:, None, :] + 15 > st)
            out[:, wd, :] = hit.any(axis=2)
        return out

    def class_times(self, secs) -> tuple[np.ndarray, np.ndarray]:
        """Clock times of class sections inside their block (for shifts, plans and agendas; who is where is still
        resolved per block). Real sections (BYU Fall and Winter, UVU Fall) at their scheduled times. Drawn ones: morning
        sections start on the hour 8–11, afternoon ones 1–4 pm, evening ones 5:30 or 6:30 pm; MWF classes run 50
        minutes, Tuesday/Thursday 75, evening 110 — the usual BYU/UVU pattern, assigned by section number (no random
        draws)."""
        acad = self.sim.systems["academics"]
        secs = np.maximum(np.asarray(secs, np.int64), 0)
        blk = acad.sec_block[secs].astype(np.int64)
        start = np.select([blk == 0, blk == 1], [8 * 60 + 60 * (secs % 4), 13 * 60 + 60 * (secs % 4)],
                          17 * 60 + 30 + 60 * (secs % 2))
        mwf = acad.sec_days[secs] == 0b10101
        dur = np.where(blk == 2, 110, np.where(mwf, 50, 75))
        end = start + dur
        if len(acad.sec_start) == len(acad.sec_block):           # real sections keep their own times
            rs, re_ = acad.sec_start[secs].astype(np.int64), acad.sec_end[secs].astype(np.int64)
            start, end = np.where(rs >= 0, rs, start), np.where(rs >= 0, re_, end)
        return start.astype(np.int32), end.astype(np.int32)

    def _after_classes(self, ids: np.ndarray) -> np.ndarray:
        """Earliest shift start per weekday for students: 15 minutes after their last class that day ends."""
        acad = self.sim.systems.get("academics")
        out = np.zeros((len(ids), 7), np.int64)
        if acad is None or not len(acad.sec_days) or acad.stu_secs.shape[0] <= int(ids.max()):
            return out
        secs = acad.stu_secs[ids]
        valid = secs >= 0
        s = np.maximum(secs, 0)
        days = acad.sec_days[s]
        _, cend = self.class_times(s)
        for wd in range(5):
            meets = valid & ((days & np.uint8(1 << wd)) > 0)
            last = np.where(meets, cend, -1).max(axis=1)
            out[:, wd] = np.where(last >= 0, last + 15, 0)
        return out

    def _shift_mask(self, ids: np.ndarray):
        """Weekdays with a shift (bit = weekday); which hours it fills follows from its minutes (`shift_minutes`)."""
        P = self.sim.w.P
        s = P.internal["shift_start"][ids]
        m = np.zeros(len(ids), np.uint32)
        for wd in range(7):
            m |= np.where(s[:, wd] >= 0, np.uint32(1 << wd), np.uint32(0))
        P.internal["shift_mask"][ids] = m

    def shift_minutes(self, b: int, wd: int) -> np.ndarray:
        """Minutes of each person's shift inside hour b today (0 without a shift or a job)."""
        P = self.sim.w.P
        n = P.n
        s = P.internal["shift_start"][:n, wd].astype(np.int32)
        e = P.internal["shift_end"][:n, wd].astype(np.int32)
        mins = np.clip(np.minimum(e, clock.END[b]) - np.maximum(s, clock.START[b]), 0, None)
        return np.where((s >= 0) & P["employed"], mins, 0)

    def _grow(self, n: int):
        """Per-person hour-to-hour memory (what they're in the middle of), grown with the population."""
        if len(self.cur_opt) < n:
            k = n - len(self.cur_opt)
            self.cur_opt = np.r_[self.cur_opt, np.full(k, NONE, np.uint8)]
            self.cur_h = np.r_[self.cur_h, np.zeros(k, np.float32)]
            self.class_sec = np.r_[self.class_sec, np.full(k, -1, np.int64)]
            self.together_h = np.r_[self.together_h, np.zeros(k, np.float32)]
            self.past_curfew = np.r_[self.past_curfew, np.zeros(k, bool)]

    # ------------------------------------------------------------------ main
    def choose(self, b: int):
        """Where everyone is in hour b: in bed, then commitments (church, class, a shift, occasions they said yes to,
        FHE and ward activities, clubs), then a free-time choice for everyone left, sleep included."""
        sim, w = self.sim, self.sim.w
        P, env = w.P, w.env
        n = P.n
        wd = env["weekday"]
        p = sim.p
        self._grow(n)
        I = P.internal
        present = P["present"]
        ctype = np.full(n, NONE, np.uint8)
        cid = np.full(n, -1, np.int64)
        act = np.full(n, A["away"], np.uint8)
        share = np.full(n, clock.LEGACY_SHARE[b], np.float32)   # how much of an old five-hour block they spend there
        unit = P["unit_id"]
        home_ok = present & (unit >= 0)
        ctype[home_ok] = CTX_ID["unit"]
        cid[home_ok] = unit[home_ok]
        act[home_ok] = A["home"]
        busy = ~present.copy()
        u = sim.u(f"activity{b}")
        occ = sim.systems["occasions"]
        plan = occ.block_plan(b)          # who is expected at which occasion in this hour (dates, dinners, dances…)
        sleep = sim.systems["sleep"]
        # ---- in bed (asleep, or lying awake trying to sleep): at home, out of reach until they get up
        resting = sleep.step(b) & present
        act[resting & home_ok] = A["sleep"]
        busy |= resting
        self.asleep_now = resting
        # ---- church (Sunday, the ward's two-hour block)
        if wd == 6:
            f = sim.systems["faith"]
            ms = f.meeting_start(np.arange(n))
            mins = clock.overlap(ms, 120, b)
            now = mins >= 30
            for att, ctxn, col in ((f.attending_today, "ward", "ward_id"), (f.attending_other, "congregation", "congregation_id")):
                go = att[:n] & now & present & ~busy
                ctype[go] = CTX_ID[ctxn]
                cid[go] = P[col][go]
                act[go] = A["church"]
                share[go] = mins[go] / 120
                busy |= go
        # occasions they're expected at in this hour (minutes there)
        occ_min = np.zeros(n, np.int32)
        if len(plan["person"]):
            np.maximum.at(occ_min, plan["person"], plan["minutes"])
        # ---- class: attendance is decided as the class starts (and then they're there for all of it)
        acad = sim.systems["academics"]
        if wd < 5 and not env["holiday"]:
            sec_now, first = acad.meeting_now(wd, b)
            has = sec_now >= 0
            cm = np.zeros(n, np.int32)
            cdur = np.ones(n, np.int32)
            if has.any():
                cs_, ce_ = self.class_times(sec_now[has])
                cm[has] = clock.overlap(cs_, ce_ - cs_, b)
                cdur[has] = np.maximum(ce_ - cs_, 1)
                # an occasion that fills more of the hour than the class shows instead (the class still happened)
                sec_now = np.where(occ_min > cm, -1, sec_now)
            sched = (sec_now >= 0) & present & ~P["ill"]
            start = sched & first
            if start.any():
                self._class_start(start, sec_now, busy, resting, b, wd, u)
            in_class = sched & ~busy & (self.class_sec[:n] == sec_now)
            ctype[in_class] = CTX_ID["class"]
            cid[in_class] = sec_now[in_class]
            act[in_class] = A["class"]
            share[in_class] = cm[in_class] / cdur[in_class]
            busy |= in_class
        # ---- work shifts and occasions: whichever fills more of this hour
        shift_min = self.shift_minutes(b, wd)
        blen = int(clock.END[b] - clock.START[b])
        on_shift = ((shift_min >= 30) & (shift_min >= occ_min) & present & ~busy & P["employed"]
                    & ~P["ill"] & (not env["holiday"]))
        ctype[on_shift] = CTX_ID["work"]
        cid[on_shift] = P["employer_id"][on_shift]
        act[on_shift] = A["work"]
        share[on_shift] = clock.LEGACY_SHARE[b] * np.minimum(shift_min[on_shift] / blen, 1.0)
        busy |= on_shift
        if len(plan["person"]):
            pp = plan["person"]
            ok = ~busy[pp] & (plan["minutes"] >= occ_min[pp])
            ok[ok] &= ~np.r_[False, (pp[ok][1:] == pp[ok][:-1])]          # one occasion per person per hour
            pp = pp[ok]
            ctype[pp] = plan["ctx"][ok]
            cid[pp] = plan["occ"][ok]
            act[pp] = plan["act"][ok]
            share[pp] = plan["share"][ok]
            busy[pp] = True
            # everyone expected at an occasion in this hour went: it was fitted around their shift, classes and other
            # plans, so a date right after a shift, or a party after a dinner, counts as attended even when something
            # else fills more of the hour (the hour's place is the one that fills most of it); asleep, they missed it
            there = present[plan["person"]] & ~resting[plan["person"]]
            occ.mark_present(b, plan["person"][there], plan["occ"][there], plan["arrive"][there])
        # ---- FHE (Monday 7 pm) and ward activities (weeknights 7 pm), in term
        if wd in (0, 1, 2, 3) and (env["term_BYU"] or env["term_UVU"]):
            mins = int(clock.overlap(19 * 60, 90, b))
            if mins >= 30:
                ud = sim.u("ward_evening")             # one draw for the evening: there for all of it or none
                if wd == 0:
                    fhe = I["fhe_group"][:n]
                    go = (fhe >= 0) & present & ~busy & (ud < P["ward_activity_rate"] * p("activity.fhe.attend_mult"))
                    ctype[go] = CTX_ID["fhe"]
                    cid[go] = fhe[go]
                else:
                    ward = P["ward_id"]
                    go = (ward >= 0) & ((ward % 3) + 1 == wd) & present & ~busy & (ud < P["ward_activity_rate"] * p("activity.ward_activity.attend_mult"))
                    ctype[go] = CTX_ID["ward"]
                    cid[go] = ward[go]
                act[go] = A["ward_activity"]
                share[go] = mins / 90
                busy |= go
        # ---- clubs, intramural teams and institute classes (weekly, in term, at their meeting times)
        free_now = present & ~busy
        met = sim.systems["groups"].meeting(b, wd, free_now, sim.u("group_attend"))
        G = w.groups
        for (gids, gid), name in zip(met, ("team", "club", "institute")):
            ctype[gids] = CTX_ID[name]
            cid[gids] = gid
            act[gids] = A["class"] if name == "institute" else A["club"]
            if len(gids):
                gs, gd = G["start"][gid].astype(np.int64), np.maximum(G["dur"][gid].astype(np.int64), 1)
                share[gids] = clock.overlap(gs, gd, b) / gd
            busy[gids] = True
        # ---- free time
        self.gathering_units = set()
        self.host_of_unit = {}
        free = present & ~busy
        self.last_choice = np.full(n, NONE, np.uint8)
        if free.any():
            self._discretionary(free, b, wd, ctype, cid, act, resting)
        # household members at home (and friends who dropped by) join a home occasion held in their apartment
        occ.walk_ins(b, ctype, cid, act, share)
        # what they're in the middle of: an outing carried on from last hour is not a new one (counted once)
        fresh = None
        if self._prev is not None and len(self._prev[1]) == n:
            fresh = ~((self._prev[1] == ctype) & (self._prev[2] == cid) & (self._prev[3] == act))
        same = self.last_choice == self.cur_opt[:n]
        self.cur_h[:n] = np.where(free & same, self.cur_h[:n] + 1, np.where(free, 1, 0)).astype(np.float32)
        self.cur_opt[:n] = np.where(free, self.last_choice, NONE)
        self._prev = (self.last_choice.copy(), ctype.copy(), cid.copy(), act.copy())
        self.ctype, self.cid, self.ctx_share = ctype, cid, share
        self.asleep_now = sleep.resting() & present
        P["activity_now"] = act
        I["dated_today"][:n] |= act == A["date"]
        # up and out (or up with people) after midnight: a late night
        if clock.PART[b] == 4:
            out = present & ~self.asleep_now & ((ctype != CTX_ID["unit"]) | (cid != unit) | (act == A["with_partner"])
                                                 | (act == A["gathering"]))
            I["out_late"][:n] |= out
        sim.systems["mind"].observe_block(act, ctype, fresh=fresh, social=occ.social_now(ctype, cid))
        rt = sim.systems.get("routine")
        if rt is not None:
            rt.observe(b, wd, free, self.last_choice)
        self._locate(ctype, cid, act)
        self._keep_frame(b)

    def _class_start(self, start: np.ndarray, sec_now: np.ndarray, busy: np.ndarray, resting: np.ndarray, b: int,
                     wd: int, u: np.ndarray):
        """A class meeting starts this hour: who goes. Asleep, they missed it (overslept); otherwise the usual
        attendance odds, lowered when something else pulls harder right now (in the middle of time with a partner or
        friends: activity.skip)."""
        sim = self.sim
        P, p = sim.w.P, sim.p
        n = P.n
        acad = sim.systems["academics"]
        idx = np.flatnonzero(start & ~busy)
        T = {"base": np.full(len(idx), p("activity.class_attendance.base")),
             "conscientious": p("activity.class_attendance.conscientiousness") * sim.z("conscientiousness")[idx],
             "tired": -p("activity.class_attendance.fatigue") * P["fatigue"][idx],
             "pressure": 0.8 * P["academic_pressure"][idx],
             "depressed": -0.6 * P["depressive_episode"][idx],
             "coping": np.asarray(sim.systems["coping"].attend_bias(), np.float64)[idx]}
        better = np.zeros(len(idx))
        best = np.full(len(idx), NONE, np.uint8)
        if len(idx):
            U, avail = self._utilities(idx, b, wd, busy=busy | start)
            Um = np.where(avail, U, -9.0)
            best = np.argmax(Um, axis=1).astype(np.uint8)
            ref = np.maximum(Um[:, O_HOME], np.where(avail[:, O_CAMPUS], Um[:, O_CAMPUS], -9.0))
            better = np.clip(Um.max(axis=1) - ref, 0, None)
            T["better_offer"] = -p("activity.skip.pull") * better
        L = sum(T.values())
        go = u[idx] < expit(L)
        self.class_sec[idx[go]] = sec_now[idx[go]]
        self.class_sec[idx[~go]] = -1
        # asleep as it starts: overslept (an alarm set and slept through) or never planned to get up
        slept = np.flatnonzero(start & resting)
        self.class_sec[slept] = -1
        sched = start.copy()
        att = np.zeros(n, bool)
        att[idx[go]] = True
        acad.record_attendance(sched, att)
        I = P.internal
        over = slept[I["alarm_for"][slept] >= 0]
        if len(over):
            sim.emit("overslept", over, mech="sleep.wake", block=int(clock.PART[b]))
        # skipped for someone: recorded, with the partner or friend they stayed with
        social = np.isin(best, (O_PARTNER, O_VISIT, O_FOOD, O_OUT))
        sk = ~go & (better > 1.0) & social
        if sk.any():
            who = idx[sk]
            did = sim.decisions.record("skip_class", sim.w.day, who, "skipped", {k: v[sk] for k, v in T.items()},
                                       base=0.0, prob=1 - expit(L[sk]), block=int(clock.PART[b]))
            pid = P["partner_id"][who].astype(np.int64)
            with_ = np.where(best[sk] == O_PARTNER, pid, -1)
            sim.emit("skipped_class", who, b=with_, mech="activity.skip", block=int(clock.PART[b]), decision=did)

    def _keep_frame(self, b: int, ctype=None, cid=None):
        """Positions at each hour of the day, kept for the map's day replay; and the latest hour's full snapshot
        (contexts, homes, rooms) for precise placement (engine/placement.py), which pages read without waiting for the
        day in progress."""
        P = self.sim.w.P
        if not hasattr(self, "frames_today"):
            self.frames_today, self.day_frames = {}, {}
        if b == 0:
            self.frames_today = {}
        self.frames_today[b] = (P["loc_lon"].astype(np.float32), P["loc_lat"].astype(np.float32),
                                P["activity_now"].astype(np.uint8))
        from .. import placement
        snap = {**placement.frame(self.sim, self.ctype if ctype is None else ctype, self.cid if cid is None else cid), "block": b}
        self.snapshot = snap                            # replaced whole, never edited: safe to read while time runs
        if not hasattr(self, "snaps_today") or b == 0:
            self.snaps_today = {}
        self.snaps_today[b] = snap

    def night(self):
        """6 am, the end of the simulated day: the day's hours become the last full day (the map's replay)."""
        if len(getattr(self, "frames_today", {})) == clock.N_BLOCKS:
            self.day_frames = {"day": self.sim.w.day, **self.frames_today}
        if len(getattr(self, "snaps_today", {})) == clock.N_BLOCKS:
            self.day_snaps = self.snaps_today            # the last full day, hour by hour (the map's live glide)
        self.frames_today, self.snaps_today = {}, {}

    def _drives(self):
        """(approach, withdraw, style): the connection drive split into reaching out vs pulling back (mind.social_pull)."""
        return self.sim.systems["mind"].social_pull()

    # ------------------------------------------------------------------ free time
    def _hour_terms(self, idx: np.ndarray, b: int, wd: int) -> np.ndarray:
        """k × NOPT time-of-day utility: each option's 24-hour curve, read later in the day for night owls (going out
        options), an hour later on Friday and Saturday nights."""
        sim, P = self.sim, self.sim.w.P
        p = sim.p
        hour = clock.HOUR[b] + 0.5
        tau = P["chronotype"][idx].astype(np.float64)
        # Friday and Saturday nights (the small hours belong to the evening before them)
        late = p("activity.hourly.weekend_later") if (wd in (4, 5) and clock.PART[b] >= 2) else 0.0
        out = np.zeros((len(idx), NOPT))
        for c, tab in HOUR_CURVE.items():
            if c in SHIFTED:
                out[:, c] = curve(tab, hour - p("activity.hourly.shift") * tau - late)
            else:
                out[:, c] = curve(tab, np.full(len(idx), hour))
        return p("activity.hourly.hour_weight") * np.nan_to_num(out, nan=0.0)

    def _utilities(self, idx: np.ndarray, b: int, wd: int, explain: bool = False, busy: np.ndarray | None = None):
        """Free-time option utilities (k × NOPT) for `idx` in hour b, with which options are open; with `explain`, also
        the terms that were summed, as {term: (label, k × NOPT contribution)}. `busy` marks people not free this hour
        (a partner who is busy can't spend it with them)."""
        sim, w = self.sim, self.sim.w
        P, env, p = w.P, w.env, sim.p
        I = P.internal
        k = len(idx)
        n = P.n
        terms: dict[str, tuple[str, np.ndarray]] = {}
        U = np.zeros((k, NOPT))            # options nobody can take now are set to -9 at the end
        avail = np.zeros((k, NOPT), bool)

        def add(name, label, col, val, where=None):
            v = val if where is None else np.where(where, val, 0.0)
            U[:, col] += v
            if explain:
                if name not in terms:
                    terms[name] = (label, np.zeros((k, NOPT)))
                terms[name][1][:, col] += v

        def open_(col, where=True):
            m = np.broadcast_to(np.asarray(where, bool), (k,))
            avail[:, col] |= m
            return m

        hour = int(clock.HOUR[b])
        appr, withdraw, _ = self._drives()
        appr, withdraw = appr[idx], withdraw[idx]
        E = sim.z("extraversion")[idx]
        weekend = 1.0 if wd >= 4 else 0.0
        enrolled = P["enrolled"][idx]
        in_term = np.where(P["school"][idx] == 1, bool(env["term_BYU"]), bool(env["term_UVU"]))
        married = P.is_("rel_status", "married")[idx]
        engaged = P.is_("rel_status", "engaged")[idx]
        dating = P.is_("rel_status", "dating")[idx]
        couple = np.where(engaged, p("occasions.couple.engaged"), np.where(dating, p("occasions.couple.dating"), 0.0))
        HT = self._hour_terms(idx, b, wd)
        # habit/trait bases plus the person's current drives (mind.choice): rest pulls home, achievement to campus,
        # fitness to the gym, fun to venues and the outdoors, connection to friends
        d = {m: P[f"drive_{m}"][idx] for m in ("rest", "achievement", "health", "fun", "partnership")}
        wgt = {m: p(f"mind.choice.{m}") for m in d}
        open_(O_HOME)
        add("base", "how much people stay in", O_HOME, p("activity.choice.home"))
        add("rest", "needs rest", O_HOME, wgt["rest"] * d["rest"])
        add("withdraw", "pulling back from people", O_HOME, p("activity.choice.withdraw") * withdraw)
        add("married", "married (home life)", O_HOME, 0.6 * married)
        add("children", "has children", O_HOME, 0.3 * (P["children"][idx] > 0))
        add("ill", "sick", O_HOME, 0.8 * P["ill"][idx])
        add("hour", "time of day", O_HOME, HT[:, O_HOME])
        # campus: libraries and study spaces open 7 am to midnight, closed on Sunday
        if 7 <= hour <= 23 and wd != 6:
            m = open_(O_CAMPUS, enrolled & in_term)
            add("base", "studying on campus", O_CAMPUS, 0.5, m)
            add("achievement", "school & career drive", O_CAMPUS, wgt["achievement"] * d["achievement"], m)
            add("conscientious", "conscientiousness", O_CAMPUS, 0.3 * sim.z("conscientiousness")[idx], m)
            add("far", "lives far from campus", O_CAMPUS, -0.25 * (P["dist_campus_km"][idx] > 3), m)
            add("hour", "time of day", O_CAMPUS, HT[:, O_CAMPUS], m)
        open_(O_GYM)
        add("habit", "workout habit", O_GYM, -2.3 + np.log(P["workouts_week"][idx] + 0.3))
        add("hour", "time of day", O_GYM, HT[:, O_GYM])
        add("health", "fitness drive", O_GYM, wgt["health"] * d["health"])
        open_(O_FOOD)
        add("base", "eating out", O_FOOD, -1.6 + 0.5 * np.log1p(I["eat_out_month"][idx] + 3 * P["soda_shop_week"][idx]))
        add("approach", "wants company", O_FOOD, p("activity.choice.approach") * 0.6 * appr)
        add("weekend", "weekend", O_FOOD, 0.3 * weekend)
        add("fun", "fun drive", O_FOOD, wgt["fun"] * 0.6 * d["fun"])
        add("hour", "time of day (what's open)", O_FOOD, HT[:, O_FOOD])
        open_(O_OUT)
        add("base", "loves the outdoors", O_OUT, -2.6 + 1.0 * P["hikes"][idx] + 0.4 * P["outdoors"][idx])
        add("weather", "the weather", O_OUT, 1.6 * env["outdoor_appeal"])
        add("weekend", "weekend", O_OUT, 0.6 * weekend)
        add("fun", "fun drive", O_OUT, wgt["fun"] * d["fun"] + 0.5 * wgt["health"] * d["health"])
        # after dark the outdoors is for the adventurous (a midnight hike up Y Mountain, stargazing)
        dark = np.minimum(HT[:, O_OUT], 0.0)
        add("hour", "time of day (daylight)", O_OUT, HT[:, O_OUT] - 0.3 * dark * np.clip(sim.z("sensation_seeking")[idx], -1, 2))
        has_f = P["n_friends"][idx] > 0
        m = open_(O_VISIT, has_f)
        add("base", "dropping by a friend's place", O_VISIT, -1.2, m)
        add("approach", "wants company", O_VISIT, p("activity.choice.approach") * appr, m)
        add("extraversion", "outgoing", O_VISIT, 0.35 * E, m)
        add("weekend", "weekend", O_VISIT, 0.5 * weekend, m)
        add("married", "married (home life)", O_VISIT, -0.5 * married, m)
        add("partner", "evenings with their partner", O_VISIT, -0.5 * couple, m)
        add("hour", "time of day", O_VISIT, HT[:, O_VISIT], m)
        m = open_(O_COMPLEX, P["complex_id"][idx] >= 0)
        add("base", "hanging out around the complex", O_COMPLEX, -2.0, m)
        add("extraversion", "outgoing", O_COMPLEX, 0.4 * E, m)
        add("approach", "wants company", O_COMPLEX, 0.5 * appr, m)
        add("culture", "a social complex", O_COMPLEX, p("culture.feedback.reputation") * sim.systems["culture"].complex_social_z(P["complex_id"][idx]), m)
        add("partner", "evenings with their partner", O_COMPLEX, -0.5 * couple, m)
        add("hour", "time of day", O_COMPLEX, HT[:, O_COMPLEX], m)
        # sleep (engine/systems/sleep.py): pressure, body clock, tomorrow's alarm, tiredness
        open_(O_SLEEP)
        add("sleep", "sleepiness (hours up, body clock, tomorrow)", O_SLEEP, sim.systems["sleep"].utility(idx, b))
        # time with a partner: both free and awake
        pid = P["partner_id"][idx].astype(np.int64)
        okp = (dating | engaged) & (pid >= 0) & (pid < n)
        if okp.any():
            ps = np.maximum(pid, 0)
            okp &= P["present"][ps] & ~self.asleep_now[ps]
            if busy is not None:
                okp &= ~busy[ps]
        m = open_(O_PARTNER, okp)
        if m.any():
            add("base", "time with their partner", O_PARTNER, p("activity.partner.base"), m)
            add("couple", "how much couples like them spend together", O_PARTNER, couple, m)
            add("partnership", "wanting time with them", O_PARTNER, p("activity.partner.drive") * d["partnership"], m)
            add("hour", "time of day", O_PARTNER, HT[:, O_PARTNER], m)
        if wd == 6:
            # the Sabbath: members who go to church keep Sunday quieter — fewer restaurants and outings, more apartments
            keep = P["lds_member"][idx] * np.clip(I["attend_prob"][idx], 0, 1)
            add("sunday", "keeping the Sabbath", O_FOOD, p("activity.choice.sunday_out") * keep)
            add("sunday", "keeping the Sabbath", O_OUT, 0.5 * p("activity.choice.sunday_out") * keep)
            add("sunday", "keeping the Sabbath", O_GYM, 0.5 * p("activity.choice.sunday_out") * keep)
            add("sunday", "Sunday at friends' places", O_VISIT, p("activity.choice.sunday_hangout") * keep, has_f)
            add("sunday", "Sunday at friends' places", O_COMPLEX, p("activity.choice.sunday_hangout") * keep, P["complex_id"][idx] >= 0)
        # dances are planned events (open occasions in systems/occasions.py), not a free-time option
        for name, label, bias in (("routine", "habit (what they usually do then)", "routine"), ("coping", "coping with a hard stretch", "coping"),
                                  ("intention", "an intention (meeting people)", "plans")):
            s = sim.systems.get(bias)
            if s is None:
                continue
            B = _wide(s.bonus(idx, wd, b) if bias == "routine" else s.choice_bias(idx), k)
            B = np.where(avail, B, 0.0)
            U += B
            if explain:
                terms[name] = (label, B)
        wb = sim.whatif.choice_bias(idx)          # a What-if's nudges on free-time choices, only on options that exist
        if not np.isscalar(wb):
            wb = np.where(avail, _wide(wb, k), 0.0)
            U += wb
            if explain:
                terms["whatif"] = ("the What-if's nudge", wb)
        # carrying on with what they're in the middle of (the same friend's place, the same venue, the same partner):
        # strong at first, fading once it has run its usual length
        if len(self.cur_opt) >= n:
            cur = self.cur_opt[idx]
            cont = (cur != NONE) & (cur < NOPT)
            if cont.any():
                r = np.flatnonzero(cont)
                c = cur[cont].astype(np.int64)
                hrs = self.cur_h[idx][cont]
                usual = USUAL_H[c]
                val = np.where(c == O_HOME, p("activity.hourly.carry_on_home"),
                               p("activity.hourly.carry_on") - p("activity.hourly.satiation") * np.clip(hrs - usual, 0, None))
                val = np.where(c == O_SLEEP, 0.0, val)
                C = np.zeros((k, NOPT))
                C[r, c] = val
                C = np.where(avail, C, 0.0)
                U += C
                if explain:
                    terms["continue"] = ("carrying on with what they're doing", C)
                # visiting hours: a guest in an opposite-sex BYU-contracted apartment after hours
                V = self._visiting_hours(idx, b, wd, cur)
                if V is not None:
                    V = np.where(avail, V, 0.0)
                    U += V
                    if explain:
                        terms["visiting_hours"] = ("visiting hours (and the heat of the moment)", V)
        for col, grp in ((O_FOOD, "food"), (O_OUT, "outdoors")):
            if grp in self.empty_groups:
                U[:, col] = -9
                avail[:, col] = False
        if "gym" in self.empty_groups:
            U[~enrolled, O_GYM] = -9
            avail[~enrolled, O_GYM] = False
        avail[:, O_DANCE] = False
        U[~avail] = -9.0
        return (U, avail, terms) if explain else (U, avail)

    def curfew(self, wd: int) -> int:
        """Visiting hours end (minute of the day): midnight, 1:30 am on Friday nights (config/policies/campus.yaml)."""
        return 25 * 60 + 30 if wd == 4 else 24 * 60

    def _guest_at(self, idx: np.ndarray, place_unit: np.ndarray) -> np.ndarray:
        """Guests in an opposite-sex apartment in BYU-contracted housing (not their own home)."""
        P, U = self.sim.w.P, self.sim.w.units
        pu = np.maximum(place_unit, 0)
        sexr = U.sex_restriction[pu]
        female = P.is_("sex", "F")[idx]
        opp = ((sexr == 1) & ~female) | ((sexr == 2) & female)
        return (place_unit >= 0) & (place_unit != P["unit_id"][idx]) & U.contracted[pu] & opp

    def _visiting_hours(self, idx, b, wd, cur):
        """k × NOPT: for guests staying on in an opposite-sex contracted apartment past visiting hours, the pull to
        leave on staying (policy.visiting_hours): rule-keeping against, the heat of the moment for a partner."""
        sim = self.sim
        P, p = sim.w.P, sim.p
        if int(clock.END[b]) <= self.curfew(wd) or self._prev is None or len(self._prev[1]) < len(self.cur_opt[: P.n]):
            return None
        stay = np.isin(cur, (O_VISIT, O_PARTNER)) & (self._prev[1][idx] == CTX_ID["unit"])
        if not stay.any():
            return None
        guest = stay & self._guest_at(idx, np.where(stay, self._prev[2][idx], -1))
        if not guest.any():
            return None
        r = np.flatnonzero(guest)
        g = idx[r]
        z = sim.z
        rule = p("policy.visiting_hours.rule") * np.clip(1 + z("conformity")[g] + 0.5 * P["religious_identity"][g]
                                                         + 0.5 * z("self_control")[g], 0, None)
        heat = np.zeros(len(g))
        partner = cur[r] == O_PARTNER
        if partner.any():
            gp = g[partner]
            pid = np.maximum(P["partner_id"][gp].astype(np.int64), 0)
            att = self._attraction(gp, pid)
            drive = (P["sex_drive"][gp].astype(np.float64) - 2) / 1.2
            heat[partner] = (p("policy.visiting_hours.heat") * np.clip(drive + att + 0.25 * self.together_h[gp], 0, None)
                             * np.clip(1 - 0.3 * z("self_control")[gp], 0.3, 2.0))
        V = np.zeros((len(idx), NOPT))
        V[r, cur[r].astype(np.int64)] = -rule + heat
        return V

    def _attraction(self, a: np.ndarray, b: np.ndarray) -> np.ndarray:
        from ..state import EdgeStore
        E = self.sim.w.E
        e = E.find(EdgeStore.make_keys(a, b))
        out = np.zeros(len(a))
        ok = e >= 0
        if ok.any():
            out[ok] = np.clip(E.attraction_from(e[ok], a[ok]), -1, 1)
        return out

    def _campus_place(self, school: np.ndarray, pick: np.ndarray, table: dict) -> np.ndarray:
        """Which real campus building (a spot or a gym, by weight) each person goes to: a building id; the school code
        (1, 2) when the building layer is missing."""
        out = school.astype(np.int64).copy()
        for s_ in (1, 2):
            t = table[s_]
            m = school == s_
            if len(t) and m.any():
                out[m] = t[np.minimum((pick[m] * len(t)).astype(np.int64), len(t) - 1)]
        return out

    def _campus_point(self, code: np.ndarray):
        """lon/lat of campus places coded as `_campus_place` returns them."""
        code = np.asarray(code, np.int64)
        lon = np.where(code == 1, BYU[0], UVU[0]).astype(float)
        lat = np.where(code == 1, BYU[1], UVU[1]).astype(float)
        bl = code > 2
        if bl.any():
            u, inv = np.unique(code[bl], return_inverse=True)
            pts = np.array([places.anchor(int(b)) for b in u])
            lon[bl], lat[bl] = pts[inv.ravel(), 0], pts[inv.ravel(), 1]
        return lon, lat

    def _discretionary(self, free, b, wd, ctype, cid, act, resting):
        """The free-time choice for everyone free this hour, then the parts that take two: time with a partner (both
        free, the other willing), a visit (to a friend who is home and up), and asking someone along on an outing."""
        sim, w = self.sim, self.sim.w
        P, p = w.P, sim.p
        n = P.n
        idx = np.flatnonzero(free)
        U, avail = self._utilities(idx, b, wd, busy=~free)
        g = sim.streams.gen(f"disc{b}", w.day).gumbel(size=(P.n, NOPT))[idx]
        V = U + g
        choice = np.argmax(V, axis=1)
        pos = np.full(n, -1, np.int64)
        pos[idx] = np.arange(len(idx))
        pick = sim.u(f"pick{b}")[idx]
        hl, ht = P["home_lon"][idx], P["home_lat"][idx]
        prev = self._prev if (self._prev is not None and len(self._prev[0]) == n) else None
        cur = self.cur_opt[idx]

        def second_best(rows, also=()):
            W = V[rows].copy()
            W[np.arange(len(rows)), choice[rows]] = -np.inf
            for c in (O_PARTNER, *also):
                W[:, c] = -np.inf
            W[~avail[rows]] = -np.inf
            return np.argmax(W, axis=1)

        # ---- time with a partner: both pick it, or the other is willing (their pull toward it beats their own pick)
        host = np.full(len(idx), -1, np.int64)
        m = np.flatnonzero(choice == O_PARTNER)
        if len(m):
            me = idx[m]
            pid = P["partner_id"][me].astype(np.int64)
            pj = pos[np.clip(pid, 0, n - 1)]
            agree = (pid >= 0) & (pj >= 0)
            if agree.any():
                r = np.flatnonzero(agree)
                jj = pj[r]
                theirs = choice[jj]
                agree[r] = (theirs == O_PARTNER) | (avail[jj, O_PARTNER] & (V[jj, O_PARTNER] + p("activity.together.partner") >= V[jj, theirs]))
            a_, j_, ja = me[agree], pid[agree], pj[agree]
            choice[ja] = O_PARTNER
            # hosted at her place (the lower id's, for same-sex couples); carrying on where they already were
            fem = P.is_("sex", "F")
            hostp = np.where(fem[a_] & ~fem[j_], a_, np.where(fem[j_] & ~fem[a_], j_, np.minimum(a_, j_)))
            hu = P["unit_id"][hostp].astype(np.int64)
            if prev is not None:
                was = (prev[3][a_] == A["with_partner"]) & (prev[1][a_] == CTX_ID["unit"]) & (prev[2][a_] >= 0)
                hu = np.where(was, prev[2][a_], hu)
            host[m[agree]] = hu
            host[ja] = hu
            no = m[~agree]
            if len(no):
                choice[no] = second_best(no)
        nohost = np.flatnonzero((choice == O_PARTNER) & (host < 0))
        if len(nohost):
            choice[nohost] = O_HOME
        # ---- visits: to a friend who is home (staying in this hour) and up, or carrying on at the same place
        dest = np.full(len(idx), -1, np.int64)
        friend = np.full(len(idx), -1, np.int64)
        stay = np.zeros(len(idx), bool)
        m = np.flatnonzero(choice == O_VISIT)
        if len(m):
            vis = idx[m]
            ok = np.zeros(len(m), bool)
            if prev is not None:
                s_ = (cur[m] == O_VISIT) & (prev[1][vis] == CTX_ID["unit"]) & (prev[2][vis] >= 0) & (prev[2][vis] != P["unit_id"][vis])
                dest[m[s_]] = prev[2][vis][s_]
                stay[m[s_]] = True
                ok |= s_
            net = sim.systems["network"]
            for t in range(2):
                need = np.flatnonzero(~ok)
                if not len(need):
                    break
                f = net.random_neighbor(vis[need], (pick[m][need] + 0.37 * t) % 1.0, min_stage=2)
                fs = np.maximum(f, 0)
                good = (f >= 0) & P["present"][fs] & (P["unit_id"][fs] >= 0) & ~self.asleep_now[fs] & (f != vis[need])
                fp = pos[fs]
                good &= (fp >= 0) & (choice[np.maximum(fp, 0)] == O_HOME)
                r = need[good]
                dest[m[r]] = P["unit_id"][fs[good]]
                friend[m[r]] = f[good]
                ok[r] = True
            no = m[~ok]
            if len(no):
                choice[no] = second_best(no, also=(O_VISIT,))
        # ---- sleep: to bed at home
        s_ = idx[choice == O_SLEEP]
        if len(s_):
            sim.systems["sleep"].to_bed(s_, b)
            act[s_] = A["sleep"]
        same = (prev[2][idx] >= 0) & (cur == choice) if prev is not None else np.zeros(len(idx), bool)
        # campus
        m = choice == O_CAMPUS
        if m.any():
            cp = self._campus_place(P["school"][idx[m]], pick[m], self.spots)
            if prev is not None:
                cp = np.where(same[m] & (prev[1][idx[m]] == CTX_ID["campus"]), prev[2][idx[m]], cp)
            ctype[idx[m]] = CTX_ID["campus"]
            cid[idx[m]] = cp
            act[idx[m]] = A["campus"]
        # gym: students use campus gym, others nearest commercial gym
        m = choice == O_GYM
        if m.any():
            gi = idx[m]
            stud = P["enrolled"][gi]
            ctype[gi] = CTX_ID["gym"]
            near = self.nearest("gym", hl[m], ht[m], 3, pick[m])
            cid[gi] = np.where(stud, 100000 + self._campus_place(P["school"][gi], pick[m], self.gyms), near)
            act[gi] = A["gym"]
        for code, group, ctxname, actname in ((O_FOOD, "food", "venue", "venue"), (O_OUT, "outdoors", "outdoors", "outdoors")):
            m = choice == code
            if m.any():
                vi = self.nearest(group, hl[m], ht[m], 6, pick[m])
                if prev is not None:
                    vi = np.where(same[m] & (prev[1][idx[m]] == CTX_ID[ctxname]), prev[2][idx[m]], vi)
                ctype[idx[m]] = CTX_ID[ctxname]
                cid[idx[m]] = vi
                act[idx[m]] = A[actname]
        # partner time
        m = choice == O_PARTNER
        ctype[idx[m]] = CTX_ID["unit"]
        cid[idx[m]] = host[m]
        act[idx[m]] = A["with_partner"]
        self.together_h[idx] = np.where(m, self.together_h[idx] + 1, 0)
        h = int(clock.HOUR[b])
        if (h >= 22 or h < 5) and m.any():          # the hours that make for the heat of the moment (intimacy.step.late)
            P.internal["late_alone_h"][idx[m]] += 1
        # visits (join the friend's household context -> meet their roommates); the friend staying in is now hosting
        m = choice == O_VISIT
        if m.any():
            vis, dv = idx[m], dest[m]
            ctype[vis] = CTX_ID["unit"]
            cid[vis] = dv
            act[vis] = A["gathering"]
            self.gathering_units.update(dv.tolist())
            sim.systems["culture"].observe_visits(dv[~stay[m]])
            fr = friend[m]
            act[fr[fr >= 0]] = A["gathering"]
        m = choice == O_COMPLEX
        ctype[idx[m]] = CTX_ID["complex"]
        cid[idx[m]] = P["complex_id"][idx[m]]
        act[idx[m]] = A["home"]
        # ---- asking someone along (a food run, a hike, the gym), and who came
        self._together(idx, choice, V, avail, pos, b, ctype, cid, act)
        self.last_choice[idx] = choice
        # ---- past visiting hours (recorded once a night)
        self._past_curfew(idx, choice, b, wd, ctype, cid)

    def _together(self, idx, choice, V, avail, pos, b, ctype, cid, act):
        """Someone heading out for food, the outdoors or the gym asks a partner or a close friend who is up and free;
        they come along if that outing (with this person) beats what they were going to do (activity.together)."""
        sim, w = self.sim, self.sim.w
        P, p = w.P, sim.p
        n = P.n
        out = np.flatnonzero(np.isin(choice, (O_FOOD, O_OUT, O_GYM)))
        if not len(out):
            return
        rng = sim.streams.gen("together", w.day, b)
        ask = out[rng.random(len(out)) < p("activity.together.ask")]
        if not len(ask):
            return
        me = idx[ask]
        # a partner if they have one, else a close friend
        pid = P["partner_id"][me].astype(np.int64)
        has_p = (pid >= 0) & (P.is_("rel_status", "dating")[me] | P.is_("rel_status", "engaged")[me] | P.is_("rel_status", "married")[me])
        fr = sim.systems["network"].random_neighbor(me, rng.random(len(me)), min_stage=3)
        who = np.where(has_p, pid, fr)
        ws = np.clip(who, 0, n - 1)
        jj = pos[ws]
        okw = (who >= 0) & (who < n) & (jj >= 0) & (who != me)          # free this hour
        if not okw.any():
            return
        r = np.flatnonzero(okw)
        a, j, k = me[r], ws[r], jj[r]
        opt = choice[ask[r]]
        theirs = choice[k]
        clos = sim.systems["encounters"]._closeness(a, j)
        is_p = has_p[r].astype(float)
        T = {"their_pull": V[k, opt], "company": p("activity.together.base") + p("activity.together.close") * clos,
             "partner": p("activity.together.partner") * is_p, "instead": -V[k, theirs]}
        # someone heading out themselves (or with their own partner) keeps their own plan, unless it's the same one
        come = (avail[k, opt] & ~np.isin(theirs, (O_FOOD, O_OUT, O_GYM, O_PARTNER)) & (sum(T.values()) > 0)) | (theirs == opt)
        _, first = np.unique(j, return_index=True)          # a companion goes one place at a time
        once = np.zeros(len(j), bool)
        once[first] = True
        come &= once & ~np.isin(j, a)
        if not come.any():
            return
        a, j, k, opt = a[come], j[come], k[come], opt[come]
        choice[k] = opt
        ctype[j], cid[j], act[j] = ctype[a], cid[a], act[a]
        # after 10 pm: a late-night plan worth recording (the food run, the drive, the midnight hike)
        h = int(clock.HOUR[b])
        if h >= 22 or h < 5:
            did = sim.decisions.record("late_night_plan", w.day, j, "came_along", {kk: v[come] for kk, v in T.items()},
                                       other=a, block=int(clock.PART[b]))
            if h < 5:
                sim.emit("late_night_out", a, b=j, mech="activity.together", block=int(clock.PART[b]), decision=did)

    def _past_curfew(self, idx, choice, b, wd, ctype, cid):
        """Guests who stayed on in an opposite-sex contracted apartment past visiting hours: recorded once a night."""
        sim, w = self.sim, self.sim.w
        P = w.P
        if int(clock.END[b]) <= self.curfew(wd):
            if b == 0:
                self.past_curfew[:] = False
            return
        g = np.flatnonzero(np.isin(choice, (O_VISIT, O_PARTNER)))
        if not len(g):
            return
        who = idx[g]
        at = np.where(ctype[who] == CTX_ID["unit"], cid[who], -1)
        guest = self._guest_at(who, at) & ~self.past_curfew[who]
        if not guest.any():
            return
        x = who[guest]
        self.past_curfew[x] = True
        pid = P["partner_id"][x].astype(np.int64)
        other = np.where(choice[g][guest] == O_PARTNER, pid, -1)
        # the host: the partner, or someone who lives there
        sim.emit("stayed_past_visiting_hours", x, b=other, mech="policy.visiting_hours", block=int(clock.PART[b]))

    def explain_choice(self, i: int, b: int | None = None) -> dict:
        """One person's free-time options now, each utility broken into the terms that were summed. Routine choices
        are not logged; this is computed on demand from the person's current state (and says so)."""
        sim, w = self.sim, self.sim.w
        b = int(clock.block_of(w.hour * 60)) if b is None else int(b)
        b = min(max(b, 0), clock.N_BLOCKS - 1)
        wd = int(w.env["weekday"])
        idx = np.array([int(i)], np.int64)
        U, avail, terms = self._utilities(idx, b, wd, explain=True)
        u = np.where(avail[0], U[0], -np.inf)
        ex = np.exp(u - u[avail[0]].max()) if avail[0].any() else np.zeros(NOPT)
        prob = ex / ex.sum() if ex.sum() > 0 else ex
        opts = []
        for c, label in enumerate(OPTIONS):
            tl = [{"term": t, "label": lab, "value": round(float(M[0, c]), 3)} for t, (lab, M) in terms.items() if abs(M[0, c]) > 1e-9]
            opts.append({"option": c, "label": label, "available": bool(avail[0, c]),
                         "utility": round(float(U[0, c]), 3) if avail[0, c] else None, "prob": round(float(prob[c]), 3),
                         "terms": sorted(tl, key=lambda r: -abs(r["value"])),
                         "note": "dances are planned events (see the day's occasions)" if c == O_DANCE else None})
        commit = sim.systems["occasions"].committed_at(int(i), b)
        return {"person": int(i), "day": int(w.day), "block": b, "block_label": clock.BLOCK_LABELS[b],
                "part": clock.PARTS[int(clock.PART[b])], "computed_now": True,
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
        if m.any():                    # the section's classroom (or its campus building): academics.section_point
            lon[m], lat[m], _, _ = sim.systems["academics"].section_point(cid[m])
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
        if m.any():
            lon[m], lat[m] = self._campus_point(cid[m])
        m = ctype == CTX_ID["gym"]
        if m.any():
            gc = cid[m]
            camp = gc >= 100000
            gl = self.v_lon[np.minimum(gc, len(self.v_lon) - 1)]
            gt = self.v_lat[np.minimum(gc, len(self.v_lat) - 1)]
            if camp.any():
                cl, ct_ = self._campus_point(gc[camp] - 100000)
                old_ = (gc[camp] - 100000) <= 2          # no building layer: the old spots by the campus gyms
                gl[camp] = np.where(old_, cl + np.where(gc[camp] - 100000 == 1, -0.003, 0.0), cl)
                gt[camp] = np.where(old_, ct_ + np.where(gc[camp] - 100000 == 1, 0.002, 0.0), ct_)
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
        # the place's own point (people sharing it are seated around it for the map: engine/placement.py)
        P["loc_lon"] = lon
        P["loc_lat"] = lat
