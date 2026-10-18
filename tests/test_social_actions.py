"""Social actions: editor vs as-person, refusals in plain words, rides that make an occasion reachable, moving a dinner
later, introductions, job offers, the act endpoints, the What-if lever, and paired-world determinism."""
import copy

import numpy as np
import pytest

from ucsim.engine import runner
from ucsim.engine.ledger import ORIGIN_ID, RESPONSE_ID
from ucsim.engine.state import EdgeStore
from ucsim.engine.systems import social_actions as SA


@pytest.fixture(scope="module")
def world():
    sim = runner.new_simulation(scale=0.03, seed=5)
    sim.run_days(4)
    return sim


def _host_with_roommates(sim, k=2):
    P = sim.w.P
    u = P["unit_id"]
    for i in np.where(P["present"] & (u >= 0) & P["enrolled"])[0]:
        if ((u == u[i]) & P["present"]).sum() >= k + 1:
            return int(i)
    raise AssertionError("no apartment with roommates")


def _stranger(sim, i):
    P, E = sim.w.P, sim.w.E
    for j in np.where(P["present"])[0][::-1]:
        if j != i and E.find(EdgeStore.make_keys(np.array([i]), np.array([j])))[0] < 0:
            return int(j)
    raise AssertionError


def _friend(sim, i):
    E = sim.w.E
    lo, hi = E.endpoints()
    nb = np.r_[hi[lo == i], lo[hi == i]]
    nb = nb[sim.w.P["present"][nb]]
    return [int(x) for x in nb]


def _social(**kw):
    return {"target_type": "social", **kw}


def test_as_person_refusals_say_why(world):
    sim = copy.deepcopy(world)
    P = sim.w.P
    h = _host_with_roommates(sim)
    s = _stranger(sim, h)
    r = SA.check(sim, {"action": "invite", "as": h, "people": [s], "start": "19:30", "day_offset": 1})
    assert not r["ok"] and "doesn't know" in r["problems"][0]
    P.cols["savings"][h] = 2
    r = SA.check(sim, {"action": "invite", "as": h, "group": "roommates", "kind": "dinner", "start": "19:30", "day_offset": 1})
    assert not r["ok"] and "can't afford" in " ".join(r["problems"])
    P.cols["savings"][h] = 400
    day = sim.w.day + 1
    wd = sim.cal.weekday(day)
    P.cols["employed"][h] = True
    P.internal["shift_start"][h, wd], P.internal["shift_end"][h, wd] = 17 * 60, 21 * 60
    r = SA.check(sim, {"action": "invite", "as": h, "group": "roommates", "start": "19:00", "day_offset": 1})
    assert not r["ok"] and "works until 9 pm" in " ".join(r["problems"])
    # the same invitation from the world editor is allowed (the host would call it off) — editors arrange, people decide
    r = SA.check(sim, {"action": "invite", "host": h, "group": "roommates", "start": "19:00", "day_offset": 1})
    assert r["ok"] and r["warnings"]
    assert "employer" in SA.check(sim, {"action": "job_offer", "as": h, "to": s})["problems"][0]
    assert not SA.check(sim, {"action": "dance_off"})["ok"]
    assert "already passed" in SA.check(sim, {"action": "invite", "host": h, "group": "roommates", "day_offset": -1,
                                              "start": "19:00"})["problems"][0]
    # only the organizer may move their occasion
    O = sim.book.occ
    plan = (O["status"] == 0) & (O["organizer"] >= 0) & (O["organizer"] != h) & (O["day"] >= sim.w.day)
    if plan.any():
        oid = int(O["id"][plan][0])
        r = SA.check(sim, {"action": "reschedule", "as": h, "occasion": oid, "start": "20:00"})
        assert not r["ok"] and "organizer" in r["problems"][0]


