"""Download public geographic data for Provo/Orem from UGRC (Utah's SGID) ArcGIS services.

Outputs GeoJSON-like JSON files under data/external/ugrc/ (gitignored). Run:

    python scripts/fetch_geodata.py            # everything
    python scripts/fetch_geodata.py parcels    # one layer

The processed, compact world used by the simulator is then built with
`python -m ucsim.geo.build_world` and committed under ucsim/geo/.
"""
from __future__ import annotations

import json
import sys
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "external" / "ugrc"
BASE = "https://services1.arcgis.com/99lidPhWCzftIe9K/arcgis/rest/services"
# Provo + Orem (+ a margin for Lindon/Springville edges)
BBOX = (-111.775, 40.170, -111.570, 40.360)

LAYERS = {
    "parcels": dict(service="Parcels_Utah_LIR", fields="PARCEL_ID,PARCEL_ADD,PARCEL_CITY,PROP_CLASS,PRIMARY_RES,HOUSE_CNT,SUBDIV_NAME,BLDG_SQFT,FLOORS_CNT,BUILT_YR,TOTAL_MKT_VALUE,TAXEXEMPT_TYPE,PARCEL_ACRES", geometry="centroid"),
    "buildings": dict(service="Buildings", fields="NAME,TYPE,ADDRESS,CITY,PARCEL_ID", geometry="polygon", offset=0.00002),
    "addresses": dict(service="UtahAddressPoints", fields="FullAdd,LandmarkName,Building,UnitType,UnitID,City,PtType,Structure,ParcelID", geometry="point"),
    "worship": dict(service="Utah_Places_of_Worship", fields="NAME,CITY", geometry="point"),
    "places": dict(service="OpenSourcePlaces", fields="osm_id,category,name,city,amenity,cuisine,shop,tourism", geometry="point"),
    "parks": dict(service="UtahParksLocal", fields="NAME,CITY,ACRES,TYPE", geometry="centroid"),
    "roads": dict(service="UtahRoads", fields="FULLNAME,CARTOCODE", geometry="polyline", offset=0.00008,
                  where="CARTOCODE IN ('1','2','3','4','5','7','8','9','10','11')"),
    # the street network for travel times (scripts/build_travel.py): every drivable class, with speed limits and one-ways
    "roads_net": dict(service="UtahRoads", fields="FULLNAME,CARTOCODE,SPEED_LMT,ONEWAY,DOT_FCLASS", geometry="polyline",
                      where="CARTOCODE IN ('1','2','3','4','5','6','7','8','9','10','11','16','18')"),
    "municipalities": dict(service="UtahMunicipalBoundaries", fields="NAME,POPLASTESTIMATE", geometry="polygon", offset=0.0003,
                           where="NAME IN ('Provo','Orem')"),
    "higher_ed": dict(service="Schools_HigherEducation", fields="SchoolName,SchoolType,CampusType,City", geometry="point"),
    "trailheads": dict(service="UtahTrailheads", fields="PrimaryName", geometry="point"),
}


def _get(url: str, params: dict, tries: int = 5) -> dict:
    q = urllib.parse.urlencode(params)
    for k in range(tries):
        try:
            with urllib.request.urlopen(f"{url}?{q}", timeout=120) as r:
                return json.loads(r.read())
        except Exception as e:  # network hiccup: exponential backoff
            if k == tries - 1:
                raise
            time.sleep(2 ** (k + 1))
            print("  retry", e, file=sys.stderr)
    return {}


def _ring_centroid(ring):
    xs = [p[0] for p in ring]
    ys = [p[1] for p in ring]
    a = cx = cy = 0.0
    for i in range(len(ring) - 1):
        cross = xs[i] * ys[i + 1] - xs[i + 1] * ys[i]
        a += cross
        cx += (xs[i] + xs[i + 1]) * cross
        cy += (ys[i] + ys[i + 1]) * cross
    if abs(a) < 1e-14:
        return sum(xs) / len(xs), sum(ys) / len(ys), 0.0
    a *= 0.5
    return cx / (6 * a), cy / (6 * a), abs(a)


def fetch_layer(name: str) -> int:
    cfg = LAYERS[name]
    url = f"{BASE}/{cfg['service']}/FeatureServer/0/query"
    common = {
        "where": cfg.get("where", "1=1"),
        "geometry": ",".join(map(str, BBOX)),
        "geometryType": "esriGeometryEnvelope", "inSR": 4326, "outSR": 4326,
        "spatialRel": "esriSpatialRelIntersects", "f": "json",
    }
    count = _get(url, {**common, "returnCountOnly": "true"})["count"]
    page = 2000
    offsets = list(range(0, count, page))

    def one(off):
        params = {**common, "outFields": cfg["fields"], "resultOffset": off, "resultRecordCount": page,
                  "returnGeometry": "true", "geometryPrecision": 6, "orderByFields": "OBJECTID"}
        if "offset" in cfg:
            params["maxAllowableOffset"] = cfg["offset"]
        return _get(url, params).get("features", [])

    with ThreadPoolExecutor(6) as ex:
        pages = list(ex.map(one, offsets))
    feats = []
    for pg in pages:
        for f in pg:
            g = f.get("geometry") or {}
            rec = dict(f["attributes"])
            gt = cfg["geometry"]
            if gt == "point":
                if "x" not in g:
                    continue
                rec["lon"], rec["lat"] = round(g["x"], 6), round(g["y"], 6)
            elif gt == "centroid":
                rings = g.get("rings")
                if not rings:
                    continue
                cx, cy, area = max((_ring_centroid(r) for r in rings), key=lambda t: t[2])
                rec["lon"], rec["lat"] = round(cx, 6), round(cy, 6)
            elif gt == "polygon":
                rings = g.get("rings")
                if not rings:
                    continue
                rec["rings"] = [[[round(x, 6), round(y, 6)] for x, y in r] for r in rings]
                cx, cy, _ = max((_ring_centroid(r) for r in rings), key=lambda t: t[2])
                rec["lon"], rec["lat"] = round(cx, 6), round(cy, 6)
            elif gt == "polyline":
                paths = g.get("paths")
                if not paths:
                    continue
                rec["paths"] = [[[round(x, 5), round(y, 5)] for x, y in p] for p in paths]
            feats.append(rec)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{name}.json").write_text(json.dumps({"layer": cfg["service"], "bbox": BBOX, "features": feats}), encoding="utf-8")
    return len(feats)


if __name__ == "__main__":
    names = sys.argv[1:] or list(LAYERS)
    for n in names:
        t = time.time()
        k = fetch_layer(n)
        print(f"{n:15s} {k:7d} features  {time.time() - t:5.1f}s")
