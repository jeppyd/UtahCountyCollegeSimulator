"""The valley endpoints (analysis/valley.py): the home screen's feed of moments, lives worth following and the
followed people right now. Read-only: nothing here changes either world."""
from __future__ import annotations

from fastapi import APIRouter, Body, HTTPException, Request

from .routes_story import _call
from .routes_trace import _server

router = APIRouter()


def _ids(people: str) -> list[int]:
    return [int(x) for x in people.split(",") if x.strip().lstrip("-").isdigit()][:200]


@router.get("/api/valley/feed")
def feed(u: str = "base", people: str = "", since: int | None = None, limit: int = 60):
    """What happened lately to the people followed (people=1,2,3) or, with no people, in the whole valley."""
    from ..analysis import valley as V
    return _call(u, V.feed, _ids(people), since=since, limit=max(1, min(limit, 300)))


@router.get("/api/valley/cast")
def cast(u: str = "base", shuffle: int = 0):
    """Lives worth following: one person per kind of life, each with a one-line hook."""
    from ..analysis import valley as V
    return _call(u, V.cast, shuffle=max(0, shuffle))


@router.get("/api/valley/now")
def now(people: str, u: str = "base"):
    """The followed people right now: what they're doing, how they feel, what's next today, their latest moment."""
    from ..analysis import valley as V
    return _call(u, V.now, _ids(people))


@router.get("/api/scene/occasion/{oid}")
def scene_occasion(oid: int, u: str = "base"):
    """One get-together as a scene to watch: invitations as texts, arrivals, who is drawn to whom, introductions and what
    happened (analysis/script.py; the words are illustrative, what happens is recorded)."""
    from ..analysis import script as SC
    return _call(u, SC.occasion_script, oid)


@router.get("/api/scene/pair")
def scene_pair(a: int, b: int, u: str = "base"):
    """Two people's history as a text thread: check-ins, invitations, asking out, dates, silences, breakups."""
    from ..analysis import script as SC
    return _call(u, SC.pair_script, a, b)


@router.post("/api/scene/narrate")
def scene_narrate(request: Request, body: dict = Body(...)):
    """Tell a scene as a story with the owner's model login: {kind: occasion, id} or {kind: pair, a, b}, pov?, u?.
    Poll /api/talk/ask/{job}. The story is checked against the scene's recorded beats."""
    from ..llm.talk import narrate
    from .routes_talk import _guard
    _guard(request)
    WS, jresp = _server()
    if WS.base is None:
        raise HTTPException(409, "build a world first")
    kind = body.get("kind")
    if kind == "occasion":
        ref = {"kind": "occasion", "id": int(body["id"])}
    elif kind == "pair":
        ref = {"kind": "pair", "a": int(body["a"]), "b": int(body["b"])}
    else:
        raise HTTPException(400, "say which scene: {kind: occasion, id} or {kind: pair, a, b}")
    u = "alt" if body.get("u") == "alt" else "base"
    WS.sim(u)
    pov = body.get("pov")
    job = narrate.start(WS, ref, None if pov in (None, "") else int(pov), u=u)
    return jresp({"job": job.id})
