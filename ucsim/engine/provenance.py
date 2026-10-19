"""Provenance helpers: the shared vocabulary systems use to say *why* something happened.

Systems record choices in `sim.decisions` and extra causes in `sim.causes` (engine/ledger.py). This module adds what
those ledgers need to be read back in words:

* **Notes.** A typed cause carries a `note` saying what kind of reason it is. One int16, in four ranges:
    [0, 10000)       a decision factor (DecisionLog.factor_id)
    [10000, 20000)   a person variable: the event moved this feeling/variable (VAR_BASE + variable code)
    [20000, 30000)   a mechanism term: the cause is that term of a composed state (MECH_BASE + mechanism code)
    [30000, …)       a role: where two people met, who introduced them, the hurt between them… (ROLES)
* **Roles** name the cause's part in the story with a plain phrase and the kind of link the trace draws (`met_at`,
  `introduced`, `contributed`, `led_to`, `caused`, `decided_by`). Append only: codes are stored on cause rows.
* **Packed refs.** A cause or factor ref is one int64:
    place  (context code << 32) | place id      the kind of place (state.CTX) and its id (unit, ward, venue, class…)
    state  (variable code << 32) | person       a feeling or other person variable of one person
    tie    EdgeStore key (lo << 32) | hi
* **Decisions.** `total` sums a decision's terms in the order the model sums them (bit-identical to the original
  expression), so systems keep their formulas and the ledger records the very terms that were added.
* **Snapshots.** `state_causes` links an event to the terms and recent events behind a feeling *at that moment*
  (decompositions are composed daily and not stored, so a later trace could otherwise only see today's).
* **Lookups** for the cause of an event that happened earlier (a person's latest event of some kinds, the latest
  event between two people, the hard memories behind a low stretch), vectorized over people.
* **Time together.** Each tie keeps the context where most of the pair's time together accrued and a runner-up
  (`note_time`), so a friendship can say "mostly in class" rather than only "met in class".

Nothing here draws random numbers or feeds back into behavior: recording never changes the world.
"""
from __future__ import annotations

import numpy as np

from .state import CTX

VAR_BASE = 10000
MECH_BASE = 20000
ROLE_BASE = 30000
# name: (link kind drawn by the trace, plain words). Append only: codes are stored on cause rows.
ROLES: dict[str, tuple[str, str]] = {
    "met_at": ("met_at", "where they first met"),
    "introduced": ("introduced", "brought them together"),
    "time_together": ("contributed", "where most of their time together was"),
    "also_together": ("contributed", "where they also spent time"),
    "time": ("contributed", "the hours they spent together"),
    "liking": ("contributed", "how much they liked each other"),
    "confiding": ("contributed", "confiding in each other"),
    "shared": ("contributed", "experiences they shared"),
    "hurt": ("contributed", "unresolved hurt between them"),
    "drifted": ("contributed", "they stopped seeing each other"),
    "around_then": ("contributed", "a change in their life shortly before"),
    "answer": ("decided_by", "the other person's answer"),
    "last_date": ("led_to", "their last date before this"),
    "ready": ("contributed", "enough dates, time and mutual interest"),
    "went_nowhere": ("contributed", "weeks of talking that never became exclusive"),
    "low_interest": ("contributed", "not enough interest on both sides"),
    "betrayal": ("contributed", "a betrayal"),
    "left": ("caused", "a partner left the area"),
    "ended_by": ("caused", "the person who ended it (the one less attracted to the other)"),
    "engaged_before": ("contributed", "already engaged when the story began"),
    "trigger": ("contributed", "a hard time shortly before"),
    "strain": ("contributed", "what was weighing on them"),
    "intention": ("led_to", "what they had set out to do"),
    "target_gone": ("caused", "the person they had in mind was no longer available"),
    "priorities": ("contributed", "something else had become more pressing"),
    "new_home": ("contributed", "the place they moved to"),
    "why_move": ("decided_by", "why they moved"),
    "employer": ("contributed", "where they worked"),
    "challenge": ("contributed", "an earlier challenge to their faith"),
    "partner": ("contributed", "their partner"),
    "moved_with": ("caused", "moved with their spouse"),
    "after": ("led_to", "came after this"),
    "friend_left": ("caused", "a close friend left"),
    "mirror": ("caused", "the same moment, for the other person"),
    "pregnancy": ("led_to", "the pregnancy"),
    "departure": ("led_to", "when they left"),
    "the_tie": ("contributed", "their relationship"),
    "certainty": ("contributed", "how sure they felt about their faith"),
    "coping": ("contributed", "how they were coping"),
    "money": ("contributed", "money pressure"),
    "home_ward": ("contributed", "the ward that came with their new home"),
    "scene": ("contributed", "where it happened"),
    "chance": ("contributed", "chance (nothing in their life made it more likely)"),
    "stressor": ("contributed", "what the strain was mostly about"),
    "resolved": ("contributed", "the strain eased"),
    "timed_out": ("contributed", "a month passed without the strain easing"),
    "faded": ("contributed", "the reason for the plan had faded"),
    "came_to_study": ("caused", "came to study"),
    "friends_differ": ("contributed", "friends who believed differently"),
    "dissonance": ("contributed", "guilt over living against their standards"),
    "invited_by": ("introduced", "the believing friend or partner who invited them"),
    "rent": ("contributed", "rent"),
    "tuition": ("contributed", "tuition"),
    "income": ("contributed", "too little income"),
    "found_out": ("caused", "found out about the cheating"),
    "picked_up_from": ("contributed", "the closest friend who already did it"),
    "enough_credits": ("caused", "their credits reached what the program requires"),
    "dealbreaker": ("caused", "finding out something that was a dealbreaker for them"),
    "brought_to_light": ("contributed", "what brought it to light"),
    "crossed": ("led_to", "a step further than they had planned"),
    "unanswered": ("caused", "a message that went unanswered"),
    "organization": ("contributed", "the organization involved (its capacity, budget and choices)"),
}
ROLE_CODE = {k: ROLE_BASE + i for i, k in enumerate(ROLES)}
ROLE_NAME = {v: k for k, v in ROLE_CODE.items()}
_LOW = np.int64(0xFFFFFFFF)


