"""The real Provo calendar and observed weather: published dates resolve, rules give plausible later years, terms /
finals / no-class days are right, the weather replays the chosen year, and calendar occasions are planned on their
days (the same way in every run)."""
import datetime as dt

import numpy as np
import pytest

from ucsim.engine.calendar_real import RealCalendar
from ucsim.engine.weather import Weather, years_available

D = dt.date


@pytest.fixture(scope="module")
def cal():
    return RealCalendar()


def test_published_terms(cal):
    assert cal.term("BYU", D(2026, 9, 1)) is None and cal.term("BYU", D(2026, 9, 2)) == "Fall"      # BYU starts Sep 2
    assert cal.term("UVU", D(2026, 8, 19)) == "Fall" and cal.term("UVU", D(2026, 8, 18)) is None
    assert cal.in_finals("BYU", D(2026, 12, 14)) and not cal.in_finals("BYU", D(2026, 12, 10))
    assert cal.in_finals("UVU", D(2026, 12, 8))
    assert cal.term("BYU", D(2026, 12, 20)) is None and cal.term("BYU", D(2027, 1, 6)) == "Winter"
    assert cal.term("BYU", D(2027, 8, 12)) == "Summer"                 # a summer term reaching into August
    assert cal.term("UVU", D(2027, 1, 11)) == "Spring"


def test_no_class_and_holidays(cal):
    assert cal.no_class("BYU", D(2026, 9, 7)) and cal.holiday(D(2026, 9, 7))          # Labor Day
    assert not cal.no_class("BYU", D(2026, 9, 8))
    assert cal.no_class("UVU", D(2026, 10, 16)) and not cal.no_class("BYU", D(2026, 10, 16))   # UVU fall break
    assert cal.no_class("BYU", D(2026, 11, 26)) and cal.travel_home_likely(D(2026, 11, 27))
    assert not cal.holiday(D(2026, 10, 31))                              # Halloween: an item, not a day off
    assert cal.conference(D(2026, 10, 3)) and cal.conference(D(2026, 10, 4)) and not cal.conference(D(2026, 10, 10))


def test_items_have_basis_and_sources(cal):
    items = cal.items_between(D(2026, 8, 1), D(2027, 7, 31))
    assert {"real", "rule", "hypothetical"} <= {it.basis for it in items}
    assert all(it.source and it.source.startswith("http") for it in items if it.basis == "real")
    games = [it for it in items if it.kind == "football"]
    assert len(games) == 7 and games[0].start == D(2026, 9, 5) and all(it.place for it in games)
    devos = [it for it in items if it.kind == "devotional"]
    assert devos and all(it.start.weekday() == 1 and it.time == "11:05" for it in devos)



def test_published_events(cal):
    """Dates and times the schools published replace assumed ones: kickoff times, the Fall devotional/forum schedule
    (no devotional Thanksgiving week), basketball home games as occasions."""
    items = cal.items_between(D(2026, 8, 1), D(2027, 7, 31))
    by_id = {it.id: it for it in items}
    assert by_id["fb_utah_tech"].time == "18:00" and by_id["fb_iowa_state"].time == "20:15"
    fall = [it for it in items if it.kind == "devotional" and D(2026, 9, 1) <= it.start <= D(2026, 12, 31)]
    assert len(fall) == 12 and all(it.basis == "real" for it in fall)
    assert D(2026, 11, 24) not in {it.start for it in fall}
    assert D(2026, 10, 6) not in {it.start for it in fall}               # Homecoming's opening ceremony instead
    assert {it.label for it in fall} == {"BYU devotional", "BYU forum"}
    winter = [it for it in items if it.kind == "devotional" and it.start.year == 2027]
    assert winter and all(it.basis == "rule" for it in winter)        # Winter 2027's schedule isn't published
    games = [it for it in items if it.kind == "basketball"]
    assert len(games) > 20 and all(it.time and it.place for it in games)
    assert {it.effects["occasion"]["kind"] for it in games} == {"basketball_game", "uvu_basketball_game"}


def test_round3_events(cal):
    """Round 3 research: the published Homecoming week (its opening ceremony at 11:00, socials and the formal dance as
    occasions), BYU women's home games, UVU's real spring break and Summer semester."""
    items = cal.items_between(D(2026, 8, 1), D(2027, 7, 31))
    by_id = {it.id: it for it in items}
    assert by_id["byu_homecoming"].basis == "real" and by_id["byu_homecoming"].start == D(2026, 10, 6)
    assert by_id["hc_opening"].time == "11:00" and by_id["hc_opening"].effects["occasion"]["kind"] == "devotional"
    assert by_id["hc_dance"].effects["occasion"]["kind"] == "homecoming_dance" and by_id["hc_dance"].start == D(2026, 10, 10)
    women = [it for it in items if it.kind == "womens_sports"]
    assert len(women) > 35 and all(it.time and it.place and it.basis == "real" for it in women)
    assert cal.no_class("UVU", D(2027, 3, 21)) and cal.term("UVU", D(2027, 5, 10)) == "Summer"
    assert cal.term("UVU", D(2027, 8, 13)) == "Summer"

