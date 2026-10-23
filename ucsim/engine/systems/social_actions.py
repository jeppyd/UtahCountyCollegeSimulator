"""Social actions: what the user can arrange in a What-if world, as a world editor or as one person.

    {"target_type": "social", "action": "invite", "as": 812, "people": "roommates", "kind": "dinner",
     "weekday": "sunday", "start": "19:30"}

Actions: invite (a one-off get-together), series (a weekly dinner or study group), reschedule (move an occasion or a
series), introduce (two people meet at a café through someone), ride (someone drives a person to an occasion),
reach_out (a text or a visit), job_offer (an employer offers a person a job), spark (the editor gives one person
feelings for another they know: what happens next — asking out, saying yes — is the model's own romance), ask_out
(someone asks someone they know out now; the answer is the other person's own), break_up (someone ends their
relationship), go_home (someone goes home to family for a few days), set_up (a blind date: two people meet at a café and
arrive open to it; whether they click is still their own attraction), fall_out (two people who know each other have a
falling-out: hurt and conflict on their tie, which the model then lives with — avoiding each other, fading friendships,
breakups), make_up (someone goes to make things right with a person they've hurt or been hurt by; forgiving is the
other person's decision) and happen (something happens to someone: one of the impulse events a What-if can inject,
such as an illness, a failed exam or a family crisis, for just that person).

* **Editor** (no "as"): arranges the opportunity. The people involved still decide with the model's usual reasons —
  attend_occasion for an invitation, take_job for an offer, reach_out for a nudge to get in touch.
* **As a person** ("as": id): what that person could really do — invite only people they know, only at a time they're
  free, only what they can afford, only rides in a car they have. A refused action says why in plain words.

`check(sim, it)` validates and previews (each person involved: free? how long a trip? how late? why not) without
changing anything or drawing random numbers. `apply_action(occasions, k, it)` lowers item k of the intervention list
into the OccasionBook (origin "user", org_kind "user", org_id = k), rides, ties and jobs; events it leads to carry the
typed cause ("action", k). Its draws are keyed on the action's own occasions (occasions._pair_u), so the Original's
numbers never move and re-deciding after a change reuses each person's number.
"""
from __future__ import annotations

import datetime as _dt

import numpy as np
from scipy.special import expit

from .. import clock
from ..ledger import CHANNEL_ID, RESPONSE_ID, STATUS_ID
from ..state import CTX_ID, EdgeStore, Tie

ACTIONS = ("invite", "series", "reschedule", "introduce", "ride", "reach_out", "job_offer", "spark", "ask_out", "break_up",
           "go_home", "set_up", "fall_out", "make_up", "happen")
WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
GROUPS = ("roommates", "housemates", "neighbors", "friends", "close_friends")
ACTION_WORDS = {"invite": "an invitation", "series": "a weekly get-together", "reschedule": "a new time",
                "introduce": "an introduction", "ride": "a ride", "reach_out": "getting in touch", "job_offer": "a job offer",
                "spark": "feelings for someone", "ask_out": "asking someone out", "break_up": "a breakup",
                "go_home": "a trip home", "set_up": "a blind date", "fall_out": "a falling-out", "make_up": "making up",
                "happen": "something happening to them"}
# what can happen to one person (`happen`): impulse events that need no bookkeeping from the system that usually emits them
# (the same ones a What-if may inject into a cohort, minus those that need a second person or a hosting)
HAPPENINGS = ("illness", "car_accident", "exam_failure", "academic_success", "family_crisis", "death_in_family",
              "financial_hardship", "spiritual_experience", "faith_challenge")
FALL_OUT = {"small": 0.35, "real": 0.7, "big": 1.0}       # how bad a falling-out is: words -> severity


class Refused(ValueError):
    """An action that can't be done, with the reason in plain words."""


def _name(P, i: int) -> str:
    from ...analysis.person import synthetic_name
    return synthetic_name(P, int(i))


def _first(P, i: int) -> str:
    return _name(P, i).split()[0]


def _int(x, what: str) -> int:
    try:
        return int(x)
    except (TypeError, ValueError):
        raise Refused(f"{what} must be a person's number, got {x!r}") from None


