"""Occasions as scenes: what was planned, who was asked and how, who decided what and why, who came, when and how,
who met whom there and what happened next. Read-only views over the OccasionBook (engine/ledger.py) for the API.
"""
from __future__ import annotations

import numpy as np

from ..engine import clock
from ..engine.state import CTX_ID
from .person import synthetic_name

WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
CHANNEL_WORDS = {"in_person": "asked in person", "text": "a text", "group_chat": "the group chat", "announcement": "heard it announced",
                 "family": "family", "app": "an app"}


def _who(P, i) -> dict | None:
    i = int(i)
    return {"id": i, "name": synthetic_name(P, i)} if 0 <= i < P.n else None


def occasion_row(sim, oid: int) -> dict:
    """One occasion in brief (for lists)."""
    book, P = sim.book, sim.w.P
    occ = sim.systems["occasions"]
    d = book.describe(int(oid))
    if not d:
        return {}
    st, du = int(d["start"]), int(d["dur"])
    org = int(d["organizer"])
    return {"id": int(oid), "kind": d["kind"], "kind_label": d["kind_label"], "name": d["name"], "day": int(d["day"]),
            "date": str(sim.cal.date(int(d["day"]))), "weekday": WEEKDAYS[sim.cal.weekday(int(d["day"]))],
            "start": st, "end": st + du, "time": f"{clock.hhmm(st)}–{clock.hhmm(st + du)}", "status": d["status"],
            "origin": d["origin"], "open": bool(d["open"]), "organizer": _who(P, org) if org >= 0 else None,
            "place": occ.place_label(int(oid)), "lon": d["lon"], "lat": d["lat"], "series": d["series"] if d["series"] >= 0 else None,
            "invited": int(d["n_invited"]), "said_yes": int(d["n_yes"]), "came": int(d["n_came"]),
            "new_ties": int(d["n_new_ties"]), "talks": int(d["n_talks"]), "conflicts": int(d["n_conflicts"]),
            "action": int(d["org_id"]) if d["org_kind"] == "user" else None}


def list_occasions(sim, day: int | None = None, kind: str | None = None, person: int | None = None, place: int | None = None,
                   limit: int = 300) -> dict:
    """Occasions on a day (default today), optionally of a kind, involving a person, or at a place."""
    book = sim.book
    O, I = book.occ, book.inv
    if not O.n:
        return {"occasions": [], "n": 0}
    m = np.ones(O.n, bool)
    if day is not None:
        m &= O["day"] == int(day)
    elif person is None:
        m &= O["day"] == sim.w.day
    if kind:
        if kind not in book.kind_id:
            return {"occasions": [], "n": 0, "error": f"unknown kind {kind}"}
        m &= O["kind"] == book.kind_id[kind]
    if place is not None:
        m &= O["place"] == int(place)
    if person is not None:
        mine = I["occ"][I["person"] == int(person)] if I.n else np.empty(0, np.int64)
        m &= np.isin(O["id"], mine) | (O["organizer"] == int(person))
    ids = O["id"][m]
    order = np.lexsort((O["start"][m], -O["day"][m])) if person is not None else np.lexsort((-O["n_came"][m], O["start"][m]))
    ids = ids[order]
    return {"n": int(len(ids)), "occasions": [occasion_row(sim, int(o)) for o in ids[:limit]],
            "kinds": {k: v.get("label", k) for k, v in book.vocab.items()}}


