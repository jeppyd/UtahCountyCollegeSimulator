"""Place cultures: apartments, complexes and wards that become recognizable ecosystems.

Groups are more than containers. Each apartment, complex and ward carries a culture — how social it is,
how religiously observant, how warm — computed from the people living or worshipping there, with inertia,
so a culture outlives the residents who made it (Schneider 1987's attraction–selection–attrition; cultural
transmission through overlapping cohorts). The culture then feeds back on individuals:

    residents' behavior ──► unit/complex/ward culture (with memory)
          ▲                         │
          │                         ├─► hosting and accepting invitations (a social apartment hosts more)
          │                         ├─► perceived norms (a devout complex raises the attendance norm)
          │                         ├─► who moves in at lease turnover (people sort toward places that fit)
          │                         └─► how fast newcomers feel they belong in a ward (warm wards integrate)
          └──── new residents, new friendships, new dating opportunities ◄─┘

That is the micro → meso → macro → micro loop: people shape a complex's culture, the culture changes who
visits and who moves in, which changes the network and the culture again.
"""
from __future__ import annotations

import numpy as np


def _z(x: np.ndarray, mask: np.ndarray) -> np.ndarray:
    xs = x[mask]
    if len(xs) < 2:
        return np.zeros_like(x)
    sd = float(xs.std()) or 1.0
    return (x - float(xs.mean())) / sd


