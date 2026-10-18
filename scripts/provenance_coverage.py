"""How traceable is the world's history?  Per event type, the share of events with a recorded reason.

    python scripts/provenance_coverage.py --scale 0.05 --days 60 --seed 3

An event counts as traced when it has a parent event (`cause`), a recorded decision (the choice that produced it) or
typed causes (the occasion, tie, person, place or earlier events behind it). "Several" counts events with at least
two distinct reasons — the start of a web rather than a chain. Prints a table and the headline shares for salient
events (salience ≥ 0.5) and the rest; `--json` writes the numbers for the report.
"""
from __future__ import annotations

import argparse
import json
import time

import numpy as np

from ucsim.engine.runner import new_simulation


def coverage(sim) -> dict:
    """Per event type: n, share with a parent / decision / typed cause / any / several reasons."""
    log, reg = sim.log, sim.reg
    n = log.n
    types = log["type"]
    has_parent = log["cause"] >= 0
    has_dec = log["decision"] >= 0
    T = sim.causes.t
    typed_n = np.bincount(T["event"][(T["event"] >= 0) & (T["event"] < n)], minlength=n) if T.n else np.zeros(n, np.int64)
    # decisions linked from the decision side too (a decision may name its event without the event naming it)
    D = sim.decisions.t
    if D.n:
        dev = D["event"]
        dev = dev[(dev >= 0) & (dev < n)]
        has_dec = has_dec.copy()
        has_dec[dev] = True
    has_typed = typed_n > 0
    n_reasons = has_parent.astype(int) + has_dec.astype(int) + typed_n
    anyr = has_parent | has_dec | has_typed
    rows = []
    for code in np.unique(types):
        m = types == code
        k = int(m.sum())
        spec = reg.events[reg.event_names[code]]
        rows.append({"type": spec.id, "salience": spec.salience, "n": k,
                     "parent": float(has_parent[m].mean()), "decision": float(has_dec[m].mean()),
                     "typed": float(has_typed[m].mean()), "any": float(anyr[m].mean()),
                     "several": float((n_reasons[m] >= 2).mean())})
    sal = np.array([e.salience for e in reg.events.values()], np.float32)[types]
    hi = sal >= 0.5
    head = {"events": int(n),
            "salient_any": float(anyr[hi].mean()) if hi.any() else None,
            "other_any": float(anyr[~hi].mean()) if (~hi).any() else None,
            "all_any": float(anyr.mean()) if n else None,
            "salient_several": float((n_reasons[hi] >= 2).mean()) if hi.any() else None,
            "decisions": int(D.n), "typed_causes": int(T.n)}
    return {"headline": head, "types": sorted(rows, key=lambda r: (-r["salience"], -r["n"]))}


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
    if a.json:
        with open(a.json, "w", encoding="utf-8") as f:
            json.dump(out, f, indent=1)


if __name__ == "__main__":
    main()
