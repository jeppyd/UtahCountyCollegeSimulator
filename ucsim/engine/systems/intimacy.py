"""Physical intimacy in couples, crossing one's own line, bishops, married sex life and dating dealbreakers.

Design notes (parameters in config/mechanisms/14_intimacy.yaml, person variables in config/variables/11_intimacy.yaml)
* The ladder: kissing → touching → under clothes → naked → sex (intimacy_level 1..5; 0 = nothing yet). Each person
  has the stage at which each tier becomes acceptable to them (LDS Sexuality Survey, June 2025: on a date / committed /
  engaged / married). A couple's weekly chance of the next step rises with drive, time together and time alone, and
  falls sharply when the step goes past either partner's line (more so the more committed to chastity they are).
* Crossing one's own line raises guilt (appraisal scales it by chastity commitment and shame), sometimes leads to a
  bishop, and strains the relationship when only one partner's line was crossed. The top step for an unmarried
  couple is romance._sex (the old weekly premarital-sex hazard is bypassed while this system runs).
* Married couples sit at the top of the ladder; their sexual satisfaction (survey-drawn) relaxes with stress and
  feeds relationship satisfaction modestly.
* Dealbreakers: a partner's porn use, past porn problem, masturbation, sexual history or asexuality comes to light
  through the relationship (its disclosure, time, engagement, a crossed line); someone who holds that dealbreaker
  decides whether it ends things (decision dealbreaker_reaction) — through romance._end, never by editing it.
"""
from __future__ import annotations

import numpy as np
from scipy.special import expit

from ..provenance import link, mirror, pick, state_ref, total
from ..state import EdgeStore, Tie

TIERS = ("touch", "underclothes", "naked", "sex")
DEALBREAKERS = ("watches_porn", "past_porn", "masturbates", "not_virgin", "asexual")


