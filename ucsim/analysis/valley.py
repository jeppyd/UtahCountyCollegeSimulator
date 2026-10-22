"""The valley: the home screen's three readers over the event log (nothing is invented, no model is called, no random
numbers are drawn, so reading never changes a world).

* `feed(sim, people)` — what happened lately, as one stream of moments: for the people you follow (anything they were
  part of) or for the whole valley (the biggest moments, a few of each kind). It is curated, not raw: the other
  person's copy of a two-person moment is shown once ("Ana and Ben got engaged", not twice), the two halves of a
  breakup are one moment, bookkeeping events (a new term, a muted chat, a renewed endorsement) are left out, and the
  same thing with the same person is folded together ("went on 3 dates with Ben"). Each moment carries its top
  recorded reasons (`story.why`).
* `cast(sim)` — lives worth following, one per kind of life (a freshman in the dorms, a newly engaged couple, a UVU
  student living at home…), each with a one-line hook, so a newcomer can pick someone in a click.
* `now(sim, ids)` — the followed people right now: what they're doing, how they feel, who they're with, what's next
  today and their latest moment.
"""
from __future__ import annotations

import numpy as np

from . import story as S
from . import trace as T
from .person import headline, synthetic_name

# events that keep the books rather than tell a story: never in the feed
QUIET = {"term_started", "added_to_chat", "left_chat", "muted_chat", "endorsement_renewed", "time_with_family",
         "intervention_exposure", "assumed_busy", "low_turnout", "hosting_strain", "counseling_session"}
# the second half of a two-sided moment, shown through its first half (same day, same two people)
HALF = {"breakup_received": "breakup_initiated", "dealbreaker_overlooked": "dealbreaker_found"}
# moments about the follower alone even when another person is named (the host they were left out by, the person
# they assumed wasn't interested): shown only for the person they happened to, and folded across the people named
SELF = {"left_out", "felt_ignored", "assumed_not_interested", "homesick"}
FOLD_DAYS = 7               # the same moment with the same person again within a week is folded into one line
MIN_CAST, MIN_VALLEY = 0.35, 0.75


def _wd(sim, day: int) -> str:
    return sim.cal.date(int(day)).strftime("%a")


