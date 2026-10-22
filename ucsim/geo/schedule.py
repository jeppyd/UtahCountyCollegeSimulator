"""BYU's and UVU's real class schedules (owner-supplied research packages) → ucsim/geo/data/byu_schedule.parquet,
byu_occupancy.parquet and uvu_schedule.parquet.

    python -m ucsim.geo.schedule            # needs data/external/byu_campus/ and/or uvu_campus/ (never committed)

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

UVU (provo-orem-student-life-research-2026-10-21.zip, its `uvu/` folder copied to data/external/uvu_campus/; collected
2026-10-21 from UVU's public Banner class search) holds Fall 2026 (202640): every section with its subject, course
number, credits, mode and enrollment, every meeting with building, room, days and HHMM times, and 17 main-campus
building centres matched to OpenStreetMap outlines (estimates, not surveyed points). Kept: in-person sections in those
17 buildings, in the same columns as BYU's. Left out: online, livestream and to-be-arranged sections, concurrent
enrollment at high schools, other sites (Lehi, Heber, the airport) and the main-campus buildings the package has no
point for (Pope Science, McKay Education, Health Professions, Digital Transformation): 53% of the in-person seats are
kept (most of the rest are high-school concurrent enrollment). UVU publishes no room floors; a room's floor comes from
its number (1xx the ground floor, 2xx the next; 0xx, the lower level, counts as the ground floor; a building whose
lowest room is 3xx or higher — Gunther Technology, Sparks, Computer Science, the Noorda Center — numbers from its
ground floor up): an estimate. Each building's room points are its centre.
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
UVU_SRC = ROOT / "data" / "external" / "uvu_campus"
UVU_OUT = Path(__file__).resolve().parent / "data" / "uvu_schedule.parquet"
UVU_DEPTS = Path(__file__).resolve().parents[1] / "config" / "places" / "uvu_departments.yaml"
UVU_TERMS = {"202640": "Fall"}
UVU_IN_PERSON = ("Face to Face", "Face to Face Lab", "Face to Face and Online", "Face to Face and Livestream")
DAY_BITS = {"M": 0, "T": 1, "W": 2, "R": 3, "F": 4, "S": 5, "U": 6}
WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")


def day_mask(days: str | None) -> int:
    return sum(1 << DAY_BITS[c] for c in set(days or "") if c in DAY_BITS)


def departments(path: Path = DEPTS) -> dict:
    """Department → study area (campus.yaml `areas` names) or "religion"; anything not listed is Humanities."""
    import yaml
    cfg = yaml.safe_load(path.read_text())
    return {d: area for area, ds in cfg["areas"].items() for d in ds}


def _csv(name: str, src: Path = SRC) -> pl.DataFrame:
    D = pl.read_csv(src / name, infer_schema_length=0, encoding="utf8-lossy")
    return D.rename({D.columns[0]: D.columns[0].lstrip("\ufeff")})


def _main_meeting(M: pl.DataFrame) -> pl.DataFrame:
    """One meeting per section: the one with the most minutes a week, with the days of the section's other meetings
    that start in the same block of the day. M needs section_id, meeting_id, days (letters), start_minute, end_minute."""
    from ..engine import clock
    M = M.with_columns(pl.col("days").map_elements(day_mask, return_dtype=pl.Int32).alias("mask"))
    M = M.filter((pl.col("mask") & 0b11111) > 0)                         # weekday classes (Saturday-only left out)
    M = M.with_columns(((pl.col("end_minute") - pl.col("start_minute")) * pl.col("mask").map_elements(
        lambda m: m.bit_count(), return_dtype=pl.Int32)).alias("weekly"),
        pl.Series("block", clock.block_of(np.maximum(M["start_minute"].to_numpy(), clock.DAY_START)).astype(np.int32)))
    M = M.filter(pl.col("block") >= 0)
    main = M.sort(["section_id", "weekly", "meeting_id"], descending=[False, True, False]).unique("section_id", keep="first")
    same_block = M.join(main.select("section_id", pl.col("block").alias("b0")), on="section_id").filter(pl.col("block") == pl.col("b0"))
    days = same_block.group_by("section_id").agg(pl.col("mask").bitwise_or().alias("days"))
    return main.drop("mask", "days").join(days, on="section_id")


def build_sections() -> pl.DataFrame:
    S = _csv("sections.csv")
    S = S.filter(pl.col("yearterm").is_in(list(TERMS)) & pl.col("section_type").is_in(["DAY", "EVENING"])
                 & pl.col("mode").is_in(["Classroom", "Blended"]))
    S = S.with_columns(pl.col("enrollment").cast(pl.Int32, strict=False).fill_null(0),
                       pl.col("credit_hours").cast(pl.Float32, strict=False).fill_null(0.0))
    S = S.filter(pl.col("enrollment") > 0).select("section_id", "yearterm", "department", "catalog_number",
                                                  "credit_hours", "enrollment")
    M = _csv("meetings.csv")
    M = M.with_columns(pl.col("start_minute").cast(pl.Int32, strict=False), pl.col("end_minute").cast(pl.Int32, strict=False),
                       pl.col("latitude").cast(pl.Float64, strict=False), pl.col("longitude").cast(pl.Float64, strict=False),
                       pl.col("room_capacity").cast(pl.Int32, strict=False))
    M = M.filter(pl.col("days").is_not_null() & pl.col("start_minute").is_not_null() & pl.col("end_minute").is_not_null()
                 & pl.col("latitude").is_not_null() & pl.col("building").is_not_null())
    R = _csv("rooms.csv")
    R = R.select("yearterm", "building", "room", pl.col("floor").cast(pl.Int32, strict=False)).unique(["yearterm", "building", "room"])
    M = M.join(R, on=["yearterm", "building", "room"], how="left")
    main = _main_meeting(M)
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
    return _columns(D)


def _columns(D: pl.DataFrame) -> pl.DataFrame:
    return D.select("term", pl.col("department").alias("dept"), pl.col("catalog_number").alias("catalog"), "level",
                    pl.col("credit_hours").alias("credits"), "enrollment", pl.col("days").cast(pl.UInt8),
                    pl.col("start").cast(pl.Int16), pl.col("end").cast(pl.Int16), "building", "room", "floor", "lon", "lat",
                    pl.col("seats").cast(pl.Int32), "area").sort(["term", "dept", "catalog", "start"])


def _hhmm(col: str) -> pl.Expr:
    return pl.col(col).str.slice(0, 2).cast(pl.Int32, strict=False) * 60 + pl.col(col).str.slice(2, 2).cast(pl.Int32, strict=False)


def _storey(room) -> int:
    digits = "".join(c for c in str(room) if c.isdigit())
    return int(digits[0]) if len(digits) >= 3 else 1


def uvu_floors(buildings: list, rooms: list) -> list:
    """UVU rooms' floors (0 = ground) from their numbers: the first digit is the storey (0xx counts as the ground);
    in a building whose lowest room starts at 3 or more, that lowest number is the ground floor."""
    st = [_storey(r) for r in rooms]
    low: dict = {}
    for b, k in zip(buildings, st):
        low[b] = min(low.get(b, 9), k)
    return [max(k - (low[b] if low[b] >= 3 else 1), 0) for b, k in zip(buildings, st)]


def build_uvu_sections() -> pl.DataFrame:
    S = _csv("sections.csv", UVU_SRC)
    S = S.filter(pl.col("term").is_in(list(UVU_TERMS)) & pl.col("mode").is_in(list(UVU_IN_PERSON)))
    S = S.with_columns(pl.col("enrollment").cast(pl.Int32, strict=False).fill_null(0),
                       pl.col("class_size").cast(pl.Int32, strict=False).alias("seats"),
                       pl.col("credit_hours").str.extract(r"([\d.]+)").cast(pl.Float32, strict=False).fill_null(0.0))   # "1-3": the low end
    S = S.filter(pl.col("enrollment") > 0)
    B = _csv("buildings.csv", UVU_SRC).with_columns(pl.col("longitude").cast(pl.Float64, strict=False),
                                                    pl.col("latitude").cast(pl.Float64, strict=False))
    B = B.filter(pl.col("longitude").is_not_null() & pl.col("latitude").is_not_null())
    M = _csv("meetings.csv", UVU_SRC).with_row_index("meeting_id")
    M = M.with_columns(_hhmm("begin_time").alias("start_minute"), _hhmm("end_time").alias("end_minute"))
    M = M.filter(pl.col("days").is_not_null() & pl.col("start_minute").is_not_null() & pl.col("end_minute").is_not_null()
                 & (pl.col("end_minute") > pl.col("start_minute")))
    M = M.join(B.select("building", pl.col("longitude").alias("lon"), pl.col("latitude").alias("lat")), on="building")
    main = _main_meeting(M)
    D = S.join(main.select("section_id", "days", pl.col("start_minute").alias("start"), pl.col("end_minute").alias("end"),
                           "building", "room", "lon", "lat"), on="section_id")
    dep = departments(UVU_DEPTS)
    num = D["catalog_number"].str.extract(r"(\d+)").cast(pl.Int32, strict=False).fill_null(0)
    D = D.with_columns(pl.col("term").replace_strict(UVU_TERMS),
                       pl.col("department").replace_strict(dep, default="Humanities").alias("area"),
                       (num // 10).alias("level"),                    # 1010 → 101, on BYU's scale (GE < 300, graduate 500+)
                       pl.Series("floor", uvu_floors(D["building"].to_list(), D["room"].to_list()), pl.Int8),
                       pl.col("lon").round(6), pl.col("lat").round(6))
    return _columns(D)


def raise_uvu_floors(D: pl.DataFrame):
    """UVU's buildings get the floors their rooms are on (the building layer mostly guesses one storey there)."""
    from ..engine import places
    from .buildings import OUT
    from .homes import raise_floors
    if not places.available():
        return
    pts = D.unique(["building", "floor"])
    _, _, row = places.settle(pts["lon"].to_numpy(), pts["lat"].to_numpy())
    ids = pl.read_parquet(OUT, columns=["building_id"])["building_id"].to_numpy()
    ok = row >= 0
    raise_floors(pl.DataFrame({"building_id": ids[row[ok]], "floor": pts["floor"].to_numpy()[ok].astype(np.int64)}))


