"""Download official neighborhood boundaries for Provo and Orem (names and outlines only).

Sources (public ArcGIS services; only the name field and geometry are requested, no contact fields):
  Provo City ComDev/Neighborhoods FeatureServer layer 1 (35 neighborhoods)
  Orem City Neighborhoods MapServer layer 0 ("Orem Neighborhoods in Action", 22 named)

Writes the compact, committed files used by the simulator and the map:
  ucsim/geo/data/neighborhoods.json      [{name, city, rings: [[[lon, lat], ...]]}]
  web/public/geo/neighborhoods.json      same, for the map layer

    python scripts/fetch_neighborhoods.py
"""
from __future__ import annotations

import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCES = [
    ("Provo", "https://gispublicweb.provo.gov/ArcGIS/rest/services/ComDev/Neighborhoods/FeatureServer/1/query", "NBHD_NAME"),
    ("Orem", "https://maps.orem.gov/arcgis/rest/services/Neighborhoods/MapServer/0/query", "DISTRICT"),
]
RENAME = {("Orem", "Orem"): "Orem South", ("Orem", "Orchard"): "Orchard (Orem East)"}


def fetch(url: str, field: str) -> dict:
    q = {"where": "1=1", "outFields": field, "returnGeometry": "true", "outSR": "4326",
         "maxAllowableOffset": "0.00015", "geometryPrecision": "5", "f": "json"}
    with urllib.request.urlopen(url + "?" + urllib.parse.urlencode(q), timeout=90) as r:
        return json.loads(r.read().decode("utf-8"))


def main() -> int:
    out = []
    for city, url, field in SOURCES:
        data = fetch(url, field)
        for f in data.get("features", []):
            name = (f["attributes"].get(field) or "").strip()
            rings = f.get("geometry", {}).get("rings") or []
            if not name or name == "Unclassified" or not rings:
                continue
            out.append({"name": RENAME.get((city, name), name), "city": city, "rings": rings})
    if not out:
        print("no neighborhoods fetched", file=sys.stderr)
        return 1
    out.sort(key=lambda r: (r["city"] != "Provo", r["name"]))
    for path in (ROOT / "ucsim" / "geo" / "data" / "neighborhoods.json", ROOT / "web" / "public" / "geo" / "neighborhoods.json"):
        path.write_text(json.dumps(out, separators=(",", ":")), encoding="utf-8")
    print(f"{len(out)} neighborhoods: " + ", ".join(r["name"] for r in out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
