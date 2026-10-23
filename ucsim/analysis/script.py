"""Scenes you can watch: the recorded facts of a get-together, or of two people's history, played back as a script of
beats: stage directions, text messages, arrivals, glances across the room, introductions and what happened next.

What happens in a script is always what the simulation recorded (who was asked, how and when, who said yes and
why, who came and how late, who met whom, who was drawn to whom, the events that followed). The *words* people say
are illustrative: picked from a small set of lines that fit what happened, the same lines every time for the same
moment (no random numbers are drawn, no model is called, nothing in either world changes). Every beat says which kind
of record it comes from, so you can always tell the fact from the flavor.

* `occasion_script(sim, oid)` — one occasion as a scene, from the decision to host to the drive home.
* `pair_script(sim, a, b)` — two people's history as a text thread: check-ins, invitations, asking out, first dates,
  silences and how they were read, breakups — in time order, with the moments between them as stage directions.
"""
from __future__ import annotations

import zlib

import numpy as np

from ..engine import clock
from ..engine.state import Tie
from . import story as S
from .person import synthetic_name
from .scenes import scene

ILLUSTRATIVE = ("What happens here is what the simulation recorded; the words people say are illustrative lines that "
                "fit what happened, the same every time you open this scene.")


def _pick(options: list[str], *key) -> str:
    """The same line for the same moment, every time (a hash of the moment, not a random draw)."""
    return options[zlib.crc32(repr(key).encode()) % len(options)]


def _first(P, i) -> str:
    return synthetic_name(P, int(i)).split()[0]


def _reasons(sim, did) -> str:
    if did is None:
        return ""
    try:
        return S.reason_text(S._reasons(S.why(sim, f"decision:{int(did)}"), 2))
    except Exception:  # noqa: BLE001  (thinned or missing details)
        return ""


# --------------------------------------------------------------------------------------------------------- the lines
INVITE = {
    "dinner": ["dinner at my place tonight at {t}? making way too much food", "come over for dinner? {t}, nothing fancy",
               "we're doing dinner at {t}, you should come!", "making soup tonight, come eat with us at {t}"],
    "game_night": ["game night at {t}!! bring a game if you have one", "settlers at mine tonight, {t}. you in?",
                   "games tonight at {t}, need a fourth"],
    "party": ["party at our place tonight, {t}. tell people!", "we're having people over at {t}, come!!",
              "getting a bunch of people together at {t} tonight"],
    "study_group": ["study group at {t}? the midterm is going to be brutal", "anyone want to study at {t}?",
                    "library at {t}? I'll bring snacks"],
    "movie_night": ["movie night at {t}, we have popcorn", "watching a movie at {t}, come hang"],
    "date": ["would you want to get dinner at {t}?", "any chance you're free at {t}? I'd love to take you out",
             "want to go on a date? thinking {t}"],
    "_": ["hanging out at {t} tonight, come by!", "a few of us are getting together at {t}, you should come",
          "come over at {t}? low key"],
}
YES = ["yes!! I'll be there", "count me in", "ooh yes, see you then", "yes! want me to bring anything?", "I'm in 🙌",
       "for sure", "yes, sounds fun"]
MAYBE = ["maybe? I'll let you know", "I'll try to make it", "possibly, depends on how much homework I get done"]
NO = ["ahh I can't tonight, sorry!", "I wish, can't make it", "not tonight but next time for sure", "can't, sorry 😕",
      "ugh I would but I can't"]
NO_BECAUSE = {"work": "I'm working till late, sorry!", "class": "I have class then 😩", "conflict": "I already have something then",
              "far": "that's kind of far for me tonight", "get there": "I don't have a ride tonight 😕",
              "ride": "I don't have a ride tonight 😕", "shift": "I'm working then, sorry!", "date": "I have a date tonight 👀"}
TIRED = ["honestly I'm so tired, next time!", "I'm dead tonight 😴 next time", "I need a night in, sorry!",
         "so tired, rain check?"]
MODE_WORDS = {"walk": "on foot", "bike": "by bike", "car": "by car", "transit": "by bus", "ride": "by ride"}
ELSEWHERE = {"left_out", "felt_ignored", "assumed_busy", "assumed_not_interested"}
ARRIVE = ["{a} arrives", "{a} walks in", "{a} shows up", "{a} gets there"]
ASK_OUT = ["would you want to go out sometime this week?", "hey, would you want to get dinner friday?",
           "this is random but would you want to go on a date?", "want to grab ice cream sometime?"]
