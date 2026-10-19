"""Family endpoints (engine/systems/family.py): a person's home, family and trips; how many people come from each
state and how many are home there right now; the people from one state. Read-only."""
from __future__ import annotations

import numpy as np
from fastapi import APIRouter, HTTPException

from .routes_trace import _server

router = APIRouter()


def _fam(sim):
    f = sim.systems.get("family")
    if f is None:
        raise HTTPException(404, "the family system isn't running in this world")
    return f


@router.get("/api/family/person/{i}")
def person(i: int, u: str = "base"):
    WS, jresp = _server()
    with WS.lock:
        sim = WS.sim(u)
        if not (0 <= i < sim.w.P.n):
            raise HTTPException(404, "no such person")
        d = _fam(sim).person(i)
        d["date"] = {t["depart"]: str(sim.cal.date(t["depart"])) for t in d["trips"]}
        return jresp(d)


@router.get("/api/family/states")
def states(u: str = "base"):
    """Per home state: how many people are from there, how many are in Provo–Orem now and how many are home."""
    WS, jresp = _server()
    with WS.lock:
        sim = WS.sim(u)
        rows = _fam(sim).by_state()
        return jresp({"day": int(sim.w.day), "date": str(sim.cal.date(sim.w.day)), "states": rows,
                      "away": int(sum(r["at_home"] for r in rows)), "total": int(sum(r["from"] for r in rows))})


@router.get("/api/family/state/{name}")
def state_people(name: str, u: str = "base", where: str = "all", limit: int = 5000):
    """People whose family lives in a state (where = all | here | home)."""
    WS, jresp = _server()
    with WS.lock:
        sim = WS.sim(u)
        P = sim.w.P
        _fam(sim)
        cats = list(P.specs["home_state"].categories)
        if name not in cats:
            raise HTTPException(404, "no such state")
        n = P.n
        here = P["present"][:n].astype(bool)
        away = P.internal["trip_away"][:n]
        m = P["home_state"][:n] == cats.index(name)
        m &= {"here": here, "home": away}.get(where, here | away)
        return jresp({"state": name, "people": np.flatnonzero(m)[:limit].tolist(), "n": int(m.sum())})
