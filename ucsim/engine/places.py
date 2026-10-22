"""Real places: every place the simulation sends people to is inside a real building footprint, so the map can show
them where the simulation has them (and nothing needs to be invented for the drawing).

- `settle_world(w)` moves each place's point (venues, workplaces, meetinghouses, congregations, complexes) into the
  footprint that contains it, else the nearest footprint within reach; idempotent (a point inside stays put).
- `settle(lon, lat)` the same for any points (groups, calendar places), with the building each ends up in.
- `campus(school)` the real buildings for classes (a slot table indexed by a section's building number), campus
  hangout spots, gyms, the study building and the events building (ucsim/config/places/campus.yaml).

Coordinates: placement's metres (east and north of ORIGIN) or lon/lat where said. Nothing here draws random numbers.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import yaml

from .placement import to_lonlat, to_xy

CFG = Path(__file__).resolve().parents[1] / "config" / "places" / "campus.yaml"
NOT_A_PLACE = ("minor", "parking")          # sheds, garages, parking structures: never where a place is
REACH_M = 60.0                              # a place's point this far from any footprint stays a point (a park)
MIN_AREA_M2 = 80.0                          # kiosks, booths and sheds are never where a place is
INSET_M = 0.8

_FP = None


def available() -> bool:
    """Whether the building layer is here (it is in the repository; a stripped checkout may lack it)."""
    from ..geo.buildings import OUT
    return OUT.exists()


def footprints() -> dict:
    """Building rings in metres, wings, kinds and names, with a centroid KD-tree; loaded once."""
    global _FP
    if _FP is None:
        import polars as pl
        from scipy.spatial import cKDTree
        from ..geo.buildings import OUT, ring_lonlat
        cols = ["lon", "lat", "area_m2", "floors", "kind", "name", "ring"]
        import pyarrow.parquet as pq
        if "wings" in pq.read_schema(OUT).names:
            cols.append("wings")
        b = pl.read_parquet(OUT, columns=cols)
        rings = []
        for r in b["ring"].to_list():
            ll = ring_lonlat(r)
            x, y = to_xy(ll[:, 0], ll[:, 1])
            rings.append(np.c_[x, y])
        cx, cy = to_xy(b["lon"].to_numpy(), b["lat"].to_numpy())
        wings = ([np.asarray(w, np.float64).reshape(-1, 5) for w in b["wings"].to_list()] if "wings" in b.columns else None)
        _FP = {"n": b.height, "rings": rings, "tree": cKDTree(np.c_[cx, cy]), "cx": cx, "cy": cy,
               "reach": np.sqrt(b["area_m2"].to_numpy()) * 1.5 + 10, "floors": b["floors"].to_numpy().astype(np.int16),
               "kind": b["kind"].to_numpy(), "name": b["name"].to_list(), "area": b["area_m2"].to_numpy(), "wings": wings}
    return _FP


def _inside(px, py, ring) -> bool:
    res = False
    xj, yj = ring[-1]
    for xi, yi in ring:
        if (yi > py) != (yj > py) and px < (xj - xi) * (py - yi) / (yj - yi + 1e-15) + xi:
            res = not res
        xj, yj = xi, yi
    return res


def _edge_dist(px, py, ring) -> float:
    a, b = ring[:-1], ring[1:]
    d = b - a
    t = np.clip(((px - a[:, 0]) * d[:, 0] + (py - a[:, 1]) * d[:, 1]) / np.maximum((d ** 2).sum(1), 1e-9), 0, 1)
    return float(np.min(np.hypot(a[:, 0] + t * d[:, 0] - px, a[:, 1] + t * d[:, 1] - py)))


_CONTAIN: dict = {}


def containing(x: np.ndarray, y: np.ndarray) -> np.ndarray:
    """The building whose footprint contains each point (−1: none). Strict; repeated points are looked up once."""
    F = footprints()
    x, y = np.asarray(x, np.float64), np.asarray(y, np.float64)
    out = np.full(len(x), -1, np.int64)
    ok = np.isfinite(x) & np.isfinite(y)
    if not ok.any():
        return out
    key = np.round(x[ok], 1) * 1e7 + np.round(y[ok], 1)
    uk, first, inv = np.unique(key, return_index=True, return_inverse=True)
    res = np.full(len(uk), -1, np.int64)
    todo = [k for k in range(len(uk)) if uk[k] not in _CONTAIN]
    if todo:
        ox, oy = x[ok][first[todo]], y[ok][first[todo]]
        d, nn = F["tree"].query(np.c_[ox, oy], k=12, distance_upper_bound=800)
        for row, k in enumerate(todo):
            hit = -1
            for dist, j in zip(d[row], nn[row]):
                if not np.isfinite(dist):
                    break
                if dist <= F["reach"][j] and _inside(ox[row], oy[row], F["rings"][j]):
                    hit = int(j)
                    break
            if len(_CONTAIN) > 400_000:
                _CONTAIN.clear()
            _CONTAIN[uk[k]] = hit
    for k in range(len(uk)):
        res[k] = _CONTAIN[uk[k]]
    out[np.flatnonzero(ok)] = res[inv.ravel()]
    return out


def nearest(x: float, y: float, max_m: float = REACH_M, avoid=NOT_A_PLACE) -> int:
    """The building whose outline is nearest the point, within max_m (−1: none)."""
    F = footprints()
    idx = F["tree"].query_ball_point([x, y], r=max_m + 300)
    best, bd = -1, max_m
    for j in idx:
        if F["kind"][j] in avoid or F["area"][j] < MIN_AREA_M2:
            continue
        dd = _edge_dist(x, y, F["rings"][j])
        if dd < bd:
            best, bd = int(j), dd
    return best


def wings_of(b: int) -> np.ndarray:
    F = footprints()
    if F["wings"] is not None and len(F["wings"][b]):
        return F["wings"][b]
    from .placement import buildings
    B = buildings()
    return np.array([[B["x"][b], B["y"][b], B["ang"][b], B["half"][b, 0], B["half"][b, 1]]])


def inside_point(b: int, x: float, y: float) -> tuple[float, float]:
    """The point inside building b's wings (inset from the walls) nearest (x, y)."""
    best, bd = None, np.inf
    for cx, cy, a, hl, hw in wings_of(b):
        ca, sa = np.cos(a), np.sin(a)
        u = (x - cx) * ca + (y - cy) * sa
        v = -(x - cx) * sa + (y - cy) * ca
        u = np.clip(u, -max(hl - INSET_M, 0), max(hl - INSET_M, 0))
        v = np.clip(v, -max(hw - INSET_M, 0), max(hw - INSET_M, 0))
        px, py = cx + u * ca - v * sa, cy + u * sa + v * ca
        d = np.hypot(px - x, py - y)
        if d < bd:
            best, bd = (float(px), float(py)), d
    return best


