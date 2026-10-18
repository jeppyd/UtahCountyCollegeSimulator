"""Scales: every numeric field has readable anchors inside its range, and /api/scales reports sensible live quantiles."""
import json

import numpy as np
import pytest

from ucsim.registry import get_registry
from ucsim.scales import BASIS_WORDS, EDGE_SCALES, distribution, percentile_of, scale_for, scale_of

UI_TIE_FIELDS = ["closeness", "liking", "trust", "attraction_lh", "belief_lh", "disclosure", "support", "hurt"]


def _numeric_person_fields():
    reg = get_registry()
    skip = {"home_lon", "home_lat", "loc_lon", "loc_lat", "institute_class"}
    return [v for v in reg.person_vars() if v.dtype not in ("bool", "cat", "str") and not v.categories and v.range
            and not v.id.endswith(("_id", "_day", "_until")) and v.id not in skip]


def _check(key, sc):
    a = sc["anchors"]
    assert 3 <= len(a) <= 7, (key, len(a))
    ats = [x["at"] for x in a]
    assert all(x < y for x, y in zip(ats, ats[1:])), (key, ats)
    assert sc["min"] <= ats[0] and ats[-1] <= sc["max"], (key, ats, sc["min"], sc["max"])
    if sc.get("view"):
        lo, hi = sc["view"]
        assert sc["min"] <= lo < hi <= sc["max"] and lo <= ats[0] and ats[-1] <= hi, (key, sc["view"], ats)
    for x in a:
        assert x["label"] and len(x["label"]) <= 40 and "_" not in x["label"], (key, x)
    assert sc["unit"] and "_" not in sc["unit"], key
    assert sc["how"] and sc["how"].endswith(".") and len(sc["how"]) < 400 and "Tracked by the model" not in sc["how"], (key, sc["how"])
    assert sc["basis"] in BASIS_WORDS, key
    assert sc["low"] == a[0]["label"] and sc["high"] == a[-1]["label"], key


def test_every_numeric_person_field_has_ordered_anchors_in_range():
    fields = _numeric_person_fields()
    assert len(fields) > 150
    for v in fields:
        sc = scale_of(v)
        assert sc is not None, v.id
        _check(v.id, sc)


def test_survey_answers_percent_and_standard_scores():
    reg = get_registry()
    picky = scale_of(reg.variables["picky"])
    assert picky["levels"][0] == "strongly disagree" and picky["basis"] == "survey" and len(picky["anchors"]) == 5
    assert "Dating survey" in picky["how"]
    att = scale_of(reg.variables["attend_rate"])
    assert att["percent"] and att["anchors"][-1]["label"] == "every Sunday"
    ext = scale_of(reg.variables["extraversion"])
    assert ext["z"] and [a["at"] for a in ext["anchors"]] == [-2, -1, 0, 1, 2] and ext["anchors"][-1]["label"] == "very outgoing"
    lone = scale_of(reg.variables["loneliness"])
    assert lone["anchors"][2]["label"] == "often lonely" and lone["basis"] == "guide" and "need" in lone["how"]
    inc = scale_of(reg.variables["parent_income"])          # long answer lists keep every level, a few anchors
    assert len(inc["levels"]) == 12 and len(inc["anchors"]) == 5
    sav = scale_of(reg.variables["savings"])
    assert sav["axis"] == "log" and sav["view"][0] < 0 < sav["view"][1]


def test_tie_fields_shown_in_the_ui_have_scales():
    reg = get_registry()
    for f in UI_TIE_FIELDS:
        v = reg.variables[f"edge.{f}"]
        sc = scale_for(v)
        assert sc is not None, f
        _check(f, sc)
        assert reg.variables[f"edge.{f}"].to_dict()["scale"]["anchors"] == sc["anchors"]
    assert set(EDGE_SCALES) >= {"closeness", "liking", "trust", "attraction", "belief", "disclosure", "support", "hurt"}


