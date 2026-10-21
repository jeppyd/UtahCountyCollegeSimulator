"""Travel endpoints (geo/travel.py): the zones and door-to-door minutes by every mode between two points."""
from __future__ import annotations

import numpy as np
from fastapi import APIRouter

from .routes_trace import _server

router = APIRouter()


def _model():
    WS, jresp = _server()
    sim = WS.base
    if sim is not None:
        return sim.travel, jresp
    from ..geo.travel import TravelModel

    class _W:            # no world yet: the matrices don't need one
        env: dict = {}
        P = None
    return TravelModel(_W()), jresp


@router.get("/api/travel/zones")
def zones():
    """The travel zones: id, name, centroid and how many dwellings each has."""
    tm, jresp = _model()
    if not tm.ok:
        return jresp({"source": tm.source, "zones": []})
    return jresp({"source": tm.source, "meta": tm.meta, "zones": [
        {"id": k, "name": n, "lon": float(tm.centroid[k, 0]), "lat": float(tm.centroid[k, 1])} for k, n in enumerate(tm.names)]})


@router.get("/api/travel/trip")
def trip(from_lon: float, from_lat: float, to_lon: float, to_lat: float, weekday: int = 1, minute: int = 480):
    """Door-to-door minutes by each mode (walk, bike, car, transit; null where a mode doesn't run)."""
    tm, jresp = _model()
    m = tm.modes(from_lon, from_lat, to_lon, to_lat, weekday, minute)
    out = {k: (None if not np.isfinite(float(v)) else round(float(v), 1)) for k, v in m.items()}
    z = tm.zone_of(np.array([from_lon, to_lon]), np.array([from_lat, to_lat]))
    names = getattr(tm, "names", None)
    return jresp({"minutes": out, "source": tm.source, "weekday": weekday, "minute": minute,
                  "from_zone": names[int(z[0])] if names else None, "to_zone": names[int(z[1])] if names else None})