def anchor(b: int) -> tuple[float, float]:
    """A point well inside building b (the middle of its largest wing), as lon/lat."""
    w = wings_of(b)[0]
    lo, la = to_lonlat(w[0], w[1])
    return float(lo), float(la)


def settle(lon, lat, max_m: float = REACH_M, avoid=NOT_A_PLACE):
    """Points moved into their building: (lon, lat, building) arrays. A point inside a footprint keeps its spot; one
    outside moves to the nearest spot inside the nearest footprint within max_m; farther ones stay (building −1)."""
    lon = np.asarray(lon, np.float64).copy()
    lat = np.asarray(lat, np.float64).copy()
    x, y = to_xy(lon, lat)
    b = containing(x, y)
    F = footprints()
    tiny = (F["area"][np.maximum(b, 0)] < MIN_AREA_M2) | np.isin(F["kind"][np.maximum(b, 0)], avoid)
    for i in np.flatnonzero((b >= 0) & tiny):
        b[i] = -1                                   # inside a garage, a parking structure or a kiosk: find the real one
    for i in np.flatnonzero((b < 0) & np.isfinite(x)):
        j = nearest(x[i], y[i], max_m, avoid)
        if j >= 0:
            px, py = inside_point(j, x[i], y[i])
            lon[i], lat[i] = to_lonlat(px, py)
            b[i] = j
    return lon, lat, b


def by_name(name: str, near: tuple | None = None, within_m: float = 2500.0) -> int:
    """The largest building with this exact name (near a point, if given); −1 if none."""
    F = footprints()
    hits = [j for j, nm in enumerate(F["name"]) if nm == name]
    if near is not None:
        x0, y0 = to_xy(*near)
        hits = [j for j in hits if np.hypot(F["cx"][j] - x0, F["cy"][j] - y0) < within_m]
    return max(hits, key=lambda j: F["area"][j]) if hits else -1


_CFG = None


def config() -> dict:
    global _CFG
    if _CFG is None:
        _CFG = yaml.safe_load(CFG.read_text(encoding="utf-8"))
    return _CFG


def _slots(weights: dict, centre, n: int) -> np.ndarray:
    """A table of n building ids in proportion to the weights (largest remainder), interleaved."""
    names = [(by_name(k, centre), float(v)) for k, v in weights.items()]
    names = [(b, v) for b, v in names if b >= 0]
    if not names:
        return np.empty(0, np.int64)
    ids = np.array([b for b, _ in names])
    wts = np.array([v for _, v in names])
    q = wts / wts.sum() * n
    k = np.floor(q).astype(int)
    k[np.argsort(-(q - k))[: n - k.sum()]] += 1
    out = np.concatenate([np.full(c, b) for b, c in zip(ids, k)])
    order = np.argsort(np.concatenate([(np.arange(c) + 0.5) / max(c, 1) for c in k]), kind="stable")
    return out[order].astype(np.int64)


