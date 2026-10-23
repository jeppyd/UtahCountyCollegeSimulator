"""Coping: the mediated path from a hard time to behavior and back.

    event → appraisal (sim.appraise) → emotion (decaying effects) → coping need
          → strategy from the person's repertoire → behavior → experienced relief → learning

Rather than rules like ``breakup → behavior X``, a person whose stress, mood or loneliness sits past their
tolerance for a few days enters a coping episode and picks a strategy from what their traits favor, what is
available and what has worked for them before (a learned value per strategy, Rescorla–Wagner):

* **support** — reach out to close friends (more contact, more disclosure, support logged on the tie);
  relief depends on whether supportive people are actually there.
* **active** — tackle the problem: study more for academic strain, work/job-hunt for money strain.
* **religious** — prayer, scripture, church: relief scales with belief (positive religious coping).
* **distraction** — gym, outdoors, outings.
* **withdrawal** — stay in, skip things, contact less: a little immediate respite, and the costs show up
  later through less contact (the loneliness loop emerges; it is not scripted).

Rumination (a trait) runs alongside any strategy: it rehearses negative memories, which keeps a named
negative mood term alive (memory.py).

Families of coping follow Skinner et al. (2003); outcomes follow Ano & Vasconcelles (2005) for religious
coping, Holahan & Moos (1987) and Penley et al. (2002) for avoidance vs approach coping, Nolen-Hoeksema
(2000) for rumination. Relief magnitudes are hypothetical and carry ranges (config/mechanisms/08_coping.yaml).
"""
from __future__ import annotations

import numpy as np

from ..provenance import link, softmax_prob, state_ref

STRATEGIES = ["none", "support", "active", "religious", "distraction", "withdrawal"]
S = {k: i for i, k in enumerate(STRATEGIES)}
STRESSORS = ["academic", "financial", "romantic", "social", "faith", "general"]


