"""Institution endpoints (engine/systems/institutions.py): the list of organizations with their capacity and state, and
one organization's history (demand, served, waitlist), its decisions, the events it ran and its queue. Read-only."""
from __future__ import annotations

import numpy as np
from fastapi import APIRouter, HTTPException

from .routes_trace import _server

router = APIRouter()
ACTION_WORDS = {"add_food": "added food", "change_night": "moved to another night", "recruit": "recruited new members",
                "cap": "capped the room", "skip_food": "dropped the food", "held_activity": "held an activity",
                "service_project": "held a service project", "resident_event": "held a resident event"}
ORG_KIND = {"club": "group", "team": "group", "institute": "group", "ward": "ward", "complex": "complex"}


def _inst(sim):
    m = sim.systems.get("institutions")
    if m is None:
        raise HTTPException(404, "institutions aren't running in this world")
    return m


@router.get("/api/institutions")
def institutions(u: str = "base", kind: str = ""):
    """Every organization (or one kind): capacity, budget, demand, served, waitlist, utilization."""
    WS, jresp = _server()
    with WS.lock:
        I = _inst(WS.sim(u))
        rows = [I.describe(j) for j in range(I.T.n)]
        if kind:
            rows = [r for r in rows if r["kind"] == kind]
        return jresp(rows)


@router.get("/api/institutions/find")
def find(kind: str, ref: int, u: str = "base"):
    """The institution id for a place (complex:12, ward:3) or a club/team (group id)."""
    WS, jresp = _server()
    with WS.lock:
        I = _inst(WS.sim(u))
        for k in ([kind] if kind != "group" else ["club", "team", "institute"]):
            j = I.row(k, ref)
            if j >= 0:
                return jresp({"id": int(I.T.ids[j])})
        raise HTTPException(404, "no such institution")


@router.get("/api/institutions/{iid}")
def institution(iid: int, u: str = "base"):
    from ..analysis.person import synthetic_name
    from ..engine.ledger import ORG_ID
    from ..engine.systems.institutions import ACTIONS
    WS, jresp = _server()
    with WS.lock:
        sim = WS.sim(u)
        I = _inst(sim)
        j = int(I.T.pos([iid])[0])
        if j < 0:
            raise HTTPException(404, "no such institution")
        d = I.describe(j)
        H = I.hist
        h = np.flatnonzero(H["inst"] == iid)
        d["history"] = [{"day": int(H["day"][r]), "demand": float(H["demand"][r]), "served": float(H["served"][r]),
                         "waitlist": int(H["waitlist"][r]), "attended": int(H["attended"][r])} for r in h]
        D = I.dec
        dr = np.flatnonzero(D["inst"] == iid)
        d["decisions"] = [{"day": int(D["day"][r]), "date": str(sim.cal.date(int(D["day"][r]))), "action": ACTIONS[int(D["action"][r])],
                           "words": ACTION_WORDS[ACTIONS[int(D["action"][r])]], "turnout": round(float(D["why"][r]), 3),
                           "officer": int(D["officer"][r]) if D["officer"][r] >= 0 else None,
                           "officer_name": synthetic_name(sim.w.P, int(D["officer"][r])) if D["officer"][r] >= 0 else None,
                           "event": int(D["event"][r]) if D["event"][r] >= 0 else None,
                           "occasion": int(D["occasion"][r]) if D["occasion"][r] >= 0 else None} for r in dr[::-1]]
        ok = ORG_KIND.get(d["kind"])
        occs = []
        if ok:
            O = sim.book.occ
            m = (O["org_kind"] == ORG_ID[ok]) & (O["org_id"] == d["ref"]) & (O["origin"] == 2)
            for r in np.flatnonzero(m)[::-1][:30]:
                occs.append({"id": int(O.ids[r]), "day": int(O["day"][r]), "date": str(sim.cal.date(int(O["day"][r]))),
                             "label": sim.book.vocab[sim.book.kinds[int(O["kind"][r])]].get("label"),
                             "came": int(O["n_came"][r]), "status": ["planned", "happened", "cancelled"][int(O["status"][r])]})
        d["occasions"] = occs
        if d["kind"] == "counseling":
            Q = I.q
            m = Q["center"] == iid
            day = sim.w.day
            waiting = np.flatnonzero(m & (Q["start"] < 0) & (Q["done"] < 0) & ~Q["gave_up"])
            care = np.flatnonzero(m & (Q["start"] >= 0) & (Q["done"] < 0))
            pr = lambda r, **kw: {"person": int(Q["person"][r]), "name": synthetic_name(sim.w.P, int(Q["person"][r])),  # noqa: E731
                                  "asked": int(Q["asked"][r]), "crisis": bool(Q["crisis"][r]), **kw}
            d["queue"] = {"waiting": [pr(r, waited=day - int(Q["asked"][r])) for r in waiting[:60]],
                          "in_care": [pr(r, sessions=int(Q["sessions"][r])) for r in care[:60]],
                          "n_waiting": int(len(waiting)), "n_in_care": int(len(care)),
                          "n_finished": int((m & (Q["done"] >= 0)).sum()), "n_gave_up": int((m & Q["gave_up"]).sum()),
                          "mean_wait_days": round(float((Q["start"][m & (Q["start"] >= 0)] - Q["asked"][m & (Q["start"] >= 0)]).mean()), 1)
                          if (m & (Q["start"] >= 0)).any() else None}
        if d["kind"] in ("club", "team", "institute", "ward", "complex"):
            d["members"] = int(len(I._members(j)))
        if d["kind"] == "employer":
            P = sim.w.P
            d["members"] = int(((P["employer_id"][: P.n] == d["ref"]) & P["employed"][: P.n] & P["present"][: P.n].astype(bool)).sum())
            d["flexibility"] = d.pop("capacity")
        return jresp(d)
