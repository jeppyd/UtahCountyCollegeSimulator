"""Workbench endpoints: events and daily counts for a selection (people, a filter, a window, categories, a search) and a
venue as a place. They only read the world."""
import json

import numpy as np
import pytest


@pytest.fixture(scope="module")
def client(ran):
    from fastapi.testclient import TestClient
    from ucsim.api import server
    old = server.WS.base
    server.WS.base = ran
    try:
        yield TestClient(server.app), ran
    finally:
        server.WS.base = old


def _busy(sim, k=3):
    """The k people with the most events."""
    c = np.bincount(sim.log["a"], minlength=sim.w.P.n)
    return [int(i) for i in np.argsort(-c)[:k]]


def test_events_for_people(client):
    cl, sim = client
    ppl = _busy(sim)
    r = cl.get("/api/bench/events", params={"people": ",".join(map(str, ppl)), "limit": 5000}).json()
    log = sim.log
    want = np.isin(log["a"], ppl) | np.isin(log["b"], ppl)
    assert r["total"] == int(want.sum()) and r["n_people"] == 3
    ev = r["events"]
    assert ev and all(e["a"] in ppl or e["b"] in ppl for e in ev)
    assert [e["id"] for e in ev] == sorted((e["id"] for e in ev), reverse=True)           # newest first
    e = ev[0]
    assert e["label"] == sim.reg.events[e["type"]].label and e["a_name"]
    # oldest first, a window and a category
    w = cl.get("/api/bench/events", params={"people": ppl[0], "since": 3, "until": 9, "cats": "social", "order": "old"}).json()
    assert all(3 <= x["day"] <= 9 and x["category"] == "social" for x in w["events"])
    assert [x["id"] for x in w["events"]] == sorted(x["id"] for x in w["events"])


def test_events_filter_search_and_errors(client):
    cl, sim = client
    f = [{"var": "sex", "op": "eq", "value": "F"}]
    r = cl.get("/api/bench/events", params={"filter": json.dumps(f), "q": "friend", "limit": 50}).json()
    P = sim.w.P
    women = P.is_("sex", "F")
    for e in r["events"]:
        assert women[e["a"]] or (e["b"] is not None and women[e["b"]])
        assert "friend" in (e["label"] + " " + e["type"]).lower()
    everyone = cl.get("/api/bench/events", params={"limit": 1}).json()
    assert everyone["total"] == sim.log.n and everyone["n_people"] is None
    assert cl.get("/api/bench/events", params={"people": "x"}).status_code == 400
    assert cl.get("/api/bench/events", params={"filter": "{bad"}).status_code == 400


def test_density_adds_up(client):
    cl, sim = client
    ppl = _busy(sim, 20)
    r = cl.get("/api/bench/density", params={"people": ",".join(map(str, ppl))}).json()
    assert r["days"][0] == 0 and r["days"][-1] == sim.w.day
    assert all(len(v) == len(r["days"]) for v in r["counts"].values())
    assert sum(sum(v) for v in r["counts"].values()) == r["total"]
    ev = cl.get("/api/bench/events", params={"people": ",".join(map(str, ppl)), "limit": 1}).json()
    assert r["total"] == ev["total"]
    # important events only are fewer
    imp = cl.get("/api/bench/density", params={"people": ",".join(map(str, ppl)), "min_salience": 0.5}).json()
    assert imp["total"] <= r["total"]


def test_venue(client):
    cl, sim = client
    log = sim.log
    dates = np.nonzero((log["type"] == sim.reg.event_ids["date"]) & (log["place"] >= 0))[0]
    if not len(dates):
        pytest.skip("no dates at a venue in this small world")
    vid = int(log["place"][dates[-1]])
    r = cl.get(f"/api/bench/venue/{vid}").json()
    assert r["name"] and r["n_events"] >= 1 and any(c["type"] == "date" for c in r["event_counts"])
    assert all(e["place"] == vid for e in r["events"])
    for o in r["occasions"]:
        assert o["kind"] in ("date", "dance") or o["place"]
    assert cl.get("/api/bench/venue/999999").status_code == 404
