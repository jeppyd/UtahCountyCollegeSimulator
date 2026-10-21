"""The model against the Psych 308 class survey (BYU, 2020; ucsim/ingest/psych308.py → config/sources/psych308_2020.json).

Compared among the simulated BYU students who are Latter-day Saints and present (the survey's respondents are 98%
Latter-day Saint BYU students). Three kinds of rows (scripts/validate.py adds them to the report):

- holdout: stable levels the model was never tuned to (family background, missions, marriage age, attitudes);
- diagnostic: 2020 pandemic-era levels (dates, sleep, screen time, work, GPA, life satisfaction) — the model simulates
  ordinary years, so these show the direction of a difference, not a failure;
- pattern: within-person associations (Spearman r) — do the model's mechanisms tie the same things together, in the
  same direction and roughly as strongly? The survey's scales differ from the model's, so a sign flips where a scale
  runs the other way (survey doubts ↔ model certainty; depressive symptoms ↔ mood; emotional stability ↔ neuroticism).
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

SRC = Path(__file__).resolve().parents[1] / "config" / "sources" / "psych308_2020.json"

# survey association (a, b) → (model a, model b, sign: model r × sign is compared with the survey's r, singles only?)
PAIR_MAP = {
    ("lonely", "connected_friends"): ("loneliness", "n_close_friends", 1, False),
    ("lonely", "dates"): ("loneliness", "dates_30d", 1, True),
    ("lonely", "lifesat"): ("loneliness", "life_satisfaction", 1, False),
    ("cesd", "selfesteem"): ("mood", "self_esteem", -1, False),
    ("cesd", "sleephrs"): ("mood", "sleep_hours", -1, False),
    ("cesd", "socialmedia"): ("mood", "social_media_hours", -1, False),
    ("cesd", "exercise"): ("mood", "workouts_week", -1, False),
    ("extraverted", "dates"): ("extraversion", "dates_30d", 1, True),
    ("extraverted", "lonely"): ("extraversion", "loneliness", 1, False),
    ("conscientious", "collgpa"): ("conscientiousness", "gpa", 1, False),
    ("hoursstudy", "collgpa"): ("study_hours", "gpa", 1, False),
    ("pray_freq", "doubt"): ("private_practice", "faith_certainty", -1, False),
    ("religimp", "lifesat"): ("cares_faith", "life_satisfaction", 1, False),
    ("emotionalstability", "cesd"): ("neuroticism", "mood", 1, False),
    ("connected_family", "lifesat"): ("family_closeness", "life_satisfaction", 1, False),
    ("religimp", "premarital"): ("cares_faith", "chastity_commitment", -1, False),
}


def _status(diff: float, tol: float) -> str:
    if not np.isfinite(diff):
        return "n/a"
    return "pass" if abs(diff) <= tol else "warn" if abs(diff) <= 2 * tol else "fail"


def _cohort(sim):
    P = sim.w.P
    n = P.n
    return (P["present"][:n].astype(bool) & P["enrolled"][:n].astype(bool) & (P["school"][:n] == P.code("school", "BYU"))
            & P["lds_member"][:n].astype(bool))


def rows(sim) -> list[dict]:
    if not SRC.exists():
        return []
    src = json.loads(SRC.read_text(encoding="utf-8"))
    P = sim.w.P
    n = P.n
    base = _cohort(sim)
    men, women = base & P.is_("sex", "M")[:n], base & P.is_("sex", "F")[:n]
    single = ~P.isin("rel_status", ["married", "engaged", "dating"])[:n]
    married = P.is_("rel_status", "married")[:n]
    out = []

    def add(table, group, kind, target, got, tol, n_sim, n_band, note=""):
        out.append({"table": f"p308_{table}", "group": group, "var": table, "kind": kind, "target": float(target), "sim": float(got),
                    "diff": float(got - target), "tol": float(tol), "n_sim": int(n_sim), "n_band": f"Psych 308 n={n_band}",
                    "status": _status(got - target, tol), "holdout": kind == "holdout", "note": note})

    def cell(sec, var, grp="all"):
        return src[sec].get(var, {}).get(grp)

    def share(sec, var, codes, grp="all"):
        c = cell(sec, var, grp)
        if not c or "shares" not in c:
            return None, 0
        return sum(c["shares"].get(str(k), 0.0) for k in codes), c["summary"]["n"]

    # ---- held-out levels (stable)
    c = cell("stable", "parentmarital")
    if c and base.sum() >= 25:
        add("parents_divorced", "LDS BYU students", "holdout", c["summary"]["mean"], P["parents_divorced"][:n][base].mean(), 0.04, base.sum(), c["summary"]["n"])
    c = cell("stable", "siblings")
    if c:
        add("siblings", "LDS BYU students", "holdout", c["summary"]["mean"], P["n_siblings"][:n][base].astype(float).mean(), 0.5, base.sum(), c["summary"]["n"])
    ms = P["mission_status"][:n]
    served = P.isin("mission_status", ["returned", "early_returned"])[:n]
    for grp, m in (("men", men), ("women", women)):
        t, nb = share("stable", "mission", [3], grp)
        if t is not None and m.sum() >= 25:
            add("mission_served", grp, "holdout", t, served[m].mean(), 0.08, m.sum(), nb)
    for grp, m in (("men", men & married), ("women", women & married)):
        c = cell("stable", "agemarried", grp)
        if c and m.sum() >= 25:
            x = P["age_at_marriage"][:n][m].astype(float)
            add("age_at_marriage", f"married {grp}", "holdout", c["summary"]["mean"], np.nanmean(x), 1.0, m.sum(), c["summary"]["n"])
    t, nb = share("stable", "political", [3])
    if t is not None:
        add("conservative_share", "LDS BYU students", "holdout", t, (P["politics"][:n][base] >= 3).mean(), 0.08, base.sum(), nb,
            "model: conservative or very conservative")
    t, nb = share("stable", "political", [1])
    if t is not None:
        add("liberal_share", "LDS BYU students", "holdout", t, (P["politics"][:n][base] <= 1).mean(), 0.06, base.sum(), nb)
    c = cell("stable", "same_sex")
    if c:
        x = P["att_gay_marriage_legal"][:n][base].astype(float)
        add("opposes_legal_ssm", "LDS BYU students", "holdout", c["summary"]["mean"], float(((x <= 1) + 0.5 * (x == 2)).mean()), 0.08,
            base.sum(), c["summary"]["n"], "model: disagree with legal SSM (neutral counted half)")
    c = cell("stable", "alcohol_any")
    if c:
        add("drank_past_month", "LDS BYU students", "diagnostic", c["summary"]["mean"], (P["alcohol"][:n][base] >= 2).mean(), 0.03,
            base.sum(), c["summary"]["n"], "model: drinks occasionally or often (no past-month measure)")
    c = cell("stable", "cheat_any")
    if c:
        add("cheated_past_year", "LDS BYU students", "diagnostic", c["summary"]["mean"], (P["cheats_school"][:n][base] >= 1).mean(), 0.08,
            base.sum(), c["summary"]["n"], "model: any academic dishonesty habit")
    # ---- pandemic-era levels (diagnostic)
    for grp, m in (("men", men & single), ("women", women & single)):
        c = cell("pandemic", "dates", grp)
        if c and m.sum() >= 25:
            add("dates_month_singles_2020", f"single {grp}", "diagnostic", c["summary"]["mean"], P["dates_30d"][:n][m].astype(float).mean(),
                0.6, m.sum(), c["summary"]["n"], "2020 pandemic level")
    for var, model, scale, tol in (("sleephrs", "sleep_hours", 1.0, 0.4), ("socialmedia", "social_media_hours", 1 / 60, 0.3),
                                   ("workhrs", "work_hours", 1.0, 3.0), ("collgpa", "gpa", 1.0, 0.12), ("lifesat", "life_satisfaction", 1.0, 0.6)):
        c = cell("pandemic", var)
        if c:
            add(f"{var}_2020", "LDS BYU students", "diagnostic", c["summary"]["mean"] * scale, np.nanmean(P[model][:n][base].astype(float)),
                tol, base.sum(), c["summary"]["n"], "2020 pandemic level")
    # ---- associations (pattern)
    from scipy.stats import spearmanr
    for a in src.get("associations", []):
        mp = PAIR_MAP.get((a["a"], a["b"]))
        if not mp:
            continue
        ma, mb, sign, only_single = mp
        m = base & single if only_single else base
        x, y = P[ma][:n][m].astype(float), P[mb][:n][m].astype(float)
        ok = np.isfinite(x) & np.isfinite(y)
        if ok.sum() < 30 or np.std(x[ok]) == 0 or np.std(y[ok]) == 0:
            continue
        r = float(spearmanr(x[ok], y[ok]).statistic) * sign
        tol = max(0.12, 0.35 * abs(a["r"]))
        st = _status(r - a["r"], tol)
        if abs(a["r"]) >= 0.1 and np.sign(r) != np.sign(a["r"]) and abs(r) >= 0.05:
            st = "fail"                                   # the opposite direction is a failure whatever the distance
        out.append({"table": "p308_assoc", "group": a["words"], "var": f"{ma}~{mb}", "kind": "pattern", "target": a["r"], "sim": round(r, 3),
                    "diff": round(r - a["r"], 3), "tol": round(tol, 3), "n_sim": int(ok.sum()), "n_band": f"Psych 308 n={a['n']}",
                    "status": st, "holdout": True, "note": f"model {ma} ~ {mb}" + (" (sign flipped: scales run opposite ways)" if sign < 0 else "")})
    return out
