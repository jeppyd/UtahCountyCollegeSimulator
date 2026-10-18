"""Trace: what led to anything in the world, and what it led to — for one life or the whole valley.

`trace(sim, ref, dir, depth)` builds a causal graph around one item (an event, a decision, an occasion, a person, a tie
"lo-hi", a feeling "mood@12", a place "complex:4") by walking every recorded link:

    event   ← its parent event (`cause`), the decision that produced it, its typed causes (occasion, tie, person,
              place, feeling, earlier events — engine/ledger.CauseLinks, with their roles from engine/provenance)
            → the events it caused, the events and decisions that cite it, the feelings it moved (decaying effects)
    decision← the events, people, occasions and feelings its factors point at; → what it produced
    occasion← who organized it and why; → who met whom there, what happened there, the decisions to go
    tie     ← where they met, who introduced them; → what happened between them
    feeling ← its decomposition *today* (mechanism terms and the events whose effects are still decaying)
    person  → their most notable events, each traced in turn

Nodes carry a day and block (and a clock minute where known), the people involved, one plain line (event `story`
templates with names) and a weight; links carry a kind (caused, decided_by, factor, attended, met_at, introduced,
contributed, led_to), a weight and words. Nothing is invented: every node and link is a ledger row, and what a cap
leaves out is counted (`more_back` / `more_fwd` per node, `cut` overall). Decomposition terms and factors are
"contributed" links with their value; they are the model's own terms, not an interpretation.

`chains(sim, since, until, people, root)` is the population view: how often events of one kind led to events of
another (through parent causes, typed causes and decisions), with example instances, and which decision factors were
the top reason for each outcome ("of 340 declined invitations, 41% had tiredness as the top reason").

Reading never changes the world (no random numbers, no rehearsal of memories).
"""
from __future__ import annotations

import weakref

import numpy as np

from ..engine import clock
from ..engine.ledger import CAUSE_ID, CAUSE_KINDS, CONSTRAINT
from ..engine.provenance import (MECH_BASE, ROLE_BASE, VAR_BASE, note_info, place_ref, split_place, split_state,
                                 state_ref, var_codes)
from ..engine.state import CTX, CTX_ID, EdgeStore
from .person import synthetic_name

LINK_KINDS = ("caused", "decided_by", "factor", "attended", "met_at", "introduced", "contributed", "led_to")
MAX_NODES = 80
FANOUT = 8
_MASK56 = (1 << 56) - 1

INTENTION_WORDS = {1: ("ask {b} out", "asking {b} out"), 2: ("reconnect with {b}", "reconnecting with {b}"),
                   3: ("meet new people", "meeting new people"), 4: ("study more", "studying more"),
                   5: ("find work", "finding work"), 6: ("get back to church", "getting back to church")}
UNITS_WORDS = {"logit": "log-odds", "utility": "utility", "log_rate": "log of the rate", "log": "log scale",
               "probability": "chance"}


def lc(s: str) -> str:
    """Lower-case a label for use mid-sentence, leaving names and acronyms alone ("Provo–Orem", "GPA", "BYU")."""
    words = str(s).split(" ")
    if words and words[0][:1].isupper() and not words[0][1:2].isupper():
        words[0] = words[0][:1].lower() + words[0][1:]
    return " ".join(words)


def positive_outcome(spec: dict, outcome=None):
    """The outcome a decision's log-odds favor (a factor > 0 pushed toward it): the kind's `positive`, else its first
    outcome; `positive: any` means every outcome is a "yes" (which practice someone took up), so it is the outcome."""
    pos = spec.get("positive")
    if pos == "any":
        return outcome
    return pos or (spec.get("outcomes") or [None])[0]


# ----------------------------------------------------------------------------- indexes (cached per world)
class _Index:
    """Sorted lookups over the ledgers, rebuilt when they grow (one trace touches each many times)."""

    def __init__(self, sim):
        self.sim = sim
        self.sig = None

    def fresh(self):
        sim = self.sim
        sig = (sim.log.n, sim.causes.t.n, sim.decisions.t.n, sim.causes.t.next_id, sim.decisions.t.next_id)
        if sig == self.sig:
            return self
        self.sig = sig
        log, C, D = sim.log, sim.causes.t, sim.decisions.t
        n = log.n
        self.cause_order = np.argsort(log["cause"], kind="stable")
        self.cause_sorted = log["cause"][self.cause_order]
        dec = log["decision"]
        self.dec_order = np.argsort(dec, kind="stable")
        self.dec_sorted = dec[self.dec_order]
        b = log["b"]
        pair = b >= 0
        self.pair_rows = np.flatnonzero(pair)
        pk = EdgeStore.make_keys(log["a"][pair].astype(np.int64), b[pair].astype(np.int64))
        o = np.argsort(pk, kind="stable")
        self.pair_rows, self.pair_sorted = self.pair_rows[o], pk[o]
        self.c_event_order = np.argsort(C["event"], kind="stable")
        self.c_event_sorted = C["event"][self.c_event_order]
        ck = (C["kind"].astype(np.int64) << 56) | (C["ref"] & _MASK56)
        self.c_ref_order = np.argsort(ck, kind="stable")
        self.c_ref_sorted = ck[self.c_ref_order]
        fr = D["f_ref"]
        fk = D["f_refkind"].astype(np.int64)
        has = (fr >= 0) & (fk >= 0)
        rows, cols = np.nonzero(has)
        key = (fk[rows, cols] << 56) | (fr[rows, cols] & _MASK56)
        o = np.argsort(key, kind="stable")
        self.f_key, self.f_row, self.f_col = key[o], rows[o], cols[o]
        self.n = n
        return self

    @staticmethod
    def _range(sorted_arr, order, value):
        lo = np.searchsorted(sorted_arr, value, side="left")
        hi = np.searchsorted(sorted_arr, value, side="right")
        return order[lo:hi]

    def children(self, e: int) -> np.ndarray:
        return self._range(self.cause_sorted, self.cause_order, e)

    def by_decision(self, d: int) -> np.ndarray:
        return self._range(self.dec_sorted, self.dec_order, d)

    def between(self, key: int) -> np.ndarray:
        return self._range(self.pair_sorted, self.pair_rows, key)

    def causes_of(self, e: int) -> np.ndarray:
        """Row positions in CauseLinks.t of the typed causes of event e."""
        return self._range(self.c_event_sorted, self.c_event_order, e)

    def cited_by(self, kind: str, ref: int) -> np.ndarray:
        """Row positions in CauseLinks.t of the typed causes that point at (kind, ref)."""
        return self._range(self.c_ref_sorted, self.c_ref_order, (CAUSE_ID[kind] << 56) | (int(ref) & _MASK56))

    def factor_refs(self, kind: str, ref: int):
        """(decision row positions, factor columns) of factors pointing at (kind, ref)."""
        key = (CAUSE_ID[kind] << 56) | (int(ref) & _MASK56)
        lo = np.searchsorted(self.f_key, key, side="left")
        hi = np.searchsorted(self.f_key, key, side="right")
        return self.f_row[lo:hi], self.f_col[lo:hi]


_INDEX: "weakref.WeakKeyDictionary" = weakref.WeakKeyDictionary()


def index(sim) -> _Index:
    ix = _INDEX.get(sim)
    if ix is None:
        ix = _INDEX[sim] = _Index(sim)
    return ix.fresh()


