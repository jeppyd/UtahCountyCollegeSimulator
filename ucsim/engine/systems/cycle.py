"""Menstrual cycle: a daily clock per woman that nudges mood, energy, anxiety and desire a little.

Design notes (parameters in config/mechanisms/21_cycle.yaml, person variables in config/variables/14_cycle.yaml)
* Women aged 12–51 who are not pregnant and didn't give birth in the last 120 days have a cycle day that advances each
  morning. Each has her own typical length (Bull et al. 2019: mean ≈ 29 days) and each cycle varies by a day or two.
* Evidence says cycle effects are modest on average and very different between people (Romans et al. 2012), so every
  effect is scaled by her own sensitivity (median ≈ 0.06; about one in five notably, a few percent strongly, like PMDD)
  and flattened to 0.3 by hormonal birth control. Nothing here is decided by the cycle alone: it only adds small terms
  to the emotion system's mood/fatigue/anxiety (`term`) and a couple's weekly intimacy step (`desire`).
* Per-person values are fixed draws from the person's id (no random stream), so they match across worlds and
  newcomers get theirs on arrival; only the cycle-to-cycle jitter uses a stream ("cycle_jitter").
"""
from __future__ import annotations

import numpy as np

from ...analysis.query import hash_uniform

HC_FLATTEN = 0.3      # what is left of the cycle's swings on hormonal birth control
PILL_CYCLE = 28       # hormonal birth control: a 28-day pack with a 4-day withdrawal bleed