class Coping:
    def __init__(self, sim):
        self.sim = sim

    def init(self):
        P = self.sim.w.P
        for c, dt, f in (("cope_start", np.int32, -1), ("cope_need0", np.float32, 0.0), ("cope_ewma", np.float32, 0.0),
                         ("cope_low_days", np.int16, 0), ("cope_stressor", np.uint8, 5), ("neg_load", np.float32, 0.0),
                         ("contacted_today", np.bool_, False), ("cope_event", np.int64, -1)):
            P.add_internal(c, dt, f)
        for s in STRATEGIES[1:]:
            P.add_internal(f"cope_v_{s}", np.float32, 0.5)

    # ------------------------------------------------------------------ need
    def need(self) -> np.ndarray:
        P, p = self.sim.w.P, self.sim.p
        raw = (0.6 * np.clip(P["stress"] - p("coping.need.stress"), 0, None)
               + 0.8 * np.clip(p("coping.need.mood") - P["mood"], 0, None)
               + 0.5 * np.clip(P["loneliness"] - p("coping.need.loneliness"), 0, None)
               + 0.4 * np.clip(P["anxiety"] - 0.55, 0, None))
        return np.clip(raw / 0.25, 0, 1)

    def _stressor(self, ids: np.ndarray) -> np.ndarray:
        """The concern most responsible for the strain (for active coping and for the person page)."""
        P = self.sim.w.P
        M = np.stack([P["academic_pressure"][ids] * P["enrolled"][ids], P["financial_stress"][ids],
                      P["romantic_longing"][ids] * 0.8 + np.nan_to_num(0.6 - P["relationship_satisfaction"][ids], nan=0.0).clip(0),
                      P["loneliness"][ids] - 0.15, P["guilt"][ids] + 0.5 * P["faith_crisis"][ids], np.full(len(ids), 0.25)])
        return np.argmax(M, axis=0).astype(np.uint8)

    # ------------------------------------------------------------------ daily
    def daily(self):
        sim, w = self.sim, self.sim.w
        P, p = w.P, sim.p
        n = P.n
        day = w.day
        need = self.need()
        P["coping_need"] = need.astype(np.float32)
        ew = P.internal["cope_ewma"][:n]
        ew[:] = 0.6 * ew + 0.4 * need
        pres = P["present"]
        strat = P["coping_strategy"]
        active = strat > 0
        # ---- relief from today's coping, by strategy
        relief_today = np.zeros(n, np.float32)
        if active.any():
            relief_today = self._relief(strat, need)
        rel = P["coping_relief"]
        P["coping_relief"] = np.clip(0.84 * rel + 0.16 * relief_today * p("coping.relief.scale"), 0, 1).astype(np.float32)
        # ---- end of episodes: strain eased for a few days, or a month without resolution
        low = active & (ew < p("coping.episode.off"))
        P.internal["cope_low_days"][:n] = np.where(low, P.internal["cope_low_days"][:n] + 1, 0)
        dur = day - P.internal["cope_start"][:n]
        done = active & ((P.internal["cope_low_days"][:n] >= 3) | (dur > 35) | ~pres)
        if done.any():
            self._end(np.where(done)[0], need)
        # ---- start of episodes
        # strain has to build before someone notices it and changes how they cope: once over the line, a daily chance
        # (about three days on average), so a new semester doesn't start everyone coping on the same morning
        start = pres & (P["coping_strategy"] == 0) & (ew > p("coping.episode.on")) & (sim.u("cope_on") < 0.3)
        if start.any():
            self._start(np.where(start)[0], need)
        # ---- rumination rehearses negative memories while strained
        rum = pres & (ew > 0.25) & (sim.u("ruminate") < P["rumination"])
        if rum.any():
            sim.memory.rehearse_negative(np.where(rum)[0], day, p("memory.forgetting.decay"))
        P.internal["contacted_today"][:n] = False

    def _start(self, ids: np.ndarray, need: np.ndarray):
        sim, w = self.sim, self.sim.w
        P, p = w.P, sim.p
        z = lambda v: sim.z(v)[ids]  # noqa: E731
        stressor = self._stressor(ids)
        controllable = np.isin(stressor, [0, 1, 2])      # school, money, dating: something can be done
        V = {s: P.internal[f"cope_v_{s}"][ids] for s in STRATEGIES[1:]}
        lv = p("coping.choice.learned")
        U = np.full((len(ids), len(STRATEGIES)), -9.0)
        # each strategy's utility, term by term (the first entry is that option's constant, recorded as its base)
        no_one = np.where(P["n_close_friends"][ids] + (P["partner_id"][ids] >= 0) > 0, 0.0, -3.0)
        relig = np.where(P["lds_member"][ids], P["faith_belief"][ids] * P["religious_identity"][ids], P["own_religiosity"][ids])
        cares_faith = P["cares_faith"][ids] > 0.4
        T = {
            "support": {"extraversion": 0.5 * z("extraversion"), "agreeableness": 0.3 * z("agreeableness"),
                        "avoidance": -(0.4 * z("attachment_avoidance")), "perceived_support": 1.2 * (P["perceived_support"][ids] - 0.5),
                        "learned": lv * V["support"], "_base": p("coping.choice.support_base"), "no_one_close": no_one},
            "active": {"conscientiousness": 0.6 * z("conscientiousness"), "controllable": 0.8 * controllable, "_base": -0.3,
                       "learned": lv * V["active"], "self_efficacy": 0.6 * (P["self_eff_academic"][ids] - 0.5) * (stressor == 0)},
            "religious": {"_base": -0.4, "faith": 2.0 * (relig - 0.4), "learned": lv * V["religious"]},
            "distraction": {"sensation": 0.4 * z("sensation_seeking"), "cares_health": 0.8 * P["cares_health"][ids],
                            "cares_fun": 0.5 * P["cares_fun"][ids], "_base": -0.5, "learned": lv * V["distraction"]},
            "withdrawal": {"neuroticism": 0.5 * z("neuroticism"), "social_anxiety": 0.5 * z("social_anxiety"),
                           "avoidance": 0.4 * z("attachment_avoidance"), "expect_social": -(1.0 * (P["expect_social"][ids] - 0.6)),
                           "_base": p("coping.choice.withdrawal_base"), "learned": lv * V["withdrawal"]},
        }
        t = T["support"]
        U[:, S["support"]] = (t["extraversion"] + t["agreeableness"] - 0.4 * z("attachment_avoidance") + t["perceived_support"]
                              + t["learned"] + t["_base"] + t["no_one_close"])
        t = T["active"]
        U[:, S["active"]] = t["conscientiousness"] + t["controllable"] + t["_base"] + t["learned"] + t["self_efficacy"]
        t = T["religious"]
        U[:, S["religious"]] = np.where(cares_faith, t["_base"] + t["faith"] + t["learned"], -9)
        t = T["distraction"]
        U[:, S["distraction"]] = t["sensation"] + t["cares_health"] + t["cares_fun"] + t["_base"] + t["learned"]
        t = T["withdrawal"]
        U[:, S["withdrawal"]] = (t["neuroticism"] + t["social_anxiety"] + t["avoidance"] - 1.0 * (P["expect_social"][ids] - 0.6)
                                 + t["_base"] + t["learned"])
        g = sim.streams.gen("coping_choice", w.day).gumbel(size=(P.n, len(STRATEGIES)))[ids]
        choice = np.argmax(U + g, axis=1).astype(np.uint8)
        P.cols["coping_strategy"][ids] = choice
        P.internal["cope_start"][ids] = w.day
        P.internal["cope_need0"][ids] = need[ids]
        P.internal["cope_stressor"][ids] = stressor
        P.internal["cope_low_days"][ids] = 0
        did = self._record_choice(ids, choice, T, U, cares_faith)
        cause = self._recent_cause(ids)
        ev = sim.emit("coping_started", ids, value=choice.astype(float), cause=cause, mech="coping.choice", decision=did)
        self._why_strained(ev, ids, stressor)
        P.internal["cope_event"][ids] = ev

    def _end(self, ids: np.ndarray, need: np.ndarray):
        sim, w = self.sim, self.sim.w
        P, p = w.P, sim.p
        strat = P["coping_strategy"][ids].astype(int)
        n0 = P.internal["cope_need0"][ids]
        # outcome: how much the strain fell, credited to the strategy (relief felt along the way counts too)
        outcome = np.clip(0.5 + 0.8 * (n0 - need[ids]) + 0.6 * (P["coping_relief"][ids] - 0.15), 0, 1)
        a = p("coping.learning.alpha")
        for k, s in enumerate(STRATEGIES[1:], start=1):
            m = strat == k
            if m.any():
                col = P.internal[f"cope_v_{s}"]
                col[ids[m]] = col[ids[m]] + a * (outcome[m] - col[ids[m]])
        eased = P.internal["cope_low_days"][ids] >= 3
        P.cols["coping_strategy"][ids] = 0
        P.internal["cope_start"][ids] = -1
        cause = P.internal["cope_event"][ids]
        ev = sim.emit("coping_ended", ids, value=outcome, cause=cause, mech="coping.learning", ev={"quality": 2 * outcome - 1})
        # how it ended: the strain eased for a few days, or a month went by without it easing (or they left)
        relief = state_ref(sim, "coping_relief", ids)
        link(sim, ev[eased], "state", relief[eased], P["coping_relief"][ids][eased], "resolved")
        link(sim, ev[~eased], "state", relief[~eased], P["coping_relief"][ids][~eased], "timed_out")

    def _relief(self, strat: np.ndarray, need: np.ndarray) -> np.ndarray:
        """Relief each strategy brought today (0-1), from what actually happened."""
        P, p = self.sim.w.P, self.sim.p
        n = P.n
        r = np.zeros(n, np.float32)
        contacted = P.internal["contacted_today"][:n] | (P.internal["close_hours_today"][:n] > 0.5)
        m = strat == S["support"]
        r[m] = p("coping.relief.support") * (0.2 + 0.8 * P["support_actual"][m]) * np.where(contacted[m], 1.0, 0.3)
        m = strat == S["active"]
        stressor = P.internal["cope_stressor"][:n]
        progress = np.where(stressor == 0, 0.5 - P["academic_pressure"], np.where(stressor == 1, 0.5 - P["financial_stress"], 0.1))
        r[m] = p("coping.relief.active") * np.clip(0.3 + progress[m], 0, 1)
        m = strat == S["religious"]
        relig = np.where(P["lds_member"], P["faith_belief"], P["own_religiosity"])
        r[m] = p("coping.relief.religious") * np.clip(relig[m], 0, 1)
        m = strat == S["distraction"]
        did = ((P.internal["gym_week"][:n] > 1) | (P.internal["fun_week"][:n] > 2)) if "fun_week" in P.internal else np.zeros(n, bool)
        r[m] = p("coping.relief.distraction") * np.where(did[m], 1.0, 0.4)
        m = strat == S["withdrawal"]
        r[m] = p("coping.relief.withdrawal")
        return r

    # ------------------------------------------------------------------ behavior hooks
    def choice_bias(self, idx: np.ndarray) -> np.ndarray:
        """Utility shifts for free-time options (home, campus, gym, venue, outdoors, dance, visit, complex)."""
        P, p = self.sim.w.P, self.sim.p
        st = P["coping_strategy"][idx]
        B = np.zeros((len(idx), 8))
        k = p("coping.behavior.strength")
        stressor = P.internal["cope_stressor"][idx]
        B[st == S["support"], 6] += 0.9 * k
        B[st == S["withdrawal"], 0] += 0.9 * k
        B[st == S["withdrawal"], 6] -= 0.6 * k
        B[st == S["withdrawal"], 3] -= 0.4 * k
        dis = st == S["distraction"]
        B[dis, 2] += 0.7 * k
        B[dis, 4] += 0.6 * k
        B[dis, 3] += 0.4 * k
        B[(st == S["active"]) & (stressor == 0), 1] += 0.9 * k
        B[st == S["religious"], 0] += 0.2 * k
        return B

    def social_bias(self):
        """Extra pull toward people (support) or away from them (withdrawal), added to mind.social_pull."""
        P = self.sim.w.P
        st = P["coping_strategy"]
        k = self.sim.p("coping.behavior.strength")
        return 0.3 * k * (st == S["support"]), 0.4 * k * (st == S["withdrawal"])

    def contact_mult(self) -> np.ndarray:
        P = self.sim.w.P
        st = P["coping_strategy"]
        k = self.sim.p("coping.behavior.strength")
        return np.where(st == S["support"], 1 + 1.2 * k, np.where(st == S["withdrawal"], 1 / (1 + 0.8 * k), 1.0))

    def study_bias(self) -> np.ndarray:
        P = self.sim.w.P
        st = P["coping_strategy"]
        stressor = P.internal["cope_stressor"][: P.n]
        return np.where((st == S["active"]) & (stressor == 0), 3.0, 0.0) - np.where(st == S["withdrawal"], 2.0, 0.0)

    def attend_bias(self) -> np.ndarray:
        """Class attendance logit shift (withdrawal skips class)."""
        P = self.sim.w.P
        return np.where(P["coping_strategy"] == S["withdrawal"], -0.6, 0.0)

    def church_bias(self) -> np.ndarray:
        P = self.sim.w.P
        return np.where(P["coping_strategy"] == S["religious"], 0.6, 0.0)

    def money_coping(self) -> np.ndarray:
        """People actively coping with money strain look for work / more hours."""
        P = self.sim.w.P
        return (P["coping_strategy"] == S["active"]) & (P.internal["cope_stressor"][: P.n] == 1)

    def supported(self, src: np.ndarray, dst: np.ndarray, eix: np.ndarray):
        """Friend contact by a support-seeker: confiding deepens the tie and is remembered as support."""
        w = self.sim.w
        P, E = w.P, w.E
        seek = P["coping_strategy"][src] == S["support"]
        P.internal["contacted_today"][src] = True
        if seek.any():
            e = eix[seek]
            resp = np.clip(E["liking"][e], 0, 1) * (0.5 + 0.5 * E["closeness"][e])
            E.cols["support"][e] = np.minimum(E["support"][e] + 0.15 * resp, 5)
            E.cols["disclosure"][e] = np.clip(E["disclosure"][e] + 0.08 * resp * (1 - E["disclosure"][e]), 0, 1)

    # ------------------------------------------------------------------ provenance helpers
    def _record_choice(self, ids, choice, T, U, cares_faith) -> np.ndarray:
        """The chosen strategy's utility terms (what pulled toward it) and its choice probability (Gumbel-max ⇒
        softmax over the five strategies)."""
        sim = self.sim
        k = len(ids)
        names = sorted({f for t in T.values() for f in t if f != "_base"} | {"not_religious"})
        F = {f: np.zeros(k) for f in names}
        base = np.zeros(k)
        for s, terms in T.items():
            sel = choice == S[s]
            if not sel.any():
                continue
            for f, v in terms.items():
                vv = np.broadcast_to(np.asarray(v, np.float64), (k,))[sel]
                if f == "_base":
                    base[sel] = vv
                else:
                    F[f][sel] = vv
        return sim.decisions.record("coping_strategy", sim.w.day, ids, choice.astype(np.int64) - 1, F, base=base,
                                    prob=softmax_prob(U[:, 1:], choice.astype(np.int64) - 1))

    def _why_strained(self, ev: np.ndarray, ids: np.ndarray, stressor: np.ndarray):
        """What the strain was: the coping need is a sum of four parts (stress, low mood, loneliness, anxiety past
        their thresholds), linked as `state` causes with their share; plus the concern it was mostly about."""
        sim, P, p = self.sim, self.sim.w.P, self.sim.p
        parts = (("stress", 0.6 * np.clip(P["stress"][ids] - p("coping.need.stress"), 0, None)),
                 ("mood", 0.8 * np.clip(p("coping.need.mood") - P["mood"][ids], 0, None)),
                 ("loneliness", 0.5 * np.clip(P["loneliness"][ids] - p("coping.need.loneliness"), 0, None)),
                 ("anxiety", 0.4 * np.clip(P["anxiety"][ids] - 0.55, 0, None)))
        tot = np.maximum(sum(v for _, v in parts), 1e-9)
        for var, v in parts:
            m = v > 0
            link(sim, ev[m], "state", state_ref(sim, var, ids[m]), v[m] / tot[m], "strain")
        svar = np.array(["academic_pressure", "financial_stress", "romantic_longing", "loneliness", "guilt", "stress"])
        for k, var in enumerate(svar[:5]):
            m = stressor == k
            link(sim, ev[m], "state", state_ref(sim, str(var), ids[m]), 1.0, "stressor")

    def _recent_cause(self, ids: np.ndarray) -> np.ndarray:
        """The most salient negative event each person had in the last three weeks (the likely trigger)."""
        sim = self.sim
        mem = sim.memory
        out = np.full(len(ids), -1, np.int64)
        if mem.n == 0:
            return out
        day = sim.w.day
        sel = (mem["day"] >= day - 21) & (mem["valence"].astype(np.float32) < -0.1) & np.isin(mem["agent"], ids)
        rows = np.where(sel)[0]
        if len(rows) == 0:
            return out
        score = mem["importance"][rows].astype(np.float32) * -mem["valence"][rows].astype(np.float32)
        order = np.lexsort((-score, mem["agent"][rows]))
        r = rows[order]
        ag = mem["agent"][r]
        first = np.r_[True, ag[1:] != ag[:-1]]
        best = dict(zip(ag[first].tolist(), mem["event"][r[first]].tolist()))
        return np.array([best.get(int(i), -1) for i in ids], np.int64)
