"""Occasions: planned things people go to — who plans them, who is invited, who can make it, who comes.

A dinner at 7:30, a Saturday party planned on Wednesday, a date at the creamery, the Friday stake dance. Each is an
occasion in the OccasionBook (engine/ledger.py) with a day, a start minute, a length, a place and an organizer:

    host decides (host_occasion) ─► picks a kind and a time that fits their own day (occasion_kind)
        ─► invites friends, closeness-weighted (housemates and neighbors in person, others by text)
        ─► invitees notice (in person at once; a text maybe, depending on phone habits and being busy)
        ─► decide (attend_occasion): closeness, friends going, wanting company, tiredness, exams, travel time,
           how late they'd be — and hard limits: a shift or class the whole time, no way to get there
        ─► on the day, some who said yes don't come (show_up, with the reason) and some come late
        ─► attend in the blocks it overlaps (ctx "occasion"; household members at home walk in)
        ─► what it cost the host, whether it becomes a weekly tradition, who takes it over when the host moves

Open occasions (dances, and the calendar's football games or devotionals) are announced rather than sent: everyone in
the kind's `audience` weighs the kind's `base` and `interest` against travel and other plans, choosing at most one of
the evening's events; past `capacity` the least keen are turned away. Dates are occasions at a venue. Commitments
(class blocks, shifts in minutes, accepted occasions) make `free_window`, `can_make` and `agenda` answerable for anyone.

Social actions from the user (engine/interventions.py, target_type "social") are lowered here: an invitation, a
weekly series, a new time, an introduction, a ride, reaching out, a job offer — arranged by an editor (people still
decide) or done as a person (only people they know, only when they're free, only what they can afford).

Randomness: per-person daily streams (`sim.u`) so the Original and a What-if draw the same numbers for the same
person; anything a user action causes draws from streams named after that action.
"""
from __future__ import annotations

import numpy as np
from scipy.special import expit
from scipy.stats import poisson

from .. import clock
from ..core import splitmix64
from ..ledger import CHANNEL_ID, ORIGIN_ID, RESPONSE_ID, STATUS_ID, Table
from ..state import CTX_ID, EdgeStore, Tie
from .activity import A as ACT_CODE

OCC = CTX_ID["occasion"]
WHERE_ACT = {"home": "gathering", "venue": "venue", "campus": "campus", "stadium": "venue", "meetinghouse": "ward_activity",
             "park": "outdoors", "group": "club", "complex": "home", "workplace": "work", "family": "away"}
WHERE_TALK = {"home": 2.24, "venue": 0.4, "campus": 0.5, "stadium": 0.35, "meetinghouse": 0.35, "park": 0.5, "group": 0.5,
              "complex": 0.5, "workplace": 0.4, "family": 1.0}
HOSTED = ("gathering", "dinner", "game_night", "party", "study_group")     # what engine hosts choose among
TRADITION_KINDS = ("gathering", "dinner", "game_night", "study_group")
# date types → (preferred start, minutes); weekend dates can be earlier in the day
DATE_TIMES = {"ice_cream": (20 * 60, 90), "restaurant": (18 * 60 + 30, 120), "hike": (17 * 60, 180), "board_games": (19 * 60, 150),
              "cook_together": (18 * 60, 150), "movie_theater": (19 * 60, 150), "soda_shop": (20 * 60 + 30, 60),
              "museum": (15 * 60, 120), "picnic": (17 * 60 + 30, 120), "stargazing": (21 * 60, 120),
              "sports_game": (19 * 60, 180), "pickleball": (18 * 60, 90)}
BYU = (-111.6493, 40.2500)
UVU = (-111.7129, 40.2773)
# commitment kinds; a guest at a get-together can come late or leave early for something else ("occasion"), the rest
# can't be moved around (a shift, a class, hosting, a date)
KIND_C = {"shift": 0, "class": 1, "occasion": 2, "host": 3, "date": 4}


def _rup15(m):
    return (np.asarray(m, np.int64) + 14) // 15 * 15


def _pair_u(seed: int, a, key, salt: int) -> np.ndarray:
    """A uniform draw per (person, occasion key). The same person deciding about the same occasion draws the same number
    in the Original and in a What-if whatever else happened that day (common random numbers), and deciding again after
    a change (a new time, an offered ride) reuses it, so only what changed can change the answer."""
    with np.errstate(over="ignore"):
        salt = ((int(seed) * 1_000_003 + np.asarray(salt, np.int64)) & 0xFFFFFFFF).astype(np.uint64)
        k = splitmix64(np.asarray(key, np.int64).astype(np.uint64) + salt)
        x = splitmix64(k ^ (np.asarray(a, np.int64).astype(np.uint64) * np.uint64(0x9E3779B97F4A7C15)))
    return ((x >> np.uint64(11)).astype(np.float64) + 0.5) / float(1 << 53)


