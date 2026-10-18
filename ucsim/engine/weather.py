"""Provo's weather, day by day, from real observations (NOAA GHCN-Daily, station PROVO BYU; config/sources/
weather_provo_daily.csv).

The simulation runs in 2026–27, past the data, so a world replays a chosen *weather year* (August–July): by default
the most recent complete one; set `weather.year` in world.yaml, the UCSIM_WEATHER_YEAR environment variable, or the
world variable env['weather_year'] (a What-if can: "replay the snowy winter of 2022–23"). Later simulated years
step back through earlier weather years. Missing observations are filled from the climate normals in world.yaml and
flagged. Pure lookup: no random numbers.
"""
from __future__ import annotations

import csv
import datetime as dt
import os
from functools import lru_cache
from pathlib import Path

import numpy as np

DATA = Path(__file__).resolve().parent.parent / "config" / "sources" / "weather_provo_daily.csv"
FIELDS = ("tmax_f", "tmin_f", "precip_in", "snow_in", "snow_depth_in")


@lru_cache(maxsize=1)
def _load(path: str = str(DATA)) -> dict[dt.date, dict]:
    out = {}
    with open(path, newline="") as fh:
        for r in csv.DictReader(fh):
            out[dt.date.fromisoformat(r["date"])] = {k: (float(r[k]) if r[k] != "" else None) for k in FIELDS}
    return out


def years_available() -> list[int]:
    """Weather years (by their fall year) with a full August–July of observations."""
    days = _load()
    ys = sorted({d.year if d.month >= 8 else d.year - 1 for d in days})
    return [y for y in ys if dt.date(y, 8, 1) in days and dt.date(y + 1, 7, 31) in days]


def default_year(cfg: dict | None = None) -> int:
    ys = years_available()
    want = os.environ.get("UCSIM_WEATHER_YEAR") or ((cfg or {}).get("weather") or {}).get("year")
    if want not in (None, "", "latest"):
        y = int(str(want)[:4])
        if y in ys:
            return y
    return ys[-1]


def label(w: dict) -> str:
    """The day in a word or two."""
    hi, rain, snow = w["tmax_f"], w["precip_in"], w["snow_in"]
    if snow >= 3:
        return "snowstorm"
    if snow >= 0.5:
        return "snow"
    if rain >= 0.25:
        return "heavy rain" if hi > 34 else "snow"
    if rain >= 0.05:
        return "rain"
    if hi >= 95:
        return "hot"
    if hi <= 28:
        return "bitter cold"
    if hi <= 40:
        return "cold"
    return "clear"


class Weather:
    def __init__(self, cfg: dict, start: dt.date):
        self.cfg = cfg
        self.start = start
        self.high = np.array(cfg["climate"]["high_f"], float)
        self.low = np.array(cfg["climate"].get("low_f", [h - 28 for h in cfg["climate"]["high_f"]]), float)
        self.year0 = default_year(cfg)
        self.sim_year0 = start.year if start.month >= 8 else start.year - 1

    def year_for(self, d: dt.date, chosen: int | None = None) -> int:
        """The weather year a simulated date replays: the chosen one for the first simulated year, then earlier ones."""
        ys = years_available()
        y0 = chosen if chosen in ys else self.year0
        k = (d.year if d.month >= 8 else d.year - 1) - self.sim_year0
        return ys[(ys.index(y0) - k) % len(ys)]

    def _normal(self, d: dt.date, arr) -> float:
        m, frac = d.month - 1, (d.day - 1) / 30.0
        return float(arr[m] * (1 - frac) + arr[(m + 1) % 12] * frac)

    def on(self, d: dt.date, chosen: int | None = None) -> dict:
        """The observed weather replayed on simulated date d (°F and inches), with its weather year and gap flags."""
        wy = self.year_for(d, chosen)
        md = (d.month, min(d.day, 28) if d.month == 2 and d.day == 29 else d.day)
        src = dt.date(wy if md[0] >= 8 else wy + 1, *md)
        obs = _load().get(src, {})
        out, filled = {}, []
        for k in FIELDS:
            v = obs.get(k)
            if v is None:
                filled.append(k)
                v = self._normal(d, self.high) if k == "tmax_f" else self._normal(d, self.low) if k == "tmin_f" else 0.0
            out[k] = float(v)
        out["label"] = label(out)
        out["weather_year"] = wy
        out["source_date"] = str(src)
        out["filled"] = filled
        return out
