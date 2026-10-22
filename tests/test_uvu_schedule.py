"""UVU's real Fall 2026 class schedule (geo/schedule.py): UVU students take real courses at their real buildings, rooms
and times, nobody's classes clash, people in class are drawn in their room's building on a floor it has, and the
committed table carries no names."""
import numpy as np
import polars as pl
import pytest

from ucsim.analysis import sync_check
from ucsim.engine import places
from ucsim.engine.runner import new_simulation
from ucsim.geo import schedule

pytestmark = pytest.mark.skipif(schedule.load("UVU") is None, reason="UVU schedule table missing")


@pytest.fixture(scope="module")
def fall():
    s = new_simulation(scale=0.1, seed=5)
    s.systems["academics"].start_term("UVU", term="Fall")
    return s


def test_table_holds_no_names():
    cols = pl.read_parquet_schema(schedule.UVU_OUT)
    assert not any(k in c.lower() for c in cols for k in ("instructor", "name", "title", "_id"))
    U = schedule.load("UVU")
    assert U.height > 2000 and set(U["term"].unique()) == {"Fall"}
    assert not U["building"].str.starts_with("HS").any()          # no high-school concurrent enrollment


def test_floors_from_room_numbers():
    assert schedule.uvu_floors(["LA", "LA", "LA", "CS", "CS"], ["002", "112", "236", "404", "707"]) == [0, 0, 1, 0, 3]


def test_sections_are_real(fall):
    ac, P = fall.systems["academics"], fall.w.P
    uvu = np.flatnonzero(ac.sec_school == 2)
    assert len(uvu) > 50 and (ac.sec_start[uvu] >= 0).all() and all(ac.sec_course[uvu])
    U = schedule.load("UVU")
    real = set(zip(U["dept"] + " " + U["catalog"], U["building"] + " " + U["room"], U["start"].to_list()))
    for s in uvu[:200]:
        assert (ac.sec_course[s], ac.sec_where[s], int(ac.sec_start[s])) in real
    assert not any(c.startswith("REL") for c in ac.sec_course[uvu])
    ids = np.flatnonzero((P["school"][: P.n] == 2) & P["enrolled"][: P.n])
    h = ac.stu_secs[ids]
    assert 3.0 < (h >= 0).sum(axis=1).mean() <= 5
    d, s_, e_ = ac.sec_days, ac.sec_start, ac.sec_end
    for j in range(5):                                       # no two of a student's classes overlap
        for k in range(j + 1, 5):
            a, b = h[:, j], h[:, k]
            ok = (a >= 0) & (b >= 0)
            a, b = np.maximum(a, 0), np.maximum(b, 0)
            assert not (ok & ((a == b) | (((d[a] & d[b]) > 0) & (s_[a] < e_[b]) & (s_[b] < e_[a])))).any()
    if places.available():
        assert (ac.sec_place[uvu] >= 0).all()
        F = places.footprints()
        assert {F["name"][b] for b in ac.sec_place[uvu]} & {"Liberal Arts Building", "Science Building", "Clarke Building"}


def test_dots_in_real_buildings():
    """On a UVU class day, UVU students in class are drawn in their real room's building, on a floor it has."""
    s = new_simulation(scale=0.05, seed=5)
    while not (s.cal.term("UVU", s.w.day) and s.cal.weekday(s.w.day) < 5 and not s.cal.holiday(s.w.day)):
        s.run_days(1)
    ac = s.systems["academics"]
    assert (ac.sec_start[ac.sec_school == 2] >= 0).all()
    s.advance_hours(4)
    rep = sync_check.check(s)
    cls = [r for r in rep["rows"] if r["place"] == "class"]
    assert cls and cls[0]["people"] > 0
    assert cls[0]["in_building"] > 0.98 and cls[0]["floor_ok"] > 0.98, sync_check.table(rep)
