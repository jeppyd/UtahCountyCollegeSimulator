"""Family and home states (engine/systems/family.py): home states follow where people are from, holidays empty
Provo and fill it again, trips are recorded with reasons, family events pull people home, the API, determinism."""
import copy
import datetime as dt

import numpy as np
from fastapi.testclient import TestClient

from ucsim.api import server
from ucsim.engine.runner import new_simulation
from ucsim.engine.systems.family import REASON_ID


def test_home_states_follow_origin(fresh):
    P = fresh.w.P
    pres = P["present"].astype(bool)
    st = P.labels("home_state", P["home_state"][pres])
    reg = P.labels("origin_region", P["origin_region"][pres])
    assert (st[reg == "Utah"] == "Utah").all()
    west = st[reg == "West Coast"]
    vals, cnt = np.unique(west, return_counts=True)
    assert vals[np.argmax(cnt)] == "California"
    assert (st[reg == "International"] == "International").all()
    far = P["home_drive_hours"][pres][st == "Florida"]
    assert len(far) == 0 or far.min() > 20


def _day_of(sim, d: dt.date) -> int:
    return (d - sim.cal.date(0)).days


def test_thanksgiving_exodus_and_return(fresh):
    sim = copy.deepcopy(fresh)
    F, P = sim.systems["family"], sim.w.P
    d0 = _day_of(sim, dt.date(2026, 11, 25))
    stu = np.flatnonzero(P["present"].astype(bool) & P["enrolled"])
    F._holiday(d0)
    away = P.internal["trip_away"][stu]
    assert 0.3 < away.mean() < 0.85
    assert not P["present"][stu[away]].any()
    T = F.trips
    assert (T["reason"] == REASON_ID["thanksgiving"]).sum() >= away.sum() * 0.9
    ret = int(T["ret"][T["reason"] == REASON_ID["thanksgiving"]].max())
    F._returns(ret)
    assert not P.internal["trip_away"].any() and P["present"][stu].all()
    D = sim.decisions
    rows = D.t["kind"][: D.t.n] == D.kind_id["trip_home"]
    far = (P["home_drive_hours"][stu] > 0.6) & (P["age"][stu] < 40)   # family in Utah County is home already
    assert rows.sum() >= far.sum() * 0.95                  # everyone else decided (went or stayed)


def test_family_events_pull_people_home(fresh):
    sim = copy.deepcopy(fresh)
    F, P = sim.systems["family"], sim.w.P
    who = np.flatnonzero(P["present"].astype(bool) & (P["home_drive_hours"] > 1) & (P["home_drive_hours"] < 6))[:30]
    ev = sim.emit("parent_ill", who, mech="family.kin")
    P.internal["kin_pull"][who] = ev
    P.internal["kin_pull_day"][who] = sim.w.day
    F._pulled(sim.w.day)
    went = F.trips["person"][F.trips["reason"] == REASON_ID["illness"]]
    assert len(went) > 5 and np.isin(went, who).all()


def test_trips_in_a_run_keep_chats(ran):
    F = ran.systems["family"]
    assert F.trips.n > 0 and (F.trips["reason"] == REASON_ID["weekend"]).any()
    M = ran.systems["messaging"]
    fam = M.threads["kind"] == 5
    assert fam.any()


def test_api(ran):
    saved = server.WS.base
    server.WS.base = ran
    try:
        c = TestClient(server.app)
        s = c.get("/api/family/states").json()
        assert s["total"] > 0 and any(r["state"] == "Utah" for r in s["states"])
        r = c.get("/api/family/state/Utah").json()
        assert r["n"] > 0
        p = c.get(f"/api/family/person/{r['people'][0]}").json()
        assert p["home_state"] == "Utah" and p["kin"]
    finally:
        server.WS.base = saved


def test_family_is_deterministic():
    out = []
    for _ in range(2):
        sim = new_simulation(scale=0.02, seed=8)
        sim.run_days(12)
        F = sim.systems["family"]
        out.append((sim.w.P["home_state"].copy(), F.trips["person"].copy(), F.kin["age"].copy()))
    for x, y in zip(*out):
        assert np.array_equal(x, y)
