"""Ledgers: the records that let anyone trace why things happened.

The event log says *what* happened and names one parent event. These ledgers keep the rest of the story:

DecisionLog   one row per recorded choice — who decided, what kind of choice, the outcome, the probability the
              model gave that outcome, and the factors that weighed in (the largest contributions on the choice's own
              log-odds or utility scale, plus hard constraints such as "working until 7 pm"), each optionally pointing
              at the event, occasion or person it refers to.
CauseLinks    extra, typed causes of an event beyond its single `cause` parent: the decision behind it, the occasion
              where it happened, the people or ties involved, a calendar item, a user's action, an institution's rule.
OccasionBook  planned social occasions (a dinner, a study group, a club night, a football game, a date): when, where and
              for how long; who organizes; who was invited through which channel; who saw it; who said yes or no and
              why; who came and when they arrived; what happened there. Occasions that happened are the model's scenes.

Rows keep stable ids. Old, unremarkable rows are thinned (`thin`) so a long full-size run stays within memory; rows
linked to salient events are kept for good. Nothing here draws random numbers: recording never changes the world.

Vocabularies (decision kinds, their outcomes and factors; occasion kinds) live in `config/decisions/*.yaml` and
`config/occasions/*.yaml` and are loaded by the registry.
"""
from __future__ import annotations

import numpy as np

K_FACTORS = 6           # factors kept per decision (largest |contribution| first)
CONSTRAINT = 99.0       # |value| stored for a hard constraint (it decided the outcome regardless of the rest)

CAUSE_KINDS = ("event", "decision", "occasion", "person", "tie", "state", "calendar", "action", "institution",
               "message", "trip", "place")
CAUSE_ID = {k: i for i, k in enumerate(CAUSE_KINDS)}

CHANNELS = ("in_person", "text", "group_chat", "announcement", "family", "app")
CHANNEL_ID = {k: i for i, k in enumerate(CHANNELS)}
RESPONSES = ("pending", "yes", "no", "no_reply", "maybe")
RESPONSE_ID = {k: i for i, k in enumerate(RESPONSES)}
STATUS = ("planned", "happened", "cancelled")
STATUS_ID = {k: i for i, k in enumerate(STATUS)}
ORIGINS = ("engine", "user", "institution", "calendar", "family")
ORIGIN_ID = {k: i for i, k in enumerate(ORIGINS)}
ORG_KINDS = ("none", "household", "group", "ward", "employer", "complex", "school", "city", "family", "service", "user")
ORG_ID = {k: i for i, k in enumerate(ORG_KINDS)}


