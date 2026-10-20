"""Deterministic fact builders: typed claims a model may phrase but never add to.

A claim is {id, kind: fact|perception|cause|measurement|belief, subject: Ref, text, value?, band?, field?, refs: [Ref],
share?, count?, numbers?, licenses?} where a Ref is {kind: person|place|event|tie|group|decision, id, name?}. The text is
a plain sentence a person could read; `band` is the value's words on its scale (ucsim/scales.py); `share` marks a
decomposition share (the checker accepts causal wording for a share ≥ check.CAUSE_SHARE); `licenses` lists fields a
group count is defined by ("lonely" = loneliness ≥ 0.5).

Two sources: a person's dossier for interviews (what they perceive and remember — never anyone else's hidden state,
and no sensitive fields unless asked), and a fixed set of world query tools for Ask the world.
"""
from __future__ import annotations

import numpy as np

from ...analysis.person import synthetic_name
from ucsim.population.structure import ward_name

# Always left out of interviews unless the owner turns sensitive topics on (besides YAML `flags: [sensitive]`).
SENSITIVE_VARS = {"porn_use", "n_sex_partners", "premarital_sex_current", "ever_cheated", "ever_cheated_on"}
SENSITIVE_EVENTS = {"premarital_sex", "ncmo", "cheating", "crossed_own_line", "intimacy_step", "dealbreaker_found",
                    "dealbreaker_overlooked", "bishop_porn_talk", "bishop_confession", "kyhv_peak"}
SENSITIVE_CATEGORIES = {"sexuality"}
FEELINGS = ("mood", "loneliness", "stress", "anxiety", "guilt", "belonging", "self_esteem", "romantic_longing", "purpose")


def is_sensitive(reg, var: str) -> bool:
    v = reg.variables.get(var)
    return var in SENSITIVE_VARS or bool(v and "sensitive" in (v.flags or []))


def event_sensitive(sim, etype: str) -> bool:
    spec = sim.reg.events.get(etype)
    return etype in SENSITIVE_EVENTS or bool(spec and spec.category in SENSITIVE_CATEGORIES)


def person_ref(sim, i: int) -> dict:
    return {"kind": "person", "id": int(i), "name": synthetic_name(sim.w.P, int(i))}


def _r(x, k: int = 3):
    x = float(x)
    return round(x, k) if np.isfinite(x) else None


class Sheet:
    """A growing fact sheet (claim ids are short and stable within one answer)."""

    def __init__(self):
        self.claims: dict[str, dict] = {}
        self.n = 0

    def add(self, kind: str, subject: dict, text: str, **kw) -> str:
        self.n += 1
        cid = f"{kind[0]}{self.n}"
        c = {"id": cid, "kind": kind, "subject": subject, "text": text, "refs": kw.pop("refs", [])}
        c.update({k: v for k, v in kw.items() if v is not None})
        self.claims[cid] = c
        return cid

    def merge(self, other: "Sheet"):
        for c in other.claims.values():
            self.add(c["kind"], c["subject"], c["text"], **{k: v for k, v in c.items() if k not in ("id", "kind", "subject", "text")})

    def as_list(self) -> list[dict]:
        return list(self.claims.values())


# ---------------------------------------------------------------------------------------------- words for values
def band(sim, var: str, value) -> str | None:
    from ... import scales
    v = sim.reg.variables.get(var)
    if v is None or value is None or not np.isfinite(float(value)):
        return None
    try:
        return scales.anchor_words(scales.scale_for(v), float(value)) or None
    except Exception:  # noqa: BLE001
        return None


def label(sim, var: str) -> str:
    v = sim.reg.variables.get(var)
    return (v.label if v else var.replace("_", " ")).lower()


