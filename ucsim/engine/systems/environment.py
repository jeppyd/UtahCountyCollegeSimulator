"""World environment: calendar flags (the real Provo calendar), observed weather, economy, interventions."""
from __future__ import annotations

import numpy as np

from ..interventions import InterventionManager
from ..weather import Weather


def _in_building(pl: dict) -> tuple[float, float]:
    """A calendar place's point inside its real building (engine/places.py): by name (the stadium's grandstand, the
    Marriott Center), else the building at or nearest the point."""
    lon, lat = float(pl.get("lon", np.nan)), float(pl.get("lat", np.nan))
    from .. import places
    if not places.available() or not np.isfinite(lon):
        return lon, lat
    b = places.named(pl.get("name", "")) if pl.get("name") else -1
    if b < 0 and pl.get("name"):
        b = places.by_name(pl["name"])
    if b >= 0:
        return places.anchor(b)
    lo, la, _ = places.settle([lon], [lat])
    return float(lo[0]), float(la[0])


class Environment:
    def __init__(self, sim):
        self.sim = sim
        w = sim.w
        cfg = w.cfg
        self.base = {
            "temp_delta": 0.0,
            "unemployment": cfg["economy"]["unemployment"],
            "wage_index": 1.0,
            "rent_index": 1.0,
            "rent_shock": 1.0,
            "housing_supply_index": 1.0,
            "tuition_byu": cfg["tuition"]["byu_lds_semester"],
            "tuition_uvu": cfg["tuition"]["uvu_semester"],
            "app_appeal": 1.0,
            "coffee_permitted": False,
            "alcohol_permitted": False,
            "contracted_housing_required": True,
            # Since fall 2022 the rule covers only single undergrads' first two semesters (freshmen); before, all years.
            "contracted_housing_all_years": False,
            # BYU Honor Code (engine/systems/honor.py): how strongly it is enforced, and whether an endorsement is required
            "honor_enforcement": 1.0,
            "endorsement_required": True,
            "interfaith_welcome": 0.0,
            "mission_norm": 1.0,
            "men_initiate_norm": 1.0,
            "church_attendance_norm": 1.0,
            "transit_quality": 1.0,
            "enrollment_index": 1.0,
            "social_media_intensity": 1.0,
            "marriage_norm": 1.0,
            # which observed weather year (fall year) this world replays; a What-if may set another
            "weather_year": 0,
        }
        w.env.update(self.base)
        self.manager = InterventionManager(sim, sim.interventions)
        self.market_rent = 1.0
        self.weather = Weather(cfg, sim.cal.start)
        self.base["weather_year"] = self.weather.year0
        w.env["weather_year"] = self.weather.year0

    def init(self):
        self._flags()

    def daily(self):
        sim, w = self.sim, self.sim.w
        d = w.day
        env = w.env
        # environment variables reset to base then interventions applied (ramps/durations)
        for k, v in self.base.items():
            env[k] = v
        env["rent_index"] = self.market_rent
        self.manager.apply_world(self.base, env, d)
        self.manager.apply_params(d)
        self.manager.apply_agents(d)
        self._flags()
        self._calendar_occasions(d)

    def _flags(self):
        sim, w = self.sim, self.sim.w
        d = w.day
        cal = sim.cal
        env = w.env
        p = sim.p
        date = cal.date(d)
        wx = self.weather.on(date, int(env.get("weather_year") or 0) or None)
        for k in ("tmax_f", "tmin_f", "precip_in", "snow_in", "snow_depth_in"):
            env[k] = wx[k]
        env["weather_label"] = wx["label"]
        env["weather_year_used"] = wx["weather_year"]
        env["weather_filled"] = bool(wx["filled"])
        # the old daytime temperature: the observed high (plus any What-if warming)
        env["temp_f"] = wx["tmax_f"] + env["temp_delta"]
        env["weekday"] = cal.weekday(d)
        env["holiday"] = cal.holiday(d)
        env["conference"] = cal.is_conference_weekend(d)
        items = cal.items_on(d)
        env["calendar_items"] = [it.id for it in items]
        env["travel_home_likely"] = any(it.effects.get("travel_home_likely") for it in items)
        for school in ("BYU", "UVU"):
            term = cal.term(school, d)
            env[f"term_{school}"] = term
            prog = cal.term_progress(school, d)
            env[f"term_progress_{school}"] = prog
            env[f"finals_{school}"] = cal.in_finals(school, d)
            env[f"no_class_{school}"] = cal.no_class(school, d)
            # exam pressure: the real finals, and midterms (approximated from term progress)
            env[f"exam_week_{school}"] = env[f"finals_{school}"] or bool(term and 0.45 < prog < 0.52)
        env["no_class"] = env["no_class_BYU"] and env["no_class_UVU"]
        env["date"] = str(date)
        env["month"] = date.month
        rain = wx["precip_in"] >= 0.05 and wx["snow_in"] < 0.5
        snow = min(wx["snow_in"], 6.0) / 6.0
        env["outdoor_appeal"] = float(np.clip(1 - abs(env["temp_f"] - 72) / 35, 0.05, 1.0)
                                      * (1 - p("weather.outdoor.rain") * rain) * (1 - p("weather.outdoor.snow") * snow))
        env["weather_penalty"] = float(p("weather.going_out.cold") * max(0.0, 35 - wx["tmin_f"]) / 20
                                       + p("weather.going_out.snow") * snow + p("weather.going_out.rain") * rain)

    def _calendar_occasions(self, d: int):
        """Plan today's calendar events that people go to (home football games, devotionals, Stadium of Fire) as open
        occasions; the occasions system settles who goes. Planned once per day and place, in both worlds alike."""
        sim = self.sim
        book = getattr(sim, "book", None)
        if book is None:
            return
        O = book.occ
        have = set(O["label"][O["day"] == d].tolist()) if O.n else set()
        for it in sim.cal.items_on(d):
            occ = it.effects.get("occasion")
            if not occ or occ.get("kind") not in book.kind_id:
                continue
            kind = occ["kind"]
            label = it.label
            if book.label_id(label) in have:
                continue
            spec = book.vocab[kind]
            start = it.minutes()
            if start is None:
                hh, mm = str(spec.get("start", "19:00")).split(":")
                start = int(hh) * 60 + int(mm)
            pl = it.place or {}
            lon, lat = _in_building(pl)
            book.plan(kind, d, start, int(spec.get("dur", 120)), lon=lon, lat=lat,
                      origin="calendar", open_=True, label=label, capacity=int(spec.get("capacity", -1)))
