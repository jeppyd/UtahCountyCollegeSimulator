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

from .osm_housing import address_keys, load_contracted, load_osm, point_in_poly

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


def norm_name(name: str) -> str:
    """Comparable complex name: lower case, without generic words ('The', 'Apartments', 'Apts', 'Condos')."""
    n = re.sub(r"(?i)\b(the|apartments?|apts?|condos?|condominiums?|homes|townhomes)\b", " ", name or "")
    return re.sub(r"[^a-z0-9]+", " ", n.lower()).strip()


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

    for c in cx:
        c["parcels"] = [c["PARCEL_ID"]]
        c["contracted_official"] = False
        c["osm_kind"] = None
        c["extra_units"] = 0
    WEAK = ("address", "ugrc_building_name")
    dlon, dlat = d["lon"].to_numpy(), d["lat"].to_numpy()
    dpar = d["PARCEL_ID"].to_list()

    def new_complex(name, src, parcels, units, lon, lat, kind=None, extra=0):
        cx.append({"PARCEL_ID": parcels[0] if parcels else None, "parcels": list(parcels), "lon": lon, "lat": lat, "units": int(units),
                   "address": None, "city": str(city_of(np.array([lon]), np.array([lat]))[0]), "built": None, "sqft": None,
                   "name": name, "name_src": src, "loc_src": src, "contracted_official": False, "osm_kind": kind, "extra_units": int(extra)})
        return cx[-1]

    # ---- (a) BYU's official contracted housing list, matched to exact UGRC address points
    by_parcel = {c["PARCEL_ID"]: c for c in cx}
    full = [str(a).upper() for a in addr["FullAdd"].to_list()]
    apar, acity = addr["PARCEL_ID"].to_list(), addr["City"].to_list()
    alons, alats = addr["lon"].to_list(), addr["lat"].to_list()
    n_contracted = 0
    for r in load_contracted():
        keys = address_keys(r["address"])
        rows = [k for k, a in enumerate(full) if acity[k] == "PROVO" and any(a == key or a.startswith(key + " ") for key in keys)]
        pids = sorted({apar[k] for k in rows})
        if not pids:
            continue
        alon = float(np.mean([alons[k] for k in rows]))
        alat = float(np.mean([alats[k] for k in rows]))
        n_contracted += 1
        hit = [by_parcel[p] for p in pids if p in by_parcel]
        if hit:
            for c in hit:
                c["name"], c["name_src"], c["contracted_official"] = r["name"], "byu_contracted_list", True
        else:
            m = np.isin(np.array(dpar, dtype=object), pids)
            c = new_complex(r["name"], "byu_contracted_list", pids, max(1, int(m.sum())), alon, alat)
            c["contracted_official"] = True

    # ---- (b) OpenStreetMap outlines: name the parcels that sit inside a named apartment/condo/dorm outline
    osm = [o for o in load_osm() if o["kind"] in ("apartments", "condos", "senior", "mobile_park", "dorm")]
    clon = np.array([c["lon"] for c in cx])
    clat = np.array([c["lat"] for c in cx])
    used = set()
    best_area = np.full(len(cx), np.inf)
    for k, o in enumerate(osm):
        x0, y0 = o["poly"].min(0)
        x1, y1 = o["poly"].max(0)
        cand = np.where((clon >= x0 - 3e-4) & (clon <= x1 + 3e-4) & (clat >= y0 - 3e-4) & (clat <= y1 + 3e-4))[0]
        if not len(cand):
            continue
        ins = cand[point_in_poly(clon[cand], clat[cand], o["poly"])]
        for i in ins:
            if cx[i]["name_src"] in WEAK + ("osm",) and o["area"] < best_area[i]:
                best_area[i] = o["area"]
                cx[i]["name"], cx[i]["name_src"], cx[i]["osm_kind"] = o["name"], "osm", o["kind"]
                used.add(k)
            elif cx[i]["name_src"] not in WEAK + ("osm",):
                cx[i]["osm_kind"] = cx[i]["osm_kind"] or o["kind"]
                used.add(k)
    # nearest named OSM building within 50 m for parcels still unnamed (address points often sit at the street)
    blds = [(k, o) for k, o in enumerate(osm) if o["is_building"]]
    if blds:
        bl = np.array([o["lon"] for _, o in blds])
        bt = np.array([o["lat"] for _, o in blds])
        for i, c in enumerate(cx):
            if c["name_src"] in WEAK:
                dd = km_dist(bl, bt, c["lon"], c["lat"]) * 1000
                j = int(np.argmin(dd))
                if dd[j] < 50:
                    k, o = blds[j]
                    c["name"], c["name_src"], c["osm_kind"] = o["name"], "osm", o["kind"]
                    used.add(k)

    # ---- (c) merge parcels that belong to the same named complex
    groups: dict[str, list[dict]] = {}
    for c in cx:
        if c["name"] and c["name_src"] != "address":
            groups.setdefault(norm_name(c["name"]), []).append(c)
    drop = set()
    for g in groups.values():
        if len(g) < 2:
            continue
        rank = {"byu_contracted_list": 0, "survey_geocode": 1, "osm": 2}
        g.sort(key=lambda c: (rank.get(c["name_src"], 3), -c["units"]))
        head = g[0]
        for c in g[1:]:
            if km_dist(c["lon"], c["lat"], head["lon"], head["lat"]) > 0.6:
                continue
            w0, w1 = head["units"], c["units"]
            head["lon"] = (head["lon"] * w0 + c["lon"] * w1) / max(w0 + w1, 1)
            head["lat"] = (head["lat"] * w0 + c["lat"] * w1) / max(w0 + w1, 1)
            head["units"] += c["units"]
            head["parcels"] += c["parcels"]
            head["contracted_official"] |= c["contracted_official"]
            head["extra_units"] += c["extra_units"]
            drop.add(id(c))
    cx = [c for c in cx if id(c) not in drop]

    # ---- (d) named OSM complexes the county address points miss (e.g. one base address for a large building)
    near_byu_dorms = km_dist(np.array([o["lon"] for o in osm]), np.array([o["lat"] for o in osm]), *BYU) < 1.3 if osm else np.array([])
    taken = {p for c in cx for p in c["parcels"] if p}
    named = {norm_name(c["name"]) for c in cx if c["name"]}
    for k, o in enumerate(osm):
        if k in used or o["kind"] not in ("apartments", "dorm", "condos") or norm_name(o["name"]) in named:
            continue
        if o["kind"] == "dorm" and near_byu_dorms[k]:
            continue  # Helaman/Heritage Halls buildings are modeled as the two BYU hall complexes
        x0, y0 = o["poly"].min(0)
        x1, y1 = o["poly"].max(0)
        box = np.where((dlon >= x0) & (dlon <= x1) & (dlat >= y0) & (dlat <= y1))[0]
        inside = box[point_in_poly(dlon[box], dlat[box], o["poly"])] if len(box) else box
        pids = sorted({dpar[i] for i in inside if dpar[i] not in taken})
        n_dw = int(np.isin(np.array(dpar, dtype=object)[inside], pids).sum()) if len(inside) else 0
        est = int(o["area"] * (o["levels"] or (3 if o["is_building"] else 2)) / 95) if o["is_building"] else 0
        if n_dw == 0 and est < 12:
            continue
        units = max(n_dw, est)
        new_complex(o["name"], "osm", pids, units, o["lon"], o["lat"], o["kind"], extra=min(400, max(0, est - n_dw)))
        taken.update(pids)
        named.add(norm_name(o["name"]))

    # ---- (e) names reported in the surveys (geocoded with Nominatim) for anything still unnamed
    geocodes = json.loads(GEOCODES.read_text(encoding="utf-8")) if GEOCODES.exists() else {}
    survey_share = json.loads(PRIORS.read_text(encoding="utf-8"))["tables"]["complexes"]
    clon = np.array([c["lon"] for c in cx])
    clat = np.array([c["lat"] for c in cx])
    named_extra = []
    for name, g in geocodes.items():
        if not g or name in SPECIAL_COMPLEXES:
            continue
        hit = [c for c in cx if c["name"] and norm_name(c["name"]) == norm_name(name)]
        if hit:
            hit[0]["survey_share"] = survey_share.get(name, 0.0)
            continue
        dist = km_dist(clon, clat, g["lon"], g["lat"])
        cand = [i for i in np.where(dist < 0.22)[0] if cx[i]["name_src"] in WEAK]
        if cand:
            i = max(cand, key=lambda k: cx[k]["units"] / (1 + 5 * dist[k]))
            cx[i]["name"], cx[i]["name_src"] = name, "survey_geocode"
            cx[i]["survey_share"] = survey_share.get(name, 0.0)
        else:
            named_extra.append((name, g))
    special_loc = {}
    for c in cx:
        for sp in SPECIAL_COMPLEXES:
            # "Helaman Hall 3" / "Wymount Terrace 12" match; "Heritage Court" (a separate south-Provo complex) does not
            if c["name"] and norm_name(c["name"]).startswith(norm_name(sp)[:-1]) and km_dist(c["lon"], c["lat"], *BYU) < 1.6:
                special_loc.setdefault(sp, []).append((c["lon"], c["lat"], c["units"]))
                c["osm_kind"] = "special_dup"   # its address points duplicate the special's modeled units
    KIND = {"condos": "condos", "senior": "senior", "mobile_park": "mobile_park", "special_dup": "special_dup"}
    complexes = []
    for c in cx:
        complexes.append(dict(
            name=c["name"] or (f"Apartments at {c['address'].title()}" if c["address"] else
                               f"{c['city']} apartment complex #{len(complexes) + 1}"),
            name_src=c["name_src"], lon=c["lon"], lat=c["lat"], units=int(c["units"]),
            city=c["city"], parcel_id=c["PARCEL_ID"], built=c["built"], kind=KIND.get(c["osm_kind"], "apartments"),
            loc_src=c.get("loc_src", "ugrc_address_points"), survey_share=float(c.get("survey_share", 0.0)),
            contracted_official=bool(c["contracted_official"]), extra_units=int(c["extra_units"]),
            parcels="|".join(str(p) for p in c["parcels"] if p)))
    for name, g in named_extra:
        complexes.append(dict(name=name, name_src="survey_geocode", lon=g["lon"], lat=g["lat"],
                              units=max(20, int(400 * survey_share.get(name, 0.002) / 0.01)),
                              city=str(city_of(np.array([g["lon"]]), np.array([g["lat"]]))[0]), parcel_id=None,
                              built=None, kind="apartments", loc_src="osm_nominatim", survey_share=survey_share.get(name, 0.0),
                              contracted_official=False, extra_units=0, parcels=""))
    for name, (kind, beds, bpu, *_rest) in SPECIAL_COMPLEXES.items():
        g = geocodes.get(name)
        if name in special_loc:  # real location from the named parcels / OSM outline
            pts = np.array(special_loc[name], float)
            g = {"lon": float(np.average(pts[:, 0], weights=pts[:, 2] + 1)), "lat": float(np.average(pts[:, 1], weights=pts[:, 2] + 1))}
        if not g:
            continue
        complexes.append(dict(name=name, name_src="survey_geocode", lon=g["lon"], lat=g["lat"], units=beds // bpu,
                              city="Provo", parcel_id=None, built=None, kind=kind, loc_src="osm_nominatim",
                              survey_share=sum(v for k, v in survey_share.items() if k.startswith(name.split()[0])),
                              contracted_official=False, extra_units=0, parcels=""))
    cdf = pl.DataFrame(complexes, infer_schema_length=None).with_row_index("complex_id")
    cdf = cdf.with_columns(
        dist_byu=pl.Series(km_dist(cdf["lon"].to_numpy(), cdf["lat"].to_numpy(), *BYU)),
        dist_uvu=pl.Series(km_dist(cdf["lon"].to_numpy(), cdf["lat"].to_numpy(), *UVU)))
    # Contracted (approximate): survey-named complexes near BYU, and dense complexes very near campus.
    # Contracted = BYU's halls + the properties on BYU's official 2026-27 contracted housing list.
    cdf = cdf.with_columns(
        contracted=(pl.col("kind") == "byu_dorm") | pl.col("contracted_official"),
        married_only=pl.col("kind") == "married",
    )
    cdf.write_parquet(OUT / "complexes.parquet")

    # Link dwellings to complexes by parcel
    pid2cx = {p: r["complex_id"] for r in cdf.iter_rows(named=True) for p in (r["parcels"] or "").split("|") if p}
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
        "named_by_source": dict(cdf["name_src"].value_counts().iter_rows()),
        "contracted_official_matched": n_contracted,
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