def role(name: str) -> int:
    return ROLE_CODE[name]


def role_info(note: int) -> tuple[str, str, str] | None:
    """(role name, link kind, words) for a cause note, or None when the note is not a role."""
    name = ROLE_NAME.get(int(note))
    if name is None:
        return None
    link_kind, words = ROLES[name]
    return name, link_kind, words


def mech_note(sim, mid: str) -> int:
    """Note code for a mechanism term (−1 when the term has no registered mechanism)."""
    k = sim.log.mech_ids.get(mid)
    return -1 if k is None else MECH_BASE + int(k)


def var_note(sim, var: str) -> int:
    return VAR_BASE + var_codes(sim.reg)[var]


def note_info(sim, note: int) -> dict | None:
    """What a cause note means: {"type": role|mechanism|variable|factor, ...} or None."""
    note = int(note)
    if note < 0:
        return None
    if note >= ROLE_BASE:
        r = role_info(note)
        return None if r is None else {"type": "role", "role": r[0], "link": r[1], "words": r[2]}
    if note >= MECH_BASE:
        names = sim.log.mech_names
        k = note - MECH_BASE
        if k >= len(names):
            return None
        mid = names[k]
        m = sim.reg.mechanisms.get(mid)
        return {"type": "mechanism", "mechanism": mid, "words": m.label if m else mid,
                "evidence": m.evidence if m else None}
    if note >= VAR_BASE:
        var_codes(sim.reg)
        k = note - VAR_BASE
        names = sim.reg._prov_var_names
        if k >= len(names):
            return None
        v = names[k]
        spec = sim.reg.variables.get(v)
        return {"type": "variable", "var": v, "words": f"changed their {spec.label.lower() if spec else v}"}
    fn = sim.decisions.factor_names
    if note < len(fn):
        kind, fid = fn[note].split(".", 1)
        fs = (sim.decisions.vocab.get(kind, {}).get("factors") or {}).get(fid, {})
        return {"type": "factor", "kind": kind, "factor": fid, "words": fs.get("label", fid)}
    return None


# ----------------------------------------------------------------------------- packed refs
def place_ref(ctx, pid) -> np.ndarray:
    """(context << 32) | place id. A missing place id (−1: hanging out, online, an app) packs as 0xFFFFFFFF."""
    c = np.asarray(ctx, np.int64)
    p = np.asarray(pid, np.int64) & _LOW
    return (c << 32) | p


