"""Print how long a simulated day takes (overall and per system) against the speed budget; --update records it.

    python scripts/perf.py [--update "why"] [--scale 0.1] [--days 5]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ucsim import perf  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--update", nargs="?", const="", default=None, help="record these timings as the budget (with a note)")
    ap.add_argument("--scale", type=float, default=perf.SETUP["scale"])
    ap.add_argument("--days", type=int, default=perf.SETUP["days"])
    a = ap.parse_args()
    m = perf.measure({"scale": a.scale, "days": a.days})
    b = perf.load_budget()
    print(f"{m['people']} people · {m['s_per_day']:.3f} s per simulated day (calibration {m['calibration_s']:.3f} s)")
    for k, v in sorted(m["systems_s_per_day"].items(), key=lambda x: -x[1])[:15]:
        ref = (b or {}).get("norm_systems", {}).get(k)
        vs = f"  ({m['norm_systems'][k] / ref:.2f}× budget)" if ref else "  (new)" if b else ""
        print(f"  {k:16s} {v:.4f} s{vs}")
    if b:
        print(f"day vs budget: {m['norm_per_day'] / b['norm_per_day']:.2f}×")
        for p in perf.check(m, b):
            print("  OVER:", p)
    if a.update is not None:
        if (a.scale, a.days) != (perf.SETUP["scale"], perf.SETUP["days"]):
            sys.exit("record the budget with the default --scale and --days")
        perf.save_budget(m, a.update)
        print("budget recorded:", perf.BUDGET)


if __name__ == "__main__":
    main()
