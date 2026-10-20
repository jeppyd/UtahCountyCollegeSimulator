"""Travel times between places in Provo and Orem (docs/EVOLUTION.md §4).

`ucsim/geo/data/travel.npz` (built by `scripts/build_travel.py` from UGRC's street network and UTA's GTFS feed) holds
73 zones — the 57 official neighborhoods, BYU and UVU campus and the outer areas people live in or go to — with a
raster that maps any point to its zone, and zone-to-zone street km (walking), driving minutes off-peak and at the
evening peak, and UTA door-to-door transit minutes for a weekday, Saturday and Sunday at four departure times.

A trip keeps its own end points: the straight-line distance between them times the street detour of their zone pair
(network km ÷ straight km), at each mode's speed (driving: the pair's minutes per km), plus parking and the walk to the
door at the destination (longer at BYU and UVU). Transit is the zone pair's door-to-door time, when UTA runs then.

Labelled assumptions (not data): who bikes (BIKER_SHARE of people without a car, fixed per person), parking minutes,
the parking hassle that weighs on choosing to drive (CHOICE_PENALTY, highest at BYU) and the wait on choosing
transit (TRANSIT_PENALTY; no bus under TRANSIT_MIN_KM), snow slowing walking, biking and
driving (and pushing bikers to walk). Without travel.npz it falls back to
straight-line estimates and says so (`TravelModel.source`).
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

DATA = Path(__file__).resolve().parent / "data" / "travel.npz"
MODES = ("walk", "bike", "car", "transit", "ride")
MODE_ID = {m: i for i, m in enumerate(MODES)}
KM_PER_DEG_LON = 85.0   # at Provo's latitude
KM_PER_DEG_LAT = 111.0
BINS = (480, 750, 1050, 1230)
# minutes from parking to the door at the destination (BYU: the Y lots are 10+ minutes' walk from the heart of campus,
# Daily Universe; UVU's garages are closer; downtown street parking) — labelled assumptions
PARK_MIN = {"BYU campus": 9.0, "UVU campus": 6.0, "Downtown (Provo)": 3.0}
PARK_DEFAULT = 1.5
CAR_OUT = 1.0          # from the door to the car at home
# when choosing a mode, driving counts these extra minutes (permits, cost, hunting for a spot) — choice only, not time.
# BYU: ~7,000 Y-lot spaces for ~33,000 students (Daily Universe 2017) keeps most students who live near campus on foot.
CHOICE_PENALTY = {"BYU campus": 12.0, "UVU campus": 4.0, "Downtown (Provo)": 4.0}
CHOICE_DEFAULT = 2.0
TRANSIT_PENALTY = 6.0  # choice only: the wait feels longer than it is, and the schedule has to fit
TRANSIT_MIN_KM = 1.2   # nobody rides the bus for a walk across a few blocks
BIKER_SHARE = 0.12     # of people without a car (no survey item on bikes)


def km_between(lon1, lat1, lon2, lat2) -> np.ndarray:
    return np.hypot((np.asarray(lon1) - lon2) * KM_PER_DEG_LON, (np.asarray(lat1) - lat2) * KM_PER_DEG_LAT)


def _bin(minute) -> np.ndarray:
    m = np.asarray(minute, float) % 1440
    return np.abs(m[..., None] - np.array(BINS)).argmin(axis=-1)


def _day(weekday) -> np.ndarray:
    wd = np.asarray(weekday, int) % 7
    return np.where(wd == 6, 2, np.where(wd == 5, 1, 0))


class TravelModel:
    """Door-to-door minutes for a trip. Vectorized over people."""

    WALK_KMH, BIKE_KMH, CAR_KMH = 4.8, 14.0, 38.0
    DETOUR = 1.3          # street distance / straight-line distance (fallback, and trips within one zone)

    def __init__(self, world, path: Path | None = None):
        self.w = world
        path = path or DATA
        self.ok = path.exists()
        if not self.ok:
            self.source = "straight-line estimate (travel matrices not built yet: run scripts/build_travel.py)"
            return
        d = np.load(path, allow_pickle=False)
        self.names = [str(x) for x in d["names"]]
        self.raster = d["raster"].astype(np.int32)
        self.bbox = d["bbox"].astype(float)
        self.cell = d["cell"].astype(float)
        self.centroid = d["centroid"].astype(float)
        straight = np.maximum(d["straight_km"].astype(float), 0.3)
        self.detour_walk = np.clip(d["walk_km"] / straight, 1.05, 2.5)
        self.detour_car = np.clip(d["car_km"] / straight, 1.05, 2.5)
        car_km = np.maximum(d["car_km"].astype(float), 0.3)
        self.car_min_km = np.stack([np.clip(d["car_off"] / car_km, 0.9, 4.0), np.clip(d["car_peak"] / car_km, 0.9, 4.5)])
        np.fill_diagonal(self.detour_walk, self.DETOUR)
        np.fill_diagonal(self.detour_car, self.DETOUR)
        for k in range(2):
            np.fill_diagonal(self.car_min_km[k], 60 / 30)       # within a zone: ~30 km/h on local streets
        self.transit = d["transit"].astype(np.float32)          # (day, bin, from, to) minutes, NaN = no service
        self.park = np.array([PARK_MIN.get(n, PARK_DEFAULT) for n in self.names], np.float32)
        self.hassle = np.array([CHOICE_PENALTY.get(n, CHOICE_DEFAULT) for n in self.names], np.float32)
        self.meta = json.loads(str(d["meta"]))
        t = self.meta.get("transit", {})
        self.source = (f"street network (UGRC) and UTA GTFS {t.get('feed_version', '')} "
                       f"({t.get('feed_start', '')}–{t.get('feed_end', '')}), {len(self.names)} zones")

    # ------------------------------------------------------------------ zones
    def zone_of(self, lon, lat) -> np.ndarray:
        """Zone index of each point (points outside the area take the nearest edge cell's zone)."""
        if not self.ok:
            return np.zeros(np.shape(np.atleast_1d(lon)), np.int32)
        ny, nx = self.raster.shape
        ix = np.clip(((np.asarray(lon, float) - self.bbox[0]) / self.cell[0]).astype(np.int64), 0, nx - 1)
        iy = np.clip(((np.asarray(lat, float) - self.bbox[1]) / self.cell[1]).astype(np.int64), 0, ny - 1)
        return self.raster[iy, ix]

    def matrix(self, mode: str, weekday: int, minute: int) -> np.ndarray:
        """Zone-centroid to zone-centroid minutes by one mode (NaN where it isn't available)."""
        if not self.ok:
            raise RuntimeError(self.source)
        c = self.centroid
        km = km_between(c[:, 0:1], c[:, 1:2], c[None, :, 0], c[None, :, 1])
        if mode == "walk":
            return (km * self.detour_walk / self.WALK_KMH * 60).astype(np.float32)
        if mode == "bike":
            return (km * self.detour_walk / self.BIKE_KMH * 60).astype(np.float32)
        if mode in ("car", "ride"):
            peak = int(_day(weekday) == 0 and _bin(minute) == 2)
            return (CAR_OUT + km * self.detour_car * self.car_min_km[peak] + self.park[None]).astype(np.float32)
        if mode == "transit":
            return self.transit[int(_day(weekday)), int(_bin(minute))].copy()
        raise ValueError(f"unknown mode {mode}")

    # ------------------------------------------------------------------ trips
    def modes(self, olon, olat, dlon, dlat, weekday, minute) -> dict[str, np.ndarray]:
        """Minutes by every mode for each trip (NaN where a mode isn't available)."""
        olon, olat, dlon, dlat = np.broadcast_arrays(*(np.asarray(x, float) for x in (olon, olat, dlon, dlat)))
        km = km_between(olon, olat, dlon, dlat)
        snow = float(self.w.env.get("snow_in", 0.0) or 0.0) if self.w is not None else 0.0
        slow_walk = 1.0 + min(0.4, 0.06 * snow)
        slow_bike = 1.0 + min(0.6, 0.10 * snow)
        slow_car = 1.0 + min(0.35, 0.05 * snow)
        if not self.ok:
            walk = km * self.DETOUR / self.WALK_KMH * 60
            return {"walk": walk * slow_walk, "bike": km * self.DETOUR / self.BIKE_KMH * 60 * slow_bike,
                    "car": (km * self.DETOUR / self.CAR_KMH * 60 + 6.0) * slow_car, "transit": np.full(km.shape, np.nan)}
        zo, zd = self.zone_of(olon, olat), self.zone_of(dlon, dlat)
        wk = km * self.detour_walk[zo, zd]
        day = np.broadcast_to(_day(weekday), km.shape)
        b = np.broadcast_to(_bin(minute), km.shape)
        peak = ((day == 0) & (b == 2)).astype(np.int64)
        car = CAR_OUT + km * self.detour_car[zo, zd] * self.car_min_km[peak, zo, zd] + self.park[zd]
        transit = self.transit[day, b, zo, zd].astype(float)
        transit = np.where(zo == zd, np.nan, transit)                   # nobody takes the bus within a neighborhood
        return {"walk": wk / self.WALK_KMH * 60 * slow_walk, "bike": wk / self.BIKE_KMH * 60 * slow_bike,
                "car": car * slow_car, "transit": transit}

    def bikes(self, people: np.ndarray) -> np.ndarray:
        """Who rides a bike (no survey item: BIKER_SHARE of people without a car, fixed per person)."""
        h = (people.astype(np.uint64) * np.uint64(2654435761)) % np.uint64(1000)
        return h < np.uint64(int(BIKER_SHARE * 1000))

    def trip(self, people, dest_lon, dest_lat, weekday: int, minute, ride=None, origin_lon=None, origin_lat=None):
        """(minutes, mode index) for each person from home (or `origin_*`) to the destination, by their best mode."""
        P = self.w.P
        people = np.atleast_1d(np.asarray(people, np.int64))
        olon = P["home_lon"][people] if origin_lon is None else np.broadcast_to(origin_lon, people.shape)
        olat = P["home_lat"][people] if origin_lat is None else np.broadcast_to(origin_lat, people.shape)
        dlon = np.broadcast_to(np.asarray(dest_lon, float), people.shape)
        dlat = np.broadcast_to(np.asarray(dest_lat, float), people.shape)
        m = self.modes(olon, olat, dlon, dlat, weekday, minute)
        car_ok = P["owns_car"][people].astype(bool) if "owns_car" in P else np.zeros(len(people), bool)
        ride_ok = np.broadcast_to(np.asarray(ride, bool), people.shape) if ride is not None else np.zeros(len(people), bool)
        snow = float(self.w.env.get("snow_in", 0.0) or 0.0)
        bike_ok = ~car_ok & self.bikes(people) & (snow < 2.0)          # most bikers walk or ride the bus in snow
        INF = np.float64(1e9)
        times = np.stack([m["walk"],
                          np.where(bike_ok, m["bike"], INF),
                          np.where(car_ok, m["car"], INF),
                          np.where(np.isfinite(m["transit"]), m["transit"], INF),
                          np.where(ride_ok & ~car_ok, m["car"], INF)], axis=1)
        cost = times.copy()
        if self.ok:                       # parking hassle weighs on choosing to drive (not on the minutes)
            cost[:, MODE_ID["car"]] += self.hassle[self.zone_of(dlon, dlat)]
            cost[:, MODE_ID["transit"]] += TRANSIT_PENALTY
            short = km_between(olon, olat, dlon, dlat) < TRANSIT_MIN_KM
            cost[short, MODE_ID["transit"]] = INF
            times[short, MODE_ID["transit"]] = INF
        mode = cost.argmin(axis=1)
        best = times[np.arange(len(people)), mode]
        return best.astype(np.float32), mode.astype(np.int8)
