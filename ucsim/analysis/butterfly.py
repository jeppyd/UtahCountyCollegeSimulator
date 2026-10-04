"""The butterfly effect: how and where two paired universes (Original vs What-if) differ.

Both universes share their random streams, so every difference is a consequence of the change —
directly, or through the people, places and events it touched. Everything here compares the same
synthetic people across the two worlds.
"""
from __future__ import annotations

import math

import numpy as np

from ..engine.state import CTX, Tie
from .explain import event_chain, event_record
from .person import headline, synthetic_name

SKIP = {"birth_day", "arrival_day", "departure_day", "loc_lon", "loc_lat", "home_lon", "home_lat"}
# states whose change marks a visibly different life (label, weight)
LIFE_STATES = [("rel_status", 2.0), ("partner_id", 3.0), ("unit_id", 1.5), ("activity", 1.5), ("living", 1.0),
               ("employed", 1.0), ("enrolled", 1.5), ("mission_status", 2.0), ("faith_crisis", 1.5), ("lds_member", 2.0),
               ("present", 2.0), ("depressive_episode", 1.0), ("school", 1.0), ("affiliation", 1.5)]
EVENT_SALIENCE = 0.5


def field_vars(reg) -> list:
    return [v for v in reg.person_vars() if "chart" in v.flags and v.dtype != "str" and not v.id.endswith("_id") and v.id not in SKIP]


def _both(base, alt):
    n = min(base.w.P.n, alt.w.P.n)
    return n, base.w.P["present"][:n] & alt.w.P["present"][:n]


def _cohen_h(p1: float, p2: float) -> float:
    c = lambda p: 2 * math.asin(math.sqrt(min(max(p, 0.0), 1.0)))  # noqa: E731
    return c(p2) - c(p1)


def compare_fields(base, alt) -> dict:
    """Every chartable field: Original vs What-if, as averages / shares and as individual churn.

    `effect` is a standardized size on one scale for all kinds (Cohen's d for numbers, Cohen's h for the
    most-changed share), so numeric and categorical fields can be ranked together. `changed_share` is
    the share of people whose own value differs — a butterfly can reshuffle lives without moving the average."""
    reg = base.reg
    n, both = _both(base, alt)
    Pb, Pa = base.w.P, alt.w.P
    rows = {}
    for v in field_vars(reg):
        xb, xa = Pb[v.id][:n][both], Pa[v.id][:n][both]
        if v.dtype == "cat":
            cats = v.categories
            k = max(len(xb), 1)
            db = np.bincount(xb, minlength=len(cats))[: len(cats)] / k
            da = np.bincount(xa, minlength=len(cats))[: len(cats)] / k
            j = int(np.argmax(np.abs(da - db)))
            rows[v.id] = {"kind": "cat", "base": dict(zip(cats, db.round(5).tolist())), "alt": dict(zip(cats, da.round(5).tolist())),
                          "tvd": float(np.abs(da - db).sum() / 2), "top": cats[j], "top_delta": float(da[j] - db[j]),
                          "effect": _cohen_h(float(db[j]), float(da[j])), "changed_share": float(np.mean(xb != xa)) if len(xb) else 0.0}
        elif v.dtype == "bool":
            pb, pa = float(xb.mean()) if len(xb) else 0.0, float(xa.mean()) if len(xa) else 0.0
            rows[v.id] = {"kind": "bool", "base": pb, "alt": pa, "delta": pa - pb, "effect": _cohen_h(pb, pa),
                          "changed_share": float(np.mean(xb != xa)) if len(xb) else 0.0}
        else:
            fb, fa = xb.astype(np.float64), xa.astype(np.float64)
            ok = np.isfinite(fb) & np.isfinite(fa)
            if not ok.any():
                continue
            mb, ma = float(fb[ok].mean()), float(fa[ok].mean())
            sd = float(fb[ok].std()) or 1.0
            ad = np.abs(fa[ok] - fb[ok])
            tol = 1e-6 + 1e-4 * (abs(mb) + sd)
            rows[v.id] = {"kind": "num", "base": mb, "alt": ma, "delta": ma - mb, "sd": sd, "effect": (ma - mb) / sd,
                          "changed_share": float(np.mean(ad > tol)), "mean_abs_change": float(ad.mean()) / sd}
    days = _attach_sparks(base, alt, rows)
    return {"day": base.w.day, "fork_day": getattr(alt, "meta_fork_day", 0), "n": int(both.sum()), "spark_days": days, "fields": rows}


