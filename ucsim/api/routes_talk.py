"""Talking to the world (ucsim/llm/talk/): Ask the world and Interviews as background jobs, polled like the What-if
compiler's. Both run the owner's own model logins, so only pages served from this computer may start them. Neither
changes a world."""
from __future__ import annotations

from fastapi import APIRouter, Body, HTTPException, Request

from .routes_trace import _server

router = APIRouter()


def _guard(request: Request):
    import sys
    main = sys.modules.get("__main__")
    lo = getattr(main, "_local_only", None) if getattr(main, "WS", None) is not None else None
    if lo is None:
        from .server import _local_only as lo
    lo(request)


@router.get("/api/talk/status")
def talk_status():
    """Which backends are available and which one each feature uses (with the recommended choice)."""
    from ..llm.talk import llm
    _, jresp = _server()
    return jresp(llm.status())


@router.post("/api/talk/settings")
def talk_settings(request: Request, body: dict = Body(...)):
    """{ask_backend?, interview_backend?: auto|claude|codex|openai, sensitive?: bool}"""
    _guard(request)
    from ..llm.talk import llm
    _, jresp = _server()
    return jresp(llm.save(body))


def _job(jid: str):
    from ..llm.talk.jobs import JOBS
    job = JOBS.get(jid)
    if job is None:
        raise HTTPException(404, "no such job (the server may have restarted)")
    return job


@router.post("/api/talk/ask")
def talk_ask(request: Request, body: dict = Body(...)):
    """Start answering a question about the world: {question, mentions?: [{kind, id, label?}], u?: base|alt}."""
    _guard(request)
    from ..llm.talk import ask
    WS, jresp = _server()
    if WS.base is None:
        raise HTTPException(409, "build a world first")
    q = str(body.get("question", "")).strip()
    if not q:
        raise HTTPException(400, "ask a question")
    u = "alt" if body.get("u") == "alt" else "base"
    WS.sim(u)
    job = ask.start(WS, q[:2000], list(body.get("mentions") or [])[:12], u=u)
    return jresp({"job": job.id})


@router.get("/api/talk/ask/{jid}")
def talk_ask_poll(jid: str):
    _, jresp = _server()
    return jresp(_job(jid).view())


@router.post("/api/talk/ask/{jid}/cancel")
def talk_ask_cancel(request: Request, jid: str):
    _guard(request)
    _, jresp = _server()
    job = _job(jid)
    job.cancel.set()
    return jresp(job.view())


@router.post("/api/talk/interview/{i}")
def talk_interview(request: Request, i: int, body: dict = Body(...)):
    """Ask person i a question: {question, history?: [{q, a}], u?: base|alt}. Poll /api/talk/ask/{job}."""
    _guard(request)
    from ..llm.talk import interview
    WS, jresp = _server()
    if WS.base is None:
        raise HTTPException(409, "build a world first")
    q = str(body.get("question", "")).strip()
    if not q:
        raise HTTPException(400, "ask a question")
    u = "alt" if body.get("u") == "alt" else "base"
    WS.sim(u)
    hist = [{"q": str(h.get("q", ""))[:600], "a": str(h.get("a", ""))[:1200]} for h in list(body.get("history") or [])[-6:] if isinstance(h, dict)]
    job = interview.start(WS, int(i), q[:1000], hist, u=u)
    return jresp({"job": job.id})


@router.get("/api/talk/differs/{i}")
def talk_differs(i: int, u: str = "base"):
    """Where person i's view differs from what's true (computed, not generated)."""
    from ..llm.talk import facts as F
    WS, jresp = _server()
    with WS.lock:
        sim = WS.sim(u)
        if not (0 <= i < sim.w.P.n):
            raise HTTPException(404, "no such person")
        return jresp(F.view_vs_truth(sim, i))
