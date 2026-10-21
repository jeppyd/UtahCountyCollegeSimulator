"""Travel times (geo/travel.py over geo/data/travel.npz): BYU↔UVU by car, UVX and walking in plausible ranges, no
UVX on Sunday (UTA's feed has none), snow slows trips, zones cover the area, vectorized trips are fast."""
import time

import numpy as np
from fastapi.testclient import TestClient

from ucsim.api import server
from ucsim.geo.travel import MODE_ID, TravelModel

BYU, UVU = (-111.6493, 40.2500), (-111.7129, 40.2773)


def test_built_matrices_are_used(fresh):
    assert fresh.travel.ok and "UTA GTFS" in fresh.travel.source
    assert len(fresh.travel.names) >= 60 and "BYU campus" in fresh.travel.names


def test_byu_to_uvu_by_mode(fresh):
    m = fresh.travel.modes(*BYU, *UVU, 1, 480)              # Tuesday 8:00
    assert 12 <= m["car"] <= 30                               # ~15 min driving plus parking at UVU
    assert 20 <= m["transit"] <= 45                           # UVX door to door
    assert 70 <= m["walk"] <= 130
    assert m["bike"] < m["walk"] and m["car"] < m["transit"] < m["walk"]
    peak = fresh.travel.modes(*BYU, *UVU, 1, 1050)["car"]
    assert peak >= m["car"]                                   # the evening peak is slower


def test_no_sunday_uvx(fresh):
    sun = fresh.travel.modes(*BYU, *UVU, 6, 750)
    sat = fresh.travel.modes(*BYU, *UVU, 5, 750)
    assert np.isnan(sun["transit"]) and np.isfinite(sat["transit"])


def test_zones_and_matrix(fresh):
    tm = fresh.travel
    z = tm.zone_of(np.array([BYU[0], UVU[0]]), np.array([BYU[1], UVU[1]]))
    assert [tm.names[k] for k in z] == ["BYU campus", "UVU campus"]
    M = tm.matrix("car", 1, 480)
    assert M.shape == (len(tm.names),) * 2 and np.isfinite(M).all()
    T = tm.matrix("transit", 6, 750)
    assert np.isnan(T).mean() > np.isnan(tm.matrix("transit", 1, 480)).mean()


def test_snow_slows(fresh):
    tm = fresh.travel
    env = fresh.w.env
    dry = tm.modes(*BYU, *UVU, 1, 480)
    old = env.get("snow_in", 0.0)
    env["snow_in"] = 4.0
    try:
        wet = tm.modes(*BYU, *UVU, 1, 480)
    finally:
        env["snow_in"] = old
    for k in ("walk", "bike", "car"):
        assert wet[k] > dry[k]


def test_trip_modes_and_speed(fresh):
    P = fresh.w.P
    ids = np.flatnonzero(P["present"].astype(bool))
    ids = np.resize(ids, 10000)
    t = time.perf_counter()
    mins, mode = fresh.travel.trip(ids, UVU[0], UVU[1], 1, 480)
    assert time.perf_counter() - t < 0.05
    assert np.isfinite(mins).all() and (mins > 0).all()
    car = P["owns_car"][ids].astype(bool)
    assert (mode[~car] != MODE_ID["car"]).all()
    assert (mode == MODE_ID["transit"]).any() and (mode == MODE_ID["car"]).any()
    _, m2 = fresh.travel.trip(ids[:200], UVU[0], UVU[1], 1, 480, ride=np.ones(200, bool))
    assert ((m2 == MODE_ID["ride"]) | car[:200]).any()


def test_fallback_without_matrices(fresh, tmp_path):
    tm = TravelModel(fresh.w, path=tmp_path / "missing.npz")
    assert not tm.ok and "straight-line" in tm.source
    mins, _ = tm.trip(np.arange(10), *UVU, 1, 480)
    assert np.isfinite(mins[fresh.w.P["present"][:10].astype(bool)]).all()


def test_api(fresh):
    saved = server.WS.base
    server.WS.base = fresh
    try:
        c = TestClient(server.app)
        z = c.get("/api/travel/zones").json()
        assert len(z["zones"]) == len(fresh.travel.names)
        r = c.get("/api/travel/trip", params={"from_lon": BYU[0], "from_lat": BYU[1], "to_lon": UVU[0], "to_lat": UVU[1],
                                              "weekday": 6, "minute": 750}).json()
        assert r["minutes"]["transit"] is None and r["minutes"]["car"] > 0 and r["from_zone"] == "BYU campus"
    finally:
        server.WS.base = saved
