"""Speed and logs: per-day timings (overall, per system, per world), this computer's speed for the world-setup estimate,
the recent log lines, and a debug bundle to attach to a bug report (ucsim/telemetry.py). Read-only; none of these
take the workspace lock, so they answer while time runs."""
from __future__ import annotations

import time

from fastapi import APIRouter
from fastapi.responses import Response

from ..telemetry import LOGBOOK, PERIODIC_WORDS, SYSTEM_WORDS, TELEMETRY, debug_bundle

router = APIRouter()


def _server():
    import sys
    main = sys.modules.get("__main__")
    if getattr(main, "WS", None) is not None and getattr(main, "_include_routers", None) is not None:
        return main.WS, main.jresp
    from .server import WS, jresp
    return WS, jresp


@router.get("/api/perf")
def perf(since_day: int | None = None, limit: int = 400):
    """The speed summary and the latest per-day records (`since_day`: only days after it)."""
    WS, jresp = _server()
    return jresp({"summary": TELEMETRY.summary(), "days": TELEMETRY.records(since_day, max(1, min(limit, TELEMETRY.KEEP))),
                  "system_words": SYSTEM_WORDS, "periodic_words": PERIODIC_WORDS,
                  "has_alt": WS.alt_now is not None, "running": WS.job.get("state") == "running"})


@router.get("/api/perf/estimate")
def perf_estimate(scale: float = 0.15):
    """Seconds per simulated day for a world of this scale on this computer: from worlds measured here before (the
    nearest scale, scaled by people), else None (the page falls back to its rule of thumb)."""
    _, jresp = _server()
    hist = TELEMETRY.speed_history()
    rows = [h for h in hist.values() if h.get("early_s")]
    if not rows:
        return jresp({"measured": False})
    near = min(rows, key=lambda h: abs(h["scale"] - scale) / max(scale, 1e-3))
    k = scale / near["scale"]                          # time per day grows roughly with the number of people
    out = {"measured": True, "from_scale": near["scale"], "updated": near.get("updated"),
           "early_s": round(near["early_s"] * k, 3)}
    if near.get("later_s"):
        out["later_s"] = round(near["later_s"] * k, 3)
    if near.get("build_s"):
        out["build_s"] = round(near["build_s"] * k ** 0.9, 1)
    return jresp(out)


@router.get("/api/logs")
def logs(since: int = -1, level: str = "info", limit: int = 1000):
    """Log lines newer than id `since`, at `level` or above (debug, info, warning, error)."""
    _, jresp = _server()
    return jresp({"lines": LOGBOOK.read(since, level, max(1, min(limit, 5000))), "next": LOGBOOK.next_id})


@router.get("/api/debug-bundle")
def bundle():
    """A zip of versions, the world's settings, speed records and logs, to attach to a bug report. No people and no
    survey data are in it."""
    WS, _ = _server()
    b = WS.base
    world = {}
    if b is not None:
        world = {"scale": b.w.scale, "seed": b.w.seed, "day": int(b.w.day), "date": str(b.w.date), "people": int(b.w.P.n),
                 "has_what_if": WS.alt_now is not None,
                 "what_if_changes": list(WS.alt_now.interventions) if WS.alt_now is not None else [],
                 "detail_days": getattr(b, "detail_days", None), "timing_total_s": {k: round(v, 2) for k, v in b.timing.items()}}
    data = debug_bundle(world, {"job": dict(WS.job), "last_job": WS.last_job})
    name = time.strftime("ucsim-debug-%Y%m%d-%H%M%S.zip")
    return Response(data, media_type="application/zip", headers={"Content-Disposition": f'attachment; filename="{name}"'})