def field_claim(sim, sh: Sheet, i: int, var: str, kind: str = "fact", who: dict | None = None) -> str | None:
    P = sim.w.P
    if var not in P.cols:
        return None
    x = P[var][i]
    if P.specs.get(var) is not None and P.specs[var].dtype == "bool":
        val = bool(x)
        who = who or person_ref(sim, i)
        return sh.add(kind, who, f"{who['name']}: {label(sim, var)} — {'yes' if val else 'no'}.", field=var, value=float(val))
    try:
        val = float(x)
    except (TypeError, ValueError):
        return None
    if not np.isfinite(val):
        return None
    who = who or person_ref(sim, i)
    v = sim.reg.variables.get(var)
    if v is not None and v.ordinal and v.dtype in ("u1", "i2") and 0 <= int(val) < len(v.ordinal):
        words = v.ordinal[int(val)]
        return sh.add(kind, who, f"{who['name']}'s {label(sim, var)}: {words}.", field=var, value=val, band=words)
    if v is not None and v.categories and 0 <= int(val) < len(v.categories):
        words = str(P.labels(var, P[var][i:i + 1])[0]).replace("_", " ")
        return sh.add(kind, who, f"{who['name']}'s {label(sim, var)}: {words}.", field=var, value=val, band=words)
    b = band(sim, var, val)
    return sh.add(kind, who, f"{who['name']}'s {label(sim, var)} is {val:.2f}" + (f" ({b})." if b else "."),
                  field=var, value=round(val, 3), band=b)


def event_line(sim, eid: int) -> str:
    from ...analysis.trace import _Words
    try:
        return _Words(sim).event_line(int(eid))
    except Exception:  # noqa: BLE001
        from ...analysis.explain import event_record
        return event_record(sim, int(eid))["label"]


# ---------------------------------------------------------------------------------------------- the interview dossier
def dossier(sim, i: int, sensitive: bool = False) -> Sheet:
    """What person i knows about their own life: their feelings, what they believe (perceived side only), their
    relationships as they see them, what they remember (read without rehearsing), what they intend, how they cope,
    and the reasons behind their own recent choices."""
    from ...analysis import inner
    P, E = sim.w.P, sim.w.E
    sh = Sheet()
    me = person_ref(sim, i)
    sh.add("fact", me, f"{me['name']} is {int(P['age'][i])} years old.", field="age", value=float(int(P["age"][i])))
    for var in ("school", "rel_status", "activity", "living", "study_area"):
        if var in P.cols:
            field_claim(sim, sh, i, var)
    part = int(P["partner_id"][i])
    if part >= 0:
        pr = person_ref(sim, part)
        sh.add("fact", me, f"{me['name']}'s partner is {pr['name']}.", refs=[pr])
        field_claim(sim, sh, i, "relationship_satisfaction")
    for var in FEELINGS + ("faith_belief",):
        if var in P.cols and not is_sensitive(sim.reg, var):
            field_claim(sim, sh, i, var)
    # beliefs: what they believe, not what is true (the difference is shown separately, computed here, not by a model)
    for var in ("perceived_support", "perceived_friend_belief", "self_eff_academic", "expect_accept", "expect_social"):
        if var in P.cols and (var != "perceived_friend_belief" or P["lds_member"][i]):
            field_claim(sim, sh, i, var, kind="perception")
    # what pulls at them
    for m in inner.motives(sim, i)[:3]:
        if (m["drive"] or 0) > 0.05:
            sh.add("perception", me, f"Right now {me['name']} feels the pull of {m['label'].lower()} most "
                                     f"(drive {m['drive']:.2f}).", field=f"drive_{m['motive']}", value=m["drive"])
    # relationships as they see them: their closest ties
    lo, hi = E.endpoints()
    mine = np.flatnonzero((lo == i) | (hi == i))
    if len(mine):
        mine = mine[np.argsort(-E["closeness"][mine].astype(float))][:6]
        stage_words = {1: "an acquaintance", 2: "a friendly acquaintance", 3: "a friend", 4: "a close friend"}
        for e in mine:
            other = int(hi[e] if lo[e] == i else lo[e])
            o = person_ref(sim, other)
            st = int(E["stage"][e])
            what = "their partner" if other == part else stage_words.get(st, "someone they know")
            c = float(E["closeness"][e])
            b = band(sim, "closeness", c)
            sh.add("perception", me, f"{me['name']} sees {o['name']} as {what} (closeness {c:.2f}" + (f", {b})." if b else ")."),
                   refs=[o, {"kind": "tie", "id": f"{min(i, other)}-{max(i, other)}"}], field="closeness", value=round(c, 3))
    # memories (a non-rehearsing read: interviewing someone never strengthens what they remember)
    for m in inner.memories(sim, i, k=8):
        ev = m["event"]
        if event_sensitive(sim, ev["type"]) and not sensitive:
            continue
        refs = [{"kind": "event", "id": ev["id"]}]
        if ev.get("b") is not None:
            refs.append(person_ref(sim, ev["b"]))
        sh.add("fact", me, f"{me['name']} remembers: {event_line(sim, ev['id'])} ({ev['date']}).", refs=refs,
               value=None, numbers=[ev["day"]])
    # intentions and coping
    if "intention" in P.cols:
        it = str(P.labels("intention", P["intention"][i:i + 1])[0])
        if it and it != "none":
            sh.add("belief", me, f"{me['name']} intends to {it.replace('_', ' ')}.")
    cp = inner.coping(sim, i)
    if cp["strategy"] and cp["strategy"] != "none":
        sh.add("fact", me, f"{me['name']} is coping by {cp['strategy'].replace('_', ' ')}"
                           + (f" (mostly about {cp['stressor'].replace('_', ' ')})." if cp.get("stressor") else "."))
    # their own recent choices and the main reason for each
    _decisions(sim, sh, i, me, since=sim.w.day - 90, sensitive=sensitive)
    return sh


