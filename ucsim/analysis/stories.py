"""Developing stories: situations in the records that are still unfolding, found by pattern (story sifting, in the
spirit of Winnow) over the social records (engine/systems/social.py). Read-only and observational: nothing here
draws a number, changes a world or nudges anyone. What it surfaces is what's interesting to follow, chosen for
variety, not a sample of how life usually goes there.

Patterns:
* reaching out again: someone whose text went unanswered (or who felt left out) is deciding what to do about it;
* two readings: one person believes the other isn't interested, while the other's real reason was something else;
* a promise coming due: "next time for sure" with the next time near;
* changed their mind: a belief revised by something the other person did (a reply, an explanation, support);
* getting closer: a pair with several warm moments lately;
* an app match heading somewhere: a dating-app conversation that's chatting, asked or has a date set.
"""
from __future__ import annotations

import numpy as np

from ..engine.state import Tie
from ..engine.systems import social as S
from .phone import PROP_WORDS, WITHHELD_WORDS, _name, _who

NOTE = ("Picked for being interesting to follow and for variety. It's not representative of how often things like "
        "this happen. Everything here comes from the records; nothing is predicted.")
KIND_TITLES = {"reaching_out": "Reaching out again", "two_readings": "Two readings of the same thing",
               "promise_due": "A promise coming due", "changed_mind": "Changed their mind",
               "getting_closer": "Getting closer", "app_match": "An app match going somewhere"}


def _first(sim, i) -> str:
    return (_name(sim, i) or "someone").split()[0]


