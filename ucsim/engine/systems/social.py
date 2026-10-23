"""Social exchanges: what people say to each other, how each side reads it, what they come to believe about each
other and what stays unresolved — the semantic layer under conversations, phones and dating apps.

Design notes (parameters in config/mechanisms/21_social.yaml, decisions in config/decisions/55_social.yaml)
* One typed record for every channel (`ExchangeLog`): in person, by text, in a group chat, on a dating app. A row is a
  *communicative act* from a small vocabulary (ACTS) by a speaker to a person (or a whole chat), about a topic that
  points at a real thing (an occasion, an earlier message, an event), with the decision behind it, what the speaker
  kept to themselves (`withheld`), how ambiguous it was, and an as-of snapshot of the tie and both moods (so an old
  exchange is never explained with today's numbers). The words are not stored: they are realized on demand
  (analysis/dialogue.py) and may never add a consequential fact.
* Each participant's reading of an exchange (`ReadLog`): busy, not interested, excluded, ignored, support, warm,
  ambiguous… with a confidence. Readings come from evidence the reader has (how often this person declined lately,
  whether they explained, whether they usually answer), not from a fresh coin per message.
* Specific beliefs about a particular person (`BeliefStore`), sparse and capped: "they're not interested in coming",
  "they left me out on purpose", "they think I'm not interested" (one level of what-they-think-of-me), "they're just
  busy", "they're ignoring me". A belief has evidence, a confidence that fades without new evidence, and is revised by
  a clarification or a late reply. Beliefs change behavior: a host who believes someone isn't interested invites them
  less (occasions._invite); someone who thinks they were left out deliberately is more likely to withdraw.
* Open situations (`ConcernLedger`): an unanswered text read as being ignored, being left out, a "next time for sure"
  promise. They persist across days, change later choices (who raises what, who comes next time, who stops texting)
  and end clarified, repaired, fulfilled, missed, renegotiated, worsened, let go or lapsed — for a recorded reason.
* Dating apps (`AppThreads`): a match becomes a short conversation — an opener, a reply (now, late or never), some
  chatting, an invitation or a fade — and only an accepted invitation books a date, through romance's own date queue.

Recording draws no random numbers. New behavioral draws use `Streams.keyed_uniform` with names of their own, keyed on
the people involved, so a What-if shares them pair by pair and watching anything never moves a draw.
"""
from __future__ import annotations

import numpy as np
from scipy.special import expit

from ..ledger import CAUSE_ID, CHANNEL_ID, RESPONSE_ID, Table
from ..state import CTX_ID, EdgeStore, Tie

# ----------------------------------------------------------------------------------------------------- vocabularies
ACTS = ("small_talk", "coordinate", "invite", "accept", "decline_explained", "decline_brief", "checkin", "reply",
        "late_reply", "no_reply", "disclose", "deflect", "support", "ask_clarify", "clarify", "reassure", "apologize",
        "withdraw", "avoid", "warm_moment", "tension", "introduce", "opener", "app_reply", "app_chat", "ask_date",
        "date_yes", "date_no", "fade", "catch_up", "promise")
ACT = {k: i for i, k in enumerate(ACTS)}
# acts that are an absence, not something said (a silence is never shown as a message the silent person sent)
ABSENT = {"no_reply", "withdraw", "avoid", "fade"}
TOPICS = ("none", "class", "work", "home", "church", "occasion", "plans", "weather", "exam", "date", "app", "struggle",
          "declines", "left_out", "silence", "outing", "fitness", "team", "club", "relationship", "news", "match")
TOPIC = {k: i for i, k in enumerate(TOPICS)}
READS = ("none", "busy", "not_interested", "excluded", "ignored", "support", "warm", "ambiguous", "obligation",
         "rejection", "unknown", "relief", "interest", "polite")
READ = {k: i for i, k in enumerate(READS)}
PROPS = ("not_interested", "excluded_me", "thinks_im_not_interested", "busy", "ignoring_me", "cares", "interested")
PROP = {k: i for i, k in enumerate(PROPS)}
# forming one of these retires the active ones it contradicts (about the same person)
CONTRA = {"busy": ("not_interested", "ignoring_me"), "not_interested": ("busy",), "ignoring_me": ("busy", "cares"),
          "excluded_me": ("thinks_im_not_interested",), "thinks_im_not_interested": ("excluded_me",),
          "cares": ("ignoring_me", "excluded_me"), "interested": ("not_interested",)}
CONCERNS = ("unanswered", "left_out", "promise", "misread", "app_waiting")
CONCERN = {k: i for i, k in enumerate(CONCERNS)}
STATUS = ("open", "clarified", "repaired", "fulfilled", "missed", "renegotiated", "worsened", "let_go", "lapsed",
          "abandoned")
CSTAT = {k: i for i, k in enumerate(STATUS)}
STANCES = ("none", "waiting", "withdrew", "raised", "checked_in", "asked")
STANCE = {k: i for i, k in enumerate(STANCES)}
# why someone said no (stored on the invitation; the decision has the full factors)
WHY = ("none", "work", "class", "clash", "ill", "far", "tired", "exam", "partner", "hurt", "not_feeling_it")
WHY_ID = {k: i for i, k in enumerate(WHY)}
# intents: what the speaker was trying to do with the act
INTENTS = ("none", "connect", "inform", "decline_gently", "keep_door_open", "check_on", "get_support", "give_support",
           "understand", "repair", "protect_self", "spare_feelings", "flirt", "test_interest", "end_it", "coordinate",
           "keep_private")
INTENT = {k: i for i, k in enumerate(INTENTS)}
APP_STAGES = ("matched", "opened", "chatting", "asked", "date_set", "declined", "unanswered", "ghosted", "faded",
              "no_opener", "closed", "offline")
APP = {k: i for i, k in enumerate(APP_STAGES)}
SOCIAL_KINDS = ("dinner", "gathering", "game_night", "party", "movie_night", "hangout", "study_group")
DIRECT = 1 << 24


def pkey(a, b) -> np.ndarray:
    """Directed pair key (a's view of b)."""
    return (np.asarray(a, np.int64) << 24) | (np.asarray(b, np.int64) & 0xFFFFFF)


def ukey(a, b) -> np.ndarray:
    """Undirected pair key (the same from both phones)."""
    a, b = np.asarray(a, np.int64), np.asarray(b, np.int64)
    return (np.minimum(a, b) << 24) | (np.maximum(a, b) & 0xFFFFFF)


# ----------------------------------------------------------------------------------------------------------- ledgers
class ExchangeLog:
    """Every recorded exchange, whatever the channel (see the module docstring)."""

    def __init__(self):
        f16 = (np.float16, np.nan)
        self.t = Table({"day": (np.int32, -1), "block": (np.int8, 0), "channel": (np.int8, 0), "thread": (np.int64, -1),
                        "pair": (np.int64, -1), "speaker": (np.int32, -1), "to": (np.int32, -1), "act": (np.int8, -1),
                        "topic": (np.int8, 0), "ref": (np.int64, -1), "ref_kind": (np.int8, -1),
                        "reply_to": (np.int64, -1), "decision": (np.int64, -1), "event": (np.int64, -1),
                        "intent": (np.int8, 0), "withheld": (np.int8, 0), "said": (np.int8, 0), "ambig": f16,
                        "tone": f16, "clos": f16, "hurt": f16, "trust": f16, "mood_s": f16, "mood_r": f16,
                        "concern": (np.int64, -1), "place": (np.int64, -1), "ctx": (np.int8, -1),
                        "conv": (np.int64, -1), "keep": (np.bool_, False),
                        # the messaging act that carried it (a check-in, a reply) and the invitation it answers
                        "msg": (np.int64, -1), "inv": (np.int64, -1)}, capacity=1 << 12)

    def add(self, sim, k: int, *, speaker, to, act, channel="in_person", day=None, block=3, snap=True, **cols) -> np.ndarray:
        """Append k exchanges with an as-of snapshot of the speaker–recipient tie and both moods."""
        k = int(k)
        if k <= 0:
            return np.empty(0, np.int64)
        P, E = sim.w.P, sim.w.E
        s = np.broadcast_to(np.asarray(speaker, np.int64), (k,))
        r = np.broadcast_to(np.asarray(to, np.int64), (k,))
        a = np.broadcast_to(np.asarray([ACT[x] for x in act] if isinstance(act, (list, tuple)) else ACT[act], np.int8)
                            if not isinstance(act, np.ndarray) else act.astype(np.int8), (k,))
        ch = CHANNEL_ID[channel] if isinstance(channel, str) else np.asarray(channel, np.int8)
        extra = {}
        if snap:
            has = r >= 0
            e = np.full(k, -1, np.int64)
            if has.any():
                e[has] = E.find(EdgeStore.make_keys(s[has], r[has]))
            ok = e >= 0
            ei = np.maximum(e, 0)
            for c in ("closeness", "hurt", "trust"):
                extra[{"closeness": "clos"}.get(c, c)] = np.where(ok, E[c][ei] if E.n else 0, np.nan)
            extra["mood_s"] = P["mood"][s]
            extra["mood_r"] = np.where(has, P["mood"][np.maximum(r, 0)], np.nan)
        pair = np.where(r >= 0, ukey(s, np.maximum(r, 0)), -1)
        return self.t.append(k, day=sim.w.day if day is None else day, block=block, channel=ch, speaker=s, to=r, act=a,
                             pair=pair, **extra, **cols)

    def between(self, a: int, b: int) -> np.ndarray:
        """Row positions of the direct exchanges between two people (either direction), in order."""
        return np.flatnonzero(self.t["pair"] == int(ukey(a, b)))

    def of(self, i: int) -> np.ndarray:
        return np.flatnonzero((self.t["speaker"] == i) | (self.t["to"] == i))


class ReadLog:
    """How each participant read an exchange."""

    def __init__(self):
        self.t = Table({"ex": (np.int64, -1), "reader": (np.int32, -1), "read": (np.int8, 0), "conf": (np.float16, 0.0),
                        "expected": (np.int8, 0), "belief": (np.int64, -1), "day": (np.int32, -1)}, capacity=1 << 12)

    def add(self, ex, reader, read, conf, day, expected=0, belief=-1) -> np.ndarray:
        ex = np.atleast_1d(np.asarray(ex, np.int64))
        r = np.asarray([READ[x] for x in read], np.int8) if isinstance(read, (list, tuple)) else \
            (np.asarray(read, np.int8) if not isinstance(read, str) else READ[read])
        return self.t.append(len(ex), ex=ex, reader=reader, read=r, conf=conf, day=day, expected=expected, belief=belief)

    def of(self, ex_ids) -> np.ndarray:
        return np.flatnonzero(np.isin(self.t["ex"], np.atleast_1d(np.asarray(ex_ids, np.int64))))