class _Ctx:
    """One action being checked or applied: the world, the actor and the problems found so far."""

    def __init__(self, sim, it: dict):
        self.sim, self.it = sim, it
        self.P, self.E = sim.w.P, sim.w.E
        self.occ = sim.systems["occasions"]
        self.actor = None if it.get("as") in (None, "", -1) else _int(it.get("as"), "'as'")
        self.problems: list[str] = []
        self.warnings: list[str] = []
        self.people: list[dict] = []

    # ------------------------------------------------------------------ people
    def person(self, x, what: str) -> int:
        i = _int(x, what)
        P = self.P
        if not 0 <= i < P.n:
            raise Refused(f"there is no person {i}")
        if not P["present"][i]:
            raise Refused(f"{_name(P, i)} isn't in Provo–Orem right now")
        return i

    def knows(self, a: int, others) -> np.ndarray:
        others = np.atleast_1d(np.asarray(others, np.int64))
        if not len(others):
            return np.zeros(0, bool)
        return self.E.find(EdgeStore.make_keys(np.full(len(others), a), others)) >= 0

    def group(self, spec, around: int) -> np.ndarray:
        """People named by id, or a group around a person (roommates, neighbors, friends, close friends)."""
        P = self.P
        if spec is None:
            return np.empty(0, np.int64)
        if isinstance(spec, dict) and "ids" in spec:
            spec = spec["ids"]
        if isinstance(spec, str):
            g = spec.strip().lower().replace(" ", "_")
            if g not in GROUPS:
                raise Refused(f"'{spec}' isn't a group I know (use people's numbers or one of: {', '.join(GROUPS)})")
            if around < 0:
                raise Refused(f"'{spec}' needs a person to be around: say who is hosting")
            pres = P["present"]
            if g in ("roommates", "housemates"):
                u = int(P["unit_id"][around])
                out = np.where(pres & (P["unit_id"] == u) & (u >= 0))[0]
            elif g == "neighbors":
                c = int(P["complex_id"][around])
                out = np.where(pres & (P["complex_id"] == c) & (c >= 0) & (P["unit_id"] != P["unit_id"][around]))[0]
                if len(out):      # the neighbors they actually know
                    out = out[self.knows(around, out)]
            else:
                indptr, nbr, _ = self.sim.systems["network"].padded()
                cand = nbr[indptr[around]: indptr[around + 1]].astype(np.int64)
                e = self.E.find(EdgeStore.make_keys(np.full(len(cand), around), cand))
                st = np.where(e >= 0, self.E["stage"][np.maximum(e, 0)], 0)
                out = cand[(st >= (4 if g == "close_friends" else 3)) & pres[cand]]
            out = out[out != around]
            if not len(out):
                raise Refused(f"{_name(P, around)} has no {g.replace('_', ' ')} here right now")
            return np.unique(out).astype(np.int64)
        ids = [self.person(x, "each guest") for x in (spec if isinstance(spec, (list, tuple)) else [spec])]
        return np.unique(np.array([i for i in ids if i != around], np.int64))

    # ------------------------------------------------------------------ time and place
    def when(self, start: int, default_today: bool = True) -> int:
        """The day: `day` (absolute), `day_offset` (from today), `date` (YYYY-MM-DD) or `weekday` (the next one whose
        start is still ahead). Without any: today if the time is still ahead, else tomorrow."""
        sim, it = self.sim, self.it
        today = sim.w.day
        now = sim.w.hour * 60 if getattr(sim, "_phases_done", 0) else 0
        if it.get("day") is not None:
            d = _int(it["day"], "day")
        elif it.get("day_offset") is not None:
            d = today + _int(it["day_offset"], "day_offset")
        elif it.get("date"):
            try:
                d = today + (_dt.date.fromisoformat(str(it["date"])) - sim.cal.date(today)).days
            except ValueError:
                raise Refused(f"'{it['date']}' isn't a date (use YYYY-MM-DD)") from None
        elif it.get("weekday") is not None:
            wd = it["weekday"]
            if isinstance(wd, str):
                key = wd.strip().lower()
                hit = [j for j, nm in enumerate(WEEKDAYS) if nm.startswith(key[:3])]
                if not hit:
                    raise Refused(f"'{wd}' isn't a day of the week")
                wd = hit[0]
            wd = int(wd) % 7
            d = today + (wd - sim.cal.weekday(today)) % 7
            if d == today and start <= now:
                d += 7
        else:
            d = today if (default_today and start > now) else today + 1
        if d < today or (d == today and start <= now):
            raise Refused("that time has already passed")
        if d > today + 365:
            raise Refused("that's more than a year ahead")
        return d

    def clock(self, key: str = "start", default: int | None = None) -> int:
        v = self.it.get(key)
        if v is None:
            if default is None:
                raise Refused(f"say when it starts ('{key}', e.g. \"19:30\")")
            return int(default)
        try:
            m = clock.parse_hhmm(v)
        except (ValueError, TypeError):
            raise Refused(f"'{v}' isn't a clock time (use e.g. \"19:30\" or \"7:30 pm\")") from None
        m = clock.day_minute(m)            # 1 am is the small hours of the same day
        if not 6 * 60 <= m <= 26 * 60:
            raise Refused(f"{clock.hhmm(m)} is too late to start something (the latest is 2 am)")
        return m

    def place(self, host: int, kind: str, near=None) -> tuple[int, float, float, str]:
        """(place id, lon, lat, words). 'home' (the host's apartment), 'venue:<id>', 'campus', or the kind's usual place."""
        sim, w, P = self.sim, self.sim.w, self.P
        act = sim.systems["activity"]
        spec = self.it.get("place")
        where = self.sim.book.vocab[kind].get("where", "venue")
        if spec is None:
            spec = "home" if where == "home" else ("campus" if where == "campus" else "venue")
        spec = str(spec)
        if spec == "home":
            if host < 0:
                raise Refused("a get-together at home needs a host")
            u = int(P["unit_id"][host])
            if u < 0:
                raise Refused(f"{_name(P, host)} has no place of their own here to host at")
            return u, float(w.units.lon[u]), float(w.units.lat[u]), f"{_first(P, host)}'s place"
        if spec == "campus":
            from .occasions import BYU, UVU
            byu = host >= 0 and P["school"][host] == 1
            lon, lat = (BYU[0] + 0.0012, BYU[1] + 0.0018) if byu or host < 0 else (UVU[0] + 0.0010, UVU[1] - 0.0008)
            return -1, lon, lat, "on campus"
        if spec.startswith("venue:"):
            v = _int(spec.partition(":")[2], "venue")
            if not 0 <= v < len(act.v_name):
                raise Refused(f"there is no venue {v}")
            return v, float(act.v_lon[v]), float(act.v_lat[v]), str(act.v_name[v])
        if spec == "venue":       # a café or restaurant near the people involved
            pts = np.atleast_1d(np.asarray(near if near is not None else [host], np.int64))
            lon, lat = float(P["home_lon"][pts].mean()), float(P["home_lat"][pts].mean())
            v = int(act.nearest("food", np.array([lon]), np.array([lat]), 1, np.zeros(1))[0])
            return v, float(act.v_lon[v]), float(act.v_lat[v]), str(act.v_name[v])
        raise Refused(f"'{spec}' isn't a place I know (use home, campus, venue or venue:<id>)")

    # ------------------------------------------------------------------ previews
    def preview(self, people, role: str, day: int, start: int, dur: int, lon: float, lat: float, occ: int = -1,
                host: bool = False, ride=None) -> dict:
        people = np.atleast_1d(np.asarray(people, np.int64))
        if not len(people):
            return {"feasible": []}
        c = self.occ.check_window(people, day, start, dur, lon, lat, occ=occ, ride=ride, host=host)
        P = self.P
        for j, i in enumerate(people.tolist()):
            row = {"id": int(i), "name": _name(P, i), "role": role, "free": bool(c["feasible"][j]),
                   "late": int(c["late"][j]), "travel": int(c["travel"][j]), "mode": c["mode"][j],
                   "arrive": clock.hhmm(c["arrive"][j]), "reason": c["reason"][j]}
            if self.actor is not None and int(i) != self.actor:
                row["knows_actor"] = bool(self.knows(self.actor, [i])[0])
            self.people.append(row)
        return c


# ---------------------------------------------------------------------- check (no changes, no draws)
def check(sim, it: dict) -> dict:
    """Validate a social action and preview it for everyone involved."""
    cx = _Ctx(sim, it)
    out = {"ok": False, "action": it.get("action"), "mode": "as" if cx.actor is not None else "editor",
           "problems": cx.problems, "warnings": cx.warnings, "people": cx.people}
    try:
        plan = _plan(cx)
        out.update(ok=not cx.problems, summary=plan.get("summary"), plan={k: v for k, v in plan.items() if k != "summary"})
    except Refused as e:
        cx.problems.append(str(e))
    if cx.actor is not None and 0 <= cx.actor < sim.w.P.n:
        out["actor"] = {"id": cx.actor, "name": _name(sim.w.P, cx.actor)}
    return out


def _plan(cx: _Ctx) -> dict:
    """Everything an action needs, resolved and checked (raises Refused for a hard stop; collects problems)."""
    it, sim, P = cx.it, cx.sim, cx.P
    a = it.get("action")
    if a not in ACTIONS:
        raise Refused(f"'{a}' isn't an action (use one of: {', '.join(ACTIONS)})")
    if cx.actor is not None:
        cx.person(cx.actor, "'as'")
    return {"invite": _plan_invite, "series": _plan_invite, "reschedule": _plan_reschedule, "introduce": _plan_introduce,
            "ride": _plan_ride, "reach_out": _plan_reach_out, "job_offer": _plan_job, "spark": _plan_spark,
            "ask_out": _plan_ask_out, "break_up": _plan_break_up, "go_home": _plan_go_home, "set_up": _plan_set_up,
            "fall_out": _plan_fall_out, "make_up": _plan_make_up, "happen": _plan_happen}[a](cx)


