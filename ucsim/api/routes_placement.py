"""Precise positions for the map (engine/placement.py) and the inside of a building (floors, apartments, bedrooms and
who is in them). Positions are read from the latest part-of-day snapshot the simulation published, so they answer at
once while time runs; the building view takes the workspace lock briefly."""
from __future__ import annotations

import numpy as np
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from ..engine import placement

router = APIRouter()
BLOCK_WORDS = ["morning", "afternoon", "evening", "late evening", "night"]


def _server():
    import sys
    main = sys.modules.get("__main__")
    if getattr(main, "WS", None) is not None and getattr(main, "_include_routers", None) is not None:
        return main
    from . import server
    return server


@router.get("/api/positions/precise")
def positions_precise(u: str = "base", block: str = "now"):
    """Everyone's position in metres from placement.ORIGIN (x east, y north, z up), their building and floor, what
    they are doing and the kind of place: as of the latest part of the day simulated (block=now), or in part 0–4
    (morning … night) of the last full day."""
    S = _server()
    sim = S.WS.sim(u)
    act = sim.systems["activity"]
    f = getattr(act, "snapshot", None)
    if block != "now":
        f = (getattr(act, "day_snaps", None) or {}).get(int(block)) if block.isdigit() else None
        if f is None:
            raise HTTPException(404, "run at least one full day first")
    if f is None:
        with S.WS.lock:
            f = {**placement.frame(sim), "block": -1}
    pos = placement.place(sim, f)
    P = sim.w.P
    n = len(f["ctype"])
    from ..engine.state import CTX
    cols = {
        "x": (pos["x"], {"origin": list(placement.ORIGIN), "m_per_deg": [placement.KX, placement.KY]}),
        "y": (pos["y"], {}), "z": (pos["z"], {}),
        "building": (pos["building"].astype(np.int32), {}), "floor": (pos["floor"].astype(np.uint8), {}),
        "act": (f["act"].astype(np.uint8), {"categories": P.specs["activity_now"].categories}),
        "ctx": (f["ctype"].astype(np.uint8), {"categories": CTX}),
        "place": (np.clip(f["cid"], -1, 2**31 - 1).astype(np.int32), {}),
        "frame": (np.array([f["day"], f["hour"], f.get("block", -1)], np.int32),
                  {"date": str(sim.cal.date(f["day"])), "block_words": BLOCK_WORDS[f["block"]] if 0 <= f.get("block", -1) < 5 else ""}),
    }
    assert all(len(v[0]) == n for k, v in cols.items() if k != "frame")
    return Response(S.pack_columns(cols), media_type="application/octet-stream")


@router.get("/api/building/{b}")
def building(b: int, u: str = "base"):
    """A building's floors with its homes, their bedrooms and who sleeps in each, and who is inside right now."""
    S = _server()
    sim = S.WS.sim(u)
    B = placement.buildings()
    if not 0 <= b < B["n"]:
        raise HTTPException(404, "no such building")
    from ..analysis.person import synthetic_name
    with S.WS.lock:
        w = sim.w
        P, U = w.P, w.units
        f = getattr(sim.systems["activity"], "snapshot", None) or placement.frame(sim)
        pos = placement.place(sim, f)
        here_now = np.flatnonzero(pos["building"] == b)
        units = np.flatnonzero(U.building_id == b) if U.building_id is not None else np.empty(0, np.int64)
        room = P.internal["room"][: P.n]
        present = P["present"][: P.n].astype(bool)
        cxn = w.complexes["name"].to_list() if hasattr(w, "complexes") and w.complexes is not None else []
        homes = []
        L = placement.layout(w)
        for uu in units.tolist():
            shape = L.outlines(uu)
            rooms = []
            for k, r in enumerate(range(int(U.room0[uu]), int(U.room0[uu]) + int(U.n_rooms[uu]))):
                who = np.flatnonzero((room == r) & present)
                rooms.append({"room": r, "beds": int(U.room_cap[r]), "shape": shape["rooms"][k] if k < len(shape["rooms"]) else None,
                              "people": [{"id": int(i), "name": synthetic_name(P, int(i))} for i in who.tolist()]})
            c = int(U.complex_id[uu])
            homes.append({"unit": uu, "label": U.label[uu] if U.label is not None else "", "floor": int(U.floor[uu]),
                          "complex": cxn[c] if 0 <= c < len(cxn) else None, "beds": int(U.capacity[uu]), "rooms": rooms,
                          "shape": shape["unit"], "living": shape["living"],
                          "kind": ("hall apartment" if int(U.unit_type[uu]) == 0 and int(U.n_rooms[uu]) > 1 else
                                   ["dorm room", "apartment", "room in a house", "married housing", "family home"][int(U.unit_type[uu])]
                                   if int(U.unit_type[uu]) < 5 else "home")})
        acts = P.specs["activity_now"].categories
        now = [{"id": int(i), "name": synthetic_name(P, int(i)), "floor": int(pos["floor"][i]),
                "doing": acts[int(f["act"][i])] if int(f["act"][i]) < len(acts) else ""} for i in here_now.tolist()[:400]]
        return S.jresp({"building": b, "name": B["name"][b], "kind": str(B["kind"][b]), "floors": int(B["floors"][b]),
                        "origin": list(placement.ORIGIN), "m_per_deg": [placement.KX, placement.KY], "storey_m": placement.STOREY,
                        "area_m2": float(B["area"][b]), "homes": sorted(homes, key=lambda h: (h["floor"], h["label"])),
                        "inside_now": now, "n_inside_now": int(len(here_now)),
                        "when": {"day": int(f["day"]), "hour": int(f["hour"]), "date": str(sim.cal.date(int(f["day"])))}})