SAID_NO = ["oh that's so nice of you, but I don't think so", "I'm actually seeing someone right now, sorry!",
           "thank you for asking! I don't think I'm interested though", "I'm flattered, but no, sorry"]
AFTER_DATE = ["I had a really good time tonight", "thanks for tonight 🙂", "that was so fun, thank you!",
              "home safe! tonight was great"]
GO_ON = ["same! let's do it again", "me too :)", "100% again soon"]
BREAKUP = ["can we talk tonight?", "hey, I've been thinking a lot about us", "do you have a minute to talk?"]
ENGAGED = ["I can't believe we're engaged 💍", "MY FIANCÉ 😭", "best day ever"]


def _no_line(dec: dict | None, key) -> str:
    if dec:
        for f in dec.get("factors", []):
            if f.get("constraint"):
                lab = (f.get("label") or "").lower()
                for k, line in NO_BECAUSE.items():
                    if k in lab:
                        return line
                return NO_BECAUSE["conflict"]
        top = sorted([f for f in dec.get("factors", []) if f["factor"] != "base"], key=lambda f: f["value"])[:1]
        if top and ("tired" in (top[0].get("label") or "") or "fatigue" in top[0]["factor"]):
            return _pick(TIRED, *key)
        if top and ("travel" in top[0]["factor"] or "far" in (top[0].get("label") or "")):
            return NO_BECAUSE["far"]
    return _pick(NO, *key)


DATE_YES = ["yes! I'd love that", "sure, sounds fun :)", "okay yes!", "I'd like that", "yes, I'm free"]


def _date_dynamics(sim, beat, ids, start, end, day):
    """How a date went, from the quality the simulation recorded for it that evening (the first_date or date event).
    A date that hasn't happened yet says nothing: how it will go isn't known."""
    log = sim.log
    x, y = int(ids[0]), int(ids[1])
    n = log.n
    lo = int(np.searchsorted(log["day"][:n], day))
    hi = int(np.searchsorted(log["day"][:n], day, side="right"))
    t = log["type"][lo:hi]
    kinds = [sim.reg.event_ids[k] for k in ("first_date", "date")]
    m = np.isin(t, kinds) & (((log["a"][lo:hi] == x) & (log["b"][lo:hi] == y)) | ((log["a"][lo:hi] == y) & (log["b"][lo:hi] == x)))
    rows = lo + np.flatnonzero(m)
    if not len(rows):
        return
    e = int(rows[0])
    q = float(log["value"][e])
    mid = start + max(end - start, 30) // 2
    ref = {"kind": "event", "id": e}
    if q >= 0.6:
        beat("stage", "The conversation is easy. They lose track of time.", minute=mid, source="how the date went (recorded that night)", ref=ref)
    elif q >= 0.1:
        beat("stage", "They like each other, you can tell, but there are a few long pauses.", minute=mid, source="how the date went (recorded that night)", ref=ref)
    elif q >= -0.4:
        beat("stage", "It's pleasant, a little polite.", minute=mid, source="how the date went (recorded that night)", ref=ref)
    else:
        beat("stage", "It never quite clicks. Both of them check the time.", minute=mid, source="how the date went (recorded that night)", ref=ref)