_CAMPUS: dict = {}


def campus(school: int) -> dict:
    """Real buildings of a campus (1 BYU, 2 UVU): teaching (40-slot table for section building numbers), spots
    (hangouts, 24 slots), gyms (8 slots), study and events (one building each)."""
    if school not in _CAMPUS:
        c = config()["byu" if school == 1 else "uvu"]
        centre = tuple(c["centre"])
        _CAMPUS[school] = {"teaching": _slots(c["teaching"], centre, 40), "spots": _slots(c["spots"], centre, 24),
                           "gyms": _slots(c["gyms"], centre, 8), "study": by_name(c["study"], centre),
                           "events": by_name(c["events"], centre)}
    return _CAMPUS[school]


def named(name: str) -> int:
    """The building of a named place the simulation knows only approximately (campus.yaml `named`); −1 if none."""
    spec = config().get("named", {}).get(name)
    if not spec:
        return -1
    if "name" in spec:
        return by_name(spec["name"])
    x, y = to_xy(*spec["building_near"])
    F = footprints()
    idx = F["tree"].query_ball_point([float(x), float(y)], r=200)
    ok = [j for j in idx if F["kind"][j] == spec.get("kind", F["kind"][j])]
    return max(ok, key=lambda j: F["area"][j]) if ok else -1


def settle_world(w):
    """Move the world's places into their buildings (in place; idempotent)."""
    import polars as pl
    from ..geo.buildings import OUT
    if not OUT.exists():
        return
    for attr in ("venues", "complexes"):
        df = getattr(w, attr, None)
        if isinstance(df, pl.DataFrame) and df.height and "lon" in df.columns:
            lo, la, _ = settle(df["lon"].to_numpy(), df["lat"].to_numpy(), max_m=REACH_M if attr == "venues" else 120.0)
            if attr == "venues" and "vtype" in df.columns:
                outdoors = df["vtype"].is_in(["park", "trailhead", "overlook"]).to_numpy()
                lo = np.where(outdoors, df["lon"].to_numpy(), lo)
                la = np.where(outdoors, df["lat"].to_numpy(), la)
            setattr(w, attr, df.with_columns(lon=pl.Series(lo), lat=pl.Series(la)))
    for attr in ("employers", "wards", "congregations", "groups"):
        settle_dict(getattr(w, attr, None))


def settle_dict(d: dict | None, place_names: list | None = None):
    """A dict of arrays with lon/lat (employers, wards, groups…): points into buildings; rows with a named approximate
    place (campus.yaml `named`, one name per row or None) onto that real building."""
    if not d or "lon" not in d or not len(d["lon"]):
        return
    lo, la, _ = settle(d["lon"], d["lat"])
    for i, nm in enumerate(place_names or []):
        b = named(nm) if nm else -1
        if b >= 0:
            lo[i], la[i] = anchor(b)
    d["lon"], d["lat"] = lo, la


_ROOMS: dict = {}


def classrooms(school: int = 1) -> dict | None:
    """BYU's classrooms with their seats (geo/floorplans.py → classrooms.parquet): arrays building, floor, seats, room,
    lon/lat; index lists by study area (campus.yaml `areas`), general education and all. None for UVU (no plans)."""
    if school != 1:
        return None
    if "byu" not in _ROOMS:
        import polars as pl
        from ..geo.floorplans import CLASSROOMS
        if not CLASSROOMS.exists():
            _ROOMS["byu"] = None
            return None
        c = pl.read_parquet(CLASSROOMS).sort(["building_id", "floor", "room"])
        F = footprints()
        x, y = c["x_m"].to_numpy().astype(float), c["y_m"].to_numpy().astype(float)
        b = c["building_id"].to_numpy().astype(np.int64)
        # a room the plan fit put outside its building: at the middle of the building instead
        inb = containing(x, y) == b
        for i in np.flatnonzero(~inb):
            x[i], y[i] = wings_of(int(b[i]))[0][:2]
        lon, lat = to_lonlat(x, y)
        codes = c["code"].to_list()
        cfg = config()
        by_area = {}
        for area, cs in (cfg.get("areas") or {}).items():
            by_area[area] = [i for i, k in enumerate(codes) if k in cs]
        by_area.setdefault("general", list(range(c.height)))
        _ROOMS["byu"] = {"building": b, "floor": c["floor"].to_numpy().astype(np.int64), "seats": c["seats"].to_numpy(),
                         "room": c["room"].to_list(), "code": codes, "lon": lon, "lat": lat,
                         "by_area": by_area, "all": list(range(c.height))}
    return _ROOMS["byu"]
