"""Scales: what every number means. Each field's range, units and anchors in words (ucsim/scales.py) together with the
live distribution among the people present (or a cohort), and where any one value sits among them. Read-only."""
from __future__ import annotations

import json

import numpy as np
from fastapi import APIRouter, HTTPException

router = APIRouter()

MIN_STAGE = 1       # tie fields are compared among people who know each other (acquaintances or closer)
# registry tie fields → EdgeStore columns (directed pairs: both directions count, one value per person and tie)
EDGE_COLS = {"attraction_lh": ("att_lh", "att_hl"), "attraction_hl": ("att_lh", "att_hl"),
             "belief_lh": ("bel_lh", "bel_hl"), "belief_hl": ("bel_lh", "bel_hl"), "n_interactions": "n_inter"}


def _server():
    """(WS, jresp) of the running server (see routes_trace._server: under `python -m`, the serving module is __main__)."""
    import sys
    main = sys.modules.get("__main__")
    if getattr(main, "WS", None) is not None and getattr(main, "_include_routers", None) is not None:
        return main.WS, main.jresp
    from .server import WS, jresp
    return WS, jresp


def _cohort(sim, filter: str | None, people: str | None) -> tuple[np.ndarray, str]:
    """Mask of the people present who match the cohort filter (query DSL JSON, or the workbench's list of conditions)
    and, if given, the listed ids; with the cohort in words."""
    from ..analysis.query import describe_filter
    from ..analysis.query import evaluate_filter
    filt = None
    if filter:
        try:
            filt = json.loads(filter)
        except json.JSONDecodeError as e:
            raise HTTPException(400, f"filter is not valid JSON: {e}") from e
        if isinstance(filt, list):
            filt = {"and": filt} if len(filt) > 1 else (filt[0] if filt else None)
    try:
        mask = evaluate_filter(sim.w, filt, sim)
    except (KeyError, ValueError, TypeError) as e:
        raise HTTPException(400, f"filter not understood: {e}") from e
    if people:
        try:
            ids = np.array([int(x) for x in people.split(",") if x.strip()], np.int64)
        except ValueError as e:
            raise HTTPException(400, "people must be a comma-separated list of ids") from e
        keep = np.zeros(sim.w.P.n, bool)
        keep[ids[(ids >= 0) & (ids < sim.w.P.n)]] = True
        mask = mask & keep
    words = describe_filter(filt) if filt else "everyone present"
    return mask, (f"{len(ids)} selected people" + ("" if not filt else f", {words}")) if people else words


def _values(sim, spec, mask: np.ndarray) -> np.ndarray | None:
    """The field's values among the cohort: one per person, or one per tie (both directions for directed tie fields)
    between two cohort members who know each other."""
    if spec.entity == "person":
        if spec.id not in sim.w.P.specs:
            return None
        return np.asarray(sim.w.P[spec.id][mask], dtype=np.float64)
    if spec.entity == "edge":
        E = sim.w.E
        lo, hi = E.endpoints()
        m = mask[lo] & mask[hi] & (E["stage"] >= MIN_STAGE)
        col = EDGE_COLS.get(spec.id, spec.id)
        if isinstance(col, tuple):
            return np.r_[E[col[0]][m], E[col[1]][m]].astype(np.float64)
        if col not in E.cols:
            return None             # computed on demand (familiarity), not stored
        return np.asarray(E[col][m], dtype=np.float64)
    return None


def _spec(reg, var: str):
    spec = reg.variables.get(var) or reg.variables.get(f"edge.{var}")
    if spec is None:
        raise HTTPException(404, f"no field {var!r}")
    return spec


@router.get("/api/scales")
def scales(u: str = "base", vars: str = "", filter: str | None = None, people: str | None = None, dist: bool = True):
    """Each field's scale (range, units, anchors in words, how it is measured) and, with `dist`, the live distribution
    among the people present or a cohort: n, mean, p10/p25/median/p75/p90, every percentile and a 20-bin histogram.
    `vars` is a comma-separated list (person fields, or tie fields as edge.<name>); empty means every numeric person
    field. `filter` is a cohort filter (query DSL JSON); `people` a comma-separated list of ids."""
    from ..scales import distribution, scale_for
    WS, jresp = _server()
    sim = WS.sim(u)
    reg = sim.reg
    ids = [x.strip() for x in vars.split(",") if x.strip()]
    if not ids:
        ids = [k for k, v in reg.variables.items() if v.entity == "person" and scale_for(v)]
    specs = [_spec(reg, x) for x in ids]
    out: dict = {}
    with WS.lock:
        mask, cohort = _cohort(sim, filter, people) if dist else (None, "")
        for key, spec in zip(ids, specs):
            sc = scale_for(spec)
            if sc is None:
                out[key] = {"label": spec.label, "scale": None, "dist": None}
                continue
            row = {"label": spec.label, "domain": spec.domain, "evidence": spec.evidence, "scale": sc}
            if dist:
                x = _values(sim, spec, mask)
                row["dist"] = distribution(x, sc) if x is not None else None
                row["among"] = "ties between people who know each other" if spec.entity == "edge" else "people"
            out[key] = row
        n = int(mask.sum()) if mask is not None else None
        day = int(sim.w.day)
    return jresp({"u": u, "day": day, "n": n, "cohort": cohort, "fields": out})


@router.get("/api/scales/value")
def scale_value(var: str, u: str = "base", value: float | None = None, person: int | None = None,
                filter: str | None = None, people: str | None = None):
    """Where one value (or one person's current value, with `person`) sits among the people present or a cohort: the
    share below, equal and above, the mid-rank percentile and the anchor words nearest to it."""
    from ..scales import anchor_words, percentile_of, scale_for
    WS, jresp = _server()
    sim = WS.sim(u)
    spec = _spec(sim.reg, var)
    sc = scale_for(spec)
    with WS.lock:
        if person is not None:
            if spec.entity != "person":
                raise HTTPException(400, "person= works for person fields; pass value= for tie fields")
            if not 0 <= person < sim.w.P.n:
                raise HTTPException(404, "no such person")
            value = float(sim.w.P[spec.id][person])
        if value is None:
            raise HTTPException(400, "pass value= or person=")
        x = _values(sim, spec, _cohort(sim, filter, people)[0])
        res = percentile_of(x, value) if x is not None else None
    return jresp({"var": var, "value": value, "words": anchor_words(sc, value) if sc else "", "scale": sc, **(res or {"n": 0})})
