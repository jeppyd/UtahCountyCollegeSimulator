"""Explainability: individual decompositions, causal event chains, cohort and universe attribution.

Simulation provenance ≠ real-world causality.  These functions answer "within this
simulated world, through which mechanisms and events did this outcome arise?".
"""
from __future__ import annotations

import numpy as np

from ..engine.state import CTX, Tie

STATE_LABEL_VARS = ["mood", "loneliness", "stress", "anxiety", "belonging", "self_esteem", "guilt", "fatigue", "purpose",
                    "financial_stress", "academic_pressure", "romantic_longing"]


def event_record(sim, eid: int) -> dict:
    log = sim.log
    a = int(log["a"][eid])
    b = int(log["b"][eid])
    mech = int(log["mech"][eid])
    spec = sim.reg.events[sim.reg.event_names[log["type"][eid]]]
    return {"id": int(eid), "day": int(log["day"][eid]), "date": str(sim.cal.date(int(log["day"][eid]))),
            "type": spec.id, "label": spec.label, "category": spec.category, "salience": spec.salience,
            "a": a, "b": b if b >= 0 else None, "value": float(log["value"][eid]),
            "cause": int(log["cause"][eid]) if log["cause"][eid] >= 0 else None,
            "mechanism": log.mech_names[mech] if mech >= 0 else None,
            "place": int(log["place"][eid]) if log["place"][eid] >= 0 else None}


def event_chain(sim, eid: int, depth: int = 12) -> list[dict]:
    """Follow causal parents back from an event."""
    out = []
    seen = set()
    cur = eid
    while cur is not None and cur >= 0 and cur not in seen and len(out) < depth:
        seen.add(cur)
        rec = event_record(sim, cur)
        out.append(rec)
        cur = rec["cause"]
    return out


def event_descendants(sim, eid: int, max_n: int = 60) -> list[dict]:
    log = sim.log
    frontier = [eid]
    out = []
    causes = log["cause"]
    while frontier and len(out) < max_n:
        kids = np.where(np.isin(causes, frontier))[0]
        kids = [k for k in kids if k not in frontier][: max_n - len(out)]
        out += [event_record(sim, int(k)) for k in kids]
        frontier = kids
    return out


def explain_state(sim, i: int, var: str) -> dict:
    """Additive decomposition of an emotional state for one agent: mechanism terms + event effects."""
    emo = sim.systems["emotion"]
    reg = sim.reg
    terms = []
    for t, arr in emo.contrib.get(var, {}).items():
        if i < len(arr):
            mid = f"{var}.{t}"
            m = reg.mechanisms.get(mid)
            terms.append({"term": t, "mechanism": mid, "label": m.label if m else t, "value": float(arr[i]),
                          "evidence": m.evidence if m else "calibrated", "sources": m.sources if m else []})
    effects = []
    for eff in sim.effects.for_agent(i, sim.w.day):
        if eff["var"] != var or abs(eff["now"]) < 0.002:
            continue
        rec = event_record(sim, eff["event"]) if eff["event"] >= 0 else None
        effects.append({"value": eff["now"], "initial": eff["mag"], "start_day": eff["start"], "half_life": eff["half_life"],
                        "event": rec})
    effects.sort(key=lambda e: -abs(e["value"]))
    P = sim.w.P
    ar = float(P.internal[f"ar_{var}"][i]) if f"ar_{var}" in P.internal else 0.0
    return {"var": var, "value": float(P[var][i]), "terms": sorted(terms, key=lambda t: -abs(t["value"])),
            "events": effects[:12], "noise": ar}


