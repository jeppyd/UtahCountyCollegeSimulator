"""Build ucsim/geo/data/travel.npz: zone-to-zone travel in Provo–Orem by walking, biking, driving and UTA transit.

    python scripts/fetch_geodata.py roads_net          # UGRC's road network (once; data/external/, not committed)
    python scripts/build_travel.py [GTFS.zip]          # downloads UTA's GTFS feed when no path is given

Zones: the 57 official Provo and Orem neighborhoods, BYU and UVU campus, and 1.5 km fill cells for the rest of the
area (Vineyard, Lindon, Springville edges, the airport…). A raster of ~170 m cells maps any point to its zone.

Streets: UGRC's UtahRoads (speed limits, one-ways, road classes) as a graph; Dijkstra from each zone's centroid (the
mean of its dwellings) gives network km for walking and biking (no freeways or ramps) and driving minutes off-peak and
at the evening peak (speed limit × a class factor for signals and turns; labelled assumptions in META).

Transit: UTA's GTFS feed on a representative weekday, Saturday and Sunday of the feed. For each zone and departure
bin (8:00, 12:30, 17:30, 20:30) a connection scan over the next 2½ hours from six departure times within the hour
(the average includes waiting): walk ≤ 800 m to a stop at 4.8 km/h, rides, transfers by walking ≤ 400 m, walk to the
door. Door-to-door minutes; no service → NaN. The feed itself is not committed — only these derived minutes.
"""
from __future__ import annotations

import datetime as dt
import io
import json
import sys
import time
import urllib.request
import zipfile
from pathlib import Path

import numpy as np
import polars as pl
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import connected_components, dijkstra

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ucsim.geo import neighborhoods  # noqa: E402

GEO = ROOT / "ucsim" / "geo" / "data"
EXT = ROOT / "data" / "external" / "ugrc"
OUT = GEO / "travel.npz"
FEED_URL = "https://gtfsfeed.rideuta.com/GTFS.zip"
KX, KY = 85.0, 111.0                         # km per degree at Provo
BBOX = (-111.80, 40.15, -111.55, 40.38)      # the raster and the fill cells
CELL = (0.002, 0.0015)                       # raster cell (lon, lat) ≈ 170 × 165 m
FILL = (0.018, 0.0135)                       # fill zones ≈ 1.5 km
CAMPUS = {"BYU campus": (-111.6493, 40.2500, 0.75), "UVU campus": (-111.7129, 40.2773, 0.55)}   # centre, radius km
OUTER_NAMES = {"Vineyard": (-111.745, 40.305), "Lindon": (-111.715, 40.340), "Springville": (-111.610, 40.165),
               "Provo Airport": (-111.723, 40.219), "Pleasant Grove": (-111.738, 40.364), "Provo Canyon": (-111.60, 40.33),
               "Spanish Fork Rd": (-111.64, 40.18), "Utah Lake shore": (-111.76, 40.24)}
BINS = (480, 750, 1050, 1230)                # departure minutes: 8:00, 12:30, 17:30, 20:30
WALK_KMH, BIKE_KMH = 4.8, 14.0
# driving: speed limit × factor (signals, turns, stop signs); default limits (mph) by UGRC CARTOCODE when missing
CLASS_FACTOR = {"1": 0.92, "2": 0.75, "3": 0.68, "4": 0.72, "5": 0.66, "6": 0.66, "7": 0.75, "8": 0.62, "9": 0.55,
                "10": 0.6, "11": 0.55, "16": 0.4, "18": 0.4}
DEFAULT_MPH = {"1": 70, "2": 55, "3": 45, "4": 50, "5": 40, "6": 40, "7": 40, "8": 35, "9": 25, "10": 30, "11": 25,
               "16": 15, "18": 15}
PEAK = {"1": 0.8, "2": 0.82, "3": 0.82, "4": 0.82, "5": 0.85, "6": 0.85, "7": 0.8, "8": 0.88}   # 5:30 pm speed factor
NO_WALK = {"1", "7"}                          # freeways and ramps


def km(lon1, lat1, lon2, lat2):
    return np.hypot((np.asarray(lon1) - lon2) * KX, (np.asarray(lat1) - lat2) * KY)