class Occasions:
    def __init__(self, sim):
        self.sim = sim
        self.book = sim.book
        self.series_members: dict[int, list] = {}    # series id -> attendee arrays of its last instances (regulars)
        self.rides: dict[tuple[int, int], int] = {}  # (occasion, rider) -> driver (offered rides)
        self.max_lead = 7                             # longest planning lead time seen (days); user actions extend it
        self._aud_cache: dict[tuple[int, int], np.ndarray] = {}
        self.trips = Table({"inv": (np.int64, -1), "minutes": (np.int16, -1), "mode": (np.int8, -1), "late": (np.int16, 0),
                            "origin": (np.int8, -1)}, capacity=1 << 12)
        self._kinds()
        self._reset_day(-1)

    # ------------------------------------------------------------------ vocabulary
    def _kinds(self):
        book = self.book
        K = len(book.kinds)
        self.k_rate = np.ones(K, np.float32)
        self.k_talk = np.full(K, 1.0, np.float32)
        self.k_social = np.zeros(K, bool)
        self.k_ncmo = np.zeros(K, bool)
        self.k_open = np.zeros(K, bool)
        self.k_act = np.full(K, ACT_CODE["venue"], np.uint8)
        self.k_cost = np.zeros(K, np.float32)
        self.k_invites = np.full(K, 5.0, np.float32)
        self.k_start = np.full(K, 19 * 60, np.int32)
        self.k_dur = np.full(K, 120, np.int32)
        self.k_latest = np.full(K, 21 * 60, np.int32)
        self.k_lead = np.zeros(K, np.int32)
        self.k_where = []
        for c, kind in enumerate(book.kinds):
            s = book.vocab[kind]
            where = s.get("where", "venue")
            self.k_where.append(where)
            self.k_rate[c] = float(s.get("rate", 1.0))
            self.k_talk[c] = float(s.get("talk_h", WHERE_TALK.get(where, 0.5)))
            self.k_social[c] = bool(s.get("social", False))
            self.k_ncmo[c] = bool(s.get("ncmo", False))
            self.k_open[c] = bool(s.get("open", False))
            self.k_act[c] = ACT_CODE.get(s.get("act") or WHERE_ACT.get(where, "venue"), ACT_CODE["venue"])
            self.k_cost[c] = float(s.get("cost", 0.0))
            self.k_invites[c] = float(s.get("invites", 5.0))
            self.k_start[c] = clock.parse_hhmm(s.get("start", "19:00"))
            self.k_dur[c] = int(s.get("dur", 120))
            self.k_latest[c] = clock.parse_hhmm(s["latest"]) if s.get("latest") else self.k_start[c] + 90
            self.k_lead[c] = int(s.get("lead", 0))
        self.k_where = np.array(self.k_where, dtype=object)
        self.k_names = np.array(book.kinds, dtype=object)
        self.hosted_codes = np.array([book.kind_id[k] for k in HOSTED], np.int16)
        self.date_code = book.kind_id["date"]

    def init(self):
        sim = self.sim
        P = sim.w.P
        P.add_internal("occ_last_kind", np.int16, -1)       # open occasions: what they went to last, and when
        P.add_internal("occ_last_day", np.int32, -10_000)
        # student shifts were drawn before class schedules existed: fit them around classes now
        stu = np.where(P["employed"] & P["enrolled"])[0]
        if len(stu):
            sim.systems["activity"].assign_shifts(stu)

    def _reset_day(self, day: int):
        self._day = day
        self._resolved: set[int] = set()
        e64, e16, e32 = np.empty(0, np.int64), np.empty(0, np.int16), np.empty(0, np.int32)
        self.R = {"person": e64, "occ": e64, "arrive": e32, "leave": e32, "inv": e64, "ride_by": e32, "came": np.empty(0, bool),
                  "travel": e16, "mode": np.empty(0, np.int8)}
        self.today: dict[int, dict] = {}      # occasion id -> {kind, start, end, unit, organizer, ctx, act, social}
        self._n_cancel = 0
        self._tarr_sig = None
        self.host_decision: dict[int, int] = {}
        self.burden_shift = set()

    # ------------------------------------------------------------------ the day (start phase)
    def plan_day(self):
        """Morning: weekly series, hosting decisions, invitations noticed and answered, today's attendance plan."""
        sim, w = self.sim, self.sim.w
        day, wd = w.day, int(w.env["weekday"])
        if self._day != day:
            self._reset_day(day)
        for school in ("BYU", "UVU"):     # new class schedules: working students rearrange their shifts
            if day > 0 and sim.cal.term_start(school, day):
                P = w.P
                ids = np.where(P["employed"] & P["enrolled"] & P.is_("school", school))[0]
                sim.systems["activity"].assign_shifts(ids)
        self._series(day, wd)
        self._host(day, wd)
        self._dances(day, wd)
        self._notice(day)
        self.resolve()

    def _dances(self, day: int, wd: int):
        """Friday and Saturday nights every dance venue holds a dance at about 9 pm (YSA stake dances, country-dance
        nights): an open occasion, announced rather than sent."""
        if wd not in (4, 5):
            return
        act = self.sim.systems["activity"]
        vids = np.where(act.v_type == "dance")[0]
        if not len(vids):
            return
        O = self.book.occ
        have = O["place"][(O["day"] == day) & (O["kind"] == self.book.kind_id["dance"])] if O.n else np.empty(0)
        vids = vids[~np.isin(vids, have)]
        if not len(vids):
            return
        c = self.book.kind_id["dance"]
        for v in vids.tolist():      # bounded: a handful of dance venues
            self.book.plan("dance", day, int(self.k_start[c]), int(self.k_dur[c]), place=v, lon=float(act.v_lon[v]),
                           lat=float(act.v_lat[v]), ctx=OCC, origin="engine", open_=True, label=act.v_name[v],
                           capacity=int(self.book.vocab["dance"].get("capacity", -1)))

    def _person_day(self) -> tuple[int, int]:
        return self.sim.w.day, int(self.sim.w.env["weekday"])

    # ------------------------------------------------------------------ hosting
    def _host(self, day: int, wd: int):
        sim, w = self.sim, self.sim.w
        P, p = w.P, sim.p
        n = P.n
        net = sim.systems["network"]
        if not hasattr(net, "adj"):
            return
        indptr, nbr, _ = net.padded()
        deg = np.diff(indptr)[:n]
        appr = sim.systems["mind"].social_pull()[0]
        base = [p("activity.gathering.host_weekday")] * 4 + [p("activity.gathering.host_friday"),
                                                             p("activity.gathering.host_saturday"),
                                                             p("activity.gathering.host_sunday")]
        cul = sim.systems["culture"]
        unit = P["unit_id"]
        elig = P["present"] & (unit >= 0) & (P["n_friends"] >= 2) & ~P["ill"] & (deg > 0)
        t_e = 0.6 * sim.z("extraversion")
        t_c = 0.8 * appr
        hm = cul.host_mult(unit)
        t_cul = np.log(np.maximum(hm, 1e-6))
        ahead = p("occasions.plan.plan_ahead_share")
        share_today = 1 - ahead if wd in (4, 5) else 1.0
        ph = base[wd] * share_today * np.exp(t_e + t_c) * hm
        hosts = np.where(elig & (sim.u("occ_host") < ph))[0]
        plans = [(hosts, day, np.full(len(hosts), np.log(base[wd] * share_today)), np.zeros(len(hosts)), ph[hosts])]
        # weekend parties planned two to five days ahead
        for lead in range(2, 6):
            twd = (wd + lead) % 7
            if twd not in (4, 5):
                continue
            ph2 = base[twd] * ahead / 4 * np.exp(t_e + t_c) * hm
            h2 = np.where(elig & (sim.u("occ_host_ahead", lead) < ph2))[0]
            h2 = h2[~np.isin(h2, hosts)]
            plans.append((h2, day + lead, np.full(len(h2), np.log(base[twd])), np.full(len(h2), np.log(ahead / 4)), ph2[h2]))
        all_hosts = []
        taken = np.zeros(n, bool)
        for h, tday, b0, t_ahead, prob in plans:
            sel = ~taken[h]
            h, b0, t_ahead, prob = h[sel], b0[sel], t_ahead[sel], prob[sel]
            if not len(h):
                continue
            taken[h] = True
            kind = self._choose_kind(h, tday, day)
            oid, ok = self._plan_hosted(h, kind, tday)
            if ok.any():
                F = {"base": b0[ok], "extraversion": t_e[h[ok]], "want_company": t_c[h[ok]], "place_culture": t_cul[h[ok]]}
                if tday != day:
                    F["plan_ahead"] = t_ahead[ok]
                did = sim.decisions.record("host_occasion", day, h[ok], "hosted", F, prob=np.clip(prob[ok], 0, 1), occasion=oid)
                self.book.occ.set("decision", oid, did)
                self.host_decision.update(zip(oid.tolist(), did.tolist()))
                self._invite(oid, h[ok], kind[ok], tday)
                all_hosts.append(h[ok])
            if (~ok).any():     # wanted to host, but their own day had no room for it
                sim.decisions.record("host_occasion", day, h[~ok], "did_not", {"base": b0[~ok]},
                                     constraints={"busy": np.ones(int((~ok).sum()), bool)})
        self.hosts_today = np.concatenate(all_hosts) if all_hosts else np.empty(0, np.int64)
        sim.systems["activity"].hosts_today = self.hosts_today

    def _choose_kind(self, h: np.ndarray, tday: int, day: int) -> np.ndarray:
        """What kind of get-together (Gumbel-max over utilities; recorded with the terms of the chosen kind)."""
        sim, w = self.sim, self.sim.w
        P, p = w.P, sim.p
        twd = sim.cal.weekday(tday)
        k = len(h)
        ahead = tday != day
        weekend = float(twd in (4, 5))
        enrolled = P["enrolled"][h].astype(float)
        exams = np.where(P["school"][h] == 1, bool(w.env.get("exam_week_BYU")), bool(w.env.get("exam_week_UVU"))) * enrolled
        married = P.is_("rel_status", "married")[h].astype(float)
        T = {nm: np.zeros((k, len(HOSTED))) for nm in ("base", "sunday", "weekend", "cooking", "gaming", "outgoing", "thrill",
                                                         "apartment", "married", "studies", "exams")}
        G, D, GN, PA, SG = range(5)
        T["base"][:, D], T["base"][:, GN], T["base"][:, PA], T["base"][:, SG] = -0.6, -0.8, -2.2, -1.6
        T["sunday"][:, D] = p("occasions.plan.dinner_sunday") * (twd == 6)
        T["sunday"][:, PA] = -2.0 * (twd == 6)        # no Sunday parties in Provo
        T["weekend"][:, PA] = p("occasions.plan.party_weekend") * weekend
        T["weekend"][:, GN] = 0.3 * weekend
        T["weekend"][:, SG] = -1.2 * weekend
        T["cooking"][:, D] = 0.4 * P["cooking"][h]
        T["gaming"][:, GN] = 0.7 * P["gaming"][h]
        T["outgoing"][:, PA] = 0.5 * sim.z("extraversion")[h]
        T["thrill"][:, PA] = 0.4 * sim.z("sensation_seeking")[h]
        T["apartment"][:, PA] = 0.5 * P["home_social_culture"][h]
        T["married"][:, D] = 0.5 * married
        T["married"][:, PA] = -1.0 * married
        T["studies"][:, SG] = np.where(enrolled > 0, 0.6, -9.0)
        T["exams"][:, SG] = p("occasions.plan.study_exams") * exams
        U = sum(T.values())
        if ahead:                                     # planned days ahead: a party (or a game night)
            U[:, [G, D, SG]] = -9.0
        g = sim.streams.gen("occ_kind", day, int(ahead)).gumbel(size=(P.n, len(HOSTED)))[h]
        ch = np.argmax(U + g, axis=1)
        ex = np.exp(U - U.max(axis=1, keepdims=True))
        prob = ex[np.arange(k), ch] / ex.sum(axis=1)
        sim.decisions.record("occasion_kind", day, h, ch, {nm: M[np.arange(k), ch] for nm, M in T.items()}, prob=prob)
        return self.hosted_codes[ch]

    def _plan_hosted(self, h: np.ndarray, kind: np.ndarray, tday: int):
        """Start time (fitted to the host's own day) and place; returns (occasion ids, which hosts could)."""
        sim, w = self.sim, self.sim.w
        P = w.P
        day = w.day
        rng = sim.streams.gen("occ_start", day, tday - day)
        jit = np.array([-30, 0, 0, 30])[rng.integers(0, 4, P.n)][h]
        start = self.k_start[kind] + jit + np.where((sim.cal.weekday(tday) == 5) & (kind == self.book.kind_id["party"]), 30, 0)
        dur = self.k_dur[kind] + np.array([-30, 0, 0, 30])[rng.integers(0, 4, P.n)][h]
        unit = P["unit_id"][h]
        home = np.array([self.k_where[c] == "home" for c in kind], bool)
        lon = np.where(home, w.units.lon[np.maximum(unit, 0)], np.nan)
        lat = np.where(home, w.units.lat[np.maximum(unit, 0)], np.nan)
        camp = ~home
        if camp.any():      # a study group on the host's campus (the library, a study room)
            byu = P["school"][h] == 1
            lon = np.where(camp, np.where(byu, BYU[0] + 0.0012, UVU[0] + 0.0010), lon)
            lat = np.where(camp, np.where(byu, BYU[1] + 0.0018, UVU[1] - 0.0008), lat)
        # the host has to be free: move it later (up to the kind's latest start) to fit a shift or a class
        f = self._feasible(h, tday, start, dur, lon, lat, host=True)
        start2 = np.where(f["conflict"] | (f["free_from"] > start - 15), _rup15(f["free_from"] + 30), start).astype(np.int32)
        ok = start2 <= self.k_latest[kind]
        f2 = self._feasible(h, tday, start2, dur, lon, lat, host=True)
        ok &= ~f2["conflict"]
        if not ok.any():
            return np.empty(0, np.int64), ok
        oid = self.book.plan(self.k_names[kind[ok]], tday, start2[ok], dur[ok], organizer=h[ok], org_kind="household", org_id=unit[ok], ctx=OCC,
                             place=np.where(home[ok], unit[ok], -1), lon=lon[ok], lat=lat[ok], origin="engine", created_day=day)
        return oid, ok

    # ------------------------------------------------------------------ invitations
    def _invite(self, oid: np.ndarray, hosts: np.ndarray, kind: np.ndarray, tday: int, members: dict | None = None,
                channel_default: str = "text", salt: int = 29):
        """Closeness-weighted invitations from each host's casual friends and friends (or a series' regulars)."""
        sim, w = self.sim, self.sim.w
        P, E, p = w.P, w.E, sim.p
        day = w.day
        n = P.n
        if members is None:
            net = sim.systems["network"]
            indptr, nbr, _ = net.padded()
            deg = (indptr[hosts + 1] - indptr[hosts]).astype(np.int64)
            # draws keyed on the host's occasion and each candidate, so one host's change never reshuffles another's
            okey = self.occ_key(oid)
            kmean = self.k_invites[kind] * p("activity.gathering.invites") / 5.0
            kk = np.minimum(np.minimum(poisson.ppf(_pair_u(w.seed, hosts, okey, salt), np.maximum(kmean, 0.1)), 40) + 1,
                            deg).astype(np.int64)
            tot = int(deg.sum())
            if tot == 0:
                return np.empty(0, np.int64)
            seg = np.repeat(np.arange(len(hosts)), deg)
            off = np.arange(tot) - np.repeat(np.cumsum(deg) - deg, deg)
            cand = nbr[np.repeat(indptr[hosts], deg) + off].astype(np.int64)
            h_rep = hosts[seg]
            close = sim.systems["encounters"]._closeness(h_rep, cand)
            near = ((P["unit_id"][cand] == P["unit_id"][h_rep]) | ((P["complex_id"][cand] == P["complex_id"][h_rep]) & (P["complex_id"][cand] >= 0)))
            gum = -np.log(-np.log(_pair_u(w.seed, cand, okey[seg], salt + 1)))
            score = np.log(0.15 + np.clip(close, 0, 1)) + p("occasions.invite.roommate_boost") * near + gum
            score = np.where(P["present"][cand], score, -np.inf)
            order = np.lexsort((-score, seg))
            rank = np.empty(tot, np.int64)
            starts = np.cumsum(deg) - deg
            rank[order] = np.arange(tot) - np.repeat(starts, deg)
            pick = (rank < kk[seg]) & np.isfinite(score)
            occ_rep, person, inviter = oid[seg][pick], cand[pick], h_rep[pick]
        else:
            occ_rep, person, inviter = members["occ"], members["person"], members["inviter"]
        if not len(person):
            return np.empty(0, np.int64)
        same = (P["unit_id"][person] == P["unit_id"][inviter]) & (P["unit_id"][person] >= 0)
        nb = (P["complex_id"][person] == P["complex_id"][inviter]) & (P["complex_id"][person] >= 0)
        ch = np.where(same | nb, CHANNEL_ID["in_person"], CHANNEL_ID[channel_default])
        inv = self.book.invite(occ_rep, person, inviter=inviter, channel=ch, day=day, block=0)
        self.deliver(inv)
        return inv

    def deliver(self, inv_ids: np.ndarray, channel: str | None = None):
        """Who notices an invitation, and when. In person: at once. A text or group chat: seen in time with a chance that
        rises with phone habits and falls when they're at work or in class when it arrives; unseen texts get another
        chance each morning until the day. Messaging (wave 2) replaces this hook with threads and attention."""
        sim, w = self.sim, self.sim.w
        P, p = w.P, sim.p
        book = self.book
        inv_ids = np.atleast_1d(np.asarray(inv_ids, np.int64))
        if not len(inv_ids):
            return np.zeros(0, bool)
        I = book.inv
        pos = I.pos(inv_ids)
        ok = pos >= 0
        pos = pos[ok]
        person = I.cols["person"][pos].astype(np.int64)
        chan = I.cols["channel"][pos]
        fresh = I.cols["seen_day"][pos] < 0
        busy = (sim.systems["activity"].shift_minutes(1, int(w.env["weekday"]))[person] > 0)
        pr = expit(p("occasions.invite.seen_base") + p("occasions.invite.seen_phone") * sim.z("social_media_hours")[person]
                   - p("occasions.invite.seen_busy") * busy)
        # a text gets a fresh chance each morning it is still unseen (the day is part of the salt)
        u = self._u(person, I.cols["occ"][pos], 17 + 7 * (w.day - I.cols["sent_day"][pos].astype(np.int64)))
        seen = fresh & ((chan == CHANNEL_ID["in_person"]) | (chan == CHANNEL_ID["family"]) | (u < pr))
        I.cols["seen_day"][pos[seen]] = w.day
        self._decide(I.ids[pos[seen]])
        return seen

    def _notice(self, day: int):
        """Unseen texts for upcoming occasions get another chance this morning."""
        I, O = self.book.inv, self.book.occ
        if not I.n:
            return
        pend = (I["seen_day"] < 0) & (I["response"] == RESPONSE_ID["pending"]) & (I["sent_day"] < day) & ~I["walk_in"]
        if not pend.any():
            return
        ids = I["id"][pend]
        od = O.get("day", I["occ"][pend], default=-1)
        st = O.get("status", I["occ"][pend], default=STATUS_ID["cancelled"])
        live = (od >= day) & (st == STATUS_ID["planned"])
        if live.any():
            self.deliver(ids[live])

    # ------------------------------------------------------------------ deciding
    def _occ_cols(self, occ_ids: np.ndarray) -> dict:
        O = self.book.occ
        pos = np.maximum(O.pos(occ_ids), 0)
        return {c: O.cols[c][pos] for c in ("kind", "day", "start", "dur", "lon", "lat", "organizer", "series", "place",
                                            "origin", "status", "open", "capacity")}

    def occ_key(self, occ_ids) -> np.ndarray:
        """A key for each occasion that is the same in the Original and a What-if: who organizes it (or where an open one
        is), the day and the kind — not its row id (a user action that adds an occasion shifts every later id) and not
        its start time (moving a dinner later must not reshuffle who would have come anyway). User-made occasions also
        key on their name, so they draw numbers of their own."""
        O = self.book.occ
        pos = np.maximum(O.pos(np.atleast_1d(np.asarray(occ_ids, np.int64))), 0)
        g = lambda c: O.cols[c][pos].astype(np.int64)   # noqa: E731
        org, place = g("organizer"), g("place")
        k = ((g("day") + 1) * 1_000_003 + org + 1) * 131 + g("kind")
        k = k * 7919 + np.where(org < 0, place + 2, 0)
        user = g("origin") != ORIGIN_ID["engine"]
        return np.where(user, k * 104_729 + g("label") + 3 + 17 * g("origin"), k)

    def _u(self, people, occ_ids, salt: int) -> np.ndarray:
        """Per (person, occasion) uniforms (see _pair_u); `salt` separates the questions asked (seen, go, show up)."""
        return _pair_u(self.sim.w.seed, people, self.occ_key(occ_ids), salt)

    def _decide(self, inv_ids: np.ndarray, salt: int = 11, extra: dict | None = None):
        """attend_occasion for invitations just seen: feasibility, the factors, the yes/no, the record."""
        sim, w = self.sim, self.sim.w
        P, E, p = w.P, w.E, sim.p
        book = self.book
        inv_ids = np.atleast_1d(np.asarray(inv_ids, np.int64))
        if not len(inv_ids):
            return
        I = book.inv
        pos = I.pos(inv_ids)
        keep = (pos >= 0)
        pos = pos[keep]
        inv_ids = inv_ids[keep]
        pos = pos[I.cols["response"][pos] == RESPONSE_ID["pending"]]
        if not len(pos):
            return
        inv_ids = I.ids[pos]
        person = I.cols["person"][pos].astype(np.int64)
        occ = I.cols["occ"][pos].astype(np.int64)
        oc = self._occ_cols(occ)
        org = oc["organizer"].astype(np.int64)
        k = len(pos)
        rides = np.array([(int(o), int(i)) in self.rides for o, i in zip(occ, person)], bool) if self.rides else np.zeros(k, bool)
        f = self._feasible(person, oc["day"], oc["start"], oc["dur"], oc["lon"], oc["lat"], occ=occ, ride=rides)
        appr = sim.systems["mind"].social_pull()[0]
        close = np.where(org >= 0, sim.systems["encounters"]._closeness(person, np.maximum(org, 0)), 0.0)
        ek = E.find(EdgeStore.make_keys(person, np.maximum(org, 0)))
        hurt = np.where((org >= 0) & (ek >= 0), E["hurt"][np.maximum(ek, 0)], 0.0)
        exams = np.where(P["school"][person] == 1, bool(w.env.get("exam_week_BYU")), bool(w.env.get("exam_week_UVU"))) & P["enrolled"][person]
        cx = np.where(org >= 0, P["complex_id"][np.maximum(org, 0)], -1)
        F = {
            "close_organizer": 2.0 * close,
            "want_company": 0.8 * appr[person],
            "extraversion": 0.4 * sim.z("extraversion")[person],
            "tired": -1.5 * P["fatigue"][person],
            "exam_soon": -p("occasions.attend.exam") * exams,
            "travel": -p("occasions.attend.travel") * np.maximum(f["travel"] - 10, 0) / 15.0,
            "late": -p("occasions.attend.late") * f["late"] / 30.0,
            "place_culture": p("culture.feedback.reputation") * sim.systems["culture"].complex_social_z(cx),
            "intention": sim.systems["plans"].accept_boost()[person],
            "hurt": -p("occasions.attend.hurt") * hurt,
        }
        if rides.any():
            F["ride"] = 0.3 * rides
        # weekly series: people who came last week tend to come again
        ser = oc["series"]
        if (ser >= 0).any():
            came_last = np.zeros(k, bool)
            for s in np.unique(ser[ser >= 0]).tolist():          # bounded: series with an instance today
                mem = self.series_members.get(int(s))
                if mem:
                    m = ser == s
                    came_last[m] = np.isin(person[m], mem[-1])
            F["routine"] = p("occasions.attend.routine") * came_last
        for nm, v in (extra or {}).items():
            F[nm] = v
        b0 = np.full(k, p("activity.gathering.accept_base"))
        logit0 = b0 + sum(F.values())
        # friends going: friends (stage ≥ 3) among the same occasion's invitees who would likely say yes
        F["friends_going"] = p("occasions.attend.friends_going") * np.log1p(self._friends_likely(occ, person, expit(logit0)))
        total = logit0 + F["friends_going"]
        pyes = expit(total)
        ill = P["ill"][person] & (oc["day"] == w.day)
        conflict, cant = f["conflict"] & ~ill, f["cant"] & ~f["conflict"] & ~ill
        blocked = conflict | cant | ill
        u = self._u(person, occ, salt)
        yes = (u < pyes) & ~blocked
        # two yeses for the same evening: keep the one they were keener on
        yes = self._one_per_evening(person, oc["day"], oc["start"], oc["dur"], pyes, yes)
        did = sim.decisions.record("attend_occasion", w.day, person, np.where(yes, "yes", "no").tolist(), F, base=b0,
                                   prob=np.where(blocked, 1.0, np.where(yes, pyes, 1 - pyes)), occasion=occ, other=org,
                                   refs={"close_organizer": ("person", org), "hurt": ("person", org)},
                                   constraints={"conflict": conflict, "cant_get_there": cant, "ill": ill}, block=0)
        book.respond(inv_ids, np.where(yes, RESPONSE_ID["yes"], RESPONSE_ID["no"]).astype(np.int8), w.day, did)
        self._note_trips(inv_ids, f)

    def _friends_likely(self, occ: np.ndarray, person: np.ndarray, p0: np.ndarray) -> np.ndarray:
        """For each invitee, how many friends (stage ≥ 3) among the same occasion's invitees would likely go."""
        E = self.sim.w.E
        k = len(occ)
        out = np.zeros(k)
        if k < 2:
            return out
        order = np.argsort(occ, kind="stable")
        so = occ[order]
        starts = np.flatnonzero(np.r_[True, so[1:] != so[:-1]])
        sizes = np.diff(np.r_[starts, k])
        big = sizes >= 2
        if not big.any():
            return out
        rows_i, rows_j = [], []
        for s, m in zip(starts[big], sizes[big]):    # bounded: invitees per occasion
            g = order[s: s + m]
            ii, jj = np.meshgrid(g, g, indexing="ij")
            msk = ii != jj
            rows_i.append(ii[msk])
            rows_j.append(jj[msk])
        ri, rj = np.concatenate(rows_i), np.concatenate(rows_j)
        e = E.find(EdgeStore.make_keys(person[ri], person[rj]))
        fr = (e >= 0) & (E["stage"][np.maximum(e, 0)] >= 3) & (p0[rj] > 0.5)
        np.add.at(out, ri[fr], 1.0)
        return out

    def _one_per_evening(self, person, day, start, dur, pyes, yes):
        """Two yeses that overlap: keep the one they were keener on (a yes given on an earlier day is a commitment
        already, handled by feasibility)."""
        if yes.sum() < 2:
            return yes
        idx = np.where(yes)[0]
        order = idx[np.lexsort((-pyes[idx], day[idx], person[idx]))]
        pg = person[order] * 65536 + day[order]
        first = np.r_[True, pg[1:] != pg[:-1]]
        lead = order[np.maximum.accumulate(np.where(first, np.arange(len(order)), 0))]
        s0, e0 = start[lead], start[lead] + dur[lead]
        clash = ~first & (start[order] < e0) & (start[order] + dur[order] > s0)
        keep = yes.copy()
        keep[order[clash]] = False
        return keep

    def _note_trips(self, inv_ids, f):
        self.trips.append(len(inv_ids), inv=inv_ids, minutes=np.clip(f["travel"], 0, 32000).astype(np.int16), mode=f["mode"],
                          late=np.clip(f["late"], 0, 32000).astype(np.int16), origin=f["origin"])

    # ------------------------------------------------------------------ commitments and feasibility
    def _commitments(self, persons: np.ndarray, days: np.ndarray, exclude_occ: np.ndarray | None, host: bool):
        """Firm commitments of each (person, day) row: shifts, classes, occasions they said yes to or organize.
        Returns (row, start, end, lon, lat, kind) arrays."""
        sim, w = self.sim, self.sim.w
        P = w.P
        cal = sim.cal
        k = len(persons)
        rows, cs, ce, clon, clat, ck = [], [], [], [], [], []
        wd = np.array([cal.weekday(int(d)) for d in days]) if len(np.unique(days)) > 1 else np.full(k, cal.weekday(int(days[0])))
        # shifts
        s = P.internal["shift_start"][persons, wd].astype(np.int32)
        e = P.internal["shift_end"][persons, wd].astype(np.int32)
        m = (s >= 0) & P["employed"][persons]
        emp = np.maximum(P["employer_id"][persons], 0)
        rows.append(np.where(m)[0])
        cs.append(s[m])
        ce.append(e[m])
        clon.append(w.employers["lon"][emp[m]])
        clat.append(w.employers["lat"][emp[m]])
        ck.append(np.full(int(m.sum()), KIND_C["shift"]))
        # classes at their clock times (activity.class_times), on school days in term
        acad = sim.systems["academics"]
        if len(acad.sec_days):
            if acad.stu_secs.shape[0] < P.n:
                acad.section_now(0, 0)      # grows the schedule table for new arrivals
            secs = acad.stu_secs[persons]
            udays = np.unique(days)
            tb = np.array([bool(cal.term("BYU", int(d))) and not cal.holiday(int(d)) for d in udays])
            tu = np.array([bool(cal.term("UVU", int(d))) and not cal.holiday(int(d)) for d in udays])
            di = np.searchsorted(udays, days)
            term = np.where(P["school"][persons] == 1, tb[di], tu[di])
            valid = (secs >= 0) & (P["enrolled"][persons] & (wd < 5) & term)[:, None]
            ss = np.maximum(secs, 0)
            meets = valid & ((acad.sec_days[ss] >> wd[:, None].astype(np.uint8)) & 1).astype(bool)
            r, j = np.nonzero(meets)
            st, en = sim.systems["activity"].class_times(ss[r, j])
            byu = P["school"][persons][r] == 1
            rows.append(r)
            cs.append(st)
            ce.append(en)
            clon.append(np.where(byu, BYU[0], UVU[0]))
            clat.append(np.where(byu, BYU[1], UVU[1]))
            ck.append(np.full(len(r), KIND_C["class"]))
        # occasions they're going to (said yes) or organizing
        I, O = self.book.inv, self.book.occ
        dset = np.unique(days)
        if O.n:
            # rows are appended in time order: only occasions created (and invitations sent) within the longest lead
            # time before these days can be on them
            since = int(dset[0]) - self.max_lead - 1
            o0 = int(np.searchsorted(O["created_day"], since))
            live = np.isin(O["day"][o0:], dset) & (O["status"][o0:] == STATUS_ID["planned"])
            if live.any():
                oids = O["id"][o0:][live]
                org = O["organizer"][o0:][live].astype(np.int64)
                i0 = int(np.searchsorted(I["sent_day"], since)) if I.n else 0
                yes_i = (I["response"][i0:] == RESPONSE_ID["yes"]) & np.isin(I["occ"][i0:], oids) if I.n else np.zeros(0, bool)
                c_person = np.r_[org, I["person"][i0:][yes_i].astype(np.int64)] if I.n else org
                c_occ = np.r_[oids, I["occ"][i0:][yes_i]] if I.n else oids
                cpos = O.pos(c_occ)
                c_day = O.cols["day"][cpos]
                key_c = c_person * 65536 + c_day
                key_r = persons.astype(np.int64) * 65536 + days.astype(np.int64)
                order = np.argsort(key_c, kind="stable")
                kc = key_c[order]
                lo = np.searchsorted(kc, key_r, side="left")
                hi = np.searchsorted(kc, key_r, side="right")
                cnt = hi - lo
                if cnt.sum():
                    r = np.repeat(np.arange(k), cnt)
                    j = order[np.repeat(lo, cnt) + (np.arange(int(cnt.sum())) - np.repeat(np.cumsum(cnt) - cnt, cnt))]
                    jo = c_occ[j]
                    keep = jo >= 0
                    if exclude_occ is not None:
                        keep &= jo != np.asarray(exclude_occ)[r]
                    r, j = r[keep], j[keep]
                    pj = cpos[j]
                    st = O.cols["start"][pj].astype(np.int32)
                    rows.append(r)
                    cs.append(st)
                    ce.append(st + O.cols["dur"][pj].astype(np.int32))
                    clon.append(O.cols["lon"][pj])
                    clat.append(O.cols["lat"][pj])
                    ck.append(np.where(c_person[j] == O.cols["organizer"][pj], KIND_C["host"],
                                       np.where(O.cols["kind"][pj] == self.date_code, KIND_C["date"], KIND_C["occasion"])))
        cat = lambda xs, dt: np.concatenate(xs).astype(dt) if xs else np.empty(0, dt)   # noqa: E731
        return (cat(rows, np.int64), cat(cs, np.int32), cat(ce, np.int32), cat(clon, np.float64), cat(clat, np.float64),
                cat(ck, np.int8))

    def _feasible(self, persons, day, start, dur, lon, lat, occ=None, ride=None, host: bool = False, firm=False) -> dict:
        """Could each person get there, and how late? Rows are (person, occasion window). A commitment covering the
        whole window is a conflict; one ending inside it makes them late (they travel from there); one starting inside
        it makes them leave early. A get-together they're a guest at bends instead: they leave it in time or come to it
        late; and for something firm (`firm`: hosting, a date) those get-togethers don't count at all. With less than
        min_stay minutes left it's a conflict (no time) or, if only the trip eats the time, no way to get there."""
        sim, w = self.sim, self.sim.w
        P, p = w.P, sim.p
        persons = np.atleast_1d(np.asarray(persons, np.int64))
        k = len(persons)
        B = lambda x, dt: np.broadcast_to(np.asarray(x, dt), (k,)).copy()   # noqa: E731
        day, start, dur = B(day, np.int64), B(start, np.int32), B(dur, np.int32)
        lon, lat = B(lon, np.float64), B(lat, np.float64)
        end = start + dur
        free_from = np.full(k, -1, np.int32)
        leave_by = end.copy()
        conflict = np.zeros(k, bool)
        olon, olat = P["home_lon"][persons].astype(np.float64), P["home_lat"][persons].astype(np.float64)
        origin = np.full(k, -1, np.int8)
        blocker = np.full(k, -1, np.int8)
        blocker_end = np.full(k, -1, np.int32)
        if k:
            r, cs, ce, cl, ct, ck = self._commitments(persons, day, occ if occ is None else np.broadcast_to(np.asarray(occ, np.int64), (k,)), host)
            flex = ck == KIND_C["occasion"]
            firm_r = np.broadcast_to(np.asarray(firm, bool) | bool(host), (k,))
            if flex.any() and firm_r.any():
                keep = ~(flex & firm_r[r])
                r, cs, ce, cl, ct, ck, flex = r[keep], cs[keep], ce[keep], cl[keep], ct[keep], ck[keep], flex[keep]
            if len(r):
                ce = np.where(flex & (cs < start[r]), np.minimum(ce, start[r] - 15), ce)    # they leave that one in time
                s_r, e_r = start[r], end[r]
                covers = (cs <= s_r) & (ce >= e_r)
                conflict[r[covers]] = True
                blocker[r[covers]] = ck[covers]
                blocker_end[r[covers]] = ce[covers]
                np.maximum.at(free_from, r[covers], ce[covers])
                before = ~covers & (cs < s_r) & (ce > s_r - 120)
                if before.any():
                    rb = r[before]
                    o = np.lexsort((ce[before], rb))          # the latest-ending commitment before the start wins
                    rb, ceb, clb, ctb, ckb = rb[o], ce[before][o], cl[before][o], ct[before][o], ck[before][o]
                    last = np.r_[rb[1:] != rb[:-1], True]
                    rb, ceb, clb, ctb, ckb = rb[last], ceb[last], clb[last], ctb[last], ckb[last]
                    free_from[rb] = np.maximum(free_from[rb], ceb)
                    has = np.isfinite(clb) & np.isfinite(ctb)
                    olon[rb[has]], olat[rb[has]] = clb[has], ctb[has]
                    origin[rb] = ckb
                    late_block = ceb > start[rb]
                    blocker[rb[late_block]] = ckb[late_block]
                    blocker_end[rb[late_block]] = ceb[late_block]
                during = ~covers & (cs >= s_r) & (cs < e_r)
                if during.any():
                    np.minimum.at(leave_by, r[during], cs[during] - 15)
        # travel
        travel = np.zeros(k, np.float32)
        mode = np.full(k, -1, np.int8)
        here = np.isfinite(lon) & np.isfinite(lat)
        if here.any():
            tm = sim.travel
            wd = np.array([sim.cal.weekday(int(d)) for d in day]) if len(np.unique(day)) > 1 else np.full(k, sim.cal.weekday(int(day[0])))
            dep_h = np.clip(np.maximum(free_from, start - 30) // 60, 0, 23)
            ride = np.zeros(k, bool) if ride is None else np.broadcast_to(np.asarray(ride, bool), (k,))
            grp = wd * 100 + dep_h
            for g in np.unique(grp[here]):         # bounded: weekday × departure hour
                m = here & (grp == g)
                mins, md = tm.trip(persons[m], lon[m], lat[m], int(g // 100), int(g % 100) * 60,
                                   ride=ride[m] if ride[m].any() else None, origin_lon=olon[m], origin_lat=olat[m])
                travel[m], mode[m] = mins, md
        # free beforehand: they leave in time; coming from a commitment: its end plus the trip
        arrive = np.where(free_from >= 0, np.maximum(start, free_from + np.ceil(travel).astype(np.int32)), start)
        need = np.minimum(p("occasions.attend.min_stay"), 0.5 * dur)
        stay = np.minimum(end, leave_by) - arrive
        stay0 = np.minimum(end, leave_by) - np.maximum(start, np.where(free_from >= 0, free_from, start))
        conflict |= stay0 < need
        cant = ~conflict & (stay < need)
        late = np.clip(arrive - start, 0, None)
        return {"ok": ~conflict & ~cant, "conflict": conflict, "cant": cant, "arrive": arrive.astype(np.int32),
                "leave": np.minimum(end, leave_by).astype(np.int32), "late": late.astype(np.int32), "travel": travel,
                "mode": mode, "free_from": free_from, "origin": origin, "blocker": blocker, "blocker_end": blocker_end}

    # ------------------------------------------------------------------ today's attendance
    def resolve(self):
        """Settle who will be at each of today's occasions not yet settled (engine, user, calendar, dates, open)."""
        sim, w = self.sim, self.sim.w
        day = w.day
        if self._day != day:
            self._reset_day(day)
        O = self.book.occ
        if not O.n:
            return
        m = (O["day"] == day) & (O["status"] == STATUS_ID["planned"])
        ids = O["id"][m]
        ids = np.array([i for i in ids.tolist() if i not in self._resolved], np.int64)
        if not len(ids):
            return
        # only what hasn't started yet (or is under way, for something planned mid-day)
        oc = self._occ_cols(ids)
        now = w.hour * 60
        live = (oc["start"].astype(np.int32) + oc["dur"].astype(np.int32)) > max(now, 0)
        ids = ids[live]
        if not len(ids):
            return
        self._resolved.update(ids.tolist())
        oc = self._occ_cols(ids)
        for i, o in enumerate(ids.tolist()):
            c = int(oc["kind"][i])
            st = int(oc["start"][i])
            self.today[o] = {"kind": c, "start": st, "end": st + int(oc["dur"][i]), "dur": int(oc["dur"][i]),
                             "unit": int(oc["place"][i]) if self.k_where[c] == "home" else -1, "organizer": int(oc["organizer"][i]),
                             "ctx": CTX_ID["date"] if c == self.date_code else OCC, "act": int(self.k_act[c]),
                             "social": bool(self.k_social[c]), "open": bool(oc["open"][i])}
        op = oc["open"].astype(bool)
        if (~op).any():
            self._resolve_closed(ids[~op])
        if op.any():
            self._resolve_open(ids[op])

    def _add_rows(self, person, occ, arrive, leave, inv, ride_by=None, travel=None, mode=None):
        k = len(person)
        if not k:
            return
        R = self.R
        add = {"person": np.asarray(person, np.int64), "occ": np.asarray(occ, np.int64), "arrive": np.asarray(arrive, np.int32),
               "leave": np.asarray(leave, np.int32), "inv": np.asarray(inv, np.int64),
               "ride_by": np.full(k, -1, np.int32) if ride_by is None else np.asarray(ride_by, np.int32), "came": np.zeros(k, bool),
               "travel": np.zeros(k, np.int16) if travel is None else np.clip(travel, 0, 32000).astype(np.int16),
               "mode": np.full(k, -1, np.int8) if mode is None else np.asarray(mode, np.int8)}
        for c in R:
            R[c] = np.r_[R[c], add[c]]

    def _resolve_closed(self, ids: np.ndarray):
        """Organizers and those who said yes: who still comes (show_up), when they arrive, when they leave."""
        sim, w = self.sim, self.sim.w
        P, p = w.P, sim.p
        book = self.book
        day = w.day
        oc = self._occ_cols(ids)
        # organizers: a host who is sick, gone, or now has a shift or class over it calls it off (recorded with why)
        org = oc["organizer"].astype(np.int64)
        og = np.maximum(org, 0)
        has_org = org >= 0
        sick = has_org & P["present"][og] & P["ill"][og]
        cand = has_org & P["present"][og] & ~sick
        busy = np.zeros(len(ids), bool)
        fo = None
        if cand.any():
            fo = self._feasible(org[cand], day, oc["start"][cand], oc["dur"][cand], oc["lon"][cand], oc["lat"][cand],
                                occ=ids[cand], host=True)
            busy[cand] = fo["conflict"]
        cancel = has_org & ~cand | busy
        off = sick | busy
        if off.any():
            sim.decisions.record("show_up", day, org[off], "did_not_come", {}, occasion=ids[off],
                                 constraints={"ill": sick[off], "conflict": busy[off]})
        if cancel.any():
            book.mark(ids[cancel], "cancelled")
            for o in ids[cancel].tolist():
                self.today.pop(o, None)
                self._n_cancel += 1
        go = cand & ~busy
        if go.any():
            sub = ~busy[cand]
            f_go = {k_: v[sub] for k_, v in fo.items()}
            home = np.array([self.k_where[c] == "home" for c in oc["kind"][go]])
            arr = np.where(home, oc["start"][go], f_go["arrive"])
            self._add_rows(org[go], ids[go], arr, f_go["leave"], np.full(int(go.sum()), -1),
                           travel=np.where(home, 0, f_go["travel"]), mode=np.where(home, -1, f_go["mode"]))
        live = ids[~cancel]
        if not len(live):
            return
        I = book.inv
        if not I.n:
            return
        m = np.isin(I["occ"], live) & (I["response"] == RESPONSE_ID["yes"]) & ~I["walk_in"]
        if not m.any():
            return
        inv = I["id"][m]
        person = I["person"][m].astype(np.int64)
        occ = I["occ"][m].astype(np.int64)
        c = self._occ_cols(occ)
        o_org = c["organizer"].astype(np.int64)
        rides = np.array([(int(o), int(i)) in self.rides for o, i in zip(occ, person)], bool) if self.rides else np.zeros(len(occ), bool)
        f = self._feasible(person, day, c["start"], c["dur"], c["lon"], c["lat"], occ=occ, ride=rides)
        ill = P["ill"][person] | ~P["present"][person]
        close = np.where(o_org >= 0, sim.systems["encounters"]._closeness(person, np.maximum(o_org, 0)), 0.5)
        ago = day - I["decided_day"][m]
        F = {"days_ahead": -p("occasions.show_up.days_ahead") * np.maximum(ago, 0), "tired": -1.0 * P["fatigue"][person],
             "close_organizer": 1.0 * close}
        base = np.full(len(person), p("occasions.show_up.base"))
        pc = expit(base + sum(F.values()))
        conflict, cant = f["conflict"] & ~ill, f["cant"] & ~f["conflict"] & ~ill
        flake = (self._u(person, occ, 13) >= pc) & (c["kind"] != self.date_code)   # dates: only illness or a clash stops them
        no = ill | conflict | cant | flake
        if no.any():
            sim.decisions.record("show_up", day, person[no], "did_not_come", {k_: v[no] for k_, v in F.items()}, base=base[no],
                                 prob=np.where(ill[no] | conflict[no] | cant[no], 1.0, 1 - pc[no]), occasion=occ[no], other=o_org[no],
                                 refs={"close_organizer": ("person", o_org[no])},
                                 constraints={"ill": ill[no], "conflict": conflict[no], "cant_get_there": cant[no]})
        go = ~no
        if not go.any():
            return
        lat_mean = p("occasions.lateness.base_minutes") * np.exp(-0.3 * sim.z("conscientiousness")[person[go]])
        extra = (sim.streams.gen("occ_late", day).exponential(1.0, P.n)[person[go]] * lat_mean).astype(np.int32)
        arrive = np.minimum(f["arrive"][go] + extra, f["leave"][go] - 15)
        drivers = np.array([self.rides.get((int(o), int(i)), -1) for o, i in zip(occ[go], person[go])], np.int32) if self.rides else None
        self._add_rows(person[go], occ[go], arrive, f["leave"][go], inv[go], ride_by=drivers, travel=f["travel"][go], mode=f["mode"][go])

    def _audience(self, kind_code: int) -> np.ndarray:
        """People an open occasion of this kind speaks to (the kind's audience filter)."""
        from ...analysis.query import evaluate_filter
        sim = self.sim
        spec = self.book.vocab[self.book.kinds[kind_code]]
        aud = spec.get("audience")
        if isinstance(aud, list):
            aud = {"and": aud} if aud else None
        key = (int(kind_code), sim.w.day)
        if key not in self._aud_cache:      # once per kind and day (a dance at five venues asks the same question)
            if len(self._aud_cache) > 64:
                self._aud_cache = {k: v for k, v in self._aud_cache.items() if k[1] == sim.w.day}
            self._aud_cache[key] = evaluate_filter(sim.w, _normalize_filter(aud), sim=sim)
        return self._aud_cache[key]

    def _interest(self, kind_code: int, people: np.ndarray) -> np.ndarray:
        sim = self.sim
        P = sim.w.P
        spec = self.book.vocab[self.book.kinds[kind_code]]
        out = np.zeros(len(people))
        for var, beta in (spec.get("interest") or {}).items():
            if var not in P:
                continue
            vs = P.specs.get(var)
            if vs is not None and (vs.dtype == "bool" or (vs.range and vs.range[0] >= 0 and vs.range[1] <= 1)):
                x = P[var][people].astype(np.float64)
            elif vs is not None and vs.dtype in ("u1", "i2") and vs.range and vs.range[1] <= 5:
                x = P[var][people].astype(np.float64) / max(vs.range[1], 1)
            else:
                x = sim.z(var)[people]
            out += float(beta) * np.nan_to_num(x)
        return out

    def _resolve_open(self, ids: np.ndarray):
        """Open occasions: everyone in an audience weighs going against the evening's other events and not going."""
        sim, w = self.sim, self.sim.w
        P, p = w.P, sim.p
        day = w.day
        oc = self._occ_cols(ids)
        order = np.lexsort((oc["place"], oc["kind"], oc["start"]))
        ids = ids[order]
        oc = {c: v[order] for c, v in oc.items()}
        st = oc["start"].astype(np.int32)
        en = st + oc["dur"].astype(np.int32)
        # groups of events that overlap in time compete for the same evening
        grp = np.zeros(len(ids), np.int64)
        cur_end, g = -1, -1
        for j in range(len(ids)):
            if st[j] >= cur_end:
                g += 1
            grp[j] = g
            cur_end = max(cur_end, en[j])
        pres = P["present"] & ~P["ill"]
        plans_b = sim.systems["plans"]
        for gi in range(g + 1):
            J = np.where(grp == gi)[0]
            aud = np.zeros((P.n, len(J)), bool)
            for c_i, j in enumerate(J):
                aud[:, c_i] = self._audience(int(oc["kind"][j])) & pres
            people = np.where(aud.any(axis=1))[0]
            if not len(people):
                continue
            Ug = np.full((len(people), len(J) + 1), -np.inf)
            Ug[:, 0] = 0.0
            terms = []
            feas = []
            for c_i, j in enumerate(J):
                kc = int(oc["kind"][j])
                sel = aud[people, c_i]
                pp = people[sel]
                f = self._feasible(pp, day, oc["start"][j], oc["dur"][j], oc["lon"][j], oc["lat"][j], occ=np.full(len(pp), ids[j]))
                spec = self.book.vocab[self.book.kinds[kc]]
                T = {"base": np.full(len(pp), float(spec.get("base", -3.0))), "interest": self._interest(kc, pp),
                     "travel": -p("occasions.attend.travel") * np.maximum(f["travel"] - 10, 0) / 15.0,
                     "late": -p("occasions.attend.late") * f["late"] / 30.0}
                intent = 0.8 * plans_b._active("meet_people")[pp] * plans_b._resolve()[pp] * self.k_social[kc]
                if self.k_act[kc] == ACT_CODE["venue"] and self.k_social[kc]:
                    wb = sim.whatif.choice_bias(pp)
                    if not np.isscalar(wb):
                        intent = intent + wb[:, 5]
                T["intention"] = p("occasions.open.intention") * intent
                T["routine"] = p("occasions.open.routine") * ((P.internal["occ_last_kind"][pp] == kc)
                                                               & (P.internal["occ_last_day"][pp] == day - 7))
                cost = self.k_cost[kc]
                if cost > 0:
                    T["money"] = -1.0 * P["financial_stress"][pp] * min(cost / 10.0, 2.0)
                u = sum(T.values())
                u = np.where(f["ok"], u, -np.inf)
                Ug[np.where(sel)[0], c_i + 1] = u
                terms.append((sel, T, f))
            key = int(sum(int(oc["kind"][j]) * 1009 + int(oc["place"][j]) % 100003 + int(st[j]) for j in J)) % 2_000_000_000
            G = sim.streams.gen("open_attend", day, key).gumbel(size=(P.n, len(J) + 1))[people]
            ch = np.argmax(Ug + G, axis=1)
            fin = np.isfinite(Ug)
            ex = np.where(fin, np.exp(np.where(fin, Ug, 0) - np.where(fin, Ug, -np.inf).max(axis=1, keepdims=True)), 0.0)
            prob = ex / ex.sum(axis=1, keepdims=True)
            for c_i, j in enumerate(J):
                sel, T, f = terms[c_i]
                loc = np.where(sel)[0]
                went = ch[loc] == c_i + 1
                if not went.any():
                    continue
                pp = people[loc][went]
                cap = int(oc["capacity"][j])
                margin = (Ug + G)[loc[went], c_i + 1]
                full = np.zeros(len(pp), bool)
                if 0 <= cap < len(pp):
                    full[np.argsort(-margin, kind="stable")[cap:]] = True
                Tw = {k_: v[went] for k_, v in T.items()}
                did = sim.decisions.record("attend_occasion", day, pp, np.where(full, "no", "yes").tolist(), Tw,
                                           prob=np.where(full, 1.0, prob[loc[went], c_i + 1]), occasion=np.full(len(pp), ids[j]),
                                           constraints={"full": full}, block=0)
                go = ~full
                pg = pp[go]
                if not len(pg):
                    continue
                inv = self.book.invite(int(ids[j]), pg, channel="announcement", day=day)
                self.book.inv.cols["seen_day"][self.book.inv.pos(inv)] = day
                self.book.respond(inv, "yes", day, did[go])
                fw = {k_: v[went][go] for k_, v in f.items()}
                self._note_trips(inv, fw)
                lat_mean = p("occasions.lateness.base_minutes") * np.exp(-0.3 * sim.z("conscientiousness")[pg])
                extra = (sim.streams.gen("occ_late", day, 1).exponential(1.0, P.n)[pg] * lat_mean).astype(np.int32)
                arrive = np.minimum(fw["arrive"] + extra, fw["leave"] - 15)
                self._add_rows(pg, np.full(len(pg), ids[j]), arrive, fw["leave"], inv, travel=fw["travel"], mode=fw["mode"])

    # ------------------------------------------------------------------ blocks (called by activity.choose)
    def _today_arrays(self):
        sig = (len(self.today), next(reversed(self.today)) if self.today else -1, self._n_cancel)
        if getattr(self, "_tarr_sig", None) == sig:
            return self._tarr
        ids = np.fromiter(self.today.keys(), np.int64, len(self.today))
        order = np.argsort(ids)
        ids = ids[order]
        vals = list(self.today.values())
        get = lambda c, dt: np.array([vals[j][c] for j in order], dt)   # noqa: E731
        self._tarr_sig = sig
        self._tarr = ids, {"ctx": get("ctx", np.uint8), "act": get("act", np.uint8), "dur": get("dur", np.int32),
                           "start": get("start", np.int32), "unit": get("unit", np.int64)}
        return self._tarr

    def block_plan(self, b: int) -> dict:
        """Who is expected at which occasion in block b: person, occ, minutes there in the block, ctx, act, share, arrive
        (sorted by person, longest first)."""
        self.resolve()
        R = self.R
        empty = {"person": np.empty(0, np.int64), "occ": np.empty(0, np.int64), "minutes": np.empty(0, np.int32),
                 "ctx": np.empty(0, np.uint8), "act": np.empty(0, np.uint8), "share": np.empty(0, np.float32),
                 "arrive": np.empty(0, np.int32)}
        if not len(R["person"]) or not self.today:
            return empty
        tid, T = self._today_arrays()
        j = np.minimum(np.searchsorted(tid, R["occ"]), len(tid) - 1)
        live = tid[j] == R["occ"]
        mins = clock.overlap(R["arrive"], np.maximum(R["leave"] - R["arrive"], 0), b)
        thr = np.minimum(30, T["dur"][j] // 2 - 1)
        m = live & (mins >= np.maximum(thr, 10))
        if not m.any():
            return empty
        j = j[m]
        person, occ, mins = R["person"][m], R["occ"][m], mins[m].astype(np.int32)
        order = np.lexsort((-mins, person))
        return {"person": person[order], "occ": occ[order], "minutes": mins[order], "ctx": T["ctx"][j][order],
                "act": T["act"][j][order], "share": (mins / np.maximum(T["dur"][j], 1))[order].astype(np.float32),
                "arrive": R["arrive"][m][order]}

    def mark_present(self, b: int, persons: np.ndarray, occs: np.ndarray, arrive: np.ndarray):
        """First block someone is actually there: record the attendance (arrival minute, ride)."""
        R = self.R
        if not len(persons) or not len(R["person"]):
            return
        key_r = (R["occ"] << 24) ^ R["person"]
        key = (occs.astype(np.int64) << 24) ^ persons.astype(np.int64)
        order = np.argsort(key_r, kind="stable")
        pos = np.searchsorted(key_r[order], key)
        pos = np.minimum(pos, len(order) - 1)
        rows = order[pos]
        ok = key_r[rows] == key
        rows = rows[ok]
        new = ~R["came"][rows]
        rows = rows[new]
        if not len(rows):
            return
        R["came"][rows] = True
        inv = R["inv"][rows]
        has = inv >= 0
        if has.any():
            self.book.attend(R["occ"][rows][has], R["person"][rows][has], arrive=R["arrive"][rows][has],
                             ride_by=R["ride_by"][rows][has], inv_ids=inv[has])
        if (~has).any():     # organizers: a row of their own (not a walk-in)
            ids = self.book.attend(R["occ"][rows][~has], R["person"][rows][~has], arrive=R["arrive"][rows][~has],
                                   day=self.sim.w.day)
            R["inv"][rows[~has]] = ids
            self.book.inv.cols["walk_in"][self.book.inv.pos(ids)] = False

    def walk_ins(self, b: int, ctype: np.ndarray, cid: np.ndarray, act: np.ndarray, share: np.ndarray):
        """Household members at home (and friends who dropped by) join a home occasion held in their apartment."""
        if not self.today:
            return
        tid, T = self._today_arrays()
        mins = clock.overlap(T["start"], T["dur"], b)
        m = (T["unit"] >= 0) & (T["ctx"] == OCC) & (mins >= np.maximum(np.minimum(30, T["dur"] // 2 - 1), 10))
        if not m.any():
            return
        units, oids, mins, acts, durs, starts = T["unit"][m], tid[m], mins[m], T["act"][m], T["dur"][m], T["start"][m]
        at_unit = (ctype == CTX_ID["unit"]) & np.isin(cid, units)
        who = np.where(at_unit)[0]
        if not len(who):
            return
        order = np.argsort(units, kind="stable")
        j = order[np.searchsorted(units[order], cid[who])]
        occ = oids[j]
        ctype[who] = OCC
        cid[who] = occ
        act[who] = acts[j]
        share[who] = mins[j] / np.maximum(durs[j], 1)
        key = (occ << 24) ^ who.astype(np.int64)
        if not hasattr(self, "_walk_keys") or self._walk_day != self._day:
            self._walk_keys, self._walk_day = np.empty(0, np.int64), self._day
        fresh = ~np.isin(key, self._walk_keys)
        if fresh.any():
            self._walk_keys = np.r_[self._walk_keys, key[fresh]]
            arrive = np.maximum(starts[j][fresh], int(clock.START[b])).astype(np.int32)
            self.book.attend(occ[fresh], who[fresh], arrive=arrive, day=self.sim.w.day)

    def social_now(self, ctype: np.ndarray, cid: np.ndarray) -> np.ndarray:
        """People at a social occasion right now (counts toward social events per month)."""
        m = ctype == OCC
        out = np.zeros(len(ctype), bool)
        if m.any():
            k = self.book.occ.get("kind", cid[m], default=0)
            out[np.where(m)[0]] = self.k_social[k]
        return out

    # ------------------------------------------------------------------ hooks for encounters and romance
    def kind_of(self, occ_ids) -> np.ndarray:
        return self.book.occ.get("kind", np.asarray(occ_ids, np.int64), default=0)

    def rate_mult(self, occ_ids) -> np.ndarray:
        """Encounter rate at each occasion relative to the calibrated get-together rate."""
        return self.k_rate[self.kind_of(occ_ids)]

    def talk_hours(self, occ_ids) -> np.ndarray:
        """Hours a conversation lasts there (a dinner vs a dance floor)."""
        return self.k_talk[self.kind_of(occ_ids)]

    def ncmo_ok(self, occ_ids) -> np.ndarray:
        return self.k_ncmo[self.kind_of(occ_ids)]

    def organizer_of(self, occ_ids) -> np.ndarray:
        return self.book.occ.get("organizer", np.asarray(occ_ids, np.int64), default=-1).astype(np.int64)

    def plan_dates(self, dates: list, meta: list) -> np.ndarray:
        """Romance's dates for today as occasions at their venue, at a time that works for both (−1: couldn't happen)."""
        sim, w = self.sim, self.sim.w
        P = w.P
        day = w.day
        k = len(dates)
        if not k:
            return np.empty(0, np.int64)
        a = np.array([d[0] for d in dates], np.int64)
        b = np.array([d[1] for d in dates], np.int64)
        vid = np.array([d[2] for d in dates], np.int64)
        act = sim.systems["activity"]
        lon, lat = act.v_lon[vid], act.v_lat[vid]
        wd = int(w.env["weekday"])
        pref = np.array([DATE_TIMES.get(m[0], (19 * 60, 150))[0] for m in meta], np.int32)
        dur = np.array([DATE_TIMES.get(m[0], (19 * 60, 150))[1] for m in meta], np.int32)
        if wd >= 5:     # weekends: some dates earlier in the day
            pref = np.where(np.isin([m[0] for m in meta], ["museum", "hike", "picnic", "pickleball"]), pref - 120, pref)
        both = np.r_[a, b]
        two = lambda x: np.r_[x, x]   # noqa: E731
        f = self._feasible(both, day, two(pref), two(dur), two(lon), two(lat), firm=True)
        # after both are free (a shift that ends at 8 pm: a 9 pm date) …
        ff = np.maximum(f["free_from"][:k], f["free_from"][k:])
        later = np.where(ff > pref - 15, _rup15(ff + 30), pref)
        fl = self._feasible(both, day, two(later), two(dur), two(lon), two(lat), firm=True)
        ok_l = ~(fl["conflict"][:k] | fl["conflict"][k:]) & (later <= 21 * 60 + 30)
        # … or before one of them has to be somewhere (a shift at 6: an afternoon date)
        lv = np.minimum(f["leave"][:k], f["leave"][k:])
        early = (lv - dur - 15) // 15 * 15
        early = np.where(early >= np.maximum(12 * 60 if wd >= 5 else 15 * 60, ff + 30), early, pref)
        start = np.where(ok_l, later, early).astype(np.int32)
        f2 = self._feasible(both, day, two(start), two(dur), two(lon), two(lat), firm=True)
        ill = P["ill"][both]
        # a date needs the whole stretch: nobody leaves early for a class or a shift, nobody comes very late
        blocked = (f2["conflict"] | f2["cant"] | ill | (two(start) > 21 * 60 + 30) | (f2["leave"] < two(start + dur) - 15)
                   | (f2["late"] > 20))
        bad = blocked[:k] | blocked[k:]
        sick = ill[:k] | ill[k:]
        # why a date can't happen today: 1 someone is sick (booked, then cancelled, with the reason), 2 their days don't
        # line up — nothing is booked and romance moves it to the next day, as people would rearrange it
        self.date_blocked = np.where(bad, np.where(sick, 1, 2), 0)
        book_it = ~bad | sick
        out = np.full(k, -1, np.int64)
        if not book_it.any():
            return out
        cause = np.array([m[2] for m in meta], np.int64)
        j = np.where(book_it)[0]
        oid = self.book.plan("date", day, start[j], dur[j], organizer=a[j], org_kind="none", ctx=CTX_ID["date"], place=vid[j],
                             lon=lon[j], lat=lat[j], origin="engine", cause=cause[j], created_day=day)
        inv = self.book.invite(oid, b[j], inviter=a[j], channel="in_person", day=day)
        self.book.inv.cols["seen_day"][self.book.inv.pos(inv)] = day
        self.book.respond(inv, "yes", day)
        s_j = sick[j]
        if s_j.any():
            who = np.r_[j[s_j], j[s_j] + k]
            occw = np.r_[oid[s_j], oid[s_j]]
            sk = ill[who]
            sim.decisions.record("show_up", day, both[who][sk], "did_not_come", {}, occasion=occw[sk], other=np.r_[b, a][who][sk],
                                 constraints={"ill": np.ones(int(sk.sum()), bool)})
            self.book.mark(oid[s_j], "cancelled")
        out[j] = np.where(s_j, -1, oid)
        return out

    def date_happened(self, oid: np.ndarray) -> np.ndarray:
        """Both came (dates that took place today)."""
        oid = np.asarray(oid, np.int64)
        ok = oid >= 0
        out = np.zeros(len(oid), bool)
        if ok.any():
            out[ok] = self.book.occ.get("n_came", oid[ok], default=0) >= 2
        return out

    def dancers(self) -> np.ndarray:
        """People at a dance-type occasion in the late block (for romance's NCMO step)."""
        act = self.sim.systems["activity"]
        m = act.ctype == OCC
        out = np.zeros(len(act.ctype), bool)
        if m.any():
            k = self.kind_of(act.cid[m])
            out[np.where(m)[0]] = (k == self.book.kind_id["dance"])
        return out

    # ------------------------------------------------------------------ end of day
    def end_of_day(self):
        """What happened: hosts' satisfactions and burdens, traditions started and kept, unanswered texts."""
        sim, w = self.sim, self.sim.w
        P, p = w.P, sim.p
        book = self.book
        day = w.day
        if self._day != day:
            self._reset_day(day)
        O, I = book.occ, book.inv
        if not O.n:
            return
        m = (O["day"] == day) & (O["status"] == STATUS_ID["planned"])
        ids = O["id"][m]
        if len(ids):
            came = O["n_came"][m]
            org = O["organizer"][m].astype(np.int64)
            org_came = np.zeros(len(ids), bool)
            if I.n:
                att = I["attended"] & np.isin(I["occ"], ids)
                ao, ap = I["occ"][att], I["person"][att]
                key = (ao.astype(np.int64) << 24) ^ ap.astype(np.int64)
                org_came = np.isin((ids << 24) ^ np.maximum(org, 0), key)
            happened = np.where(org >= 0, org_came & (came >= 2), came >= 1)
            book.mark(ids[happened], "happened")
            book.mark(ids[~happened], "cancelled")
            self._hosts(ids[happened & (org >= 0)])
            self._open_memory(ids[happened & O["open"][m]])
        # unanswered invitations to today's occasions
        if I.n:
            pend = (I["response"] == RESPONSE_ID["pending"])
            if pend.any():
                od = O.get("day", I["occ"][pend], default=-1)
                late = od <= day
                if late.any():
                    I.cols["response"][np.where(pend)[0][late]] = RESPONSE_ID["no_reply"]
        for key in [k for k in self.rides if self.book.occ.get("day", [k[0]], default=-1)[0] <= day]:
            self.rides.pop(key, None)

    def _hosts(self, ids: np.ndarray):
        """Hosted occasions that happened: the host's event, the culture's memory, the burden, low turnout, traditions."""
        sim, w = self.sim, self.sim.w
        P, p = w.P, sim.p
        book = self.book
        day = w.day
        if not len(ids):
            return
        oc = self._occ_cols(ids)
        kind = oc["kind"]
        home = np.array([self.k_where[c] == "home" for c in kind])
        hosted = home | np.isin(kind, self.hosted_codes)
        ids, oc, kind, home = ids[hosted], {c: v[hosted] for c, v in oc.items()}, kind[hosted], home[hosted]
        if not len(ids):
            return
        org = oc["organizer"].astype(np.int64)
        pos = book.occ.pos(ids)
        guests = np.maximum(book.occ.cols["n_came"][pos] - 1, 0).astype(np.float64)
        invited = book.occ.cols["n_invited"][pos].astype(np.float64)
        did = book.occ.cols["decision"][pos]
        hev = sim.emit("hosted_gathering", org, value=guests, block=clock.EVENING[0], decision=np.where(did >= 0, did, -1),
                       causes=[("occasion", ids, 1.0)])
        unit = P["unit_id"][org]
        hu = home & (unit >= 0)
        if hu.any():
            sim.systems["culture"].observe_gathering(unit[hu], guests[hu])
        # what hosting cost: guests, a shift the same day, exams, food money, tiredness
        wd = int(w.env["weekday"])
        worked = (P.internal["shift_start"][org, wd] >= 0) & P["employed"][org]
        exams = np.where(P["school"][org] == 1, bool(w.env.get("exam_week_BYU")), bool(w.env.get("exam_week_UVU"))) & P["enrolled"][org]
        food = self.k_cost[kind] > 0
        money = P["financial_stress"][org] * food
        # running late on a school night (Sunday to Thursday) costs sleep before an early class or shift
        end = (oc["start"] + oc["dur"]).astype(np.float64)
        late_night = np.maximum(end - 22 * 60, 0) / 60.0 * (wd in (6, 0, 1, 2, 3))
        burden = (guests / 6.0 + p("occasions.burden.shift") * worked + p("occasions.burden.exams") * exams
                  + p("occasions.burden.money") * money + P["fatigue"][org] + p("occasions.burden.late") * late_night)
        spend = (self.k_cost[kind] * guests).astype(np.float32)
        if (spend > 0).any():
            P.cols["savings"][org] = np.maximum(P["savings"][org] - spend, 0)
        strain = burden > p("occasions.burden.threshold")
        if strain.any():
            sim.emit("hosting_strain", org[strain], value=burden[strain], cause=hev[strain], block=clock.EVENING[-1],
                     causes=[("occasion", ids[strain], 1.0)], mech="occasions.burden")
        flop = (invited >= 3) & (guests <= 1)
        if flop.any():
            sim.emit("low_turnout", org[flop], value=guests[flop], cause=hev[flop], block=clock.EVENING[-1],
                     causes=[("occasion", ids[flop], 1.0)], mech="occasions.burden")
        self._last_burden = dict(zip(ids.tolist(), burden.tolist()))
        # traditions: keep a series going (or not); turn a good one-off into a weekly thing (or not)
        ser = oc["series"]
        if (ser >= 0).any():
            self._keep_series(ids[ser >= 0], org[ser >= 0], ser[ser >= 0], guests[ser >= 0], burden[ser >= 0], money[ser >= 0], hev[ser >= 0])
        one = (ser < 0) & np.isin(kind, [book.kind_id[k] for k in TRADITION_KINDS]) & (guests >= 3)
        if one.any():
            self._maybe_start(ids[one], org[one], kind[one], oc, one, guests[one], invited[one], burden[one], hev[one])

    def _maybe_start(self, ids, org, kind, oc, sel, guests, invited, burden, hev):
        sim, w = self.sim, self.sim.w
        P, p = w.P, sim.p
        day = w.day
        F = {"turnout": 0.8 * np.log(guests / 3.0), "enjoyed": 0.5 * (P["mood"][org] - 0.5) * 2,
             "outgoing": 0.3 * sim.z("extraversion")[org], "organized": 0.3 * sim.z("conscientiousness")[org],
             "burden": -0.5 * burden}
        base = np.full(len(org), p("occasions.tradition.start_base"))
        pr = expit(base + sum(F.values()))
        go = sim.u("occ_tradition")[org] < pr
        if not go.any():
            return
        did = sim.decisions.record("start_tradition", day, org[go], "started", {k_: v[go] for k_, v in F.items()}, base=base[go],
                                   prob=pr[go], occasion=ids[go])
        wd = int(w.env["weekday"])
        st, du = oc["start"][sel][go], oc["dur"][sel][go]
        unit = P["unit_id"][org[go]]
        sid = self.book.add_series(self.k_names[kind[go]], wd, st, du, first_day=day + 7, organizer=org[go], org_kind="household",
                                   org_id=unit, ctx=OCC, place=oc["place"][sel][go], lon=oc["lon"][sel][go], lat=oc["lat"][sel][go],
                                   origin="engine", cause=hev[go], created_day=day)
        for s, o in zip(sid.tolist(), ids[go].tolist()):
            self.series_members[s] = [self.book.attendees(o)]
        sim.emit("tradition_started", org[go], cause=hev[go], decision=did, causes=[("occasion", ids[go], 1.0)],
                 mech="occasions.tradition")

    def _keep_series(self, ids, org, ser, guests, burden, money, hev):
        sim, w = self.sim, self.sim.w
        P, p = w.P, sim.p
        day = w.day
        S = self.book.series
        regulars = np.array([len(np.unique(np.concatenate(self.series_members.get(int(s), [np.empty(0, np.int64)])[-3:])))
                             if self.series_members.get(int(s)) else 0 for s in ser], np.float64)
        weeks = (day - S.get("first_day", ser, default=day)) / 7.0
        for s, o in zip(ser.tolist(), ids.tolist()):
            self.series_members.setdefault(s, []).append(self.book.attendees(o))
            self.series_members[s] = self.series_members[s][-4:]
        F = {"turnout": 1.5 * np.log((guests + 0.5) / (np.maximum(regulars - 1, 0) + 0.5)), "burden": -0.6 * burden,
             "habit": 0.15 * np.minimum(weeks, 20), "outgoing": 0.2 * sim.z("extraversion")[org],
             "stress": -1.0 * (P["stress"][org] - 0.4), "money": -0.8 * money}
        base = np.full(len(org), p("occasions.tradition.continue_base"))
        pr = expit(base + sum(F.values()))
        keep = sim.u("occ_series_keep")[org] < pr
        did = sim.decisions.record("continue_tradition", day, org, np.where(keep, "continued", "ended").tolist(), F, base=base,
                                   prob=np.where(keep, pr, 1 - pr), occasion=ids)
        end = ~keep
        if end.any():
            S.set("active", ser[end], False)
            S.set("last_day", ser[end], day)
            sim.emit("tradition_ended", org[end], cause=hev[end], decision=did[end], causes=[("occasion", ids[end], 1.0)],
                     mech="occasions.tradition")

    def _open_memory(self, ids: np.ndarray):
        """Who went to which open event (a habit: the same dance next week)."""
        P = self.sim.w.P
        I = self.book.inv
        if not len(ids) or not I.n:
            return
        m = I["attended"] & np.isin(I["occ"], ids)
        if m.any():
            P.internal["occ_last_kind"][I["person"][m]] = self.kind_of(I["occ"][m])
            P.internal["occ_last_day"][I["person"][m]] = self.sim.w.day

    # ------------------------------------------------------------------ weekly series
    def _series(self, day: int, wd: int):
        """Today's instance of each weekly series: the host (or a successor) invites the regulars."""
        sim, w = self.sim, self.sim.w
        P = w.P
        book = self.book
        sids = book.due_series(day, wd)
        if not len(sids):
            return
        S = book.series
        pos = S.pos(sids)
        org = S.cols["organizer"][pos].astype(np.int64)
        home_unit = S.cols["org_id"][pos].astype(np.int64)
        moved = ~P["present"][org] | ((home_unit >= 0) & (P["unit_id"][org] != home_unit))
        for j in np.where(moved)[0]:         # bounded: series whose host moved out this week
            new = self._succession(int(sids[j]), int(org[j]), int(home_unit[j]))
            org[j] = new
        live = org >= 0
        if not live.any():
            return
        sids, org = sids[live], org[live]
        oid = book.instantiate(sids, day)
        book.occ.set("organizer", oid, org)
        book.occ.set("decision", oid, -1)
        # regulars: everyone who came in the last three weeks (and the founders), minus the host
        occ_l, per_l, inv_l = [], [], []
        for o, s, h in zip(oid.tolist(), sids.tolist(), org.tolist()):
            mem = self.series_members.get(s, [])
            reg = np.unique(np.concatenate(mem[-3:])) if mem else np.empty(0, np.int64)
            reg = reg[(reg != h) & P["present"][reg]]
            occ_l.append(np.full(len(reg), o))
            per_l.append(reg)
            inv_l.append(np.full(len(reg), h))
        if occ_l:
            members = {"occ": np.concatenate(occ_l).astype(np.int64), "person": np.concatenate(per_l).astype(np.int64),
                       "inviter": np.concatenate(inv_l).astype(np.int64)}
            kinds = book.occ.get("kind", oid)
            self._invite(oid, org, kinds, day, members=members, channel_default="group_chat")

    def _succession(self, sid: int, old: int, unit: int) -> int:
        """The host moved out: a regular still living there may take it over; otherwise it ends."""
        sim, w = self.sim, self.sim.w
        P, p = w.P, sim.p
        day = w.day
        S = self.book.series
        mem = self.series_members.get(sid, [])
        reg = np.concatenate(mem) if mem else np.empty(0, np.int64)
        cand, counts = np.unique(reg, return_counts=True) if len(reg) else (np.empty(0, np.int64), np.empty(0))
        here = (cand != old) & P["present"][cand] & (P["unit_id"][cand] == unit) if len(cand) else np.zeros(0, bool)
        cand, counts = cand[here], counts[here]
        new = -1
        if len(cand):
            F = {"outgoing": 0.5 * sim.z("extraversion")[cand], "regular": 0.8 * counts / max(len(mem), 1),
                 "close_host": 1.0 * sim.systems["encounters"]._closeness(cand, np.full(len(cand), old))}
            base = np.full(len(cand), p("occasions.tradition.takeover_base"))
            pr = expit(base + sum(F.values()))
            yes = sim.u("occ_takeover")[cand] < pr
            did = sim.decisions.record("take_over_tradition", day, cand, np.where(yes, "took_over", "declined").tolist(), F,
                                       base=base, prob=np.where(yes, pr, 1 - pr), other=np.full(len(cand), old))
            if yes.any():
                j = int(np.argmax(np.where(yes, pr, -1)))
                new = int(cand[j])
                S.set("organizer", [sid], new)
                sim.emit("tradition_passed_on", [new], b=[old], decision=did[j:j + 1], causes=[("person", [old], 1.0)],
                         mech="occasions.tradition")
                return new
        did = sim.decisions.record("continue_tradition", day, [old], "ended", {}, constraints={"host_left": [True]})
        S.set("active", [sid], False)
        S.set("last_day", [sid], day)
        if P["present"][old]:
            sim.emit("tradition_ended", [old], decision=did, causes=[("person", [old], 1.0)], mech="occasions.tradition")
        return new

    # ------------------------------------------------------------------ helpers for the UI and actions
    def can_make(self, people, occ: int, ride=None) -> dict:
        """(feasible, minutes late, travel minutes, mode, reason) for each person and one planned occasion."""
        people = np.atleast_1d(np.asarray(people, np.int64))
        oc = self._occ_cols(np.array([occ], np.int64))
        return self.check_window(people, int(oc["day"][0]), int(oc["start"][0]), int(oc["dur"][0]), float(oc["lon"][0]),
                                 float(oc["lat"][0]), occ=int(occ), ride=ride)

    def check_window(self, people, day: int, start: int, dur: int, lon: float, lat: float, occ: int = -1, ride=None,
                     host: bool = False) -> dict:
        from ...geo.travel import MODES
        people = np.atleast_1d(np.asarray(people, np.int64))
        f = self._feasible(people, day, start, dur, lon, lat, occ=np.full(len(people), occ), ride=ride, host=host)
        P = self.sim.w.P
        ill = P["ill"][people] & (day == self.sim.w.day)
        reasons = [self._why(f, j, bool(ill[j])) for j in range(len(people))]
        return {"feasible": (f["ok"] & ~ill).tolist(), "late": f["late"].tolist(), "travel": np.round(f["travel"]).astype(int).tolist(),
                "mode": [MODES[m] if m >= 0 else None for m in f["mode"].tolist()], "arrive": f["arrive"].tolist(),
                "leave": f["leave"].tolist(), "reason": reasons}

    _BLOCKER = {0: "works", 1: "is in class", 2: "is going to something else", 3: "is hosting something", 4: "has a date"}

    def _why(self, f: dict, j: int, ill: bool = False) -> str:
        from ...geo.travel import MODES
        if ill:
            return "sick that day"
        bk, be = int(f["blocker"][j]), int(f["blocker_end"][j])
        mode = MODES[int(f["mode"][j])] if f["mode"][j] >= 0 else None
        trip = f"a {int(round(f['travel'][j]))}-minute trip" + (f" by {mode}" if mode else "")
        if f["conflict"][j]:
            return f"{self._BLOCKER.get(bk, 'is busy')} until {clock.hhmm(be)}" if bk >= 0 and be >= 0 else "busy the whole time"
        if f["cant"][j]:
            return f"no way to get there in time ({trip})"
        if f["late"][j] > 10:
            what = self._BLOCKER.get(bk, "is busy") if bk >= 0 else "the trip"
            return f"would be {int(f['late'][j])} minutes late ({what} until {clock.hhmm(be)}, then {trip})" if bk >= 0 else \
                f"would be {int(f['late'][j])} minutes late ({trip})"
        return f"free ({trip})" if f["travel"][j] > 0 else "free"

    def free_window(self, i: int, day: int) -> list[dict]:
        """Free stretches of a person's day between 8 am and 11:30 pm (firm commitments only)."""
        r, cs, ce, _, _, ck = self._commitments(np.array([int(i)]), np.array([int(day)]), None, False)
        iv = sorted(zip(cs.tolist(), ce.tolist()))
        out, t = [], clock.DAY_START
        for s, e in iv:
            if s > t:
                out.append({"start": t, "end": int(s), "label": f"{clock.hhmm(t)}–{clock.hhmm(s)}"})
            t = max(t, int(e))
        if t < clock.DAY_END:
            out.append({"start": t, "end": clock.DAY_END, "label": f"{clock.hhmm(t)}–{clock.hhmm(clock.DAY_END)}"})
        return out

    def committed_at(self, i: int, b: int) -> str | None:
        """What a person is committed to in block b today, in words (None when free)."""
        w = self.sim.w
        day = w.day
        t0, t1 = int(clock.START[b]), int(clock.END[b])
        for c in self.agenda(i, day)["commitments"]:
            if c["firm"] and c["start"] < t1 and c["end"] > t0 and min(c["end"], t1) - max(c["start"], t0) >= 0.5 * (t1 - t0):
                return f"{c['what']} ({clock.hhmm(c['start'])}–{clock.hhmm(c['end'])})"
        return None

    def agenda(self, i: int, day: int | None = None) -> dict:
        """A person's day: the four blocks, commitments with times, occasions (invited or organizing), free time."""
        sim, w = self.sim, self.sim.w
        P = w.P
        from ...analysis.person import synthetic_name
        from ...geo.travel import MODES
        i = int(i)
        day = w.day if day is None else int(day)
        wd = sim.cal.weekday(day)
        com = []
        s, e = int(P.internal["shift_start"][i, wd]), int(P.internal["shift_end"][i, wd])
        if s >= 0 and P["employed"][i]:
            emp = int(P["employer_id"][i])
            name = w.employers["name"][emp] if emp >= 0 else "work"
            com.append({"kind": "shift", "what": f"work at {name}", "start": s, "end": e, "firm": True})
        acad = sim.systems["academics"]
        if P["enrolled"][i] and wd < 5 and len(acad.sec_days) and acad.stu_secs.shape[0] > i:
            sch = "BYU" if P["school"][i] == 1 else "UVU"
            if sim.cal.term(sch, day) and not sim.cal.holiday(day):
                for sec in acad.stu_secs[i]:
                    if sec >= 0 and (acad.sec_days[sec] >> wd) & 1:
                        cs_, ce_ = sim.systems["activity"].class_times([sec])
                        com.append({"kind": "class", "what": f"class at {sch}", "start": int(cs_[0]), "end": int(ce_[0]),
                                    "firm": True, "section": int(sec)})
        G = w.groups
        for col, kind in (("club_id", "club"), ("team_id", "team"), ("institute_class", "institute")):
            g = int(P[col][i])
            if g >= 0 and int(G["weekday"][g]) == wd:
                st = int(G["start"][g])
                com.append({"kind": kind, "what": G["name"][g], "start": st, "end": st + int(G["dur"][g]), "firm": False})
        if wd == 0 and P.internal["fhe_group"][i] >= 0:
            com.append({"kind": "fhe", "what": "family home evening", "start": 19 * 60, "end": 20 * 60 + 30, "firm": False})
        if wd == 6 and P["lds_member"][i] and P.internal["attend_prob"][i] >= 0.5:
            com.append({"kind": "church", "what": "church", "start": 9 * 60, "end": 12 * 60, "firm": False})
        occs = []
        book = self.book
        I, O = book.inv, book.occ
        seen_o = set()
        rows = []
        if I.n:
            m = I["person"] == i
            if m.any():
                od = O.get("day", I["occ"][m], default=-1)
                for inv_id in I["id"][m][od == day].tolist():
                    rows.append(book.inv.row(inv_id))
        if O.n:
            for oid in O["id"][(O["organizer"] == i) & (O["day"] == day)].tolist():
                if not any(r["occ"] == oid for r in rows):
                    rows.append({"occ": oid, "organizer": True})
        for r in rows:
            oid = int(r["occ"])
            if oid in seen_o:
                continue
            seen_o.add(oid)
            d = book.describe(oid)
            if not d:
                continue
            org = int(d["organizer"])
            role = "organizer" if org == i else ("walked in" if r.get("walk_in") else "invited")
            trip = None
            tp = np.where(self.trips["inv"] == r["id"])[0] if self.trips.n and "id" in r else np.empty(0, np.int64)
            if len(tp):
                q = int(tp[-1])
                md = int(self.trips.cols["mode"][q])
                trip = {"minutes": int(self.trips.cols["minutes"][q]), "mode": MODES[md] if md >= 0 else None}
            going = role == "organizer" or r.get("response") == RESPONSE_ID["yes"]
            occs.append({"id": oid, "kind": d["kind"], "kind_label": d["kind_label"], "name": d["name"], "start": d["start"],
                         "end": d["start"] + d["dur"], "time": f"{clock.hhmm(d['start'])}–{clock.hhmm(d['start'] + d['dur'])}",
                         "status": d["status"], "organizer": org, "organizer_name": synthetic_name(P, org) if org >= 0 else None,
                         "role": role, "response": ("yes" if role == "organizer" else
                                                    ["pending", "yes", "no", "no_reply", "maybe"][int(r.get("response", 0))]),
                         "seen_day": r.get("seen_day"), "attended": bool(r.get("attended")), "arrive": r.get("arrive"),
                         "channel": ["in_person", "text", "group_chat", "announcement", "family", "app"][int(r.get("channel", 0))]
                         if "channel" in r else None, "trip": trip, "place": self.place_label(oid)})
            if going and d["status"] != "cancelled":
                com.append({"kind": "occasion", "what": f"{d['kind_label'].lower()}" + (" (hosting)" if role == "organizer" else ""),
                            "start": d["start"], "end": d["start"] + d["dur"], "firm": True, "occasion": oid})
        com.sort(key=lambda c: c["start"])
        for c in com:
            c["time"] = f"{clock.hhmm(c['start'])}–{clock.hhmm(c['end'])}"
        blocks = [{"block": b, "label": clock.BLOCK_LABELS[b], "start": int(clock.START[b]), "end": int(clock.END[b])}
                  for b in range(clock.N_BLOCKS)]
        act = sim.systems["activity"]
        frames = getattr(act, "frames_today", {}) if day == w.day else (
            getattr(act, "day_frames", {}) if getattr(act, "day_frames", {}).get("day") == day else {})
        cats = P.specs["activity_now"].categories
        for bl in blocks:
            fr = frames.get(bl["block"]) if frames else None
            if fr is not None and i < len(fr[2]):
                bl["doing"] = cats[int(fr[2][i])]
        return {"person": i, "name": synthetic_name(P, i), "day": day, "date": str(sim.cal.date(day)),
                "weekday": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"][wd],
                "blocks": blocks, "commitments": com, "occasions": sorted(occs, key=lambda o: o["start"]),
                "free": self.free_window(i, day)}

    def place_label(self, oid: int) -> str:
        """Where an occasion is, in words."""
        sim, w = self.sim, self.sim.w
        d = self.book.describe(int(oid))
        if not d:
            return ""
        c = self.book.kind_id[d["kind"]]
        if self.k_where[c] == "home" and d["place"] >= 0:
            u = int(d["place"])
            cx = int(w.units.complex_id[u]) if u < len(w.units) else -1
            org = d["organizer"]
            from ...analysis.person import synthetic_name
            whose = f"{synthetic_name(w.P, org).split()[0]}'s place" if org >= 0 else "an apartment"
            return f"{whose} ({w.complexes['name'][cx]})" if cx >= 0 else whose
        if c == self.date_code or self.k_where[c] == "venue":
            act = sim.systems["activity"]
            pl = int(d["place"])
            if 0 <= pl < len(act.v_name):
                return act.v_name[pl]
        if self.k_where[c] == "campus":
            return "on campus"
        return self.k_where[c]

    def thin(self):
        """Keep the trip table in step with the invitation ledger (rows of thinned invitations go)."""
        if self.trips.n:
            self.trips.keep(self.book.inv.pos(self.trips["inv"]) >= 0)
        day = self.sim.w.day
        for s in list(self.series_members):
            act = self.book.series.get("active", [s], default=False)[0]
            if not act and self.book.series.get("last_day", [s], default=day)[0] < day - 120:
                self.series_members.pop(s, None)

    # ------------------------------------------------------------------ social actions (engine/interventions.py)
    def apply_action(self, k: int, it: dict) -> dict:
        from .social_actions import apply_action
        return apply_action(self, k, it)


def _normalize_filter(f):
    """Audience filters may use symbols (==, >=) and lists (an AND); the query DSL wants eq/ge and {"and": [...]}."""
    if f is None:
        return None
    if isinstance(f, list):
        return {"and": [_normalize_filter(x) for x in f]} if f else None
    if not isinstance(f, dict):
        return f
    sym = {"==": "eq", "=": "eq", "!=": "ne", "<": "lt", "<=": "le", ">": "gt", ">=": "ge"}
    out = {}
    for k, v in f.items():
        if k in ("and", "or"):
            out[k] = [_normalize_filter(x) for x in v]
        elif k == "not":
            out[k] = _normalize_filter(v)
        elif k == "op":
            out[k] = sym.get(v, v)
        else:
            out[k] = v
    return out