def feed(sim, people: list[int] | None = None, since: int | None = None, limit: int = 60,
         min_salience: float | None = None) -> dict:
    """What happened lately to the people followed (or in the whole valley), newest first (see the module docstring)."""
    log, reg = sim.log, sim.reg
    n = log.n
    today = sim.w.day
    names = reg.event_names
    sal = T._salience(sim)
    W = T._Words(sim)
    cast = sorted({int(i) for i in (people or []) if 0 <= int(i) < sim.w.P.n})
    lo = today - 14 if since is None else int(since)
    lo_row = int(np.searchsorted(log["day"][:n], lo, side="left"))
    day, typ, a, b = (log[c][lo_row:n] for c in ("day", "type", "a", "b"))
    quiet = np.array([nm in QUIET for nm in names])
    keep = ~quiet[typ] & (a >= 0)
    if cast:
        cs = np.array(cast)
        self_only = np.array([nm in SELF for nm in names])[typ]
        keep &= (np.isin(a, cs) | (np.isin(b, cs) & ~self_only)) & (sal[typ] >= (MIN_CAST if min_salience is None else min_salience))
    else:
        keep &= sal[typ] >= (MIN_VALLEY if min_salience is None else min_salience)
    rows = lo_row + np.flatnonzero(keep)
    tid = {nm: k for k, nm in enumerate(names)}
    firsts = {}                                   # (first half's type, day, a, b) for the two-sided moments
    for half, first in HALF.items():
        if first in tid and half in tid:
            for e in rows[log["type"][rows] == tid[first]]:
                firsts[(first, int(log["day"][e]), int(log["a"][e]), int(log["b"][e]))] = int(e)
    per_type: dict[int, int] = {}
    per_cat: dict[str, int] = {}
    seen: set = set()
    folded: dict[tuple, dict] = {}
    out: list[dict] = []
    for e in rows[::-1]:                          # newest first
        e = int(e)
        t, d, x, y = int(log["type"][e]), int(log["day"][e]), int(log["a"][e]), int(log["b"][e])
        nm = names[t]
        pair = (min(x, y), max(x, y)) if y >= 0 else (x, -1)
        if (nm, d, pair) in seen:                 # the other person's copy of the same moment
            continue
        first = HALF.get(nm)
        if first and ((first, d, y, x) in firsts or (first, d, x, y) in firsts):
            continue                              # shown through its first half
        seen.add((nm, d, pair))
        fk = (nm, (x, -1)) if nm in SELF else (nm, pair)
        if fk in folded and folded[fk]["first_day"] - d <= FOLD_DAYS:
            line = folded[fk]
            line["times"] += 1
            line["first_day"] = d
            line["first_date"] = str(sim.cal.date(d))
            continue
        spec = reg.events[nm]
        if not cast:                              # the whole valley: a few of each kind, so one busy kind can't flood it
            if per_type.get(t, 0) >= 3 or per_cat.get(spec.category, 0) >= 8:
                continue
            per_type[t] = per_type.get(t, 0) + 1
            per_cat[spec.category] = per_cat.get(spec.category, 0) + 1
        if len(out) >= limit:
            break
        try:
            w = S.why(sim, f"event:{e}")
            rs = S._reasons(w, 2)
        except Exception:  # noqa: BLE001  (an older event whose details were thinned)
            rs = []
        for r_ in rs:
            if str(r_.get("words", "")).startswith("action "):
                r_["words"], r_["share"] = "you made it happen", None
        who = [x] + ([y] if y >= 0 else [])
        line = {"event": e, "day": d, "date": str(sim.cal.date(d)), "weekday": _wd(sim, d), "type": nm,
                "label": spec.label, "category": spec.category, "salience": float(sal[t]), "text": W.event_line(e),
                "people": [{"id": p, "name": W.name(p)} for p in who], "cast": [p for p in who if p in cast],
                "reasons": rs, "because": S.reason_text(rs), "times": 1, "first_day": d, "first_date": str(sim.cal.date(d)),
                "big": bool(sal[t] >= 0.8)}
        folded[fk] = line
        out.append(line)
    _occasions(sim, out)
    return {"today": today, "date": str(sim.cal.date(today)), "since": lo, "people": cast, "moments": out,
            "note": "Reasons are the model's own recorded pushes inside this simulated world, as shares of the whole."}


def _occasions(sim, lines: list[dict]):
    """Mark each moment that happened at an occasion (a dinner, a date, a party) with it, so it can be watched."""
    if not lines:
        return
    from ..engine.ledger import CAUSE_ID
    t = sim.causes.t
    ids = np.array([ln["event"] for ln in lines], np.int64)
    m = np.isin(t["event"], ids) & (t["kind"] == CAUSE_ID["occasion"])
    occ = dict(zip(t["event"][m].tolist(), t["ref"][m].tolist()))
    for ln in lines:
        o = occ.get(ln["event"])
        ln["occasion"] = int(o) if o is not None and o >= 0 else None


# ---------------------------------------------------------------------------------------------------------------- cast
def _cat(P, field: str, value: str) -> np.ndarray:
    cats = P.specs[field].categories
    return P[field] == cats.index(value) if value in cats else np.zeros(P.n, bool)