# ----------------------------------------------------------------------------- words
class _Words:
    """Names and plain phrases for people, places, events and decisions (cached for one trace)."""

    def __init__(self, sim):
        self.sim = sim
        self.P = sim.w.P
        self._names: dict[int, str] = {}
        self._cx: dict[int, str] | None = None

    def name(self, i) -> str:
        i = int(i)
        if i < 0 or i >= self.P.n:
            return "someone"
        if i not in self._names:
            self._names[i] = synthetic_name(self.P, i)
        return self._names[i]

    def complex_name(self, c: int) -> str:
        if self._cx is None:
            cx = self.sim.w.complexes
            self._cx = dict(zip(cx["complex_id"].to_list(), cx["name"].to_list())) if cx is not None and len(cx) else {}
        return str(self._cx.get(int(c)) or f"complex {c}")

    def place(self, ctx: str, pid: int) -> str:
        w = self.sim.w
        act = self.sim.systems.get("activity")
        try:
            if ctx == "unit" and pid >= 0:
                cx = int(w.units.complex_id[pid]) if pid < len(w.units.complex_id) else -1
                return f"their apartment at {self.complex_name(cx)}" if cx >= 0 else "an apartment"
            if ctx == "complex" and pid >= 0:
                return self.complex_name(pid)
            if ctx == "gathering":
                if pid >= 0 and pid < len(w.units.complex_id) and w.units.complex_id[pid] >= 0:
                    return f"a get-together at {self.complex_name(int(w.units.complex_id[pid]))}"
                return "a get-together"
            if ctx == "ward" and pid >= 0:
                kind = str(w.wards["kind"][pid]).replace("byu_ysa", "BYU student").replace("ysa", "young single adult")
                return f"a {kind.replace('_', ' ')} ward"
            if ctx == "work" and pid >= 0 and pid < len(w.employers["name"]):
                return str(w.employers["name"][pid])
            if ctx in ("venue", "gym", "dance", "outdoors") and act is not None and 0 <= pid < len(act.v_name):
                return str(act.v_name[pid])
            if ctx in ("club", "team") and w.groups and 0 <= pid < len(w.groups["name"]):
                return str(w.groups["name"][pid])
            if ctx == "congregation" and w.congregations and 0 <= pid < len(w.congregations.get("name", [])):
                return str(w.congregations["name"][pid])
            if ctx == "campus":
                return {1: "BYU", 2: "UVU"}.get(pid, "campus")
        except Exception:   # noqa: BLE001 — a missing name never breaks a trace
            pass
        return {"class": "class", "fhe": "an FHE group", "app": "a dating app", "date": "a date", "family": "family",
                "preexisting": "knew each other before", "hangout": "hanging out", "online": "online",
                "institute": "institute", "occasion": "an occasion", "unit": "home", "work": "work", "ward": "church",
                "gym": "the gym", "venue": "out somewhere", "dance": "a dance", "outdoors": "outdoors",
                "club": "a club", "team": "a team", "complex": "their complex"}.get(ctx, ctx.replace("_", " "))

    def event_line(self, eid: int) -> str:
        sim = self.sim
        log = sim.log
        spec = sim.reg.events[sim.reg.event_names[log["type"][eid]]]
        a, b = int(log["a"][eid]), int(log["b"][eid])
        tpl = spec.story or ("{a}: " + lc(spec.label))
        if spec.id in ("intention_formed", "plan_abandoned"):
            k = int(round(float(log["value"][eid])))
            w = INTENTION_WORDS.get(k)
            if w:
                tpl = ("{a} set out to " + w[0]) if spec.id == "intention_formed" else ("{a} gave up on " + w[1])
        elif spec.id in ("whatif_shock", "whatif_practice", "intervention_exposure"):
            from .explain import event_record
            r = event_record(sim, eid)
            tpl = r.get("story") or ("{a}: " + lc(str(r.get("label", spec.label))))
        return tpl.replace("{a}", self.name(a)).replace("{b}", self.name(b) if b >= 0 else "someone")

    def var_label(self, var: str) -> str:
        spec = self.sim.reg.variables.get(var)
        return spec.label if spec else var.replace("_", " ")


# ----------------------------------------------------------------------------- refs
def parse_ref(ref) -> tuple[str, object]:
    """'event:12' → ('event', 12); 'tie:3-9' → ('tie', (3, 9)); 'var:mood@12' / 'state:mood@12' → ('state', ('mood', 12));
    'place:complex:4' → ('place', ('complex', 4)); 'person:5' → ('person', 5)."""
    if isinstance(ref, dict):
        ref = f"{ref.get('kind')}:{ref.get('id')}"
    s = str(ref).strip()
    kind, _, rest = s.partition(":")
    kind = kind.lower()
    if kind in ("event", "decision", "occasion", "person"):
        return kind, int(rest)
    if kind == "tie":
        a, _, b = rest.replace(",", "-").partition("-")
        a, b = int(a), int(b)
        return "tie", (min(a, b), max(a, b))
    if kind in ("var", "state"):
        var, _, who = rest.partition("@")
        return "state", (var, int(who))
    if kind == "place":
        ctx, _, pid = rest.partition(":")
        if not pid:
            c, p = split_place(int(ctx))
            return "place", (c, p)
        return "place", (ctx, int(pid))
    raise ValueError(f"unknown ref {ref!r}: use event:<id>, decision:<id>, occasion:<id>, person:<id>, tie:<a>-<b>, "
                     f"var:<field>@<person> or place:<kind>:<id>")


def node_key(kind: str, ident) -> str:
    if kind == "other":
        return f"{ident[0]}:{ident[1]}"
    if kind == "tie":
        return f"tie:{ident[0]}-{ident[1]}"
    if kind == "state":
        return f"state:{ident[0]}@{ident[1]}"
    if kind == "place":
        return f"place:{ident[0]}:{ident[1]}"
    return f"{kind}:{ident}"


def _ref_json(kind: str, ident) -> dict:
    if kind == "other":
        return {"kind": ident[0], "id": int(ident[1])}
    if kind == "tie":
        return {"kind": "tie", "id": f"{ident[0]}-{ident[1]}"}
    if kind == "state":
        return {"kind": "var", "id": f"{ident[0]}@{ident[1]}"}
    if kind == "place":
        return {"kind": "place", "id": f"{ident[0]}:{ident[1]}"}
    return {"kind": kind, "id": int(ident)}