def _decisions(sim, sh: Sheet, i: int, me: dict, since: int, sensitive: bool, limit: int = 6):
    try:
        from ...analysis.trace import person_decisions
    except Exception:  # noqa: BLE001
        return
    sens_kinds = {"cheat", "intimacy_step", "dealbreaker_reaction"}
    for d in person_decisions(sim, i, since=since, limit=40):
        if len([c for c in sh.claims.values() if c["kind"] == "cause"]) >= limit:
            break
        if d["kind"] in sens_kinds and not sensitive:
            continue
        top = d.get("top")
        if not top or top.get("constraint"):
            continue
        refs = [{"kind": "decision", "id": d["id"]}]
        if d.get("other") is not None:
            refs.append(person_ref(sim, d["other"]))
        who = f" ({d['other_name']})" if d.get("other_name") else ""
        sh.add("cause", me, f"{d['label']}{who} on {sim.cal.date(int(d['day']))}: {d['outcome']}, mostly because of "
                            f"{top['words']}.", refs=refs)


def view_vs_truth(sim, i: int) -> list[dict]:
    """Where their view differs from what's true (inner_life's perceived vs actual; deterministic)."""
    from ...analysis import inner
    out = []
    for b in inner.beliefs(sim, i):
        if b.get("believed") is None or b.get("actual") is None:
            continue
        gap = b["believed"] - b["actual"]
        if abs(gap) < 0.1:
            continue
        out.append({"what": b["what"], "believed": b["believed"], "actual": b["actual"], "gap": round(gap, 3),
                    "words": f"{'Thinks it is higher' if gap > 0 else 'Thinks it is lower'} than it really is", "note": b.get("note")})
    return out


# ---------------------------------------------------------------------------------------------- world query tools
TOOLS = {
    "find_people": {"desc": "Count people matching a filter (the cohort filter DSL) and name a few of them.",
                    "args": {"filter": "a filter, e.g. {\"and\":[{\"var\":\"school\",\"op\":\"eq\",\"value\":\"BYU\"},{\"var\":\"loneliness\",\"op\":\"ge\",\"value\":0.5}]}",
                             "what": "a few words naming the group, e.g. 'lonely BYU students'"}},
    "rank_places": {"desc": "Rank apartment complexes or wards by the average of a measure among the people there.",
                    "args": {"kind": "complex or ward", "var": "a person measure, e.g. loneliness", "order": "high or low", "k": "how many (≤ 8)"}},
    "event_counts": {"desc": "How many events of some types happened in a window of days.",
                     "args": {"types": "event type ids, e.g. [\"breakup_initiated\"]", "since": "first day (number)", "until": "last day"}},
    "explain_feeling": {"desc": "Why one person feels the way they do: the parts of a feeling and the events behind it.",
                        "args": {"person": "person id", "var": "a feeling, e.g. loneliness, stress, mood"}},
    "why_changed": {"desc": "For a group, what a measure is made of now (mechanism terms as shares).",
                    "args": {"filter": "a filter", "var": "a feeling", "what": "the group in words"}},
    "most_affected": {"desc": "Who the running What-if changed most on a measure (needs a What-if world).",
                      "args": {"var": "a person measure", "k": "how many (≤ 8)"}},
    "person": {"desc": "The basic facts and feelings of one person.", "args": {"person": "person id"}},
    "trace": {"desc": "What led to an event (its causes, a few steps back).", "args": {"event": "event id"}},
}


