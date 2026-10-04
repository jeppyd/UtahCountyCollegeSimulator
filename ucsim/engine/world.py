"""The World container: every entity table plus environment state for one universe."""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import polars as pl

from ..registry import ParamSet, Registry
from .state import EdgeStore, PersonTable


@dataclass
class World:
    reg: Registry
    params: ParamSet
    cfg: dict
    scale: float
    seed: int
    start_date: dt.date
    P: PersonTable
    E: EdgeStore
    units: Any
    complexes: pl.DataFrame
    wards: dict
    employers: dict
    venues: pl.DataFrame
    meetinghouses: pl.DataFrame
    day: int = 0
    hour: int = 6
    env: dict = field(default_factory=dict)        # world-level variables (temp, unemployment, rent index…)
    sections: dict = field(default_factory=dict)   # class sections for the current term
    groups: dict = field(default_factory=dict)     # clubs, intramural teams, institute classes (systems/groups.py)
    congregations: dict = field(default_factory=dict)  # non-LDS congregations (geo/data/congregations.json)
    meta: dict = field(default_factory=dict)

    @property
    def date(self) -> dt.date:
        return self.start_date + dt.timedelta(days=self.day)

    def present_mask(self) -> np.ndarray:
        return self.P["present"]