def _attach_sparks(base, alt, rows: dict) -> list[int]:
    """Difference over time since the split, from the weekly field aggregates of both universes."""
    Fb, Fa = base.systems["recorder"].fields, alt.systems["recorder"].fields
    fork = getattr(alt, "meta_fork_day", 0)
    days = [d for d in Fb["days"] if d >= fork and d in set(Fa["days"])]
    ib = {d: k for k, d in enumerate(Fb["days"])}
    ia = {d: k for k, d in enumerate(Fa["days"])}
    gb, ga = Fb["groups"].get("all", {}), Fa["groups"].get("all", {})
    for v, r in rows.items():
        sb, sa = gb.get(v), ga.get(v)
        if sb is None or sa is None:
            continue
        out = []
        for d in days:
            xb, xa = sb[ib[d]], sa[ia[d]]
            if xb is None or xa is None:
                out.append(None)
            elif r["kind"] == "cat":
                out.append(round(float(np.abs(np.array(xa) - np.array(xb)).sum() / 2), 5))
            else:
                out.append(round(float(xa - xb), 6))
        r["spark"] = out
    for r in rows.values():
        r.setdefault("spark", [])
    return days


# ----------------------------------------------------------------------------- events, matched across worlds
def _event_keys(sim, since: int, n: int):
    """(index, key) of salient events since `since`, keyed by (person, day, type, other person)."""
    log, reg = sim.log, sim.reg
    sal = np.array([e.salience for e in reg.events.values()])
    idx = np.where((log["day"] >= since) & (sal[log["type"]] >= EVENT_SALIENCE) & (log["a"] >= 0) & (log["a"] < n))[0]
    a = log["a"][idx].astype(np.int64)
    key = ((a * 8192 + log["day"][idx].astype(np.int64)) * 512 + log["type"][idx].astype(np.int64)) * (n + 2) + (log["b"][idx].astype(np.int64) + 1)
    return idx, key


def event_differences(base, alt):
    """Salient events since the split that happened in only one world (indices into each log)."""
    n = min(base.w.P.n, alt.w.P.n)
    fork = getattr(alt, "meta_fork_day", 0)
    ib, kb = _event_keys(base, fork, n)
    ia, ka = _event_keys(alt, fork, n)
    only_b = ib[~np.isin(kb, ka)]
    only_a = ia[~np.isin(ka, kb)]
    return n, only_b, only_a


def _home(sim, i: int) -> str:
    """Where person i lives, in words (complex name, or the kind of home)."""
    P, w = sim.w.P, sim.w
    cx = int(P["complex_id"][i])
    if not P["present"][i]:
        return "not in Provo–Orem"
    if 0 <= cx < w.complexes.height:
        return str(w.complexes["name"][cx])
    return P.specs["living"].categories[int(P["living"][i])].replace("_", " ")


def _fmt(P, var, x):
    spec = P.specs[var]
    if var == "partner_id":
        return synthetic_name(P, int(x)) if x >= 0 else "nobody"
    if var == "unit_id":
        return f"home #{int(x)}" if x >= 0 else "no home here"
    if spec.dtype == "cat":
        return spec.categories[int(x)].replace("_", " ")
    if spec.dtype == "bool":
        return "yes" if x else "no"
    return round(float(x), 3)