def split_place(ref: int) -> tuple[str, int]:
    """(context name, place id or −1)."""
    ref = int(ref)
    c, p = ref >> 32, ref & 0xFFFFFFFF
    return (CTX[c] if 0 <= c < len(CTX) else "?"), (-1 if p == 0xFFFFFFFF else p)


def var_codes(reg) -> dict[str, int]:
    """Stable codes for person variables (their order in the registry), cached on the registry."""
    vc = getattr(reg, "_prov_var_codes", None)
    if vc is None:
        vc = {v.id: k for k, v in enumerate(reg.person_vars())}
        reg._prov_var_codes = vc
        reg._prov_var_names = list(vc)
    return vc


def state_ref(sim, var: str, person) -> np.ndarray:
    code = var_codes(sim.reg)[var]
    return (np.int64(code) << 32) | (np.asarray(person, np.int64) & _LOW)


def split_state(sim, ref: int) -> tuple[str, int]:
    var_codes(sim.reg)
    ref = int(ref)
    return sim.reg._prov_var_names[ref >> 32], ref & 0xFFFFFFFF


def tie_key(a, b) -> np.ndarray:
    a = np.asarray(a, np.int64)
    b = np.asarray(b, np.int64)
    return (np.minimum(a, b) << 32) | np.maximum(a, b)


# ----------------------------------------------------------------------------- linking
def link(sim, events, kind: str, refs, weight=1.0, role_name: str | None = None, note: int | None = None):
    """Typed causes for events (refs aligned with events; refs < 0 are skipped)."""
    events = np.atleast_1d(np.asarray(events, np.int64))
    if not len(events):
        return
    code = note if note is not None else (-1 if role_name is None else ROLE_CODE[role_name])
    sim.causes.add(events, kind, refs, weight, code)


def mirror(sim, events, firsts):
    """The other person's copy of a two-person event points at the first copy."""
    link(sim, events, "event", firsts, 1.0, "mirror")


# ----------------------------------------------------------------------------- decisions
def total(base, terms: dict):
    """base + Σ terms, added in the dict's order — the same order (and so the same floating-point result) as the
    model's own `base + t1 + t2 + …` expression."""
    acc = base
    for v in terms.values():
        acc = acc + v
    return acc


def pick(terms: dict, sel) -> dict:
    """The terms of a subset of the people a formula was computed for (scalars stay scalars)."""
    return {k: (v[sel] if np.ndim(v) else v) for k, v in terms.items()}


def softmax_prob(U: np.ndarray, choice: np.ndarray) -> np.ndarray:
    """Probability of the chosen option under a Gumbel-max choice (= the logit / softmax probability)."""
    U = np.asarray(U, np.float64)
    e = np.exp(U - U.max(axis=1, keepdims=True))
    return e[np.arange(len(U)), choice] / e.sum(axis=1)


def chance(sim, kind: str, agents, rate, outcome="happened", factors: dict | None = None, **kw) -> np.ndarray:
    """Record an outcome the model leaves to chance at a known rate (units: probability). Saying so is the honest
    reason: nothing about the person made it more likely unless a factor says otherwise."""
    agents = np.atleast_1d(np.asarray(agents, np.int64))
    if not len(agents):
        return np.empty(0, np.int64)
    rate = np.broadcast_to(np.asarray(rate, np.float32), (len(agents),))
    return sim.decisions.record(kind, sim.w.day, agents, outcome, factors or {}, base=rate, prob=rate, **kw)


# ----------------------------------------------------------------------------- state snapshots
def _sources(sim, var: str, names: list[str]) -> list[str]:
    """The person variable each term of a composed state reads (its mechanism's first source), else the state."""
    out = []
    for t in names:
        m = sim.reg.mechanisms.get(f"{var}.{t}")
        src = next((s for s in (m.sources if m else []) if s in sim.w.P.specs), None)
        out.append(src or var)
    return out


