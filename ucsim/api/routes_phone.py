"""Phones, dating apps and listening in (analysis/phone.py), plus model wording for them (llm/talk/dialogue.py).

Every view returns its planned lines with words: the accepted model wording when it has been made for exactly this
content, otherwise the structured wording. Reading never changes a world or draws a number. `POST /api/phone/realize`
queues model wording for one view; the plan is built under the world lock, the model runs without it."""
from __future__ import annotations

from fastapi import APIRouter, Body, HTTPException, Request

from .routes_story import _call
from .routes_trace import _server

router = APIRouter()


def _ids(people: str) -> list[int]:
    return [int(x) for x in people.split(",") if x.strip().lstrip("-").isdigit()][:200]


def _plan(sim, view: dict) -> tuple[list[dict], dict]:
    """The planned lines of one view and its info: {kind: dm, a, b} | {kind: group, viewer, t} | {kind: app, id} |
    {kind: listen, people | occ, days}."""
    from ..analysis import phone as PH
    k = view.get("kind")
    since, until = view.get("since"), view.get("until")
    if k == "dm":
        a, b = int(view["a"]), int(view["b"])
        lo = since if since is not None else max(0, sim.w.day - 60)
        return PH.dm_lines(sim, a, b, since=lo, until=until), {"since": lo}
    if k == "group":
        return PH.group_lines(sim, int(view["viewer"]), int(view["t"]), since=since, until=until)
    if k == "app":
        return PH.app_lines(sim, int(view["id"]))
    if k == "listen":
        c = PH.conversations(sim, people=view.get("people") or None, occ=view.get("occ"), days=int(view.get("days", 2)))
        gs = [g for g in c["conversations"] if not view.get("conv") or g["key"] == view["conv"]]
        return [s for g in gs for s in g["lines"]], {}
    raise ValueError("say which view: {kind: dm, a, b} | {kind: group, viewer, t} | {kind: app, id} | {kind: listen, ...}")


def _key(sim, specs) -> tuple:
    from ..analysis import dialogue as D
    from ..llm.talk import dialogue as TD
    return (TD.lineage(sim), D.content_key(specs), D.SCHEMA)


def _render(sim, specs: list[dict]) -> tuple[list[dict], dict]:
    """Planned lines → shown lines (words from the cache or the structured wording) and the wording state."""
    from ..analysis import dialogue as D
    from ..analysis.phone import _name
    from ..engine import clock
    from ..llm.talk import dialogue as TD
    key = _key(sim, specs)
    texts, source = TD.apply(sim, specs, key)
    out = []
    for s, t in zip(specs, texts):
        blk = s["block"]
        out.append({"id": D.lid(s), "speaker": s["speaker"], "speaker_name": _name(sim, s["speaker"]) if s["speaker"] is not None else None,
                    "to": s["to"], "act": s["act"], "act_words": D.label_act(s["act"]), "channel": s["channel"],
                    "day": s["day"], "date": str(sim.cal.date(s["day"])), "block": blk,
                    "time": clock.hhmm(clock.PART_HOUR[blk] * 60) if 0 <= blk < len(clock.PART_HOUR) else None,
                    "text": t, "absent": bool(s.get("absent")), "kind": s.get("kind", "line"), "ex": s.get("ex"),
                    "msg": s.get("msg"), "inv": s.get("inv"), "ref": s.get("ref"), "note": s.get("note") or None})
    st = TD.status(key)
    return out, {"source": source, "state": st.get("state"), "job": st.get("job"), "removed": st.get("removed", 0),
                 "key": key[1], "realizable": any(s.get("kind") != "stage" and not s.get("absent") for s in specs)}


def _view(u: str, view: dict):
    WS, jresp = _server()
    with WS.lock:
        sim = WS.sim(u)
        try:
            specs, info = _plan(sim, view)
            lines, wording = _render(sim, specs)
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
        except KeyError as e:
            raise HTTPException(404, str(e).strip("'\"")) from e
        return jresp({**info, "lines": lines, "wording": wording, "day": int(sim.w.day)})


@router.get("/api/phone/inbox/{i}")
def inbox(i: int, u: str = "base"):
    """Someone's phone: the people they text, their group chats (past ones too) and their dating-app conversations."""
    from ..analysis import phone as PH
    return _call(u, PH.inbox, i)


@router.get("/api/phone/dm")
def dm(a: int, b: int, u: str = "base", since: int | None = None, until: int | None = None):
    """Two people's text thread: the same messages from either phone."""
    return _view(u, {"kind": "dm", "a": a, "b": b, "since": since, "until": until})