def diverged_people(base, alt, k: int = 40) -> dict:
    """Who ended up living a different life: ranked by changed life states, one-world-only events and feelings."""
    Pb, Pa = base.w.P, alt.w.P
    n, only_b, only_a = event_differences(base, alt)
    eb = np.bincount(base.log["a"][only_b], minlength=n)[:n] if len(only_b) else np.zeros(n, int)
    ea = np.bincount(alt.log["a"][only_a], minlength=n)[:n] if len(only_a) else np.zeros(n, int)
    ever = Pb["present"][:n] | Pa["present"][:n]
    score = (eb + ea).astype(np.float64)
    state_diff = np.zeros(n, np.int32)
    for var, wgt in LIFE_STATES:
        if var not in Pb.specs:
            continue
        d = Pb[var][:n] != Pa[var][:n]
        score += wgt * d
        state_diff += d
    feel = np.abs(Pa["mood"][:n].astype(float) - Pb["mood"][:n].astype(float)) + np.abs(Pa["loneliness"][:n].astype(float) - Pb["loneliness"][:n].astype(float))
    score += 4.0 * np.nan_to_num(feel)
    score[~ever] = 0
    order = [int(i) for i in np.argsort(-score)[:k] if score[i] > 0.05]
    first_b = _first_by_person(base, only_b)
    first_a = _first_by_person(alt, only_a)
    people = []
    for i in order:
        diffs = []
        for var, _ in LIFE_STATES:
            if var not in Pb.specs or Pb[var][i] == Pa[var][i]:
                continue
            if var == "unit_id":
                hb, ha = _home(base, i), _home(alt, i)
                diffs.append({"var": var, "label": "Home", "base": hb if hb != ha else f"{hb} (one unit)", "alt": ha if hb != ha else f"{ha} (another unit)"})
            else:
                diffs.append({"var": var, "label": Pb.specs[var].label, "base": _fmt(Pb, var, Pb[var][i]), "alt": _fmt(Pa, var, Pa[var][i])})
        fd = None
        cand = [(r, w) for r, w in ((first_b.get(i), "base"), (first_a.get(i), "alt")) if r is not None]
        if cand:
            rec, world = min(cand, key=lambda c: c[0]["day"])
            fd = {"world": world, "day": rec["day"], "date": rec["date"], "label": rec["label"], "type": rec["type"]}
        people.append({"id": i, "name": synthetic_name(Pb, i), "score": round(float(score[i]), 3),
                       "headline_base": headline(base, i), "headline_alt": headline(alt, i),
                       "events_only_base": int(eb[i]), "events_only_alt": int(ea[i]),
                       "mood": [float(Pb["mood"][i]), float(Pa["mood"][i])], "loneliness": [float(Pb["loneliness"][i]), float(Pa["loneliness"][i])],
                       "diffs": diffs, "first_divergence": fd})
    life_diff = (((eb + ea) > 0) | (state_diff > 0)) & ever
    return {"n": int(ever.sum()), "with_event_diff": int(((eb + ea) > 0).sum()), "with_state_diff": int((state_diff > 0).sum()),
            "with_any_diff": int(life_diff.sum()), "with_feeling_diff": int(((np.nan_to_num(feel) > 0.05) & ever).sum()), "people": people}


def _first_by_person(sim, idx) -> dict:
    out = {}
    log = sim.log
    for e in idx:  # idx is in log order, i.e. time order
        a = int(log["a"][e])
        if a not in out:
            out[a] = event_record(sim, int(e))
    return out


