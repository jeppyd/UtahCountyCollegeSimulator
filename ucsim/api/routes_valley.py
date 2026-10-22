"""The valley endpoints (analysis/valley.py): the home screen's feed of moments, lives worth following and the
followed people right now. Read-only: nothing here changes either world."""
from __future__ import annotations

from fastapi import APIRouter

from .routes_story import _call

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
