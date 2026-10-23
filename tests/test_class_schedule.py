"""BYU's real class schedule (geo/schedule.py): Fall and Winter sections are real courses at their real rooms and
times, nobody's classes clash, the simulated campus fills buildings like BYU's own occupancy numbers, and the
committed tables carry no names."""
import numpy as np
import polars as pl
import pytest

from ucsim.analysis import sync_check
from ucsim.engine import clock, places
from ucsim.engine.runner import new_simulation
from ucsim.geo import schedule

pytestmark = pytest.mark.skipif(schedule.load() is None, reason="schedule table missing")


@pytest.fixture(scope="module")
def fall():
    s = new_simulation(scale=0.1, seed=5)
    s.systems["academics"].start_term("BYU", term="Fall")
    return s


def test_tables_hold_no_names():
    for path in (schedule.OUT, schedule.OCC):
        cols = pl.read_parquet_schema(path)
        assert not any(k in c.lower() for c in cols for k in ("instructor", "name", "title", "_id"))


def test_sections_are_real(fall):
    ac, P = fall.systems["academics"], fall.w.P
    byu = np.flatnonzero(ac.sec_school == 1)
    assert len(byu) > 50 and (ac.sec_start[byu] >= 0).all() and all(ac.sec_course[byu])
    S = schedule.load().filter(pl.col("term") == "Fall")
    real = set(zip(S["dept"] + " " + S["catalog"], S["building"] + " " + S["room"], S["start"].to_list()))
    for s in byu[:200]:
        assert (ac.sec_course[s], ac.sec_where[s], int(ac.sec_start[s])) in real
    st, en = fall.systems["activity"].class_times(byu)
    assert (st == ac.sec_start[byu]).all() and (en == ac.sec_end[byu]).all()
    assert (ac.sec_block[byu] == np.minimum(clock.part_of(st), 2)).all()      # its time band: morning, afternoon, evening
    ids = np.flatnonzero((P["school"][: P.n] == 1) & P["enrolled"][: P.n])
    h = ac.stu_secs[ids]
    assert 4.0 < (h >= 0).sum(axis=1).mean() <= 5
    d, s_, e_ = ac.sec_days, ac.sec_start, ac.sec_end
    for j in range(5):                                       # no two of a student's classes overlap
        for k in range(j + 1, 5):
            a, b = h[:, j], h[:, k]
            ok = (a >= 0) & (b >= 0)
            a, b = np.maximum(a, 0), np.maximum(b, 0)
            assert not (ok & ((a == b) | (((d[a] & d[b]) > 0) & (s_[a] < e_[b]) & (s_[b] < e_[a])))).any()
    if places.available():
        assert (ac.sec_place[byu] >= 0).mean() > 0.95


def test_buildings_fill_like_byu(fall):
    """Scheduled presence by building and block (over the week) against the package's occupancy (scaled to the simulated
    students): the same buildings are busy at the same times."""
    ac, P = fall.systems["academics"], fall.w.P
    byu = np.flatnonzero(ac.sec_school == 1)
    held = ac.stu_secs[: P.n]
    size = np.bincount(held[held >= 0], minlength=len(ac.sec_school))[byu]
    code = np.array([w.split(" ")[0] for w in ac.sec_where[byu]])
    rows = []
    for wd in range(5):
        meets = ((ac.sec_days[byu] >> wd) & 1).astype(bool)
        for b in range(clock.N_PARTS):          # the package's occupancy is by part of the day
            s0, e0 = ac.sec_start[byu].astype(np.int32), ac.sec_end[byu].astype(np.int32)
            ov = np.clip(np.minimum(e0, clock.PART_END[b]) - np.maximum(s0, clock.PART_START[b]), 0, None)
            v = size * ov * meets / (clock.PART_END[b] - clock.PART_START[b])
            rows += [(c, wd, b, float(v[code == c].sum())) for c in np.unique(code)]
    sim_ = pl.DataFrame(rows, schema=["building", "wd", "block", "sim"], orient="row")
    occ = schedule.occupancy().filter((pl.col("term") == "Fall") & (pl.col("wd") < 5)).with_columns(
        pl.col("wd").cast(pl.Int64), pl.col("block").cast(pl.Int64))
    J = (occ.join(sim_, on=["building", "wd", "block"], how="full", coalesce=True).fill_null(0)
         .group_by("building", "block").agg(pl.col("people").sum(), pl.col("sim").sum()))   # the week, per block
    n = int(((P["school"][: P.n] == 1) & P["enrolled"][: P.n]).sum())
    exp = J["people"].to_numpy() * n / 37874              # BYU's Fall 2026 daytime students (the package's README)
    assert np.corrcoef(exp, J["sim"].to_numpy())[0, 1] > 0.8
    assert 0.7 < J["sim"].sum() / exp.sum() < 1.15


def test_dots_in_real_rooms():
    """On the first day of Fall classes, people in class are drawn in their real room's building, on its floor."""
    s = new_simulation(scale=0.05, seed=5)
    while not (s.cal.term("BYU", s.w.day) and s.cal.weekday(s.w.day) < 5 and not s.cal.holiday(s.w.day)):
        s.run_days(1)
    ac = s.systems["academics"]
    assert (ac.sec_start[ac.sec_school == 1] >= 0).all()          # the term began with the real schedule
    s.advance_hours(4)
    rep = sync_check.check(s)
    cls = [r for r in rep["rows"] if r["place"] == "class"]
    assert cls and cls[0]["people"] > 0
    assert cls[0]["in_building"] > 0.98 and cls[0]["floor_ok"] > 0.98, sync_check.table(rep)
    from ucsim.analysis.now import _place_words
    from ucsim.engine import placement
    from ucsim.engine.state import CTX_ID
    f = s.systems["activity"].snapshot
    i = np.flatnonzero((f["ctype"] == CTX_ID["class"]) & f["present"])
    words = _place_words(s, f, placement.place(s, f), int(i[0]))
    assert words["course"] and words["words"].startswith(words["course"] + " class in ")
