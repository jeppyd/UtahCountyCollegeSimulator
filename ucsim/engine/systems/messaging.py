"""Messaging and group chats: structured communication (no generated text), so invitations, replies, silence and news
are traceable records.

Design notes (parameters in config/mechanisms/15_messaging.yaml)
* Threads: apartment chats (people sharing a unit), friend-group chats (clusters of close friends found weekly by
  label propagation on the close-friend graph; a chat follows its group, gains members, and splits when the group
  does), club and team chats, ward chats. Direct threads between two people are implicit (id −1) and never stored.
  Joining, leaving and muting are events; starting a group chat and adding people to it, and leaving one, are
  decisions.
* Acts: typed records — invite (an occasion posted to a group chat), check-in (a text to a friend), reply, silence,
  news, plan change. Only these salient acts are stored; everything else is a per-thread daily volume.
* Attention: each person checks their phone a few times a day (more with social-media habits, less when at work or in
  class). A message is seen in time with a chance that falls as the thread gets busy and rises when it is addressed
  to them. Group-chat and text invitations go through this (occasions.deliver asks `notice_prob`), so "saw it late"
  and "never saw it" happen.
* Replies and silence: a check-in is answered with a chance rising with closeness, responsiveness (conscientiousness
  and agreeableness) and mood, falling when busy (decision `reply_message`). Unanswered after a couple of days, the
  sender interprets it: rejection-sensitive people read it as being ignored (hurt on the tie, a lower belief that
  the friend cares, a little loneliness), others assume the friend is busy. Both are events.
* Left out: when friends get together, a close friend of two or more who came, who wasn't invited, can find out
  (through a shared chat or the news) — hurt on the tie with the host, lower belonging. When the host didn't think
  they were interested, the host's side is recorded too.
* Who knows what: a KnowledgeStore (person, event, source, day, channel) for salient life events. The person it is
  about decides whether to share (decision `share_news`; private things like a faith crisis are often kept close);
  news then spreads along close ties and through group chats, with a source and a day, for three weeks.
"""
from __future__ import annotations

import numpy as np
from scipy.special import expit

from ..ledger import CHANNEL_ID, Table
from ..provenance import link
from ..state import EdgeStore
from ucsim.population.structure import ward_name

KINDS = ("household", "friends", "club", "team", "ward", "family")
KIND_ID = {k: i for i, k in enumerate(KINDS)}
ACTS = ("invite", "checkin", "reply", "silence", "news", "plan_change")
ACT_ID = {k: i for i, k in enumerate(ACTS)}
# salient life events that travel as news, with how private they are (0 = everyone tells, 1 = rarely told)
NEWS = {"engaged": 0.0, "wedding": 0.0, "relationship_started": 0.2, "breakup_initiated": 0.3, "breakup_received": 0.35,
        "pregnancy": 0.2, "birth": 0.0, "mission_call": 0.0, "mission_departure": 0.0, "mission_return": 0.0,
        "early_return": 0.6, "graduation": 0.0, "job_lost": 0.5, "death_in_family": 0.3, "disaffiliated": 0.7,
        "faith_crisis_start": 0.85, "stopped_attending": 0.7, "returned_to_activity": 0.4, "baptized": 0.0,
        "academic_probation": 0.8, "dropout": 0.5, "depressive_episode_start": 0.85, "left_area": 0.0}
SOCIAL_OCCASIONS = ("dinner", "gathering", "game_night", "party", "movie_night", "hangout")


class KnowledgeStore:
    """Who knows about which event, from whom, when and how (person, event, source, day, channel)."""

    def __init__(self):
        self.t = Table({"person": (np.int32, -1), "event": (np.int64, -1), "source": (np.int32, -1), "day": (np.int32, -1),
                        "channel": (np.int8, 0)}, capacity=1 << 14)
        self._keys = np.empty(0, np.int64)        # sorted event·2^24 + person

    @staticmethod
    def key(event, person) -> np.ndarray:
        return (np.asarray(event, np.int64) << 24) | (np.asarray(person, np.int64) & 0xFFFFFF)

    def knows(self, event, person) -> np.ndarray:
        k = self.key(event, person)
        if not len(self._keys):
            return np.zeros(len(np.atleast_1d(k)), bool)
        i = np.clip(np.searchsorted(self._keys, k), 0, len(self._keys) - 1)
        return self._keys[i] == k

    def add(self, person, event, source, day: int, channel) -> np.ndarray:
        person = np.atleast_1d(np.asarray(person, np.int64))
        event = np.broadcast_to(np.asarray(event, np.int64), person.shape)
        k = self.key(event, person)
        k, first = np.unique(k, return_index=True)
        new = ~self.knows(event[first], person[first])
        sel = first[new]
        if not len(sel):
            return sel
        src = np.broadcast_to(np.asarray(source, np.int64), person.shape)[sel]
        ch = np.broadcast_to(np.asarray(channel, np.int8), person.shape)[sel]
        self.t.append(len(sel), person=person[sel], event=event[sel], source=src, day=day, channel=ch)
        self._keys = np.union1d(self._keys, k[new])
        return sel

    def about(self, event: int) -> dict:
        m = self.t["event"] == int(event)
        return {c: self.t[c][m] for c in ("person", "source", "day", "channel")}