def run_tool(ws, name: str, args: dict, u: str = "base", sensitive: bool = True) -> Sheet:
    """Run one query tool against a world (callers hold WS.lock). Unknown tools and bad arguments raise ValueError."""
    sim = ws.sim(u) if hasattr(ws, "sim") else ws
    fn = {"find_people": _find_people, "rank_places": _rank_places, "event_counts": _event_counts,
          "explain_feeling": _explain_feeling, "why_changed": _why_changed, "person": _person, "trace": _trace}.get(name)
    if name == "most_affected":
        alt = getattr(ws, "alt", None)
        if alt is None or getattr(ws, "base", None) is None:
            raise ValueError("there is no What-if world running")
        return _most_affected(ws.base, alt, args)
    if fn is None:
        raise ValueError(f"unknown tool {name!r}")
    if not isinstance(args, dict):
        raise ValueError("arguments must be an object")
    var = args.get("var")
    if var is not None and is_sensitive(sim.reg, str(var)) and not sensitive:
        raise ValueError(f"{var} is a sensitive field")
    return fn(sim, args)


def _var(sim, args, default="loneliness") -> str:
    var = str(args.get("var") or default)
    if var not in sim.w.P.cols:
        raise ValueError(f"no measure named {var!r}")
    return var


def _find_people(sim, args) -> Sheet:
    from ...analysis.query import describe_filter, evaluate_filter
    P = sim.w.P
    filt = args.get("filter") or {"all": True}
    m = evaluate_filter(sim.w, filt, sim)
    pres = P["present"][: P.n].astype(bool)
    n, tot = int(m.sum()), int(pres.sum())
    what = str(args.get("what") or describe_filter(filt))[:120]
    sh = Sheet()
    group = {"kind": "group", "id": "filter", "name": what}
    fields = sorted({c.get("var") for c in _conds(filt) if c.get("var") in P.cols})
    share = n / max(tot, 1)
    sh.add("measurement", group, f"{n:,} of {tot:,} people ({100 * share:.0f}%) are {what}.", value=round(share, 4),
           count=n, numbers=[tot], licenses=fields, filter=filt)
    ids = np.flatnonzero(m)
    if len(ids):
        pick = ids[np.linspace(0, len(ids) - 1, min(5, len(ids))).astype(int)]
        for i in pick:
            pr = person_ref(sim, int(i))
            sh.add("fact", pr, f"{pr['name']} is one of the {what}.", licenses=fields)
    return sh


def _conds(f):
    if isinstance(f, dict):
        yield f
        for k in ("and", "or"):
            for g in f.get(k, []) or []:
                yield from _conds(g)
        if isinstance(f.get("not"), dict):
            yield from _conds(f["not"])


