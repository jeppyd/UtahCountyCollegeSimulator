"""Published apartment totals (config/places/complex_totals.yaml, geo/complex_totals.py): the big Orem complexes the
county's address points barely cover get their real size, applying them twice changes nothing, and the world houses
people there at the published beds per apartment."""
import numpy as np
import polars as pl
import yaml

from ucsim.geo import complex_totals as ct


def test_totals_applied_and_idempotent():
    spec = yaml.safe_load(ct.SPEC.read_text(encoding="utf-8"))["complexes"]
    cx = pl.read_parquet(ct.GEO / "complexes.parquet")
    dw = pl.read_parquet(ct.GEO / "dwellings.parquet", columns=["complex_id"])
    assert ct.apply(cx, dw, spec).equals(cx)
    for s in spec:
        r = cx.filter(pl.col("name") == s["complex"]).row(0, named=True)
        assert r["units"] == s["units"] and abs(r["beds_per_unit"] * s["units"] - s["beds"]) < s["units"] * 0.01
    green = cx.filter(pl.col("name") == "The Green").row(0, named=True)
    assert green["extra_units"] > 400


def test_world_houses_people_there():
    from ucsim.engine.runner import new_simulation
    s = new_simulation(scale=0.1, seed=2)
    cx = pl.read_parquet(ct.GEO / "complexes.parquet")
    i = cx.filter(pl.col("name") == "Wolverine Crossing")["complex_id"][0]
    m = s.w.units.complex_id == i
    assert m.sum() > 10 and 4.5 < s.w.units.capacity[m].mean() < 5.5
