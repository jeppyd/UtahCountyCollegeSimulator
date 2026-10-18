"""Occasions: hosting, invitations, feasibility, attendance in the blocks they overlap, open events, dates,
traditions, the scene and agenda views, and their endpoints."""
import copy

import numpy as np
import pytest

from ucsim.engine import clock
from ucsim.engine.ledger import RESPONSE_ID, STATUS_ID
from ucsim.engine.state import CTX_ID
from ucsim.registry import get_registry


def _kind(sim, name):
    return sim.book.kind_id[name]


def test_hosts_plan_kinds_and_times_and_invite(ran):
    book, O, I = ran.book, ran.book.occ, ran.book.inv
    hosted = np.isin(O["kind"], [_kind(ran, k) for k in ("gathering", "dinner", "game_night", "party", "study_group")])
    assert hosted.sum() > 50
    assert (O["organizer"][hosted] >= 0).all() and (O["n_invited"][hosted] > 0).mean() > 0.9
    # start times are clock times in the evening (moved later to fit the host's day, never past the kind's latest start)
    st = O["start"][hosted]
    assert (st >= 15 * 60).all() and (st <= 22 * 60).all()
    assert (O["start"][hosted] + O["dur"][hosted] <= 24 * 60).all()
    # every hosted occasion has the host's recorded decision, with the kind chosen and why
    dec = O["decision"][hosted]
    assert (dec >= 0).mean() > 0.9
    d = ran.decisions.get(int(dec[dec >= 0][0]))
    assert d["kind"] == "host_occasion" and d["outcome"] == "hosted" and d["factors"]
    # roommates are asked in person, others mostly by text
    ch = I["channel"]
    assert (ch == 0).any() and (ch == 1).any()
    # parties are on weekends, some planned days ahead
    party = O["kind"] == _kind(ran, "party")
    wd = np.array([ran.cal.weekday(int(x)) for x in O["day"][party]])
    assert party.any() and (np.isin(wd, (4, 5)).mean() > 0.6)
    assert (O["day"][party] > O["created_day"][party]).any()


def test_invitation_answers_have_reasons_and_constraints(ran):
    I, dl = ran.book.inv, ran.decisions
    decided = I["decision"] >= 0
    assert decided.sum() > 100
    kinds = {dl.get(int(x))["kind"] for x in I["decision"][decided][:200]}
    assert "attend_occasion" in kinds
    # someone who couldn't come because of a shift or class is recorded as "couldn't", not "didn't want to"
    rows = [dl.get(int(x)) for x in I["decision"][decided & (I["response"] == RESPONSE_ID["no"])][:2000]]
    cons = [f for r in rows if r for f in r["factors"] if f["constraint"]]
    assert cons and {f["factor"] for f in cons} & {"conflict", "cant_get_there", "ill"}
    # yeses and attendance agree with the counters
    O = ran.book.occ
    j = int(np.argmax(O["n_came"]))
    oid = int(O["id"][j])
    assert len(ran.book.attendees(oid)) == int(O["n_came"][j])


def test_every_recorded_factor_is_declared(ran):
    reg = get_registry()
    for key in ran.decisions.factor_names:
        kind, f = key.split(".", 1)
        assert f in (reg.decisions[kind].get("factors") or {}), key


def test_attendance_follows_the_clock(ran):
    """Who was at an occasion was there in the blocks it overlaps; arrivals are at or after the start."""
    I, O = ran.book.inv, ran.book.occ
    att = I["attended"] & (I["arrive"] >= 0)
    occ = I["occ"][att]
    pos = O.pos(occ)
    ok = pos >= 0
    st = O.cols["start"][pos[ok]].astype(np.int32)
    du = O.cols["dur"][pos[ok]].astype(np.int32)
    arr = I["arrive"][att][ok].astype(np.int32)
    assert (arr >= st - 1).mean() > 0.99 and (arr <= st + du).all()
    # dances are Friday and Saturday nights at 9 pm, in the late-evening block
    dance = O["kind"] == _kind(ran, "dance")
    assert dance.any()
    assert set(ran.cal.weekday(int(d)) for d in O["day"][dance]) <= {4, 5}
    assert all(clock.main_blocks(int(s), int(d)) == [3] for s, d in zip(O["start"][dance], O["dur"][dance]))


