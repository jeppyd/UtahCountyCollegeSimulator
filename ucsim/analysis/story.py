"""Stories: the recorded causes of the world, read as plain sentences.

Three readers over the same ledgers the Trace tool walks (nothing is invented, no model is called, no random numbers
are drawn):

* `why(sim, ref)` — the share of the push behind one thing. For a recorded choice it is the model's own terms: each
  factor's share of the total push, |term| / Σ|terms| (the base rate is reported apart, as is the chance it had), split
  into what pushed toward what happened and what pushed against it. For an event with no choice behind it, the
  weights of its recorded causes (the tie, the place, the earlier event, a feeling) are shared out the same way.
* `story(sim, i)` — one person's life as chapters (a new chapter at each month and at turning points such as a move
  or a relationship starting), one sentence per notable event with its top reasons, repeats folded together.
* `ripple(sim, ref)` — what one moment led to, as a tree of sentences ("…which led to…"), following the same
  forward links as Trace (choices, answers, introductions, where people met).

Shares are the model's reasons inside this simulated world, not real-world proof of cause.
"""
from __future__ import annotations

import numpy as np

from . import trace as T

# the turning points that start a new chapter of a story
TURNING = {"moved", "relationship_started", "breakup_received", "breakup_initiated", "engaged", "wedding",
           "mission_departure", "mission_return", "graduation", "left_church", "returned_to_activity",
           "honor_suspended", "birth"}
MIN_SHARE = 0.08          # reasons below this share are left out of a sentence (still listed by `why`)
MIRROR = "the same moment, for the other person"
GENERIC = {"led to this", "the choice behind it", ""}
STEPS = {"caused", "led_to", "attended", "decided_by"}     # link kinds that are a sequence, not a weighted push


def _sign_toward(D, d: dict) -> float:
    """+1 when a positive term pushed toward the outcome that happened, −1 when it pushed away from it."""
    spec = D.vocab.get(d["kind"], {})
    if d.get("units") != "logit":
        return 1.0
    pos = T.positive_outcome(spec, d["outcome"])
    return 1.0 if pos is None or str(pos) == str(d["outcome"]) else -1.0


def _decision_why(sim, did: int) -> dict | None:
    D = sim.decisions
    d = T.decision_detail(sim, did)
    if not d:
        return None
    s = _sign_toward(D, d)
    terms = [f for f in d["factors"] if f["factor"] != "base"]
    constraint = next((f for f in terms if f.get("constraint")), None)
    total = sum(abs(f["value"]) for f in terms if not f.get("constraint")) or 1.0
    toward, against = [], []
    for f in terms:
        if f.get("constraint"):
            continue
        item = {"label": f["label"], "words": f.get("words") or f["label"], "share": round(abs(f["value"]) / total, 3),
                "value": f["value"], "ref": f.get("ref"), "ref_label": f.get("ref_label")}
        (toward if f["value"] * s > 0 else against).append(item)
    toward.sort(key=lambda x: -x["share"])
    against.sort(key=lambda x: -x["share"])
    out = {"kind": "decision", "ref": f"decision:{did}", "title": f"{d['agent_name']}: {T.lc(d['label'])}",
           "outcome": str(d["outcome"]).replace("_", " "), "chance": d.get("prob"), "units": d.get("units"),
           "day": int(d["day"]), "date": d["date"], "toward": toward, "against": against,
           "base": next((f["value"] for f in d["factors"] if f["factor"] == "base"), d.get("base")),
           "other_name": d.get("other_name")}
    if constraint is not None:
        out["constraint"] = {"label": constraint["label"], "words": constraint.get("words") or constraint["label"]}
    return out


def _event_decision(sim, eid: int) -> int | None:
    log = sim.log
    did = int(log["decision"][eid]) if "decision" in log.cols else -1
    if did < 0:
        ids = sim.decisions.for_event(eid)
        did = int(ids[0]) if len(ids) else -1
    return did if did >= 0 and sim.decisions.get(did) else None