def _rank_places(sim, args) -> Sheet:
    P, w = sim.w.P, sim.w
    kind = "ward" if str(args.get("kind")) == "ward" else "complex"
    var = _var(sim, args)
    k = int(min(max(int(args.get("k") or 5), 1), 8))
    col = "ward_id" if kind == "ward" else "complex_id"
    pres = P["present"][: P.n].astype(bool) & (P[col][: P.n] >= 0)
    gid = P[col][: P.n][pres]
    x = P[var][: P.n][pres].astype(float)
    ok = np.isfinite(x)
    nn = np.bincount(gid[ok], minlength=int(gid.max()) + 1 if len(gid) else 1)
    s = np.bincount(gid[ok], weights=x[ok], minlength=len(nn))
    elig = np.flatnonzero(nn >= 8)
    if not len(elig):
        raise ValueError("no place has enough residents")
    mean = s[elig] / nn[elig]
    order = np.argsort(mean if str(args.get("order")) == "low" else -mean)[:k]
    sh = Sheet()
    words = "lowest" if str(args.get("order")) == "low" else "highest"
    for rank, o in enumerate(order, 1):
        g = int(elig[o])
        name = str(w.complexes["name"][g]) if kind == "complex" else ward_name(w.wards, g)
        ref = {"kind": "place", "id": f"{kind}:{g}", "name": name}
        b = band(sim, var, mean[o])
        sh.add("measurement", ref, f"{name}: average {label(sim, var)} {mean[o]:.2f}" + (f" ({b})" if b else "")
               + f" among {int(nn[g])} residents — number {rank} ({words}) of {len(elig)} {kind + ('es' if kind == 'complex' else 's')} with 8 or more residents.",
               field=var, value=round(float(mean[o]), 3), band=b, numbers=[int(nn[g]), rank, len(elig)])
    return sh


def _event_counts(sim, args) -> Sheet:
    log = sim.log
    types = args.get("types") or []
    types = [types] if isinstance(types, str) else list(types)
    ids = [sim.reg.event_ids[t] for t in types if t in sim.reg.event_ids]
    if not ids:
        raise ValueError("name event types, e.g. breakup_initiated, engaged, first_date")
    d0 = int(args.get("since") if args.get("since") is not None else max(sim.w.day - 30, 0))
    d1 = int(args.get("until") if args.get("until") is not None else sim.w.day)
    day, typ = log["day"][: log.n], log["type"][: log.n]
    sh = Sheet()
    for t, k in zip(types, ids):
        n = int(((typ == k) & (day >= d0) & (day <= d1)).sum())
        lbl = sim.reg.events[t].label.lower()
        sh.add("measurement", {"kind": "group", "id": f"events:{t}", "name": lbl},
               f"{n:,} events \"{lbl}\" between {sim.cal.date(d0)} and {sim.cal.date(d1)} (days {d0}–{d1}).",
               value=float(n), count=n, numbers=[d0, d1])
    return sh


def _explain_feeling(sim, args) -> Sheet:
    from ...analysis.explain import explain_state
    i = int(args.get("person"))
    var = _var(sim, args)
    sh = Sheet()
    me = person_ref(sim, i)
    field_claim(sim, sh, i, var)
    ex = explain_state(sim, i, var)
    parts = [(t["label"], float(t["value"]), None) for t in ex["terms"]] + \
            [((e["event"] or {}).get("label", "an event"), float(e["value"]), e["event"]) for e in ex["events"]]
    tot = sum(abs(v) for _, v, _ in parts) or 1.0
    for lbl, v, ev in sorted(parts, key=lambda p: -abs(p[1]))[:6]:
        share = abs(v) / tot
        if share < 0.03:
            continue
        refs = [{"kind": "event", "id": ev["id"]}] if ev else []
        if ev and ev.get("b") is not None:
            refs.append(person_ref(sim, ev["b"]))
        sh.add("measurement", me, f"Of {me['name']}'s {label(sim, var)}, {v:+.2f} ({100 * share:.0f}% of the parts) comes from "
                                  f"{lbl.lower() if not ev else event_line(sim, ev['id'])}.",
               field=None, value=round(v, 3), share=round(share, 3), refs=refs)
    return sh


