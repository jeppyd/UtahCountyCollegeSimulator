"""Phones, dating apps, listening in and perspectives: read-only views over the recorded communication.

Sources (nothing here draws a number or changes a world):
* texts: messaging acts between two people (check-ins, replies, silences, plan changes), invitations sent by text with
  their answers (OccasionBook: what the no said and why), and the social exchanges that rode on them (a late reply's
  apology, a clarification, a disclosure) — one message per actual act, the same on both phones;
* group chats: invitations posted there and the answers to them, news, plans called off — shown only for the time the
  viewer was a member (their membership history), with everyday chatter summarized, never invented;
* dating apps: the app thread (match, opener, replies, chatting, an ask and its answer, or the silence that ended it);
* in person: the conversations the engine kept (consequential ones always, ordinary talk as a fixed sample).

Each planned line (analysis/dialogue.py) carries its record ids, so its wording can be realized once and shared.
"""
from __future__ import annotations

import numpy as np

from ..engine import clock
from ..engine.ledger import CAUSE_KINDS, CHANNEL_ID, RESPONSE_ID
from ..engine.state import CTX
from ..engine.systems import social as S
from . import dialogue as D
from .person import synthetic_name

NEWS_FIRST = {"engaged": "WE'RE ENGAGED 💍", "wedding": "we're married!!", "relationship_started": "so... I'm dating someone 🙈",
              "mission_call": "I got my mission call!!", "mission_departure": "heading out on my mission, love you all",
              "mission_return": "I'm home!!", "graduation": "I graduated!!", "job_lost": "lost my job today, ugh",
              "pregnancy": "we have some news 👶", "birth": "baby is here!!", "baptized": "I got baptized today",
              "breakup_initiated": "we broke up. I'm okay", "breakup_received": "we broke up. not doing great",
              "death_in_family": "we lost someone in my family. would appreciate prayers", "left_area": "moving away, gonna miss you all"}
PLACE_CTX = {"unit": "at home", "complex": "around the complex", "class": "in class", "ward": "at church", "fhe": "at FHE",
             "work": "at work", "gym": "at the gym", "venue": "out", "gathering": "at a get-together", "campus": "on campus",
             "dance": "at a dance", "outdoors": "outdoors", "hangout": "hanging out", "online": "on a call", "club": "at their club",
             "team": "at practice", "institute": "at institute", "congregation": "at church"}
GAP_NOTE = "Routine chatter is summarized; the exchanges that mattered are shown."


def _name(sim, i) -> str | None:
    i = int(i)
    return synthetic_name(sim.w.P, i) if 0 <= i < sim.w.P.n else None


def _who(sim, i) -> dict | None:
    n = _name(sim, i) if i is not None and int(i) >= 0 else None
    return {"id": int(i), "name": n} if n else None


def _soc(sim):
    return sim.systems.get("social")


def kept_since(sim) -> int:
    """The first day whose detailed messages are still kept (older ones thinned to what mattered)."""
    return max(0, sim.w.day - int(getattr(sim, "detail_days", 120)))


def _ex_rows(sim, mask) -> np.ndarray:
    return np.flatnonzero(mask)


def _occ_slots(sim, oid, said_day) -> dict:
    sl = D.occ_slots(sim, oid)
    if sl:
        sl["when"] = D._when(sim, sl, said_day)
        sl["at_home"] = sl.get("kind") in ("dinner", "gathering", "game_night", "party", "movie_night")
    return sl


