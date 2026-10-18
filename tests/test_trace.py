"""Trace: graphs of causes and consequences around one item, their caps, and the population view of chains."""
import json

import numpy as np
import pytest
from provworld import world

from ucsim.analysis import trace as T


@pytest.fixture(scope="module")
def sim():
    return world()


def _last(sim, etype):
    m = np.flatnonzero(sim.log["type"] == sim.reg.event_ids[etype])
    return int(m[-1]) if len(m) else None


def _check_shape(g):
    keys = {n["key"] for n in g["nodes"]}
    assert g["root"] in keys
    for n in g["nodes"]:
        assert {"key", "kind", "ref", "day", "people", "label", "weight", "depth", "more_back", "more_fwd"} <= set(n)
        assert isinstance(n["label"], str) and n["label"]
        assert n["day"] is not None
    for L in g["links"]:
        assert L["source"] in keys and L["target"] in keys and L["source"] != L["target"]
        assert L["kind"] in T.LINK_KINDS
        assert isinstance(L["words"], str)
    lane_ids = [l["id"] for l in g["lanes"]]
    assert len(lane_ids) == len(set(lane_ids))
    assert g["range"][0] <= g["range"][1]


def test_event_trace_back_and_forward(sim):
    e = _last(sim, "breakup_received") or _last(sim, "rejected")
    g = T.trace(sim, f"event:{e}", "both", 3)
    _check_shape(g)
    root = next(n for n in g["nodes"] if n["key"] == g["root"])
    assert root["depth"] == 0 and root["ref"] == {"kind": "event", "id": e}
    # the root's people are the first lanes, by name
    assert g["lanes"][0]["id"] in root["people"] and g["lanes"][0]["name"]
    back = T.trace(sim, f"event:{e}", "back", 3)
    assert all(n["depth"] <= 0 for n in back["nodes"])
    assert any(L["target"] == back["root"] for L in back["links"])
    fwd = T.trace(sim, f"event:{e}", "fwd", 3)
    assert all(n["depth"] >= 0 for n in fwd["nodes"])
    # events and decisions are resolved per block or per day: no clock time is claimed for them
    assert all(n["minute"] is None for n in g["nodes"] if n["kind"] in ("event", "decision"))


def test_words_read_as_plain_language(sim):
    assert T.lc("Whether to ask them out") == "whether to ask them out"
    assert T.lc("GPA") == "GPA" and T.lc("When a stay in Provo–Orem ends") == "when a stay in Provo–Orem ends"
    assert T.positive_outcome({"outcomes": ["yes", "no"]}, "no") == "yes"
    assert T.positive_outcome({"outcomes": ["coffee", "alcohol"], "positive": "any"}, "alcohol") == "alcohol"
    # chains: each reason's examples say who chose, about whom, and their own top reason
    c = T.chains(sim, 0, sim.w.day)
    ex = [x for r in c["reasons"] for x in r["examples"]]
    assert ex and all(isinstance(x["who"], str) and x["who"] and "id" in x and "day" in x for x in ex)
    assert all(sim.decisions.get(x["id"]) for x in ex[:20])


def test_depth_grows_the_graph_and_bounds_distance(sim):
    e = _last(sim, "first_date")
    sizes = []
    for d in (1, 2, 4):
        g = T.trace(sim, f"event:{e}", "back", d)
        sizes.append(len(g["nodes"]))
        assert all(-d <= n["depth"] <= 0 for n in g["nodes"])
    assert sizes == sorted(sizes) and sizes[-1] > 1


def test_caps_say_what_was_cut(sim):
    e = _last(sim, "new_friend")
    big = T.trace(sim, f"event:{e}", "both", 4, max_nodes=200)
    small = T.trace(sim, f"event:{e}", "both", 4, max_nodes=6)
    assert len(small["nodes"]) <= 6
    if len(big["nodes"]) > 6:
        c = small["cut"]
        assert c["cap_hits"] > 0 or c["back"] + c["fwd"] > 0
        assert any("Not shown" in s for s in small["notes"])
    narrow = T.trace(sim, f"event:{e}", "fwd", 2, fanout=1)
    for n in narrow["nodes"]:
        out = [L for L in narrow["links"] if L["source"] == n["key"]]
        assert len(out) <= 1 + 1        # one consequence per item (a merged two-way link may add one)