class Messaging:
    def __init__(self, sim):
        self.sim = sim
        self.threads = Table({"kind": (np.int8, -1), "key": (np.int64, -1), "creator": (np.int32, -1),
                              "created_day": (np.int32, -1), "active": (np.bool_, True), "volume": (np.float32, 0.0),
                              "today": (np.int32, 0), "n": (np.int32, 0)}, capacity=1 << 12)
        self.members = Table({"thread": (np.int64, -1), "person": (np.int32, -1), "joined": (np.int32, -1),
                              "left": (np.int32, -1), "muted": (np.bool_, False)}, capacity=1 << 14)
        self.acts = Table({"thread": (np.int64, -1), "day": (np.int32, -1), "block": (np.int8, 3), "sender": (np.int32, -1),
                           "kind": (np.int8, -1), "to": (np.int32, -1), "ref": (np.int64, -1), "reply_to": (np.int64, -1),
                           "replied_day": (np.int32, -1), "event": (np.int64, -1)}, capacity=1 << 14)
        self.know = KnowledgeStore()
        self.live_news = {"event": np.empty(0, np.int64), "subject": np.empty(0, np.int64), "day": np.empty(0, np.int32),
                          "shared": np.empty(0, bool)}
        self._idx = None                 # (person-sorted member rows, indptr) for active memberships
        self._log_seen = 0

    # ------------------------------------------------------------------ setup
    def init(self):
        self._sync(initial=True)
        self._log_seen = self.sim.log.n

    def _active_rows(self) -> np.ndarray:
        M = self.members
        return np.flatnonzero(M["left"] < 0)

    def index(self):
        """CSR of each person's active threads (rebuilt after membership changes)."""
        if self._idx is None:
            n = self.sim.w.P.n
            rows = self._active_rows()
            per = self.members["person"][rows].astype(np.int64)
            order = np.argsort(per, kind="stable")
            rows = rows[order]
            indptr = np.zeros(n + 1, np.int64)
            np.add.at(indptr, per + 1, 1)
            self._idx = (rows, np.cumsum(indptr))
        rows, indptr = self._idx
        n = self.sim.w.P.n
        if len(indptr) < n + 1:
            indptr = np.r_[indptr, np.full(n + 1 - len(indptr), indptr[-1])]
            self._idx = (rows, indptr)
        return self._idx

    def threads_of(self, i: int) -> np.ndarray:
        rows, indptr = self.index()
        return self.members["thread"][rows[indptr[i]:indptr[i + 1]]]

    def shared_thread(self, a: np.ndarray, b: np.ndarray, prefer=("friends", "household", "team", "club", "ward")) -> np.ndarray:
        """For each pair, a thread both are active members of (the most personal kind first); −1 if none."""
        a = np.asarray(a, np.int64)
        b = np.asarray(b, np.int64)
        out = np.full(len(a), -1, np.int64)
        if not len(a) or not self.members.n:
            return out
        rows, indptr = self.index()
        deg = indptr[a + 1] - indptr[a]
        rep = np.repeat(np.arange(len(a)), deg)
        if not len(rep):
            return out
        off = np.arange(len(rep)) - np.repeat(np.cumsum(deg) - deg, deg)
        th = self.members["thread"][rows[indptr[a[rep]] + off]]
        member_keys = np.sort((self.members["thread"][rows].astype(np.int64) << 24) | self.members["person"][rows].astype(np.int64))
        k = (th << 24) | b[rep]
        i = np.clip(np.searchsorted(member_keys, k), 0, max(len(member_keys) - 1, 0))
        both = member_keys[i] == k
        rank = np.full(len(KINDS), 99)
        for r, kd in enumerate(prefer):
            rank[KIND_ID[kd]] = r
        tk = self.threads.get("kind", th, default=0)
        score = np.where(both, rank[tk], 999)
        order = np.lexsort((score, rep))
        first = np.unique(rep[order], return_index=True)[1]
        best = order[first]
        ok = score[best] < 999
        out[rep[best][ok]] = th[best][ok]
        return out

    # ------------------------------------------------------------------ attention
    def checks(self, person: np.ndarray) -> np.ndarray:
        """How many times a day each person looks at their messages."""
        sim, w = self.sim, self.sim.w
        p = sim.p
        busy = sim.systems["activity"].shift_minutes(1, sim.cal.weekday(w.day))[person] > 0
        return np.exp(p("messaging.attention.checks") + p("messaging.attention.phone") * sim.z("social_media_hours")[person]
                      - p("messaging.attention.busy") * busy)

    def notice_prob(self, person, channel, thread=None, mention=True) -> np.ndarray:
        """Chance a message is seen in time today: more phone checks, fewer when the thread is busy, more when it is
        addressed to them; a muted chat is rarely read."""
        p = self.sim.p
        person = np.asarray(person, np.int64)
        thread = np.full(len(person), -1, np.int64) if thread is None else np.asarray(thread, np.int64)
        vol = np.where(thread >= 0, self.threads.get("volume", thread, default=0.0), 0.0)
        f = 1.0 / (1.0 + vol / p("messaging.attention.volume_scale"))
        f = f * np.where(np.broadcast_to(mention, person.shape), p("messaging.attention.mention"), 1.0)
        muted = self._muted(person, thread)
        f = np.where(muted, f * 0.15, f)
        return 1 - np.exp(-self.checks(person) * np.clip(f, 0, 1) * 0.35)

    def _muted(self, person, thread) -> np.ndarray:
        if not self.members.n or not (thread >= 0).any():
            return np.zeros(len(person), bool)
        M = self.members
        m = M["muted"] & (M["left"] < 0)
        if not m.any():
            return np.zeros(len(person), bool)
        keys = np.sort((M["thread"][m].astype(np.int64) << 24) | M["person"][m].astype(np.int64))
        k = (thread << 24) | person
        i = np.clip(np.searchsorted(keys, k), 0, len(keys) - 1)
        return (thread >= 0) & (keys[i] == k)

    def assign_threads(self, inv_ids: np.ndarray):
        """Group-chat invitations go to a chat the inviter and invitee share (else they arrive as a text); one invite
        act per occasion and chat is recorded."""
        book = self.sim.book
        I = book.inv
        pos = I.pos(np.atleast_1d(np.asarray(inv_ids, np.int64)))
        pos = pos[pos >= 0]
        gc = pos[(I.cols["channel"][pos] == CHANNEL_ID["group_chat"]) & (I.cols["inviter"][pos] >= 0)]
        if not len(gc):
            return
        th = self.shared_thread(I.cols["inviter"][gc], I.cols["person"][gc])
        I.cols["thread"][gc] = th
        I.cols["channel"][gc[th < 0]] = CHANNEL_ID["text"]
        ok = th >= 0
        if ok.any():
            occ = I.cols["occ"][gc[ok]].astype(np.int64)
            pair, first = np.unique(np.c_[occ, th[ok]], axis=0, return_index=True)
            self.acts.append(len(pair), thread=pair[:, 1], day=self.sim.w.day, block=0,
                             sender=I.cols["inviter"][gc[ok]][first], kind=ACT_ID["invite"], ref=pair[:, 0])
            self._bump(pair[:, 1])

    def family_news(self, people, events):
        """News from home arrives in the family chat (posted by someone off-map)."""
        th = self._thread_ids("family", np.asarray(people, np.int64), self.sim.w.day)
        self.acts.append(len(th), thread=th, day=self.sim.w.day, block=3, sender=-1, kind=ACT_ID["news"], to=people,
                         ref=events, event=events)
        self._bump(th)

    def _bump(self, threads, k=1):
        p = self.threads.pos(np.asarray(threads, np.int64))
        p = p[p >= 0]
        np.add.at(self.threads.cols["today"], p, k)

    def plan_change(self, occ_ids: np.ndarray):
        """A cancelled plan: the host tells the people who said yes, in the chat it was posted to."""
        book = self.sim.book
        I = book.inv
        if not I.n or not len(occ_ids):
            return
        m = np.isin(I["occ"], occ_ids) & (I["response"] == 1)
        if not m.any():
            return
        th = I["thread"][m]
        occ = I["occ"][m]
        key, first = np.unique(np.c_[occ, th], axis=0, return_index=True)
        sender = book.occ.get("organizer", key[:, 0], default=-1)
        to = np.where(key[:, 1] < 0, I["person"][m][first], -1)
        self.acts.append(len(key), thread=key[:, 1], day=self.sim.w.day, block=1, sender=sender, kind=ACT_ID["plan_change"],
                         to=to, ref=key[:, 0])

    # ------------------------------------------------------------------ daily
    def end_of_day(self):
        sim, w = self.sim, self.sim.w
        day = w.day
        self._checkins(day)
        self._silences(day)
        self._left_out(day)
        self._news(day)
        T = self.threads
        if T.n:
            rate = np.array([sim.p(f"messaging.background.{k}") for k in KINDS])[np.clip(T["kind"], 0, len(KINDS) - 1)]
            today = T["today"] + rate * T["n"]
            T.cols["volume"][: T.n] = (0.7 * T["volume"] + 0.3 * today).astype(np.float32)
            T.cols["today"][: T.n] = 0
        if day % 7 == 6:
            self._sync(initial=False)
            self._thin(day)

    def _checkins(self, day: int):
        """Texts to friends, more to friends who are struggling; replies or silence."""
        sim, w = self.sim, self.sim.w
        P, E, p = w.P, w.E, sim.p
        net = sim.systems["network"]
        if not hasattr(net, "adj_close"):
            return
        indptr, nbr, _ = net.padded(net.adj_close)
        n = P.n
        deg = np.diff(indptr)[:n]
        rng = sim.streams.gen("msg_checkin", day)
        lam = p("messaging.checkin.rate") * np.exp(0.2 * sim.z("agreeableness") + 0.2 * sim.z("extraversion"))
        k = np.where(P["present"][:n] & (deg > 0), rng.poisson(lam), 0)
        a = np.repeat(np.arange(n), k)
        if not len(a):
            return
        b = nbr[indptr[a] + (rng.random(len(a)) * deg[a]).astype(np.int64)]
        low = (P["mood"][b] < 0.35) | (P["loneliness"][b] > 0.6)          # struggling friends get more texts
        keep = P["present"][b] & (b != a) & ((rng.random(len(a)) < 0.55) | low)
        a, b = a[keep], b[keep]
        if not len(a):
            return
        eix = E.find(EdgeStore.make_keys(a, b))
        ok = eix >= 0
        a, b, eix = a[ok], b[ok], eix[ok]
        acts = self.acts.append(len(a), thread=-1, day=day, block=2, sender=a, kind=ACT_ID["checkin"], to=b)
        busy = sim.systems["activity"].shift_minutes(1, sim.cal.weekday(day))[b] > 0
        resp = (sim.z("conscientiousness")[b] + sim.z("agreeableness")[b]) / 2
        T = {"closeness": p("messaging.reply.closeness") * E["closeness"][eix],
             "responsiveness": p("messaging.reply.responsive") * resp,
             "mood": p("messaging.reply.mood") * (P["mood"][b] - 0.5),
             "busy": -p("messaging.reply.busy") * busy,
             "depression": -1.0 * P["depressive_episode"][b]}
        base = p("messaging.reply.base")
        pr = expit(base + sum(T.values()))
        rep = rng.random(len(a)) < pr
        out = np.where(rep, "replied", "no_reply")
        did = np.empty(len(a), np.int64)
        for o in ("replied", "no_reply"):
            s = out == o
            if s.any():
                did[s] = sim.decisions.record("reply_message", day, b[s], o, {k: v[s] for k, v in T.items()}, base=base,
                                              prob=np.where(rep[s], pr[s], 1 - pr[s]), other=a[s])
        if rep.any():
            r = np.flatnonzero(rep)
            self.acts.append(len(r), thread=-1, day=day, block=3, sender=b[r], kind=ACT_ID["reply"], to=a[r], reply_to=acts[r])
            self.acts.set("replied_day", acts[r], day)
            E.cols["last_day"][eix[r]] = day
        nr = np.flatnonzero(~rep)
        self._pending = getattr(self, "_pending", np.empty((0, 4), np.int64))
        due = day + int(p("messaging.reply.silence_days"))
        self._pending = np.r_[self._pending, np.c_[a[nr], b[nr], acts[nr], np.full(len(nr), due)]] if len(nr) else self._pending
        del did

    def _silences(self, day: int):
        """Unanswered texts are interpreted: rejection-sensitive people feel ignored, others assume the friend is busy."""
        sim, w = self.sim, self.sim.w
        P, E, p = w.P, w.E, sim.p
        pend = getattr(self, "_pending", None)
        if pend is None or not len(pend):
            return
        due = pend[:, 3] <= day
        if not due.any():
            return
        a, b, act = pend[due, 0], pend[due, 1], pend[due, 2]
        self._pending = pend[~due]
        pres = P["present"][a] & P["present"][b]
        a, b, act = a[pres], b[pres], act[pres]
        if not len(a):
            return
        sil = self.acts.append(len(a), thread=-1, day=day, block=3, sender=b, kind=ACT_ID["silence"], to=a, reply_to=act)
        u = sim.streams.uniform("msg_silence", day, len(a))
        ignored = u < expit(p("messaging.silence.ignored_base") + p("messaging.silence.rs") * sim.z("rejection_sensitivity")[a])
        for m, et in ((ignored, "felt_ignored"), (~ignored, "assumed_busy")):
            if not m.any():
                continue
            ev = sim.emit(et, a[m], b=b[m], mech="messaging.silence", block=3)
            link(sim, ev, "message", act[m], 1.0, "unanswered")
            self.acts.set("event", sil[m], ev)
        if ignored.any():
            eix = E.find(EdgeStore.make_keys(a[ignored], b[ignored]))
            ok = eix >= 0
            e, aa = eix[ok], a[ignored][ok]
            E.cols["hurt"][e] = np.clip(E["hurt"][e] + 0.04, 0, 1)
            lo, _ = EdgeStore.split(E.key_array[e])
            col = np.where(lo == aa, "bel_lh", "bel_hl")      # what the sender believes the friend feels for them
            for c in ("bel_lh", "bel_hl"):
                s = col == c
                E.cols[c][e[s]] = E[c][e[s]] * 0.92

    def _left_out(self, day: int):
        """Friends got together without them: they may find out through a shared chat or the news."""
        sim, w = self.sim, self.sim.w
        P, E, p = w.P, w.E, sim.p
        book = sim.book
        O, I = book.occ, book.inv
        if not O.n or not I.n:
            return
        from ..ledger import STATUS_ID
        m = (O["day"] == day) & (O["status"] == STATUS_ID["happened"]) & (O["organizer"] >= 0) & (O["n_came"] >= 3)
        if not m.any():
            return
        occ = O["id"][m]
        att = I["attended"] & np.isin(I["occ"], occ)
        ao, ap = I["occ"][att].astype(np.int64), I["person"][att].astype(np.int64)
        invited = np.isin(I["occ"], occ)
        inv_key = np.unique((I["occ"][invited].astype(np.int64) << 24) | I["person"][invited].astype(np.int64))
        net = sim.systems["network"]
        indptr, nbr, _ = net.padded(net.adj_close)
        deg = indptr[ap + 1] - indptr[ap]
        rep = np.repeat(np.arange(len(ap)), deg)
        if not len(rep):
            return
        off = np.arange(len(rep)) - np.repeat(np.cumsum(deg) - deg, deg)
        friend = nbr[indptr[ap[rep]] + off]
        o = ao[rep]
        k = (o << 24) | friend
        k = k[~np.isin(k, inv_key)]                                  # not invited (and so not there)
        uk, cnt = np.unique(k, return_counts=True)
        sel = uk[cnt >= int(p("messaging.leftout.min_friends"))]
        if not len(sel):
            return
        o, x = sel >> 24, sel & 0xFFFFFF
        org = O.get("organizer", o, default=-1).astype(np.int64)
        ok = P["present"][x].astype(bool) & (x != org) & (org >= 0)
        o, x, org = o[ok], x[ok], org[ok]
        if not len(o):
            return
        shared = self.shared_thread(x, org) >= 0
        pr = np.where(shared, p("messaging.leftout.via_chat"), p("messaging.leftout.via_news"))
        u = sim.streams.uniform("msg_leftout", day, len(o))
        f = u < pr
        if not f.any():
            return
        o, x, org, shared = o[f], x[f], org[f], shared[f]
        ev = sim.emit("left_out", x, b=org, mech="messaging.leftout", block=3, causes=[("occasion", o, 1.0)])
        eix = E.find(EdgeStore.make_keys(x, org))
        okk = eix >= 0
        E.cols["hurt"][eix[okk]] = np.clip(E["hurt"][eix[okk]] + 0.06, 0, 1)
        # the host's side: they know this person but aren't close, and didn't think they'd want to come
        okk_i = np.maximum(eix, 0)
        thought = okk & (E["stage"][okk_i] >= 2) & (E["closeness"][okk_i] < 0.35)
        if thought.any():
            ev2 = sim.emit("assumed_not_interested", org[thought], b=x[thought], mech="messaging.leftout", block=3,
                           causes=[("occasion", o[thought], 1.0)])
            link(sim, ev2, "event", ev[thought], 1.0, "mirror")

    # ------------------------------------------------------------------ news and knowledge
    def _news(self, day: int):
        sim, w = self.sim, self.sim.w
        P, p = w.P, sim.p
        log = sim.log
        if log.n > self._log_seen:
            rows = np.arange(self._log_seen, log.n)
            types = np.array([sim.reg.event_ids.get(t, -1) for t in NEWS])
            priv = np.array(list(NEWS.values()))
            hit = np.isin(log["type"][rows], types[types >= 0])
            rows = rows[hit]
            if len(rows):
                a = log["a"][rows].astype(np.int64)
                lut = np.full(max(types.max() + 1, 1), 0.0)
                lut[types[types >= 0]] = priv[types >= 0]
                pv = lut[log["type"][rows]]
                T = {"privacy": -p("messaging.news.privacy") * pv, "extraversion": 0.4 * sim.z("extraversion")[a],
                     "close_friends": 0.3 * np.log1p(P["n_close_friends"][a])}
                base = p("messaging.news.share_base")
                pr = expit(base + sum(T.values()))
                share = sim.streams.uniform("msg_share", day, len(a)) < pr
                for o in ("shared", "kept_private"):
                    s = share if o == "shared" else ~share
                    if s.any():
                        did = sim.decisions.record("share_news", day, a[s], o, {k: v[s] for k, v in T.items()}, base=base,
                                                   prob=np.where(share[s], pr[s], 1 - pr[s]))
                        del did
                self.know.add(a, rows, -1, day, CHANNEL_ID["in_person"])
                b = log["b"][rows].astype(np.int64)
                hb = b >= 0
                self.know.add(b[hb], rows[hb], a[hb], day, CHANNEL_ID["in_person"])
                L = self.live_news
                L["event"] = np.r_[L["event"], rows]
                L["subject"] = np.r_[L["subject"], a]
                L["day"] = np.r_[L["day"], np.full(len(rows), day, np.int32)]
                L["shared"] = np.r_[L["shared"], share]
                if share.any():          # posted to their friend-group chat
                    th = self._friend_thread(a[share])
                    ok = th >= 0
                    if ok.any():
                        self.acts.append(int(ok.sum()), thread=th[ok], day=day, block=3, sender=a[share][ok],
                                         kind=ACT_ID["news"], ref=rows[share][ok], event=rows[share][ok])
                        self._spread_chat(rows[share][ok], th[ok], a[share][ok], day)
            self._log_seen = log.n
        self._gossip(day)

    def _friend_thread(self, people: np.ndarray) -> np.ndarray:
        """Each person's friend-group chat (−1 if none)."""
        M, T = self.members, self.threads
        rows = np.flatnonzero((M["left"] < 0) & (T.get("kind", M["thread"], default=-1) == KIND_ID["friends"]))
        cur = np.full(self.sim.w.P.n, -1, np.int64)
        cur[M["person"][rows]] = M["thread"][rows]
        return cur[np.asarray(people, np.int64)]

    def _spread_chat(self, events, threads, senders, day):
        """News posted to a chat reaches the members who notice it."""
        M = self.members
        rows = np.flatnonzero((M["left"] < 0) & np.isin(M["thread"], threads))
        if not len(rows):
            return
        mt = M["thread"][rows].astype(np.int64)
        order = np.argsort(mt, kind="stable")
        rows, mt = rows[order], mt[order]
        lo = np.searchsorted(mt, threads, "left")
        hi = np.searchsorted(mt, threads, "right")
        cnt = hi - lo
        rep = np.repeat(np.arange(len(threads)), cnt)
        off = np.arange(len(rep)) - np.repeat(np.cumsum(cnt) - cnt, cnt)
        mem = M["person"][rows[lo[rep] + off]].astype(np.int64)
        keep = mem != senders[rep]
        rep, mem = rep[keep], mem[keep]
        u = self.sim.streams.uniform("msg_chatnews", day, len(mem))
        seen = u < self.notice_prob(mem, "group_chat", threads[rep], False)
        self.know.add(mem[seen], events[rep][seen], senders[rep][seen], day, CHANNEL_ID["group_chat"])

    def _gossip(self, day: int):
        """Knowers tell their close friends (the person it's about only when they chose to share)."""
        sim, w = self.sim, self.sim.w
        P, E, p = w.P, w.E, sim.p
        L = self.live_news
        live = day - L["day"] <= int(p("messaging.news.days"))
        for k in L:
            L[k] = L[k][live]
        if not len(L["event"]):
            return
        order = np.argsort(L["event"])
        ev_s, subj_s, sh_s = L["event"][order], L["subject"][order], L["shared"][order]
        K = self.know.t
        m = np.isin(K["event"][: K.n], ev_s)
        kp, ke = K["person"][: K.n][m].astype(np.int64), K["event"][: K.n][m].astype(np.int64)
        if not len(kp):
            return
        j = np.searchsorted(ev_s, ke)
        cnt = np.bincount(j, minlength=len(ev_s))
        is_subj = subj_s[j] == kp
        keep = (cnt[j] < int(p("messaging.news.cap"))) & ~(is_subj & ~sh_s[j]) & P["present"][kp].astype(bool)
        kp, ke, is_subj = kp[keep], ke[keep], is_subj[keep]
        net = sim.systems["network"]
        indptr, nbr, eidx = net.padded(net.adj_close)
        deg = indptr[kp + 1] - indptr[kp]
        rep = np.repeat(np.arange(len(kp)), deg)
        if not len(rep):
            return
        off = np.arange(len(rep)) - np.repeat(np.cumsum(deg) - deg, deg)
        at = indptr[kp[rep]] + off
        to = nbr[at]
        clos = E["closeness"][eidx[at]]
        rate = np.where(is_subj[rep], p("messaging.news.tell"), p("messaging.news.gossip"))
        u = sim.streams.uniform("msg_gossip", day, len(rep))
        go = (u < rate * (0.5 + clos)) & P["present"][to].astype(bool)
        if go.any():
            self.know.add(to[go], ke[rep][go], kp[rep][go], day, CHANNEL_ID["text"])

    # ------------------------------------------------------------------ threads
    def _sync(self, initial: bool):
        """Weekly: apartment, club, team and ward chats follow who lives and belongs where; friend-group chats follow
        clusters of close friends."""
        sim, w = self.sim, self.sim.w
        P = w.P
        n = P.n
        pres = P["present"][:n].astype(bool)
        if "trip_away" in P.internal:          # away on a trip home is not moving out
            pres = pres | P.internal["trip_away"][:n]
        for kind, col in (("household", "unit_id"), ("club", "club_id"), ("team", "team_id"), ("ward", "ward_id")):
            if col not in P.cols:
                continue
            g = P[col][:n].astype(np.int64)
            ok = pres & (g >= 0)
            if kind == "ward":
                ok &= P["lds_member"][:n].astype(bool) & (P["attend_rate"][:n] > 0.2)
            self._follow(kind, g, ok, initial, min_n=2)
        if "home_state" in P.cols:              # a family chat with the people back home (kin are off-map)
            self._follow("family", np.arange(n, dtype=np.int64), pres & (P["home_state"][:n] > 0), initial, min_n=1)
        self._friend_groups(initial)
        self._idx = None
        T, M = self.threads, self.members
        if T.n:
            live = M["thread"][M["left"] < 0].astype(np.int64)
            cnt = np.bincount(live, minlength=T.next_id) if len(live) else np.zeros(T.next_id, np.int64)
            T.cols["n"][: T.n] = cnt[T["id"]]
        if not initial:
            self._mute(w.day)

    def _thread_ids(self, kind: str, keys: np.ndarray, day: int, creator=None) -> np.ndarray:
        """Thread ids for (kind, key), creating the missing ones."""
        T = self.threads
        k = KIND_ID[kind]
        have = (T["kind"] == k) & T["active"]
        hk, hid = T["key"][have], T["id"][have]
        order = np.argsort(hk)
        hk, hid = hk[order], hid[order]
        out = np.full(len(keys), -1, np.int64)
        if len(hk):
            i = np.clip(np.searchsorted(hk, keys), 0, len(hk) - 1)
            f = hk[i] == keys
            out[f] = hid[i[f]]
        new = out < 0
        if new.any():
            out[new] = T.append(int(new.sum()), kind=k, key=keys[new], created_day=day,
                                creator=-1 if creator is None else creator[new])
        return out

    def _follow(self, kind: str, group: np.ndarray, ok: np.ndarray, initial: bool, min_n: int):
        sim, w = self.sim, self.sim.w
        day = w.day
        M = self.members
        people = np.flatnonzero(ok)
        g = group[people]
        ug, cnt = np.unique(g, return_counts=True)
        big = ug[cnt >= min_n]
        sel = np.isin(g, big)
        people, g = people[sel], g[sel]
        th = self._thread_ids(kind, np.unique(g), day)
        want_t = th[np.searchsorted(np.unique(g), g)] if len(g) else np.empty(0, np.int64)
        want = np.unique((want_t << 24) | people) if len(people) else np.empty(0, np.int64)
        cur_rows = np.flatnonzero((M["left"] < 0) & (self.threads.get("kind", M["thread"], default=-1) == KIND_ID[kind]))
        cur = (M["thread"][cur_rows].astype(np.int64) << 24) | M["person"][cur_rows].astype(np.int64)
        gone = cur_rows[~np.isin(cur, want)]
        add = want[~np.isin(want, cur)]
        if len(gone):
            M.cols["left"][gone] = day
            if not initial:
                lp = M["person"][gone].astype(np.int64)
                pr = sim.w.P["present"][lp].astype(bool)
                if pr.any() and kind in ("household", "club", "team"):
                    sim.emit("left_chat", lp[pr], mech="messaging.chat", value=float(KIND_ID[kind]))
        if len(add):
            M.append(len(add), thread=add >> 24, person=add & 0xFFFFFF, joined=day)
            if not initial and kind in ("household", "club", "team"):
                sim.emit("added_to_chat", (add & 0xFFFFFF), mech="messaging.chat", value=float(KIND_ID[kind]))

    def _communities(self) -> np.ndarray:
        """Label propagation on the close-friend graph (closeness-weighted, ties to the smaller label)."""
        sim, w = self.sim, self.sim.w
        P, E = w.P, w.E
        net = sim.systems["network"]
        indptr, nbr, eidx = net.padded(net.adj_close)
        n = P.n
        pres = P["present"][:n].astype(bool)
        lab = np.arange(n, dtype=np.int64)
        deg = np.diff(indptr)[:n]
        src = np.repeat(np.arange(n), deg)
        dst = nbr[: len(src)].astype(np.int64)
        wt = E["closeness"][eidx[: len(src)]].astype(float)
        ok = pres[src] & pres[dst]
        src, dst, wt = src[ok], dst[ok], wt[ok]
        for _ in range(6):
            s = np.r_[src, np.arange(n)]
            l_ = np.r_[lab[dst], lab]
            ww = np.r_[wt, np.full(n, 0.5)]
            key, inv = np.unique(s * n + l_, return_inverse=True)
            tot = np.bincount(inv.ravel(), weights=ww)
            node, cand = key // n, key % n
            order = np.lexsort((cand, -tot, node))
            first = np.unique(node[order], return_index=True)[1]
            lab[node[order][first]] = cand[order][first]
        lab[~pres | (np.diff(indptr)[:n] < 2)] = -1
        return lab

    def _friend_groups(self, initial: bool):
        sim, w = self.sim, self.sim.w
        P, E, p = w.P, w.E, sim.p
        day = w.day
        M, T = self.members, self.threads
        lab = self._communities()
        ul, cnt = np.unique(lab[lab >= 0], return_counts=True)
        ok_l = ul[(cnt >= 3) & (cnt <= 15)]
        people = np.flatnonzero(np.isin(lab, ok_l))
        comm = lab[people]
        # each person's current friend-group chat
        fr_rows = np.flatnonzero((M["left"] < 0) & (T.get("kind", M["thread"], default=-1) == KIND_ID["friends"]))
        cur_t = np.full(P.n, -1, np.int64)
        cur_t[M["person"][fr_rows]] = M["thread"][fr_rows]
        # match each community to the chat most of its members are in
        pairs = np.c_[comm, cur_t[people]]
        pairs = pairs[pairs[:, 1] >= 0]
        match: dict[int, int] = {}
        if len(pairs):
            up, pc = np.unique(pairs, axis=0, return_counts=True)
            order = np.argsort(-pc, kind="stable")
            used = set()
            sizes = dict(zip(ul.tolist(), cnt.tolist()))
            for (c, t), k in zip(up[order].tolist(), pc[order].tolist()):
                if c in match or t in used or k < 2 or k < 0.5 * sizes.get(c, 99):
                    continue
                match[c], used = t, used | {t}
            # a group that changed shape keeps the chat most of its members already share (no new chat for a reshuffle)
            for (c, t), k in zip(up[order].tolist(), pc[order].tolist()):
                if c not in match and t not in used and k >= 2:
                    match[c], used = t, used | {t}
        rng = sim.streams.gen("msg_groups", day)
        cl = np.array(sorted(match), np.int64)
        mt = np.array([match[c] for c in cl.tolist()], np.int64)
        # ---- new group chats: the best-connected member starts it and adds the others
        new_c = ok_l[~np.isin(ok_l, cl)]
        inn = np.isin(comm, new_c)
        np_, nc = people[inn], comm[inn]
        joins_p, joins_t = [np.empty(0, np.int64)], [np.empty(0, np.int64)]
        if len(np_):
            order = np.argsort(nc, kind="stable")
            np_, nc = np_[order], nc[order]
            uc, start, size = np.unique(nc, return_index=True, return_counts=True)
            g = np.repeat(np.arange(len(uc)), size * size)               # every ordered pair inside each group
            off = np.arange(len(g)) - np.repeat(np.cumsum(size * size) - size * size, size * size)
            i_ = start[g] + off // size[g]
            j_ = start[g] + off % size[g]
            eix = E.find(EdgeStore.make_keys(np_[i_], np_[j_]))
            clos = np.where((eix >= 0) & (i_ != j_), E["closeness"][np.maximum(eix, 0)], 0.0)
            tot = np.bincount(i_, weights=clos, minlength=len(np_))
            best = np.lexsort((-tot, nc))
            creator_pos = best[np.unique(nc[best], return_index=True)[1]]
            creators = np_[creator_pos]
            tids = T.append(len(uc), kind=KIND_ID["friends"], key=T.next_id + np.arange(len(uc)), created_day=day, creator=creators)
            gi = np.searchsorted(uc, nc)
            joins_p.append(np_)
            joins_t.append(tids[gi])
            if not initial:
                ev = sim.emit("group_chat_started", creators, mech="messaging.chat", value=size.astype(float))
                others = np_ != creators[gi]
                op, og = np_[others], gi[others]
                e2 = E.find(EdgeStore.make_keys(creators[og], op))
                c2 = np.where(e2 >= 0, E["closeness"][np.maximum(e2, 0)], 0.0)
                did = sim.decisions.record("add_to_chat", day, creators[og], "added",
                                           {"closeness": 2.0 * c2, "in_the_group": np.ones(len(op))}, base=0.0, other=op)
                sim.emit("added_to_chat", op, b=creators[og], mech="messaging.chat", value=float(KIND_ID["friends"]),
                         decision=did, cause=ev[og])
        # ---- existing chats: newcomers join; people who drifted out of the group may leave
        if len(cl):
            inm = np.isin(comm, cl)
            mp, mc = people[inm], comm[inm]
            mth = mt[np.searchsorted(cl, mc)]
            live = (M["left"] < 0) & np.isin(M["thread"], mt)
            have_k = (M["thread"][live].astype(np.int64) << 24) | M["person"][live].astype(np.int64)
            want_k = (mth << 24) | mp
            newbies = ~np.isin(want_k, have_k)
            joins_p.append(mp[newbies])
            joins_t.append(mth[newbies])
            if newbies.any() and not initial:
                sim.emit("added_to_chat", mp[newbies], mech="messaging.chat", value=float(KIND_ID["friends"]))
            drift_rows = np.flatnonzero(live)[~np.isin(have_k, want_k)]
            if len(drift_rows) and not initial:
                dp = M["person"][drift_rows].astype(np.int64)
                dt = M["thread"][drift_rows].astype(np.int64)
                # mean closeness to the group the chat now follows
                order = np.argsort(mth, kind="stable")
                gm, gt = mp[order], mth[order]
                lo_ = np.searchsorted(gt, dt, "left")
                cnt = np.searchsorted(gt, dt, "right") - lo_
                rep = np.repeat(np.arange(len(dp)), cnt)
                off = np.arange(len(rep)) - np.repeat(np.cumsum(cnt) - cnt, cnt)
                e3 = E.find(EdgeStore.make_keys(dp[rep], gm[lo_[rep] + off]))
                c3 = np.where(e3 >= 0, E["closeness"][np.maximum(e3, 0)], 0.0)
                clos = np.bincount(rep, weights=c3, minlength=len(dp)) / np.maximum(cnt, 1)
                TL = {"drifted": p("messaging.chat.drift") * (0.3 - clos)}
                base = p("messaging.chat.leave_base")
                pr = expit(base + TL["drifted"])
                go = rng.random(len(dp)) < pr
                if go.any():
                    did = sim.decisions.record("leave_chat", day, dp[go], "left", {"drifted": TL["drifted"][go]}, base=base,
                                               prob=pr[go])
                    M.cols["left"][drift_rows[go]] = day
                    sim.emit("left_chat", dp[go], mech="messaging.chat", value=float(KIND_ID["friends"]), decision=did)
        jp, jt = np.concatenate(joins_p), np.concatenate(joins_t)
        if len(jp):
            # one friend-group chat at a time: joining this one means leaving the old one (the group split)
            cur_rows = np.flatnonzero((M["left"] < 0) & np.isin(M["person"], jp)
                                      & (T.get("kind", M["thread"], default=-1) == KIND_ID["friends"]))
            new_of = np.full(P.n, -1, np.int64)
            new_of[jp] = jt
            M.cols["left"][cur_rows[M["thread"][cur_rows] != new_of[M["person"][cur_rows]]]] = day
            M.append(len(jp), thread=jt, person=jp, joined=day)
        # chats left with fewer than two members go quiet
        fr = np.flatnonzero((T["kind"] == KIND_ID["friends"]) & T["active"])
        if len(fr):
            live = M["thread"][M["left"] < 0].astype(np.int64)
            cnt = np.bincount(live, minlength=T.next_id) if len(live) else np.zeros(T.next_id, np.int64)
            quiet = fr[cnt[T["id"][fr]] < 2]
            T.cols["active"][quiet] = False
            M.cols["left"][np.flatnonzero((M["left"] < 0) & np.isin(M["thread"], T["id"][quiet]))] = day

    def _mute(self, day: int):
        """People quietly mute busy chats they barely care about (ward and club chats, mostly)."""
        sim = self.sim
        M, T = self.members, self.threads
        live = np.flatnonzero((M["left"] < 0) & ~M["muted"])
        if not len(live):
            return
        vol = T.get("volume", M["thread"][live], default=0.0)
        kind = T.get("kind", M["thread"][live], default=0)
        big = np.isin(kind, [KIND_ID["ward"], KIND_ID["club"], KIND_ID["team"]])
        pr = expit(sim.p("messaging.chat.mute_base") + 0.05 * vol) * big
        u = sim.streams.uniform("msg_mute", day, len(live))
        m = u < pr
        if m.any():
            M.cols["muted"][live[m]] = True
            sim.emit("muted_chat", M["person"][live[m]].astype(np.int64), mech="messaging.chat", value=kind[m].astype(float))

    def _thin(self, day: int):
        keep_days = getattr(self.sim, "detail_days", 120)
        A = self.acts
        if A.n:
            A.keep((A["day"] >= day - keep_days) | (A["kind"] == ACT_ID["news"]))
        M = self.members
        if M.n:
            M.keep((M["left"] < 0) | (M["left"] >= day - keep_days))
        K = self.know.t
        if K.n and K.keep(K["day"] >= day - keep_days):
            self.know._keys = np.sort(self.know.key(K["event"][: K.n], K["person"][: K.n]))
        self._idx = None

    # ------------------------------------------------------------------ reading
    def thread_name(self, t: int) -> str:
        w = self.sim.w
        T = self.threads
        k = KINDS[int(T.get("kind", [t], default=0)[0])]
        key = int(T.get("key", [t], default=-1)[0])
        try:
            if k == "household":
                P = w.P
                who = np.flatnonzero((P["unit_id"] == key) & P["present"])
                cx = int(P["complex_id"][who[0]]) if len(who) else -1
                return f"Apartment chat ({w.complexes['name'][cx]})" if cx >= 0 else "Apartment chat"
            if k in ("club", "team"):
                return f"{w.groups['name'][key]} chat"
            if k == "ward":
                return f"{ward_name(w.wards, key)} chat"
        except Exception:  # noqa: BLE001
            pass
        return {"friends": "Friend group chat", "family": "Family chat"}.get(k, f"{k.title()} chat")