# ----------------------------------------------------------------------------- zones
def build_zones():
    nb = neighborhoods.load()
    names = [f"{r['name']} ({r['city']})" for r in nb] + list(CAMPUS)
    nx = int(round((BBOX[2] - BBOX[0]) / CELL[0]))
    ny = int(round((BBOX[3] - BBOX[1]) / CELL[1]))
    gx, gy = np.meshgrid(BBOX[0] + (np.arange(nx) + 0.5) * CELL[0], BBOX[1] + (np.arange(ny) + 0.5) * CELL[1])
    lon, lat = gx.ravel(), gy.ravel()
    z = neighborhoods.locate(lon, lat).astype(np.int32) - 1          # -1 outside every neighborhood
    for k, (nm, (clon, clat, r)) in enumerate(CAMPUS.items()):
        z[km(lon, lat, clon, clat) <= r] = len(nb) + k
    # fill cells for the rest
    fx = ((lon - BBOX[0]) // FILL[0]).astype(int)
    fy = ((lat - BBOX[1]) // FILL[1]).astype(int)
    out = z < 0
    keys = np.unique(fx[out] * 1000 + fy[out])
    fill_of = {}
    for key in keys:
        cx = BBOX[0] + (key // 1000 + 0.5) * FILL[0]
        cy = BBOX[1] + (key % 1000 + 0.5) * FILL[1]
        near = min(OUTER_NAMES, key=lambda n: km(cx, cy, *OUTER_NAMES[n]))
        fill_of[key] = len(names)
        names.append(f"Outer area near {near} #{len(names) - len(nb) - len(CAMPUS) + 1}")
    z[out] = [fill_of[k] for k in (fx[out] * 1000 + fy[out])]
    # keep a fill cell only where people live or go (dwellings, venues, work sites); the rest join the nearest zone
    pts = [pl.read_parquet(GEO / f) for f in ("dwellings.parquet", "venues.parquet", "work_sites.parquet")]
    plon = np.concatenate([d["lon"].to_numpy() for d in pts])
    plat = np.concatenate([d["lat"].to_numpy() for d in pts])
    raster = z.reshape(ny, nx)
    used = np.bincount(zone_lookup(raster, plon, plat), minlength=len(names))
    first_fill = len(nb) + len(CAMPUS)
    keep = np.r_[np.ones(first_fill, bool), used[first_fill:] >= 10]
    from scipy.spatial import cKDTree
    good = keep[z]
    tree = cKDTree(np.c_[lon[good] * KX, lat[good] * KY])
    _, j = tree.query(np.c_[lon[~good] * KX, lat[~good] * KY])
    z[~good] = z[good][j]
    new = -np.ones(len(names), int)
    new[keep] = np.arange(keep.sum())
    names = [n for n, k in zip(names, keep) if k]
    k_out = 0
    for i in range(first_fill, len(names)):           # renumber the outer names 1..n
        k_out += 1
        names[i] = names[i].rsplit(" #", 1)[0] + f" #{k_out}"
    return names, new[z].reshape(ny, nx), lon, lat


def centroids(names, raster, cell_lon, cell_lat):
    """Each zone's centre: the mean of its dwellings (where people live), else of its raster cells."""
    dw = pl.read_parquet(GEO / "dwellings.parquet")
    dlon, dlat = dw["lon"].to_numpy(), dw["lat"].to_numpy()
    zi = zone_lookup(raster, dlon, dlat)
    flat = raster.ravel()
    c = np.zeros((len(names), 2))
    n = np.zeros(len(names), int)
    for k in range(len(names)):
        m = zi == k
        if m.sum() >= 5:
            c[k] = dlon[m].mean(), dlat[m].mean()
        else:
            cm = flat == k
            c[k] = cell_lon[cm].mean(), cell_lat[cm].mean()
        n[k] = int(m.sum())
    return c, n


def zone_lookup(raster, lon, lat):
    ny, nx = raster.shape
    ix = np.clip(((np.asarray(lon) - BBOX[0]) / CELL[0]).astype(int), 0, nx - 1)
    iy = np.clip(((np.asarray(lat) - BBOX[1]) / CELL[1]).astype(int), 0, ny - 1)
    return raster[iy, ix]


# ----------------------------------------------------------------------------- streets
def build_graph():
    feats = json.loads((EXT / "roads_net.json").read_text(encoding="utf-8"))["features"]
    node_id: dict[tuple, int] = {}
    xy = []

    def nid(p):
        k = (round(p[0], 5), round(p[1], 5))
        if k not in node_id:
            node_id[k] = len(xy)
            xy.append(k)
        return node_id[k]

    rows = []   # (a, b, km, class, mph, oneway)
    for f in feats:
        cc = str(f.get("CARTOCODE") or "11")
        mph = float(f.get("SPEED_LMT") or 0) or DEFAULT_MPH.get(cc, 25)
        ow = str(f.get("ONEWAY") or "0")
        for path in f["paths"]:
            ids = [nid(p) for p in path]
            for a, b in zip(ids[:-1], ids[1:]):
                if a != b:
                    rows.append((a, b, cc, mph, ow))
    xy = np.array(xy)
    a = np.array([r[0] for r in rows])
    b = np.array([r[1] for r in rows])
    seg = km(xy[a, 0], xy[a, 1], xy[b, 0], xy[b, 1])
    cls = np.array([r[2] for r in rows])
    mph = np.array([r[3] for r in rows], float)
    ow = np.array([r[4] for r in rows])
    return xy, a, b, seg, cls, mph, ow


def graphs(xy, a, b, seg, cls, mph, ow):
    n = len(xy)
    walkable = ~np.isin(cls, list(NO_WALK))
    walk = csr_matrix((np.r_[seg[walkable], seg[walkable]], (np.r_[a[walkable], b[walkable]], np.r_[b[walkable], a[walkable]])), shape=(n, n))
    fac = np.array([CLASS_FACTOR.get(c, 0.55) for c in cls])
    kmh = mph * 1.609 * fac
    peak = np.array([PEAK.get(c, 0.95) for c in cls])
    out = {}
    for name, sp in (("car_off", kmh), ("car_peak", kmh * peak)):
        t = seg / sp * 60
        fwd = ow != "2"          # UGRC ONEWAY: 0 two-way, 1 along the digitized direction, 2 against it
        bwd = ow != "1"
        src = np.r_[a[fwd], b[bwd]]
        dst = np.r_[b[fwd], a[bwd]]
        out[name] = csr_matrix((np.r_[t[fwd], t[bwd]], (src, dst)), shape=(n, n))
        out[name + "_km"] = csr_matrix((np.r_[seg[fwd], seg[bwd]], (src, dst)), shape=(n, n))
    out["walk"] = walk
    return out


def nearest_nodes(xy, pts, ok):
    idx = np.flatnonzero(ok)
    d = km(xy[idx, 0][None], xy[idx, 1][None], pts[:, 0:1], pts[:, 1:2])
    j = d.argmin(axis=1)
    return idx[j], d[np.arange(len(pts)), j]


def street_matrices(cent, xy, G):
    n = len(xy)
    # snap each centroid to the largest connected part of each graph
    res = {}
    for key in ("walk", "car_off"):
        _, lab = connected_components(G[key], directed=key != "walk", connection="weak")
        big = lab == np.bincount(lab).argmax()
        res[key] = nearest_nodes(xy, cent, big)
    wn, wd = res["walk"]
    cn, cd = res["car_off"]
    walk_km = dijkstra(G["walk"], indices=wn)[:, wn] + wd[:, None] + wd[None, :]
    car_off = dijkstra(G["car_off"], indices=cn)[:, cn]
    car_peak = dijkstra(G["car_peak"], indices=cn)[:, cn]
    # the km of the fastest off-peak route: re-run on km weights with predecessors would be costly; use the km graph's
    # shortest path (close to the fastest route's length in a grid city)
    car_km = dijkstra(G["car_off_km"], indices=cn)[:, cn]
    access = cd / 20 * 60                     # to and from the street network at ~20 km/h
    car_off = car_off + access[:, None] + access[None, :]
    car_peak = car_peak + access[:, None] + access[None, :]
    car_km = car_km + cd[:, None] + cd[None, :]
    del n
    return walk_km, car_off, car_peak, car_km


# ----------------------------------------------------------------------------- transit
def read_feed(path: str | None):
    if path:
        raw = Path(path).read_bytes()
    else:
        with urllib.request.urlopen(FEED_URL, timeout=120) as r:
            raw = r.read()
    z = zipfile.ZipFile(io.BytesIO(raw))
    rd = lambda n, **k: pl.read_csv(io.BytesIO(z.read(n)), infer_schema_length=0, **k)   # noqa: E731
    return {n: rd(f"{n}.txt") for n in ("feed_info", "calendar", "calendar_dates", "trips", "stops", "routes")} | {
        "stop_times": rd("stop_times.txt", columns=["trip_id", "arrival_time", "departure_time", "stop_id", "stop_sequence"])}


def service_days(F):
    """A representative weekday, Saturday and Sunday inside the feed, avoiding holidays (most regular dates)."""
    fi = F["feed_info"].row(0, named=True)
    start = dt.datetime.strptime(fi["feed_start_date"], "%Y%m%d").date()
    end = dt.datetime.strptime(fi["feed_end_date"], "%Y%m%d").date()
    mid = start + (end - start) / 2
    out = {}
    for name, wd in (("weekday", 1), ("saturday", 5), ("sunday", 6)):
        d = mid + dt.timedelta(days=(wd - mid.weekday()) % 7)
        out[name] = d
    return out, fi


def active_services(F, day: dt.date) -> set:
    cal = F["calendar"]
    col = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"][day.weekday()]
    ds = day.strftime("%Y%m%d")
    on = set(cal.filter((pl.col(col) == "1") & (pl.col("start_date") <= ds) & (pl.col("end_date") >= ds))["service_id"])
    cd = F["calendar_dates"].filter(pl.col("date") == ds)
    on |= set(cd.filter(pl.col("exception_type") == "1")["service_id"])
    on -= set(cd.filter(pl.col("exception_type") == "2")["service_id"])
    return on


def hms(s: pl.Expr) -> pl.Expr:
    p = s.str.strip_chars().str.split(":")
    return p.list.get(0).cast(int) * 60 + p.list.get(1).cast(int) + p.list.get(2).cast(int) / 60


def connections(F, day, slon, slat):
    """(dep_stop, arr_stop, dep_min, arr_min, trip) for the day's trips, between stops in the area."""
    svc = active_services(F, day)
    trips = F["trips"].filter(pl.col("service_id").is_in(list(svc)))["trip_id"]
    st = (F["stop_times"].filter(pl.col("trip_id").is_in(trips.to_list()))
          .with_columns(pl.col("stop_sequence").cast(int), dep=hms(pl.col("departure_time")), arr=hms(pl.col("arrival_time")))
          .sort(["trip_id", "stop_sequence"]))
    st = st.with_columns(nxt_stop=pl.col("stop_id").shift(-1).over("trip_id"), nxt_arr=pl.col("arr").shift(-1).over("trip_id"))
    c = st.filter(pl.col("nxt_stop").is_not_null())
    return c


def transit(F, cent, names):
    days, fi = service_days(F)
    stops = F["stops"].with_columns(pl.col("stop_lat").cast(float), pl.col("stop_lon").cast(float))
    area = stops.filter(pl.col("stop_lon").is_between(-112.0, -111.4) & pl.col("stop_lat").is_between(40.0, 40.55))
    sid = area["stop_id"].to_list()
    six = {s: i for i, s in enumerate(sid)}
    slon, slat = area["stop_lon"].to_numpy(), area["stop_lat"].to_numpy()
    S = len(sid)
    # footpaths between stops (≤ 400 m) and access to/from zone centroids (≤ 800 m), straight line × 1.3 at walking pace
    dss = km(slon[:, None], slat[:, None], slon[None], slat[None]) * 1.3 / WALK_KMH * 60
    foot = [np.flatnonzero((dss[i] <= 400 * 1.3 / 1000 / WALK_KMH * 60) & (np.arange(S) != i)) for i in range(S)]
    dzs = km(cent[:, 0:1], cent[:, 1:2], slon[None], slat[None]) * 1.3 / WALK_KMH * 60
    acc = dzs <= 0.8 * 1.3 / WALK_KMH * 60
    Z = len(cent)
    out = np.full((3, len(BINS), Z, Z), np.nan, np.float32)
    info = {}
    for di, (dname, day) in enumerate(days.items()):
        c = connections(F, day, slon, slat).filter(pl.col("stop_id").is_in(sid) & pl.col("nxt_stop").is_in(sid))
        if not c.height:
            info[dname] = {"date": str(day), "connections": 0}
            continue
        c = c.sort("dep")
        ds_ = np.array([six[s] for s in c["stop_id"]])
        as_ = np.array([six[s] for s in c["nxt_stop"]])
        dep = c["dep"].to_numpy()
        arr = c["nxt_arr"].to_numpy()
        _, trip = np.unique(c["trip_id"].to_numpy(), return_inverse=True)
        info[dname] = {"date": str(day), "connections": int(c.height), "trips": int(trip.max() + 1)}
        for bi, b0 in enumerate(BINS):
            acc_total = np.zeros((Z, Z))
            n_ok = np.zeros((Z, Z))
            for off in range(0, 60, 10):
                T = b0 + off
                best = csa(T, ds_, as_, dep, arr, trip, foot, dss, dzs, acc, S, Z)
                door = np.full((Z, Z), np.inf)
                for zd in range(Z):
                    st_ = np.flatnonzero(acc[zd])
                    if len(st_):
                        door[:, zd] = (best[:, st_] + dzs[zd, st_][None]).min(axis=1)
                ok = np.isfinite(door) & (door - T <= 150)
                acc_total[ok] += door[ok] - T
                n_ok[ok] += 1
            m = n_ok >= 4                                  # served from most departure times in the hour
            out[di, bi][m] = (acc_total[m] / n_ok[m]).astype(np.float32)
        print(f"  transit {dname} {day}: {c.height} connections", flush=True)
    return out, {"feed_version": fi.get("feed_version"), "feed_start": fi.get("feed_start_date"),
                 "feed_end": fi.get("feed_end_date"), "days": info}


def csa(T, ds_, as_, dep, arr, trip, foot, dss, dzs, acc, S, Z):
    """Connection scan from every zone at once: earliest arrival (minutes) at each stop. (Z, S)."""
    best = np.full((Z, S), np.inf)
    walk0 = np.where(acc, T + dzs, np.inf)
    best[:] = walk0
    for s in range(S):                                   # walk on to nearby stops before boarding
        if len(foot[s]):
            best[:, foot[s]] = np.minimum(best[:, foot[s]], best[:, s:s + 1] + dss[s, foot[s]][None])
    on = np.zeros((Z, trip.max() + 1), bool)
    lo, hi = np.searchsorted(dep, T), np.searchsorted(dep, T + 150)
    for k in range(lo, hi):
        s, t, tr = ds_[k], as_[k], trip[k]
        board = on[:, tr] | (best[:, s] <= dep[k])
        if not board.any():
            continue
        on[:, tr] = board
        a = arr[k]
        upd = board & (a < best[:, t])
        if upd.any():
            best[upd, t] = a
            f = foot[t]
            if len(f):
                rows = np.flatnonzero(upd)
                best[np.ix_(rows, f)] = np.minimum(best[np.ix_(rows, f)], a + dss[t, f][None])
    return best


# ----------------------------------------------------------------------------- main
def main(argv):
    t0 = time.time()
    names, raster, clon, clat = build_zones()
    cent, n_dw = centroids(names, raster, clon, clat)
    print(f"zones {len(names)} ({len(neighborhoods.load())} neighborhoods); raster {raster.shape}", flush=True)
    xy, a, b, seg, cls, mph, ow = build_graph()
    G = graphs(xy, a, b, seg, cls, mph, ow)
    walk_km, car_off, car_peak, car_km = street_matrices(cent, xy, G)
    print(f"streets: {len(xy)} nodes, {len(seg)} segments ({time.time() - t0:.0f}s)", flush=True)
    F = read_feed(argv[0] if argv else None)
    tr, tinfo = transit(F, cent, names)
    meta = {"built": str(dt.date.today()), "method": __doc__.strip().split("\n\n", 1)[1],
            "roads": "UGRC UtahRoads (SGID), fetched by scripts/fetch_geodata.py roads_net",
            "transit": {"source": FEED_URL, **tinfo, "downloaded": str(dt.date.today()),
                        "terms": "UTA's GTFS terms (listed by the Mobility Database as http://developer.rideuta.com/TermsOfUse.aspx; "
                                 "that site no longer resolves). The feed is not redistributed; only derived minutes."},
            "bins": list(BINS), "days": ["weekday", "saturday", "sunday"],
            "assumptions": {"walk_kmh": WALK_KMH, "bike_kmh": BIKE_KMH, "class_factor": CLASS_FACTOR, "peak": PEAK,
                            "default_mph": DEFAULT_MPH, "transit_walk_m": 800, "transfer_walk_m": 400}}
    straight = km(cent[:, 0:1], cent[:, 1:2], cent[None, :, 0], cent[None, :, 1])
    np.savez_compressed(OUT, names=np.array(names), raster=raster.astype(np.uint16), bbox=np.array(BBOX), cell=np.array(CELL),
                        centroid=cent.astype(np.float32), dwellings=n_dw.astype(np.int32),
                        straight_km=straight.astype(np.float32), walk_km=walk_km.astype(np.float32),
                        car_off=car_off.astype(np.float32), car_peak=car_peak.astype(np.float32), car_km=car_km.astype(np.float32),
                        transit=tr, meta=np.array(json.dumps(meta)))
    print(f"wrote {OUT} ({OUT.stat().st_size / 1e6:.2f} MB) in {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main(sys.argv[1:])
