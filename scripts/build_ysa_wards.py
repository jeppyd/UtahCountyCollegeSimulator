"""Build ucsim/geo/data/ysa_wards.json from the Provo YSA ward listings (PDFs the owner supplied: "Provo YSA
Apartment Listing by Ward (2026-27)" and "On Campus Housing Assignments 2026-2027").

Each row is a stake, a ward, a building or complex (with unit ranges) and its address. Addresses on Provo's grid
("600 N 195 E", "760 E 820 N", "1378 N Freedom Blvd") are placed with a grid fitted to the model's own geocoded
complexes; campus halls and named places ("Heritage Halls", "Riviera") are matched by name. The listings name
buildings, not people, so nothing here is personal.

    python scripts/build_ysa_wards.py listing.pdf on-campus.pdf
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import numpy as np
import polars as pl

ROOT = Path(__file__).resolve().parents[1]
GEO = ROOT / "ucsim" / "geo" / "data"
NAMED_STREETS = {"UNIVERSITY AVE": ("E", 0), "FREEDOM BLVD": ("W", 200), "CENTER ST": ("N", 0)}
# places in the listings with no grid address: matched to the model's complex of that name
BY_NAME = {"HERITAGE HALLS": "Heritage Halls", "HELAMAN HALLS": "Helaman Halls", "WYVIEW PARK": "Wyview Park",
           "CANYON RD": "Riviera Apartments", "BELMONT PLACE": "Belmont Pl"}


def read_rows(pdfs: list[str]) -> list[dict]:
    import pdfplumber
    rows, seen = [], set()
    for f in pdfs:
        with pdfplumber.open(f) as pdf:
            for page in pdf.pages:
                for t in page.extract_tables():
                    for r in t:
                        if not r or len(r) < 4:
                            continue
                        r = [re.sub(r"\s+", " ", (x or "").replace("\n", " ").replace("‐", "-")).strip() for x in r[:4]]
                        if r[0].lower() == "stake" or not r[1] or not r[2]:
                            continue
                        key = tuple(r)
                        if key in seen:             # the campus listing repeats the main listing's campus rows
                            continue
                        seen.add(key)
                        rows.append({"stake": r[0], "ward": r[1], "name": r[2], "address": r[3]})
    return rows


def fit_grid(cx: pl.DataFrame):
    """lon/lat as linear functions of (north, east) grid numbers, fitted robustly to 'Apartments at <address>' names."""
    pat = re.compile(r"(\d+)\s+([NS])\s+(\d+)\s+([EW])\b")
    X, Y = [], []
    for name, lon, lat, city in cx.select(["name", "lon", "lat", "city"]).iter_rows():
        m = pat.search(name or "")
        if m and str(city).lower().startswith("provo"):
            X.append((int(m[1]) * (1 if m[2] == "N" else -1), int(m[3]) * (1 if m[4] == "E" else -1)))
            Y.append((lon, lat))
    X, Y = np.array(X, float), np.array(Y)
    A = np.c_[X, np.ones(len(X))]
    keep = np.ones(len(X), bool)
    for _ in range(4):
        cl, *_ = np.linalg.lstsq(A[keep], Y[keep, 0], rcond=None)
        ca, *_ = np.linalg.lstsq(A[keep], Y[keep, 1], rcond=None)
        e = np.hypot((A @ cl - Y[:, 0]) * 84000, (A @ ca - Y[:, 1]) * 111000)
        keep = e < max(150, np.percentile(e[keep], 90))
    return cl, ca, float(np.sqrt((e[keep] ** 2).mean()))


def grid_numbers(addr: str):
    """(north, east) from a Provo address: two coordinate tokens in either order, or one plus a named street."""
    a = addr.upper().replace(".", "")
    toks = re.findall(r"(\d+)(?:\s*(?:-|&)\s*\d+)?\s+([NSEW])\b", a)
    ns = ew = None
    for num, d in toks:
        v = int(num) * (1 if d in "NE" else -1)
        if d in "NS" and ns is None:
            ns = v
        elif d in "EW" and ew is None:
            ew = v
    for street, (d, v) in NAMED_STREETS.items():
        if street in a:
            if d in "EW" and ew is None:
                ew = v * (1 if d == "E" else -1)
            if d in "NS" and ns is None:
                ns = v
    return (ns, ew) if ns is not None and ew is not None else None


def main(pdfs: list[str]):
    cx = pl.read_parquet(GEO / "complexes.parquet")
    cl, ca, rmse = fit_grid(cx)
    names = {str(n): (lo, la) for n, lo, la in cx.select(["name", "lon", "lat"]).iter_rows()}
    out, miss = [], []
    for r in read_rows(pdfs):
        g = grid_numbers(r["address"])
        lon = lat = None
        src = ""
        if g is not None:
            lon = float(cl[0] * g[0] + cl[1] * g[1] + cl[2])
            lat = float(ca[0] * g[0] + ca[1] * g[1] + ca[2])
            src = "grid"
        else:
            key = next((v for k, v in BY_NAME.items() if k in r["address"].upper() or k in r["name"].upper()), None)
            hit = next((v for n_, v in names.items() if key and key.lower() in n_.lower()), None)
            if hit is not None:
                lon, lat = hit
                src = "name"
        if lon is None:
            miss.append(r)
            continue
        out.append({**r, "lon": round(lon, 6), "lat": round(lat, 6), "geocode": src,
                    "married": r["ward"].upper().startswith("M")})
    meta = {"source": "Provo YSA Apartment Listing by Ward (2026-27) and On Campus Housing Assignments 2026-2027 "
                      "(supplied by the owner)", "grid_rmse_m": round(rmse, 1), "rows": len(out), "unplaced": len(miss),
            "wards": len({(r["stake"], r["ward"]) for r in out}),
            "unplaced_examples": [f"{m['name']} — {m['address']}" for m in miss[:12]]}
    (GEO / "ysa_wards.json").write_text(json.dumps({"meta": meta, "rows": out}, indent=1), encoding="utf-8")
    print(json.dumps(meta, indent=1))


if __name__ == "__main__":
    main(sys.argv[1:])
