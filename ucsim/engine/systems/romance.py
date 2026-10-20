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
from ..provenance import latest_between, latest_event, link, mirror, pick, state_ref, total
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
        self.ncmo_queue: list[tuple] = []   # (day, a, b, place, cause_event): meet-ups arranged over an app
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
            rng0 = np.random.default_rng([self.sim.w.seed, 88])
            lead = (10 + 110 * rng0.random(len(a))).astype(int)
            students = P["enrolled"][a] | P["enrolled"][P["partner_id"][a]]
            lead = self._break_date(lead, students, rng0.random(len(a)))
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
        rel_fit = np.where(lds_src, -p("romance.attraction.religiosity_fit") * np.abs(act_s - act_d) / 3 * (0.4 + P["imp_spirituality"][src] / 5),
                           # non-members: a religious person prefers their own tradition; anyone may balk at a devout member
                           -p("romance.attraction.religiosity_fit") * (0.7 * P["own_religiosity"][src] * (P["affiliation"][src] != P["affiliation"][dst])
                                                                       + 0.25 * (act_d == 3)))
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
        """Pull today's scheduled dates; choose venues; book each as an occasion at a time that works for both
        (systems/occasions.py: shifts and classes move it later; illness or an unavoidable clash cancels it)."""
        sim, w = self.sim, self.sim.w
        P = w.P
        day = w.day
        todays = [q for q in self.queue if q[0] == day]
        self.queue = [q for q in self.queue if q[0] > day]
        self.dates_today, self._dates_meta = [], []
        act = sim.systems["activity"]
        busy = set()
        keep = []
        for q in todays:              # bounded: today's scheduled dates (one date per person per day)
            a, b = q[1], q[2]
            if not (P["present"][a] and P["present"][b]) or a in busy or b in busy:
                continue
            busy.update((a, b))
            keep.append(q)
        if keep:
            # venues: near the midpoint of their homes (dinner or board games at home: the nearest food place stands in
            # for the location); some hikes and stargazing dates go up Y Mountain / Kyhv Peak
            k = len(keep)
            a = np.array([q[1] for q in keep], np.int64)
            b = np.array([q[2] for q in keep], np.int64)
            dtypes = np.array([q[3] for q in keep], dtype=object)
            group = np.array(["food" if DATE_VENUE_GROUP[t] == "home" else DATE_VENUE_GROUP[t] for t in dtypes], dtype=object)
            lon = (P["home_lon"][a] + P["home_lon"][b]) / 2
            lat = (P["home_lat"][a] + P["home_lat"][b]) / 2
            rng = sim.streams.gen("date_venue", day)
            pick, peak = rng.random(k), rng.random(k)
            vid = np.zeros(k, np.int64)
            for g in np.unique(group).tolist():      # bounded: venue groups
                m = group == g
                vid[m] = act.nearest(g, lon[m], lat[m], 5, pick[m])
            if not hasattr(self, "_kyhv"):
                hit = [j for j, nm in enumerate(act.v_name) if "KhPeak" in str(nm)]
                self._kyhv = hit[0] if hit else -1
            if self._kyhv >= 0:
                vid = np.where(np.isin(dtypes, ["hike", "stargazing"]) & (peak < 0.18), self._kyhv, vid)
            self.dates_today = [(int(q[1]), int(q[2]), int(v)) for q, v in zip(keep, vid)]
            self._dates_meta = [(q[3], q[4], q[5]) for q in keep]
        occ = sim.systems.get("occasions")
        self.date_occ = occ.plan_dates(self.dates_today, self._dates_meta) if occ is not None else \
            np.full(len(self.dates_today), -1, np.int64)
        # a date their schedules can't fit today (or one of them is sick) moves to the next day, for up to a week, as
        # people would rearrange it; one that still doesn't fit is dropped
        if occ is not None and len(self.dates_today):
            moved = getattr(self, "_moved", {})
            tries = int(sim.p("occasions.date.reschedule_days"))
            for j, why in enumerate(occ.date_blocked.tolist()):
                a_, b_, _ = self.dates_today[j]
                key = (min(a_, b_), max(a_, b_))
                if why == 0:
                    moved.pop(key, None)
                elif moved.get(key, 0) < tries:
                    dtype, first, cause = self._dates_meta[j]
                    moved[key] = moved.get(key, 0) + 1
                    self.queue.append((day + 1, a_, b_, dtype, first, cause))
                    P.internal["date_planned"][[a_, b_]] = day + 1
                else:
                    moved.pop(key, None)
            self._moved = moved

    def evening(self):
        """After the late evening: how today's dates went, app meet-ups, then make-outs at parties and dances."""
        self._run_dates()
        self._app_ncmo_meetups()
        occ = self.sim.systems.get("occasions")
        act = self.sim.systems["activity"]
        if occ is None:
            self._ncmo()
            return
        # dancers are at an occasion now; the NCMO step recognizes a dance floor by its context
        saved = act.ctype
        view = saved.copy()
        view[occ.dancers()] = CTX_ID["dance"]
        act.ctype = view
        try:
            self._ncmo()
        finally:
            act.ctype = saved

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
        # how much a partner is missed (the partnership drive) against what else is pressing (mind.drive)
        competing = (P["drive_achievement"] + P["drive_security"] + P["drive_rest"]) / 0.55
        mot = expit(p("romance.motivation.base")
                    + p("romance.motivation.wants") * (P["wants_relationship"] - 2.5) / 1.5
                    + p("romance.motivation.longing") * P["drive_partnership"] / 0.55
                    + p("romance.motivation.marriage_norm") * w.env["marriage_norm"] * age_norm * lds_active
                    + 0.4 * rm_recent + 0.25 * sim.z("extraversion")
                    - 0.8 * P["depressive_episode"] - p("romance.motivation.competing") * competing + sim.nudge("dating"))
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
        out = day + np.where(u < 0.75, base, near)
        # fewer dates on Sunday (they still happen): most of those move to Monday
        sun = (out - day + wd) % 7 == 6
        move = sun & ((u * 7919) % 1 >= self.sim.p("romance.date.sunday_keep"))
        return out + move

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
        # what they believe the other feels (perceived, not actual) and what they have learned to expect
        ek = E.find(EdgeStore.make_keys(ids, tgt))
        believed = np.where(ek >= 0, E.belief_from(np.maximum(ek, 0), ids), 0.0)
        exp_yes = np.clip(P["expect_accept"][ids], 0.03, 0.97)
        # the log-odds of asking, term by term (summed in this order; the ledger keeps the same terms)
        terms = {"attraction": p("romance.ask.attraction") * catt[ids],
                 "motivation": p("romance.ask.motivation") * (P["dating_motivation"][ids] - 0.5),
                 "confidence": p("romance.ask.confidence") * (P["self_esteem"][ids] - 0.5),
                 "expectation": p("romance.ask.expectation") * (np.log(exp_yes / (1 - exp_yes)) - 0.405),
                 "believed_interest": p("mind.romantic_perception.ask_weight") * (believed - 0.15),
                 "gender_norm": np.where(male, p("romance.ask.male") * w.env["men_initiate_norm"], -p("romance.ask.male") * w.env["men_initiate_norm"] * 0.9),
                 "propensity": p("romance.ask.propensity") * np.log(P["dating_propensity"][ids] + 0.5),
                 "asks_numbers": 0.25 * (P["asks_for_numbers"][ids] - 2) / 2}
        logit = total(p("romance.ask.base"), terms)
        plans = sim.systems.get("plans")
        if plans is not None:
            terms["intention"] = plans.ask_boost(ids, tgt)
            logit = logit + terms["intention"]
        u = sim.u("ask")[ids]
        pr = expit(logit) * dow_mult
        go = u < pr
        sel = np.flatnonzero(go)
        ids, tgt = ids[go], tgt[go]
        if len(ids) == 0:
            return
        # resolve duplicates: one ask per target per day
        tgt_u, first = np.unique(tgt, return_index=True)
        ids, tgt, sel = ids[first], tgt[first], sel[first]
        keys = EdgeStore.make_keys(ids, tgt)
        eix = E.find(keys)
        has = eix >= 0
        ids, tgt, eix, sel = ids[has], tgt[has], eix[has], sel[has]
        a_ji = E.attraction_from(eix, tgt)
        a_ij = E.attraction_from(eix, ids)
        first_date = E["dates"][eix] == 0
        taken = P.isin("rel_status", ["dating", "engaged", "married"])[tgt] | (P.is_("rel_status", "talking")[tgt] & (P["partner_id"][tgt] != ids))
        planned_t = P.internal["date_planned"][: P.n][tgt] >= day
        acc_terms = {"attraction": p("romance.accept.attraction") * a_ji,
                     "politeness": np.where(first_date, p("romance.accept.politeness") * (P["accepts_first_dates"][tgt] - 2) / 2, 0),
                     "motivation": p("romance.accept.motivation") * (P["dating_motivation"][tgt] - 0.4)}
        acc_logit = total(p("romance.accept.base"), acc_terms)
        acc_terms["picky"] = -(p("romance.accept.picky") * (P["picky"][tgt] - 2) / 2)
        acc_terms["taken"] = -(3.0 * taken)
        acc_terms["busy"] = -(1.5 * planned_t)
        acc = expit(acc_logit - p("romance.accept.picky") * (P["picky"][tgt] - 2) / 2 - 3.0 * taken - 1.5 * planned_t)
        ua = sim.u("accept")[tgt]
        yes = ua < acc
        # why each asked (the terms that were added) and why the other said yes or no
        D = sim.decisions
        rec = pick(terms, sel)
        rec["weekday"] = np.full(len(sel), np.log(dow_mult))
        plan_ev = plans.formed_event(ids, "ask_out", tgt) if plans is not None else np.full(len(ids), -1, np.int64)
        ask_did = D.record("ask_out", day, ids, "asked", rec, base=p("romance.ask.base"), prob=pr[sel], other=tgt,
                           refs={"attraction": ("person", tgt), "believed_interest": ("person", tgt),
                                 "intention": ("event", plan_ev)})
        acc_did = D.record("accept_date", day, tgt, np.where(yes, 0, 1), acc_terms, base=p("romance.accept.base"),
                           prob=np.where(yes, acc, 1 - acc), other=ids, refs={"attraction": ("person", ids)})
        ask_ev = sim.emit("asked_out", ids, b=tgt, value=a_ij, mech="romance.ask", decision=ask_did)
        link(sim, ask_ev, "decision", acc_did, 1.0, "answer")
        link(sim, ask_ev, "event", plan_ev, 0.5, "intention")
        mind = sim.systems["mind"]
        mind.learn_ask(ids, yes)
        mind.reveal(eix, ids, tgt, np.where(yes, 0.4, 1.0))
        if plans is not None:
            plans.asked(ids, tgt, yes, ask_ev)
        # rejections
        no = ~yes
        if no.any():
            ri, rt = ids[no], tgt[no]
            P.cols["rejections_recent"][ri] += 1
            sim.emit("rejected", ri, b=rt, cause=ask_ev[no], mech="romance.accept",
                     ev={"recent_rejections": np.log1p(P["rejections_recent"][ri])}, decision=acc_did[no])
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
        a, b = np.asarray(a, np.int64), np.asarray(b, np.int64)
        if not len(a):
            return []
        # each pair's mean preference for every date type (2.5 where there is no survey item), cold weather counting
        # against outdoor ones, plus Gumbel noise drawn in the same order as one pair at a time
        sc = np.empty((len(a), len(DATE_TYPES)))
        for k, t in enumerate(DATE_TYPES):
            c = f"fd_{t}"
            v = (P[c][a] + P[c][b]) / 2 if c in P.cols else np.full(len(a), 2.5)   # float32 like the columns
            if winter and t in ("hike", "picnic", "stargazing", "pickleball"):
                v = v - 1.5
            sc[:, k] = v
        sc += rng.gumbel(size=sc.shape) * 0.8
        return [DATE_TYPES[i] for i in sc.argmax(axis=1).tolist()]

    def _app(self, wd: int):
        """Dating apps create opportunity beyond physical propinquity."""
        sim, w = self.sim, self.sim.w
        P, E, p = w.P, w.E, sim.p
        day = w.day
        seek = self.seeking_mask() & P["app_user"]
        planned = P.internal["date_planned"][: P.n] >= day
        rate = p("romance.app.rate") * w.env["app_appeal"] * P["app_hours"] / 7.0
        u = sim.u("app")
        pool = np.where(seek & ~planned)[0]
        # most NCMOs start here: app users who want something casual match and meet up (a parked car, an apartment,
        # somewhere quiet) instead of going on a date
        self._app_ncmo(pool)
        ids = np.where(seek & ~planned & (u < rate))[0]
        if len(ids) == 0:
            return
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
            sim.systems["mind"].init_beliefs(ni, lo, hi)
        E.cols["flags"][eix] |= Tie.APP_MATCH
        # why a session happened today: the rate is a product (base × the apps' appeal × hours on them), so its log
        # splits into one term per part; the match itself needs both to like the other's profile
        did = sim.decisions.record("app_match", day, ids, "matched",
                                   {"app_hours": np.log(np.maximum(P["app_hours"][ids], 1e-3) / 7.0),
                                    "app_appeal": np.full(len(ids), np.log(max(float(w.env["app_appeal"]), 1e-6)))},
                                   base=float(np.log(p("romance.app.rate"))), prob=np.clip(rate[ids], 0, 1), other=tgt,
                                   refs={"app_hours": ("state", state_ref(sim, "app_hours", ids))})
        ev = sim.emit("app_match", ids, b=tgt, mech="romance.app", decision=did)
        # the match turns into a date with probability ~ conversation success
        go = sim.u("app_date")[ids] < p("romance.app.date_conversion")
        ids, tgt, ev = ids[go], tgt[go], ev[go]
        dd = self._next_date_day(wd, sim.u("app_dday")[ids])
        dtypes = self._date_type(ids, tgt)
        for a_, b_, d_, t_, c_ in zip(ids.tolist(), tgt.tolist(), dd.tolist(), dtypes, ev.tolist()):
            self.queue.append((d_, a_, b_, t_, True, c_))
        P.internal["date_planned"][ids] = dd
        P.internal["date_planned"][tgt] = dd

    NCMO_PLACES = ("a parked car", "an apartment", "a quiet spot")

    def _app_ncmo(self, pool: np.ndarray):
        """App users looking for something casual (romance.ncmo app terms): today's hazard per person is
        app_rate · hours/7 · logistic(app_base + βi·(interest − 1.5) + 0.5·SS − βc·(chastity − 0.5)); they match with
        another such user who likes their profile and meet up within 0–3 days."""
        sim, w = self.sim, self.sim.w
        P, p = w.P, sim.p
        if len(pool) < 10:
            return
        lean = expit(p("romance.ncmo.app_base") + p("romance.ncmo.interest") * (P["ncmo_interest"][pool] - 1.5)
                     + 0.5 * sim.z("sensation_seeking")[pool] - p("romance.ncmo.chastity") * (P["chastity_commitment"][pool] - 0.5))
        want = sim.u("app_ncmo")[pool] < p("romance.ncmo.app_rate") * P["app_hours"][pool] / 7.0 * w.env["app_appeal"] * lean
        ids = pool[want]
        open_ = pool[lean > 0.2]
        if not len(ids) or len(open_) < 5:
            return
        rng = sim.streams.gen("app_ncmo_pool", w.day)
        K = 8
        cand = open_[rng.integers(0, len(open_), (len(ids), K))]
        src = np.repeat(ids, K)
        ok = (self.compatible(src, cand.ravel()) & self.compatible(cand.ravel(), src)).reshape(-1, K) & (cand != ids[:, None])
        a1 = self.initial_attraction(src, cand.ravel()).reshape(-1, K)
        a2 = self.initial_attraction(cand.ravel(), src).reshape(-1, K)
        sc = np.where(ok & (a2 > 0), a1, -9)
        best = np.argmax(sc, axis=1)
        tgt = cand[np.arange(len(ids)), best]
        hit = sc[np.arange(len(ids)), best] > 0
        ids, tgt = ids[hit], tgt[hit]
        u = sim.u("app_ncmo_when")[ids]
        for a_, b_, uu in zip(ids.tolist(), tgt.tolist(), u.tolist()):
            self.ncmo_queue.append((w.day + int(uu * 4), a_, b_, int(uu * 1000) % 3, -1))

    def _app_ncmo_meetups(self):
        """Tonight's app meet-ups (both still single and in town)."""
        sim, w = self.sim, self.sim.w
        P, E = w.P, w.E
        day = w.day
        due = [q for q in self.ncmo_queue if q[0] <= day]
        self.ncmo_queue = [q for q in self.ncmo_queue if q[0] > day]
        if not due:
            return
        a = np.array([q[1] for q in due], np.int64)
        b = np.array([q[2] for q in due], np.int64)
        place = np.array([q[3] for q in due], np.float64)
        seek = self.seeking_mask()
        ok = seek[a] & seek[b] & P["present"][a].astype(bool) & P["present"][b].astype(bool)
        a, b, place = a[ok], b[ok], place[ok]
        if not len(a):
            return
        eix = E.upsert(EdgeStore.make_keys(a, b))
        new_k = (E["flags"][eix] & Tie.KISSED) == 0
        E.cols["flags"][eix] |= Tie.NCMO | Tie.KISSED
        E.cols["last_day"][eix] = day
        for x, y in ((a, b), (b, a)):
            P.cols["n_ncmo"][x] += 1
            P.cols["n_kissed"][x[new_k]] += 1
            sim.emit("ncmo", x, b=y, value=place, block=3, mech="romance.ncmo")

    # ------------------------------------------------------------------ dates
    def _run_dates(self):
        sim, w = self.sim, self.sim.w
        P, E, p = w.P, w.E, sim.p
        day = w.day
        if not self.dates_today:
            return
        occ_ids = np.asarray(getattr(self, "date_occ", np.full(len(self.dates_today), -1)), np.int64)
        occs = sim.systems.get("occasions")
        took_place = occs.date_happened(occ_ids) if occs is not None else np.ones(len(self.dates_today), bool)
        if not took_place.any():
            return
        keep = np.where(took_place)[0]
        a = np.array([self.dates_today[j][0] for j in keep])
        b = np.array([self.dates_today[j][1] for j in keep])
        venue = np.array([self.dates_today[j][2] for j in keep])
        dtypes = [self._dates_meta[j][0] for j in keep]
        first = np.array([self._dates_meta[j][1] for j in keep], bool)
        cause = np.array([self._dates_meta[j][2] for j in keep])
        occ_ids = occ_ids[keep]
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
        # a date is far more informative than a passing conversation about how the other feels
        mind = sim.systems["mind"]
        dr = p("mind.romantic_perception.date_reveal")
        mind.reveal(eix, a, b, dr)
        mind.reveal(eix, b, a, dr)
        E.cols["dates"][eix] += 1
        E.cols["flags"][eix] |= Tie.DATED
        E.cols["shared"][eix] += 1
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
                          block=2, mech="romance.date", ev={"quality": q[first]}, causes=[("occasion", occ_ids[first], 1.0)])
            sim.emit("first_date", b[first], b=a[first], value=q[first], cause=cause[first], place=venue[first],
                     block=2, mech="romance.date", ev={"quality": q[first]}, causes=[("occasion", occ_ids[first], 1.0)])
            ev_first[first] = e1
        if (~first).any():
            nf = ~first
            sim.emit("date", a[nf], b=b[nf], value=q[nf], cause=cause[nf], place=venue[nf], block=2,
                     mech="romance.date", ev={"quality": q[nf]}, causes=[("occasion", occ_ids[nf], 1.0)])
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
        sim.systems["mind"].reveal(eix, a, b, 1.0)
        sim.systems["mind"].reveal(eix, b, a, 1.0)
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
            P.cols["made_out_kyhv_peak"][np.r_[a[sp], b[sp]]] = True
            sim.emit("kyhv_peak", a[sp], b=b[sp], cause=cause[sp], block=2, mech="romance.kiss")
            sim.emit("kyhv_peak", b[sp], b=a[sp], cause=cause[sp], block=2, mech="romance.kiss")

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
                   + 0.4 * (loc[a] == CTX_ID["dance"])
                   - (sim.p("intimacy.ncmo.boundary") * ((P["ok_stage_touch"][a].astype(float) + P["ok_stage_touch"][b]) / 2 - 1)
                      if "intimacy" in sim.systems else 0.0))
        hit = comp & (mutual > 0.1) & (sim.u("ncmo")[a] < pn)
        if not hit.any():
            return
        a, b, eix = a[hit], b[hit], eix[hit]
        new_k = (E["flags"][eix] & Tie.KISSED) == 0
        E.cols["flags"][eix] |= Tie.NCMO | Tie.KISSED
        for x, y in ((a, b), (b, a)):
            P.cols["n_ncmo"][x] += 1
            P.cols["n_kissed"][x[new_k]] += 1
            sim.emit("ncmo", x, b=y, value=np.full(len(x), 3.0), block=2, mech="romance.ncmo")

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
        rel_mis = (np.abs(P["faith_belief"][ids] - P["faith_belief"][j]) + 0.3 * np.abs(P["activity"][ids].astype(float) - P["activity"][j]) / 3
                   + 0.5 * (P["affiliation"][ids] != P["affiliation"][j]) * np.maximum(P["own_religiosity"][ids], P["own_religiosity"][j]))
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
        # couple time: dates per week by stage (Dating survey: ~4–8 dates/month for couples; married
        # couples' weekly "date night"), on distinct days; exclusive couples also hang out a lot
        code = {s_: P.code("rel_status", s_) for s_ in ("talking", "dating", "engaged", "married")}
        uk = sim.streams.uniform("kdates", day, len(ids))
        rate = np.select([status == code["talking"], status == code["dating"], status == code["engaged"], status == code["married"]],
                         [p("romance.couple_time.talking"), p("romance.couple_time.dating"), p("romance.couple_time.engaged"),
                          p("romance.couple_time.married")], 0.0)
        k_dates = (np.floor(rate) + (uk < rate - np.floor(rate))).astype(int)
        exclusive = np.isin(status, [code["talking"], code["dating"], code["engaged"]])
        has = k_dates > 0
        if has.any():
            xa, xb, kd = ids[has], j[has], k_dates[has]
            first = self._next_date_day(6, sim.streams.uniform("cdate0", day, len(xa))) - day  # 1..7
            # a couple's dates come from their relationship's latest milestone; couples together since before the
            # story began have none, so their dates follow from the last one (dating is habitual)
            why = P.internal["rel_event"][xa].astype(np.int64)
            none = why < 0
            if none.any():
                why[none] = latest_between(sim, xa[none], xb[none], ("date", "first_date"), day - 60)
            for kk in range(int(kd.max())):
                sel = kd > kk
                dd = day + 1 + ((first[sel] - 1 + 3 * kk) % 7)
                dtypes = self._date_type(xa[sel], xb[sel])
                for a_, b_, d_, t_, c_ in zip(xa[sel].tolist(), xb[sel].tolist(), dd.tolist(), dtypes, why[sel].tolist()):
                    self.queue.append((d_, a_, b_, t_, False, c_))
        if exclusive.any():
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
            ev2 = sim.emit("relationship_started", b_, b=a_, cause=P.internal["rel_event"][a_], mech="romance.progress")
            # becoming exclusive is a gate (enough dates, two weeks of talking, mutual interest) and then a weekly
            # 12% chance: the reasons are the readiness of the tie and their latest date
            mirror(sim, ev2, ev)
            link(sim, ev, "tie", keys[dtr], mutual[dtr], "ready")
            link(sim, ev, "event", latest_between(sim, a_, b_, ("date", "first_date"), day - 30), 0.5, "last_date")
            P.internal["rel_event"][a_] = ev
            P.internal["rel_event"][b_] = ev
        # talking fizzles
        long_ = (day - tstart) > 42
        fizzle = talking & ~dtr & (long_ | (mutual < 0.3))
        fizzle &= rng.random(len(ids)) < 0.6
        if fizzle.any():
            f = np.flatnonzero(fizzle)
            why = [("tie", np.where(long_[f], keys[f], -1), np.clip((day - tstart[f]) / 42 - 1, 0.05, 1), "went_nowhere"),
                   ("tie", np.where(mutual[f] < 0.3, keys[f], -1), np.clip(0.3 - mutual[f], 0.05, 1), "low_interest")]
            self._end(ids[f], j[f], att_a[f], att_b[f], kind="talking", why=why)
        # engagement hazard (dating couples)
        both_active = P.is_("activity", "active")[ids] & P.is_("activity", "active")[j]
        ideal = (P["ideal_months_engaged"][ids] + P["ideal_months_engaged"][j]) / 2
        mean_age = (P["age"][ids] + P["age"][j]) / 2
        fin = (P["financial_stress"][ids] + P["financial_stress"][j]) / 2
        # young LDS men usually serve a mission before marrying; teen grooms are rare
        man = np.where(P.is_("sex", "M")[ids], ids, j)
        young_man = -1.8 * (P["age"][man] < 20) - 1.2 * (P["lds_member"][man] & P.is_("mission_status", "none")[man] & (P["age"][man] < 21.5))
        # same-sex marriage conflicts with Church policy: rare while either partner is active, and no
        # active-member marriage-norm boost
        same_sex = P["sex"][ids] == P["sex"][j]
        any_active = P.is_("activity", "active")[ids] | P.is_("activity", "active")[j]
        # the engagement log-odds term by term (the expression adds them in the model's order; subtracted terms are
        # recorded with their sign)
        T = {"young_man": young_man, "commitment": p("romance.engage.commitment") * commit,
             "timing": p("romance.engage.timing") * np.clip((months - ideal) / 4, -2, 2),
             "active_lds": p("romance.engage.active_lds") * (both_active & ~same_sex) * w.env["marriage_norm"],
             "same_sex": 3.0 * (same_sex & any_active), "age": 0.35 * np.clip((mean_age - 20.5) / 2, -1, 1.5),
             "money": 0.8 * fin, "mismatch": 1.2 * rel_mis}
        h_eng = expit(T["young_man"] + p("romance.engage.base") + T["commitment"] + T["timing"] + T["active_lds"]
                      - T["same_sex"] + T["age"] - T["money"] - T["mismatch"])
        eng = dating & (months >= 2.0) & (rng.random(len(ids)) < h_eng)
        if eng.any():
            a_, b_ = ids[eng], j[eng]
            for x in (a_, b_):
                P.cols["rel_status"][x] = P.code("rel_status", "engaged")
                P.cols["engaged_day"][x] = day
            # active LDS couples: usually 4–7 months (median ≈ 5½), about one in five a quick ~3 months
            k = eng.sum()
            quick = rng.random(k) < 0.2
            lds_lead = np.where(quick, rng.uniform(75, 110, k), rng.triangular(110, 165, 260, k))
            lead = np.where(both_active[eng], lds_lead, rng.uniform(120, 300, k)).astype(int)
            # student couples usually marry between semesters: move the date to the next break if one starts soon after
            students = P["enrolled"][a_] | P["enrolled"][b_]
            wed = self._break_date(day + lead, students, rng.random(eng.sum()))
            P.internal["wedding_planned"][a_] = wed
            P.internal["wedding_planned"][b_] = wed
            rec = pick(T, eng)
            for k_ in ("same_sex", "money", "mismatch"):
                rec[k_] = -rec[k_]
            did = sim.decisions.record("get_engaged", day, a_, "engaged", rec, base=p("romance.engage.base"),
                                       prob=h_eng[eng], other=b_)
            ev = sim.emit("engaged", a_, b=b_, cause=P.internal["rel_event"][a_], mech="romance.engage", decision=did)
            ev2 = sim.emit("engaged", b_, b=a_, cause=P.internal["rel_event"][a_], mech="romance.engage")
            mirror(sim, ev2, ev)
            P.internal["rel_event"][a_] = ev
            P.internal["rel_event"][b_] = ev
        # breakups
        hurt = E["hurt"][eix]
        TB = {"commitment": p("romance.breakup.commitment") * commit, "mismatch": p("romance.breakup.religious_mismatch") * rel_mis,
              "conflict": 1.5 * conflict, "hurt": 1.5 * hurt}
        h_brk = expit(p("romance.breakup.base") - TB["commitment"] + TB["mismatch"] + TB["conflict"] + TB["hurt"])
        h_brk = np.where(engaged, h_brk * 0.25, np.where(married, h_brk * p("romance.breakup.married_mult"), h_brk))
        brk = (dating | engaged | married) & ~eng & (rng.random(len(ids)) < h_brk)
        if brk.any():
            f = np.flatnonzero(brk)
            rec = pick(TB, f)
            rec["commitment"] = -rec["commitment"]
            rec["stage"] = np.where(engaged[f], np.log(0.25), np.where(married[f], np.log(p("romance.breakup.married_mult")), 0.0))
            a_, b_ = ids[f], j[f]
            why = [("event", latest_between(sim, a_, b_, ("conflict",), day - 120), 0.6, "hurt"),
                   ("event", latest_between(sim, a_, b_, ("cheating",), day - 365), 1.0, "betrayal")]
            self._end(a_, b_, att_a[f], att_b[f], married=married[f], why=why,
                      decide=("break_up", rec, p("romance.breakup.base"), h_brk[f]))
        # infidelity (rare): low commitment, high NCMO interest; often discovered → breakup risk
        excl = (dating | engaged | married) & ~brk
        TC = {"commitment": 4.0 * (commit - 0.5), "ncmo": 0.5 * (P["ncmo_interest"][ids] - 2),
              "sensation": 0.4 * sim.z("sensation_seeking")[ids]}
        h_ch = expit(-8.5 - TC["commitment"] + TC["ncmo"] + TC["sensation"])
        cheat = excl & (rng.random(len(ids)) < h_ch)
        if cheat.any():
            ci, cj = ids[cheat], j[cheat]
            P.cols["ever_cheated"][ci] = True
            rec = pick(TC, cheat)
            rec["commitment"] = -rec["commitment"]
            did = sim.decisions.record("cheat", day, ci, "cheated", rec, base=-8.5, prob=h_ch[cheat], other=cj)
            ev = sim.emit("cheating", ci, b=cj, mech="romance.breakup", decision=did)
            link(sim, ev, "tie", keys[cheat], 1.0, "the_tie")
            found = rng.random(len(ci)) < 0.5
            P.cols["ever_cheated_on"][cj[found]] = True
            E.cols["conflict"][eix[cheat][found]] = 1.0
            E.cols["trust"][eix[cheat][found]] *= 0.3
            E.cols["hurt"][eix[cheat][found]] = 1.0          # betrayal: a deep, slow-healing injury
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

    def _break_date(self, want: np.ndarray, students: np.ndarray, u: np.ndarray) -> np.ndarray:
        """Wedding dates for student couples snap (with probability `romance.wedding.break_share`) to the next
        stretch between semesters — the end of winter semester through summer, or Christmas break — if it
        begins within 75 days of the date they would otherwise pick."""
        cal = self.sim.cal
        out = want.copy()
        share = self.sim.p("romance.wedding.break_share")
        for k in np.where(students & (u < share))[0]:
            d0 = int(want[k])
            for d in range(d0, d0 + 76):
                dt = cal.date(d)
                md = (dt.month, dt.day)
                in_break = ((4, 23) <= md <= (8, 22)) or md >= (12, 18) or md <= (1, 5)
                if in_break:
                    # spread across the break's first weeks (Saturdays are the usual wedding day)
                    out[k] = d + int((u[k] / max(share, 1e-9)) * 28) // 7 * 7 + (5 - cal.weekday(d)) % 7
                    break
        return out

    def _sex(self, a, b, eix, via_ladder=False, decision=None):
        """Premarital sex begins. With the intimacy system running, only its ladder gets here (the weekly hazard
        above is bypassed); returns the first partner's event ids."""
        sim, w = self.sim, self.sim.w
        P, E, p = w.P, w.E, sim.p
        if not via_ladder and "intimacy" in sim.systems:
            return None
        E.cols["flags"][eix] |= Tie.SEXUAL
        first = None
        for x, y in ((a, b), (b, a)):
            P.cols["n_sex_partners"][x] += 1
            P.cols["premarital_sex_current"][x] = True
            ev = sim.emit("premarital_sex", x, b=y, cause=P.internal["rel_event"][x], mech="romance.sex",
                          decision=decision if first is None else None)
            if first is None:
                first = ev
            else:
                mirror(sim, ev, first)
            # dissonance pathway: some will meet with a bishop (repentance), others shift beliefs (faith system)
            lds = P["lds_member"][x] & (P["chastity_commitment"][x] > 0.35)
            pc = expit(p("romance.confession.base") + 2.0 * P["religious_identity"][x] + 1.5 * P["guilt"][x]
                       - 1.2 * P["moral_autonomy"][x])
            conf = lds & (sim.u("confess")[x] < pc)
            delay = (7 + 40 * sim.u("confess_delay")[x]).astype(int)
            P.internal["confess_day"][x[conf]] = w.day + delay[conf]
            P.internal["rel_event"][x[conf]] = ev[conf]
        return first

    def _confessions(self):
        sim, w = self.sim, self.sim.w
        P = w.P
        due = np.where(P.internal["confess_day"][: P.n] == w.day)[0]
        if len(due) == 0:
            return
        inst = sim.systems.get("institutions")
        if inst is not None:      # bishops make time for everyone who asks
            ok = inst.bishop_gate(due)
            P.internal["confess_day"][due[~ok]] = w.day + 1
            due = due[ok]
            if len(due) == 0:
                return
        exp_pos = P["institutional_trust"][due] - 0.4
        ev = sim.emit("bishop_confession", due, cause=P.internal["rel_event"][due], mech="romance.confession",
                      ev={"experience": exp_pos})
        P.cols["bishop_meetings"][due] = np.minimum(P["bishop_meetings"][due] + 1, 10)
        P.cols["temple_recommend"][due] = False
        P.cols["chastity_commitment"][due] = np.clip(P["chastity_commitment"][due] + 0.08, 0, 1)
        P.cols["institutional_trust"][due] = np.clip(P["institutional_trust"][due] + 0.04 * np.sign(exp_pos), 0, 1)
        if inst is not None:      # recommend held for a few weeks, often the sacrament too; monthly follow-ups
            inst.counsel(due, "sex", ev)

    def _end(self, a, b, att_a, att_b, kind="breakup", married=None, why=None, decide=None):
        """End a relationship; the less-attracted partner initiates.

        Provenance: `decide` = (decision kind, terms, base, prob) aligned with `a` is recorded as the initiator's
        decision; `why` lists extra typed causes (kind, refs, weight, role) aligned with `a`. The receiver's event
        names the person who ended it."""
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
        E.cols["hurt"][eix[ok]] = np.maximum(E["hurt"][eix[ok]], 0.5 if kind != "talking" else 0.2)
        E.cols["att_lh"][eix[ok]] *= 0.4
        E.cols["att_hl"][eix[ok]] *= 0.4
        cause = P.internal["rel_event"][a]
        did = None
        if decide is not None:
            dk, terms, base, prob = decide
            did = sim.decisions.record(dk, day, initiator, 0, terms, base=base, prob=prob, other=receiver)
        if kind == "talking":
            first = sim.emit("rejected", receiver, b=initiator, cause=cause, mech="romance.progress",
                             ev={"recent_rejections": np.log1p(P["rejections_recent"][receiver])}, decision=did)
            link(sim, first, "person", initiator, 1.0, "ended_by")
        else:
            ev = {"rel_months_log": np.log1p(months)}
            first = sim.emit("breakup_initiated", initiator, b=receiver, cause=cause, mech="romance.breakup", ev=ev,
                             decision=did)
            got = sim.emit("breakup_received", receiver, b=initiator, cause=cause, mech="romance.breakup", ev=ev)
            mirror(sim, got, first)
            link(sim, got, "person", initiator, 1.0, "ended_by")
            P.cols["n_breakups"][np.r_[a, b]] += 1
            # rebound vs withdrawal: cooldown length varies with attachment avoidance and distress
            for x in (initiator, receiver):
                cd = (14 + 60 * expit(sim.z("attachment_avoidance")[x] + 0.5 * sim.z("neuroticism")[x])
                      * (1.5 if x is receiver else 0.7)).astype(int)
                P.internal["cooldown_until"][x] = day + cd
        link(sim, first, "tie", keys, 1.0, "the_tie")
        for kind_, refs, wgt, role_ in why or ():
            link(sim, first, kind_, refs, wgt, role_)
        is_married = married if married is not None else np.zeros(len(a), bool)
        for x in (a, b):
            P.cols["rel_status"][x] = np.where(is_married, P.code("rel_status", "divorced"), P.code("rel_status", "single"))
            P.cols["partner_id"][x] = -1
            P.cols["premarital_sex_current"][x] = False
            P.cols["sexual_satisfaction"][x] = 0.0            # a married-life measure; none once it ends
            P.cols["relationship_satisfaction"][x] = np.nan
            P.internal["wedding_planned"][x] = -1
            P.cols["waiting_for_missionary"][x] = False
        return first

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
        # a partner away on the day (a trip home, a mission farewell): the wedding moves a week rather than vanishing;
        # if one of them has left the area for good, the engagement ends
        gone = ~ok & ((P["departure_day"][a] >= 0) | (P["departure_day"][b] >= 0))
        late = ~ok & ~gone
        if late.any():
            P.internal["wedding_planned"][a[late]] = day + 7
            P.internal["wedding_planned"][b[late]] = day + 7
        if gone.any():
            ga, gb = a[gone], b[gone]
            ge = E.upsert(EdgeStore.make_keys(ga, gb))
            left = np.maximum(latest_event(sim, ga, ("left_area", "mission_departure"), day - 400),
                              latest_event(sim, gb, ("left_area", "mission_departure"), day - 400))
            self._end(ga, gb, E.attraction_from(ge, ga), E.attraction_from(ge, gb), why=[("event", left, 1.0, "left")])
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
        ev2 = sim.emit("wedding", b, b=a, cause=cause, mech="romance.engage")
        mirror(sim, ev2, ev)
        # the date was set when they got engaged; couples engaged before the story began point at their tie
        keys = EdgeStore.make_keys(a, b)
        link(sim, ev, "tie", np.where(cause < 0, keys, -1), 1.0, "engaged_before")
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
        """A partner leaves on a mission or moves away: wait, or break up. Returns (leavers, breakup events) so the
        caller can point each breakup at the departure it logs afterwards."""
        sim, w = self.sim, self.sim.w
        P = w.P
        none = (np.empty(0, np.int64), np.empty(0, np.int64))
        ids = ids[P["partner_id"][ids] >= 0]
        if len(ids) == 0:
            return none
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
            ev = self._end(ids[brk], part[brk], w.E.attraction_from(eix, ids[brk]) - 0.5, w.E.attraction_from(eix, part[brk]))
            return ids[brk], ev
        return none