def why(sim, ref) -> dict:
    """The share of the push behind one event, choice or feeling (see the module docstring)."""
    kind, ident = T.parse_ref(ref)
    if kind == "decision":
        out = _decision_why(sim, int(ident))
        if out is None:
            raise KeyError(f"{ref} is not in the record")
        return out
    did = None
    if kind == "event":
        eid = int(ident)
        if not 0 <= eid < sim.log.n:
            raise KeyError(f"{ref} is not in the record")
        did = _event_decision(sim, eid)
        if did is not None:
            out = _decision_why(sim, did)
            out.update(kind="event", ref=f"event:{eid}", title=T._Words(sim).event_line(eid), decision=did)
            return out
    # no choice behind it: share out the weights of its recorded causes (one step back in the trace)
    g = T.trace(sim, ref, dir="back", depth=1, max_nodes=40)
    nodes = {n["key"]: n for n in g["nodes"]}
    root = nodes[g["root"]]
    links = [L for L in g["links"] if L["target"] == g["root"] and L.get("weight") is not None
             and L["words"] != MIRROR]
    first = next((L["source"] for L in g["links"] if L["target"] == g["root"] and L["words"] == MIRROR), None)
    if not links and first is not None and first != g["root"]:
        # the other person's copy of a two-person moment: its reasons are the first copy's
        out = why(sim, first)
        out.update(ref=g["root"], title=nodes[g["root"]].get("label", out["title"]))
        return out
    # what it simply followed from (the ask before a date, the trip before time at home) is not a share of a push
    after, other_choice = [], None
    for L in links:
        src = nodes.get(L["source"], {})
        if L["kind"] in STEPS or src.get("kind") == "occasion":
            if src.get("kind") == "decision" and other_choice is None:
                other_choice = int(src["ref"]["id"])
            elif src.get("kind") in ("event", "occasion"):
                after.append({"label": src.get("label", L["source"]), "ref": src.get("ref"), "day": src.get("day")})
    links = [L for L in links if L["kind"] not in STEPS and nodes.get(L["source"], {}).get("kind") != "occasion"]
    if not links and other_choice is not None:
        # it came from someone else's choice (an answer, an invitation): their reasons
        out = _decision_why(sim, other_choice)
        if out is not None:
            out.update(kind=kind, ref=g["root"], title=root.get("label", str(ref)), decision=other_choice, after=after,
                       by=T._Words(sim).name(sim.decisions.get(other_choice)["agent"]))
            return out
    total = sum(abs(L["weight"]) for L in links) or 1.0
    toward, against = [], []
    for L in links:
        src = nodes.get(L["source"], {})
        lab = src.get("label", L["source"])
        # an earlier moment or a plan reads best by itself; a place, tie or feeling with what it did
        named = src.get("kind") in ("event", "occasion", "decision", "person") or L["words"] in GENERIC
        lw = (L["words"] or "").split("; ")
        if named:
            words = lab
        elif src.get("kind") == "place":
            words = f"{lw[0]}: {T.lc(lab)}"
        else:
            words = " and ".join(lw[:2]) or lab
        item = {"label": lab, "words": words, "named": bool(named),
                "share": round(abs(L["weight"]) / total, 3), "value": L["weight"],
                "ref": src.get("ref"), "ref_label": src.get("label")}
        (against if L["weight"] < 0 and kind == "state" else toward).append(item)
    toward.sort(key=lambda x: -x["share"])
    against.sort(key=lambda x: -x["share"])
    return {"kind": kind, "ref": g["root"], "title": root.get("label", str(ref)), "day": root.get("day"),
            "date": str(sim.cal.date(int(root["day"]))) if root.get("day") is not None else None,
            "toward": toward, "against": against, "after": after, "chance": None, "units": "weight",
            "note": "No recorded choice behind this; the shares are the weights of what it is recorded to come from."
            + (" It followed from the moments listed under 'after'." if after else "")}


def _reasons(w: dict, k: int = 3) -> list[dict]:
    if w.get("constraint"):
        return [{"words": f"couldn't: {w['constraint']['words']}", "share": 1.0}]
    if not w.get("toward") and w.get("against") and w.get("chance") is not None:
        # everything recorded pushed the other way: it happened against the odds
        return [{"words": f"against the odds (the model gave it {round(100 * w['chance'])}%)", "share": None}]
    return [{"words": r["words"] if r.get("named") else T.lc(r["words"]), "share": r["share"]}
            for r in w["toward"][:k] if r["share"] >= MIN_SHARE and r["words"]]


