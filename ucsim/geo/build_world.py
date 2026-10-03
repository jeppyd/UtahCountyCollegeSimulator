"""Build the compact simulation geography for Provo/Orem from public data.

Inputs  (data/external/ugrc/*.json, fetched by scripts/fetch_geodata.py):
  UGRC SGID address points, Utah County LIR parcels, building footprints, places of worship,
  OpenSourcePlaces (OSM-derived POIs), local parks, trailheads, roads, municipal boundaries.
  Complex names geocoded with OSM Nominatim (scripts/geocode_complexes.py).

Outputs (committed, ucsim/geo/data/):
  dwellings.parquet     one row per residential address point (≈ housing unit)
  complexes.parquet     multi-unit parcels (≥5 units) + named student complexes + BYU halls
  meetinghouses.parquet LDS meetinghouses (ward meeting places)
  venues.parquet        third places: restaurants, soda shops, gyms, cinemas, parks, overlooks…
and map layers for the web UI (web/public/geo/).

Approximations are recorded per row (`loc_src`, `name_src`) and documented in DATA_SOURCES.md.
"""
from __future__ import annotations

import json
import re
import struct
from pathlib import Path

import numpy as np
import polars as pl

ROOT = Path(__file__).resolve().parents[2]
EXT = ROOT / "data" / "external" / "ugrc"
OUT = Path(__file__).resolve().parent / "data"
WEB = ROOT / "web" / "public" / "geo"
GEOCODES = Path(__file__).resolve().parent / "complex_geocodes.json"
PRIORS = ROOT / "ucsim" / "priors" / "survey_priors.json"

BYU = (-111.6493, 40.2500)   # campus centroid (Harold B. Lee Library area)
UVU = (-111.7129, 40.2773)
KM_PER_DEG_LAT = 111.32
KM_PER_DEG_LON = 111.32 * np.cos(np.radians(40.26))

# Hand-specified facts that public layers do not carry (approximate; see MODEL_ASSUMPTIONS.md).
SPECIAL_COMPLEXES = {
    # name: (kind, beds, beds_per_unit, sex_split, contracted, married_only)
    "Helaman Halls": ("byu_dorm", 2000, 2, True, True, False),
    "Heritage Halls": ("byu_dorm", 2400, 6, True, True, False),
    "Wymount Terrace": ("married", 900, 2, False, False, True),
    "Wyview Park": ("married", 700, 2, False, False, True),
}


def _load(name):
    return json.loads((EXT / f"{name}.json").read_text(encoding="utf-8"))["features"]


def km_dist(lon1, lat1, lon2, lat2):
    return np.hypot((np.asarray(lon1) - lon2) * KM_PER_DEG_LON, (np.asarray(lat1) - lat2) * KM_PER_DEG_LAT)


def _point_in_poly(x, y, ring):
    """Vectorized ray casting for one ring."""
    ring = np.asarray(ring)
    inside = np.zeros(len(x), dtype=bool)
    xj, yj = ring[-1]
    for xi, yi in ring:
        cond = ((yi > y) != (yj > y)) & (x < (xj - xi) * (y - yi) / (yj - yi + 1e-15) + xi)
        inside ^= cond
        xj, yj = xi, yi
    return inside