def person_divergence(base, alt, i: int) -> dict:
    """One person's two lives since the split: events side by side, the first fork in the road and its causes,
    friends and partners gained or lost, and the states that differ now."""
    Pb, Pa = base.w.P, alt.w.P
    fork = getattr(alt, "meta_fork_day", 0)
    n, only_b, only_a = event_differences(base, alt)
    only_b = only_b[base.log["a"][only_b] == i]
    only_a = only_a[alt.log["a"][only_a] == i]
    sb, sa = set(only_b.tolist()), set(only_a.tolist())

    def life(sim, only):
        log, reg = sim.log, sim.reg
        sal = np.array([e.salience for e in reg.events.values()])
        m = np.where((log["a"] == i) & (log["day"] >= fork) & (sal[log["type"]] >= 0.45))[0][-120:]
        out = []
        for e in m:
            r = event_record(sim, int(e))
            r["only_here"] = int(e) in only
            r["a_name"] = synthetic_name(sim.w.P, r["a"])
            r["b_name"] = synthetic_name(sim.w.P, r["b"]) if r["b"] is not None else None
            out.append(r)
        return out

    def chain(sim, idx):
        if not len(idx):
            return None
        c = event_chain(sim, int(idx[0]), depth=10)
        for r in c:
            r["a_name"] = synthetic_name(sim.w.P, r["a"])
            r["b_name"] = synthetic_name(sim.w.P, r["b"]) if r["b"] is not None else None
        return c

    states = []
    for var, spec in Pb.specs.items():
        if spec.dtype == "str" or var in SKIP or var in ("activity_now",) or var.endswith("_day") or (var.endswith("_id") and var != "partner_id"):
            continue
        xb, xa = Pb[var][i], Pa[var][i]
        if spec.dtype in ("f4", "f8"):
            if np.isfinite(xb) and np.isfinite(xa) and abs(float(xa) - float(xb)) > 0.02 * (abs(float(xb)) + 0.5):
                states.append({"id": var, "label": spec.label, "domain": spec.domain, "base": float(xb), "alt": float(xa)})
        elif xb != xa:
            states.append({"id": var, "label": spec.label, "domain": spec.domain, "base": _fmt(Pb, var, xb), "alt": _fmt(Pa, var, xa)})
    if Pb["unit_id"][i] != Pa["unit_id"][i]:
        states.append({"id": "living", "label": "Home", "domain": "academics_work", "base": _home(base, i), "alt": _home(alt, i)})

    def ties(sim):
        E = sim.w.E
        lo, hi = E.endpoints()
        m = ((lo == i) | (hi == i)) & (E["stage"] >= 3)
        idx = np.where(m)[0]
        other = np.where(lo[idx] == i, hi[idx], lo[idx])
        return {int(o): int(e) for o, e in zip(other, idx)}

    tb, ta = ties(base), ties(alt)

    def tie_row(sim, o, e):
        E = sim.w.E
        fl = int(E["flags"][e])
        return {"id": o, "name": synthetic_name(sim.w.P, o), "stage": int(E["stage"][e]), "closeness": float(E["closeness"][e]),
                "romantic": bool(fl & (Tie.ROMANTIC | Tie.SPOUSE)), "met": CTX[int(E["origin_ctx"][e])] if int(E["origin_ctx"][e]) < len(CTX) else "?",
                "first_day": int(E["first_day"][e])}

    gained = sorted([tie_row(alt, o, e) for o, e in ta.items() if o not in tb], key=lambda r: -r["closeness"])
    lost = sorted([tie_row(base, o, e) for o, e in tb.items() if o not in ta], key=lambda r: -r["closeness"])
    first_b, first_a = (only_b[:1], only_a[:1])
    pb, pa = int(Pb["partner_id"][i]), int(Pa["partner_id"][i])
    return {"id": i, "name": synthetic_name(Pb, i), "fork_day": fork,
            "headline_base": headline(base, i), "headline_alt": headline(alt, i),
            "partner_base": {"id": pb, "name": synthetic_name(Pb, pb)} if pb >= 0 else None,
            "partner_alt": {"id": pa, "name": synthetic_name(Pa, pa)} if pa >= 0 else None,
            "states": states, "life_base": life(base, sb), "life_alt": life(alt, sa),
            "first_base": chain(base, first_b), "first_alt": chain(alt, first_a),
            "friends_gained": gained[:30], "friends_lost": lost[:30],
            "n_friends": [len(tb), len(ta)]}


# ----------------------------------------------------------------------------- relationships
def _couples(sim, n):
    P = sim.w.P
    pid = P["partner_id"][:n]
    i = np.where((pid >= 0) & (pid < n) & (np.arange(n) < pid))[0]
    cats = P.specs["rel_status"].categories
    return {(int(a), int(pid[a])): cats[int(P["rel_status"][a])] for a in i}


