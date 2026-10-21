"""Housing market and residential mobility (UrbanSim-style location choice with sampled alternatives).

Lease turnover (end of April, mid-August) triggers moving decisions for renters.  Movers
choose among a random sample of vacant eligible units by a multinomial-logit utility over
rent relative to budget, distance to campus, friends living in the candidate complex,
and unit quality (McFadden's sampling-of-alternatives result makes this consistent).
Close friends who are both moving try to room together.  Newlyweds move into married
housing.  Moving changes ward, roommates, neighbors and commute — and therefore the
whole downstream social opportunity structure.
"""
from __future__ import annotations

import numpy as np
from scipy.special import expit

from ...population.structure import BYU, UVU, km
from .. import rooms
from ..provenance import link, pick, place_ref, state_ref
from ..state import CTX_ID


class Housing:
    def __init__(self, sim):
        self.sim = sim

    def init(self):
        w = self.sim.w
        U = w.units
        P = w.P
        self.occ = np.bincount(P["unit_id"][P["unit_id"] >= 0], minlength=len(U)).astype(np.int32)
        self._ward_maps()
        rooms.assign_all(w)

    def _ward_maps(self):
        w = self.sim.w
        P = w.P
        cx = P["complex_id"]
        ward = P["ward_id"]
        m = (cx >= 0) & (ward >= 0)
        self.complex_ward = {}
        if m.any():
            pairs = np.c_[cx[m], ward[m]]
            uniq, cnt = np.unique(pairs, axis=0, return_counts=True)
            for (c, wd_), k in zip(uniq, cnt):
                if k > self.complex_ward.get(int(c), (None, 0))[1]:
                    self.complex_ward[int(c)] = (int(wd_), int(k))

    def _assign_ward(self, ids: np.ndarray):
        """Ward for people who moved: complex ward if known, else nearest ward of the right kind."""
        w = self.sim.w
        P = w.P
        kinds = w.wards["kind"]
        wl, wt = w.wards["lon"], w.wards["lat"]
        married = P.is_("rel_status", "married")[ids]
        byu_single = (P["school"][ids] == 1) & ~married & P["enrolled"][ids]
        real, r2w = w.units.real_ward, w.wards.get("real_to_ward")
        for k, i in enumerate(ids):
            if not P["lds_member"][i]:
                P.cols["ward_id"][i] = -1
                continue
            # the real ward of the building they moved into, when its listed ward exists in this world
            ru = int(P["unit_id"][i])
            rw = int(real[ru]) if real is not None and ru >= 0 else -1
            if rw >= 0 and P["age"][i] < 31 and r2w is not None and r2w[rw] >= 0 and (kinds[r2w[rw]] == "married_student") == bool(married[k]):
                P.cols["ward_id"][i] = int(r2w[rw])
                continue
            c = int(P["complex_id"][i])
            if c in self.complex_ward and not married[k]:
                cand_w = self.complex_ward[c][0]
                if kinds[cand_w] in ("byu_ysa", "ysa"):
                    P.cols["ward_id"][i] = cand_w
                    continue
            want = ["married_student", "family"] if married[k] else (["byu_ysa"] if byu_single[k] else ["ysa", "byu_ysa"])
            ok = np.isin(kinds, want)
            if not ok.any():
                ok = np.ones(len(kinds), bool)
            d = km(wl, wt, P["home_lon"][i], P["home_lat"][i]) + np.where(ok, 0, 1e6)
            P.cols["ward_id"][i] = int(np.argmin(d))

    def _vacant(self, mask: np.ndarray) -> np.ndarray:
        U = self.sim.w.units
        return np.where(mask & (self.occ < U.capacity))[0]

    def place(self, ids: np.ndarray, married: bool = False, reason: str = "moved", cause=None, why=None):
        """Move people (singles bed-by-bed, or one couple per call when married=True).

        Provenance: each mover's choice of place is recorded (the chosen place's utility terms measured against the
        average of the places they looked at, and its logit probability among them); `why` = the decisions to move
        (aligned with ids), linked to the moved events."""
        sim, w = self.sim, self.sim.w
        P, U, p = w.P, w.units, sim.p
        if len(ids) == 0:
            return
        rng = sim.streams.gen("housing_place", w.day, int(ids[0]) % 997)
        old = P["unit_id"][ids].copy()
        for o in old[old >= 0]:
            self.occ[o] -= 1
        anchor = np.where((P["school"][ids] == 2)[:, None], np.array(UVU)[None, :], np.array(BYU)[None, :])
        names = ("rent", "distance", "friends", "quality", "culture")
        F = {f: np.zeros(len(ids)) for f in names}
        base = np.zeros(len(ids))
        prob = np.full(len(ids), np.nan)
        if married:
            elig = (U.unit_type == 3) | ((U.unit_type == 2) & (U.capacity <= 4)) | ((U.unit_type == 1) & ~U.contracted)
            cand = self._vacant(elig & (self.occ == 0))
            if len(cand) == 0:
                cand = self._vacant(elig)
            take = rng.choice(cand, size=min(20, len(cand)), replace=False)
            d = km(U.lon[take], U.lat[take], anchor[0, 0], anchor[0, 1])
            util = -0.6 * d + 1.0 * U.quality[take] + rng.gumbel(size=len(take))
            j = int(np.argmax(util))
            u = int(take[j])
            det = {"distance": -0.6 * d, "quality": 1.0 * U.quality[take]}
            self._note_choice(F, base, prob, slice(None), det, j)
            for i in ids:
                self._set_home(i, u)
            self.occ[u] += len(ids)
        else:
            years = ["freshman", "sophomore", "junior", "senior"] if w.env.get("contracted_housing_all_years") else ["freshman"]
            need_contract = (P["school"][ids] == 1) & P.isin("class_standing", years)[ids] & bool(w.env["contracted_housing_required"])
            budget = np.maximum(P.internal["budget_pref"][ids], 250)
            # friends among movers in this call: group close friends of the same sex
            friends_cx = self._friend_complexes(ids)
            for k, i in enumerate(ids):
                sexc = 1 if P["sex"][i] == P.code("sex", "F") else 2
                if need_contract[k]:
                    elig = U.contracted & (U.unit_type != 3) & ~U.married_only
                else:
                    elig = ~U.married_only & (U.unit_type != 3) & (U.unit_type != 0) & \
                        np.where(rng.random() < 0.55, ~U.contracted, True)
                elig = elig & ((U.sex_restriction == 0) | (U.sex_restriction == sexc))
                cand = self._vacant(elig)
                if len(cand) == 0:   # shortage: relax the contract and unit-type rules, never the same-sex rule
                    cand = self._vacant(~U.married_only & ((U.sex_restriction == 0) | (U.sex_restriction == sexc)))
                if len(cand) == 0:
                    cand = self._vacant(~U.married_only)
                take = rng.choice(cand, size=min(25, len(cand)), replace=False)
                per_bed = U.rent_total[take] / np.maximum(U.capacity[take], 1) * w.env.get("rent_index", 1.0) * w.env.get("rent_shock", 1.0)
                d = km(U.lon[take], U.lat[take], anchor[k, 0], anchor[k, 1])
                fr = np.array([friends_cx.get(int(i), {}).get(int(c), 0) for c in U.complex_id[take]])
                det = {"rent": -p("housing.choice.rent") * per_bed / budget[k], "distance": p("housing.choice.distance") * d,
                       "friends": p("housing.choice.friends") * np.log1p(fr), "quality": 0.8 * U.quality[take]}
                util = det["rent"] - det["distance"] + det["friends"] + det["quality"] + rng.gumbel(size=len(take))
                if "culture" in w.meta:   # people sort toward complexes whose culture fits them (attraction–selection)
                    det["culture"] = p("culture.feedback.sorting") * sim.systems["culture"].housing_fit(int(i), U.complex_id[take])
                    util = util + det["culture"]
                det["distance"] = -det["distance"]
                jj = int(np.argmax(util))
                u = int(take[jj])
                self._note_choice(F, base, prob, k, det, jj)
                if U.sex_restriction[u] == 0 and U.unit_type[u] != 4:
                    U.sex_restriction[u] = sexc
                self._set_home(i, u)
                self.occ[u] += 1
        # leaving emptied units unrestricted again
        for o in old[old >= 0]:
            if self.occ[o] == 0 and not U.contracted[o]:
                U.sex_restriction[o] = 0
        self._update_rent(ids)
        self._assign_ward(ids)
        mm = P["unit_id"][ids] != old
        moved = ids[mm]
        if len(moved) and reason:
            did = sim.decisions.record("choose_home", w.day, moved, "chosen", {f: v[mm] for f, v in F.items()},
                                       base=base[mm], prob=prob[mm])
            ev = sim.emit(reason, moved, cause=cause, mech="housing.choice", decision=did)
            if why is not None:
                link(sim, ev, "decision", np.asarray(why, np.int64)[mm], 1.0, "why_move")
            cx = P["complex_id"][moved]
            link(sim, ev, "place", np.where(cx >= 0, place_ref(CTX_ID["complex"], cx), -1), 1.0, "new_home")

    @staticmethod
    def _note_choice(F: dict, base: np.ndarray, prob: np.ndarray, k, det: dict, j: int):
        """Store the chosen place's terms against the average of the places looked at (they add up to its
        deterministic utility minus that average), and its logit probability among them."""
        tot = sum(det.values())
        for f, v in det.items():
            v = np.asarray(v, np.float64)
            F[f][k] = v[j] - v.mean()
        base[k] = float(np.mean(tot))
        e = np.exp(tot - np.max(tot))
        prob[k] = float(e[j] / e.sum())

    def _friend_complexes(self, ids):
        w = self.sim.w
        P, E = w.P, w.E
        out = {}
        if E.n == 0:
            return out
        lo, hi = E.endpoints()
        m = (E["stage"] >= 3)
        a, b = lo[m], hi[m]
        for x, y in ((a, b), (b, a)):
            sel = np.isin(x, ids)
            for i, j in zip(x[sel], y[sel]):
                c = int(P["complex_id"][j])
                if c >= 0 and P["present"][j]:
                    d = out.setdefault(int(i), {})
                    d[c] = d.get(c, 0) + 1
        return out

    def _set_home(self, i: int, u: int):
        w = self.sim.w
        P, U = w.P, w.units
        P.cols["unit_id"][i] = u
        P.cols["household_id"][i] = u
        P.cols["home_lon"][i] = U.lon[u]
        P.cols["home_lat"][i] = U.lat[u]
        P.cols["complex_id"][i] = U.complex_id[u]
        P.cols["city"][i] = U.city[u] if U.city[u] in (0, 1) else 2
        P.cols["neighborhood"][i] = U.nbhd[u]
        ut = U.unit_type[u]
        married = P["rel_status"][i] == P.code("rel_status", "married")
        living = ("dorm" if ut == 0 else "married_housing" if (ut == 3 or married) else "contracted" if U.contracted[u]
                  else "house_share" if ut in (2, 4) else "apartment")
        P.cols["living"][i] = P.code("living", living)
        anchor = UVU if P["school"][i] == 2 else BYU
        d = float(km(U.lon[u], U.lat[u], anchor[0], anchor[1]))
        P.cols["dist_campus_km"][i] = d
        P.cols["commute_min"][i] = d * 13 if d < 1.5 else (6 + d * 2.4 if P["owns_car"][i] else 10 + d * 4.5 / max(w.env.get("transit_quality", 1.0), 0.2))

    def _update_rent(self, ids):
        w = self.sim.w
        P, U = w.P, w.units
        u = P["unit_id"][ids]
        ok = u >= 0
        occ = np.maximum(self.occ[np.maximum(u, 0)], 1)
        married = P.is_("rel_status", "married")[ids]
        share = np.where(U.unit_type[np.maximum(u, 0)] == 0, U.rent_total[np.maximum(u, 0)] / np.maximum(U.capacity[np.maximum(u, 0)], 1),
                         np.where(married, U.rent_total[np.maximum(u, 0)] / 2, U.rent_total[np.maximum(u, 0)] / np.maximum(U.capacity[np.maximum(u, 0)], occ)))
        P.cols["rent"][ids] = np.where(ok, share, 0)

    def couple_move(self, a: np.ndarray, b: np.ndarray, cause):
        for x, y, c in zip(a, b, np.atleast_1d(cause)):
            self.place(np.array([x, y]), married=True, reason="moved", cause=int(c))

    # ------------------------------------------------------------------ daily / monthly
    def daily(self):
        self._turnover()
        rooms.sync(self.sim)          # beds for whoever moved, arrived or came back today (before the night's positions)

    def _turnover(self):
        sim, w = self.sim, self.sim.w
        if not sim.cal.is_lease_turnover(w.day):
            return
        P, p = w.P, sim.p
        renters = P["present"] & (P["unit_id"] >= 0) & ~P.isin("living", ["with_parents", "family_home"]) & \
            ~P.is_("rel_status", "married") & (P["age"] < 32)
        T = {"roommates": 2.0 * (P["roommate_cohesion"] - 0.5), "rent": 1.2 * np.clip(P["rent_burden"] - 0.5, 0, 2),
             "dorm": 0.8 * P.is_("living", "dorm"), "openness": 0.3 * sim.z("openness")}
        h = expit(p("housing.move.base") - T["roommates"] + T["rent"] + T["dorm"] + T["openness"])
        movers = np.where(renters & (sim.u("move") < h))[0]
        if len(movers):
            rec = pick(T, movers)
            rec["roommates"] = -rec["roommates"]
            why = sim.decisions.record("move_out", w.day, movers, "moved", rec, base=p("housing.move.base"), prob=h[movers],
                                       refs={"rent": ("state", state_ref(sim, "rent_burden", movers)),
                                             "roommates": ("state", state_ref(sim, "roommate_cohesion", movers))})
            self.place(movers, why=why)

    def monthly(self):
        sim, w = self.sim, self.sim.w
        U = w.units
        env = w.env
        # construction: housing_supply_index > 1 adds new near-campus apartment units over time
        target_units = int(round(self._base_units() * env.get("housing_supply_index", 1.0)))
        add = target_units - len(U)
        if add > 0:
            self._construct(min(add, max(10, int(0.04 * len(U)))))
        # market rent responds to vacancy in the student zone
        student = (km(U.lon, U.lat, *BYU) < 3) | (km(U.lon, U.lat, *UVU) < 2.5)
        cap = U.capacity[student].sum()
        vac = 1 - self.occ[student].sum() / max(cap, 1)
        adj = sim.p("housing.market.rent_response") * (0.06 - vac)
        sysenv = sim.systems["environment"]
        sysenv.market_rent = float(np.clip(sysenv.market_rent * (1 + adj), 0.6, 2.0))
        U.rent_total = (U.rent_total * (1 + adj)).astype(np.float32)

    def _base_units(self):
        if not hasattr(self, "_n0"):
            self._n0 = len(self.sim.w.units)
        return self._n0

    def _construct(self, k: int):
        sim, w = self.sim, self.sim.w
        U = w.units
        rng = sim.streams.gen("construction", w.day)
        apt = np.where((U.unit_type == 1) & (km(U.lon, U.lat, *BYU) < 2.5))[0]
        if len(apt) == 0:
            return
        src = rng.choice(apt, k)
        for name in ("lon", "lat"):
            setattr(U, name, np.r_[getattr(U, name), getattr(U, name)[src] + rng.normal(0, 0.0015, k)])
        U.capacity = np.r_[U.capacity, U.capacity[src]]
        U.rent_total = np.r_[U.rent_total, U.rent_total[src] * 1.05]
        U.contracted = np.r_[U.contracted, U.contracted[src]]
        U.sex_restriction = np.r_[U.sex_restriction, np.zeros(k, np.uint8)]
        U.married_only = np.r_[U.married_only, np.zeros(k, bool)]
        U.unit_type = np.r_[U.unit_type, U.unit_type[src]]
        U.complex_id = np.r_[U.complex_id, U.complex_id[src]]
        U.city = np.r_[U.city, U.city[src]]
        U.quality = np.r_[U.quality, np.full(k, 0.85, np.float32)]
        U.kind_src = np.r_[U.kind_src, U.kind_src[src]]
        U.nbhd = np.r_[U.nbhd, U.nbhd[src]]
        if U.room0 is not None:     # new buildings near campus: the same layouts as the units they copy, no address yet
            U.building_id = np.r_[U.building_id, np.full(k, -1, np.int32)]
            U.floor = np.r_[U.floor, np.zeros(k, np.int8)]
            U.label = U.label + [""] * k
            caps = [U.room_cap[U.room0[s_]: U.room0[s_] + U.n_rooms[s_]] for s_ in src]
            U.room0 = np.r_[U.room0, len(U.room_cap) + np.r_[0, np.cumsum([len(c) for c in caps])[:-1]]].astype(np.int32)
            U.n_rooms = np.r_[U.n_rooms, np.array([len(c) for c in caps], np.uint8)]
            U.room_unit = np.r_[U.room_unit, np.repeat(np.arange(len(U.lon) - k, len(U.lon), dtype=np.int32), [len(c) for c in caps])]
            U.room_cap = np.r_[U.room_cap, np.concatenate(caps).astype(np.uint8)]
        self.occ = np.r_[self.occ, np.zeros(k, np.int32)]
