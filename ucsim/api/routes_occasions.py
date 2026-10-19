"""Occasions and a person's day: the scene of a dinner or a dance, the day's occasions, someone's agenda, and the
free-time options they weigh right now (engine/systems/occasions.py, analysis/scenes.py)."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

router = APIRouter()


def _person(sim, i: int):
    if not 0 <= i < sim.w.P.n:
        raise HTTPException(404, f"no person {i}")


@router.get("/api/occasion/{oid}")
def occasion(oid: int, u: str = "base"):
    """One occasion as a scene: when and where, who organized it and why, every invitation (how it was sent, when it
    was seen, the answer and the reasons), who came (when, how they got there), who met whom, and what happened."""
    from ..analysis.scenes import scene
    from .routes_trace import _server
    WS, jresp = _server()   # under `python -m` the serving module is __main__
    sim = WS.sim(u)
    with WS.lock:
        out = scene(sim, oid)
    if not out:
        raise HTTPException(404, f"no occasion {oid} (it may never have existed in this world)")
    return jresp(out)


@router.get("/api/occasions")
def occasions(u: str = "base", day: int | None = None, kind: str | None = None, person: int | None = None,
              place: int | None = None, limit: int = 300):
    """Occasions on a day (default today), of a kind, involving a person (all days), or at a place."""
    from ..analysis.scenes import list_occasions
    from .routes_trace import _server
    WS, jresp = _server()   # under `python -m` the serving module is __main__
    sim = WS.sim(u)
    with WS.lock:
        out = list_occasions(sim, day=day, kind=kind, person=person, place=place, limit=max(1, min(limit, 2000)))
        out["today"] = sim.w.day
    return jresp(out)


@router.get("/api/person/{i}/day")
def person_day(i: int, u: str = "base", day: int | None = None):
    """A person's day: the four blocks (what they were doing), commitments with clock times (classes, shifts, church,
    clubs), the occasions they're invited to or organize (with times, places, how they'd get there) and free stretches."""
    from .routes_trace import _server
    WS, jresp = _server()   # under `python -m` the serving module is __main__
    sim = WS.sim(u)
    with WS.lock:
        _person(sim, i)
        return jresp(sim.systems["occasions"].agenda(i, day))


@router.get("/api/person/{i}/choice")
def person_choice(i: int, u: str = "base", block: int | None = None):
    """The free-time options a person weighs in a block today, each utility broken into the terms that were summed
    (computed now: everyday free-time choices are not logged one by one)."""
    from .routes_trace import _server
    WS, jresp = _server()   # under `python -m` the serving module is __main__
    sim = WS.sim(u)
    with WS.lock:
        _person(sim, i)
        return jresp(sim.systems["activity"].explain_choice(i, block))
