"""Real BYU/UVU majors (ucsim/config/majors.yaml) with stable global ids for the major_id column."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import numpy as np
import yaml

MAJORS = Path(__file__).resolve().parents[1] / "config" / "majors.yaml"


@lru_cache(maxsize=1)
def catalog() -> list[dict]:
    doc = yaml.safe_load(MAJORS.read_text(encoding="utf-8"))
    out = []
    for school in ("BYU", "UVU"):
        for m in doc[school]:
            out.append({**m, "school": school, "id": len(out)})
    return out


def label(major_id: int) -> str | None:
    cat = catalog()
    return cat[major_id]["major"] if 0 <= major_id < len(cat) else None


def sample(rng: np.random.Generator, school: str, areas: np.ndarray) -> np.ndarray:
    """A major id for each person, drawn within their study area at their school by popularity weight."""
    cat = [m for m in catalog() if m["school"] == school]
    out = np.full(len(areas), -1, np.int16)
    for area in np.unique(areas):
        pool = [m for m in cat if m["area"] == area] or [m for m in cat if m["area"] == "Undeclared"]
        if not pool:
            continue
        w = np.array([m.get("weight", 1.0) for m in pool], float)
        idx = np.where(areas == area)[0]
        out[idx] = np.array([m["id"] for m in pool])[rng.choice(len(pool), len(idx), p=w / w.sum())]
    return out