def test_preview_lists_everyone_involved(world):
    h = _host_with_roommates(world)
    r = SA.check(world, {"action": "invite", "as": h, "group": "roommates", "kind": "dinner", "weekday": "sunday", "start": "7:30 pm"})
    assert r["ok"], r["problems"]
    roles = {p["role"] for p in r["people"]}
    assert roles == {"host", "guest"}
    assert all(set(p) >= {"free", "travel", "late", "reason", "name"} for p in r["people"])
    assert "7:30 pm" in r["summary"] and "Sun" in r["summary"]


def test_invite_lowers_to_a_user_occasion_that_people_decide_about(world):
    h = _host_with_roommates(world)
    alt = runner.fork(world, [_social(action="invite", **{"as": h}, group="roommates", kind="dinner", day_offset=0, start="19:30")])
    alt.step_day()
    res = alt.systems["environment"].manager.social_results[0]
    assert res["ok"] and res["invitations"] >= 2
    oid = res["occasion"]
    d = alt.book.describe(oid)
    assert d["origin"] == "user" and d["org_kind"] == "user" and d["org_id"] == 0 and d["organizer"] == h
    inv = alt.book.invitation_rows(alt.book.invitations(oid))
    asked = [r for r in inv if r["person"] != h]
    assert all(r["decision"] >= 0 for r in asked if r["seen_day"] >= 0)
    assert all(r["channel"] == "in_person" for r in asked)        # roommates are asked face to face
    if d["status"] == "happened":
        ev = alt.causes.effects_of("action", 0)
        assert len(ev)                                            # the host's event names the action as a cause


def test_ride_makes_an_occasion_reachable(world, monkeypatch):
    """Without a car the trip takes too long to be worth going; with an offered ride they could."""
    sim = copy.deepcopy(world)
    P = sim.w.P
    occ = sim.systems["occasions"]
    tm = sim.travel

    def trip(people, lon, lat, weekday, minute, ride=None, origin_lon=None, origin_lat=None):
        k = len(np.atleast_1d(people))
        r = np.zeros(k, bool) if ride is None else np.broadcast_to(np.asarray(ride, bool), (k,))
        return np.where(r, 20.0, 80.0).astype(np.float32), np.where(r, 4, 1).astype(np.int8)

    monkeypatch.setattr(tm, "trip", trip)
    i = int(np.where(P["present"] & ~P["owns_car"])[0][0]) if "owns_car" in P else int(np.where(P["present"])[0][0])
    day = sim.w.day + 1
    wd = sim.cal.weekday(day)
    P.cols["employed"][i] = True
    P.internal["shift_start"][i, wd], P.internal["shift_end"][i, wd] = 14 * 60, 18 * 60
    lon, lat = -111.70, 40.30
    no = occ.check_window([i], day, 18 * 60 + 30, 90, lon, lat)
    yes = occ.check_window([i], day, 18 * 60 + 30, 90, lon, lat, ride=np.ones(1, bool))
    assert not no["feasible"][0] and "no way to get there" in no["reason"][0]
    assert yes["feasible"][0] and yes["mode"][0] == "ride" and yes["late"][0] == 0
    # through the action: the rider reconsiders, and "no way to get there" is no longer what decides it
    host = _host_with_roommates(sim)
    oid = int(sim.book.plan("dinner", day, 18 * 60 + 30, 90, organizer=host, lon=lon, lat=lat, ctx=255, origin="user",
                            label="Far dinner")[0])
    inv = occ.send_invites([oid], [i], host, "text")
    first = sim.decisions.get(int(sim.book.inv.get("decision", inv)[0])) if sim.book.inv.get("seen_day", inv)[0] >= 0 else None
    if first is not None:
        assert first["outcome"] == "no" and any(f["factor"] == "cant_get_there" for f in first["factors"])
    sim.book.inv.cols["seen_day"][sim.book.inv.pos(inv)] = sim.w.day
    occ.rides[(oid, i)] = -2
    occ.reconsider(oid, [i])
    again = sim.decisions.get(int(sim.book.inv.get("decision", inv)[0]))
    assert not any(f["factor"] == "cant_get_there" for f in again["factors"])
    assert any(f["factor"] == "ride" for f in again["factors"]) or again["outcome"] in ("yes", "no")


