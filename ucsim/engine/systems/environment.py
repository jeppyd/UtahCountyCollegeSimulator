"""World environment: calendar flags, weather, economy, interventions."""
from __future__ import annotations

import numpy as np

from ..interventions import InterventionManager


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
            "contracted_housing_required": True,
            # Since fall 2022 the rule covers only single undergrads' first two semesters (freshmen); before, all years.
            "contracted_housing_all_years": False,
            "mission_norm": 1.0,
            "men_initiate_norm": 1.0,
            "church_attendance_norm": 1.0,
            "transit_quality": 1.0,
            "enrollment_index": 1.0,
            "social_media_intensity": 1.0,
            "marriage_norm": 1.0,
        }
        w.env.update(self.base)
        self.manager = InterventionManager(sim, sim.interventions)
        self.market_rent = 1.0

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

    def _flags(self):
        sim, w = self.sim, self.sim.w
        d = w.day
        cal = sim.cal
        env = w.env
        noise = sim.streams.normal("weather", d, 1)[0]
        env["temp_f"] = cal.temp_f(d) + 7.0 * noise + env["temp_delta"]
        env["weekday"] = cal.weekday(d)
        env["holiday"] = cal.holiday(d)
        env["conference"] = cal.is_conference_weekend(d)
        for school in ("BYU", "UVU"):
            term = cal.term(school, d)
            env[f"term_{school}"] = term
            prog = cal.term_progress(school, d)
            env[f"term_progress_{school}"] = prog
            env[f"exam_week_{school}"] = bool(term and prog > 0.9) or bool(term and 0.45 < prog < 0.52)
        env["date"] = str(cal.date(d))
        env["month"] = cal.date(d).month
        env["outdoor_appeal"] = float(np.clip(1 - abs(env["temp_f"] - 72) / 35, 0.05, 1.0))
