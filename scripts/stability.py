"""Four-year stability check: do the big numbers stay put when the simulation runs for years?

    python scripts/stability.py --scale 0.05 --years 4 --seed 3

Writes ucsim/config/stability.json (shown in the app's Model check page). Snapshots are taken mid-fall
(late October) and mid-winter (early March) each year, when a survey would be fielded.
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np

from ucsim.engine.runner import new_simulation

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "ucsim" / "config" / "stability.json"


def snapshot(sim) -> dict:
    P = sim.w.P
    pres = P["present"].astype(bool)
    stu = pres & P["enrolled"].astype(bool)
    single = stu & P.isin("rel_status", ["single", "talking", "divorced"])
    lds = pres & P["lds_member"].astype(bool)
    return {
        "day": sim.w.day, "date": str(sim.cal.date(sim.w.day)),
        "byu_students_full_scale": round(int((stu & (P["school"] == 1)).sum()) / sim.w.scale),
        "uvu_students_full_scale": round(int((stu & (P["school"] == 2)).sum()) / sim.w.scale),
        "married_share_students": round(float(P.is_("rel_status", "married")[stu].mean()), 3),
        "dating_or_engaged_students": round(float(P.isin("rel_status", ["dating", "engaged"])[stu].mean()), 3),
        "dates_per_month_singles": round(float(P["dates_30d"][single].mean()), 2),
        "friends": round(float(P["n_friends"][pres].mean()), 2),
        "close_friends": round(float(P["n_close_friends"][pres].mean()), 2),
        "loneliness": round(float(P["loneliness"][pres].mean()), 3),
        "depressive_episode": round(float(P["depressive_episode"][pres].mean()), 3),
        "active_share_lds": round(float(P.is_("activity", "active")[lds].mean()), 3),
        "non_lds_share": round(float((~P["lds_member"].astype(bool))[pres].mean()), 3),
        "serving_missions": int(P.is_("mission_status", "serving").sum()),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scale", type=float, default=0.05)
    ap.add_argument("--years", type=int, default=4)
    ap.add_argument("--seed", type=int, default=3)
    a = ap.parse_args()
    t0 = time.time()
    sim = new_simulation(scale=a.scale, seed=a.seed)
    rows = []
    for y in range(a.years):
        for d in (60, 192):   # late October, early March
            sim.run_until(365 * y + d)
            rows.append(snapshot(sim))
            print(rows[-1], flush=True)
    keys = [k for k in rows[0] if k not in ("day", "date")]
    first, last = rows[:2], rows[-2:]
    drift = {k: round(float(np.mean([r[k] for r in last]) - np.mean([r[k] for r in first])), 3) for k in keys}
    OUT.write_text(json.dumps({"generated": time.strftime("%Y-%m-%d"), "scale": a.scale, "seed": a.seed, "years": a.years,
                               "rows": rows, "drift_first_to_last_year": drift, "seconds": round(time.time() - t0)}, indent=1),
                   encoding="utf-8")
    print("drift:", drift)


if __name__ == "__main__":
    main()
