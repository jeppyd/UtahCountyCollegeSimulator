"""Messaging endpoints (engine/systems/messaging.py): a person's chats and recent messages, one chat's members and
messages, and who heard about an event — from whom and when. Read-only."""
from __future__ import annotations

import numpy as np
from fastapi import APIRouter, HTTPException

from .routes_trace import _server

router = APIRouter()

ACT_WORDS = {"invite": "posted an invitation", "checkin": "checked in", "reply": "replied", "silence": "didn't reply",
             "news": "shared news", "plan_change": "called off a plan"}
CHANNEL_WORDS = {0: "in person", 1: "by text", 2: "in a group chat", 3: "by announcement", 4: "family", 5: "on an app"}


def _msg(sim):
    m = sim.systems.get("messaging")
    if m is None:
        raise HTTPException(404, "messaging isn't running in this world")
    return m


def _name(sim, i):
    from ..analysis.person import synthetic_name
    i = int(i)
    return synthetic_name(sim.w.P, i) if 0 <= i < sim.w.P.n else None


def _acts(sim, M, rows) -> list[dict]:
    from ..engine.systems.messaging import ACTS
    A = M.acts
    book = sim.book
    out = []
    for r in rows:
        kind = ACTS[int(A.cols["kind"][r])]
        ref = int(A.cols["ref"][r])
        row = {"id": int(A.ids[r]), "day": int(A.cols["day"][r]), "date": str(sim.cal.date(int(A.cols["day"][r]))),
               "kind": kind, "words": ACT_WORDS[kind], "thread": int(A.cols["thread"][r]),
               "sender": int(A.cols["sender"][r]), "sender_name": _name(sim, A.cols["sender"][r]),
               "to": int(A.cols["to"][r]) if A.cols["to"][r] >= 0 else None,
               "to_name": _name(sim, A.cols["to"][r]) if A.cols["to"][r] >= 0 else None,
               "replied_day": int(A.cols["replied_day"][r]) if A.cols["replied_day"][r] >= 0 else None,
               "event": int(A.cols["event"][r]) if A.cols["event"][r] >= 0 else None}
        if kind in ("invite", "plan_change") and ref >= 0:
            d = book.describe(ref)
            row["occasion"] = {"id": ref, "label": d.get("name") or d.get("kind_label"), "day": d.get("day")} if d else None
        elif kind == "news" and ref >= 0:
            from ..analysis.explain import event_record
            row["news"] = event_record(sim, ref)
        if kind == "silence" and row["event"] is not None:
            row["read_as"] = sim.reg.event_names[int(sim.log["type"][row["event"]])]
        out.append(row)
    return out


@router.get("/api/messaging/person/{i}")
def person_messages(i: int, u: str = "base", days: int = 60, limit: int = 200):
    """A person's chats (kind, name, members, muted) and the messages they sent or got in their chats lately."""
    from ..engine.systems.messaging import KINDS
    WS, jresp = _server()
    with WS.lock:
        sim = WS.sim(u)
        if not (0 <= i < sim.w.P.n):
            raise HTTPException(404, "no such person")
        M = _msg(sim)
        Mm, T = M.members, M.threads
        mine = np.flatnonzero((Mm["person"] == i) & (Mm["left"] < 0))
        threads = []
        for r in mine:
            t = int(Mm.cols["thread"][r])
            p = T.pos([t])[0]
            threads.append({"id": t, "kind": KINDS[int(T.cols["kind"][p])], "name": M.thread_name(t), "n": int(T.cols["n"][p]),
                            "volume": round(float(T.cols["volume"][p]), 1), "muted": bool(Mm.cols["muted"][r]),
                            "joined": int(Mm.cols["joined"][r])})
        A = M.acts
        tids = [t["id"] for t in threads]
        since = sim.w.day - days
        m = (A["day"] >= since) & ((A["sender"] == i) | (A["to"] == i) | (np.isin(A["thread"], tids) & (A["thread"] >= 0)))
        rows = np.flatnonzero(m)[::-1][:limit]
        return jresp({"person": i, "name": _name(sim, i), "threads": sorted(threads, key=lambda t: KINDS.index(t["kind"])),
                      "acts": _acts(sim, M, rows), "today": int(sim.w.day)})


@router.get("/api/messaging/thread/{t}")
def thread(t: int, u: str = "base", limit: int = 200):
    """One chat: its kind and name, who is in it (and who left or muted it), and its recorded messages."""
    from ..engine.systems.messaging import KINDS
    WS, jresp = _server()
    with WS.lock:
        sim = WS.sim(u)
        M = _msg(sim)
        T, Mm = M.threads, M.members
        p = T.pos([t])[0]
        if p < 0:
            raise HTTPException(404, "no such chat")
        rows = np.flatnonzero(Mm["thread"] == t)
        members = [{"id": int(Mm.cols["person"][r]), "name": _name(sim, Mm.cols["person"][r]), "joined": int(Mm.cols["joined"][r]),
                    "left": int(Mm.cols["left"][r]) if Mm.cols["left"][r] >= 0 else None, "muted": bool(Mm.cols["muted"][r])}
                   for r in rows[:400]]
        arows = np.flatnonzero(M.acts["thread"] == t)[::-1][:limit]
        return jresp({"id": t, "kind": KINDS[int(T.cols["kind"][p])], "name": M.thread_name(t), "active": bool(T.cols["active"][p]),
                      "created_day": int(T.cols["created_day"][p]), "creator": int(T.cols["creator"][p]) if T.cols["creator"][p] >= 0 else None,
                      "volume": round(float(T.cols["volume"][p]), 1), "members": members, "acts": _acts(sim, M, arows)})


@router.get("/api/messaging/news/{event}")
def news(event: int, u: str = "base"):
    """Who knows about an event, who told them, when and how — the spreading tree (source −1 = it happened to them)."""
    from ..analysis.explain import event_record
    WS, jresp = _server()
    with WS.lock:
        sim = WS.sim(u)
        M = _msg(sim)
        if not (0 <= event < sim.log.n):
            raise HTTPException(404, "no such event")
        k = M.know.about(event)
        order = np.argsort(k["day"], kind="stable")
        rows = [{"person": int(k["person"][j]), "name": _name(sim, k["person"][j]), "source": int(k["source"][j]),
                 "source_name": _name(sim, k["source"][j]) if k["source"][j] >= 0 else None, "day": int(k["day"][j]),
                 "channel": CHANNEL_WORDS.get(int(k["channel"][j]), "?")} for j in order]
        return jresp({"event": event_record(sim, event), "knowers": rows, "tracked": bool(rows)})
