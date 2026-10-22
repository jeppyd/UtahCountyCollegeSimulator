"""BYU Housing floor plans (owner-supplied PDFs from BYU Facilities Planning) → apartment rosters for the map and the
simulation, in ucsim/geo/data/plan_units.parquet.

    python -m ucsim.geo.floorplans          # needs data/external/floorplans/<complex>/*.pdf (never committed) and pymupdf

The PDFs stay local (data/external/ is ignored) and so does their geometry. What is kept, per apartment: the building,
floor, apartment number, the beds in each bedroom, and the apartment's centre on the real footprint rounded to a metre
— enough to put each apartment in its place and each resident in a bedroom, nothing a visitor couldn't count from
outside. Plans with text (Revit exports: Heritage Halls, Wyview Park, Riviera, LISR) are read from their room labels;
the plan is placed on its footprint by turning and shifting it until its labels fall inside the outline (scale from
the drawing's 1/16" = 1'-0"). Older scans without text are described in ucsim/config/places/flagship.yaml by hand.
"""
from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path

import numpy as np
import polars as pl

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "data" / "external" / "floorplans"
OUT = Path(__file__).resolve().parent / "data" / "plan_units.parquet"
CLASSROOMS = Path(__file__).resolve().parent / "data" / "classrooms.parquet"
PT_PER_M = 72 / 16 / 0.3048            # 1/16" = 1'-0": 4.5 pt a foot
FLOOR_WORDS = {"1st": 0, "2nd": 1, "3rd": 2, "4th": 3, "5th": 4}


def words(pdf: Path) -> list[tuple[float, float, str]]:
    import pymupdf
    pg = pymupdf.open(pdf)[0]
    return [((x0 + x1) / 2, (y0 + y1) / 2, t) for x0, y0, x1, y1, t, *_ in pg.get_text("words")]