def test_moving_a_dinner_later_lets_a_working_student_come(world):
    sim = copy.deepcopy(world)
    P = sim.w.P
    occ = sim.systems["occasions"]
    h = _host_with_roommates(sim)
    guests = SA._Ctx(sim, {}).group("roommates", h)
    w = int(guests[0])
    day = sim.w.day + 2
    wd = sim.cal.weekday(day)
    P.cols["employed"][w] = True
    P.internal["shift_start"][w, wd], P.internal["shift_end"][w, wd] = 15 * 60, 19 * 60
    oid = int(sim.book.plan("dinner", day, 18 * 60, 90, organizer=h, place=int(P["unit_id"][h]),
                            lon=float(sim.w.units.lon[P["unit_id"][h]]), lat=float(sim.w.units.lat[P["unit_id"][h]]),
                            ctx=255, origin="user", label="Dinner")[0])
    inv = occ.send_invites([oid], guests, h, "in_person")
    row = sim.book.inv.pos(inv)[list(guests).index(w)]
    d0 = sim.decisions.get(int(sim.book.inv.cols["decision"][row]))
    assert d0["outcome"] == "no" and any(f["factor"] == "conflict" for f in d0["factors"])
    alt_item = {"action": "reschedule", "as": h, "occasion": oid, "start": "19:30"}
    chk = SA.check(sim, alt_item)
    assert chk["ok"] and "more could come" in chk["summary"]
    me = next(p for p in chk["people"] if p["id"] == w)
    assert me["free"] and not me["free_before"]
    res = SA.apply_action(occ, 0, {"target_type": "social", **alt_item})
    assert res["ok"]
    d1 = sim.decisions.get(int(sim.book.inv.cols["decision"][row]))
    assert not any(f["constraint"] for f in d1["factors"])          # now it's their call, not their shift's
    assert sim.book.describe(oid)["start"] == 19 * 60 + 30


def test_introduction_and_job_offer(world):
    sim = copy.deepcopy(world)
    occ = sim.systems["occasions"]
    h = _host_with_roommates(sim)
    fr = _friend(sim, h)
    a, b = fr[0], fr[-1]
    res = SA.apply_action(occ, 3, {"target_type": "social", "action": "introduce", "as": h, "a": a, "b": b, "day_offset": 0,
                                   "start": "20:00"})
    assert res["ok"] and res["invitations"] == 2
    oid = res["occasion"]
    assert sim.book.describe(oid)["kind"] == "introduction"
    for x in sim.book.invitations(oid):
        did = int(sim.book.inv.get("decision", [x])[0])
        if did >= 0:
            assert any(f["factor"] == "introduced" for f in sim.decisions.get(did)["factors"])
    s = _stranger(sim, h)
    res = SA.apply_action(occ, 4, {"target_type": "social", "action": "job_offer", "to": s, "hours": 10})
    assert res["ok"] and res["decision"] >= 0
    d = sim.decisions.get(res["decision"])
    assert d["kind"] == "take_job" and d["outcome"] in ("accepted", "declined")
    if res["accepted"]:
        assert sim.w.P["employed"][s] and sim.log["type"][res["event"]] == sim.reg.event_names.index("job_found")


