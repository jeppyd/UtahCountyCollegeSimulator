"""Does the map show people where the simulation has them? (engine/placement.py draws; this checks the drawing.)

For everyone present in a frame (activity keeps one per block), by kind of place:

- placed:      the simulation's point for the place lies inside a real building footprint (a place the map can stand up);
- in_building: the drawn dot lies inside the footprint of that same building (or, for homes, the home's building);
- floor_ok:    the drawn height is a floor the building has (homes: the home's own floor or, for a house, upstairs);
- together:    people the simulation has in one group (same context: a class, a date, a ward) are drawn within reach of
               each other (not asked of strangers sharing a place: a restaurant's diners, a gym's, campus);
- apart:       people in different groups are not drawn on top of each other (no two dots within 0.3 m).

    python -m ucsim.analysis.sync_check --scale 0.05 --days 3      # a table by kind of place
"""
from __future__ import annotations

import numpy as np

from ..engine import placement
from ..engine.state import CTX

def footprints():
    from ..engine.places import footprints as fp
    return fp()


def containing(x: np.ndarray, y: np.ndarray) -> np.ndarray:
    from ..engine.places import containing as c
    return c(x, y)


def check(sim, f: dict | None = None, pos: dict | None = None) -> dict:
    """Per kind of place: counts and shares (see the module docstring), plus a few examples of misses."""
    f = f if f is not None else sim.systems["activity"].snapshot
    pos = pos if pos is not None else placement.place(sim, f)
    U = sim.w.units
    present = f["present"] & (f["ctype"] != placement.NONE)
    ii = np.flatnonzero(present)
    ct = f["ctype"][ii].astype(np.int64)
    # where the simulation has them: homes by the home's building, everything else by its point
    sx, sy = placement.to_xy(f["lon"][ii], f["lat"][ii])
    want = containing(sx, sy)
    home = ct == 0
    if U.building_id is not None and home.any():
        hb = U.building_id[np.clip(f["cid"][ii][home], 0, len(U.lon) - 1)]
        want[home] = np.where(hb >= 0, hb, want[home])
    got = containing(pos["x"][ii].astype(np.float64), pos["y"][ii].astype(np.float64))
    F = footprints()
    floors = np.where(want >= 0, F["floors"][np.maximum(want, 0)], 1)
    fl = np.round((pos["z"][ii] - placement.EYE) / placement.STOREY).astype(np.int64)
    floor_ok = (fl >= -2) & (fl < np.maximum(floors, 1))          # (classrooms can be in a basement)
    # groups: same (ctype, cid) and, for homes, same unit — drawn within reach of each other
    key = ct * (1 << 40) + f["cid"][ii].astype(np.int64)
    order = np.argsort(key, kind="stable")
    k_s = key[order]
    start = np.r_[0, np.flatnonzero(np.diff(k_s)) + 1]
    gid = np.empty(len(ii), np.int64)
    gid[order] = np.repeat(np.arange(len(start)), np.diff(np.r_[start, len(k_s)]))
    gx = np.bincount(gid, pos["x"][ii]) / np.bincount(gid)
    gy = np.bincount(gid, pos["y"][ii]) / np.bincount(gid)
    spread = np.hypot(pos["x"][ii] - gx[gid], pos["y"][ii] - gy[gid])
    together = spread < 60.0
    ambient = np.isin(ct, [CTX.index(k) for k in placement.AMBIENT])
    # overlaps between different groups
    xyz = np.round(np.c_[pos["x"][ii], pos["y"][ii], pos["z"][ii]] / 0.3).astype(np.int64)
    _, inv, cnt = np.unique(xyz, axis=0, return_inverse=True, return_counts=True)
    stacked = cnt[inv.ravel()] > 1
    rows = []
    for c in np.unique(ct):
        m = ct == c
        placed = want[m] >= 0
        rows.append({"place": CTX[c], "people": int(m.sum()), "placed": float(placed.mean()),
                     "in_building": float((got[m] == want[m])[placed].mean()) if placed.any() else float("nan"),
                     "floor_ok": float(floor_ok[m][placed].mean()) if placed.any() else float("nan"),
                     "together": float(together[m].mean()) if not ambient[m].all() else float("nan"),
                     "stacked": float(stacked[m].mean()),
                     "miss_examples": [int(p) for p in ii[m][(want[m] >= 0) & (got[m] != want[m])][:3]]})
    rows.sort(key=lambda r: -r["people"])
    tot = {"people": int(len(ii)), "placed": float((want >= 0).mean()) if len(ii) else 0.0,
           "in_building": float((got == want)[want >= 0].mean()) if (want >= 0).any() else 0.0,
           "floor_ok": float(floor_ok[want >= 0].mean()) if (want >= 0).any() else 0.0,
           "stacked": float(stacked.mean()) if len(ii) else 0.0}
    return {"block": f.get("block"), "day": f.get("day"), "total": tot, "rows": rows}


def table(rep: dict) -> str:
    out = [f"day {rep['day']} block {rep['block']}: {rep['total']['people']} people; "
           f"placed {rep['total']['placed']:.1%}, drawn in that building {rep['total']['in_building']:.1%}, "
           f"floor ok {rep['total']['floor_ok']:.1%}, stacked {rep['total']['stacked']:.1%}",
           f"{'place':14s} {'people':>6s} {'placed':>7s} {'in bldg':>7s} {'floor':>6s} {'togeth':>6s} {'stack':>6s}"]
    for r in rep["rows"]:
        out.append(f"{r['place']:14s} {r['people']:6d} {r['placed']:7.1%} {r['in_building']:7.1%} {r['floor_ok']:6.1%} "
                   f"{r['together']:6.1%} {r['stacked']:6.1%}")
    return "\n".join(out)


if __name__ == "__main__":
    import argparse
    from ..engine.runner import new_simulation
    ap = argparse.ArgumentParser()
    ap.add_argument("--scale", type=float, default=0.05)
    ap.add_argument("--days", type=int, default=3)
    ap.add_argument("--seed", type=int, default=4)
    a = ap.parse_args()
    sim = new_simulation(scale=a.scale, seed=a.seed)
    sim.run_days(a.days)
    for h in (4, 3, 3, 3):       # through the day: morning classes, afternoon, evening, night
        sim.advance_hours(h)
        print(table(check(sim)), "\n")