def state_causes(sim, events, people, var: str, sign: int = -1, k: int = 2, k_events: int = 2, min_abs: float = 0.01):
    """Link events to what was moving a feeling at that moment: its `k` largest terms in direction `sign` (−1: the
    terms pulling it down, +1: pushing it up) as `state` causes on the term's source variable (note = the mechanism),
    and its `k_events` largest decaying event effects in that direction as `event` causes (note = the variable)."""
    events = np.atleast_1d(np.asarray(events, np.int64))
    people = np.atleast_1d(np.asarray(people, np.int64))
    if not len(events):
        return
    emo = sim.systems.get("emotion")
    C = emo.contrib.get(var) if emo is not None else None
    if C:
        names = [t for t in C if len(C[t]) > int(people.max())]
        if names:
            M = np.stack([C[t][people] for t in names]).astype(np.float32)        # (terms, people)
            S = sign * M
            srcs = _sources(sim, var, names)
            notes = np.array([mech_note(sim, f"{var}.{t}") for t in names], np.int64)
            codes = var_codes(sim.reg)
            src_code = np.array([codes[s] for s in srcs], np.int64)
            order = np.argsort(-S, axis=0)[: min(k, len(names))]
            ar = np.arange(len(people))
            for r in range(len(order)):
                t = order[r]
                ok = S[t, ar] >= min_abs
                if not ok.any():
                    continue
                refs = (src_code[t] << 32) | (people & _LOW)
                for nt in np.unique(notes[t[ok]]):
                    m = ok & (notes[t] == nt)
                    link(sim, events[m], "state", refs[m], M[t[m], ar[m]], note=int(nt) if nt >= 0 else var_note(sim, var))
    if k_events <= 0:
        return
    eff = sim.effects
    if eff.n == 0 or var not in eff.vid:
        return
    n = eff.n
    pmax = int(max(people.max(), eff.agent[:n].max())) + 1
    pos = np.full(pmax, -1, np.int64)
    pos[people] = np.arange(len(people))
    sel = np.flatnonzero((eff.var[:n] == eff.vid[var]) & (pos[eff.agent[:n]] >= 0) & (eff.event[:n] >= 0))
    if not len(sel):
        return
    c = eff.contributions(sim.w.day)[sel] * sign
    keep = c >= min_abs
    sel, c = sel[keep], c[keep]
    if not len(sel):
        return
    ag = eff.agent[sel].astype(np.int64)
    order = np.lexsort((-c, ag))
    sel, c, ag = sel[order], c[order], ag[order]
    start = np.r_[0, np.flatnonzero(ag[1:] != ag[:-1]) + 1]
    rank = np.arange(len(ag)) - np.repeat(start, np.diff(np.r_[start, len(ag)]))
    top = rank < k_events
    j = pos[ag[top]]
    link(sim, events[j], "event", eff.event[sel[top]], sign * c[top], note=var_note(sim, var))


# ----------------------------------------------------------------------------- lookups
def _window(log, since: int) -> int:
    """First log row on or after `since` (the log is in time order)."""
    return int(np.searchsorted(log["day"], since, side="left"))


def latest_event(sim, people, types, since: int, until: int | None = None, who: str = "a") -> np.ndarray:
    """For each person, the id of their latest event of one of `types` on days [since, until] (−1 if none)."""
    people = np.atleast_1d(np.asarray(people, np.int64))
    out = np.full(len(people), -1, np.int64)
    log = sim.log
    if not len(people) or not log.n:
        return out
    s = _window(log, since)
    codes = [sim.reg.event_ids[t] for t in types if t in sim.reg.event_ids]
    t = log["type"][s:]
    m = np.isin(t, codes)
    if until is not None:
        m &= log["day"][s:] <= until
    rows = np.flatnonzero(m) + s
    if not len(rows):
        return out
    ag = log[who][rows].astype(np.int64)
    order = np.lexsort((rows, ag))           # by person, then id: the last of each run is the latest
    ag, rows = ag[order], rows[order]
    last = np.r_[ag[1:] != ag[:-1], True]
    ag, rows = ag[last], rows[last]
    k = np.searchsorted(ag, people)
    k = np.clip(k, 0, len(ag) - 1)
    hit = ag[k] == people
    out[hit] = rows[k[hit]]
    return out


