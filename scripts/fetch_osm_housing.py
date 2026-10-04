"""Download named apartment / dormitory / residential outlines for Provo-Orem from OpenStreetMap (Overpass API).

Output: data/external/osm/housing_geom.json (gitignored; OSM data (c) OpenStreetMap contributors, ODbL). Run:

    python scripts/fetch_osm_housing.py

then rebuild the world with `python -m ucsim.geo.build_world`. BYU's official contracted-housing list
(ucsim/geo/byu_contracted_2026_27.csv) is committed directly; see docs/DATA_SOURCES.md.
"""
from __future__ import annotations

import json
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "external" / "osm" / "housing_geom.json"
BBOX = "40.17,-111.775,40.36,-111.57"   # south, west, north, east
MIRRORS = ["https://overpass-api.de/api/interpreter",
           "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
           "https://overpass.kumi.systems/api/interpreter"]
SELECTORS = [
    'way["building"~"^(apartments|dormitory|residential)$"]["name"]',
    'way["landuse"="residential"]["name"]',
    'way["amenity"="student_accommodation"]',
    'way["building"="dormitory"]',
    'node["building"~"^(apartments|dormitory)$"]["name"]',
    'node["amenity"="student_accommodation"]',
    'relation["landuse"="residential"]["name"]',
    'relation["building"="apartments"]["name"]',
]
QUERY = "[out:json][timeout:120];(" + "".join(f"{s}({BBOX});" for s in SELECTORS) + ");out center geom tags;"


def main() -> int:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    body = urllib.parse.urlencode({"data": QUERY}).encode()
    for attempt in range(4):
        for url in MIRRORS:
            try:
                with urllib.request.urlopen(urllib.request.Request(url, data=body), timeout=180) as r:
                    data = json.loads(r.read().decode("utf-8"))
                n = len(data.get("elements", []))
                if n:
                    OUT.write_text(json.dumps(data), encoding="utf-8")
                    print(f"{n} elements from {url} -> {OUT}")
                    return 0
            except Exception as e:  # mirrors are often busy; try the next one
                print(f"{url}: {e}", file=sys.stderr)
        time.sleep(2 ** (attempt + 1))
    return 1


if __name__ == "__main__":
    sys.exit(main())