def build():
    OUT.mkdir(parents=True, exist_ok=True)
    WEB.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ city polygons
    munis = _load("municipalities")

    def city_of(lon, lat):
        city = np.full(len(lon), "Other Utah County", dtype=object)
        for m in munis:
            inside = np.zeros(len(lon), dtype=bool)
            for ring in m["rings"]:
                inside ^= _point_in_poly(lon, lat, ring)
            city[inside] = m["NAME"]
        return city

    # ------------------------------------------------------------------ parcels
    parcels = pl.DataFrame(_load("parcels"), infer_schema_length=None).select(
        "PARCEL_ID", "PARCEL_ADD", "PARCEL_CITY", "PROP_CLASS", "HOUSE_CNT", "BLDG_SQFT", "FLOORS_CNT",
        "BUILT_YR", "TOTAL_MKT_VALUE", "PARCEL_ACRES", "lon", "lat").unique("PARCEL_ID", keep="first")

    # ------------------------------------------------------------------ dwellings (address points)
    addr = pl.DataFrame(_load("addresses"), infer_schema_length=None)
    addr = addr.filter(pl.col("City").is_in(["PROVO", "OREM"]) &
                       pl.col("PtType").is_in(["Residential", "Unknown", "BASE ADDRESS"]) &
                       ~pl.col("UnitType").is_in(["STE", "HNGR", "BLDG"]))
    # A BASE ADDRESS point duplicates its unit points; drop base points on parcels that have unit points.
    has_units = addr.filter(pl.col("UnitID") != "").select("ParcelID").unique()
    addr = addr.filter(~((pl.col("PtType") == "BASE ADDRESS") & pl.col("ParcelID").is_in(has_units["ParcelID"].implode())))
    addr = addr.with_columns(pl.col("ParcelID").alias("PARCEL_ID"))
    per_parcel = addr.group_by("PARCEL_ID").agg(n_units=pl.len())
    d = (addr.join(per_parcel, on="PARCEL_ID", how="left")
         .join(parcels.drop("lon", "lat"), on="PARCEL_ID", how="left"))
    # Exclude obviously non-residential parcels (commercial class with a single address and no units)
    d = d.filter(~((pl.col("PROP_CLASS") == "Commercial") & (pl.col("n_units") <= 1)))
    d = d.with_columns(
        kind=pl.when(pl.col("UnitType") == "TRLR").then(pl.lit("mobile_home"))
        .when(pl.col("n_units") >= 5).then(pl.lit("apartment"))
        .when(pl.col("n_units") >= 2).then(pl.lit("small_multi"))
        .otherwise(pl.lit("house")))
    lon = d["lon"].to_numpy()
    lat = d["lat"].to_numpy()
    d = d.with_columns(
        city=pl.Series(city_of(lon, lat)),
        dist_byu=pl.Series(km_dist(lon, lat, *BYU)),
        dist_uvu=pl.Series(km_dist(lon, lat, *UVU)),
    )
    # Value per unit -> housing quality/price index (rank-normalized later when setting rents)
    d = d.with_columns(
        value_per_unit=(pl.col("TOTAL_MKT_VALUE") / pl.col("n_units").clip(1, None)),
        sqft_per_unit=(pl.col("BLDG_SQFT") / pl.col("n_units").clip(1, None)),
    )

    # ------------------------------------------------------------------ complexes
    apt = d.filter(pl.col("n_units") >= 5).group_by("PARCEL_ID").agg(
        lon=pl.col("lon").mean(), lat=pl.col("lat").mean(), units=pl.len(),
        address=pl.col("PARCEL_ADD").first(), city=pl.col("city").first(),
        built=pl.col("BUILT_YR").first(), sqft=pl.col("BLDG_SQFT").first())
    apt = apt.sort("units", descending=True)
    cx = apt.to_dicts()
    for c in cx:
        c["name"] = None
        c["name_src"] = "address"
        c["loc_src"] = "ugrc_address_points"
    # Named building footprints on these parcels
    bnames = {}
    for b in _load("buildings"):
        if b.get("NAME") and b.get("PARCEL_ID"):
            bnames.setdefault(b["PARCEL_ID"], b["NAME"].title())
    for c in cx:
        if c["PARCEL_ID"] in bnames and re.search(r"(?i)apart|condo|village|court|manor|place|park|terrace|lofts|halls", bnames[c["PARCEL_ID"]]):
            c["name"], c["name_src"] = bnames[c["PARCEL_ID"]], "ugrc_building_name"

    geocodes = json.loads(GEOCODES.read_text(encoding="utf-8")) if GEOCODES.exists() else {}
    survey_share = json.loads(PRIORS.read_text(encoding="utf-8"))["tables"]["complexes"]
    clon = np.array([c["lon"] for c in cx])
    clat = np.array([c["lat"] for c in cx])
    named_extra = []
    for name, g in geocodes.items():
        if not g:
            continue
        if name in SPECIAL_COMPLEXES:
            continue
        dist = km_dist(clon, clat, g["lon"], g["lat"])
        cand = np.where((dist < 0.22))[0]
        cand = [i for i in cand if cx[i]["name_src"] != "survey_geocode"]
        if cand:
            i = max(cand, key=lambda k: cx[k]["units"] / (1 + 5 * dist[k]))
            cx[i]["name"], cx[i]["name_src"] = name, "survey_geocode"
            cx[i]["survey_share"] = survey_share.get(name, 0.0)
        else:
            named_extra.append((name, g))
    complexes = []
    for c in cx:
        complexes.append(dict(
            name=c["name"] or (f"Apartments at {c['address'].title()}" if c["address"] else
                               f"{c['city']} apartment complex #{len(complexes) + 1}"),
            name_src=c["name_src"], lon=c["lon"], lat=c["lat"], units=int(c["units"]),
            city=c["city"], parcel_id=c["PARCEL_ID"], built=c["built"], kind="apartments",
            loc_src="ugrc_address_points", survey_share=float(c.get("survey_share", 0.0))))
    for name, g in named_extra:
        complexes.append(dict(name=name, name_src="survey_geocode", lon=g["lon"], lat=g["lat"],
                              units=max(20, int(400 * survey_share.get(name, 0.002) / 0.01)),
                              city=str(city_of(np.array([g["lon"]]), np.array([g["lat"]]))[0]), parcel_id=None,
                              built=None, kind="apartments", loc_src="osm_nominatim", survey_share=survey_share.get(name, 0.0)))
    for name, (kind, beds, bpu, *_rest) in SPECIAL_COMPLEXES.items():
        g = geocodes.get(name)
        if not g:
            continue
        complexes.append(dict(name=name, name_src="survey_geocode", lon=g["lon"], lat=g["lat"], units=beds // bpu,
                              city="Provo", parcel_id=None, built=None, kind=kind, loc_src="osm_nominatim",
                              survey_share=sum(v for k, v in survey_share.items() if k.startswith(name.split()[0]))))
    cdf = pl.DataFrame(complexes, infer_schema_length=None).with_row_index("complex_id")
    cdf = cdf.with_columns(
        dist_byu=pl.Series(km_dist(cdf["lon"].to_numpy(), cdf["lat"].to_numpy(), *BYU)),
        dist_uvu=pl.Series(km_dist(cdf["lon"].to_numpy(), cdf["lat"].to_numpy(), *UVU)))
    # Contracted (approximate): survey-named complexes near BYU, and dense complexes very near campus.
    cdf = cdf.with_columns(
        contracted=((pl.col("kind") == "byu_dorm") |
                    ((pl.col("name_src") == "survey_geocode") & (pl.col("dist_byu") < 2.2) & (pl.col("kind") == "apartments")) |
                    ((pl.col("dist_byu") < 1.0) & (pl.col("kind") == "apartments") & (pl.col("units") >= 12))),
        married_only=pl.col("kind") == "married",
    )
    cdf.write_parquet(OUT / "complexes.parquet")

    # Link dwellings to complexes by parcel
    pid2cx = {r["parcel_id"]: r["complex_id"] for r in cdf.iter_rows(named=True) if r["parcel_id"]}
    d = d.with_columns(complex_id=pl.col("PARCEL_ID").replace_strict(pid2cx, default=None, return_dtype=pl.Int64))
    dw = d.select(
        pl.col("lon").cast(pl.Float32), pl.col("lat").cast(pl.Float32), "PARCEL_ID", "complex_id", "city", "kind",
        "n_units", pl.col("dist_byu").cast(pl.Float32), pl.col("dist_uvu").cast(pl.Float32),
        pl.col("value_per_unit").cast(pl.Float32), pl.col("sqft_per_unit").cast(pl.Float32),
        pl.col("BUILT_YR").alias("built"), pl.col("UnitType").alias("unit_type"))
    dw.write_parquet(OUT / "dwellings.parquet")

    # ------------------------------------------------------------------ workplace sites (commercial parcels)
    com = parcels.filter((pl.col("PROP_CLASS") == "Commercial") & (pl.col("BLDG_SQFT") >= 2500))
    com = com.with_columns(city=pl.Series(city_of(com["lon"].to_numpy(), com["lat"].to_numpy())))
    com = com.filter(pl.col("city").is_in(["Provo", "Orem"])).select(
        pl.col("lon").cast(pl.Float32), pl.col("lat").cast(pl.Float32), pl.col("BLDG_SQFT").cast(pl.Float32).alias("sqft"),
        "city").with_row_index("site_id")
    com.write_parquet(OUT / "work_sites.parquet")

    # ------------------------------------------------------------------ meetinghouses
    w = [x for x in _load("worship") if x["NAME"].upper().startswith("THE CHURCH OF JESUS")]
    mh = pl.DataFrame({"lon": [x["lon"] for x in w], "lat": [x["lat"] for x in w]}).with_row_index("meetinghouse_id")
    mh = mh.with_columns(city=pl.Series(city_of(mh["lon"].to_numpy(), mh["lat"].to_numpy())))
    mh.write_parquet(OUT / "meetinghouses.parquet")

    # ------------------------------------------------------------------ venues
    venues = []
    soda_re = re.compile(r"(?i)swig|sodalicious|fiiz|thirst|pop shop|twisted sugar|soda")
    dessert_re = re.compile(r"(?i)crumbl|ice cream|cream|dessert|cookie|yogurt|blox|sub zero|rush bowls")
    for p in _load("places"):
        cat, name = p.get("category"), p.get("name") or ""
        if not name or p.get("lon") is None:
            continue
        vt = None
        if soda_re.search(name) and "liquor" not in name.lower():
            vt = "soda_shop"
        elif dessert_re.search(name):
            vt = "dessert"
        elif cat in ("restaurant", "fast_food", "food_court"):
            vt = "restaurant"
        elif cat == "cafe":
            vt = "cafe"
        elif cat in ("fitness_centre", "sports_centre"):
            vt = "gym"
        elif cat in ("cinema", "theatre"):
            vt = "cinema_theatre"
        elif cat in ("museum",):
            vt = "museum"
        elif cat in ("library",):
            vt = "library"
        elif cat in ("stadium",):
            vt = "stadium"
        elif cat in ("viewpoint",):
            vt = "overlook"
        elif cat in ("attraction", "swimming_pool", "community_centre"):
            vt = "recreation"
        elif cat in ("pub", "bar"):
            vt = "bar"
        if vt:
            venues.append(dict(name=name, vtype=vt, lon=p["lon"], lat=p["lat"], src="ugrc_opensourceplaces"))
    for p in _load("parks"):
        venues.append(dict(name=p["NAME"] or "Park", vtype="park", lon=p["lon"], lat=p["lat"], src="ugrc_parks"))
    for t in _load("trailheads"):
        venues.append(dict(name=t["PrimaryName"] + " Trailhead", vtype="trailhead", lon=t["lon"], lat=t["lat"], src="ugrc_trailheads"))
    # Country/latin dance venues named in the College Life survey are not in OSM; placed approximately.
    venues += [
        dict(name="Country dance night (Provo, approx.)", vtype="dance", lon=-111.6605, lat=40.2745, src="synthetic_approximate"),
        dict(name="Country dance night (Orem, approx.)", vtype="dance", lon=-111.6948, lat=40.2960, src="synthetic_approximate"),
        dict(name="Grove Station (Pleasant Grove, approx.)", vtype="dance", lon=-111.7380, lat=40.3640, src="synthetic_approximate"),
    ]
    vdf = pl.DataFrame(venues).with_row_index("venue_id")
    vdf = vdf.with_columns(city=pl.Series(city_of(vdf["lon"].to_numpy(), vdf["lat"].to_numpy())))
    vdf.write_parquet(OUT / "venues.parquet")

    # ------------------------------------------------------------------ web map layers
    _write_web_layers(munis)
    summary = {
        "dwellings": dw.height, "complexes": cdf.height,
        "named_complexes": int((cdf["name_src"] != "address").sum()),
        "meetinghouses": mh.height, "venues": vdf.height,
        "dwellings_by_kind": dict(dw["kind"].value_counts().iter_rows()),
        "dwellings_by_city": dict(dw["city"].value_counts().iter_rows()),
        "venues_by_type": dict(vdf["vtype"].value_counts().iter_rows()),
    }
    (OUT / "summary.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    return summary


def _write_web_layers(munis):
    # Major roads (simplified) as GeoJSON
    keep = {"1", "2", "3", "4", "5", "7", "8", "9", "10", "11"}
    major = {"1", "2", "3", "4", "5"}
    feats = []
    for r in _load("roads"):
        if r.get("CARTOCODE") not in keep:
            continue
        for path in r["paths"]:
            feats.append({"type": "Feature", "properties": {"n": (r.get("FULLNAME") or "").title(),
                                                           "c": 1 if r["CARTOCODE"] in major else 2},
                          "geometry": {"type": "LineString", "coordinates": path}})
    (WEB / "roads.json").write_text(json.dumps({"type": "FeatureCollection", "features": feats}, separators=(",", ":")), encoding="utf-8")
    (WEB / "cities.json").write_text(json.dumps({"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"name": m["NAME"]},
         "geometry": {"type": "Polygon", "coordinates": m["rings"]}} for m in munis]}, separators=(",", ":")), encoding="utf-8")
    # Building footprints: compact binary (int32 microdegree deltas). Header: n_polygons, then per polygon
    # n_vertices followed by vertices.  Decoded in web/src/map/buildings.ts.
    blds = _load("buildings")
    buf = bytearray()
    n = 0
    lon0, lat0 = -111.775, 40.17
    parts = []
    for b in blds:
        ring = b["rings"][0]
        if len(ring) < 4:
            continue
        xs = np.round((np.array([p[0] for p in ring]) - lon0) * 1e5).astype(np.int32)
        ys = np.round((np.array([p[1] for p in ring]) - lat0) * 1e5).astype(np.int32)
        arr = np.empty(len(xs) * 2, dtype=np.int32)
        arr[0::2], arr[1::2] = xs, ys
        parts.append(struct.pack("<i", len(xs)) + arr.tobytes())
        n += 1
    buf += struct.pack("<idd", n, lon0, lat0)
    for p in parts:
        buf += p
    (WEB / "buildings.bin").write_bytes(bytes(buf))


if __name__ == "__main__":
    print(json.dumps(build(), indent=1))