# ------------------------------------------------------------------------------------------------------------- texts
def dm_lines(sim, i: int, j: int, since: int | None = None, until: int | None = None) -> list[dict]:
    """The planned lines of i and j's text thread, in order (the same list from either phone)."""
    i, j = int(i), int(j)
    M = sim.systems.get("messaging")
    soc = _soc(sim)
    from ..engine.systems.messaging import ACTS
    lo = -10 ** 9 if since is None else int(since)
    hi = 10 ** 9 if until is None else int(until)
    out: list[tuple] = []
    X = soc.ex.t if soc is not None else None
    # social exchanges that ride on a message or an invitation (indexed by what they ride on)
    by_msg, by_inv, free = {}, {}, []
    if X is not None and X.n:
        pk = int(S.ukey(i, j))
        rows = np.flatnonzero((X["pair"] == pk) & (X["day"] >= lo) & (X["day"] <= hi))
        for r in rows.tolist():
            ch = int(X.cols["channel"][r])
            if ch not in (CHANNEL_ID["text"],):
                continue
            if X.cols["msg"][r] >= 0:
                by_msg.setdefault(int(X.cols["msg"][r]), []).append(r)
            elif X.cols["inv"][r] >= 0:
                by_inv[int(X.cols["inv"][r])] = r
            else:
                free.append(r)
    if M is not None and M.acts.n:
        A = M.acts
        s, t = A["sender"], A["to"]
        m = (A["thread"] < 0) & (((s == i) & (t == j)) | ((s == j) & (t == i))) & (A["day"] >= lo) & (A["day"] <= hi)
        for r in np.flatnonzero(m).tolist():
            kind = ACTS[int(A.cols["kind"][r])]
            mid = int(A.ids[r])
            sp, to, d, b = int(A.cols["sender"][r]), int(A.cols["to"][r]), int(A.cols["day"][r]), int(A.cols["block"][r])
            xs = by_msg.get(mid, [])
            xact = S.ACTS[int(X.cols["act"][xs[0]])] if xs else None
            if kind == "checkin":
                act = {"ask_clarify": "ask_clarify", "checkin": "checkin_again"}.get(xact, "checkin")
                sl = {"topic": "silence"} if act == "ask_clarify" else {}
                out.append((d, b, mid, D.line(sp, to, act, "text", d, b, sl, msg=mid, ex=int(X.ids[xs[0]]) if xs else None)))
                if A.cols["replied_day"][r] < 0 and A.cols["day"][r] < sim.w.day - 2 and not xs:
                    pass
            elif kind == "reply":
                act, sl = "reply", {}
                exid = None
                if xs:
                    x = xs[0]
                    exid = int(X.ids[x])
                    act = {"late_reply": "late_reply", "clarify": "clarify", "disclose": "disclose", "deflect": "deflect",
                           "reply": "reply"}.get(xact, "reply")
                    if act == "late_reply":
                        sl = {"apology": bool(X.cols["said"][x])}
                    elif act == "clarify":
                        sl = {"topic": "silence", "reason": S.WHY[int(X.cols["said"][x])] if 0 <= X.cols["said"][x] < len(S.WHY) else "none"}
                    elif act == "disclose":
                        sl = {"topic": "struggle"}
                out.append((d, b, mid, D.line(sp, to, act, "text", d, b, sl, msg=mid, ex=exid)))
            elif kind == "silence":
                # the absence of a reply, shown to both as such (never a message the silent person sent)
                exid = int(X.ids[xs[0]]) if xs else None
                out.append((d, 3, mid, D.line(sp, to, "no_reply", "text", d, 3,
                                               {"text": f"No reply from {_name(sim, sp).split()[0]}."}, msg=mid, ex=exid, absent=True)))
            elif kind == "plan_change":
                out.append((d, b, mid, D.line(sp, to, "plan_change", "text", d, b, _occ_slots(sim, int(A.cols["ref"][r]), d), msg=mid,
                                               ref={"kind": "occasion", "id": int(A.cols["ref"][r])})))
    # invitations by text, and their answers
    I = sim.book.inv
    if I.n:
        m = (I["thread"] < 0) & (I["channel"] == CHANNEL_ID["text"]) & (
            ((I["inviter"] == i) & (I["person"] == j)) | ((I["inviter"] == j) & (I["person"] == i))) & \
            (I["sent_day"] >= lo) & (I["sent_day"] <= hi)
        for r in np.flatnonzero(m).tolist():
            iid = int(I.ids[r])
            inviter, person = int(I.cols["inviter"][r]), int(I.cols["person"][r])
            occ = int(I.cols["occ"][r])
            d0, b0 = int(I.cols["sent_day"][r]), int(I.cols["sent_block"][r])
            sl = _occ_slots(sim, occ, d0)
            out.append((d0, b0, iid * 2, D.line(inviter, person, "invite", "text", d0, b0, sl, inv=iid,
                                                ref={"kind": "occasion", "id": occ}, licensed={"invite": True})))
            resp = int(I.cols["response"][r])
            dd = int(I.cols["decided_day"][r])
            if I.cols["seen_day"][r] < 0:
                if sim.w.day > d0:
                    out.append((d0, b0, iid * 2 + 1, D.line(person, inviter, "unseen", "text", d0, b0,
                                                            {"text": f"{_name(sim, person).split()[0]} never saw it."}, inv=iid, absent=True)))
                continue
            if dd < 0 or resp == RESPONSE_ID["pending"]:
                continue
            x = by_inv.get(iid)
            exid = int(X.ids[x]) if x is not None else None
            said = int(I.cols["said"][r]) if "said" in I.cols else 0
            why = S.WHY[int(I.cols["why"][r])] if "why" in I.cols and 0 <= I.cols["why"][r] < len(S.WHY) else "none"
            if resp == RESPONSE_ID["yes"]:
                ln = D.line(person, inviter, "accept", "text", dd, b0, {}, inv=iid, ex=exid, licensed={"accept": True})
            elif resp == RESPONSE_ID["maybe"]:
                ln = D.line(person, inviter, "maybe", "text", dd, b0, {}, inv=iid, ex=exid)
            elif resp == RESPONSE_ID["no"]:
                promise = x is not None and S.ACTS[int(X.cols["act"][x])] == "promise"
                act = "decline_explained" if said == 1 or promise else "decline_brief"
                ln = D.line(person, inviter, act, "text", dd, b0,
                            {"reason": why if act == "decline_explained" else "none", "promise": promise,
                             "withheld": why if act == "decline_brief" else None},
                            inv=iid, ex=exid, licensed={"decline": True, "promise": promise})
            else:
                ln = D.line(person, inviter, "no_reply", "text", dd, b0, {"text": f"{_name(sim, person).split()[0]} saw it and didn't answer."},
                            inv=iid, absent=True)
            out.append((dd, max(b0, 0), iid * 2 + 1, ln))
    # what rode on nothing else: support after a disclosure, a clarification after being left out, the reassurance
    if X is not None:
        for r in free:
            act = S.ACTS[int(X.cols["act"][r])]
            if act in S.ABSENT and act != "no_reply":
                continue                 # pulling back or avoiding isn't a message (perspectives show it)
            sp, to = int(X.cols["speaker"][r]), int(X.cols["to"][r])
            d, b = int(X.cols["day"][r]), int(X.cols["block"][r])
            sl = {"topic": S.TOPICS[int(X.cols["topic"][r])]}
            absent = act == "no_reply"
            if act == "clarify":
                sl["reason"] = S.WHY[int(X.cols["said"][r])] if 0 <= X.cols["said"][r] < len(S.WHY) else "none"
            if act == "ask_clarify":
                sl["channel_text"] = True
            if act == "reassure":
                sl["held"] = bool(X.cols["said"][r])
            if absent:
                sl["text"] = f"No reply from {_name(sim, sp).split()[0]}."
            out.append((d, b, 10 ** 12 + int(X.ids[r]), D.line(sp, to, act, "text", d, b, sl, ex=int(X.ids[r]), absent=absent)))
    out.sort(key=lambda x: (x[0], x[1], x[2]))
    return [x[3] for x in out]