def reason_text(reasons: list[dict]) -> str:
    if not reasons:
        return ""
    parts = [r["words"] if r["share"] is None else f"{r['words']} ({round(100 * r['share'])}%)" for r in reasons]
    return parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + " and " + parts[-1]


def story(sim, i: int, since: int | None = None, until: int | None = None, min_salience: float = 0.3,
          limit: int = 400) -> dict:
    """One person's life as chapters of sentences (see the module docstring)."""
    i = int(i)
    log = sim.log
    if not 0 <= i < sim.w.P.n:
        raise KeyError(f"no person {i}")
    W = T._Words(sim)
    names = sim.reg.event_names
    sal = T._salience(sim)
    rows = np.flatnonzero(log["a"] == i)
    if since is not None:
        rows = rows[log["day"][rows] >= since]
    if until is not None:
        rows = rows[log["day"][rows] <= until]
    rows = rows[sal[log["type"][rows]] >= min_salience]
    rows = rows[-limit:]
    chapters: list[dict] = []
    cur = None
    for e in rows.tolist():
        day = int(log["day"][e])
        typ = names[log["type"][e]]
        date = sim.cal.date(day)
        month = (date.year, date.month)
        if cur is None or (typ in TURNING and cur["lines"]) or cur["_month"] != month:
            title = date.strftime("%B %Y")
            if typ in TURNING:
                title = f"{title}: {T.lc(sim.reg.events[typ].label)}"
            cur = {"title": title, "start": day, "end": day, "lines": [], "_month": month, "_seen": {}}
            chapters.append(cur)
        cur["end"] = day
        b = int(log["b"][e])
        key = (typ, b)
        if key in cur["_seen"]:                         # the same thing again with the same person: fold it in
            line = cur["_seen"][key]
            line["times"] += 1
            line["last_day"] = day
            continue
        try:
            w = why(sim, f"event:{e}")
            rs = _reasons(w)
            chance = w.get("chance")
        except Exception:  # noqa: BLE001  (an older event whose details were thinned)
            w, rs, chance = {}, [], None
        aft = w.get("after", [])
        evs = [a for a in aft if (a.get("ref") or {}).get("kind") == "event"]
        line = {"after": [a["label"] for a in (evs or aft)][:2], "by": w.get("by"),"event": int(e), "day": day, "date": str(date), "type": typ, "category": sim.reg.events[typ].category,
                "text": W.event_line(e), "reasons": rs, "because": reason_text(rs), "chance": chance,
                "other": b if b >= 0 else None, "times": 1, "last_day": day, "salience": float(sal[log["type"][e]])}
        cur["_seen"][key] = line
        cur["lines"].append(line)
    for c in chapters:
        c.pop("_month")
        c.pop("_seen")
        c["date"] = str(sim.cal.date(c["start"]))
    return {"person": i, "name": W.name(i), "chapters": chapters, "n_events": int(len(rows)),
            "note": "Each reason's share is its part of the total push the model recorded for that moment."}