def _plan_invite(cx: _Ctx) -> dict:
    it, sim, P, occ = cx.it, cx.sim, cx.P, cx.occ
    series = it.get("action") == "series"
    host = cx.actor if cx.actor is not None else (cx.person(it["host"], "host") if it.get("host") is not None else -1)
    if cx.actor is not None and it.get("host") is not None and _int(it["host"], "host") != cx.actor:
        raise Refused(f"acting as {_name(P, cx.actor)}, you can only invite people to something {_first(P, cx.actor)} hosts")
    kind = str(it.get("kind") or ("study_group" if it.get("study") else "dinner"))
    book = sim.book
    if kind not in book.kind_id:
        raise Refused(f"'{kind}' isn't a kind of get-together (try: dinner, gathering, game_night, party, study_group)")
    spec = book.vocab[kind]
    if spec.get("open") or kind == "date":
        raise Refused(f"a {spec.get('label', kind).lower()} isn't something one person invites people to")
    guests = cx.group(it.get("people") if it.get("people") not in (None, [], "") else it.get("group"), host)
    if not len(guests):
        raise Refused("say who is invited ('people': numbers or roommates / friends / neighbors)")
    if len(guests) > 60:
        raise Refused("that's more than 60 people; pick a smaller group")
    c = book.kind_id[kind]
    start = cx.clock("start", int(occ.k_start[c]))
    dur = int(it.get("dur") or occ.k_dur[c])
    if not 15 <= dur <= 600:
        raise Refused("a get-together lasts between 15 minutes and 10 hours")
    day = cx.when(start)
    place, lon, lat, where = cx.place(host, kind, near=np.r_[guests, [host]] if host >= 0 else guests)
    if host < 0 and occ.k_where[c] == "home":
        raise Refused("a get-together at someone's place needs a host ('host' or 'as')")
    cost = float(occ.k_cost[c]) * len(guests) if place >= 0 and occ.k_where[c] == "home" else 0.0
    when_words = f"{['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'][sim.cal.weekday(day)]} {sim.cal.date(day)} at {clock.hhmm(start)}"
    if host >= 0:
        h = cx.preview([host], "host", day, start, dur, lon, lat, host=True)
        if cx.actor is not None:
            if not h["feasible"][0]:
                cx.problems.append(f"{_name(P, host)} isn't free then: {h['reason'][0]}")
            unknown = guests[~cx.knows(host, guests)]
            if len(unknown):
                names = ", ".join(_name(P, i) for i in unknown[:5]) + (" …" if len(unknown) > 5 else "")
                cx.problems.append(f"{_first(P, host)} doesn't know {names} — acting as someone, you can only invite people they know")
            savings = float(P["savings"][host])
            if cost > savings:
                cx.problems.append(f"{_first(P, host)} can't afford it: food for {len(guests)} costs about ${cost:.0f} "
                                   f"and {_first(P, host)} has ${savings:.0f}")
        elif not h["feasible"][0]:
            cx.warnings.append(f"the host isn't free then ({h['reason'][0]}): they would call it off")
    g = cx.preview(guests, "guest", day, start, dur, lon, lat)
    n_free = int(np.sum(g["feasible"]))
    if n_free == 0:
        cx.warnings.append("none of the guests can make that time")
    weeks = None
    if series:
        weeks = it.get("weeks")
        weeks = None if weeks in (None, 0, "") else max(1, min(int(weeks), 52))
    what = spec.get("label", kind).lower()
    who = f"{_first(P, host)}'s" if host >= 0 else "a"
    summary = (f"{who} weekly {what} on {WEEKDAYS[sim.cal.weekday(day)].capitalize()}s at {clock.hhmm(start)}"
               + (f" for {weeks} weeks" if weeks else "") + f", starting {sim.cal.date(day)}" if series else
               f"{who} {what} on {when_words} at {where}") + f": {len(guests)} invited, {n_free} free then"
    if cost:
        summary += f"; food about ${cost:.0f}"
    return {"summary": summary, "host": int(host), "guests": guests.tolist(), "kind": kind, "day": int(day), "start": int(start),
            "dur": dur, "place": int(place), "lon": lon, "lat": lat, "where": where, "weeks": weeks, "cost": round(cost, 2),
            "channel": it.get("channel")}


def _find_occ(cx: _Ctx, oid) -> int:
    O = cx.sim.book.occ
    oid = _int(oid, "occasion")
    if O.pos([oid])[0] < 0:
        raise Refused(f"there is no occasion {oid} (it may be too old)")
    return oid


def _plan_reschedule(cx: _Ctx) -> dict:
    it, sim, P, occ, book = cx.it, cx.sim, cx.P, cx.occ, cx.sim.book
    if it.get("series") is not None:
        S = book.series
        sid = _int(it["series"], "series")
        if S.pos([sid])[0] < 0 or not S.get("active", [sid])[0]:
            raise Refused(f"weekly get-together {sid} isn't running")
        org = int(S.get("organizer", [sid])[0])
        if cx.actor is not None and cx.actor != org:
            raise Refused(f"only the organizer ({_name(P, org)}) can move it")
        start = cx.clock("start", int(S.get("start", [sid])[0]))
        dur = int(it.get("dur") or S.get("dur", [sid])[0])
        wd = it.get("weekday")
        nwd = int(S.get("weekday", [sid])[0])
        if wd is not None:
            nwd = [j for j, nm in enumerate(WEEKDAYS) if nm.startswith(str(wd).lower()[:3])][0] if isinstance(wd, str) else int(wd) % 7
        nxt = sim.w.day + (nwd - sim.cal.weekday(sim.w.day)) % 7
        lon, lat = float(S.get("lon", [sid])[0]), float(S.get("lat", [sid])[0])
        regs = occ.regulars(sid)
        if org >= 0:
            h = cx.preview([org], "host", nxt, start, dur, lon, lat, host=True)
            if cx.actor is not None and not h["feasible"][0]:
                cx.problems.append(f"{_name(P, org)} isn't free then: {h['reason'][0]}")
        cx.preview(regs, "regular", nxt, start, dur, lon, lat)
        return {"summary": f"the weekly get-together moves to {WEEKDAYS[nwd].capitalize()}s at {clock.hhmm(start)}",
                "series": sid, "weekday": nwd, "start": int(start), "dur": dur, "organizer": org}
    oid = _find_occ(cx, it.get("occasion"))
    d = book.describe(oid)
    if d["status"] != "planned":
        raise Refused(f"that {d['kind_label'].lower()} has already {'happened' if d['status'] == 'happened' else 'been called off'}")
    if d["open"]:
        raise Refused("an announced event's time isn't up to one person")
    org = int(d["organizer"])
    if cx.actor is not None and cx.actor != org:
        raise Refused(f"only the organizer ({_name(P, org) if org >= 0 else 'nobody'}) can change the time")
    start = cx.clock("start", int(d["start"]))
    dur = int(it.get("dur") or d["dur"])
    if any(it.get(k) is not None for k in ("day", "day_offset", "date", "weekday")):
        day = cx.when(start)
    else:
        day = int(d["day"])
        now = sim.w.hour * 60 if getattr(sim, "_phases_done", 0) else 0
        if day < sim.w.day or (day == sim.w.day and start <= now):
            raise Refused("that time has already passed")
    lon, lat = d["lon"] if d["lon"] is not None else np.nan, d["lat"] if d["lat"] is not None else np.nan
    inv = book.invitations(oid)
    who = book.inv.get("person", inv).astype(np.int64) if len(inv) else np.empty(0, np.int64)
    walk = book.inv.get("walk_in", inv) if len(inv) else np.zeros(0, bool)
    who = np.unique(who[~walk])
    if org >= 0:
        h = cx.preview([org], "host", day, start, dur, lon, lat, occ=oid, host=True)
        if cx.actor is not None and not h["feasible"][0]:
            cx.problems.append(f"{_name(P, org)} isn't free then: {h['reason'][0]}")
    before = occ.check_window(who, int(d["day"]), int(d["start"]), int(d["dur"]), lon, lat, occ=oid) if len(who) else None
    g = cx.preview(who, "invited", day, start, dur, lon, lat, occ=oid)
    if before is not None:
        for j, row in enumerate(cx.people[-len(who):]):
            row["free_before"] = bool(before["feasible"][j])
        gained = int(np.sum(np.array(g["feasible"]) & ~np.array(before["feasible"])))
        lost = int(np.sum(~np.array(g["feasible"]) & np.array(before["feasible"])))
    else:
        gained = lost = 0
    return {"summary": f"{d['kind_label']} moves to {sim.cal.date(day)} at {clock.hhmm(start)}: {gained} more could come, {lost} couldn't anymore",
            "occasion": oid, "day": int(day), "start": int(start), "dur": dur, "organizer": org}


