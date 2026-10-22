"""A slice of time, in words: for one person, what they are doing right now, where (the building, floor and home or
the venue), with whom and how they know each other, the occasion they are at and why they came, and what is on their
mind. For the map's inspect cards. Every sentence comes from the model's own state (nothing is invented here);
`mind` is written from the person's drives, intentions, plans, memories and the gaps between what they believe and
what is true.
"""
from __future__ import annotations

import numpy as np

from ..engine import placement, places
from ..engine.state import CTX, CTX_ID, Tie
from .person import headline, synthetic_name

ACT_WORDS = {"home": "at home", "class": "in class", "work": "at work", "church": "at church", "campus": "on campus",
             "gym": "working out", "gathering": "at a get-together", "date": "on a date", "venue": "out (eating or shopping)",
             "outdoors": "outdoors", "ward_activity": "at a ward activity", "away": "away from Provo", "club": "at a club"}


def _tie_words(w, i: int, j: int) -> str:
    """How i knows j, in a few words."""
    P, E = w.P, w.E
    if int(P["partner_id"][i]) == j:
        return "spouse" if P.is_("rel_status", "married")[i] else "partner"
    from ..engine.rooms import same_room
    if same_room(w, np.array([i]), np.array([j]))[0]:
        return "bedroom-mate"
    k = E.find(E.make_keys(np.array([i]), np.array([j])))[0] if E.n else -1
    if k < 0:
        return "someone they don't know yet"
    st = int(E["stage"][k])
    fl = int(E["flags"][k])
    parts = []
    if fl & Tie.ROMANTIC:
        parts.append("dating")
    if P["unit_id"][i] >= 0 and P["unit_id"][i] == P["unit_id"][j]:
        parts.append("roommate")
    parts.append({0: "met once", 1: "acquaintance", 2: "friend", 3: "close friend", 4: "best friend"}.get(st, "friend"))
    return ", ".join(dict.fromkeys(parts))


def _place_words(sim, f: dict, pos: dict, i: int) -> dict:
    w = sim.w
    U = w.units
    ct, cid = int(f["ctype"][i]), int(f["cid"][i])
    b = int(pos["building"][i])
    B = placement.buildings()
    bname = B["name"][b] if 0 <= b < B["n"] else None
    floor = int(pos["floor"][i])
    out = {"kind": CTX[ct] if ct < len(CTX) else "", "building": b if b >= 0 else None, "building_name": bname, "floor": floor}
    words = ""
    if ct == CTX_ID["unit"]:
        lab = U.label[cid] if U.label is not None and 0 <= cid < len(U.label) else ""
        own = cid == int(f["unit"][i])
        cx = int(U.complex_id[cid]) if 0 <= cid < len(U.lon) else -1
        cname = w.complexes["name"][cx] if 0 <= cx < w.complexes.height else None
        where = ", ".join(x for x in (lab, bname or cname) if x)
        words = ("at home" if own else "at a friend's place") + (f" ({where})" if where else "")
    elif ct in (CTX_ID["venue"], CTX_ID["outdoors"], CTX_ID["dance"]):
        a = sim.systems["activity"]
        words = a.v_name[cid] if 0 <= cid < len(a.v_name) else "a venue"
    elif ct == CTX_ID["class"]:
        ac = sim.systems["academics"]
        rm = int(ac.sec_room[cid]) if 0 <= cid < len(ac.sec_room) else -1
        R = places.classrooms(1) if rm >= 0 else None
        course = ac.sec_course[cid] if 0 <= cid < len(ac.sec_course) else ""
        if course:
            out["course"] = course
        if R is not None:
            words = f"class in {R['code'][rm]} {R['room'][rm]} ({bname}, {int(R['seats'][rm])} seats)"
            out["room"] = f"{R['code'][rm]} {R['room'][rm]}"
        elif 0 <= cid < len(ac.sec_where) and ac.sec_where[cid]:
            words = f"class in {ac.sec_where[cid]}" + (f" ({bname})" if bname else "")
            out["room"] = ac.sec_where[cid]
        else:
            words = f"class in {bname}" if bname else "in class"
        if course and words.startswith("class in "):
            words = f"{course} class in {words[len('class in '):]}"
    elif ct == CTX_ID["ward"]:
        nm = w.wards.get("name")
        words = f"{nm[cid]} (church)" if nm is not None and 0 <= cid < len(nm) else "church"
    elif ct == CTX_ID["work"]:
        nm = w.employers.get("name")
        words = f"work at {nm[cid]}" if nm is not None and 0 <= cid < len(nm) and nm[cid] else "work"
    elif ct in (CTX_ID["club"], CTX_ID["team"], CTX_ID["institute"]):
        nm = w.groups.get("name")
        words = nm[cid] if nm is not None and 0 <= cid < len(nm) else CTX[ct]
    elif ct == CTX_ID["campus"]:
        words = f"on campus{f' ({bname})' if bname else ''}"
    elif ct == CTX_ID["complex"]:
        words = "around their complex"
    out["words"] = words
    if floor > 0 and bname:
        out["words"] += f", floor {floor + 1}"
    return out