# ----------------------------------------------------------------------------- the graph
class _Graph:
    def __init__(self, sim, max_nodes: int, fanout: int):
        self.sim = sim
        self.ix = index(sim)
        self.W = _Words(sim)
        self.nodes: dict[str, dict] = {}
        self.links: dict[tuple, dict] = {}
        self.max_nodes = max_nodes
        self.fanout = fanout
        self.cut = 0

    # ---------------------------------------------------------------- nodes
    def node(self, kind: str, ident, depth: int = 0, hint_day: int | None = None) -> str | None:
        """Add (or find) a node; None when the item no longer exists (thinned) or the cap is reached."""
        key = node_key(kind, ident)
        if key in self.nodes:
            n = self.nodes[key]
            if abs(depth) < abs(n["depth"]):
                n["depth"] = depth
            return key
        if len(self.nodes) >= self.max_nodes:
            self.cut += 1
            return None
        n = getattr(self, f"_make_{kind}")(ident, hint_day)
        if n is None:
            return None
        n.update(key=key, kind=n.get("kind", kind), ref=_ref_json(kind, ident), depth=depth, more_back=0, more_fwd=0)
        self.nodes[key] = n
        return key

    def _make_event(self, eid, hint_day):
        log = self.sim.log
        eid = int(eid)
        if eid < 0 or eid >= log.n:
            return None
        spec = self.sim.reg.events[self.sim.reg.event_names[log["type"][eid]]]
        a, b, blk = int(log["a"][eid]), int(log["b"][eid]), int(log["block"][eid])
        people = [a] + ([b] if b >= 0 else [])
        return {"day": int(log["day"][eid]), "block": blk, "minute": int(clock.START[min(blk, clock.N_BLOCKS - 1)]),
                "people": people, "lane": a, "label": self.W.event_line(eid), "type": spec.id, "category": spec.category,
                "weight": float(spec.salience), "detail": {"value": round(float(log["value"][eid]), 3), "title": spec.label}}

    def _make_decision(self, did, hint_day):
        D = self.sim.decisions
        d = D.get(int(did))
        if not d:
            return None
        spec = D.vocab[d["kind"]]
        units = d.get("units", "logit")
        outcome = str(d["outcome"]).replace("_", " ")
        who = self.W.name(d["agent"])
        other = f" (about {self.W.name(d['other'])})" if d.get("other") is not None else ""
        prob = d.get("prob")
        chance = f" — the model gave this a {prob:.0%} chance" if prob is not None and np.isfinite(prob) else ""
        factors = _factor_refs(self.sim, self.W, d["factors"])
        people = [int(d["agent"])] + ([int(d["other"])] if d.get("other") is not None else [])
        return {"day": int(d["day"]), "block": int(d["block"]), "minute": int(clock.START[min(int(d["block"]), clock.N_BLOCKS - 1)]),
                "people": people, "lane": int(d["agent"]), "label": f"{who}: {lc(d['label'])} → {outcome}{other}",
                "type": d["kind"], "category": "decision", "weight": float(prob) if prob is not None else 0.5,
                "detail": {"title": d["label"], "outcome": outcome, "prob": prob, "units": units,
                           "units_words": UNITS_WORDS.get(units, units), "base": d["base"], "total": d["total"],
                           "factors": factors, "positive": positive_outcome(spec, d["outcome"])}}

    def _make_occasion(self, oid, hint_day):
        B = self.sim.book
        r = B.describe(int(oid))
        if not r:
            return None
        org = int(r["organizer"])
        came = B.attendees(int(oid))
        name = r.get("name") or r.get("kind_label") or "an occasion"
        host = f" hosted by {self.W.name(org)}" if org >= 0 else ""
        people = ([org] if org >= 0 else []) + [int(x) for x in came[:12] if int(x) != org]
        start = int(r["start"]) if r["start"] >= 0 else None
        blk = int(clock.block_of(start)) if start is not None else 2
        return {"day": int(r["day"]), "block": max(blk, 0), "minute": start, "people": people,
                "lane": org if org >= 0 else (people[0] if people else None),
                "label": f"{name}{host}" + (f" at {clock.hhmm(start)}" if start is not None else ""),
                "type": r["kind"], "category": "occasion", "weight": 0.6,
                "detail": {"title": r.get("kind_label"), "status": r["status"], "invited": r["n_invited"], "said_yes": r["n_yes"],
                           "came": r["n_came"], "talks": r["n_talks"], "new_ties": r["n_new_ties"], "conflicts": r["n_conflicts"],
                           "came_ids": [int(x) for x in came[:40]], "organizer": org if org >= 0 else None}}

    def _make_person(self, i, hint_day):
        i = int(i)
        if i < 0 or i >= self.sim.w.P.n:
            return None
        return {"day": hint_day, "block": None, "minute": None, "people": [i], "lane": i, "label": self.W.name(i),
                "type": "person", "category": "person", "weight": 0.5, "timeless": hint_day is None, "detail": {}}

    def _make_tie(self, pair, hint_day):
        E = self.sim.w.E
        lo, hi = pair
        k = int(EdgeStore.make_keys(np.array([lo]), np.array([hi]))[0])
        e = int(E.find(np.array([k], np.int64))[0])
        W = self.W
        if e < 0:
            return {"day": hint_day, "block": None, "minute": None, "people": [lo, hi], "lane": lo,
                    "label": f"{W.name(lo)} and {W.name(hi)} (no longer in touch)", "type": "tie", "category": "tie",
                    "weight": 0.3, "detail": {"gone": True}}
        oc = int(E["origin_ctx"][e])
        where = CTX[oc] if oc < len(CTX) else "?"
        stage = int(E["stage"][e])
        st = {0: "strangers", 1: "acquaintances", 2: "casual friends", 3: "friends", 4: "close friends"}.get(stage, "")
        from ..engine.state import Tie
        flags = Tie.decode(int(E["flags"][e]))
        if "spouse" in flags:
            st = "married"
        elif "romantic" in flags:
            st = "a couple"
        elif "ex" in flags:
            st = "exes"
        top = int(E["top_ctx"][e])
        th, tot = float(E["top_h"][e]), float(E["hours"][e])
        detail = {"stage": st, "met": W.place(where, int(E["origin_place"][e])) if where != "occasion" else "an occasion",
                  "first_day": int(E["first_day"][e]), "last_day": int(E["last_day"][e]), "hours": round(tot, 1),
                  "closeness": round(float(E["closeness"][e]), 2), "liking": round(float(E["liking"][e]), 2),
                  "flags": flags}
        if th > 0 and top < len(CTX):
            detail["mostly"] = W.place(CTX[top], int(E["top_place"][e]))
            detail["mostly_share"] = round(th / max(tot, 1e-6), 2)
        if E["introducer"][e] >= 0:
            detail["introducer"] = int(E["introducer"][e])
        return {"day": int(E["first_day"][e]), "block": None, "minute": None, "people": [lo, hi], "lane": lo,
                "label": f"{W.name(lo)} and {W.name(hi)}: {st}", "type": "tie", "category": "tie",
                "weight": float(np.clip(E["closeness"][e], 0.2, 1.0)), "detail": detail}

    def _make_state(self, vi, hint_day):
        var, i = vi
        P = self.sim.w.P
        if var not in P or i < 0 or i >= P.n:
            return None
        v = P[var][i]
        val = float(v) if np.ndim(v) == 0 and np.issubdtype(np.asarray(v).dtype, np.number) else None
        now = self.sim.w.day
        return {"day": hint_day if hint_day is not None else now, "block": None, "minute": None, "people": [int(i)],
                "lane": int(i), "label": f"{self.W.name(i)}'s {lc(self.W.var_label(var))}", "type": var,
                "category": "state", "weight": 0.5,
                "detail": {"var": var, "now": None if val is None or not np.isfinite(val) else round(val, 3), "today": now}}

    def _make_place(self, cp, hint_day):
        ctx, pid = cp
        return {"day": hint_day, "block": None, "minute": None, "people": [], "lane": None,
                "label": self.W.place(ctx, pid), "type": ctx, "category": "place", "weight": 0.4,
                "timeless": True, "detail": {"ctx": ctx, "id": pid}}

    def _make_other(self, kr, hint_day):
        kind, ref = kr
        return {"kind": kind, "day": hint_day, "block": None, "minute": None, "people": [], "lane": None,
                "label": f"{kind} {ref}", "type": kind, "category": kind, "weight": 0.3, "timeless": True, "detail": {}}

    # ---------------------------------------------------------------- links
    def link(self, src: str | None, dst: str | None, kind: str, weight=None, words: str | None = None):
        if src is None or dst is None or src == dst:
            return
        key = (src, dst)
        w = None if weight is None or not np.isfinite(weight) else round(float(weight), 3)
        if key in self.links:
            L = self.links[key]
            if words and words not in L["words"]:
                L["words"].append(words)
            if w is not None:
                L["weight"] = w if L["weight"] is None else max(L["weight"], w, key=abs)
            if LINK_KINDS.index(kind) < LINK_KINDS.index(L["kind"]):
                L["kind"] = kind
            return
        self.links[key] = {"source": src, "target": dst, "kind": kind, "weight": w, "words": [words] if words else []}

    # ---------------------------------------------------------------- cause rows
    def _cause_words(self, note: int, weight: float) -> tuple[str, str]:
        info = note_info(self.sim, note)
        if info is None:
            return "contributed", ""
        if info["type"] == "role":
            return info["link"], info["words"]
        if info["type"] == "mechanism":
            return "contributed", info["words"]
        if info["type"] == "variable":
            return "contributed", info["words"]
        return "factor", info["words"]

    def _cause_target(self, kind: str, ref: int, hint_day, depth):
        """Node for a typed-cause ref."""
        if kind == "event":
            return self.node("event", int(ref), depth, hint_day)
        if kind == "decision":
            return self.node("decision", int(ref), depth, hint_day)
        if kind == "occasion":
            return self.node("occasion", int(ref), depth, hint_day)
        if kind == "person":
            return self.node("person", int(ref), depth, hint_day)
        if kind == "tie":
            lo, hi = int(ref) >> 32, int(ref) & 0xFFFFFFFF
            return self.node("tie", (lo, hi), depth, hint_day)
        if kind == "state":
            var, i = split_state(self.sim, int(ref))
            return self.node("state", (var, int(i)), depth, hint_day)
        if kind == "place":
            return self.node("place", split_place(int(ref)), depth, hint_day)
        return self.node("other", (kind, int(ref)), depth, hint_day)

    # ---------------------------------------------------------------- expansion: what led to it
    def back(self, key: str, depth: int) -> list[str]:
        n = self.nodes[key]
        cands = getattr(self, f"_back_{n['kind']}", lambda *_: [])(n, depth)
        return self._admit(n, cands, "more_back")

    def fwd(self, key: str, depth: int) -> list[str]:
        n = self.nodes[key]
        cands = getattr(self, f"_fwd_{n['kind']}", lambda *_: [])(n, depth)
        return self._admit(n, cands, "more_fwd")

    def _admit(self, n: dict, cands: list, counter: str) -> list[str]:
        """cands: (priority, make() -> key or None, link args). Keeps the `fanout` most important; counts the rest."""
        cands.sort(key=lambda c: -c[0])
        out = []
        for k, (_, make, lk) in enumerate(cands):
            if k >= self.fanout:
                n[counter] += len(cands) - k
                break
            other = make()
            if other is None:
                n[counter] += 1
                continue
            src, dst = (other, n["key"]) if counter == "more_back" else (n["key"], other)
            self.link(src, dst, *lk)
            out.append(other)
        return out

    def _back_event(self, n, depth):
        sim, ix = self.sim, self.ix
        log = sim.log
        eid = int(n["ref"]["id"])
        day = n["day"]
        cands = []
        par = int(log["cause"][eid])
        if par >= 0:
            words = "the same moment, for the other person" if _is_mirror(log, par, eid) else "led to this"
            cands.append((3.0, lambda p=par: self.node("event", p, depth - 1, day), ("caused", 1.0, words)))
        did = int(log["decision"][eid])
        if did >= 0:
            cands.append((2.9, lambda d=did: self.node("decision", d, depth - 1, day), ("decided_by", None, "the choice behind it")))
        C = sim.causes.t
        rows = ix.causes_of(eid)
        for r in rows:
            kind = CAUSE_KINDS[int(C.cols["kind"][r])]
            ref = int(C.cols["ref"][r])
            w = float(C.cols["weight"][r])
            note = int(C.cols["note"][r])
            lk, words = self._cause_words(note, w)
            if lk == "caused" and note == ROLE_BASE + list(_roles()).index("mirror"):
                words = "the same moment, for the other person"
            pri = 2.0 + min(abs(w), 1.0) if kind in ("event", "decision", "occasion") else 1.0 + min(abs(w), 1.0)
            cands.append((pri, lambda k=kind, rf=ref: self._cause_target(k, rf, day, depth - 1), (lk, w, words)))
        return cands

    def _back_decision(self, n, depth):
        sim = self.sim
        did = int(n["ref"]["id"])
        d = n["detail"]
        day = n["day"]
        cands = []
        for f in d["factors"]:
            ref = f.get("ref")
            if not ref:
                continue
            kind, rid = parse_ref(f"{ref['kind']}:{ref['id']}")
            v = f["value"]
            words = f.get("words") or f["label"]
            if f.get("constraint"):
                words = f"couldn't: {words}"
            cands.append((1.5 + min(abs(v), 2.0), lambda k=kind, r=rid: self.node(k, r, depth - 1, day), ("factor", v, words)))
        row = sim.decisions.t.row(did)
        if row and row.get("occasion", -1) >= 0:
            oid = int(row["occasion"])
            cands.append((3.0, lambda o=oid: self.node("occasion", o, depth - 1, day), ("attended", None, "what they were deciding about")))
        return cands

    def _back_occasion(self, n, depth):
        B = self.sim.book
        oid = int(n["ref"]["id"])
        r = B.occ.row(oid)
        day = n["day"]
        cands = []
        if r.get("organizer", -1) >= 0:
            cands.append((2.0, lambda i=int(r["organizer"]): self.node("person", i, depth - 1, day), ("led_to", None, "organized it")))
        if r.get("decision", -1) >= 0:
            cands.append((2.5, lambda d=int(r["decision"]): self.node("decision", d, depth - 1, day), ("decided_by", None, "the decision to host")))
        if r.get("cause", -1) >= 0:
            cands.append((2.4, lambda e=int(r["cause"]): self.node("event", e, depth - 1, day), ("caused", None, "led to it")))
        return cands

    def _back_tie(self, n, depth):
        E = self.sim.w.E
        lo, hi = (int(x) for x in n["ref"]["id"].split("-"))
        e = int(E.find(EdgeStore.make_keys(np.array([lo]), np.array([hi])))[0])
        if e < 0:
            return []
        day = int(E["first_day"][e])
        cands = []
        oc, op = int(E["origin_ctx"][e]), int(E["origin_place"][e])
        if oc == CTX_ID["occasion"] and op >= 0:
            cands.append((3.0, lambda o=op: self.node("occasion", o, depth - 1, day), ("met_at", None, "where they first met")))
        elif oc < len(CTX) and CTX[oc] != "preexisting":
            cands.append((2.5, lambda c=CTX[oc], p=op: self.node("place", (c, p), depth - 1, day), ("met_at", None, "where they first met")))
        if E["introducer"][e] >= 0:
            cands.append((2.8, lambda i=int(E["introducer"][e]): self.node("person", i, depth - 1, day),
                          ("introduced", None, "brought them together")))
        return cands

    def _back_state(self, n, depth):
        """A feeling's decomposition — only for today (decompositions are composed daily, not stored)."""
        sim = self.sim
        var, i = n["ref"]["id"].split("@")
        i = int(i)
        if n["day"] is not None and n["day"] < sim.w.day - 3:
            n["detail"]["note"] = (f"How this felt is broken down only for today (day {sim.w.day}); this was recorded on day "
                                   f"{n['day']}, so its causes at the time are the ones linked to the event that cited it.")
            return []
        emo = sim.systems.get("emotion")
        if emo is None or var not in emo.contrib:
            return []
        from .explain import explain_state
        x = explain_state(sim, i, var)
        n["detail"]["decomposition"] = [{"term": t["term"], "label": t["label"], "value": round(t["value"], 3),
                                         "evidence": t["evidence"]} for t in x["terms"][:10]]
        n["detail"]["asof"] = sim.w.day
        cands = []
        P = sim.w.P
        for t in x["terms"][:8]:
            if abs(t["value"]) < 0.01:
                continue
            src = next((s for s in t["sources"] if s in P.specs and s != var), None)
            if src is None:
                continue
            cands.append((1.0 + min(abs(t["value"]) * 5, 1.0),
                          lambda s=src: self.node("state", (s, i), depth - 1, sim.w.day), ("contributed", t["value"], t["label"])))
        for eff in x["events"][:6]:
            ev = eff.get("event")
            if not ev:
                continue
            cands.append((2.0 + min(abs(eff["value"]) * 5, 1.0), lambda e=int(ev["id"]): self.node("event", e, depth - 1),
                          ("contributed", eff["value"], f"still affecting their {lc(self.W.var_label(var))}")))
        if var == "mood" and any(t["term"] == "rumination" and abs(t["value"]) >= 0.005 for t in x["terms"]):
            for e in self._ruminated(i)[:3]:
                cands.append((1.8, lambda e=e: self.node("event", e, depth - 1), ("contributed", None, "a memory they keep going back to")))
        return cands

    def _ruminated(self, i: int) -> list[int]:
        mem = self.sim.memory
        if mem.n == 0:
            return []
        rows = np.flatnonzero((mem["agent"] == i) & (mem["valence"].astype(np.float32) < -0.1) & (mem["rehearsal"] > 0))
        if not len(rows):
            return []
        rows = rows[np.argsort(-mem["rehearsal"][rows].astype(np.int32))]
        return [int(e) for e in mem["event"][rows] if 0 <= int(e) < self.sim.log.n]

    # ---------------------------------------------------------------- expansion: what it led to
    def _fwd_event(self, n, depth):
        sim, ix = self.sim, self.ix
        eid = int(n["ref"]["id"])
        log = sim.log
        cands = []
        sal = _salience(sim)
        mirror_note = ROLE_BASE + list(_roles()).index("mirror")
        C = sim.causes.t
        mirrored = set()
        for r in ix.cited_by("event", eid):
            ch = int(C.cols["event"][r])
            note = int(C.cols["note"][r])
            if note == mirror_note:
                mirrored.add(ch)
            lk, words = self._cause_words(note, float(C.cols["weight"][r]))
            cands.append((1.5 + sal[log["type"][ch]], lambda e=ch: self.node("event", e, depth + 1),
                          (lk, float(C.cols["weight"][r]), words or "contributed to this")))
        for ch in ix.children(eid):
            ch = int(ch)
            words = "the same moment, for the other person" if ch in mirrored or _is_mirror(log, eid, ch) else "led to this"
            cands.append((2.0 + sal[log["type"][ch]], lambda e=ch: self.node("event", e, depth + 1), ("caused", 1.0, words)))
        rows, cols = ix.factor_refs("event", eid)
        D = sim.decisions
        for r, c in zip(rows[:40], cols[:40]):
            did = int(D.t.ids[r])
            v = float(D.t.cols["f_val"][r, c])
            code = int(D.t.cols["f_code"][r, c])
            words = _factor_words(D, code, v)
            cands.append((1.4 + min(abs(v), 1.0), lambda d=did: self.node("decision", d, depth + 1), ("factor", v, words)))
        # the feelings it moved (decaying effects still on the books)
        eff = sim.effects
        if eff.n:
            m = np.flatnonzero(eff.event[: eff.n] == eid)
            if len(m):
                now = eff.contributions(sim.w.day)[m]
                for j, c in zip(m[:6], now[:6]):
                    var = eff.var_names[int(eff.var[j])]
                    who = int(eff.agent[j])
                    mag = float(eff.mag[j])
                    cands.append((1.0 + min(abs(mag) * 5, 1.0), lambda v=var, w=who: self.node("state", (v, w), depth + 1, n["day"]),
                                  ("contributed", mag, f"changed their {lc(self.W.var_label(var))} (now {c:+.3f})")))
        return cands

    def _fwd_decision(self, n, depth):
        did = int(n["ref"]["id"])
        cands = []
        for e in self.ix.by_decision(did):
            cands.append((3.0, lambda e=int(e): self.node("event", e, depth + 1), ("decided_by", None, "the choice behind it")))
        C = self.sim.causes.t
        for r in self.ix.cited_by("decision", did):
            e = int(C.cols["event"][r])
            lk, words = self._cause_words(int(C.cols["note"][r]), float(C.cols["weight"][r]))
            cands.append((2.5, lambda e=e: self.node("event", e, depth + 1), (lk, float(C.cols["weight"][r]), words)))
        return cands

    def _fwd_occasion(self, n, depth):
        sim = self.sim
        oid = int(n["ref"]["id"])
        cands = []
        C = sim.causes.t
        log = sim.log
        sal = _salience(sim)
        for r in self.ix.cited_by("occasion", oid):
            e = int(C.cols["event"][r])
            lk, words = self._cause_words(int(C.cols["note"][r]), float(C.cols["weight"][r]))
            cands.append((2.0 + sal[log["type"][e]], lambda e=e: self.node("event", e, depth + 1), (lk, None, words or "happened there")))
        E = sim.w.E
        met = np.flatnonzero((E["origin_ctx"] == CTX_ID["occasion"]) & (E["origin_place"] == oid))
        lo, hi = E.split(E.key_array[met]) if len(met) else (np.array([], np.int64), np.array([], np.int64))
        for a, b in zip(lo[:30], hi[:30]):
            cands.append((1.8, lambda a=int(a), b=int(b): self.node("tie", (a, b), depth + 1), ("met_at", None, "met here")))
        n["detail"]["met_here"] = int(len(met))
        D = sim.decisions
        ids = D.for_occasion(oid)
        if len(ids):
            n["detail"]["why_came"] = D.factor_summary(ids)[:6]
        for did in ids[:30]:
            cands.append((1.2, lambda d=int(did): self.node("decision", d, depth + 1), ("attended", None, "deciding whether to go")))
        return cands

    def _fwd_tie(self, n, depth):
        lo, hi = (int(x) for x in n["ref"]["id"].split("-"))
        key = (lo << 32) | hi
        log = self.sim.log
        sal = _salience(self.sim)
        cands = []
        rows = self.ix.between(key)
        for e in rows:
            e = int(e)
            cands.append((1.5 + sal[log["type"][e]] + 0.001 * e / max(log.n, 1), lambda e=e: self.node("event", e, depth + 1),
                          ("led_to", None, "between them")))
        C = self.sim.causes.t
        for r in self.ix.cited_by("tie", key):
            e = int(C.cols["event"][r])
            lk, words = self._cause_words(int(C.cols["note"][r]), float(C.cols["weight"][r]))
            cands.append((2.2 + sal[log["type"][e]], lambda e=e: self.node("event", e, depth + 1), (lk, float(C.cols["weight"][r]), words)))
        return cands

    STATE_WINDOW = 21     # days after a feeling was moved in which later items citing it count as its consequences

    def _fwd_state(self, n, depth):
        """Later events and decisions that cite this feeling (from the day it was recorded, for three weeks: a feeling
        has no single moment, so 'what it led to' is bounded by how long an event's effect typically lasts)."""
        var, i = n["ref"]["id"].split("@")
        ref = int(state_ref(self.sim, var, int(i)))
        C = self.sim.causes.t
        log = self.sim.log
        sal = _salience(self.sim)
        d0 = n["day"] if n.get("day") is not None else self.sim.w.day
        d1 = d0 + self.STATE_WINDOW
        n["detail"]["window"] = [d0, d1]
        cands = []
        for r in self.ix.cited_by("state", ref):
            e = int(C.cols["event"][r])
            if not d0 <= log["day"][e] <= d1:
                continue
            lk, words = self._cause_words(int(C.cols["note"][r]), float(C.cols["weight"][r]))
            cands.append((1.5 + sal[log["type"][e]], lambda e=e: self.node("event", e, depth + 1), (lk, float(C.cols["weight"][r]), words)))
        rows, cols = self.ix.factor_refs("state", ref)
        D = self.sim.decisions
        days = D.t.cols["day"][rows] if len(rows) else np.zeros(0, np.int32)
        ok = (days >= d0) & (days <= d1)
        for r, c in zip(rows[ok][:30], cols[ok][:30]):
            v = float(D.t.cols["f_val"][r, c])
            words = _factor_words(D, int(D.t.cols["f_code"][r, c]), v)
            cands.append((1.3 + min(abs(v), 1.0), lambda d=int(D.t.ids[r]): self.node("decision", d, depth + 1), ("factor", v, words)))
        return cands

    def _fwd_place(self, n, depth):
        ctx, pid = n["ref"]["id"].split(":")
        pid = int(pid)
        if ctx not in CTX_ID:
            return []
        ref = int(place_ref(CTX_ID[ctx], pid))
        C = self.sim.causes.t
        log = self.sim.log
        sal = _salience(self.sim)
        cands = []
        for r in self.ix.cited_by("place", ref)[-60:]:
            e = int(C.cols["event"][r])
            lk, words = self._cause_words(int(C.cols["note"][r]), float(C.cols["weight"][r]))
            cands.append((1.5 + sal[log["type"][e]], lambda e=e: self.node("event", e, depth + 1), (lk, None, words)))
        E = self.sim.w.E
        met = np.flatnonzero((E["origin_ctx"] == CTX_ID[ctx]) & (E["origin_place"] == pid))[-30:]
        if len(met):
            lo, hi = E.split(E.key_array[met])
            for a, b in zip(lo, hi):
                cands.append((1.2, lambda a=int(a), b=int(b): self.node("tie", (a, b), depth + 1), ("met_at", None, "met here")))
        return cands

    def _fwd_person(self, n, depth):
        return []