def test_dates_are_occasions_at_a_venue_with_both(ran):
    O, I = ran.book.occ, ran.book.inv
    dates = (O["kind"] == _kind(ran, "date")) & (O["status"] == STATUS_ID["happened"])
    assert dates.sum() > 10
    j = np.where(dates)[0][0]
    oid = int(O["id"][j])
    came = ran.book.attendees(oid)
    assert len(came) == 2 and int(O["organizer"][j]) in came.tolist()
    assert O["place"][j] >= 0 and np.isfinite(O["lon"][j])
    # the date events point at their occasion
    evs = ran.causes.effects_of("occasion", oid)
    assert len(evs) and {ran.reg.event_names[ran.log["type"][e]] for e in evs} & {"date", "first_date"}


def test_social_events_month_stays_plausible(ran):
    P = ran.w.P
    m = P["present"] & (P["school"] > 0)
    v = P["social_events_month"][m]
    assert 1.0 < float(np.mean(v)) < 12.0


def test_feasibility_shift_then_dinner(fresh):
    """A working student can make a 7:30 dinner but not a 6:00 one when their shift ends at 7 pm."""
    sim = copy.deepcopy(fresh)
    sim.run_days(1)
    P = sim.w.P
    occ = sim.systems["occasions"]
    i = int(np.where(P["present"] & P["enrolled"] & (P["unit_id"] >= 0))[0][0])
    day = sim.w.day + 1
    wd = sim.cal.weekday(day)
    P.cols["employed"][i] = True
    P.internal["shift_start"][i, wd] = 15 * 60
    P.internal["shift_end"][i, wd] = 19 * 60
    u = int(P["unit_id"][i])
    lon, lat = float(sim.w.units.lon[u]), float(sim.w.units.lat[u])
    early = occ.check_window([i], day, 18 * 60, 90, lon, lat)
    later = occ.check_window([i], day, 19 * 60 + 30, 90, lon, lat)
    assert not early["feasible"][0] and "works until 7 pm" in early["reason"][0]
    assert later["feasible"][0] and later["late"][0] <= 15
    # a shift ending inside the dinner makes them late by the trip
    mid = occ.check_window([i], day, 18 * 60 + 45, 120, lon, lat)
    assert mid["feasible"][0] and mid["late"][0] >= 15
    fw = occ.free_window(i, day)
    assert any(w["start"] <= 19 * 60 + 30 and w["end"] >= 21 * 60 for w in fw)
    assert all(not (w["start"] < 19 * 60 and w["end"] > 15 * 60) for w in fw)


def test_open_occasion_audience_capacity_and_travel(fresh):
    sim = copy.deepcopy(fresh)
    sim.run_days(2)
    occ, book = sim.systems["occasions"], sim.book
    act = sim.systems["activity"]
    v = int(np.where(act.v_type == "dance")[0][0])
    spec = book.vocab["dance"]
    old = spec["base"]
    try:
        spec["base"] = 2.0              # everyone in the audience is keen: capacity decides
        oid = book.plan("dance", sim.w.day, 21 * 60, 150, place=v, lon=float(act.v_lon[v]), lat=float(act.v_lat[v]),
                        ctx=CTX_ID["occasion"], open_=True, capacity=5, label="Test dance")
        occ.resolve()
    finally:
        spec["base"] = old
    o = int(oid[0])
    rows = sim.decisions.for_occasion(o)
    full = [sim.decisions.get(int(x)) for x in rows]
    yes = [d for d in full if d["outcome"] == "yes"]
    turned = [d for d in full if d["outcome"] == "no" and any(f["factor"] == "full" for f in d["factors"])]
    assert len(yes) == 5 and turned
    # only the audience (single 18–30) considers it
    P = sim.w.P
    who = np.array([d["agent"] for d in full])
    assert (P["age"][who] >= 18).all() and (P["age"][who] < 31).all()


def test_traditions_start_pass_on_and_end(fresh):
    sim = copy.deepcopy(fresh)
    sim.p.values["occasions.tradition.start_base"] = 6.0      # every good get-together becomes a weekly thing
    sim.p.values["occasions.tradition.takeover_base"] = 6.0
    sim.run_days(8)
    S, book = sim.book.series, sim.book
    assert S.n > 0
    started = np.where(sim.log["type"] == sim.reg.event_names.index("tradition_started"))[0]
    assert len(started) and sim.log["decision"][started[0]] >= 0          # the host's start_tradition decision
    # the next week's instance invites the regulars by group chat
    sim.run_days(7)
    inst = book.occ["series"] >= 0
    assert inst.any()
    oid = int(book.occ["id"][inst][0])
    ch = book.inv.get("channel", book.invitations(oid))
    assert len(ch)
    # the host moves out: a roommate who came takes it over (or it ends), with a recorded decision and an event
    sid = int(book.occ["series"][inst][0])
    host = int(S.get("organizer", [sid])[0])
    occ = sim.systems["occasions"]
    occ.series_members[sid].append(np.array([host], np.int64))
    sim.w.P.cols["unit_id"][host] = -1
    sim.run_days(7)
    names = {sim.reg.event_names[t] for t in sim.log["type"][sim.log["day"] >= sim.w.day - 7]}
    assert names & {"tradition_passed_on", "tradition_ended"}
    if not S.get("active", [sid])[0]:
        assert "tradition_ended" in names
    else:
        assert int(S.get("organizer", [sid])[0]) != host