class Table:
    """Growable columnar table with stable row ids (ids survive thinning; look rows up with `pos`)."""

    def __init__(self, schema: dict[str, tuple], capacity: int = 1024):
        self.schema = {}
        for name, spec in schema.items():
            dtype, fill = spec[0], spec[1]
            shape = spec[2] if len(spec) > 2 else ()
            self.schema[name] = (np.dtype(dtype), fill, shape)
        self.cap = max(16, capacity)
        self.n = 0
        self.next_id = 0
        self.cols = {name: np.full((self.cap, *shape), fill, dtype) for name, (dtype, fill, shape) in self.schema.items()}
        self.ids = np.zeros(self.cap, np.int64)

    def __getstate__(self):
        """Copies and pickles carry the used rows plus headroom (see state.PersonTable)."""
        from .state import _headroom
        keep = max(16, _headroom(self.n, self.cap))
        st = dict(self.__dict__)
        st["cols"] = {k: v[:keep] for k, v in self.cols.items()}
        st["ids"] = self.ids[:keep]
        st["cap"] = keep
        return st

    def __len__(self):
        return self.n

    def _grow(self, need: int):
        if self.n + need <= self.cap:
            return
        new_cap = max(self.cap * 2, self.n + need + 1024)
        for name, (dtype, fill, shape) in self.schema.items():
            g = np.full((new_cap, *shape), fill, dtype)
            g[: self.n] = self.cols[name][: self.n]
            self.cols[name] = g
        g = np.zeros(new_cap, np.int64)
        g[: self.n] = self.ids[: self.n]
        self.ids = g
        self.cap = new_cap

    def append(self, k: int, **values) -> np.ndarray:
        """Append k rows; each value is a scalar or an array broadcastable to (k, *shape). Returns the new ids."""
        k = int(k)
        if k <= 0:
            return np.empty(0, np.int64)
        self._grow(k)
        s = slice(self.n, self.n + k)
        for name, v in values.items():
            if v is None:
                continue
            dtype, _, shape = self.schema[name]
            self.cols[name][s] = np.broadcast_to(np.asarray(v).astype(dtype, copy=False), (k, *shape))
        ids = np.arange(self.next_id, self.next_id + k, dtype=np.int64)
        self.ids[s] = ids
        self.n += k
        self.next_id += k
        return ids

    def __getitem__(self, name: str) -> np.ndarray:
        if name == "id":
            return self.ids[: self.n]
        return self.cols[name][: self.n]

    def pos(self, ids) -> np.ndarray:
        """Row positions of ids (−1 when the id was never issued or has been thinned)."""
        ids = np.atleast_1d(np.asarray(ids, np.int64))
        have = self.ids[: self.n]
        p = np.searchsorted(have, ids)
        ok = (p < self.n) & (ids >= 0)
        ok[ok] &= have[p[ok]] == ids[ok]
        return np.where(ok, p, -1)

    def set(self, name: str, ids, values):
        p = self.pos(ids)
        m = p >= 0
        if m.any():
            v = np.broadcast_to(np.asarray(values), (len(p), *self.schema[name][2]))
            self.cols[name][p[m]] = v[m]

    def get(self, name: str, ids, default=None):
        p = self.pos(ids)
        col = self.cols[name]
        out = col[np.maximum(p, 0)].copy()
        if default is not None:
            out[p < 0] = default
        return out

    def keep(self, mask: np.ndarray) -> int:
        """Drop rows where mask is False (ids of kept rows stay valid). Returns how many rows were dropped."""
        mask = np.asarray(mask, bool)
        k = int(mask.sum())
        dropped = self.n - k
        if dropped == 0:
            return 0
        for name in self.schema:
            self.cols[name][:k] = self.cols[name][: self.n][mask]
            self.cols[name][k: self.n] = self.schema[name][1]
        self.ids[:k] = self.ids[: self.n][mask]
        self.n = k
        return dropped

    def row(self, i: int) -> dict:
        """One row as plain Python values (by id)."""
        p = int(self.pos(i)[0])
        if p < 0:
            return {}
        out = {"id": int(i)}
        for name in self.schema:
            v = self.cols[name][p]
            out[name] = v.tolist() if hasattr(v, "tolist") else v
        return out

    def nbytes(self) -> int:
        return int(sum(c[: self.n].nbytes for c in self.cols.values()) + self.ids[: self.n].nbytes)


