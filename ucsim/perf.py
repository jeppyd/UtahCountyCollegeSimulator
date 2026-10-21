"""Speed budget: how long a simulated day takes, overall and per system, normalized for the machine.

`measure()` builds a small world, runs a warm-up, then times a few days and each system's share (`sim.timing`). Times
are divided by a fixed NumPy calibration workload run on the same machine, so a budget recorded on one computer can
be checked on another. `config/perf_budget.json` holds the reference; `tests/test_speed_budget.py` fails when a day
gets much slower than it, or when one system (a new layer, say) takes far more than its share.

    python scripts/perf.py            # print today's timings against the budget
    python scripts/perf.py --update   # record them as the new budget (say why in docs/HANDOFF.md)
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np

BUDGET = Path(__file__).resolve().parent / "config" / "perf_budget.json"
SETUP = {"scale": 0.1, "seed": 3, "warmup": 2, "days": 5}
TOLERANCE = 1.5          # a day may take up to 1.5× the budget
SYSTEM_TOLERANCE = 2.5   # one system up to 2.5× its own budget…
SYSTEM_FLOOR = 0.10      # …or 10% of the day's budget, whichever is larger (small systems are noisy)


def calibrate(reps: int = 5) -> float:
    """Seconds for a fixed mix of the NumPy work the engine does (sorting, indexing, elementwise math); best of reps."""
    rng = np.random.default_rng(0)
    x = rng.random(400_000)
    idx = rng.integers(0, len(x), 400_000)
    best = np.inf
    for _ in range(reps):
        t = time.perf_counter()
        for _ in range(4):
            np.sort(x)
            y = np.exp(-x[idx]) * 1.7 + np.sqrt(x)
            np.add.at(np.zeros(1000), idx % 1000, y)
            np.searchsorted(np.sort(x[:100_000]), x)
            np.unique(idx)
        best = min(best, time.perf_counter() - t)
    return float(best)


def measure(setup: dict | None = None) -> dict:
    """Seconds per simulated day (total and per system), raw and normalized by `calibrate()`."""
    from .engine.runner import new_simulation
    s = {**SETUP, **(setup or {})}
    cal = calibrate()
    sim = new_simulation(scale=s["scale"], seed=s["seed"])
    sim.run_days(s["warmup"])
    sim.timing.clear()
    t = time.perf_counter()
    sim.run_days(s["days"])
    total = (time.perf_counter() - t) / s["days"]
    systems = {k: v / s["days"] for k, v in sim.timing.items()}
    cal_after = calibrate()
    cal = min(cal, cal_after)
    return {"setup": s, "calibration_s": cal, "people": int(sim.w.P.n), "s_per_day": total, "systems_s_per_day": systems,
            "norm_per_day": total / cal, "norm_systems": {k: v / cal for k, v in systems.items()}}


def load_budget() -> dict | None:
    return json.loads(BUDGET.read_text(encoding="utf-8")) if BUDGET.exists() else None


def check(m: dict, budget: dict) -> list[str]:
    """Plain-language problems (empty when within budget)."""
    out = []
    ref = budget["norm_per_day"]
    if m["norm_per_day"] > TOLERANCE * ref:
        out.append(f"a simulated day takes {m['norm_per_day'] / ref:.2f}× the budget (limit {TOLERANCE}×)")
    for k, v in m["norm_systems"].items():
        lim = max(SYSTEM_TOLERANCE * budget["norm_systems"].get(k, 0.0), SYSTEM_FLOOR * ref)
        if v > lim:
            out.append(f"system '{k}' takes {v / ref:.0%} of the day's budget (limit {lim / ref:.0%})")
    return out


def save_budget(m: dict, note: str = ""):
    m = {**m, "recorded": time.strftime("%Y-%m-%d"), "note": note}
    BUDGET.write_text(json.dumps(m, indent=1, sort_keys=True), encoding="utf-8")