_CORE: dict = {}


@router.get("/api/buildings/core")
def buildings_core(u: str = "base"):
    """The buildings people use in this world, drawn standing in 3D: homes of simulated people, the halls, campus
    buildings, venues, churches and workplaces (everything else is drawn flat)."""
    S = _server()
    sim = S.WS.sim(u)
    U = sim.w.units
    key = (id(U), len(U.lon))
    if key not in _CORE:
        import polars as pl
        from ..geo.buildings import OUT
        B = placement.buildings()
        ids = set()
        if U.building_id is not None:
            ids |= set(np.unique(U.building_id[U.building_id >= 0]).tolist())
        f = OUT.parent / "place_buildings.parquet"
        if f.exists():
            ids |= set(pl.read_parquet(f)["building_id"].to_list())
        if B["n"]:
            ids |= set(np.flatnonzero(np.isin(B["kind"], ["campus", "dorm", "school", "church", "sports", "civic"])).tolist())
        _CORE.clear()
        _CORE[key] = np.array(sorted(ids), np.int32)
    return Response(_CORE[key].tobytes(), media_type="application/octet-stream")


@router.get("/api/now/person/{i}")
def now_person(i: int, u: str = "base"):
    """One person at this moment, in words: doing what, where, with whom (and how they know them), at which occasion
    and why, and what's on their mind (analysis/now.py)."""
    S = _server()
    sim = S.WS.sim(u)
    from ..analysis.now import person_now
    with S.WS.lock:
        if not 0 <= i < sim.w.P.n:
            raise HTTPException(404, "no such person")
        return S.jresp(person_now(sim, i))


@router.get("/api/now/occasions")
def now_occasions(u: str = "base", block: str = "now"):
    """What's happening right now: every occasion people are at in the latest part of the day (or part 0–4 of the last
    full day), with how many are there and where (for the map's pins and the 'right now' list)."""
    S = _server()
    sim = S.WS.sim(u)
    act = sim.systems["activity"]
    f = getattr(act, "snapshot", None) if block == "now" else (getattr(act, "day_snaps", None) or {}).get(int(block)) if block.isdigit() else None
    if f is None:
        return S.jresp({"occasions": [], "counts": {}})
    from ..engine.state import CTX_ID
    m = ((f["ctype"] == CTX_ID["occasion"]) | (f["ctype"] == CTX_ID["date"])) & f["present"]
    oid, inv, n = np.unique(f["cid"][m], return_inverse=True, return_counts=True)
    # pins sit where the people are (a dinner in the host's apartment, not the building's middle)
    pos = placement.place(sim, f)
    px = np.bincount(inv, weights=pos["x"][m].astype(np.float64)) / np.maximum(n, 1)
    py = np.bincount(inv, weights=pos["y"][m].astype(np.float64)) / np.maximum(n, 1)
    plon, plat = placement.to_lonlat(px, py)
    with S.WS.lock:
        O = sim.book.occ
        pos = O.pos(oid.astype(np.int64))
        ok = pos >= 0
        oid, n, pos, plon, plat = oid[ok], n[ok], pos[ok], plon[ok], plat[ok]
        kinds = O.cols["kind"][pos]
        book = sim.book
        rows = []
        for o, k, c, p, lo, la in zip(oid.tolist(), kinds.tolist(), n.tolist(), pos.tolist(), plon.tolist(), plat.tolist()):
            kind = book.kinds[k]
            v = book.vocab.get(kind, {})
            lab = int(O.cols["label"][p])
            rows.append({"id": int(o), "kind": kind, "label": v.get("label", kind), "category": v.get("category", "social"),
                         "name": book.labels[lab] if 0 <= lab < len(book.labels) else None, "n": int(c),
                         "lon": lo, "lat": la,
                         "start": int(O.cols["start"][p]), "dur": int(O.cols["dur"][p])})
    rows.sort(key=lambda r: -r["n"])
    counts: dict = {}
    for r in rows:
        c = counts.setdefault(r["label"], {"label": r["label"], "category": r["category"], "occasions": 0, "people": 0})
        c["occasions"] += 1
        c["people"] += r["n"]
    return S.jresp({"occasions": rows[:3000], "counts": sorted(counts.values(), key=lambda c: -c["people"]),
                    "day": int(f["day"]), "block": int(f.get("block", -1)), "date": str(sim.cal.date(int(f["day"])))})