def _plan_introduce(cx: _Ctx) -> dict:
    it, sim, P, occ = cx.it, cx.sim, cx.P, cx.occ
    a = cx.person(it.get("a"), "'a'")
    b = cx.person(it.get("b"), "'b'")
    if a == b:
        raise Refused("introduce two different people")
    by = cx.actor if cx.actor is not None else (cx.person(it["by"], "'by'") if it.get("by") is not None else -1)
    if by in (a, b):
        raise Refused("someone can't introduce themselves; use reach_out")
    if cx.knows(a, [b])[0]:
        cx.warnings.append(f"{_first(P, a)} and {_first(P, b)} already know each other")
    c = sim.book.kind_id["introduction"]
    start = cx.clock("start", int(occ.k_start[c]))
    dur = int(it.get("dur") or occ.k_dur[c])
    day = cx.when(start)
    people = [x for x in (a, b, by) if x >= 0]
    place, lon, lat, where = cx.place(by, "introduction", near=people)
    if by >= 0:
        h = cx.preview([by], "introducer", day, start, dur, lon, lat, host=True)
        if cx.actor is not None:
            if not h["feasible"][0]:
                cx.problems.append(f"{_name(P, by)} isn't free then: {h['reason'][0]}")
            k = cx.knows(by, [a, b])
            for x, ok in zip((a, b), k):
                if not ok:
                    cx.problems.append(f"{_first(P, by)} doesn't know {_name(P, x)} — you can only introduce people you know")
    cx.preview([a, b], "introduced", day, start, dur, lon, lat)
    return {"summary": f"{_first(P, a)} and {_first(P, b)} meet at {where} on {sim.cal.date(day)} at {clock.hhmm(start)}"
                       + (f", introduced by {_first(P, by)}" if by >= 0 else ""),
            "a": a, "b": b, "by": int(by), "day": int(day), "start": int(start), "dur": dur, "place": int(place),
            "lon": lon, "lat": lat, "where": where}


def _plan_ride(cx: _Ctx) -> dict:
    it, sim, P, occ, book = cx.it, cx.sim, cx.P, cx.occ, cx.sim.book
    oid = _find_occ(cx, it.get("occasion"))
    d = book.describe(oid)
    if d["status"] != "planned":
        raise Refused("that occasion isn't coming up anymore")
    rider = cx.person(it.get("rider"), "rider")
    driver = cx.actor if cx.actor is not None else (cx.person(it["driver"], "driver") if it.get("driver") is not None else -1)
    if driver == rider:
        raise Refused("someone can't give themselves a ride")
    lon, lat = d["lon"] if d["lon"] is not None else np.nan, d["lat"] if d["lat"] is not None else np.nan
    if driver >= 0:
        if not ("owns_car" in P and bool(P["owns_car"][driver])):
            cx.problems.append(f"{_name(P, driver)} doesn't have a car")
        if cx.actor is not None and not cx.knows(driver, [rider])[0]:
            cx.problems.append(f"{_first(P, driver)} doesn't know {_name(P, rider)}")
        dv = cx.preview([driver], "driver", int(d["day"]), int(d["start"]) - 30, 45, lon, lat, occ=oid, host=True)
        if not dv["feasible"][0]:
            cx.problems.append(f"{_name(P, driver)} isn't free to drive then: {dv['reason'][0]}")
    no = cx.preview([rider], "rider (without a ride)", int(d["day"]), int(d["start"]), int(d["dur"]), lon, lat, occ=oid)
    yes = cx.preview([rider], "rider (with the ride)", int(d["day"]), int(d["start"]), int(d["dur"]), lon, lat, occ=oid,
                     ride=np.ones(1, bool))
    gain = "makes it possible" if yes["feasible"][0] and not no["feasible"][0] else (
        f"saves {max(no['travel'][0] - yes['travel'][0], 0)} minutes" if yes["feasible"][0] else "still doesn't get them there in time")
    return {"summary": f"a ride for {_first(P, rider)} to the {d['kind_label'].lower()} ({gain})", "occasion": oid,
            "rider": rider, "driver": int(driver)}


def _plan_reach_out(cx: _Ctx) -> dict:
    it, P = cx.it, cx.P
    src = cx.actor if cx.actor is not None else cx.person(it.get("from"), "'from'")
    dst = cx.person(it.get("to"), "'to'")
    if src == dst:
        raise Refused("reach out to someone else")
    if cx.actor is not None and not cx.knows(src, [dst])[0]:
        cx.problems.append(f"{_first(P, src)} doesn't know {_name(P, dst)} — introduce them first")
    channel = str(it.get("channel") or "text")
    if channel not in ("text", "in_person"):
        raise Refused("reach out by 'text' or 'in_person'")
    how = "texts" if channel == "text" else "drops by to see"
    return {"summary": f"{_first(P, src)} {how} {_first(P, dst)}" + ("" if cx.actor is not None else " (if they decide to)"),
            "from": src, "to": dst, "channel": channel}


