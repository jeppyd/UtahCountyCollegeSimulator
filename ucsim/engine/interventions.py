"""Structured interventions.

An intervention changes the world at a time, for a population, with a ramp:

    {"id": "tuition_up", "name": "BYU tuition +20%", "target_type": "world", "target": "tuition_byu",
     "op": "mul", "value": 1.2, "start_day": 30, "duration_days": null, "ramp_days": 0,
     "population": null, "confidence": "hypothetical", "description": "..."}

target_type
  world   – an environment variable (env[...]): tuition, unemployment, temperature delta, app appeal …
  param   – a mechanism parameter "<mechanism id>.<param>" (effect strengths; sensitivity analysis)
  agent   – a person variable for a filtered population (applied once at start; logged as exposure events)
  venue   – adds a new venue (a new business opening) {"vtype": ..., "lon": ..., "lat": ..., "name": ...}

Interventions never touch the shared registry; parameter changes live in the run's ParamSet.
The natural-language → intervention compiler (LLM layer) only has to emit this JSON.
"""
from __future__ import annotations

import copy
from pathlib import Path

import numpy as np
import yaml

PRESETS = Path(__file__).resolve().parents[1] / "config" / "interventions.yaml"


def load_presets() -> dict:
    return yaml.safe_load(PRESETS.read_text(encoding="utf-8"))["interventions"]


def expand(spec: dict | str) -> list[dict]:
    """A preset id or a spec dict -> list of atomic intervention dicts (presets may bundle several)."""
    presets = load_presets()
    if isinstance(spec, str):
        spec = {"preset": spec}
    if "preset" in spec:
        base = copy.deepcopy(presets[spec["preset"]])
        overrides = {k: v for k, v in spec.items() if k != "preset"}
        parts = base.pop("parts", None)
        if parts:
            out = []
            for p in parts:
                q = {**{k: v for k, v in base.items() if k not in ("parts",)}, **p, **overrides}
                q.setdefault("id", spec["preset"])
                out.append(q)
            return out
        base.update(overrides)
        base.setdefault("id", spec["preset"])
        return [base]
    return [spec]


class InterventionManager:
    def __init__(self, sim, specs: list):
        self.sim = sim
        self.items: list[dict] = []
        for s in specs:
            for atom in expand(s):
                atom.setdefault("start_day", 0)
                atom.setdefault("ramp_days", 0)
                atom.setdefault("duration_days", None)
                atom.setdefault("op", "set")
                self.items.append(atom)
        self._applied_agent: set[int] = set()
        self._base_params = dict(sim.p.values)

    def _ramp(self, it, day) -> float:
        s = it["start_day"]
        if day < s:
            return 0.0
        dur = it.get("duration_days")
        if dur is not None and day >= s + dur:
            return 0.0
        r = it.get("ramp_days") or 0
        return 1.0 if r <= 0 else min(1.0, (day - s + 1) / r)

    @staticmethod
    def _combine(base, op, value, frac):
        if op == "set":
            if isinstance(base, (bool, np.bool_)) or isinstance(value, bool):
                return value if frac >= 0.5 else base
            return base + (value - base) * frac
        if op == "add":
            return base + value * frac
        if op == "mul":
            return base * (1 + (value - 1) * frac)
        raise ValueError(op)

    def apply_world(self, env_base: dict, env: dict, day: int):
        for it in self.items:
            if it.get("target_type") != "world":
                continue
            f = self._ramp(it, day)
            if f > 0:
                env[it["target"]] = self._combine(env.get(it["target"], env_base.get(it["target"], 0.0)), it["op"], it["value"], f)

    def apply_params(self, day: int):
        p = self.sim.p
        touched = {}
        for it in self.items:
            if it.get("target_type") != "param":
                continue
            key = it["target"]
            f = self._ramp(it, day)
            base = touched.get(key, self._base_params[key])
            touched[key] = self._combine(base, it["op"], float(it["value"]), f) if f > 0 else base
        for k, v in touched.items():
            p.values[k] = v

    def apply_agents(self, day: int):
        from ..analysis.query import evaluate_filter
        sim = self.sim
        P = sim.w.P
        for k, it in enumerate(self.items):
            if it.get("target_type") not in ("agent", "venue") or k in self._applied_agent or day < it["start_day"]:
                continue
            self._applied_agent.add(k)
            if it["target_type"] == "venue":
                sim.systems["activity"].add_venue(it["value"])
                continue
            mask = P["present"].copy()
            if it.get("population"):
                mask &= evaluate_filter(sim.w, it["population"])
            ids = np.where(mask)[0]
            col = P.cols[it["target"]]
            cur = col[ids].astype(np.float64)
            new = self._combine(cur, it["op"], float(it["value"]), 1.0)
            spec = P.specs[it["target"]]
            if spec.range:
                new = np.clip(new, spec.range[0], spec.range[1])
            col[ids] = new.astype(col.dtype)
            sim.emit("intervention_exposure", ids, value=float(it["value"]))

    def summary(self) -> list[dict]:
        return [dict(it) for it in self.items]
