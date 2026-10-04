"""Validation report: simulate a year and compare against survey aggregates and institutional targets.

    python scripts/validate.py --scale 0.15 --days 365 --seed 1

Writes docs/VALIDATION.md and ucsim/config/validation.json (shown in the app's Model check page).
Every comparison is labeled:
  benchmark  – official statistics (Census ACS for Provo + Orem): the most trustworthy targets
  emergent   – produced by simulated behavior, compared with the surveys (the real test of dynamics)
  input      – the variable is synthesized from the survey (checks the synthesizer, not the dynamics)
  diagnostic – survey rows known to be biased (the dating surveys under-sample married people)
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
ACS = ROOT / "ucsim" / "config" / "sources" / "acs_married_share_provo_orem.json"
OUT_JSON = ROOT / "ucsim" / "config" / "validation.json"


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
    # by-age rows mix singles and couples in the survey's (singles-heavy) proportions → diagnostic only;
    # the rows stratified by relationship status below are robust to that composition bias
    "dates_month_by_sex_age": ("dates_30d", None, "diagnostic", 0.4),
    "dates_month_by_sex_rel_activity": ("dates_30d", None, "emergent", 0.6),
    "married_share_by_age_sex": ("rel_status", "married", "diagnostic", 0.04),
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


# Survey tables held out of calibration (scripts/calibrate.py never sees them): they test the calibrated model
# on targets it was not tuned to.
HOLDOUT = {"gpa_by_school_sex", "scripture_minutes_by_activity", "alcohol_by_activity", "sleep_by_school"}


def patterns(sim):
    """Pattern-oriented checks (Grimm et al. 2005): structural signatures the model should reproduce besides
    population means — perception gaps, network structure, the intention–behavior gap, seasonal rhythm."""
    from ucsim.engine.state import Tie
    P, E = sim.w.P, sim.w.E
    pres = P["present"].astype(bool)
    rows = []

    def row(name, group, target, got, tol, kind, note):
        rows.append({"table": name, "group": group, "var": name, "kind": kind, "target": target, "sim": got,
                     "diff": got - target if np.isfinite(got) else float("nan"), "tol": tol, "n_sim": int(pres.sum()),
                     "n_band": note, "status": status(got - target, tol) if np.isfinite(got) else "n/a"})

    r = float(np.corrcoef(P["perceived_support"][pres], P["support_actual"][pres])[0, 1])
    row("perceived_vs_actual_support", "everyone present", 0.40, r, 0.12, "pattern",
        "literature: perceived vs received r=.35 (Haber 2007); vs network .2–.5")
    # clustering of the friendship network (stage ≥ friend, present people)
    lo, hi = E.endpoints()
    m = (E["stage"] >= 3) & pres[lo] & pres[hi]
    a, b = lo[m], hi[m]
    n = P.n
    import scipy.sparse as sp
    A = sp.coo_matrix((np.ones(2 * len(a)), (np.r_[a, b], np.r_[b, a])), shape=(n, n)).tocsr()
    deg = np.asarray(A.sum(axis=1)).ravel()
    tri = np.asarray((A @ A).multiply(A).sum(axis=1)).ravel() / 2
    possible = deg * (deg - 1) / 2
    cc = float(np.mean(tri[deg >= 2] / possible[deg >= 2])) if (deg >= 2).any() else float("nan")
    row("friend_network_clustering", "people with ≥2 friends", 0.25, cc, 0.10, "pattern",
        "student friendship networks ≈ .2–.35 (assumption from network studies)")
    plans = sim.systems.get("plans")
    if plans is not None and plans.n:
        since = sim.w.day - 120
        fin = (plans["start"] >= since) & (plans["status"] > 0)
        kept = float((plans["status"][fin] == 1).mean()) if fin.any() else float("nan")
        row("intentions_carried_out", "intentions in the last 120 days", 0.50, kept, 0.12, "pattern",
            "about half of intentions are acted on (Sheeran 2002)")
    log = sim.log
    code = sim.reg.event_ids["wedding"]
    wm = log["type"] == code
    if wm.sum() >= 20:
        mon = np.array([sim.cal.date(int(d)).month for d in log["day"][wm]])
        dd = np.array([sim.cal.date(int(d)).day for d in log["day"][wm]])
        brk = ((mon >= 5) & (mon <= 7)) | ((mon == 4) & (dd >= 23)) | ((mon == 8) & (dd <= 22)) | ((mon == 12) & (dd >= 18)) | ((mon == 1) & (dd <= 5))
        row("weddings_between_semesters", "weddings so far", 0.60, float(brk.mean()), 0.15, "diagnostic",
            "assumption: student weddings cluster in breaks")
    # liking gap: new acquaintances underestimate the other's interest
    new = (E["n_inter"] <= 5) & (E["stage"] >= 1)
    if new.any():
        gap = float(np.mean(np.r_[E["bel_lh"][new] - E["att_hl"][new], E["bel_hl"][new] - E["att_lh"][new]]))
        row("liking_gap_new_acquaintances", "ties with ≤5 interactions", -0.05, gap, 0.08, "diagnostic",
            "Boothby et al. 2018: people underestimate how much new partners like them")
    lds_doubt = pres & P["lds_member"].astype(bool) & (P["faith_belief"] < 0.45)
    if lds_doubt.sum() >= 25:
        pi = float(np.mean(P["perceived_friend_belief"][lds_doubt] - P["friend_belief_actual"][lds_doubt]))
        row("pluralistic_ignorance_doubters", "members with belief < 0.45", 0.05, pi, 0.05, "diagnostic",
            "doubters overestimate peers' belief (Prentice & Miller 1993 direction)")
    dep = float(P["depressive_episode"][pres].mean())
    row("depressive_episode_prevalence", "everyone present", 0.08, dep, 0.04, "diagnostic",
        "point prevalence ~6-10% (NSDUH 18-25 past-year MDE ≈19%; assumption)")
    return rows


def longitudinal(sim):
    from ucsim.analysis.panel import report
    return report(sim)


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
                         "diff": got - target, "tol": tol, "n_sim": n, "n_band": r.get("n_band"), "status": status(got - target, tol),
                         "holdout": table in HOLDOUT})
    return rows


def benchmarks(sim):
    """Married share by age and sex for everyone present, vs Census ACS for Provo + Orem residents."""
    if not ACS.exists():
        return []
    P = sim.w.P
    pres = P["present"].astype(bool)
    rows = []
    for r in json.loads(ACS.read_text(encoding="utf-8"))["rows"]:
        lo, hi = age_band(r["age_band"])
        m = pres & P.is_("sex", r["sex"]) & (P["age"] >= lo) & (P["age"] < hi)
        n = int(m.sum())
        if n < 25:
            continue
        got = float(P.is_("rel_status", "married")[m].mean())
        tol = max(0.15 * r["married_share"], 0.04)
        # from 25 on, Provo/Orem residents are mostly non-students the model does not include (single working
        # adults), so those bands compare different populations: shown, not scored
        kind = "benchmark" if r["age_band"] in ("18-19", "20-24") else "diagnostic"
        rows.append({"table": "married_share_acs", "group": f"sex={r['sex']}, age={r['age_band']}", "var": "rel_status",
                     "kind": kind, "target": r["married_share"], "sim": got, "diff": got - r["married_share"],
                     "tol": tol, "n_sim": n, "n_band": f"ACS n={r['n']:,}", "status": status(got - r["married_share"], tol)})
    # institutional married shares of enrolled students (BYU ≈ 25%, UVU ≈ 30%; world.yaml)
    for school, key in (("BYU", "byu"), ("UVU", "uvu")):
        t = float(sim.w.cfg["population"][key]["married_share"])
        m = P["present"].astype(bool) & P["enrolled"].astype(bool) & P.is_("school", school)
        if m.sum() >= 25:
            got = float(P.is_("rel_status", "married")[m].mean())
            rows.append({"table": "married_share_institutional", "group": f"school={school}", "var": "rel_status",
                         "kind": "benchmark", "target": t, "sim": got, "diff": got - t, "tol": 0.04, "n_sim": int(m.sum()),
                         "n_band": "institutional", "status": status(got - t, 0.04)})
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
    early = benchmarks(sim) + compare(sim, priors)
    traj += trajectory(sim, 140, every=30)
    final = benchmarks(sim) + compare(sim, priors) + patterns(sim)
    inst = institutional(sim)
    snap_day = sim.w.day
    traj += trajectory(sim, max(a.days - 200, 0), every=30)
    longi = longitudinal(sim)
    timing = {k: round(v, 2) for k, v in sorted(sim.timing.items(), key=lambda kv: -kv[1])}
    run_s = time.time() - t0 - build_s

    scored = [r for r in final if r["kind"] != "diagnostic"]
    counts = {s: sum(r["status"] == s for r in scored) for s in ("pass", "warn", "fail")}
    emer = [r for r in final if r["kind"] in ("emergent", "benchmark")]
    counts_e = {s: sum(r["status"] == s for r in emer) for s in ("pass", "warn", "fail")}
    bench = [r for r in final if r["kind"] == "benchmark"]
    counts_b = {s: sum(r["status"] == s for r in bench) for s in ("pass", "warn", "fail")}
    hold = [r for r in final if r.get("holdout")]
    counts_h = {s: sum(r["status"] == s for r in hold) for s in ("pass", "warn", "fail")}
    pat = [r for r in final if r["kind"] in ("pattern",) or r["table"] in ("liking_gap_new_acquaintances", "pluralistic_ignorance_doubters",
                                                                            "weddings_between_semesters", "depressive_episode_prevalence")]
    survey_rows = [r for r in final if r not in pat]
    early_map = {(r["table"], r["group"]): r for r in early}
    for r in final:
        e = early_map.get((r["table"], r["group"]))
        r["sim_day60"] = e["sim"] if e else float("nan")

    doc = f"""# Validation

