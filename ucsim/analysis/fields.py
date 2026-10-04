"""Field-level reads for the explorer: current summaries, timelines, one person's history, and the
"pulse" of the world (what's happening now) for the landing page."""
from __future__ import annotations

import numpy as np

from .explain import event_record
from .person import headline, synthetic_name

STAT_PCTS = (10, 25, 50, 75, 90)


def summary(sim, var_ids: list[str]) -> dict:
    """Current value of each field over the people present: mean/percentiles, or shares by category."""
    P = sim.w.P
    pres = P["present"].astype(bool)
    k = int(pres.sum())
    out = {}
    for v in var_ids:
        spec = P.specs[v]
        x = P[v][pres]
        if spec.dtype == "cat":
            cnt = np.bincount(x, minlength=len(spec.categories))[: len(spec.categories)]
            out[v] = {"kind": "cat", "shares": dict(zip(spec.categories, (cnt / max(k, 1)).round(5).tolist())),
                      "top": spec.categories[int(np.argmax(cnt))] if k else None}
        elif spec.dtype == "bool":
            out[v] = {"kind": "bool", "share": float(x.mean()) if k else None}
        else:
            xf = x.astype(np.float64)
            xf = xf[np.isfinite(xf)]
            if not len(xf):
                out[v] = {"kind": "num", "mean": None}
                continue
            p = np.percentile(xf, STAT_PCTS)
            out[v] = {"kind": "num", "mean": float(xf.mean()), "sd": float(xf.std()), "min": float(xf.min()), "max": float(xf.max()),
                      "p10": float(p[0]), "p25": float(p[1]), "p50": float(p[2]), "p75": float(p[3]), "p90": float(p[4]), "n": int(len(xf))}
    return {"n": k, "fields": out}


def timeline(sim, var: str, group: str = "all") -> dict | None:
    """Weekly group mean / shares (and percentiles for everyone) plus the daily series when one is recorded."""
    rec = sim.systems["recorder"]
    F = rec.fields
    G = F["groups"].get(group)
    if G is None or var not in G:
        return None
    spec = sim.w.P.specs[var]
    out = {"days": list(F["days"]), "n": list(G["n"])}
    if spec.dtype == "cat":
        cats = spec.categories
        out["shares"] = {c: [None if r is None else r[j] for r in G[var]] for j, c in enumerate(cats)}
    else:
        out["mean"] = list(G[var])
        if group == "all" and var in F["pct"]:
            out["pct"] = list(F["pct"][var])
    if var in rec.vars and rec.rows:
        rows = [r for r in rec.rows if r.get("group") == group]
        out["daily_days"] = [r["day"] for r in rows]
        if spec.dtype == "cat":
            out["daily_shares"] = {c: [r.get(f"{var}={c}") for r in rows] for c in spec.categories}
        else:
            out["daily_mean"] = [r.get(var) for r in rows]
    return out


def person_history(sim, i: int) -> dict:
    """One person's tracked states at every snapshot (every two weeks) plus now."""
    H, P = sim.systems["history"], sim.w.P
    days, present = [], []
    cats = {v: [] for v in H.cat_vars}
    nums = {v: [] for v in H.num_vars}
    snaps = [s for s in H.snaps if s["n"] > i]
    for s in snaps:
        if s["day"] >= sim.w.day:
            continue
        days.append(s["day"])
        here = bool(s["present"][i])
        present.append(here)
        for v in H.cat_vars:
            spec = P.specs[v]
            code = int(s[v][i])
            cats[v].append(None if not here else (spec.categories[code] if spec.dtype == "cat" else bool(code)))
        for v in H.num_vars:
            x = float(s[v][i])
            nums[v].append(round(x, 4) if here and np.isfinite(x) else None)
    # now
    days.append(sim.w.day)
    here = bool(P["present"][i])
    present.append(here)
    for v in H.cat_vars:
        spec = P.specs[v]
        cats[v].append(None if not here else (spec.categories[int(P[v][i])] if spec.dtype == "cat" else bool(P[v][i])))
    for v in H.num_vars:
        x = float(P[v][i])
        nums[v].append(round(x, 4) if here and np.isfinite(x) else None)
    return {"days": days, "dates": [str(sim.cal.date(d)) for d in days], "present": present, "cats": cats, "nums": nums}


def dedupe_pairs(events: list[dict]) -> list[dict]:
    """A wedding/engagement is logged once per partner; show each pair once."""
    seen, out = set(), []
    for e in events:
        k = f"{e['id']}" if e.get("b") is None else f"{e['type']}|{e['day']}|{min(e['a'], e['b'])}|{max(e['a'], e['b'])}"
        if k in seen:
            continue
        seen.add(k)
        out.append(e)
    return out


