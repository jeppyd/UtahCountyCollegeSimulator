"""Romance: attraction, asking out, dates, kissing/NCMOs, DTR, engagement, marriage, breakups.

Design notes
* Attraction is directed and mostly pair-specific (idiosyncratic "spark"), with smaller
  shared components (perceived attractiveness, religiosity fit, age/height preferences from
  the Dating & ProvoStats surveys, RM preference). Shared hobbies only nudge it — the Dating
  survey ranks shared interests last among six partner qualities.
* Opportunity first: people can only ask out someone they already know (an edge exists),
  or someone they matched with on an app.
* Culture: men are expected to ask (survey: most agree men should make the first move);
  most first dates are accepted "to be polite" (ProvoStats); courtship-to-engagement is
  short for active LDS couples (Dating/Culture surveys: ~6–8 months typical).
* Commitment follows Rusbult's investment model; breakup distress is moderated by attachment
  anxiety, relationship length, initiator status and close-friend support (events.yaml).
"""
from __future__ import annotations

import numpy as np
from scipy.special import expit

from ..core import pair_normal
from ..state import CTX_ID, EdgeStore, Tie

DATE_TYPES = ["ice_cream", "restaurant", "hike", "board_games", "cook_together", "movie_theater", "soda_shop",
              "museum", "picnic", "stargazing", "sports_game", "pickleball"]
DATE_VENUE_GROUP = {"ice_cream": "date_fun", "restaurant": "food", "hike": "outdoors", "board_games": "home",
                    "cook_together": "home", "movie_theater": "date_fun", "soda_shop": "food", "museum": "date_fun",
                    "picnic": "outdoors", "stargazing": "outdoors", "sports_game": "date_fun", "pickleball": "outdoors"}