def ripple(sim, ref, depth: int = 6, max_nodes: int = 160) -> dict:
    """What one moment led to, as a tree of sentences (see the module docstring). Each moment hangs under the latest
    earlier moment it is recorded to come from, so a chain reads in order (met → asked out → first date)."""
    g = T.trace(sim, ref, dir="fwd", depth=depth, max_nodes=max_nodes)
    nodes = {n["key"]: n for n in g["nodes"]}
    links = list(g["links"])
    root = g["root"]
    # an event at a get-together, a date, an activity: what happened at that occasion follows from it too
    if root.startswith("event:"):
        back = T.trace(sim, root, dir="back", depth=1, max_nodes=30)
        for n in back["nodes"]:
            if n["kind"] == "occasion" and n.get("day") == nodes[root].get("day"):
                fw = T.trace(sim, n["key"], dir="fwd", depth=max(depth - 1, 1), max_nodes=max_nodes)
                for m in fw["nodes"]:
                    nodes.setdefault(m["key"], m)
                links += fw["links"] + [{"source": root, "target": n["key"], "kind": "attended", "words": "at", "weight": None}]
    log = sim.log
    W = T._Words(sim)
    # which nodes become sentences; ties become "met" lines when people met at or through something
    met = {L["target"]: L["kind"] for L in links if L["kind"] in ("met_at", "introduced") and L["target"] in nodes}
    answers = {L["target"] for L in links if "answer" in (L.get("words") or "")}

    def shown(k: str) -> bool:
        n = nodes[k]
        return k == root or n["kind"] in ("event", "occasion") or (n["kind"] == "tie" and k in met) \
            or (n["kind"] == "decision" and k in answers)

    def text(k: str) -> str:
        n = nodes[k]
        if k == root:
            return n.get("label", k)
        if n["kind"] == "tie":
            who = n.get("label", "").split(":")[0]
            return f"{who} {'were introduced' if met[k] == 'introduced' else 'met'}"
        if n["kind"] == "decision":
            d = sim.decisions.get(int(n["ref"]["id"]))
            if d:
                return f"{W.name(d['agent'])} said {str(d['outcome']).replace('_', ' ')}"
        return n.get("label", k)

    # the other person's copy of a two-person moment is the same moment
    mirror = {L["target"] for L in links if L.get("words") == MIRROR}
    ev = sorted(int(k.split(":")[1]) for k in nodes if k.startswith("event:") and k not in mirror)
    for k in list(nodes):
        if k.startswith("event:") and k != root and k not in mirror:
            e = int(k.split(":")[1])
            if any(T._is_mirror(log, f, e) for f in ev if f < e):
                mirror.add(k)
    keep = {k for k in nodes if shown(k) and k not in mirror and nodes[k]["kind"] != "state"}
    # incoming links (through bridges: places, people, plain ties) → candidate parents among the kept nodes
    inc: dict[str, list] = {}
    for L in links:
        if L["source"] in nodes and L["target"] in nodes:
            inc.setdefault(L["target"], []).append(L)

    def kept_sources(k: str, seen: set) -> list[tuple[str, str]]:
        out = []
        for L in inc.get(k, []):
            s_ = L["source"]
            if s_ in seen:
                continue
            seen.add(s_)
            words = "" if (L.get("words") or "") in GENERIC or L.get("words") == MIRROR else L["words"]
            if s_ in keep:
                out.append((s_, words))
            elif nodes[s_]["kind"] != "state":
                out += [(a, words or w_) for a, w_ in kept_sources(s_, seen)]
        return out

    day = lambda k: nodes[k].get("day") if nodes[k].get("day") is not None else -1   # noqa: E731
    parent: dict[str, tuple] = {}
    for k in keep - {root}:
        cands = [(a, w_) for a, w_ in kept_sources(k, {k}) if a != k and day(a) <= day(k)]
        if not cands:
            continue
        parent[k] = max(cands, key=lambda c: (day(c[0]), c[0] != root))
    # keep only what hangs from the root
    kids: dict[str, list] = {}
    for k, (pa, _w) in parent.items():
        kids.setdefault(pa, []).append(k)
    steps = []

    def walk(k: str, lvl: int, via: str, seen: set):
        n = nodes[k]
        steps.append({"key": k, "kind": n["kind"], "text": text(k), "day": n.get("day"),
                      "date": str(sim.cal.date(int(n["day"]))) if n.get("day") is not None else None,
                      "parent": parent[k][0] if k in parent else None, "level": lvl, "via": via,
                      "people": n.get("people", [])})
        for c in sorted(kids.get(k, []), key=lambda c: (day(c), c)):
            if c not in seen:
                seen.add(c)
                walk(c, lvl + 1, parent[c][1], seen)
    walk(root, 0, "", {root})
    return {"root": root, "steps": steps, "cut": g["cut"], "notes": g["notes"],
            "longest": max((s["level"] for s in steps), default=0)}