def goals(sim, i: int) -> list[dict]:
    """BDI-style current desires with intensities (derived from state; read-only)."""
    P = sim.w.P
    g = []
    single = P.isin("rel_status", ["single", "divorced", "talking"])[i]
    if single and P["dating_motivation"][i] > 0.3:
        g.append({"goal": "Find a relationship", "intensity": float(P["dating_motivation"][i])})
    if P.is_("rel_status", "dating")[i] or P.is_("rel_status", "engaged")[i]:
        g.append({"goal": "Move toward marriage" if P["activity"][i] == 3 else "Grow the relationship",
                  "intensity": float(np.nan_to_num(P["relationship_commitment"][i], nan=0.5))})
    if P["enrolled"][i]:
        g.append({"goal": "Graduate", "intensity": float(np.clip(P["credits_done"][i] / 120, 0.2, 1))})
        if P["academic_pressure"][i] > 0.3:
            g.append({"goal": "Raise grades", "intensity": float(P["academic_pressure"][i])})
    if P["loneliness"][i] > 0.5:
        g.append({"goal": "Make closer friends", "intensity": float(P["loneliness"][i])})
    if P["financial_stress"][i] > 0.5:
        g.append({"goal": "Get finances under control", "intensity": float(P["financial_stress"][i])})
    if P["faith_crisis"][i]:
        g.append({"goal": "Resolve questions about faith", "intensity": 0.8})
    if P["lds_member"][i] and P.is_("mission_status", "none")[i] and P["age"][i] < 21 and P["faith_belief"][i] > 0.7:
        g.append({"goal": "Prepare to serve a mission", "intensity": float(P["faith_belief"][i])})
    if P["guilt"][i] > 0.3:
        g.append({"goal": "Repent / resolve guilt", "intensity": float(P["guilt"][i])})
    if not P["employed"][i] and not P["enrolled"][i]:
        g.append({"goal": "Find work", "intensity": 0.7})
    return sorted(g, key=lambda x: -x["intensity"])


def ego_network(sim, i: int, max_nodes: int = 60, min_stage: int = 1) -> dict:
    w = sim.w
    P, E = w.P, w.E
    lo, hi = E.endpoints()
    m = ((lo == i) | (hi == i)) & (E["stage"] >= min_stage)
    idx = np.where(m)[0]
    other = np.where(lo[idx] == i, hi[idx], lo[idx])
    score = E["closeness"][idx] + 0.5 * (E["stage"][idx] >= 3) + 2.0 * ((E["flags"][idx] & (Tie.ROMANTIC | Tie.SPOUSE)) > 0)
    order = np.argsort(-score)[:max_nodes]
    idx, other = idx[order], other[order]
    nodes = [{"id": int(i), "ego": True}] + [{"id": int(o)} for o in other]
    edges = []
    for e, o in zip(idx, other):
        att_out = float(E.attraction_from(np.array([e]), np.array([i]))[0])
        att_in = float(E.attraction_from(np.array([e]), np.array([o]))[0])
        edges.append({"source": int(i), "target": int(o), "stage": int(E["stage"][e]), "closeness": float(E["closeness"][e]),
                      "liking": float(E["liking"][e]), "trust": float(E["trust"][e]), "hours": float(E["hours"][e]),
                      "attraction_out": att_out, "attraction_in": att_in, "types": Tie.decode(int(E["flags"][e])),
                      "met": CTX[int(E["origin_ctx"][e])] if int(E["origin_ctx"][e]) < len(CTX) else "?",
                      "first_day": int(E["first_day"][e]), "last_day": int(E["last_day"][e]),
                      "introducer": int(E["introducer"][e]) if E["introducer"][e] >= 0 else None, "dates": int(E["dates"][e])})
    # ties among the alters (so clusters are visible)
    alters = set(other.tolist())
    if alters:
        al = np.array(sorted(alters))
        mm = np.isin(lo, al) & np.isin(hi, al) & (E["stage"] >= 2)
        for e in np.where(mm)[0][:400]:
            edges.append({"source": int(lo[e]), "target": int(hi[e]), "stage": int(E["stage"][e]),
                          "closeness": float(E["closeness"][e]), "types": Tie.decode(int(E["flags"][e])), "alter_tie": True})
    return {"nodes": nodes, "edges": edges}


def cohort_term_attribution(sim, mask: np.ndarray, var: str) -> list[dict]:
    """Mean of each mechanism term for a cohort (now)."""
    emo = sim.systems["emotion"]
    out = []
    for t, arr in emo.contrib.get(var, {}).items():
        if len(arr) == len(mask):
            out.append({"term": t, "mechanism": f"{var}.{t}", "mean": float(arr[mask].mean())})
    tr = emo.transient.get(var)
    if tr is not None and len(tr) == len(mask):
        out.append({"term": "events", "mechanism": None, "mean": float(tr[mask].mean())})
    return out


