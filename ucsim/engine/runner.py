"""Runs, paired universes, Monte Carlo and parameter sweeps, with Parquet storage.

Storage layout (runs/<run_id>/):
  config.json          scale, seed, interventions, parameter overrides, notes
  timeseries.parquet   daily group means of time-series variables
  terms.parquet        daily group means of every mechanism term (population attribution)
  event_counts.parquet daily event counts by type
  events.parquet       the full salient-event log with causal parents
  persons.parquet      final person state (all registered columns)
  edges.parquet        final relationship edges
  snapshots/           monthly person snapshots (time-varying columns)
"""
from __future__ import annotations

import copy
import json
import multiprocessing as mp
import time
import uuid
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import polars as pl

from ..population.build import build_world
from .sim import Simulation

RUNS = Path(__file__).resolve().parents[2] / "runs"


def new_simulation(scale: float = 0.3, seed: int = 1, interventions: list | None = None,
                   overrides: dict | None = None, name: str = "baseline") -> Simulation:
    world = build_world(scale=scale, seed=seed, overrides=overrides)
    return Simulation(world, interventions=interventions, name=name)


def fork(sim: Simulation, interventions: list, name: str = "intervention", start_now: bool = True) -> Simulation:
    """Branch a universe: an exact copy of `sim` now, plus interventions starting today.

    Both universes share the seed, so their random streams stay synchronized (common random
    numbers) and any divergence is caused by the intervention — directly or by the butterfly
    effects it triggers."""
    sim.w.meta.pop("synthesizer", None)
    twin = copy.deepcopy(sim)
    twin.name = name
    specs = []
    from .interventions import expand
    for s in interventions:
        for atom in expand(s):
            if start_now:
                atom["start_day"] = max(int(atom.get("start_day", 0)), sim.w.day)
            specs.append(atom)
    twin.interventions = specs
    env = twin.systems["environment"]
    from .interventions import InterventionManager
    env.manager = InterventionManager(twin, specs)
    twin.meta_fork_day = sim.w.day
    return twin


def divergence(a: Simulation, b: Simulation) -> dict:
    """How different are two universes right now?"""
    Pa, Pb = a.w.P, b.w.P
    n = min(Pa.n, Pb.n)
    out = {"day": a.w.day}
    for col in ("rel_status", "activity", "unit_id", "partner_id", "employed", "mission_status", "present"):
        out[f"diff_{col}"] = float(np.mean(Pa[col][:n] != Pb[col][:n]))
    for col in ("mood", "loneliness", "faith_belief", "stress"):
        out[f"mad_{col}"] = float(np.mean(np.abs(Pa[col][:n].astype(float) - Pb[col][:n].astype(float))))
    ka = a.w.E.key_array[a.w.E["stage"] >= 3]
    kb = b.w.E.key_array[b.w.E["stage"] >= 3]
    inter = np.intersect1d(ka, kb, assume_unique=True).size
    union = len(ka) + len(kb) - inter
    out["friendship_jaccard_distance"] = float(1 - inter / union) if union else 0.0
    out["any_state_diff"] = float(np.mean((Pa["rel_status"][:n] != Pb["rel_status"][:n]) | (Pa["unit_id"][:n] != Pb["unit_id"][:n])
                                          | (Pa["activity"][:n] != Pb["activity"][:n]) | (np.abs(Pa["mood"][:n] - Pb["mood"][:n]) > 0.05)))
    return out


class PairedRun:
    """Baseline and intervention universes stepped in lockstep."""

    def __init__(self, base: Simulation, interventions: list):
        self.base = base
        self.alt = fork(base, interventions)
        self.divergence: list[dict] = []
        self.fork_day = base.w.day

    def step(self, days: int = 1, progress=None):
        for i in range(days):
            self.base.step_day()
            self.alt.step_day()
            if self.base.w.day % 3 == 0 or days < 10:
                self.divergence.append(divergence(self.base, self.alt))
            if progress:
                progress(i + 1, days)