def mind_sentences(sim, i: int) -> list[dict]:
    """What is on their mind, as plain sentences, each with the field it comes from."""
    from .inner import inner_life
    P = sim.w.P
    il = inner_life(sim, i)
    out = []
    mot = sorted(il.get("motives", []), key=lambda m: -m.get("drive", 0))
    if mot and mot[0].get("drive", 0) > 0.12:
        m = mot[0]
        out.append({"text": f"Wants {m['label']} most right now ({'badly' if m['drive'] > 0.35 else 'somewhat'}: cares a lot, has less of it than they'd like).",
                    "from": "motives"})
    lon = float(P["loneliness"][i]) if "loneliness" in P else None
    if lon is not None and np.isfinite(lon):
        pct = float((P["loneliness"][P["present"]] < lon).mean())
        if pct > 0.8:
            out.append({"text": "Lonelier than most people here.", "from": "loneliness"})
        elif pct < 0.2:
            out.append({"text": "Feeling well connected.", "from": "loneliness"})
    mood = float(P["mood"][i]) if "mood" in P else None
    if mood is not None and np.isfinite(mood):
        pm = float((P["mood"][P["present"]] < mood).mean())
        if pm < 0.15:
            out.append({"text": "In a low mood lately.", "from": "mood"})
        elif pm > 0.85:
            out.append({"text": "In a good mood.", "from": "mood"})
    if il.get("intention") and il["intention"] != "none":
        out.append({"text": f"Intends to {str(il['intention']).replace('_', ' ')}.", "from": "intention"})
    for p in (il.get("plans") or [])[:2]:
        t = p.get("label") or p.get("what") or p.get("goal")
        if t:
            out.append({"text": f"Working on a plan: {t}.", "from": "plans"})
    mem = il.get("memories") or []
    if mem:
        m = mem[0]
        t = m.get("story") or m.get("label") or m.get("what")
        if t:
            out.append({"text": f"Still thinking about: {t}.", "from": "memories"})
    for b in il.get("beliefs") or []:
        if abs(b.get("gap", 0)) > 0.35:
            more = b["believed"] > b["actual"]
            out.append({"text": f"{b['what']}: believes it's {'more' if more else 'less'} than it really is.", "from": "beliefs"})
            break
    return out[:6]


def _why_came(me: dict) -> dict:
    """How a guest was invited, why they said yes (the decision's factors, strongest first) and how they got there."""
    dec = me.get("decision") or {}
    fac = [f for f in dec.get("factors", []) if not f.get("constraint") and f.get("words")]
    pro = [f["words"] for f in sorted(fac, key=lambda f: -f["value"]) if f["value"] > 0.05][:3]
    con = [f["words"] for f in sorted(fac, key=lambda f: f["value"]) if f["value"] < -0.05][:2]
    trip = me.get("trip") or {}
    return {"role": me.get("role"), "inviter": me.get("inviter"), "channel": me.get("channel_words"),
            "for": pro, "against": con, "prob": dec.get("prob"), "arrive": me.get("arrive"), "late_minutes": me.get("late_minutes"),
            "ride": (me.get("ride") or {}).get("name"), "trip_minutes": trip.get("minutes"), "trip_mode": trip.get("mode")}