TREND_VARS = ["loneliness", "mood", "stress", "belonging", "dates_30d", "attend_rate", "faith_belief", "financial_stress",
              "romantic_longing", "n_friends", "n_close_friends", "rent_burden", "gpa", "anxiety", "purpose", "life_satisfaction"]
TREND_SHARES = [("rel_status", "married"), ("rel_status", "dating"), ("rel_status", "engaged"), ("activity", "active"),
                ("faith_crisis", None), ("depressive_episode", None), ("employed", None)]


def pulse(sim, featured: list | None = None) -> dict:
    """What's happening in the world right now: who's doing what, the week's events and headlines, and what's moving."""
    w, P, log, reg = sim.w, sim.w.P, sim.log, sim.reg
    pres = P["present"].astype(bool)
    act = P["activity_now"][pres]
    acats = P.specs["activity_now"].categories
    cnt = np.bincount(act, minlength=len(acats))
    doing = sorted([{"activity": acats[k], "n": int(cnt[k])} for k in range(len(acats)) if cnt[k] and acats[k] != "away"], key=lambda r: -r["n"])
    # a day in the life: where everyone was in each block of the last full day
    blocks = []
    fr = getattr(sim.systems.get("activity"), "day_frames", None) or {}
    for b, label in enumerate(("Morning", "Midday", "Evening", "Night")):
        if b not in fr:
            continue
        a = np.asarray(fr[b][2])
        m = pres[: len(a)]
        c = np.bincount(a[m], minlength=len(acats))
        blocks.append({"block": label, "doing": sorted([{"activity": acats[k], "n": int(c[k])} for k in range(len(acats))
                                                         if c[k] and acats[k] != "away"], key=lambda r: -r["n"])})
    names = reg.event_names
    sal = np.array([e.salience for e in reg.events.values()])

    def counts(since):
        m = log["day"] >= since
        c = np.bincount(log["type"][m], minlength=len(names))
        return sorted([{"type": names[k], "label": reg.events[names[k]].label, "category": reg.events[names[k]].category, "count": int(c[k])}
                       for k in np.nonzero(c)[0] if reg.events[names[k]].salience >= 0.4 and names[k] != "intervention_exposure"], key=lambda r: -r["count"])

    idx = np.where((sal[log["type"]] >= 0.8) & (log["a"] >= 0) & (log["day"] >= w.day - 14))[0][-400:][::-1]
    heads, per_type = [], {}
    for e in idx:  # newest first, at most three of a kind so one busy event type can't flood the news
        t = int(log["type"][e])
        if per_type.get(t, 0) >= 3:
            continue
        r = event_record(sim, int(e))
        r["a_name"] = synthetic_name(P, r["a"])
        r["b_name"] = synthetic_name(P, r["b"]) if r["b"] is not None else None
        heads.append(r)
        heads = dedupe_pairs(heads)
        per_type[t] = sum(1 for h in heads if h["type"] == r["type"])
        if len(heads) >= 16:
            break
    # what's moving: change over the last ~4 weeks, standardized
    trends = []
    rows = [r for r in sim.systems["recorder"].rows if r.get("group") == "all"]
    if len(rows) >= 2:
        now = rows[-1]
        then = next((r for r in rows if r["day"] >= now["day"] - 28), rows[0])
        span = now["day"] - then["day"]
        for v in TREND_VARS:
            if v not in now or now.get(v) is None or then.get(v) is None:
                continue
            x = P[v][pres].astype(np.float64)
            x = x[np.isfinite(x)]
            sd = float(x.std()) if len(x) else 1.0
            d = now[v] - then[v]
            trends.append({"var": v, "label": P.specs[v].label, "now": now[v], "then": then[v], "delta": d, "effect": d / (sd or 1.0),
                           "days": span, "kind": "num"})
        for v, c in TREND_SHARES:
            key = f"{v}={c}" if c else v
            if key not in now or now.get(key) is None or then.get(key) is None:
                continue
            p0, p1 = then[key], now[key]
            h = 2 * np.arcsin(np.sqrt(min(max(p1, 0), 1))) - 2 * np.arcsin(np.sqrt(min(max(p0, 0), 1)))
            lab = P.specs[v].label + (f": {c.replace('_', ' ')}" if c else "")
            trends.append({"var": v, "cat": c, "label": lab, "now": p1, "then": p0, "delta": p1 - p0, "effect": float(h), "days": span, "kind": "share"})
        trends.sort(key=lambda t: -abs(t["effect"]))
    return {"day": w.day, "hour": w.hour, "date": str(w.date), "weekday": w.date.strftime("%A"), "season": sim.cal.season(w.day),
            "present": int(pres.sum()), "doing": doing, "day_blocks": blocks,
            "day_blocks_date": str(sim.cal.date(int(fr["day"]))) if "day" in fr else None, "today": counts(w.day - 1), "week": counts(w.day - 7),
            "headlines": heads, "trends": trends[:8], "featured": featured or []}


