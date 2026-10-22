"""Published apartment and bed totals for complexes the address points under-count (config/places/complex_totals.yaml)
→ complexes.parquet's `units`, `extra_units` and `beds_per_unit`. Idempotent: the missing apartments are always the
published total less the complex's own address points.

    python -m ucsim.geo.complex_totals
"""
from __future__ import annotations

from pathlib import Path

import polars as pl
import yaml

GEO = Path(__file__).resolve().parent / "data"
SPEC = Path(__file__).resolve().parents[1] / "config" / "places" / "complex_totals.yaml"


def apply(cx: pl.DataFrame, dw: pl.DataFrame, spec: list) -> pl.DataFrame:
    have = dict(dw.filter(pl.col("complex_id").is_not_null()).group_by("complex_id").len().iter_rows())
    ids = dict(zip(cx["name"].to_list(), cx["complex_id"].to_list()))
    units, extra = cx["units"].to_list(), cx["extra_units"].to_list()
    bpu = cx["beds_per_unit"].to_list() if "beds_per_unit" in cx.columns else [None] * cx.height
    for s in spec:
        i = ids[s["complex"]]
        also = [ids[n] for n in s.get("also", []) if n in ids]
        points = have.get(i, 0) + sum(have.get(j, 0) + extra[j] for j in also)
        units[i], extra[i] = int(s["units"]), max(0, int(s["units"]) - points)
        bpu[i] = round(s["beds"] / s["units"], 2) if s.get("beds") else None
    return cx.with_columns(units=pl.Series(units, dtype=cx["units"].dtype), extra_units=pl.Series(extra, dtype=pl.Int64),
                           beds_per_unit=pl.Series(bpu, dtype=pl.Float64))


def main():
    spec = yaml.safe_load(SPEC.read_text(encoding="utf-8"))["complexes"]
    cx = pl.read_parquet(GEO / "complexes.parquet")
    out = apply(cx, pl.read_parquet(GEO / "dwellings.parquet", columns=["complex_id"]), spec)
    out.write_parquet(GEO / "complexes.parquet")
    for s in spec:
        r = out.filter(pl.col("name") == s["complex"]).row(0, named=True)
        print(f"{s['complex']}: {r['units']} apartments ({r['extra_units']} beyond its address points), {r['beds_per_unit']} beds each")


if __name__ == "__main__":
    main()
