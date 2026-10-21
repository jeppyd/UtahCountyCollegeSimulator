"""The building layer: every building footprint in Provo/Orem with its height, floors, name and kind, for placing
people on real floors (homes, halls, classrooms) and for the 3D map.

Input  data/external/overture/buildings.parquet (scripts/fetch_overture.py; OpenStreetMap + Esri Community Maps +
       Microsoft footprints, heights mostly from lidar) and data/external/ugrc/parcels.json (county floor counts).
Output ucsim/geo/data/buildings.parquet   one row per building (rings as flat lon/lat lists)
       web/public/geo/buildings3d.bin     the same footprints with heights, compact, for the map

    python -m ucsim.geo.buildings

Floors, in order of preference: the mapped floor count (OpenStreetMap `building:levels`), the county parcel's floor
count when the parcel's centroid falls inside the footprint, the measured height ÷ 3.2 m, else 1 (2 for an apartment
building). Height: measured, else floors × 3.2 m. Every row says where its floors and height came from.
"""
from __future__ import annotations

import json
import struct
from pathlib import Path

import numpy as np
import polars as pl

ROOT = Path(__file__).resolve().parents[2]
EXT = ROOT / "data" / "external"
OUT = Path(__file__).resolve().parent / "data" / "buildings.parquet"
WEB = ROOT / "web" / "public" / "geo" / "buildings3d.bin"
STOREY_M = 3.2
LON0, LAT0 = -111.70, 40.26                                   # rings are stored as 1e-6° offsets from here
KX, KY = 111_320 * np.cos(np.radians(40.26)), 111_320.0     # metres per degree here

# building kinds for the map's colors and the simulation's uses (from Overture/OSM class, then subtype)
KIND_OF_CLASS = {
    "house": "house", "detached": "house", "semidetached_house": "house", "residential": "house", "terrace": "townhouse",
    "bungalow": "house", "static_caravan": "mobile", "apartments": "apartments", "dormitory": "dorm",
    "university": "campus", "college": "campus", "school": "school", "kindergarten": "school",
    "church": "church", "chapel": "church", "temple": "church", "religious": "church", "cathedral": "church",
    "commercial": "commercial", "retail": "commercial", "supermarket": "commercial", "office": "office",
    "industrial": "industrial", "warehouse": "industrial", "hospital": "civic", "civic": "civic", "government": "civic",
    "public": "civic", "library": "civic", "sports_centre": "sports", "stadium": "sports", "grandstand": "sports",
    "sports_hall": "sports", "hotel": "commercial", "garage": "minor", "garages": "minor", "shed": "minor",
    "carport": "minor", "roof": "minor", "parking": "parking", "service": "minor",
}
KIND_OF_SUBTYPE = {"residential": "house", "commercial": "commercial", "education": "campus", "religious": "church",
                   "industrial": "industrial", "civic": "civic", "medical": "civic", "entertainment": "commercial",
                   "outbuilding": "minor", "service": "minor", "transportation": "minor", "agricultural": "minor"}
KINDS = ["other", "house", "townhouse", "apartments", "dorm", "mobile", "campus", "school", "church", "commercial",
         "office", "industrial", "civic", "sports", "parking", "minor"]


def wkb_rings(b: bytes) -> list[np.ndarray]:
    """Outer rings of a WKB Polygon or MultiPolygon (holes dropped), as (k, 2) lon/lat arrays."""
    def read_poly(off, le):
        e = "<" if le else ">"
        (nr,) = struct.unpack_from(e + "I", b, off)
        off += 4
        rings = []
        for r in range(nr):
            (n,) = struct.unpack_from(e + "I", b, off)
            off += 4
            pts = np.frombuffer(b, dtype=e + "f8", count=2 * n, offset=off).reshape(n, 2)
            off += 16 * n
            if r == 0:
                rings.append(pts)
        return rings, off
    le = b[0] == 1
    (t,) = struct.unpack_from("<I" if le else ">I", b, 1)
    t &= 0xFF
    if t == 3:
        return read_poly(5, le)[0]
    if t == 6:
        (n,) = struct.unpack_from("<I" if le else ">I", b, 5)
        off, out = 9, []
        for _ in range(n):
            le2 = b[off] == 1
            rings, off = read_poly(off + 5, le2)
            out += rings
        return out
    return []


def area_m2(ring: np.ndarray) -> float:
    x, y = ring[:, 0] * KX, ring[:, 1] * KY
    return float(abs(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1))) / 2)


def centroid(ring: np.ndarray) -> tuple[float, float]:
    x, y = ring[:-1, 0], ring[:-1, 1]
    x1, y1 = np.roll(x, -1), np.roll(y, -1)
    c = x * y1 - x1 * y
    a = c.sum() / 2
    if abs(a) < 1e-14:
        return float(x.mean()), float(y.mean())
    return float(((x + x1) * c).sum() / (6 * a)), float(((y + y1) * c).sum() / (6 * a))


def inside(px: np.ndarray, py: np.ndarray, ring: np.ndarray) -> np.ndarray:
    """Points inside one ring (ray casting)."""
    res = np.zeros(len(px), bool)
    xj, yj = ring[-1]
    for xi, yi in ring:
        res ^= ((yi > py) != (yj > py)) & (px < (xj - xi) * (py - yi) / (yj - yi + 1e-15) + xi)
        xj, yj = xi, yi
    return res


