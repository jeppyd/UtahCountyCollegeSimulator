"""Stock-flow accounting over a multi-year run.

    python scripts/accounting.py --scale 0.05 --years 3 --seed 3

Checkpoints on the same calendar day each year (late October by default), so seasonal moves cancel.
For each year prints stocks, flows, the balance residual and per-capita hazards, then the Little's-law
equilibrium implied by the last year's flows next to the starting stock (a start far from its equilibrium
drifts until it gets there). Writes ucsim/config/accounting.json (read by the Model check page).
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from ucsim.analysis.accounting import equilibria, stocks, yearly_report
from ucsim.engine.runner import new_simulation

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "ucsim" / "config" / "accounting.json"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scale", type=float, default=0.05)
    ap.add_argument("--years", type=int, default=3)
    ap.add_argument("--seed", type=int, default=3)
    ap.add_argument("--day", type=int, default=60, help="checkpoint day within each simulated year")
    ap.add_argument("--no-write", action="store_true")
    a = ap.parse_args()
    t0 = time.time()
    sim = new_simulation(scale=a.scale, seed=a.seed)
    cps = [{"day": 0, "stocks": stocks(sim)}]
    for y in range(a.years + 1):
        d = 365 * y + a.day
        sim.run_until(d)
        cps.append({"day": d, "stocks": stocks(sim)})
        print(f"day {d}: {cps[-1]['stocks']}", flush=True)
    rows = yearly_report(sim, cps[1:])
    for r in rows:
        print(f"\n== day {r['from']} → {r['to']}")
        for s, b in r["balance"].items():
            print(f"  {s:22s} Δ{b['delta']:+6d}  in {b['in']:6d}  out {b['out']:6d}  residual {b['residual']:+6d}")
        print("  hazards:", r["hazards"])
    eq = equilibria(rows[-1]["hazards"], cps[1]["stocks"]) if rows else {}
    print("\nimplied equilibria (vs first checkpoint):", eq)
    if not a.no_write:
        OUT.write_text(json.dumps({"generated": time.strftime("%Y-%m-%d"), "scale": a.scale, "seed": a.seed,
                                   "years": a.years, "checkpoints": cps, "years_table": rows, "equilibria": eq,
                                   "seconds": round(time.time() - t0)}, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
