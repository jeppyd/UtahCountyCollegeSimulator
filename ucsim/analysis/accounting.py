"""Demographic and institutional accounting: do stocks, inflows, outflows and durations add up?

A world can drift for years while every daily rule looks plausible. This module checks the run as a
dynamic system rather than a set of rules:

* **stocks** at each checkpoint (people present, students, serving missionaries, married people,
  Latter-day Saint members, people in a depressive episode),
* **flows** between checkpoints counted from the event log (arrivals, departures, weddings, divorces,
  calls, returns, onsets, remissions …),
* the **balance** ``Δstock − (inflow − outflow)``: a large residual means some transition is not logged
  or a stock is changed outside its flows,
* **implied equilibria** for first-order stocks: with a per-capita exit hazard ``h`` and an inflow ``I``
  the stock settles near ``I / h`` (Little's law). A start far from that value means the initial
  condition is out of equilibrium and the stock will drift until it gets there.

Checkpoints are taken on the same calendar day each year so seasonal moves (the summer exodus) cancel.
"""
from __future__ import annotations

import numpy as np

# stock name -> (in events, out events). Two-person events are logged once per person, so person counts
# are exact for weddings and divorces.
FLOWS = {
    "present": (["arrival", "mission_return", "early_return"], ["mission_departure", "left_area"]),
    "serving_missionaries": (["mission_departure"], ["mission_return", "early_return"]),
    "married": (["wedding"], ["breakup_received_married", "breakup_initiated_married"]),
    "depressive_episode": (["depressive_episode_start"], ["depressive_episode_end"]),
    "lds_members": (["baptized"], ["resigned_membership"]),
}


def stocks(sim) -> dict:
    """Current values of the accounted stocks."""
    P = sim.w.P
    pres = P["present"].astype(bool)
    stu = pres & P["enrolled"].astype(bool)
    return {
        "present": int(pres.sum()),
        "students_byu": int((stu & (P["school"] == 1)).sum()),
        "students_uvu": int((stu & (P["school"] == 2)).sum()),
        "serving_missionaries": int(P.is_("mission_status", "serving").sum()),
        "married": int((pres & P.is_("rel_status", "married")).sum()),
        "depressive_episode": int((pres & P["depressive_episode"].astype(bool)).sum()),
        "lds_members": int((pres & P["lds_member"].astype(bool)).sum()),
        "rows_allocated": int(P.n),
    }


def flow_counts(sim, d0: int, d1: int) -> dict:
    """Event counts by type in [d0, d1), with married/unmarried breakups and resignations split out."""
    log = sim.log
    day = log["day"]
    m = (day >= d0) & (day < d1)
    names = sim.reg.event_names
    cnt = np.bincount(log["type"][m], minlength=len(names))
    out = {names[k]: int(cnt[k]) for k in np.nonzero(cnt)[0]}
    # breakups of married couples are divorces: value carries no flag, so use the a-person's status now
    # being 'divorced' as the marker (status only becomes divorced through that path)
    P = sim.w.P
    for et in ("breakup_received", "breakup_initiated"):
        code = sim.reg.event_ids[et]
        mm = m & (log["type"] == code)
        a = log["a"][mm]
        out[f"{et}_married"] = int(P.is_("rel_status", "divorced")[a].sum()) if len(a) else 0
    return out


def hazards(sim, d0: int, d1: int, mid: dict) -> dict:
    """Per-capita annual rates for the main transitions, using the mid-period stock as exposure."""
    f = flow_counts(sim, d0, d1)
    yrs = max((d1 - d0) / 365.25, 1e-9)
    out = {}
    pres = max(mid.get("present", 1), 1)

    def rate(num, den):
        return round(num / max(den, 1) / yrs, 4)

    out["mission_departures_per_year"] = round(f.get("mission_departure", 0) / yrs, 1)
    out["mission_returns_per_year"] = round((f.get("mission_return", 0) + f.get("early_return", 0)) / yrs, 1)
    out["weddings_per_1000_present"] = round(1000 * f.get("wedding", 0) / 2 / pres / yrs, 2)
    out["divorce_rate_married"] = rate(f.get("breakup_received_married", 0), mid.get("married", 0))
    out["depression_onsets_per_year"] = round(f.get("depressive_episode_start", 0) / yrs, 1)
    out["depression_remission_hazard"] = rate(f.get("depressive_episode_end", 0), mid.get("depressive_episode", 0))
    out["arrivals_per_year"] = round(f.get("arrival", 0) / yrs, 1)
    out["departures_per_year"] = round(f.get("left_area", 0) / yrs, 1)
    return out


def equilibria(h: dict, now: dict) -> dict:
    """Little's-law equilibrium of first-order stocks vs their current value."""
    out = {}
    dep = h.get("mission_departures_per_year", 0)
    ret = h.get("mission_returns_per_year", 0)
    if ret > 0 and now.get("serving_missionaries"):
        mean_service = now["serving_missionaries"] / max(ret, 1e-9)  # years (stock / outflow)
        out["serving_missionaries"] = {"now": now["serving_missionaries"], "implied": round(dep * min(mean_service, 2.0)),
                                       "note": "departures/yr × mean service (≤2 yr)"}
    rem = h.get("depression_remission_hazard", 0)
    on = h.get("depression_onsets_per_year", 0)
    if rem > 0:
        out["depressive_episode"] = {"now": now.get("depressive_episode", 0), "implied": round(on / rem),
                                     "note": "onsets/yr ÷ remission hazard"}
    return out


def yearly_report(sim, checkpoints: list[dict]) -> list[dict]:
    """Balance table between consecutive checkpoints ({day, stocks})."""
    rows = []
    for a, b in zip(checkpoints[:-1], checkpoints[1:]):
        f = flow_counts(sim, a["day"], b["day"])
        mid = {k: (a["stocks"][k] + b["stocks"][k]) / 2 for k in a["stocks"]}
        row = {"from": a["day"], "to": b["day"], "stocks_from": a["stocks"], "stocks_to": b["stocks"],
               "hazards": hazards(sim, a["day"], b["day"], mid), "balance": {}}
        for s, (ins, outs) in FLOWS.items():
            if s not in a["stocks"]:
                continue
            inflow = sum(f.get(e, 0) for e in ins)
            outflow = sum(f.get(e, 0) for e in outs)
            d = b["stocks"][s] - a["stocks"][s]
            row["balance"][s] = {"delta": d, "in": inflow, "out": outflow, "residual": d - (inflow - outflow)}
        rows.append(row)
    return rows