def _factor_refs(sim, W: _Words, factors: list[dict]) -> list[dict]:
    """Factors with plain words and their refs in the client's form (var:<field>@<person>, place:<kind>:<id>)."""
    out = []
    for f in factors:
        f = {**f, "words": f.get("words") or f["label"]}
        ref = f.get("ref")
        if ref:
            if ref["kind"] == "person":
                f["ref_label"] = W.name(ref["id"])
            elif ref["kind"] == "event" and 0 <= ref["id"] < sim.log.n:
                f["ref_label"] = W.event_line(ref["id"])
            elif ref["kind"] == "state":
                var, i = split_state(sim, ref["id"])
                f["ref"] = {"kind": "var", "id": f"{var}@{i}"}
                f["ref_label"] = f"{W.name(i)}'s {lc(W.var_label(var))}"
            elif ref["kind"] == "place":
                c, p = split_place(ref["id"])
                f["ref"] = {"kind": "place", "id": f"{c}:{p}"}
                f["ref_label"] = W.place(c, p)
            elif ref["kind"] == "tie":
                lo, hi = int(ref["id"]) >> 32, int(ref["id"]) & 0xFFFFFFFF
                f["ref"] = {"kind": "tie", "id": f"{lo}-{hi}"}
                f["ref_label"] = f"{W.name(lo)} and {W.name(hi)}"
        out.append(f)
    return out


