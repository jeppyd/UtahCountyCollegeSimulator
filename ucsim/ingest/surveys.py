"""Load raw LDStats survey exports and harmonize them into tidy respondent tables.

The output of this module is respondent-level and therefore *local only*
(written to data/derived/, which is gitignored).  `ucsim.ingest.priors` turns
these tables into aggregate, privacy-preserving priors that are committed.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import polars as pl

from .survey_spec import REL_MAP, SPEC

ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = ROOT / "data" / "raw"
DERIVED_DIR = ROOT / "data" / "derived"

US_STATES = {
    "Alabama", "Alaska", "Arizona", "Arkansas", "California", "Colorado", "Connecticut", "Delaware", "Florida",
    "Georgia", "Hawaii", "Idaho", "Illinois", "Indiana", "Iowa", "Kansas", "Kentucky", "Louisiana", "Maine",
    "Maryland", "Massachusetts", "Michigan", "Minnesota", "Mississippi", "Missouri", "Montana", "Nebraska",
    "Nevada", "New Hampshire", "New Jersey", "New Mexico", "New York", "North Carolina", "North Dakota", "Ohio",
    "Oklahoma", "Oregon", "Pennsylvania", "Rhode Island", "South Carolina", "South Dakota", "Tennessee", "Texas",
    "Utah", "Vermont", "Virginia", "Washington", "West Virginia", "Wisconsin", "Wyoming", "District of Columbia",
}


def _norm(v) -> str:
    return str(v).strip().lower().replace("’", "'")


def _code_value(vtype: str, opts: dict, raw):
    """Convert one raw answer to its harmonized value (or dict of flags for multi)."""
    if raw is None or (isinstance(raw, str) and raw.strip() == ""):
        return None
    if vtype == "num":
        try:
            x = float(raw)
        except (TypeError, ValueError):
            return None
        if not np.isfinite(x):
            return None
        lo, hi = opts["clip"]
        if x < lo or x > hi * 3:  # implausible -> missing; mild overshoot -> clipped
            return None
        return float(min(max(x, lo), hi))
    if vtype == "ord":
        levels = opts["levels"]
        key = _norm(raw)
        return levels.index(key) if key in levels else None
    if vtype == "bin":
        return 1 if _norm(raw) in opts["yes"] else 0
    if vtype == "cat":
        return str(raw).strip()
    if vtype == "multi":
        selected = raw if isinstance(raw, list) else [s for s in str(raw).split(",")]
        sel = {str(s).strip() for s in selected}
        return {flag: int(label in sel) for label, flag in opts["flags"].items()}
    raise ValueError(vtype)


def raw_path(slug: str) -> Path | None:
    """The survey's raw export: the JSON export named in the spec, else a Qualtrics CSV export `<slug>*.csv`."""
    p = RAW_DIR / SPEC[slug]["file"]
    if p.exists():
        return p
    csvs = sorted(RAW_DIR.glob(f"{slug}*.csv"))
    return csvs[-1] if csvs else None


def _csv_responses(path: Path) -> list[dict]:
    """Read a CSV export into the JSON export's shape: answers keyed by column position (`v000`, `v001`, …), which is
    how the spec's question ids were assigned. Qualtrics' extra header rows (question text, ImportId) and survey
    previews are skipped; `Finished` (when present) says whether a response was completed."""
    import csv
    with path.open(newline="", encoding="utf-8-sig") as f:
        rows = list(csv.reader(f))
    header = rows[0]
    finished = header.index("Finished") if "Finished" in header else None
    status = header.index("Status") if "Status" in header else None
    out = []
    for r in rows[1:]:
        if any(c.startswith('{"ImportId"') for c in r[:3]) or (finished is not None and r[finished] == "Finished"):
            continue                                   # Qualtrics header rows 2–3
        if status is not None and r[status] == "Survey Preview":
            continue
        done = True if finished is None else r[finished].strip().lower() == "true"
        out.append({"completed": done,
                    "answers": [{"question_id": f"v{j:03d}", "answer_value": v} for j, v in enumerate(r) if v.strip() != ""]})
    return out


