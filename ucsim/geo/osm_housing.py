"""Real named housing: OpenStreetMap apartment/dorm/residential outlines and BYU's official contracted list.

Inputs (fetch with scripts/fetch_osm_housing.py):
  data/external/osm/housing_geom.json     Overpass result: named apartments/dormitory/residential ways with geometry
  ucsim/geo/byu_contracted_2026_27.csv    BYU Off-Campus Housing "Contracted Housing List" (name, size, address)
"""
from __future__ import annotations

import csv
import json
import re
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
OSM = ROOT / "data" / "external" / "osm" / "housing_geom.json"
CONTRACTED = Path(__file__).resolve().parent / "byu_contracted_2026_27.csv"
M_PER_DEG_LAT = 111320.0
M_PER_DEG_LON = 111320.0 * np.cos(np.radians(40.26))

JUNK_NAME = re.compile(r"^(?:[A-Z]{0,2}\d{0,4}[A-Z]?|Building\s+\S+|Bldg\.?\s*\S+|R\d+|\d+\s*[A-Z]?)$", re.I)
FIXES = [(r"\bAparments\b", "Apartments"), (r"\bApts?\.?$", "Apartments"), (r"\s+", " ")]


def clean_name(name: str) -> str | None:
    n = (name or "").strip()
    if len(n) < 3 or JUNK_NAME.match(n):
        return None
    for a, b in FIXES:
        n = re.sub(a, b, n)
    return n.strip()


def classify(tags: dict, name: str) -> str:
    nm = name.lower()
    if re.search(r"retire|senior|assisted|memory care|care center|rehab|nursing home|55\+", nm):
        return "senior"
    if re.search(r"mobile|trailer|manufactured|\brv\b", nm) or tags.get("residential") in ("trailer_park", "mobile"):
        return "mobile_park"
    if tags.get("building") == "dormitory" or tags.get("amenity") == "student_accommodation" or re.search(r"\bhall\b|halls\b|dorm", nm):
        return "dorm"
    if re.search(r"condo|townhom|townhouse|estates|villas?\b|homes\b|cottages", nm) or tags.get("residential") in ("condominium", "townhomes"):
        return "condos"
    if tags.get("landuse") == "residential" and tags.get("residential") not in ("apartments", None):
        return "neighborhood"
    if tags.get("landuse") == "residential" and not tags.get("residential") and not re.search(r"apartment|apts|plaza|place|court|village|park|square|commons|flats|lofts|terrace|tower|manor|gardens|house", nm):
        return "neighborhood"
    return "apartments"


def _area_m2(poly: np.ndarray) -> float:
    x = poly[:, 0] * M_PER_DEG_LON
    y = poly[:, 1] * M_PER_DEG_LAT
    return float(abs(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1))) / 2)


def load_osm() -> list[dict]:
    if not OSM.exists():
        return []
    out = []
    for e in json.loads(OSM.read_text(encoding="utf-8")).get("elements", []):
        geom = e.get("geometry")
        tags = e.get("tags", {})
        name = clean_name(tags.get("name", ""))
        if not geom or len(geom) < 3 or not name:
            continue
        poly = np.array([[g["lon"], g["lat"]] for g in geom], float)
        lv = re.match(r"\d+", str(tags.get("building:levels", "")))
        out.append({"name": name, "kind": classify(tags, name), "poly": poly, "area": _area_m2(poly),
                    "lon": float(poly[:, 0].mean()), "lat": float(poly[:, 1].mean()), "levels": int(lv.group()) if lv else None,
                    "osm_id": e.get("id"), "is_building": "building" in tags})
    return out


def point_in_poly(x: np.ndarray, y: np.ndarray, ring: np.ndarray) -> np.ndarray:
    inside = np.zeros(len(x), dtype=bool)
    xj, yj = ring[-1]
    for xi, yi in ring:
        inside ^= ((yi > y) != (yj > y)) & (x < (xj - xi) * (y - yi) / (yj - yi + 1e-15) + xi)
        xj, yj = xi, yi
    return inside


def load_contracted() -> list[dict]:
    if not CONTRACTED.exists():
        return []
    with open(CONTRACTED, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def address_keys(addr: str) -> list[str]:
    """Normalized 'number dir street' prefixes for matching the official list to UGRC address points."""
    a = addr.upper().replace("AVENUE", "AVE").strip()
    nums = re.match(r"^(\d+)(?:/(\d+))?\s+(.*)$", a)
    if not nums:
        return [a]
    rest = nums.group(3)
    if "UNIVERSITY AVE" in rest and not rest.startswith(("N ", "S ")):
        rest = "N " + rest
    return [f"{n} {rest}" for n in (nums.group(1), nums.group(2)) if n]
