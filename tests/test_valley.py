"""The valley (analysis/valley.py) and scenes (analysis/script.py): the home screen's curated feed, lives worth
following, the followed people now, watchable scripts, and acting in the Original world. Reading never changes a world."""
import copy

import numpy as np
from fastapi.testclient import TestClient

from ucsim.analysis import script as SC
from ucsim.analysis import valley as V
from ucsim.engine.state import EdgeStore, Tie


def _first(sim, kind):
    t = sim.log.cols["type"][: sim.log.n]
    return np.flatnonzero(t == sim.reg.event_ids[kind])


def test_valley_feed_is_curated(ran):
    n0 = ran.log.n
    f = V.feed(ran, since=0, limit=300)
    ms = f["moments"]
    assert ms and ran.log.n == n0
    assert all(m["salience"] >= V.MIN_VALLEY and m["type"] not in V.QUIET for m in ms)
    days = [m["day"] for m in ms]
    assert days == sorted(days, reverse=True)
    # a two-person moment shows once, and the received half of a breakup never shows next to its first half
    keys = [(m["type"], m["day"], tuple(sorted(p["id"] for p in m["people"]))) for m in ms]
    assert len(keys) == len(set(keys))
    firsts = {(m["day"], tuple(sorted(p["id"] for p in m["people"]))) for m in ms if m["type"] == "breakup_initiated"}
    assert not any(m["type"] == "breakup_received" and (m["day"], tuple(sorted(p["id"] for p in m["people"]))) in firsts for m in ms)
    # a few of each kind, so one busy kind can't flood it
    kinds = {}
    for m in ms:
        kinds[m["type"]] = kinds.get(m["type"], 0) + 1
    assert max(kinds.values()) <= 3


def test_feed_for_followed_people(ran):
    a = int(ran.log["a"][int(_first(ran, "first_date")[0])])
    f = V.feed(ran, [a], since=0, limit=200)
    assert f["moments"] and all(a in [p["id"] for p in m["people"]] for m in f["moments"])
    assert any(m["because"] for m in f["moments"])
    assert all(m["times"] >= 1 and m["first_day"] <= m["day"] for m in f["moments"])
    assert all("occasion" in m for m in f["moments"])


def test_cast_and_now(ran):
    c = V.cast(ran)["cast"]
    assert len(c) >= 3 and len({x["id"] for x in c}) == len(c)
    assert all(x["hook"] and x["label"] and x["headline"] for x in c)
    assert V.cast(ran)["cast"] == c                          # deterministic
    now = V.now(ran, [x["id"] for x in c[:3]])["people"]
    assert len(now) == 3 and all(p["doing"] and 0 <= p["mood"] <= 1 for p in now)


def test_occasion_script(ran):
    O = ran.book.occ
    done = np.flatnonzero((O["n_came"][: O.n] >= 3))
    assert len(done)
    oid = int(O["id"][done[-1]])
    s1 = SC.occasion_script(ran, oid)
    assert s1 == SC.occasion_script(ran, oid)                # the same words every time
    kinds = {b["kind"] for b in s1["beats"]}
    assert "arrive" in kinds and s1["note"]
    assert any(b.get("line") for b in s1["beats"])
    timed = [b["minute"] for b in s1["beats"] if b["minute"] is not None]
    assert timed == sorted(timed)


def test_pair_script(ran):
    e = int(_first(ran, "first_date")[0])
    a, b = int(ran.log["a"][e]), int(ran.log["b"][e])
    s = SC.pair_script(ran, a, b)
    assert s["beats"] and s["tie"] is not None
    assert any("date" in (x.get("text") or "") or x.get("source") == "first date" for x in s["beats"])
    dates = [x["date"] for x in s["beats"]]
    assert dates == sorted(dates)


def _knowers(sim):
    P, E = sim.w.P, sim.w.E
    lo, hi = E.endpoints()
    single = P.is_("rel_status", "single")
    for x, y in zip(lo.tolist(), hi.tolist()):
        e = E.find(EdgeStore.make_keys(np.array([x]), np.array([y])))[0]
        if single[x] and single[y] and P["present"][x] and P["present"][y] and not (E["flags"][e] & Tie.EX):
            return x, y
    raise AssertionError("no pair")