class BeliefStore:
    """Sparse, capped beliefs about particular people (owner, about, proposition, confidence, evidence)."""

    def __init__(self):
        self.t = Table({"owner": (np.int32, -1), "about": (np.int32, -1), "prop": (np.int8, -1), "conf": (np.float32, 0.0),
                        "formed": (np.int32, -1), "updated": (np.int32, -1), "evidence": (np.int64, -1),
                        "revised_by": (np.int64, -1), "revised_day": (np.int32, -1), "active": (np.bool_, True),
                        "first_conf": (np.float32, 0.0)}, capacity=1 << 11)
        self._idx = None

    def _key(self, owner, about, prop) -> np.ndarray:
        return (pkey(owner, about) << 3) | np.asarray(prop, np.int64)

    def _index(self):
        if self._idx is None:
            T = self.t
            act = np.flatnonzero(T["active"])
            k = self._key(T["owner"][act], T["about"][act], T["prop"][act])
            o = np.argsort(k, kind="stable")
            self._idx = (k[o], act[o])
        return self._idx

    def find(self, owner, about, prop) -> np.ndarray:
        """Row of the active belief (−1 if none)."""
        owner = np.atleast_1d(np.asarray(owner, np.int64))
        k = self._key(owner, np.broadcast_to(np.asarray(about, np.int64), owner.shape),
                      np.broadcast_to(np.asarray(prop if not isinstance(prop, str) else PROP[prop], np.int64), owner.shape))
        keys, rows = self._index()
        if not len(keys):
            return np.full(len(k), -1, np.int64)
        i = np.clip(np.searchsorted(keys, k), 0, len(keys) - 1)
        return np.where(keys[i] == k, rows[i], -1)

    def conf(self, owner, about, prop) -> np.ndarray:
        r = self.find(owner, about, prop)
        return np.where(r >= 0, self.t.cols["conf"][np.maximum(r, 0)], 0.0)

    def believe(self, owner, about, prop: str, conf, day: int, evidence=-1) -> np.ndarray:
        """Form or strengthen a belief; contradicting active beliefs about the same person are revised by `evidence`.
        Returns the belief ids."""
        owner = np.atleast_1d(np.asarray(owner, np.int64))
        k = len(owner)
        if not k:
            return np.empty(0, np.int64)
        about = np.broadcast_to(np.asarray(about, np.int64), (k,))
        conf = np.broadcast_to(np.asarray(conf, np.float32), (k,))
        evidence = np.broadcast_to(np.asarray(evidence, np.int64), (k,))
        for c in CONTRA.get(prop, ()):
            self.revise(owner, about, c, day, evidence)
        T = self.t
        r = self.find(owner, about, prop)
        have = r >= 0
        out = np.empty(k, np.int64)
        if have.any():
            rr = r[have]
            old = T.cols["conf"][rr]
            T.cols["conf"][rr] = np.maximum(old, conf[have]) + 0.25 * np.minimum(old, conf[have]) * (1 - np.maximum(old, conf[have]))
            T.cols["updated"][rr] = day
            T.cols["evidence"][rr] = evidence[have]
            out[have] = T.ids[rr]
        new = ~have
        if new.any():
            # one row per (owner, about) in this batch
            kk = self._key(owner[new], about[new], PROP[prop])
            _, first = np.unique(kk, return_index=True)
            sel = np.flatnonzero(new)[first]
            ids = T.append(len(sel), owner=owner[sel], about=about[sel], prop=PROP[prop], conf=conf[sel], formed=day,
                           updated=day, evidence=evidence[sel], first_conf=conf[sel])
            self._idx = None
            r2 = self.find(owner[new], about[new], prop)
            out[new] = np.where(r2 >= 0, T.ids[np.maximum(r2, 0)], -1)
            del ids
        return out

    def revise(self, owner, about, prop: str, day: int, by=-1) -> np.ndarray:
        """Retire active beliefs (a clarification, a late reply, evidence the other way). Returns the revised ids."""
        r = self.find(owner, about, prop)
        ok = r >= 0
        if not ok.any():
            return np.empty(0, np.int64)
        T = self.t
        rr = r[ok]
        T.cols["active"][rr] = False
        T.cols["revised_by"][rr] = np.broadcast_to(np.asarray(by, np.int64), r.shape)[ok]
        T.cols["revised_day"][rr] = day
        self._idx = None
        return T.ids[rr]

    def fade(self, day: int, half_life: float, cap: int):
        """Weekly: beliefs fade without new evidence; the weakest go when someone holds more than `cap`."""
        T = self.t
        a = np.flatnonzero(T["active"])
        if not len(a):
            return
        age = np.maximum(day - T.cols["updated"][a], 0)
        T.cols["conf"][a] = T.cols["conf"][a] * np.exp(-np.log(2) * np.minimum(age, 7) / max(half_life, 1.0))
        gone = a[T.cols["conf"][a] < 0.12]
        own = T.cols["owner"][a]
        o = np.lexsort((-T.cols["conf"][a], own))
        so = own[o]
        start = np.r_[0, np.flatnonzero(np.diff(so)) + 1]
        rank = np.arange(len(so)) - np.repeat(start, np.diff(np.r_[start, len(so)]))
        gone = np.union1d(gone, a[o][rank >= cap])
        if len(gone):
            T.cols["active"][gone] = False
            T.cols["revised_day"][gone] = day
            self._idx = None

    def of(self, i: int, active_only=False) -> np.ndarray:
        m = (self.t["owner"] == i) | (self.t["about"] == i)
        if active_only:
            m &= self.t["active"]
        return np.flatnonzero(m)


class ConcernLedger:
    """Open situations between two people that later choices can resolve, worsen or let lapse."""

    def __init__(self):
        self.t = Table({"owner": (np.int32, -1), "other": (np.int32, -1), "kind": (np.int8, -1), "ref": (np.int64, -1),
                        "ref_kind": (np.int8, -1), "evidence": (np.int64, -1), "importance": (np.float32, 0.0),
                        "opened": (np.int32, -1), "deadline": (np.int32, -1), "status": (np.int8, 0),
                        "stance": (np.int8, 0), "resolved_day": (np.int32, -1), "resolved_by": (np.int64, -1),
                        "belief": (np.int64, -1), "acted_day": (np.int32, -1)}, capacity=1 << 11)
        self._idx = None

    def _index(self):
        if self._idx is None:
            T = self.t
            o = np.flatnonzero(T["status"] == CSTAT["open"])
            k = (pkey(T["owner"][o], T["other"][o]) << 3) | T["kind"][o].astype(np.int64)
            s = np.argsort(k, kind="stable")
            u = ukey(T["owner"][o], T["other"][o])
            su = np.argsort(u, kind="stable")
            self._idx = (k[s], o[s], u[su], o[su])
        return self._idx

    def find(self, owner, other, kind: str) -> np.ndarray:
        owner = np.atleast_1d(np.asarray(owner, np.int64))
        k = (pkey(owner, np.broadcast_to(np.asarray(other, np.int64), owner.shape)) << 3) | CONCERN[kind]
        keys, rows, _, _ = self._index()
        if not len(keys):
            return np.full(len(k), -1, np.int64)
        i = np.clip(np.searchsorted(keys, k), 0, len(keys) - 1)
        return np.where(keys[i] == k, rows[i], -1)

    def between_mask(self, a, b) -> np.ndarray:
        """Which pairs have any open concern (either way round)."""
        _, _, u, _ = self._index()
        k = ukey(a, b)
        if not len(u):
            return np.zeros(len(k), bool)
        i = np.clip(np.searchsorted(u, k), 0, len(u) - 1)
        return u[i] == k

    def open(self, owner, other, kind: str, day: int, *, importance, deadline, ref=-1, ref_kind=-1, evidence=-1,
             belief=-1) -> np.ndarray:
        """Open concerns (an open one of the same kind between the same people is kept and made more important)."""
        owner = np.atleast_1d(np.asarray(owner, np.int64))
        k = len(owner)
        if not k:
            return np.empty(0, np.int64)
        other = np.broadcast_to(np.asarray(other, np.int64), (k,))
        importance = np.broadcast_to(np.asarray(importance, np.float32), (k,))
        r = self.find(owner, other, kind)
        T = self.t
        out = np.empty(k, np.int64)
        have = r >= 0
        if have.any():
            rr = r[have]
            T.cols["importance"][rr] = np.minimum(1.0, T.cols["importance"][rr] + 0.5 * importance[have])
            T.cols["deadline"][rr] = np.maximum(T.cols["deadline"][rr], np.broadcast_to(np.asarray(deadline, np.int64), (k,))[have])
            out[have] = T.ids[rr]
        new = np.flatnonzero(~have)
        if len(new):
            kk = pkey(owner[new], other[new])
            _, first = np.unique(kk, return_index=True)
            sel = new[first]
            bc = lambda v: np.broadcast_to(np.asarray(v, np.int64), (k,))[sel]   # noqa: E731
            ids = T.append(len(sel), owner=owner[sel], other=other[sel], kind=CONCERN[kind], ref=bc(ref),
                           ref_kind=bc(ref_kind), evidence=bc(evidence), importance=importance[sel], opened=day,
                           deadline=bc(deadline), belief=bc(belief))
            self._idx = None
            lut = dict(zip(kk[first].tolist(), ids.tolist()))
            out[new] = [lut[x] for x in kk.tolist()]
        return out

    def close(self, ids, status: str, day: int, by=-1):
        ids = np.atleast_1d(np.asarray(ids, np.int64))
        by = np.broadcast_to(np.asarray(by, np.int64), ids.shape)
        p = self.t.pos(ids)
        ok = p >= 0
        ok[ok] &= self.t.cols["status"][p[ok]] == CSTAT["open"]
        if not ok.any():
            return
        T = self.t
        T.cols["status"][p[ok]] = CSTAT[status]
        T.cols["resolved_day"][p[ok]] = day
        T.cols["resolved_by"][p[ok]] = by[ok]
        self._idx = None

    def of(self, i: int) -> np.ndarray:
        return np.flatnonzero((self.t["owner"] == i) | (self.t["other"] == i))


class AppThreads:
    """Dating-app conversations: one row per match, moving through APP_STAGES."""

    def __init__(self):
        self.t = Table({"a": (np.int32, -1), "b": (np.int32, -1), "matched": (np.int32, -1), "match_event": (np.int64, -1),
                        "stage": (np.int8, 0), "opener": (np.int32, -1), "opened_day": (np.int32, -1),
                        "replied_day": (np.int32, -1), "last_day": (np.int32, -1), "last_by": (np.int32, -1),
                        "n_msgs": (np.int16, 0), "chat_days": (np.int16, 0), "asker": (np.int32, -1),
                        "date_day": (np.int32, -1), "ended_day": (np.int32, -1), "ended_by": (np.int32, -1),
                        "mutual": (np.bool_, False), "reply_due": (np.int32, -1)}, capacity=1 << 10)

    def live(self) -> np.ndarray:
        s = self.t["stage"]
        return np.flatnonzero(s <= APP["asked"])

    def of(self, i: int) -> np.ndarray:
        return np.flatnonzero((self.t["a"] == i) | (self.t["b"] == i))