def _plan_spark(cx: _Ctx) -> dict:
    it, P = cx.it, cx.P
    if cx.actor is not None:
        raise Refused("nobody can decide to have feelings for someone; spark is the world editor's (leave out 'as')")
    src = cx.person(it.get("from"), "'from'")
    dst = cx.person(it.get("to"), "'to'")
    if src == dst:
        raise Refused("spark feelings for someone else")
    if not cx.knows(src, [dst])[0]:
        cx.problems.append(f"{_first(P, src)} and {_first(P, dst)} have never met — introduce them first")
    strength = float(np.clip(float(it.get("strength", 0.7)), 0.1, 1.0))
    if P["partner_id"][src] == dst:
        cx.warnings.append(f"{_first(P, src)} is already with {_first(P, dst)}")
    E = cx.sim.w.E
    e = E.find(EdgeStore.make_keys(np.array([src]), np.array([dst])))[0]
    if e >= 0 and E["flags"][e] & Tie.EX:
        cx.warnings.append(f"{_first(P, src)} and {_first(P, dst)} used to date: people here rarely ask out an ex, so it may go nowhere")
    mutual = bool(it.get("mutual"))
    if mutual:
        return {"summary": f"{_first(P, src)} and {_first(P, dst)} start to have feelings for each other (who makes a move, "
                           f"and when, is up to them)", "from": src, "to": dst, "strength": strength, "mutual": True}
    return {"summary": f"{_first(P, src)} starts to have feelings for {_first(P, dst)} (whether they act on it, and how "
                       f"{_first(P, dst)} answers, is up to them)", "from": src, "to": dst, "strength": strength}


def _plan_job(cx: _Ctx) -> dict:
    it, sim, P = cx.it, cx.sim, cx.P
    if cx.actor is not None:
        raise Refused("a job offer comes from an employer, not a person: make it as the world editor")
    i = cx.person(it.get("to"), "'to'")
    emp = sim.w.employers
    if it.get("employer") is not None:
        e = _int(it["employer"], "employer")
        if not 0 <= e < len(emp["type"]):
            raise Refused(f"there is no employer {e}")
    else:   # the nearest workplace to home
        d2 = (np.asarray(emp["lon"]) - P["home_lon"][i]) ** 2 * 0.58 + (np.asarray(emp["lat"]) - P["home_lat"][i]) ** 2
        e = int(np.argmin(d2))
    hours = float(it.get("hours") or (15 if P["enrolled"][i] else 30))
    if not 2 <= hours <= 60:
        raise Refused("a job is between 2 and 60 hours a week")
    wage = float(it.get("wage") or max(float(P["wage"][i]), 14.0))
    name = str(emp["name"][e]) if "name" in emp else f"employer {e}"
    note = " (they already have a job; taking it would replace it)" if P["employed"][i] else ""
    return {"summary": f"{name} offers {_first(P, i)} {hours:.0f} hours a week at ${wage:.2f}/h{note}", "to": i, "employer": e,
            "hours": hours, "wage": wage, "shifts": it.get("shifts")}


def _plan_ask_out(cx: _Ctx) -> dict:
    it, P = cx.it, cx.P
    src = cx.actor if cx.actor is not None else cx.person(it.get("from"), "'from'")
    dst = cx.person(it.get("to"), "'to'")
    if src == dst:
        raise Refused("ask someone else out")
    if not cx.knows(src, [dst])[0]:
        cx.problems.append(f"{_first(P, src)} doesn't know {_name(P, dst)} — introduce them first")
    if P["partner_id"][src] == dst:
        cx.problems.append(f"{_first(P, src)} is already with {_first(P, dst)}")
    if P.isin("rel_status", ["married", "engaged"])[dst]:
        cx.warnings.append(f"{_first(P, dst)} is {P.labels('rel_status', [P['rel_status'][dst]])[0]}: expect a no")
    elif P["partner_id"][dst] >= 0:
        cx.warnings.append(f"{_first(P, dst)} is seeing someone: likely a no")
    if P.isin("rel_status", ["dating", "engaged", "married"])[src]:
        cx.warnings.append(f"{_first(P, src)} is already in a relationship")
    return {"summary": f"{_first(P, src)} asks {_first(P, dst)} out (the answer is {_first(P, dst)}'s)", "from": src, "to": dst}


def _plan_break_up(cx: _Ctx) -> dict:
    it, P = cx.it, cx.P
    src = cx.actor if cx.actor is not None else cx.person(it.get("from"), "'from'")
    b = int(P["partner_id"][src])
    if b < 0:
        raise Refused(f"{_name(P, src)} isn't with anyone")
    if P.is_("rel_status", "married")[src]:
        raise Refused("a divorce isn't something to arrange here")
    word = "stops talking to" if P.is_("rel_status", "talking")[src] else "breaks up with"
    return {"summary": f"{_first(P, src)} {word} {_first(P, b)}", "from": src, "partner": b}


def _plan_go_home(cx: _Ctx) -> dict:
    it, sim, P = cx.it, cx.sim, cx.P
    i = cx.actor if cx.actor is not None else cx.person(it.get("who", it.get("from")), "'who'")
    hrs = float(P["home_drive_hours"][i])
    if hrs <= 0.6:
        raise Refused(f"{_first(P, i)}'s family lives right here")
    fam = sim.systems.get("family")
    if fam is None:
        raise Refused("this world has no families away from Provo")
    nights = int(np.clip(int(it.get("nights") or 2), 1, 14))
    how = "flies" if hrs > float(sim.p("family.trip.fly_hours")) else f"drives {hrs:.0f} hours"
    return {"summary": f"{_first(P, i)} goes home for {nights} night{'s' if nights > 1 else ''} ({how})", "who": i, "nights": nights}


def _tie(cx: _Ctx, a: int, b: int) -> int:
    return int(cx.E.find(EdgeStore.make_keys(np.array([a]), np.array([b])))[0])


def _plan_set_up(cx: _Ctx) -> dict:
    """A blind date: an introduction at a café where both arrive open to it. Their attraction is still their own (a
    poor fit stays a poor fit); being set up only adds `open` to what each would feel on meeting."""
    it, sim, P = cx.it, cx.sim, cx.P
    plan = _plan_introduce(cx)
    a, b = plan["a"], plan["b"]
    rom = sim.systems["romance"]
    for x, y in ((a, b), (b, a)):
        if not rom.compatible(np.array([x]), np.array([y]))[0]:
            cx.warnings.append(f"{_first(P, x)} isn't attracted to {'men' if P['sex'][y] == P.code('sex', 'M') else 'women'}: "
                               f"expect a friendly coffee, not a romance")
        if P.isin("rel_status", ["dating", "engaged", "married"])[x]:
            cx.warnings.append(f"{_first(P, x)} is {P.labels('rel_status', [P['rel_status'][x]])[0]}: they may not come, "
                               f"or may not be interested")
    if _tie(cx, a, b) >= 0:
        cx.warnings.append(f"{_first(P, a)} and {_first(P, b)} already know each other: it's a date someone pushed them "
                           f"into, and being set up won't change how they feel")
    opn = float(np.clip(float(it.get("open", 0.25)), 0.0, 0.6))
    plan["open"] = opn
    plan["summary"] = (f"a blind date: {_first(P, a)} and {_first(P, b)} meet at {plan['where']} on {sim.cal.date(plan['day'])} "
                       f"at {clock.hhmm(plan['start'])}" + (f", set up by {_first(P, plan['by'])}" if plan["by"] >= 0 else "")
                       + " (whether they click is up to them)")
    return plan