def test_spark_and_acting_in_the_original(ran):
    from ucsim.api import server
    keep = server.WS.base, server.WS.alt
    try:
        server.WS.base, server.WS.alt = copy.deepcopy(ran), None
        c = TestClient(server.app)
        x, y = _knowers(server.WS.base)
        body = {"action": "spark", "from": x, "to": y, "strength": 0.9}
        chk = c.post("/api/act/check", json={**body, "u": "base"}).json()
        assert chk["ok"] and chk["world"] == "Original"
        r = c.post("/api/act", json={**body, "world": "original"}).json()
        assert r["ok"] and r["sparked"] and r["world"] == "Original" and server.WS.alt is None   # no What-if made
        E = server.WS.base.w.E
        e = E.find(EdgeStore.make_keys(np.array([x]), np.array([y])))
        assert float(E.attraction_from(e, np.array([x]))[0]) >= 0.9 - 1e-6
        ev = r["event"]
        assert server.WS.base.reg.event_names[int(server.WS.base.log["type"][ev])] == "spark"
        bad = c.post("/api/act", json={"action": "spark", "as": x, "from": x, "to": y, "world": "original"}).json()
        assert not bad["ok"]                                   # nobody decides to have feelings: editor only
        assert c.get("/api/valley/feed", params={"people": str(x)}).json()["moments"][0]["because"] == "you made it happen"
        assert c.get("/api/valley/cast").json()["cast"]
        assert c.get("/api/valley/now", params={"people": f"{x},{y}"}).json()["people"]
        assert c.get("/api/scene/pair", params={"a": x, "b": y}).json()["beats"]
    finally:
        server.WS.base, server.WS.alt = keep


def test_ask_out_break_up_and_go_home_in_the_original(ran):
    from ucsim.api import server
    keep = server.WS.base, server.WS.alt
    try:
        server.WS.base, server.WS.alt = copy.deepcopy(ran), None
        sim = server.WS.base
        P = sim.w.P
        c = TestClient(server.app)
        names = sim.reg.event_names
        # asking someone out: the answer is theirs, and the ask points at what you did
        x, y = _knowers(sim)
        r = c.post("/api/act", json={"action": "ask_out", "as": x, "to": y, "world": "original"}).json()
        assert r["ok"] and r["asked"] and names[int(sim.log["type"][r["event"]])] == "asked_out"
        assert r["yes"] == (P.internal["date_planned"][x] >= sim.w.day)
        # breaking up: the couple is single afterwards, and the one you chose ended it
        a = int(np.flatnonzero(P.isin("rel_status", ["dating", "engaged"]) & (P["partner_id"] >= 0) & P["present"])[0])
        b = int(P["partner_id"][a])
        r = c.post("/api/act", json={"action": "break_up", "as": a, "world": "original"}).json()
        assert r["ok"] and r["ended"] and P["partner_id"][a] == -1 and P["partner_id"][b] == -1
        assert int(sim.log["a"][r["event"]]) == a
        assert not c.post("/api/act", json={"action": "break_up", "as": a, "world": "original"}).json()["ok"]  # nobody left
        # going home: away until they come back
        g = int(np.flatnonzero(P["present"] & (P["home_drive_hours"] > 1) & (P["home_drive_hours"] < 6))[0])
        r = c.post("/api/act", json={"action": "go_home", "as": g, "nights": 3, "world": "original"}).json()
        assert r["ok"] and r["went"] and not P["present"][g]
        assert names[int(sim.log["type"][r["event"]])] == "went_home"
        # undo puts the world back as it was just before the last change (one step)
        assert "goes home" in c.get("/api/status").json()["checkpoint"]["label"]
        u = c.post("/api/act/undo").json()
        assert u["ok"] and server.WS.base is not sim and server.WS.base.w.P["present"][g]
        assert server.WS.base.w.P["partner_id"][a] == -1            # the breakup before it stays
        assert c.post("/api/act/undo").status_code == 400          # the copy is used up
    finally:
        server.WS.base, server.WS.alt = keep