def group_lines(sim, viewer: int, t: int, since: int | None = None, until: int | None = None) -> tuple[list[dict], dict]:
    """A group chat's planned lines that the viewer could see (while they were a member), and the membership view."""
    M = sim.systems["messaging"]
    Mm = M.members
    rows = np.flatnonzero((Mm["thread"] == t) & (Mm["person"] == int(viewer)))
    spans = [(int(Mm.cols["joined"][r]), int(Mm.cols["left"][r]) if Mm.cols["left"][r] >= 0 else 10 ** 9) for r in rows]
    lo = -10 ** 9 if since is None else int(since)
    hi = 10 ** 9 if until is None else int(until)
    vis = lambda d: any(a <= d <= b for a, b in spans)       # noqa: E731
    from ..engine.systems.messaging import ACTS
    A = M.acts
    out, hidden = [], 0
    for r in np.flatnonzero((A["thread"] == t) & (A["day"] >= lo) & (A["day"] <= hi)).tolist():
        d, b = int(A.cols["day"][r]), int(A.cols["block"][r])
        if not vis(d):
            hidden += 1
            continue
        kind = ACTS[int(A.cols["kind"][r])]
        sp = int(A.cols["sender"][r])
        mid = int(A.ids[r])
        if kind == "invite":
            occ = int(A.cols["ref"][r])
            out.append((d, b, mid, D.line(sp, -1, "invite_group", "group_chat", d, b, _occ_slots(sim, occ, d), msg=mid,
                                          ref={"kind": "occasion", "id": occ}, licensed={"invite": True})))
            # the answers posted to the chat (visible to everyone in it then)
            I = sim.book.inv
            ans = np.flatnonzero((I["occ"] == occ) & (I["thread"] == t) & (I["decided_day"] >= 0)
                                 & np.isin(I["response"], [RESPONSE_ID["yes"], RESPONSE_ID["no"]]))
            for q in ans[:30].tolist():
                who = int(I.cols["person"][q])
                dd = int(I.cols["decided_day"][q])
                if not vis(dd):
                    continue
                yes = I.cols["response"][q] == RESPONSE_ID["yes"]
                said = int(I.cols["said"][q]) if "said" in I.cols else 0
                why = S.WHY[int(I.cols["why"][q])] if "why" in I.cols else "none"
                act = "accept" if yes else ("decline_explained" if said == 1 else "decline_brief")
                out.append((dd, b, mid + 0.001 * (q % 997 + 1), D.line(who, sp, act, "group_chat", dd, b,
                                                                     {"reason": why if act == "decline_explained" else "none"},
                                                                     inv=int(I.ids[q]), licensed={"accept": bool(yes), "decline": not yes})))
        elif kind == "news":
            ev = int(A.cols["event"][r])
            nm = sim.reg.event_names[int(sim.log["type"][ev])] if 0 <= ev < sim.log.n else ""
            if sp < 0:
                from .trace import _Words
                txt = "From home: " + _Words(sim).event_line(ev)
            else:
                txt = NEWS_FIRST.get(nm, sim.reg.events[nm].label if nm in sim.reg.events else "news")
            out.append((d, b, mid, D.line(sp if sp >= 0 else None, -1, "news", "group_chat", d, b, {"text": txt, "event": nm},
                                          msg=mid, ref={"kind": "event", "id": ev}, licensed={"news": nm})))
        elif kind == "plan_change":
            occ = int(A.cols["ref"][r])
            out.append((d, b, mid, D.line(sp, -1, "plan_change", "group_chat", d, b, _occ_slots(sim, occ, d), msg=mid,
                                          ref={"kind": "occasion", "id": occ})))
    out.sort(key=lambda x: (x[0], x[1], x[2]))
    T = M.threads
    p = T.pos([int(t)])[0]
    # everyday chatter isn't stored message by message: a summary line stands in for each stretch between kept messages
    vol = float(T.cols["volume"][p]) if p >= 0 else 0.0
    if vol >= 0.5 and out:
        filled, prev = [], None
        for x in out:
            if prev is not None and x[0] - prev >= 2:
                n = int(round(vol * (x[0] - prev)))
                filled.append((prev, 3, -1, D.line(None, -1, "chatter", "group_chat", prev, 3,
                                                   {"text": f"{x[0] - prev - 1 or 1} day{'s' if x[0] - prev > 2 else ''} of everyday "
                                                            f"chatter (about {n} messages at the chat's recent pace), summarized"},
                                                   kind="stage", absent=True)))
            filled.append(x)
            prev = x[0]
        out = filled
    info = {"name": M.thread_name(int(t)), "spans": [{"joined": a, "left": (b if b < 10 ** 9 else None)} for a, b in spans], "hidden_before_joining": hidden,
            "volume": round(float(T.cols["volume"][p]), 1) if p >= 0 else 0.0}
    return [x[3] for x in out], info


