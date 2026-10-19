"""Workbench reads: events for a selection (many people or a filter, a time window, categories, a search), how many
events of each kind happened each day for that selection, and a venue as a place. Read-only, vectorized over the event
log; names and labels are made only for the rows that are returned."""
from __future__ import annotations

import json

import numpy as np
from fastapi import APIRouter, HTTPException

router = APIRouter()

MAX_PEOPLE = 20000


def _server():
    """(WS, jresp) of the running server (see routes_trace._server: under `python -m` the serving module is __main__)."""
    from .routes_trace import _server as s
    return s()


def _ids(people: str) -> np.ndarray | None:
    if not people:
        return None
    try:
        ids = np.array([int(x) for x in people.split(",") if x.strip() != ""], dtype=np.int64)
    except ValueError:
        raise HTTPException(400, "people must be comma-separated person numbers") from None
    if len(ids) > MAX_PEOPLE:
        raise HTTPException(400, f"at most {MAX_PEOPLE} people; use a filter for bigger groups")
    return ids


def _person_mask(sim, people: str, filter: str) -> np.ndarray | None:
    """Who the selection is, as a mask over everyone (None = no restriction). People who left still count: their
    events stay in the log."""
    from ..analysis.query import evaluate_filter
    n = sim.w.P.n
    m = None
    ids = _ids(people)
    if ids is not None:
        m = np.zeros(n, bool)
        m[ids[(ids >= 0) & (ids < n)]] = True
    if filter:
        try:
            f = json.loads(filter)
        except ValueError:
            raise HTTPException(400, "filter must be JSON") from None
        if isinstance(f, list):
            f = {"and": f} if f else None
        if f:
            fm = evaluate_filter(sim.w, f, sim, include_absent=True)
            m = fm if m is None else (m & fm)
    return m


def _event_mask(sim, pm, since, until, cats, types, min_salience, place):
    log, reg = sim.log, sim.reg
    m = np.ones(log.n, bool)
    if since is not None:
        m &= log["day"] >= since
    if until is not None:
        m &= log["day"] <= until
    names = reg.event_names
    if cats or types or min_salience > 0:
        cat_ok = np.ones(len(names), bool)
        if cats:
            want = set(cats.split(","))
            cat_ok &= np.array([reg.events[t].category in want for t in names])
        if types:
            want = set(types.split(","))
            cat_ok &= np.array([t in want for t in names])
        if min_salience > 0:
            cat_ok &= np.array([reg.events[t].salience >= min_salience for t in names])
        m &= cat_ok[log["type"]]
    if place is not None:
        m &= log["place"] == place
    if pm is not None:
        a, b = log["a"], log["b"]
        hit = pm[np.clip(a, 0, len(pm) - 1)] & (a >= 0) & (a < len(pm))
        hit |= (b >= 0) & (b < len(pm)) & pm[np.clip(b, 0, len(pm) - 1)]
        m &= hit
    return m


def _rows(sim, idx: np.ndarray) -> list[dict]:
    from ..analysis import explain as X
    from ..analysis.person import synthetic_name
    log, reg, P = sim.log, sim.reg, sim.w.P
    special = {reg.event_ids[t] for t in ("whatif_shock", "whatif_practice", "intervention_exposure") if t in reg.event_ids}
    day, blk, typ = log["day"][idx], log["block"][idx], log["type"][idx]
    a, b, cause, dec, place, val = (log["a"][idx], log["b"][idx], log["cause"][idx], log["decision"][idx],
                                    log["place"][idx], log["value"][idx])
    names = {}

    def nm(i):
        if i not in names:
            names[i] = synthetic_name(P, i) if 0 <= i < P.n else None
        return names[i]
    out = []
    for k in range(len(idx)):
        t = int(typ[k])
        spec = reg.events[reg.event_names[t]]
        label = X.event_record(sim, int(idx[k]))["label"] if t in special else spec.label
        ai, bi = int(a[k]), int(b[k])
        out.append({"id": int(idx[k]), "day": int(day[k]), "block": int(blk[k]), "type": spec.id, "label": label,
                    "category": spec.category, "salience": spec.salience, "value": round(float(val[k]), 3),
                    "a": ai, "a_name": nm(ai), "b": bi if bi >= 0 else None, "b_name": nm(bi) if bi >= 0 else None,
                    "cause": int(cause[k]) if cause[k] >= 0 else None, "decision": int(dec[k]) if dec[k] >= 0 else None,
                    "place": int(place[k]) if place[k] >= 0 else None})
    return out


