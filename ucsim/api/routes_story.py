"""Story endpoints (analysis/story.py): a person's life as chapters of sentences, the share of the push behind any
event or choice, and the ripple of what one moment led to. Read-only: nothing here changes either world."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from .routes_trace import _server

router = APIRouter()


def _call(u: str, fn, *args, **kw):
    WS, jresp = _server()
    with WS.lock:
        sim = WS.sim(u)
        try:
            return jresp(fn(sim, *args, **kw))
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
        except KeyError as e:
            raise HTTPException(404, str(e).strip("'\"")) from e


@router.get("/api/story/person/{i}")
def person_story(i: int, u: str = "base", since: int | None = None, until: int | None = None, min_salience: float = 0.3):
    """One person's life as chapters: a sentence per notable event with its top reasons (share of the push)."""
    from ..analysis import story as S
    return _call(u, S.story, i, since=since, until=until, min_salience=min_salience)


@router.get("/api/story/why")
def why(ref: str, u: str = "base"):
    """The share of the push behind one event, choice or feeling: ref = event:<id> | decision:<id> | var:<field>@<id>."""
    from ..analysis import story as S
    return _call(u, S.why, ref)


@router.get("/api/story/ripple")
def ripple(ref: str, u: str = "base", depth: int = 6):
    """What one moment led to, as a tree of sentences."""
    from ..analysis import story as S
    return _call(u, S.ripple, ref, depth=depth)
