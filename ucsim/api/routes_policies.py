"""Campus policies (config/policies/campus.yaml) with what they do in the running world: Honor Code reports and
outcomes, endorsements, who left BYU and why, and the world switches a What-if can change. Read-only."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import numpy as np
import yaml
from fastapi import APIRouter

router = APIRouter()
POLICY_FILE = Path(__file__).resolve().parent.parent / "config" / "policies" / "campus.yaml"
SWITCHES = ("honor_enforcement", "endorsement_required", "coffee_permitted", "alcohol_permitted",
            "contracted_housing_required", "contracted_housing_all_years")


def _server():
    from .routes_trace import _server as s
    return s()


@lru_cache(maxsize=1)
def policies() -> list[dict]:
    return yaml.safe_load(POLICY_FILE.read_text(encoding="utf-8"))["policies"]


@router.get("/api/policies")
def campus_policies(u: str = "base"):
    """Every policy with its source, plus live numbers from the world: the Honor Code's reports and outcomes so far,
    standing and endorsement counts among BYU students now, and the current world switches."""
    WS, jresp = _server()
    sim = WS.sim(u)
    with WS.lock:
        P, reg, log = sim.w.P, sim.reg, sim.log
        h = sim.systems.get("honor")
        n = P.n
        byu = (P["school"] == P.code("school", "BYU")) & P.is_("role", "byu_student") & P["present"]

        def counts(var):
            cats = reg.variables[var].categories
            c = np.bincount(P[var][:n][byu], minlength=len(cats))
            return {cats[k]: int(c[k]) for k in range(len(cats)) if cats[k] != "n/a"}
        names = ("honor_reported", "honor_warning", "honor_probation", "honor_suspended", "endorsement_withdrawn", "left_byu")
        ev = {}
        if log.n:
            for t in names:
                if t in reg.event_ids:
                    ev[t] = int((log["type"][: log.n] == reg.event_ids[t]).sum())
        live = {"byu_students": int(byu.sum()), "standing": counts("honor_standing"), "endorsement": counts("endorsement"),
                "events": ev, "totals": {"reports": h.reports, "outcomes": h.outcomes, "withdrawn": h.withdrawn, "left": h.left} if h else None,
                "days": int(sim.w.day)}
        sw = {k: sim.w.env.get(k) for k in SWITCHES}
        return jresp({"policies": policies(), "live": live, "switches": sw,
                      "switch_words": {k: reg.variables[f"world.{k}"].label for k in SWITCHES if f"world.{k}" in reg.variables}})
