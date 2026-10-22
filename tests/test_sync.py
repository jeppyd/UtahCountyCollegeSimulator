"""The map shows people where the simulation has them (analysis/sync_check.py): every dot inside the building of its
place, on a floor that building has, groups together, nobody drawn on top of anybody."""
import numpy as np
import pytest

from ucsim.analysis import sync_check
from ucsim.engine import places
from ucsim.engine.runner import new_simulation
from ucsim.engine.state import CTX_ID

pytestmark = pytest.mark.skipif(not places.available(), reason="building layer missing")


@pytest.fixture(scope="module")
def sim():
    s = new_simulation(scale=0.05, seed=4)
    s.run_days(1)
    return s


def test_dots_where_the_simulation_has_them(sim):
    for h in (4, 3, 3):                       # morning classes, afternoon, evening
        sim.advance_hours(h)
        rep = sync_check.check(sim)
        t = rep["total"]
        assert t["in_building"] > 0.98, sync_check.table(rep)
        assert t["floor_ok"] > 0.98, sync_check.table(rep)
        assert t["stacked"] < 0.01, sync_check.table(rep)
        for r in rep["rows"]:
            if r["place"] in ("class", "ward", "club", "campus") and r["people"] >= 5:
                assert r["placed"] == 1.0 and r["in_building"] == 1.0, r


def test_campus_places_are_real_buildings(sim):
    F = places.footprints()
    for s_ in (1, 2):
        c = places.campus(s_)
        assert len(c["teaching"]) == 40 and (c["teaching"] >= 0).all()
        assert all(F["kind"][b] not in ("house", "minor") for b in np.unique(c["teaching"]))
    act = sim.systems["activity"]
    lon, lat = act._campus_point(np.array([int(places.campus(1)["spots"][0])]))
    from ucsim.engine.placement import to_xy
    x, y = to_xy(lon, lat)
    assert places.containing(x, y)[0] == places.campus(1)["spots"][0]


def test_settle_is_idempotent(sim):
    w = sim.w
    lo0, la0 = w.venues["lon"].to_numpy().copy(), w.venues["lat"].to_numpy().copy()
    places.settle_world(w)
    assert np.allclose(w.venues["lon"].to_numpy(), lo0) and np.allclose(w.venues["lat"].to_numpy(), la0)


def test_classes_meet_in_real_classrooms_that_fit(sim):
    import copy
    R = places.classrooms(1)
    if R is None:
        pytest.skip("no classroom plans")
    sim = copy.deepcopy(sim)
    ac = sim.systems["academics"]
    if not (ac.sec_school == 1).any():               # between BYU terms on this date: start one
        ac.start_term("BYU")
    byu = ac.sec_school == 1
    rm = ac.sec_room
    assert (rm[byu] >= 0).mean() > 0.95                          # nearly every BYU section has a room
    size = np.bincount(ac.stu_secs[ac.stu_secs >= 0], minlength=len(rm))
    has = rm >= 0
    assert (R["seats"][rm[has]] >= size[has]).all()             # everyone has a seat
    key = rm[has].astype(np.int64) * 1000 + ac.sec_days[has].astype(np.int64) * 10 + ac.sec_block[has]
    assert len(np.unique(key)) == has.sum()                      # no room double-booked at an hour
    from ucsim.analysis.now import _place_words
    f = sim.systems["activity"].snapshot
    from ucsim.engine import placement
    cls = (f["ctype"] == CTX_ID["class"]) & f["present"] & (f["cid"] >= 0) & (f["cid"] < len(rm))
    i = np.flatnonzero(cls)
    i = i[rm[f["cid"][i]] >= 0]
    if len(i):
        words = _place_words(sim, f, placement.place(sim, f), int(i[0]))["words"]
        assert words.startswith("class in ") and "seats" in words
