"""The four-block day: clock helpers, phases, shifts with clock times, meeting times, routines and the day replay."""
import numpy as np
import pytest

from ucsim.engine import clock
from ucsim.engine.sim import Simulation
from ucsim.engine.state import CTX_ID


def test_blocks_tile_the_day_and_split_the_old_evening():
    assert clock.N_BLOCKS == 4 and clock.SLOTS_PER_WEEK == 28
    assert all(clock.END[b] == clock.START[b + 1] for b in range(clock.N_BLOCKS - 1))
    assert clock.DAY_START == 8 * 60 and clock.DAY_END == 23 * 60 + 30
    # a whole evening in one place adds up to exactly one old five-hour evening of ambient exposure
    assert clock.LEGACY_SHARE[list(clock.EVENING)].sum() == pytest.approx(1.0)
    assert clock.LEGACY_SHARE[1] == pytest.approx(1.0) and clock.LEGACY_SHARE[0] == pytest.approx(0.9)
    # each block's phase runs in its block (the clock steps whole hours, so the late block starts at the 8 pm tick)
    for b, h in enumerate(clock.BLOCK_HOUR):
        assert clock.START[b] - 60 < h * 60 < clock.END[b]


def test_clock_helpers():
    assert clock.parse_hhmm("19:30") == 1170 == clock.parse_hhmm("7:30 pm") == clock.parse_hhmm(1170)
    assert clock.parse_hhmm("12 am") == 0 and clock.parse_hhmm("12:15 pm") == 735
    with pytest.raises(ValueError):
        clock.parse_hhmm("25:00")
    assert clock.hhmm(1170) == "7:30 pm" and clock.hhmm(720) == "12 pm" and clock.hhmm(480) == "8 am"
    assert clock.block_of([7 * 60, 8 * 60, 12 * 60 + 29, 12 * 60 + 30, 20 * 60 + 14, 20 * 60 + 15, 23 * 60 + 30]).tolist() == \
        [-1, 0, 0, 1, 2, 3, -1]
    assert int(clock.overlap(19 * 60, 120, 2)) == 75 and int(clock.overlap(19 * 60, 120, 3)) == 45
    assert clock.main_blocks(19 * 60, 120) == [2, 3] and clock.main_blocks(19 * 60, 90, 30) == [2]
    assert clock.slot(6, 3) == 27 and clock.slot(0, 0) == 0


def test_phases_run_in_clock_order():
    names = [n for n, _ in Simulation.PHASES]
    hours = [h for _, h in Simulation.PHASES]
    assert names == ["start", "block0", "block1", "block2", "block3", "end"]
    assert hours == sorted(hours) and hours[1:5] == list(clock.BLOCK_HOUR)


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
    # the blocks a shift fills follow from its minutes
    i = int(np.where(has.any(axis=1))[0][0])
    wd = int(np.where(has[i])[0][0])
    m = int(P.internal["shift_mask"][i])
    for b in range(clock.N_BLOCKS):
        mins = int(clock.overlap(s[i, wd], e[i, wd] - s[i, wd], b))
        filled = mins >= min(120, 0.5 * (clock.END[b] - clock.START[b]))
        assert bool(m >> int(clock.slot(wd, b)) & 1) == filled


def test_group_meetings_have_times_inside_their_blocks(ran):
    G = ran.w.groups
    grp = ran.systems["groups"]
    assert (G["start"] >= 12 * 60).all() and (G["start"] + G["dur"] <= 23 * 60).all()
    assert grp.meets_in.shape[1] == clock.N_BLOCKS and grp.meets_in.any(axis=1).all()
    assert (grp.meets_in.sum(axis=1) <= 2).all()


def test_four_frames_and_a_night_and_28_routine_slots(ran):
    act = ran.systems["activity"]
    fr = act.day_frames
    assert set(fr) == {"day", *range(clock.N_BLOCKS + 1)}
    assert ran.systems["routine"].act.shape[1] == 28
    # time in a context is kept in old-block units (a share of the five-hour block it replaces)
    assert len(act.ctx_share) == len(act.ctype)
    assert act.ctx_share.min() >= 0 and act.ctx_share.max() <= 1.0 + 1e-6


def test_late_evening_at_home_counts_its_share_of_the_old_evening(fresh):
    import copy
    sim = copy.deepcopy(fresh)
    sim.run_days(1)
    sim.advance_hours(14)          # 6 am → 8 pm: the late-evening block has just been chosen
    act = sim.systems["activity"]
    P = sim.w.P
    own = (act.ctype == CTX_ID["unit"]) & (act.cid == P["unit_id"]) & P["present"]
    assert own.any()
    assert np.allclose(act.ctx_share[own], clock.LEGACY_SHARE[3])


def test_day_replay_endpoint_serves_five_frames(ran):
    from fastapi.testclient import TestClient
    from ucsim.api import server
    keep = server.WS.base, server.WS.alt
    try:
        server.WS.base, server.WS.alt = ran, None
        r = TestClient(server.app).get("/api/positions/day")
        assert r.status_code == 200 and b"lon4" in r.content and b"act3" in r.content
    finally:
        server.WS.base, server.WS.alt = keep
