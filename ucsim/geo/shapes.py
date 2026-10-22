"""Building shapes as rectangles, for laying out apartments and seats inside real footprints.

- `min_rect(xy)`: the footprint's smallest-area enclosing rectangle (rotating calipers over the convex hull). The old
  box used the outline's principal direction, which on near-square buildings tilts 45° and pokes the corners out.
- `wings(xy)`: the footprint split into rectangles that lie inside it — an L-shaped hall becomes two wings, a U three
  — found by slicing the outline (in its rectangle's frame) at its corners and merging slices with the same extent.

Coordinates are metres (placement's frame: east and north of ORIGIN). Each rectangle is (cx, cy, angle, half_len,
half_wid) with angle the long side's direction in radians from east.

    python -m ucsim.geo.shapes          # sets the centroid, box (min_rect) and `wings` columns of ucsim/geo/data/buildings.parquet
"""
from __future__ import annotations

import numpy as np

MIN_WING = 3.0          # m: a wing narrower than this is a sliver, not a wing
MERGE_TOL = 1.2         # m: adjacent slices whose edges differ by less than this are one wing


def _hull(xy: np.ndarray) -> np.ndarray:
    pts = np.unique(np.round(xy, 3), axis=0)
    if len(pts) < 3:
        return pts
    pts = pts[np.lexsort((pts[:, 1], pts[:, 0]))]

    def half(p):
        h = []
        for q in p:
            while len(h) >= 2 and ((h[-1][0] - h[-2][0]) * (q[1] - h[-2][1]) - (h[-1][1] - h[-2][1]) * (q[0] - h[-2][0])) <= 0:
                h.pop()
            h.append(q)
        return h
    lo, up = half(pts), half(pts[::-1])
    return np.array(lo[:-1] + up[:-1])


def min_rect(xy: np.ndarray) -> tuple[float, float, float, float, float]:
    """Smallest-area rectangle around the points: (cx, cy, angle of the long side, half length, half width)."""
    h = _hull(xy)
    if len(h) < 3:
        c = xy.mean(axis=0)
        return float(c[0]), float(c[1]), 0.0, 1.0, 1.0
    e = np.roll(h, -1, axis=0) - h
    ang = np.unique(np.round(np.mod(np.arctan2(e[:, 1], e[:, 0]), np.pi / 2), 6))
    best = None
    for a in ang:
        ca, sa = np.cos(a), np.sin(a)
        u = h[:, 0] * ca + h[:, 1] * sa
        v = -h[:, 0] * sa + h[:, 1] * ca
        area = (u.max() - u.min()) * (v.max() - v.min())
        if best is None or area < best[0] - 1e-9:
            best = (area, a, u.min(), u.max(), v.min(), v.max())
    _, a, u0, u1, v0, v1 = best
    hl, hw = (u1 - u0) / 2, (v1 - v0) / 2
    if hw > hl:                                  # the long side first
        a, hl, hw = a + np.pi / 2, hw, hl
        u0, u1, v0, v1 = v0, v1, -u1, -u0
    ca, sa = np.cos(a), np.sin(a)
    mu, mv = (u0 + u1) / 2, (v0 + v1) / 2
    a = float(np.mod(a + np.pi / 2, np.pi) - np.pi / 2)
    return float(mu * ca - mv * sa), float(mu * sa + mv * ca), a, float(hl), float(hw)


def _cross(u: float, ring: np.ndarray) -> list[tuple[float, float]]:
    """Inside intervals of the polygon along the vertical line at u (ring in the rectangle's frame)."""
    x0, y0 = ring[:, 0], ring[:, 1]
    x1, y1 = np.roll(x0, -1), np.roll(y0, -1)
    m = (x0 <= u) != (x1 <= u)
    if not m.any():
        return []
    t = (u - x0[m]) / (x1[m] - x0[m])
    v = np.sort(y0[m] + t * (y1[m] - y0[m]))
    return [(float(v[i]), float(v[i + 1])) for i in range(0, len(v) - 1, 2)]


def _inter(a, b):
    out = []
    for lo, hi in a:
        for lo2, hi2 in b:
            lo3, hi3 = max(lo, lo2), min(hi, hi2)
            if hi3 - lo3 > 0.5:
                out.append((lo3, hi3))
    return out


