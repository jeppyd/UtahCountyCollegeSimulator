"""The real Provo YSA wards (geo/data/ysa_wards.json, built by scripts/build_ysa_wards.py from the 2026-27 listings).

Each housing unit near a listed building or complex belongs to that building's ward; where several wards share one
address (Glenwood, Wyview, the halls) the complex's units are split among them in proportion to the listing rows.
At smaller world sizes a ward would have only a handful of members, so neighbouring wards of the same stake are
merged until each has `min_size` members; the merged ward keeps both numbers in its name.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

import numpy as np

GEO = Path(__file__).resolve().parent.parent / "geo" / "data"
NEAR_M = 150          # a unit this close to a listed address belongs to its ward
SAME_SPOT_M = 30      # listed rows this close together share one place (split its units among their wards)


@lru_cache(maxsize=1)
def listing() -> dict:
    p = GEO / "ysa_wards.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {"meta": {}, "rows": []}


def _num(s: str) -> int:
    m = re.search(r"\d+", s)
    return int(m.group()) if m else 0


def ordinal(n: int) -> str:
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def real_wards() -> tuple[list[tuple[str, str]], dict]:
    """The listed wards as (stake, ward) keys in stake/ward order, and key → index."""
    keys = sorted({(r["stake"], r["ward"]) for r in listing()["rows"]},
                  key=lambda k: (k[0].startswith("M"), _num(k[0]), _num(k[1])))
    return keys, {k: i for i, k in enumerate(keys)}


def unit_wards(lon: np.ndarray, lat: np.ndarray) -> np.ndarray:
    """For each unit, the index of its real ward (−1 when no listed building is near)."""
    rows = listing()["rows"]
    keys, idx = real_wards()
    out = np.full(len(lon), -1, np.int32)
    if not rows or not len(lon):
        return out
    elon = np.array([r["lon"] for r in rows])
    elat = np.array([r["lat"] for r in rows])
    ew = np.array([idx[(r["stake"], r["ward"])] for r in rows])
    kx, ky = 111320 * np.cos(np.radians(40.25)), 110540
    # places: rows within SAME_SPOT_M of each other (one address with several wards)
    spot = np.full(len(rows), -1)
    for i in range(len(rows)):
        if spot[i] < 0:
            near = np.hypot((elon - elon[i]) * kx, (elat - elat[i]) * ky) < SAME_SPOT_M
            spot[near & (spot < 0)] = i
    # nearest place for each unit (in chunks to bound memory)
    best = np.full(len(lon), -1)
    for a in range(0, len(lon), 4000):
        d = np.hypot((lon[a:a + 4000, None] - elon[None]) * kx, (lat[a:a + 4000, None] - elat[None]) * ky)
        j = d.argmin(axis=1)
        ok = d[np.arange(len(j)), j] < NEAR_M
        best[a:a + 4000] = np.where(ok, spot[j], -1)
    for s in np.unique(best[best >= 0]):
        us = np.flatnonzero(best == s)                      # units at this place, in unit order
        wards, counts = np.unique(ew[spot == s], return_counts=True)
        cuts = np.round(np.cumsum(counts) / counts.sum() * len(us)).astype(int)
        start = 0
        for wd, c in zip(wards, cuts):
            out[us[start:c]] = wd
            start = c
    return out


def merge_plan(members_per_real: np.ndarray, min_size: int) -> list[list[int]]:
    """Groups of real wards (consecutive wards within one stake) with at least min_size members each."""
    keys, _ = real_wards()
    groups, cur, cur_n, cur_stake = [], [], 0, None
    for i, (stake, _w) in enumerate(keys):
        n = int(members_per_real[i])
        if n == 0:
            continue
        if cur and (stake != cur_stake or cur_n >= min_size):
            groups.append(cur)
            cur, cur_n = [], 0
        cur.append(i)
        cur_n += n
        cur_stake = stake
    if cur:
        if groups and cur_n < min_size and keys[groups[-1][-1]][0] == cur_stake:
            groups[-1] += cur
        else:
            groups.append(cur)
    return groups


def group_name(group: list[int]) -> tuple[str, str]:
    """('YSA Stake 3', '35th Ward' or 'Wards 33–36') for a group of real wards."""
    keys, _ = real_wards()
    stake = keys[group[0]][0]
    married = stake.upper().startswith("M")
    stake_name = f"{'Married Student' if married else 'YSA'} Stake {_num(stake)}"
    nums = [_num(keys[i][1]) for i in group]
    ward = f"{ordinal(nums[0])} Ward" if len(nums) == 1 else f"Wards {', '.join(str(n) for n in nums)}" if len(nums) <= 3 \
        else f"Wards {nums[0]}–{nums[-1]}"
    return stake_name, ward


def complex_names(cx_lon: np.ndarray, cx_lat: np.ndarray, names: list[str]) -> dict[int, str]:
    """Listing names for complexes the map data only knows by address ('Apartments at …', 'Provo apartment complex
    #…'): the nearest listed building within 60 m, in title case without unit ranges."""
    rows = listing()["rows"]
    if not rows:
        return {}
    elon = np.array([r["lon"] for r in rows])
    elat = np.array([r["lat"] for r in rows])
    kx, ky = 111320 * np.cos(np.radians(40.25)), 110540
    out = {}
    for i, n in enumerate(names):
        if not re.match(r"^(Apartments at |Provo apartment complex|Orem apartment complex)", n or ""):
            continue
        d = np.hypot((elon - cx_lon[i]) * kx, (elat - cx_lat[i]) * ky)
        j = int(d.argmin())
        if d[j] < 60 and rows[j]["geocode"] == "grid":
            nm = re.sub(r"\s*[\(:].*$", "", rows[j]["name"])                  # drop "(101-112)" and ": APTS …"
            nm = re.sub(r"\s+\d+\s*-\s*\d+.*$", "", nm).strip(" -,")          # drop trailing unit ranges
            if nm and not re.fullmatch(r"(HOUSE|VARIOUS HOUSE APARTMENTS)", nm.upper()):
                out[i] = nm.title().replace("'S", "'s")
    return out