def compare_universes(base, alt, mask_fn=None) -> dict:
    """Difference decomposition between paired universes.

    For each composed state: Δmean = Σ_terms Δterm + Δevents + Δnoise (exact, additive).
    Each term's Δ is attributed to its mechanism; mechanisms are linked to their source
    variables, whose own Δ is reported — giving a multi-level causal web of differences.
    Event-type count differences show the discrete consequence chains.
    """
    Pb, Pa = base.w.P, alt.w.P
    n = min(Pb.n, Pa.n)
    mb = Pb["present"][:n]
    ma = Pa["present"][:n]
    both = mb & ma
    if mask_fn is not None:
        both &= mask_fn(base)[:n]
    reg = base.reg
    out = {"day": base.w.day, "n": int(both.sum()), "states": {}, "variables": {}, "events": [], "mechanisms": {}}
    eb, ea = base.systems["emotion"], alt.systems["emotion"]
    for s in STATE_LABEL_VARS:
        rows = []
        for t in eb.contrib.get(s, {}):
            xb = eb.contrib[s][t][:n][both].mean()
            xa = ea.contrib[s].get(t, np.zeros(n))[:n][both].mean()
            rows.append({"term": t, "mechanism": f"{s}.{t}", "delta": float(xa - xb)})
        tb = eb.transient.get(s)
        ta = ea.transient.get(s)
        if tb is not None and ta is not None:
            rows.append({"term": "events", "mechanism": None, "delta": float(ta[:n][both].mean() - tb[:n][both].mean())})
        out["states"][s] = {"delta": float(Pa[s][:n][both].mean() - Pb[s][:n][both].mean()),
                            "terms": sorted(rows, key=lambda r: -abs(r["delta"]))}
    for v in reg.person_vars():
        if v.dtype in ("str",) or v.id in ("birth_day", "arrival_day", "departure_day", "loc_lon", "loc_lat", "home_lon", "home_lat"):
            continue
        xb, xa = Pb[v.id][:n][both], Pa[v.id][:n][both]
        if v.dtype == "cat":
            cats = v.categories
            db = np.bincount(xb, minlength=len(cats)) / max(len(xb), 1)
            da = np.bincount(xa, minlength=len(cats)) / max(len(xa), 1)
            diff = da - db
            k = int(np.argmax(np.abs(diff)))
            out["variables"][v.id] = {"kind": "cat", "delta": float(np.abs(diff).sum() / 2), "top": cats[k], "top_delta": float(diff[k]),
                                      "base": dict(zip(cats, db.round(4).tolist())), "alt": dict(zip(cats, da.round(4).tolist()))}
        else:
            fb, fa = xb.astype(float), xa.astype(float)
            okb, oka = np.isfinite(fb), np.isfinite(fa)
            if not okb.any() or not oka.any():
                continue
            mbv, mav = fb[okb].mean(), fa[oka].mean()
            sd = fb[okb].std() or 1.0
            out["variables"][v.id] = {"kind": "num", "base": float(mbv), "alt": float(mav), "delta": float(mav - mbv),
                                      "delta_sd": float((mav - mbv) / sd), "changed_share": float(np.mean(np.abs(fa - fb) > 1e-6))}
    # event-count differences since the fork
    fork_day = getattr(alt, "meta_fork_day", 0)
    lb, la = base.log, alt.log
    cb = np.bincount(lb["type"][lb["day"] >= fork_day], minlength=len(reg.event_names))
    ca = np.bincount(la["type"][la["day"] >= fork_day], minlength=len(reg.event_names))
    for code in np.nonzero(cb + ca)[0]:
        out["events"].append({"type": reg.event_names[code], "label": reg.events[reg.event_names[code]].label,
                              "base": int(cb[code]), "alt": int(ca[code]), "delta": int(ca[code] - cb[code]),
                              "rel": float((ca[code] - cb[code]) / max(cb[code], 1))})
    out["events"].sort(key=lambda r: -abs(r["rel"]) * np.log1p(r["base"] + r["alt"]))
    # mechanism-level magnitudes (from state term deltas)
    for s, d in out["states"].items():
        for r in d["terms"]:
            if r["mechanism"]:
                out["mechanisms"][r["mechanism"]] = r["delta"]
    return out


def most_affected(base, alt, var: str, k: int = 12) -> list[dict]:
    Pb, Pa = base.w.P, alt.w.P
    n = min(Pb.n, Pa.n)
    both = Pb["present"][:n] & Pa["present"][:n]
    d = Pa[var][:n].astype(float) - Pb[var][:n].astype(float)
    d = np.where(both & np.isfinite(d), d, 0)
    idx = np.argsort(-np.abs(d))[:k]
    return [{"id": int(i), "delta": float(d[i]), "base": float(Pb[var][i]), "alt": float(Pa[var][i])} for i in idx if d[i] != 0]
