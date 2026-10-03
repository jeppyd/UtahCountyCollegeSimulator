"""Rich individual profile: identity, background, personality, faith, emotions, life story, why."""
from __future__ import annotations

import numpy as np

from .explain import STATE_LABEL_VARS, ego_network, event_record, explain_state, goals

FIRST_F = ["Emma", "Abigail", "Hannah", "Ellie", "Olivia", "Ava", "Sarah", "Rachel", "Lydia", "Eliza", "Brooklyn", "McKenna",
           "Kate", "Lauren", "Megan", "Rebecca", "Anna", "Claire", "Madison", "Jenna", "Sophie", "Grace", "Natalie", "Camille"]
FIRST_M = ["Jacob", "Ethan", "Tyler", "Spencer", "Josh", "Caleb", "Sam", "Nathan", "Ben", "Isaac", "Tanner", "Jared", "Dallin",
           "Brigham", "Carter", "Logan", "Michael", "Daniel", "Austin", "Parker", "Hunter", "Mason", "Luke", "Andrew"]
LAST = ["Anderson", "Christensen", "Jensen", "Larsen", "Peterson", "Smith", "Johnson", "Bowen", "Hansen", "Nielsen",
        "Taylor", "Clark", "Allen", "Hall", "Walker", "Robinson", "Thompson", "Martinez", "Nguyen", "Garcia", "Kimball",
        "Cannon", "Richards", "Snow", "Lee", "Pratt", "Bennion", "Ashby", "Rasband", "Wilkinson"]


from ..population.majors import label as major_label  # noqa: E402


def synthetic_name(P, i: int) -> str:
    """Deterministic, obviously-synthetic display name (no relation to any real respondent)."""
    h = (i * 2654435761) & 0xFFFFFFFF
    female = P["sex"][i] == P.code("sex", "F")
    first = (FIRST_F if female else FIRST_M)[h % 24]
    return f"{first} {LAST[(h >> 8) % len(LAST)]}"


def _val(P, k, i):
    spec = P.specs[k]
    x = P[k][i]
    if spec.dtype == "cat":
        return spec.categories[int(x)]
    if spec.dtype == "bool":
        return bool(x)
    if spec.dtype in ("f4", "f8"):
        return None if not np.isfinite(x) else round(float(x), 4)
    return int(x)


def profile(sim, i: int) -> dict:
    w = sim.w
    P = w.P
    reg = sim.reg
    domains: dict[str, list] = {}
    for k, spec in P.specs.items():
        if spec.dtype == "str" or k in ("loc_lon", "loc_lat"):
            continue
        domains.setdefault(spec.domain, []).append({"id": k, "label": spec.label, "value": _val(P, k, i),
                                                    "units": spec.units, "kind": spec.kind, "evidence": spec.evidence,
                                                    "group": spec.group})
    # life history: salient events involving the person
    log = sim.log
    mine = np.where((log["a"] == i))[0]
    sal = np.array([reg.events[reg.event_names[t]].salience for t in log["type"][mine]]) if len(mine) else np.array([])
    keep = mine[sal >= 0.45] if len(mine) else mine
    timeline = [event_record(sim, int(e)) for e in keep[-250:]]
    me = synthetic_name(P, i)
    for ev in timeline:
        ev["a_name"] = me
        if ev["b"] is not None:
            ev["b_name"] = synthetic_name(P, ev["b"])
    # composition of emotional states
    why = {s: explain_state(sim, i, s) for s in STATE_LABEL_VARS}
    partner = int(P["partner_id"][i])
    unit = int(P["unit_id"][i])
    roommates = [int(x) for x in np.where((P["unit_id"] == unit) & (np.arange(P.n) != i))[0]] if unit >= 0 else []
    cx = int(P["complex_id"][i])
    complex_name = w.complexes["name"][cx] if cx >= 0 and cx < w.complexes.height else None
    ward = int(P["ward_id"][i])
    emp = int(P["employer_id"][i])
    exposures = [event_record(sim, int(e)) for e in mine if reg.event_names[log["type"][e]] == "intervention_exposure"]
    return {
        "id": i, "name": synthetic_name(P, i), "synthetic": True,
        "major": major_label(int(P["major_id"][i])) if "major_id" in P else None,
        "college": _val(P, "college", i) if "college" in P else None,
        "looks": {"height_in": float(P["height_in"][i]), "weight_lb": float(P["weight_lb"][i]) if "weight_lb" in P else None,
                  "build": _val(P, "body_build", i) if "body_build" in P else None,
                  "hair": _val(P, "hair_color", i) if "hair_color" in P else None, "eyes": _val(P, "eye_color", i) if "eye_color" in P else None},
        "headline": headline(sim, i),
        "domains": domains,
        "partner": {"id": partner, "name": synthetic_name(P, partner)} if partner >= 0 else None,
        "roommates": [{"id": r, "name": synthetic_name(P, r)} for r in roommates[:10]],
        "home": {"lon": float(P["home_lon"][i]), "lat": float(P["home_lat"][i]), "complex": complex_name,
                 "living": _val(P, "living", i), "rent": float(P["rent"][i])},
        "ward": {"id": ward, "kind": str(w.wards["kind"][ward])} if ward >= 0 else None,
        "employer": {"id": emp, "name": str(w.employers["name"][emp]), "type": str(w.employers["type"][emp])} if emp >= 0 else None,
        "timeline": timeline,
        "why": why,
        "goals": goals(sim, i),
        "network": _named(ego_network(sim, i, max_nodes=40), P),
        "exposures": exposures,
        "now": {"activity": _val(P, "activity_now", i), "lon": float(np.nan_to_num(P["loc_lon"][i])), "lat": float(np.nan_to_num(P["loc_lat"][i]))},
    }


def _named(net: dict, P) -> dict:
    for e in net.get("edges", []):
        if not e.get("alter_tie"):
            e["name"] = synthetic_name(P, int(e["target"]))
    return net


def headline(sim, i: int) -> str:
    P = sim.w.P
    age = int(P["age"][i])
    role = {"byu_student": "BYU student", "uvu_student": "UVU student", "young_adult": "young adult", "spouse": "spouse",
            "faculty": "professor", "staff": "university staff", "community": "community member"}[_val(P, "role", i)]
    rel = _val(P, "rel_status", i)
    act = _val(P, "activity", i).replace("_", " ")
    ms = _val(P, "mission_status", i)
    bits = [f"{age}-year-old {role}", rel]
    if "major_id" in P and int(P["major_id"][i]) >= 0 and P["enrolled"][i]:
        m = major_label(int(P["major_id"][i]))
        if m and not m.startswith("Exploratory"):
            bits[0] += f" studying {m}"
        elif m:
            bits[0] += " (undeclared)"
    if ms in ("returned", "early_returned"):
        bits.append("returned missionary" if ms == "returned" else "early-returned missionary")
    if ms == "serving":
        bits.append("serving a mission")
    if P["lds_member"][i]:
        bits.append(f"{act} Latter-day Saint")
    living = _val(P, "living", i).replace("_", " ")
    bits.append(f"lives in {living}")
    return ", ".join(bits)
