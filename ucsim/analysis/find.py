"""Find people by who they are and how they stand with someone, instead of guessing names.

`find(sim, around=i, relation="friends", filter=..., q="", sort="closeness")` narrows everyone in Provo–Orem with the
same filter conditions the rest of the app uses (analysis/query.py), then by how they relate to one person — knows,
hasn't met, friends, roommates, classmates, exes, someone they're into or who is into them, someone things are tense
with — and by name. Rows come sorted by closeness, distance, either side's interest, tension, name or any person
variable, with each one's tie to that person in words. Read-only: nothing is drawn or changed.
"""
from __future__ import annotations

import numpy as np

from ..engine.state import Tie
from .person import FIRST_F, FIRST_M, LAST, headline
from .query import evaluate_filter

# value -> (label, needs a person to be around)
RELATIONS: dict[str, str] = {
    "any": "anyone", "knows": "people they know", "strangers": "people they haven't met", "friends": "friends",
    "close_friends": "close friends", "roommates": "roommates", "neighbors": "neighbors (their complex)",
    "ward": "their ward", "classmates": "classmates", "coworkers": "coworkers", "family": "family",
    "exes": "exes", "partner": "their partner", "likes": "people they're into", "into_them": "people into them",
    "tense": "people things are tense with",
}
SORTS = {"closeness": "closest to them", "nearest": "lives nearest", "my_interest": "their interest in them",
         "their_interest": "interest in them", "tension": "most tension", "name": "name"}
STAGE = {0: "met once", 1: "acquaintance", 2: "friendly", 3: "friend", 4: "close friend"}
INTO = 0.3        # attraction that counts as being into someone
TENSE_HURT, TENSE_CONFLICT = 0.05, 0.2


def names(P, ids: np.ndarray) -> np.ndarray:
    """analysis.person.synthetic_name for many people at once."""
    ids = np.asarray(ids, np.int64)
    h = (ids * 2654435761) & 0xFFFFFFFF
    female = P["sex"][ids] == P.code("sex", "F")
    first = np.where(female, np.array(FIRST_F, object)[h % 24], np.array(FIRST_M, object)[h % 24])
    last = np.array(LAST, object)[(h >> 8) % len(LAST)]
    return first + " " + last


def _km(P, a: int, ids: np.ndarray) -> np.ndarray:
    dx = (P["home_lon"][ids] - P["home_lon"][a]) * 84.0       # km per degree of longitude at 40° N
    dy = (P["home_lat"][ids] - P["home_lat"][a]) * 111.0
    return np.hypot(dx, dy)


def _tie_words(P, a: int, j: int, e: int, E) -> str:
    if int(P["partner_id"][a]) == j:
        return "spouse" if P.is_("rel_status", "married")[a] else "partner"
    if e < 0:
        return "hasn't met"
    fl = int(E["flags"][e])
    bits = [STAGE.get(int(E["stage"][e]), "knows")]
    for flag, w in ((Tie.ROOMMATE, "roommate"), (Tie.FAMILY, "family"), (Tie.CLASSMATE, "classmate"),
                    (Tie.COWORKER, "coworker"), (Tie.EX, "ex"), (Tie.NEIGHBOR, "neighbor")):
        if fl & flag:
            bits.append(w)
    if P["unit_id"][a] >= 0 and P["unit_id"][a] == P["unit_id"][j] and "roommate" not in bits:
        bits.append("roommate")
    return ", ".join(bits)


