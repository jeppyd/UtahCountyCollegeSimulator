"""Official Provo/Orem neighborhoods (ucsim/geo/data/neighborhoods.json, from scripts/fetch_neighborhoods.py).

Codes match the `neighborhood` person variable: 0 = Other, k = the k-th neighborhood in the file.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import numpy as np

from .osm_housing import point_in_poly

FILE = Path(__file__).resolve().parent / "data" / "neighborhoods.json"


@lru_cache(maxsize=1)
def load() -> list[dict]:
    if not FILE.exists():
        return []
    out = json.loads(FILE.read_text(encoding="utf-8"))
    for r in out:
        r["np"] = [np.asarray(ring, float) for ring in r["rings"]]
        allp = np.vstack(r["np"])
        r["bbox"] = (allp[:, 0].min(), allp[:, 1].min(), allp[:, 0].max(), allp[:, 1].max())
    return out


def locate(lon, lat) -> np.ndarray:
    """Neighborhood code for each point (0 = outside every mapped neighborhood)."""
    lon = np.atleast_1d(np.asarray(lon, float))
    lat = np.atleast_1d(np.asarray(lat, float))
    code = np.zeros(len(lon), np.uint8)
    for k, r in enumerate(load(), start=1):
        x0, y0, x1, y1 = r["bbox"]
        m = np.where((code == 0) & (lon >= x0) & (lon <= x1) & (lat >= y0) & (lat <= y1))[0]
        if len(m) == 0:
            continue
        inside = np.zeros(len(m), bool)
        for ring in r["np"]:          # even-odd across rings handles holes and multipart shapes
            inside ^= point_in_poly(lon[m], lat[m], ring)
        code[m[inside]] = k
    return code
