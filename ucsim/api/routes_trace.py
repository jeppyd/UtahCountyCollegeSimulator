"""Trace endpoints: causes and consequences of anything (analysis/trace.py), decisions with their reasons, and the
population view of chain reactions. Read-only: nothing here changes either world."""
from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException

router = APIRouter()


@router.get("/api/trace")
def trace(ref: str, u: str = "base", dir: str = "both", depth: int = 3, max_nodes: int = 80, fanout: int = 8,
          since: int | None = None):
    """The causal graph around one item: ref = event:<id> | decision:<id> | occasion:<id> | person:<id> | tie:<a>-<b> |
    var:<field>@<person> | place:<kind>:<id>; dir = back (what led to it) | fwd (what it led to) | both."""
    from ..analysis import trace as T
    from .server import WS, jresp
    if dir not in ("back", "fwd", "both"):
        raise HTTPException(400, "dir must be back, fwd or both")
    sim = WS.sim(u)
    with WS.lock:
        try:
            return jresp(T.trace(sim, ref, dir=dir, depth=depth, max_nodes=max_nodes, fanout=fanout, since=since))
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
        except KeyError as e:
            raise HTTPException(404, str(e).strip("'\"")) from e


@router.get("/api/trace/chains")
def chains(u: str = "base", since: int | None = None, until: int | None = None, filter: str | None = None,
           root: str | None = None, repeats: bool = False, max_links: int = 60):
    """Population chain reactions in a window: which kinds of events (and which decisions) led to which, with example
    instances, and the top reasons behind each decision outcome. `filter` is a cohort filter (JSON, query DSL); `root`
    an event type to center on."""
    import numpy as np

    from ..analysis import trace as T
    from ..analysis.query import evaluate_filter
    from .server import WS, jresp
    sim = WS.sim(u)
    with WS.lock:
        people = None
        if filter:
            try:
                filt = json.loads(filter)
            except json.JSONDecodeError as e:
                raise HTTPException(400, f"filter is not valid JSON: {e}") from e
            if filt:
                people = np.flatnonzero(evaluate_filter(sim.w, filt, sim, include_absent=True))
        if root and root not in sim.reg.events:
            raise HTTPException(404, f"no event type {root!r}")
        return jresp(T.chains(sim, since, until, people=people, root=root or None, repeats=repeats,
                              max_links=int(np.clip(max_links, 5, 200))))


@router.get("/api/decision/{did}")
def decision(did: int, u: str = "base"):
    """One recorded decision: its factors in words (with what they point at), the outcome, its probability, and the
    events it produced."""
    from ..analysis import trace as T
    from .server import WS, jresp
    sim = WS.sim(u)
    with WS.lock:
        d = T.decision_detail(sim, did)
        if not d:
            raise HTTPException(404, "no such decision (it may be older than the detailed history that is kept)")
        return jresp(d)


@router.get("/api/person/{i}/decisions")
def person_decisions(i: int, u: str = "base", since: int | None = None, limit: int = 200):
    """A person's recorded decisions, newest first, each with its top reason."""
    from ..analysis import trace as T
    from .server import WS, jresp
    sim = WS.sim(u)
    with WS.lock:
        if i < 0 or i >= sim.w.P.n:
            raise HTTPException(404, "no such person")
        return jresp({"person": i, "decisions": T.person_decisions(sim, i, since, limit=max(1, min(limit, 1000)))})