@router.get("/api/phone/group")
def group(viewer: int, t: int, u: str = "base", since: int | None = None, until: int | None = None):
    """A group chat as the viewer saw it: only while they were a member."""
    return _view(u, {"kind": "group", "viewer": viewer, "t": t, "since": since, "until": until})


@router.get("/api/phone/app/{tid}")
def app_thread(tid: int, u: str = "base"):
    """A dating-app conversation from match to date, silence or a no."""
    return _view(u, {"kind": "app", "id": tid})


@router.get("/api/phone/profile/{i}")
def profile(i: int, u: str = "base"):
    """What someone shows on their dating profile (self-presented)."""
    from ..analysis import phone as PH
    return _call(u, PH.profile, i)


@router.get("/api/listen")
def listen(u: str = "base", people: str = "", occ: int | None = None, since_ex: int = -1, days: int = 2):
    """In-person conversations of some people (or at one get-together): `since_ex` returns only newer ones."""
    from ..analysis import phone as PH
    WS, jresp = _server()
    with WS.lock:
        sim = WS.sim(u)
        c = PH.conversations(sim, people=_ids(people) or None, occ=occ, since_ex=since_ex, days=max(0, min(days, 30)))
        for g in c["conversations"]:
            g["lines"], g["wording"] = _render(sim, g["lines"])
        return jresp(c)


@router.get("/api/phone/perspective/{ex}")
def perspective(ex: int, u: str = "base"):
    """One exchange from both sides and what came of it (from the records; nothing written by a model)."""
    from ..analysis import phone as PH
    return _call(u, PH.perspective, ex)


@router.get("/api/phone/concern/{cid}")
def concern(cid: int, u: str = "base"):
    from ..analysis import phone as PH
    WS, jresp = _server()
    with WS.lock:
        v = PH.concern_view(WS.sim(u), cid)
    if v is None:
        raise HTTPException(404, "no such concern")
    return jresp(v)


@router.post("/api/phone/realize")
def realize(request: Request, body: dict = Body(...)):
    """Word one view with the owner's model: body = a view ({kind: dm, a, b} ...) plus u?, priority? (0 = on screen
    now). The plan is fixed now; the wording is checked line by line and shared by every view of the same content."""
    from ..analysis import dialogue as D
    from ..analysis.phone import _name
    from ..llm.talk import dialogue as TD
    from .routes_talk import _guard
    _guard(request)
    WS, jresp = _server()
    if WS.base is None:
        raise HTTPException(409, "build a world first")
    u = "alt" if body.get("u") == "alt" else "base"
    with WS.lock:
        sim = WS.sim(u)
        try:
            specs, _ = _plan(sim, body)
        except (ValueError, KeyError) as e:
            raise HTTPException(400, str(e).strip("'\"")) from e
        key = _key(sim, specs)
        people = sorted({p for s in specs for p in (s["speaker"], s["to"]) if p is not None and p >= 0})
        names = {p: _name(sim, p).split()[0] for p in people}
        allowed = set(names.values()) | {str(s["slots"].get("host")) for s in specs if s["slots"].get("host")}
        context = {"people": [{"name": names[p], "texting_style": D.style_words(D.style(sim, p))} for p in people[:12]],
                   "setting": "Provo–Orem, Utah; college students and young adults", "view": body.get("kind")}
        for s in specs:
            s["_draft"] = D.fallback(sim, s)
    plan = (specs, names, allowed, context)
    label = f"Wording a {'text thread' if body.get('kind') == 'dm' else body.get('kind', 'view')}"
    st = TD.request(key, label, lambda: plan, priority=int(body.get("priority", 1)))
    return jresp({**st, "key": key[1]})


@router.get("/api/phone/realize/{job}")
def realize_status(job: str):
    from ..llm.talk import jobs
    j = jobs.JOBS.get(job)
    if j is None:
        raise HTTPException(404, "no such job")
    return {"state": j.state, "error": j.error, "steps": j.steps[-4:], "result": getattr(j, "result", None)}


@router.delete("/api/phone/realize/{job}")
def realize_cancel(job: str, request: Request):
    from ..llm.talk import dialogue as TD
    from .routes_talk import _guard
    _guard(request)
    return {"cancelled": TD.cancel(job_id=job)}


@router.get("/api/stories")
def stories(u: str = "base", people: str = "", limit: int = 12):
    """Developing stories: situations the records show are still open (observational; not representative)."""
    from ..analysis import stories as ST
    return _call(u, ST.developing, _ids(people) or None, limit=max(1, min(limit, 40)))