def _is_mirror(log, first: int, second: int) -> bool:
    """The other person's copy of a two-person event (same type and day, the two people swapped)."""
    return bool(log["type"][first] == log["type"][second] and log["day"][first] == log["day"][second]
                and log["a"][first] == log["b"][second] and log["b"][first] == log["a"][second])


def _roles():
    from ..engine.provenance import ROLES
    return ROLES


def _salience(sim) -> np.ndarray:
    s = getattr(sim.reg, "_trace_salience", None)
    if s is None or len(s) != len(sim.reg.event_names):
        s = np.array([sim.reg.events[k].salience for k in sim.reg.event_names], np.float32)
        sim.reg._trace_salience = s
    return s


def _factor_words(D, code: int, v: float) -> str:
    if code < 0 or code >= len(D.factor_names):
        return ""
    kind, fid = D.factor_names[code].split(".", 1)
    fs = (D.vocab.get(kind, {}).get("factors") or {}).get(fid, {})
    words = fs.get("more" if v > 0 else "less") or fs.get("label", fid)
    return f"couldn't: {words}" if abs(v) >= CONSTRAINT - 1 else words


# ----------------------------------------------------------------------------- public: one item
def person_seeds(sim, i: int, since: int | None = None, k: int = 10) -> list[int]:
    """A person's most notable events (salience first, then the most recent) — the starting points of their trace."""
    log = sim.log
    rows = np.flatnonzero(log["a"] == i)
    if since is not None:
        rows = rows[log["day"][rows] >= since]
    if not len(rows):
        return []
    sal = _salience(sim)[log["type"][rows]]
    rows = rows[sal >= 0.45] if (sal >= 0.45).sum() >= 3 else rows
    sal = _salience(sim)[log["type"][rows]]
    order = np.lexsort((-rows, -sal))
    return sorted(int(r) for r in rows[order[:k]])


