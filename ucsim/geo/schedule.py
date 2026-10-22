"""BYU's real class schedule (owner-supplied campus data package) → ucsim/geo/data/byu_schedule.parquet and
byu_occupancy.parquet.

    python -m ucsim.geo.schedule            # needs data/external/byu_campus/ (never committed)

The package (byu-campus-data-01.zip, collected 2026-10-22 from BYU's public class schedule and BYU's public ArcGIS
layers; see its README) holds Fall 2026 (20265) and Winter 2027 (20271): every section with its enrollment, every
meeting with its room, days and times, and each building's scheduled student presence every 10 minutes. What is kept
here, per in-person section: the course (department and number), credits, enrollment, its main meeting's days, start
and end, and its room (building code, room, floor, point, seats) — no titles, no instructor names. And per building,
weekday and simulation block: the mean scheduled student presence, to check the simulated campus against.

A section with several meetings keeps its main one (most minutes a week); other meetings that start in the same
block of the day add their days (a Thursday lab after a Monday–Wednesday lecture in the morning). Online sections,
off-campus programs (Salt Lake, study abroad, Jerusalem, the Executive MBA), sections with nobody enrolled and
meetings with no days, time or known building are left out.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import polars as pl

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "data" / "external" / "byu_campus"
OUT = Path(__file__).resolve().parent / "data" / "byu_schedule.parquet"
OCC = Path(__file__).resolve().parent / "data" / "byu_occupancy.parquet"
DEPTS = Path(__file__).resolve().parents[1] / "config" / "places" / "byu_departments.yaml"
TERMS = {"20265": "Fall", "20271": "Winter"}
DAY_BITS = {"M": 0, "T": 1, "W": 2, "R": 3, "F": 4, "S": 5, "U": 6}
WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")


def day_mask(days: str | None) -> int:
    return sum(1 << DAY_BITS[c] for c in set(days or "") if c in DAY_BITS)


def departments() -> dict:
    """Department → study area (campus.yaml `areas` names) or "religion"; anything not listed is Humanities."""
    import yaml
    cfg = yaml.safe_load(DEPTS.read_text())
    return {d: area for area, ds in cfg["areas"].items() for d in ds}


def _csv(name: str) -> pl.DataFrame:
    return pl.read_csv(SRC / name, infer_schema_length=0, encoding="utf8-lossy")


def build_sections() -> pl.DataFrame:
    from ..engine import clock
    S = _csv("sections.csv")
    S = S.rename({S.columns[0]: S.columns[0].lstrip("﻿")})
    S = S.filter(pl.col("yearterm").is_in(list(TERMS)) & pl.col("section_type").is_in(["DAY", "EVENING"])
                 & pl.col("mode").is_in(["Classroom", "Blended"]))
    S = S.with_columns(pl.col("enrollment").cast(pl.Int32, strict=False).fill_null(0),
                       pl.col("credit_hours").cast(pl.Float32, strict=False).fill_null(0.0))
    S = S.filter(pl.col("enrollment") > 0).select("section_id", "yearterm", "department", "catalog_number",
                                                  "credit_hours", "enrollment")
    M = _csv("meetings.csv")
    M = M.rename({M.columns[0]: M.columns[0].lstrip("﻿")})
    M = M.with_columns(pl.col("start_minute").cast(pl.Int32, strict=False), pl.col("end_minute").cast(pl.Int32, strict=False),
                       pl.col("latitude").cast(pl.Float64, strict=False), pl.col("longitude").cast(pl.Float64, strict=False),
                       pl.col("room_capacity").cast(pl.Int32, strict=False))
    M = M.filter(pl.col("days").is_not_null() & pl.col("start_minute").is_not_null() & pl.col("end_minute").is_not_null()
                 & pl.col("latitude").is_not_null() & pl.col("building").is_not_null())
    M = M.with_columns(pl.col("days").map_elements(day_mask, return_dtype=pl.Int32).alias("mask"))
    M = M.filter((pl.col("mask") & 0b11111) > 0)                         # weekday classes (Saturday-only left out)
    M = M.with_columns(((pl.col("end_minute") - pl.col("start_minute")) * pl.col("mask").map_elements(
        lambda m: m.bit_count(), return_dtype=pl.Int32)).alias("weekly"),
        pl.Series("block", clock.block_of(np.maximum(M["start_minute"].to_numpy(), clock.DAY_START)).astype(np.int32)))
    M = M.filter(pl.col("block") >= 0)
    R = _csv("rooms.csv")
    R = R.rename({R.columns[0]: R.columns[0].lstrip("﻿")})
    R = R.select("yearterm", "building", "room", pl.col("floor").cast(pl.Int32, strict=False)).unique(["yearterm", "building", "room"])
    M = M.join(R, on=["yearterm", "building", "room"], how="left")
    main = M.sort(["section_id", "weekly", "meeting_id"], descending=[False, True, False]).unique("section_id", keep="first")
    same_block = M.join(main.select("section_id", pl.col("block").alias("b0")), on="section_id").filter(pl.col("block") == pl.col("b0"))
    days = same_block.group_by("section_id").agg(pl.col("mask").bitwise_or().alias("days"))
    main = main.drop("mask", "days").join(days, on="section_id")
    D = S.join(main.select("section_id", "days", pl.col("start_minute").alias("start"), pl.col("end_minute").alias("end"),
                           "building", "room", "floor", pl.col("longitude").alias("lon"), pl.col("latitude").alias("lat"),
                           pl.col("room_capacity").alias("seats")), on="section_id")
    dep = departments()
    lvl = D["catalog_number"].str.extract(r"(\d+)").cast(pl.Int32, strict=False).fill_null(0)
    D = D.with_columns(pl.col("yearterm").replace_strict(TERMS).alias("term"),
                       pl.col("department").replace_strict(dep, default="Humanities").alias("area"),
                       lvl.alias("level"),
                       ((pl.col("floor").fill_null(1) - 1).clip(0, None)).cast(pl.Int8).alias("floor"),   # GIS floors count from 1
                       pl.col("lon").round(6), pl.col("lat").round(6))
    return D.select("term", pl.col("department").alias("dept"), pl.col("catalog_number").alias("catalog"), "level",
                    pl.col("credit_hours").alias("credits"), "enrollment", pl.col("days").cast(pl.UInt8),
                    pl.col("start").cast(pl.Int16), pl.col("end").cast(pl.Int16), "building", "room", "floor", "lon", "lat",
                    "seats", "area").sort(["term", "dept", "catalog", "start"])


def build_occupancy() -> pl.DataFrame:
    """Mean scheduled student presence per building, term, weekday and simulation block."""
    from ..engine import clock
    O = _csv("building_occupancy.csv")
    O = O.rename({O.columns[0]: O.columns[0].lstrip("﻿")})
    O = O.filter(pl.col("yearterm").is_in(list(TERMS)))
    hm = O["slot_start"].str.split_exact(":", 1)
    minute = hm.struct.field("field_0").cast(pl.Int32) * 60 + hm.struct.field("field_1").cast(pl.Int32)
    O = O.with_columns(pl.Series("block", clock.block_of(minute.to_numpy()).astype(np.int32)),
                       pl.col("weekday").replace_strict({d: i for i, d in enumerate(WEEKDAYS)}, return_dtype=pl.Int8).alias("wd"),
                       pl.col("estimated_people").cast(pl.Float64))
    O = O.filter(pl.col("block") >= 0)
    return (O.group_by("yearterm", "building", "wd", "block").agg(pl.col("estimated_people").mean().round(1).alias("people"))
            .with_columns(pl.col("yearterm").replace_strict(TERMS).alias("term"))
            .select("term", "building", "wd", pl.col("block").cast(pl.Int8), "people")
            .filter(pl.col("people") > 0).sort(["term", "building", "wd", "block"]))


_CACHE: dict = {}


def load() -> pl.DataFrame | None:
    """The committed schedule (None when absent: then classes are drawn, not real)."""
    if "s" not in _CACHE:
        _CACHE["s"] = pl.read_parquet(OUT) if OUT.exists() else None
    return _CACHE["s"]


def occupancy() -> pl.DataFrame | None:
    if "o" not in _CACHE:
        _CACHE["o"] = pl.read_parquet(OCC) if OCC.exists() else None
    return _CACHE["o"]


def main():
    D = build_sections()
    D.write_parquet(OUT, compression="zstd")
    O = build_occupancy()
    O.write_parquet(OCC, compression="zstd")
    for t in TERMS.values():
        d = D.filter(pl.col("term") == t)
        print(f"{t}: {d.height} sections, {int(d['enrollment'].sum())} seats filled, "
              f"{d['building'].n_unique()} buildings; areas: {dict(d.group_by('area').agg(pl.col('enrollment').sum()).iter_rows())}")
    print(f"occupancy rows: {O.height}; {OUT.stat().st_size // 1024} KB + {OCC.stat().st_size // 1024} KB")


if __name__ == "__main__":
    main()
