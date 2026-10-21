"""The living map: homes on real buildings and floors, everyone in a bedroom, people at the same occasion seated
together, flagship halls on their real buildings, and the map's endpoints (positions, a building's inside, a person
right now, what's happening now)."""
import numpy as np
import pytest
from fastapi.testclient import TestClient

from ucsim.api import server
from ucsim.engine import placement, rooms
from ucsim.engine.runner import new_simulation
from ucsim.engine.state import CTX_ID


@pytest.fixture(scope="module")
def sim():
    s = new_simulation(scale=0.05, seed=4)
    s.run_days(3)
    s.advance_hours(13)            # the evening: dates, dinners, parties
    return s


def test_everyone_at_home_has_a_bed(sim):
    P, U = sim.w.P, sim.w.units
    room = P.internal["room"][: P.n]
    home = (P["unit_id"][: P.n] >= 0) & P["present"][: P.n]
    assert (room[home] >= 0).all()
    assert (U.room_unit[room[home]] == P["unit_id"][: P.n][home]).all()
    assert int(U.room_cap.sum()) == int(U.capacity.sum())


def test_spouses_share_a_room(sim):
    P = sim.w.P
    m = np.flatnonzero(P.is_("rel_status", "married")[: P.n] & P["present"][: P.n] & (P["partner_id"][: P.n] >= 0))
    j = P["partner_id"][m]
    same_home = P["unit_id"][m] == P["unit_id"][j]
    assert same_home.any()
    assert rooms.same_room(sim.w, m[same_home], j[same_home]).mean() > 0.95


def test_flagship_halls_on_real_buildings(sim):
    U = sim.w.units
    halls = np.isin(U.complex_id, sim.w.complexes.filter(sim.w.complexes["kind"].is_in(["byu_dorm"]))["complex_id"].to_numpy())
    assert halls.sum() > 10
    assert (U.building_id[halls] >= 0).all()
    assert U.floor[halls].max() >= 2           # Heritage has four floors


def test_occasion_pairs_sit_together_and_nobody_overlaps(sim):
    f = sim.systems["activity"].snapshot
    pos = placement.place(sim, f)
    ok = np.isfinite(pos["x"])
    assert ok.sum() == f["present"].sum()
    d = np.flatnonzero((f["ctype"] == CTX_ID["occasion"]) & f["present"])
    oid, cnt = np.unique(f["cid"][d], return_counts=True)
    pairs = oid[cnt == 2]
    assert len(pairs)
    for o in pairs[:10]:
        ii = d[f["cid"][d] == o]
        assert np.hypot(*(pos["x"][ii[0]] - pos["x"][ii[1]], pos["y"][ii[0]] - pos["y"][ii[1]])) < 2.0
    xy = np.round(np.c_[pos["x"][ok], pos["y"][ok], pos["z"][ok]], 1)
    _, c = np.unique(xy, axis=0, return_counts=True)
    assert (c > 1).mean() < 0.05             # almost everyone has a spot of their own


def test_endpoints(sim):
    saved = server.WS.base, server.WS.alt
    server.WS.base, server.WS.alt = sim, None
    try:
        c = TestClient(server.app)
        r = c.get("/api/positions/precise")
        assert r.status_code == 200 and len(r.content) > 1000
        assert c.get("/api/positions/precise", params={"block": 2}).status_code == 200
        core = np.frombuffer(c.get("/api/buildings/core").content, np.int32)
        assert len(core) > 100
        b = int(sim.w.units.building_id[sim.w.units.building_id >= 0][0])
        d = c.get(f"/api/building/{b}").json()
        assert d["homes"] and all("rooms" in h for h in d["homes"])
        occ = c.get("/api/now/occasions").json()
        assert occ["occasions"] and occ["counts"]
        f = sim.systems["activity"].snapshot
        i = int(np.flatnonzero((f["ctype"] == CTX_ID["occasion"]) & f["present"])[0])
        now = c.get(f"/api/now/person/{i}").json()
        assert now["occasion"]["id"] == int(f["cid"][i]) and now["doing"] and isinstance(now["mind"], list)
    finally:
        server.WS.base, server.WS.alt = saved