def test_decision_trace_and_detail(sim):
    D = sim.decisions
    did = int(D.t["id"][D.t["kind"] == D.kind_id["accept_date"]][-1])
    g = T.trace(sim, f"decision:{did}", "both", 2)
    _check_shape(g)
    root = next(n for n in g["nodes"] if n["key"] == g["root"])
    assert root["kind"] == "decision" and root["detail"]["factors"]
    d = T.decision_detail(sim, did)
    assert d["label"] and d["outcome"] in ("yes", "no") and 0 < d["prob"] <= 1
    assert d["agent_name"] and d["other_name"]
    assert all(f["words"] for f in d["factors"])
    assert T.decision_detail(sim, 10**9) == {}
    # time runs one way: being asked out comes before the answer, and the answer before what it led to
    back = {L["source"]: L for L in g["links"] if L["target"] == g["root"]}
    asks = [k for k in back if k.startswith("event:")
            and sim.reg.event_names[sim.log["type"][int(k.split(":")[1])]] == "asked_out"]
    assert asks and back[asks[0]]["kind"] == "caused"
    assert not any(L["source"] == g["root"] and L["target"] == asks[0] for L in g["links"])
    ga = T.trace(sim, asks[0], "both", 1)
    assert any(L["source"] == asks[0] and L["target"] == g["root"] for L in ga["links"])


def test_other_refs(sim):
    E = sim.w.E
    lo, hi = E.endpoints()
    k = int(np.argmax(E["hours"]))
    for ref in (f"person:{int(lo[k])}", f"tie:{int(hi[k])}-{int(lo[k])}", f"var:loneliness@{int(lo[k])}",
                "place:complex:" + str(int(sim.w.P["complex_id"][lo[k]]))):
        g = T.trace(sim, ref, "both", 2)
        _check_shape(g)
    g = T.trace(sim, f"person:{int(lo[k])}", "both", 2)
    assert len(g["nodes"]) > 1 and g["lanes"][0]["id"] == int(lo[k])
    with pytest.raises(ValueError):
        T.parse_ref("nonsense:1")
    with pytest.raises(KeyError):
        T.trace(sim, f"event:{10**9}")


def test_feeling_trace_uses_todays_decomposition(sim):
    i = int(np.argmax(sim.w.P["loneliness"] * sim.w.P["present"]))
    g = T.trace(sim, f"var:loneliness@{i}", "back", 1)
    root = next(n for n in g["nodes"] if n["key"] == g["root"])
    assert root["detail"]["asof"] == sim.w.day and root["detail"]["decomposition"]
    assert all(L["kind"] == "contributed" for L in g["links"])


def test_person_decisions(sim):
    D = sim.decisions
    i = int(np.bincount(D.t["agent"]).argmax())
    rows = T.person_decisions(sim, i)
    assert rows and all(r["label"] and r["outcome"] for r in rows)
    assert rows == sorted(rows, key=lambda r: -r["id"])