def developing(sim, people: list[int] | None = None, limit: int = 12, days: int = 14) -> dict:
    soc = sim.systems.get("social")
    if soc is None:
        return {"stories": [], "note": NOTE}
    day = int(sim.w.day)
    pp = None if not people else np.asarray(people, np.int64)

    def mine(*cols):
        if pp is None:
            return np.ones(len(cols[0]), bool)
        return np.logical_or.reduce([np.isin(c, pp) for c in cols])
    found: list[dict] = []

    # reaching out again / a promise coming due (open concerns)
    C = soc.concerns.t
    if C.n:
        own, oth, kind = C["owner"], C["other"], C["kind"]
        m = (C["status"] == S.CSTAT["open"]) & (C["opened"] >= day - days) & mine(own, oth)
        for r in np.flatnonzero(m).tolist():
            k = S.CONCERNS[int(kind[r])]
            a, b = int(own[r]), int(oth[r])
            imp = float(C.cols["importance"][r])
            st = S.STANCES[int(C.cols["stance"][r])]
            if k == "promise":
                due = int(C.cols["deadline"][r])
                if due < day or due > day + 7:
                    continue
                found.append({"kind": "promise_due", "people": [a, b], "day": int(C.cols["opened"][r]), "score": imp + 0.3,
                              "summary": f"{_first(sim, a)} told {_first(sim, b)} they'd come next time. The next time is "
                                         f"{'today' if due == day else 'in ' + str(due - day) + ' day' + ('s' if due - day != 1 else '')}.",
                              "links": {"concern": int(C.ids[r])}})
            elif k in ("unanswered", "left_out"):
                what = "a text went unanswered" if k == "unanswered" else f"they weren't invited to {_first(sim, b)}'s get-together"
                doing = {"waiting": "waiting to see", "withdrew": "pulling back", "raised": "brought it up",
                         "checked_in": "texted again", "asked": "asked what's up"}.get(st, "deciding what to do")
                found.append({"kind": "reaching_out", "people": [a, b], "day": int(C.cols["opened"][r]), "score": imp,
                              "summary": f"{_first(sim, a)} noticed {what} and is {doing}.",
                              "links": {"concern": int(C.ids[r]), "exchange": int(C.cols["evidence"][r]) if C.cols["evidence"][r] >= 0 else None}})

    # two readings / changed their mind (beliefs)
    B = soc.beliefs.t
    X = soc.ex.t
    if B.n:
        own, ab, prop = B["owner"], B["about"], B["prop"]
        neg = np.isin(prop, [S.PROP["not_interested"], S.PROP["ignoring_me"]])
        m = B["active"] & neg & (B["formed"] >= day - days) & mine(own, ab)
        for r in np.flatnonzero(m).tolist():
            ev = int(B.cols["evidence"][r])
            p = X.pos([ev])[0] if ev >= 0 else -1
            if p < 0:
                continue
            w = int(X.cols["withheld"][p]) or int(X.cols["said"][p])
            if not (1 <= w <= 8):           # their real reason was something ordinary (work, class, a clash, being sick...)
                continue
            a, b = int(own[r]), int(ab[r])
            pr = S.PROPS[int(prop[r])]
            found.append({"kind": "two_readings", "people": [a, b], "day": int(B.cols["formed"][r]),
                          "score": 0.5 + float(B.cols["conf"][r]),
                          "summary": f"{_first(sim, a)} thinks {PROP_WORDS[pr].format(o=_first(sim, b))}. "
                                     f"{_first(sim, b)}'s real reason was {WITHHELD_WORDS.get(w, 'something else')}.",
                          "links": {"exchange": ev, "belief": int(B.ids[r])}})
        m = (B["revised_by"] >= 0) & (B["revised_day"] >= day - days) & neg & mine(own, ab)
        for r in np.flatnonzero(m).tolist():
            a, b = int(own[r]), int(ab[r])
            pr = S.PROPS[int(prop[r])]
            found.append({"kind": "changed_mind", "people": [a, b], "day": int(B.cols["revised_day"][r]),
                          "score": 0.6 + float(B.cols["first_conf"][r]),
                          "summary": f"{_first(sim, a)} had decided {PROP_WORDS[pr].format(o=_first(sim, b))}, then something "
                                     f"{_first(sim, b)} did changed that.",
                          "links": {"exchange": int(B.cols["revised_by"][r]), "belief": int(B.ids[r])}})

    # getting closer (several warm moments in a pair lately)
    if X.n:
        lo = int(np.searchsorted(X["day"], day - days)) if X.n else 0
        warm = lo + np.flatnonzero((X["act"][lo:] == S.ACT["warm_moment"]) & mine(X["speaker"][lo:], X["to"][lo:]))
        if len(warm):
            pairs, cnt = np.unique(X["pair"][warm], return_counts=True)
            E = sim.w.E
            for pk, n in zip(pairs[cnt >= 3].tolist(), cnt[cnt >= 3].tolist()):
                r = warm[X["pair"][warm] == pk][-1]
                a, b = int(X.cols["speaker"][r]), int(X.cols["to"][r])
                e = E.find(E.make_keys(np.array([a]), np.array([b])))[0]
                if e >= 0 and (int(E["flags"][e]) & (Tie.ROMANTIC | Tie.SPOUSE)):      # a couple isn't a friendship forming
                    continue
                if e >= 0 and float(E["closeness"][e]) >= 0.7:                          # already close
                    continue
                found.append({"kind": "getting_closer", "people": [a, b], "day": int(X.cols["day"][r]), "score": 0.3 + 0.1 * n,
                              "summary": f"{_first(sim, a)} and {_first(sim, b)} have had {n} good conversations in two weeks.",
                              "links": {"exchange": int(X.ids[r])}})

    # an app match going somewhere
    T = soc.app.t
    if T.n:
        st = T["stage"]
        m = np.isin(st, [S.APP["chatting"], S.APP["asked"], S.APP["date_set"]]) & (T["last_day"] >= day - days) & mine(T["a"], T["b"])
        for r in np.flatnonzero(m).tolist():
            a, b = int(T.cols["a"][r]), int(T.cols["b"][r])
            s = S.APP_STAGES[int(st[r])]
            dd = int(T.cols["date_day"][r])
            words = {"chatting": "have been talking on the app", "asked": "are waiting on an answer to a date",
                     "date_set": "have a date set" + (f" for {sim.cal.date(dd).strftime('%A')}" if dd >= day else "")}[s]
            found.append({"kind": "app_match", "people": [a, b], "day": int(T.cols["last_day"][r]),
                          "score": {"chatting": 0.4, "asked": 0.7, "date_set": 0.8}[s],
                          "summary": f"{_first(sim, a)} and {_first(sim, b)} matched {day - int(T.cols['matched'][r])} days ago and {words}.",
                          "links": {"app": int(T.ids[r])}})

    # rank: importance, then recency; then diversify (kinds take turns; nobody more than twice)
    for f in found:
        f["score"] = round(f["score"] * (0.6 + 0.4 * max(0.0, 1 - (day - f["day"]) / max(days, 1))), 3)
    found.sort(key=lambda f: (-f["score"], -f["day"]))
    by_kind: dict[str, list[dict]] = {}
    for f in found:
        by_kind.setdefault(f["kind"], []).append(f)
    out, seen = [], {}
    while len(out) < limit and any(by_kind.values()):
        for k in list(by_kind):
            while by_kind[k]:
                f = by_kind[k].pop(0)
                if all(seen.get(p, 0) < 2 for p in f["people"]):
                    break
            else:
                continue
            for p in f["people"]:
                seen[p] = seen.get(p, 0) + 1
            f["title"] = KIND_TITLES[f["kind"]]
            f["who"] = [_who(sim, p) for p in f["people"]]
            f["date"] = str(sim.cal.date(f["day"]))
            f["links"] = {k2: v for k2, v in f["links"].items() if v is not None}
            out.append(f)
            if len(out) >= limit:
                break
    counts = {k: sum(1 for f in found if f["kind"] == k) for k in KIND_TITLES}
    return {"stories": out, "found": counts, "today": day, "note": NOTE}