# ----------------------------------------------------------------------------- decisions
class DecisionLog:
    """Why people chose what they chose.

    record(kind, day, agents, outcome, factors) stores, per agent, the K largest factor contributions (in the
    decision's units: log-odds for yes/no choices, utility for choices among options), the baseline (`base`), the
    total, and the probability the model gave the outcome that happened. Factor contributions are *already multiplied
    by their coefficients* — they are the terms that were summed. Hard constraints ("working until 7 pm", "no car and
    no bus that late") are passed in `constraints` as boolean masks and stored as ±CONSTRAINT so the UI can say
    "couldn't" rather than "didn't want to".
    """

    def __init__(self, vocab: dict):
        self.vocab = vocab                       # kind -> {label, outcomes[], units, factors{fid: {...}}}
        self.kinds = list(vocab)
        self.kind_id = {k: i for i, k in enumerate(self.kinds)}
        self.factor_names: list[str] = []        # global "kind.factor"
        self.factor_id: dict[str, int] = {}
        for k, spec in vocab.items():
            for f in (spec.get("factors") or {}):
                self._factor(k, f)
        K = K_FACTORS
        self.t = Table({"day": (np.int32, -1), "block": (np.int8, 0), "kind": (np.int16, -1), "agent": (np.int32, -1),
                        "other": (np.int32, -1), "outcome": (np.int8, -1), "prob": (np.float16, np.nan),
                        "base": (np.float16, 0.0), "total": (np.float16, 0.0), "occasion": (np.int32, -1),
                        "event": (np.int64, -1), "f_code": (np.int16, -1, (K,)), "f_val": (np.float16, 0.0, (K,)),
                        "f_ref": (np.int64, -1, (K,)), "f_refkind": (np.int8, -1, (K,))}, capacity=1 << 14)

    def _factor(self, kind: str, f: str) -> int:
        key = f"{kind}.{f}"
        if key not in self.factor_id:
            self.factor_id[key] = len(self.factor_names)
            self.factor_names.append(key)
        return self.factor_id[key]

    def outcome_code(self, kind: str, outcome) -> np.ndarray:
        outs = self.vocab[kind].get("outcomes") or []
        if isinstance(outcome, str):
            return np.int8(outs.index(outcome))
        o = np.asarray(outcome)
        if o.dtype.kind in "US" or o.dtype == object:
            return np.array([outs.index(x) for x in o], np.int8)
        return o.astype(np.int8)

    def record(self, kind: str, day: int, agents, outcome, factors: dict, *, block: int = 0, other=None, prob=None,
               base=0.0, occasion=None, refs: dict | None = None, constraints: dict | None = None) -> np.ndarray:
        """Record one decision per agent. `factors`: name -> contribution array (len k) or scalar. `refs`: factor name
        -> (refkind, ids) the factor points at (an event, an occasion, a person). `constraints`: name -> bool mask.
        Returns the decision ids (one per agent)."""
        if kind not in self.kind_id:
            raise KeyError(f"unregistered decision kind {kind!r} (add it to config/decisions/*.yaml)")
        agents = np.atleast_1d(np.asarray(agents, np.int64))
        k = len(agents)
        if k == 0:
            return np.empty(0, np.int64)
        names = list(factors)
        cons = list(constraints or {})
        allnames = names + cons
        F = len(allnames)
        V = np.zeros((k, F), np.float32)
        for j, nm in enumerate(names):
            V[:, j] = np.broadcast_to(np.asarray(factors[nm], np.float32), (k,))
        for j, nm in enumerate(cons):
            V[:, len(names) + j] = np.where(np.broadcast_to(np.asarray(constraints[nm], bool), (k,)), -CONSTRAINT, 0.0)
        codes = np.array([self._factor(kind, nm) for nm in allnames], np.int16)
        total = np.broadcast_to(np.asarray(base, np.float32), (k,)) + V[:, : len(names)].sum(axis=1)
        KK = min(K_FACTORS, F)
        if F:
            order = np.argsort(-np.abs(V), axis=1, kind="stable")[:, :KK]
            vals = np.take_along_axis(V, order, axis=1)
            fc = np.full((k, K_FACTORS), -1, np.int16)
            fv = np.zeros((k, K_FACTORS), np.float32)
            fc[:, :KK] = np.where(vals != 0, codes[order], -1)
            fv[:, :KK] = vals
            fr = np.full((k, K_FACTORS), -1, np.int64)
            fk = np.full((k, K_FACTORS), -1, np.int8)
            for nm, (refkind, rid) in (refs or {}).items():
                if nm not in allnames:
                    continue
                j = allnames.index(nm)
                hit = order == j
                rid = np.broadcast_to(np.asarray(rid, np.int64), (k,))
                rows, cols = np.nonzero(hit)
                fr[rows, cols] = rid[rows]
                fk[rows, cols] = CAUSE_ID[refkind]
        else:
            fc = np.full((k, K_FACTORS), -1, np.int16)
            fv = np.zeros((k, K_FACTORS), np.float32)
            fr = np.full((k, K_FACTORS), -1, np.int64)
            fk = np.full((k, K_FACTORS), -1, np.int8)
        return self.t.append(k, day=day, block=block, kind=self.kind_id[kind], agent=agents,
                             other=-1 if other is None else other, outcome=self.outcome_code(kind, outcome),
                             prob=np.nan if prob is None else prob, base=base, total=total,
                             occasion=-1 if occasion is None else occasion, f_code=fc, f_val=fv, f_ref=fr, f_refkind=fk)

    def link_event(self, decision_ids, event_ids):
        self.t.set("event", decision_ids, np.asarray(event_ids, np.int64))

    def get(self, did: int) -> dict:
        """A decision with readable factors (largest first), or {} if unknown / thinned."""
        r = self.t.row(int(did))
        if not r:
            return {}
        kind = self.kinds[r["kind"]]
        spec = self.vocab[kind]
        outs = spec.get("outcomes") or []
        fl = []
        for c, v, ref, rk in zip(r["f_code"], r["f_val"], r["f_ref"], r["f_refkind"]):
            if c < 0:
                continue
            key = self.factor_names[c]
            fid = key.split(".", 1)[1]
            fs = (spec.get("factors") or {}).get(fid, {})
            item = {"factor": fid, "label": fs.get("label", fid.replace("_", " ")), "value": round(float(v), 3),
                    "constraint": abs(float(v)) >= CONSTRAINT - 1, "kind": fs.get("kind", "utility"),
                    "words": fs.get("more" if v > 0 else "less")}
            if ref >= 0:
                item["ref"] = {"kind": CAUSE_KINDS[rk], "id": int(ref)}
            fl.append(item)
        return {"id": int(did), "kind": kind, "label": spec.get("label", kind), "units": spec.get("units", "logit"),
                "day": r["day"], "block": r["block"], "agent": r["agent"], "other": r["other"] if r["other"] >= 0 else None,
                "outcome": outs[r["outcome"]] if 0 <= r["outcome"] < len(outs) else r["outcome"],
                "prob": None if np.isnan(r["prob"]) else round(float(r["prob"]), 3), "base": round(float(r["base"]), 3),
                "total": round(float(r["total"]), 3), "occasion": r["occasion"] if r["occasion"] >= 0 else None,
                "event": r["event"] if r["event"] >= 0 else None, "factors": fl}

    def for_agent(self, i: int, since: int = -10**9, kind: str | None = None) -> np.ndarray:
        m = (self.t["agent"] == i) & (self.t["day"] >= since)
        if kind is not None:
            m &= self.t["kind"] == self.kind_id[kind]
        return self.t["id"][m]

    def for_event(self, eid: int) -> np.ndarray:
        return self.t["id"][self.t["event"] == eid]

    def for_occasion(self, oid: int) -> np.ndarray:
        return self.t["id"][self.t["occasion"] == oid]

    def factor_summary(self, ids: np.ndarray) -> list[dict]:
        """Across many decisions: how often each factor appears among the top ones and its mean contribution."""
        p = self.t.pos(ids)
        p = p[p >= 0]
        if not len(p):
            return []
        fc = self.t.cols["f_code"][p].ravel()
        fv = self.t.cols["f_val"][p].ravel().astype(np.float32)
        m = fc >= 0
        fc, fv = fc[m], fv[m]
        out = []
        for c in np.unique(fc):
            v = fv[fc == c]
            kind, fid = self.factor_names[c].split(".", 1)
            fs = (self.vocab[kind].get("factors") or {}).get(fid, {})
            cons = np.abs(v) >= CONSTRAINT - 1
            out.append({"factor": fid, "kind": kind, "label": fs.get("label", fid), "n": int(len(v)),
                        "share": round(len(v) / len(p), 3), "mean": round(float(v[~cons].mean()), 3) if (~cons).any() else None,
                        "constraint_n": int(cons.sum())})
        return sorted(out, key=lambda r: -r["n"])


