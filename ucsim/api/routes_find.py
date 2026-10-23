"""Finding people (analysis/find.py): narrow everyone by filters, by how they stand with one person and by name, so
Make it happen can pick someone without guessing names; and the workplaces near someone, for a job offer."""
from __future__ import annotations

from fastapi import APIRouter, Body

from .routes_story import _call

router = APIRouter()


@router.post("/api/people/find")
def people_find(body: dict = Body(...)):
    """{"u", "around": person, "relation": friends | strangers | roommates | likes | tense | ..., "filter": [conditions],
    "q": name, "sort": closeness | nearest | my_interest | their_interest | tension | name | <person variable>, "desc",
    "offset", "limit"}"""
    from ..analysis import find as F
    return _call(body.get("u") or "base", F.find, around=body.get("around"), relation=body.get("relation") or "any",
                 filter=body.get("filter"), q=body.get("q") or "", sort=body.get("sort"), desc=body.get("desc"),
                 offset=int(body.get("offset") or 0), limit=int(body.get("limit") or 25))


@router.get("/api/people/{i}/workplaces")
def people_workplaces(i: int, u: str = "base", k: int = 20):
    from ..analysis import find as F
    return _call(u, F.workplaces, i, k=max(1, min(k, 60)))
