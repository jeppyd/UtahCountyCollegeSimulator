"""Non-LDS congregations in Provo/Orem: UGRC places of worship + OpenStreetMap, merged and classified.

Inputs:  data/external/ugrc/worship.json (scripts/fetch_geodata.py)
         OpenStreetMap amenity=place_of_worship via Overpass (fetched here)
Output:  ucsim/geo/data/congregations.json   [{name, affiliation, lon, lat, src}]  (committed)

    python scripts/build_congregations.py [saved_overpass_result.json]
"""
from __future__ import annotations

import json
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
UGRC = ROOT / "data" / "external" / "ugrc" / "worship.json"
OUT = ROOT / "ucsim" / "geo" / "data" / "congregations.json"
BBOX = "40.17,-111.775,40.36,-111.57"
MIRRORS = ["https://overpass-api.de/api/interpreter", "https://maps.mail.ru/osm/tools/overpass/api/interpreter"]
LDS = re.compile(r"latter|jesus christ of|seminary|institute of religion", re.I)
RULES = [  # (regex on name or denomination, affiliation)
    (r"catholic|roman_catholic|st\.? francis|saint francis", "Catholic"),
    (r"jehovah|kingdom hall|adventist|seventh", "Other Christian"),
    (r"mosque|islamic|masjid|muslim", "Muslim"),
    (r"buddh|paramita|zen|sangha|hindu|temple of|sikh|jewish|synagogue|chabad", "Other faith"),
    (r"church|chapel|fellowship|bible|baptist|lutheran|episcopal|anglican|nazarene|assembly|pentecostal|"
     r"evangelical|congregational|methodist|presbyterian|community|calvary|iglesia|the rock|centerpoint|"
     r"harvest|maranatha|protestant|nondenominational", "Protestant"),
]


def classify(text: str) -> str | None:
    for rx, aff in RULES:
        if re.search(rx, text, re.I):
            return aff
    return None


def nice(name: str) -> str:
    small = {"of", "the", "and", "on", "a", "de", "la", "en"}
    words = name.replace("SAINT ", "Saint ").split()
    out = [w if not w.isupper() else (w.lower() if w.lower() in small and k else w.capitalize()) for k, w in enumerate(words)]
    return " ".join(out).replace("Marys", "Mary's").replace("Marks", "Mark's")


def fetch_osm() -> list[dict]:
    if len(sys.argv) > 1 and Path(sys.argv[1]).exists():   # a saved Overpass result, if the mirrors are busy
        return json.loads(Path(sys.argv[1]).read_text(encoding="utf-8")).get("elements", [])
    q = f'[out:json][timeout:90];(nwr["amenity"="place_of_worship"]({BBOX}););out center tags;'
    body = urllib.parse.urlencode({"data": q}).encode()
    for url in MIRRORS:
        try:
            with urllib.request.urlopen(urllib.request.Request(url, data=body), timeout=150) as r:
                return json.loads(r.read().decode("utf-8")).get("elements", [])
        except Exception as e:  # mirrors are often busy
            print(f"{url}: {e}", file=sys.stderr)
    return []


def main() -> int:
    rows = []
    if UGRC.exists():
        feats = json.loads(UGRC.read_text(encoding="utf-8"))
        feats = feats.get("features", feats) if isinstance(feats, dict) else feats
        for f in feats:
            name = f.get("NAME") or ""
            if LDS.search(name):
                continue
            aff = classify(name)
            if aff:
                rows.append({"name": nice(name), "affiliation": aff, "lon": round(f["lon"], 5), "lat": round(f["lat"], 5), "src": "ugrc"})
    for e in fetch_osm():
        t = e.get("tags", {})
        name, den = t.get("name") or "", t.get("denomination") or ""
        if LDS.search(name) or re.search(r"latter|mormon", den, re.I) or not name:
            continue
        aff = classify(f"{name} {den} {t.get('religion', '')}")
        if t.get("religion") == "multifaith":
            aff = None
        lon = e.get("lon", e.get("center", {}).get("lon"))
        lat = e.get("lat", e.get("center", {}).get("lat"))
        if aff and lon is not None:
            rows.append({"name": name, "affiliation": aff, "lon": round(lon, 5), "lat": round(lat, 5), "src": "osm"})
    # merge duplicates (same place within ~60 m, or same name); the UGRC record wins
    out: list[dict] = []
    for r in rows:
        dup = next((o for o in out if np.hypot((o["lon"] - r["lon"]) * 85, (o["lat"] - r["lat"]) * 111) < 0.06
                    or o["name"].lower().replace("saint ", "st ") == r["name"].lower().replace("saint ", "st ")), None)
        if dup is None:
            out.append(r)
    out.sort(key=lambda r: (r["affiliation"], r["name"]))
    OUT.write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(f"{len(out)} congregations:")
    for r in out:
        print(f"  {r['affiliation']:16s} {r['name']} ({r['src']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