def build_occupancy() -> pl.DataFrame:
    """Mean scheduled student presence per building, term, weekday and simulation block."""
    from ..engine import clock
    O = _csv("building_occupancy.csv")
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


def load(school: str = "BYU") -> pl.DataFrame | None:
    """A school's committed schedule (None when absent: then classes are drawn, not real)."""
    if school not in _CACHE:
        path = OUT if school == "BYU" else UVU_OUT
        _CACHE[school] = pl.read_parquet(path) if path.exists() else None
    return _CACHE[school]


def occupancy() -> pl.DataFrame | None:
    if "o" not in _CACHE:
        _CACHE["o"] = pl.read_parquet(OCC) if OCC.exists() else None
    return _CACHE["o"]


def _report(D: pl.DataFrame):
    for t in D["term"].unique(maintain_order=True).to_list():
        d = D.filter(pl.col("term") == t)
        print(f"{t}: {d.height} sections, {int(d['enrollment'].sum())} seats filled, "
              f"{d['building'].n_unique()} buildings; areas: {dict(d.group_by('area').agg(pl.col('enrollment').sum()).iter_rows())}")


def main():
    if SRC.exists():
        D = build_sections()
        D.write_parquet(OUT, compression="zstd")
        O = build_occupancy()
        O.write_parquet(OCC, compression="zstd")
        print("BYU")
        _report(D)
        print(f"occupancy rows: {O.height}; {OUT.stat().st_size // 1024} KB + {OCC.stat().st_size // 1024} KB")
    if UVU_SRC.exists():
        U = build_uvu_sections()
        U.write_parquet(UVU_OUT, compression="zstd")
        print("UVU")
        _report(U)
        raise_uvu_floors(U)
        print(f"{UVU_OUT.stat().st_size // 1024} KB")


if __name__ == "__main__":
    main()