@router.get("/api/bench/events")
def bench_events(u: str = "base", people: str = "", filter: str = "", since: int | None = None, until: int | None = None,
                 cats: str = "", types: str = "", q: str = "", min_salience: float = 0.0, place: int | None = None,
                 limit: int = 300, offset: int = 0, order: str = "new"):
    """Events involving the selected people (ids and/or a filter), in a time window, of some categories or types,
    whose label or type matches `q`; newest first unless order=old."""
    WS, jresp = _server()
    sim = WS.sim(u)
    with WS.lock:
        pm = _person_mask(sim, people, filter)
        m = _event_mask(sim, pm, since, until, cats, types, min_salience, place)
        if q.strip():
            reg = sim.reg
            words = q.strip().lower().split()
            ok = np.array([all(w in (reg.events[t].label + " " + t.replace("_", " ")).lower() for w in words)
                           for t in reg.event_names])
            m &= ok[sim.log["type"]]
        idx = np.nonzero(m)[0]
        if order != "old":
            idx = idx[::-1]
        total = int(len(idx))
        limit = max(1, min(int(limit), 5000))
        rows = _rows(sim, idx[offset: offset + limit])
        return jresp({"total": total, "events": rows, "today": sim.w.day, "start_date": str(sim.cal.date(0)),
                      "n_people": None if pm is None else int(pm.sum())})


@router.get("/api/bench/density")
def bench_density(u: str = "base", people: str = "", filter: str = "", since: int | None = None,
                  until: int | None = None, min_salience: float = 0.0):
    """How many events of each category happened on each day, for the selected people (or everyone)."""
    WS, jresp = _server()
    sim = WS.sim(u)
    with WS.lock:
        log, reg = sim.log, sim.reg
        d0 = 0 if since is None else max(int(since), int(log["day"].min()) if log.n else 0)
        d1 = sim.w.day if until is None else min(int(until), sim.w.day)
        pm = _person_mask(sim, people, filter)
        m = _event_mask(sim, pm, d0, d1, "", "", min_salience, None)
        cats = sorted({e.category for e in reg.events.values()})
        cat_of = np.array([cats.index(reg.events[t].category) for t in reg.event_names])
        nd = max(d1 - d0 + 1, 1)
        c = cat_of[log["type"][m]]
        dd = log["day"][m] - d0
        grid = np.bincount(dd * len(cats) + c, minlength=nd * len(cats)).reshape(nd, len(cats))
        used = grid.sum(0) > 0
        return jresp({"days": list(range(d0, d0 + nd)), "cats": [k for k, x in zip(cats, used) if x],
                      "counts": {k: grid[:, j].tolist() for j, k in enumerate(cats) if used[j]},
                      "total": int(m.sum()), "n_people": None if pm is None else int(pm.sum()),
                      "start_date": str(sim.cal.date(0)), "today": sim.w.day})


@router.get("/api/bench/venue/{vid}")
def bench_venue(vid: int, u: str = "base", limit: int = 60):
    """A venue (a café, a park, a dance hall…) as a place: what it is, the occasions held there and the events the log
    places there (dates, first kisses, introductions; most events are recorded by person, not by place)."""
    WS, jresp = _server()
    sim = WS.sim(u)
    with WS.lock:
        act = sim.systems["activity"]
        if not 0 <= vid < len(act.v_name):
            raise HTTPException(404, f"no venue {vid}")
        log, reg = sim.log, sim.reg
        at = np.nonzero(log["place"] == vid)[0] if log.n else np.empty(0, np.int64)
        # only event types that record a venue as their place (dates, kisses, introductions)
        venue_types = {"first_date", "date", "first_kiss_with", "introduced"}
        codes = [reg.event_ids[t] for t in venue_types if t in reg.event_ids]
        at = at[np.isin(log["type"][at], codes)]
        cnt = np.bincount(log["type"][at], minlength=len(reg.event_names)) if len(at) else np.zeros(0, int)
        counts = [{"type": reg.event_names[k], "label": reg.events[reg.event_names[k]].label, "count": int(cnt[k])}
                  for k in np.nonzero(cnt)[0]]
        counts.sort(key=lambda r: -r["count"])
        occs = []
        book = sim.book
        O = book.occ
        if O.n:
            occ_sys = sim.systems["occasions"]
            venue_kinds = [c for c in range(len(occ_sys.k_where)) if occ_sys.k_where[c] == "venue" or c == occ_sys.date_code]
            mo = (O["place"] == vid) & np.isin(O["kind"], venue_kinds)
            ids = O["id"][mo]
            ids = ids[np.argsort(-O["day"][mo], kind="stable")][:limit]
            from ..analysis.scenes import occasion_row
            occs = [occasion_row(sim, int(o)) for o in ids]
        return jresp({"id": vid, "name": act.v_name[vid], "vtype": str(act.v_type[vid]), "lon": float(act.v_lon[vid]),
                      "lat": float(act.v_lat[vid]), "event_counts": counts, "n_events": int(len(at)),
                      "events": _rows(sim, at[::-1][:limit]), "occasions": occs, "n_occasions": int(O.n and mo.sum()),
                      "note": "Events here are the ones the model records at a venue (dates, first kisses, introductions);"
                              " most events are recorded by person, not by place."})