def latest_between(sim, a, b, types, since: int) -> np.ndarray:
    """For each pair, the latest event of one of `types` between them (either direction) since a day (−1 if none)."""
    a = np.atleast_1d(np.asarray(a, np.int64))
    b = np.atleast_1d(np.asarray(b, np.int64))
    out = np.full(len(a), -1, np.int64)
    log = sim.log
    if not len(a) or not log.n:
        return out
    s = _window(log, since)
    codes = [sim.reg.event_ids[t] for t in types if t in sim.reg.event_ids]
    m = np.isin(log["type"][s:], codes) & (log["b"][s:] >= 0)
    rows = np.flatnonzero(m) + s
    if not len(rows):
        return out
    kk = tie_key(log["a"][rows], log["b"][rows])
    order = np.lexsort((rows, kk))
    kk, rows = kk[order], rows[order]
    last = np.r_[kk[1:] != kk[:-1], True]
    kk, rows = kk[last], rows[last]
    want = tie_key(a, b)
    k = np.clip(np.searchsorted(kk, want), 0, len(kk) - 1)
    hit = kk[k] == want
    out[hit] = rows[k[hit]]
    return out


def best_neighbor(adj, ids, ok, weight) -> np.ndarray:
    """For each person in `ids`, the neighbor in CSR adjacency `adj` = (indptr, nbr, eidx) with the largest edge
    `weight` among those where `ok[neighbor]` holds (−1 if none): e.g. the closest friend who already drinks coffee."""
    indptr, nbr, eidx = adj
    ids = np.atleast_1d(np.asarray(ids, np.int64))
    out = np.full(len(ids), -1, np.int64)
    if not len(ids) or not len(nbr):
        return out
    ids_c = np.minimum(ids, len(indptr) - 2)
    start, stop = indptr[ids_c], indptr[ids_c + 1]
    cnt = np.where(ids < len(indptr) - 1, stop - start, 0)
    if not cnt.sum():
        return out
    owner = np.repeat(np.arange(len(ids)), cnt)
    flat = np.repeat(start - np.r_[0, np.cumsum(cnt)[:-1]], cnt) + np.arange(int(cnt.sum()))
    nb = nbr[flat].astype(np.int64)
    good = ok[nb]
    owner, nb, wt = owner[good], nb[good], np.asarray(weight)[eidx[flat[good]]]
    if not len(owner):
        return out
    order = np.lexsort((-wt, owner))
    owner, nb = owner[order], nb[order]
    first = np.r_[True, owner[1:] != owner[:-1]]
    out[owner[first]] = nb[first]
    return out


def hard_memories(sim, people, days: int, per: int = 1) -> np.ndarray:
    """The most salient negative memories each person laid down in the last `days` days: (len(people), per) event
    ids, −1 where there are fewer. Read-only (it does not rehearse anything)."""
    people = np.atleast_1d(np.asarray(people, np.int64))
    out = np.full((len(people), per), -1, np.int64)
    mem = sim.memory
    if mem.n == 0 or not len(people):
        return out
    day = sim.w.day
    pm = np.zeros(int(max(people.max(), mem["agent"].max())) + 1, bool)
    pm[people] = True
    sel = np.flatnonzero((mem["day"] >= day - days) & (mem["valence"].astype(np.float32) < -0.1) & pm[mem["agent"]])
    if not len(sel):
        return out
    score = mem["importance"][sel].astype(np.float32) * -mem["valence"][sel].astype(np.float32)
    ag = mem["agent"][sel].astype(np.int64)
    order = np.lexsort((-score, ag))
    sel, ag = sel[order], ag[order]
    start = np.r_[0, np.flatnonzero(ag[1:] != ag[:-1]) + 1]
    rank = np.arange(len(ag)) - np.repeat(start, np.diff(np.r_[start, len(ag)]))
    keep = rank < per
    sel, ag, rank = sel[keep], ag[keep], rank[keep]
    srt = np.argsort(people, kind="stable")
    ps = people[srt]
    k = np.clip(np.searchsorted(ps, ag), 0, len(ps) - 1)
    ok = ps[k] == ag
    out[srt[k[ok]], rank[ok]] = mem["event"][sel[ok]]
    return out


