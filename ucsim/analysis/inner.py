"""A person's inner life, assembled from real simulated state (nothing here is generated text).

What they care about and what is pulling at them now; what they believe and how that differs from reality;
what they remember; what they were trying to do and why plans changed; how they cope and what they have
learned works; what they learned about the world (expectations that shifted, with the memories behind the
shift); the shape of their week; and how they changed the social world around them.
"""
from __future__ import annotations

import numpy as np

from ..engine.state import EdgeStore, Tie
from ..engine.systems.coping import STRATEGIES, STRESSORS
from ..engine.systems.mind import MOTIVE_LABEL, MOTIVES
from .explain import event_record
from .person import synthetic_name


def _f(x) -> float | None:
    x = float(x)
    return round(x, 4) if np.isfinite(x) else None


def _pct(P, var: str, i: int, mask=None) -> float | None:
    x = P[var].astype(float)
    m = P["present"].astype(bool) if mask is None else mask
    xs = x[m & np.isfinite(x)]
    if not len(xs) or not np.isfinite(x[i]):
        return None
    return round(float((xs < x[i]).mean()), 3)


def motives(sim, i: int) -> list[dict]:
    P = sim.w.P
    sat = sim.systems["mind"].satisfactions()
    out = []
    for m in MOTIVES:
        out.append({"motive": m, "label": MOTIVE_LABEL[m], "cares": _f(P[f"cares_{m}"][i]), "fulfilled": _f(np.clip(sat[m][i], 0, 1)),
                    "drive": _f(P[f"drive_{m}"][i]), "cares_pct": _f(np.mean(P[f"cares_{m}"][P["present"].astype(bool)] < P[f"cares_{m}"][i]))})
    return sorted(out, key=lambda d: -(d["drive"] or 0))


def beliefs(sim, i: int) -> list[dict]:
    """Where what they believe and what is true come apart."""
    P, E = sim.w.P, sim.w.E
    out = [{"what": "Support they could count on", "believed": _f(P["perceived_support"][i]), "actual": _f(P["support_actual"][i]),
            "note": "What they believe is there buffers stress and loneliness; the actual figure is what their close ties could give."}]
    if P["lds_member"][i]:
        out.append({"what": "How strongly their friends believe", "believed": _f(P["perceived_friend_belief"][i]),
                    "actual": _f(P["friend_belief_actual"][i]),
                    "note": "Friends who have not confided show the belief they express, pulled toward the local norm."})
    if P["enrolled"][i] or np.isfinite(P["gpa"][i]):
        abil = sim.z("academic_ability")[i]
        out.append({"what": "Academic ability (confidence vs. measured, as a percentile)", "believed": _f(P["self_eff_academic"][i]),
                    "actual": _f(float((sim.z("academic_ability")[P["present"].astype(bool)] < abil).mean())),
                    "note": "Confidence moves with grades relative to classmates; ability is the trait that drives grades."})
    # expected vs experienced yes-rate on asks
    log = sim.log
    code_ask = sim.reg.event_ids["asked_out"]
    code_rej = sim.reg.event_ids["rejected"]
    asks = int(((log["type"] == code_ask) & (log["a"] == i)).sum())
    if asks:
        rej_m = (log["type"] == code_rej) & (log["a"] == i) & (log["mech"] == log.mech_ids.get("romance.accept", -9))
        out.append({"what": "Chance an ask gets a yes", "believed": _f(P["expect_accept"][i]), "actual": _f(1 - rej_m.sum() / asks),
                    "note": f"Learned from their {asks} ask{'s' if asks != 1 else ''}; rejection-sensitive people learn more from a no."})
    # crush: own feelings, what they think the other feels, what the other actually feels
    crush = int(P.internal["crush_id"][i]) if "crush_id" in P.internal else -1
    if crush >= 0:
        e = E.find(EdgeStore.make_keys(np.array([i]), np.array([crush])))
        if e[0] >= 0:
            own = float(E.attraction_from(e, np.array([i]))[0])
            bel = float(E.belief_from(e, np.array([i]))[0])
            act = float(E.attraction_from(e, np.array([crush]))[0])
            out.append({"what": f"Whether {synthetic_name(P, crush).split()[0]} is interested", "believed": _f(bel), "actual": _f(act),
                        "own": _f(own), "other": crush, "other_name": synthetic_name(P, crush),
                        "note": "Their read of the other's interest (−1 to 1) mixes real signals with projection of their own feelings."})
    for d in out:
        if d["believed"] is not None and d["actual"] is not None:
            d["gap"] = round(d["believed"] - d["actual"], 3)
    return out


def memories(sim, i: int, k: int = 12) -> list[dict]:
    mem = sim.memory
    decay = sim.p("memory.forgetting.decay")
    rows = mem.recall(i, sim.w.day, decay, k=k, rehearse=False)
    st = mem.strength(sim.w.day, decay) if rows else None
    out = []
    P = sim.w.P
    for r in rows:
        ev = event_record(sim, int(mem["event"][r]))
        if ev.get("b") is not None:
            ev["b_name"] = synthetic_name(P, ev["b"])
        out.append({"event": ev, "valence": _f(mem["valence"][r]), "importance": _f(mem["importance"][r]),
                    "strength": _f(st[r]), "rehearsed": int(mem["rehearsal"][r]), "core": bool(mem["importance"][r] >= 0.8)})
    return out