def save_run(sim: Simulation, run_id: str | None = None, notes: str = "", snapshots: bool = True) -> Path:
    run_id = run_id or f"{time.strftime('%Y%m%d-%H%M%S')}-{sim.name}-{uuid.uuid4().hex[:6]}"
    d = RUNS / run_id
    d.mkdir(parents=True, exist_ok=True)
    w = sim.w
    cfg = {"run_id": run_id, "name": sim.name, "scale": w.scale, "seed": w.seed, "start_date": str(w.start_date),
           "days": w.day, "interventions": sim.interventions, "param_overrides": w.params.changed(), "notes": notes}
    (d / "config.json").write_text(json.dumps(cfg, indent=1, default=str))
    rec = sim.systems["recorder"]
    rec.frame().write_parquet(d / "timeseries.parquet")
    rec.terms_frame().write_parquet(d / "terms.parquet")
    rec.events_frame().write_parquet(d / "event_counts.parquet")
    events_frame(sim).write_parquet(d / "events.parquet")
    persons_frame(sim).write_parquet(d / "persons.parquet")
    edges_frame(sim).write_parquet(d / "edges.parquet")
    return d


def persons_frame(sim: Simulation, columns: list[str] | None = None) -> pl.DataFrame:
    P = sim.w.P
    cols = columns or [k for k, s in P.specs.items() if s.dtype != "str"]
    data = {"id": np.arange(P.n)}
    for c in cols:
        spec = P.specs[c]
        x = P[c]
        data[c] = P.labels(c) if spec.dtype == "cat" else x
    return pl.DataFrame(data)


def edges_frame(sim: Simulation) -> pl.DataFrame:
    E = sim.w.E
    lo, hi = E.endpoints()
    data = {"a": lo, "b": hi}
    for c in E.cols:
        data[c] = E[c]
    return pl.DataFrame(data)


def events_frame(sim: Simulation) -> pl.DataFrame:
    log = sim.log
    names = np.array(sim.reg.event_names)
    mech = np.array(log.mech_names + [""])
    return pl.DataFrame({
        "event_id": np.arange(log.n), "day": log["day"], "block": log["block"], "type": names[log["type"]],
        "a": log["a"], "b": log["b"], "place": log["place"], "value": log["value"], "cause": log["cause"],
        "mechanism": mech[log["mech"]],
    })


# ----------------------------------------------------------------------------- Monte Carlo & sweeps
SUMMARY_VARS = ["mood", "loneliness", "stress", "faith_belief", "attend_rate", "dates_30d", "n_friends", "n_close_friends",
                "financial_stress", "romantic_longing", "gpa", "savings", "life_satisfaction", "belonging"]


