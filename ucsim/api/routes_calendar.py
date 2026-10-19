"""The Provo calendar and weather for the workbench: dated items (with their basis and source), terms and finals per
school, and the observed weather each simulated day replays. Read-only; /api/calendar (the time ribbon) stays in
server.py."""
from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, HTTPException

router = APIRouter()


def _server():
    from .routes_trace import _server as s
    return s()


def _window(sim, frm: int | None, to: int | None) -> tuple[int, int]:
    a = sim.w.day - 28 if frm is None else int(frm)
    b = sim.w.day + 56 if to is None else int(to)
    if b < a:
        raise HTTPException(400, "'to' is before 'from'")
    return a, min(b, a + 800)


@router.get("/api/calendar/items")
def calendar_items(u: str = "base", frm: int | None = None, to: int | None = None, kinds: str = ""):
    """Calendar items between two simulation days (default: four weeks back to eight ahead), with terms and finals."""
    WS, jresp = _server()
    sim = WS.sim(u)
    cal = sim.cal
    a, b = _window(sim, frm, to)
    da, db = cal.date(a), cal.date(b)
    want = {k for k in kinds.split(",") if k}
    items = []
    for it in cal.real.items_between(da, db):
        if want and it.kind not in want:
            continue
        r = it.to_dict()
        r["day"], r["end_day"] = (it.start - cal.start).days, (it.end - cal.start).days
        items.append(r)
    terms = [{"school": t.school, "name": t.name, "basis": t.basis, "source": t.source,
              "start": (t.start - cal.start).days, "classes_end": (t.classes_end - cal.start).days,
              "finals_start": (t.finals_start - cal.start).days, "end": (t.finals_end - cal.start).days}
             for t in cal.real.terms_between(da, db)]
    return jresp({"from": a, "to": b, "today": sim.w.day, "start_date": str(cal.start), "items": items, "terms": terms,
                  "basis_words": {"real": "published date (with source)", "rule": "a recurring rule (exact date not yet published)",
                                  "hypothetical": "our estimate (nothing published)"}})


@router.get("/api/calendar/weather")
def calendar_weather(u: str = "base", frm: int | None = None, to: int | None = None):
    """The daily weather series between two simulation days: the observed Provo weather each day replays."""
    from ..engine.weather import years_available
    WS, jresp = _server()
    sim = WS.sim(u)
    a, b = _window(sim, frm, to)
    env = sim.w.env
    wx = sim.systems["environment"].weather
    chosen = int(env.get("weather_year") or 0) or None
    rows = []
    for d in range(a, b + 1):
        r = wx.on(sim.cal.date(d), chosen)
        rows.append({"day": d, "date": str(sim.cal.date(d)), **{k: r[k] for k in ("tmax_f", "tmin_f", "precip_in", "snow_in", "snow_depth_in")},
                     "label": r["label"], "weather_year": r["weather_year"], "filled": r["filled"]})
    y = wx.year_for(sim.cal.date(sim.w.day), chosen)
    return jresp({"from": a, "to": b, "today": sim.w.day, "days": rows, "weather_year": y, "weather_year_label": f"{y}–{str(y + 1)[2:]}",
                  "years_available": years_available(),
                  "source": "NOAA NCEI GHCN-Daily, station PROVO BYU (USC00427064); public domain",
                  "note": "The simulation runs past the data, so each world replays an observed year of Provo weather; "
                          "missing observations are filled from monthly normals (listed under 'filled')."})