# ----------------------------------------------------------------------------- causes
class CauseLinks:
    """Extra typed causes of events: event id -> (kind, ref, weight, note). `note` is a factor or variable code."""

    def __init__(self):
        self.t = Table({"event": (np.int64, -1), "kind": (np.int8, -1), "ref": (np.int64, -1),
                        "weight": (np.float16, 1.0), "note": (np.int16, -1)}, capacity=1 << 14)

    def add(self, event_ids, kind: str, refs, weight=1.0, note=-1) -> np.ndarray:
        event_ids = np.atleast_1d(np.asarray(event_ids, np.int64))
        k = len(event_ids)
        refs = np.broadcast_to(np.asarray(refs, np.int64), (k,))
        ok = refs >= 0
        if not ok.any():
            return np.empty(0, np.int64)
        w = np.broadcast_to(np.asarray(weight, np.float32), (k,))[ok]
        nt = np.broadcast_to(np.asarray(note, np.int16), (k,))[ok]
        return self.t.append(int(ok.sum()), event=event_ids[ok], kind=CAUSE_ID[kind], ref=refs[ok], weight=w, note=nt)

    def of(self, eid: int) -> list[dict]:
        m = self.t["event"] == eid
        return [{"kind": CAUSE_KINDS[k], "ref": int(r), "weight": round(float(w), 3), "note": int(n)}
                for k, r, w, n in zip(self.t["kind"][m], self.t["ref"][m], self.t["weight"][m], self.t["note"][m])]

    def effects_of(self, kind: str, ref: int) -> np.ndarray:
        """Events that list (kind, ref) among their causes."""
        m = (self.t["kind"] == CAUSE_ID[kind]) & (self.t["ref"] == ref)
        return self.t["event"][m]