def test_hosting_burden_rises_late_on_school_nights(fresh):
    sim = copy.deepcopy(fresh)
    sim.p.values["occasions.burden.threshold"] = 0.0      # every host notices the work
    sim.run_days(4)
    t = sim.reg.event_names.index("hosting_strain")
    ev = np.where(sim.log["type"] == t)[0]
    assert len(ev)
    assert (sim.log["cause"][ev] >= 0).all()           # caused by the hosted_gathering event


def test_a_date_right_after_a_shift_happens(fresh):
    """A shift that ends at 2:45 fills most of the afternoon block, but the 3:15 date after it still happens: everyone
    expected at an occasion is recorded as there, whatever else fills more of the block."""
    sim = copy.deepcopy(fresh)
    sim.run_days(1)
    P = sim.w.P
    rom, occ = sim.systems["romance"], sim.systems["occasions"]
    cand = np.where(P["present"] & ~P["enrolled"] & (P["unit_id"] >= 0) & (P["age"] < 40))[0]
    a, b = int(cand[0]), int(cand[1])
    day = sim.w.day                     # the next day to run
    wd = sim.cal.weekday(day)
    P.cols["employed"][a] = True
    P.internal["shift_start"][[a, b]] = -1
    P.internal["shift_end"][[a, b]] = -1
    P.internal["shift_start"][a, wd], P.internal["shift_end"][a, wd] = 8 * 60, 14 * 60 + 45
    P.cols["ill"][[a, b]] = False
    rom.queue.append((day, a, b, "museum", False, -1))
    sim.run_days(1)
    j = [k for k, d in enumerate(rom.dates_today) if {d[0], d[1]} == {a, b}]
    assert j, "the date was booked"
    oid = int(rom.date_occ[j[0]])
    d = sim.book.describe(oid)
    assert d["start"] >= 15 * 60 and d["status"] == "happened"        # after the shift, and both came
    assert sorted(sim.book.attendees(oid).tolist()) == sorted([a, b])


def test_a_date_that_does_not_fit_moves_to_a_free_evening(fresh):
    """One of them works every evening but one this week: the date moves day by day until it fits."""
    sim = copy.deepcopy(fresh)
    sim.run_days(1)
    P = sim.w.P
    rom = sim.systems["romance"]
    cand = np.where(P["present"] & ~P["enrolled"] & (P["unit_id"] >= 0) & (P["age"] < 40)
                    & P.is_("rel_status", "single"))[0]
    a, b = int(cand[2]), int(cand[3])
    day0, wd0 = sim.w.day, sim.cal.weekday(sim.w.day)
    P.cols["employed"][a] = True
    P.internal["shift_start"][[a, b]] = -1
    P.internal["shift_end"][[a, b]] = -1
    for d in range(7):
        if d != 3:
            P.internal["shift_start"][a, (wd0 + d) % 7], P.internal["shift_end"][a, (wd0 + d) % 7] = 12 * 60, 22 * 60
    P.cols["ill"][[a, b]] = False
    rom.queue.append((day0, a, b, "restaurant", False, -1))
    sim.run_days(5)
    O = sim.book.occ
    mine = (O["kind"] == _kind(sim, "date")) & (O["organizer"] == a)
    assert mine.any(), "booked once it fit"
    assert int(O["day"][mine][0]) == day0 + 3 and O["status"][mine][0] == STATUS_ID["happened"]


def test_plans_made_weeks_ahead_still_count(fresh):
    """Something planned three weeks ahead by another system (without a created_day) still fills that evening when
    the day comes near: lookups skip only rows too old to matter, whatever days other systems wrote on them."""
    sim = copy.deepcopy(fresh)
    sim.run_days(1)
    occ, book, P = sim.systems["occasions"], sim.book, sim.w.P
    far = sim.w.day + 21
    i = int(np.where(P["present"] & (P["unit_id"] >= 0) & ~P["employed"] & ~P["enrolled"])[0][0])
    u = int(P["unit_id"][i])
    lon, lat = float(sim.w.units.lon[u]), float(sim.w.units.lat[u])
    book.plan("dinner", far, 19 * 60, 120, organizer=i, org_kind="household", ctx=CTX_ID["occasion"], place=u, lon=lon,
              lat=lat, origin="engine")
    sim.run_days(16)
    c = occ.check_window([i], far, 19 * 60 + 30, 60, lon, lat)
    assert not c["feasible"][0] and "hosting" in c["reason"][0]
    assert occ.max_lead >= 21


