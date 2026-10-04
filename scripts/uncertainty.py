"""Uncertainty ensemble for a What-if: stochastic vs model/parameter uncertainty.

    python scripts/uncertainty.py --preset rent_up_20 --draws 6 --seeds 1,2,3 --days 90 --scale 0.05

Prints, for each outcome, the mean paired effect with its 10th–90th percentile range, the share of variance
due to parameter draws vs random social history, how often the effect has the same sign, and the parameters
that drive it (with evidence labels). Writes runs/uncertainty_<preset>.json.
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from ucsim.engine.uncertainty import ensemble

ROOT = Path(__file__).resolve().parents[1]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--preset", default="rent_up_20")
    ap.add_argument("--draws", type=int, default=6)
    ap.add_argument("--seeds", default="1,2,3")
    ap.add_argument("--days", type=int, default=90)
    ap.add_argument("--warmup", type=int, default=21)
    ap.add_argument("--scale", type=float, default=0.05)
    ap.add_argument("--workers", type=int, default=4)
    a = ap.parse_args()
    t0 = time.time()
    res = ensemble([{"preset": a.preset}], n_draws=a.draws, seeds=tuple(int(s) for s in a.seeds.split(",")), days=a.days,
                   warmup=a.warmup, scale=a.scale, workers=a.workers,
                   progress=lambda i, n: print(f"  {i}/{n} pairs ({time.time() - t0:.0f}s)", flush=True))
    print(f"\n{a.preset}: {res['n_params']} uncertain parameters × {a.draws} draws × {len(res['seeds'])} seeds, {a.days} days")
    for k, d in sorted(res["outcomes"].items(), key=lambda kv: -abs(kv[1]["mean"]) / (kv[1]["sd_total"] + 1e-9)):
        drv = ", ".join(f"{x['param']} ({x['evidence']}, ρ={x['rho']:+.2f})" for x in d["drivers"][:3]) or (d.get("drivers_note") or "no single parameter stands out")
        print(f"  {k:22s} effect {d['mean']:+.4f} [{d['p10']:+.4f}, {d['p90']:+.4f}]  parametric {d['share_parametric']:.0%}"
              f"  stochastic {d['share_stochastic']:.0%}  same sign {d['same_sign'] if d['same_sign'] is None else round(d['same_sign'], 2)}  ← {drv}")
    out = ROOT / "runs"
    out.mkdir(exist_ok=True)
    (out / f"uncertainty_{a.preset}.json").write_text(json.dumps(res, indent=1, default=float), encoding="utf-8")
    print(f"\n{time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