def trace(sim, ref, dir: str = "both", depth: int = 3, max_nodes: int = MAX_NODES, fanout: int = FANOUT,
          since: int | None = None) -> dict:
    """The causal graph around `ref` (see the module docstring). `dir`: back (what led to it), fwd (what it led to)
    or both; `depth`: how many steps each way. Returns {root, nodes, links, lanes, range, cut, notes}."""
    kind, ident = parse_ref(ref)
    depth = int(np.clip(depth, 1, 8))
    G = _Graph(sim, int(np.clip(max_nodes, 5, 400)), int(np.clip(fanout, 1, 50)))
    notes = []
    seeds = []
    if kind == "person":
        root = G.node("person", int(ident), 0, None)
        if root is None:
            raise KeyError(f"no person {ident}")
        G.nodes[root]["root"] = True
        for e in person_seeds(sim, int(ident), since):
            k = G.node("event", e, 0)
            if k:
                seeds.append(k)
        if seeds:
            G.nodes[root]["day"] = min(G.nodes[k]["day"] for k in seeds)
        notes.append("A person's trace starts from their most notable events; click one to follow it further.")
        depth = max(1, depth - 1)
    else:
        root = G.node(kind, ident, 0, None)
        if root is None:
            raise KeyError(f"{ref} is not in the record (it may be older than the detailed history that is kept)")
        G.nodes[root]["root"] = True
        seeds = [root]
    for go, step in (("back", G.back), ("fwd", G.fwd)):
        if dir not in (go, "both"):
            continue
        frontier = list(seeds)
        for _ in range(depth):
            nxt = []
            for key in frontier:
                nxt += step(key, 0)
            frontier = [k for k in dict.fromkeys(nxt) if k in G.nodes]
            if not frontier:
                break
    _place_timeless(G)
    nodes = list(G.nodes.values())
    _depths(G, root)
    lanes = _lanes(G, root)
    days = [n["day"] for n in nodes if n.get("day") is not None]
    for L in G.links.values():
        L["words"] = "; ".join(w for w in L["words"] if w)
    cut_back = sum(n["more_back"] for n in nodes)
    cut_fwd = sum(n["more_fwd"] for n in nodes)
    if cut_back or cut_fwd or G.cut:
        notes.append(f"Not shown: {cut_back} more causes and {cut_fwd} more consequences "
                     f"({'the node limit' if G.cut else 'the per-item limit'}); click an item to follow those.")
    return {"root": root, "nodes": nodes, "links": list(G.links.values()), "lanes": lanes,
            "range": [min(days), max(days)] if days else [sim.w.day, sim.w.day], "today": sim.w.day,
            "start_date": str(sim.cal.date(0)),
            "cut": {"back": int(cut_back), "fwd": int(cut_fwd), "cap_hits": int(G.cut), "max_nodes": G.max_nodes,
                    "fanout": G.fanout},
            "notes": notes}


def _place_timeless(G: _Graph):
    """People, places and other timeless nodes sit at the time of the earliest item they link to."""
    by = {}
    for (s, t) in G.links:
        for a, b in ((s, t), (t, s)):
            d = G.nodes[b].get("day") if b in G.nodes else None
            if d is not None:
                by[a] = min(by.get(a, d), d)
    for k, n in G.nodes.items():
        if n.get("day") is None:
            n["day"] = by.get(k, G.sim.w.day)
            n["timeless"] = True


def _depths(G: _Graph, root: str):
    """Signed distance from the root along links (negative = a cause, positive = a consequence)."""
    out_adj, in_adj = {}, {}
    for (s, t) in G.links:
        out_adj.setdefault(s, []).append(t)
        in_adj.setdefault(t, []).append(s)
    seen = {root: 0}
    for adj, sign in ((in_adj, -1), (out_adj, 1)):
        frontier = [root]
        d = 0
        while frontier:
            d += 1
            nxt = []
            for k in frontier:
                for m in adj.get(k, ()):
                    if m not in seen:
                        seen[m] = sign * d
                        nxt.append(m)
            frontier = nxt
    for k, n in G.nodes.items():
        n["depth"] = seen.get(k, n.get("depth", 0))


def _lanes(G: _Graph, root: str) -> list[dict]:
    """One lane per person: the root's people first, then by how many items they appear in."""
    count: dict[int, int] = {}
    for n in G.nodes.values():
        for p in n.get("people") or []:
            count[p] = count.get(p, 0) + 1
    first = G.nodes[root].get("people") or []
    order = list(dict.fromkeys([p for p in first if p in count] + sorted(count, key=lambda p: (-count[p], p))))
    return [{"id": int(p), "name": G.W.name(p), "n": int(count[p]), "root": p in first} for p in order]