def _one_run(args) -> dict:
    scale, seed, interventions, overrides, days, label = args
    sim = new_simulation(scale=scale, seed=seed, interventions=interventions, overrides=overrides, name=label)
    sim.run_days(days)
    ts = sim.systems["recorder"].frame()
    ev = sim.systems["recorder"].events_frame()
    P = sim.w.P
    pres = P["present"]
    final = {v: float(np.nanmean(P[v][pres].astype(float))) for v in SUMMARY_VARS}
    final["married_share"] = float(P.is_("rel_status", "married")[pres].mean())
    final["dating_share"] = float(P.isin("rel_status", ["dating", "engaged"])[pres].mean())
    final["active_share"] = float(P.is_("activity", "active")[pres & P["lds_member"]].mean())
    final["coffee_share"] = float((P["coffee"][pres] > 0).mean())
    final["weddings"] = int(ev.filter(pl.col("event") == "wedding")["count"].sum() // 2) if ev.height else 0
    final["breakups"] = int(ev.filter(pl.col("event") == "breakup_received")["count"].sum()) if ev.height else 0
    final["disaffiliations"] = int(ev.filter(pl.col("event") == "disaffiliated")["count"].sum()) if ev.height else 0
    final["new_friendships"] = int(ev.filter(pl.col("event") == "new_friend")["count"].sum() // 2) if ev.height else 0
    small = ts.filter(pl.col("group") == "all").select(["day"] + [c for c in ts.columns if c in SUMMARY_VARS])
    return {"label": label, "seed": seed, "final": final, "series": small.to_dict(as_series=False)}


def monte_carlo(scenarios: dict[str, list], seeds: list[int], days: int, scale: float = 0.15,
                overrides: dict | None = None, workers: int = 4) -> dict:
    """Run each scenario for each seed. Same seed across scenarios = paired comparison."""
    jobs = [(scale, s, specs, overrides, days, name) for name, specs in scenarios.items() for s in seeds]
    with ProcessPoolExecutor(max_workers=workers, mp_context=mp.get_context("spawn")) as ex:
        results = list(ex.map(_one_run, jobs))
    return summarize_mc(results)


def summarize_mc(results: list[dict]) -> dict:
    out = {"runs": len(results), "scenarios": {}}
    labels = sorted({r["label"] for r in results})
    for lab in labels:
        rs = [r for r in results if r["label"] == lab]
        finals = {k: np.array([r["final"][k] for r in rs], dtype=float) for k in rs[0]["final"]}
        stats = {k: {"mean": float(v.mean()), "median": float(np.median(v)), "p10": float(np.percentile(v, 10)),
                     "p90": float(np.percentile(v, 90)), "sd": float(v.std()), "values": v.tolist()} for k, v in finals.items()}
        series = {}
        days = rs[0]["series"]["day"]
        for var in SUMMARY_VARS:
            if var in rs[0]["series"]:
                M = np.array([r["series"][var] for r in rs], dtype=float)
                series[var] = {"day": days, "p10": np.nanpercentile(M, 10, axis=0).tolist(),
                               "median": np.nanmedian(M, axis=0).tolist(), "p90": np.nanpercentile(M, 90, axis=0).tolist()}
        out["scenarios"][lab] = {"final": stats, "series": series, "seeds": [r["seed"] for r in rs]}
    # paired differences vs baseline (same seeds)
    if "baseline" in out["scenarios"]:
        base = {r["seed"]: r for r in results if r["label"] == "baseline"}
        for lab in labels:
            if lab == "baseline":
                continue
            diffs = {}
            for k in results[0]["final"]:
                d = np.array([r["final"][k] - base[r["seed"]]["final"][k] for r in results if r["label"] == lab and r["seed"] in base])
                if len(d):
                    diffs[k] = {"mean": float(d.mean()), "p10": float(np.percentile(d, 10)), "p90": float(np.percentile(d, 90)),
                                "prob_positive": float((d > 0).mean())}
            out["scenarios"][lab]["paired_diff"] = diffs
    return out


def sweep(param: str, values: list[float], seeds: list[int], days: int, scale: float = 0.15, workers: int = 4) -> dict:
    """Response curves: final outcomes as a function of one mechanism parameter or world variable."""
    jobs = []
    for v in values:
        if param.startswith("world:"):
            spec = [{"target_type": "world", "target": param[6:], "op": "set", "value": v}]
            jobs += [(scale, s, spec, None, days, f"{v}") for s in seeds]
        else:
            jobs += [(scale, s, [], {param: v}, days, f"{v}") for s in seeds]
    with ProcessPoolExecutor(max_workers=workers, mp_context=mp.get_context("spawn")) as ex:
        results = list(ex.map(_one_run, jobs))
    curves = {}
    for k in results[0]["final"]:
        rows = []
        for v in values:
            arr = np.array([r["final"][k] for r in results if r["label"] == f"{v}"], dtype=float)
            rows.append({"value": v, "mean": float(arr.mean()), "p10": float(np.percentile(arr, 10)), "p90": float(np.percentile(arr, 90))})
        curves[k] = rows
    return {"param": param, "values": values, "curves": curves}