def _date_words(sim, i: int, sc: dict) -> dict:
    """The other person on a date, how many dates the two have been on, who asked, and where they stand."""
    w = sim.w
    others = [p["person"]["id"] for p in sc.get("people", []) if p.get("came") and p["person"]["id"] != i]
    if not others:
        return {}
    j = int(others[0])
    book = sim.book
    inv, occ = book.inv, book.occ
    n = inv.n
    per, att, oc = inv.cols["person"][:n], inv.cols["attended"][:n], inv.cols["occ"][:n]
    mine = set(oc[(per == i) & att].tolist())
    theirs = set(oc[(per == j) & att].tolist())
    both = np.array(sorted(mine & theirs), np.int64)
    kd = book.kind_id.get("date", -1)
    if len(both):
        pos = occ.pos(both)
        ok = pos >= 0
        both = both[ok][occ.cols["kind"][pos[ok]] == kd]
    nth = int((both <= int(sc["id"])).sum()) if len(both) else 1
    org = (sc.get("organizer") or {}).get("id")
    E = w.E
    k = E.find(E.make_keys(np.array([i]), np.array([j])))[0] if E.n else -1
    status = _tie_words(w, i, j)
    return {"with": {"id": j, "name": synthetic_name(w.P, j)}, "nth": max(nth, 1),
            "asked_by": "they asked" if org == i else f"{synthetic_name(w.P, j)} asked" if org == j else None,
            "status": status, "liking": round(float(E["liking"][k]), 2) if k >= 0 else None}


def person_now(sim, i: int, f: dict | None = None) -> dict:
    w = sim.w
    P = w.P
    f = f or getattr(sim.systems["activity"], "snapshot", None) or placement.frame(sim)
    if not 0 <= i < len(f["ctype"]):
        return {}
    pos = placement.place(sim, f)
    acts = P.specs["activity_now"].categories
    act = acts[int(f["act"][i])] if int(f["act"][i]) < len(acts) else ""
    out = {"id": i, "name": synthetic_name(P, i), "headline": headline(sim, i), "doing": ACT_WORDS.get(act, act.replace("_", " ")),
           "activity": act, "present": bool(f["present"][i]), "day": int(f["day"]), "date": str(sim.cal.date(int(f["day"]))),
           "block": int(f.get("block", -1)), "place": _place_words(sim, f, pos, i)}
    # the occasion they're at, and why they came
    ct, cid = int(f["ctype"][i]), int(f["cid"][i])
    if ct in (CTX_ID["occasion"], CTX_ID["date"]) and cid >= 0:
        from .scenes import scene
        sc = scene(sim, cid) or {}
        me = next((p for p in sc.get("people", []) if (p.get("person") or {}).get("id") == i), None)
        out["occasion"] = {k: sc.get(k) for k in ("id", "kind", "kind_label", "name", "time", "date", "n_people", "organizer", "how", "note")}
        if sc.get("kind_label"):        # the occasion names what they're doing ("Game night", "Date")
            out["doing"] = "on a date" if sc.get("kind") == "date" else sc["kind_label"]
        if me:
            out["occasion"]["me"] = _why_came(me)
        if sc.get("kind") == "date":
            out["date_info"] = _date_words(sim, i, sc)
        if out["place"]["words"] == "":
            out["place"]["words"] = sc.get("place") if isinstance(sc.get("place"), str) else (sc.get("place") or {}).get("name", "") if isinstance(sc.get("place"), dict) else ""
    # who they are with: everyone sharing the same place and moment
    same = np.flatnonzero((f["ctype"] == ct) & (f["cid"] == cid) & f["present"]) if ct != 255 else np.empty(0, np.int64)
    same = same[same != i]
    if ct == CTX_ID["unit"]:
        # at home: the people in the same home right now, bedroom-mates first
        from ..engine.rooms import same_room
        same = same[np.argsort(~same_room(w, np.full(len(same), i), same), kind="stable")]
    out["n_with"] = int(len(same))
    out["with"] = [{"id": int(j), "name": synthetic_name(P, int(j)), "tie": _tie_words(w, i, int(j))} for j in same[:16]]
    known = [x for x in out["with"] if x["tie"] != "someone they don't know yet"]
    out["n_known"] = len(known) + max(0, sum(1 for j in same[16:] if _tie_words(w, i, int(j)) != "someone they don't know yet"))
    out["mind"] = mind_sentences(sim, i)
    return out
