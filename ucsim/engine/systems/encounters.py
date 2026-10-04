"""Encounters: co-presence → interactions → relationship state.

Opportunity precedes compatibility.  People only interact with others who share a
context (unit, class section, ward, FHE group, workplace, venue, gathering, campus…).
Within a context each person initiates a Poisson number of interactions; partners are
chosen among a few randomly encountered co-present people, favouring the familiar
(repeated exposure), the liked, the similar (homophily) and — for single people — the
romantically attractive.  Interaction valence depends on pair chemistry (persistent,
pair-specific), personalities, moods and similarity; repeated positive interactions
accumulate into liking, closeness and eventually friendship (network system).
"""
from __future__ import annotations

import numpy as np

from ..core import pair_normal
from ..state import CTX, CTX_ID, EdgeStore, Tie
from .activity import NONE

DURATION = {"unit": 0.9, "complex": 0.25, "class": 0.15, "ward": 0.3, "fhe": 0.8, "work": 0.4, "gym": 0.15,
            "venue": 0.35, "gathering": 1.4, "campus": 0.2, "dance": 0.4, "outdoors": 0.5, "hangout": 1.6, "online": 0.3,
            "club": 0.5, "team": 0.6, "institute": 0.35, "congregation": 0.35}
LEISURE_W = {"unit": 1.0, "complex": 0.8, "class": 0.3, "ward": 0.6, "fhe": 0.9, "work": 0.35, "gym": 0.5,
             "venue": 1.0, "gathering": 1.0, "campus": 0.45, "dance": 1.0, "outdoors": 1.0, "hangout": 1.0, "online": 0.5,
             "club": 0.85, "team": 0.95, "institute": 0.6, "congregation": 0.6}
RATE_KEYS = ("unit", "complex", "class", "ward", "fhe", "work", "gym", "venue", "campus", "dance", "outdoors",
             "club", "team", "institute", "congregation")
TIE_OF = {"class": Tie.CLASSMATE, "work": Tie.COWORKER, "ward": Tie.WARD, "fhe": Tie.FHE, "complex": Tie.NEIGHBOR,
          "club": Tie.CLUBMATE, "team": Tie.TEAMMATE, "institute": Tie.INSTITUTE,
          "congregation": Tie.CONGREGATION}
C = 3  # candidates sampled per interaction attempt


def activation(n, first, last, day, d=0.5):
    """ACT-R base-level activation with Petrov's (2006) hybrid approximation (k=1)."""
    tn = np.maximum(day - last, 0) + 0.5
    L = np.maximum(day - first, 0) + 1.0
    n = np.maximum(n, 1)
    rest = np.where(L > tn + 1e-6, (n - 1) / (1 - d) * (L ** (1 - d) - tn ** (1 - d)) / (L - tn + 1e-9), 0.0)
    return np.log(tn ** (-d) + np.maximum(rest, 0))


