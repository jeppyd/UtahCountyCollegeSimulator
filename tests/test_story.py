"""Stories (analysis/story.py): shares of the push add up, a life reads as chapters with reasons, ripples follow what a
moment led to, and the endpoints serve them. Reading never changes the world."""
import numpy as np
from fastapi.testclient import TestClient

from ucsim.analysis import story as S
from ucsim.api import server


def _first(sim, kind):
    t = sim.log.cols["type"][: sim.log.n]
    return np.flatnonzero(t == sim.reg.event_ids[kind])


def test_why_shares_of_a_choice(ran):
    eid = int(_first(ran, "asked_out")[0])
    w = S.why(ran, f"event:{eid}")
    assert w["decision"] is not None and w["toward"]
    tot = sum(x["share"] for x in w["toward"] + w["against"])
    assert abs(tot - 1) < 0.02 or w.get("constraint")
    assert all(0 <= x["share"] <= 1 for x in w["toward"])
    assert w["toward"] == sorted(w["toward"], key=lambda x: -x["share"])


def test_why_of_an_event_without_a_choice(ran):
    eid = int(_first(ran, "new_friend")[0])
    w = S.why(ran, f"event:{eid}")
    assert w["toward"] and abs(sum(x["share"] for x in w["toward"]) - 1) < 0.02


def test_story_reads_as_chapters(ran):
    a = int(ran.log["a"][int(_first(ran, "first_date")[0])])
    n0 = ran.log.n
    st = S.story(ran, a)
    assert st["chapters"] and st["name"]
    lines = [l for c in st["chapters"] for l in c["lines"]]
    assert any(l["type"] == "first_date" for l in lines)
    assert any(l["because"] for l in lines)
    assert all(l["text"] for l in lines)
    days = [l["day"] for l in lines]
    assert days == sorted(days)
    assert ran.log.n == n0                                   # reading never changes the world


def test_ripple_follows_what_happened_next(ran):
    for e in _first(ran, "asked_out")[:30]:
        r = S.ripple(ran, f"event:{int(e)}")
        if len(r["steps"]) >= 3:
            break
    assert r["steps"][0]["key"] == r["root"] and r["steps"][0]["level"] == 0
    keys = {s["key"] for s in r["steps"]}
    assert all(s["parent"] in keys for s in r["steps"][1:])
    assert len(r["steps"]) >= 3


def test_endpoints(ran):
    saved = server.WS.base
    server.WS.base = ran
    try:
        c = TestClient(server.app)
        eid = int(_first(ran, "asked_out")[0])
        assert c.get("/api/story/why", params={"ref": f"event:{eid}"}).json()["toward"]
        assert c.get(f"/api/story/person/{int(ran.log['a'][eid])}").json()["chapters"]
        assert c.get("/api/story/ripple", params={"ref": f"event:{eid}"}).json()["steps"]
        assert c.get("/api/story/why", params={"ref": "event:999999999"}).status_code == 404
    finally:
        server.WS.base = saved
