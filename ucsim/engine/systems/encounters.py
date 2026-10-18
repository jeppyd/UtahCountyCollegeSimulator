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

from .. import clock
from ..core import pair_normal
from ..provenance import link, note_time, place_ref
from ..state import CTX, CTX_ID, EdgeStore, Tie
from .activity import NONE

# hours a conversation lasts by context; at an occasion it is 1 x the kind's talk_h (occasions.talk_hours)
DURATION = {"unit": 0.9, "complex": 0.25, "class": 0.15, "ward": 0.3, "fhe": 0.8, "work": 0.4, "gym": 0.15,
            "venue": 0.35, "gathering": 1.4, "campus": 0.2, "dance": 0.4, "outdoors": 0.5, "hangout": 1.6, "online": 0.3,
            "club": 0.5, "team": 0.6, "institute": 0.35, "congregation": 0.35, "occasion": 1.0}
LEISURE_W = {"unit": 1.0, "complex": 0.8, "class": 0.3, "ward": 0.6, "fhe": 0.9, "work": 0.35, "gym": 0.5,
             "venue": 1.0, "gathering": 1.0, "campus": 0.45, "dance": 1.0, "outdoors": 1.0, "hangout": 1.0, "online": 0.5,
             "club": 0.85, "team": 0.95, "institute": 0.6, "congregation": 0.6, "occasion": 1.0}
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


SHARED = ("gathering", "hangout", "team", "club", "outdoors", "dance", "fhe", "date", "institute", "occasion")