def compare_relationships(base, alt, k: int = 40) -> dict:
    """Couples and friendships that exist in only one of the two worlds."""
    n = min(base.w.P.n, alt.w.P.n)
    cb, ca = _couples(base, n), _couples(alt, n)
    Pb, Pa = base.w.P, alt.w.P

    def couple_row(sim, pair, status):
        a, b = pair
        E = sim.w.E
        e = int(E.find(np.array([E.make_keys(np.array([a]), np.array([b]))[0]]))[0])
        met = CTX[int(E["origin_ctx"][e])] if e >= 0 and int(E["origin_ctx"][e]) < len(CTX) else None
        return {"a": a, "b": b, "a_name": synthetic_name(sim.w.P, a), "b_name": synthetic_name(sim.w.P, b), "status": status, "met": met,
                "since": int(sim.w.P["rel_start_day"][a]) if "rel_start_day" in sim.w.P else None}

    only_a = [couple_row(alt, p, s) for p, s in ca.items() if p not in cb]
    only_b = [couple_row(base, p, s) for p, s in cb.items() if p not in ca]
    changed = [{**couple_row(alt, p, s), "status_base": cb[p]} for p, s in ca.items() if p in cb and cb[p] != s]
    rank = {"married": 0, "engaged": 1, "dating": 2, "talking": 3}
    for lst in (only_a, only_b):
        lst.sort(key=lambda r: (rank.get(r["status"], 9), -(r["since"] or 0)))

    def by_status(rows):
        out: dict = {}
        for r in rows:
            out[r["status"]] = out.get(r["status"], 0) + 1
        return out

    def friend_keys(sim):
        E = sim.w.E
        return E.key_array[E["stage"] >= 3].copy(), np.where(E["stage"] >= 3)[0]

    kb, ib = friend_keys(base)
    ka, ia = friend_keys(alt)
    fa_only = ia[~np.isin(ka, kb)]
    fb_only = ib[~np.isin(kb, ka)]

    def by_ctx(sim, idx):
        oc = sim.w.E["origin_ctx"][idx]
        cnt = np.bincount(oc, minlength=len(CTX))
        return {CTX[c]: int(cnt[c]) for c in range(len(CTX)) if cnt[c]}

    def friend_rows(sim, idx):
        E = sim.w.E
        idx = idx[np.argsort(-E["closeness"][idx])][:k]
        lo, hi = E.split(E.key_array[idx])
        return [{"a": int(a), "b": int(b), "a_name": synthetic_name(sim.w.P, int(a)), "b_name": synthetic_name(sim.w.P, int(b)),
                 "closeness": float(E["closeness"][e]), "met": CTX[int(E["origin_ctx"][e])] if int(E["origin_ctx"][e]) < len(CTX) else "?"}
                for a, b, e in zip(lo, hi, idx)]

    return {"couples": {"base": len(cb), "alt": len(ca), "only_alt": len(only_a), "only_base": len(only_b), "changed_status": len(changed),
                        "only_alt_by_status": by_status(only_a), "only_base_by_status": by_status(only_b),
                        "examples_alt": only_a[:k], "examples_base": only_b[:k], "examples_changed": changed[:k]},
            "friendships": {"base": int(len(kb)), "alt": int(len(ka)), "only_alt": int(len(fa_only)), "only_base": int(len(fb_only)),
                            "only_alt_by_met": by_ctx(alt, fa_only), "only_base_by_met": by_ctx(base, fb_only),
                            "examples_alt": friend_rows(alt, fa_only), "examples_base": friend_rows(base, fb_only)},
            "n": n}


# ----------------------------------------------------------------------------- places
def compare_places(base, alt, kind: str, var: str, min_n: int = 3) -> list[dict]:
    """Average of a field per place (complex, ward, neighborhood, school) in both worlds."""
    n = min(base.w.P.n, alt.w.P.n)
    rows = []

    def groups(sim):
        P, w = sim.w.P, sim.w
        pres = P["present"][:n]
        if kind == "complex":
            g, names = P["complex_id"][:n], list(w.complexes["name"])
        elif kind == "ward":
            g, names = P["ward_id"][:n], [f"{str(k).replace('_', ' ').upper()} ward #{j}" for j, k in enumerate(w.wards["kind"])]
        elif kind == "neighborhood":
            g, names = P["neighborhood"][:n].astype(np.int64), list(P.specs["neighborhood"].categories)
        elif kind == "school":
            g = np.where(P["enrolled"][:n], P["school"][:n].astype(np.int64), -1)
            names = ["none", "BYU", "UVU"]
        else:
            raise ValueError(kind)
        g = np.where(pres, g, -1)
        x = P[var][:n].astype(np.float64)
        ok = (g >= 0) & np.isfinite(x)
        m = len(names)
        cnt = np.bincount(g[ok], minlength=m)[:m]
        s = np.bincount(g[ok], weights=x[ok], minlength=m)[:m]
        return names, cnt, s, g

    names, nb, sb, gb = groups(base)
    _, na, sa, ga = groups(alt)
    moved = (gb != ga) & (gb >= 0)
    mv = np.bincount(gb[moved], minlength=len(names))[: len(names)]
    for j, name in enumerate(names):
        if max(nb[j], na[j]) < min_n or (kind == "neighborhood" and name == "Other"):
            continue
        mb = float(sb[j] / nb[j]) if nb[j] else None
        ma = float(sa[j] / na[j]) if na[j] else None
        rows.append({"id": j, "name": str(name), "n_base": int(nb[j]), "n_alt": int(na[j]), "base": mb, "alt": ma,
                     "delta": (ma - mb) if mb is not None and ma is not None else None, "moved_out": int(mv[j])})
    if kind == "complex":
        cx = base.w.complexes
        for r in rows:
            r["lon"], r["lat"] = float(cx["lon"][r["id"]]), float(cx["lat"][r["id"]])
    rows.sort(key=lambda r: -abs(r["delta"] or 0))
    return rows
