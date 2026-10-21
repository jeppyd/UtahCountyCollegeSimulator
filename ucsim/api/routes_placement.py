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
                          "kind": ["dorm room", "apartment", "room in a house", "married housing", "family home"][int(U.unit_type[uu])]
                          if int(U.unit_type[uu]) < 5 else "home"})
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