class Encounters:
    def __init__(self, sim):
        self.sim = sim
        n_ctx = len(CTX)
        self.shared_ctx = np.zeros(n_ctx, bool)
        for k in SHARED:
            self.shared_ctx[CTX_ID[k]] = True
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
        """Interactions among co-present people in block b. Attempt rates are per old (five-hour) block: ambient time
        is scaled by its share of the block (activity.ctx_share: a whole evening at home adds up to one old evening);
        at an occasion the rate is the get-together rate x the kind's rate x the share of the occasion in this block."""
        sim, w = self.sim, self.sim.w
        P, E, p = w.P, w.E, sim.p
        act = sim.systems["activity"]
        occs = sim.systems["occasions"]
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
        at_occ = ct == CTX_ID["occasion"]
        if at_occ.any():
            rate[at_occ] = p("encounter.rate.gathering") * occs.rate_mult(cid[idx[at_occ]])
        share = act.ctx_share[idx] if len(act.ctx_share) == len(ctype) else clock.LEGACY_SHARE[b]
        rate = rate * share
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
        occ_pair = ctx == CTX_ID["occasion"]
        new_at_occ = occ_pair & (E.find(EdgeStore.make_keys(a, bb)) < 0) if occ_pair.any() else occ_pair
        self.apply(a, bb, ctx, cplace, b, sim_[rows, best][ok], gflag)
        if new_at_occ.any():
            # met at someone's occasion: the organizer introduced them (first meetings only)
            lo_, hi_, place_ = a[new_at_occ], bb[new_at_occ], cplace[new_at_occ]
            org = occs.organizer_of(place_)
            intro = (org >= 0) & (org != lo_) & (org != hi_)
            if intro.any():
                eix = E.find(EdgeStore.make_keys(lo_[intro], hi_[intro]))
                fresh = (eix >= 0) & (E["introducer"][np.maximum(eix, 0)] < 0)
                E.cols["introducer"][eix[fresh]] = org[intro][fresh]
                E.cols["flags"][eix[fresh]] |= Tie.INTRODUCED
        if b in clock.EVENING:
            social = gflag | (ctx == CTX_ID["dance"])
            if occ_pair.any():
                social = social | (occ_pair & occs.ncmo_ok(np.where(occ_pair, cplace, 0)))
            pairs = (a[social], bb[social])
            prev = self.evening_social_pairs if b != clock.EVENING[0] else None
            self.evening_social_pairs = pairs if prev is None else (np.r_[prev[0], pairs[0]], np.r_[prev[1], pairs[1]])
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
        lam = (p("encounter.friend_contact.rate") * np.exp(0.25 * sim.z("extraversion") + 0.6 * appr) * np.where(married, 0.6, 1.0)
               * sim.systems["coping"].contact_mult())
        rng = sim.streams.gen("friend_contact", w.day)
        k = np.where(P["present"] & (deg > 0), rng.poisson(lam), 0)
        src = np.repeat(np.arange(n), k)
        if len(src) == 0:
            return
        d = deg[src]
        o1 = (rng.random(len(src)) * d).astype(np.int64)
        o2 = (rng.random(len(src)) * d).astype(np.int64)
        # look edges up by key: the weekly adjacency's edge indices go stale as new ties are inserted mid-week
        c1 = self._closeness(src, nbr[indptr[src] + o1])
        c2 = self._closeness(src, nbr[indptr[src] + o2])
        pick2 = c2 > c1
        off = np.where(pick2, o2, o1)
        plans = sim.systems.get("plans")
        if plans is not None:
            off = plans.reconnect_pick(src, off, indptr, nbr, rng)
        dst = nbr[indptr[src] + off]
        chosen = E.find(EdgeStore.make_keys(src, dst))
        ok = P["present"][dst] & (dst != src) & (chosen >= 0)
        src, dst, chosen = src[ok], dst[ok], chosen[ok]
        sim.systems["coping"].supported(src, dst, chosen)
        if plans is not None:
            plans.contacted(src, dst)
        dist = np.hypot((P["home_lon"][src] - P["home_lon"][dst]) * 85, (P["home_lat"][src] - P["home_lat"][dst]) * 111)
        in_person = rng.random(len(src)) < np.where(dist < 4, 0.6, 0.2)
        # an unrepaired hurt makes people less likely to follow through on seeing each other
        hurt = E["hurt"][chosen]
        go = rng.random(len(src)) >= 0.6 * hurt
        src, dst, in_person = src[go], dst[go], in_person[go]
        ctx = np.where(in_person, CTX_ID["hangout"], CTX_ID["online"]).astype(np.uint8)
        self.apply(src, dst, ctx, np.full(len(src), -1, np.int64), 2, self.similarity(src, dst), np.zeros(len(src), bool))
        self._introductions(src[in_person], dst[in_person], rng)

    def _introductions(self, src: np.ndarray, dst: np.ndarray, rng):
        """Friends bring friends: some in-person hangouts include a friend of the friend, closing triads
        (Rapoport 1953; Kossinets & Watts 2006; RSiena's transitivity effect)."""
        sim, w = self.sim, self.sim.w
        P, E, p = w.P, w.E, sim.p
        if len(src) == 0:
            return
        net = sim.systems["network"]
        indptr, nbr, _ = net.padded()
        bring = rng.random(len(src)) < p("relationship.introductions.rate")
        s, d = src[bring], dst[bring]
        deg = indptr[d + 1] - indptr[d]
        ok = deg > 1
        s, d, deg = s[ok], d[ok], deg[ok]
        if len(s) == 0:
            return
        f = nbr[indptr[d] + (rng.random(len(d)) * deg).astype(np.int64)]
        ok = (f != s) & P["present"][f]
        s, d, f = s[ok], d[ok], f[ok]
        if len(s) == 0:
            return
        keys = EdgeStore.make_keys(s, f)
        new = E.find(keys) < 0
        self.apply(s, f, np.full(len(s), CTX_ID["hangout"], np.uint8), np.full(len(s), -1, np.int64), 2,
                   self.similarity(s, f), np.zeros(len(s), bool))
        if new.any():
            eix = E.find(keys[new])
            E.cols["introducer"][eix] = d[new]
            E.cols["flags"][eix] |= Tie.INTRODUCED

    def _closeness(self, a: np.ndarray, b: np.ndarray) -> np.ndarray:
        E = self.sim.w.E
        e = E.find(EdgeStore.make_keys(a, b))
        return np.where(e >= 0, E["closeness"][np.maximum(e, 0)], 0.0)

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
        # where each conversation happened, as ties remember it: a hosted get-together counts as a gathering
        ctx_eff = np.where(gath, CTX_ID["gathering"], ctx).astype(np.int64)
        occ_code = CTX_ID["occasion"]
        ni = jj = None
        # ---- initialize brand-new edges
        if new_before.any():
            # where they met: the first record of each new edge
            rec_new = np.flatnonzero(new_before)
            ni, first = np.unique(idx[rec_new], return_index=True)
            jj = rec_new[first]
            lo, hi = E.split(E.key_array[ni])
            E.cols["first_day"][ni] = day
            E.cols["chemistry"][ni] = pair_normal(w.seed, lo, hi, 11)
            E.cols["origin_ctx"][ni] = ctx_eff[jj]
            E.cols["origin_place"][ni] = place[jj]
            # who brought them together: the host of a get-together, the organizer of an occasion
            intro_by = np.full(len(ni), -1, np.int64)
            hosts_map = getattr(sim.systems["activity"], "host_of_unit", None)
            if gath.any() and hosts_map:
                hu = np.fromiter(hosts_map.keys(), np.int64, len(hosts_map))
                hv = np.fromiter(hosts_map.values(), np.int64, len(hosts_map))
                o = np.argsort(hu)
                hu, hv = hu[o], hv[o]
                k = np.clip(np.searchsorted(hu, place[jj]), 0, len(hu) - 1)
                intro_by = np.where(gath[jj] & (hu[k] == place[jj]), hv[k], intro_by)
            at_occ = ctx[jj] == occ_code
            if at_occ.any() and len(sim.book.occ):
                intro_by[at_occ] = sim.book.occ.get("organizer", place[jj][at_occ], default=-1)
            intro = (intro_by >= 0) & (intro_by != lo) & (intro_by != hi)
            E.cols["introducer"][ni[intro]] = intro_by[intro]
            E.cols["flags"][ni[intro]] |= Tie.INTRODUCED
            rom = sim.systems["romance"]
            att_lh, att_hl = rom.initial_attraction(lo, hi), rom.initial_attraction(hi, lo)
            E.cols["att_lh"][ni] = att_lh
            E.cols["att_hl"][ni] = att_hl
            sim.systems["mind"].init_beliefs(ni, lo, hi)
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
        at_occ = ctx == CTX_ID["occasion"]
        if at_occ.any():    # how long people talk at an occasion depends on the kind (a dinner vs a dance floor)
            dur[at_occ] *= sim.systems["occasions"].talk_hours(place[at_occ])
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
        # where their time together goes (per tie and kind of place; bookkeeping for tracing)
        slot = idx * 256 + ctx_eff
        su, sinv = np.unique(slot, return_inverse=True)
        last_rec = np.zeros(len(su), np.int64)
        np.maximum.at(last_rec, sinv, np.arange(len(slot)))
        note_time(E, su // 256, su % 256, place[last_rec], np.bincount(sinv, weights=dur))
        E.cols["hours_leisure"][uniq] += lhrs
        E.cols["n_inter"][uniq] += cnt.astype(np.int32)
        E.cols["last_day"][uniq] = day
        E.cols["stage"][uniq] = np.maximum(E["stage"][uniq], 1)
        neg = np.bincount(inv, weights=np.clip(-v, 0, None))
        E.cols["conflict"][uniq] = np.clip(E["conflict"][uniq] * 0.97 + 0.08 * neg, 0, 1)
        # relationship history: experiences shared (a party, a team, a hike) and confiding between people who are close
        shared_now = np.bincount(inv, weights=(self.shared_ctx[ctx] | gath).astype(float)) > 0
        E.cols["shared"][uniq[shared_now]] = np.minimum(E["shared"][uniq[shared_now]] + 1, 30000)
        warm = (vmean > 0) & (E["stage"][uniq] >= 2)
        if warm.any():
            ue = uniq[warm]
            d = E["disclosure"][ue]
            E.cols["disclosure"][ue] = np.clip(d + p("relationship.disclosure.rate") * np.tanh(vmean[warm]) * E["closeness"][ue] * (1 - d), 0, 1)
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
        # only people who could act on it (single or talking) need a running read of the other's interest
        seek = rom.seeking_mask()
        either = (comp_ab | comp_ba) & (seek[a] | seek[b])
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
        # ---- salient conflicts leave a hurt that must be repaired
        bad = (v < -1.9) & (E["stage"][idx] >= 2)
        if bad.any():
            ev = sim.emit("conflict", a[bad], b=b[bad], value=v[bad], block=block, mech="encounter.valence")
            E.cols["hurt"][idx[bad]] = np.clip(E["hurt"][idx[bad]] + p("relationship.hurt.conflict"), 0, 1)
            link(sim, ev, "tie", keys[bad], 1.0, "the_tie")
            cb, pb = ctx[bad], place[bad]
            at = cb == occ_code
            link(sim, ev[at], "occasion", pb[at], 1.0, "scene")
            link(sim, ev[~at], "place", place_ref(ctx_eff[bad][~at], pb[~at]), 1.0, "scene")
        # ---- what happened at occasions (the scene): conversations, first meetings, falling-outs
        at = ctx == occ_code
        if at.any():
            oid, n_talk = np.unique(place[at], return_counts=True)
            n_new = np.zeros(len(oid), np.int64)
            if ni is not None:
                met = ctx[jj] == occ_code
                if met.any():
                    np.add.at(n_new, np.searchsorted(oid, place[jj][met]), 1)
            n_bad = np.zeros(len(oid), np.int64)
            if (bad & at).any():
                np.add.at(n_bad, np.searchsorted(oid, place[bad & at]), 1)
            sim.book.note_scene(oid, talks=n_talk, new_ties=n_new, conflicts=n_bad)