def place_on(pts_pt: np.ndarray, footprint_xy: np.ndarray, scale: float = PT_PER_M, wide: bool = False):
    """Plan points (PDF points, y down) → footprint metres: the turn and shift that put the most of them inside the
    outline (1 m in from the walls), searched over degrees and metre shifts. Returns (a function taking more plan
    points of the same sheet to metres, the share of these points inside). `wide`: the sheet shows part of the building
    (its north half, a wing), so start the search from everywhere inside the outline, not just its middle."""
    p = np.c_[pts_pt[:, 0], -pts_pt[:, 1]] / scale              # metres, y up
    m0 = p.mean(axis=0)
    p = p - m0
    p = p[:: max(1, len(p) // 60)]                              # the search scores a sample of the labels
    ring = footprint_xy
    c0 = ring[:-1].mean(axis=0) if len(ring) > 3 else ring.mean(axis=0)
    # centroid of the outline's area
    x, y = ring[:, 0] - c0[0], ring[:, 1] - c0[1]
    cr = x[:-1] * y[1:] - x[1:] * y[:-1]
    a = cr.sum() / 2
    if abs(a) > 1e-6:
        c0 = c0 + np.array([((x[:-1] + x[1:]) * cr).sum() / (6 * a), ((y[:-1] + y[1:]) * cr).sum() / (6 * a)])
    from .buildings import inside

    def score(q):                     # points inside, also 1 m in every direction (off the walls)
        ok = inside(q[:, 0], q[:, 1], ring)
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            ok &= inside(q[:, 0] + dx, q[:, 1] + dy, ring)
        return int(ok.sum())

    def turned(deg):
        t = np.radians(deg)
        return np.array([[np.cos(t), -np.sin(t)], [np.sin(t), np.cos(t)]])
    starts = [c0]
    if wide:
        lo, hi = ring.min(axis=0), ring.max(axis=0)
        step = max(6.0, np.sqrt((hi - lo).prod() / 150))
        gx, gy = np.meshgrid(np.arange(lo[0], hi[0], step), np.arange(lo[1], hi[1], step))
        g = np.c_[gx.ravel(), gy.ravel()]
        starts = list(g[inside(g[:, 0], g[:, 1], ring)]) or [c0]
    best = (-1, None)
    for st in starts:
        for deg in range(0, 360, 2 if not wide else 10):
            s_ = score(p @ turned(deg).T + st)
            if s_ > best[0]:
                best = (s_, (deg, st))
    deg0, c0 = best[1]
    best = (-1, None)
    span = 4.0 if not wide else 8.0
    for deg in np.arange(deg0 - (2 if not wide else 6), deg0 + (2.01 if not wide else 6.01), 1.0):
        q0 = p @ turned(deg).T + c0
        for dx in np.arange(-span, span + 0.01, 1.0):
            for dy in np.arange(-span, span + 0.01, 1.0):
                s_ = score(q0 + (dx, dy))
                if s_ > best[0]:
                    best = (s_, (deg, dx, dy))
    deg, dx, dy = best[1]
    R = turned(deg)
    shift = c0 + (dx, dy)

    def to_m(pts):
        pts = np.asarray(pts, np.float64)
        return (np.c_[pts[:, 0], -pts[:, 1]] / scale - m0) @ R.T + shift
    q = to_m(pts_pt)
    return to_m, float(inside(q[:, 0], q[:, 1], ring).mean())


# ---------------------------------------------------------------------- Heritage Halls (Revit, 2019)
def heritage() -> list[dict]:
    """Apartments of Heritage Halls buildings 2–16: number 'FWNN' (floor, wing, apartment); rooms A kitchen, B living,
    C–E bedrooms of two beds, F–H baths, J closet, K hall (read off the plans)."""
    from ..engine import places
    pat = re.compile(r"^(\d{4})([A-Z]?)$")
    rows = []
    for code in range(2, 17):
        b = places.by_name(f"Heritage Halls Building {code}")
        if b < 0:
            continue
        ring = places.footprints()["rings"][b]
        # all floors' labels placed together (the floors stack): one fit per building, from its 2nd floor
        per_floor = {}
        for fw, fl in FLOOR_WORDS.items():
            f = SRC / "heritage" / f"HR{code:02d} {fw} Floor.pdf"
            if f.exists():
                per_floor[fl] = [w for w in words(f) if pat.match(w[2])]
        if not per_floor:
            continue
        ref = per_floor.get(1) or next(iter(per_floor.values()))
        ref_xy = np.array([(x, y) for x, y, _ in ref])
        to_m, share = place_on(ref_xy, ring)          # the floors' sheets line up: one fit per building
        for fl, ws in per_floor.items():
            q = to_m(np.array([(x, y) for x, y, _ in ws]))
            rooms = defaultdict(list)
            for (x, y), (_, _, t) in zip(q, ws):
                m = pat.match(t)
                rooms[m.group(1)].append((m.group(2), x, y))
            for apt, rr in rooms.items():
                letters = {r for r, _, _ in rr if r}
                if apt.endswith("00") or len(letters) < 3 or not {"A", "B"} & letters:
                    continue
                top = max((("CDE".index(r) + 1) for r in letters if r in "CDE"), default=1)
                xs = np.array([x for _, x, _ in rr])
                ys = np.array([y for _, _, y in rr])
                rows.append({"complex": "heritage_halls", "building_id": int(b), "building": f"Heritage Halls Building {code}",
                             "floor": fl, "label": apt, "bedrooms": [2] * top,
                             "x_m": round(float(xs.mean())), "y_m": round(float(ys.mean())), "fit": round(share, 2)})
    return rows


# ---------------------------------------------------------------------- sheets in general
ORD = re.compile(r"\b(\d+)(?:st|nd|rd|th)\b", re.I)


def sheet_floor(name: str) -> int | None:
    """Floor index (0 ground, −1 basement) from a sheet's file name; None for roofs, attics, parking, site plans."""
    n = name.lower()
    if "basement" in n:
        m = re.search(r"basement\s*(\d)", n)
        return -int(m.group(1)) if m else -1
    m = ORD.search(name)
    if m and not any(w in n for w in ("parking", "roof", "attic", "mezz", "penthouse", "press box")):
        return int(m.group(1)) - 1
    return None


def sheet_scale(pdf: Path) -> float | None:
    """Points per metre from the sheet's printed scale (1/16" = 1'-0", 1" = 20'), or None."""
    import pymupdf
    t = pymupdf.open(pdf)[0].get_text().replace("\n", " ")
    m = re.search(r"(\d+)/(\d+)\"\s*=\s*1'", t)
    if m:
        return 72 * int(m.group(1)) / int(m.group(2)) / 0.3048
    m = re.search(r"\b1\"\s*=\s*(\d+)'", t)
    if m:
        return 72 / int(m.group(1)) / 0.3048
    return None


# ---------------------------------------------------------------------- classrooms (BYU academic buildings)
ROOM = re.compile(r"^[A-Z]?\d{3,4}[A-Z]?$")
CAP = re.compile(r"cap(?:acity)?\s*[:=]?\s*(\d{1,4})", re.I)


def capacities(pdf: Path) -> list[tuple[str, int, float, float]]:
    """(room, seats, x, y) for each room labelled with a capacity: the capacity label and the room number nearest it."""
    import pymupdf
    pg = pymupdf.open(pdf)[0]
    lines = []
    for b in pg.get_text("dict")["blocks"]:
        for ln in b.get("lines", []):
            t = " ".join(sp["text"] for sp in ln["spans"]).strip()
            x0, y0, x1, y1 = ln["bbox"]
            lines.append(((x0 + x1) / 2, (y0 + y1) / 2, t))
    rooms = [(x, y, t) for x, y, t in lines if ROOM.match(t)]
    caps = []
    for x, y, t in lines:
        m = CAP.search(t)
        if m:
            caps.append((x, y, int(m.group(1))))
        elif re.match(r"^cap", t, re.I):
            near = [(abs(x2 - x) + abs(y2 - y), int(t2)) for x2, y2, t2 in lines
                    if t2.isdigit() and not ROOM.match(t2) and abs(x2 - x) + abs(y2 - y) < 14]
            if near:
                caps.append((x, y, min(near)[1]))
    out, used = [], set()
    for x, y, c in sorted(caps, key=lambda r: r[1]):
        if not rooms:
            break
        d = [np.hypot(x - rx, y - ry) + (1e6 if t in used else 0) for rx, ry, t in rooms]
        j = int(np.argmin(d))
        if d[j] > 40 or c < 8:            # too far from any room number, or a closet's "capacity"
            continue
        used.add(rooms[j][2])
        out.append((rooms[j][2], c, rooms[j][0], rooms[j][1]))
    return out, rooms


def classrooms() -> list[dict]:
    """Every BYU room whose plan gives a seating capacity (classrooms, lecture halls, labs): building, floor, room,
    seats, and where it is on the footprint (rounded to a metre)."""
    from ..engine import places
    codes = places.config().get("codes", {})
    byu = tuple(places.config()["byu"]["centre"])
    rows = []
    for pdf in sorted((SRC / "academic").glob("*.pdf")):
        code = pdf.stem.split()[0]
        fl = sheet_floor(pdf.stem)
        if code not in codes or fl is None:
            continue
        b = places.by_name(codes[code], byu)
        if b < 0:
            continue
        caps, rooms = capacities(pdf)
        if not caps:
            continue
        print(f"  {pdf.stem}: {len(caps)} rooms with seats", flush=True)
        ring = places.footprints()["rings"][b]
        scale = sheet_scale(pdf) or PT_PER_M
        part = any(w in pdf.stem.lower() for w in ("north", "south", "east", "west", "center"))
        allxy = np.array([(x, y) for x, y, _ in rooms])
        to_m, share = place_on(allxy, ring, scale, wide=part)
        q = to_m(np.array([(x, y) for _, _, x, y in caps]))
        for (room, seats, _, _), (mx, my) in zip(caps, q):
            rows.append({"code": code, "building_id": int(b), "building": codes[code], "floor": fl, "room": room,
                         "seats": int(seats), "x_m": round(float(mx)), "y_m": round(float(my)), "fit": round(share, 2)})
    return rows


def build(only: str | None = None):
    if only in (None, "housing"):
        rows = heritage()
        df = pl.DataFrame(rows)
        df.write_parquet(OUT, compression="zstd")
        print(df.group_by("complex").agg(pl.len().alias("apartments"), pl.col("building_id").n_unique().alias("buildings"),
                                         (pl.col("bedrooms").list.sum()).sum().alias("beds"), pl.col("fit").min().alias("worst_fit")))
    if only not in (None, "classrooms"):
        return
    cr = pl.DataFrame(classrooms()).unique(["building_id", "room"], keep="first")
    cr.write_parquet(CLASSROOMS, compression="zstd")
    from .homes import raise_floors
    raise_floors(cr.select("building_id", "floor"))         # a classroom on the 5th floor: the building has five
    with pl.Config(tbl_rows=60):
        print(cr.group_by("code").agg(pl.len().alias("rooms"), pl.col("seats").sum(), pl.col("fit").min()).sort("code"))


if __name__ == "__main__":
    import sys
    build(sys.argv[1] if len(sys.argv) > 1 else None)     # housing | classrooms | (both)
