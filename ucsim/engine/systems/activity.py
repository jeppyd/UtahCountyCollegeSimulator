"""Daily activity patterns: where each agent is in each block of the day.

Obligations (class, work shifts, Sunday meetings, FHE, ward activities, dates, gatherings)
take precedence; free time is allocated by a random-utility choice whose utilities depend
on traits, habits, current emotional state, weather and day of week. Loneliness pushes
some people toward company (approach) and others toward withdrawal (Cacioppo &
Hawkley 2009) depending on extraversion, social anxiety and neuroticism.
"""
from __future__ import annotations

import numpy as np
from scipy.spatial import cKDTree
from scipy.special import expit

from ..state import CTX_ID

BYU = (-111.6493, 40.2500)
UVU = (-111.7129, 40.2773)
ACT = ["home", "class", "work", "church", "campus", "gym", "gathering", "date", "venue", "outdoors",
       "ward_activity", "away", "club"]
A = {k: i for i, k in enumerate(ACT)}
NONE = 255


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
        P.add_internal("shift_mask", np.uint32, 0)
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
        self.gathering_units: set = set()
        self.host_of_unit: dict = {}
        self.hosts_today = np.empty(0, np.int64)

    def _build_trees(self):
        self.trees = {}
        groups = {"food": ["restaurant", "cafe", "soda_shop", "dessert"], "gym": ["gym"],
                  "outdoors": ["park", "trailhead", "overlook"], "dance": ["dance"],
                  "date_fun": ["cinema_theatre", "museum", "recreation", "stadium", "dessert", "soda_shop"]}
        for g, types in groups.items():
            idx = np.where(np.isin(self.v_type, types))[0]
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
        tree, idx = self.trees[group]
        k = min(k, len(idx))
        _, nn = tree.query(np.c_[np.asarray(lon) * 0.763, lat], k=k)
        nn = np.atleast_2d(nn)
        if nn.shape[0] != len(pick):
            nn = nn.reshape(len(pick), -1)
        col = np.minimum((pick * nn.shape[1]).astype(int), nn.shape[1] - 1)
        return idx[nn[np.arange(len(pick)), col]]

    def assign_shifts(self, ids: np.ndarray):
        P = self.sim.w.P
        rng = np.random.default_rng([self.sim.w.seed, 405, len(ids), int(ids[0]) if len(ids) else 0])
        hours = P["work_hours"][ids]
        nblocks = np.clip(np.round(hours / 4.5), 0, 15).astype(int)
        student = P["enrolled"][ids]
        masks = np.zeros(len(ids), np.uint32)
        # block slots: bit = weekday*3 + block
        weekday_day = [d * 3 + b for d in range(5) for b in (0, 1)]
        student_slots = [d * 3 + b for d in range(5) for b in (1, 2)] + [15, 16, 17]
        for j in range(len(ids)):
            k = nblocks[j]
            if k == 0:
                continue
            slots = student_slots if student[j] else weekday_day + [15, 16]
            pick = rng.choice(slots, size=min(k, len(slots)), replace=False)
            m = 0
            for s in pick:
                m |= 1 << int(s)
            if rng.random() < 0.05:
                m |= 1 << (18 + 1)
            masks[j] = m
        P.internal["shift_mask"][ids] = masks

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
        unit = P["unit_id"]
        home_ok = present & (unit >= 0)
        ctype[home_ok] = CTX_ID["unit"]
        cid[home_ok] = unit[home_ok]
        act[home_ok] = A["home"]
        busy = ~present.copy()
        u = sim.u(f"activity{b}")
        # ---- dates (evening): scheduled by romance
        rom = sim.systems["romance"]
        if b == 2 and len(rom.dates_today):
            for k, (a_, b_, vid) in enumerate(rom.dates_today):
                for x in (a_, b_):
                    if present[x]:
                        ctype[x] = CTX_ID["date"]
                        cid[x] = k
                        act[x] = A["date"]
                        busy[x] = True
        # ---- church (Sunday morning)
        if wd == 6 and b == 0:
            att = sim.systems["faith"].attending_today & present & ~busy
            ctype[att] = CTX_ID["ward"]
            cid[att] = P["ward_id"][att]
            act[att] = A["church"]
            busy |= att
            oth = sim.systems["faith"].attending_other & present & ~busy
            ctype[oth] = CTX_ID["congregation"]
            cid[oth] = P["congregation_id"][oth]
            act[oth] = A["church"]
            busy |= oth
        # ---- class
        acad = sim.systems["academics"]
        if wd < 5 and not env["holiday"]:
            sec_now = acad.section_now(wd, b)
            in_class = (sec_now >= 0) & present & ~busy & ~P["ill"]
            p_att = expit(p("activity.class_attendance.base") + p("activity.class_attendance.conscientiousness") * sim.z("conscientiousness")
                          - p("activity.class_attendance.fatigue") * P["fatigue"] + 0.8 * P["academic_pressure"] - 0.6 * P["depressive_episode"])
            go = in_class & (u < p_att)
            ctype[go] = CTX_ID["class"]
            cid[go] = sec_now[go]
            act[go] = A["class"]
            busy |= go
            acad.record_attendance(in_class, go)
        # ---- work shifts
        bit = np.uint32(1 << min(wd * 3 + b, 31))
        on_shift = ((P.internal["shift_mask"][:n] & bit) > 0) & present & ~busy & P["employed"] & ~P["ill"] & (not env["holiday"])
        ctype[on_shift] = CTX_ID["work"]
        cid[on_shift] = P["employer_id"][on_shift]
        act[on_shift] = A["work"]
        busy |= on_shift
        # ---- FHE (Monday evening) and ward activities
        if b == 2 and (env["term_BYU"] or env["term_UVU"]):
            fhe = P.internal["fhe_group"][:n]
            if wd == 0:
                go = (fhe >= 0) & present & ~busy & (u < P["ward_activity_rate"] * p("activity.fhe.attend_mult"))
                ctype[go] = CTX_ID["fhe"]
                cid[go] = fhe[go]
                act[go] = A["ward_activity"]
                busy |= go
            elif wd in (1, 2, 3):
                ward = P["ward_id"]
                go = (ward >= 0) & ((ward % 3) + 1 == wd) & present & ~busy & (u < P["ward_activity_rate"] * p("activity.ward_activity.attend_mult"))
                ctype[go] = CTX_ID["ward"]
                cid[go] = ward[go]
                act[go] = A["ward_activity"]
                busy |= go
        # ---- clubs, intramural teams and institute classes (weekly, in term)
        if b >= 1:
            free_now = present & ~busy
            met = sim.systems["groups"].meeting(b, wd, free_now, u)
            for (gids, gid), name in zip(met, ("team", "club", "institute")):
                ctype[gids] = CTX_ID[name]
                cid[gids] = gid
                act[gids] = A["class"] if name == "institute" else A["club"]
                busy[gids] = True
        # ---- gatherings (evening)
        self.gathering_units = set()
        self.host_of_unit = {}
        if b == 2:
            self._gatherings(ctype, cid, act, busy, present, wd)
        # ---- discretionary choice for everyone still free (not night)
        free = present & ~busy
        if free.any():
            self._discretionary(free, b, wd, ctype, cid, act)
        self.ctype, self.cid = ctype, cid
        P["activity_now"] = act
        self._locate(ctype, cid, act)
        self._keep_frame(b)

    def _keep_frame(self, b: int):
        """Positions at each block of the day, kept for the map's day replay."""
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
        self._keep_frame(3)
        if len(self.frames_today) == 4:
            self.day_frames = {"day": self.sim.w.day, **self.frames_today}
        self.frames_today = {}

    def _drives(self):
        sim, P = self.sim, self.sim.w.P
        p = sim.p
        approach = expit(p("activity.loneliness_response.extraversion") * sim.z("extraversion")
                         - p("activity.loneliness_response.social_anxiety") * sim.z("social_anxiety")
                         - p("activity.loneliness_response.neuroticism") * sim.z("neuroticism")
                         + p("activity.loneliness_response.base"))
        lon = P["loneliness"]
        return lon * approach, lon * (1 - approach), approach

    def _discretionary(self, free, b, wd, ctype, cid, act):
        sim, w = self.sim, self.sim.w
        P, env, p = w.P, w.env, sim.p
        idx = np.where(free)[0]
        k = len(idx)
        appr, withdraw, _ = self._drives()
        appr, withdraw = appr[idx], withdraw[idx]
        E = sim.z("extraversion")[idx]
        weekend = 1.0 if wd >= 4 else 0.0
        enrolled = P["enrolled"][idx]
        in_term = np.where(P["school"][idx] == 1, bool(env["term_BYU"]), bool(env["term_UVU"]))
        married = P.is_("rel_status", "married")[idx]
        single = ~married & ~P.isin("rel_status", ["dating", "engaged"])[idx]
        U = np.full((k, 8), -9.0)
        U[:, 0] = (p("activity.choice.home") + 1.2 * P["fatigue"][idx] + p("activity.choice.withdraw") * withdraw
                   + 0.6 * married + 0.3 * (P["children"][idx] > 0) + (0.6 if b == 0 else 0.0) + 0.8 * P["ill"][idx])
        if b < 2:
            U[:, 1] = np.where(enrolled & in_term, 0.5 + 1.3 * P["academic_pressure"][idx] + 0.3 * sim.z("conscientiousness")[idx]
                               - 0.25 * (P["dist_campus_km"][idx] > 3), -9)
        U[:, 2] = -2.3 + np.log(P["workouts_week"][idx] + 0.3) + (0.4 if b != 1 else -0.3)
        if b >= 1:
            U[:, 3] = (-1.6 + 0.5 * np.log1p(P.internal["eat_out_month"][idx] + 3 * P["soda_shop_week"][idx])
                       + p("activity.choice.approach") * 0.6 * appr + 0.3 * weekend)
            U[:, 4] = -2.6 + 1.0 * P["hikes"][idx] + 0.4 * P["outdoors"][idx] + 1.6 * env["outdoor_appeal"] + 0.6 * weekend
        if b == 2 and wd in (3, 4, 5):
            U[:, 5] = np.where(single, -3.2 + 0.9 * P["dancing"][idx] + 0.8 * P["romantic_longing"][idx] + 0.5 * appr, -9)
        if b >= 1:
            has_f = P["n_friends"][idx] > 0
            U[:, 6] = np.where(has_f, -1.2 + p("activity.choice.approach") * appr + 0.35 * E + 0.5 * weekend - 0.5 * married, -9)
        if b == 2:
            U[:, 7] = np.where(P["complex_id"][idx] >= 0, -2.0 + 0.4 * E, -9)
        g = sim.streams.gen(f"disc{b}", w.day).gumbel(size=(P.n, 8))[idx]
        choice = np.argmax(U + g, axis=1)
        pick = sim.u(f"pick{b}")[idx]
        hl, ht = P["home_lon"][idx], P["home_lat"][idx]
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
        for code, group, ctxname, actname in ((3, "food", "venue", "venue"), (4, "outdoors", "outdoors", "outdoors"),
                                              (5, "dance", "dance", "venue")):
            m = choice == code
            if m.any():
                vi = self.nearest(group, hl[m], ht[m], 6 if code != 5 else 2, pick[m])
                ctype[idx[m]] = CTX_ID[ctxname]
                cid[idx[m]] = vi
                act[idx[m]] = A[actname]
        # visit a friend (joins the friend's household context -> meets their roommates)
        m = choice == 6
        if m.any():
            net = self.sim.systems["network"]
            vis = idx[m]
            friend = net.random_neighbor(vis, pick[m], min_stage=2)
            ok = friend >= 0
            ok[ok] &= P["present"][friend[ok]] & (P["unit_id"][friend[ok]] >= 0)
            vis, friend = vis[ok], friend[ok]
            ctype[vis] = CTX_ID["unit"]
            cid[vis] = P["unit_id"][friend]
            act[vis] = A["gathering"]
            self.gathering_units.update(P["unit_id"][friend].tolist())
        m = choice == 7
        ctype[idx[m]] = CTX_ID["complex"]
        cid[idx[m]] = P["complex_id"][idx[m]]
        act[idx[m]] = A["home"]

    def _gatherings(self, ctype, cid, act, busy, present, wd):
        sim, w = self.sim, self.sim.w
        P, p = w.P, sim.p
        net = sim.systems["network"]
        appr, _, _ = self._drives()
        base = [p("activity.gathering.host_weekday")] * 4 + [p("activity.gathering.host_friday"),
                                                              p("activity.gathering.host_saturday"),
                                                              p("activity.gathering.host_sunday")]
        ph = base[wd] * np.exp(0.6 * sim.z("extraversion") + 0.8 * appr) * (P["n_friends"] >= 2)
        u = sim.u("host")
        hosts = np.where(present & ~busy & (P["unit_id"] >= 0) & (u < ph))[0]
        self.hosts_today = hosts
        if len(hosts) == 0:
            return
        indptr, nbr, eidx = net.padded()
        deg = indptr[hosts + 1] - indptr[hosts]
        hosts = hosts[deg > 0]
        deg = deg[deg > 0]
        if len(hosts) == 0:
            return
        rng = sim.streams.gen("invites", w.day)
        k = np.minimum(rng.poisson(p("activity.gathering.invites"), len(hosts)) + 1, deg)
        h_rep = np.repeat(hosts, k)
        off = (rng.random(len(h_rep)) * np.repeat(deg, k)).astype(np.int64)
        inv = nbr[np.repeat(indptr[hosts], k) + off]
        close = w.E["closeness"][eidx[np.repeat(indptr[hosts], k) + off]]
        pa = expit(p("activity.gathering.accept_base") + 2.0 * close + 0.4 * sim.z("extraversion")[inv]
                   - 1.5 * P["fatigue"][inv] + 0.8 * appr[inv])
        go = present[inv] & ~busy[inv] & (rng.random(len(inv)) < pa)
        inv, h_rep = inv[go], h_rep[go]
        inv, first = np.unique(inv, return_index=True)
        h_rep = h_rep[first]
        hu = P["unit_id"][h_rep]
        ctype[inv] = CTX_ID["unit"]
        cid[inv] = hu
        act[inv] = A["gathering"]
        busy[inv] = True
        ctype[hosts] = CTX_ID["unit"]
        cid[hosts] = P["unit_id"][hosts]
        act[hosts] = A["gathering"]
        busy[hosts] = True
        self.gathering_units.update(P["unit_id"][hosts].tolist())
        order = np.argsort(hosts)
        pos = order[np.searchsorted(hosts[order], h_rep)]
        sizes = np.bincount(pos, minlength=len(hosts)).astype(float)
        self.host_of_unit = dict(zip(P["unit_id"][hosts].tolist(), hosts.tolist()))
        sim.emit("hosted_gathering", hosts, value=sizes, block=2)

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
        m = ctype == CTX_ID["date"]
        if m.any():
            rom = sim.systems["romance"]
            vids = np.array([d[2] for d in rom.dates_today])[cid[m]]
            lon[m], lat[m] = self.v_lon[vids], self.v_lat[vids]
        jit = sim.streams.normal("locjit", w.day, n * 2, block=int(act.sum() % 7)).reshape(2, n) * 0.00025
        P["loc_lon"] = np.where(np.isfinite(lon), lon + jit[0], np.nan)
        P["loc_lat"] = np.where(np.isfinite(lat), lat + jit[1], np.nan)