# ------------------------------------------------------------------------------------------------------------ system
class Social:
    def __init__(self, sim):
        self.sim = sim
        self.ex = ExchangeLog()
        self.reads = ReadLog()
        self.beliefs = BeliefStore()
        self.concerns = ConcernLedger()
        self.app = AppThreads()
        self._decl = None            # (day, sorted keys inviter<<24|person, brief counts, explained counts)
        self._conv_next = 0

    def init(self):
        pass

    # ------------------------------------------------------------------ helpers
    def _u(self, name: str, a, b) -> np.ndarray:
        return self.sim.streams.keyed_uniform(name, self.sim.w.day, np.asarray(a, np.int64), np.asarray(b, np.int64))

    def _tie(self, a, b) -> tuple[np.ndarray, np.ndarray]:
        E = self.sim.w.E
        e = E.find(EdgeStore.make_keys(np.asarray(a, np.int64), np.asarray(b, np.int64)))
        return e, e >= 0

    def _col(self, col: str, a, b, default=0.0) -> np.ndarray:
        E = self.sim.w.E
        e, ok = self._tie(a, b)
        return np.where(ok, E[col][np.maximum(e, 0)] if E.n else default, default)

    def _conv(self, k: int) -> np.ndarray:
        """Conversation ids (exchanges that belong together share one)."""
        out = np.arange(self._conv_next, self._conv_next + k, dtype=np.int64)
        self._conv_next += k
        return out

    def declines_recent(self, inviter, person) -> tuple[np.ndarray, np.ndarray]:
        """How many of `inviter`'s invitations `person` turned down in the last 30 days: (brief, explained)."""
        sim = self.sim
        day = sim.w.day
        if self._decl is None or self._decl[0] != day:
            I = sim.book.inv
            if I.n and "said" in I.cols:
                m = (I["response"] == RESPONSE_ID["no"]) & (I["inviter"] >= 0) & (I["sent_day"] >= day - 30)
                k = pkey(I["inviter"][m], I["person"][m])
                br = I["said"][m] == 2
                order = np.argsort(k, kind="stable")
                k, br = k[order], br[order]
                uk, start = np.unique(k, return_index=True)
                nb = np.add.reduceat(br.astype(np.int64), start) if len(k) else np.empty(0, np.int64)
                nt = np.diff(np.r_[start, len(k)])
                self._decl = (day, uk, nb, nt - nb)
            else:
                self._decl = (day, np.empty(0, np.int64), np.empty(0, np.int64), np.empty(0, np.int64))
        _, uk, nb, ne = self._decl
        k = pkey(inviter, person)
        if not len(uk):
            z = np.zeros(len(np.atleast_1d(k)), np.int64)
            return z, z
        i = np.clip(np.searchsorted(uk, k), 0, len(uk) - 1)
        hit = uk[i] == k
        return np.where(hit, nb[i], 0), np.where(hit, ne[i], 0)

    def invite_penalty(self, hosts, cand) -> np.ndarray:
        """occasions._invite: a host who believes someone isn't interested invites them less (log-score term)."""
        if not self.beliefs.t.n:
            return np.zeros(len(np.atleast_1d(cand)))
        return -self.sim.p("social.belief.invite_penalty") * self.beliefs.conf(hosts, cand, "not_interested")

    def promised(self, person, org) -> np.ndarray:
        """occasions._decide: an open "next time for sure" to this organizer pulls toward yes."""
        if not self.concerns.t.n:
            return np.zeros(len(np.atleast_1d(person)))
        r = self.concerns.find(person, org, "promise")
        return self.sim.p("social.promise.pull") * (r >= 0)

    def suppressed(self, a, b) -> np.ndarray:
        """messaging._checkins: someone who withdrew over an open concern doesn't text that person."""
        C = self.concerns
        if not C.t.n:
            return np.zeros(len(np.atleast_1d(a)), bool)
        out = np.zeros(len(np.atleast_1d(a)), bool)
        for kind in ("unanswered", "left_out"):
            r = C.find(a, b, kind)
            ok = r >= 0
            out[ok] |= C.t.cols["stance"][r[ok]] == STANCE["withdrew"]
        return out

    # ------------------------------------------------------------------ 1. declining an invitation
    def on_declines(self, inv_ids, person, org, occ, F: dict, conflict, cant, ill, yes):
        """Called by occasions._decide after the answers: why each said no (stored on the invitation), whether they
        said why (`decline_message`), how the host read it (`read_decline`), and a "next time" promise."""
        sim, w = self.sim, self.sim.w
        P, p = w.P, sim.p
        I = sim.book.inv
        if "said" not in I.cols:
            return
        day = w.day
        pos = I.pos(inv_ids)
        no = (~yes) & (pos >= 0)
        # the reason that decided it: a constraint, else the largest push toward no
        why = np.zeros(len(person), np.int8)
        neg = {"tired": "tired", "exam_soon": "exam", "partner": "partner", "hurt": "hurt", "travel": "far", "late": "far",
               "weather": "far"}
        best = np.zeros(len(person))
        for nm, code in neg.items():
            v = F.get(nm)
            if v is None:
                continue
            v = np.broadcast_to(np.asarray(v, float), (len(person),))
            m = v < best
            why[m] = WHY_ID[code]
            best = np.minimum(best, v)
        why[(why == 0) & no] = WHY_ID["not_feeling_it"]
        shift = sim.systems["activity"].shift_minutes(1, sim.cal.weekday(day))[person] > 0
        why[conflict & shift] = WHY_ID["work"]
        why[conflict & ~shift] = WHY_ID["clash"]
        why[cant] = WHY_ID["far"]
        why[ill] = WHY_ID["ill"]
        I.cols["why"][pos[pos >= 0]] = why[pos >= 0]
        real = no & (org >= 0) & (org != person) & np.isin(occ, sim.book.occ["id"])
        kinds = sim.systems["occasions"].kind_of(np.where(real, occ, -1)) if real.any() else None
        if kinds is not None:
            soc = np.isin(kinds, [sim.book.kind_id.get(k, -99) for k in SOCIAL_KINDS])
            real &= soc
        j = np.flatnonzero(real)
        if not len(j):
            return
        a, h, o = person[j], org[j], occ[j]
        clos = self._col("closeness", a, h)
        nameable = why[j] != WHY_ID["not_feeling_it"]
        T = {"closeness": p("social.decline.closeness") * clos,
             "agreeableness": p("social.decline.agreeableness") * sim.z("agreeableness")[a],
             "has_a_reason": p("social.decline.reason") * nameable,
             "outgoing": p("social.decline.extraversion") * sim.z("extraversion")[a]}
        base = p("social.decline.base")
        pr = expit(base + sum(T.values()))
        explain = self._u("decline_msg", a, o) < pr
        I.cols["said"][pos[j]] = np.where(explain, 1, 2)
        # the host reads it: an explained clash reads as busy; a brief no, against how often they've said no lately
        nb, ne = self.declines_recent(h, a)
        R = {"declined_before": p("social.read.repeat") * np.minimum(nb, 4),
             "explained_before": -p("social.read.explained") * np.minimum(ne, 3),
             "sensitive": p("social.read.rs") * sim.z("rejection_sensitivity")[h],
             "closeness": -p("social.read.closeness") * clos}
        rbase = p("social.read.base")
        pni = expit(rbase + sum(R.values()))
        ni = ~explain & (self._u("read_decline", h, a) < pni)
        had_ni = self.beliefs.conf(h, a, "not_interested") > 0
        revise = explain & nameable & had_ni            # an explained clash corrects an earlier misreading
        # a "next time for sure" from someone close, when there was a real reason (a promise they can keep or break)
        PR = {"closeness": p("social.promise.closeness") * (clos - 0.4), "agreeableness": 0.4 * sim.z("agreeableness")[a]}
        pp = expit(p("social.promise.base") + sum(PR.values()))
        promise = explain & nameable & (clos >= 0.35) & (self._u("rain_check", a, o) < pp)
        # an open promise to this host: saying no again breaks it (briefly) or renegotiates it (with a reason)
        old = self.concerns.find(a, h, "promise")
        has_old = old >= 0
        rec = ni | revise | promise | has_old
        if not rec.any():
            return
        r = np.flatnonzero(rec)
        did = sim.decisions.record("decline_message", day, a[r], np.where(explain[r], "explained", "brief").tolist(),
                                   {k_: v[r] for k_, v in T.items()}, base=base,
                                   prob=np.where(explain[r], pr[r], 1 - pr[r]), occasion=o[r], other=h[r])
        thread = I.cols["thread"][pos[j][r]]
        chan = I.cols["channel"][pos[j][r]]
        ex = self.ex.add(sim, len(r), speaker=a[r], to=h[r], act=np.where(explain[r], ACT["decline_explained"], ACT["decline_brief"]),
                         channel=chan, thread=thread, block=0, topic=TOPIC["occasion"], ref=o[r], ref_kind=CAUSE_ID["occasion"],
                         decision=did, intent=np.where(explain[r], INTENT["keep_door_open"], INTENT["decline_gently"]),
                         withheld=np.where(explain[r], 0, why[j][r]), said=np.where(explain[r], why[j][r], 0),
                         ambig=np.where(explain[r], 0.15, 0.6), conv=self._conv(len(r)), keep=True,
                         inv=np.asarray(inv_ids, np.int64)[j][r])
        # the host's reading of each recorded decline
        rd = np.where(ni[r], READ["not_interested"], np.where(explain[r], READ["busy"], READ["ambiguous"]))
        conf = np.where(ni[r], pni[r], np.where(explain[r], 0.7, 1 - pni[r]))
        bel = np.full(len(r), -1, np.int64)
        m = ni[r]
        if m.any():
            rdid = sim.decisions.record("read_decline", day, h[r][m], "not_interested", {k_: v[r][m] for k_, v in R.items()},
                                        base=rbase, prob=pni[r][m], occasion=o[r][m], other=a[r][m],
                                        refs={"declined_before": ("person", a[r][m])})
            del rdid
            bel[m] = self.beliefs.believe(h[r][m], a[r][m], "not_interested", pni[r][m], day, ex[m])
        m = revise[r]
        if m.any():
            bel[m] = self.beliefs.believe(h[r][m], a[r][m], "busy", 0.7, day, ex[m])
        self.reads.add(ex, h[r], rd.astype(np.int8), conf, day, expected=READ["polite"], belief=bel)
        # promises: kept or broken later; an old one is broken (brief no) or renegotiated (another real reason)
        ho = has_old[r]
        if ho.any():
            st = np.where(explain[r][ho] & nameable[r][ho], CSTAT["renegotiated"], CSTAT["missed"])
            for s_ in (CSTAT["renegotiated"], CSTAT["missed"]):
                mm = st == s_
                if mm.any():
                    self.concerns.close(old[r][ho][mm], STATUS[s_], day, ex[ho][mm])
                    if s_ == CSTAT["missed"]:
                        sim.emit("promise_broken", a[r][ho][mm], b=h[r][ho][mm], mech="social.promise", block=0,
                                 causes=[("occasion", o[r][ho][mm], 1.0)])
        m = promise[r]
        if m.any():
            self.concerns.open(a[r][m], h[r][m], "promise", day, importance=0.4 + 0.4 * clos[r][m],
                               deadline=day + int(p("social.promise.days")), ref=o[r][m], ref_kind=CAUSE_ID["occasion"],
                               evidence=ex[m])
            self.ex.t.set("act", ex[m], ACT["promise"])

    def on_attend(self, person, occ):
        """An open promise to this occasion's organizer is kept when they come."""
        C = self.concerns
        if not C.t.n or not len(person):
            return
        org = self.sim.book.occ.get("organizer", occ, default=-1).astype(np.int64)
        ok = org >= 0
        r = C.find(np.asarray(person)[ok], org[ok], "promise")
        hit = r >= 0
        if hit.any():
            ids = C.t.ids[r[hit]]
            C.close(ids, "fulfilled", self.sim.w.day)
            self.sim.emit("promise_kept", np.asarray(person)[ok][hit], b=org[ok][hit], mech="social.promise", block=2,
                          causes=[("occasion", np.asarray(occ)[ok][hit], 1.0)])

    # ------------------------------------------------------------------ 2. being left out
    def on_left_out(self, x, org, o, ev):
        """messaging._left_out found that x heard about a get-together at org's without them. How x reads it comes
        from evidence (x's own recent declines to org; rejection sensitivity; closeness), and replaces the old fixed
        hurt. Returns the hurt to add on each tie."""
        sim = self.sim
        p, day = sim.p, sim.w.day
        nb, ne = self.declines_recent(org, x)
        own = nb + ne
        clos = self._col("closeness", x, org)
        T = {"sensitive": p("social.leftout.rs") * sim.z("rejection_sensitivity")[x],
             "closeness": -p("social.leftout.closeness") * clos,
             "hurt_before": p("social.leftout.hurt") * self._col("hurt", x, org)}
        pex = expit(p("social.leftout.base") + sum(T.values()))
        u = self._u("leftout_read", x, org)
        self_aware = own >= 2                                    # they know they've been saying no
        excluded = ~self_aware & (u < pex)
        read = np.where(self_aware, READ["not_interested"], np.where(excluded, READ["excluded"], READ["unknown"]))
        ex = self.ex.add(sim, len(x), speaker=org, to=x, act="no_reply", channel="group_chat", block=3, topic=TOPIC["left_out"],
                         ref=o, ref_kind=CAUSE_ID["occasion"], event=ev, said=0, ambig=0.8, conv=self._conv(len(x)), keep=True)
        bel = np.full(len(x), -1, np.int64)
        if self_aware.any():
            bel[self_aware] = self.beliefs.believe(x[self_aware], org[self_aware], "thinks_im_not_interested",
                                                   0.4 + 0.1 * np.minimum(own[self_aware], 4), day, ex[self_aware])
        if excluded.any():
            bel[excluded] = self.beliefs.believe(x[excluded], org[excluded], "excluded_me", pex[excluded], day, ex[excluded])
        self.reads.add(ex, x, read.astype(np.int8), np.where(self_aware, 0.6, np.where(excluded, pex, 0.4)), day,
                       expected=READ["warm"], belief=bel)
        imp = np.clip(0.3 + 0.6 * clos, 0.2, 1.0)
        cid = self.concerns.open(x, org, "left_out", day, importance=imp, deadline=day + int(p("social.leftout.days")),
                                 ref=o, ref_kind=CAUSE_ID["occasion"], evidence=ex, belief=bel)
        self.ex.t.set("concern", ex, cid)
        # what the host believed (only when they actually held it)
        held = self.beliefs.conf(org, x, "not_interested") > 0
        hurt = np.where(excluded, p("social.leftout.hurt_excluded"),
                        np.where(self_aware, p("social.leftout.hurt_self_aware"), p("social.leftout.hurt_unsure")))
        return hurt, held, ex

    # ------------------------------------------------------------------ 3. unanswered texts
    def read_silence(self, a, b, act, sil=None):
        """messaging._silences: a's text to b went unanswered. Evidence: does a believe b is busy (they explained before,
        or a sees their schedule: roommates, coworkers), how often b answered a lately. Returns (ignored mask, ex ids)."""
        sim = self.sim
        P, p, day = sim.w.P, sim.p, sim.w.day
        e, ok = self._tie(a, b)
        E = sim.w.E
        flags = np.where(ok, E["flags"][np.maximum(e, 0)] if E.n else 0, 0)
        sees = (flags & (Tie.ROOMMATE | Tie.COWORKER)) > 0
        busy_now = sim.systems["activity"].shift_minutes(1, sim.cal.weekday(day))[b] > 0
        knows_busy = (self.beliefs.conf(a, b, "busy") > 0) | (sees & busy_now)
        replies, silences = self._reply_history(b, a)
        T = {"sensitive": p("messaging.silence.rs") * sim.z("rejection_sensitivity")[a],
             "knows_busy": -p("social.silence.knows_busy") * knows_busy,
             "usually_answers": -p("social.silence.history") * np.minimum(replies, 4) / 4,
             "silent_before": p("social.silence.history") * np.minimum(silences, 3) / 3}
        base = p("messaging.silence.ignored_base")
        pr = expit(base + sum(T.values()))
        ignored = self._u("silence_read", a, act) < pr
        did = np.empty(len(a), np.int64)
        for o_, m in (("ignoring_me", ignored), ("busy", ~ignored)):
            if m.any():
                did[m] = sim.decisions.record("read_silence", day, a[m], o_, {k: v[m] for k, v in T.items()}, base=base,
                                              prob=np.where(ignored[m], pr[m], 1 - pr[m]), other=b[m])
        ex = self.ex.add(sim, len(a), speaker=b, to=a, act="no_reply", channel="text", block=3, topic=TOPIC["silence"],
                         ref=act, ref_kind=CAUSE_ID["message"], decision=did, ambig=0.7, conv=self._conv(len(a)), keep=True,
                         msg=-1 if sil is None else sil)
        bel = np.full(len(a), -1, np.int64)
        if ignored.any():
            bel[ignored] = self.beliefs.believe(a[ignored], b[ignored], "ignoring_me", pr[ignored], day, ex[ignored])
            cid = self.concerns.open(a[ignored], b[ignored], "unanswered", day, importance=0.2 + 0.6 * self._col("closeness", a[ignored], b[ignored]),
                                     deadline=day + int(p("social.silence.wait_days")), ref=act[ignored],
                                     ref_kind=CAUSE_ID["message"], evidence=ex[ignored], belief=bel[ignored])
            self.ex.t.set("concern", ex[ignored], cid)
        self.reads.add(ex, a, np.where(ignored, READ["ignored"], np.where(knows_busy, READ["busy"], READ["unknown"])).astype(np.int8),
                       np.where(ignored, pr, 1 - pr), day, expected=READ["warm"], belief=bel)
        # the silent friend may still answer in a day or three (late_reply, decided then)
        self._late = np.r_[getattr(self, "_late", np.empty((0, 4), np.int64)),
                           np.c_[b, a, act, np.full(len(a), day, np.int64)]] if len(a) else getattr(self, "_late", np.empty((0, 4), np.int64))
        return ignored, ex

    def _reply_history(self, replier, sender) -> tuple[np.ndarray, np.ndarray]:
        """How often `replier` answered `sender`'s texts lately (messaging acts): (replies, silences)."""
        M = self.sim.systems["messaging"]
        A = M.acts
        from .messaging import ACT_ID
        if not A.n:
            z = np.zeros(len(replier), np.int64)
            return z, z
        day = self.sim.w.day
        m = (A["thread"] < 0) & (A["day"] >= day - 45)
        kind = A["kind"][m]
        s, t = A["sender"][m], A["to"][m]
        rk = pkey(s[kind == ACT_ID["reply"]], t[kind == ACT_ID["reply"]])
        sk = pkey(s[kind == ACT_ID["silence"]], t[kind == ACT_ID["silence"]])
        q = pkey(replier, sender)
        cnt = lambda arr: np.searchsorted(np.sort(arr), q, "right") - np.searchsorted(np.sort(arr), q, "left")   # noqa: E731
        return cnt(rk), cnt(sk)

    def _late_replies(self, day: int):
        """A text left unanswered may still get an answer, late (`late_reply`); the sender's reading is revised."""
        L = getattr(self, "_late", None)
        if L is None or not len(L):
            return
        sim, w = self.sim, self.sim.w
        P, E, p = w.P, w.E, sim.p
        age = day - L[:, 3]
        due = (age >= 1) & (age <= 3)
        drop = age >= 3
        b, a, act = L[due, 0], L[due, 1], L[due, 2]
        self._late = L[~drop]
        if not len(b):
            return
        pres = P["present"][a].astype(bool) & P["present"][b].astype(bool)
        b, a, act = b[pres], a[pres], act[pres]
        if not len(b):
            return
        clos = self._col("closeness", b, a)
        T = {"closeness": p("social.late.closeness") * clos,
             "conscientious": 0.4 * sim.z("conscientiousness")[b],
             "mood": p("messaging.reply.mood") * (P["mood"][b] - 0.5),
             "depression": -1.0 * P["depressive_episode"][b]}
        base = p("social.late.base")
        pr = expit(base + sum(T.values()))
        go = self._u("late_reply", b, act) < pr
        if not go.any():
            return
        b, a, act, clos = b[go], a[go], act[go], clos[go]
        did = sim.decisions.record("late_reply", day, b, "answered", {k: v[go] for k, v in T.items()}, base=base,
                                   prob=pr[go], other=a)
        # a close friend apologizes for the delay; the reply also lands in the text thread
        sorry = clos >= p("social.late.apology_closeness")
        M = sim.systems["messaging"]
        from .messaging import ACT_ID
        mid = M.acts.append(len(b), thread=-1, day=day, block=1, sender=b, kind=ACT_ID["reply"], to=a, reply_to=act)
        M.acts.set("replied_day", act, day)
        if "decision" in M.acts.cols:
            M.acts.set("decision", mid, did)
        self._late = self._late[~np.isin(self._late[:, 2], act)]
        ev = sim.emit("late_reply", b, b=a, mech="social.late", block=1, decision=did)
        ex = self.ex.add(sim, len(b), speaker=b, to=a, act="late_reply", channel="text", block=1, topic=TOPIC["silence"],
                         ref=act, ref_kind=CAUSE_ID["message"], decision=did, event=ev,
                         intent=np.where(sorry, INTENT["repair"], INTENT["inform"]), said=np.where(sorry, 1, 0), ambig=0.25,
                         conv=self._conv(len(b)), keep=True, msg=mid)
        # the sender's reading: an apology or any answer revises "ignoring me" (very sensitive people stay unsure)
        had = self.beliefs.conf(a, b, "ignoring_me") > 0
        unsure = sim.z("rejection_sensitivity")[a] > p("social.late.stay_unsure_rs")
        revised = had & (sorry | ~unsure)
        bel = np.full(len(b), -1, np.int64)
        if revised.any():
            bel[revised] = self.beliefs.believe(a[revised], b[revised], "busy", 0.6, day, ex[revised])
            sim.emit("clarified", a[revised], b=b[revised], mech="social.late", block=1, cause=ev[revised])
        self.reads.add(ex, a, np.where(revised, READ["relief"], np.where(had, READ["ambiguous"], READ["warm"])).astype(np.int8),
                       np.where(revised, 0.6, 0.4), day, expected=READ["none"], belief=bel)
        C = self.concerns
        r = C.find(a, b, "unanswered")
        hit = r >= 0
        if hit.any():
            C.close(C.t.ids[r[hit]], "repaired", day, ex[hit])
            e, ok = self._tie(a[hit & revised], b[hit & revised])
            E.cols["hurt"][e[ok]] = np.clip(E["hurt"][e[ok]] - p("social.late.repair"), 0, 1)

    # ------------------------------------------------------------------ 4. support
    def on_checkin_replies(self, a, b, reply_act):
        """messaging._checkins: b answered a's check-in. A struggling b discloses or deflects (`disclose_struggle`)."""
        sim, w = self.sim, self.sim.w
        P, E, p = w.P, w.E, sim.p
        day = w.day
        low = (P["mood"][b] < p("social.support.low_mood")) | P["depressive_episode"][b].astype(bool) | (P["loneliness"][b] > 0.6)
        if not low.any():
            return
        a, b, reply_act = a[low], b[low], reply_act[low]
        e, ok = self._tie(a, b)
        ei = np.maximum(e, 0)
        clos = np.where(ok, E["closeness"][ei], 0.0)
        trust = np.where(ok, E["trust"][ei], 0.0)
        dep = P["depressive_episode"][b].astype(bool)
        T = {"closeness": p("social.support.closeness") * clos,
             "trust": p("social.support.trust") * trust,
             "private": -p("social.support.privacy") * np.where(dep, 0.85, 0.3),
             "burden": -p("social.support.burden") * np.clip(0.6 - P["self_esteem"][b], 0, 1),
             "openness": 0.3 * sim.z("extraversion")[b]}
        base = p("social.support.base")
        pr = expit(base + sum(T.values()))
        tell = self._u("disclose", b, a) < pr
        did = np.empty(len(a), np.int64)
        for o_, m in (("disclosed", tell), ("deflected", ~tell)):
            if m.any():
                did[m] = sim.decisions.record("disclose_struggle", day, b[m], o_, {k: v[m] for k, v in T.items()}, base=base,
                                              prob=np.where(tell[m], pr[m], 1 - pr[m]), other=a[m])
        # what they're going through, as an event a friend can know about (their latest private hard event)
        about = self._struggle_event(b)
        conv = self._conv(len(a))
        ex = self.ex.add(sim, len(a), speaker=b, to=a, act=np.where(tell, ACT["disclose"], ACT["deflect"]), channel="text",
                         block=3, topic=TOPIC["struggle"], ref=about, ref_kind=np.where(about >= 0, CAUSE_ID["event"], -1),
                         reply_to=-1, decision=did, intent=np.where(tell, INTENT["get_support"], INTENT["keep_private"]),
                         withheld=np.where(tell, 0, 1), ambig=np.where(tell, 0.1, 0.5), conv=conv, keep=True, msg=reply_act)
        M = sim.systems["messaging"]
        know_before = M.know.knows(np.maximum(about, 0), a) & (about >= 0)
        if tell.any():
            t = np.flatnonzero(tell)
            ev = sim.emit("confided", b[t], b=a[t], mech="social.support", block=3, decision=did[t])
            self.ex.t.set("event", ex[t], ev)
            k = about[t] >= 0
            if k.any():               # a confidence: known to this friend, not passed on as gossip
                M.know.add(a[t][k], about[t][k], b[t][k], day, CHANNEL_ID["confided"])
            # the friend's support (the same channel coping uses: support given, a little more disclosure)
            resp = np.clip(E["liking"][ei[t]], 0, 1) * (0.5 + 0.5 * clos[t])
            okt = ok[t]
            et = ei[t][okt]
            E.cols["support"][et] = np.minimum(E["support"][et] + 0.15 * resp[okt], 5)
            E.cols["disclosure"][et] = np.clip(E["disclosure"][et] + 0.08 * resp[okt] * (1 - E["disclosure"][et]), 0, 1)
            sx = self.ex.add(sim, len(t), speaker=a[t], to=b[t], act="support", channel="text", block=3,
                             topic=TOPIC["struggle"], ref=about[t], reply_to=ex[t], intent=INTENT["give_support"], ambig=0.1,
                             conv=conv[t], keep=True)
            self.reads.add(sx, b[t], READ["support"], 0.8, day, expected=READ["none"])
            self.reads.add(ex[t], a[t], READ["obligation"], 0.5, day)
            # a supportive answer challenges an earlier "they don't care"
            for prop in ("ignoring_me", "excluded_me"):
                rv = self.beliefs.revise(b[t], a[t], prop, day, sx)
                del rv
        d = np.flatnonzero(~tell)
        if len(d):
            # a friend who already knew reads the deflection as not ready to talk; others take "fine" at face value
            self.reads.add(ex[d], a[d], np.where(know_before[d], READ["ambiguous"], READ["warm"]).astype(np.int8),
                           np.where(know_before[d], 0.5, 0.6), day)

    def _struggle_event(self, people) -> np.ndarray:
        """Each person's latest hard private event within 60 days (depressive episode, faith crisis…), or −1."""
        sim = self.sim
        log = sim.log
        out = np.full(len(people), -1, np.int64)
        types = [sim.reg.event_ids[t] for t in ("depressive_episode_start", "faith_crisis_start", "academic_probation",
                                                  "job_lost", "breakup_received", "death_in_family") if t in sim.reg.event_ids]
        n = log.n
        lo = int(np.searchsorted(log["day"][:n], sim.w.day - 60))
        rows = lo + np.flatnonzero(np.isin(log["type"][lo:n], types))
        if not len(rows):
            return out
        who = log["a"][rows].astype(np.int64)
        last = {}
        for r_, w_ in zip(rows.tolist(), who.tolist()):
            last[w_] = r_
        return np.array([last.get(int(i), -1) for i in np.asarray(people).tolist()], np.int64)

    # ------------------------------------------------------------------ 5. what people do about open concerns
    def _concern_choices(self, day: int):
        """Open concerns whose owner hasn't acted: left out → clarify / withdraw / let it go (`left_out_response`);
        an unanswered text past its wait → check in again / ask what's up / withdraw (`concern_next`). Lapsed ones
        close."""
        sim, w = self.sim, self.sim.w
        P, p = w.P, sim.p
        C = self.concerns
        T = C.t
        if not T.n:
            return
        op = np.flatnonzero(T["status"] == CSTAT["open"])
        if not len(op):
            return
        late = op[(T["deadline"][op] < day)]
        if len(late):
            withdrew = T["stance"][late] == STANCE["withdrew"]
            if withdrew.any():
                C.close(T.ids[late[withdrew]], "abandoned", day)
            if (~withdrew).any():
                C.close(T.ids[late[~withdrew]], "lapsed", day)
            op = np.flatnonzero(T["status"] == CSTAT["open"])
        own, oth, kind = T["owner"][op].astype(np.int64), T["other"][op].astype(np.int64), T["kind"][op]
        pres = P["present"][own].astype(bool) & P["present"][oth].astype(bool)
        # ---- left out: decide once, the day after finding out
        lo = op[(kind == CONCERN["left_out"]) & (T["stance"][op] == 0) & (T["opened"][op] < day) & pres]
        if len(lo):
            x, h = T["owner"][lo].astype(np.int64), T["other"][lo].astype(np.int64)
            clos = self._col("closeness", x, h)
            aware = self.beliefs.conf(x, h, "thinks_im_not_interested")
            excl = self.beliefs.conf(x, h, "excluded_me")
            U = {"clarify": p("social.respond.clarify") + p("social.respond.closeness") * clos + 0.4 * sim.z("extraversion")[x]
                 + p("social.respond.aware") * aware,
                 "withdraw": p("social.respond.withdraw") + p("social.respond.rs") * sim.z("rejection_sensitivity")[x]
                 + p("social.respond.excluded") * excl,
                 "let_go": np.zeros(len(x))}
            names = list(U)
            Ux = np.stack([U[k] for k in names], 1)
            pr = np.exp(Ux - Ux.max(1, keepdims=True))
            pr /= pr.sum(1, keepdims=True)
            u = self._u("leftout_resp", x, h)
            ch = (u[:, None] > np.cumsum(pr, 1)).sum(1)
            ch = np.minimum(ch, len(names) - 1)
            for j, nm in enumerate(names):
                m = ch == j
                if not m.any():
                    continue
                did = sim.decisions.record("left_out_response", day, x[m], nm,
                                           {"closeness": p("social.respond.closeness") * clos[m],
                                            "sensitive": p("social.respond.rs") * sim.z("rejection_sensitivity")[x[m]],
                                            "thinks_they_misread": p("social.respond.aware") * aware[m],
                                            "felt_excluded": p("social.respond.excluded") * excl[m]},
                                           base=0.0, prob=pr[m, j], other=h[m])
                rows = lo[m]
                if nm == "clarify":
                    T.cols["stance"][rows] = STANCE["asked"]
                    self._clarify(x[m], h[m], T.ids[rows], did, "text", 1)
                elif nm == "withdraw":
                    T.cols["stance"][rows] = STANCE["withdrew"]
                    self.ex.add(sim, int(m.sum()), speaker=x[m], to=h[m], act="withdraw", channel="text", block=1,
                                topic=TOPIC["left_out"], decision=did, concern=T.ids[rows], intent=INTENT["protect_self"],
                                withheld=1, ambig=0.9, conv=self._conv(int(m.sum())), keep=True)
                else:
                    C.close(T.ids[rows], "let_go", day)
                T.cols["acted_day"][rows] = day
        # ---- an unanswered text past its wait
        un = op[(kind == CONCERN["unanswered"]) & np.isin(T["stance"][op], [0]) & (day - T["opened"][op] >= 2) & pres]
        if len(un):
            a, b = T["owner"][un].astype(np.int64), T["other"][un].astype(np.int64)
            clos = self._col("closeness", a, b)
            U = {"check_again": p("social.next.again") + p("social.next.closeness") * clos,
                 "ask_whats_up": p("social.next.ask") + 0.5 * sim.z("extraversion")[a] + 0.5 * clos,
                 "withdraw": p("social.next.withdraw") + p("social.respond.rs") * sim.z("rejection_sensitivity")[a],
                 "wait": np.zeros(len(a))}
            names = list(U)
            Ux = np.stack([U[k] for k in names], 1)
            pr = np.exp(Ux - Ux.max(1, keepdims=True))
            pr /= pr.sum(1, keepdims=True)
            u = self._u("unanswered_next", a, b)
            ch = np.minimum((u[:, None] > np.cumsum(pr, 1)).sum(1), len(names) - 1)
            for j, nm in enumerate(names):
                m = ch == j
                if not m.any() or nm == "wait":
                    continue
                did = sim.decisions.record("concern_next", day, a[m], nm,
                                           {"closeness": p("social.next.closeness") * clos[m],
                                            "sensitive": p("social.respond.rs") * sim.z("rejection_sensitivity")[a[m]]},
                                           base=0.0, prob=pr[m, j], other=b[m])
                rows = un[m]
                T.cols["acted_day"][rows] = day
                if nm == "withdraw":
                    T.cols["stance"][rows] = STANCE["withdrew"]
                    self.ex.add(sim, int(m.sum()), speaker=a[m], to=b[m], act="withdraw", channel="text", block=1,
                                topic=TOPIC["silence"], decision=did, concern=T.ids[rows], intent=INTENT["protect_self"],
                                withheld=1, ambig=0.9, conv=self._conv(int(m.sum())), keep=True)
                else:
                    T.cols["stance"][rows] = STANCE["checked_in"] if nm == "check_again" else STANCE["asked"]
                    self._follow_up(a[m], b[m], T.ids[rows], did, ask=nm == "ask_whats_up")

    def _follow_up(self, a, b, cids, did, ask: bool):
        """A second text after a silence: a low-pressure check-in, or asking whether everything is okay. b answers
        with the same reply model (`reply_message` terms); an answer repairs, another silence worsens."""
        sim, w = self.sim, self.sim.w
        P, E, p = w.P, w.E, sim.p
        day = w.day
        M = sim.systems["messaging"]
        from .messaging import ACT_ID
        mid = M.acts.append(len(a), thread=-1, day=day, block=1, sender=a, kind=ACT_ID["checkin"], to=b)
        if "decision" in M.acts.cols:
            M.acts.set("decision", mid, did)
        conv = self._conv(len(a))
        ex = self.ex.add(sim, len(a), speaker=a, to=b, act="ask_clarify" if ask else "checkin", channel="text", block=1,
                         topic=TOPIC["silence"], ref=mid, ref_kind=CAUSE_ID["message"], decision=did, concern=cids,
                         intent=INTENT["understand"] if ask else INTENT["check_on"], ambig=0.3, conv=conv, keep=True, msg=mid)
        clos = self._col("closeness", b, a)
        busy = sim.systems["activity"].shift_minutes(1, sim.cal.weekday(day))[b] > 0
        resp = (sim.z("conscientiousness")[b] + sim.z("agreeableness")[b]) / 2
        T = {"closeness": p("messaging.reply.closeness") * clos, "responsiveness": p("messaging.reply.responsive") * resp,
             "mood": p("messaging.reply.mood") * (P["mood"][b] - 0.5), "busy": -p("messaging.reply.busy") * busy,
             "depression": -1.0 * P["depressive_episode"][b], "asked_directly": np.full(len(a), p("social.next.direct") * ask)}
        base = p("messaging.reply.base")
        pr = expit(base + sum(T.values()))
        yes = self._u("followup_reply", b, mid) < pr
        rdid = np.empty(len(a), np.int64)
        for o_, m in (("replied", yes), ("no_reply", ~yes)):
            if m.any():
                rdid[m] = sim.decisions.record("reply_message", day, b[m], o_, {k: v[m] for k, v in T.items()}, base=base,
                                               prob=np.where(yes[m], pr[m], 1 - pr[m]), other=a[m])
        C = self.concerns
        if yes.any():
            y = np.flatnonzero(yes)
            rm = M.acts.append(len(y), thread=-1, day=day, block=2, sender=b[y], kind=ACT_ID["reply"], to=a[y], reply_to=mid[y])
            M.acts.set("replied_day", mid[y], day)
            if "decision" in M.acts.cols:
                M.acts.set("decision", rm, rdid[y])
            rx = self.ex.add(sim, len(y), speaker=b[y], to=a[y], act="clarify" if ask else "reply", channel="text", block=2,
                             topic=TOPIC["silence"], reply_to=ex[y], decision=rdid[y], concern=cids[y],
                             said=np.where(busy[y], WHY_ID["work"], 0), intent=INTENT["repair"], ambig=0.2, conv=conv[y], keep=True,
                             msg=rm)
            bel = self.beliefs.believe(a[y], b[y], "busy", 0.6, day, rx)
            self.reads.add(rx, a[y], READ["relief"], 0.6, day, belief=bel)
            C.close(cids[y], "repaired", day, rx)
            sim.emit("clarified", a[y], b=b[y], mech="social.late", block=2, decision=rdid[y])
            e, ok = self._tie(a[y], b[y])
            E.cols["hurt"][e[ok]] = np.clip(E["hurt"][e[ok]] - p("social.late.repair"), 0, 1)
        n = np.flatnonzero(~yes)
        if len(n):
            nx = self.ex.add(sim, len(n), speaker=b[n], to=a[n], act="no_reply", channel="text", block=3, topic=TOPIC["silence"],
                             reply_to=ex[n], decision=rdid[n], concern=cids[n], ambig=0.8, conv=conv[n], keep=True)
            conf = self.beliefs.conf(a[n], b[n], "ignoring_me")
            bel = self.beliefs.believe(a[n], b[n], "ignoring_me", np.minimum(0.95, conf + 0.2), day, nx)
            self.reads.add(nx, a[n], READ["ignored"], np.minimum(0.95, conf + 0.2), day, belief=bel)
            C.close(cids[n], "worsened", day, nx)
            e, ok = self._tie(a[n], b[n])
            E.cols["hurt"][e[ok]] = np.clip(E["hurt"][e[ok]] + p("social.next.worse"), 0, 1)

    def _clarify(self, x, h, cids, did, channel: str, block: int, conv=None):
        """x tells h why they've been saying no (the reason they kept to themselves before). h's reading is revised
        when h held the misreading; h answers warmly either way. The concern is clarified; part of the hurt heals."""
        sim, w = self.sim, self.sim.w
        E, p = w.E, sim.p
        day = w.day
        I = sim.book.inv
        reason = self._usual_reason(x, h) if I.n and "why" in I.cols else np.zeros(len(x), np.int8)
        conv = self._conv(len(x)) if conv is None else conv
        # someone who has been saying no explains why; someone who hadn't just asks to be included next time
        nb, ne = self.declines_recent(h, x)
        had = (nb + ne) > 0
        ex = self.ex.add(sim, len(x), speaker=x, to=h, act=np.where(had, ACT["clarify"], ACT["ask_clarify"]).astype(np.int8),
                         channel=channel, block=block, topic=np.where(had, TOPIC["declines"], TOPIC["left_out"]).astype(np.int8),
                         decision=did, concern=cids, said=np.where(had, reason, 0).astype(np.int8), intent=INTENT["repair"],
                         ambig=0.15, conv=conv, keep=True, ref=self.concerns.t.get("ref", cids, default=-1),
                         ref_kind=CAUSE_ID["occasion"])
        held = self.beliefs.conf(h, x, "not_interested") > 0
        bel = np.full(len(x), -1, np.int64)
        if held.any():
            bel[held] = self.beliefs.believe(h[held], x[held], "busy", 0.75, day, ex[held])
        self.reads.add(ex, h, np.where(held, READ["relief"], READ["warm"]).astype(np.int8), 0.7, day,
                       expected=np.where(held, READ["not_interested"], READ["none"]).astype(np.int8), belief=bel)
        rx = self.ex.add(sim, len(x), speaker=h, to=x, act=np.where(had | held, ACT["reassure"], ACT["apologize"]).astype(np.int8),
                         channel=channel, block=block, topic=np.where(had, TOPIC["declines"], TOPIC["left_out"]).astype(np.int8),
                         reply_to=ex, concern=cids, said=held.astype(np.int8), intent=INTENT["repair"], ambig=0.15, conv=conv, keep=True)
        for prop in ("excluded_me", "thinks_im_not_interested"):
            self.beliefs.revise(x, h, prop, day, rx)
        self.reads.add(rx, x, READ["relief"], 0.7, day)
        self.concerns.close(cids, "clarified", day, rx)
        ev = sim.emit("clarified", x, b=h, mech="social.respond", block=block, decision=did)
        self.ex.t.set("event", ex, ev)
        e, ok = self._tie(x, h)
        E.cols["hurt"][e[ok]] = E["hurt"][e[ok]] * (1 - p("social.respond.repair"))
        return ex, rx

    def _usual_reason(self, x, h) -> np.ndarray:
        """The most common reason x gave (or kept back) for turning down h lately."""
        I = self.sim.book.inv
        day = self.sim.w.day
        m = (I["response"] == RESPONSE_ID["no"]) & (I["sent_day"] >= day - 45) & (I["why"] > 0)
        k = pkey(I["person"][m], I["inviter"][m])
        why = I["why"][m]
        q = pkey(x, h)
        out = np.zeros(len(q), np.int8)
        hit = np.isin(q, k)
        for j in np.flatnonzero(hit).tolist():           # bounded: a day's clarifications
            v = why[k == q[j]]
            out[j] = np.bincount(v).argmax()
        return out

    # ------------------------------------------------------------------ 6. in person (encounters.apply)
    def in_person(self, a, b, ctx, place, block, v, idx, new_before, bad):
        """Observational capture of conversations, and the moment an open concern gets raised or avoided.
        Capture: every consequential talk (a first meeting at a get-together, a conflict, a raised concern) plus a
        deterministic, hash-thinned sample of ordinary talk among people who know each other. No random numbers."""
        sim, w = self.sim, self.sim.w
        E, P, p = w.E, w.P, sim.p
        day = w.day
        n = len(a)
        if not n:
            return
        stage = E["stage"][idx]
        social_ctx = np.isin(ctx, [CTX_ID[k] for k in ("occasion", "gathering", "hangout", "unit", "dance", "club", "team",
                                                      "fhe", "outdoors", "venue", "work", "class", "ward", "complex")])
        h = (ukey(a, b) * np.int64(0x9E3779B1) + np.int64(day * 7 + block)) & 0x7FFFFFFF
        every = int(p("social.capture.ordinary_every"))
        rom = (E["flags"][idx] & (Tie.ROMANTIC | Tie.SPOUSE)) > 0
        ordinary = social_ctx & (stage >= 2) & ((h % every) == 0)
        ordinary |= rom & ((h % max(every // 2, 1)) == 0)
        # first meetings at get-togethers (thinned the same way: a party can introduce dozens of people)
        meet = new_before & np.isin(ctx, [CTX_ID[k] for k in ("occasion", "gathering", "hangout", "dance", "club", "team")]) \
            & ((h % max(every // 2, 1)) == 0)
        # concerns raised in person (owner decides raise or avoid; only once a day per concern)
        C = self.concerns
        raised = np.zeros(n, bool)
        if C.t.n:
            has = C.between_mask(a, b)
            if has.any():
                raised = self._raise(np.flatnonzero(has), a, b, ctx, place, block, v)
        cap = (ordinary | meet | bad) & ~raised
        if not cap.any():
            return
        j = np.flatnonzero(cap)
        # one record per pair per block (a pair can meet twice in a block's sampling)
        _, first = np.unique(ukey(a[j], b[j]), return_index=True)
        j = j[first]
        act = np.where(bad[j], ACT["tension"], np.where(meet[j], ACT["introduce"],
                                                       np.where(v[j] > 1.0, ACT["warm_moment"], ACT["small_talk"])))
        topic, ref, rk = self._topic(a[j], b[j], ctx[j], place[j])
        occ = np.where(ctx[j] == CTX_ID["occasion"], place[j], -1)
        self.ex.add(sim, len(j), speaker=a[j], to=b[j], act=act.astype(np.int8), channel="in_person", block=block,
                    topic=topic, ref=ref, ref_kind=rk, tone=v[j], place=np.where(occ >= 0, occ, place[j]),
                    ctx=ctx[j].astype(np.int8), conv=self._conv(len(j)), keep=bad[j] | meet[j],
                    ambig=np.where(bad[j], 0.4, 0.1))

    def _topic(self, a, b, ctx, place):
        """What ordinary talk is about, from the shared context only (no new facts): the class, the shift, the
        apartment, church, the get-together they're at, plans they both said yes to, exams, the weather."""
        sim, w = self.sim, self.sim.w
        name = {CTX_ID.get(k, -1): t for k, t in (("class", "class"), ("work", "work"), ("unit", "home"), ("complex", "home"),
                                                  ("ward", "church"), ("fhe", "church"), ("congregation", "church"),
                                                  ("institute", "church"), ("gym", "fitness"), ("team", "team"),
                                                  ("club", "club"), ("outdoors", "outing"), ("venue", "outing"),
                                                  ("occasion", "occasion"), ("gathering", "occasion"), ("hangout", "outing"),
                                                  ("dance", "occasion"))}
        topic = np.array([TOPIC[name.get(int(c), "none")] for c in ctx.tolist()], np.int8)
        ref = np.where(ctx == CTX_ID["occasion"], place, -1).astype(np.int64)
        rk = np.where(ref >= 0, CAUSE_ID["occasion"], -1).astype(np.int8)
        P = w.P
        exams = np.where(P["school"][a] == 1, bool(w.env.get("exam_week_BYU")), bool(w.env.get("exam_week_UVU"))) \
            & P["enrolled"][a] & P["enrolled"][b]
        topic = np.where(exams & (topic != TOPIC["occasion"]), TOPIC["exam"], topic)
        # plans they both said yes to (coordination): the next upcoming occasion with both on its yes list
        I = sim.book.inv
        if I.n:
            O = sim.book.occ
            m = (I["response"] == RESPONSE_ID["yes"])
            od = O.get("day", I["occ"][m], default=-1)
            fut = od >= w.day
            pk = (I["occ"][m][fut].astype(np.int64) << 24) | I["person"][m][fut].astype(np.int64)
            if len(pk):
                pk = np.sort(pk)
                occs = np.unique(I["occ"][m][fut]).astype(np.int64)
                # bounded: captured talk is a small sample; check each pair against occasions they could share
                for jj in np.flatnonzero(topic != TOPIC["occasion"]).tolist()[:200]:
                    ka = (occs << 24) | int(a[jj])
                    kb = (occs << 24) | int(b[jj])
                    ia = np.clip(np.searchsorted(pk, ka), 0, len(pk) - 1)
                    ib = np.clip(np.searchsorted(pk, kb), 0, len(pk) - 1)
                    both = occs[(pk[ia] == ka) & (pk[ib] == kb)]
                    if len(both):
                        topic[jj], ref[jj], rk[jj] = TOPIC["plans"], int(both[0]), CAUSE_ID["occasion"]
        return topic, ref, rk

    def _raise(self, rows, a, b, ctx, place, block, v) -> np.ndarray:
        """Two people with an open concern are talking: the owner raises it or avoids it (`raise_concern`)."""
        sim, w = self.sim, self.sim.w
        E, p = w.E, sim.p
        day = w.day
        C = self.concerns
        T = C.t
        raised = np.zeros(len(a), bool)
        # orient each pair as (owner, other) for every open concern kind that can be talked about
        hits = []
        for kind in ("left_out", "unanswered"):
            for x_, y_ in ((a, b), (b, a)):
                r = C.find(x_[rows], y_[rows], kind)
                ok = (r >= 0)
                ok[ok] &= T.cols["acted_day"][r[ok]] < day
                ok[ok] &= T.cols["stance"][r[ok]] != STANCE["raised"]
                if ok.any():
                    hits.append((rows[ok], x_[rows][ok], y_[rows][ok], r[ok]))
        if not hits:
            return raised
        j = np.concatenate([h[0] for h in hits])
        own = np.concatenate([h[1] for h in hits]).astype(np.int64)
        oth = np.concatenate([h[2] for h in hits]).astype(np.int64)
        cr = np.concatenate([h[3] for h in hits])
        _, first = np.unique(cr, return_index=True)
        j, own, oth, cr = j[first], own[first], oth[first], cr[first]
        clos = self._col("closeness", own, oth)
        withdrew = T.cols["stance"][cr] == STANCE["withdrew"]
        TT = {"closeness": p("social.raise.closeness") * clos, "assertive": 0.4 * sim.z("extraversion")[own],
              "importance": p("social.raise.importance") * T.cols["importance"][cr],
              "withdrew": -p("social.raise.withdrew") * withdrew,
              "sensitive": -0.3 * sim.z("rejection_sensitivity")[own]}
        base = p("social.raise.base")
        pr = expit(base + sum(TT.values()))
        go = self._u("raise_concern", own, oth + 7919 * block) < pr
        T.cols["acted_day"][cr] = day
        did = np.empty(len(own), np.int64)
        for o_, m in (("raised", go), ("avoided", ~go)):
            if m.any():
                did[m] = sim.decisions.record("raise_concern", day, own[m], o_, {k: v_[m] for k, v_ in TT.items()}, base=base,
                                              prob=np.where(go[m], pr[m], 1 - pr[m]), other=oth[m], block=block)
        conv = self._conv(len(own))
        occ = np.where(ctx[j] == CTX_ID["occasion"], place[j], -1)
        common = dict(channel="in_person", block=block, place=np.where(occ >= 0, occ, place[j]), ctx=ctx[j].astype(np.int8),
                      tone=v[j], concern=T.ids[cr], conv=conv, keep=True)
        av = np.flatnonzero(~go)
        if len(av):
            self.ex.add(sim, len(av), speaker=own[av], to=oth[av], act="avoid", topic=TOPIC["none"],
                        decision=did[av], withheld=1, intent=INTENT["protect_self"], ambig=0.5,
                        **{k: (vv[av] if isinstance(vv, np.ndarray) else vv) for k, vv in common.items()})
        g = np.flatnonzero(go)
        if len(g):
            kind = T.cols["kind"][cr[g]]
            T.cols["stance"][cr[g]] = STANCE["raised"]
            sub = lambda vv: vv[g] if isinstance(vv, np.ndarray) else vv   # noqa: E731
            topic = np.where(kind == CONCERN["left_out"], TOPIC["left_out"], TOPIC["silence"])
            ax = self.ex.add(sim, len(g), speaker=own[g], to=oth[g], act="ask_clarify", topic=topic, decision=did[g],
                             intent=INTENT["understand"], ambig=0.3, **{k: sub(vv) for k, vv in common.items()})
            # how it goes depends on how the talk itself went (the encounter's valence)
            worse = v[j][g] < p("social.raise.worse_below")
            ok = ~worse
            if ok.any():
                k = np.flatnonzero(ok)
                held = self.beliefs.conf(oth[g][k], own[g][k], "not_interested") > 0
                # the other's side first: an honest "I figured you weren't interested" reveals the misreading
                rx = self.ex.add(sim, len(k), speaker=oth[g][k], to=own[g][k],
                                 act=np.where(held, ACT["clarify"], ACT["apologize"]).astype(np.int8),
                                 topic=topic[k], reply_to=ax[k], said=held.astype(np.int8),
                                 intent=np.where(held, INTENT["inform"], INTENT["repair"]).astype(np.int8),
                                 ambig=0.15, **{kk: (sub(vv)[k] if isinstance(vv, np.ndarray) else vv) for kk, vv in common.items()})
                self.reads.add(rx, own[g][k], np.where(held, READ["relief"], READ["warm"]).astype(np.int8), 0.7, day)
                lo_ = kind[k] == CONCERN["left_out"]
                if lo_.any():
                    kk = np.flatnonzero(lo_)
                    self._clarify(own[g][k][kk], oth[g][k][kk], T.ids[cr[g][k][kk]], did[g][k][kk], "in_person", block,
                                  conv=conv[g][k][kk])
                un = ~lo_
                if un.any():
                    kk = np.flatnonzero(un)
                    self.beliefs.believe(own[g][k][kk], oth[g][k][kk], "busy", 0.6, day, rx[kk])
                    C.close(T.ids[cr[g][k][kk]], "repaired", day, rx[kk])
                    e, okk = self._tie(own[g][k][kk], oth[g][k][kk])
                    E.cols["hurt"][e[okk]] = np.clip(E["hurt"][e[okk]] - p("social.late.repair"), 0, 1)
                    sim.emit("clarified", own[g][k][kk], b=oth[g][k][kk], mech="social.raise", block=block, decision=did[g][k][kk])
            if worse.any():
                k = np.flatnonzero(worse)
                tx = self.ex.add(sim, len(k), speaker=oth[g][k], to=own[g][k], act="tension", topic=topic[k], reply_to=ax[k],
                                 intent=INTENT["protect_self"], ambig=0.5,
                                 **{kk: (sub(vv)[k] if isinstance(vv, np.ndarray) else vv) for kk, vv in common.items()})
                self.reads.add(tx, own[g][k], READ["rejection"], 0.6, day)
                C.close(T.ids[cr[g][k]], "worsened", day, tx)
                e, okk = self._tie(own[g][k], oth[g][k])
                E.cols["hurt"][e[okk]] = np.clip(E["hurt"][e[okk]] + p("social.next.worse"), 0, 1)
        raised[j] = True
        return raised

    # ------------------------------------------------------------------ 7. dating apps
    def app_matched(self, a, b, ev):
        """romance._app made matches: each becomes an app thread (the conversation decides whether a date follows)."""
        sim = self.sim
        if not len(a):
            return
        P = sim.w.P
        T = self.app.t
        k = ukey(a, b)
        live = self.app.live()
        have = ukey(T["a"][live], T["b"][live]) if len(live) else np.empty(0, np.int64)
        new = ~np.isin(k, have)
        _, first = np.unique(k, return_index=True)
        keep = np.zeros(len(a), bool)
        keep[first] = True
        new &= keep
        if not new.any():
            return
        mutual = (P["app_mutual"][a] == P["app_mutual"][b]) & P["app_mutual"][a].astype(bool)
        T.append(int(new.sum()), a=a[new], b=b[new], matched=sim.w.day, match_event=ev[new], stage=APP["matched"],
                 last_day=sim.w.day, mutual=mutual[new])

    def _app_day(self, wd: int):
        """Advance every live app conversation one day."""
        sim, w = self.sim, self.sim.w
        P, E, p = w.P, w.E, sim.p
        day = w.day
        A = self.app
        T = A.t
        live = A.live()
        if not len(live):
            return
        rom = sim.systems["romance"]
        a, b = T["a"][live].astype(np.int64), T["b"][live].astype(np.int64)
        stage = T["stage"][live]
        e, ok = self._tie(a, b)
        ei = np.maximum(e, 0)
        att_ab = np.where(ok, E.attraction_from(ei, a), 0.0)
        att_ba = np.where(ok, E.attraction_from(ei, b), 0.0)
        seek = rom.seeking_mask()
        gone = ~(P["present"][a].astype(bool) & P["present"][b].astype(bool))
        taken_a, taken_b = ~seek[a], ~seek[b]
        tid = T.ids[live]
        male_a = P["sex"][a] == P.code("sex", "M")
        norm = float(w.env.get("men_initiate_norm", 1.0))
        hours = lambda x: np.log(np.maximum(P["app_hours"][x], 0.05))    # noqa: E731
        # ---- nobody can carry on: one of them left, or got into a relationship (that thread just stops)
        stop = gone | (taken_a & taken_b)
        # ---- they already went out, or have a date coming, arranged another way: the app thread is done (no second
        # "first" date from the app)
        pending = {(min(q[1], q[2]), max(q[1], q[2])) for q in rom.queue}
        offline = ok & ((E["flags"][ei] & Tie.DATED) > 0)
        if pending:
            offline |= np.fromiter(((min(x, y), max(x, y)) in pending for x, y in zip(a.tolist(), b.tolist())), bool, len(a))
        offline &= ~stop & (stage <= APP["asked"])
        if offline.any():
            T.cols["stage"][live[offline]] = APP["offline"]
            T.cols["ended_day"][live[offline]] = day
            stop = stop | offline
        # ---- matched: an opener, from whoever is keener (men more often, by the norm), or nothing
        m0 = (stage == APP["matched"]) & ~stop
        if m0.any():
            j = np.flatnonzero(m0)
            first_a = (att_ab[j] + 0.3 * norm * (male_a[j].astype(float) * 2 - 1)) >= att_ba[j]
            s = np.where(first_a, a[j], b[j])
            r = np.where(first_a, b[j], a[j])
            att = np.where(first_a, att_ab[j], att_ba[j])
            TT = {"attraction": p("social.app.open_attraction") * att, "motivation": 1.0 * (P["dating_motivation"][s] - 0.4),
                  "app_hours": 0.4 * hours(s), "boldness": 0.3 * sim.z("extraversion")[s]}
            base = p("social.app.open_base")
            pr = expit(base + sum(TT.values()))
            go = (self._u("app_open", s, tid[j]) < pr) & ~(taken_a[j] | taken_b[j])
            if go.any():
                g = np.flatnonzero(go)
                did = sim.decisions.record("app_opener", day, s[g], "sent", {k: v[g] for k, v in TT.items()}, base=base,
                                           prob=pr[g], other=r[g])
                rows = live[j[g]]
                T.cols["stage"][rows] = APP["opened"]
                T.cols["opener"][rows] = s[g]
                T.cols["opened_day"][rows] = day
                T.cols["last_day"][rows] = day
                T.cols["last_by"][rows] = s[g]
                T.cols["n_msgs"][rows] += 1
                self.ex.add(sim, len(g), speaker=s[g], to=r[g], act="opener", channel="app", thread=tid[j[g]], block=2,
                            topic=TOPIC["match"], decision=did, intent=INTENT["test_interest"], ambig=0.3,
                            conv=tid[j[g]], keep=True)
                # when the reply comes (decided now, from the stored draw; shown only once it happens)
                self._schedule_reply(rows, r[g], s[g], tid[j[g]], np.where(first_a[g], att_ba[j[g]], att_ab[j[g]]), day)
            old = ~go & (day - T["matched"][live[j]] >= int(p("social.app.open_days")))
            if old.any():
                T.cols["stage"][live[j[old]]] = APP["no_opener"]
                T.cols["ended_day"][live[j[old]]] = day
        # ---- opened: the reply arrives on its day (or never: an unanswered opener)
        m1 = (stage == APP["opened"]) & ~stop
        if m1.any():
            j = np.flatnonzero(m1)
            rows = live[j]
            due = T["reply_due"][rows]
            s = T["opener"][rows].astype(np.int64)
            r = np.where(s == a[j], b[j], a[j])
            now = (due >= 0) & (due <= day)
            if now.any():
                n_ = np.flatnonzero(now)
                late = due[n_] > T["opened_day"][rows[n_]]
                rr = rows[n_]
                T.cols["stage"][rr] = APP["chatting"]
                T.cols["replied_day"][rr] = day
                T.cols["last_day"][rr] = day
                T.cols["last_by"][rr] = r[n_]
                T.cols["n_msgs"][rr] += 1
                ex = self.ex.add(sim, len(n_), speaker=r[n_], to=s[n_], act="app_reply", channel="app", thread=tid[j[n_]],
                                 block=2, topic=TOPIC["match"], said=late.astype(np.int8), intent=INTENT["connect"], ambig=0.3,
                                 conv=tid[j[n_]], keep=True)
                self.reads.add(ex, s[n_], np.where(late, READ["ambiguous"], READ["interest"]).astype(np.int8),
                               np.where(late, 0.4, 0.6), day)
            never = (due < 0) & (day - T["opened_day"][rows] >= int(p("social.app.reply_days")))
            if never.any():
                n_ = np.flatnonzero(never)
                T.cols["stage"][rows[n_]] = APP["unanswered"]
                T.cols["ended_day"][rows[n_]] = day
                T.cols["ended_by"][rows[n_]] = r[n_]
                ex = self.ex.add(sim, len(n_), speaker=r[n_], to=s[n_], act="no_reply", channel="app", thread=tid[j[n_]],
                                 block=3, topic=TOPIC["match"], ambig=0.8, conv=tid[j[n_]], keep=True)
                self.reads.add(ex, s[n_], READ["unknown"], 0.5, day)
        # ---- chatting: carry on, ask for a date, or drift (a fade, or one of them stops answering: ghosting)
        m2 = (stage == APP["chatting"]) & ~stop & (T["last_day"][live] < day)
        if m2.any():
            j = np.flatnonzero(m2)
            rows = live[j]
            mutual_att = np.minimum(att_ab[j], att_ba[j])
            cd = T["chat_days"][rows].astype(float)
            # the asker: men by the norm, else the keener one
            ask_a = (att_ab[j] + 0.4 * norm * (male_a[j].astype(float) * 2 - 1)) >= att_ba[j]
            s = np.where(ask_a, a[j], b[j])
            r = np.where(ask_a, b[j], a[j])
            att_s = np.where(ask_a, att_ab[j], att_ba[j])
            planned = P.internal["date_planned"][: P.n]
            free = (planned[s] < day) & (planned[r] < day)
            TA = {"attraction": p("social.app.ask_attraction") * att_s, "chatting": p("social.app.ask_chat") * np.minimum(cd, 4),
                  "motivation": 1.0 * (P["dating_motivation"][s] - 0.4), "boldness": 0.3 * sim.z("extraversion")[s]}
            abase = p("social.app.ask_base")
            pa = expit(abase + sum(TA.values()))
            ask = free & ~taken_a[j] & ~taken_b[j] & (self._u("app_ask", s, tid[j] * 64 + cd.astype(np.int64)) < pa)
            # interest fading on either side
            fade_a = expit(p("social.app.fade_base") - p("social.app.fade_attraction") * att_ab[j] + 2.0 * taken_a[j]
                           + 0.2 * cd)
            fade_b = expit(p("social.app.fade_base") - p("social.app.fade_attraction") * att_ba[j] + 2.0 * taken_b[j]
                           + 0.2 * cd)
            ua = self._u("app_fade", a[j], tid[j] * 64 + cd.astype(np.int64))
            ub = self._u("app_fade", b[j], tid[j] * 64 + cd.astype(np.int64))
            fa, fb = (ua < fade_a) & ~ask, (ub < fade_b) & ~ask
            both = fa & fb
            one = (fa ^ fb)
            if ask.any():
                g = np.flatnonzero(ask)
                did = sim.decisions.record("app_ask", day, s[g], "asked", {k: v[g] for k, v in TA.items()}, base=abase,
                                           prob=pa[g], other=r[g])
                T.cols["stage"][rows[g]] = APP["asked"]
                T.cols["asker"][rows[g]] = s[g]
                T.cols["last_day"][rows[g]] = day
                T.cols["last_by"][rows[g]] = s[g]
                T.cols["n_msgs"][rows[g]] += 1
                self.ex.add(sim, len(g), speaker=s[g], to=r[g], act="ask_date", channel="app", thread=tid[j[g]], block=2,
                            topic=TOPIC["date"], decision=did, intent=INTENT["flirt"], ambig=0.1, conv=tid[j[g]], keep=True)
            if both.any():
                g = np.flatnonzero(both)
                T.cols["stage"][rows[g]] = APP["faded"]
                T.cols["ended_day"][rows[g]] = day
                self.ex.add(sim, len(g), speaker=a[j[g]], to=b[j[g]], act="fade", channel="app", thread=tid[j[g]], block=3,
                            topic=TOPIC["match"], ambig=0.6, conv=tid[j[g]], keep=True)
            if one.any():
                g = np.flatnonzero(one)
                quitter = np.where(fa[g], a[j[g]], b[j[g]])
                other = np.where(fa[g], b[j[g]], a[j[g]])
                T.cols["stage"][rows[g]] = APP["ghosted"]
                T.cols["ended_day"][rows[g]] = day
                T.cols["ended_by"][rows[g]] = quitter
                ev = sim.emit("ghosted", other, b=quitter, mech="social.app", block=3)
                ex = self.ex.add(sim, len(g), speaker=quitter, to=other, act="no_reply", channel="app", thread=tid[j[g]],
                                 block=3, topic=TOPIC["match"], event=ev, ambig=0.8, conv=tid[j[g]], keep=True)
                self.reads.add(ex, other, READ["rejection"], 0.5, day)
            rest = ~(ask | fa | fb)
            if rest.any():
                g = np.flatnonzero(rest)
                T.cols["chat_days"][rows[g]] += 1
                T.cols["n_msgs"][rows[g]] += 2
                T.cols["last_day"][rows[g]] = day
                sp = np.where((T["chat_days"][rows[g]] % 2) == 0, a[j[g]], b[j[g]])
                to = np.where(sp == a[j[g]], b[j[g]], a[j[g]])
                self.ex.add(sim, len(g), speaker=sp, to=to, act="app_chat", channel="app", thread=tid[j[g]], block=2,
                            topic=TOPIC["match"], intent=INTENT["connect"], ambig=0.2, conv=tid[j[g]],
                            keep=True, tone=np.minimum(att_ab[j[g]], att_ba[j[g]]))
                del mutual_att
        # ---- asked: the answer (the same accept terms as any date), and a date booked once through romance's queue
        m3 = (stage == APP["asked"]) & (T["last_day"][live] < day) & ~offline
        if m3.any():
            j = np.flatnonzero(m3)
            rows = live[j]
            s = T["asker"][rows].astype(np.int64)
            r = np.where(s == a[j], b[j], a[j])
            att_r = np.where(s == a[j], att_ba[j], att_ab[j])
            planned = P.internal["date_planned"][: P.n]
            taken = ~seek[r] | ~seek[s] | stop[j]
            busy = (planned[r] >= day) | (planned[s] >= day)
            TT = {"attraction": p("romance.accept.attraction") * att_r,
                  "politeness": p("romance.accept.politeness") * (P["accepts_first_dates"][r] - 2) / 2,
                  "motivation": p("romance.accept.motivation") * (P["dating_motivation"][r] - 0.4),
                  "picky": -(p("romance.accept.picky") * (P["picky"][r] - 2) / 2)}
            base = p("romance.accept.base") + p("social.app.accept_shift")
            pr = expit(base + sum(TT.values()))
            yes = (self._u("app_yes", r, tid[j]) < pr) & ~taken & ~busy
            did = np.empty(len(j), np.int64)
            for o_, m in (("yes", yes), ("no", ~yes)):
                if m.any():
                    did[m] = sim.decisions.record("app_answer", day, r[m], o_, {k: v[m] for k, v in TT.items()}, base=base,
                                                  prob=np.where(yes[m], pr[m], 1 - pr[m]), other=s[m],
                                                  constraints={"taken": taken[m], "already_planned": busy[m]})
            ex = self.ex.add(sim, len(j), speaker=r, to=s, act=np.where(yes, ACT["date_yes"], ACT["date_no"]).astype(np.int8),
                             channel="app", thread=tid[j], block=1, topic=TOPIC["date"], decision=did,
                             intent=np.where(yes, INTENT["connect"], INTENT["spare_feelings"]), ambig=0.1, conv=tid[j], keep=True)
            self.reads.add(ex, s, np.where(yes, READ["interest"], READ["rejection"]).astype(np.int8), 0.8, day)
            T.cols["last_day"][rows] = day
            T.cols["last_by"][rows] = r
            if (~yes).any():
                n_ = np.flatnonzero(~yes)
                T.cols["stage"][rows[n_]] = APP["declined"]
                T.cols["ended_day"][rows[n_]] = day
                T.cols["ended_by"][rows[n_]] = r[n_]
            if yes.any():
                g = np.flatnonzero(yes)
                dd = rom._next_date_day(wd, self._u("app_dday", s[g], tid[j[g]]))
                dtypes = rom._date_type(s[g], r[g])
                for a_, b_, d_, t_, c_ in zip(s[g].tolist(), r[g].tolist(), dd.tolist(), dtypes,
                                               T["match_event"][rows[g]].tolist()):
                    rom.queue.append((d_, a_, b_, t_, True, c_))
                P.internal["date_planned"][s[g]] = dd
                P.internal["date_planned"][r[g]] = dd
                T.cols["stage"][rows[g]] = APP["date_set"]
                T.cols["date_day"][rows[g]] = dd
                sim.emit("app_date_set", s[g], b=r[g], mech="social.app", block=1, decision=did[g],
                         cause=T["match_event"][rows[g]])
        # threads that stopped because one of them can't carry on
        st = stop & ~offline & (stage <= APP["chatting"])
        if st.any():
            T.cols["stage"][live[st]] = APP["closed"]
            T.cols["ended_day"][live[st]] = day
        # a thread that went quiet for too long fades
        quiet = (T["stage"][live] <= APP["chatting"]) & (day - T["last_day"][live] > int(p("social.app.quiet_days")))
        if quiet.any():
            T.cols["stage"][live[quiet]] = APP["faded"]
            T.cols["ended_day"][live[quiet]] = day

    def _schedule_reply(self, rows, r, s, tid, att_r, day):
        """When (if ever) the match answers an opener: today, a few days late, or never (`app_reply`)."""
        sim = self.sim
        P, p = sim.w.P, sim.p
        TT = {"attraction": p("social.app.reply_attraction") * att_r, "motivation": 1.0 * (P["dating_motivation"][r] - 0.4),
              "app_hours": 0.4 * np.log(np.maximum(P["app_hours"][r], 0.05)), "taken": -2.0 * ~sim.systems["romance"].seeking_mask()[r]}
        base = p("social.app.reply_base")
        pr = expit(base + sum(TT.values()))
        u = self._u("app_reply", r, tid)
        will = u < pr
        # among replies, the slower ones (a draw near the edge) come late: 1–3 days
        lateness = np.where(will, np.floor(3.0 * np.clip(u / np.maximum(pr, 1e-6) - p("social.app.prompt_share"), 0, 1)
                                           / max(1 - p("social.app.prompt_share"), 1e-6)), -1).astype(np.int64)
        lateness = np.minimum(lateness, 3)
        self.app.t.cols["reply_due"][rows] = np.where(will, day + lateness, -1)
        did = np.empty(len(r), np.int64)
        for o_, m in (("will_reply", will), ("no_reply", ~will)):
            if m.any():
                did[m] = sim.decisions.record("app_reply", day, r[m], o_, {k: v[m] for k, v in TT.items()}, base=base,
                                              prob=np.where(will[m], pr[m], 1 - pr[m]), other=s[m])
        return did

    # ------------------------------------------------------------------ daily
    def daily(self):
        day = self.sim.w.day
        self._late_replies(day)
        self._concern_choices(day)
        self._app_day(self.sim.w.env["weekday"])
        if day % 7 == 6:
            p = self.sim.p
            self.beliefs.fade(day, p("social.belief.half_life"), int(p("social.belief.cap")))
            self._thin(day)

    def _thin(self, day: int):
        """Ordinary talk older than two weeks thins away; consequential exchanges (keep) stay for detail_days;
        closed app threads after detail_days. Recording thins; behavior never reads what thinned."""
        keep_days = getattr(self.sim, "detail_days", 120)
        X = self.ex.t
        if X.n:
            X.keep((X["day"] >= day - 14) | (X["keep"] & (X["day"] >= day - keep_days)))
        R = self.reads.t
        if R.n:
            R.keep(R["day"] >= day - keep_days)
        A = self.app.t
        if A.n:
            A.keep((A["stage"] <= APP["asked"]) | (A["ended_day"] >= day - keep_days) | (A["ended_day"] < 0))
        C = self.concerns.t
        if C.n:
            C.keep((C["status"] == CSTAT["open"]) | (C["resolved_day"] >= day - keep_days))
            self.concerns._idx = None
        B = self.beliefs.t
        if B.n:
            B.keep(B["active"] | (B["revised_day"] >= day - keep_days))
            self.beliefs._idx = None
