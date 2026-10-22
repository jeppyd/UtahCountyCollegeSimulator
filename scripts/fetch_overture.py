"""Fetch Overture Maps buildings and places for Provo/Orem (public S3, no account needed).

    python scripts/fetch_overture.py              # → data/external/overture/{buildings,places}.parquet (gitignored)
    python scripts/fetch_overture.py --release 2026-09-23.0

Overture buildings carry OpenStreetMap footprints (with names and floor counts where mappers added them) merged with
Esri Community Maps and Microsoft footprints, and heights for most buildings (estimated from lidar). Licenses:
buildings ODbL (© OpenStreetMap contributors, Overture Maps Foundation); places CDLA-Permissive-2.0. Then run
`python -m ucsim.geo.buildings` to build the committed building layer.
"""
from __future__ import annotations

import argparse
import time
from pathlib import Path

import pyarrow.compute as pc
import pyarrow.dataset as ds
import pyarrow.fs as fs
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "external" / "overture"
BUCKET = "overturemaps-us-west-2/release"
BBOX = (-111.775, 40.170, -111.570, 40.360)     # same box as scripts/fetch_geodata.py
LAYERS = {"buildings": ("buildings", "building"), "places": ("places", "place")}


def latest_release(s3) -> str:
    rel = [i.base_name for i in s3.get_file_info(fs.FileSelector(BUCKET)) if i.type == fs.FileType.Directory]
    return sorted(rel)[-1]


def fetch(name: str, release: str, s3) -> int:
    theme, typ = LAYERS[name]
    d = ds.dataset(f"{BUCKET}/{release}/theme={theme}/type={typ}/", filesystem=s3, format="parquet")
    f = lambda k: pc.field("bbox", k)                                          # noqa: E731
    flt = (f("xmin") > BBOX[0]) & (f("xmax") < BBOX[2]) & (f("ymin") > BBOX[1]) & (f("ymax") < BBOX[3])
    tab = d.to_table(filter=flt)
    OUT.mkdir(parents=True, exist_ok=True)
    pq.write_table(tab.replace_schema_metadata({"overture_release": release}), OUT / f"{name}.parquet")
    return tab.num_rows


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--release", default=None, help="Overture release (default: the latest)")
    ap.add_argument("--only", choices=sorted(LAYERS), default=None)
    a = ap.parse_args()
    s3 = fs.S3FileSystem(anonymous=True, region="us-west-2")
    release = a.release or latest_release(s3)
    print(f"Overture release {release}")
    for name in ([a.only] if a.only else LAYERS):
        t = time.time()
        print(f"  {name:10s} {fetch(name, release, s3):7d} features  {time.time() - t:5.1f}s")


if __name__ == "__main__":
    main()