# --------------------------------------------------------------------------------------------------- occasion scenes
def occasion_script(sim, oid: int) -> dict:
    """One occasion as a scene (see the module docstring)."""
    sc = scene(sim, int(oid))
    if not sc:
        raise KeyError(f"no occasion {oid}")
    P, E = sim.w.P, sim.w.E
    org = sc["organizer"]
    kind = sc["kind"]
    start = int(sc["start"])
    t_words = clock.hhmm(start)
    beats: list[dict] = []

    def beat(kind_, text, minute=None, who=None, line=None, why="", source="", ref=None, **kw):
        beats.append({"kind": kind_, "text": text, "minute": minute, "time": clock.hhmm(minute) if minute is not None else None,
                      "who": who, "line": line, "why": why, "source": source, "ref": ref, **kw})

    # how it came about
    hd = sc.get("host_decision")
    if org and hd:
        why = _reasons(sim, hd["id"])
        chance = hd.get("prob")
        what = {"gathering": "people over", "dinner": "a dinner", "party": "a party", "game_night": "a game night",
                "study_group": "a study group"}.get(kind, sc["kind_label"].lower())
        beat("decide", f"{org['name']} decides to have {what}.", who=org, why=why,
             source="their choice to host" + (f" · it had a {round(100 * chance)}% chance" if chance is not None else ""),
             ref={"kind": "decision", "id": hd["id"]})
    elif kind == "date" and org and len(sc["people"]) >= 2:
        other = next((p["person"] for p in sc["people"] if p["person"]["id"] != org["id"]), None)
        log, n = sim.log, sim.log.n
        why = ""
        if other:
            t = sim.reg.event_ids.get("asked_out")
            m = np.flatnonzero((log["type"][:n] == t) & (log["a"][:n] == org["id"]) & (log["b"][:n] == other["id"]) & (log["day"][:n] <= sc["day"]))
            if len(m):
                try:
                    why = S.reason_text(S._reasons(S.why(sim, f"event:{int(m[-1])}"), 2))
                except Exception:  # noqa: BLE001
                    why = ""
        beat("setup", f"{org['name']} has been working up the nerve to ask {other['name'] if other else 'someone'} out.",
             who=org, why=why, source="why they asked")
    else:
        beat("setup", f"{sc['kind_label']} — {sc['how']}.", source="how it came about")
    # the invitations, as messages (texts and group chats) or as asking in person
    invited = [p for p in sc["people"] if p["role"] == "invited"]
    lines = INVITE.get(kind, INVITE["_"])
    group_said = False
    for p in invited:
        who, inviter = p["person"], p.get("inviter") or org
        if not who or not inviter:
            continue
        msg = _pick(lines, oid, who["id"]).format(t=t_words)
        chan = p["channel"]
        dec = p.get("decision")
        if chan == "group_chat":
            if not group_said:
                beat("text", "", who=inviter, line=_pick(lines, oid, "group").format(t=t_words), channel="the group chat",
                     source="invitation in the group chat")
                group_said = True
        elif chan in ("text", "app"):
            beat("text", "", who=inviter, to=who, line=msg, channel=p["channel_words"], source=f"invitation by {p['channel_words']}")
        else:
            beat("say", f"{inviter['name']} asks {who['name']} {'in person' if chan == 'in_person' else 'through ' + p['channel_words']}.",
                 who=inviter, to=who, line=msg, source=f"invitation ({p['channel_words']})")
        if kind == "date":
            msg = _pick(ASK_OUT, oid, who["id"])
            beats[-1]["line"] = msg
        r = p["response"]
        if p.get("seen_day") is None:
            beat("unseen", f"{who['name']} never sees it.", who=who, source="the invitation was never seen")
            continue
        why = _reasons(sim, dec["id"]) if dec else ""
        if r == "yes":
            beat("text" if chan != "in_person" else "say", "", who=who, to=inviter, line=_pick(DATE_YES if kind == "date" else YES, oid, who["id"], "y"),
                 why=why, source="their answer", ref={"kind": "decision", "id": dec["id"]} if dec else None)
        elif r == "maybe":
            beat("text" if chan != "in_person" else "say", "", who=who, to=inviter, line=_pick(MAYBE, oid, who["id"]),
                 why=why, source="their answer", ref={"kind": "decision", "id": dec["id"]} if dec else None)
        elif r == "no":
            beat("text" if chan != "in_person" else "say", "", who=who, to=inviter, line=_no_line(dec, (oid, who["id"])),
                 why=why, source="their answer", ref={"kind": "decision", "id": dec["id"]} if dec else None)
        elif r == "no_reply":
            beat("silence", f"{who['name']} sees it and doesn't answer.", who=who, why=why, source="seen, no reply")
    # arrivals in clock order
    came = sorted([p for p in sc["people"] if p["came"]],
                  key=lambda p: (p["role"] != "organizer", p.get("late_minutes") or 0, p["person"]["id"]))
    if sc["status"] == "cancelled":
        beat("note", "In the end it doesn't happen: it was cancelled.", source="the occasion's status")
    for p in came:
        who = p["person"]
        if p["role"] == "organizer":
            if kind == "date":
                beat("stage", f"{who['name']} gets there a few minutes early.", minute=max(start - 5, 0), who=who, source="the organizer")
            elif sc.get("org_kind") in ("household", "user", "engine") and "place" in str(sc.get("place", "")):
                beat("stage", f"{who['name']} gets the place ready.", minute=max(start - 30, 0), who=who, source="the organizer")
            continue
        late = p.get("late_minutes") or 0
        trip = p.get("trip") or {}
        how = []
        if p.get("ride"):
            how.append(f"a ride from {p['ride']['name']}")
        elif trip.get("mode"):
            how.append("just down the hall" if trip["minutes"] <= 1 else
                       f"{trip['minutes']} minutes {MODE_WORDS.get(trip['mode'], 'by ' + trip['mode'].replace('_', ' '))}")
        txt = _pick(ARRIVE, oid, who["id"]).format(a=who["name"])
        if p["role"] == "walked in":
            txt = f"{who['name']} wanders in with a friend, uninvited"
        elif p.get("response") == "no" and (trip.get("minutes") or 0) <= 1:
            txt = f"{who['name']} said no, but it's their place too: they end up in the living room anyway"
            how, late = [], 0
        elif p.get("response") == "no":
            txt = f"{who['name']} said no, but changes their mind and comes"
        if late >= 15:
            txt += f", {late} minutes late"
        beat("arrive", txt + (f" ({', '.join(how)})." if how else "."), minute=start + late, who=who,
             source="arrival, trip and lateness")
    for p in sc["people"]:
        if p.get("no_show"):
            beat("note", f"{p['person']['name']} said yes but never comes.", who=p["person"],
                 why=_reasons(sim, p["no_show"]["id"]), source="their choice on the day")
    # the room: who is drawn to whom, old friends, tension, who hangs back
    ids = [p["person"]["id"] for p in came]
    if kind == "date" and len(ids) == 2:
        _date_dynamics(sim, beat, ids, start, int(sc["end"]), int(sc["day"]))
    elif len(ids) >= 2:
        a_, b_ = np.triu_indices(len(ids), 1)
        A, B = np.array(ids)[a_], np.array(ids)[b_]
        eix = E.find(E.make_keys(A, B))
        ok = eix >= 0
        A, B, eix = A[ok], B[ok], eix[ok]
        mid = start + max(int(sc["end"]) - start, 30) // 2
        if len(eix):
            lo, _hi = E.endpoints()
            clos = E["closeness"][eix]
            busy: set = set()
            for k in np.argsort(-clos)[:6]:
                if len(busy) >= 4:
                    break
                if clos[k] >= 0.45 and not (E["flags"][eix[k]] & Tie.ROMANTIC) and not ({int(A[k]), int(B[k])} & busy):
                    busy |= {int(A[k]), int(B[k])}
                    beat("stage", f"{_first(P, A[k])} and {_first(P, B[k])} end up in the corner catching up for most of the night.",
                         minute=mid, source="how close they are", ref={"kind": "tie", "id": f"{min(A[k], B[k])}-{max(A[k], B[k])}"})
            # attraction: att_lh is how drawn the lower id is to the higher one
            low = lo[eix]
            to_hi = E["att_lh"][eix]
            to_lo = E["att_hl"][eix]
            for k in np.argsort(-(np.maximum(to_hi, to_lo)))[:2]:
                x, y = (A[k], B[k]) if low[k] == A[k] else (B[k], A[k])
                fx, fy = float(to_hi[k]), float(to_lo[k])        # x → y, y → x
                if max(fx, fy) < 0.35:
                    continue
                ref = {"kind": "tie", "id": f"{min(x, y)}-{max(x, y)}"}
                if E["flags"][eix[k]] & Tie.ROMANTIC:
                    beat("stage", f"{_first(P, x)} and {_first(P, y)} sit together, obviously a couple.", minute=mid, source="their relationship", ref=ref)
                elif min(fx, fy) >= 0.35:
                    beat("stage", f"Something between {_first(P, x)} and {_first(P, y)}: they keep finding each other.",
                         minute=mid + 10, source="mutual attraction", ref=ref)
                else:
                    s_, o_ = (x, y) if fx >= fy else (y, x)
                    beat("stage", f"{_first(P, s_)} keeps glancing at {_first(P, o_)}. {_first(P, o_)} doesn't seem to notice.",
                         minute=mid + 10, source="one-sided attraction", ref=ref)
            con = E["conflict"][eix]
            for k in np.argsort(-con)[:1]:
                if con[k] >= 0.3:
                    beat("stage", f"A little tension between {_first(P, A[k])} and {_first(P, B[k])}; they mostly stay on opposite sides of the room.",
                         minute=mid + 20, source="unresolved conflict between them",
                         ref={"kind": "tie", "id": f"{min(A[k], B[k])}-{max(A[k], B[k])}"})
        if "extraversion" in P:
            known = {int(x) for x in np.concatenate([A, B])} if len(A) else set()
            shy = [i for i in ids if P["extraversion"][i] < 0.3 and i not in known]
            for i in shy[:1]:
                beat("stage", f"{_first(P, i)} doesn't know anyone and hangs back by the snacks.", minute=start + 20,
                     source="how outgoing they are, and who they know there")
    for m in sc.get("met", []):
        intro = m.get("introducer")
        beat("meet", (f"{intro['name'].split()[0]} introduces {m['a']['name']} to {m['b']['name']}." if intro
                      else f"{m['a']['name']} and {m['b']['name']} meet."),
             minute=start + 25, who=m["a"], to=m["b"], line=_pick(["have you two met?", "you two would get along", "wait, you don't know each other?"], oid, m["a"]["id"]) if intro else None,
             speaker=intro, source="a new tie that began here",
             ref={"kind": "tie", "id": f"{min(m['a']['id'], m['b']['id'])}-{max(m['a']['id'], m['b']['id'])}"})
    shown_ev = set()
    for ev in sc.get("events", []):
        if ev["type"] in ("hosted_gathering",):
            continue
        mk = (ev["type"], ev["day"], tuple(sorted((ev["a"], ev.get("b") if ev.get("b") is not None else -1))))
        if mk in shown_ev:
            continue
        shown_ev.add(mk)
        try:
            from .trace import _Words
            txt = _Words(sim).event_line(int(ev["id"]))
        except Exception:  # noqa: BLE001
            txt = f"{ev['a_name']}: {ev['label'].lower()}"
        if ev["type"] in ELSEWHERE:
            txt = "Elsewhere: " + txt
        beat("event", txt + ".", minute=int(sc["end"]) - 10, source="an event recorded here", ref={"kind": "event", "id": ev["id"]},
             category=ev.get("category"))
    if sc["status"] == "happened" and kind == "date" and len(ids) == 2:
        beat("wrap", f"Around {clock.hhmm(int(sc['end']))} they say goodbye.", minute=int(sc["end"]), source="when it ended")
    elif sc["status"] == "happened":
        bits = [f"{sc['talks']} conversations"] if sc.get("talks") else []
        if sc.get("new_ties"):
            bits.append(f"{sc['new_ties']} {'person' if sc['new_ties'] == 1 else 'people'} met for the first time")
        bits.append("no arguments" if not sc.get("conflicts") else f"{sc['conflicts']} arguments")
        beat("wrap", f"By {clock.hhmm(int(sc['end']))} it winds down: " + ", ".join(bits) + ".", minute=int(sc["end"]),
             source="the scene's counts")
    beats.sort(key=lambda b_: (b_["minute"] is not None, b_["minute"] if b_["minute"] is not None else 0))
    return {"kind": "occasion", "id": int(oid), "title": sc.get("name") or sc["kind_label"], "place": sc["place"],
            "date": sc["date"], "weekday": sc["weekday"], "time": sc["time"], "status": sc["status"],
            "organizer": org, "cast": [p["person"] for p in came] or [p["person"] for p in sc["people"]][:12],
            "beats": beats, "note": ILLUSTRATIVE}


