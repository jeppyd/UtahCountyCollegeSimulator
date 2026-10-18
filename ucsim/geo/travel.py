"""Travel times between places in Provo and Orem (docs/EVOLUTION.md §4).

This is the interface the engine uses. Until the zone matrices (`ucsim/geo/data/travel.npz`, built by
`scripts/build_travel.py` from the street network and UTA's GTFS feed) exist, it falls back to straight-line
estimates with typical speeds, a detour factor and parking time, and says so (`TravelModel.source`).
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

DATA = Path(__file__).resolve().parent / "data" / "travel.npz"
MODES = ("walk", "bike", "car", "transit", "ride")
MODE_ID = {m: i for i, m in enumerate(MODES)}
KM_PER_DEG_LON = 85.0   # at Provo's latitude
KM_PER_DEG_LAT = 111.0


def km_between(lon1, lat1, lon2, lat2) -> np.ndarray:
    return np.hypot((np.asarray(lon1) - lon2) * KM_PER_DEG_LON, (np.asarray(lat1) - lat2) * KM_PER_DEG_LAT)


class TravelModel:
    """Door-to-door minutes for a trip. Vectorized over people."""

    WALK_KMH, BIKE_KMH, CAR_KMH = 4.8, 14.0, 38.0
    DETOUR = 1.3          # street distance / straight-line distance

    def __init__(self, world):
        self.w = world
        self.source = "straight-line estimate (travel matrices not built yet)"

    def trip(self, people, dest_lon, dest_lat, weekday: int, minute, ride=None, origin_lon=None, origin_lat=None):
        """(minutes, mode index) for each person from where they are (or `origin_*`) to the destination."""
        P = self.w.P
        people = np.atleast_1d(np.asarray(people, np.int64))
        olon = P["home_lon"][people] if origin_lon is None else np.broadcast_to(origin_lon, people.shape)
        olat = P["home_lat"][people] if origin_lat is None else np.broadcast_to(origin_lat, people.shape)
        km = km_between(olon, olat, dest_lon, dest_lat) * self.DETOUR
        walk = km / self.WALK_KMH * 60
        car_ok = P["owns_car"][people].astype(bool) if "owns_car" in P else np.zeros(len(people), bool)
        if ride is not None:
            car_ok = car_ok | np.broadcast_to(np.asarray(ride, bool), people.shape)
        car = km / self.CAR_KMH * 60 + 6.0     # parking and walking to the door
        bike = km / self.BIKE_KMH * 60
        best = np.where(car_ok, np.minimum(car, walk), np.minimum(walk, bike * 1.15))
        mode = np.where(car_ok & (car <= walk), MODE_ID["ride"] if ride is not None else MODE_ID["car"],
                        np.where(walk <= bike * 1.15, MODE_ID["walk"], MODE_ID["bike"]))
        snow = float(self.w.env.get("snow_in", 0.0) or 0.0)
        if snow > 0:
            best = best * (1.0 + min(0.5, 0.08 * snow))
        return best.astype(np.float32), mode.astype(np.int8)