def scene(sim, oid: int) -> dict:
    """The whole story of one occasion."""
    from .explain import event_record
    book, P, E = sim.book, sim.w.P, sim.w.E
    occ = sim.systems["occasions"]
    oid = int(oid)
    row = occasion_row(sim, oid)
    if not row:
        return {}
    d = book.describe(oid)
    # how it came about: the organizer's decision to host (or the action, the series, the calendar)
    why = None
    if d["decision"] >= 0:
        why = sim.decisions.get(int(d["decision"])) or None
    origin = {"engine": "planned by the organizer", "user": "arranged by a What-if action", "calendar": "on the calendar",
              "institution": "organized by an institution", "family": "a family thing"}.get(d["origin"], d["origin"])
    if row["series"] is not None:
        S = book.series
        sid = int(row["series"])
        origin += f" · week {1 + (int(d['day']) - int(S.get('first_day', [sid])[0])) // max(int(S.get('every', [sid])[0]), 1)} of a weekly series"
    # invitations and attendance
    inv_ids = book.invitations(oid)
    trips = occ.trips
    tmap = {}
    if trips.n and len(inv_ids):
        m = np.isin(trips["inv"], inv_ids)
        for r_inv, mins, md, late in zip(trips["inv"][m].tolist(), trips["minutes"][m].tolist(), trips["mode"][m].tolist(),
                                         trips["late"][m].tolist()):
            tmap[int(r_inv)] = (mins, md, late)       # the latest check wins
    from ..geo.travel import MODES
    people = []
    for r in book.invitation_rows(inv_ids):
        i = int(r["person"])
        dec = sim.decisions.get(int(r["decision"])) if r["decision"] >= 0 else None
        t = tmap.get(int(r["id"]))
        role = "organizer" if i == int(d["organizer"]) else ("walked in" if r["walk_in"] else "invited")
        rec = {"person": _who(P, i), "role": role, "channel": r["channel"], "channel_words": CHANNEL_WORDS.get(r["channel"], r["channel"]),
               "inviter": _who(P, r["inviter"]) if r["inviter"] >= 0 else None, "sent_day": r["sent_day"],
               "seen_day": r["seen_day"] if r["seen_day"] >= 0 else None, "response": r["response"],
               "decided_day": r["decided_day"] if r["decided_day"] >= 0 else None, "came": bool(r["attended"]),
               "arrive": clock.hhmm(r["arrive"]) if r["attended"] and r["arrive"] >= 0 else None,
               "late_minutes": max(int(r["arrive"]) - int(d["start"]), 0) if r["attended"] and r["arrive"] >= 0 else None,
               "ride": (_who(P, r["ride_by"]) if r["ride_by"] >= 0 else ({"name": "someone"} if r["ride_by"] == -2 else None)),
               "trip": {"minutes": int(t[0]), "mode": MODES[t[1]] if t[1] >= 0 else None} if t else None,
               "decision": dec}
        if r["response"] == "yes" and not r["attended"] and d["status"] != "planned":
            sh = sim.decisions.for_occasion(oid).tolist()
            for x in sh[::-1]:
                g = sim.decisions.get(int(x))
                if g and g["kind"] == "show_up" and g["agent"] == i:
                    rec["no_show"] = g
                    break
        people.append(rec)
    came = [p for p in people if p["came"]]
    # who met whom there (new ties that started at this occasion)
    met = []
    if E.n:
        oc = E["origin_ctx"] == CTX_ID["occasion"]
        hit = np.where(oc & (E["origin_place"] == oid))[0]
        if len(hit):
            lo, hi = E.endpoints()
            for e in hit[:200].tolist():
                intro = int(E["introducer"][e])
                met.append({"a": _who(P, lo[e]), "b": _who(P, hi[e]), "introducer": _who(P, intro) if intro >= 0 else None,
                            "closeness_now": round(float(E["closeness"][e]), 3), "stage_now": int(E["stage"][e])})
    # what happened there and because of it
    evs = sim.causes.effects_of("occasion", oid)
    events = [event_record(sim, int(e)) for e in np.unique(evs)[:200]]
    for ev in events:
        ev["a_name"] = synthetic_name(P, ev["a"])
        if ev.get("b") is not None:
            ev["b_name"] = synthetic_name(P, ev["b"])
    S = None
    if row["series"] is not None:
        sid = int(row["series"])
        Sx = book.series
        S = {"id": sid, "weekday": WEEKDAYS[int(Sx.get("weekday", [sid])[0]) % 7], "start": clock.hhmm(int(Sx.get("start", [sid])[0])),
             "active": bool(Sx.get("active", [sid])[0]), "regulars": [_who(P, i) for i in occ.regulars(sid)[:40]],
             "organizer": _who(P, int(Sx.get("organizer", [sid])[0]))}
    burden = getattr(occ, "_last_burden", {}).get(oid)
    return {**row, "how": origin, "org_kind": d["org_kind"],
            "host_decision": why, "people": people, "n_people": len(people), "came_list": came, "met": met,
            "events": events, "series_info": S, "host_burden": None if burden is None else round(float(burden), 2),
            "note": "Times are clock minutes; who met whom lists ties that began here (including people who walked in)."}