def test_rule_years_are_plausible(cal):
    for y in (2027, 2028, 2031):
        Y = cal.year(y)
        byu = {t.name: t for t in Y.terms["BYU"]}
        assert [t.name for t in Y.terms["BYU"]] == ["Fall", "Winter", "Spring", "Summer"]
        assert D(y, 8, 28) <= byu["Fall"].start <= D(y, 9, 6) and byu["Fall"].start.weekday() == 2
        assert byu["Fall"].finals_end < byu["Winter"].start < byu["Spring"].start < byu["Summer"].start
        ids = {it.id for it in Y.items}
        assert {"labor_day", "thanksgiving", "conference_oct", "conference_apr", "christmas_break"} <= ids
        th = next(it for it in Y.items if it.id == "thanksgiving")
        assert th.start.weekday() == 3 and 22 <= th.start.day <= 28
    # UVU's published Summer 2028 start (Wed May 10) comes out of the rule
    assert next(t for t in cal.year(2027).terms["UVU"] if t.name == "Summer").start == D(2028, 5, 10)


def test_weather_years():
    ys = years_available()
    assert ys[0] == 2015 and ys[-1] >= 2025
    cfg = {"climate": {"high_f": [38, 44, 54, 61, 71, 82, 91, 89, 79, 65, 50, 39]}}
    W = Weather(cfg, D(2026, 8, 24))
    jan = W.on(D(2027, 1, 15))
    assert jan["weather_year"] == ys[-1] and jan["source_date"] == f"{ys[-1] + 1}-01-15"
    assert -20 < jan["tmin_f"] <= jan["tmax_f"] < 70
    snowy = W.on(D(2027, 1, 15), chosen=2022)
    assert snowy["weather_year"] == 2022 and snowy["source_date"] == "2023-01-15"
    assert W.on(D(2027, 9, 1))["weather_year"] == ys[-2]              # the next simulated year steps back
    # winter 2022–23 was snowy in Provo: more snow on the ground than the default year
    depth = lambda y: sum(W.on(D(2027, 1, 1) + dt.timedelta(days=k), chosen=y)["snow_depth_in"] for k in range(59))
    assert depth(2022) > depth(ys[-1])


def test_environment_and_occasions(ran):
    sim = ran
    env = sim.w.env
    for k in ("tmax_f", "tmin_f", "precip_in", "snow_in", "snow_depth_in", "weather_label", "weather_penalty",
              "calendar_items", "no_class", "finals_BYU", "finals_UVU", "temp_f", "outdoor_appeal", "exam_week_BYU"):
        assert k in env
    O = sim.book.occ
    fb = sim.book.kind_id["football_game"]
    days = sorted(int(d) for d in O["day"][O["kind"] == fb])
    assert days == [(D(2026, 9, 5) - sim.cal.start).days, (D(2026, 9, 12) - sim.cal.start).days]
    devo = O["kind"] == sim.book.kind_id["devotional"]
    assert devo.any() and all(sim.cal.weekday(int(d)) == 1 for d in O["day"][devo])
    from ucsim.engine.ledger import ORIGIN_ID
    assert (O["origin"][O["kind"] == fb] == ORIGIN_ID["calendar"]).all()
    # people went: a sizeable minority of enrolled BYU students, nobody from outside the audience
    from ucsim.analysis.scenes import occasion_row
    r = occasion_row(sim, int(O["id"][O["kind"] == fb][0]))
    P = sim.w.P
    byu = int(((P["school"] == 1) & P["enrolled"] & P["present"]).sum())
    assert 0.08 * byu < r["came"] < 0.5 * byu


def test_determinism():
    from ucsim.engine.runner import new_simulation
    a, b = new_simulation(scale=0.02, seed=5), new_simulation(scale=0.02, seed=5)
    a.run_days(13), b.run_days(13)
    fa, fb = a.book.occ, b.book.occ
    k = a.book.kind_id["football_game"]
    assert fa.n == fb.n and np.array_equal(fa["day"][fa["kind"] == k], fb["day"][fb["kind"] == k])
    assert a.w.env["tmax_f"] == b.w.env["tmax_f"]


def test_api(ran):
    from fastapi.testclient import TestClient
    from ucsim.api import server
    old = server.WS.base
    server.WS.base = ran
    try:
        cl = TestClient(server.app)
        r = cl.get("/api/calendar/items", params={"frm": 0, "to": 120}).json()
        assert any(it["id"] == "fb_notre_dame" and it["basis"] == "real" for it in r["items"])
        assert {t["school"] for t in r["terms"]} == {"BYU", "UVU"}
        w = cl.get("/api/calendar/weather", params={"frm": 0, "to": 30}).json()
        assert len(w["days"]) == 31 and w["weather_year"] in w["years_available"]
        c = cl.get("/api/calendar").json()
        assert any(s["kind"] == "term" for s in c["segments"])
    finally:
        server.WS.base = old