# ----------------------------------------------------------------------------- public: decisions
def decision_detail(sim, did: int) -> dict:
    """One decision with its factors in words, the people and items they point at, and what it produced."""
    D = sim.decisions
    d = D.get(int(did))
    if not d:
        return {}
    W = _Words(sim)
    spec = D.vocab[d["kind"]]
    d["agent_name"] = W.name(d["agent"])
    if d.get("other") is not None:
        d["other_name"] = W.name(d["other"])
    d["units_words"] = UNITS_WORDS.get(d["units"], d["units"])
    d["positive"] = positive_outcome(spec, d["outcome"])
    d["outcomes"] = spec.get("outcomes") or []
    d["factors"] = _factor_refs(sim, W, d["factors"])
    produced = [int(e) for e in index(sim).by_decision(int(did))]
    if d.get("event") is not None and d["event"] not in produced:
        produced.insert(0, int(d["event"]))
    d["events"] = [{"id": e, "label": W.event_line(e), "day": int(sim.log["day"][e])} for e in produced[:10] if 0 <= e < sim.log.n]
    d["date"] = str(sim.cal.date(int(d["day"])))
    return d


def person_decisions(sim, i: int, since: int | None = None, limit: int = 200) -> list[dict]:
    """A person's recorded decisions (newest first), each with its top factor in words."""
    D = sim.decisions
    ids = D.for_agent(int(i), since if since is not None else -10**9)[::-1][:limit]
    out = []
    W = _Words(sim)
    for did in ids:
        d = D.get(int(did))
        if not d:
            continue
        top = d["factors"][0] if d["factors"] else None
        out.append({"id": d["id"], "day": d["day"], "kind": d["kind"], "label": d["label"],
                    "outcome": str(d["outcome"]).replace("_", " "), "prob": d["prob"],
                    "other": d.get("other"), "other_name": W.name(d["other"]) if d.get("other") is not None else None,
                    "event": d.get("event"),
                    "top": {"label": top["label"], "words": top.get("words") or top["label"], "value": top["value"],
                            "constraint": top["constraint"]} if top else None})
    return out