# ----------------------------------------------------------------------------- occasions
class OccasionBook:
    """Planned occasions, their invitations and attendance (scenes)."""

    def __init__(self, vocab: dict):
        self.vocab = vocab                      # kind -> {label, ctx, start, dur, open, social, category, ...}
        self.kinds = list(vocab)
        self.kind_id = {k: i for i, k in enumerate(self.kinds)}
        self.labels: list[str] = []             # free-text occasion names ("BYU vs. Utah", "Maya's Sunday dinner")
        self._label_id: dict[str, int] = {}
        self.occ = Table({"kind": (np.int16, -1), "label": (np.int32, -1), "organizer": (np.int32, -1),
                          "org_kind": (np.int8, 0), "org_id": (np.int32, -1), "ctx": (np.uint8, 255), "place": (np.int64, -1),
                          "lon": (np.float32, np.nan), "lat": (np.float32, np.nan), "day": (np.int32, -1),
                          "start": (np.int16, -1), "dur": (np.int16, 0), "capacity": (np.int32, -1),
                          "series": (np.int32, -1), "status": (np.int8, 0), "origin": (np.int8, 0), "open": (np.bool_, False),
                          "cause": (np.int64, -1), "decision": (np.int64, -1), "created_day": (np.int32, -1),
                          "n_invited": (np.int32, 0), "n_yes": (np.int32, 0), "n_came": (np.int32, 0),
                          "n_talks": (np.int32, 0), "n_new_ties": (np.int32, 0), "n_conflicts": (np.int32, 0)},
                         capacity=1 << 12)
        self.inv = Table({"occ": (np.int64, -1), "person": (np.int32, -1), "inviter": (np.int32, -1),
                          "channel": (np.int8, 0), "thread": (np.int32, -1), "sent_day": (np.int32, -1),
                          "sent_block": (np.int8, 0), "seen_day": (np.int32, -1), "response": (np.int8, 0),
                          "decided_day": (np.int32, -1), "decision": (np.int64, -1), "attended": (np.bool_, False),
                          "arrive": (np.int16, -1), "ride_by": (np.int32, -1), "walk_in": (np.bool_, False)},
                         capacity=1 << 14)
        self.series = Table({"kind": (np.int16, -1), "label": (np.int32, -1), "organizer": (np.int32, -1),
                             "org_kind": (np.int8, 0), "org_id": (np.int32, -1), "ctx": (np.uint8, 255),
                             "place": (np.int64, -1), "lon": (np.float32, np.nan), "lat": (np.float32, np.nan),
                             "weekday": (np.int8, -1), "start": (np.int16, -1), "dur": (np.int16, 0),
                             "every": (np.int16, 7), "first_day": (np.int32, -1), "last_day": (np.int32, -1),
                             "capacity": (np.int32, -1), "origin": (np.int8, 0), "active": (np.bool_, True),
                             "open": (np.bool_, False), "cause": (np.int64, -1), "created_day": (np.int32, -1)},
                            capacity=256)

    # ------------------------------------------------------------------ vocabulary helpers
    def label_id(self, text: str | None) -> int:
        if not text:
            return -1
        if text not in self._label_id:
            self._label_id[text] = len(self.labels)
            self.labels.append(text)
        return self._label_id[text]

    def kind_code(self, kind) -> np.ndarray:
        if isinstance(kind, str):
            if kind not in self.kind_id:
                raise KeyError(f"unregistered occasion kind {kind!r} (add it to config/occasions/*.yaml)")
            return np.int16(self.kind_id[kind])
        return np.array([self.kind_id[k] for k in kind], np.int16)

    def spec(self, code: int) -> dict:
        return self.vocab[self.kinds[int(code)]]

    # ------------------------------------------------------------------ planning
    def plan(self, kind, day, start, dur, *, k: int | None = None, organizer=-1, org_kind="none", org_id=-1, ctx=255,
             place=-1, lon=np.nan, lat=np.nan, capacity=-1, series=-1, origin="engine", open_=False, cause=-1,
             decision=-1, label: str | None = None, created_day=None) -> np.ndarray:
        """Plan k occasions (array arguments broadcast). `start` is minutes after midnight; `dur` minutes."""
        if k is None:
            k = max((len(np.atleast_1d(x)) for x in (organizer, day, start, place) if np.ndim(x)), default=1)
        return self.occ.append(k, kind=self.kind_code(kind), label=self.label_id(label), organizer=organizer,
                               org_kind=ORG_ID[org_kind] if isinstance(org_kind, str) else org_kind, org_id=org_id, ctx=ctx,
                               place=place, lon=lon, lat=lat, day=day, start=start, dur=dur, capacity=capacity,
                               series=series, status=STATUS_ID["planned"],
                               origin=ORIGIN_ID[origin] if isinstance(origin, str) else origin, open=open_, cause=cause,
                               decision=decision, created_day=day if created_day is None else created_day)

    def add_series(self, kind, weekday, start, dur, *, first_day, last_day=-1, every=7, organizer=-1, org_kind="none",
                   org_id=-1, ctx=255, place=-1, lon=np.nan, lat=np.nan, capacity=-1, origin="engine", open_=False,
                   cause=-1, label: str | None = None, created_day=None) -> np.ndarray:
        """A recurring occasion (weekly by default). Instances are planned by `due_series(day)`."""
        k = max((len(np.atleast_1d(x)) for x in (organizer, weekday, start, place) if np.ndim(x)), default=1)
        return self.series.append(k, kind=self.kind_code(kind), label=self.label_id(label), organizer=organizer,
                                  org_kind=ORG_ID[org_kind] if isinstance(org_kind, str) else org_kind, org_id=org_id,
                                  ctx=ctx, place=place, lon=lon, lat=lat, weekday=weekday, start=start, dur=dur,
                                  every=every, first_day=first_day, last_day=last_day, capacity=capacity,
                                  origin=ORIGIN_ID[origin] if isinstance(origin, str) else origin, active=True,
                                  open=open_, cause=cause, created_day=first_day if created_day is None else created_day)

    def due_series(self, day: int, weekday: int) -> np.ndarray:
        """Series ids with an instance due on `day` (active, in range, right weekday and cadence)."""
        S = self.series
        if not S.n:
            return np.empty(0, np.int64)
        fd = S["first_day"]
        ok = S["active"] & (fd <= day) & ((S["last_day"] < 0) | (S["last_day"] >= day))
        ok &= (S["weekday"] == weekday) | (S["weekday"] < 0)
        ok &= ((day - fd) % np.maximum(S["every"], 1)) == 0
        return S["id"][ok]

    def instantiate(self, series_ids, day: int) -> np.ndarray:
        """Plan today's instance of each series (returns occasion ids, aligned with series_ids)."""
        sid = np.atleast_1d(np.asarray(series_ids, np.int64))
        if not len(sid):
            return np.empty(0, np.int64)
        S = self.series
        p = S.pos(sid)
        g = lambda c: S.cols[c][p]   # noqa: E731
        return self.occ.append(len(sid), kind=g("kind"), label=g("label"), organizer=g("organizer"), org_kind=g("org_kind"),
                               org_id=g("org_id"), ctx=g("ctx"), place=g("place"), lon=g("lon"), lat=g("lat"), day=day,
                               start=g("start"), dur=g("dur"), capacity=g("capacity"), series=sid,
                               status=STATUS_ID["planned"], origin=g("origin"), open=g("open"), cause=g("cause"),
                               created_day=day)

    # ------------------------------------------------------------------ invitations and attendance
    def invite(self, occ, people, *, inviter=-1, channel="in_person", thread=-1, day, block=0) -> np.ndarray:
        people = np.atleast_1d(np.asarray(people, np.int64))
        k = len(people)
        if not k:
            return np.empty(0, np.int64)
        ids = self.inv.append(k, occ=occ, person=people, inviter=inviter,
                              channel=CHANNEL_ID[channel] if isinstance(channel, str) else channel, thread=thread,
                              sent_day=day, sent_block=block, response=RESPONSE_ID["pending"])
        occ_arr = np.broadcast_to(np.asarray(occ, np.int64), (k,))
        self._bump("n_invited", occ_arr)
        return ids

    def seen(self, inv_ids, day: int):
        p = self.inv.pos(inv_ids)
        p = p[p >= 0]
        fresh = p[self.inv.cols["seen_day"][p] < 0]
        self.inv.cols["seen_day"][fresh] = day

    def respond(self, inv_ids, response, day: int, decision_ids=None):
        p = self.inv.pos(inv_ids)
        m = p >= 0
        p = p[m]
        code = RESPONSE_ID[response] if isinstance(response, str) else np.broadcast_to(np.asarray(response, np.int8), (len(m),))[m]
        was_yes = self.inv.cols["response"][p] == RESPONSE_ID["yes"]
        self.inv.cols["response"][p] = code
        self.inv.cols["decided_day"][p] = day
        if decision_ids is not None:
            self.inv.cols["decision"][p] = np.broadcast_to(np.asarray(decision_ids, np.int64), (len(m),))[m]
        now_yes = self.inv.cols["response"][p] == RESPONSE_ID["yes"]
        occ = self.inv.cols["occ"][p]
        self._bump("n_yes", occ[now_yes & ~was_yes])
        self._bump("n_yes", occ[was_yes & ~now_yes], -1)

    def attend(self, occ, people, *, arrive=-1, ride_by=-1, inv_ids=None, day: int | None = None) -> np.ndarray:
        """Mark attendance. Invited people are matched to their invitation (pass inv_ids when known); anyone else
        becomes a walk-in row. Returns the invitation-row ids of everyone who came."""
        people = np.atleast_1d(np.asarray(people, np.int64))
        k = len(people)
        if not k:
            return np.empty(0, np.int64)
        occ = np.broadcast_to(np.asarray(occ, np.int64), (k,))
        if inv_ids is None:
            inv_ids = self._find_inv(occ, people)
        inv_ids = np.asarray(inv_ids, np.int64)
        walk = inv_ids < 0
        if walk.any():
            d = day if day is not None else self.occ.get("day", occ[walk])
            new = self.inv.append(int(walk.sum()), occ=occ[walk], person=people[walk], channel=CHANNEL_ID["in_person"],
                                  sent_day=d, response=RESPONSE_ID["yes"], walk_in=True)
            inv_ids = inv_ids.copy()
            inv_ids[walk] = new
        p = self.inv.pos(inv_ids)
        self.inv.cols["attended"][p] = True
        self.inv.cols["arrive"][p] = np.broadcast_to(np.asarray(arrive, np.int16), (k,))
        self.inv.cols["ride_by"][p] = np.broadcast_to(np.asarray(ride_by, np.int32), (k,))
        self._bump("n_came", occ)
        return inv_ids

    def _find_inv(self, occ: np.ndarray, people: np.ndarray) -> np.ndarray:
        """Invitation row id for each (occasion, person) pair, −1 if none (latest invitation wins)."""
        I = self.inv
        if not I.n:
            return np.full(len(occ), -1, np.int64)
        key_have = (I["occ"].astype(np.int64) << 24) ^ I["person"].astype(np.int64)
        order = np.argsort(key_have, kind="stable")
        ks = key_have[order]
        key = (occ.astype(np.int64) << 24) ^ people.astype(np.int64)
        p = np.searchsorted(ks, key, side="right") - 1
        ok = (p >= 0) & (ks[np.maximum(p, 0)] == key)
        rows = order[np.maximum(p, 0)]
        ok &= (I["occ"][rows] == occ) & (I["person"][rows] == people)
        return np.where(ok, I["id"][rows], -1)

    def _bump(self, col: str, occ_ids: np.ndarray, by: int = 1):
        if not len(occ_ids):
            return
        p = self.occ.pos(occ_ids)
        p = p[p >= 0]
        np.add.at(self.occ.cols[col], p, by)

    def mark(self, occ_ids, status: str):
        self.occ.set("status", occ_ids, STATUS_ID[status])

    def note_scene(self, occ_ids, talks=0, new_ties=0, conflicts=0):
        """Encounters report what happened at occasions (counts per occasion id; repeated ids accumulate)."""
        occ_ids = np.atleast_1d(np.asarray(occ_ids, np.int64))
        p = self.occ.pos(occ_ids)
        m = p >= 0
        for col, v in (("n_talks", talks), ("n_new_ties", new_ties), ("n_conflicts", conflicts)):
            v = np.broadcast_to(np.asarray(v, np.int64), (len(occ_ids),))[m]
            if np.any(v):
                np.add.at(self.occ.cols[col], p[m], v.astype(np.int32))

    # ------------------------------------------------------------------ queries
    def on_day(self, day: int, status: str | None = None) -> np.ndarray:
        m = self.occ["day"] == day
        if status is not None:
            m &= self.occ["status"] == STATUS_ID[status]
        return self.occ["id"][m]

    def overlapping(self, day: int, t0: int, t1: int, status: str = "planned") -> np.ndarray:
        """Occasions on `day` that overlap the minutes [t0, t1)."""
        O = self.occ
        s = O["start"].astype(np.int32)
        m = (O["day"] == day) & (O["status"] == STATUS_ID[status]) & (s < t1) & (s + O["dur"].astype(np.int32) > t0)
        return O["id"][m]

    def invitations(self, occ_id: int) -> np.ndarray:
        return self.inv["id"][self.inv["occ"] == occ_id]

    def attendees(self, occ_id: int) -> np.ndarray:
        m = (self.inv["occ"] == occ_id) & self.inv["attended"]
        return self.inv["person"][m]

    def of_person(self, i: int, since: int = -10**9) -> np.ndarray:
        """Invitation-row ids for a person (invited or walked in) since a day."""
        m = (self.inv["person"] == i) & (self.inv["sent_day"] >= since)
        return self.inv["id"][m]

    def describe(self, oid: int) -> dict:
        r = self.occ.row(int(oid))
        if not r:
            return {}
        spec = self.spec(r["kind"])
        r["kind"] = self.kinds[r["kind"]]
        r["kind_label"] = spec.get("label", r["kind"])
        r["name"] = self.labels[r["label"]] if r["label"] >= 0 else None
        r["status"] = STATUS[r["status"]]
        r["origin"] = ORIGINS[r["origin"]]
        r["org_kind"] = ORG_KINDS[r["org_kind"]]
        for c in ("lon", "lat"):
            r[c] = None if np.isnan(r[c]) else float(r[c])
        return r

    def invitation_rows(self, inv_ids) -> list[dict]:
        out = []
        for i in np.atleast_1d(inv_ids):
            r = self.inv.row(int(i))
            if not r:
                continue
            r["channel"] = CHANNELS[r["channel"]]
            r["response"] = RESPONSES[r["response"]]
            out.append(r)
        return out

    # ------------------------------------------------------------------ memory management
    def thin(self, before_day: int, keep_occ: np.ndarray | None = None):
        """Drop old invitations that went nowhere (not attended, not linked to a kept decision or a listed occasion)."""
        I = self.inv
        if not I.n:
            return 0
        old = I["sent_day"] < before_day
        keep = ~old | I["attended"]
        if keep_occ is not None and len(keep_occ):
            keep |= np.isin(I["occ"], keep_occ)
        return I.keep(keep)


def thin_decisions(log: DecisionLog, before_day: int, keep_event_mask_fn=None, keep_ids: np.ndarray | None = None) -> int:
    """Drop old decisions not tied to a kept event (keep_event_mask_fn(event_ids) -> bool) nor listed in keep_ids."""
    T = log.t
    if not T.n:
        return 0
    old = T["day"] < before_day
    keep = ~old
    ev = T["event"]
    if keep_event_mask_fn is not None:
        has = ev >= 0
        km = np.zeros(T.n, bool)
        if has.any():
            km[has] = keep_event_mask_fn(ev[has])
        keep |= km
    if keep_ids is not None and len(keep_ids):
        keep |= np.isin(T["id"], keep_ids)
    return T.keep(keep)