def test_chains_flows_and_reasons(sim):
    c = T.chains(sim, 0, sim.w.day)
    assert c["events"] > 1000 and c["links"] and c["reasons"]
    ids = {n["id"] for n in c["nodes"]}
    for L in c["links"]:
        assert L["source"] in ids and L["target"] in ids and L["value"] > 0
        assert L["source"].endswith("|from") and L["target"].endswith("|to")
        for ex in L["examples"]:
            assert ex["label"] and 0 <= ex["event"] < sim.log.n
    # repeats (one date to the next) are hidden unless asked for
    assert all(L["source"].split("|")[0] != L["target"].split("|")[0] for L in c["links"])
    r = c["reasons"][0]
    assert r["sentence"].startswith("Of ") and sum(t["share"] for t in r["top"]) <= 1.0001
    # a root centers the flows on one kind of event
    root = "rejected"
    rc = T.chains(sim, 0, sim.w.day, root=root)
    assert rc["links"] and all(f"event:{root}|root" in (L["source"], L["target"]) for L in rc["links"])
    # a cohort narrows the counts
    people = np.flatnonzero(sim.w.P["sex"] == sim.w.P.code("sex", "F"))
    cc = T.chains(sim, 0, sim.w.day, people=people)
    assert 0 < cc["events"] < c["events"]


def test_where_they_met_sits_before_what_it_led_to(sim):
    rows = np.flatnonzero(sim.log["type"] == sim.reg.event_ids["new_friend"])[-30:]
    seen = 0
    for e in rows:
        g = T.trace(sim, f"event:{int(e)}", "back", 2)
        day = {n["key"]: n["day"] for n in g["nodes"]}
        for L in g["links"]:
            if L["kind"] == "met_at" and L["source"].startswith("place:"):
                assert day[L["source"]] <= day[L["target"]]
                seen += 1
    assert seen


def test_chains_show_where_friends_met_and_the_feelings_behind_coping(sim):
    c = T.chains(sim, 0, sim.w.day, root="new_friend", max_links=200)
    met = [L for L in c["links"] if L["source"].startswith("place:") and L["kind"] == "met_at"]
    assert met and all(L["from_label"].startswith("Met ") and L["target"] == "event:new_friend|root" for L in met)
    # each example names the very place and opens a real friendship
    ex = met[0]["examples"][0]
    assert ex["from_label"] and sim.reg.event_names[sim.log["type"][ex["event"]]] == "new_friend"
    # the counts are the typed causes: no flow claims more friendships than were recorded with that kind of place
    n_new = int((sim.log["type"] == sim.reg.event_ids["new_friend"]).sum())
    assert sum(L["value"] for L in met) <= n_new
    cop = T.chains(sim, 0, sim.w.day, root="coping_started")
    feel = [L for L in cop["links"] if L["source"].startswith("state:")]
    assert feel and all(L["examples"][0]["from_label"].endswith(L["from_label"].lower()) for L in feel)
    # without contexts only events and decisions remain
    plain = T.chains(sim, 0, sim.w.day, root="coping_started", contexts=False)
    assert all(L["source"].split(":")[0] in ("event", "decision") for L in plain["links"])


def test_api(sim):
    from fastapi.testclient import TestClient
    from ucsim.api import server
    old = server.WS.base
    server.WS.base = sim
    try:
        _api_checks(TestClient(server.app), sim)
    finally:
        server.WS.base = old


def _api_checks(cl, sim):
    e = _last(sim, "asked_out")
    r = cl.get("/api/trace", params={"ref": f"event:{e}", "dir": "both", "depth": 2})
    assert r.status_code == 200 and r.json()["root"] == f"event:{e}"
    assert cl.get("/api/trace", params={"ref": "bogus"}).status_code == 400
    assert cl.get("/api/trace", params={"ref": f"event:{10**9}"}).status_code == 404
    r = cl.get("/api/trace/chains", params={"since": 0, "filter": json.dumps({"var": "sex", "op": "eq", "value": "F"})})
    assert r.status_code == 200 and r.json()["cohort"] > 0
    assert cl.get("/api/trace/chains", params={"root": "no_such_type"}).status_code == 404
    did = int(sim.log["decision"][e])
    r = cl.get(f"/api/decision/{did}")
    assert r.status_code == 200 and r.json()["kind"] == "ask_out"
    a = int(sim.log["a"][e])
    r = cl.get(f"/api/person/{a}/decisions", params={"since": 0})
    assert r.status_code == 200 and any(d["id"] == did for d in r.json()["decisions"])