def _plan_fall_out(cx: _Ctx) -> dict:
    it, P = cx.it, cx.P
    if cx.actor is not None:
        raise Refused("a falling-out isn't something one person decides; make it as the world editor (leave out 'as')")
    a = cx.person(it.get("a", it.get("from")), "'a'")
    b = cx.person(it.get("b", it.get("to")), "'b'")
    if a == b:
        raise Refused("a falling-out takes two people")
    e = _tie(cx, a, b)
    if e < 0:
        raise Refused(f"{_first(P, a)} and {_first(P, b)} don't know each other, so there's nothing to fall out over")
    how = str(it.get("how") or "real")
    if how not in FALL_OUT:
        raise Refused(f"'{how}' isn't how bad a falling-out is (use small, real or big)")
    hurt = float(cx.E["hurt"][e])
    if hurt >= 0.3:
        cx.warnings.append(f"things are already tense between them (hurt {hurt:.2f}): this adds to it")
    words = {"small": "have words", "real": "have a real falling-out", "big": "have a blowup"}[how]
    together = P["unit_id"][a] >= 0 and P["unit_id"][a] == P["unit_id"][b]
    partner = int(P["partner_id"][a]) == b
    after = " (they live together, so they'll keep running into it)" if together else (
        " (couples who fight like this break up more often)" if partner else "")
    return {"summary": f"{_first(P, a)} and {_first(P, b)} {words}{after}", "a": a, "b": b, "how": how,
            "severity": FALL_OUT[how]}


def _plan_make_up(cx: _Ctx) -> dict:
    it, P = cx.it, cx.P
    src = cx.actor if cx.actor is not None else cx.person(it.get("from"), "'from'")
    dst = cx.person(it.get("to"), "'to'")
    if src == dst:
        raise Refused("make up with someone else")
    e = _tie(cx, src, dst)
    if e < 0:
        cx.problems.append(f"{_first(P, src)} doesn't know {_name(P, dst)}")
        return {"summary": "", "from": src, "to": dst}
    hurt, conflict = float(cx.E["hurt"][e]), float(cx.E["conflict"][e])
    if hurt < 0.02 and conflict < 0.05:
        cx.warnings.append("there's nothing between them to make up for: it'll just be a friendly visit")
    return {"summary": f"{_first(P, src)} goes to {_first(P, dst)} to make things right (whether {_first(P, dst)} lets it go "
                       f"is up to them; hurt between them now {hurt:.2f})", "from": src, "to": dst}


def _plan_happen(cx: _Ctx) -> dict:
    it, sim, P = cx.it, cx.sim, cx.P
    if cx.actor is not None:
        raise Refused("this is something that happens to someone: make it as the world editor (leave out 'as')")
    i = cx.person(it.get("who", it.get("to")), "'who'")
    ev = str(it.get("event") or "")
    if ev not in HAPPENINGS:
        raise Refused(f"'{ev}' isn't something that can happen to one person here (use one of: {', '.join(HAPPENINGS)})")
    sev = float(np.clip(float(it.get("severity", 1.0)), 0.25, 4.0))
    if ev in ("exam_failure", "academic_success") and not P["enrolled"][i]:
        cx.warnings.append(f"{_first(P, i)} isn't taking classes right now")
    lab = sim.reg.events[ev].label.lower()
    how = "" if sev == 1.0 else (" (milder than usual)" if sev < 1 else " (harder than usual)" if ev not in
                                 ("academic_success", "spiritual_experience") else " (stronger than usual)")
    return {"summary": f"{_name(P, i)}: {lab}{how}", "who": i, "event": ev, "severity": sev}


# ---------------------------------------------------------------------- apply
def apply_action(occ, k: int, it: dict) -> dict:
    """Lower intervention item k (target_type 'social') into the world. Returns what happened, with any refusal."""
    sim = occ.sim
    cx = _Ctx(sim, it)
    try:
        plan = _plan(cx)
    except Refused as e:
        return {"ok": False, "problems": [str(e)]}
    if cx.problems:
        return {"ok": False, "problems": cx.problems, "people": cx.people}
    a = it["action"]
    fn = {"invite": _do_invite, "series": _do_invite, "reschedule": _do_reschedule, "introduce": _do_introduce,
          "ride": _do_ride, "reach_out": _do_reach_out, "job_offer": _do_job, "spark": _do_spark,
          "ask_out": _do_ask_out, "break_up": _do_break_up, "go_home": _do_go_home, "set_up": _do_set_up,
          "fall_out": _do_fall_out, "make_up": _do_make_up, "happen": _do_happen}[a]
    res = fn(occ, k, it, plan, cx)
    return {"ok": True, "summary": plan.get("summary"), "warnings": cx.warnings, **res}


def _label(it: dict, plan: dict, P) -> str:
    if it.get("occasion_name"):
        return str(it["occasion_name"])[:80]
    host = plan.get("host", -1)
    kind = plan.get("kind", "get-together").replace("_", " ")
    return f"{_first(P, host)}'s {kind}" if host is not None and host >= 0 else kind.capitalize()


def _do_invite(occ, k, it, plan, cx) -> dict:
    sim, P, book = occ.sim, occ.sim.w.P, occ.book
    host, guests = plan["host"], np.asarray(plan["guests"], np.int64)
    label = _label(it, plan, P)
    occ.max_lead = max(occ.max_lead, plan["day"] - sim.w.day + 1)
    if it["action"] == "series":
        weeks = plan["weeks"]
        sid = book.add_series(plan["kind"], sim.cal.weekday(plan["day"]), plan["start"], plan["dur"], first_day=plan["day"],
                              last_day=plan["day"] + 7 * (weeks - 1) if weeks else -1, organizer=host, org_kind="user",
                              org_id=k, ctx=CTX_ID["occasion"], place=plan["place"], lon=plan["lon"], lat=plan["lat"],
                              origin="user", label=label, created_day=sim.w.day)
        occ.series_members[int(sid[0])] = [guests]
        oids = occ.start_series_now(sid)          # today's instance, when the day's planning is already done
        return {"series": int(sid[0]), "occasions": [int(o) for o in oids]}
    oid = book.plan(plan["kind"], plan["day"], plan["start"], plan["dur"], organizer=host, org_kind="user", org_id=k,
                    ctx=CTX_ID["occasion"], place=plan["place"], lon=plan["lon"], lat=plan["lat"], origin="user", label=label,
                    created_day=sim.w.day)
    inv = occ.send_invites(oid, guests, host, plan.get("channel"))
    return {"occasion": int(oid[0]), "invitations": int(len(inv))}