def inbox(sim, i: int) -> dict:
    """Everyone i has texted with, their group chats (past ones too) and their app conversations, newest first."""
    i = int(i)
    M = sim.systems.get("messaging")
    soc = _soc(sim)
    partners: dict[int, dict] = {}

    def bump(j, d, unanswered=False):
        j = int(j)
        if j < 0 or j == i:
            return
        c = partners.setdefault(j, {"id": j, "last_day": -1, "n": 0, "unanswered": False})
        c["last_day"] = max(c["last_day"], int(d))
        c["n"] += 1
        c["unanswered"] |= unanswered
    if M is not None and M.acts.n:
        A = M.acts
        m = (A["thread"] < 0) & ((A["sender"] == i) | (A["to"] == i))
        for r in np.flatnonzero(m).tolist():
            o = int(A.cols["to"][r]) if A.cols["sender"][r] == i else int(A.cols["sender"][r])
            bump(o, A.cols["day"][r])
    I = sim.book.inv
    if I.n:
        m = (I["thread"] < 0) & (I["channel"] == CHANNEL_ID["text"]) & ((I["inviter"] == i) | (I["person"] == i)) & (I["inviter"] >= 0)
        for r in np.flatnonzero(m).tolist():
            o = int(I.cols["person"][r]) if I.cols["inviter"][r] == i else int(I.cols["inviter"][r])
            bump(o, I.cols["sent_day"][r])
    if soc is not None and soc.ex.t.n:
        X = soc.ex.t
        m = (X["channel"] == CHANNEL_ID["text"]) & (X["thread"] < 0) & ((X["speaker"] == i) | (X["to"] == i))
        for r in np.flatnonzero(m).tolist():
            o = int(X.cols["to"][r]) if X.cols["speaker"][r] == i else int(X.cols["speaker"][r])
            bump(o, X.cols["day"][r])
    dms = sorted(partners.values(), key=lambda c: -c["last_day"])[:80]
    for c in dms:
        c["name"] = _name(sim, c["id"])
        c["date"] = str(sim.cal.date(c["last_day"])) if c["last_day"] >= 0 else None
        lines = dm_lines(sim, i, c["id"], since=c["last_day"] - 14)
        last = next((x for x in reversed(lines) if not x.get("absent")), lines[-1] if lines else None)
        if last is not None:
            c["preview"] = D.fallback(sim, last) if not last.get("absent") else (last["slots"].get("text") or "")
            c["preview_me"] = last.get("speaker") == i
            c["waiting"] = lines[-1].get("absent", False) and lines[-1].get("act") == "no_reply" and lines[-1].get("to") == i
    groups = []
    if M is not None:
        from ..engine.systems.messaging import KINDS
        Mm, T = M.members, M.threads
        rows = np.flatnonzero(Mm["person"] == i)
        seen = set()
        for r in rows.tolist():
            t = int(Mm.cols["thread"][r])
            if t in seen:
                continue
            seen.add(t)
            p = T.pos([t])[0]
            if p < 0:
                continue
            arows = np.flatnonzero(M.acts["thread"] == t)
            last = int(M.acts["day"][arows].max()) if len(arows) else int(Mm.cols["joined"][r])
            groups.append({"id": t, "kind": KINDS[int(T.cols["kind"][p])], "name": M.thread_name(t), "n": int(T.cols["n"][p]),
                           "member": bool(Mm.cols["left"][r] < 0), "joined": int(Mm.cols["joined"][r]),
                           "left": int(Mm.cols["left"][r]) if Mm.cols["left"][r] >= 0 else None,
                           "muted": bool(Mm.cols["muted"][r]), "last_day": last, "volume": round(float(T.cols["volume"][p]), 1)})
        groups.sort(key=lambda g: (not g["member"], -g["last_day"]))
    apps = app_list(sim, i)
    return {"person": i, "name": _name(sim, i), "today": int(sim.w.day), "kept_since": kept_since(sim), "dms": dms,
            "groups": groups, "apps": apps, "style": D.style_words(D.style(sim, i)), "style_note": D.STYLE_NOTE,
            "note": GAP_NOTE}


# -------------------------------------------------------------------------------------------------------- dating apps
APP_WORDS = {"matched": "matched, nobody has said anything yet", "opened": "waiting for an answer", "chatting": "talking",
             "asked": "asked out, waiting for an answer", "date_set": "a date is set", "declined": "said no to a date",
             "unanswered": "the first message was never answered", "ghosted": "one of them stopped answering",
             "faded": "it fizzled out", "no_opener": "matched, but nobody ever wrote", "closed": "ended (one of them is seeing someone or left)"}


