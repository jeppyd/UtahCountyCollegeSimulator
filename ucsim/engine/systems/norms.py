"""Behavioral norms and practice diffusion through the friendship network.

Adoption hazard = f(personal attitude, perceived peer adoption).  Normative/risky behaviors
spread as *complex contagion* (Centola & Macy 2007): one adopting friend helps little,
several help a lot.  Dissonance can also be resolved by quitting (guilt raises quit hazard).
"""
from __future__ import annotations

import numpy as np
from scipy.special import expit

PRACTICES = {
    # name: (person column, adoption event, value when adopted)
    "coffee": ("coffee", "started_coffee", 2),
    "alcohol": ("alcohol", "started_drinking", 1),
    "pickleball": ("pickleball", "adopted_practice", True),
    "dating_app": ("app_user", "adopted_practice", True),
}


class Norms:
    def __init__(self, sim):
        self.sim = sim

    def daily(self):
        pass

    def _peer(self, adopted: np.ndarray):
        net = self.sim.systems["network"]
        indptr, nbr, _ = net.padded()
        P = self.sim.w.P
        n = P.n
        cnt = np.zeros(n)
        deg = np.diff(indptr)[:n]
        src = np.repeat(np.arange(len(indptr) - 1), np.diff(indptr))
        np.add.at(cnt, src, adopted[nbr].astype(float))
        frac = np.where(deg > 0, cnt / np.maximum(deg, 1), 0)
        return cnt, frac

    def weekly(self):
        sim, w = self.sim, self.sim.w
        P, p, env = w.P, sim.p, w.env
        n = P.n
        present = P["present"]
        lds_active = P["lds_member"] & (P["activity"] >= 2)
        permitted = 1.0 if env["coffee_permitted"] else 0.0
        prohib = P["orthodoxy"] * lds_active * (1 - permitted)
        thr = p("norms.contagion.threshold")
        for name, (col, ev, val) in PRACTICES.items():
            cur = P[col]
            adopted = cur > 0 if cur.dtype != np.bool_ else cur
            cnt, frac = self._peer(adopted)
            peer = p("norms.contagion.peer") * np.log1p(cnt) * np.clip(cnt / thr, 0, 1) + 0.8 * frac
            if name == "coffee":
                att = (p("norms.coffee.base") - p("norms.coffee.prohibition") * prohib * (1 + P["chastity_commitment"])
                       + 0.8 * (1 - P["faith_belief"]) + 0.6 * P["moral_autonomy"] + 0.2 * sim.z("sensation_seeking")
                       + p("norms.coffee.permitted_boost") * permitted * P["lds_member"])
                quit_h = p("norms.quit.guilt") * P["guilt"] * prohib
            elif name == "alcohol":
                muslim = P.is_("affiliation", "Muslim")
                att = (p("norms.alcohol.base") - 2.5 * P["orthodoxy"] * lds_active - 1.2 * P["faith_belief"] * P["lds_member"]
                       - P["own_religiosity"] * np.where(muslim, 3.5, 0.8) * ~P["lds_member"]
                       + 0.6 * P["moral_autonomy"] + 0.4 * sim.z("sensation_seeking") + 0.4 * (P["age"] >= 21))
                quit_h = p("norms.quit.guilt") * P["guilt"] * P["orthodoxy"] * lds_active
            elif name == "pickleball":
                att = p("norms.pickleball.base") + 0.8 * P["sports"] + 0.3 * sim.z("extraversion") + 0.3 * P["hikes"]
                quit_h = np.full(n, 0.004)
            else:  # dating apps
                seek = P.isin("rel_status", ["single", "divorced"]) & (P["age"] >= 18)
                att = np.where(seek, p("norms.app.base") + 1.5 * P["dating_motivation"] + np.log(env["app_appeal"] + 1e-9)
                               + 0.3 * (P["picky"] - 2) / 2, -9)
                quit_h = np.where(seek, 0.01, 0.15)
            hz = expit(att + peer) * 0.05
            u = sim.u(f"adopt_{name}")
            new = present & ~adopted & (u < hz)
            qq = present & adopted & (sim.u(f"quit_{name}") < np.clip(quit_h, 0, 0.5))
            if new.any():
                ids = np.where(new)[0]
                P.cols[col][ids] = val
                if ev == "adopted_practice":
                    sim.emit(ev, ids, value=float(list(PRACTICES).index(name)), mech=f"norms.{name if name != 'dating_app' else 'app'}")
                else:
                    sim.emit(ev, ids, mech=f"norms.{name}", ev={"norm_permitted": permitted})
            if qq.any():
                P.cols[col][np.where(qq)[0]] = 0 if val is not True else False
            if name == "dating_app" and new.any():
                P.cols["app_hours"][np.where(new)[0]] = np.maximum(P["app_hours"][np.where(new)[0]], 1.0)
        # moral incongruence around pornography (Grubbs et al. 2019): use × moral disapproval
        P["porn_incongruence"] = np.clip(P["porn_use"] / 3 * P["chastity_commitment"] * (0.5 + P["orthodoxy"]) * 1.4, 0, 1).astype(np.float32)