def _do_reschedule(occ, k, it, plan, cx) -> dict:
    if "series" in plan:
        S = occ.book.series
        sid = plan["series"]
        S.set("start", [sid], plan["start"])
        S.set("dur", [sid], plan["dur"])
        if plan["weekday"] != int(S.get("weekday", [sid])[0]):
            S.set("weekday", [sid], plan["weekday"])
            # keep the weekly cadence on the new weekday
            fd = int(S.get("first_day", [sid])[0])
            S.set("first_day", [sid], fd + (plan["weekday"] - occ.sim.cal.weekday(fd)) % 7)
        O = occ.book.occ
        up = O["id"][(O["series"] == sid) & (O["status"] == STATUS_ID["planned"]) & (O["day"] >= occ.sim.w.day)]
        for o in up.tolist():       # an instance already planned moves too
            occ.move(o, int(O.cols["day"][O.pos([o])[0]]), plan["start"], plan["dur"], k)
        return {"series": sid}
    occ.move(plan["occasion"], plan["day"], plan["start"], plan["dur"], k)
    return {"occasion": plan["occasion"]}


def _do_introduce(occ, k, it, plan, cx) -> dict:
    sim, P, book = occ.sim, occ.sim.w.P, occ.book
    by = plan["by"]
    label = str(it.get("occasion_name") or f"{_first(P, plan['a'])} meets {_first(P, plan['b'])}")
    occ.max_lead = max(occ.max_lead, plan["day"] - sim.w.day + 1)
    oid = book.plan("introduction", plan["day"], plan["start"], plan["dur"], organizer=by, org_kind="user", org_id=k,
                    ctx=CTX_ID["occasion"], place=plan["place"], lon=plan["lon"], lat=plan["lat"], origin="user", label=label,
                    created_day=sim.w.day)
    o = int(oid[0])
    occ.occ_extra[o] = {"introduced": sim.p("occasions.action.introduced")}
    occ.introductions[o] = (plan["a"], plan["b"], by, k)
    inv = occ.send_invites(oid, np.array([plan["a"], plan["b"]], np.int64), by, "text")
    return {"occasion": o, "invitations": int(len(inv))}


def _do_ride(occ, k, it, plan, cx) -> dict:
    o, rider, driver = plan["occasion"], plan["rider"], plan["driver"]
    occ.rides[(o, rider)] = driver if driver >= 0 else -2       # −2: a ride from someone the user didn't name
    redo = occ.reconsider(o, [rider])
    return {"occasion": o, "reconsidered": redo}


def _do_reach_out(occ, k, it, plan, cx) -> dict:
    sim, w = occ.sim, occ.sim.w
    P, E, p = w.P, w.E, sim.p
    src, dst = plan["from"], plan["to"]
    did = None
    if cx.actor is None:      # editor: a nudge — they decide whether to get in touch
        enc = sim.systems["encounters"]
        e = E.find(EdgeStore.make_keys(np.array([src]), np.array([dst])))[0]
        F = {"close": 2.0 * float(enc._closeness(np.array([src]), np.array([dst]))[0]),
             "extraversion": 0.4 * float(sim.z("extraversion")[src]),
             "want_company": 0.8 * float(sim.systems["mind"].social_pull()[0][src]),
             "hurt": -2.0 * (float(E["hurt"][e]) if e >= 0 else 0.0)}
        base = p("occasions.action.reach_base")
        pr = float(expit(base + sum(F.values())))
        from .occasions import _pair_u
        go = bool(_pair_u(w.seed, src, 7_000_003 * (k + 1) + dst, 31) < pr)
        did = sim.decisions.record("reach_out", w.day, [src], "reached_out" if go else "did_not", F, base=base,
                                   prob=pr if go else 1 - pr, other=[dst], refs={"close": ("person", [dst])})
        if not go:
            return {"reached_out": False, "decision": int(did[0])}
    ctx = CTX_ID["online"] if plan["channel"] == "text" else CTX_ID["hangout"]
    enc = sim.systems["encounters"]
    a, b = np.array([src], np.int64), np.array([dst], np.int64)
    enc.apply(a, b, np.array([ctx], np.uint8), np.full(1, -1, np.int64), 2, enc.similarity(a, b), np.zeros(1, bool))
    plans = sim.systems.get("plans")
    if plans is not None:
        plans.contacted(a, b)
    ev = sim.emit("reached_out", a, b=b, block=2, mech="occasions.action", salt=5003 + k,
                  decision=did, causes=[("action", [k], 1.0), ("person", b, 0.5)])
    return {"reached_out": True, "event": int(ev[0]), "decision": None if did is None else int(did[0])}


def _do_spark(occ, k, it, plan, cx) -> dict:
    """Raise one person's attraction to another (and keep the tie recent, so it counts as a current interest); the
    romance system's own crushes, asking out and answers take it from there."""
    sim, w = occ.sim, occ.sim.w
    E = w.E
    src, dst = plan["from"], plan["to"]
    e = E.find(EdgeStore.make_keys(np.array([src]), np.array([dst])))
    if e[0] < 0:
        return {"sparked": False}
    now = float(E.attraction_from(e, np.array([src]))[0])
    E.set_attraction_from(e, np.array([src]), np.array([max(now, plan["strength"])], np.float32))
    E.cols["last_day"][e] = np.maximum(E["last_day"][e], w.day)
    ev = sim.emit("spark", np.array([src]), b=np.array([dst]), value=plan["strength"], mech="occasions.action",
                  salt=5101 + k, causes=[("action", [k], 1.0)])
    out = {"sparked": True, "event": int(ev[0]), "before": round(now, 3)}
    if plan.get("mutual"):
        back = float(E.attraction_from(e, np.array([dst]))[0])
        E.set_attraction_from(e, np.array([dst]), np.array([max(back, plan["strength"])], np.float32))
        ev2 = sim.emit("spark", np.array([dst]), b=np.array([src]), value=plan["strength"], mech="occasions.action",
                       salt=5107 + k, causes=[("action", [k], 1.0)])
        out.update(event_back=int(ev2[0]), before_back=round(back, 3))
    return out


