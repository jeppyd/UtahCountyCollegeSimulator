"""Real-world grounding and the newer systems: majors, physical traits, class mix, housing rules,
neighborhoods, clubs/teams/institute, history snapshots, flows and transition filters."""
import numpy as np
import pytest

from ucsim.analysis.query import evaluate_filter
from ucsim.engine.state import CTX_ID, Tie
from ucsim.geo import neighborhoods
from ucsim.population import majors


def test_majors_catalog_is_real_and_school_specific(fresh):
    cat = majors.catalog()
    byu = [m for m in cat if m["school"] == "BYU"]
    uvu = [m for m in cat if m["school"] == "UVU"]
    assert len(byu) > 100 and len(uvu) > 100
    assert any(m["major"] == "Neuroscience" for m in byu)
    P = fresh.w.P
    for s, pool in ((1, byu), (2, uvu)):
        stu = np.where(P["enrolled"] & (P["school"] == s))[0]
        mid = P["major_id"][stu]
        assert (mid >= 0).mean() > 0.95
        assert {cat[int(m)]["school"] for m in mid if m >= 0} == {pool[0]["school"]}
    never_student = ~P.isin("role", ["byu_student", "uvu_student"])
    assert (P["major_id"][never_student] == -1).all()     # (missionaries and students on break keep their major)


def test_physical_traits_are_plausible(fresh):
    P = fresh.w.P
    pres = P["present"] & (P["age"] >= 18)
    for sex, (h_lo, h_hi), (w_lo, w_hi) in (("F", (63.5, 67), (125, 165)), ("M", (68.5, 72.5), (155, 200))):
        m = pres & P.is_("sex", sex)
        assert h_lo < np.median(P["height_in"][m]) < h_hi
        assert w_lo < np.median(P["weight_lb"][m]) < w_hi
    assert 16 <= P["bmi"][pres].min() and P["bmi"][pres].max() <= 52
    assert len(np.unique(P["hair_color"][pres])) >= 4


def test_class_mix_matches_published_shape(fresh):
    P = fresh.w.P
    byu = P["enrolled"] & (P["school"] == 1)
    share = lambda c: P.is_("class_standing", c)[byu].mean()  # noqa: E731
    assert abs(share("freshman") - 0.17) < 0.05
    assert share("senior") > share("freshman")


def test_contracted_rule_covers_first_years_only(fresh):
    P = fresh.w.P
    byu_single = P["enrolled"] & (P["school"] == 1) & ~P.is_("rel_status", "married")
    fresh_ = byu_single & P.is_("class_standing", "freshman")
    compliant = P.isin("living", ["dorm", "contracted", "with_parents"])
    assert compliant[fresh_].mean() > 0.85
    assert compliant[byu_single & ~fresh_].mean() < 0.5      # upperclassmen choose freely
    assert fresh.w.env["contracted_housing_required"] and not fresh.w.env["contracted_housing_all_years"]


def test_neighborhoods_locate_known_places(fresh):
    names = ["Other"] + [r["name"] for r in neighborhoods.load()]
    assert len(names) > 50
    code = neighborhoods.locate([-111.6493, -111.7129, -111.50], [40.2500, 40.2773, 40.00])
    assert names[code[2]] == "Other"
    assert code[0] > 0 and code[1] > 0
    P = fresh.w.P
    byu = P["enrolled"] & (P["school"] == 1)
    top = np.bincount(P["neighborhood"][byu]).argmax()
    assert names[top] in ("Joaquin", "University")      # the classic BYU student neighborhoods


def test_groups_meet_and_make_ties(ran):
    P, G, E = ran.w.P, ran.w.groups, ran.w.E
    assert {"club", "team", "institute"} <= set(G["kind"])
    stu = P["enrolled"] & P["present"]
    assert 0.1 < (P["club_id"][stu] >= 0).mean() < 0.6
    assert (P["institute_class"][P["enrolled"] & (P["school"] == 1)] < 0).all()   # BYU students take religion on campus
    assert (P["n_groups"] == (P["club_id"] >= 0).astype(int) + (P["team_id"] >= 0) + (P["institute_class"] >= 0)).all()
    met = np.isin(E["origin_ctx"], [CTX_ID["club"], CTX_ID["team"], CTX_ID["institute"]])
    assert met.sum() > 0
    assert ((E["flags"][met] & (Tie.CLUBMATE | Tie.TEAMMATE | Tie.INSTITUTE)) > 0).all()


def test_history_flows_and_transition_filter(ran):
    H = ran.systems["history"]
    days = H.days()
    assert days[0] == 0 and len(days) >= 2
    x0, pres0 = H.values("rel_status", 0)
    assert pres0.sum() > 0 and (x0[~pres0] == 255).all()
    lo, _ = H.values("loneliness", days[-1])
    assert np.isfinite(lo[ran.w.P["present"][: len(lo)]]).mean() > 0.9
    P = ran.w.P
    filt = {"transition": {"var": "rel_status", "from": ["single", "talking"], "to": ["dating", "engaged"], "d0": 0, "d1": ran.w.day}}
    m = evaluate_filter(ran.w, filt, ran)
    if m.any():
        assert P.isin("rel_status", ["dating", "engaged"])[m].all()
        assert np.isin(x0[np.where(m)[0]], [P.code("rel_status", "single"), P.code("rel_status", "talking")]).all()


@pytest.fixture(scope="module")
def api(ran):
    from fastapi.testclient import TestClient
    from ucsim.api import server
    server.WS.set_base(ran) if hasattr(server.WS, "set_base") else setattr(server.WS, "base", ran)
    return TestClient(server.app)


def test_flow_and_network_endpoints(api, ran):
    r = api.post("/api/flows", json={"var": "rel_status", "days": [0, ran.w.day]}).json()
    assert len(r["columns"]) == 2
    assert sum(lk["n"] for lk in r["links"]) == r["total"]
    assert api.post("/api/cohort_timeline", json={"vars": ["loneliness"]}).status_code == 200
    g = api.get("/api/network/sample", params={"tie": "roommate", "min_stage": 1, "max_nodes": 300}).json()
    E = ran.w.E
    assert g["nodes"] is not None and ((E["flags"] & Tie.ROOMMATE) > 0).any()
    pj = api.get(f"/api/person/{int(np.where(ran.w.P['n_groups'] > 0)[0][0])}").json()
    assert pj["groups"] and pj["looks"]["height_in"] > 0
