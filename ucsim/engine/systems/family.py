"""Family and home states: where people are from, their family back home (as light kin records), and trips home.

Design notes (parameters in config/mechanisms/17_family.yaml)
* Home: a state (and a metro point) consistent with origin_region, drawn from the ProvoStats origin-state table within
  the region; Utah homes are Utah County for people whose family is local, else Salt Lake, Davis/Weber, Cache or
  Washington County. Drive time home from the distance (beyond ~12 hours people fly).
* Kin (off-map): two parents (together or divorced per family_structure), siblings (more in Latter-day Saint
  families), living grandparents, each with an age, closeness and their own life events: siblings marry, serve
  missions and have babies; parents fall ill; grandparents die (this replaces lifecourse's random death in the
  family). Those events pull people home.
* Trips (decision `trip_home`): weekends home for people within a few hours' drive; Thanksgiving and Christmas (the
  calendar's travel days) for most; trips for a sibling's wedding, a mission farewell or homecoming, a parent's illness
  or a funeral. Factors: closeness, distance and cost, homesickness, obligations (a shift, exams), married couples
  alternate families. While away a person isn't in Provo (present is off; `trip_away` marks them as away, not gone);
  back home they get family time; coming back some feel homesick. People who stay for Thanksgiving host or join a
  Friendsgiving. Families also visit Provo (game days, graduation).
* Trip ledger: person, depart, return, destination state, reason, mode, decision.
"""
from __future__ import annotations

import numpy as np
from scipy.special import expit

from ..ledger import Table
from ..provenance import link

PROVO = (40.2338, -111.6585)
# approximate population centers (lat, lon) of each state; Utah's metros are listed separately
STATE_LL = {
    "Alabama": (33.0, -86.8), "Alaska": (61.2, -149.9), "Arizona": (33.4, -112.0), "Arkansas": (34.8, -92.3),
    "California": (35.5, -119.4), "Colorado": (39.7, -105.0), "Connecticut": (41.6, -72.7), "Delaware": (39.4, -75.6),
    "District of Columbia": (38.9, -77.0), "Florida": (27.8, -81.6), "Georgia": (33.6, -84.2), "Hawaii": (21.3, -157.9),
    "Idaho": (43.6, -116.0), "Illinois": (41.3, -88.4), "Indiana": (39.8, -86.3), "Iowa": (41.9, -93.4),
    "Kansas": (38.5, -96.8), "Kentucky": (37.8, -85.6), "Louisiana": (30.7, -91.4), "Maine": (44.3, -69.8),
    "Maryland": (39.1, -76.8), "Massachusetts": (42.3, -71.4), "Michigan": (42.9, -84.2), "Minnesota": (45.2, -93.6),
    "Mississippi": (32.6, -89.7), "Missouri": (38.4, -92.2), "Montana": (46.6, -111.0), "Nebraska": (41.3, -97.4),
    "Nevada": (36.4, -115.4), "New Hampshire": (43.0, -71.5), "New Jersey": (40.4, -74.4), "New Mexico": (34.6, -106.3),
    "New York": (41.5, -74.6), "North Carolina": (35.6, -79.6), "North Dakota": (47.4, -99.0), "Ohio": (40.5, -82.7),
    "Oklahoma": (35.6, -96.8), "Oregon": (44.7, -122.6), "Pennsylvania": (40.5, -77.3), "Rhode Island": (41.8, -71.4),
    "South Carolina": (34.0, -81.0), "South Dakota": (44.0, -98.6), "Tennessee": (35.8, -86.4), "Texas": (30.9, -97.4),
    "Utah": (40.76, -111.89), "Vermont": (44.1, -72.8), "Virginia": (38.0, -77.8), "Washington": (47.3, -121.6),
    "West Virginia": (38.8, -80.8), "Wisconsin": (43.7, -89.0), "Wyoming": (42.6, -106.9),
}
STATES = sorted(STATE_LL) + ["International"]
REGIONS = {"Mountain West": ["Idaho", "Arizona", "Nevada", "Colorado", "Wyoming", "Montana", "New Mexico"],
           "West Coast": ["California", "Oregon", "Washington", "Alaska", "Hawaii"]}
