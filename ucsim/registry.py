"""Variable, mechanism and event-type registries.

The registries are the single source of truth for:
* the columnar state store (dtype, defaults, categories),
* the analysis UI (labels, domains, evidence badges, filter/chart/map flags),
* mechanism parameters used by the engine (so sweeps/sensitivity can perturb them by id),
* event-type effect templates (magnitude, decay, moderators),
* generated documentation (VARIABLE_CATALOG.md, MECHANISMS.md).
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np
import yaml

CONFIG = Path(__file__).resolve().parent / "config"

EVIDENCE_LEVELS = {
    "observed": "Directly observed in relevant data",
    "empirical": "Empirically estimated from data (survey copula / tables)",
    "literature": "Supported by established theory or replicated research",
    "calibrated": "Chosen to reproduce observed population patterns",
    "extrapolated": "Applied from another population",
    "structural": "A plausible structural assumption: a modeling form chosen for coherence, not a measured effect",
    "hypothetical": "Reasonable but insufficiently evidenced",
    "speculative": "Frontier: exploratory mechanism with weak or contested evidence",
}
# How much a parameter of each evidence level is allowed to vary in uncertainty ensembles, as a share of its
# declared range (1 = the full range). Better-evidenced parameters move less.
EVIDENCE_SPREAD = {"observed": 0.0, "empirical": 0.25, "literature": 0.5, "calibrated": 0.5, "extrapolated": 0.75,
                   "structural": 1.0, "hypothetical": 1.0, "speculative": 1.0}

DTYPES = {
    "f4": np.float32, "f8": np.float64, "i4": np.int32, "i2": np.int16, "u1": np.uint8,
    "u2": np.uint16, "u4": np.uint32, "bool": np.bool_, "cat": np.uint8, "str": object,
}


@dataclass
class VarSpec:
    id: str
    entity: str
    domain: str
    label: str
    dtype: str = "f4"
    kind: str = "attribute"
    units: str | None = None
    range: list | None = None
    categories: list | None = None
    ordinal: list | None = None
    update: str = "static"
    derived: bool = False
    desc: str = ""
    init: str = ""
    source: list = field(default_factory=list)
    evidence: str = "calibrated"
    flags: list = field(default_factory=list)
    group: str | None = None
    fill: Any = None

    @property
    def np_dtype(self):
        return DTYPES[self.dtype]

    def default_fill(self):
        if self.fill is not None:
            return self.fill
        if self.dtype == "i4":
            return -1
        if self.dtype in ("f4", "f8"):
            return 0.0
        return 0

    def to_dict(self) -> dict:
        d = {k: v for k, v in self.__dict__.items() if v not in (None, [], "")}
        d["filterable"] = "filter" in self.flags
        d["chartable"] = "chart" in self.flags
        d["mappable"] = "map" in self.flags
        d["intervenable"] = "intervene" in self.flags or self.kind in ("trait", "belief", "habit", "preference")
        d["time_varying"] = self.update not in ("static",)
        return d


@dataclass
class MechSpec:
    id: str
    system: str
    label: str
    target: str | list
    sources: list
    form: str
    params: dict
    evidence: str
    desc: str = ""
    moderators: list = field(default_factory=list)
    timescale: str = "daily"
    delay: str = "none"
    refs: list = field(default_factory=list)
    population: str = "all"
    applicability: str = ""
    context: list = field(default_factory=list)

    def p(self, name: str) -> float:
        return float(self.params[name]["value"])

    def to_dict(self) -> dict:
        return copy.deepcopy(self.__dict__)


@dataclass
class EventSpec:
    id: str
    label: str
    category: str
    salience: float
    effects: list
    evidence: str
    desc: str = ""
    refs: list = field(default_factory=list)
    story: str = ""   # sentence template for feeds and life stories: "{a} got engaged to {b}"

    def to_dict(self) -> dict:
        return copy.deepcopy(self.__dict__)


class Registry:
    # short names used in mechanism YAML for edge/world inputs → registry ids
    ALIASES = {"attraction": "edge.attraction_lh", "crush attraction": "edge.attraction_lh", "spark": "edge.chemistry",
               "friends' mood": "mood", "friends' belief": "faith_belief"}

    def __init__(self, config_dir: Path = CONFIG):
        self.config_dir = config_dir
        self.variables: dict[str, VarSpec] = {}
        self.mechanisms: dict[str, MechSpec] = {}
        self.events: dict[str, EventSpec] = {}
        self._load_variables()
        self._load_mechanisms()
        self._load_events()
        self._resolve_refs()
        self.event_ids = {k: i for i, k in enumerate(self.events)}
        self.event_names = list(self.events)

    # ------------------------------------------------------------------ loading
    def _load_variables(self):
        for path in sorted((self.config_dir / "variables").glob("*.yaml")):
            doc = yaml.safe_load(path.read_text(encoding="utf-8"))
            sections = doc.get("sections") or [doc]
            domain_default = path.stem.split("_", 1)[1]
            for sec in sections:
                entity = sec["entity"]
                defaults = sec.get("defaults", {})
                for vid, spec in sec["variables"].items():
                    merged = {**defaults, **(spec or {})}
                    domain = merged.pop("domain", None) or domain_default
                    key = vid if entity == "person" else f"{entity}.{vid}"
                    if key in self.variables:
                        raise ValueError(f"duplicate variable {key} in {path.name}")
                    if merged.get("dtype") == "cat" and not merged.get("categories"):
                        raise ValueError(f"categorical variable {key} needs categories")
                    self.variables[key] = VarSpec(id=vid, entity=entity, domain=domain,
                                                  label=merged.pop("label", vid), **merged)

    def _load_mechanisms(self):
        for path in sorted((self.config_dir / "mechanisms").glob("*.yaml")):
            doc = yaml.safe_load(path.read_text(encoding="utf-8"))
            system = doc["system"]
            for mid, spec in doc["mechanisms"].items():
                if mid in self.mechanisms:
                    raise ValueError(f"duplicate mechanism {mid}")
                spec = dict(spec)
                spec.setdefault("params", {})
                self.mechanisms[mid] = MechSpec(id=mid, system=system, **spec)

    def resolve(self, name: str) -> str | None:
        """Map a mechanism input/target name to a registry id (person, edge.* or world.*), if any."""
        if name in self.variables:
            return name
        for cand in (self.ALIASES.get(name), f"edge.{name}", f"world.{name}"):
            if cand and cand in self.variables:
                return cand
        return None

    def _resolve_refs(self):
        """Normalize mechanism targets/sources/moderators to registry ids; free-text inputs that are
        not state variables (\"calendar\", \"distance to campus\") move to `context`."""
        for m in self.mechanisms.values():
            tg = m.target if isinstance(m.target, list) else [m.target]
            rt = [self.resolve(t) for t in tg]
            if any(r is None for r in rt):
                raise ValueError(f"mechanism {m.id} targets unknown variable(s) {[t for t, r in zip(tg, rt) if r is None]}")
            m.target = rt if isinstance(m.target, list) else rt[0]
            for attr in ("sources", "moderators"):
                keep = []
                for x in getattr(m, attr):
                    r = self.resolve(x)
                    if r is None:
                        m.context.append(x)
                    elif r not in keep:
                        keep.append(r)
                setattr(m, attr, keep)

    def _load_events(self):
        path = self.config_dir / "events.yaml"
        if not path.exists():
            return
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
        for eid, spec in doc["events"].items():
            spec = dict(spec)
            spec.setdefault("effects", [])
            spec.setdefault("evidence", "calibrated")
            self.events[eid] = EventSpec(id=eid, **spec)

    # ------------------------------------------------------------------ queries
    def entity_vars(self, entity: str) -> list[VarSpec]:
        return [v for v in self.variables.values() if v.entity == entity]

    def person_vars(self) -> list[VarSpec]:
        return self.entity_vars("person")

    def mech(self, mid: str) -> MechSpec:
        return self.mechanisms[mid]

    def mechanisms_targeting(self, var: str) -> list[MechSpec]:
        out = []
        for m in self.mechanisms.values():
            tgt = m.target if isinstance(m.target, list) else [m.target]
            if var in tgt:
                out.append(m)
        return out

    def mechanisms_from(self, var: str) -> list[MechSpec]:
        return [m for m in self.mechanisms.values() if var in m.sources or var in m.moderators]

    def events_affecting(self, var: str) -> list[EventSpec]:
        return [e for e in self.events.values() if any(ef["var"] == var for ef in e.effects)]

    def as_json(self) -> dict:
        return {
            "evidence_levels": EVIDENCE_LEVELS,
            "variables": {k: v.to_dict() for k, v in self.variables.items()},
            "mechanisms": {k: m.to_dict() for k, m in self.mechanisms.items()},
            "events": {k: e.to_dict() for k, e in self.events.items()},
        }


@lru_cache(maxsize=1)
def get_registry() -> Registry:
    return Registry()


class ParamSet:
    """Mutable view of mechanism parameters for one simulation run.

    Interventions and sweeps override parameters here (never the shared registry),
    so paired universes can differ only in the parameters an intervention touches.
    """

    def __init__(self, registry: Registry, overrides: dict[str, float] | None = None):
        self.base = {f"{mid}.{p}": float(spec["value"])
                     for mid, m in registry.mechanisms.items() for p, spec in m.params.items()}
        self.values = dict(self.base)
        for k, v in (overrides or {}).items():
            self.set(k, v)

    def set(self, key: str, value: float):
        if key not in self.base:
            raise KeyError(f"unknown mechanism parameter {key}")
        self.values[key] = float(value)

    def __call__(self, key: str) -> float:
        return self.values[key]

    def get(self, mid: str, p: str) -> float:
        return self.values[f"{mid}.{p}"]

    def changed(self) -> dict[str, float]:
        return {k: v for k, v in self.values.items() if v != self.base[k]}
