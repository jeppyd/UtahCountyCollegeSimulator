"""Geocode named student-housing complexes with OpenStreetMap Nominatim.

Respects the Nominatim usage policy (≤1 request/second, identifying User-Agent,
results cached in ucsim/geo/complex_geocodes.json so this runs once).
Data © OpenStreetMap contributors (ODbL).
"""
from __future__ import annotations

import json
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "ucsim" / "geo" / "complex_geocodes.json"
PRIORS = ROOT / "ucsim" / "priors" / "survey_priors.json"
VIEWBOX = "-111.78,40.37,-111.56,40.16"
UA = "UtahCountyCollegeSimulator/0.1 (research prototype; synthetic population)"

# Extra complexes well known in the BYU/UVU housing market but absent/rare in the survey list.
EXTRA = ["Helaman Halls", "Heritage Halls", "Wymount Terrace", "The Village at South Campus", "Joaquin Village",
         "The Quarry", "Kensington Manor", "Moon River", "Stadium Terrace", "The Lodge", "Roosevelt Apartments",
         "Northfield Apartments", "Ivy Lofts", "University Villa", "The Cottages", "Somerset Apartments"]


def _query(q: str):
    params = urllib.parse.urlencode({"q": q, "format": "json", "limit": 3, "viewbox": VIEWBOX, "bounded": 1})
    req = urllib.request.Request(f"https://nominatim.openstreetmap.org/search?{params}", headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read())


def clean(name: str) -> str:
    n = re.sub(r"^Helaman Halls:.*", "Helaman Halls", name)
    n = re.sub(r"^Heritage Halls.*", "Heritage Halls", n)
    return n.replace("Riveria", "Riviera").replace("Wymount Apartments", "Wymount Terrace")


def main():
    cache = json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}
    names = list(json.loads(PRIORS.read_text(encoding="utf-8"))["tables"]["complexes"]) + EXTRA
    names = [n for n in names if n not in ("House", "None of the Above")]
    for name in names:
        key = clean(name)
        if key in cache:
            continue
        hit = None
        base = re.sub(r"\b(Apartments|Condominiums|Condos)\b", "", key).strip()
        for q in (f"{key}, Provo", f"{key}, Orem", f"{base} Apartments, Provo", f"{base} Apartments, Orem"):
            try:
                res = _query(q)
            except Exception as e:  # noqa: BLE001
                print("error", q, e)
                res = []
            time.sleep(1.1)
            res = [r for r in res if r.get("class") in ("building", "landuse", "place", "amenity", "leisure", "residential")
                   or r.get("type") in ("residential", "apartments", "dormitory", "yes", "house")]
            if res:
                r = res[0]
                hit = {"lat": float(r["lat"]), "lon": float(r["lon"]), "display": r["display_name"][:120],
                       "osm_type": r.get("type"), "query": q}
                break
        cache[key] = hit
        print(f"{key:35s} -> {hit and (hit['lat'], hit['lon'])}")
        CACHE.write_text(json.dumps(cache, indent=1), encoding="utf-8")
    CACHE.write_text(json.dumps(cache, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