class Cycle:
    def __init__(self, sim):
        self.sim = sim

    def init(self):
        P = self.sim.w.P
        P.add_internal("cycle_base_len", np.uint8, 0)
        P.add_internal("period_len", np.uint8, 5)
        P.add_internal("desire_amp", np.float32, 0.0)
        self.daily(advance=False)

    # ------------------------------------------------------------------ per-person draws
    def _traits(self, ids: np.ndarray):
        """Typical length, period length, sensitivity and desire amplitude for women without them yet."""
        from scipy.special import ndtri
        P = self.sim.w.P
        z = ndtri(np.clip(hash_uniform(ids, "cycle:length"), 1e-6, 1 - 1e-6))
        P.internal["cycle_base_len"][ids] = np.clip(np.round(29 + 2.5 * z), 23, 38).astype(np.uint8)
        P.internal["period_len"][ids] = (4 + np.floor(3 * hash_uniform(ids, "cycle:period"))).astype(np.uint8)
        # heavily skewed: P(> 0.4) ≈ 20%, P(> 0.7) ≈ 8%, P(> 0.85) ≈ 4%
        P.cols["cycle_sensitivity"][ids] = (hash_uniform(ids, "cycle:sensitivity") ** 4).astype(np.float32)
        P.internal["desire_amp"][ids] = (0.3 + 0.7 * hash_uniform(ids, "cycle:desire")).astype(np.float32)

    # ------------------------------------------------------------------ daily clock
    def daily(self, advance: bool = True):
        sim, w = self.sim, self.sim.w
        P = w.P
        n = P.n
        day = w.day
        female = P.is_("sex", "F") & P["present"].astype(bool)
        # newborn_until is the birth day + 120 (lifecourse.py)
        new_mother = P.internal["newborn_until"][:n] > day if "newborn_until" in P.internal else np.zeros(n, bool)
        cycling = female & (P["age"] >= 12) & (P["age"] <= 51) & ~P["pregnant"].astype(bool) & ~new_mother
        need = female & (P.internal["cycle_base_len"][:n] == 0)
        if need.any():
            self._traits(np.flatnonzero(need))
        # hormonal birth control: a fixed draw per woman against a share that depends on her situation (a smaller share
        # is contained in a larger one, so marrying can start it but never makes a woman who used it stop)
        married = P.is_("rel_status", "married")
        share = np.where(married, 0.40, np.where(P["lds_member"].astype(bool), 0.12, 0.30))
        hc = cycling & (hash_uniform(np.arange(n), "cycle:hc") < share)
        P["hormonal_contraception"] = hc
        cd = P["cycle_day"].astype(np.int32)
        ln = P["cycle_length"].astype(np.int32)
        base = P.internal["cycle_base_len"][:n].astype(np.int32)
        ln = np.where(hc, PILL_CYCLE, np.where(ln == 0, base, ln))
        start = cycling & (cd == 0)       # a cycle begins (newcomers, after a birth): spread evenly across it
        cd = np.where(start, 1 + np.floor(hash_uniform(np.arange(n), "cycle:start") * ln).astype(np.int32), cd)
        if advance:
            cd = np.where(cycling & ~start, cd + 1, cd)
            wrap = cycling & (cd > ln)
            if wrap.any():
                j = int(round(sim.p("cycle.rhythm.jitter")))
                u = sim.u("cycle_jitter")[:n]
                nxt = np.clip(base + np.floor(u * (2 * j + 1)).astype(np.int32) - j, 21, 45)
                ln = np.where(wrap, np.where(hc, PILL_CYCLE, nxt), ln)
                cd = np.where(wrap, 1, cd)
        cd = np.where(cycling, cd, 0)
        ln = np.where(cycling, ln, 0)
        P["cycle_day"] = cd.astype(np.uint8)
        P["cycle_length"] = ln.astype(np.uint8)
        P["cycle_phase"] = self._phase(cd, ln, hc)

    def _phase(self, cd, ln, hc) -> np.ndarray:
        P = self.sim.w.P
        ov = ln - 14
        per = P.internal["period_len"][: P.n].astype(np.int32)
        c = lambda s: P.code("cycle_phase", s)  # noqa: E731
        return np.select(
            [cd == 0, hc & (cd <= 4), hc, cd <= per, cd > ln - 5, (cd >= ov - 5) & (cd <= ov), cd < ov],
            [c("none"), c("period"), c("steady (birth control)"), c("period"), c("premenstrual"), c("fertile window"),
             c("follicular")], c("luteal")).astype(np.uint8)

    # ------------------------------------------------------------------ what the cycle does
    def _shapes(self):
        """(premenstrual, period, fertile, on-period, luteal) weights for today, all 0 without a cycle."""
        P = self.sim.w.P
        cd = P["cycle_day"].astype(np.float64)
        ln = P["cycle_length"].astype(np.float64)
        on = cd > 0
        hc = P["hormonal_contraception"].astype(bool)
        pm = np.clip((cd - (ln - 6)) / 4, 0, 1) + np.where(cd == 1, 1.0, np.where(cd == 2, 0.5, 0.0))
        per = np.select([cd == 1, cd == 2, cd == 3], [1.0, 0.8, 0.4], 0.0)
        ov = ln - 14
        fert = np.where(hc, 0.0, np.exp(-(((cd - (ov - 1)) / 2.0) ** 2)))
        period_on = cd <= np.where(hc, 4, P.internal["period_len"][: P.n])
        luteal = ~hc & (cd > ov + 1) & (cd <= ln - 5)
        z = lambda x: np.where(on, x, 0.0)  # noqa: E731
        return z(pm), z(per), z(fert), z(period_on.astype(float)), z(luteal.astype(float))

    def term(self, state: str) -> np.ndarray | None:
        """The cycle's additive term in an emotion state (mood, fatigue or anxiety), or None for other states."""
        if state not in ("mood", "fatigue", "anxiety"):
            return None
        P = self.sim.w.P
        p = self.sim.p
        s = P["cycle_sensitivity"].astype(np.float64)
        flat = np.where(P["hormonal_contraception"].astype(bool), HC_FLATTEN, 1.0)
        pm, per, _, _, _ = self._shapes()
        if state == "mood":
            return -p("mood.cycle.beta") * s * flat * pm
        if state == "anxiety":
            return p("anxiety.cycle.beta") * s * flat * pm
        return p("fatigue.cycle.beta") * (0.3 + 0.7 * s) * flat * (per + 0.5 * pm)

    def desire(self, x: np.ndarray) -> np.ndarray:
        """Each person's cycle shift in interest in physical intimacy today (0 for men and without a cycle)."""
        P = self.sim.w.P
        _, _, fert, period_on, luteal = self._shapes()
        flat = np.where(P["hormonal_contraception"].astype(bool), HC_FLATTEN, 1.0)
        d = P.internal["desire_amp"][: P.n] * flat * (fert - 0.7 * period_on - 0.15 * luteal)
        return d[x]