def wings(xy: np.ndarray, max_wings: int = 6) -> list[tuple[float, float, float, float, float]]:
    """Rectangles inside the footprint (largest first) that together cover most of it."""
    cx, cy, a, hl, hw = min_rect(xy)
    ca, sa = np.cos(a), np.sin(a)
    d = xy - (cx, cy)
    ring = np.c_[d[:, 0] * ca + d[:, 1] * sa, -d[:, 0] * sa + d[:, 1] * ca]
    if len(ring) > 3 and np.allclose(ring[0], ring[-1]):
        ring = ring[:-1]
    # slice at the corners' u (close corners merged)
    us = np.sort(np.r_[ring[:, 0], -hl, hl])
    cuts = [us[0]]
    for u in us[1:]:
        if u - cuts[-1] > 1.0:
            cuts.append(u)
    cuts[-1] = max(cuts[-1], us[-1])
    slices = []
    for u0, u1 in zip(cuts[:-1], cuts[1:]):
        e = min(0.25, (u1 - u0) / 4)
        iv = _inter(_inter(_cross(u0 + e, ring), _cross((u0 + u1) / 2, ring)), _cross(u1 - e, ring))
        slices.append((u0, u1, iv))
    # merge neighbouring slices whose intervals line up
    rects, open_ = [], []
    for u0, u1, iv in slices:
        nxt = []
        for lo, hi in iv:
            hit = None
            for r in open_:
                if abs(r[2] - lo) < MERGE_TOL and abs(r[3] - hi) < MERGE_TOL:
                    hit = r
                    break
            if hit is not None:
                open_.remove(hit)
                nxt.append([hit[0], u1, max(hit[2], lo), min(hit[3], hi)])
            else:
                nxt.append([u0, u1, lo, hi])
        rects += open_
        open_ = nxt
    rects += open_
    out = []
    for u0, u1, v0, v1 in rects:
        lu, lv = u1 - u0, v1 - v0
        if min(lu, lv) < MIN_WING:
            continue
        mu, mv = (u0 + u1) / 2, (v0 + v1) / 2
        wx, wy = cx + mu * ca - mv * sa, cy + mu * sa + mv * ca
        if lu >= lv:
            out.append((float(wx), float(wy), float(a), lu / 2, lv / 2))
        else:
            b = float(np.mod(a + np.pi / 2 + np.pi / 2, np.pi) - np.pi / 2)
            out.append((float(wx), float(wy), b, lv / 2, lu / 2))
    out.sort(key=lambda r: -r[3] * r[4])
    out = out[:max_wings]
    if not out:                                  # no clean rectangle (a sliver, a ring): a small box at the middle
        out = [(cx, cy, a, max(hl * 0.5, 1.0), max(hw * 0.5, 1.0))]
    return out


def build():
    import polars as pl
    from ..engine.placement import to_xy, to_lonlat
    from .buildings import OUT, centroid, ring_lonlat
    b = pl.read_parquet(OUT)
    box, wcol, fill, cen = [], [], [], []
    for r in b["ring"].to_list():
        ll = ring_lonlat(r)
        cen.append(centroid(ll))
        x, y = to_xy(ll[:, 0], ll[:, 1])
        xy = np.c_[x, y]
        cx, cy, a, hl, hw = min_rect(xy)
        lo, la = to_lonlat(cx, cy)
        box.append((float(lo), float(la), round(a, 4), round(hl, 2), round(hw, 2)))
        ws = wings(xy)
        wcol.append([round(v, 2) if k % 5 != 2 else round(v, 4) for w in ws for k, v in enumerate(w)])
        fill.append(sum(4 * w[3] * w[4] for w in ws))
    box = np.array(box)
    area = b["area_m2"].to_numpy()
    cen = np.array(cen)
    b = b.with_columns(lon=pl.Series(cen[:, 0]), lat=pl.Series(cen[:, 1]), box_lon=pl.Series(box[:, 0]), box_lat=pl.Series(box[:, 1]), angle=pl.Series(box[:, 2]),
                       half_len_m=pl.Series(box[:, 3]), half_wid_m=pl.Series(box[:, 4]),
                       wings=pl.Series(wcol, dtype=pl.List(pl.Float32)))
    b.write_parquet(OUT, compression="zstd", compression_level=19)
    f = np.array(fill) / np.maximum(area, 1)
    print(f"{b.height} buildings: wings cover a median {np.median(f):.0%} of the footprint "
          f"(10th percentile {np.percentile(f, 10):.0%}); {np.mean([len(w) // 5 > 1 for w in wcol]):.1%} have several wings")


if __name__ == "__main__":
    build()