# ----------------------------------------------------------------------------- time together on ties
def note_time(E, eix, ctx, place, hours):
    """Credit hours together to each tie's context slots.

    A tie keeps a top context (with the latest place of that kind and its hours) and a runner-up. Hours in the top
    context add to it; hours in the runner-up's add there and can overtake the top; hours in any other context are
    taken from the runner-up until that context replaces it (Misra–Gries style). The top slot's hours are exact while
    it stays on top; the runner-up's are a lower bound. Bookkeeping only: nothing in behavior reads these columns."""
    eix = np.atleast_1d(np.asarray(eix, np.int64))
    if not len(eix):
        return
    ctx = np.broadcast_to(np.asarray(ctx, np.int64), eix.shape)
    place = np.broadcast_to(np.asarray(place, np.int64), eix.shape)
    hours = np.broadcast_to(np.asarray(hours, np.float32), eix.shape)
    m = hours > 0
    if not m.any():
        return
    eix, ctx, place, hours = eix[m], ctx[m], place[m], hours[m]
    order = np.argsort(eix, kind="stable")
    eix, ctx, place, hours = eix[order], ctx[order], place[order], hours[order]
    start = np.r_[0, np.flatnonzero(eix[1:] != eix[:-1]) + 1]
    rank = np.arange(len(eix)) - np.repeat(start, np.diff(np.r_[start, len(eix)]))
    C = E.cols
    for r in range(int(rank.max()) + 1):
        s = rank == r
        e, c, pl, h = eix[s], ctx[s], place[s], hours[s]
        tc, th, tp = C["top_ctx"][e].astype(np.int64), C["top_h"][e], C["top_place"][e]
        ac, ah = C["alt_ctx"][e].astype(np.int64), C["alt_h"][e]
        on_top = (th <= 0) | (tc == c)
        th2 = np.where(on_top, np.maximum(th, 0) + h, th)
        tc2 = np.where(on_top, c, tc)
        tp2 = np.where(on_top & ((pl >= 0) | (th <= 0)), pl, tp)
        rest = ~on_top
        on_alt = rest & (ah > 0) & (ac == c)
        empty = rest & (ah <= 0)
        other = rest & ~on_alt & ~empty
        ah2 = np.where(on_alt, ah + h, np.where(empty, h, np.where(other, ah - h, ah)))
        ac2 = np.where(empty, c, ac)
        took = other & (ah2 < 0)
        ah2 = np.where(took, -ah2, ah2)
        ac2 = np.where(took, c, ac2)
        swap = ah2 > th2
        C["top_ctx"][e] = np.where(swap, ac2, tc2)
        C["top_h"][e] = np.where(swap, ah2, th2)
        C["top_place"][e] = np.where(swap, np.where(ac2 == c, pl, -1), tp2)
        C["alt_ctx"][e] = np.where(swap, tc2, ac2)
        C["alt_h"][e] = np.where(swap, th2, ah2)


def tie_story_causes(sim, events, eix, E=None):
    """Where a pair met, who brought them together and where their time together went, as typed causes of
    `events` (one per tie in `eix`)."""
    E = E if E is not None else sim.w.E
    events = np.atleast_1d(np.asarray(events, np.int64))
    eix = np.atleast_1d(np.asarray(eix, np.int64))
    if not len(events):
        return
    from .state import CTX_ID
    oc = E["origin_ctx"][eix].astype(np.int64)
    op = E["origin_place"][eix].astype(np.int64)
    occ = CTX_ID.get("occasion", -1)
    at_occ = oc == occ
    link(sim, events[at_occ], "occasion", op[at_occ], 0.6, "met_at")
    # elsewhere: the kind of place and its id (people who knew each other before the story began say so)
    other = ~at_occ
    link(sim, events[other], "place", place_ref(oc[other], op[other]), 0.6, "met_at")
    intro = E["introducer"][eix].astype(np.int64)
    link(sim, events, "person", intro, 0.5, "introduced")
    tot = np.maximum(E["hours"][eix], 1e-6)
    th = E["top_h"][eix]
    has = th > 0
    link(sim, events[has], "place", place_ref(E["top_ctx"][eix][has], E["top_place"][eix][has]),
         np.clip(th[has] / tot[has], 0, 1), "time_together")
    ah = E["alt_h"][eix]
    has = ah > 0
    link(sim, events[has], "place", place_ref(E["alt_ctx"][eix][has], -1), np.clip(ah[has] / tot[has], 0, 1),
         "also_together")
