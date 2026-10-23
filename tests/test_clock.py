"""The hour-by-hour day: clock helpers, phases, shifts with clock times, meeting times, routines and the day replay."""
import numpy as np
import pytest

from ucsim.engine import clock
from ucsim.engine.sim import Simulation
from ucsim.engine.state import CTX_ID


def test_hours_tile_the_day_from_6_am_to_6_am():
    assert clock.N_BLOCKS == 24 and clock.SLOTS_PER_WEEK == 168
    assert all(clock.END[b] == clock.START[b + 1] for b in range(clock.N_BLOCKS - 1))
    assert clock.DAY_START == 6 * 60 and clock.DAY_END == 30 * 60
    assert clock.HOUR.tolist() == [*range(6, 24), *range(0, 6)]
    # the parts of the day tile it too, and every hour belongs to one
    assert clock.PART_START[0] == clock.DAY_START and clock.PART_END[-1] == clock.DAY_END
    assert all(clock.PART_END[k] == clock.PART_START[k + 1] for k in range(clock.N_PARTS - 1))
    assert clock.PART.tolist() == [0] * 6 + [1] * 5 + [2] * 3 + [3] * 4 + [4] * 6
    # a day like the old ones (8 am to 11:30 pm in one place) adds up to the contact the rates were fitted to
    day = (clock.START >= 8 * 60) & (clock.END <= 23 * 60 + 30)
    assert clock.LEGACY_SHARE[day].sum() == pytest.approx(0.2 * 9.5 + 6 / 6, abs=0.1)
    assert clock.LEGACY_SHARE[3] == pytest.approx(0.2) and clock.LEGACY_SHARE[20] == pytest.approx(1 / 6)
    # each hour's phase runs at the start of its hour
    for b, h in enumerate(clock.BLOCK_HOUR):
        assert h * 60 == clock.START[b]


def test_clock_helpers():
    assert clock.parse_hhmm("19:30") == 1170 == clock.parse_hhmm("7:30 pm") == clock.parse_hhmm(1170)
    assert clock.parse_hhmm("12 am") == 0 and clock.parse_hhmm("12:15 pm") == 735
    assert clock.parse_hhmm("25:00") == 1500           # 1 am, written as the small hours of the day before
    with pytest.raises(ValueError):
        clock.parse_hhmm("31:00")
    assert clock.hhmm(1170) == "7:30 pm" and clock.hhmm(720) == "12 pm" and clock.hhmm(480) == "8 am"
    assert clock.hhmm(1500) == "1 am"
    assert clock.day_minute(60) == 1500 and clock.day_minute(420) == 420
    assert clock.block_of([6 * 60, 7 * 60 + 59, 12 * 60, 23 * 60 + 30, 60, 5 * 60 + 59]).tolist() == [0, 1, 6, 17, 19, 23]
    assert clock.part_of([7 * 60, 12 * 60, 17 * 60 + 30, 21 * 60, 2 * 60]).tolist() == [0, 1, 2, 3, 4]
    assert int(clock.overlap(19 * 60 + 30, 120, 13)) == 30 and int(clock.overlap(19 * 60 + 30, 120, 14)) == 60
    assert clock.main_blocks(19 * 60, 120) == [13, 14] and clock.main_blocks(19 * 60 + 10, 40, 30) == [13]
    assert int(clock.block_mask(19 * 60, 120)) == (1 << 13) | (1 << 14)
    assert clock.slot(6, 23) == 167 and clock.slot(0, 0) == 0


def test_phases_run_in_clock_order():
    names = [n for n, _ in Simulation.PHASES]
    hours = [h for _, h in Simulation.PHASES]
    assert names == ["start", *(f"block{b}" for b in range(24)), "end"]
    assert hours == sorted(hours) and hours[1:25] == list(clock.BLOCK_HOUR) and hours[-1] == 30


def test_shifts_have_clock_times_that_fit_around_classes(ran):
    P = ran.w.P
    act = ran.systems["activity"]
    s = P.internal["shift_start"][: P.n].astype(np.int32)
    e = P.internal["shift_end"][: P.n].astype(np.int32)
    has = (s >= 0) & P["employed"][:, None]
    assert has.any()
    assert (e[has] > s[has]).all() and (e[has] - s[has] >= 90).all() and (e[has] <= 23 * 60).all()
    stu = P["employed"] & P["enrolled"]
    assert (e[stu[:, None] & (s >= 0)] <= 22 * 60).all(), "students' shifts end by 10 pm"
    # a student's shift never overlaps one of their classes (15 minutes to get between them)
    acad = ran.systems["academics"]
    ids = np.where(stu & P["present"])[0][:300]
    secs = acad.stu_secs[ids]
    for wd in range(5):
        meets = (secs >= 0) & ((acad.sec_days[np.maximum(secs, 0)] >> wd) & 1).astype(bool)
        cs, ce = act.class_times(np.maximum(secs, 0))
        ss, se = s[ids, wd][:, None], e[ids, wd][:, None]
        clash = meets & (ss >= 0) & (cs < se + 15) & (ce + 15 > ss)
        assert not clash.any()
    # the weekdays a shift fills follow from its minutes
    i = int(np.where(has.any(axis=1))[0][0])
    m = int(P.internal["shift_mask"][i])
    for wd in range(7):
        assert bool(m >> wd & 1) == bool(has[i, wd])


def test_group_meetings_have_times_inside_their_blocks(ran):
    G = ran.w.groups
    grp = ran.systems["groups"]
    assert (G["start"] >= 12 * 60).all() and (G["start"] + G["dur"] <= 23 * 60).all()
    assert grp.meets_in.shape[1] == clock.N_BLOCKS and grp.meets_in.any(axis=1).all()
    assert (grp.meets_in.sum(axis=1) <= 2).all()


def test_24_frames_and_168_routine_slots(ran):
    act = ran.systems["activity"]
    fr = act.day_frames
    assert set(fr) == {"day", *range(clock.N_BLOCKS)}
    assert ran.systems["routine"].act.shape[1] == 168
    # time in a context is kept in old-block units (a share of the five-hour block it replaces)
    assert len(act.ctx_share) == len(act.ctype)
    assert act.ctx_share.min() >= 0 and act.ctx_share.max() <= 1.0 + 1e-6


def test_an_evening_hour_at_home_counts_its_share_of_the_old_evening(fresh):
    import copy
    sim = copy.deepcopy(fresh)
    sim.run_days(1)
    sim.advance_hours(14)          # 6 am → 8 pm: the 8 pm hour has just been chosen
    act = sim.systems["activity"]
    P = sim.w.P
    own = (act.ctype == CTX_ID["unit"]) & (act.cid == P["unit_id"]) & P["present"]
    assert own.any()
    assert np.allclose(act.ctx_share[own], clock.LEGACY_SHARE[14])


def test_day_replay_endpoint_serves_24_frames(ran):
    from fastapi.testclient import TestClient
    from ucsim.api import server
    keep = server.WS.base, server.WS.alt
    try:
        server.WS.base, server.WS.alt = ran, None
        r = TestClient(server.app).get("/api/positions/day")
        assert r.status_code == 200 and b"lon23" in r.content and b"act23" in r.content
    finally:
        server.WS.base, server.WS.alt = keep