UTAH_METROS = [("Utah County", 40.30, -111.70, 0.0), ("Salt Lake County", 40.67, -111.92, 0.45),
               ("Davis and Weber counties", 41.10, -111.95, 0.25), ("Cache County", 41.73, -111.83, 0.1),
               ("Washington County", 37.10, -113.58, 0.12), ("Elsewhere in Utah", 39.5, -111.6, 0.08)]
REL = ("mother", "father", "sibling", "grandparent")
REASONS = ("weekend", "thanksgiving", "christmas", "wedding", "mission", "illness", "funeral", "baby")
REASON_ID = {k: i for i, k in enumerate(REASONS)}


def _km(lat1, lon1, lat2, lon2):
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dl = np.radians(np.asarray(lon2) - np.asarray(lon1))
    a = np.sin((p2 - p1) / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2
    return 6371 * 2 * np.arcsin(np.sqrt(np.clip(a, 0, 1)))


class Family:
    def __init__(self, sim):
        self.sim = sim
        self.kin = Table({"person": (np.int32, -1), "rel": (np.int8, -1), "age": (np.float32, 0), "alive": (np.bool_, True),
                          "married": (np.bool_, False), "lds": (np.bool_, False), "closeness": (np.float32, 0.5),
                          "away_until": (np.int32, -1), "ill_until": (np.int32, -1)}, capacity=1 << 12)
        self.trips = Table({"person": (np.int32, -1), "depart": (np.int32, -1), "ret": (np.int32, -1), "state": (np.int16, -1),
                            "reason": (np.int8, -1), "fly": (np.bool_, False), "decision": (np.int64, -1),
                            "event": (np.int64, -1), "with_partner": (np.int32, -1)}, capacity=1 << 12)
        self._done = 0

    # ------------------------------------------------------------------ setup
    def init(self):
        sim, w = self.sim, self.sim.w
        P = w.P
        for c, dt, f in (("trip_away", np.bool_, False), ("trip_return", np.int32, -1), ("home_lat", np.float32, np.nan),
                         ("home_lon", np.float32, np.nan), ("family_turn", np.int8, 0), ("kin_pull", np.int64, -1),
                         ("kin_pull_day", np.int32, -1)):
            P.add_internal(c, dt, f)
        self.arrive(np.flatnonzero(P["present"][: P.n].astype(bool)))

    def arrive(self, ids: np.ndarray):
        """Home state, metro, distance, closeness and kin for new people (everyone at the start)."""
        sim, w = self.sim, self.sim.w
        P = w.P
        ids = np.asarray(ids, np.int64)
        ids = ids[P.cols["home_state"][ids] == 0] if self._done else ids
        if not len(ids):
            return
        rng = sim.streams.gen("family_home", w.day, int(ids[0]) % 9973)
        n = len(ids)
        from ...population.sampling import load_priors
        table = load_priors().get("tables", {}).get("origin_state", {})
        reg = np.asarray(P.labels("origin_region", P["origin_region"][ids]), dtype=object)
        state = np.full(n, "Utah", dtype=object)
        for region, pool in (("Mountain West", REGIONS["Mountain West"]), ("West Coast", REGIONS["West Coast"]),
                             ("Other US", [s for s in STATE_LL if s != "Utah" and s not in REGIONS["Mountain West"]
                                           and s not in REGIONS["West Coast"]])):
            m = reg == region
            if not m.any():
                continue
            wts = np.array([table.get(s, 0.0) for s in pool]) + 0.002
            state[m] = rng.choice(pool, int(m.sum()), p=wts / wts.sum())
        state[reg == "International"] = "International"
        lat = np.array([STATE_LL.get(s, (np.nan, np.nan))[0] for s in state])
        lon = np.array([STATE_LL.get(s, (np.nan, np.nan))[1] for s in state])
        ut = state == "Utah"
        local = P["family_local"][ids].astype(bool)
        if ut.any():
            wts = np.array([m[3] for m in UTAH_METROS])
            k = rng.choice(len(UTAH_METROS), n, p=wts / wts.sum())
            k = np.where(local, 0, k)
            lat = np.where(ut, [UTAH_METROS[j][1] for j in k], lat)
            lon = np.where(ut, [UTAH_METROS[j][2] for j in k], lon)
        km = _km(PROVO[0], PROVO[1], lat, lon) * 1.25 + 5         # road distance ≈ 1.25 × straight line
        hours = np.where(state == "International", 30.0, km / 95.0)
        P.cols["home_state"][ids] = P.codes("home_state", state)
        P.cols["home_drive_hours"][ids] = np.round(hours, 1).astype(np.float32)
        P.internal["home_lat"][ids] = lat
        P.internal["home_lon"][ids] = lon
        z = sim.z
        clos = np.clip(0.55 + 0.12 * z("agreeableness")[ids] + 0.15 * P["family_expectation"][ids]
                       - 0.12 * P["parents_divorced"][ids] + 0.08 * local + 0.1 * rng.standard_normal(n), 0.05, 1)
        P.cols["family_closeness"][ids] = clos.astype(np.float32)
        # kin: parents, siblings, living grandparents
        age = P["age"][ids].astype(float)
        lds = P["lds_member"][ids].astype(bool)
        sib = rng.poisson(np.where(lds, 3.2, 1.6))
        P.cols["n_siblings"][ids] = np.minimum(sib, 12).astype(np.uint8)
        pa = age + 26 + rng.normal(0, 3.5, n)
        gp = rng.binomial(4, np.clip(1.15 - (pa + 27) / 95, 0.05, 0.95))
        rows_p, rows_r, rows_a, rows_c, rows_m, rows_l = [], [], [], [], [], []
        for rel, cnt, a in (("mother", np.ones(n, int), pa - 1.5), ("father", np.ones(n, int), pa + 1.5),
                            ("grandparent", gp, pa + 27)):
            rows_p.append(np.repeat(ids, cnt))
            rows_r.append(np.full(int(cnt.sum()), REL.index(rel)))
            rows_a.append(np.repeat(a, cnt) + rng.normal(0, 2, int(cnt.sum())))
            rows_c.append(np.repeat(clos, cnt) * (0.75 if rel == "grandparent" else 1.0))
            rows_m.append(np.repeat(~P["parents_divorced"][ids].astype(bool), cnt) if rel != "grandparent" else np.ones(int(cnt.sum()), bool))
            rows_l.append(np.repeat(lds, cnt))
        si = np.repeat(np.arange(n), sib)
        sa = np.clip(age[si] + rng.normal(0, 5, len(si)), 0.5, pa[si] - 2 - 19)    # mothers have children from ~19
        rows_p.append(ids[si])
        rows_r.append(np.full(len(si), REL.index("sibling")))
        rows_a.append(np.clip(sa, 1, 60))
        rows_c.append(np.clip(clos[si] + 0.15 * rng.standard_normal(len(si)), 0.05, 1))
        rows_m.append(sa > 23 + 6 * rng.random(len(si)))
        rows_l.append(lds[si] & (rng.random(len(si)) < 0.85))
        cat = lambda xs: np.concatenate(xs)  # noqa: E731
        self.kin.append(len(cat(rows_p)), person=cat(rows_p), rel=cat(rows_r), age=cat(rows_a), closeness=cat(rows_c),
                        married=cat(rows_m), lds=cat(rows_l))
        self._done = 1

    # ------------------------------------------------------------------ daily
    def daily(self):
        sim, w = self.sim, self.sim.w
        day = w.day
        P = w.P
        self._returns(day)
        new = np.flatnonzero(P["present"][: P.n].astype(bool) & (P["home_state"][: P.n] == 0))
        if len(new):
            self.arrive(new)
        if sim.cal.weekday(day) == 6:
            self._kin_week(day)
        holiday = bool(w.env.get("travel_home_likely", False))
        prev = bool(getattr(self, "_holiday_prev", False))
        self._holiday_prev = holiday
        if holiday and not prev:
            self._holiday(day)
        if sim.cal.weekday(day) == 4 and not holiday:
            self._weekend(day)
        self._pulled(day)
        self._visits(day)
        if holiday and sim.cal.date(day).month == 11 and sim.cal.weekday(day) == 3:
            self._friendsgiving(day)

    # ------------------------------------------------------------------ trips
    def _obligations(self, ids: np.ndarray, d0: int, d1: int) -> np.ndarray:
        """Shifts on the days they'd be away, and exams coming up (0 none … 1 heavy)."""
        sim, w = self.sim, self.sim.w
        P = w.P
        shifts = np.zeros(len(ids))
        days = range(d0, min(d1, d0 + 6) + 1)            # a week tells: the share of days they'd have to miss work
        for d in days:
            wd = sim.cal.weekday(d)
            shifts += (P.internal["shift_start"][ids, wd] >= 0) & P["employed"][ids]
        shifts = 2.0 * shifts / len(days)
        exams = np.zeros(len(ids))
        if bool(w.env.get("exam_week", False)):
            exams = P["enrolled"][ids].astype(float)
        return np.clip(0.35 * shifts + 0.6 * exams, 0, 1.5)

    def _go(self, ids: np.ndarray, day: int, ret: np.ndarray, reason: str, T: dict, base: float, pr: np.ndarray, go: np.ndarray):
        """Record the decisions; send the ones going home (with a partner, for married couples)."""
        sim, w = self.sim, self.sim.w
        P = w.P
        if not len(ids):
            return
        for o in ("went", "stayed"):
            s = go if o == "went" else ~go
            if s.any():
                did = sim.decisions.record("trip_home", day, ids[s], o, {k: v[s] for k, v in T.items()}, base=base,
                                           prob=np.where(go[s], pr[s], 1 - pr[s]))
                if o == "went":
                    dids = did
        x = ids[go]
        if not len(x):
            return
        ret = np.asarray(ret)[go] if np.ndim(ret) else np.full(len(x), int(ret))
        partner = P["partner_id"][x].astype(np.int64)
        married = (partner >= 0) & P.is_("rel_status", "married")[x]
        fly = P["home_drive_hours"][x] > p_fly(sim)
        ev = sim.emit("went_home", x, value=float(REASON_ID[reason]), mech="family.trip", decision=dids)
        pull = P.internal["kin_pull_day"][x] >= day - 10
        link(sim, ev, "event", np.where(pull, P.internal["kin_pull"][x].astype(np.int64), -1), 1.0, "after")
        self.trips.append(len(x), person=x, depart=day, ret=ret, state=P["home_state"][x].astype(np.int16), reason=REASON_ID[reason],
                          fly=fly, decision=dids, event=ev, with_partner=np.where(married, partner, -1))
        travelers = np.unique(np.r_[x, partner[married & P["present"][np.maximum(partner, 0)].astype(bool)]])
        rmap = np.full(P.n, -1, np.int32)
        rmap[x] = ret
        rmap[partner[married]] = np.maximum(rmap[partner[married]], ret[married])
        P.internal["trip_return"][travelers] = rmap[travelers]
        P.internal["trip_away"][travelers] = True
        P.cols["present"][travelers] = False
        P.cols["trips_home"][x] += 1
        P.internal["family_turn"][x[married]] ^= 1
        P.internal["family_turn"][partner[married]] ^= 1

    def _returns(self, day: int):
        sim, w = self.sim, self.sim.w
        P = w.P
        back = np.flatnonzero(P.internal["trip_away"][: P.n] & (P.internal["trip_return"][: P.n] <= day))
        if not len(back):
            return
        P.internal["trip_away"][back] = False
        P.internal["trip_return"][back] = -1
        P.cols["present"][back] = True
        u = sim.streams.uniform("family_homesick", day, len(back))
        sad = u < 0.1 + 0.35 * P["family_closeness"][back] * (P["home_drive_hours"][back] > 3)
        if sad.any():
            who = back[sad]
            # the trip they came back from (event ids grow with time, so the largest is the latest)
            trip = np.full(P.n, -1, np.int64)
            np.maximum.at(trip, self.trips["person"].astype(np.int64), self.trips["event"].astype(np.int64))
            sim.emit("homesick", who, cause=trip[who], mech="family.trip")

    def _decide(self, ids: np.ndarray, day: int, nights: int, reason: str, extra: float | np.ndarray = 0.0):
        sim, w = self.sim, self.sim.w
        P, p = w.P, sim.p
        hrs = P["home_drive_hours"][ids].astype(float)
        fly = hrs > p_fly(sim)
        cost = np.where(fly, p("family.trip.flight_cost"), hrs * 2 * 95 * 0.12)       # dollars: a flight, or gas
        T = {"closeness": p("family.trip.closeness") * (P["family_closeness"][ids] - 0.5),
             "distance": -p("family.trip.distance") * np.log1p(hrs) * (nights <= 3),
             "cost": -p("family.trip.cost") * (cost / 300) * (0.5 + P["financial_stress"][ids]),
             "homesick": p("family.trip.homesick") * (P["loneliness"][ids] - 0.3),
             "obligations": -p("family.trip.obligations") * self._obligations(ids, day, day + nights),
             "occasion": np.broadcast_to(np.asarray(extra, float), ids.shape).copy()}
        married = P.is_("rel_status", "married")[ids] & (P["partner_id"][ids] >= 0)
        T["partner_family"] = -0.8 * (married & (P.internal["family_turn"][ids] == 1))       # their turn with the in-laws
        base = p(f"family.trip.base_{reason if reason in ('thanksgiving', 'christmas', 'weekend') else 'event'}")
        pr = expit(base + sum(T.values()))
        go = sim.streams.uniform(f"family_trip_{reason}", day, len(ids)) < pr
        go &= P["home_state"][ids] != P.code("home_state", "International") if reason == "weekend" else go
        self._go(ids, day, day + nights, reason, T, base, pr, go)

    def _eligible(self) -> np.ndarray:
        P = self.sim.w.P
        n = P.n
        return np.flatnonzero(P["present"][:n].astype(bool) & ~P.internal["trip_away"][:n] & ~P.internal["summer_away"][:n]
                              & (P["home_drive_hours"][:n] > 0.6) & (P["age"][:n] < 40))

    def _weekend(self, day: int):
        P, p = self.sim.w.P, self.sim.p
        ids = self._eligible()
        ids = ids[P["home_drive_hours"][ids] <= p("family.trip.weekend_hours")]
        if len(ids):
            self._decide(ids, day, 2, "weekend")

    def _holiday(self, day: int):
        sim, w = self.sim, self.sim.w
        ids = self._eligible()
        if not len(ids):
            return
        m = sim.cal.date(day).month
        reason = "thanksgiving" if m == 11 else "christmas"
        span = 1
        while span < 25 and any(it.effects.get("travel_home_likely") for it in sim.cal.items_on(day + span)):
            span += 1
        stu = w.P["enrolled"][ids]
        nights = np.where(stu, span, min(span, 5 if reason == "christmas" else 4))
        for nn in np.unique(nights):
            s = nights == nn
            self._decide(ids[s], day, int(nn), reason)

    def _pulled(self, day: int):
        """A family event pulls people home: a sibling's wedding or mission farewell, a sick parent, a funeral."""
        P = self.sim.w.P
        ids = self._eligible()
        ids = ids[P.internal["kin_pull_day"][ids] == day]
        if not len(ids):
            return
        reason_of = P.internal["kin_pull"][ids]           # holds the event id; its type says why
        log = self.sim.log
        names = self.sim.reg.event_names
        typ = np.array([names[int(log["type"][e])] for e in reason_of])
        R = {"sibling_wedding": ("wedding", 3, 1.5), "sibling_mission": ("mission", 2, 0.8), "parent_ill": ("illness", 7, 1.2),
             "death_in_family": ("funeral", 4, 2.0), "new_niece_nephew": ("baby", 2, 0.3)}
        for t, (reason, nights, boost) in R.items():
            s = typ == t
            if s.any():
                self._decide(ids[s], day, nights, reason, extra=boost)

    # ------------------------------------------------------------------ kin life events (weekly)
    def _kin_week(self, day: int):
        sim, w = self.sim, self.sim.w
        P, p = w.P, sim.p
        K = self.kin
        if not K.n:
            return
        K.cols["age"][: K.n] += 7 / 365.25
        alive = K["alive"] & P["present"][K["person"]].astype(bool) | (K["alive"] & P.internal["trip_away"][K["person"]])
        u = sim.streams.uniform("family_kin", day, K.n)
        rel, age = K["rel"], K["age"]
        sib = alive & (rel == REL.index("sibling"))
        par = alive & np.isin(rel, [REL.index("mother"), REL.index("father")])
        gpa = alive & (rel == REL.index("grandparent"))
        hz = {"sibling_wedding": sib & ~K["married"] & (age >= 19) & (age <= 30) & (u < p("family.kin.wedding") * np.where(K["lds"], 1.6, 0.6)),
              "sibling_mission": sib & K["lds"] & (age >= 18) & (age < 19) & (K["away_until"] < 0) & (u < p("family.kin.mission")),
              "new_niece_nephew": sib & K["married"] & (age >= 22) & (age <= 40) & (u < p("family.kin.baby")),
              "parent_ill": par & (age >= 45) & (K["ill_until"] < day) & (u < p("family.kin.illness") * np.exp((age - 55) / 12)),
              "death_in_family": gpa & (u < p("family.kin.death") * np.exp((age - 80) / 8))}
        for etype, m in hz.items():
            rows = np.flatnonzero(m)
            if not len(rows):
                continue
            who = K["person"][rows].astype(np.int64)
            if etype == "sibling_wedding":
                K.cols["married"][rows] = True
            elif etype == "sibling_mission":
                K.cols["away_until"][rows] = day + 730
            elif etype == "parent_ill":
                K.cols["ill_until"][rows] = day + 120
            elif etype == "death_in_family":
                K.cols["alive"][rows] = False
            ev = sim.emit(etype, who, mech="family.kin", value=K["closeness"][rows].astype(float))
            msg = sim.systems.get("messaging")
            if msg is not None:
                msg.family_news(who, ev)
            near = P["home_drive_hours"][who] <= np.where(np.isin(etype, ["parent_ill", "death_in_family", "sibling_wedding"]), 14, 6)
            close = K["closeness"][rows] > 0.4
            pull = near & close
            P.internal["kin_pull"][who[pull]] = ev[pull]
            P.internal["kin_pull_day"][who[pull]] = day + np.where(etype == "sibling_wedding", 6, 1)
        # missionaries coming home
        back = np.flatnonzero(K["away_until"] == day)
        if len(back):
            K.cols["away_until"][back] = -1
            sim.emit("sibling_mission", K["person"][back].astype(np.int64), mech="family.kin", value=-1.0)

    # ------------------------------------------------------------------ the people who stay, and visits
    def _friendsgiving(self, day: int):
        """Thanksgiving in Provo: people who stayed host friends who also stayed."""
        sim, w = self.sim, self.sim.w
        P, E = w.P, w.E
        occ = sim.systems.get("occasions")
        net = sim.systems["network"]
        if occ is None or not hasattr(net, "adj_close"):
            return
        indptr, nbr, _ = net.padded(net.adj_close)
        stay = P["present"][: P.n].astype(bool) & (P["age"][: P.n] < 35) & (P["unit_id"][: P.n] >= 0)
        cand = np.flatnonzero(stay)
        deg_stay = np.array([stay[nbr[indptr[i]:indptr[i + 1]]].sum() for i in cand]) if len(cand) else np.zeros(0)
        cand = cand[deg_stay >= 2]
        if not len(cand):
            return
        u = sim.streams.uniform("friendsgiving", day, len(cand))
        hosts = cand[u < sim.p("family.friendsgiving.host") * (1 + sim.z("extraversion")[cand].clip(-1, 2) * 0.3)]
        taken = np.zeros(P.n, bool)
        for h in hosts.tolist():
            if taken[h]:
                continue
            fr = nbr[indptr[h]:indptr[h + 1]]
            fr = fr[stay[fr] & ~taken[fr]][:8]
            if len(fr) < 2:
                continue
            unit = int(P["unit_id"][h])
            oid = sim.book.plan("friendsgiving", day, 15 * 60, 180, organizer=h, org_kind="household", org_id=unit,
                                lon=float(w.units.lon[unit]), lat=float(w.units.lat[unit]), origin="family")
            occ.send_invites(oid, fr, h, channel="text")
            taken[h] = True
            taken[fr] = True

    def _visits(self, day: int):
        """Parents come to Provo: on game days, for graduation, or just to visit."""
        sim, w = self.sim, self.sim.w
        P, p = w.P, sim.p
        n = P.n
        boost = 1.0
        for it in sim.cal.items_on(day):
            occ = (it.effects or {}).get("occasion") or {}
            if occ.get("kind") == "football_game" or "ommencement" in str(it.label) or "raduation" in str(it.label):
                boost = p("family.visit.event_boost")
        ids = np.flatnonzero(P["present"][:n].astype(bool) & (P["home_drive_hours"][:n] <= 8) & (P["home_drive_hours"][:n] > 0.6)
                             & (P["age"][:n] < 30))
        if not len(ids):
            return
        pr = p("family.visit.rate") * boost * (0.5 + P["family_closeness"][ids]) * (1 + (sim.cal.weekday(day) >= 4))
        hit = sim.streams.uniform("family_visit", day, len(ids)) < pr
        if hit.any():
            sim.emit("family_visited", ids[hit], mech="family.visit")

    # ------------------------------------------------------------------ reading
    def person(self, i: int) -> dict:
        sim, w = self.sim, self.sim.w
        P = w.P
        K = self.kin
        rows = np.flatnonzero(K["person"] == i)
        kin = [{"rel": REL[int(K["rel"][r])], "age": int(K["age"][r]), "alive": bool(K["alive"][r]), "married": bool(K["married"][r]),
                "closeness": round(float(K["closeness"][r]), 2),
                "on_mission": bool(K["away_until"][r] > w.day), "ill": bool(K["ill_until"][r] > w.day)} for r in rows]
        T = self.trips
        tr = np.flatnonzero(T["person"] == i)
        trips = [{"depart": int(T["depart"][r]), "return": int(T["ret"][r]), "reason": REASONS[int(T["reason"][r])],
                  "fly": bool(T["fly"][r]), "decision": int(T["decision"][r]), "event": int(T["event"][r]),
                  "with_partner": int(T["with_partner"][r]) if T["with_partner"][r] >= 0 else None} for r in tr[::-1][:40]]
        st = str(P.labels("home_state", P["home_state"][i:i + 1])[0])
        return {"person": i, "home_state": st, "drive_hours": float(P["home_drive_hours"][i]),
                "flies": bool(P["home_drive_hours"][i] > p_fly(sim)), "closeness": round(float(P["family_closeness"][i]), 2),
                "away": bool(P.internal["trip_away"][i]), "returns": int(P.internal["trip_return"][i]),
                "kin": kin, "trips": trips}

    def by_state(self) -> list[dict]:
        P = self.sim.w.P
        n = P.n
        st = P["home_state"][:n]
        here = P["present"][:n].astype(bool)
        away = P.internal["trip_away"][:n]
        cats = P.specs["home_state"].categories
        out = []
        for k in np.unique(st[here | away]).tolist():
            if k == 0:
                continue
            m = st == k
            out.append({"state": str(cats[k]), "from": int((m & (here | away)).sum()), "in_provo": int((m & here).sum()),
                        "at_home": int((m & away).sum())})
        return out


def p_fly(sim) -> float:
    return sim.p("family.trip.fly_hours")
