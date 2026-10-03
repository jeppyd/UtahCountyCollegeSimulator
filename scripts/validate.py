"""Validation report: simulate a year and compare against survey aggregates and institutional targets.

    python scripts/validate.py --scale 0.15 --days 365 --seed 1

Writes docs/VALIDATION.md (and runs/validation.json). Every comparison is labeled:
  input    – the variable is synthesized from the survey (checks the synthesizer, not the dynamics)
  emergent – produced by simulated behavior (the real test)
Status bands use a tolerance of max(15% of target, 10% of target IQR, an absolute floor).
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np

from ucsim.engine.runner import new_simulation
from ucsim.population.sampling import load_priors

ROOT = Path(__file__).resolve().parents[1]
ACT = {0: "inactive", 1: "less_active", 2: "active"}


def age_band(label: str) -> tuple[float, float]:
    if label.endswith("+"):
        return float(label[:-1]), 99.0
    lo, hi = label.split("-")
    return float(lo), float(hi) + 1


def band_mask(P, row):
    m = (P["school"] > 0) & P["present"].astype(bool)
    if "sex" in row:
        m &= P.is_("sex", row["sex"])
    if "school_proxy" in row:
        m &= P.is_("school", row["school_proxy"])
    if "rel" in row:
        rel = {"single": ["single", "talking", "divorced"], "dating": ["dating"], "engaged": ["engaged"], "married": ["married"]}.get(row["rel"], [row["rel"]])
        m &= P.isin("rel_status", rel)
    if "activity" in row and row["activity"] is not None:
        m &= P["lds_member"].astype(bool) & P.is_("activity", ACT[int(row["activity"])])
    if "age_band" in row:
        lo, hi = age_band(row["age_band"])
        m &= (P["age"] >= lo) & (P["age"] < hi)
    return m


# target table → (simulated variable, transform, kind, absolute floor)
CHECKS = {
    "dates_month_by_sex_age": ("dates_30d", None, "emergent", 0.4),
    "dates_month_by_sex_rel_activity": ("dates_30d", None, "emergent", 0.6),
    "married_share_by_age_sex": ("rel_status", "married", "emergent", 0.04),
    "n_relationships_by_sex_age": ("n_relationships", None, "input", 0.3),
    "n_kissed_by_sex_age": ("n_kissed", None, "input", 1.0),
    "gpa_by_school_sex": ("gpa", None, "emergent", 0.1),
    "sleep_by_school": ("sleep_hours", None, "emergent", 0.3),
    "work_hours_by_school": ("work_hours", None, "input", 2.0),
    "social_events_by_sex_rel": ("social_events_month", None, "emergent", 1.0),
    "app_hours_by_sex_rel": ("app_hours", None, "emergent", 0.25),
    "social_media_hours_by_sex": ("social_media_hours", None, "input", 0.3),
    "coffee_by_activity": ("coffee", None, "emergent", 0.15),
    "alcohol_by_activity": ("alcohol", None, "emergent", 0.15),
    "temple_per_year_by_activity": ("temple_per_year", None, "emergent", 2.0),
    "scripture_minutes_by_activity": ("scripture_minutes", None, "emergent", 3.0),
}


def sim_value(P, var, transform, m):
    if transform == "married":
        return float(P.is_("rel_status", "married")[m].mean())
    x = P[var][m].astype(float)
    x = x[np.isfinite(x)]
    return float(x.mean()) if len(x) else float("nan")


def status(diff, tol):
    if not np.isfinite(diff):
        return "n/a"
    return "pass" if abs(diff) <= tol else "warn" if abs(diff) <= 2 * tol else "fail"


def compare(sim, priors):
    P = sim.w.P
    rows = []
    for table, (var, transform, kind, floor) in CHECKS.items():
        for r in priors["targets"].get(table, []):
            if r.get("n_band") in ("<10",):
                continue
            m = band_mask(P, r)
            n = int(m.sum())
            if n < 25:
                continue
            target = float(r["mean"]) if transform != "married" else float(r["share_pos"])
            got = sim_value(P, var, transform, m)
            iqr = float(r.get("p75", 0) - r.get("p25", 0))
            tol = max(0.15 * abs(target), 0.1 * iqr, floor)
            group = ", ".join(f"{k}={ACT.get(v, v) if k == 'activity' else v}" for k, v in r.items()
                              if k in ("sex", "rel", "activity", "age_band", "school_proxy"))
            rows.append({"table": table, "group": group, "var": var, "kind": kind, "target": target, "sim": got,
                         "diff": got - target, "tol": tol, "n_sim": n, "n_band": r.get("n_band"), "status": status(got - target, tol)})
    return rows


def institutional(sim):
    P, cfg = sim.w.P, sim.w.cfg
    present = P["present"].astype(bool)
    out = []
    for school, key in (("BYU", "byu"), ("UVU", "uvu")):
        t = cfg["population"][key]
        m = present & P.is_("school", school)
        out.append({"metric": f"{school} students (scaled to full)", "target": t["students"], "sim": round(m.sum() / sim.w.scale)})
        out.append({"metric": f"{school} married share", "target": t["married_share"],
                    "sim": round(float(P.is_("rel_status", "married")[m].mean()), 3)})
    lds = present & P["lds_member"].astype(bool) & P.is_("school", "UVU")
    out.append({"metric": "UVU LDS share", "target": cfg["population"]["uvu"]["lds_share"],
                "sim": round(float(lds.sum() / max((present & P.is_("school", "UVU")).sum(), 1)), 3)})
    return out


def trajectory(sim, days, every=30):
    P = sim.w.P
    rows = []
    t0 = time.time()
    for d in range(days):
        sim.step_day()
        if (d + 1) % every == 0 or d == days - 1:
            present = P["present"].astype(bool)
            stu = present & (P["school"] > 0)
            single = stu & P.isin("rel_status", ["single", "talking", "divorced"])
            rows.append({
                "day": sim.w.day, "date": str(sim.cal.date(sim.w.day)), "present": int(present.sum()),
                "students": int(stu.sum()), "married": round(float(P.is_("rel_status", "married")[stu].mean()), 3),
                "dating_or_engaged": round(float(P.isin("rel_status", ["dating", "engaged"])[stu].mean()), 3),
                "dates_30d_singles": round(float(P["dates_30d"][single].mean()), 2),
                "friends": round(float(P["n_friends"][present].mean()), 1),
                "close_friends": round(float(P["n_close_friends"][present].mean()), 1),
                "loneliness": round(float(P["loneliness"][present].mean()), 3),
                "depressed": round(float(P["depressive_episode"][present].mean()), 3) if "depressive_episode" in P else None,
                "active_lds": round(float(P.is_("activity", "active")[present & P["lds_member"].astype(bool)].mean()), 3),
                "serving_missions": int(P.is_("mission_status", "serving").sum()),
                "sec_per_day": round((time.time() - t0) / (d + 1), 3),
            })
            print(rows[-1])
    return rows


def md_table(rows, cols):
    head = "| " + " | ".join(cols) + " |\n|" + "---|" * len(cols) + "\n"
    def f(v):
        return f"{v:.3g}" if isinstance(v, float) else str(v)
    return head + "\n".join("| " + " | ".join(f(r.get(c)) for c in cols) + " |" for r in rows) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scale", type=float, default=0.15)
    ap.add_argument("--days", type=int, default=365)
    ap.add_argument("--seed", type=int, default=1)
    a = ap.parse_args()
    t0 = time.time()
    sim = new_simulation(scale=a.scale, seed=a.seed)
    build_s = time.time() - t0
    priors = load_priors()
    traj = []
    # compare in the fall (day 60) and mid-winter semester (day 200, primary); the year-end snapshot
    # lands just after the new cohort arrives, which is not comparable to a mid-semester survey
    traj += trajectory(sim, 60, every=15)
    early = compare(sim, priors)
    traj += trajectory(sim, 140, every=30)
    final = compare(sim, priors)
    inst = institutional(sim)
    snap_day = sim.w.day
    traj += trajectory(sim, max(a.days - 200, 0), every=30)
    timing = {k: round(v, 2) for k, v in sorted(sim.timing.items(), key=lambda kv: -kv[1])}
    run_s = time.time() - t0 - build_s

    counts = {s: sum(r["status"] == s for r in final) for s in ("pass", "warn", "fail")}
    emer = [r for r in final if r["kind"] == "emergent"]
    counts_e = {s: sum(r["status"] == s for r in emer) for s in ("pass", "warn", "fail")}
    early_map = {(r["table"], r["group"]): r for r in early}
    for r in final:
        e = early_map.get((r["table"], r["group"]))
        r["sim_day60"] = e["sim"] if e else float("nan")

    doc = f"""# Validation

