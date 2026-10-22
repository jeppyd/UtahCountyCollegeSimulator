"""The Psych 308 class survey (BYU, 2020) → aggregates for checking the model, in
ucsim/config/sources/psych308_2020.json.

    python -m ucsim.ingest.psych308            # needs data/raw/psych308_2020.xlsx (never committed)

947 BYU students who took Psych 308 between March 17 and December 14, 2020 (98% Latter-day Saints, 64% women, a third
freshmen, 37% psychology majors). Every response came during the COVID-19 pandemic, so this module sorts its measures:

- stable: family background, personality, religiosity, attitudes, marriage plans, study habits and other answers a
  pandemic shifts little (or that ask about high school) → held-out checks of the model's levels;
- pandemic: dating, loneliness, depression, life satisfaction, sleep, screen time, exercise, connectedness →
  diagnostics only, labelled as 2020 (the model simulates ordinary years);
- associations: within-person correlations (Spearman, pairwise) among Latter-day Saint respondents → pattern checks
  of the model's mechanisms (signs and rough sizes), which a pandemic shifts far less than levels.

Privacy: the same boundary as the other surveys — only aggregates, every stored cell has ≥ K_MIN respondents, no
respondent rows. Free-text columns (…_TEXT), the record id and the timestamps are never read. Undocumented recodes
(…_win, …cat, depressiondiag) are not used; minutes and hours are summarized by medians and 1%-trimmed means.
"""
from __future__ import annotations

import json
import warnings
from datetime import date
from pathlib import Path

import numpy as np
import polars as pl

from .priors import K_MIN
from .surveys import RAW_DIR

RAW = RAW_DIR / "psych308_2020.xlsx"
OUT = Path(__file__).resolve().parents[1] / "config" / "sources" / "psych308_2020.json"
NEVER = ("id", "StartDate", "duration", "month")          # identifiers and timing: never read

# column → (label, kind, codes) for the measures kept; codes as in the questionnaire
STABLE = {
    "parentmarital": "Parents divorced (1 = divorced)",
    "siblings": "Number of siblings",
    "mission": "Mission: 1 not going, 2 planning, 3 served",
    "belief": "Believes in God",
    "religimp": "Importance of religion (1–5)",
    "doubt": "Doubts in the last year (1 none … 4 many)",
    "pray_freq": "Private prayer frequency now (1 never … 6 several times a day)",
    "scripture_freq": "Scripture reading frequency now (1–6)",
    "relspir": "1 neither, 2 religious and spiritual, 3 religious not spiritual, 4 spiritual not religious",
    "political": "1 liberal, 2 moderate, 3 conservative",
    "same_sex": "Opposes legal same-sex marriage",
    "premarital": "Premarital sex: 1 always wrong … 4 not wrong at all",
    "getmarried": "Singles: how much they want to marry now (1–5)",
    "agemarried": "Married: age at marriage",
    "hoursstudy": "Study hours per week per credit hour",
    "cheat_any": "Cheated on an assignment or exam in the past year",
    "alcohol_any": "Drank alcohol in the past month",
    "extraverted": "TIPI-style item, 1–7", "conscientious": "1–7", "openness": "1–7", "agreeableness": "1–7",
    "emotionalstability": "1–7",
    "parentingstyle": "1 authoritative, 2 authoritarian, 3 permissive, 4 neglectful",
    "connected_family": "Connected to family now (1–5)",
    "connected_family_hs": "Connected to family in high school (1–5)",
    "dates_hs": "Dates per month in high school",
}
PANDEMIC = {
    "dates": "Dates per month (2020)", "lonely": "'I felt lonely' past week: 0 rarely … 3 most days",
    "cesd": "CES-D-10 total (0–30; 10+ = notable symptoms)", "lifesat": "Life satisfaction (0–10)",
    "selfesteem": "Self-esteem (mean of 3 items, 1–5)", "sleephrs": "Sleep hours a night", "socialmedia": "Social media minutes a day",
    "exercise": "Exercise hours a week", "videogames": "Video game hours a week", "workhrs": "Work hours a week",
    "connected_friends": "Connected to friends now (1–5)", "collgpa": "College GPA", "attendance": "Classes missed in the last 4 weeks",
}
# associations to compute: (a, b, words)
PAIRS = [
    ("lonely", "connected_friends", "lonelier ↔ less connected to friends"),
    ("lonely", "dates", "lonelier ↔ fewer dates (singles)"),
    ("lonely", "lifesat", "lonelier ↔ less satisfied with life"),
    ("cesd", "selfesteem", "more depressive symptoms ↔ lower self-esteem"),
    ("cesd", "sleephrs", "more depressive symptoms ↔ sleep"),
    ("cesd", "socialmedia", "more depressive symptoms ↔ social media time"),
    ("cesd", "exercise", "more depressive symptoms ↔ exercise"),
    ("extraverted", "dates", "more outgoing ↔ more dates (singles)"),
    ("extraverted", "lonely", "more outgoing ↔ less lonely"),
    ("conscientious", "collgpa", "more self-disciplined ↔ higher GPA"),
    ("hoursstudy", "collgpa", "more study ↔ higher GPA"),
    ("pray_freq", "doubt", "prays more ↔ fewer doubts"),
    ("religimp", "lifesat", "religion more important ↔ life satisfaction"),
    ("emotionalstability", "cesd", "calmer ↔ fewer depressive symptoms"),
    ("connected_family", "lifesat", "closer to family ↔ life satisfaction"),
    ("religimp", "premarital", "religion more important ↔ more disapproval of premarital sex (reversed scale)"),
]