def kind_of(cls, sub, name) -> str:
    if cls in KIND_OF_CLASS:
        return KIND_OF_CLASS[cls]
    if name and any(w in name.lower() for w in (" hall", "building", "center", "centre", "library")) and sub == "education":
        return "campus"
    return KIND_OF_SUBTYPE.get(sub, "other")


def build():
    import pyarrow.parquet as pq
    from scipy.spatial import cKDTree

    t = pq.read_table(EXT / "overture" / "buildings.parquet",
                      columns=["id", "names", "class", "subtype", "height", "num_floors", "is_underground", "geometry"]).to_pylist()
    parcels = [p for p in json.loads((EXT / "ugrc" / "parcels.json").read_text())["features"] if p.get("FLOORS_CNT")]
    p_xy = np.array([[p["lon"] * KX, p["lat"] * KY] for p in parcels])
    p_fl = np.array([int(p["FLOORS_CNT"]) for p in parcels])
    tree = cKDTree(p_xy)
    rows = []
    for r in t:
        if r["is_underground"]:
            continue
        rings = wkb_rings(r["geometry"])
        if not rings:
            continue
        ring = max(rings, key=area_m2)
        a = area_m2(ring)
        if a < 6:                                   # slivers
            continue
        cx, cy = centroid(ring)
        name = (r["names"] or {}).get("primary")
        kind = kind_of(r["class"], r["subtype"], name)
        floors, f_src = r["num_floors"], "mapped"
        if not floors:
            # a county floor count from a parcel whose centroid is inside this footprint (small parcels: one building)
            near = tree.query_ball_point([cx * KX, cy * KY], r=max(8.0, np.sqrt(a)))
            if near:
                ins = inside(p_xy[near, 0] / KX, p_xy[near, 1] / KY, ring)
                if ins.any():
                    floors, f_src = int(np.max(p_fl[np.array(near)[ins]])), "county"
        h, h_src = r["height"], "measured"
        if not floors:
            if h:
                floors, f_src = max(1, int(round(h / STOREY_M))), "height"
            else:
                floors, f_src = (2 if kind in ("apartments", "dorm", "townhouse") else 1), "guess"
        floors = int(min(max(floors, 1), 30))
        if not h:
            h, h_src = floors * STOREY_M + (1.0 if kind in ("house", "townhouse") else 0.0), "floors"
        rows.append({"ov_id": r["id"], "name": name, "kind": kind, "cls": r["class"], "lon": cx, "lat": cy,
                     "floors": floors, "floors_src": f_src, "height_m": round(float(h), 1), "height_src": h_src,
                     "area_m2": round(a, 1),
                     "ring": np.round((ring - (LON0, LAT0)) * 1e6).astype(np.int32).ravel().tolist()})
    df = pl.DataFrame(rows).sort(["lat", "lon"]).with_row_index("building_id")
    df = df.with_columns(pl.col("building_id").cast(pl.Int32))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    df.write_parquet(OUT, compression="zstd", compression_level=19)
    write_web(df)
    print(f"{df.height} buildings → {OUT.relative_to(ROOT)} ({OUT.stat().st_size / 1e6:.1f} MB), "
          f"{WEB.relative_to(ROOT)} ({WEB.stat().st_size / 1e6:.1f} MB)")
    print(df.group_by("floors_src").len().sort("len", descending=True))
    print(df.group_by("kind").len().sort("len", descending=True))
    return df


def write_web(df: pl.DataFrame):
    """Footprints with heights for the map. Little-endian: magic 'UB3D', version u16, n i32, lon0 f64, lat0 f64; per
    building: id i32, height decimetres u16, floors u8, kind u8, vertex count u16, the first vertex as an i32 pair of
    1e-6 degrees from (lon0, lat0), then each next vertex as an i16 pair of 1e-6-degree steps (the closing vertex is
    left out). Decoded in web/src/map/buildings.ts."""
    buf = bytearray(b"UB3D") + struct.pack("<Hidd", 1, df.height, LON0, LAT0)
    kinds = {k: i for i, k in enumerate(KINDS)}
    for bid, h, fl, kind, ring in df.select("building_id", "height_m", "floors", "kind", "ring").iter_rows():
        q = np.asarray(ring, np.int64).reshape(-1, 2)
        if len(q) > 3 and (q[0] == q[-1]).all():
            q = q[:-1]
        d = np.diff(q, axis=0)
        if len(d) and np.abs(d).max() > 32767:      # a footprint wider than ~3.6 km between vertices: skip it
            continue
        buf += struct.pack("<iHBBHii", bid, min(65535, int(round(h * 10))), min(255, fl), kinds.get(kind, 0), len(q), *q[0])
        buf += d.astype("<i2").tobytes()
    WEB.parent.mkdir(parents=True, exist_ok=True)
    WEB.write_bytes(bytes(buf))


def load() -> pl.DataFrame:
    return pl.read_parquet(OUT)


def ring_lonlat(ring) -> np.ndarray:
    """A stored ring (flat 1e-6° offsets) as a (k, 2) lon/lat array."""
    return np.asarray(ring, np.float64).reshape(-1, 2) / 1e6 + (LON0, LAT0)


if __name__ == "__main__":
    build()