def _do_job(occ, k, it, plan, cx) -> dict:
    sim, w = occ.sim, occ.sim.w
    P, p = w.P, sim.p
    i, hours = plan["to"], plan["hours"]
    act = sim.systems["activity"]
    # what the job would look like around their classes (restored if they say no)
    saved = {c: P.internal[c][i].copy() for c in ("shift_start", "shift_end", "shift_mask")}
    saved_cols = {c: P.cols[c][i].copy() for c in ("work_hours", "employed", "employer_id", "wage")}
    P.cols["work_hours"][i] = hours
    P.cols["employed"][i] = True
    shifts = plan.get("shifts")
    if shifts:
        P.internal["shift_start"][i] = -1
        P.internal["shift_end"][i] = -1
        for s in shifts:
            wd = s.get("weekday")
            wd = [j for j, nm in enumerate(WEEKDAYS) if nm.startswith(str(wd).lower()[:3])][0] if isinstance(wd, str) else int(wd) % 7
            P.internal["shift_start"][i, wd] = clock.parse_hhmm(s["start"])
            P.internal["shift_end"][i, wd] = clock.parse_hhmm(s["end"])
        act._shift_mask(np.array([i]))
    else:
        act.assign_shifts(np.array([i]), stream=f"social_action{k}_shifts")
    s, e = P.internal["shift_start"][i].astype(np.int32), P.internal["shift_end"][i].astype(np.int32)
    fitted = float(np.where(s >= 0, e - s, 0).sum()) / 60.0
    clash = bool(P["enrolled"][i]) and fitted < 0.5 * hours
    employed = bool(saved_cols["employed"])
    F = {"money": p("occasions.action.job_money") * (float(P["financial_stress"][i]) - 0.4),
         "school": -p("occasions.action.job_school") * float(P["academic_pressure"][i]) * float(P["enrolled"][i]) * hours / 20.0,
         "has_job": -p("occasions.action.job_has_job") * employed,
         "hours": -p("occasions.action.job_hours") * max(hours - (20 if P["enrolled"][i] else 40), 0)}
    base = p("occasions.action.job_base")
    pr = float(expit(base + sum(F.values())))
    from .occasions import _pair_u
    yes = not clash and bool(_pair_u(w.seed, i, 9_000_011 * (k + 1), 37) < pr)
    did = sim.decisions.record("take_job", w.day, [i], "accepted" if yes else "declined", F, base=base,
                               prob=1.0 if clash else (pr if yes else 1 - pr), constraints={"schedule": [clash]})
    if not yes:
        for c, v in saved.items():
            P.internal[c][i] = v
        for c, v in saved_cols.items():
            P.cols[c][i] = v
        return {"accepted": False, "decision": int(did[0]), "why": "the shifts clash with classes" if clash else "declined"}
    P.cols["employer_id"][i] = plan["employer"]
    P.cols["wage"][i] = plan["wage"]
    ev = sim.emit("job_found", [i], decision=did, mech="occasions.action", salt=5011 + k, causes=[("action", [k], 1.0)])
    return {"accepted": True, "decision": int(did[0]), "event": int(ev[0])}


def _do_ask_out(occ, k, it, plan, cx) -> dict:
    return occ.sim.systems["romance"].ask_now(plan["from"], plan["to"], k)


def _do_break_up(occ, k, it, plan, cx) -> dict:
    return occ.sim.systems["romance"].end_now(plan["from"], k)


def _do_go_home(occ, k, it, plan, cx) -> dict:
    sim = occ.sim
    fam = sim.systems["family"]
    i, day = np.array([plan["who"]], np.int64), sim.w.day
    fam._go(i, day, day + plan["nights"], "weekend", {}, 0.0, np.ones(1), np.ones(1, bool))
    ev = int(fam.trips["event"][fam.trips.n - 1])
    from ..provenance import link
    link(sim, [ev], "action", [k], 1.0)
    return {"went": True, "event": ev, "back_day": day + plan["nights"]}


def _do_set_up(occ, k, it, plan, cx) -> dict:
    P = occ.sim.w.P
    it = {**it, "occasion_name": it.get("occasion_name") or f"Blind date: {_first(P, plan['a'])} and {_first(P, plan['b'])}"}
    res = _do_introduce(occ, k, it, plan, cx)
    occ.setups[res["occasion"]] = plan["open"]
    return res


def _do_fall_out(occ, k, it, plan, cx) -> dict:
    """Hurt and conflict on the tie (what the model already reads: friendships fade, people skip each other's
    get-togethers, couples break up), a little less liking, and a falling-out for each of them."""
    sim, w = occ.sim, occ.sim.w
    E, p = w.E, sim.p
    a, b, sev = plan["a"], plan["b"], plan["severity"]
    key = EdgeStore.make_keys(np.array([a]), np.array([b]))
    e = E.find(key)
    E.cols["hurt"][e] = np.clip(E["hurt"][e] + p("occasions.action.fallout_hurt") * sev, 0, 1)
    E.cols["conflict"][e] = np.clip(E["conflict"][e] + 0.4 * sev, 0, 1)
    E.cols["liking"][e] = np.clip(E["liking"][e] - 0.1 * sev, -1, 1)
    E.cols["last_day"][e] = np.maximum(E["last_day"][e], w.day)
    ev = sim.emit("conflict", [a, b], b=[b, a], value=[-sev, -sev], block=clock.EVENING[0], mech="occasions.action",
                  scale=sev, salt=5303 + k, causes=[("action", [k, k], 1.0)])
    from ..provenance import link
    link(sim, ev, "tie", np.r_[key, key], 1.0, "the_tie")
    return {"event": int(ev[0]), "hurt": round(float(E["hurt"][e][0]), 3)}


def _do_make_up(occ, k, it, plan, cx) -> dict:
    """They see each other in person; the other decides whether to let it go (closeness and agreeableness for, the
    hurt against). Forgiven: most of the hurt and conflict lift. Not: the visit happened, the hurt stays."""
    sim, w = occ.sim, occ.sim.w
    E, p = w.E, sim.p
    src, dst = plan["from"], plan["to"]
    e = E.find(EdgeStore.make_keys(np.array([src]), np.array([dst])))
    hurt = float(E["hurt"][e][0])
    F = {"close": p("occasions.action.forgive_close") * float(E["closeness"][e][0]),
         "agreeable": 0.6 * float(sim.z("agreeableness")[dst]),
         "hurt": -p("occasions.action.forgive_hurt") * hurt}
    base = p("occasions.action.forgive_base")
    pr = float(expit(base + sum(F.values())))
    from .occasions import _pair_u
    yes = bool(_pair_u(w.seed, dst, 7_100_019 * (k + 1) + src, 47) < pr)
    did = sim.decisions.record("forgive", w.day, [dst], "forgave" if yes else "still_hurt", F, base=base,
                               prob=pr if yes else 1 - pr, other=[src], refs={"close": ("person", [src])})
    enc = sim.systems["encounters"]
    a, b = np.array([src], np.int64), np.array([dst], np.int64)
    if yes:
        E.cols["hurt"][e] = E["hurt"][e] * 0.3
        E.cols["conflict"][e] = E["conflict"][e] * 0.5
    enc.apply(a, b, np.array([CTX_ID["hangout"]], np.uint8), np.full(1, -1, np.int64), clock.EVENING[0], enc.similarity(a, b),
              np.zeros(1, bool))
    ev = sim.emit("made_up" if yes else "apology_refused", a, b=b, block=clock.EVENING[0], mech="occasions.action",
                  salt=5311 + k, decision=did, causes=[("action", [k], 1.0), ("person", b, 0.5)])
    return {"forgiven": yes, "event": int(ev[0]), "decision": int(did[0]), "chance": round(pr, 3),
            "hurt_before": round(hurt, 3), "hurt": round(float(E["hurt"][e][0]), 3)}


def _do_happen(occ, k, it, plan, cx) -> dict:
    sim = occ.sim
    ev = sim.emit(plan["event"], [plan["who"]], mech="occasions.action", scale=plan["severity"], salt=5401 + k,
                  causes=[("action", [k], 1.0)])
    return {"event": int(ev[0])}