def find(sim, around: int | None = None, relation: str = "any", filter=None, q: str = "", sort: str | None = None,
         desc: bool | None = None, offset: int = 0, limit: int = 25) -> dict:
    w = sim.w
    P, E = w.P, w.E
    n = P.n
    if relation not in RELATIONS:
        raise ValueError(f"'{relation}' isn't a relation (use one of: {', '.join(RELATIONS)})")
    if isinstance(filter, list):
        filter = filter[0] if len(filter) == 1 else ({"and": filter} if filter else None)
    mask = evaluate_filter(w, filter, sim)
    a = None if around in (None, "", -1) else int(around)
    if a is not None and not 0 <= a < n:
        raise KeyError(f"there is no person {a}")
    if a is None and relation != "any":
        raise ValueError("a relation needs a person to be around")
    tie = np.full(n, -1, np.int64)
    counts: dict[str, int] = {}
    if a is not None:
        lo, hi = E.endpoints()
        idx = np.flatnonzero((lo == a) | (hi == a))
        other = np.where(lo[idx] == a, hi[idx], lo[idx])
        tie[other] = idx
        mask[a] = False
        has = tie >= 0
        st, fl = np.zeros(n, np.int64), np.zeros(n, np.int64)
        att_me, att_them, tense = np.zeros(n), np.zeros(n), np.zeros(n, bool)
        st[other], fl[other] = E["stage"][idx], E["flags"][idx]
        att_me[other] = E.attraction_from(idx, np.full(len(idx), a))       # a -> them
        att_them[other] = E.attraction_from(idx, other)                     # them -> a
        tense[other] = (E["hurt"][idx] >= TENSE_HURT) | (E["conflict"][idx] >= TENSE_CONFLICT)
        everyone = np.arange(n)
        unit, cx = int(P["unit_id"][a]), int(P["complex_id"][a])
        rel = {
            "any": np.ones(n, bool), "knows": has, "strangers": ~has, "friends": has & (st >= 3),
            "close_friends": has & (st >= 4), "roommates": (P["unit_id"] == unit) & (unit >= 0),
            "neighbors": (P["complex_id"] == cx) & (cx >= 0) & (P["unit_id"] != unit),
            "ward": (P["ward_id"] == P["ward_id"][a]) & (P["ward_id"][a] >= 0),
            "classmates": (fl & Tie.CLASSMATE) > 0, "coworkers": (fl & Tie.COWORKER) > 0,
            "family": (fl & Tie.FAMILY) > 0, "exes": (fl & Tie.EX) > 0,
            "partner": everyone == int(P["partner_id"][a]),
            "likes": has & (att_me >= INTO), "into_them": has & (att_them >= INTO),
            "tense": tense,
        }
        counts = {k: int((m & mask).sum()) for k, m in rel.items()}
        mask &= rel[relation]
    ids = np.flatnonzero(mask)
    nm = names(P, ids)
    ql = (q or "").strip().lower()
    if ql:
        if ql.isdigit():
            hit = ids == int(ql)
        else:
            hit = np.array([ql in s.lower() for s in nm.tolist()], bool)
        ids, nm = ids[hit], nm[hit]
    sort = sort or ("closeness" if a is not None else "name")
    if sort in ("closeness", "nearest", "my_interest", "their_interest", "tension") and a is None:
        sort = "name"
    e = np.maximum(tie[ids], 0)
    has = tie[ids] >= 0
    if sort == "name":
        key, d0 = nm.astype(str), False
    elif sort == "closeness":
        key, d0 = np.where(has, E["closeness"][e], -1.0), True
    elif sort == "nearest":
        key, d0 = _km(P, a, ids), False
    elif sort == "my_interest":
        key, d0 = np.where(has, E.attraction_from(e, np.full(len(ids), a)), -2.0), True
    elif sort == "their_interest":
        key, d0 = np.where(has, E.attraction_from(e, ids), -2.0), True
    elif sort == "tension":
        key, d0 = np.where(has, E["hurt"][e] + 0.5 * E["conflict"][e], -1.0), True
    elif sort in P.specs and P.specs[sort].entity == "person" and P.specs[sort].dtype != "str":
        key, d0 = P[sort][ids].astype(float), True
        key = np.where(np.isfinite(key), key, -np.inf)
    else:
        raise ValueError(f"can't sort by '{sort}'")
    desc = d0 if desc is None else bool(desc)
    order = np.argsort(key, kind="stable")
    if desc:
        order = order[::-1]
    ids, nm = ids[order], nm[order]
    total = len(ids)
    offset = max(0, int(offset))
    page = ids[offset: offset + max(1, min(int(limit), 100))]
    rows = []
    for j in page.tolist():
        k = int(tie[j])
        r = {"id": j, "name": str(nm[offset + len(rows)]), "headline": headline(sim, j),
             "age": int(P["age"][j]), "sex": "F" if P["sex"][j] == P.code("sex", "F") else "M"}
        if a is not None:
            r["tie"] = _tie_words(P, a, j, k, E)
            r["km"] = round(float(_km(P, a, np.array([j]))[0]), 1)
            if k >= 0:
                kk = np.array([k])
                r.update(closeness=round(float(E["closeness"][k]), 2),
                         my_interest=round(float(E.attraction_from(kk, np.array([a]))[0]), 2),
                         their_interest=round(float(E.attraction_from(kk, np.array([j]))[0]), 2),
                         hurt=round(float(E["hurt"][k]), 2))
        if sort in P.specs:
            spec = P.specs[sort]
            v = P[sort][j]
            r["value"] = (spec.categories[int(v)].replace("_", " ") if spec.dtype == "cat" else bool(v) if spec.dtype == "bool"
                          else (round(float(v), 2) if np.isfinite(v) else None))
        rows.append(r)
    return {"total": total, "offset": offset, "rows": rows, "counts": counts, "sort": sort, "desc": desc,
            "around": a, "relation": relation, "relations": RELATIONS, "sorts": SORTS}


def workplaces(sim, near: int, k: int = 20) -> list[dict]:
    """The workplaces nearest someone's home, for a job offer."""
    P, emp = sim.w.P, sim.w.employers
    lon, lat = np.asarray(emp["lon"], float), np.asarray(emp["lat"], float)
    km = np.hypot((lon - P["home_lon"][near]) * 84.0, (lat - P["home_lat"][near]) * 111.0)
    out = []
    for e in np.argsort(km)[:k].tolist():
        nm = str(emp["name"][e]) if "name" in emp and emp["name"][e] else f"Workplace {e}"
        out.append({"id": int(e), "name": nm, "type": str(emp["type"][e]).replace("_", " "), "km": round(float(km[e]), 1)})
    return out