Generated by `scripts/validate.py --scale {a.scale} --days {a.days} --seed {a.seed}` —
{sim.w.P.n:,} agent rows ({int(sim.w.P['present'].sum()):,} present at the end), build {build_s:.1f}s, simulation {run_s:.0f}s
({run_s / a.days:.2f}s per simulated day).

**What this is.** Simulated group means compared with the survey aggregates (small cells suppressed) and the
institutional targets in `world.yaml`. Rows marked *input* are synthesized from the same survey — agreement there
checks the synthesizer. Rows marked *emergent* are produced by simulated behavior and are the real test.
Tolerance per row = max(15% of target, 10% of the target's IQR, an absolute floor); **pass** ≤ 1×, **warn** ≤ 2×, **fail** beyond.

**Caveat.** The surveys are convenience samples of mostly BYU students (married students and UVU are under-represented),
so a mismatch can mean the survey is biased, not the model. Married shares are calibrated to institutional
targets, not the survey (BYU survey 12% vs ~25% institutional).

## Summary at day {snap_day} ({sim.cal.date(snap_day)}, mid winter semester)

All rows: {counts['pass']} pass · {counts['warn']} warn · {counts['fail']} fail.
Emergent rows only: {counts_e['pass']} pass · {counts_e['warn']} warn · {counts_e['fail']} fail.

## Institutional targets (day {snap_day})

{md_table(inst, ['metric', 'target', 'sim'])}
## Survey comparisons

{md_table(final, ['table', 'group', 'kind', 'target', 'sim_day60', 'sim', 'tol', 'status', 'n_sim', 'n_band'])}
## One-year trajectory (stability)

{md_table(traj, list(traj[0].keys()))}
## Where the time goes (seconds, whole run)

{md_table([{'system': k, 'seconds': v} for k, v in timing.items()], ['system', 'seconds'])}
## Reading the remaining mismatches

- **Married share among older students** (22+): the surveys under-sample married students (BYU survey 12%
  married vs ≈25% institutionally), so their married share by age is biased low. The model is calibrated to
  the institutional totals, which puts more of the married students in the older bands. Treat these rows
  as a survey-bias diagnostic rather than a model failure.
- **Dating frequency** is now within tolerance for most single and dating groups; engaged couples date
  somewhat more than reported, and older singles somewhat more often than the survey says.
- *Input* rows (synthesized from the survey) that drift are changed by dynamics on purpose (e.g. work hours
  respond to financial strain); a large drift there points to a mechanism that needs a counterweight.

## Known gaps (first iteration)

- Dating frequency and relationship progression are calibrated by hand against the dating survey; a formal
  calibration loop (simulated method of moments over the mechanism parameter ranges) is on the roadmap.
- Several targets (GPA, sleep, app hours) depend on survey-derived starting values plus modest dynamics, so they
  agree partly by construction.
- No administrative validation yet (actual marriage counts, enrollment flows, rent series).
"""
    (ROOT / "docs").mkdir(exist_ok=True)
    (ROOT / "docs" / "VALIDATION.md").write_text(doc)
    (ROOT / "runs").mkdir(exist_ok=True)
    (ROOT / "runs" / "validation.json").write_text(json.dumps({"final": final, "institutional": inst, "trajectory": traj, "timing": timing}, default=float, indent=1))
    print(f"wrote docs/VALIDATION.md — {counts}")


if __name__ == "__main__":
    main()