def test_paired_worlds_stay_identical_without_an_action_and_local_with_one(world):
    base = copy.deepcopy(world)
    same = runner.fork(base, [])
    for _ in range(3):
        base.step_day()
        same.step_day()
    for c in ("mood", "loneliness", "unit_id", "n_friends", "social_events_month"):
        assert np.array_equal(base.w.P[c], same.w.P[c]), c
    for c in ("kind", "organizer", "start", "n_came"):
        assert np.array_equal(base.book.occ[c], same.book.occ[c]), c
    # with an action: two forks with the same action agree exactly; on the action's day, every occasion planned by
    # someone the action doesn't involve is planned the same way as in the Original (same host, kind and time)
    start = copy.deepcopy(world)
    h = _host_with_roommates(start)
    act = [_social(action="invite", **{"as": h}, group="roommates", kind="dinner", day_offset=0, start="19:30")]
    x, y = runner.fork(start, act), runner.fork(start, act)
    orig = copy.deepcopy(start)
    for s in (x, y, orig):
        s.step_day()
    assert np.array_equal(x.book.occ["organizer"], y.book.occ["organizer"])
    assert np.array_equal(x.book.inv["response"], y.book.inv["response"])
    involved = set([h]) | set(SA._Ctx(start, {}).group("roommates", h).tolist())

    def planned(s):
        O = s.book.occ
        m = (O["created_day"] == start.w.day) & (O["origin"] == ORIGIN_ID["engine"]) & ~np.isin(O["organizer"], list(involved))
        m &= O["kind"] != s.book.kind_id["dance"]
        return sorted(zip(O["organizer"][m].tolist(), O["kind"][m].tolist(), O["start"][m].tolist(), O["day"][m].tolist()))

    assert planned(x) == planned(orig)
    # and the Original never saw the action
    assert not (orig.book.occ["origin"] == ORIGIN_ID["user"]).any()
    assert (x.book.occ["origin"] == ORIGIN_ID["user"]).sum() == 1


def test_act_endpoints_fork_and_apply(world):
    from fastapi.testclient import TestClient
    from ucsim.api import server
    keep = server.WS.base, server.WS.alt
    try:
        server.WS.base, server.WS.alt = copy.deepcopy(world), None
        c = TestClient(server.app)
        h = _host_with_roommates(server.WS.base)
        body = {"action": "invite", "as": h, "group": "roommates", "kind": "game_night", "day_offset": 1, "start": "20:00"}
        r = c.post("/api/act/check", json=body).json()
        assert r["ok"] and r["world"] == "Original" and r["people"]
        bad = c.post("/api/act", json={**body, "people": [_stranger(server.WS.base, h)], "group": None}).json()
        assert not bad["ok"] and bad["problems"] and server.WS.alt is None      # refused: no What-if made
        r = c.post("/api/act", json=body).json()
        assert r["ok"] and r["made_whatif"] and r["occasion"] >= 0
        assert server.WS.alt is not None and server.WS.alt.book.describe(r["occasion"])["origin"] == "user"
        assert server.WS.base.book.occ.pos([r["occasion"]])[0] < 0 or \
            server.WS.base.book.describe(r["occasion"])["origin"] != "user"
        sc = c.get(f"/api/occasion/{r['occasion']}", params={"u": "alt"}).json()
        assert sc["how"].startswith("arranged") and sc["people"]
    finally:
        server.WS.base, server.WS.alt = keep


def test_whatif_plan_with_a_social_change_compiles(world):
    from ucsim.llm.plan import lower, validate
    h = _host_with_roommates(world)
    plan = {"title": "Sunday dinner", "reply": "ok", "assumptions": [], "not_modeled": [], "expectations": [],
            "confidence": "medium",
            "changes": [{"kind": "social", "label": "Sunday dinner", "why": "asked",
                         "social": {"action": "invite", "as": h, "group": "roommates", "kind": "dinner", "weekday": "sunday",
                                    "start": "19:30"}}]}
    v = validate(plan, world)
    assert v["ok"], v["errors"]
    assert v["changes"][0]["n"] >= 2 and "7:30 pm" in v["changes"][0]["summary"]
    atoms = lower(v["plan"], world.w.day, "wiX")
    assert atoms[0]["target_type"] == "social" and atoms[0]["action"] == "invite" and atoms[0]["as"] == h
    bad = {**plan, "changes": [{**plan["changes"][0], "social": {"action": "invite", "as": h, "people": [_stranger(world, h)],
                                                                  "start": "19:30"}}]}
    v2 = validate(bad, world)
    assert not v2["ok"] and any("doesn't know" in e for e in v2["errors"])