def test_couples_and_quiet_evenings_show_in_the_choice(ran):
    """Free-time terms for the two evening blocks: a serious relationship pulls evenings away from friends, and someone
    who stayed in for the early evening rarely heads out after 8:15."""
    sim = copy.deepcopy(ran)
    P = sim.w.P
    act = sim.systems["activity"]
    i = int(np.where(P["present"] & (P["n_friends"] > 0))[0][0])
    P.cols["rel_status"][i] = P.code("rel_status", "engaged")
    ch = act.explain_choice(i, 2)
    visit = next(o for o in ch["options"] if o["option"] == 6)
    assert any(t["term"] == "partner" and t["value"] < 0 for t in visit["terms"])
    n = P.n
    act._prev = (np.zeros(n, np.uint8), np.zeros(n, np.uint8), np.full(n, -1, np.int64), np.zeros(n, np.uint8))
    late = act.explain_choice(i, 3)
    visit = next(o for o in late["options"] if o["option"] == 6)
    assert any(t["term"] == "settled" and t["value"] < 0 for t in visit["terms"])


def test_scene_agenda_and_choice(ran):
    from ucsim.analysis.scenes import list_occasions, scene
    O = ran.book.occ
    hosted = (O["kind"] == _kind(ran, "dinner")) & (O["status"] == STATUS_ID["happened"])
    oid = int(O["id"][hosted][np.argmax(O["n_came"][hosted])])
    sc = scene(ran, oid)
    assert sc["kind"] == "dinner" and sc["organizer"] and sc["people"] and sc["came"] >= 2
    p = next(r for r in sc["people"] if r["role"] == "invited")
    assert p["channel"] in ("in_person", "text") and (p["decision"] is None or p["decision"]["factors"])
    assert any(e["type"] == "hosted_gathering" for e in sc["events"])
    lst = list_occasions(ran, day=int(O["day"][hosted][0]))
    assert lst["n"] > 0 and all(r["day"] == int(O["day"][hosted][0]) for r in lst["occasions"])
    org = sc["organizer"]["id"]
    ag = ran.systems["occasions"].agenda(org, int(sc["day"]))
    assert any(o["id"] == oid and o["role"] == "organizer" for o in ag["occasions"])
    assert len(ag["blocks"]) == 4 and ag["free"]
    ch = ran.systems["activity"].explain_choice(org, 2)
    assert ch["computed_now"] and ch["options"][0]["terms"]
    assert abs(sum(o["prob"] for o in ch["options"]) - 1) < 1e-2


def test_occasion_endpoints(ran):
    from fastapi.testclient import TestClient
    from ucsim.api import server
    keep = server.WS.base, server.WS.alt
    try:
        server.WS.base, server.WS.alt = ran, None
        c = TestClient(server.app)
        O = ran.book.occ
        oid = int(O["id"][np.argmax(O["n_came"])])
        r = c.get(f"/api/occasion/{oid}")
        assert r.status_code == 200 and r.json()["id"] == oid
        assert c.get("/api/occasion/99999999").status_code == 404
        lst = c.get("/api/occasions", params={"day": int(O["day"][0])}).json()
        assert lst["n"] >= 1
        i = int(ran.book.attendees(oid)[0])
        assert c.get("/api/occasions", params={"person": i}).json()["n"] >= 1
        d = c.get(f"/api/person/{i}/day").json()
        assert d["person"] == i and len(d["blocks"]) == 4
        ch = c.get(f"/api/person/{i}/choice", params={"block": 3}).json()
        assert ch["block"] == 3 and ch["options"]
    finally:
        server.WS.base, server.WS.alt = keep


def test_same_seed_same_occasions():
    from ucsim.engine.runner import new_simulation
    a = new_simulation(scale=0.02, seed=21).run_days(4)
    b = new_simulation(scale=0.02, seed=21).run_days(4)
    for c in ("kind", "organizer", "day", "start", "n_came"):
        assert np.array_equal(a.book.occ[c], b.book.occ[c]), c
    assert np.array_equal(a.book.inv["response"], b.book.inv["response"])
