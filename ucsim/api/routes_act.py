"""Social actions from the workbench: preview one (who is free, how long the trip, how late, why not) and do it in the
What-if world (engine/systems/social_actions.py). The Original is never changed."""
from __future__ import annotations

from fastapi import APIRouter, Body, HTTPException

router = APIRouter()


def _atom(body: dict) -> dict:
    it = dict(body.get("action") if isinstance(body.get("action"), dict) else body)
    it.pop("u", None)
    it.pop("world", None)
    it["target_type"] = "social"
    if not it.get("action"):
        raise HTTPException(400, "say which action: invite, series, reschedule, introduce, ride, reach_out or job_offer")
    return it


@router.post("/api/act/check")
def act_check(body: dict = Body(...)):
    """Preview an action without doing it: for each person involved, whether they're free, the trip, how late they'd
    be and why not; problems that would stop it (acting as someone: only people they know, when they're free, what
    they can afford). Checked against the What-if world when there is one (that's where it would happen)."""
    from ..engine.systems.social_actions import check
    from .routes_trace import _server
    WS, jresp = _server()   # under `python -m` the serving module is __main__
    if WS.base is None:
        raise HTTPException(400, "no world")
    it = _atom(body)
    u = body.get("u") or ("base" if body.get("world") == "original" or WS.alt is None else "alt")
    sim = WS.sim(u)
    with WS.lock:
        out = check(sim, it)
        out["world"] = "What-if" if sim is WS.alt else "Original"
        out["day"] = sim.w.day
    return jresp(out)


@router.post("/api/act")
def act(body: dict = Body(...)):
    """Do an action now. By default in the What-if world (making the What-if from the Original first if there isn't
    one); with "world": "original", in the Original itself: the change becomes part of your world's own history, with
    no copy to compare against (a What-if made earlier doesn't get it)."""
    from ..engine import runner
    from ..engine.systems.social_actions import check
    from .routes_trace import _server
    WS, jresp = _server()   # under `python -m` the serving module is __main__
    if WS.base is None:
        raise HTTPException(400, "no world")
    if WS.job.get("state") == "building":
        raise HTTPException(409, "a new world is being built; wait for it to finish")
    original = body.get("world") == "original"
    it = _atom(body)
    if original:
        with WS.lock:
            sim = WS.base
            pre = check(sim, it)
            if not pre["ok"]:
                return jresp({"ok": False, "problems": pre["problems"], "people": pre["people"], "made_whatif": False})
            man = sim.systems["environment"].manager
            it["start_day"] = sim.w.day
            it.setdefault("name", f"Social action: {it['action'].replace('_', ' ')}")
            man.add(it)
            sim.interventions.append(it)
            k = len(man.items) - 1
            res = man.apply_now(k)
            WS.compare_cache = None
            return jresp({**res, "item": k, "made_whatif": False, "world": "Original", "day": sim.w.day})
    with WS.lock:
        made = WS.alt is None
        target = WS.base if made else WS.take_alt()   # mid-run the live What-if may be on the second core
        pre = check(target, it)
        if not pre["ok"]:
            return jresp({"ok": False, "problems": pre["problems"], "people": pre["people"], "made_whatif": False})
        if made:
            WS.alt = runner.fork(WS.base, [])
            WS.fork_id += 1
            WS._index = None
            WS.divergence = [runner.divergence(WS.base, WS.alt)]
        alt = WS.alt
        man = alt.systems["environment"].manager
        it["start_day"] = alt.w.day
        it.setdefault("name", f"Social action: {it['action'].replace('_', ' ')}")
        man.add(it)
        alt.interventions.append(it)
        k = len(man.items) - 1
        res = man.apply_now(k)
        WS.compare_cache = None
        return jresp({**res, "item": k, "made_whatif": made, "day": alt.w.day, "fork_day": getattr(alt, "meta_fork_day", None)})
