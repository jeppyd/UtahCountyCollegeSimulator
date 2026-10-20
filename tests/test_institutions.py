"""Institutions (engine/systems/institutions.py): counseling queues with capacity and crisis priority, bishops'
interview slots, club officers adapting, member-only events, shift flexibility, the API and determinism."""
import numpy as np
from fastapi.testclient import TestClient

from ucsim.api import server
from ucsim.engine.runner import new_simulation
from ucsim.engine.systems.institutions import ACTION_ID, KIND_ID


def test_counseling_respects_capacity_and_crisis_first(ran):
    I = ran.systems["institutions"]
    T, Q = I.T, I.q
    assert Q.n > 0
    for c in np.flatnonzero(T["kind"] == KIND_ID["counseling"]):
        cid = T.ids[c]
        assert T["served"][c] <= T["capacity"][c] + 1e-6
        m = Q["center"] == cid
        for d in np.unique(Q["start"][m & (Q["start"] >= 0)]):
            started = m & (Q["start"] == d)
            left = m & (Q["asked"] <= d) & ((Q["start"] < 0) | (Q["start"] > d)) & ~Q["gave_up"]
            if (Q["crisis"][left]).any():            # nobody non-urgent got in ahead of someone in crisis
                assert Q["crisis"][started].all()


def test_bishop_sees_everyone_who_asks(fresh):
    """Bishops make time for members who want to talk: no queue, no waiting; the ward counts the meetings."""
    I = fresh.systems["institutions"]
    P = fresh.w.P
    ward = int(np.bincount(P["ward_id"][P["ward_id"] >= 0]).argmax())
    people = np.flatnonzero((P["ward_id"] == ward) & P["present"].astype(bool))[:20]
    assert I.bishop_gate(people).all()
    assert I.bishop_gate(people[:3]).all()                  # and again the same week
    assert int(I.T["waitlist"][I.row("ward", ward)]) == 0
    L = fresh.log
    assert (L.cols["type"][: L.n] == fresh.reg.event_ids["waiting_for_bishop"]).sum() == 0


def test_officers_adapt_after_low_turnout(fresh):
    I = fresh.systems["institutions"]
    T = I.T
    j = int(np.flatnonzero(T["kind"] == KIND_ID["club"])[0])
    oid = I._event(j, fresh.w.day, "club_social", "group", 19 * 60, -1)
    T.cols["low_runs"][j] = 3
    n0 = I.dec.n
    I._after(j, fresh.w.day)
    assert I.dec.n == n0 + 1 and I.dec["action"][-1] in (ACTION_ID["add_food"], ACTION_ID["change_night"], ACTION_ID["recruit"])
    assert I.dec["occasion"][-1] == oid


def test_member_only_events(ran):
    from ucsim.engine.ledger import ORG_ID
    O, Iv = ran.book.occ, ran.book.inv
    P = ran.w.P
    ward_occ = np.flatnonzero((O["org_kind"] == ORG_ID["ward"]) & (O["n_came"] > 0))
    assert len(ward_occ)
    for r in ward_occ[:5]:
        came = Iv["person"][(Iv["occ"] == O.ids[r]) & Iv["attended"]]
        assert (P["ward_id"][came] == O["org_id"][r]).all()


def test_shift_flex_is_stable_and_by_job(fresh):
    I = fresh.systems["institutions"]
    P = fresh.w.P
    emp = np.flatnonzero(P["employed"] & (P["employer_id"] >= 0))
    a, b = I.shift_flex(emp, 10), I.shift_flex(emp, 10)
    assert np.array_equal(a, b) and 0.05 < a.mean() < 0.7


def test_api_and_trace(ran):
    saved = server.WS.base
    server.WS.base = ran
    try:
        c = TestClient(server.app)
        rows = c.get("/api/institutions", params={"kind": "counseling"}).json()
        d = c.get(f"/api/institutions/{rows[0]['id']}").json()
        assert d["queue"]["n_in_care"] + d["queue"]["n_finished"] > 0 and d["history"]
        ev = int(np.flatnonzero(ran.log.cols["type"][: ran.log.n] == ran.reg.event_ids["counseling_started"])[0])
        assert c.get("/api/trace", params={"ref": f"event:{ev}", "dir": "back"}).status_code == 200
    finally:
        server.WS.base = saved


def test_institutions_are_deterministic():
    out = []
    for _ in range(2):
        sim = new_simulation(scale=0.02, seed=6)
        sim.run_days(15)
        I = sim.systems["institutions"]
        out.append((I.q["person"].copy(), I.q["start"].copy(), I.hist["served"].copy(), sim.book.occ["n_came"].copy()))
    for x, y in zip(*out):
        assert np.array_equal(x, y)


def test_bishop_counsel_holds_recommend_then_restores():
    """After a premarital-sex confession the recommend is held for weeks (often the sacrament too), there are
    follow-ups about monthly, and the recommend comes back when the hold ends."""
    sim = new_simulation(scale=0.02, seed=4)
    P, I = sim.w.P, sim.systems["institutions"]
    x = np.flatnonzero(P["lds_member"] & P["present"].astype(bool) & P.is_("activity", "active"))[:30]
    P.cols["premarital_sex_current"][x] = False
    I.counsel(x, "sex")
    assert not P["temple_recommend"][x].any()
    until = P.internal["recommend_hold_until"][x]
    assert (until - sim.w.day >= 7).all() and (until - sim.w.day <= 7 * 12).all()
    assert P.internal["sacrament_hold"][x].any() and (P.internal["bishop_next"][x] > sim.w.day).all()
    d0 = sim.w.day
    for d in range(d0, d0 + 120):
        sim.w.day = d
        I._bishop_day(d)
    assert P["temple_recommend"][x].all() and not P.internal["sacrament_hold"][x].any()
    L = sim.log
    t = L.cols["type"][: L.n]
    assert (t == sim.reg.event_ids["bishop_followup"]).sum() > 0
    assert (t == sim.reg.event_ids["recommend_restored"]).sum() == len(x)