def test_distribution_and_percentile_math():
    rng = np.random.default_rng(0)
    x = rng.random(5000)
    d = distribution(x, {"min": 0, "max": 1})
    assert abs(d["p50"] - 0.5) < 0.03 and abs(d["p10"] - 0.1) < 0.02 and d["n"] == 5000 and len(d["q"]) == 101
    assert sum(d["hist"]["counts"]) == 5000 and len(d["hist"]["edges"]) == 21 and "values" not in d
    p = percentile_of(x, 0.78)
    assert abs(p["below"] - 0.78) < 0.02 and p["equal"] == 0
    k = np.r_[np.zeros(60), np.ones(30), np.full(10, 4.0)]          # a survey item: few whole-number answers
    dk = distribution(k, {"min": 0, "max": 4})
    assert dk["values"] == [[0.0, 0.6], [1.0, 0.3], [4.0, 0.1]]
    pk = percentile_of(k, 1)
    assert pk["below"] == 0.6 and pk["equal"] == 0.3 and pk["pct"] == 0.75
    # a log axis puts bin edges at growing steps and counts values beyond the view in the end bins
    m = np.r_[np.zeros(10), rng.lognormal(7, 1, 990)]
    dm = distribution(m, {"min": 0, "max": 20000, "view": [0, 5000], "axis": "log", "log_c": 300})
    e = dm["hist"]["edges"]
    assert e[0] == 0 and abs(e[-1] - 5000) < 1 and (e[2] - e[1]) < (e[-1] - e[-2])
    assert sum(dm["hist"]["counts"]) == 1000 and dm["hist"]["above"] == int((m > 5000).sum())


@pytest.fixture(scope="module")
def client(ran):
    from fastapi.testclient import TestClient

    from ucsim.api import server
    keep = server.WS.base, server.WS.alt
    server.WS.base, server.WS.alt = ran, None
    yield TestClient(server.app)
    server.WS.base, server.WS.alt = keep


def test_scales_endpoint_quantiles(client, ran):
    r = client.get("/api/scales?vars=loneliness,picky,n_friends,edge.closeness,edge.attraction_lh")
    assert r.status_code == 200, r.text
    d = r.json()
    P = ran.w.P
    pres = P["present"].astype(bool)
    assert d["n"] == int(pres.sum()) and d["cohort"] == "everyone present"
    lone = d["fields"]["loneliness"]
    q = lone["dist"]
    assert lone["scale"]["anchors"][0]["label"] == "not lonely"
    assert 0 <= q["p10"] <= q["p25"] <= q["p50"] <= q["p75"] <= q["p90"] <= 1
    assert abs(q["p50"] - float(np.median(P["loneliness"][pres]))) < 1e-3
    assert q["n"] == int(pres.sum()) and len(q["hist"]["counts"]) == 20 and sum(q["hist"]["counts"]) == q["n"]
    assert "values" in d["fields"]["picky"]["dist"]                      # survey answers: shares by answer
    clo = d["fields"]["edge.closeness"]
    assert clo["dist"]["n"] > 0 and 0 <= clo["dist"]["p50"] <= 1 and clo["among"].startswith("ties")
    att = d["fields"]["edge.attraction_lh"]["dist"]
    assert -1 <= att["p10"] <= att["p90"] <= 1


def test_scales_endpoint_cohort_and_all_fields(client, ran):
    f = json.dumps({"var": "sex", "op": "eq", "value": "F"})
    d = client.get(f"/api/scales?vars=mood&filter={f}").json()
    P = ran.w.P
    women = P["present"].astype(bool) & P.is_("sex", "F")
    assert d["n"] == int(women.sum()) and d["fields"]["mood"]["dist"]["n"] == int(women.sum())
    every = client.get("/api/scales?dist=false").json()
    assert len(every["fields"]) > 150 and all(r["scale"] for r in every["fields"].values())
    assert client.get("/api/scales?vars=no_such_field").status_code == 404
    assert client.get("/api/scales?vars=mood&filter={bad").status_code == 400


def test_scale_value_percentile(client, ran):
    P = ran.w.P
    pres = P["present"].astype(bool)
    x = P["loneliness"][pres]
    v = float(np.quantile(x, 0.78))
    d = client.get(f"/api/scales/value?var=loneliness&value={v}").json()
    assert abs(d["below"] - 0.78) < 0.02 and d["n"] == int(pres.sum()) and d["words"]
    i = int(np.flatnonzero(pres)[0])
    dp = client.get(f"/api/scales/value?var=loneliness&person={i}").json()
    assert abs(dp["value"] - float(P["loneliness"][i])) < 1e-6 and 0 <= dp["pct"] <= 1
    assert client.get("/api/scales/value?var=loneliness").status_code == 400