def app_list(sim, i: int) -> list[dict]:
    soc = _soc(sim)
    if soc is None or not soc.app.t.n:
        return []
    T = soc.app.t
    out = []
    for r in soc.app.of(int(i)).tolist()[::-1][:60]:
        o = int(T.cols["b"][r]) if T.cols["a"][r] == i else int(T.cols["a"][r])
        st = S.APP_STAGES[int(T.cols["stage"][r])]
        out.append({"id": int(T.ids[r]), "with": _who(sim, o), "stage": st, "words": APP_WORDS.get(st, st),
                    "matched": int(T.cols["matched"][r]), "last_day": int(T.cols["last_day"][r]),
                    "date_day": int(T.cols["date_day"][r]) if T.cols["date_day"][r] >= 0 else None,
                    "ended_by_them": bool(T.cols["ended_by"][r] == o), "ended_by_me": bool(T.cols["ended_by"][r] == i)})
    return out


def profile(sim, i: int) -> dict:
    """What someone shows on a dating app: self-presented facts, not their hidden state."""
    P = sim.w.P
    i = int(i)
    lab = lambda v: str(P.labels(v, [P[v][i]])[0]) if v in P else None   # noqa: E731
    hobbies = [h for h, v in (("hiking", "hikes"), ("games", "gaming"), ("sports", "sports"), ("music", "music_maker")) if v in P and P[v][i]]
    wants = float(P["wants_relationship"][i]) if "wants_relationship" in P else 2.0
    school = lab("school")
    out = {"id": i, "first_name": _name(sim, i).split()[0], "age": int(P["age"][i]), "school": school if school not in (None, "none") else None,
           "studying": lab("study_area") if bool(P["enrolled"][i]) else None, "returned_missionary": lab("mission_status") == "returned",
           "hobbies": hobbies, "app": "Mutual" if bool(P["app_mutual"][i]) else "a general dating app",
           "looking_for": "something serious" if wants >= 3 else "seeing where it goes" if wants >= 1.5 else "not sure yet",
           "uses_apps": bool(P["app_user"][i]), "photo": None,
           "note": "What they put on their profile: self-presented. It doesn't show how drawn they are to anyone, what they "
                   "believe or what they intend — the conversation and what they do show that."}
    return out


def app_lines(sim, tid: int) -> tuple[list[dict], dict]:
    soc = _soc(sim)
    T = soc.app.t
    p = T.pos([int(tid)])[0]
    if p < 0:
        raise KeyError("no such app conversation (it may be older than the record keeps)")
    a, b = int(T.cols["a"][p]), int(T.cols["b"][p])
    X = soc.ex.t
    rows = np.flatnonzero((X["channel"] == CHANNEL_ID["app"]) & (X["thread"] == int(tid)))
    out = []
    P = sim.w.P
    for r in rows.tolist():
        act = S.ACTS[int(X.cols["act"][r])]
        sp, to = int(X.cols["speaker"][r]), int(X.cols["to"][r])
        d, b_ = int(X.cols["day"][r]), int(X.cols["block"][r])
        sl = {}
        absent = act in ("no_reply", "fade")
        if act == "opener":
            sl["school"] = "BYU" if P["school"][to] == 1 else "UVU" if P["school"][to] == 2 else None
        elif act == "app_reply":
            sl["late"] = bool(X.cols["said"][r])
        elif act == "no_reply":
            sl["text"] = f"{_name(sim, sp).split()[0]} never answered." if X.cols["topic"][r] == S.TOPIC["match"] else "No reply."
        elif act == "fade":
            sl["text"] = "Neither of them wrote again."
        out.append(D.line(sp, to, act, "app", d, b_, sl, ex=int(X.ids[r]), absent=absent,
                          licensed={"ask_date": act == "ask_date", "accept": act == "date_yes", "decline": act == "date_no"}))
        if act == "app_chat":
            out.append({**D.line(to, sp, "app_chat", "app", d, b_, {}, ex=int(X.ids[r])), "sub": 2})
    st = S.APP_STAGES[int(T.cols["stage"][p])]
    info = {"id": int(tid), "a": _who(sim, a), "b": _who(sim, b), "matched": int(T.cols["matched"][p]),
            "matched_date": str(sim.cal.date(int(T.cols["matched"][p]))), "stage": st, "words": APP_WORDS.get(st, st),
            "date_day": int(T.cols["date_day"][p]) if T.cols["date_day"][p] >= 0 else None,
            "date_date": str(sim.cal.date(int(T.cols["date_day"][p]))) if T.cols["date_day"][p] >= 0 else None,
            "match_event": int(T.cols["match_event"][p]), "ended_by": _who(sim, int(T.cols["ended_by"][p])) if T.cols["ended_by"][p] >= 0 else None,
            "mutual_app": bool(T.cols["mutual"][p])}
    # what happened next: the date (if it took place) and after
    if info["date_day"] is not None:
        info["date"] = _date_outcome(sim, a, b, info["date_day"])
    return out, info


def _date_outcome(sim, a, b, day) -> dict:
    log = sim.log
    n = log.n
    lo = int(np.searchsorted(log["day"][:n], day))
    rows = lo + np.flatnonzero(((log["a"][lo:n] == a) & (log["b"][lo:n] == b)) | ((log["a"][lo:n] == b) & (log["b"][lo:n] == a)))
    names = sim.reg.event_names
    evs = [{"id": int(e), "type": names[int(log["type"][e])], "day": int(log["day"][e])} for e in rows[:12].tolist()]
    happened = any(e["type"] in ("first_date", "date") for e in evs)
    state = "happened" if happened else ("planned" if day >= sim.w.day else "didn't happen (moved or called off)")
    return {"state": state, "events": evs}