class Intimacy:
    def __init__(self, sim):
        self.sim = sim

    def init(self):
        P = self.sim.w.P
        P.add_internal("db_known", np.uint8, 0)        # bits: which of the partner's dealbreaker facts this person knows
        P.add_internal("db_partner", np.int32, -1)     # the partner those bits are about
        P.add_internal("sx_married", np.bool_, False)  # sexual satisfaction shown since marrying
        for c, f in (("sexsat_latent", 0.65), ("desire_gap_latent", 0.0)):
            if c not in P.internal:
                P.add_internal(c, np.float32, f)
        self._start_levels()

    # ------------------------------------------------------------------ helpers
    def stage_index(self, status: np.ndarray) -> np.ndarray:
        """talking → 0 (on a date), dating → 1 (committed), engaged → 2, married → 3; −1 otherwise."""
        P = self.sim.w.P
        out = np.full(len(status), -1, np.int8)
        for k, s in enumerate(("talking", "dating", "engaged", "married")):
            out[status == P.code("rel_status", s)] = k
        return out

    def allowed(self, x: np.ndarray, stage: np.ndarray) -> np.ndarray:
        """The highest ladder level person x thinks is acceptable at this stage (1 = kissing only … 5 = sex)."""
        P = self.sim.w.P
        ok = np.ones(len(x), np.int8)
        for t in TIERS:
            ok += (P[f"ok_stage_{t}"][x].astype(np.int8) <= stage)
        return ok

    def tier_stage(self, x: np.ndarray, tier: np.ndarray) -> np.ndarray:
        """The stage at which person x thinks ladder tier `tier` (0 touch … 3 sex) becomes acceptable."""
        P = self.sim.w.P
        st = np.column_stack([P[f"ok_stage_{t}"][x] for t in TIERS]).astype(np.int8)
        return st[np.arange(len(x)), tier]

    def _couples(self):
        w = self.sim.w
        P, E = w.P, w.E
        part = P["partner_id"]
        n = P.n
        ids = np.where((part >= 0) & (np.arange(n) < part) & P["present"])[0]
        j = part[ids].astype(np.int64)
        keys = EdgeStore.make_keys(ids, j)
        eix = E.upsert(keys)
        return ids, j, keys, eix

    def _start_levels(self):
        """Couples already together when the story begins: as far as both their limits allow at this stage (or
        further when they are already sexually active), married couples at the top."""
        P, E = self.sim.w.P, self.sim.w.E
        ids, j, keys, eix = self._couples()
        if not len(ids):
            return
        stage = self.stage_index(P["rel_status"][ids])
        lvl = np.minimum(self.allowed(ids, stage), self.allowed(j, stage))
        lvl = np.where(stage <= 0, np.minimum(lvl, 1), np.minimum(lvl, 4))   # sex itself happens on screen
        lvl = np.where((E["flags"][eix] & Tie.SEXUAL) > 0, 5, lvl)
        lvl = np.where(stage == 3, 5, np.where(stage < 0, 0, lvl)).astype(np.uint8)
        for x in (ids, j):
            P.cols["intimacy_level"][x] = lvl
        married = stage == 3
        for x in (ids[married], j[married]):
            P.internal["sx_married"][x] = True

    # ------------------------------------------------------------------ weekly
    def weekly(self):
        sim, w = self.sim, self.sim.w
        P = w.P
        single = P["partner_id"][: P.n] < 0
        P.cols["intimacy_level"][: P.n][single] = 0
        self._bishop_porn()

    def couples_week(self):
        """Each couple's week of physical intimacy and discovered dealbreakers, on the couple's own day."""
        ids, j, keys, eix = self._couples()
        turn = self.sim.my_turn(ids)
        ids, j, keys, eix = ids[turn], j[turn], keys[turn], eix[turn]
        self._married(ids, j, eix)
        if len(ids):
            crossed = self._steps(ids, j, keys, eix)
            self._dealbreakers(ids, j, keys, eix, crossed)

    def _married(self, ids, j, eix):
        sim, w = self.sim, self.sim.w
        P, p = w.P, sim.p
        unmarried = P["rel_status"][: P.n] != P.code("rel_status", "married")
        P.cols["sexual_satisfaction"][: P.n][unmarried] = 0.0
        P.cols["desire_gap"][: P.n][unmarried] = 0.0
        P.internal["sx_married"][: P.n][unmarried] = False
        if not len(ids):
            return
        m = P["rel_status"][ids] == P.code("rel_status", "married")
        a, b = ids[m], j[m]
        if not len(a):
            return
        for x in (a, b):
            P.cols["intimacy_level"][x] = 5
            new = ~P.internal["sx_married"][x]
            P.cols["sexual_satisfaction"][x[new]] = P.internal["sexsat_latent"][x[new]]
            P.cols["desire_gap"][x[new]] = P.internal["desire_gap_latent"][x[new]]
            P.internal["sx_married"][x] = True
            target = np.clip(P.internal["sexsat_latent"][x] - 0.1 * (P["stress"][x] - 0.3), 0, 1)
            P.cols["sexual_satisfaction"][x] = P["sexual_satisfaction"][x] + 0.25 * (target - P["sexual_satisfaction"][x])
        mean = (P["sexual_satisfaction"][a] + P["sexual_satisfaction"][b]) / 2
        bump = p("intimacy.married.weight") * (mean - 0.65)
        for x in (a, b):
            rs = P["relationship_satisfaction"][x]
            P.cols["relationship_satisfaction"][x] = np.where(np.isfinite(rs), np.clip(rs + bump, 0, 1), rs)

    def _steps(self, ids, j, keys, eix) -> np.ndarray:
        """One week of escalation for unmarried couples. Returns, per couple, whether a line was crossed."""
        sim, w = self.sim, self.sim.w
        P, E, p = w.P, w.E, sim.p
        day = w.day
        stage = self.stage_index(P["rel_status"][ids])
        crossed_any = np.zeros(len(ids), bool)
        unm = (stage >= 0) & (stage <= 2)
        lvl = np.minimum(P["intimacy_level"][ids], P["intimacy_level"][j]).astype(np.int8)
        kissed = (E["flags"][eix] & Tie.KISSED) > 0
        lvl = np.where(unm & (lvl == 0) & kissed, 1, lvl)
        lvl = np.where(unm & ((E["flags"][eix] & Tie.SEXUAL) > 0), 5, lvl)
        for x in (ids, j):
            P.cols["intimacy_level"][x] = np.where(unm, lvl, P["intimacy_level"][x])
        cand = unm & (lvl >= 1) & (lvl < 5)
        if not cand.any():
            return crossed_any
        c = np.flatnonzero(cand)
        a, b, ek, kk, st, lv = ids[c], j[c], eix[c], keys[c], stage[c], lvl[c]
        nxt = lv + 1
        ok_a = self.allowed(a, st) >= nxt
        ok_b = self.allowed(b, st) >= nxt
        months = np.maximum((day - P["rel_start_day"][a]) / 30.4, 0)
        drive = (P["sex_drive"][a].astype(float) + P["sex_drive"][b]) / 2
        # how far ahead of their own stage the step is (stages early), weighted by how committed to chastity they are
        tier = np.clip(nxt - 2, 0, 3)
        gap_a = np.clip(self.tier_stage(a, tier) - st, 0, 3)
        gap_b = np.clip(self.tier_stage(b, tier) - st, 0, 3)
        cross_cost = (gap_a * (0.2 + 1.2 * P["chastity_commitment"][a]) + gap_b * (0.2 + 1.2 * P["chastity_commitment"][b]))
        T = {"tier": p("intimacy.step.tier") * (lv - 1),
             "drive": p("intimacy.step.drive") * (drive - 2) / 2,
             "time_together": p("intimacy.step.months") * np.log1p(months),
             "alone_time": -p("intimacy.step.alone") * (P.is_("living", "contracted")[a] & P.is_("living", "contracted")[b]),
             "within_lines": np.where(ok_a & ok_b, p("intimacy.step.within"), -p("intimacy.step.cross") * cross_cost),
             "self_control": -0.5 * (sim.z("self_control")[a] + sim.z("self_control")[b]) / 2,
             "sensation": 0.4 * (sim.z("sensation_seeking")[a] + sim.z("sensation_seeking")[b]) / 2}
        base = p("intimacy.step.base")
        h = expit(total(base, T))
        u = sim.streams.uniform("intimacy_step", day, len(a))
        go = u < h
        # held back: the more permissive partner waits on the other's limits (a small, steady strain)
        held = ~go & (ok_a != ok_b) & (drive >= 2)
        E.cols["conflict"][ek[held]] = np.clip(E["conflict"][ek[held]] + p("intimacy.mismatch.held_back"), 0, 1)
        if not go.any():
            return crossed_any
        g = np.flatnonzero(go)
        a, b, ek, kk, nxt, ok_a, ok_b = a[g], b[g], ek[g], kk[g], nxt[g], ok_a[g], ok_b[g]
        did = sim.decisions.record("intimacy_step", day, a, "took_a_step", pick(T, g), base=base, prob=h[g], other=b)
        for x in (a, b):
            P.cols["intimacy_level"][x] = nxt.astype(np.uint8)
        top = nxt == 5
        step_ev = np.full(len(a), -1, np.int64)
        if (~top).any():
            s = ~top
            ev = sim.emit("intimacy_step", a[s], b=b[s], value=nxt[s].astype(float), cause=P.internal["rel_event"][a[s]],
                          mech="intimacy.step", decision=did[s], block=3)
            ev2 = sim.emit("intimacy_step", b[s], b=a[s], value=nxt[s].astype(float), cause=P.internal["rel_event"][a[s]],
                           mech="intimacy.step", block=3)
            mirror(sim, ev2, ev)
            link(sim, ev, "tie", kk[s], 1.0, "the_tie")
            step_ev[s] = ev
        if top.any():
            romance = sim.systems["romance"]
            step_ev[top] = romance._sex(a[top], b[top], ek[top], via_ladder=True, decision=did[top])
        # crossing one's own line
        one_sided = ok_a != ok_b
        E.cols["conflict"][ek[one_sided]] = np.clip(E["conflict"][ek[one_sided]] + p("intimacy.mismatch.crossed"), 0, 1)
        for x, y, ok in ((a, b, ok_a), (b, a, ok_b)):
            cr = ~ok
            if not cr.any():
                continue
            if (cr & ~top).any():          # the top step's guilt is premarital_sex's own (romance._sex)
                s = cr & ~top
                ev = sim.emit("crossed_own_line", x[s], b=y[s], value=nxt[s].astype(float), cause=step_ev[s],
                              mech="intimacy.step", block=3)
                link(sim, ev, "event", step_ev[s], 1.0, "crossed")
                lds = P["lds_member"][x[s]] & (P["chastity_commitment"][x[s]] > 0.35)
                pc = expit(p("intimacy.confession.base") + 2.0 * P["religious_identity"][x[s]] + 1.5 * P["guilt"][x[s]]
                           - 1.2 * P["moral_autonomy"][x[s]])
                conf = lds & (sim.u("intimacy_confess")[x[s]] < pc) & (P.internal["confess_day"][x[s]] < day)
                delay = (7 + 35 * sim.u("intimacy_confess_delay")[x[s]]).astype(int)
                who = x[s][conf]
                P.internal["confess_day"][who] = day + delay[conf]
                P.internal["rel_event"][who] = ev[conf]
        crossed_any[c[g]] = ~(ok_a & ok_b)
        return crossed_any

    # ------------------------------------------------------------------ dealbreakers
    def facts(self, x: np.ndarray, partner: np.ndarray, eix: np.ndarray) -> np.ndarray:
        """(len(x), 5) bool: what is true of x that the five dealbreakers name (x's partner is `partner`)."""
        w = self.sim.w
        P, E = w.P, w.E
        with_this_one = ((E["flags"][eix] & Tie.SEXUAL) > 0).astype(np.int16)
        return np.column_stack([
            P["porn_use"][x] >= 1,
            P["talked_to_bishop_sexual"][x] | (P["porn_use"][x] >= 2),
            P["masturbation"][x] >= 1,
            (P["n_sex_partners"][x] - with_this_one) > 0,
            P.is_("orientation", "asexual")[x],
        ])

    def _dealbreakers(self, ids, j, keys, eix, crossed):
        sim, w = self.sim, self.sim.w
        P, E, p = w.P, w.E, sim.p
        day = w.day
        stage = self.stage_index(P["rel_status"][ids])
        live = (stage >= 0) & (stage <= 2)                 # dating dealbreakers: not for married couples
        if not live.any():
            return
        c = np.flatnonzero(live)
        months = np.maximum((day - P["rel_start_day"][ids[c]]) / 30.4, 0)
        engaged = stage[c] == 2
        bits = 1 << np.arange(5, dtype=np.uint8)
        rng = sim.streams.gen("dealbreaker_reveal", day)
        ends_a, ends_b, recs, probs, found_ev = [], [], [], [], []
        for x, y in ((ids[c], j[c]), (j[c], ids[c])):
            stale = P.internal["db_partner"][x] != y
            P.internal["db_known"][x[stale]] = 0
            P.internal["db_partner"][x] = y
            known = (P.internal["db_known"][x][:, None] & bits[None, :]) > 0
            true = self.facts(y, x, eix[c])
            hold = np.column_stack([np.clip((P[f"db_{d}"][x].astype(float) - 2) / 2, 0, 1) for d in DEALBREAKERS])
            pr = expit(p("intimacy.reveal.base") + p("intimacy.reveal.disclosure") * E["disclosure"][eix[c]]
                       + p("intimacy.reveal.months") * np.log1p(months) + p("intimacy.reveal.engaged") * engaged
                       + p("intimacy.reveal.crossed") * crossed[c])
            new = true & ~known & (rng.random(true.shape) < pr[:, None])
            if not new.any():
                continue
            P.internal["db_known"][x] = P.internal["db_known"][x] | (new * bits[None, :]).sum(1).astype(np.uint8)
            s = np.where(new, hold, 0.0)
            worst = s.argmax(1)
            strength = s[np.arange(len(x)), worst]
            hit = strength > 0
            if not hit.any():
                continue
            r = np.flatnonzero(hit)
            xr, yr, er, kr = x[r], y[r], eix[c][r], keys[c][r]
            told = rng.random(len(r)) < np.clip(0.4 + 0.2 * sim.z("agreeableness")[yr] + 0.2 * sim.z("conscientiousness")[yr], 0.05, 0.95)
            fev = sim.emit("dealbreaker_found", xr, b=yr, value=worst[r].astype(float), cause=P.internal["rel_event"][xr],
                           mech="intimacy.reveal", block=3)
            link(sim, fev, "tie", kr, E["disclosure"][er], "brought_to_light")
            link(sim, fev, "person", np.where(told, yr, -1), 1.0, "brought_to_light")
            T = {"strength": p("intimacy.dealbreaker.strength") * strength[r],
                 "commitment": -p("intimacy.dealbreaker.commitment") * P["relationship_commitment"][xr],
                 "closeness": -p("intimacy.dealbreaker.closeness") * E["closeness"][er],
                 "time_together": -p("intimacy.dealbreaker.months") * np.log1p(months[r]),
                 "honesty": np.where(told, -p("intimacy.dealbreaker.honesty"), 0.5 * p("intimacy.dealbreaker.honesty"))}
            base = p("intimacy.dealbreaker.base")
            h = expit(total(base, T))
            end = rng.random(len(r)) < h
            stay = ~end
            if stay.any():
                did = sim.decisions.record("dealbreaker_reaction", day, xr[stay], "stayed", pick(T, stay), base=base,
                                           prob=1 - h[stay], other=yr[stay])
                ev = sim.emit("dealbreaker_overlooked", xr[stay], b=yr[stay], cause=fev[stay], mech="intimacy.dealbreaker",
                              decision=did, block=3)
                E.cols["conflict"][er[stay]] = np.clip(E["conflict"][er[stay]] + 0.1 * strength[r][stay], 0, 1)
                del ev
            if end.any():
                ends_a.append(xr[end])
                ends_b.append(yr[end])
                recs.append(pick(T, end))
                probs.append(h[end])
                found_ev.append(fev[end])
        if not ends_a:
            return
        a = np.concatenate(ends_a)
        b = np.concatenate(ends_b)
        fev = np.concatenate(found_ev)
        rec = {k: np.concatenate([np.broadcast_to(r_[k], len(e)) for r_, e in zip(recs, ends_a)]) for k in recs[0]}
        prob = np.concatenate(probs)
        # a couple can't end twice in one week (both may have found something out)
        key = EdgeStore.make_keys(a, b)
        _, first = np.unique(key, return_index=True)
        first = np.sort(first)
        a, b, fev, prob = a[first], b[first], fev[first], prob[first]
        rec = {k: v[first] for k, v in rec.items()}
        still = P["partner_id"][a] == b
        a, b, fev, prob = a[still], b[still], fev[still], prob[still]
        rec = {k: v[still] for k, v in rec.items()}
        if not len(a):
            return
        P.internal["rel_event"][a] = fev
        married = np.zeros(len(a), bool)
        sim.systems["romance"]._end(a, b, np.zeros(len(a)), np.ones(len(a)), married=married,
                                    why=[("event", fev, 1.0, "dealbreaker")],
                                    decide=("dealbreaker_reaction", rec, p("intimacy.dealbreaker.base"), prob))
        for x in (a, b):
            P.cols["intimacy_level"][x] = 0

    # ------------------------------------------------------------------ porn and bishops
    def _bishop_porn(self):
        sim, w = self.sim, self.sim.w
        P, p = w.P, sim.p
        n = P.n
        inst = sim.systems.get("institutions")
        seeing = inst.in_followup(n) if inst is not None else np.zeros(n, bool)   # already meeting monthly
        who = P["present"][:n] & P["lds_member"][:n] & (P["porn_use"][:n] >= 1) & ~seeing
        self._bishop_masturbation(inst, seeing)
        if not who.any():
            return
        x = np.flatnonzero(who)
        h = expit(p("intimacy.bishop_porn.base") + 2.0 * P["porn_incongruence"][x] + P["religious_identity"][x])
        go = sim.u("bishop_porn")[x] < h
        if not go.any():
            return
        x = x[go]
        if inst is not None:      # bishops make time for everyone who asks
            x = x[inst.bishop_gate(x, "porn")]
            if not len(x):
                return
        ev = sim.emit("bishop_porn_talk", x, mech="intimacy.bishop_porn")
        link(sim, ev, "state", state_ref(sim, "porn_incongruence", x), P["porn_incongruence"][x], "dissonance")
        P.cols["talked_to_bishop_sexual"][x] = True
        P.cols["bishop_meetings"][x] = np.minimum(P["bishop_meetings"][x] + 1, 10)
        if inst is not None:
            inst.counsel(x, "porn", ev)

    def _bishop_masturbation(self, inst, seeing: np.ndarray):
        """Members who masturbate (and don't use porn, whose talks cover both) sometimes raise it with their bishop."""
        sim, w = self.sim, self.sim.w
        P, p = w.P, sim.p
        n = P.n
        who = P["present"][:n] & P["lds_member"][:n] & (P["masturbation"][:n] >= 1) & (P["porn_use"][:n] == 0) & ~seeing
        if not who.any():
            return
        x = np.flatnonzero(who)
        h = expit(p("intimacy.bishop_masturbation.base") + 2.0 * P["sexual_shame"][x] + P["religious_identity"][x])
        x = x[sim.u("bishop_mast")[x] < h]
        if inst is not None and len(x):
            x = x[inst.bishop_gate(x, "masturbation")]
        if not len(x):
            return
        ev = sim.emit("bishop_masturbation_talk", x, mech="intimacy.bishop_masturbation")
        P.cols["talked_to_bishop_sexual"][x] = True
        P.cols["bishop_meetings"][x] = np.minimum(P["bishop_meetings"][x] + 1, 10)
        if inst is not None:
            inst.counsel(x, "masturbation", ev)