def featured_people(sim, days: int = 30, k: int = 6) -> list[dict]:
    """Eventful lives lately: people with the most salient recent events, spread across life domains."""
    log, reg, P = sim.log, sim.reg, sim.w.P
    sal = np.array([e.salience for e in reg.events.values()])
    recent = (log["day"] >= sim.w.day - days) & (sal[log["type"]] >= 0.75) & (log["a"] >= 0)
    idx = np.where(recent)[0]
    if not len(idx):
        return []
    score = np.bincount(log["a"][idx], weights=sal[log["type"][idx]], minlength=P.n)
    score[~P["present"].astype(bool)] = 0
    cats = [e.category for e in reg.events.values()]
    out, used = [], set()
    for i in np.argsort(-score)[: 200]:
        if score[i] <= 0 or len(out) >= k:
            break
        mine = idx[log["a"][idx] == i]
        main_cat = cats[int(log["type"][mine[-1]])]
        if main_cat in used and len(used) < 4:
            continue  # prefer variety: romance, faith, school, family…
        used.add(main_cat)
        evs = [event_record(sim, int(e)) for e in mine[-4:][::-1]]
        for r in evs:
            r["a_name"] = synthetic_name(P, r["a"])
            r["b_name"] = synthetic_name(P, r["b"]) if r["b"] is not None else None
        out.append({"id": int(i), "name": synthetic_name(P, int(i)), "headline": headline(sim, int(i)), "events": evs, "theme": main_cat,
                    "mood": float(P["mood"][i]), "loneliness": float(P["loneliness"][i])})
    return out


def relationships(sim, status: str = "", limit: int = 60) -> dict:
    """Couples and the kinds of ties that hold the world together."""
    from ..engine.state import CTX, Tie
    P, E = sim.w.P, sim.w.E
    n = P.n
    pid = P["partner_id"][:n]
    rel = P.specs["rel_status"].categories
    a = np.where((pid >= 0) & (np.arange(n) < pid) & P["present"][:n])[0]
    st = np.array([rel[int(P["rel_status"][i])] for i in a]) if len(a) else np.array([], dtype=str)
    by_status = {s: int((st == s).sum()) for s in ("talking", "dating", "engaged", "married") if (st == s).any()}
    if status:
        a = a[st == status]
    since = P["rel_start_day"][a].astype(np.int64) if "rel_start_day" in P else np.full(len(a), -1)
    e_all = E.find(E.make_keys(a, pid[a])) if len(a) else np.array([], dtype=np.int64)
    met_day = np.where(e_all >= 0, E["first_day"][np.maximum(e_all, 0)], -1) if len(a) else np.array([])
    key = np.where(since >= 0, since, met_day)            # talking couples have no start day yet: use when they met
    order = np.argsort(-key, kind="stable")[:limit]
    eidx = e_all[order]
    couples = []
    for j, e in zip(order, eidx):
        i, k = int(a[j]), int(pid[a[j]])
        couples.append({"a": i, "b": k, "a_name": synthetic_name(P, i), "b_name": synthetic_name(P, k),
                        "status": rel[int(P["rel_status"][i])], "since": int(since[j]), "since_date": str(sim.cal.date(int(since[j]))) if since[j] >= 0 else None,
                        "met_date": str(sim.cal.date(int(met_day[j]))) if met_day[j] >= 0 else None,
                        "met": CTX[int(E["origin_ctx"][e])] if e >= 0 and int(E["origin_ctx"][e]) < len(CTX) else None,
                        "dates": int(E["dates"][e]) if e >= 0 else 0, "closeness": float(E["closeness"][e]) if e >= 0 else None})
    stage = E["stage"]
    fl = E["flags"]
    friends = stage >= 3
    types = {}
    for bit, name in Tie.NAMES.items():
        if name in ("preexisting", "dated", "ex", "kissed", "ncmo", "sexual", "app_match", "family"):
            continue
        c = int(((fl & bit) > 0)[friends].sum())
        if c:
            types[name] = c
    pres = P["present"].astype(bool)
    return {"couples_by_status": by_status, "couples": couples, "friendships": int(friends.sum()), "close": int((stage >= 4).sum()),
            "acquaintances": int((stage >= 1).sum()), "friends_by_type": dict(sorted(types.items(), key=lambda kv: -kv[1])),
            "mean_friends": float(P["n_friends"][pres].mean()) if pres.any() else 0.0,
            "mean_close": float(P["n_close_friends"][pres].mean()) if pres.any() else 0.0,
            "isolated": int(((P["n_friends"] == 0) & pres).sum())}
