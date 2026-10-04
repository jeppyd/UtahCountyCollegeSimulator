"""Two kinds of uncertainty about a What-if result.

* **Stochastic** — "would this still happen under a different random social history?" Same assumptions,
  different seeds (different people, meetings, chance).
* **Model / parameter** — "would this still happen if uncertain behavioral assumptions were different?"
  Same seed, different draws of the mechanism parameters (and alternative mechanism forms).

An ensemble crosses the two: for each parameter draw d and seed s it builds a world, warms it up, forks a
What-if with the scenario (common random numbers within the pair), runs both, and records the paired effect
on each outcome. The effects are then decomposed:

    total variance = between-draw (parametric) + within-draw (stochastic)

using the standard two-way estimator (the between-draw variance of draw means, corrected for the
stochastic noise those means still carry). Sensitivity reports which sampled parameters move the effect
most (Spearman rank correlation of each parameter with the draw-mean effect), with their evidence labels,
so a result that rests on a hypothetical mechanism says so.

Parameter draws: each parameter with a declared range varies within a band around its point value whose
width depends on its evidence level (registry.EVIDENCE_SPREAD — observed parameters do not move,
hypothetical and structural ones use the full range). Triangular draws peak at the point value; `dist:
choice` parameters (alternative mechanism forms) pick an option. Latin hypercube stratification keeps small
ensembles spread out.
"""
from __future__ import annotations

import multiprocessing as mp
from concurrent.futures import ProcessPoolExecutor

import numpy as np

from ..registry import EVIDENCE_SPREAD, Registry, get_registry

OUTCOMES = ["loneliness", "mood", "stress", "financial_stress", "faith_belief", "attend_rate", "n_friends", "n_close_friends",
            "dates_30d", "social_events_month", "perceived_support", "life_satisfaction"]
SHARES = {"married": ("rel_status", "married"), "dating": ("rel_status", "dating"), "active_lds": ("activity", "active")}
MIN_DRAWS_FOR_DRIVERS = 12


def uncertain_params(reg: Registry, levels: tuple = ("hypothetical", "structural", "speculative", "extrapolated", "calibrated"),
                     systems: tuple | None = None) -> list[dict]:
    """Parameters eligible for ensemble draws: (key, value, lo, hi, dist, options, evidence)."""
    out = []
    for mid, m in reg.mechanisms.items():
        if systems and m.system not in systems:
            continue
        spread = EVIDENCE_SPREAD.get(m.evidence, 1.0)
        for pname, spec in m.params.items():
            rng_ = spec.get("range")
            # alternative mechanism forms are always part of model uncertainty, whatever the mechanism's evidence
            if spec.get("structural") and spec.get("dist") == "choice":
                out.append({"key": f"{mid}.{pname}", "value": float(spec["value"]), "lo": float(rng_[0]), "hi": float(rng_[1]),
                            "dist": "choice", "options": list(spec.get("options", rng_)), "evidence": "structural"})
                continue
            if m.evidence not in levels or not rng_ or spread <= 0:
                continue
            v = float(spec["value"])
            lo, hi = float(rng_[0]), float(rng_[1])
            if spec.get("dist") == "choice":
                out.append({"key": f"{mid}.{pname}", "value": v, "lo": lo, "hi": hi, "dist": "choice",
                            "options": list(spec.get("options", [lo, hi])), "evidence": m.evidence})
                continue
            lo2, hi2 = v - spread * (v - lo), v + spread * (hi - v)
            if hi2 - lo2 <= 1e-12:
                continue
            out.append({"key": f"{mid}.{pname}", "value": v, "lo": lo2, "hi": hi2, "dist": spec.get("dist", "triangular"),
                        "evidence": m.evidence})
    return out


def sample(params: list[dict], n: int, seed: int = 0) -> list[dict[str, float]]:
    """Latin-hypercube draws of the parameters (dict per draw). Draw 0 is always the point values."""
    rng = np.random.default_rng(seed)
    k = len(params)
    U = (np.argsort(rng.random((n, k)), axis=0) + rng.random((n, k))) / n   # stratified uniforms per column
    draws = []
    for i in range(n):
        d = {}
        for j, p in enumerate(params):
            u = U[i, j]
            if i == 0:
                d[p["key"]] = p["value"]
            elif p["dist"] == "choice":
                opts = p["options"]
                d[p["key"]] = float(opts[min(int(u * len(opts)), len(opts) - 1)])
            elif p["dist"] == "uniform":
                d[p["key"]] = p["lo"] + u * (p["hi"] - p["lo"])
            else:   # triangular with mode at the point value
                a, b, c = p["lo"], p["hi"], min(max(p["value"], p["lo"]), p["hi"])
                fc = (c - a) / (b - a)
                d[p["key"]] = a + np.sqrt(u * (b - a) * (c - a)) if u < fc else b - np.sqrt((1 - u) * (b - a) * (b - c))
            d[p["key"]] = float(d[p["key"]])
        draws.append(d)
    return draws