# ----------------------------------------------------------------------------- public: the population view
def _top_reason(D, rows: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Per decision row: (factor code, value) of the top reason for the outcome that happened — a constraint if any;
    otherwise the largest term pushing toward that outcome (for yes/no log-odds kinds, toward 'no' means negative)."""
    T = D.t
    fc = T.cols["f_code"][rows]
    fv = T.cols["f_val"][rows].astype(np.float32)
    kinds = T.cols["kind"][rows]
    outc = T.cols["outcome"][rows]
    sign = np.ones(len(rows), np.float32)
    for k in np.unique(kinds):
        spec = D.vocab[D.kinds[k]]
        units = spec.get("units", "logit")
        outs = spec.get("outcomes") or []
        pos = spec.get("positive") or (outs[0] if outs else None)
        if units in ("logit", "log_rate", "probability") and pos in outs:
            m = kinds == k
            sign[m] = np.where(outc[m] == outs.index(pos), 1.0, -1.0)
    valid = fc >= 0
    cons = valid & (np.abs(fv) >= CONSTRAINT - 1)
    score = np.where(valid, fv * sign[:, None], -np.inf)
    score = np.where(cons, np.inf, score)
    j = np.argmax(score, axis=1)
    ar = np.arange(len(rows))
    best = score[ar, j]
    code = np.where(np.isfinite(best) & (best > 0) | cons[ar, j], fc[ar, j], -1)
    return code.astype(np.int64), fv[ar, j]


def chains(sim, since: int | None = None, until: int | None = None, people: np.ndarray | None = None,
           root: str | None = None, max_links: int = 60, examples: int = 5, repeats: bool = False) -> dict:
    """Population chain reactions in a window (and cohort): flows between event types through recorded causes, flows
    from decisions to the events they produced, and the top reasons behind each decision outcome. `repeats`: also
    count links between events of the same kind (one date leading to the next), hidden by default."""
    log, reg = sim.log, sim.reg
    names = reg.event_names
    day = sim.w.day
    since = day - 60 if since is None else int(since)
    until = day if until is None else int(until)
    s0 = int(np.searchsorted(log["day"], since, side="left"))
    s1 = int(np.searchsorted(log["day"], until, side="right"))
    rows = np.arange(s0, s1)
    if people is not None:
        pm = np.zeros(sim.w.P.n, bool)
        pm[np.asarray(people, np.int64)] = True
        rows = rows[pm[log["a"][rows]]]
    W = _Words(sim)
    types = log["type"]
    root_code = reg.event_ids.get(root) if root else None
    mirror_note = ROLE_BASE + list(_roles()).index("mirror")
    # ---- event → event (parent causes, then typed causes of kind event)
    par = log["cause"][rows]
    m = par >= 0
    src_e, dst_e = par[m], rows[m]
    kinds = np.zeros(len(src_e), np.int8)                       # 0 = parent link
    C = sim.causes.t
    if C.n:
        ce = C["event"]
        sel = (ce >= s0) & (ce < s1) & (C["kind"] == CAUSE_ID["event"]) & (C["note"] != mirror_note) & (C["ref"] >= 0) & (C["ref"] < log.n)
        if people is not None:
            sel &= pm[log["a"][np.clip(ce, 0, log.n - 1)]]
        src_e = np.r_[src_e, C["ref"][sel]]
        dst_e = np.r_[dst_e, ce[sel]]
        kinds = np.r_[kinds, np.ones(int(sel.sum()), np.int8)]
    # a two-person event's mirror copy is the same moment: count each moment once
    same = types[src_e] == types[dst_e]
    same &= log["day"][src_e] == log["day"][dst_e]
    keep = ~(same & (log["a"][src_e] == log["b"][dst_e]))
    src_e, dst_e, kinds = src_e[keep], dst_e[keep], kinds[keep]
    st, dt = types[src_e].astype(np.int64), types[dst_e].astype(np.int64)
    n_repeat = int((st == dt).sum())
    if not repeats:
        diff = st != dt
        src_e, dst_e, st, dt, kinds = src_e[diff], dst_e[diff], st[diff], dt[diff], kinds[diff]
    if root_code is not None:
        touch = (st == root_code) | (dt == root_code)
        src_e, dst_e, st, dt, kinds = src_e[touch], dst_e[touch], st[touch], dt[touch], kinds[touch]
    pair = st * 4096 + dt
    links = []
    if len(pair):
        u, inv, cnt = np.unique(pair, return_inverse=True, return_counts=True)
        top = np.argsort(-cnt)[:max_links]
        for t in top:
            a, b = divmod(int(u[t]), 4096)
            which = np.flatnonzero(inv == t)
            ex = which[np.argsort(-dst_e[which])][:examples]
            links.append({"source": f"event:{names[a]}", "target": f"event:{names[b]}", "value": int(cnt[t]),
                          "kind": "caused" if (kinds[which] == 0).mean() >= 0.5 else "contributed",
                          "from_label": reg.events[names[a]].label, "to_label": reg.events[names[b]].label,
                          "examples": [{"event": int(dst_e[x]), "from": int(src_e[x]), "day": int(log["day"][dst_e[x]]),
                                        "label": W.event_line(int(dst_e[x])), "from_label": W.event_line(int(src_e[x]))}
                                       for x in ex]})
    # ---- decision → event
    D = sim.decisions
    dec = log["decision"][rows]
    m = dec >= 0
    drow = D.t.pos(dec[m])
    ok = drow >= 0
    ev_rows, drow = rows[m][ok], drow[ok]
    dlinks = []
    if len(drow):
        dk = D.t.cols["kind"][drow].astype(np.int64)
        do = D.t.cols["outcome"][drow].astype(np.int64)
        et = types[ev_rows].astype(np.int64)
        if root_code is not None:
            sel = et == root_code
            dk, do, et, ev_rows, drow = dk[sel], do[sel], et[sel], ev_rows[sel], drow[sel]
        key = (dk * 64 + do) * 4096 + et
        if len(key):
            u, inv, cnt = np.unique(key, return_inverse=True, return_counts=True)
            for t in np.argsort(-cnt)[:max_links]:
                kk, e = divmod(int(u[t]), 4096)
                k_, o_ = divmod(kk, 64)
                kind = D.kinds[k_]
                outs = D.vocab[kind].get("outcomes") or []
                oname = outs[o_] if 0 <= o_ < len(outs) else str(o_)
                which = np.flatnonzero(inv == t)[-examples:]
                dlinks.append({"source": f"decision:{kind}:{oname}", "target": f"event:{names[e]}", "value": int(cnt[t]),
                               "kind": "decided_by", "from_label": f"{D.vocab[kind].get('label', kind)} → {oname.replace('_', ' ')}",
                               "to_label": reg.events[names[e]].label,
                               "examples": [{"event": int(ev_rows[x]), "decision": int(D.t.ids[drow[x]]), "day": int(log["day"][ev_rows[x]]),
                                             "label": W.event_line(int(ev_rows[x]))} for x in which]})
    # ---- reasons: decision factors → outcomes (all recorded decisions in the window and cohort)
    T = D.t
    dm = (T["day"] >= since) & (T["day"] <= until)
    if people is not None:
        dm &= pm[np.clip(T["agent"], 0, sim.w.P.n - 1)]
    drows = np.flatnonzero(dm)
    if root_code is not None and len(drows):
        ev = T["event"][drows]
        okr = (ev >= 0) & (ev < log.n)
        okr[okr] &= types[ev[okr]] == root_code
        drows = drows[okr]
    reasons = []
    if len(drows):
        code, val = _top_reason(D, drows)
        kk = T.cols["kind"][drows].astype(np.int64) * 64 + T.cols["outcome"][drows].astype(np.int64)
        for g in np.unique(kk):
            gm = kk == g
            k_, o_ = divmod(int(g), 64)
            kind = D.kinds[k_]
            spec = D.vocab[kind]
            outs = spec.get("outcomes") or []
            oname = outs[o_] if 0 <= o_ < len(outs) else str(o_)
            n = int(gm.sum())
            cg = code[gm]
            vg = val[gm]
            top = []
            for c in np.unique(cg):
                cm = cg == c
                if c < 0:
                    words = ("chance (nothing about them made it more likely)" if spec.get("units") == "probability"
                             else "no single reason stood out")
                    top.append({"factor": None, "label": words, "words": words, "n": int(cm.sum()),
                                "share": round(float(cm.mean()), 3)})
                    continue
                kname, fid = D.factor_names[c].split(".", 1)
                fs = (spec.get("factors") or {}).get(fid, {})
                v = float(np.median(vg[cm]))
                words = (fs.get("more" if v > 0 else "less") or fs.get("label", fid))
                cons = abs(v) >= CONSTRAINT - 1
                top.append({"factor": fid, "label": fs.get("label", fid), "words": ("couldn't: " if cons else "") + words,
                            "n": int(cm.sum()), "share": round(float(cm.mean()), 3), "constraint": cons,
                            "median": None if cons else round(v, 3)})
            top.sort(key=lambda r: -r["n"])
            ex = T["id"][drows[gm]][-examples:]
            lead = next((t for t in top if t["factor"]), None)
            what = f"Of {n:,} times the choice “{spec.get('label', kind)}” came out “{oname.replace('_', ' ')}”, "
            sentence = (what + f"{lead['share']:.0%} had “{lead['words']}” as the top reason." if lead
                        else what + "the model gave no reason beyond chance.")
            reasons.append({"decision": kind, "label": spec.get("label", kind), "outcome": oname, "n": n,
                            "top": top[:6], "sentence": sentence, "examples": [int(x) for x in ex]})
        reasons.sort(key=lambda r: -r["n"])
    # ---- nodes for a left→right flow: causes on the left, results on the right (a type can appear on both sides)
    nodes: dict[str, dict] = {}
    flow = []
    rk = f"event:{root}" if root else None
    for L in links + dlinks:
        s_root, t_root = L["source"] == rk, L["target"] == rk
        s = L["source"] + ("|root" if s_root else "|from")
        t = L["target"] + ("|root" if t_root and not s_root else "|to")
        for k, label in ((s, L["from_label"]), (t, L["to_label"])):
            nd = nodes.setdefault(k, {"id": k, "label": label, "side": k.rsplit("|", 1)[1], "kind": k.split(":", 1)[0],
                                      "in": 0, "out": 0})
        nodes[s]["out"] += L["value"]
        nodes[t]["in"] += L["value"]
        flow.append({**L, "source": s, "target": t})
    for nd in nodes.values():
        nd["n"] = max(nd.pop("in"), nd.pop("out"))
    n_events = int(len(rows))
    return {"window": [since, until], "events": n_events, "cohort": None if people is None else int(len(people)),
            "today": day, "start_date": str(sim.cal.date(0)),
            "root": root, "root_label": reg.events[root].label if root in reg.events else None,
            "nodes": list(nodes.values()), "links": flow, "reasons": reasons[:40],
            "repeats_hidden": 0 if repeats else n_repeat,
            "notes": ["Flows count recorded links between events (a parent cause or a typed cause) and from decisions to "
                      "the events they produced; a two-person moment is counted once. Reasons are each decision's "
                      "largest recorded term in the direction of what happened."]
            + ([f"{n_repeat:,} links between events of the same kind (one date leading to the next) are not shown."]
               if n_repeat and not repeats else [])}


# ----------------------------------------------------------------------------- coverage
BOOKKEEPING = ("intention_formed",)     # event types added so other records have a beginning (no effects, no memory)


def coverage(sim) -> dict:
    """How traceable the record is: per event type, the share of events with a parent event, a recorded decision,
    typed causes, any of these, and at least two distinct reasons (scripts/provenance_coverage.py)."""
    log, reg = sim.log, sim.reg
    n = log.n
    types = log["type"]
    has_parent = log["cause"] >= 0
    has_dec = log["decision"] >= 0
    T = sim.causes.t
    typed_n = np.bincount(T["event"][(T["event"] >= 0) & (T["event"] < n)], minlength=n) if T.n else np.zeros(n, np.int64)
    # decisions linked from the decision side too (a decision may name its event without the event naming it)
    D = sim.decisions.t
    if D.n:
        dev = D["event"]
        dev = dev[(dev >= 0) & (dev < n)]
        has_dec = has_dec.copy()
        has_dec[dev] = True
    has_typed = typed_n > 0
    n_reasons = has_parent.astype(int) + has_dec.astype(int) + typed_n
    anyr = has_parent | has_dec | has_typed
    rows = []
    for code in np.unique(types):
        m = types == code
        k = int(m.sum())
        spec = reg.events[reg.event_names[code]]
        rows.append({"type": spec.id, "salience": spec.salience, "n": k,
                     "parent": float(has_parent[m].mean()), "decision": float(has_dec[m].mean()),
                     "typed": float(has_typed[m].mean()), "any": float(anyr[m].mean()),
                     "several": float((n_reasons[m] >= 2).mean())})
    sal = np.array([e.salience for e in reg.events.values()], np.float32)[types]
    hi = sal >= 0.5
    extra = np.isin(types, [reg.event_ids[t] for t in BOOKKEEPING if t in reg.event_ids])
    lo_ex = ~hi & ~extra
    head = {"events": int(n),
            "other_any_excl": float(anyr[lo_ex].mean()) if lo_ex.any() else None,
            "all_any_excl": float(anyr[~extra].mean()) if (~extra).any() else None,
            "salient_any": float(anyr[hi].mean()) if hi.any() else None,
            "other_any": float(anyr[~hi].mean()) if (~hi).any() else None,
            "all_any": float(anyr.mean()) if n else None,
            "salient_several": float((n_reasons[hi] >= 2).mean()) if hi.any() else None,
            "decisions": int(D.n), "typed_causes": int(T.n)}
    return {"headline": head, "types": sorted(rows, key=lambda r: (-r["salience"], -r["n"]))}