Generated by `scripts/validate.py --scale {a.scale} --days {a.days} --seed {a.seed}` —
{sim.w.P.n:,} agent rows ({int(sim.w.P['present'].sum()):,} present at the end), build {build_s:.1f}s, simulation {run_s:.0f}s
({run_s / a.days:.2f}s per simulated day).

**What this is.** Simulated group means compared with official statistics, the survey aggregates (small cells
suppressed) and the institutional targets in `world.yaml`. *Benchmark* rows are Census ACS figures for Provo + Orem
(the most trustworthy). *Emergent* rows are produced by simulated behavior (the real test of the dynamics).
*Input* rows are synthesized from the same survey (agreement checks the synthesizer). *Diagnostic* rows are
survey cells known to be biased and are not scored.
Tolerance per row = max(15% of target, 10% of the target's IQR, an absolute floor); **pass** ≤ 1×, **warn** ≤ 2×, **fail** beyond.

**Caveat.** The surveys are convenience samples of mostly single BYU students (married students and UVU are
under-represented), so a mismatch can mean the survey is biased, not the model. Married shares are calibrated to
the Census (ACS 2020-24: e.g. 60% of Provo/Orem women aged 25-29 are married, versus 35% of the dating-survey
respondents aged 24-26).

## Summary at day {snap_day} ({sim.cal.date(snap_day)}, mid winter semester)

Scored rows: {counts['pass']} pass · {counts['warn']} warn · {counts['fail']} fail.
Census benchmarks: {counts_b['pass']} pass · {counts_b['warn']} warn · {counts_b['fail']} fail.
Behavior (benchmark + emergent): {counts_e['pass']} pass · {counts_e['warn']} warn · {counts_e['fail']} fail.
Held out of calibration ({', '.join(sorted(HOLDOUT))}): {counts_h['pass']} pass · {counts_h['warn']} warn · {counts_h['fail']} fail.

## Institutional targets (day {snap_day})

{md_table(inst, ['metric', 'target', 'sim'])}
## Survey comparisons

{md_table(survey_rows, ['table', 'group', 'kind', 'target', 'sim_day60', 'sim', 'tol', 'status', 'holdout', 'n_sim', 'n_band'])}
## Patterns (structure, not just means)

Signatures the model should reproduce besides averages (pattern-oriented modeling, Grimm et al. 2005). *Pattern* rows
are scored against literature ranges; *diagnostic* rows check a direction or an assumption and are not scored.

{md_table(pat, ['table', 'group', 'kind', 'target', 'sim', 'tol', 'status', 'n_band'])}
## Longitudinal structure (within- vs between-person)

From two-weekly person snapshots at ~4-week lags over the run (`ucsim/analysis/panel.py`): *between r* correlates people's
averages; *X→Y* and *Y→X* are within-person cross-lagged effects (standardized deviations from each person's own mean,
controlling the outcome's lag — the logic of the RI-CLPM, Hamaker et al. 2015). In real panels within-person
cross-lagged effects are typically small (Orth et al. 2022 benchmarks: .03 small, .07 medium, .12 large) even where
cross-sectional correlations are strong; the model shows the same gap. Short panels bias within-person estimates
slightly negative (Nickell bias), so read signs near zero with care. The same estimator runs on real survey waves.

{md_table(longi, ['x', 'y', 'waves', 'people', 'cross_sectional_r', 'between_r', 'x_to_y', 'y_to_x']) if longi else 'n/a'}
## One-year trajectory (stability)

{md_table(traj, list(traj[0].keys()))}
## Where the time goes (seconds, whole run)

{md_table([{'system': k, 'seconds': v} for k, v in timing.items()], ['system', 'seconds'])}
## Reading the remaining mismatches

- **Dates per month by age** mixes singles and couples in the survey's proportions, so it is shown as
  *diagnostic*; the rows by relationship status and church activity are the scored test.
- **Census married share at 25+** is shown but not scored: most Provo/Orem residents of those ages are
  non-students outside the model's scope (single working adults), so the populations differ.
- **Married share by age**: the surveys under-sample married students (BYU survey 12% married vs ≈25%
  institutionally), so the survey's married share by age is biased low; those rows are shown as *diagnostic*.
  The Census rows are the benchmark the model is calibrated to.
- **Dating frequency** is now within tolerance for most single and dating groups; engaged couples date
  somewhat more than reported, and older singles somewhat more often than the survey says.
- *Input* rows (synthesized from the survey) that drift are changed by dynamics on purpose (e.g. work hours
  respond to financial strain); a large drift there points to a mechanism that needs a counterweight.

## Calibration

`scripts/calibrate.py` searches the ranges of the most influential parameters (asking out, kissing, couple time,
engagement, breakups, job search) to minimize the weighted squared misfit across the benchmark, emergent and
input rows above (two seeds, common random numbers). The chosen values are written back to the mechanism files.

## Known gaps

- The fit is to one year; the four-year check (`scripts/stability.py`) shows slower drifts that remain.
- Several targets (GPA, sleep, app hours) depend on survey-derived starting values plus modest dynamics, so they
  agree partly by construction.
- No administrative validation yet (actual marriage counts, enrollment flows, rent series).
"""
    (ROOT / "docs").mkdir(exist_ok=True)
    (ROOT / "docs" / "VALIDATION.md").write_text(doc, encoding="utf-8")
    summary = {"generated": time.strftime("%Y-%m-%d"), "scale": a.scale, "seed": a.seed, "day": snap_day,
               "date": str(sim.cal.date(snap_day)), "counts": counts, "counts_benchmark": counts_b, "counts_behavior": counts_e,
               "counts_holdout": counts_h}
    OUT_JSON.write_text(json.dumps({"summary": summary, "rows": final, "institutional": inst, "trajectory": traj,
                                    "longitudinal": longi},
                                   default=lambda x: None if isinstance(x, float) and not np.isfinite(x) else float(x), indent=1),
                        encoding="utf-8")
    print(f"wrote docs/VALIDATION.md — {counts}")


if __name__ == "__main__":
    main()
