"""How traceable is the world's history?  Per event type, the share of events with a recorded reason.

    python -m scripts.provenance_coverage --scale 0.05 --days 60 --seed 3

An event counts as traced when it has a parent event (`cause`), a recorded decision (the choice that produced it) or
typed causes (the occasion, tie, person, place or earlier events behind it). "Several" counts events with at least
two distinct reasons — the start of a web rather than a chain. Prints a table and the headline shares for salient
events (salience ≥ 0.5) and the rest (also without the bookkeeping events added for provenance, so new event types
cannot flatter the score); `--json` writes the numbers for the report.
"""
from __future__ import annotations

import argparse
import json
import time

from ucsim.analysis.trace import coverage
from ucsim.engine.runner import new_simulation


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scale", type=float, default=0.05)
    ap.add_argument("--days", type=int, default=60)
    ap.add_argument("--seed", type=int, default=3)
    ap.add_argument("--json", default="", help="also write the result to this file")
    a = ap.parse_args()
    t0 = time.time()
    sim = new_simulation(scale=a.scale, seed=a.seed)
    sim.run_days(a.days)
    out = coverage(sim)
    out["run"] = {"scale": a.scale, "days": a.days, "seed": a.seed, "seconds": round(time.time() - t0, 1)}
    print(f"{'event':28s} {'sal':>4s} {'n':>6s} {'parent':>7s} {'decision':>8s} {'typed':>6s} {'any':>6s} {'several':>7s}")
    for r in out["types"]:
        print(f"{r['type']:28s} {r['salience']:4.2f} {r['n']:6d} {r['parent']:7.0%} {r['decision']:8.0%} "
              f"{r['typed']:6.0%} {r['any']:6.0%} {r['several']:7.0%}")
    h = out["headline"]
    pct = lambda x: "—" if x is None else f"{x:.0%}"   # noqa: E731
    print(f"\n{h['events']} events · salient (≥ 0.5) traced {pct(h['salient_any'])} (several reasons "
          f"{pct(h['salient_several'])}) · others {pct(h['other_any'])} · all {pct(h['all_any'])} · "
          f"{h['decisions']} decisions, {h['typed_causes']} typed causes · {out['run']['seconds']} s")
    print(f"without bookkeeping events: others {pct(h['other_any_excl'])} · all {pct(h['all_any_excl'])}")
    if a.json:
        with open(a.json, "w", encoding="utf-8") as f:
            json.dump(out, f, indent=1)


if __name__ == "__main__":
    main()
