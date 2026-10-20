"""Campus policies: the sourced policy file, the BYU Honor Code (reports → decisions → standing, leaving BYU), the
ecclesiastical endorsement, the What-if switches and /api/policies."""
import copy

import numpy as np
import pytest
import yaml

from ucsim.api.routes_policies import POLICY_FILE
from ucsim.engine.runner import new_simulation


def test_policy_file_is_sourced():
    pol = yaml.safe_load(POLICY_FILE.read_text())["policies"]
    assert {p["school"] for p in pol} == {"BYU", "UVU"}
    for p in pol:
        assert p["source"].startswith("https://") and p["rules"] and p["status"] in ("modelled", "data", "not_binding")
        if p["status"] == "not_binding":
            assert p.get("notes")             # says why it never binds
    assert any(p["id"] == "byu_honor_code" and p["status"] == "modelled" for p in pol)


@pytest.fixture(scope="module")
def world():
    return new_simulation(scale=0.03, seed=3)


def _byu(sim):
    P = sim.w.P
    return np.flatnonzero((P["school"] == 1) & P.is_("role", "byu_student") & P["present"] & P["enrolled"])


def test_reports_decisions_and_leaving(world):
    sim = copy.deepcopy(world)
    P = sim.w.P
    ids = _byu(sim)
    assert (P["honor_standing"][ids] == P.code("honor_standing", "good")).all()
    P.cols["coffee"][ids] = 3
    P.cols["alcohol"][ids[: len(ids) // 3]] = 2
    sim.w.env["honor_enforcement"] = 40.0       # make violations surface quickly
    h = sim.systems["honor"]
    for _ in range(4):
        h.weekly()
        sim.w.day += 7
    assert h.reports > 0 and sum(h.outcomes.values()) == h.reports
    assert h.outcomes["warning"] > h.outcomes["suspension"]
    st = P["honor_standing"][ids]
    assert (st == P.code("honor_standing", "warned")).any() and (st == P.code("honor_standing", "probation")).any()
    assert (P["honor_reports"][ids] > 0).any()
    # many quit after a report
    assert (P["coffee"][ids] == 0).sum() > 0
    # anyone suspended left BYU: to UVU (a UVU student now) or out of school
    gone = ids[np.isin(st, [P.code("honor_standing", "suspended"), P.code("honor_standing", "dismissed")])]
    assert not P["enrolled"][gone].any()
    assert np.isin(P["role"][gone], [P.code("role", "uvu_student"), P.code("role", "young_adult")]).all()
    # every outcome is a recorded decision with its factors
    d = sim.decisions.t
    assert (d["kind"][: d.n] == sim.decisions.kind_id["honor_outcome"]).sum() == h.reports


def test_not_enforced_means_no_reports(world):
    sim = copy.deepcopy(world)
    P = sim.w.P
    P.cols["coffee"][_byu(sim)] = 3
    sim.w.env["honor_enforcement"] = 0.0
    h = sim.systems["honor"]
    h.weekly()
    assert h.reports == 0


def test_endorsement_withdrawn_at_renewal_and_no_enrollment(world):
    sim = copy.deepcopy(world)
    P, p = sim.w.P, sim.p
    ids = _byu(sim)
    lds = ids[P["lds_member"][ids]][:20]
    P.cols["activity"][lds] = P.code("activity", "inactive")
    sim.p.set("honor.endorsement.decline_inactive", 1.0)
    # a year of day hooks: each renews on their own date, and the next term start turns the withdrawn away
    h = sim.systems["honor"]
    d0 = sim.w.day
    for d in range(d0, d0 + 400):
        sim.w.day = d
        h.daily()
    out = lds[P["endorsement"][lds] == 0]                    # withdrawn, then left (endorsement cleared to n/a)
    assert h.withdrawn > 0 and len(out) > 0
    assert not P["enrolled"][out].any()


def test_switch_off_endorsement(world):
    sim = copy.deepcopy(world)
    sim.w.env["endorsement_required"] = False
    for d in range(sim.w.day, sim.w.day + 400):
        sim.w.day = d
        sim.systems["honor"].daily()
    assert sim.systems["honor"].withdrawn == 0


def test_api(ran):
    from fastapi.testclient import TestClient
    from ucsim.api import server
    old = server.WS.base
    server.WS.base = ran
    try:
        r = TestClient(server.app).get("/api/policies").json()
        assert len(r["policies"]) >= 10 and r["live"]["byu_students"] > 0
        assert set(r["live"]["standing"]) >= {"good", "probation"} and r["switches"]["honor_enforcement"] == 1.0
    finally:
        server.WS.base = old
