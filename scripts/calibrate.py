"""Calibrate the most influential mechanism parameters to the validation targets.

A small simulated-method-of-moments loop: each candidate parameter set is simulated for 200 days on two
seeds (common random numbers across candidates), compared with the same targets as scripts/validate.py
(Census benchmarks weighted most, then emergent survey rows, then input rows; biased survey rows excluded),
and improved by coordinate search with shrinking steps. The best values are written back into the
mechanism files (ucsim/config/mechanisms/*.yaml), keeping their declared ranges.

    python scripts/calibrate.py --rounds 3 --scale 0.05 --workers 4          # search and write back
    python scripts/calibrate.py --dry-run                                      # search only
"""
from __future__ import annotations

import argparse
import json
import multiprocessing as mp
import re
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
MECH = ROOT / "ucsim" / "config" / "mechanisms"

# (parameter, low, high): searched inside (a subset of) each parameter's declared range
PARAMS = [
    ("romance.ask.base", -5.5, -3.5),
    ("romance.kiss.base", -4.0, -1.5),
    ("romance.couple_time.dating", 0.8, 2.2),
    ("romance.couple_time.engaged", 0.8, 3.0),
    ("romance.couple_time.married", 0.5, 1.4),
    ("romance.engage.base", -8.5, -5.5),
    ("romance.breakup.base", -3.8, -1.5),
    ("economy.job_find.base", -2.0, 0.0),
    ("economy.work_more.threshold", 0.4, 0.85),
    # social life: realized social events (gatherings, FHE) are an emergent row since iteration 5
    ("activity.gathering.accept_base", -1.5, 0.5),
    ("activity.gathering.host_saturday", 0.02, 0.1),
    ("activity.fhe.attend_mult", 0.5, 1.0),
    # pattern rows: support perception and friendship clustering
    ("mind.perceived_support.reality", 0.1, 0.6),
    ("relationship.introductions.rate", 0.05, 0.5),
]
WEIGHT = {"benchmark": 3.0, "emergent": 1.0, "pattern": 1.0, "input": 0.5, "diagnostic": 0.0}
CHECK_DAYS = (60, 200)


def evaluate(job):
    """Run one candidate on one seed; return {row key: (kind, z at each check day)}."""
    overrides, seed, scale = job
    from validate import benchmarks, compare, patterns  # scripts/ is on sys.path in spawned workers too (module level)

    from ucsim.engine.runner import new_simulation
    from ucsim.population.sampling import load_priors
    priors = load_priors()
    sim = new_simulation(scale=scale, seed=seed, overrides=overrides)
    out: dict = {}
    for day in CHECK_DAYS:
        sim.run_until(day)
        for r in benchmarks(sim) + compare(sim, priors) + patterns(sim):
            if np.isfinite(r["diff"]) and not r.get("holdout"):   # held-out tables are never used for fitting
                out.setdefault(f"{r['table']}|{r['group']}", [r["kind"], []])[1].append(r["diff"] / r["tol"])
    return out


def loss(results: list[dict]) -> float:
    """Weighted mean of capped squared standardized misfits, averaged over seeds and check days."""
    tot, wsum = 0.0, 0.0
    for res in results:
        for kind, zs in res.values():
            w = WEIGHT.get(kind, 0.0)
            for z in zs:
                tot += w * min(z * z, 9.0)
                wsum += w
    return tot / max(wsum, 1e-9)


def write_back(values: dict[str, float]):
    """Replace `value:` for each parameter in the mechanism YAML files, preserving formatting."""
    for key, val in values.items():
        mid, par = key.rsplit(".", 1)
        for f in sorted(MECH.glob("*.yaml")):
            text = f.read_text(encoding="utf-8")
            m = re.search(rf"^  {re.escape(mid)}:\s*$", text, re.M)
            if not m:
                continue
            nxt = re.search(r"^  \S", text[m.end():], re.M)
            end = m.end() + (nxt.start() if nxt else len(text) - m.end())
            block = text[m.start():end]
            new_block, n = re.subn(rf"(^\s+{re.escape(par)}: \{{value: )([-0-9.eE]+)", rf"\g<1>{val:.3g}", block, count=1, flags=re.M)
            if n:
                f.write_text(text[:m.start()] + new_block + text[end:], encoding="utf-8")
                break
        else:
            print(f"  ! could not write {key}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rounds", type=int, default=3)
    ap.add_argument("--scale", type=float, default=0.05)
    ap.add_argument("--seeds", default="11,12")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    from ucsim.registry import ParamSet, get_registry
    base = ParamSet(get_registry())
    seeds = [int(s) for s in a.seeds.split(",")]
    x = {k: base(k) for k, _, _ in PARAMS}
    step = {k: 0.25 * (hi - lo) for k, lo, hi in PARAMS}
    log = []
    t0 = time.time()
    with ProcessPoolExecutor(max_workers=a.workers, mp_context=mp.get_context("spawn")) as ex:
        def score(cands: list[dict]) -> list[float]:
            jobs = [(c, s, a.scale) for c in cands for s in seeds]
            res = list(ex.map(evaluate, jobs))
            return [loss(res[i * len(seeds):(i + 1) * len(seeds)]) for i in range(len(cands))]

        best = score([x])[0]
        print(f"start loss {best:.3f} ({time.time() - t0:.0f}s)", flush=True)
        log.append({"round": 0, "loss": best, "params": dict(x)})
        for rnd in range(1, a.rounds + 1):
            for k, lo, hi in PARAMS:
                cands = [dict(x, **{k: float(np.clip(x[k] + s * step[k], lo, hi))}) for s in (-1, 1)]
                cands = [c for c in cands if abs(c[k] - x[k]) > 1e-9]
                if not cands:
                    continue
                scores = score(cands)
                j = int(np.argmin(scores))
                if scores[j] < best - 1e-3:
                    print(f"  r{rnd} {k}: {x[k]:.3g} → {cands[j][k]:.3g}   loss {best:.3f} → {scores[j]:.3f}", flush=True)
                    x, best = cands[j], scores[j]
                else:
                    print(f"  r{rnd} {k}: keep {x[k]:.3g} (tried {[round(c[k], 3) for c in cands]} → {[round(s, 3) for s in scores]})", flush=True)
            for k in step:
                step[k] *= 0.55
            log.append({"round": rnd, "loss": best, "params": dict(x)})
            print(f"round {rnd}: loss {best:.3f} ({time.time() - t0:.0f}s)", flush=True)
    (ROOT / "runs").mkdir(exist_ok=True)
    (ROOT / "runs" / "calibration.json").write_text(json.dumps(log, indent=1), encoding="utf-8")
    changed = {k: v for k, v in x.items() if abs(v - base(k)) > 1e-9}
    print("calibrated:", json.dumps({k: round(v, 3) for k, v in changed.items()}))
    if changed and not a.dry_run:
        write_back(changed)
        print("written to ucsim/config/mechanisms/")


if __name__ == "__main__":
    main()