def _why_changed(sim, args) -> Sheet:
    from ...analysis.explain import cohort_term_attribution
    from ...analysis.query import describe_filter, evaluate_filter
    P = sim.w.P
    var = _var(sim, args)
    filt = args.get("filter") or {"all": True}
    m = evaluate_filter(sim.w, filt, sim) & P["present"][: P.n].astype(bool)
    if not m.any():
        raise ValueError("nobody matches that filter")
    what = str(args.get("what") or describe_filter(filt))[:120]
    group = {"kind": "group", "id": "filter", "name": what}
    sh = Sheet()
    mean = float(np.nanmean(P[var][: P.n][m].astype(float)))
    b = band(sim, var, mean)
    sh.add("measurement", group, f"Average {label(sim, var)} of {what}: {mean:.2f}" + (f" ({b})" if b else "") + f" ({int(m.sum()):,} people).",
           field=var, value=round(mean, 3), band=b, count=int(m.sum()))
    terms = cohort_term_attribution(sim, m, var)
    tot = sum(abs(t["mean"]) for t in terms) or 1.0
    for t in sorted(terms, key=lambda t: -abs(t["mean"]))[:6]:
        share = abs(t["mean"]) / tot
        mech = sim.reg.mechanisms.get(t["mechanism"]) if t["mechanism"] else None
        lbl = (mech.label if mech else ("recent events" if t["term"] == "events" else t["term"].replace("_", " "))).lower()
        sh.add("measurement", group, f"For {what}, {t['mean']:+.3f} of {label(sim, var)} ({100 * share:.0f}% of the parts) comes from {lbl}.",
               value=round(float(t["mean"]), 4), share=round(share, 3))
    hist = sim.systems.get("history")
    if hist is not None and getattr(hist, "snaps", None) and hist.tracked(var):
        s0 = hist.snaps[max(0, len(hist.snaps) - 3)]
        n0 = min(s0["n"], P.n)
        mm = m[:n0] & s0["present"][:n0]
        if mm.any():
            then = float(np.nanmean(np.asarray(s0[var][:n0], float)[mm]))
            sh.add("measurement", group, f"On day {s0['day']} the same people's average {label(sim, var)} was {then:.2f}; "
                                         f"it is {mean:.2f} now (a change of {mean - then:+.2f}).",
                   field=var, value=round(mean, 3), numbers=[round(then, 3), round(mean - then, 3), s0["day"]])
    return sh


def _most_affected(base, alt, args) -> Sheet:
    from ...analysis.explain import most_affected
    var = _var(base, args)
    k = int(min(max(int(args.get("k") or 5), 1), 8))
    sh = Sheet()
    for r in most_affected(base, alt, var, k=k):
        pr = person_ref(base, r["id"])
        sh.add("measurement", pr, f"In the What-if, {pr['name']}'s {label(base, var)} is {r['alt']:.2f} instead of "
                                  f"{r['base']:.2f} (a change of {r['delta']:+.2f}).", field=var, value=round(r["alt"], 3),
               numbers=[round(r["base"], 3), round(r["delta"], 3)])
    if not sh.claims:
        raise ValueError("the What-if hasn't changed that measure yet")
    return sh


def _person(sim, args) -> Sheet:
    i = int(args.get("person"))
    P = sim.w.P
    if not (0 <= i < P.n):
        raise ValueError("no such person")
    sh = Sheet()
    pr = person_ref(sim, i)
    sh.add("fact", pr, f"{pr['name']} is {int(P['age'][i])} years old.", value=float(int(P["age"][i])))
    for var in ("school", "rel_status", "activity", "living", *FEELINGS, "faith_belief", "n_friends", "relationship_satisfaction"):
        if var in P.cols:
            field_claim(sim, sh, i, var)
    part = int(P["partner_id"][i])
    if part >= 0:
        o = person_ref(sim, part)
        sh.add("fact", pr, f"{pr['name']}'s partner is {o['name']}.", refs=[o])
    return sh


def _trace(sim, args) -> Sheet:
    sh = Sheet()
    try:
        from ...analysis import trace as T
    except Exception:  # noqa: BLE001
        raise ValueError("tracing isn't available") from None
    eid = int(args.get("event"))
    g = T.trace(sim, f"event:{eid}", dir="back", depth=2, max_nodes=24, fanout=4)
    nodes = {n["key"]: n for n in g["nodes"]}
    for ln in g["links"][:12]:
        a, b = nodes.get(ln["source"]), nodes.get(ln["target"])
        if not a or not b:
            continue
        refs = [x for n in (a, b) for x in ([{"kind": n["ref"]["kind"], "id": n["ref"]["id"]}]
                                            + [person_ref(sim, p) for p in n.get("people", [])[:2]])]
        sh.add("cause", {"kind": "event", "id": eid}, f"{a['label']} → {b['label']}" + (f" ({ln['words']})." if ln.get("words") else "."),
               refs=refs)
    return sh