def _kinds(sim):
    """(id, label, hook, mask) for each kind of life; masks over everyone present."""
    P = sim.w.P
    age = P["age"]
    student = _cat(P, "school", "BYU") | _cat(P, "school", "UVU")
    single = _cat(P, "rel_status", "single") | _cat(P, "rel_status", "talking")
    lonely = P["loneliness"] >= np.quantile(P["loneliness"][P["present"].astype(bool)], 0.9)
    lds = P["lds_member"].astype(bool) if "lds_member" in P else np.zeros(P.n, bool)
    crisis = P["faith_crisis"].astype(bool) if "faith_crisis" in P else np.zeros(P.n, bool)
    return [
        ("freshman", "A freshman in the dorms", "First semester away from home, and everyone on the floor is new too.",
         _cat(P, "class_standing", "freshman") & (_cat(P, "living", "dorm") | _cat(P, "living", "contracted"))),
        ("rm", "Just home from a mission", "Back from two years of rules and companions, and expected to start dating.",
         _cat(P, "mission_status", "returned") & single & student & (age <= 24)),
        ("engaged", "Newly engaged", "A ring, a temple date and a few months to plan a wedding between classes.",
         _cat(P, "rel_status", "engaged") & student),
        ("married", "Married students", "Rent, classes, a part-time job and a marriage, all at once.",
         _cat(P, "rel_status", "married") & student & (age <= 27)),
        ("commuter", "A UVU student living at home", "Classes in Orem, a job, and dinner with the family every night.",
         _cat(P, "school", "UVU") & (_cat(P, "living", "with_parents") | _cat(P, "living", "family_home"))),
        ("far", "From far away", "An international student making a life in a very particular town.",
         _cat(P, "origin_region", "International") & student),
        ("outsider", "Not a Latter-day Saint in Provo", "A student of another faith, or none, in a mostly Latter-day Saint town.",
         ~lds & student),
        ("lonely", "Quietly struggling", "Lonelier than nine in ten people here. Will anyone notice?", lonely & student),
        ("questioning", "Questioning their faith", "Belief that was certain a year ago isn't anymore.", crisis & lds),
    ]


def cast(sim, k: int = 9, shuffle: int = 0) -> dict:
    """Lives worth following, one per kind of life, each with a hook (see the module docstring). `shuffle` picks other
    people of the same kinds (deterministic: the same number gives the same people)."""
    P, log = sim.w.P, sim.log
    pres = P["present"].astype(bool)
    sal = T._salience(sim)
    lo_row = int(np.searchsorted(log["day"][:log.n], sim.w.day - 30, side="left"))
    a, t = log["a"][lo_row:log.n], log["type"][lo_row:log.n]
    m = a >= 0
    lively = np.bincount(a[m], weights=sal[t[m]], minlength=P.n)[: P.n]     # a life with something going on
    out, used = [], set()
    for kid, label, hook, mask in _kinds(sim):
        c = np.flatnonzero(mask & pres)
        c = c[~np.isin(c, list(used))] if used else c
        if not len(c):
            continue
        top = c[np.argsort(-lively[c], kind="stable")][: max(5, 2 * (shuffle + 1))]
        i = int(top[shuffle % len(top)])
        used.add(i)
        out.append({"kind": kid, "label": label, "hook": hook, "id": i, "name": synthetic_name(P, i),
                    "headline": headline(sim, i), "mood": float(P["mood"][i]), "loneliness": float(P["loneliness"][i])})
        if len(out) >= k:
            break
    return {"cast": out}


# ----------------------------------------------------------------------------------------------------------------- now
RESP_WORDS = {"pending": "hasn't seen it yet", "yes": "said yes", "no": "said no", "no_reply": "didn't answer", "maybe": "said maybe"}


