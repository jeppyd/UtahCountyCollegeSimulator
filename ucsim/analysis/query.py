"""Cohort filter DSL, evaluated against the live columnar state.

A filter is JSON:
  {"and": [f, ...]} | {"or": [f, ...]} | {"not": f}
  {"var": "age", "op": "between", "value": [18, 23]}
  {"var": "sex", "op": "eq", "value": "F"}                        # categorical by label
  {"var": "activity", "op": "in", "value": ["active", "less_active"]}
  {"recent_event": "breakup_received", "days": 90}                 # had event in last N days
  {"household": {"var": "activity", "op": "eq", "value": "active"}, "share": ">=", "value": 0.5}
                                                                   # share of co-residents matching
  {"var": "faith_belief", "op": "quantile_ge", "value": 0.8}       # top 20%
Ops: eq, ne, lt, le, gt, ge, between, in, notin, isnull, notnull, quantile_ge, quantile_le.
"""
from __future__ import annotations

import numpy as np

OPS = ("eq", "ne", "lt", "le", "gt", "ge", "between", "in", "notin", "isnull", "notnull", "quantile_ge", "quantile_le")


def _codes(P, var, vals):
    spec = P.specs[var]
    if spec.dtype == "cat":
        out = []
        for v in (vals if isinstance(vals, (list, tuple)) else [vals]):
            out.append(spec.categories.index(v) if isinstance(v, str) else int(v))
        return out
    return vals


def _cond(world, c: dict, sim=None) -> np.ndarray:
    P = world.P
    n = P.n
    if "and" in c:
        m = np.ones(n, bool)
        for f in c["and"]:
            m &= _cond(world, f, sim)
        return m
    if "or" in c:
        m = np.zeros(n, bool)
        for f in c["or"]:
            m |= _cond(world, f, sim)
        return m
    if "not" in c:
        return ~_cond(world, c["not"], sim)
    if "recent_event" in c:
        if sim is None:
            return np.zeros(n, bool)
        log = sim.log
        code = sim.reg.event_ids[c["recent_event"]]
        days = int(c.get("days", 90))
        m = (log["type"] == code) & (log["day"] >= world.day - days)
        out = np.zeros(n, bool)
        out[log["a"][m]] = True
        return out
    if "household" in c:
        inner = _cond(world, c["household"], sim)
        unit = P["unit_id"]
        has = unit >= 0
        tot = np.bincount(unit[has], minlength=int(unit.max()) + 2 if has.any() else 1).astype(float)
        hit = np.bincount(unit[has & inner], minlength=len(tot)).astype(float)
        # exclude self
        u = np.maximum(unit, 0)
        others = tot[u] - 1
        others_hit = hit[u] - inner
        share = np.where(has & (others > 0), others_hit / np.maximum(others, 1), np.nan)
        thr = float(c.get("value", 0.5))
        op = c.get("share", ">=")
        return np.nan_to_num({">=": share >= thr, ">": share > thr, "<=": share <= thr, "<": share < thr}[op], nan=False).astype(bool)
    var, op = c["var"], c.get("op", "eq")
    x = P[var]
    val = c.get("value")
    if op in ("eq", "ne", "in", "notin"):
        codes = _codes(P, var, val)
        if op in ("eq", "ne"):
            code = codes[0] if isinstance(codes, list) else codes
            m = x == code
            return m if op == "eq" else ~m
        m = np.isin(x, codes)
        return m if op == "in" else ~m
    xf = x.astype(np.float64)
    if op == "isnull":
        return ~np.isfinite(xf)
    if op == "notnull":
        return np.isfinite(xf)
    if op == "between":
        lo, hi = val
        return (xf >= float(lo)) & (xf <= float(hi))
    if op in ("quantile_ge", "quantile_le"):
        pres = P["present"] & np.isfinite(xf)
        q = np.quantile(xf[pres], float(val)) if pres.any() else 0
        return (xf >= q) if op == "quantile_ge" else (xf <= q)
    v = float(val)
    return {"lt": xf < v, "le": xf <= v, "gt": xf > v, "ge": xf >= v}[op]


def evaluate_filter(world, filt: dict | None, sim=None, include_absent: bool = False) -> np.ndarray:
    P = world.P
    base = np.ones(P.n, bool) if include_absent else P["present"].copy()
    if not filt:
        return base
    return base & _cond(world, filt, sim)


def describe_filter(filt: dict | None) -> str:
    if not filt:
        return "everyone present"
    if "and" in filt:
        return " AND ".join(describe_filter(f) for f in filt["and"])
    if "or" in filt:
        return "(" + " OR ".join(describe_filter(f) for f in filt["or"]) + ")"
    if "not" in filt:
        return "NOT " + describe_filter(filt["not"])
    if "recent_event" in filt:
        return f"{filt['recent_event']} in last {filt.get('days', 90)} days"
    if "household" in filt:
        return f"co-residents {filt.get('share', '>=')} {filt.get('value')} with ({describe_filter(filt['household'])})"
    return f"{filt['var']} {filt.get('op', 'eq')} {filt.get('value')}"