def coping(sim, i: int) -> dict:
    P, log = sim.w.P, sim.log
    strat = int(P["coping_strategy"][i])
    learned = {s: _f(P.internal[f"cope_v_{s}"][i]) for s in STRATEGIES[1:]}
    code_s, code_e = sim.reg.event_ids["coping_started"], sim.reg.event_ids["coping_ended"]
    m = np.where((log["a"] == i) & np.isin(log["type"], [code_s, code_e]))[0][-16:]
    episodes = []
    for e in m:
        rec = event_record(sim, int(e))
        if rec["type"] == "coping_started":
            rec["strategy"] = STRATEGIES[int(round(rec["value"]))]
            if rec.get("cause") is not None:
                rec["trigger"] = event_record(sim, rec["cause"])
        else:
            rec["outcome"] = rec["value"]
        episodes.append(rec)
    return {"strategy": STRATEGIES[strat], "need": _f(P["coping_need"][i]), "relief": _f(P["coping_relief"][i]),
            "stressor": STRESSORS[int(P.internal["cope_stressor"][i])] if strat else None,
            "since": int(P.internal["cope_start"][i]) if strat else None, "rumination": _f(P["rumination"][i]),
            "learned": learned, "episodes": episodes}


def lessons(sim, i: int) -> list[dict]:
    """Expectations that shifted most over their history, with the memories formed in that stretch."""
    hist = sim.systems["history"]
    out = []
    spec = {"expect_social": ("how warm people are", "connection"), "expect_accept": ("whether asks get a yes", "partnership"),
            "self_eff_academic": ("their academic ability", "achievement"), "perceived_support": ("the support they have", "connection")}
    if not hist.snaps:
        return out
    days = hist.days()
    for var, (what, motive) in spec.items():
        if not hist.tracked(var):
            continue
        series = []
        for s in hist.snaps:
            if i < s["n"] and s["present"][i]:
                series.append((s["day"], float(s[var][i])))
        series.append((sim.w.day, float(sim.w.P[var][i])))
        if len(series) < 3:
            continue
        vals = np.array([v for _, v in series])
        lo, hi = int(np.argmin(vals)), int(np.argmax(vals))
        a, b = (lo, hi) if lo < hi else (hi, lo)
        change = vals[b] - vals[a]
        if abs(change) < 0.08:
            continue
        d0, d1 = series[a][0], series[b][0]
        mem = sim.memory
        rows = np.where((mem["agent"] == i) & (mem["day"] >= d0) & (mem["day"] <= d1))[0]
        rows = rows[np.array([mem.motive_of[t] == motive for t in mem["etype"][rows]], bool)] if len(rows) else rows
        rows = rows[np.argsort(-mem["importance"][rows].astype(float))][:3] if len(rows) else rows
        out.append({"about": what, "var": var, "from": round(vals[a], 3), "to": round(vals[b], 3), "start_day": int(d0), "end_day": int(d1),
                    "direction": "up" if change > 0 else "down", "because": [event_record(sim, int(mem["event"][r])) for r in rows]})
    del days
    return sorted(out, key=lambda d: -abs(d["to"] - d["from"]))


def footprint(sim, i: int) -> dict:
    """How this person changed the social world around them."""
    P, E, log = sim.w.P, sim.w.E, sim.log
    intro = np.where(E["introducer"] == i)[0]
    lo, hi = E.endpoints()
    introduced_friends = int((E["stage"][intro] >= 3).sum())
    hosted = int(((log["type"] == sim.reg.event_ids["hosted_gathering"]) & (log["a"] == i)).sum())
    mine = (lo == i) | (hi == i)
    supported = int((mine & (E["support"] > 0)).sum())
    unit = int(P["unit_id"][i])
    out = {"introductions": int(len(intro)), "introductions_became_friends": introduced_friends, "gatherings_hosted": hosted,
           "ties_with_support": supported, "people_known": int(mine.sum()),
           "friends_made_here": int((mine & (E["stage"] >= 3) & ((E["flags"] & Tie.PREEXISTING) == 0)).sum())}
    C = sim.w.meta.get("culture")
    if C and unit >= 0:
        out["apartment_sociability_z"] = _f(P["home_social_culture"][i])
    return out


def inner_life(sim, i: int) -> dict:
    P = sim.w.P
    plans = sim.systems["plans"].for_agent(i)
    for pl in plans:
        if pl["target"] is not None:
            pl["target_name"] = synthetic_name(P, pl["target"])
        if pl["event"] is not None:
            pl["event_record"] = event_record(sim, pl["event"])
    return {"id": i, "day": int(sim.w.day), "top_priority": P.labels("top_priority", P["top_priority"][i:i + 1])[0],
            "motives": motives(sim, i), "beliefs": beliefs(sim, i), "expectations": {
                "expect_accept": _f(P["expect_accept"][i]), "expect_social": _f(P["expect_social"][i]),
                "self_eff_academic": _f(P["self_eff_academic"][i])},
            "memories": memories(sim, i), "memory": {"count": int(P["n_memories"][i]), "tone": _f(P["memory_tone"][i])},
            "intention": P.labels("intention", P["intention"][i:i + 1])[0], "plans": plans,
            "plans_kept": int(P["plans_kept"][i]), "plans_abandoned": int(P["plans_abandoned"][i]),
            "coping": coping(sim, i), "lessons": lessons(sim, i), "routine": sim.systems["routine"].for_agent(i),
            "routine_strength": _f(P["routine_strength"][i]), "footprint": footprint(sim, i),
            "home_culture": {"sociability_z": _f(P["home_social_culture"][i]), "observance": _f(P["home_faith_culture"][i])}}
