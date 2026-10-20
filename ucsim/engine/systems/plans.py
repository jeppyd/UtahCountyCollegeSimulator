"""Intentions: what people are trying to do, whether they do it, and why plans change.

Each week a person may form one intention from their drives and situation — ask someone out, reconnect
with a friend who is drifting, meet new people, study more, find work, get back to church. The intention
raises the odds of the behavior over the next couple of weeks (an implementation boost scaled by
conscientiousness and self-control) but does not guarantee it: about half of intentions are not carried
out (the intention–behavior gap; Sheeran 2002, Sheeran & Webb 2016).

Every intention is a row in a ledger with its target, why it was formed (the drive and its strength) and how
it ended: **kept**, **abandoned** (the target became unavailable, or priorities shifted — another drive took
over and this one faded) or **lapsed** (the window passed). That ledger is what the person page shows as
"what they were trying to do" and "why their plans changed". Long-run plans (missions, weddings, moves)
live in their own systems; this is the week-to-week layer.

The architecture borrows from BDI agents (beliefs → desires → intentions with commitment and
reconsideration; Rao & Georgeff 1995) and MATSim's plan memory, kept vectorized.
"""
from __future__ import annotations

import numpy as np
from scipy.special import expit

from ..provenance import latest_event, link, softmax_prob, state_ref
from ..state import Tie

KINDS = ["none", "ask_out", "reconnect", "meet_people", "study_more", "find_work", "return_to_church"]
K = {k: i for i, k in enumerate(KINDS)}
STATUS = ["active", "kept", "abandoned", "lapsed"]
REASONS = ["", "done", "target unavailable", "priorities changed", "the window passed", "left the area"]
MOTIVE_OF = {"ask_out": "partnership", "reconnect": "connection", "meet_people": "connection", "study_more": "achievement",
             "find_work": "security", "return_to_church": "faith"}
_M = ["connection", "partnership", "achievement", "security", "faith", "rest", "fun", "health"]   # mind.MOTIVES order
MOTIVE_IDX = np.array([0] + [_M.index(MOTIVE_OF[k]) for k in KINDS[1:]])