def _outcomes(sim) -> dict[str, float]:
    P = sim.w.P
    pres = P["present"].astype(bool)
    out = {v: float(np.nanmean(P[v][pres].astype(float))) for v in OUTCOMES if v in P}
    for k, (var, lab) in SHARES.items():
        m = pres & (P["lds_member"].astype(bool) if k == "active_lds" else True)
        out[f"{k}_share"] = float(P.is_(var, lab)[m].mean()) if m.any() else float("nan")
    return out


def _pair(job) -> dict:
    """One (draw, seed) pair: baseline and What-if from the same warmed-up world."""
    scale, seed, overrides, scenario, warmup, days, d_idx = job
    from .runner import fork, new_simulation
    base = new_simulation(scale=scale, seed=seed, overrides=overrides)
    base.run_days(warmup)
    alt = fork(base, scenario)
    for _ in range(days):
        base.step_day()
        alt.step_day()
    ob, oa = _outcomes(base), _outcomes(alt)
    return {"draw": d_idx, "seed": seed, "base": ob, "alt": oa, "effect": {k: oa[k] - ob[k] for k in ob}}


def decompose(effects: np.ndarray) -> dict:
    """effects: draws × seeds. Two-way variance decomposition of the paired effect."""
    D, S = effects.shape
    draw_means = np.nanmean(effects, axis=1)
    within = float(np.nanmean(np.nanvar(effects, axis=1, ddof=1))) if S > 1 else float("nan")
    between_raw = float(np.nanvar(draw_means, ddof=1)) if D > 1 else 0.0
    between = max(between_raw - (within / S if np.isfinite(within) else 0.0), 0.0)
    total = between + (within if np.isfinite(within) else 0.0)
    allv = effects[np.isfinite(effects)]
    mean = float(allv.mean()) if len(allv) else float("nan")
    return {"mean": mean, "p10": float(np.percentile(allv, 10)) if len(allv) else None,
            "p90": float(np.percentile(allv, 90)) if len(allv) else None,
            "sd_total": float(np.sqrt(total)), "share_parametric": between / total if total > 0 else 0.0,
            "share_stochastic": (within if np.isfinite(within) else 0.0) / total if total > 0 else 0.0,
            "same_sign": float(np.mean(np.sign(allv) == np.sign(mean))) if len(allv) and mean != 0 else None,
            "point_estimate": float(np.nanmean(effects[0])) if D else None}


def _spearman(x: np.ndarray, y: np.ndarray) -> float:
    if len(x) < 3 or np.std(x) == 0 or np.std(y) == 0:
        return 0.0
    rx, ry = np.argsort(np.argsort(x)), np.argsort(np.argsort(y))
    return float(np.corrcoef(rx, ry)[0, 1])


def ensemble(scenario: list, n_draws: int = 6, seeds: tuple = (1, 2, 3), days: int = 90, warmup: int = 21, scale: float = 0.05,
             levels: tuple = ("hypothetical", "structural", "speculative", "extrapolated"), workers: int = 4, seed: int = 0,
             progress=None) -> dict:
    reg = get_registry()
    params = uncertain_params(reg, levels)
    draws = sample(params, n_draws, seed)
    jobs = [(scale, s, d, scenario, warmup, days, i) for i, d in enumerate(draws) for s in seeds]
    results = []
    if workers <= 1:
        for j in jobs:
            results.append(_pair(j))
            if progress:
                progress(len(results), len(jobs))
    else:
        with ProcessPoolExecutor(max_workers=workers, mp_context=mp.get_context("spawn")) as ex:
            for r in ex.map(_pair, jobs):
                results.append(r)
                if progress:
                    progress(len(results), len(jobs))
    keys = list(results[0]["effect"])
    seed_idx = {s: k for k, s in enumerate(seeds)}
    out = {"scenario": scenario, "n_draws": n_draws, "seeds": list(seeds), "days": days, "warmup": warmup, "scale": scale,
           "levels": list(levels), "n_params": len(params), "outcomes": {}}
    for key in keys:
        M = np.full((n_draws, len(seeds)), np.nan)
        for r in results:
            M[r["draw"], seed_idx[r["seed"]]] = r["effect"][key]
        dec = decompose(M)
        dm = np.nanmean(M, axis=1)
        sens = []
        # attribution needs enough draws: with few draws and many parameters, rank correlations are spurious
        if n_draws >= MIN_DRAWS_FOR_DRIVERS:
            thr = max(0.5, 2.0 / np.sqrt(n_draws))
            for p in params:
                x = np.array([d[p["key"]] for d in draws])
                rho = _spearman(x, dm)
                if abs(rho) >= thr:
                    sens.append({"param": p["key"], "rho": round(rho, 3), "evidence": p["evidence"]})
            sens.sort(key=lambda t: -abs(t["rho"]))
        dec["drivers"] = sens[:6]
        dec["drivers_note"] = (None if n_draws >= MIN_DRAWS_FOR_DRIVERS else
                               f"run at least {MIN_DRAWS_FOR_DRIVERS} parameter draws to attribute the effect to parameters")
        dec["by_draw"] = [round(float(v), 5) for v in dm]
        out["outcomes"][key] = dec
    out["draws"] = [{k: round(v, 4) for k, v in d.items()} for d in draws]
    return out