def load() -> pl.DataFrame:
    if not RAW.exists():
        raise FileNotFoundError(f"{RAW} is missing (the owner's raw export; never committed)")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        df = pl.read_excel(RAW, sheet_name="Dataset", engine="openpyxl")
    keep = [c for c in df.columns if not c.endswith("_TEXT") and c not in NEVER and not c.endswith("_win")]
    df = df.select(keep)
    f = pl.col
    return df.with_columns(
        parentmarital=(f("parentmarital") == 0).cast(pl.Float64),          # survey: 0 divorced, 1 married
        pray_freq=f("relprivcurr_1"), scripture_freq=f("relprivcurr_2"),
        cheat_any=pl.when(f("behaviors_7").is_null() & f("behaviors_8").is_null()).then(None)
        .otherwise(((f("behaviors_7").fill_null(1) >= 2) | (f("behaviors_8").fill_null(1) >= 2)).cast(pl.Float64)),
        alcohol_any=pl.when(f("alcohol").is_null()).then(None).otherwise((f("alcohol") > 0).cast(pl.Float64)),
        connected_family=f("connected_1"), connected_friends=f("connected_2"), connected_family_hs=f("connectedhs_1"),
        dates_hs=f("dateshs"), lonely=f("depression_9"), cesd=f("depression"),
        same_sex=f("same_sex").cast(pl.Float64), belief=f("belief").cast(pl.Float64),
        lds=(f("religion") == 1), female=(f("gender") == 1), single=(f("relatstatus") == 1), married=(f("relatstatus") == 3),
    )


def _num(s: pl.Series) -> np.ndarray:
    return s.cast(pl.Float64).to_numpy()


def summary(x: np.ndarray) -> dict | None:
    x = x[np.isfinite(x)]
    if len(x) < K_MIN:
        return None
    lo, hi = np.quantile(x, [0.005, 0.995])
    t = x[(x >= lo) & (x <= hi)]
    return {"n": int(len(x)), "mean": round(float(t.mean()), 3), "median": round(float(np.median(x)), 3),
            "p25": round(float(np.quantile(x, 0.25)), 3), "p75": round(float(np.quantile(x, 0.75)), 3)}


def shares(x: np.ndarray) -> dict | None:
    """Share at each code, pooling codes with fewer than K_MIN answers into 'other' (and dropping it if still small)."""
    x = x[np.isfinite(x)]
    if len(x) < K_MIN:
        return None
    vals, cnt = np.unique(x, return_counts=True)
    out, other = {}, 0
    for v, c in zip(vals, cnt):
        if c >= K_MIN:
            out[str(int(v)) if float(v).is_integer() else str(v)] = round(float(c / len(x)), 4)
        else:
            other += c
    if other >= K_MIN:
        out["other"] = round(float(other / len(x)), 4)
    return {"n": int(len(x)), "shares": out}


def spearman(a: np.ndarray, b: np.ndarray) -> dict | None:
    m = np.isfinite(a) & np.isfinite(b)
    if m.sum() < 30:
        return None
    from scipy.stats import spearmanr
    r = spearmanr(a[m], b[m]).statistic
    return {"n": int(m.sum()), "r": round(float(r), 3)}


def build(write: bool = True) -> dict:
    df = load()
    lds = df.filter(pl.col("lds"))
    groups = {"all": lds, "men": lds.filter(~pl.col("female")), "women": lds.filter(pl.col("female"))}
    out = {"meta": {"source": "Psych 308 class survey, BYU, Mar 17 – Dec 14, 2020 (during the COVID-19 pandemic)",
                    "built": str(date.today()), "n": df.height, "n_lds": lds.height, "k_min": K_MIN,
                    "make_up": {"women": round(float(df["female"].mean()), 3),
                                "freshmen": round(float((df["year"] == 1).mean()), 3),
                                "psychology_majors": round(float((df["major"] == 1).mean()), 3),
                                "single": round(float(df["single"].mean()), 3), "married": round(float(df["married"].mean()), 3),
                                "age_median": float(df["age"].median())},
                    "note": "Latter-day Saint respondents only below. Stable = usable as held-out checks; pandemic = 2020 "
                            "levels, diagnostics only; associations = Spearman correlations (pairwise complete).",
                    "labels": {**STABLE, **PANDEMIC}},
           "stable": {}, "pandemic": {}, "associations": []}
    for section, cols in (("stable", STABLE), ("pandemic", PANDEMIC)):
        for c in cols:
            if c not in df.columns:
                continue
            for g, d in groups.items():
                if c == "getmarried":
                    d = d.filter(pl.col("single"))
                elif c == "agemarried":
                    d = d.filter(pl.col("married"))
                elif c == "dates":
                    d = d.filter(pl.col("single"))
                x = _num(d[c])
                cat = c in ("mission", "doubt", "relspir", "political", "premarital", "parentingstyle", "pray_freq", "scripture_freq",
                            "lonely", "religimp", "getmarried")
                s = shares(x) if cat or c in ("parentmarital", "same_sex", "cheat_any", "alcohol_any", "belief") else None
                m = summary(x)
                if m is None:
                    continue
                cell = {"summary": m}
                if s:
                    cell["shares"] = s["shares"]
                out[section].setdefault(c, {})[g] = cell
    for a, b, words in PAIRS:
        d = lds.filter(pl.col("single")) if "dates" in (a, b) else lds
        r = spearman(_num(d[a]), _num(d[b]))
        if r:
            out["associations"].append({"a": a, "b": b, "words": words, "who": "singles" if "dates" in (a, b) else "all", **r})
    if write:
        OUT.write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
    return out


if __name__ == "__main__":
    o = build()
    print(f"{o['meta']['n']} respondents ({o['meta']['n_lds']} LDS) → {OUT}")
    for k in ("stable", "pandemic"):
        print(k, ", ".join(o[k]))
    for r in o["associations"]:
        print(f"  r={r['r']:+.2f} (n={r['n']}) {r['words']}")