# ---------------------------------------------------------------------------------------------------------- in person
def _place_words(sim, ctx: int, place: int) -> str:
    c = CTX[ctx] if 0 <= ctx < len(CTX) else ""
    if c == "occasion" and place >= 0:
        try:
            d = sim.book.describe(int(place))
            name = d.get("name") or d.get("kind_label")
            return f"at {name} ({sim.systems['occasions'].place_label(int(place))})"
        except Exception:  # noqa: BLE001
            return "at a get-together"
    return PLACE_CTX.get(c, "together")


def conversations(sim, people: list[int] | None = None, occ: int | None = None, since_ex: int = -1, days: int = 7,
                  limit: int = 60) -> dict:
    """In-person conversations the engine kept, for some people or one occasion: newest last; `since_ex` returns only
    newer exchanges (a live view appends them)."""
    soc = _soc(sim)
    if soc is None:
        return {"conversations": [], "now": None}
    X = soc.ex.t
    day = sim.w.day
    m = (X["channel"] == CHANNEL_ID["in_person"]) & (X["day"] >= day - days)
    if occ is not None:
        m &= X["place"] == int(occ)
    elif people:
        pp = np.asarray(people, np.int64)
        m &= np.isin(X["speaker"], pp) | np.isin(X["to"], pp)
    if since_ex >= 0:
        m &= X["id"] > since_ex
    rows = np.flatnonzero(m)[-limit * 3:]
    groups: dict[tuple, dict] = {}
    for r in rows.tolist():
        a, b = int(X.cols["speaker"][r]), int(X.cols["to"][r])
        d, blk = int(X.cols["day"][r]), int(X.cols["block"][r])
        ctx, place = int(X.cols["ctx"][r]), int(X.cols["place"][r])
        key = (d, blk, place if CTX[ctx] == "occasion" else int(S.ukey(a, b)))
        g = groups.get(key)
        if g is None:
            g = groups[key] = {"key": f"{d}.{blk}.{key[2]}", "day": d, "date": str(sim.cal.date(d)), "block": blk,
                               "block_name": clock.BLOCK_NAMES[blk] if 0 <= blk < len(clock.BLOCK_NAMES) else "",
                               "where": _place_words(sim, ctx, place), "people": [], "lines": [], "exchanges": [],
                               "occasion": place if 0 <= ctx < len(CTX) and CTX[ctx] == "occasion" else None}
        for w in (a, b):
            if w >= 0 and all(p["id"] != w for p in g["people"]):
                g["people"].append(_who(sim, w))
        g["exchanges"].append(int(X.ids[r]))
        g["lines"].extend(_in_person(sim, r))
    convs = sorted(groups.values(), key=lambda g: (g["day"], g["block"], g["exchanges"][0]))[-limit:]
    # the parts of today already resolved (blocks run when the clock reaches them; nothing later is shown)
    done = [b for b, hh in enumerate(clock.BLOCK_HOUR) if hh <= sim.w.hour]
    now_block = done[-1] if done else None
    last_ex = int(X.ids[rows[-1]]) if len(rows) else since_ex
    return {"conversations": convs, "day": day, "hour": int(sim.w.hour), "block": now_block, "last_ex": last_ex,
            "note": "Conversations the simulation resolved in each part of the day (it doesn't run minute by minute). "
                    "Important ones are always kept; ordinary talk is a fixed sample."}


def _in_person(sim, r: int) -> list[dict]:
    soc = _soc(sim)
    X = soc.ex.t
    act = S.ACTS[int(X.cols["act"][r])]
    topic = S.TOPICS[int(X.cols["topic"][r])]
    sp, to = int(X.cols["speaker"][r]), int(X.cols["to"][r])
    d, blk = int(X.cols["day"][r]), int(X.cols["block"][r])
    exid = int(X.ids[r])
    row = {"id": exid, "speaker": sp, "to": to, "act_name": act, "topic_name": topic, "day": d, "block": blk,
           "tone": float(X.cols["tone"][r]) if not np.isnan(X.cols["tone"][r]) else 0.0}
    if X.cols["ref_kind"][r] >= 0 and CAUSE_KINDS[int(X.cols["ref_kind"][r])] == "occasion" and X.cols["ref"][r] >= 0:
        sl = D.occ_slots(sim, int(X.cols["ref"][r]))
        if sl:
            sl["when"] = D._when(sim, sl, d)
        row["occ"] = sl
    if act in ("small_talk", "warm_moment", "tension", "introduce", "avoid"):
        return D.in_person_lines(sim, row)
    sl = {"topic": topic}
    if act == "clarify":
        sl["reason"] = S.WHY[int(X.cols["said"][r])] if 0 <= X.cols["said"][r] < len(S.WHY) else "none"
        # the other side's honest answer when asked ("I figured you weren't interested") reveals their misreading
        sl["revealed_belief"] = S.INTENTS[int(X.cols["intent"][r])] == "inform" and bool(X.cols["said"][r])
        if sl["revealed_belief"]:
            sl["reason"] = "none"
    if act == "reassure":
        sl["held"] = bool(X.cols["said"][r])
    if act == "ask_clarify" and topic == "left_out":
        o = D.occ_slots(sim, _concern_ref(sim, int(X.cols["concern"][r])))
        sl.update({"what": o.get("what"), "host": o.get("host")})
    return [D.line(sp, to, act, "in_person", d, blk, sl, ex=exid)]


