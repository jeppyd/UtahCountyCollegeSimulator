"""Weekly network dynamics: tie stages, closeness, decay/forgetting, derived network metrics."""
from __future__ import annotations

import numpy as np

from ..provenance import latest_between, latest_event, link, tie_story_causes
from ..state import Tie
from .encounters import activation

# changes in a life that can pull friends apart (looked up as the context of a fading friendship)
LIFE_CHANGES = ("moved", "mission_departure", "mission_call", "left_area", "graduation", "dropout", "wedding", "engaged",
                "relationship_started", "job_found", "quit_job", "job_lost", "birth", "stopped_attending",
                "disaffiliated", "depressive_episode_start", "breakup_initiated", "breakup_received")


class Network:
    def __init__(self, sim):
        self.sim = sim
        self.adj = (np.zeros(1, np.int64), np.zeros(0, np.int64), np.zeros(0, np.int64))

    def init(self):
        P = self.sim.w.P
        P.add_internal("new_friend_days", np.int32, -10000)
        self.weekly(initial=True)

    def padded(self, adj=None):
        """CSR adjacency whose indptr covers every allocated agent (new arrivals have no ties yet)."""
        indptr, nbr, eidx = adj if adj is not None else self.adj
        n = self.sim.w.P.n
        if len(indptr) < n + 1:
            indptr = np.r_[indptr, np.full(n + 1 - len(indptr), indptr[-1])]
        return indptr, nbr, eidx

    def random_neighbor(self, ids: np.ndarray, u: np.ndarray, min_stage: int = 2) -> np.ndarray:
        indptr, nbr, _ = self.padded()
        deg = indptr[ids + 1] - indptr[ids]
        out = np.full(len(ids), -1, np.int64)
        ok = deg > 0
        off = (u[ok] * deg[ok]).astype(np.int64)
        out[ok] = nbr[indptr[ids[ok]] + off]
        return out

    def weekly(self, initial: bool = False):
        sim, w = self.sim, self.sim.w
        P, E, p = w.P, w.E, sim.p
        day = w.day
        n = E.n
        if n == 0:
            return
        lo, hi = E.endpoints()
        hrs = E["hours_leisure"]
        lik = E["liking"]
        stage = E["stage"].copy()
        k = p("network.stage.hours_scale")
        since = day - E["last_day"]
        flags = E["flags"]
        # closeness: grows toward a target set by recent leisure time & liking; decays without contact
        recent = np.clip((day - E["last_day"]) < 14, 0, 1)
        # closeness is built from time and liking, deepened by confiding and shared experiences, and held back
        # by unrepaired hurt (relationship.history)
        hurt = E["hurt"]
        target = np.clip(0.12 * np.log1p(hrs / 10) + 0.35 * np.clip(lik, 0, 1) + p("relationship.history.disclosure") * E["disclosure"]
                         + p("relationship.history.shared") * np.log1p(E["shared"]) - p("relationship.history.hurt") * hurt, 0, 1)
        clo = E["closeness"]
        grow = p("network.closeness.growth")
        decay = np.exp(-7.0 / p("network.closeness.decay_days"))
        newc = np.where(recent > 0, clo + grow * (target - clo), clo * decay)
        romantic = (flags & (Tie.ROMANTIC | Tie.SPOUSE | Tie.FAMILY)) > 0
        newc = np.where(romantic, np.maximum(newc, clo), newc)
        E.cols["closeness"][:n] = np.clip(newc, 0, 1)
        # repair: hurt heals with warm contact, slowly without it; confiding fades when people stop talking
        warm = recent & (lik > 0.1)
        E.cols["hurt"][:n] = (hurt * np.where(warm, 1 - p("relationship.hurt.repair"), 0.98)).astype(np.float32)
        E.cols["disclosure"][:n] = (E["disclosure"] * np.where(recent > 0, 1.0, 0.99)).astype(np.float32)
        # stage thresholds (Hall 2019: ~50 h casual friend, ~90 h friend, ~200 h close friend)
        fam = activation(E["n_inter"], E["first_day"], E["last_day"], day)
        up = np.ones(n, np.uint8)
        up[(hrs >= 0.55 * k * 50) & (lik > 0.1)] = 2
        up[(hrs >= 0.55 * k * 90) & (lik > 0.25) & (newc >= 0.3)] = 3
        up[(hrs >= 0.55 * k * 200) & (lik > 0.4) & (newc >= 0.5)] = 4
        # hysteresis: a tie keeps its stage until closeness/liking fall clearly below the entry thresholds
        keep4 = (newc >= 0.38) & (lik > 0.3)
        keep3 = (newc >= 0.2) & (lik > 0.15)
        keep2 = lik > 0.0
        down_ok = np.select([stage == 4, stage == 3, stage == 2], [keep4, keep3, keep2], True)
        new_stage = np.where(up > stage, up, np.where(down_ok, stage, np.maximum(stage.astype(np.int16) - 1, 1))).astype(np.uint8)
        new_stage = np.maximum(new_stage, np.minimum(stage, 1)).astype(np.uint8)
        new_stage = np.where(romantic, np.maximum(new_stage, 3), new_stage)
        E.cols["stage"][:n] = new_stage
        if not initial:
            up3 = (stage < 3) & (new_stage >= 3)
            up4 = (stage < 4) & (new_stage == 4)
            down = (stage == 4) & (new_stage < 4) & ~romantic
            pres = P["present"]
            if up3.any():
                m = np.flatnonzero(up3 & pres[lo] & pres[hi])
                ev = sim.emit("new_friend", lo[m], b=hi[m], block=2, mech="network.stage")
                sim.emit("new_friend", hi[m], b=lo[m], cause=ev, block=2, mech="network.stage")
                P.internal["new_friend_days"][lo[m]] = day
                P.internal["new_friend_days"][hi[m]] = day
                self._why_closer(ev, m, lo, hi)
                tie_story_causes(sim, ev, m)
            if up4.any():
                m = np.flatnonzero(up4 & pres[lo] & pres[hi])
                before = latest_between(sim, lo[m], hi[m], ("new_friend",), 0)
                ev = sim.emit("close_friend", lo[m], b=hi[m], cause=before, block=2, mech="network.stage")
                sim.emit("close_friend", hi[m], b=lo[m], cause=ev, block=2, mech="network.stage")
                self._why_closer(ev, m, lo, hi)
            if down.any():
                m = np.flatnonzero(down & pres[lo] & pres[hi])
                before = latest_between(sim, lo[m], hi[m], ("close_friend",), 0)
                ev = sim.emit("friendship_faded", lo[m], b=hi[m], cause=before, block=2, mech="network.closeness")
                self._why_apart(ev, m, lo, hi)
        # forgetting: drop weak, unflagged ties whose memory activation decayed
        keep_flags = Tie.ROMANTIC | Tie.SPOUSE | Tie.FAMILY | Tie.EX | Tie.DATED | Tie.KISSED | Tie.NCMO | Tie.SEXUAL
        forget = (new_stage <= 1) & (fam < p("network.forget.activation")) & ((flags & keep_flags) == 0)
        # acquaintances of people who have left the area for good are not tracked further (keeps long runs lean)
        gone = (~P["present"]) & (P["departure_day"] >= 0)
        forget |= (new_stage <= 2) & (gone[lo] | gone[hi]) & ((flags & keep_flags) == 0)
        if forget.any():
            E.remove(forget)
        # derived per-person metrics
        lo, hi = E.endpoints()
        st = E["stage"]
        nn = P.n
        P["n_friends"] = np.minimum(np.bincount(np.r_[lo[st >= 3], hi[st >= 3]], minlength=nn), 32000).astype(np.int16)
        P["n_close_friends"] = np.minimum(np.bincount(np.r_[lo[st >= 4], hi[st >= 4]], minlength=nn), 32000).astype(np.int16)
        P["n_acquaintances"] = np.minimum(np.bincount(np.r_[lo, hi], minlength=nn), 32000).astype(np.int16)
        P["degree"] = P["n_acquaintances"]
        nf = P.internal["new_friend_days"][:nn]
        recent_new = np.zeros(nn, np.int16)
        if not initial:
            m3 = (st >= 3) & (E["first_day"] > day - 90)
            recent_new = np.minimum(np.bincount(np.r_[lo[m3], hi[m3]], minlength=nn), 32000).astype(np.int16)
        P["new_friends_90d"] = recent_new
        del nf
        # roommate cohesion: mean liking among co-resident ties
        rm = (E["flags"] & Tie.ROOMMATE) > 0
        same = rm & (P["unit_id"][lo] == P["unit_id"][hi]) & (P["unit_id"][lo] >= 0)
        s = np.bincount(np.r_[lo[same], hi[same]], weights=np.r_[E["liking"][same], E["liking"][same]], minlength=nn)
        c = np.bincount(np.r_[lo[same], hi[same]], minlength=nn)
        P["roommate_cohesion"] = np.where(c > 0, (s / np.maximum(c, 1) + 1) / 2, 0.5).astype(np.float32)
        # adjacency for gatherings / influence (friends and casual friends among present people)
        mask = (st >= 2)
        self.adj = E.csr(mask, nn)
        self.adj_close = E.csr(st >= 3, nn)

    # ------------------------------------------------------------------ provenance
    def _why_closer(self, ev, eix, lo, hi):
        """A friendship's reasons, on the closeness scale the weekly update uses: hours together, liking, confiding,
        shared experiences and unrepaired hurt (relationship.history), each as a typed cause on the tie."""
        sim, E, p = self.sim, self.sim.w.E, self.sim.p
        keys = E.key_array[eix]
        parts = (("time", 0.12 * np.log1p(E["hours_leisure"][eix] / 10)),
                 ("liking", 0.35 * np.clip(E["liking"][eix], 0, 1)),
                 ("confiding", p("relationship.history.disclosure") * E["disclosure"][eix]),
                 ("shared", p("relationship.history.shared") * np.log1p(E["shared"][eix])),
                 ("hurt", -p("relationship.history.hurt") * E["hurt"][eix]))
        for name, w in parts:
            big = np.abs(w) >= 0.02
            link(sim, ev[big], "tie", keys[big], w[big], name)

    def _why_apart(self, ev, eix, lo, hi):
        """A close friendship fading: how long since they saw each other, hurt between them, and a change in either
        life shortly before they stopped seeing each other (a move, a mission, a new relationship, a new job…)."""
        sim, E = self.sim, self.sim.w.E
        day = sim.w.day
        keys = E.key_array[eix]
        last = E["last_day"][eix].astype(np.int64)
        link(sim, ev, "tie", keys, np.clip((day - last) / 60, 0.05, 1), "drifted")
        hurt = E["hurt"][eix]
        big = hurt >= 0.05
        link(sim, ev[big], "tie", keys[big], hurt[big], "hurt")
        fell_out = latest_between(sim, lo[eix], hi[eix], ("conflict",), day - 120)
        link(sim, ev, "event", fell_out, 0.6, "hurt")
        since = int(last.min()) - 14 if len(last) else day
        el = latest_event(sim, lo[eix], LIFE_CHANGES, since)
        eh = latest_event(sim, hi[eix], LIFE_CHANGES, since)
        best = np.maximum(el, eh)
        ok = best >= 0
        ok[ok] &= sim.log["day"][best[ok]] >= last[ok] - 14
        link(sim, ev[ok], "event", best[ok], 0.5, "around_then")

    def neighbor_mean(self, values: np.ndarray, weight: str = "closeness", min_stage: int = 3,
                      present_only: bool = True) -> tuple[np.ndarray, np.ndarray]:
        """Closeness-weighted mean of a person variable over each agent's ties (and total weight)."""
        w = self.sim.w
        E, P = w.E, w.P
        lo, hi = E.endpoints()
        m = E["stage"] >= min_stage
        if present_only:
            m &= P["present"][lo] & P["present"][hi]
        wt = E[weight][m].astype(np.float64)
        a, b = lo[m], hi[m]
        num = np.bincount(a, weights=wt * values[b], minlength=P.n) + np.bincount(b, weights=wt * values[a], minlength=P.n)
        den = np.bincount(a, weights=wt, minlength=P.n) + np.bincount(b, weights=wt, minlength=P.n)
        return np.where(den > 0, num / np.maximum(den, 1e-9), np.nan), den