class Plans:
    # event: what it led to (the ask, the job…); formed: the intention_formed event that started it (its decision
    # says why this plan, and why now)
    COLS = {"agent": np.int32, "kind": np.uint8, "target": np.int32, "start": np.int32, "due": np.int32, "end": np.int32,
            "status": np.uint8, "reason": np.uint8, "strength": np.float32, "x0": np.float32, "event": np.int64,
            "formed": np.int64}

    def __init__(self, sim):
        self.sim = sim
        self.n = 0
        self.cap = 1 << 14
        self.cols = {c: np.zeros(self.cap, t) for c, t in self.COLS.items()}

    def init(self):
        P = self.sim.w.P
        P.add_internal("plan_row", np.int32, -1)

    def __getitem__(self, c):
        return self.cols[c][: self.n]

    def _append(self, rows: dict) -> np.ndarray:
        k = len(rows["agent"])
        if self.n + k > self.cap:
            new_cap = max(self.cap * 2, self.n + k + 1024)
            for c, arr in self.cols.items():
                g = np.zeros(new_cap, arr.dtype)
                g[: self.cap] = arr
                self.cols[c] = g
            self.cap = new_cap
        s = slice(self.n, self.n + k)
        for c in self.COLS:
            self.cols[c][s] = rows.get(c, 0)
        self.cols["end"][s] = -1
        self.cols["event"][s] = rows.get("event", -1)
        self.cols["formed"][s] = rows.get("formed", -1)
        out = np.arange(self.n, self.n + k)
        self.n += k
        return out

    # ------------------------------------------------------------------ helpers for behavior hooks
    def _active(self, kind: str) -> np.ndarray:
        """Per-agent bool: has an active intention of this kind."""
        P = self.sim.w.P
        row = P.internal["plan_row"][: P.n]
        has = row >= 0
        out = np.zeros(P.n, bool)
        if has.any():
            r = row[has]
            out[np.where(has)[0]] = self.cols["kind"][r] == K[kind]
        return out

    def _resolve(self) -> np.ndarray:
        """Per-agent follow-through strength: how reliably intentions turn into action (0.4–1)."""
        sim = self.sim
        key = (sim.w.day, sim.w.P.n)
        if getattr(self, "_res_key", None) != key:          # traits only: the same all day
            self._res = expit(0.4 + 0.5 * sim.z("conscientiousness") + 0.4 * sim.z("self_control"))
            self._res.flags.writeable = False
            self._res_key = key
        return self._res

    def _target(self) -> np.ndarray:
        P = self.sim.w.P
        row = P.internal["plan_row"][: P.n]
        return np.where(row >= 0, self.cols["target"][np.maximum(row, 0)], -1)

    def formed_event(self, ids: np.ndarray, kind: str | None = None, target=None) -> np.ndarray:
        """The intention_formed event of each person's active plan (of `kind`, aimed at `target`), −1 if none."""
        P = self.sim.w.P
        row = P.internal["plan_row"][ids]
        ok = row >= 0
        r = np.maximum(row, 0)
        if kind is not None:
            ok &= self.cols["kind"][r] == K[kind]
        if target is not None:
            ok &= self.cols["target"][r] == np.asarray(target)
        return np.where(ok, self.cols["formed"][r], -1)

    def ask_boost(self, ids: np.ndarray, tgt: np.ndarray) -> np.ndarray:
        has = self._active("ask_out")[ids]
        aim = self._target()[ids] == tgt
        return self.sim.p("plans.execution.ask") * self._resolve()[ids] * (has & aim)

    def study_boost(self) -> np.ndarray:
        return self.sim.p("plans.execution.study") * self._resolve() * self._active("study_more")

    def church_boost(self) -> np.ndarray:
        return self.sim.p("plans.execution.church") * self._resolve() * self._active("return_to_church")

    def wants_work(self) -> np.ndarray:
        return self._active("find_work")

    def choice_bias(self, idx: np.ndarray) -> np.ndarray:
        """Meeting new people: venues, dances, the complex and visiting acquaintances get more appealing."""
        B = np.zeros((len(idx), 8))
        meet = self._active("meet_people")[idx] * self._resolve()[idx] * self.sim.p("plans.execution.meet")
        B[:, 3] += 0.6 * meet
        B[:, 5] += 0.8 * meet
        B[:, 7] += 0.8 * meet
        B[:, 6] += 0.4 * meet
        return B

    def accept_boost(self) -> np.ndarray:
        """Invitations to gatherings are accepted more often by people trying to meet people."""
        return 0.8 * self._active("meet_people") * self._resolve()

    def reconnect_pick(self, src: np.ndarray, off: np.ndarray, indptr: np.ndarray, nbr: np.ndarray, rng) -> np.ndarray:
        """Friend contact: someone intending to reconnect reaches for that friend."""
        P = self.sim.w.P
        rec = self._active("reconnect")[src]
        if not rec.any():
            return off
        tgt = self._target()[src]
        go = rec & (rng.random(len(src)) < 0.7 * self._resolve()[src])
        out = off.copy()
        for j in np.where(go)[0]:
            s, t = int(src[j]), int(tgt[j])
            seg = nbr[indptr[s]: indptr[s + 1]]
            hit = np.flatnonzero(seg == t)
            if len(hit):
                out[j] = hit[0]
        del P
        return out

    # ------------------------------------------------------------------ outcome hooks
    def asked(self, ids: np.ndarray, tgt: np.ndarray, yes: np.ndarray, ask_ev: np.ndarray):
        has = self._active("ask_out")[ids]
        if has.any():
            self._close(ids[has], "kept", "done", event=ask_ev[has])

    def contacted(self, src: np.ndarray, dst: np.ndarray):
        has = self._active("reconnect")[src]
        if has.any():
            hit = has & (self._target()[src] == dst)
            if hit.any():
                self._close(np.unique(src[hit]), "kept", "done")

    def _close(self, agents: np.ndarray, status: str, reason: str, event=None, why=None):
        """End plans. A plan given up for a concrete reason is logged (plan_abandoned) with its beginning as the
        cause and `why` — (kind, refs, weight, role) aligned with `agents` — as typed causes."""
        sim, w = self.sim, self.sim.w
        P = w.P
        rows = P.internal["plan_row"][agents]
        ok = rows >= 0
        agents, rows = agents[ok], rows[ok]
        if len(rows) == 0:
            return
        self.cols["status"][rows] = STATUS.index(status)
        self.cols["reason"][rows] = REASONS.index(reason)
        self.cols["end"][rows] = w.day
        if event is not None:
            self.cols["event"][rows] = np.asarray(event)[ok]
        P.internal["plan_row"][agents] = -1
        P.cols["intention"][agents] = 0
        if status == "kept":
            P.cols["plans_kept"][agents] = np.minimum(P["plans_kept"][agents] + 1, 2000)
        else:
            P.cols["plans_abandoned"][agents] = np.minimum(P["plans_abandoned"][agents] + 1, 2000)
            if reason in ("target unavailable", "priorities changed"):
                kinds = self.cols["kind"][rows].astype(float)
                ev = sim.emit("plan_abandoned", agents, b=np.where(self.cols["target"][rows] >= 0, self.cols["target"][rows], -1),
                              value=kinds, mech="plans.reconsider", cause=self.cols["formed"][rows])
                for kind_, refs, wgt, role_ in why or ():
                    refs = np.broadcast_to(np.asarray(refs, np.int64), ok.shape)[ok]
                    wgt = np.broadcast_to(np.asarray(wgt, np.float32), ok.shape)[ok]
                    link(sim, ev, kind_, refs, wgt, role_)

    # ------------------------------------------------------------------ daily: keep, abandon, lapse
    def daily(self):
        sim, w = self.sim, self.sim.w
        P = w.P
        n = P.n
        row = P.internal["plan_row"][:n]
        has = row >= 0
        if not has.any():
            return
        ids = np.where(has)[0]
        r = row[ids]
        kind = self.cols["kind"][r]
        tgt = self.cols["target"][r]
        day = w.day
        # left the area / went on a mission
        gone = ~P["present"][ids]
        if gone.any():
            self._close(ids[gone], "abandoned", "left the area")
        keep = np.zeros(len(ids), bool)
        drop = np.zeros(len(ids), bool)
        # kept: the behavior happened
        keep |= (kind == K["find_work"]) & P["employed"][ids]
        if w.env["weekday"] == 6:
            keep |= (kind == K["return_to_church"]) & sim.systems["faith"].attending_today[ids]
        soc = sim.systems["mind"].last_social[ids]
        keep |= (kind == K["meet_people"]) & soc & (sim.u("meet_kept")[ids] < 0.5)
        keep |= (kind == K["study_more"]) & (P["study_hours"][ids] >= self.cols["x0"][r] + 1)
        # abandoned: the target is no longer available
        tsafe = np.maximum(tgt, 0)
        taken = P.isin("rel_status", ["dating", "engaged", "married"])[tsafe] & (P["partner_id"][tsafe] != ids)
        drop |= (kind == K["ask_out"]) & (tgt >= 0) & (taken | ~P["present"][tsafe])
        drop |= (kind == K["reconnect"]) & (tgt >= 0) & ~P["present"][tsafe]
        drop |= (kind == K["ask_out"]) & ~P.isin("rel_status", ["single", "divorced", "talking"])[ids]
        drop &= ~keep & ~gone
        keep &= ~gone
        if keep.any():
            self._close(ids[keep], "kept", "done")
        if drop.any():
            d = np.flatnonzero(drop)
            since = int(self.cols["start"][r[d]].min()) - 1
            # what made the target unavailable (they got together with someone, left), or what changed for the
            # person themselves (an ask-out plan ends when they start seeing someone)
            moved_on = ("talking_started", "relationship_started", "engaged", "wedding", "left_area", "mission_departure")
            them = latest_event(sim, tsafe[d], moved_on, since)
            me = latest_event(sim, ids[d], moved_on[:4], since)
            self._close(ids[d], "abandoned", "target unavailable",
                        why=[("event", np.where(tgt[d] >= 0, them, -1), 1.0, "target_gone"), ("event", me, 1.0, "around_then")])
        # priorities changed: this drive has faded to under half and another clearly dominates
        rest = ~keep & ~drop & ~gone
        if rest.any():
            D = sim.systems["mind"].drives()[:, ids[rest]]
            dnow = D[MOTIVE_IDX[kind[rest]], np.arange(int(rest.sum()))]
            dmax = np.max(D, axis=0)
            shift = (dnow < 0.5 * self.cols["strength"][r[rest]]) & (dmax > 2.5 * np.maximum(dnow, 0.02))
            if shift.any():
                who = ids[rest][shift].astype(np.int64)
                top = np.argmax(D[:, shift], axis=0)
                codes = self._drive_codes()
                mine = MOTIVE_IDX[kind[rest][shift]]
                self._close(who, "abandoned", "priorities changed",
                            why=[("state", codes[top] + who, dmax[shift], "priorities"),
                                 ("state", codes[mine] + who, dnow[shift], "faded")])
            lapse = (day >= self.cols["due"][r[rest]]) & ~shift
            if lapse.any():
                self._close(ids[rest][lapse], "lapsed", "the window passed")

    # ------------------------------------------------------------------ weekly: form intentions
    def weekly(self):
        sim, w = self.sim, self.sim.w
        P, E, p = w.P, w.E, sim.p
        n = P.n
        day = w.day
        free = P["present"] & (P.internal["plan_row"][:n] < 0)
        if not free.any():
            return
        S = np.zeros((len(KINDS), n))
        tgt = np.full((len(KINDS), n), -1, np.int64)
        seek = sim.systems["romance"].seeking_mask()
        crush = P.internal["crush_id"][:n]
        catt = P.internal["crush_att"][:n]
        ok = seek & (crush >= 0) & (catt > p("romance.ask.min_attraction") * 0.8)
        S[K["ask_out"]] = np.where(ok, P["drive_partnership"] * catt * (0.5 + P["expect_accept"]) * 3.0, 0)
        tgt[K["ask_out"]] = np.where(ok, crush, -1)
        # reconnect: the closest friend not seen in two weeks or more
        best_c = np.zeros(n)
        if E.n:
            lo, hi = E.endpoints()
            fade = (E["stage"] >= 3) & ((day - E["last_day"]) >= 14) & P["present"][lo] & P["present"][hi] & \
                ((E["flags"] & (Tie.ROMANTIC | Tie.SPOUSE)) == 0)
            if fade.any():
                a = np.r_[lo[fade], hi[fade]]
                b = np.r_[hi[fade], lo[fade]]
                c = np.r_[E["closeness"][fade], E["closeness"][fade]]
                order = np.lexsort((-c, a))
                a, b, c = a[order], b[order], c[order]
                first = np.r_[True, a[1:] != a[:-1]]
                best_b = np.full(n, -1, np.int64)
                best_b[a[first]] = b[first]
                best_c[a[first]] = c[first]
                S[K["reconnect"]] = P["drive_connection"] * best_c * 2.5
                tgt[K["reconnect"]] = best_b
        S[K["meet_people"]] = P["drive_connection"] * np.clip(1 - P["n_friends"] / 4, 0, 1) * 1.5
        in_term = P["enrolled"] & np.where(P["school"] == 1, bool(w.env.get("term_BYU")), bool(w.env.get("term_UVU")))
        gpa = np.nan_to_num(P["gpa"], nan=3.3)
        S[K["study_more"]] = np.where(in_term, P["drive_achievement"] * (1 + 0.8 * (gpa < 3.0)) * 1.6, 0)
        S[K["find_work"]] = np.where(~P["employed"] & (P["age"] < 60) & ~P.is_("role", "faculty"), P["drive_security"] * 1.8, 0)
        lapsed = P["lds_member"] & (P["cares_faith"] > 0.5) & (P["attend_rate"] < 0.5)
        S[K["return_to_church"]] = np.where(lapsed, P["drive_faith"] * 2.0, 0)
        noise = sim.streams.gen("intend", day).gumbel(size=(len(KINDS) - 1, n)) * 0.15
        best = 1 + np.argmax(S[1:] + noise, axis=0)
        score = S[best, np.arange(n)]
        form = free & (score > p("plans.formation.threshold"))
        ids = np.where(form)[0]
        if len(ids) == 0:
            return
        kind = best[ids]
        t = tgt[kind, ids]
        horizon = np.where(kind == K["ask_out"], 10, np.where(kind == K["find_work"], 35, 14))
        x0 = np.where(kind == K["study_more"], P["study_hours"][ids], 0)
        # strength = the motivating drive at formation (reconsideration compares the drive now with this)
        drive0 = sim.systems["mind"].drives()[MOTIVE_IDX[kind], ids]
        formed = self._record_formation(ids, kind, t, S, catt, best_c, gpa)
        rows = self._append({"agent": ids, "kind": kind, "target": t, "start": np.full(len(ids), day), "due": day + horizon,
                             "status": 0, "reason": 0, "strength": drive0, "x0": x0, "formed": formed})
        P.internal["plan_row"][ids] = rows
        P.cols["intention"][ids] = kind.astype(np.uint8)
        self._prune()

    # ------------------------------------------------------------------ provenance
    # typical values the parts of a formation score are measured against (a factor of 0 means "about typical")
    _REF = {"drive": 0.2, "crush": 0.4, "expect": 1.0, "closeness": 0.5, "few_friends": 0.5, "grades": 1.0}
    _CONST = {"ask_out": 3.0, "reconnect": 2.5, "meet_people": 1.5, "study_more": 1.6, "find_work": 1.8, "return_to_church": 2.0}
    _PARTS = {"ask_out": ("drive", "crush", "expect"), "reconnect": ("drive", "closeness"),
              "meet_people": ("drive", "few_friends"), "study_more": ("drive", "grades"), "find_work": ("drive",),
              "return_to_church": ("drive",)}

    def _drive_codes(self) -> np.ndarray:
        """Packed `state` ref prefixes (variable code << 32) of the drives, in mind.MOTIVES order."""
        return np.array([state_ref(self.sim, f"drive_{m}", 0) for m in _M], np.int64)

    def _record_formation(self, ids, kind, t, S, catt, best_c, gpa) -> np.ndarray:
        """Why this plan: its score is a product (drive × what the situation offers × a constant) compared with a bar,
        so the log of score/bar splits exactly into one factor per part, each measured against a typical value.
        Records the decision and returns the intention_formed events (one per person)."""
        sim, w = self.sim, self.sim.w
        P, p = w.P, sim.p
        k = len(ids)
        thr = p("plans.formation.threshold")
        parts = {f: np.ones(k) for f in self._REF}
        motive = np.array(_M)[MOTIVE_IDX[kind]]
        for m in set(motive.tolist()):
            sel = motive == m
            parts["drive"][sel] = P[f"drive_{m}"][ids[sel]]
        a = kind == K["ask_out"]
        parts["crush"][a] = catt[ids[a]]
        parts["expect"][a] = 0.5 + P["expect_accept"][ids[a]]
        rc = kind == K["reconnect"]
        parts["closeness"][rc] = best_c[ids[rc]]
        mp = kind == K["meet_people"]
        parts["few_friends"][mp] = np.clip(1 - P["n_friends"][ids[mp]] / 4, 0, 1)
        sm = kind == K["study_more"]
        parts["grades"][sm] = 1 + 0.8 * (gpa[ids[sm]] < 3.0)
        base = np.zeros(k)
        # the drive is named by its motive ("really wanted a relationship"), so a reason reads as what it was about
        motives = sorted(set(MOTIVE_OF.values()))
        factors = {f: np.zeros(k) for f in self._REF if f != "drive"} | {f"drive_{m}": np.zeros(k) for m in motives}
        for kn, names in self._PARTS.items():
            sel = kind == K[kn]
            if not sel.any():
                continue
            ref = float(np.prod([self._REF[f] for f in names]))
            base[sel] = np.log(self._CONST[kn] * ref / thr)
            for f in names:
                factors[f"drive_{MOTIVE_OF[kn]}" if f == "drive" else f][sel] = np.log(np.maximum(parts[f][sel], 1e-6) / self._REF[f])
        # which plan, among those in reach: a Gumbel-max choice over the scores (noise scale 0.15)
        prob = softmax_prob(S[1:, ids].T / 0.15, kind - 1)
        did = sim.decisions.record("form_intention", w.day, ids, kind - 1, factors, base=base, prob=prob,
                                   other=np.where(t >= 0, t, -1),
                                   refs={**{f"drive_{m}": ("state", state_ref(sim, f"drive_{m}", ids)) for m in motives},
                                         "crush": ("person", t), "closeness": ("person", t)})
        return sim.emit("intention_formed", ids, b=np.where(t >= 0, t, -1), value=kind.astype(np.float32),
                        mech="plans.formation", decision=did)

    def _prune(self, keep_per_agent: int = 12):
        """Keep active intentions and each person's most recent finished ones."""
        if self.n < 200_000 and self.n < 40 * max(self.sim.w.P.n, 1):
            return
        P = self.sim.w.P
        idx = np.arange(self.n)
        order = np.lexsort((-self["start"], self["agent"]))
        ag = self["agent"][order]
        first = np.r_[0, np.flatnonzero(ag[1:] != ag[:-1]) + 1]
        rank = np.arange(len(order)) - np.repeat(first, np.diff(np.r_[first, len(order)]))
        keep = np.zeros(self.n, bool)
        keep[order] = rank < keep_per_agent
        keep |= self["status"] == 0
        remap = np.full(self.n, -1, np.int64)
        remap[idx[keep]] = np.arange(int(keep.sum()))
        k = int(keep.sum())
        for c, arr in self.cols.items():
            arr[:k] = arr[: self.n][keep]
        self.n = k
        row = P.internal["plan_row"][: P.n]
        has = row >= 0
        row[has] = remap[row[has]]

    # ------------------------------------------------------------------ queries (UI)
    def for_agent(self, i: int, limit: int = 12) -> list[dict]:
        rows = np.where(self["agent"] == i)[0]
        rows = rows[np.argsort(-self["start"][rows])][:limit]
        out = []
        for r in rows:
            out.append({"kind": KINDS[int(self.cols["kind"][r])], "target": int(self.cols["target"][r]) if self.cols["target"][r] >= 0 else None,
                        "start": int(self.cols["start"][r]), "due": int(self.cols["due"][r]),
                        "end": int(self.cols["end"][r]) if self.cols["end"][r] >= 0 else None,
                        "status": STATUS[int(self.cols["status"][r])], "reason": REASONS[int(self.cols["reason"][r])],
                        "strength": round(float(self.cols["strength"][r]), 3), "motive": MOTIVE_OF.get(KINDS[int(self.cols["kind"][r])]),
                        "event": int(self.cols["event"][r]) if self.cols["event"][r] >= 0 else None})
        return out

    def summary(self, since: int = 0) -> dict:
        m = self["start"] >= since
        out = {}
        for k in KINDS[1:]:
            mk = m & (self["kind"] == K[k])
            tot = int(mk.sum())
            if tot:
                st = self["status"][mk]
                out[k] = {"formed": tot, **{s: int((st == i).sum()) for i, s in enumerate(STATUS)}}
        return out