def _held_at(sim, owner, about, day) -> bool:
    soc = _soc(sim)
    B = soc.beliefs.t
    m = (B["owner"] == owner) & (B["about"] == about) & (B["prop"] == S.PROP["not_interested"]) & (B["formed"] <= day)
    return bool(m.any())


def _concern_ref(sim, cid: int) -> int:
    soc = _soc(sim)
    if cid < 0:
        return -1
    p = soc.concerns.t.pos([cid])[0]
    return int(soc.concerns.t.cols["ref"][p]) if p >= 0 else -1


# ------------------------------------------------------------------------------------------------------ perspectives
INTENT_WORDS = {"connect": "to connect", "inform": "to let them know", "decline_gently": "to say no without making it a thing",
                "keep_door_open": "to say no but keep the door open", "check_on": "to check on them",
                "get_support": "to be honest about how they're doing", "give_support": "to support them",
                "understand": "to understand what happened", "repair": "to set things right", "protect_self": "to protect themselves",
                "spare_feelings": "to let them down gently", "flirt": "to ask them out", "test_interest": "to see if they're interested",
                "keep_private": "to keep it to themselves", "coordinate": "to coordinate"}
READ_WORDS = {"busy": "they're just busy", "not_interested": "they aren't interested", "excluded": "they were left out on purpose",
              "ignored": "they're being ignored", "support": "they're being supported", "warm": "it's friendly",
              "ambiguous": "they can't tell what it means", "obligation": "they should be there for them",
              "rejection": "a rejection", "unknown": "they aren't sure what it means", "relief": "relief: it wasn't what they feared",
              "interest": "interest", "polite": "politeness", "none": ""}
PROP_WORDS = {"not_interested": "{o} isn't interested in coming", "excluded_me": "{o} left them out on purpose",
              "thinks_im_not_interested": "{o} thinks they aren't interested", "busy": "{o} is just busy",
              "ignoring_me": "{o} is ignoring them", "cares": "{o} cares about them", "interested": "{o} is interested"}
WITHHELD_WORDS = {1: "work", 2: "class", 3: "another commitment", 4: "being sick", 5: "not being able to get there",
                  6: "being tired", 7: "studying for a test", 8: "plans with their partner", 9: "a hurt between them",
                  10: "just not feeling it"}


def _beliefs_then(sim, owner, about, day) -> list[dict]:
    soc = _soc(sim)
    B = soc.beliefs.t
    m = (B["owner"] == owner) & (B["about"] == about) & (B["formed"] <= day) & (B["active"] | (B["revised_day"] > day))
    o = _name(sim, about).split()[0]
    return [{"id": int(B.ids[r]), "prop": S.PROPS[int(B.cols["prop"][r])],
             "words": PROP_WORDS[S.PROPS[int(B.cols["prop"][r])]].format(o=o), "confidence": round(float(B.cols["first_conf"][r]), 2),
             "formed": int(B.cols["formed"][r])} for r in np.flatnonzero(m).tolist()]