class Encounters:
    def __init__(self, sim):
        self.sim = sim
        n_ctx = len(CTX)
        self.dur = np.zeros(n_ctx, np.float32)
        self.leisure = np.zeros(n_ctx, np.float32)
        for k, v in DURATION.items():
            if k in CTX_ID:
                self.dur[CTX_ID[k]] = v
        for k, v in LEISURE_W.items():
            if k in CTX_ID:
                self.leisure[CTX_ID[k]] = v

    def init(self):
        self.evening_social_pairs = None
        P = self.sim.w.P
        for c in ("hours_today", "close_hours_today"):
            P.add_internal(c, np.float32, 0.0)

    def rates(self) -> np.ndarray:
        p = self.sim.p
        r = np.zeros(len(CTX), np.float32)
        for k in RATE_KEYS:
            r[CTX_ID[k]] = p(f"encounter.rate.{k}")
        return r

    def run(self, b: int):
        sim, w = self.sim, self.sim.w
        P, E, p = w.P, w.E, sim.p
        act = sim.systems["activity"]
        ctype, cid = act.ctype, act.cid
        day = w.day
        valid = (ctype != NONE) & (cid >= 0) & (ctype != CTX_ID["date"])
        idx = np.where(valid)[0]
        if len(idx) < 2:
            return
        key = (ctype[idx].astype(np.int64) << 40) | cid[idx]
        order = np.argsort(key, kind="stable")
        idx, key = idx[order], key[order]
        starts = np.flatnonzero(np.r_[True, key[1:] != key[:-1]])
        sizes = np.diff(np.r_[starts, len(key)])
        gid = np.repeat(np.arange(len(starts)), sizes)
        gsize, gstart = sizes[gid], starts[gid]
        ct = ctype[idx]
        # gathering boost: the hosted unit becomes a lively context
        is_gath = np.zeros(len(idx), bool)
        if act.gathering_units:
            gu = np.fromiter(act.gathering_units, dtype=np.int64)
            is_gath = (ct == CTX_ID["unit"]) & np.isin(cid[idx], gu)
        rate = self.rates()[ct]
        rate = np.where(is_gath, p("encounter.rate.gathering"), rate)
        appr, _, _ = act._drives()
        soc = np.exp(p("encounter.sociability.extraversion") * sim.z("extraversion")[idx]
                     - p("encounter.sociability.social_anxiety") * np.clip(sim.z("social_anxiety")[idx], 0, None)
                     + 0.4 * appr[idx]) * (1 - 0.5 * P["fatigue"][idx])
        lam = np.where(gsize >= 2, rate * soc, 0.0)
        rng = sim.streams.gen("encounter", day, b)
        att = rng.poisson(lam)
        src_pos = np.repeat(np.arange(len(idx)), att)
        if len(src_pos) == 0:
            return
        r = rng.random((len(src_pos), C))
        cand_pos = gstart[src_pos][:, None] + (r * gsize[src_pos][:, None]).astype(np.int64)
        src = idx[src_pos]
        cand = idx[cand_pos]
        bad = cand == src[:, None]
        k_flat = EdgeStore.make_keys(np.repeat(src, C), cand.ravel())
        eix = E.find(k_flat).reshape(-1, C)
        has = eix >= 0
        e_safe = np.where(has, eix, 0)
        fam = np.where(has, activation(E["n_inter"][e_safe], E["first_day"][e_safe], E["last_day"][e_safe], day), -3.0)
        lik = np.where(has, E["liking"][e_safe], 0.0)
        sim_ = self.similarity(np.repeat(src, C), cand.ravel()).reshape(-1, C)
        rom = sim.systems["romance"]
        seeking = rom.seeking_mask()
        attr = np.zeros_like(lik)
        if has.any():
            a_dir = E.attraction_from(e_safe.ravel(), np.repeat(src, C)).reshape(-1, C)
            attr = np.where(has & seeking[src][:, None], np.clip(a_dir, 0, None), 0.0)
        score = (p("encounter.choice.familiarity") / (1 + np.exp(-(fam + 1)))
                 + p("encounter.choice.liking") * lik + p("encounter.choice.similarity") * sim_
                 + p("encounter.choice.attraction") * attr + rng.gumbel(size=lik.shape))
        score[bad] = -np.inf
        best = np.argmax(score, axis=1)
        rows = np.arange(len(src))
        ok = ~bad[rows, best]
        a = src[ok]
        bb = cand[rows, best][ok]
        ctx = ct[src_pos][ok]
        cplace = cid[a]
        gflag = is_gath[src_pos][ok]
        self.apply(a, bb, ctx, cplace, b, sim_[rows, best][ok], gflag)
        if b == 2:
            social = gflag | (ctx == CTX_ID["dance"])
            self.evening_social_pairs = (a[social], bb[social])
        elif b == 0:
            self.evening_social_pairs = None

    def friend_contact(self):
        """Deliberate contact with existing friends (plans, meals, calls, texts).

        Friendships are maintained by choice, not only by chance co-presence: each day people
        reach out to friends at a rate rising with extraversion and with loneliness among
        approach-oriented people; the friend is chosen by closeness. Nearby friends are
        usually seen in person, distant ones mostly contacted remotely."""
        sim, w = self.sim, self.sim.w
        P, E, p = w.P, w.E, sim.p
        net = sim.systems["network"]
        if not hasattr(net, "adj_close"):
            return
        indptr, nbr, eidx = net.padded(net.adj_close)
        n = P.n
        deg = np.diff(indptr)[:n]
        act = sim.systems["activity"]
        appr, _, _ = act._drives()
        married = P.is_("rel_status", "married")
        lam = p("encounter.friend_contact.rate") * np.exp(0.25 * sim.z("extraversion") + 0.6 * appr) * np.where(married, 0.6, 1.0)
        rng = sim.streams.gen("friend_contact", w.day)
        k = np.where(P["present"] & (deg > 0), rng.poisson(lam), 0)
        src = np.repeat(np.arange(n), k)
        if len(src) == 0:
            return
        d = deg[src]
        o1 = (rng.random(len(src)) * d).astype(np.int64)
        o2 = (rng.random(len(src)) * d).astype(np.int64)
        e1, e2 = eidx[indptr[src] + o1], eidx[indptr[src] + o2]
        pick2 = E["closeness"][e2] > E["closeness"][e1]
        off = np.where(pick2, o2, o1)
        dst = nbr[indptr[src] + off]
        ok = P["present"][dst] & (dst != src)
        src, dst = src[ok], dst[ok]
        dist = np.hypot((P["home_lon"][src] - P["home_lon"][dst]) * 85, (P["home_lat"][src] - P["home_lat"][dst]) * 111)
        in_person = rng.random(len(src)) < np.where(dist < 4, 0.6, 0.2)
        ctx = np.where(in_person, CTX_ID["hangout"], CTX_ID["online"]).astype(np.uint8)
        self.apply(src, dst, ctx, np.full(len(src), -1, np.int64), 2, self.similarity(src, dst), np.zeros(len(src), bool))

    def similarity(self, a: np.ndarray, b: np.ndarray) -> np.ndarray:
        P = self.sim.w.P
        s = -np.abs(P["age"][a] - P["age"][b]) / 4.0
        s += 0.35 * (P["school"][a] == P["school"][b])
        s += 0.3 * ((P["study_area"][a] == P["study_area"][b]) & P["enrolled"][a] & P["enrolled"][b])
        s += 0.35 * (P["activity"][a] == P["activity"][b])
        s -= 0.12 * np.abs(P["politics"][a].astype(np.int16) - P["politics"][b].astype(np.int16))
        s += 0.15 * (P["rel_status"][a] == P["rel_status"][b])
        s += 0.08 * ((P["hikes"][a] & P["hikes"][b]).astype(float) + (P["gaming"][a] & P["gaming"][b]) +
                     (P["sports"][a] & P["sports"][b]) + (P["music_maker"][a] & P["music_maker"][b]))
        s += 0.1 * (P["origin_region"][a] == P["origin_region"][b])
        return s.astype(np.float32)

    def apply(self, a, b, ctx, place, block, sim_, gath):
        sim, w = self.sim, self.sim.w
        P, E, p = w.P, w.E, sim.p
        day = w.day
        keys = EdgeStore.make_keys(a, b)
        new_before = E.find(keys) < 0
        idx = E.upsert(keys)
        # ---- initialize brand-new edges
        if new_before.any():
            ni = np.unique(idx[new_before])
            lo, hi = E.split(E.key_array[ni])
            E.cols["first_day"][ni] = day
            E.cols["chemistry"][ni] = pair_normal(w.seed, lo, hi, 11)
            # where they met (first record of each new edge)
            first_rec = {}
            for j in np.where(new_before)[0]:
                first_rec.setdefault(int(idx[j]), j)
            jj = np.array([first_rec[int(e)] for e in ni])
            ctx_names = np.array(CTX)[ctx[jj]]
            E.cols["origin_ctx"][ni] = np.where(gath[jj], CTX_ID["gathering"], ctx[jj])
            E.cols["origin_place"][ni] = place[jj]
            if gath.any():
                act = sim.systems["activity"]
                hosts = np.array([act.host_of_unit.get(int(u), -1) for u in place[jj]])
                intro = gath[jj] & (hosts >= 0) & (hosts != lo) & (hosts != hi)
                E.cols["introducer"][ni[intro]] = hosts[intro]
                E.cols["flags"][ni[intro]] |= Tie.INTRODUCED
            rom = sim.systems["romance"]
            att_lh, att_hl = rom.initial_attraction(lo, hi), rom.initial_attraction(hi, lo)
            E.cols["att_lh"][ni] = att_lh
            E.cols["att_hl"][ni] = att_hl
            sim.systems["mind"].init_beliefs(ni, lo, hi)
            del ctx_names
        # ---- interaction valence
        rng = sim.streams.gen("valence", day, block)
        chem = E["chemistry"][idx]
        mood = P["mood"]
        v = (p("encounter.valence.base") + p("encounter.valence.chemistry") * chem
             + p("encounter.valence.agreeableness") * (sim.z("agreeableness")[a] + sim.z("agreeableness")[b]) / 2
             + p("encounter.valence.social_skill") * (sim.z("social_skill")[a] + sim.z("social_skill")[b]) / 2
             + p("encounter.valence.mood") * (mood[a] + mood[b] - 1.0)
             + p("encounter.valence.similarity") * sim_
             + p("encounter.valence.liking") * E["liking"][idx]
             + p("encounter.valence.noise") * rng.standard_normal(len(a)))
        dur = self.dur[ctx] * np.where(gath, 1.6, 1.0) * rng.lognormal(0, 0.5, len(a))
        lw = np.where(gath, 1.0, self.leisure[ctx])
        # ---- aggregate duplicates per edge then update once
        uniq, inv = np.unique(idx, return_inverse=True)
        cnt = np.bincount(inv)
        vsum = np.bincount(inv, weights=v)
        vmean = vsum / cnt
        hrs = np.bincount(inv, weights=dur)
        lhrs = np.bincount(inv, weights=dur * lw)
        alpha = 1 - (1 - p("network.liking.learning_rate")) ** cnt
        E.cols["liking"][uniq] = np.clip(E["liking"][uniq] + alpha * (np.tanh(vmean) - E["liking"][uniq]), -1, 1)
        E.cols["hours"][uniq] += hrs
        E.cols["hours_leisure"][uniq] += lhrs
        E.cols["n_inter"][uniq] += cnt.astype(np.int32)
        E.cols["last_day"][uniq] = day
        E.cols["stage"][uniq] = np.maximum(E["stage"][uniq], 1)
        neg = np.bincount(inv, weights=np.clip(-v, 0, None))
        E.cols["conflict"][uniq] = np.clip(E["conflict"][uniq] * 0.97 + 0.08 * neg, 0, 1)
        E.cols["trust"][uniq] = np.clip(E["trust"][uniq] + 0.004 * np.clip(vsum, -3, 3) * (1 - E["trust"][uniq]), 0, 1)
        # tie-type flags from the context
        cflags = np.zeros(len(idx), np.uint32)
        for name, flag in TIE_OF.items():
            cflags[ctx == CTX_ID[name]] = flag
        same_home = (ctx == CTX_ID["unit"]) & (P["unit_id"][a] == P["unit_id"][b]) & (P["unit_id"][a] >= 0)
        cflags[same_home] |= Tie.ROOMMATE
        np.bitwise_or.at(E.cols["flags"], idx, cflags)
        # ---- romantic attraction drifts with interaction quality (compatible pairs only)
        rom = sim.systems["romance"]
        comp_ab = rom.compatible(a, b)
        comp_ba = rom.compatible(b, a)
        eta = p("romance.attraction.interaction_update")
        for src, dst, comp in ((a, b, comp_ab), (b, a, comp_ba)):
            if comp.any():
                ii = idx[comp]
                cur = E.attraction_from(ii, src[comp])
                E.set_attraction_from(ii, src[comp], np.clip(cur + eta * (v[comp] - 0.15), -1, 1))
        # ---- each interaction is also a noisy read of the other's interest (perceived, not actual)
        mind = sim.systems["mind"]
        either = comp_ab | comp_ba
        if either.any():
            mind.update_beliefs(idx[either], a[either], b[either], p("mind.romantic_perception.learning_rate"), block)
        mind.observe_interactions(a, b, ctx, v)
        # ---- social-contact accounting
        hours_today = P.internal["hours_today"]
        close_today = P.internal["close_hours_today"]
        np.add.at(hours_today, a, dur)
        np.add.at(hours_today, b, dur)
        close = (E["stage"][idx] >= 3) | ((E["flags"][idx] & (Tie.ROMANTIC | Tie.SPOUSE)) > 0) | (same_home & (E["liking"][idx] > 0.35))
        np.add.at(close_today, a[close], dur[close])
        np.add.at(close_today, b[close], dur[close])
        # ---- salient conflicts
        bad = (v < -1.9) & (E["stage"][idx] >= 2)
        if bad.any():
            sim.emit("conflict", a[bad], b=b[bad], value=v[bad], block=block, mech="encounter.valence")
