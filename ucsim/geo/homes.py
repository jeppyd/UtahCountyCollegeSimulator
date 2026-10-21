"""Homes on real floors: which building every dwelling is in, on which floor, with its apartment label; and the unit
rosters of the flagship complexes (ucsim/config/places/flagship.yaml), down to their bedrooms.

Input  ucsim/geo/data/{dwellings,buildings,complexes}.parquet, data/external/ugrc/addresses.json
Output ucsim/geo/data/homes.parquet          one row per dwelling (same order as dwellings.parquet)
       ucsim/geo/data/flagship_units.parquet one row per unit of a flagship complex

    python -m ucsim.geo.homes

A dwelling's building is the footprint its address point falls in (else the nearest footprint within 25 m). Its
floor comes from the apartment number when there is one ("Apt 204" → 2nd floor; "Apt 3102" in a 4-floor building →
3rd), else the building's homes are spread over its floors in address order (floor_src says which).
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np
import polars as pl
import yaml

from .buildings import KX, KY, inside, ring_lonlat

ROOT = Path(__file__).resolve().parents[2]
GEO = Path(__file__).resolve().parent / "data"
EXT = ROOT / "data" / "external" / "ugrc"
FLAGSHIP = ROOT / "ucsim" / "config" / "places" / "flagship.yaml"


class Footprints:
    """Point-in-footprint lookups over the building layer."""

    def __init__(self, b: pl.DataFrame):
        from scipy.spatial import cKDTree
        self.b = b
        self.ids = b["building_id"].to_numpy()
        self.rings = [ring_lonlat(r) for r in b["ring"].to_list()]
        self.r = np.sqrt(b["area_m2"].to_numpy()) * 1.2 + 10
        self.tree = cKDTree(np.c_[b["lon"].to_numpy() * KX, b["lat"].to_numpy() * KY])

    def locate(self, lon: np.ndarray, lat: np.ndarray, snap_m: float = 25.0, only: set | None = None) -> np.ndarray:
        """Building row (index into the layer) containing each point; the nearest within snap_m if none; −1."""
        xy = np.c_[lon * KX, lat * KY]
        out = np.full(len(lon), -1, np.int64)
        d, nn = self.tree.query(xy, k=12, distance_upper_bound=400)
        for i in range(len(lon)):
            best = -1
            for dist, j in zip(d[i], nn[i]):
                if not np.isfinite(dist):
                    break
                if only is not None and j not in only:
                    continue
                if dist <= self.r[j] and inside(np.array([lon[i]]), np.array([lat[i]]), self.rings[j])[0]:
                    best = j
                    break
            if best < 0:
                for dist, j in zip(d[i], nn[i]):
                    if not np.isfinite(dist):
                        break
                    if (only is None or j in only) and dist <= snap_m + self.r[j] * 0.5:
                        best = j
                        break
            out[i] = best
        return out


def floor_of_label(label: str, floors: int) -> int | None:
    """Floor (0 = ground) from an apartment number, or None."""
    m = re.search(r"(\d+)", label or "")
    if not m or floors <= 1:
        return None
    s = m.group(1)
    if len(s) < 3:
        return None
    f = int(s[0]) if len(s) in (3, 4) else int(s[:-2])
    return min(max(f, 1), floors) - 1


def one_house_one_footprint(fp: Footprints, row: np.ndarray, lon: np.ndarray, lat: np.ndarray, single: np.ndarray,
                            reach_m: float = 45.0) -> np.ndarray:
    """A house's address point often sits by the street, outside its footprint, so two neighbors can land on the same
    one. Houses that share a footprint with another house: the one inside it (else the closest) keeps it, the others
    take the nearest footprint no house has claimed, within reach_m."""
    row = row.copy()
    sx, sy = fp.b["lon"].to_numpy() * KX, fp.b["lat"].to_numpy() * KY
    hx, hy = lon * KX, lat * KY
    house = np.flatnonzero(single & (row >= 0))
    taken = np.zeros(len(fp.ids), np.int32)
    np.add.at(taken, row[row >= 0], 1)
    order = house[np.argsort(np.hypot(hx[house] - sx[row[house]], hy[house] - sy[row[house]]))]
    claimed = np.zeros(len(fp.ids), bool)
    moved = []
    for i in order:
        j = row[i]
        if not claimed[j]:
            claimed[j] = True
        else:
            moved.append(i)
    for i in moved:
        d, nn = fp.tree.query([hx[i], hy[i]], k=10, distance_upper_bound=reach_m + 30)
        row[i] = -1
        for dist, j in zip(np.atleast_1d(d), np.atleast_1d(nn)):
            if np.isfinite(dist) and not claimed[j] and taken[j] == 0 and fp.b["area_m2"][int(j)] >= 40:
                row[i] = j
                claimed[j] = True
                break
    return row


def _addresses() -> pl.DataFrame:
    a = pl.DataFrame(json.loads((EXT / "addresses.json").read_text(encoding="utf-8"))["features"], infer_schema_length=None)
    return a.filter(pl.col("City").is_in(["PROVO", "OREM"]))


def _label(r: dict) -> str:
    parts = []
    if r.get("Building"):
        parts.append(f"Bldg {r['Building']}")
    if r.get("UnitID"):
        parts.append(f"{(r.get('UnitType') or 'Apt').title()} {r['UnitID']}")
    return " ".join(parts)


def dwellings_on_floors(fp: Footprints, addr: pl.DataFrame) -> pl.DataFrame:
    dw = pl.read_parquet(GEO / "dwellings.parquet")
    lon, lat = dw["lon"].to_numpy().astype(float), dw["lat"].to_numpy().astype(float)
    # each dwelling's own address row: the same parcel and point, taken in file order (build_world kept that order)
    pool: dict = {}
    for r in addr.select("ParcelID", "lon", "lat", "Building", "UnitType", "UnitID").iter_rows(named=True):
        pool.setdefault((r["ParcelID"], round(r["lon"], 5), round(r["lat"], 5)), []).append(r)
    labels = []
    for pid, x, y in zip(dw["PARCEL_ID"].to_list(), lon, lat):
        q = pool.get((pid, round(float(x), 5), round(float(y), 5)))
        labels.append(_label(q.pop(0)) if q else "")
    row = fp.locate(lon, lat)
    row = one_house_one_footprint(fp, row, lon, lat, dw["n_units"].to_numpy() <= 1)
    bid = np.where(row >= 0, fp.ids[np.maximum(row, 0)], -1)
    floors_b = np.where(row >= 0, fp.b["floors"].to_numpy()[np.maximum(row, 0)], 1)
    floor = np.full(len(dw), -1, np.int16)
    src = np.full(len(dw), "", object)
    for i, (lab, nf) in enumerate(zip(labels, floors_b)):
        f = floor_of_label(lab, int(nf))
        if f is not None:
            floor[i], src[i] = f, "number"
    # the rest: one home per building → ground floor; several → spread over the floors in label order
    df = pl.DataFrame({"i": np.arange(len(dw)), "bid": bid, "label": labels, "nf": floors_b, "floor": floor})
    rest = df.filter((pl.col("floor") < 0) & (pl.col("bid") >= 0)).sort(["bid", "label", "i"])
    for _, g in rest.group_by("bid", maintain_order=True):
        ii = g["i"].to_numpy()
        nf = int(g["nf"][0])
        k = np.arange(len(ii))
        floor[ii] = 0 if len(ii) == 1 else (k * nf // len(ii)).astype(np.int16)
        src[ii] = "single" if len(ii) == 1 else "spread"
    floor[floor < 0] = 0
    src[src == ""] = "no_building"
    return pl.DataFrame({"building_id": bid.astype(np.int32), "floor": floor.astype(np.int8), "label": labels,
                         "floor_src": src.astype(str)})


def _pick_buildings(fp: Footprints, spec: dict) -> np.ndarray:
    b = fp.b
    m = np.ones(b.height, bool)
    names = b["name"].fill_null("").to_numpy()
    if "names" in spec:
        m &= np.isin(names, spec["names"])
    if "name_prefix" in spec:
        m &= np.char.startswith(names.astype(str), spec["name_prefix"])
    if "name_pattern" in spec:
        pat = re.compile(spec["name_pattern"])
        m &= np.array([bool(pat.search(n)) for n in names])
    if "near" in spec:
        lo, la, r = spec["near"]
        m &= np.hypot((b["lon"].to_numpy() - lo) * KX, (b["lat"].to_numpy() - la) * KY) <= r
    if "kinds" in spec:
        m &= np.isin(b["kind"].to_numpy(), spec["kinds"])
    if "min_area_m2" in spec:
        m &= b["area_m2"].to_numpy() >= spec["min_area_m2"]
    if "max_area_m2" in spec:
        m &= b["area_m2"].to_numpy() <= spec["max_area_m2"]
    if "exclude" in spec:
        m &= ~np.isin(names, spec["exclude"])
    rows = np.flatnonzero(m)
    # a building mapped in parts (several footprints, one name): the largest part is the building
    area = b["area_m2"].to_numpy()
    best: dict = {}
    for r in rows:
        n = names[r]
        if not n:
            best[("", r)] = r
        elif n not in best or area[r] > area[best[n]]:
            best[n] = r
    return np.array(sorted(best.values()), np.int64)


def _bldg_num(name: str) -> str:
    m = re.search(r"(\d+[A-Z]?)\s*$", name or "")
    return m.group(1) if m else ""


def flagship_rosters(fp: Footprints, addr: pl.DataFrame) -> pl.DataFrame:
    spec = yaml.safe_load(FLAGSHIP.read_text(encoding="utf-8"))["flagship"]
    rows = []
    for key, s in spec.items():
        if s["units_from"] == "dwellings":
            continue                                 # layouts for an ordinary complex's own homes (see complex_layouts)
        rr = _pick_buildings(fp, s["buildings"])
        b = fp.b[rr]
        names = b["name"].fill_null("").to_list()
        floors = [int(s["floors"])] * len(rr) if "floors" in s else [max(int(f), int(s.get("min_floors", 1))) for f in b["floors"].to_list()]
        lay = s["layouts"]
        shares = np.array([l_["share"] for l_ in lay], float)
        units = []                                   # (building row, floor, label)
        if s["units_from"] == "addresses":
            a = addr.filter(pl.col("UnitID") != "")
            if "street" in s:
                a = a.filter(pl.col("FullAdd").str.starts_with(s["street"]))
            lon, lat = a["lon"].to_numpy(), a["lat"].to_numpy()
            if "street_near" in s:
                lo, la, r = s["street_near"]
                keep = np.hypot((lon - lo) * KX, (lat - la) * KY) <= r
                a, lon, lat = a.filter(pl.Series(keep)), lon[keep], lat[keep]
            # by building number in the address when it names one of these buildings, else by the footprint it is in
            by_num = {_bldg_num(n): j for j, n in enumerate(names) if _bldg_num(n)}
            hit = fp.locate(lon, lat, snap_m=15, only=set(rr.tolist()))
            pos = {int(r_): j for j, r_ in enumerate(rr)}
            for k, r in enumerate(a.iter_rows(named=True)):
                j = by_num.get(str(r["Building"]).strip()) if r["Building"] else None
                if j is None and hit[k] >= 0:
                    j = pos.get(int(hit[k]))
                if j is None:
                    continue
                f = floor_of_label(r["UnitID"], floors[j])
                units.append((j, 0 if f is None else f, _label(r)))
        else:
            if "per_floor" in s:
                for j in range(len(rr)):
                    for f in range(floors[j]):
                        for u in range(int(s["per_floor"])):
                            units.append((j, f, f"Room {f + 1}{u + 1:02d}"))
            else:
                # `total` units over the buildings, in proportion to floor area (footprint × floors)
                cap = b["area_m2"].to_numpy() * np.array(floors)
                n = np.floor(cap / cap.sum() * int(s["total"])).astype(int)
                n[np.argsort(-(cap / cap.sum() * int(s["total"]) - n))[: int(s["total"]) - n.sum()]] += 1
                for j in range(len(rr)):
                    for u in range(n[j]):
                        f = u * floors[j] // max(1, n[j])
                        units.append((j, f, f"Apt {f + 1}{u + 1:02d}"))
        units.sort(key=lambda t: (t[0], t[1], t[2]))
        # which buildings are family housing (a split complex: that share of buildings from the north or south end)
        comm = [s.get("community", "single")] * len(rr)
        if "split" in s:
            order = np.argsort(b["lat"].to_numpy())
            if s["split"]["family"] == "north":
                order = order[::-1]
            for j in order[: int(round(len(rr) * float(s["split"]["share_family"])))]:
                comm[j] = "family"
        # layouts in a fixed, even pattern over the units (golden-ratio steps through the shares), never random
        for k, (j, f, label) in enumerate(units):
            ly = s["family_layouts"] if comm[j] == "family" and "family_layouts" in s else lay
            cum = np.cumsum([x["share"] for x in ly]) / sum(x["share"] for x in ly)
            li = min(int(np.searchsorted(cum, (k * 0.6180339887) % 1.0, side="right")), len(ly) - 1)
            sex = (s.get("sexes") or {}).get(names[j], "")
            rows.append({"flagship": key, "complex": s["complex"], "building_id": int(fp.ids[rr[j]]),
                         "building": names[j] or f"{s['complex']} building", "floor": int(f), "label": label,
                         "community": comm[j], "layout": li, "bedrooms": [int(x) for x in ly[li]["bedrooms"]],
                         "baths": int(ly[li].get("baths", 1)), "words": ly[li].get("words", ""), "sex": sex})
        print(f"  {key:16s} {len(rr):3d} buildings  {len(units):5d} units  {sum(sum(r['bedrooms']) for r in rows if r['flagship'] == key):5d} beds")
    return pl.DataFrame(rows)


def build():
    from .buildings import load
    fp = Footprints(load())
    addr = _addresses()
    homes = dwellings_on_floors(fp, addr)
    homes.write_parquet(GEO / "homes.parquet", compression="zstd")
    print(f"homes.parquet: {homes.height} dwellings; floor from", dict(homes["floor_src"].value_counts().iter_rows()))
    fl = flagship_rosters(fp, addr)
    fl.write_parquet(GEO / "flagship_units.parquet", compression="zstd")
    print(f"flagship_units.parquet: {fl.height} units")


if __name__ == "__main__":
    build()