def perspective(sim, ex_id: int) -> dict:
    """One exchange from both sides: what the speaker meant and why, what they kept back, how the other read it, what
    each came to believe, and what happened after (concern, later exchanges, the tie then and now)."""
    soc = _soc(sim)
    X = soc.ex.t
    p = X.pos([int(ex_id)])[0]
    if p < 0:
        raise KeyError("no such exchange (it may be older than the record keeps)")
    g = lambda c: X.cols[c][p]   # noqa: E731
    sp, to, d = int(g("speaker")), int(g("to")), int(g("day"))
    act = S.ACTS[int(g("act"))]
    spk, rcp = _who(sim, sp), _who(sim, to) if to >= 0 else None
    did = int(g("decision"))
    dec = sim.decisions.get(did) if did >= 0 else {}
    withheld = int(g("withheld"))
    speaker = {"who": spk, "act": act, "act_words": D.label_act(act),
               "intent": INTENT_WORDS.get(S.INTENTS[int(g("intent"))], "") or None,
               "communicated": _communicated(sim, p),
               "kept_back": (WITHHELD_WORDS.get(withheld, "how they really felt") if withheld else None) if act not in ("disclose",) else None,
               "decision": _dec_view(dec), "beliefs": _beliefs_then(sim, sp, to, d) if to >= 0 else []}
    reads = []
    for r in soc.reads.of(int(ex_id)).tolist():
        R = soc.reads.t
        rd = S.READS[int(R.cols["read"][r])]
        reads.append({"who": _who(sim, int(R.cols["reader"][r])), "read": rd, "words": READ_WORDS.get(rd, rd),
                      "confidence": round(float(R.cols["conf"][r]), 2),
                      "expected": READ_WORDS.get(S.READS[int(R.cols["expected"][r])], "") or None,
                      "belief": int(R.cols["belief"][r]) if R.cols["belief"][r] >= 0 else None})
    other = {"who": rcp, "reads": reads, "beliefs": _beliefs_then(sim, to, sp, d) if to >= 0 else []}
    # aftermath
    after = {"concern": None, "next": [], "tie_then": None, "tie_now": None, "revised": []}
    cid = int(g("concern"))
    if cid >= 0:
        after["concern"] = concern_view(sim, cid)
    if to >= 0:
        rows = np.flatnonzero((X["pair"] == int(S.ukey(sp, to))) & (X["id"] > int(ex_id)))[:6]
        after["next"] = [{"id": int(X.ids[r]), "day": int(X.cols["day"][r]), "date": str(sim.cal.date(int(X.cols["day"][r]))),
                          "who": _who(sim, int(X.cols["speaker"][r])), "act": S.ACTS[int(X.cols["act"][r])],
                          "words": D.label_act(S.ACTS[int(X.cols["act"][r])]),
                          "channel": ["in person", "text", "group chat", "", "", "app", ""][int(X.cols["channel"][r])]} for r in rows.tolist()]
        if not np.isnan(g("clos")):
            after["tie_then"] = {"closeness": round(float(g("clos")), 2), "hurt": round(float(g("hurt")), 2)}
        E = sim.w.E
        e = E.find(E.make_keys(np.array([sp]), np.array([to])))[0]
        if e >= 0:
            after["tie_now"] = {"closeness": round(float(E["closeness"][e]), 2), "hurt": round(float(E["hurt"][e]), 2)}
        B = soc.beliefs.t
        rv = np.flatnonzero(B["revised_by"] == int(ex_id))
        after["revised"] = [{"who": _who(sim, int(B.cols["owner"][r])),
                             "words": PROP_WORDS[S.PROPS[int(B.cols["prop"][r])]].format(o=_name(sim, int(B.cols["about"][r])).split()[0]),
                             "held_since": int(B.cols["formed"][r])} for r in rv.tolist()]
    unknown = []
    if int(g("channel")) == CHANNEL_ID["text"]:
        unknown.append("When exactly a text was read isn't recorded (only the day it was answered).")
    if act in ("small_talk", "warm_moment"):
        unknown.append("Ordinary talk records how it went and what it was about, not the actual words.")
    return {"id": int(ex_id), "day": d, "date": str(sim.cal.date(d)), "act": act, "act_words": D.label_act(act),
            "channel": ["in person", "text", "group chat", "announcement", "family", "app", "confided"][int(g("channel"))],
            "topic": S.TOPICS[int(g("topic"))], "ambiguity": None if np.isnan(g("ambig")) else round(float(g("ambig")), 2),
            "speaker": speaker, "other": other, "after": after, "unknown": unknown,
            "event": int(g("event")) if g("event") >= 0 else None,
            "note": "From the simulation's records: the decision behind the act, the readings and beliefs it formed. "
                    "Nothing here is written by a model."}


def _communicated(sim, p) -> str:
    soc = _soc(sim)
    X = soc.ex.t
    act = S.ACTS[int(X.cols["act"][p])]
    said = int(X.cols["said"][p])
    if act in ("decline_explained", "promise"):
        r = S.WHY[said] if 0 <= said < len(S.WHY) else "none"
        return f"that they can't come because of {WITHHELD_WORDS.get(said, 'something else')}" + (", and next time for sure" if act == "promise" else "") \
            if r not in ("none", "not_feeling_it") else "that they can't come"
    if act == "decline_brief":
        return "only that they can't come"
    if act == "clarify":
        return f"why they kept saying no ({WITHHELD_WORDS.get(said, 'it was not about them')})" if said else "that it wasn't about them"
    if act in S.ABSENT:
        return "nothing (an absence, not a message)"
    return D.label_act(act)


def _dec_view(dec: dict) -> dict | None:
    if not dec:
        return None
    fs = [f for f in dec.get("factors", []) if f["factor"] != "base"][:5]
    return {"id": dec["id"], "label": dec["label"], "outcome": dec["outcome"], "chance": dec.get("prob"),
            "factors": [{"label": f["label"], "words": f.get("words"), "value": f["value"], "constraint": f["constraint"]} for f in fs]}


def concern_view(sim, cid: int) -> dict | None:
    soc = _soc(sim)
    C = soc.concerns.t
    p = C.pos([int(cid)])[0]
    if p < 0:
        return None
    own, oth = int(C.cols["owner"][p]), int(C.cols["other"][p])
    kind = S.CONCERNS[int(C.cols["kind"][p])]
    st = S.STATUS[int(C.cols["status"][p])]
    o = _name(sim, oth).split()[0]
    words = {"unanswered": f"a text to {o} that went unanswered", "left_out": f"being left out by {o}",
             "promise": f"a promise to {o} to come next time", "misread": f"a misunderstanding with {o}",
             "app_waiting": f"waiting on {o}"}[kind]
    return {"id": int(cid), "owner": _who(sim, own), "other": _who(sim, oth), "kind": kind, "words": words, "status": st,
            "stance": S.STANCES[int(C.cols["stance"][p])], "opened": int(C.cols["opened"][p]),
            "deadline": int(C.cols["deadline"][p]), "importance": round(float(C.cols["importance"][p]), 2),
            "resolved_day": int(C.cols["resolved_day"][p]) if C.cols["resolved_day"][p] >= 0 else None,
            "resolved_by": int(C.cols["resolved_by"][p]) if C.cols["resolved_by"][p] >= 0 else None,
            "evidence": int(C.cols["evidence"][p]) if C.cols["evidence"][p] >= 0 else None}