def load_survey(slug: str) -> pl.DataFrame:
    spec = SPEC[slug]
    path = raw_path(slug)
    if path is None:
        raise FileNotFoundError(f"no raw export for {slug} in {RAW_DIR}")
    responses = _csv_responses(path) if path.suffix == ".csv" else json.loads(path.read_text(encoding="utf-8"))["responses"]
    rows = []
    for resp in responses:
        if not resp.get("completed", True):
            continue
        answers = {a["question_id"]: a["answer_value"] for a in resp["answers"]}
        row: dict = {}
        for qid, (name, vtype, opts) in spec["vars"].items():
            val = _code_value(vtype, opts, answers.get(qid))
            if vtype == "multi":
                flags = val if isinstance(val, dict) else None
                for flag in opts["flags"].values():
                    # A multi-select left blank is ambiguous (none vs skipped); only code when answered.
                    row[flag] = None if flags is None else flags[flag]
            else:
                row[name] = val
        rows.append(row)
    df = pl.DataFrame(rows, infer_schema_length=None)
    return _derive_bridge(slug, df)


def _derive_bridge(slug: str, df: pl.DataFrame) -> pl.DataFrame:
    """Create the shared 'bridge' variables used to link surveys."""
    cols = df.columns
    sex = df["sex_raw"].map_elements(
        lambda s: {"male": "M", "female": "F"}.get(_norm(s)), return_dtype=pl.Utf8
    )
    rel = df["rel_raw"].map_elements(lambda s: REL_MAP.get(_norm(s)), return_dtype=pl.Utf8)
    out = df.with_columns(sex=sex, rel=rel)

    # LDS membership
    if slug == "provostats":
        lds = out["lds_member"]
    elif slug == "culture-lifestyle":
        lds = out["membership"].map_elements(lambda s: int(_norm(s) == "current member"), return_dtype=pl.Int64)
    else:
        lds = out["religion"].map_elements(lambda s: int(_norm(s).startswith("church of jesus")), return_dtype=pl.Int64)
    out = out.with_columns(lds=lds)

    # Current school (best available proxy)
    if slug == "provostats":
        school = pl.when(pl.col("in_college") == 0).then(pl.lit("none")).otherwise(
            pl.col("school").replace_strict({"BYU": "BYU", "UVU": "UVU", "Other": "other"}, default="other"))
    else:
        school = (pl.when(pl.col("att_byu") == 1).then(pl.lit("BYU"))
                  .when(pl.col("att_uvu") == 1).then(pl.lit("UVU"))
                  .when(pl.col("att_byu").is_null()).then(pl.lit(None))
                  .otherwise(pl.lit("other")))
    out = out.with_columns(school_proxy=school)

    # Lives in Provo/Orem
    if "city" in cols:
        out = out.with_columns(local=pl.col("city").is_in(["Provo", "Orem"]).cast(pl.Int64))
    elif "local_provo_orem" in cols:
        out = out.with_columns(local=pl.col("local_provo_orem"))

    if "origin" in cols:
        out = out.with_columns(
            origin_utah=(pl.col("origin") == "Utah").cast(pl.Int64),
            origin_international=(~pl.col("origin").is_in(list(US_STATES)) & pl.col("origin").is_not_null()).cast(pl.Int64),
        )
    if "mission_place" in cols:
        out = out.with_columns(
            mission_foreign=pl.when(pl.col("mission_place").is_null()).then(None)
            .otherwise((~pl.col("mission_place").is_in(list(US_STATES))).cast(pl.Int64))
        )
    orient = out["orientation"].map_elements(
        lambda s: {"straight": "straight", "bisexual": "bi", "pansexual": "bi", "gay": "gay",
                   "asexual": "asexual"}.get(_norm(s), "other"), return_dtype=pl.Utf8)
    out = out.with_columns(orientation=orient)

    rel_level = pl.col("rel").replace_strict(
        {"single": 0, "divorced": 0, "dating": 1, "engaged": 2, "married": 3}, default=None, return_dtype=pl.Int64)
    out = out.with_columns(rel_level=rel_level,
                           married=(pl.col("rel") == "married").cast(pl.Int64),
                           male=(pl.col("sex") == "M").cast(pl.Int64))
    # Activity is only meaningful for members; non-members get null.
    if "activity" in out.columns:
        out = out.with_columns(activity=pl.when(pl.col("lds") == 1).then(pl.col("activity")).otherwise(None))
    drop = [c for c in ("sex_raw", "rel_raw", "religion", "membership", "school") if c in out.columns]
    out = out.drop(drop)
    return out.with_columns(survey=pl.lit(slug))


def load_all(write: bool = True) -> dict[str, pl.DataFrame]:
    frames = {}
    for slug in SPEC:
        if raw_path(slug) is None:
            continue
        df = load_survey(slug)
        frames[slug] = df
        if write:
            DERIVED_DIR.mkdir(parents=True, exist_ok=True)
            df.write_parquet(DERIVED_DIR / f"{slug}.parquet")
    return frames


if __name__ == "__main__":
    for slug, df in load_all().items():
        print(slug, df.shape)
