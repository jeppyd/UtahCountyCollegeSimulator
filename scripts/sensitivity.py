"""Which social parameters move the conversation layer's outcomes most (opt-in; Morris elementary effects via SALib).

    pip install SALib
    python scripts/sensitivity.py [--trajectories 6] [--seeds 2] [--scale 0.02] [--days 14]

Each run builds a small world, sets the sampled parameters (sim.p, never the shared registry) and simulates; every
point is replicated over seeds and averaged, so the effects aren't just noise. Prints mu* (mean absolute effect) and
sigma (interaction/nonlinearity) for each parameter on each outcome. It's a research aid for tuning: nothing in the
app or the tests depends on it, and SALib isn't a dependency of the simulator.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

PARAMS = {   # mechanism parameter -> range explored (inside each one's declared range)
    "social.decline.base": (-2.0, 1.0),
    "social.read.base": (-3.0, -1.0),
    "social.respond.clarify": (-2.5, 0.5),
    "social.support.base": (-1.5, 0.5),
    "social.promise.base": (-3.0, -0.5),
    "social.app.ask_base": (-3.0, -1.0),
}
OUTCOMES = ("clarified", "late_reply", "confided", "promise_broken", "app_date_set", "first_date")


def run(values: dict, seed: int, scale: float, days: int) -> dict:
    from ucsim.engine.runner import new_simulation
    sim = new_simulation(scale=scale, seed=seed)
    for k, v in values.items():
        sim.p.set(k, float(v))
    sim.run_days(days)
    n = sim.log.n
    t = sim.log["type"][:n]
    out = {e: float((t == sim.reg.event_ids[e]).sum()) / max(1, int(sim.w.P["present"].sum())) * 1000 for e in OUTCOMES}
    B = sim.systems["social"].beliefs.t
    from ucsim.engine.systems.social import PROP
    out["misread_beliefs"] = float((B["prop"] == PROP["not_interested"]).sum()) / max(1, int(sim.w.P["present"].sum())) * 1000
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--trajectories", type=int, default=6)
    ap.add_argument("--seeds", type=int, default=2)
    ap.add_argument("--scale", type=float, default=0.02)
    ap.add_argument("--days", type=int, default=14)
    a = ap.parse_args()
    try:
        from SALib.analyze import morris as analyze
        from SALib.sample import morris as sample
    except ImportError:
        sys.exit("This optional script needs SALib: pip install SALib")
    names = list(PARAMS)
    problem = {"num_vars": len(names), "names": names, "bounds": [list(PARAMS[k]) for k in names]}
    X = sample.sample(problem, a.trajectories, num_levels=4, seed=1)
    print(f"{len(X)} points × {a.seeds} seeds at scale {a.scale}, {a.days} days")
    Y: dict[str, list[float]] = {}
    for k, x in enumerate(X):
        reps = [run(dict(zip(names, x)), seed=11 + s, scale=a.scale, days=a.days) for s in range(a.seeds)]
        for o in reps[0]:
            Y.setdefault(o, []).append(float(np.mean([r[o] for r in reps])))
        print(f"  {k + 1}/{len(X)}", end="\r", flush=True)
    print()
    for o, y in Y.items():
        res = analyze.analyze(problem, X, np.array(y), num_levels=4, print_to_console=False)
        order = np.argsort(-np.asarray(res["mu_star"]))
        print(f"\n{o} (per 1,000 people)")
        for i in order:
            print(f"  {names[i]:28s} mu* {res['mu_star'][i]:8.3f}   sigma {res['sigma'][i]:8.3f}")


if __name__ == "__main__":
    main()