class Romance:
    def __init__(self, sim):
        self.sim = sim
        self.queue: list[tuple] = []   # (day, a, b, date_type, is_first, cause_event)
        self.dates_today: list[tuple] = []   # (a, b, venue_id)
        self._dates_meta: list[tuple] = []
        self.last_evening_pairs = None

    def init(self):
        P = self.sim.w.P
        for c, dt, f in (("crush_id", np.int32, -1), ("crush_att", np.float32, 0.0), ("cooldown_until", np.int32, -1),
                         ("wedding_planned", np.int32, -1), ("talk_start", np.int32, -1), ("date_planned", np.int32, -1),
                         ("confess_day", np.int32, -1), ("rel_event", np.int64, -1)):
            P.add_internal(c, dt, f)
        eng = np.where(P.is_("rel_status", "engaged") & (P["partner_id"] >= 0))[0]
        if len(eng):
            a = eng[eng < P["partner_id"][eng]]
            lead = (10 + 110 * np.random.default_rng([self.sim.w.seed, 88]).random(len(a))).astype(int)
            P.internal["wedding_planned"][a] = lead
            P.internal["wedding_planned"][P["partner_id"][a]] = lead
        self.weekly()

    # ------------------------------------------------------------------ attraction model
    def compatible(self, src: np.ndarray, dst: np.ndarray) -> np.ndarray:
        P = self.sim.w.P
        o = P["orientation"][src]
        same = P["sex"][src] == P["sex"][dst]
        straight, bi, gay = P.code("orientation", "straight"), P.code("orientation", "bi"), P.code("orientation", "gay")
        other = P.code("orientation", "other")
        return ((o == straight) & ~same) | ((o == gay) & same) | (o == bi) | (o == other)

    def initial_attraction(self, src: np.ndarray, dst: np.ndarray) -> np.ndarray:
        """Directed initial attraction src→dst in [-1, 1] (0 if orientation-incompatible)."""
        sim, w = self.sim, self.sim.w
        P, p = w.P, sim.p
        if len(src) == 0:
            return np.zeros(0, np.float32)
        comp = self.compatible(src, dst)
        spark = (p("romance.attraction.spark_shared") * pair_normal(w.seed, src, dst, 23)
                 + p("romance.attraction.spark_directed") * pair_normal(w.seed, src, dst, 29, directed=True))
        looks = p("romance.attraction.looks") * P["attractiveness"][dst] * (0.5 + P["imp_physical"][src] / 5)
        dage = P["age"][dst] - P["age"][src]
        age_pen = -p("romance.attraction.age_fit") * (np.clip(dage - P["max_older"][src], 0, None) + np.clip(-dage - P["max_younger"][src], 0, None))
        f_src = P["sex"][src] == P.code("sex", "F")
        m_dst = P["sex"][dst] == P.code("sex", "M")
        height_pen = np.where(f_src & m_dst, -p("romance.attraction.height") * np.clip(P["min_height_req"][src] - P["height_in"][dst], 0, None) / 2, 0)
        lds_src = P["lds_member"][src]
        act_s = P["activity"][src].astype(float)
        act_d = P["activity"][dst].astype(float)
        rel_fit = np.where(lds_src, -p("romance.attraction.religiosity_fit") * np.abs(act_s - act_d) / 3 * (0.4 + P["imp_spirituality"][src] / 5), 0)
        rm = np.where(f_src & lds_src & (P["mission_status"][dst] >= P.code("mission_status", "returned")),
                      p("romance.attraction.rm_bonus") * (P["prefers_rm"][src] - 2) / 2, 0)
        shared = p("romance.attraction.shared_interests") * (P["imp_shared_interests"][src] / 5) * (
            (P["hikes"][src] & P["hikes"][dst]).astype(float) + (P["music_maker"][src] & P["music_maker"][dst]) +
            (P["sports"][src] & P["sports"][dst]) + (P["gaming"][src] & P["gaming"][dst]))
        eth = np.where(P["ethnicity"][src] == P["ethnicity"][dst], p("romance.attraction.ethnic_homophily"), 0)
        persona = p("romance.attraction.personality") * (0.4 * sim.z("agreeableness")[dst] + 0.3 * sim.z("social_skill")[dst])
        raw = spark + looks + age_pen + height_pen + rel_fit + rm + shared + eth + persona + p("romance.attraction.base")
        out = np.tanh(raw / 1.5)
        return np.where(comp, out, 0.0).astype(np.float32)

    def seeking_mask(self) -> np.ndarray:
        P = self.sim.w.P
        status_ok = P.isin("rel_status", ["single", "divorced", "talking"])
        return status_ok & P["present"] & (P["age"] >= 18) & (P.internal["cooldown_until"][: P.n] <= self.sim.w.day) & \
            (P.code("orientation", "asexual") != P["orientation"])

    # ------------------------------------------------------------------ daily
    def plan_day(self):
        """Pull today's scheduled dates; choose venues."""
        sim, w = self.sim, self.sim.w
        P = w.P
        day = w.day
        todays = [q for q in self.queue if q[0] == day]
        self.queue = [q for q in self.queue if q[0] > day]
        self.dates_today, self._dates_meta = [], []
        act = sim.systems["activity"]
        busy = set()
        rng = sim.streams.gen("date_venue", day)
        for (_, a, b, dtype, first, cause) in todays:
            if not (P["present"][a] and P["present"][b]) or a in busy or b in busy:
                continue
            busy.update((a, b))
            group = DATE_VENUE_GROUP[dtype]
            if group == "home":
                # dinner/board games at one of their apartments: treat as nearest dessert/food venue for location
                group = "food"
            lon = (P["home_lon"][a] + P["home_lon"][b]) / 2
            lat = (P["home_lat"][a] + P["home_lat"][b]) / 2
            vid = int(act.nearest(group, np.array([lon]), np.array([lat]), 5, rng.random(1))[0])
            if dtype in ("hike", "stargazing") and rng.random() < 0.18:
                kyhv = np.where(np.char.find(np.array(act.v_name, dtype=str), "KhPeak") >= 0)[0]
                if len(kyhv):
                    vid = int(kyhv[0])
            self.dates_today.append((a, b, vid))
            self._dates_meta.append((dtype, first, cause))

    def evening(self):
        self._run_dates()
        self._ncmo()

    def daily(self):
        sim, w = self.sim, self.sim.w
        P, p = w.P, sim.p
        day = w.day
        n = P.n
        P["dates_30d"] = P["dates_30d"] * np.exp(-1 / 30)
        P["rejections_recent"] = P["rejections_recent"] * np.exp(-1 / 30)
        # dating motivation
        age = P["age"]
        lds_active = P.is_("activity", "active")
        age_norm = np.clip((age - 19.5) / 3, 0, 1) * np.clip((31 - age) / 5, 0, 1)
        rm_recent = (P.is_("mission_status", "returned")) & (age < 24)
        mot = expit(p("romance.motivation.base")
                    + p("romance.motivation.wants") * (P["wants_relationship"] - 2.5) / 1.5
                    + p("romance.motivation.longing") * P["romantic_longing"]
                    + p("romance.motivation.marriage_norm") * w.env["marriage_norm"] * age_norm * lds_active
                    + 0.4 * rm_recent + 0.25 * sim.z("extraversion")
                    - 0.8 * P["depressive_episode"] - 0.5 * P["academic_pressure"] - 0.4 * P["fatigue"])
        P["dating_motivation"] = np.where(self.seeking_mask(), mot, 0.0).astype(np.float32)
        self._weddings()
        self._confessions()
        wd = w.env["weekday"]
        self._asks(wd)
        self._app(wd)

    # ------------------------------------------------------------------ asking out
    def _next_date_day(self, wd: int, u: np.ndarray) -> np.ndarray:
        day = self.sim.w.day
        to_fri = (4 - wd) % 7
        to_sat = (5 - wd) % 7
        to_fri = np.where(to_fri == 0, 7, to_fri) if wd == 4 else to_fri
        base = np.where(u < 0.55, to_fri, to_sat)
        base = np.where(base < 1, base + 7, base)
        near = 1 + (u * 3).astype(int)
        return day + np.where(u < 0.75, base, near)

    def _asks(self, wd: int):
        sim, w = self.sim, self.sim.w
        P, E, p = w.P, w.E, sim.p
        day = w.day
        seek = self.seeking_mask()
        crush = P.internal["crush_id"][: P.n]
        catt = P.internal["crush_att"][: P.n]
        planned = P.internal["date_planned"][: P.n] >= day
        cand = seek & (crush >= 0) & (catt > p("romance.ask.min_attraction")) & ~planned
        ids = np.where(cand)[0]
        if len(ids) == 0:
            return
        tgt = crush[ids].astype(np.int64)
        okt = P["present"][tgt] & ~P.isin("rel_status", ["married", "engaged"])[tgt]
        ids, tgt = ids[okt], tgt[okt]
        male = P["sex"][ids] == P.code("sex", "M")
        dow_mult = np.array([1.2, 1.2, 1.1, 1.0, 0.7, 0.4, 0.3])[wd]
        logit = (p("romance.ask.base") + p("romance.ask.attraction") * catt[ids]
                 + p("romance.ask.motivation") * (P["dating_motivation"][ids] - 0.5)
                 + p("romance.ask.confidence") * (P["self_esteem"][ids] - 0.5)
                 - p("romance.ask.rejection_sensitivity") * np.clip(sim.z("rejection_sensitivity")[ids], 0, None) * np.log1p(P["rejections_recent"][ids])
                 + np.where(male, p("romance.ask.male") * w.env["men_initiate_norm"], -p("romance.ask.male") * w.env["men_initiate_norm"] * 0.9)
                 + p("romance.ask.propensity") * np.log(P["dating_propensity"][ids] + 0.5)
                 + 0.25 * (P["asks_for_numbers"][ids] - 2) / 2)
        u = sim.u("ask")[ids]
        go = u < expit(logit) * dow_mult
        ids, tgt = ids[go], tgt[go]
        if len(ids) == 0:
            return
        # resolve duplicates: one ask per target per day
        tgt_u, first = np.unique(tgt, return_index=True)
        ids, tgt = ids[first], tgt[first]
        keys = EdgeStore.make_keys(ids, tgt)
        eix = E.find(keys)
        has = eix >= 0
        ids, tgt, eix = ids[has], tgt[has], eix[has]
        a_ji = E.attraction_from(eix, tgt)
        a_ij = E.attraction_from(eix, ids)
        first_date = E["dates"][eix] == 0
        taken = P.isin("rel_status", ["dating", "engaged", "married"])[tgt] | (P.is_("rel_status", "talking")[tgt] & (P["partner_id"][tgt] != ids))
        planned_t = P.internal["date_planned"][: P.n][tgt] >= day
        acc = expit(p("romance.accept.base") + p("romance.accept.attraction") * a_ji
                    + np.where(first_date, p("romance.accept.politeness") * (P["accepts_first_dates"][tgt] - 2) / 2, 0)
                    + p("romance.accept.motivation") * (P["dating_motivation"][tgt] - 0.4)
                    - p("romance.accept.picky") * (P["picky"][tgt] - 2) / 2
                    - 3.0 * taken - 1.5 * planned_t)
        ua = sim.u("accept")[tgt]
        yes = ua < acc
        ask_ev = sim.emit("asked_out", ids, b=tgt, value=a_ij, mech="romance.ask")
        # rejections
        no = ~yes
        if no.any():
            ri, rt = ids[no], tgt[no]
            P.cols["rejections_recent"][ri] += 1
            sim.emit("rejected", ri, b=rt, cause=ask_ev[no], mech="romance.accept",
                     ev={"recent_rejections": np.log1p(P["rejections_recent"][ri])})
            E.set_attraction_from(eix[no], ri, np.clip(a_ij[no] - 0.2, -1, 1))
            P.internal["crush_id"][ri] = -1
        if yes.any():
            yi, yt = ids[yes], tgt[yes]
            dd = self._next_date_day(w.env["weekday"], sim.u("dday")[yi])
            dtypes = self._date_type(yi, yt)
            for a_, b_, d_, t_, f_, c_ in zip(yi.tolist(), yt.tolist(), dd.tolist(), dtypes, first_date[yes].tolist(), ask_ev[yes].tolist()):
                self.queue.append((d_, a_, b_, t_, f_, c_))
            P.internal["date_planned"][yi] = dd
            P.internal["date_planned"][yt] = dd

    def _date_type(self, a: np.ndarray, b: np.ndarray) -> list[str]:
        sim = self.sim
        P = sim.w.P
        rng = sim.streams.gen("date_type", sim.w.day)
        winter = sim.w.env["temp_f"] < 45
        out = []
        cols = [f"fd_{t}" if f"fd_{t}" in P.cols else None for t in DATE_TYPES]
        for x, y in zip(a, b):
            sc = []
            for t, c in zip(DATE_TYPES, cols):
                v = (P[c][x] + P[c][y]) / 2 if c else 2.5
                if winter and t in ("hike", "picnic", "stargazing", "pickleball"):
                    v -= 1.5
                sc.append(v)
            sc = np.array(sc) + rng.gumbel(size=len(sc)) * 0.8
            out.append(DATE_TYPES[int(np.argmax(sc))])
        return out

    def _app(self, wd: int):
        """Dating apps create opportunity beyond physical propinquity."""
        sim, w = self.sim, self.sim.w
        P, E, p = w.P, w.E, sim.p
        day = w.day
        seek = self.seeking_mask() & P["app_user"]
        planned = P.internal["date_planned"][: P.n] >= day
        rate = p("romance.app.rate") * w.env["app_appeal"] * P["app_hours"] / 7.0
        u = sim.u("app")
        ids = np.where(seek & ~planned & (u < rate))[0]
        if len(ids) == 0:
            return
        pool = np.where(seek & ~planned)[0]
        if len(pool) < 10:
            return
        rng = sim.streams.gen("app_pool", day)
        K = 10
        cand = pool[rng.integers(0, len(pool), (len(ids), K))]
        # same-app pools: Mutual users mostly match with Mutual users
        mutual_ok = (P["app_mutual"][ids][:, None] == P["app_mutual"][cand]) | (rng.random((len(ids), K)) < 0.35)
        src = np.repeat(ids, K)
        a1 = self.initial_attraction(src, cand.ravel()).reshape(-1, K)
        a2 = self.initial_attraction(cand.ravel(), src).reshape(-1, K)
        pic = p("romance.app.photo_weight") * P["attractiveness"][cand]
        score = np.where(mutual_ok & (cand != ids[:, None]), a1 + pic, -9)
        best = np.argmax(score, axis=1)
        tgt = cand[np.arange(len(ids)), best]
        like_back = a2[np.arange(len(ids)), best] + p("romance.app.photo_weight") * P["attractiveness"][ids]
        match = (score[np.arange(len(ids)), best] > 0.15) & (like_back > 0.1)
        ids, tgt = ids[match], tgt[match]
        if len(ids) == 0:
            return
        keys = EdgeStore.make_keys(ids, tgt)
        new = E.find(keys) < 0
        eix = E.upsert(keys)
        if new.any():
            ni = eix[new]
            lo, hi = E.split(E.key_array[ni])
            E.cols["first_day"][ni] = day
            E.cols["last_day"][ni] = day
            E.cols["n_inter"][ni] = 1
            E.cols["stage"][ni] = 1
            E.cols["chemistry"][ni] = pair_normal(w.seed, lo, hi, 11)
            E.cols["att_lh"][ni] = self.initial_attraction(lo, hi)
            E.cols["att_hl"][ni] = self.initial_attraction(hi, lo)
            E.cols["origin_ctx"][ni] = CTX_ID["app"]
        E.cols["flags"][eix] |= Tie.APP_MATCH
        ev = sim.emit("app_match", ids, b=tgt, mech="romance.app")
        # the match turns into a date with probability ~ conversation success
        go = sim.u("app_date")[ids] < p("romance.app.date_conversion")
        ids, tgt, ev = ids[go], tgt[go], ev[go]
        dd = self._next_date_day(wd, sim.u("app_dday")[ids])
        dtypes = self._date_type(ids, tgt)
        for a_, b_, d_, t_, c_ in zip(ids.tolist(), tgt.tolist(), dd.tolist(), dtypes, ev.tolist()):
            self.queue.append((d_, a_, b_, t_, True, c_))
        P.internal["date_planned"][ids] = dd
        P.internal["date_planned"][tgt] = dd

    # ------------------------------------------------------------------ dates
    def _run_dates(self):
        sim, w = self.sim, self.sim.w
        P, E, p = w.P, w.E, sim.p
        day = w.day
        if not self.dates_today:
            return
        a = np.array([d[0] for d in self.dates_today])
        b = np.array([d[1] for d in self.dates_today])
        venue = np.array([d[2] for d in self.dates_today])
        dtypes = [m[0] for m in self._dates_meta]
        first = np.array([m[1] for m in self._dates_meta])
        cause = np.array([m[2] for m in self._dates_meta])
        keys = EdgeStore.make_keys(a, b)
        eix = E.upsert(keys)
        rng = sim.streams.gen("date_outcome", day)
        pref = np.zeros(len(a))
        for k, t in enumerate(dtypes):
            c = f"fd_{t}"
            if c in P.cols:
                pref[k] = (P[c][a[k]] + P[c][b[k]]) / 2 - 2
        spark = pair_normal(w.seed, a, b, 23)
        q = (p("romance.date.spark") * spark + p("romance.date.preference") * pref / 2
             + 0.25 * (sim.z("social_skill")[a] + sim.z("social_skill")[b]) / 2
             + 0.3 * (P["mood"][a] + P["mood"][b] - 1) + 0.5 * rng.standard_normal(len(a)))
        eta = p("romance.date.attraction_update")
        for src, dst in ((a, b), (b, a)):
            cur = E.attraction_from(eix, src)
            directed = pair_normal(w.seed, src, dst, 31, directed=True)
            E.set_attraction_from(eix, src, np.clip(cur + eta * (q + 0.3 * directed), -1, 1))
        E.cols["dates"][eix] += 1
        E.cols["flags"][eix] |= Tie.DATED
        E.cols["hours"][eix] += 2.5
        E.cols["hours_leisure"][eix] += 2.5
        E.cols["last_day"][eix] = day
        E.cols["n_inter"][eix] += 1
        both = np.r_[a, b]
        P.cols["dates_30d"][both] += 1
        P.cols["dates_total"][both] += 1
        P.internal["close_hours_today"][both] += 2.5
        P.internal["hours_today"][both] += 2.5
        ev_first = np.full(len(a), -1, np.int64)
        if first.any():
            P.cols["first_dates_total"][np.r_[a[first], b[first]]] += 1
            e1 = sim.emit("first_date", a[first], b=b[first], value=q[first], cause=cause[first], place=venue[first],
                          block=2, mech="romance.date", ev={"quality": q[first]})
            sim.emit("first_date", b[first], b=a[first], value=q[first], cause=cause[first], place=venue[first],
                     block=2, mech="romance.date", ev={"quality": q[first]})
            ev_first[first] = e1
        if (~first).any():
            nf = ~first
            sim.emit("date", a[nf], b=b[nf], value=q[nf], cause=cause[nf], place=venue[nf], block=2,
                     mech="romance.date", ev={"quality": q[nf]})
        date_ev = np.where(ev_first >= 0, ev_first, cause)
        # kissing
        att_ab = E.attraction_from(eix, a)
        att_ba = E.attraction_from(eix, b)
        mutual = np.minimum(att_ab, att_ba)
        kissed = (E["flags"][eix] & Tie.KISSED) > 0
        ndates = E["dates"][eix].astype(float)
        couple = P["partner_id"][a] == b
        pk = expit(p("romance.kiss.base") + p("romance.kiss.attraction") * mutual + 0.6 * np.log(ndates)
                   + np.where(ndates <= 1, p("romance.kiss.first_date_ok") * ((P["kiss_first_date_ok"][a] + P["kiss_first_date_ok"][b]) / 2 - 2) / 2, 0)
                   - 0.3 * (P["scared_initiate_kiss"][a] - 2) / 2 + 0.3 * (sim.z("sensation_seeking")[a] + sim.z("sensation_seeking")[b]) / 2
                   + 1.2 * couple)
        kiss = ~kissed & (mutual > 0.05) & (rng.random(len(a)) < pk)
        if kiss.any():
            self._kiss(a[kiss], b[kiss], eix[kiss], date_ev[kiss], venue[kiss])
        # progression to "talking"
        st = P["rel_status"]
        single_a = np.isin(st[a], [P.code("rel_status", "single"), P.code("rel_status", "divorced")])
        single_b = np.isin(st[b], [P.code("rel_status", "single"), P.code("rel_status", "divorced")])
        talk = single_a & single_b & (ndates >= 2) & (mutual > p("romance.progress.talk_threshold"))
        if talk.any():
            ta, tb = a[talk], b[talk]
            for x, y in ((ta, tb), (tb, ta)):
                P.cols["rel_status"][x] = P.code("rel_status", "talking")
                P.cols["partner_id"][x] = y
                P.internal["talk_start"][x] = day
            ev = sim.emit("talking_started", ta, b=tb, cause=date_ev[talk], mech="romance.progress")
            sim.emit("talking_started", tb, b=ta, cause=date_ev[talk], mech="romance.progress")
            P.internal["rel_event"][ta] = ev
            P.internal["rel_event"][tb] = ev
            E.cols["flags"][eix[talk]] |= Tie.ROMANTIC
        # ghosting after a dud first date where interest is one-sided
        dud = first & ((att_ab < -0.05) ^ (att_ba < -0.05))
        if dud.any():
            ghost_r = np.where(att_ab[dud] < att_ba[dud], b[dud], a[dud])
            ghost_s = np.where(att_ab[dud] < att_ba[dud], a[dud], b[dud])
            g = rng.random(len(ghost_r)) < p("romance.ghosting.rate")
            if g.any():
                sim.emit("ghosted", ghost_r[g], b=ghost_s[g], mech="romance.ghosting")

    def _kiss(self, a, b, eix, cause, venue):
        sim, w = self.sim, self.sim.w
        P, E = w.P, w.E
        E.cols["flags"][eix] |= Tie.KISSED
        for x, y in ((a, b), (b, a)):
            first_ever = P["n_kissed"][x] == 0
            P.cols["n_kissed"][x] += 1
            sim.emit("first_kiss_with", x, b=y, cause=cause, place=venue, block=2, mech="romance.kiss")
            if first_ever.any():
                sim.emit("first_kiss_ever", x[first_ever], b=y[first_ever], cause=cause[first_ever], block=2, mech="romance.kiss")
        act = sim.systems["activity"]
        kyhv = np.array(["KhPeak" in act.v_name[v] for v in venue])
        night_outdoor = np.isin(act.v_type[venue], ["overlook", "trailhead"]) & (sim.u("kyhv")[a] < 0.5)
        sp = kyhv | night_outdoor & (sim.u("kyhv2")[a] < 0.25)
        if sp.any():
            P.cols["made_out_squaw_peak"][np.r_[a[sp], b[sp]]] = True
            sim.emit("squaw_peak", a[sp], b=b[sp], cause=cause[sp], block=2, mech="romance.kiss")
            sim.emit("squaw_peak", b[sp], b=a[sp], cause=cause[sp], block=2, mech="romance.kiss")

    def _ncmo(self):
        """Non-committal make-outs at gatherings and dances among mutually attracted single people."""
        sim, w = self.sim, self.sim.w
        P, E, p = w.P, w.E, sim.p
        act = sim.systems["activity"]
        loc = act.ctype
        pairs = sim.systems["encounters"].evening_social_pairs
        if pairs is None or len(pairs[0]) == 0:
            return
        a, b = pairs
        seek = self.seeking_mask()
        ok = seek[a] & seek[b]
        a, b = a[ok], b[ok]
        if len(a) == 0:
            return
        key = np.unique(EdgeStore.make_keys(a, b))
        a, b = EdgeStore.split(key)
        keys = EdgeStore.make_keys(a, b)
        eix = E.find(keys)
        ok = eix >= 0
        a, b, eix = a[ok], b[ok], eix[ok]
        if len(a) == 0:
            return
        mutual = np.minimum(E.attraction_from(eix, a), E.attraction_from(eix, b))
        comp = self.compatible(a, b) & self.compatible(b, a)
        chast = (P["chastity_commitment"][a] + P["chastity_commitment"][b]) / 2
        pn = expit(p("romance.ncmo.base") + p("romance.ncmo.interest") * ((P["ncmo_interest"][a] + P["ncmo_interest"][b]) / 2 - 1.5)
                   + 0.5 * (sim.z("sensation_seeking")[a] + sim.z("sensation_seeking")[b]) / 2
                   - p("romance.ncmo.chastity") * (chast - 0.5) + 2.0 * mutual
                   + 0.4 * (loc[a] == CTX_ID["dance"]))
        hit = comp & (mutual > 0.1) & (sim.u("ncmo")[a] < pn)
        if not hit.any():
            return
        a, b, eix = a[hit], b[hit], eix[hit]
        new_k = (E["flags"][eix] & Tie.KISSED) == 0
        E.cols["flags"][eix] |= Tie.NCMO | Tie.KISSED
        for x, y in ((a, b), (b, a)):
            P.cols["n_ncmo"][x] += 1
            P.cols["n_kissed"][x[new_k]] += 1
            sim.emit("ncmo", x, b=y, block=2, mech="romance.ncmo")

    # ------------------------------------------------------------------ weekly relationship dynamics
    def weekly(self):
        sim, w = self.sim, self.sim.w
        P, E, p = w.P, w.E, sim.p
        day = w.day
        self._crushes()
        part = P["partner_id"]
        st = P["rel_status"]
        n = P.n
        ids = np.where((part >= 0) & (np.arange(n) < part) & P["present"])[0]
        if len(ids) == 0:
            return
        j = part[ids].astype(np.int64)
        keys = EdgeStore.make_keys(ids, j)
        eix = E.upsert(keys)
        status = st[ids]
        att_a = E.attraction_from(eix, ids)
        att_b = E.attraction_from(eix, j)
        chem = E["chemistry"][eix]
        rel_mis = np.abs(P["faith_belief"][ids] - P["faith_belief"][j]) + 0.3 * np.abs(P["activity"][ids].astype(float) - P["activity"][j]) / 3
        stress = (P["stress"][ids] + P["stress"][j]) / 2
        conflict = E["conflict"][eix]
        rng = sim.streams.gen("rel_weekly", day)
        # satisfaction & commitment (Rusbult)
        target = expit(p("romance.relationship.sat_base") + 0.9 * (att_a + att_b) / 2 + 0.35 * chem
                       - p("romance.relationship.religious_mismatch") * rel_mis - 1.2 * conflict - 0.8 * (stress - 0.3)
                       + 0.2 * (sim.z("agreeableness")[ids] + sim.z("agreeableness")[j]) / 2)
        sat = P["relationship_satisfaction"][ids]
        sat = np.where(np.isfinite(sat), sat, target)
        sat = sat + 0.25 * (target - sat) + 0.03 * rng.standard_normal(len(ids))
        months = (day - P["rel_start_day"][ids]) / 30.4
        invest = np.clip(np.log1p(np.maximum(months, 0)) / 3, 0, 1)
        alt = np.clip(np.maximum(P.internal["crush_att"][ids], P.internal["crush_att"][j]), 0, 1)
        commit = np.clip(0.55 * sat + 0.35 * invest - 0.3 * alt + 0.15 * w.env["marriage_norm"] * (status != P.code("rel_status", "talking")), 0, 1)
        for x in (ids, j):
            P.cols["relationship_satisfaction"][x] = sat
            P.cols["relationship_commitment"][x] = commit
        # couple time: dating couples see each other often (dates + hanging out)
        exclusive = np.isin(status, [P.code("rel_status", s) for s in ("talking", "dating", "engaged")])
        if exclusive.any():
            xa, xb = ids[exclusive], j[exclusive]
            k_dates = np.where(sim.streams.uniform("kdates", day, len(xa)) < 0.25, 2, 1)
            for kk in range(int(k_dates.max())):
                sel = k_dates > kk
                dd = self._next_date_day(6, sim.streams.uniform(f"cdate{kk}", day, len(xa))[sel])
                dtypes = self._date_type(xa[sel], xb[sel])
                for a_, b_, d_, t_ in zip(xa[sel].tolist(), xb[sel].tolist(), dd.tolist(), dtypes):
                    self.queue.append((d_ if d_ > day else day + 1, a_, b_, t_, False, int(P.internal["rel_event"][a_])))
            E.cols["hours_leisure"][eix[exclusive]] += 6.0
            E.cols["hours"][eix[exclusive]] += 8.0
            E.cols["last_day"][eix[exclusive]] = day
        # ---- transitions
        mutual = np.minimum(att_a, att_b)
        talking = status == P.code("rel_status", "talking")
        dating = status == P.code("rel_status", "dating")
        engaged = status == P.code("rel_status", "engaged")
        married = status == P.code("rel_status", "married")
        ndates = E["dates"][eix]
        tstart = P.internal["talk_start"][ids]
        # DTR
        dtr = talking & (ndates >= p("romance.progress.dtr_dates")) & (day - tstart >= 14) & (mutual > p("romance.progress.dtr_threshold"))
        dtr &= rng.random(len(ids)) < 0.12
        if dtr.any():
            a_, b_ = ids[dtr], j[dtr]
            for x, y in ((a_, b_), (b_, a_)):
                P.cols["rel_status"][x] = P.code("rel_status", "dating")
                P.cols["rel_start_day"][x] = day
                P.cols["n_relationships"][x] += 1
            ev = sim.emit("relationship_started", a_, b=b_, cause=P.internal["rel_event"][a_], mech="romance.progress")
            sim.emit("relationship_started", b_, b=a_, cause=P.internal["rel_event"][a_], mech="romance.progress")
            P.internal["rel_event"][a_] = ev
            P.internal["rel_event"][b_] = ev
        # talking fizzles
        fizzle = talking & ~dtr & (((day - tstart) > 42) | (mutual < 0.3))
        fizzle &= rng.random(len(ids)) < 0.6
        if fizzle.any():
            self._end(ids[fizzle], j[fizzle], att_a[fizzle], att_b[fizzle], kind="talking")
        # engagement hazard (dating couples)
        both_active = P.is_("activity", "active")[ids] & P.is_("activity", "active")[j]
        ideal = (P["ideal_months_engaged"][ids] + P["ideal_months_engaged"][j]) / 2
        mean_age = (P["age"][ids] + P["age"][j]) / 2
        fin = (P["financial_stress"][ids] + P["financial_stress"][j]) / 2
        h_eng = expit(p("romance.engage.base") + p("romance.engage.commitment") * commit
                      + p("romance.engage.timing") * np.clip((months - ideal) / 4, -2, 2)
                      + p("romance.engage.active_lds") * both_active * w.env["marriage_norm"]
                      + 0.35 * np.clip((mean_age - 20.5) / 2, -1, 1.5) - 0.8 * fin - 1.2 * rel_mis)
        eng = dating & (months >= 2.0) & (rng.random(len(ids)) < h_eng)
        if eng.any():
            a_, b_ = ids[eng], j[eng]
            for x in (a_, b_):
                P.cols["rel_status"][x] = P.code("rel_status", "engaged")
                P.cols["engaged_day"][x] = day
            lead = np.where(both_active[eng], rng.uniform(70, 140, eng.sum()), rng.uniform(120, 300, eng.sum())).astype(int)
            P.internal["wedding_planned"][a_] = day + lead
            P.internal["wedding_planned"][b_] = day + lead
            ev = sim.emit("engaged", a_, b=b_, cause=P.internal["rel_event"][a_], mech="romance.engage")
            sim.emit("engaged", b_, b=a_, cause=P.internal["rel_event"][a_], mech="romance.engage")
            P.internal["rel_event"][a_] = ev
            P.internal["rel_event"][b_] = ev
        # breakups
        h_brk = expit(p("romance.breakup.base") - p("romance.breakup.commitment") * commit
                      + p("romance.breakup.religious_mismatch") * rel_mis + 1.5 * conflict)
        h_brk = np.where(engaged, h_brk * 0.25, np.where(married, h_brk * p("romance.breakup.married_mult"), h_brk))
        brk = (dating | engaged | married) & ~eng & (rng.random(len(ids)) < h_brk)
        if brk.any():
            self._end(ids[brk], j[brk], att_a[brk], att_b[brk], married=married[brk])
        # infidelity (rare): low commitment, high NCMO interest; often discovered → breakup risk
        excl = (dating | engaged | married) & ~brk
        h_ch = expit(-8.5 - 4.0 * (commit - 0.5) + 0.5 * (P["ncmo_interest"][ids] - 2) + 0.4 * sim.z("sensation_seeking")[ids])
        cheat = excl & (rng.random(len(ids)) < h_ch)
        if cheat.any():
            ci, cj = ids[cheat], j[cheat]
            P.cols["ever_cheated"][ci] = True
            ev = sim.emit("cheating", ci, b=cj, mech="romance.breakup")
            found = rng.random(len(ci)) < 0.5
            P.cols["ever_cheated_on"][cj[found]] = True
            E.cols["conflict"][eix[cheat][found]] = 1.0
            E.cols["trust"][eix[cheat][found]] *= 0.3
            del ev
        # premarital sex
        unmarried_pair = (dating | engaged) & ~brk
        if unmarried_pair.any():
            sexual = (E["flags"][eix] & Tie.SEXUAL) > 0
            chast = np.minimum(P["chastity_commitment"][ids], P["chastity_commitment"][j])
            h_sex = expit(p("romance.sex.base") + p("romance.sex.chastity") * (0.5 - chast) + 0.6 * engaged
                          + 0.3 * np.log1p(np.maximum(months, 0)) + 0.4 * (sim.z("sensation_seeking")[ids] + sim.z("sensation_seeking")[j]) / 2
                          - 0.5 * (sim.z("self_control")[ids] + sim.z("self_control")[j]) / 2
                          - 0.4 * (P.is_("living", "contracted")[ids] & P.is_("living", "contracted")[j]))
            sx = unmarried_pair & ~sexual & (rng.random(len(ids)) < h_sex)
            if sx.any():
                self._sex(ids[sx], j[sx], eix[sx])

    def _sex(self, a, b, eix):
        sim, w = self.sim, self.sim.w
        P, E, p = w.P, w.E, sim.p
        E.cols["flags"][eix] |= Tie.SEXUAL
        for x, y in ((a, b), (b, a)):
            P.cols["n_sex_partners"][x] += 1
            P.cols["premarital_sex_current"][x] = True
            ev = sim.emit("premarital_sex", x, b=y, cause=P.internal["rel_event"][x], mech="romance.sex")
            # dissonance pathway: some will meet with a bishop (repentance), others shift beliefs (faith system)
            lds = P["lds_member"][x] & (P["chastity_commitment"][x] > 0.35)
            pc = expit(p("romance.confession.base") + 2.0 * P["religious_identity"][x] + 1.5 * P["guilt"][x]
                       - 1.2 * P["moral_autonomy"][x])
            conf = lds & (sim.u("confess")[x] < pc)
            delay = (7 + 40 * sim.u("confess_delay")[x]).astype(int)
            P.internal["confess_day"][x[conf]] = w.day + delay[conf]
            P.internal["rel_event"][x[conf]] = ev[conf]

    def _confessions(self):
        sim, w = self.sim, self.sim.w
        P = w.P
        due = np.where(P.internal["confess_day"][: P.n] == w.day)[0]
        if len(due) == 0:
            return
        exp_pos = P["institutional_trust"][due] - 0.4
        sim.emit("bishop_confession", due, cause=P.internal["rel_event"][due], mech="romance.confession",
                 ev={"experience": exp_pos})
        P.cols["bishop_meetings"][due] = np.minimum(P["bishop_meetings"][due] + 1, 10)
        P.cols["temple_recommend"][due] = False
        P.cols["chastity_commitment"][due] = np.clip(P["chastity_commitment"][due] + 0.08, 0, 1)
        P.cols["institutional_trust"][due] = np.clip(P["institutional_trust"][due] + 0.04 * np.sign(exp_pos), 0, 1)

    def _end(self, a, b, att_a, att_b, kind="breakup", married=None):
        """End a relationship; the less-attracted partner initiates."""
        sim, w = self.sim, self.sim.w
        P, E, p = w.P, w.E, sim.p
        day = w.day
        init_a = att_a <= att_b
        initiator = np.where(init_a, a, b)
        receiver = np.where(init_a, b, a)
        months = np.maximum((day - P["rel_start_day"][a]) / 30.4, 0.1)
        keys = EdgeStore.make_keys(a, b)
        eix = E.find(keys)
        ok = eix >= 0
        E.cols["flags"][eix[ok]] = (E["flags"][eix[ok]] & ~np.uint32(Tie.ROMANTIC)) | Tie.EX
        E.cols["liking"][eix[ok]] = E["liking"][eix[ok]] - 0.3
        E.cols["att_lh"][eix[ok]] *= 0.4
        E.cols["att_hl"][eix[ok]] *= 0.4
        cause = P.internal["rel_event"][a]
        if kind == "talking":
            sim.emit("rejected", receiver, b=initiator, cause=cause, mech="romance.progress",
                     ev={"recent_rejections": np.log1p(P["rejections_recent"][receiver])})
        else:
            ev = {"rel_months_log": np.log1p(months)}
            sim.emit("breakup_initiated", initiator, b=receiver, cause=cause, mech="romance.breakup", ev=ev)
            sim.emit("breakup_received", receiver, b=initiator, cause=cause, mech="romance.breakup", ev=ev)
            P.cols["n_breakups"][np.r_[a, b]] += 1
            # rebound vs withdrawal: cooldown length varies with attachment avoidance and distress
            for x in (initiator, receiver):
                cd = (14 + 60 * expit(sim.z("attachment_avoidance")[x] + 0.5 * sim.z("neuroticism")[x])
                      * (1.5 if x is receiver else 0.7)).astype(int)
                P.internal["cooldown_until"][x] = day + cd
        is_married = married if married is not None else np.zeros(len(a), bool)
        for x in (a, b):
            P.cols["rel_status"][x] = np.where(is_married, P.code("rel_status", "divorced"), P.code("rel_status", "single"))
            P.cols["partner_id"][x] = -1
            P.cols["premarital_sex_current"][x] = False
            P.cols["relationship_satisfaction"][x] = np.nan
            P.internal["wedding_planned"][x] = -1
            P.cols["waiting_for_missionary"][x] = False

    def _weddings(self):
        sim, w = self.sim, self.sim.w
        P, E = w.P, w.E
        day = w.day
        due = np.where((P.internal["wedding_planned"][: P.n] == day) & P.is_("rel_status", "engaged"))[0]
        if len(due) == 0:
            return
        part = P["partner_id"][due]
        a = due[due < part]
        b = P["partner_id"][a].astype(np.int64)
        if len(a) == 0:
            return
        ok = P["present"][a] & P["present"][b]
        a, b = a[ok], b[ok]
        for x in (a, b):
            P.cols["rel_status"][x] = P.code("rel_status", "married")
            P.cols["married_day"][x] = day
            P.cols["age_at_marriage"][x] = P["age"][x]
            P.cols["premarital_sex_current"][x] = False
        eix = E.upsert(EdgeStore.make_keys(a, b))
        E.cols["flags"][eix] |= Tie.SPOUSE
        cause = P.internal["rel_event"][a]
        ev = sim.emit("wedding", a, b=b, cause=cause, mech="romance.engage")
        sim.emit("wedding", b, b=a, cause=cause, mech="romance.engage")
        P.internal["rel_event"][a] = ev
        P.internal["rel_event"][b] = ev
        sim.systems["housing"].couple_move(a, b, ev)

    def _crushes(self):
        """Each seeking person's strongest current romantic interest among recently-seen people."""
        sim, w = self.sim, self.sim.w
        P, E = w.P, w.E
        day = w.day
        n = P.n
        P.internal["crush_id"][:n] = -1
        P.internal["crush_att"][:n] = 0
        if E.n == 0:
            return
        lo, hi = E.endpoints()
        recent = (day - E["last_day"]) < 45
        seek = self.seeking_mask()
        avail = seek | P.is_("rel_status", "dating")  # people do notice others while dating (alternatives)
        src = np.r_[lo, hi]
        dst = np.r_[hi, lo]
        att = np.r_[E["att_lh"], E["att_hl"]]
        rec = np.r_[recent, recent]
        dst_open = seek[dst] | (P["partner_id"][dst] == src)
        m = rec & avail[src] & P["present"][dst] & dst_open & (att > 0.05)
        m &= ~((np.r_[E["flags"], E["flags"]] & Tie.EX) > 0)
        src, dst, att = src[m], dst[m], att[m]
        # exclude own partner as "alternative"
        own = P["partner_id"][src] == dst
        src, dst, att = src[~own], dst[~own], att[~own]
        if len(src) == 0:
            return
        order = np.lexsort((-att, src))
        src, dst, att = src[order], dst[order], att[order]
        first = np.r_[True, src[1:] != src[:-1]]
        P.internal["crush_id"][src[first]] = dst[first]
        P.internal["crush_att"][src[first]] = att[first]

    # ------------------------------------------------------------------ hooks used by other systems
    def handle_departure(self, ids: np.ndarray):
        """A partner leaves on a mission or moves away: wait, or break up."""
        sim, w = self.sim, self.sim.w
        P = w.P
        ids = ids[P["partner_id"][ids] >= 0]
        if len(ids) == 0:
            return
        part = P["partner_id"][ids].astype(np.int64)
        st = P["rel_status"][ids]
        u = sim.u("depart_rel")[ids]
        wait = np.isin(st, [P.code("rel_status", "dating"), P.code("rel_status", "engaged")]) & (u < 0.35)
        if wait.any():
            P.cols["waiting_for_missionary"][part[wait]] = True
        brk = ~wait & ~P.is_("rel_status", "married")[ids]
        if brk.any():
            keys = EdgeStore.make_keys(ids[brk], part[brk])
            eix = w.E.upsert(keys)
            self._end(ids[brk], part[brk], w.E.attraction_from(eix, ids[brk]) - 0.5, w.E.attraction_from(eix, part[brk]))