def _plans(sim, i: int) -> list[dict]:
    """Their get-togethers from yesterday to the next few days: what, when, where, their part and their answer, and
    whether it already happened (then it can be watched)."""
    from .scenes import occasion_row
    book = sim.book
    I, O = book.inv, book.occ
    day = sim.w.day
    mine = I["occ"][I["person"] == i] if I.n else np.empty(0, np.int64)
    own = O["id"][: O.n][O["organizer"][: O.n] == i] if O.n else np.empty(0, np.int64)
    ids = np.unique(np.r_[mine, own]) if len(mine) + len(own) else np.empty(0, np.int64)
    out = []
    for o in ids.tolist():
        row = occasion_row(sim, int(o))
        if not row or not (day - 1 <= row["day"] <= day + 6) or row["kind"] in ("devotional",):
            continue
        hosting = row.get("organizer") and row["organizer"]["id"] == i
        r = None
        if not hosting:
            k = np.flatnonzero((I["occ"] == o) & (I["person"] == i))
            if len(k):
                r = book.inv.row(int(I["id"][k[-1]]))
        resp = r.get("response") if r else None
        if isinstance(resp, (int, np.integer)):
            from ..engine.ledger import RESPONSES
            resp = RESPONSES[int(resp)]
        label = row.get("name") or row["kind_label"]
        if row["kind"] == "date":
            others = [int(p) for p in I["person"][I["occ"] == o].tolist() if int(p) != i]
            if row.get("organizer") and row["organizer"]["id"] != i:
                others.insert(0, row["organizer"]["id"])
            if others:
                label = f"Date with {synthetic_name(sim.w.P, others[0])}"
        elif row.get("organizer") and not hosting and not row.get("name"):
            label = f"{row['organizer']['name'].split()[0]}'s {row['kind_label'].lower()}"
        out.append({"occasion": int(o), "label": label, "kind": row["kind"], "day": row["day"],
                    "time": row["time"], "place": row["place"], "status": row["status"], "hosting": bool(hosting),
                    "organizer": row.get("organizer"), "answer": RESP_WORDS.get(str(resp), None) if resp is not None else None,
                    "came": bool(r.get("attended")) if r else bool(hosting)})
    return sorted(out, key=lambda x: (x["day"], x["time"]))[:6]

def now(sim, ids: list[int]) -> dict:
    """The followed people right now (see the module docstring)."""
    P, log = sim.w.P, sim.log
    acats = P.specs["activity_now"].categories
    rel = P.specs["rel_status"].categories
    occ = sim.systems.get("occasions")
    minute = int(sim.w.hour) * 60
    out = []
    for i in ids:
        i = int(i)
        if not 0 <= i < P.n:
            continue
        pid = int(P["partner_id"][i]) if "partner_id" in P else -1
        nxt = None
        if occ is not None and P["present"][i]:
            try:
                ag = occ.agenda(i, None)
                items = [(c["start"], c.get("what") or c.get("kind"), c.get("time")) for c in ag.get("commitments", [])]
                items += [(o["start"], o.get("name") or o.get("kind_label") or "an occasion", o.get("time")) for o in ag.get("occasions", [])]
                later = sorted(x for x in items if x[0] is not None and x[0] >= minute)
                if later:
                    nxt = {"what": later[0][1], "time": later[0][2]}
            except Exception:  # noqa: BLE001  (an agenda the occasions system can't build for this person today)
                nxt = None
        rows = np.flatnonzero((log["a"][: log.n] == i))
        last = None
        sal = T._salience(sim)
        quiet = {k for k, nm in enumerate(sim.reg.event_names) if nm in QUIET}
        for e in rows[::-1][:40]:
            if int(log["type"][e]) not in quiet and sal[log["type"][e]] >= MIN_CAST:
                last = {"event": int(e), "text": T._Words(sim).event_line(int(e)), "day": int(log["day"][e]),
                        "date": str(sim.cal.date(int(log["day"][e])))}
                break
        out.append({"id": i, "name": synthetic_name(P, i), "headline": headline(sim, i), "present": bool(P["present"][i]),
                    "plans": _plans(sim, i),
                    "doing": acats[int(P["activity_now"][i])], "status": rel[int(P["rel_status"][i])],
                    "partner": {"id": pid, "name": synthetic_name(P, pid)} if pid >= 0 else None,
                    "mood": float(P["mood"][i]), "loneliness": float(P["loneliness"][i]), "stress": float(P["stress"][i]),
                    "next": nxt, "last": last})
    return {"day": sim.w.day, "hour": int(sim.w.hour), "people": out}