class Culture:
    def __init__(self, sim):
        self.sim = sim
        self.history: list[dict] = []

    def init(self):
        w = self.sim.w
        self.gath = np.zeros(len(w.units), np.float32)
        self.visits = np.zeros(len(w.units), np.float32)
        if "unit_social" not in w.meta.get("culture", {}):
            now = self._now()
            w.meta["culture"] = {k: v.astype(np.float32) for k, v in now.items()}
        self._person()

    # ------------------------------------------------------------------ observation hooks
    def observe_gathering(self, units: np.ndarray, sizes: np.ndarray):
        self._grow()
        np.add.at(self.gath, units, 1.0 + 0.2 * np.asarray(sizes, float))

    def observe_visits(self, units: np.ndarray):
        self._grow()
        np.add.at(self.visits, units, 1.0)

    def _grow(self):
        w = self.sim.w
        nu = len(w.units)
        C = w.meta.get("culture", {})
        if len(self.gath) < nu:
            self.gath = np.r_[self.gath, np.zeros(nu - len(self.gath), np.float32)]
            self.visits = np.r_[self.visits, np.zeros(nu - len(self.visits), np.float32)]
        for k in ("unit_social", "unit_relig", "unit_cohesion"):
            if k in C and len(C[k]) < nu:
                fill = float(np.median(C[k])) if len(C[k]) else 0.0
                C[k] = np.r_[C[k], np.full(nu - len(C[k]), fill, np.float32)]

    # ------------------------------------------------------------------ aggregates
    def _now(self) -> dict:
        w = self.sim.w
        P = w.P
        nu = len(w.units)
        ncx = w.complexes.height
        nw = len(w.wards["kind"])
        pres = P["present"]
        unit = P["unit_id"]
        m = pres & (unit >= 0)
        u = unit[m]
        occ = np.bincount(u, minlength=nu).astype(float)
        practice = np.where(P["lds_member"], P["attend_rate"], P["service_attend"])
        relig = np.bincount(u, weights=practice[m], minlength=nu)
        coh = np.bincount(u, weights=P["roommate_cohesion"][m], minlength=nu)
        has = occ > 0
        social = np.log1p((self.gath[:nu] if len(self.gath) >= nu else np.zeros(nu)) * 3
                          + (self.visits[:nu] if len(self.visits) >= nu else np.zeros(nu))) / np.maximum(np.sqrt(occ), 1)
        out = {"unit_social": np.where(has, social, 0.0), "unit_relig": np.where(has, relig / np.maximum(occ, 1), 0.5),
               "unit_cohesion": np.where(has, coh / np.maximum(occ, 1), 0.5)}
        cx = P["complex_id"]
        mc = pres & (cx >= 0)
        c = cx[mc]
        cocc = np.bincount(c, minlength=ncx).astype(float)
        party = ((P["coffee"] > 0) | (P["alcohol"] > 0)).astype(float)
        married = P.is_("rel_status", "married").astype(float)
        ucx = np.asarray(w.units.complex_id[:nu])
        sel = has & (ucx >= 0)
        hosted = np.bincount(ucx[sel], weights=out["unit_social"][sel], minlength=ncx)
        nunits = np.bincount(ucx[sel], minlength=ncx).astype(float)
        hc = cocc > 0
        out["cx_social"] = np.where(nunits > 0, hosted / np.maximum(nunits, 1), 0.0)
        out["cx_relig"] = np.where(hc, np.bincount(c, weights=practice[mc], minlength=ncx) / np.maximum(cocc, 1), 0.5)
        out["cx_party"] = np.where(hc, np.bincount(c, weights=party[mc], minlength=ncx) / np.maximum(cocc, 1), 0.0)
        out["cx_married"] = np.where(hc, np.bincount(c, weights=married[mc], minlength=ncx) / np.maximum(cocc, 1), 0.0)
        out["cx_residents"] = cocc
        ward = P["ward_id"]
        mw = pres & (ward >= 0)
        wd = ward[mw]
        wocc = np.bincount(wd, minlength=nw).astype(float)
        hw = wocc > 0
        out["ward_warmth"] = np.where(hw, np.bincount(wd, weights=P["ward_belonging"][mw], minlength=nw) / np.maximum(wocc, 1), 0.5)
        out["ward_activity"] = np.where(hw, np.bincount(wd, weights=P["ward_activity_rate"][mw], minlength=nw) / np.maximum(wocc, 1), 0.3)
        return out

    def weekly(self):
        sim, w = self.sim, self.sim.w
        p = sim.p
        self._grow()
        now = self._now()
        C = w.meta["culture"]
        rates = {"unit": p("culture.inertia.unit"), "cx": p("culture.inertia.complex"), "ward": p("culture.inertia.ward")}
        occupied_u = np.bincount(w.P["unit_id"][(w.P["unit_id"] >= 0) & w.P["present"]], minlength=len(w.units)) > 0
        for k, v in now.items():
            if k == "cx_residents":
                C[k] = v.astype(np.float32)
                continue
            r = rates["unit"] if k.startswith("unit") else rates["cx"] if k.startswith("cx") else rates["ward"]
            old = C.get(k, v)
            if len(old) < len(v):
                old = np.r_[old, v[len(old):]]
            if k.startswith("unit"):
                # an empty apartment keeps its reputation until someone moves in
                C[k] = np.where(occupied_u, (1 - r) * old + r * v, old).astype(np.float32)
            else:
                C[k] = ((1 - r) * old + r * v).astype(np.float32)
        self.gath[:] = 0
        self.visits[:] = 0
        self._person()
        d = sim.cal.date(w.day)
        if d.day <= 7:   # first Sunday-night of the month: keep a record for place histories
            self.history.append({"day": int(w.day), "cx_social": C["cx_social"].round(3).copy(), "cx_relig": C["cx_relig"].round(3).copy(),
                                 "cx_party": C["cx_party"].round(3).copy()})

    def _person(self):
        """Each person's home culture, as fields people can be filtered, mapped and charted by."""
        w = self.sim.w
        P = w.P
        C = w.meta["culture"]
        unit, cx = P["unit_id"], P["complex_id"]
        us = C["unit_social"]
        occ = np.bincount(unit[(unit >= 0) & P["present"]], minlength=len(us)) > 0
        z = _z(us, occ)
        P["home_social_culture"] = np.where(unit >= 0, z[np.maximum(unit, 0)], 0.0).astype(np.float32)
        P["home_faith_culture"] = np.where(cx >= 0, C["cx_relig"][np.maximum(cx, 0)], C["unit_relig"][np.maximum(unit, 0)]).astype(np.float32)

    # ------------------------------------------------------------------ feedback hooks
    def host_mult(self, unit: np.ndarray) -> np.ndarray:
        """Social apartments host more (culture.feedback.hosting)."""
        w, p = self.sim.w, self.sim.p
        C = w.meta["culture"]
        us = C["unit_social"]
        occ = np.bincount(w.P["unit_id"][(w.P["unit_id"] >= 0) & w.P["present"]], minlength=len(us)) > 0
        z = _z(us, occ)
        return np.exp(p("culture.feedback.hosting") * np.clip(np.where(unit >= 0, z[np.maximum(unit, 0)], 0.0), -2, 3))

    def complex_social_z(self, cx: np.ndarray) -> np.ndarray:
        C = self.sim.w.meta["culture"]
        cs = C["cx_social"]
        z = _z(cs, C["cx_residents"] > 0)
        return np.where(cx >= 0, np.clip(z[np.maximum(cx, 0)], -2, 3), 0.0)

    def complex_relig(self, cx: np.ndarray) -> np.ndarray:
        C = self.sim.w.meta["culture"]
        return np.where(cx >= 0, C["cx_relig"][np.maximum(cx, 0)], np.nan)

    def ward_warmth_dev(self, ward: np.ndarray) -> np.ndarray:
        C = self.sim.w.meta["culture"]
        ww = C["ward_warmth"]
        return np.where(ward >= 0, ww[np.maximum(ward, 0)] - float(ww.mean()), 0.0)

    def housing_fit(self, i: int, complexes: np.ndarray) -> np.ndarray:
        """How well candidate complexes' cultures fit a mover (religious practice and sociability)."""
        sim, w = self.sim, self.sim.w
        P = w.P
        C = w.meta["culture"]
        practice = float(P["attend_rate"][i] if P["lds_member"][i] else P["service_attend"][i])
        rel = np.where(complexes >= 0, C["cx_relig"][np.maximum(complexes, 0)], practice)
        soc = self.complex_social_z(complexes)
        ex = float(sim.z("extraversion")[i])
        return -2.0 * np.abs(rel - practice) - 0.4 * np.abs(soc - ex)

    # ------------------------------------------------------------------ queries
    def complex_profile(self, cx: int) -> dict:
        C = self.sim.w.meta["culture"]
        out = {k[3:]: round(float(C[k][cx]), 3) for k in ("cx_social", "cx_relig", "cx_party", "cx_married", "cx_residents")}
        out["social_z"] = round(float(self.complex_social_z(np.array([cx]))[0]), 2)
        out["history"] = [{"day": h["day"], "social": float(h["cx_social"][cx]), "relig": float(h["cx_relig"][cx]),
                           "party": float(h["cx_party"][cx])} for h in self.history if cx < len(h["cx_social"])]
        return out