# ---------------------------------------------------------------------------------------------------- two people
SHORT = {"gathering": "hangout", "ward_activity_plain": "ward activity", "club_social_food": "club social",
         "resident_event": "resident event"}
MET_WORDS = {"unit": "as roommates", "complex": "in their apartment complex", "class": "in class", "ward": "at church",
             "fhe": "in their family home evening group", "work": "at work", "gym": "at the gym", "venue": "out somewhere",
             "gathering": "at a get-together", "campus": "on campus", "app": "on a dating app", "date": "on a date",
             "occasion": "at a get-together", "online": "online", "hangout": "hanging out", "club": "at a club",
             "team": "on a team", "institute": "at institute", "family": "as family", "dance": "at a dance",
             "outdoors": "outdoors", "congregation": "at church"}
PAIR_EVENTS = {"asked_out", "rejected", "first_date", "date", "talking_started", "relationship_started", "first_kiss_with",
               "engaged", "wedding", "breakup_initiated", "breakup_received", "new_friend", "close_friend", "friendship_faded",
               "ghosted", "dealbreaker_found", "dealbreaker_overlooked", "intimacy_step", "ncmo", "app_match",
               "felt_ignored", "assumed_busy", "assumed_not_interested", "spark", "reached_out", "introduced"}


def pair_script(sim, a: int, b: int, limit: int = 120) -> dict:
    """Two people's history as a text thread (see the module docstring)."""
    P, log = sim.w.P, sim.log
    a, b = int(a), int(b)
    for i in (a, b):
        if not 0 <= i < P.n:
            raise KeyError(f"no person {i}")
    n = log.n
    la, lb, lt, ld = log["a"][:n], log["b"][:n], log["type"][:n], log["day"][:n]
    rows = np.flatnonzero(((la == a) & (lb == b)) | ((la == b) & (lb == a)))
    names = sim.reg.event_names
    from .trace import _Words
    W = _Words(sim)
    items: list[tuple] = []           # (day, order, beat)
    seen = set()
    for e in rows.tolist():
        nm = names[int(lt[e])]
        if nm not in PAIR_EVENTS:
            continue
        x, y, d = int(la[e]), int(lb[e]), int(ld[e])
        key = (nm, d, min(x, y))
        if key in seen:
            continue
        seen.add(key)
        did = int(log["decision"][e]) if log["decision"][e] >= 0 else None
        why = _reasons(sim, did) if did is not None else ""
        src = {"kind": "event", "id": int(e)}
        if nm == "asked_out":
            items.append((d, 1, {"kind": "text", "who": {"id": x, "name": W.name(x)}, "line": _pick(ASK_OUT, e), "why": why, "source": "asked out", "ref": src}))
        elif nm == "rejected":           # x was turned down by y
            items.append((d, 2, {"kind": "text", "who": {"id": y, "name": W.name(y)}, "line": _pick(SAID_NO, e), "why": why, "source": "turned down", "ref": src}))
        elif nm == "first_date":
            items.append((d, 3, {"kind": "stage", "text": f"Their first date.", "source": "first date", "ref": src}))
            items.append((d, 4, {"kind": "text", "who": {"id": x, "name": W.name(x)}, "line": _pick(AFTER_DATE, e), "source": "after the date", "ref": src}))
            items.append((d, 5, {"kind": "text", "who": {"id": y, "name": W.name(y)}, "line": _pick(GO_ON, e), "source": "after the date", "ref": src}))
        elif nm == "breakup_initiated":
            items.append((d, 1, {"kind": "text", "who": {"id": x, "name": W.name(x)}, "line": _pick(BREAKUP, e), "why": why, "source": "the breakup", "ref": src}))
            items.append((d, 2, {"kind": "stage", "text": W.event_line(e) + ".", "why": why, "source": "the breakup", "ref": src}))
        elif nm == "engaged":
            items.append((d, 2, {"kind": "stage", "text": W.event_line(e) + ".", "why": why, "source": "engagement", "ref": src}))
            items.append((d, 3, {"kind": "text", "who": {"id": x, "name": W.name(x)}, "line": _pick(ENGAGED, e), "source": "engagement", "ref": src}))
        elif nm in ("felt_ignored", "assumed_busy", "assumed_not_interested"):
            items.append((d, 6, {"kind": "thought", "who": {"id": x, "name": W.name(x)}, "text": W.event_line(e) + ".", "why": why, "source": "how they read the silence", "ref": src}))
        elif nm == "spark":
            items.append((d, 0, {"kind": "thought", "who": {"id": x, "name": W.name(x)},
                                 "text": f"{W.name(x).split()[0]} can't stop thinking about {W.name(y).split()[0]}.", "why": "you made it happen",
                                 "source": "feelings you gave them", "ref": src}))
        elif nm == "date":
            items.append((d, 3, {"kind": "stage", "text": W.event_line(e) + ".", "source": "a date", "ref": src, "fold": "date"}))
        else:
            items.append((d, 3, {"kind": "stage", "text": W.event_line(e) + ".", "why": why, "source": nm.replace("_", " "), "ref": src}))
    # the occasions they were both at (each one can be watched)
    I = sim.book.inv
    if I.n:
        att = I["attended"]
        oa = set(I["occ"][att & (I["person"] == a)].tolist())
        both = sorted(oa & set(I["occ"][att & (I["person"] == b)].tolist()))
        from .scenes import occasion_row
        for o in both[-40:]:
            row = occasion_row(sim, int(o))
            if not row:
                continue
            org = row.get("organizer") or {}
            what = SHORT.get(row["kind"], row["kind_label"].lower()) if not row.get("name") else row["name"]
            first = org["name"].split()[0] if org.get("name") else ""
            whose = f"{first}'s {what}" if first and not row.get("name") else what
            place = "" if first and str(row["place"]).startswith(first) else f", {row['place']}"
            items.append((int(row["day"]), 2, {"kind": "stage", "text": f"Both at {whose} ({row['time'].split('–')[0]}{place}).",
                                               "source": "an occasion they both came to", "ref": {"kind": "occasion", "id": int(o)}}))
    # their texts: the same planned lines, and the same words, as on their phones (analysis/phone.py)
    from . import dialogue as D
    from . import phone as PH
    from ..llm.talk import dialogue as TD
    specs = PH.dm_lines(sim, a, b, since=max(0, sim.w.day - 60))
    texts, _ = TD.apply(sim, specs, (TD.lineage(sim), D.content_key(specs), D.SCHEMA))
    for k, (sp, txt) in enumerate(zip(specs, texts)):
        who = {"id": sp["speaker"], "name": W.name(sp["speaker"])} if sp["speaker"] is not None else None
        ref = {"kind": "exchange", "id": sp["ex"]} if sp.get("ex") is not None else sp.get("ref")
        if sp.get("absent") or sp.get("kind") == "stage":
            items.append((sp["day"], 1, {"kind": "silence", "who": who, "text": txt, "source": D.label_act(sp["act"]), "ref": ref}))
        else:
            items.append((sp["day"], 0, {"kind": "text", "who": who, "line": txt, "source": D.label_act(sp["act"]), "ref": ref,
                                         "order": k}))
    # how they met
    E = sim.w.E
    e0 = E.find(E.make_keys(np.array([a]), np.array([b])))[0]
    if e0 >= 0 and (E["first_day"][e0] >= 0 or E["flags"][e0] & Tie.PREEXISTING):
        from ..engine.state import CTX
        ctx = CTX[int(E["origin_ctx"][e0])] if int(E["origin_ctx"][e0]) < len(CTX) else ""
        intro = int(E["introducer"][e0])
        where = MET_WORDS.get(ctx, f"through {ctx.replace('_', ' ')}" if ctx else "")
        txt = f"They met {where}" + (f", introduced by {W.name(intro)}" if intro >= 0 else "") + "."
        if E["flags"][e0] & Tie.PREEXISTING:
            txt = "They already knew each other when the story began."
        items.append((max(int(E["first_day"][e0]), 0), -1, {"kind": "stage", "text": txt, "source": "where their tie began"}))
    items.sort(key=lambda x: (x[0], x[1]))
    beats, folded = [], None
    for d, _o, bt in items:
        if bt.get("fold") == "date" and folded is not None and folded["day"] >= d - 21:
            folded["n"] += 1
            folded["text"] = f"They keep going out ({folded['n']} dates since {folded['since']})."
            continue
        bt["day"], bt["date"] = d, str(sim.cal.date(d))
        if bt.get("fold") == "date":
            dt = sim.cal.date(d)
            bt["n"], bt["since"] = 1, f"{dt:%b} {dt.day}"  # Windows strftime rejects the no-padding flag
            folded = bt
        beats.append(bt)
    E = sim.w.E
    eix = E.find(E.make_keys(np.array([a]), np.array([b])))[0]
    tie = None
    if eix >= 0:
        lo = min(a, b)
        tie = {"closeness": float(E["closeness"][eix]), "conflict": float(E["conflict"][eix]),
               "drawn_a": float(E["att_lh"][eix] if a == lo else E["att_hl"][eix]),
               "drawn_b": float(E["att_hl"][eix] if a == lo else E["att_lh"][eix]),
               "since": str(sim.cal.date(int(E["first_day"][eix]))) if E["first_day"][eix] >= 0 else None,
               "dates": int(E["dates"][eix])}
    return {"kind": "pair", "a": {"id": a, "name": W.name(a)}, "b": {"id": b, "name": W.name(b)}, "tie": tie,
            "beats": beats[-limit:], "note": ILLUSTRATIVE}
