"""FastAPI analysis server for the Utah County College Social Simulator.

Run:  python -m ucsim.api.server --scale 0.3 --seed 1 --port 8000
The React workstation (web/) talks to /api/*.  All heavy reads are columnar and binary.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import struct
import threading
import time
import traceback
from pathlib import Path

import numpy as np
import orjson
import polars as pl
from fastapi import Body, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from ..analysis import butterfly as B
from ..analysis import explain as X
from ..analysis import fields as F
from ..analysis.inner import inner_life
from ..analysis.person import headline, profile, synthetic_name
from ..analysis.query import describe_filter, evaluate_filter
from ..engine import runner
from ..engine.interventions import load_presets
from ..engine.state import CTX, Tie
from ..registry import get_registry
from ucsim.population.structure import ward_name

ROOT = Path(__file__).resolve().parents[2]
WEB_DIST = ROOT / "web" / "dist"
GEO_DIR = ROOT / "web" / "public" / "geo"


def jresp(obj) -> Response:
    return Response(orjson.dumps(obj, option=orjson.OPT_SERIALIZE_NUMPY | orjson.OPT_NON_STR_KEYS, default=str),
                    media_type="application/json")


def pack_columns(cols: dict[str, tuple[np.ndarray, dict]]) -> bytes:
    """Binary columnar payload: [u32 header_len][header json][pad][column blocks (4-byte aligned)]."""
    blocks, meta, off = [], [], 0
    for name, (arr, extra) in cols.items():
        b = arr.tobytes()
        meta.append({"id": name, "dtype": {np.dtype("float32"): "f32", np.dtype("uint8"): "u8",
                                           np.dtype("int32"): "i32", np.dtype("uint16"): "u16"}[arr.dtype],
                     "offset": off, "length": int(arr.size), **extra})
        pad = (-len(b)) % 4
        blocks.append(b + b"\0" * pad)
        off += len(b) + pad
    header = json.dumps({"columns": meta}).encode()
    header += b" " * ((-len(header) - 4) % 4)
    return struct.pack("<I", len(header)) + header + b"".join(blocks)


def column_array(P, var: str) -> tuple[np.ndarray, dict]:
    spec = P.specs[var]
    x = P[var]
    if spec.dtype == "cat":
        return x.astype(np.uint8), {"categories": spec.categories}
    if spec.dtype == "bool":
        return x.astype(np.uint8), {"bool": True}
    if spec.dtype == "i4" and var.endswith("_id"):
        return x.astype(np.int32), {}
    return x.astype(np.float32), {}


class FairLock:
    """A re-entrant lock handed out in arrival order.

    A run re-takes the workspace lock for every simulated day.  With a plain RLock the run thread wins that race
    almost every time, so page requests (the What-if comparisons, the map, people) waited for the whole run.  Here
    every request queued during a day goes before the next day starts."""

    def __init__(self):
        self._cv = threading.Condition(threading.Lock())
        self._owner = None
        self._depth = 0
        self._next = 0      # next ticket to hand out
        self._serving = 0   # ticket whose turn it is

    def acquire(self):
        me = threading.get_ident()
        with self._cv:
            if self._owner == me:
                self._depth += 1
                return True
            ticket = self._next
            self._next += 1
            while self._serving != ticket or self._owner is not None:
                self._cv.wait()
            self._owner, self._depth = me, 1
            return True

    def release(self):
        with self._cv:
            if self._owner != threading.get_ident():
                raise RuntimeError("release of a lock this thread does not hold")
            self._depth -= 1
            if self._depth == 0:
                self._owner = None
                self._serving += 1
                self._cv.notify_all()

    def __enter__(self):
        return self.acquire()

    def __exit__(self, *exc):
        self.release()


class Workspace:
    def __init__(self):
        self.lock = FairLock()
        self.job_lock = threading.Lock()   # makes "is anything running? then start" atomic
        self.base = None
        self.alt = None
        self.divergence: list[dict] = []
        self.job = {"state": "idle"}
        self.last_job: dict | None = None   # how the previous run or build ended (shown in the HUD)
        self.mc = None
        self.sweep_result = None
        self.unc = None
        self.compare_cache = None
        self.world_id = 0
        self.fork_id = 0      # bumped whenever the What-if world is replaced (cache tags must never match across experiments)
        self.plans: dict[str, dict] = {}   # compiled What-if plans by id (natural-language What-ifs)
        self._index = None
        self.registry = get_registry()

    def sim(self, u: str):
        s = self.alt if u == "alt" else self.base
        if s is None:
            raise HTTPException(404, f"universe '{u}' not available")
        return s

    def busy(self) -> bool:
        return self.job.get("state") in ("running", "building")

    def start_job(self, job: dict, target, *args) -> bool:
        """Claim the job slot and start `target` in the background; False if something is already running.
        Claiming happens before the thread starts, so two quick clicks can never start two runs at once."""
        with self.job_lock:
            if self.busy():
                return False
            now = time.time()
            self.job = {**job, "progress": 0, "started": now, "updated": now}
        threading.Thread(target=target, args=args, daemon=True).start()
        return True

    def finish_job(self, kind: str, reason: str, **extra):
        j = self.job
        self.last_job = {"kind": kind, "reason": reason, "progress": j.get("progress", 0), "total": j.get("total", 0),
                         "ended": time.time(), "seconds": round(time.time() - j.get("started", time.time()), 1), **extra}
        self.job = {"state": "error", "error": extra.get("error", "")} if reason == "error" else {"state": "idle"}

    def build(self, scale: float, seed: int, warmup: int = 0):
        """Synthesize a new world (replacing the current one and any intervention universe), then warm it up."""
        self.job.update(phase="synthesizing")
        try:
            sim = runner.new_simulation(scale=scale, seed=seed)
            for k in range(warmup):
                if self.job.get("cancel"):
                    break
                self.job.update(phase="warming up", progress=k, updated=time.time())
                sim.step_day()
            with self.lock:
                self.base, self.alt, self.divergence, self.compare_cache = sim, None, [], None
                self.world_id += 1
                self._index = None
            self.finish_job("build", "done")
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            self.finish_job("build", "error", error=repr(e))

    def step(self, days: int = 0, hours: int = 0, pace: float = 0.0):
        """Advance both universes. `pace` = minimum seconds per simulated day (the slow "watch it" speed)."""
        world = "Original"
        try:
            if hours and not days:
                with self.lock:
                    for s in (self.base, self.alt):
                        if s is not None:
                            s.advance_hours(hours)
            for k in range(days):
                if self.job.get("cancel"):
                    break
                t_day = time.time()
                with self.lock:
                    world = "Original"
                    self.base.step_day()
                    alt = self.alt
                    if alt is not None:
                        world = "What-if"
                        alt.step_day()
                        while alt.w.day < self.base.w.day:   # catch up if an earlier error left the What-if behind
                            alt.step_day()
                        if self.base.w.day % 3 == 0 or days <= 14:
                            self.divergence.append(runner.divergence(self.base, alt))
                    self.compare_cache = None
                self.job.update(progress=k + 1, updated=time.time(), day_seconds=round(time.time() - t_day, 2))
                while pace and time.time() - t_day < pace and not self.job.get("cancel"):
                    time.sleep(0.05)
            self.finish_job("run", "paused" if self.job.get("cancel") and self.job.get("progress", 0) < days else "done")
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            self.finish_job("run", "error", error=f"the {world} world hit an error on day {self.base.w.day}: {e!r}")


WS = Workspace()
app = FastAPI(title="Utah County College Social Simulator", version="0.1")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


# ----------------------------------------------------------------------------- meta
@app.get("/api/registry")
def registry():
    return jresp(WS.registry.as_json())


@app.get("/api/status")
async def status():
    """The clock, the job and headline counts.  Runs on the event loop (never queues behind other requests or the
    workspace lock) and reads without locking, so the clock and the pause button keep working during a long run."""
    b, alt = WS.base, WS.alt
    out = {"job": dict(WS.job), "last_job": WS.last_job, "has_alt": alt is not None, "has_world": b is not None,
           "world_id": WS.world_id, "scale_agents_per_unit": 60000}
    if b is None:
        return jresp(out)
    try:
        w, log = b.w, b.log
        n_ev = int(log.n)
        cnt = np.bincount(log.cols["type"][:n_ev], minlength=len(WS.registry.event_names))
        ev = WS.registry.event_ids
        out["totals"] = {k: int(cnt[ev[k]]) for k in ("new_friend", "close_friend", "first_date", "relationship_started", "engaged",
                                                        "wedding", "breakup_received", "birth", "mission_departure", "graduation", "moved")}
        out["season"] = b.cal.season(w.day)
        divergence = WS.divergence
        out.update({"day": w.day, "hour": w.hour, "date": str(w.date), "weekday": w.date.strftime("%A"),
                    "scale": w.scale, "seed": w.seed, "agents": int(w.P.n), "present": int(w.P["present"].sum()),
                    "edges": int(w.E.n), "events": n_ev, "env": {k: v for k, v in dict(w.env).items() if not isinstance(v, np.ndarray)},
                    "alt_interventions": list(alt.interventions) if alt is not None else [],
                    "fork_day": getattr(alt, "meta_fork_day", None) if alt is not None else None,
                    "divergence": divergence[-1] if alt is not None and divergence else None,
                    "last_event_id": n_ev - 1,
                    "timing": dict(b.timing)})
    except Exception as e:  # noqa: BLE001  (a read raced a day in progress; the next poll will be complete)
        out["partial"] = repr(e)
    return jresp(out)


@app.post("/api/world")
def new_world(body: dict = Body(default={})):
    """Build a new world in the background: {"scale": 0.02–1, "seed": int, "warmup": days}."""
    scale = float(body.get("scale", 0.3))
    if not 0.01 <= scale <= 1.0:
        raise HTTPException(400, "scale must be between 0.01 and 1")
    seed = int(body.get("seed", 1))
    warmup = max(0, min(int(body.get("warmup", 0)), 365))
    job = {"state": "building", "phase": "queued", "total": max(warmup, 1), "scale": scale, "seed": seed}
    if not WS.start_job(job, WS.build, scale, seed, warmup):
        raise HTTPException(409, "the simulator is busy; pause it first")
    return {"ok": True}


@app.post("/api/step")
def step(body: dict = Body(default={})):
    if WS.base is None:
        raise HTTPException(400, "no world")
    days = int(body.get("days", 0))
    if "until_day" in body:
        days = int(body["until_day"]) - WS.base.w.day
    days = max(0, min(days, 3650))
    hours = max(0, min(int(body.get("hours", 0)), 24))
    pace = max(0.0, min(float(body.get("pace", 0.0)), 10.0))
    if not WS.start_job({"state": "running", "total": days or 1, "pace": pace}, WS.step, days, hours, pace):
        raise HTTPException(409, "time is already running; pause it first")
    return {"ok": True, "days": days, "hours": hours, "pace": pace}


@app.get("/api/validation")
def validation():
    """The latest validation report, four-year stability check and stock-flow accounting
    (scripts/validate.py, scripts/stability.py, scripts/accounting.py)."""
    cfg = Path(__file__).resolve().parents[1] / "config"
    out = {}
    for key, name in (("validation", "validation.json"), ("stability", "stability.json"), ("accounting", "accounting.json")):
        f = cfg / name
        out[key] = json.loads(f.read_text(encoding="utf-8")) if f.exists() else None
    return jresp(out)


@app.get("/api/calendar")
def calendar():
    """The academic year around today as labelled segments (terms and breaks), for the time ribbon."""
    if WS.base is None:
        raise HTTPException(404, "no world")
    sim = WS.base
    cal, day = sim.cal, sim.w.day
    today = cal.date(day)
    y0 = today.year if today.month >= 8 else today.year - 1
    start = dt.date(y0, 8, 1)
    end = dt.date(y0 + 1, 7, 31)
    segs = []
    for t in cal.real.terms_between(start, end):     # BYU's real terms (engine/calendar_real.py)
        if t.school != "BYU":
            continue
        segs.append({"label": f"{t.name} {'semester' if t.name in ('Fall', 'Winter') else 'term'}", "kind": "term",
                     "start": max((t.start - cal.start).days, (start - cal.start).days),
                     "end": min((t.finals_end - cal.start).days, (end - cal.start).days)})
    segs.sort(key=lambda s: s["start"])
    full, cur = [], (start - cal.start).days
    for s in segs:
        if s["start"] > cur:
            gap = cal.date(cur)
            label = "Christmas break" if gap.month == 12 else "Break" if s["start"] - cur < 14 else "Summer break"
            full.append({"label": label, "kind": "break", "start": cur, "end": s["start"] - 1})
        full.append(s)
        cur = s["end"] + 1
    last = (end - cal.start).days
    if cur <= last:
        full.append({"label": "Late-summer break", "kind": "break", "start": cur, "end": last})
    fork_day = getattr(WS.alt, "meta_fork_day", None) if WS.alt is not None else None
    return jresp({"year": f"{y0}-{str(y0 + 1)[2:]}", "start": (start - cal.start).days, "end": last, "today": day,
                  "fork_day": fork_day, "segments": full, "start_date": str(cal.start)})


@app.get("/api/positions/day")
def positions_day(u: str = "base"):
    """Where everyone was in each block of the last full simulated day (morning, afternoon, evening, late evening) and
    at night (map day replay)."""
    from ..engine import clock
    sim = WS.sim(u)
    with WS.lock:
        fr = getattr(sim.systems["activity"], "day_frames", {}) or {}
        if len(fr) < clock.N_BLOCKS + 2:          # the blocks, the night and the day number
            raise HTTPException(404, "run at least one full day first")
        P = sim.w.P
        n = P.n
        cols = {}
        for b in range(clock.N_BLOCKS + 1):
            lon, lat, act = fr[b]
            pad = n - len(lon)
            cols[f"lon{b}"] = (np.r_[lon, np.full(pad, np.nan, np.float32)].astype(np.float32), {})
            cols[f"lat{b}"] = (np.r_[lat, np.full(pad, np.nan, np.float32)].astype(np.float32), {})
            cols[f"act{b}"] = (np.r_[act, np.zeros(pad, np.uint8)].astype(np.uint8), {"categories": P.specs["activity_now"].categories})
        cols["day"] = (np.array([fr["day"]], np.int32), {"date": str(sim.cal.date(fr["day"]))})
        return Response(pack_columns(cols), media_type="application/octet-stream")


@app.get("/api/history/frames")
def history_frames(var: str = "rel_status", u: str = "base", max_frames: int = 40):
    """Homes and one tracked variable at each history snapshot (map 'months go by' playback)."""
    sim = WS.sim(u)
    with WS.lock:
        H, P = sim.systems["history"], sim.w.P
        if not H.tracked(var):
            raise HTTPException(400, f"{var} is not tracked over time")
        snaps = H.snaps
        if len(snaps) > max_frames:
            idx = np.unique(np.linspace(0, len(snaps) - 1, max_frames).round().astype(int))
            snaps = [snaps[i] for i in idx]
        cols, days = {}, []
        spec = P.specs[var]
        for k, s in enumerate(snaps):
            lon, lat = H.homes(s)
            x, _ = H.values(var, s["day"])
            cols[f"lon{k}"] = (lon, {})
            cols[f"lat{k}"] = (lat, {})
            if spec.dtype in ("cat", "bool"):
                cols[f"v{k}"] = (x.astype(np.uint8), {"categories": spec.categories} if spec.dtype == "cat" else {"bool": True})
            else:
                cols[f"v{k}"] = (x.astype(np.float32), {})
            days.append(s["day"])
        cols["days"] = (np.array(days, np.int32), {"dates": [str(sim.cal.date(d)) for d in days]})
        return Response(pack_columns(cols), media_type="application/octet-stream")


@app.post("/api/cancel")
async def cancel():
    """Pause: the current run stops after the day in progress.  On the event loop, so it is never stuck in a queue."""
    WS.job["cancel"] = True
    return {"ok": True, "state": WS.job.get("state")}


@app.get("/api/interventions/presets")
def presets():
    return jresp(load_presets())


@app.post("/api/fork")
def fork(body: dict = Body(...)):
    if WS.base is None:
        raise HTTPException(400, "no world")
    if WS.job.get("state") == "building":
        raise HTTPException(409, "a new world is being built; wait for it to finish")
    with WS.lock:
        WS.alt = runner.fork(WS.base, body.get("interventions", []))
        WS.fork_id += 1
        WS._index = None
        WS.divergence = [runner.divergence(WS.base, WS.alt)]
        WS.compare_cache = None
    return {"ok": True, "fork_day": WS.base.w.day}


@app.delete("/api/fork")
def unfork():
    with WS.lock:
        WS.alt = None
        WS.fork_id += 1
        WS._index = None
        WS.divergence = []
        WS.compare_cache = None
    return {"ok": True}


# ----------------------------------------------------------------------------- columns & positions
@app.get("/api/columns")
def columns(vars: str, u: str = "base"):
    sim = WS.sim(u)
    with WS.lock:
        P = sim.w.P
        cols = {}
        for v in vars.split(","):
            v = v.strip()
            if v in P.specs and P.specs[v].dtype != "str":
                cols[v] = column_array(P, v)
            elif v == "_id":
                cols[v] = (np.arange(P.n, dtype=np.int32), {})
        return Response(pack_columns(cols), media_type="application/octet-stream")


@app.get("/api/positions")
def positions(u: str = "base", mode: str = "now"):
    sim = WS.sim(u)
    with WS.lock:
        P = sim.w.P
        lon = P["loc_lon"] if mode == "now" else P["home_lon"]
        lat = P["loc_lat"] if mode == "now" else P["home_lat"]
        pres = P["present"]
        lon = np.where(pres, lon, np.nan).astype(np.float32)
        lat = np.where(pres, lat, np.nan).astype(np.float32)
        act = P["activity_now"].astype(np.uint8)
        return Response(pack_columns({"lon": (lon, {}), "lat": (lat, {}),
                                      "activity_now": (act, {"categories": P.specs["activity_now"].categories})}),
                        media_type="application/octet-stream")


# ----------------------------------------------------------------------------- people
@app.get("/api/person/{i}")
def person(i: int, u: str = "base"):
    sim = WS.sim(u)
    with WS.lock:
        if i < 0 or i >= sim.w.P.n:
            raise HTTPException(404, "no such person")
        prof = profile(sim, i)
        if WS.alt is not None and u == "base" and i < WS.alt.w.P.n:
            prof["counterfactual"] = counterfactual(i)
        return jresp(prof)


def counterfactual(i: int) -> dict:
    """How this person's life differs in the intervention universe."""
    b, a = WS.base, WS.alt
    Pb, Pa = b.w.P, a.w.P
    diffs = []
    for k, spec in Pb.specs.items():
        if spec.dtype == "str" or k in ("loc_lon", "loc_lat", "activity_now", "birth_day") or k.endswith("_day") or (k.endswith("_id") and k != "partner_id"):
            continue
        xb, xa = Pb[k][i], Pa[k][i]
        if spec.dtype in ("f4", "f8"):
            if np.isfinite(xb) and np.isfinite(xa) and abs(float(xa) - float(xb)) > 0.02 * (abs(float(xb)) + 0.5):
                diffs.append({"id": k, "label": spec.label, "base": float(xb), "alt": float(xa)})
        elif xb != xa:
            fmt = (lambda v: spec.categories[int(v)]) if spec.dtype == "cat" else (lambda v: v.item() if hasattr(v, "item") else v)
            diffs.append({"id": k, "label": spec.label, "base": fmt(xb), "alt": fmt(xa)})
    fork_day = getattr(a, "meta_fork_day", 0)

    def evs(sim):
        log = sim.log
        m = np.where((log["a"] == i) & (log["day"] >= fork_day))[0]
        return [X.event_record(sim, int(e)) for e in m if sim.reg.events[sim.reg.event_names[log["type"][e]]].salience >= 0.45][-80:]
    return {"fork_day": fork_day, "diffs": diffs, "base_events": evs(b), "alt_events": evs(a)}


@app.get("/api/person/{i}/inner")
def person_inner(i: int, u: str = "base"):
    """The inner life: motives and drives, beliefs vs reality, memories, intentions, coping, lessons, routine, footprint."""
    sim = WS.sim(u)
    with WS.lock:
        if i < 0 or i >= sim.w.P.n:
            raise HTTPException(404, "no such person")
        return jresp(inner_life(sim, i))


@app.get("/api/person/{i}/network")
def person_network(i: int, u: str = "base", max_nodes: int = 60):
    sim = WS.sim(u)
    with WS.lock:
        net = X.ego_network(sim, i, max_nodes=max_nodes)
        P = sim.w.P
        for nd in net["nodes"]:
            j = nd["id"]
            nd.update({"name": synthetic_name(P, j), "sex": P.labels("sex", P["sex"][j:j + 1])[0],
                       "age": float(P["age"][j]), "activity": P.labels("activity", P["activity"][j:j + 1])[0],
                       "role": P.labels("role", P["role"][j:j + 1])[0], "rel": P.labels("rel_status", P["rel_status"][j:j + 1])[0],
                       "mood": float(P["mood"][j]), "loneliness": float(P["loneliness"][j])})
        return jresp(net)


@app.get("/api/people/featured")
def featured(u: str = "base", days: int = 30, k: int = 6):
    """Eventful lives lately: people with the most salient recent events, spread across life domains."""
    sim = WS.sim(u)
    with WS.lock:
        return jresp(F.featured_people(sim, days, k))


@app.get("/api/people/brief")
def people_brief(ids: str, u: str = "base"):
    """Small cards for followed people: name, one-line headline, latest salient events."""
    sim = WS.sim(u)
    with WS.lock:
        P, log, reg = sim.w.P, sim.log, sim.reg
        sal = np.array([e.salience for e in reg.events.values()])
        out = []
        for t in ids.split(","):
            if not t.strip().isdigit() or int(t) >= P.n:
                continue
            i = int(t)
            mine = np.where(((log["a"] == i) | (log["b"] == i)) & (sal[log["type"]] >= 0.5))[0][-3:][::-1]
            evs = [X.event_record(sim, int(e)) for e in mine]
            for r in evs:
                r["a_name"] = synthetic_name(P, r["a"])
                r["b_name"] = synthetic_name(P, r["b"]) if r["b"] is not None else None
            out.append({"id": i, "name": synthetic_name(P, i), "headline": headline(sim, i), "present": bool(P["present"][i]),
                        "mood": float(P["mood"][i]), "loneliness": float(P["loneliness"][i]), "events": evs})
        return jresp(out)


@app.get("/api/people/search")
def search(q: str = "", u: str = "base", limit: int = 20):
    sim = WS.sim(u)
    P = sim.w.P
    out = []
    ql = q.lower().strip()
    if ql.isdigit():
        i = int(ql)
        if i < P.n:
            out.append({"id": i, "name": synthetic_name(P, i)})
    else:
        for i in np.where(P["present"])[0][:20000]:
            nm = synthetic_name(P, int(i))
            if ql in nm.lower():
                out.append({"id": int(i), "name": nm})
                if len(out) >= limit:
                    break
    return jresp(out)


# ----------------------------------------------------------------------------- events & provenance
@app.get("/api/events")
def events(u: str = "base", type: str = "", agent: int = -1, since: int = -100000, limit: int = 200, offset: int = 0,
           min_salience: float = 0.0, after_id: int = -1):
    sim = WS.sim(u)
    with WS.lock:
        log = sim.log
        m = log["day"] >= since
        if after_id >= 0:
            m &= np.arange(log.n) > after_id
        if type:
            codes = [sim.reg.event_ids[t] for t in type.split(",") if t in sim.reg.event_ids]
            m &= np.isin(log["type"], codes)
        if agent >= 0:
            m &= (log["a"] == agent) | (log["b"] == agent)
        if min_salience > 0:
            sal = np.array([e.salience for e in sim.reg.events.values()])
            m &= sal[log["type"]] >= min_salience
        idx = np.where(m)[0][::-1]
        total = len(idx)
        idx = idx[offset: offset + limit]
        recs = [X.event_record(sim, int(e)) for e in idx]
        P = sim.w.P
        for r in recs:
            r["a_name"] = synthetic_name(P, r["a"])
            if r["b"] is not None:
                r["b_name"] = synthetic_name(P, r["b"])
        return jresp({"total": total, "events": recs})


@app.get("/api/events/summary")
def events_summary(u: str = "base", since: int = -100000):
    sim = WS.sim(u)
    with WS.lock:
        log = sim.log
        m = log["day"] >= since
        cnt = np.bincount(log["type"][m], minlength=len(sim.reg.event_names))
        rows = [{"type": sim.reg.event_names[k], "label": sim.reg.events[sim.reg.event_names[k]].label,
                 "category": sim.reg.events[sim.reg.event_names[k]].category, "count": int(cnt[k]),
                 "salience": sim.reg.events[sim.reg.event_names[k]].salience} for k in np.nonzero(cnt)[0]]
        # consequentiality: how many downstream events each type caused (direct children)
        causes = log["cause"][m]
        has = causes >= 0
        parent_types = log["type"][causes[has]]
        child_cnt = np.bincount(parent_types, minlength=len(sim.reg.event_names))
        for r in rows:
            r["children"] = int(child_cnt[sim.reg.event_ids[r["type"]]])
        daily = sim.systems["recorder"].events_frame()
        if daily.height:
            daily = daily.filter(pl.col("day") >= since)
        return jresp({"types": sorted(rows, key=lambda r: -r["count"]), "daily": daily.to_dicts() if daily.height else []})


@app.get("/api/event/{eid}")
def event(eid: int, u: str = "base"):
    sim = WS.sim(u)
    with WS.lock:
        if eid < 0 or eid >= sim.log.n:
            raise HTTPException(404, "no such event")
        P = sim.w.P
        chain = X.event_chain(sim, eid)
        desc = X.event_descendants(sim, eid)
        for r in chain + desc:
            r["a_name"] = synthetic_name(P, r["a"])
            if r["b"] is not None:
                r["b_name"] = synthetic_name(P, r["b"])
        return jresp({"event": chain[0], "ancestors": chain[1:], "descendants": desc})


# ----------------------------------------------------------------------------- time series
@app.get("/api/timeseries")
def timeseries(vars: str, group: str = "all"):
    out = {}
    for name, sim in (("base", WS.base), ("alt", WS.alt)):
        if sim is None:
            continue
        with WS.lock:
            df = sim.systems["recorder"].frame()
        if df.height == 0:
            continue
        df = df.filter(pl.col("group") == group)
        cols = ["day"] + [v for v in vars.split(",") if v in df.columns]
        out[name] = df.select(cols).to_dict(as_series=False)
    return jresp(out)


@app.get("/api/timeseries/columns")
def timeseries_columns():
    sim = WS.base
    if sim is None:
        return jresp([])
    df = sim.systems["recorder"].frame()
    return jresp([c for c in df.columns if c not in ("day", "group", "n")])


@app.get("/api/terms")
def terms(group: str = "all", state: str = "loneliness"):
    out = {}
    for name, sim in (("base", WS.base), ("alt", WS.alt)):
        if sim is None:
            continue
        with WS.lock:
            df = sim.systems["recorder"].terms_frame()
        if df.height == 0:
            continue
        df = df.filter(pl.col("group") == group)
        cols = ["day"] + [c for c in df.columns if c.startswith(state + ".")]
        out[name] = df.select(cols).to_dict(as_series=False)
    return jresp(out)


# ----------------------------------------------------------------------------- cohorts
@app.post("/api/cohort/explain")
def cohort_explain(body: dict = Body(...)):
    u = body.get("u", "base")
    sim = WS.sim(u)
    var = body.get("var", "loneliness")
    with WS.lock:
        mask = evaluate_filter(sim.w, body.get("filter"), sim)
        P = sim.w.P
        n = int(mask.sum())
        out = {"n": n, "description": describe_filter(body.get("filter")), "var": var}
        if n == 0:
            return jresp(out)
        everyone = P["present"]
        if var in sim.systems["emotion"].contrib:
            coh = {r["term"]: r for r in X.cohort_term_attribution(sim, mask, var)}
            pop = {r["term"]: r for r in X.cohort_term_attribution(sim, everyone, var)}
            rows = []
            for t, r in coh.items():
                m = sim.reg.mechanisms.get(r["mechanism"]) if r["mechanism"] else None
                rows.append({"term": t, "mechanism": r["mechanism"], "label": m.label if m else "Recent events",
                             "evidence": m.evidence if m else None, "cohort": r["mean"], "population": pop.get(t, {}).get("mean"),
                             "gap": r["mean"] - pop.get(t, {}).get("mean", 0)})
            out["terms"] = sorted(rows, key=lambda r: -abs(r["gap"]))
        x = P[var].astype(float)
        ids = np.where(mask & np.isfinite(x))[0]
        if len(ids):
            order = ids[np.argsort(x[ids])]
            pick = {"lowest": order[0], "p10": order[int(0.1 * (len(order) - 1))], "median": order[len(order) // 2],
                    "p90": order[int(0.9 * (len(order) - 1))], "highest": order[-1]}
            out["representatives"] = [{"role": k, "id": int(v), "name": synthetic_name(P, int(v)), "value": float(x[v])} for k, v in pick.items()]
            out["cohort_mean"] = float(x[ids].mean())
            out["population_mean"] = float(np.nanmean(x[everyone]))
        return jresp(out)


@app.post("/api/cohort/count")
def cohort_count(body: dict = Body(...)):
    sim = WS.sim(body.get("u", "base"))
    with WS.lock:
        mask = evaluate_filter(sim.w, body.get("filter"), sim)
        return jresp({"n": int(mask.sum()), "description": describe_filter(body.get("filter")),
                      "ids": np.where(mask)[0][: int(body.get("max_ids", 0))].tolist()})


# ----------------------------------------------------------------------------- history & flows
from ..analysis.query import NOT_HERE, state_labels  # noqa: E402


@app.get("/api/history/info")
def history_info(u: str = "base"):
    sim = WS.sim(u)
    H = sim.systems["history"]
    return jresp({"days": H.days(), "now": sim.w.day, "start_date": str(sim.cal.date(0)),
                  "categorical": H.cat_vars, "numeric": H.num_vars})


def _flow_mask(sim, filt):
    if not filt:
        return np.ones(sim.w.P.n, bool)
    return evaluate_filter(sim.w, filt, sim, include_absent=True)


@app.post("/api/flows")
def flows(body: dict = Body(...)):
    """Who moved between the states of a categorical variable across a sequence of days (Sankey)."""
    sim = WS.sim(body.get("u", "base"))
    var = body["var"]
    with WS.lock:
        H, P = sim.systems["history"], sim.w.P
        if var not in H.cat_vars:
            raise HTTPException(400, f"{var} is not tracked over time")
        days = sorted({min(int(d), sim.w.day) for d in body.get("days", [0, sim.w.day])})
        mask = _flow_mask(sim, body.get("filter"))
        labels = state_labels(P, var) + [NOT_HERE]
        def lab(code):
            return NOT_HERE if code == 255 else labels[int(code)]
        cols = [H.values(var, d if d < sim.w.day else None)[0][mask] for d in days]
        ever = np.zeros(mask.sum(), bool)
        for c in cols:
            ever |= c != 255
        cols = [c[ever] for c in cols]
        columns = []
        for d, c in zip(days, cols):
            vals, cnt = np.unique(c, return_counts=True)
            columns.append({"day": d, "date": str(sim.cal.date(d)), "nodes": [{"state": lab(v), "n": int(k)} for v, k in zip(vals, cnt)]})
        links = []
        for k in range(len(cols) - 1):
            pair = cols[k].astype(np.int32) * 256 + cols[k + 1]
            vals, cnt = np.unique(pair, return_counts=True)
            for v, m in zip(vals, cnt):
                links.append({"step": k, "from": lab(v // 256), "to": lab(v % 256), "n": int(m)})
        return jresp({"var": var, "states": labels, "days": days, "columns": columns, "links": links, "total": int(ever.sum())})


@app.post("/api/cohort_timeline")
def cohort_timeline(body: dict = Body(...)):
    """Average trajectory of today's cohort (people matching the filter now) vs everyone, at each snapshot."""
    sim = WS.sim(body.get("u", "base"))
    with WS.lock:
        H, P = sim.systems["history"], sim.w.P
        vars_ = [v for v in body.get("vars", []) if H.tracked(v)]
        mask = _flow_mask(sim, body.get("filter"))
        if body.get("people"):   # a hand-picked selection (the workbench) narrows the group further
            ids = np.asarray([int(i) for i in body["people"] if 0 <= int(i) < P.n], np.int64)
            sel = np.zeros(P.n, bool)
            sel[ids] = True
            mask = mask & sel
        if body.get("filter_world") == "base" and sim is not WS.base and WS.base is not None:
            # the same people as in the Original: pick the group there, follow them in this world
            mb = _flow_mask(WS.base, body.get("filter"))
            mask = np.zeros(P.n, bool)
            k = min(P.n, len(mb))
            mask[:k] = mb[:k]
        days = H.days() + ([sim.w.day] if not H.days() or H.days()[-1] < sim.w.day else [])
        out = {"days": days, "dates": [str(sim.cal.date(d)) for d in days], "cohort": {}, "everyone": {}, "n": []}
        for d in days:
            dd = None if d >= sim.w.day else d
            _, pres = H.values(vars_[0] if vars_ else H.cat_vars[0], dd)
            out["n"].append(int((pres & mask).sum()))
        for v in vars_:
            cat = v in H.cat_vars
            series_c, series_a = [], []
            for d in days:
                x, pres = H.values(v, None if d >= sim.w.day else d)
                if cat:  # share in the "positive"/top category for bools, else distribution
                    labs = state_labels(P, v)
                    def shares(m):
                        k = int(m.sum())
                        return {labs[c]: float((x[m] == c).sum() / k) for c in range(len(labs))} if k else None
                    series_c.append(shares(pres & mask)); series_a.append(shares(pres))
                else:
                    def mean(m):
                        y = x[m]
                        y = y[np.isfinite(y)]
                        return float(y.mean()) if len(y) else None
                    series_c.append(mean(pres & mask)); series_a.append(mean(pres))
            out["cohort"][v], out["everyone"][v] = series_c, series_a
        return jresp(out)


# ----------------------------------------------------------------------------- compare universes
@app.get("/api/compare")
def compare():
    if WS.alt is None:
        raise HTTPException(404, "no intervention universe")

    def build():
        c = X.compare_universes(WS.base, WS.alt)
        c["divergence"] = list(WS.divergence)
        c["interventions"] = WS.alt.interventions
        c["most_affected"] = {v: X.most_affected(WS.base, WS.alt, v) for v in ("mood", "loneliness", "faith_belief", "financial_stress")}
        for v, rows in c["most_affected"].items():
            for r in rows:
                r["name"] = synthetic_name(WS.base.w.P, r["id"])
        return c
    c = _cached(("compare",), build)
    WS.compare_cache = c     # the cause-and-effect graph reads the latest comparison
    return jresp(c)


def _need_alt():
    if WS.alt is None or WS.base is None:
        raise HTTPException(404, "no what-if world; make a change first")


_memo: dict = {}   # key -> (state tag, answer)


def _tag() -> tuple:
    alt = WS.alt
    return (WS.world_id, WS.fork_id, id(WS.base), id(alt), WS.base.w.day, WS.base.w.hour, alt.w.day, alt.w.hour, len(alt.interventions))


def _cached(key: tuple, fn):
    """Reuse a comparison until either world moves, so pages polling during a run don't recompute it.
    An answer already computed for the current state is a finished snapshot, so it is returned without waiting for
    the workspace lock (a run holds it for a whole simulated day); otherwise it is computed under the lock."""
    hit = _memo.get(key)
    if hit is not None and hit[0] == _tag():
        return hit[1]
    with WS.lock:
        tag = _tag()
        hit = _memo.get(key)
        if hit is None or hit[0] != tag:
            for k in [k for k, v in _memo.items() if v[0] != tag]:
                _memo.pop(k, None)
            hit = (tag, fn())
            _memo[key] = hit
        return hit[1]


@app.get("/api/compare/fields")
def compare_fields():
    """Every chartable field, Original vs What-if: averages or shares, effect size, how many people changed,
    and the difference over time since the split."""
    _need_alt()
    return jresp(_cached(("fields",), lambda: B.compare_fields(WS.base, WS.alt)))


@app.get("/api/compare/people")
def compare_people(k: int = 40):
    """The people whose lives diverged most between the two worlds, and why."""
    _need_alt()
    k = max(1, min(k, 200))
    return jresp(_cached(("people", k), lambda: B.diverged_people(WS.base, WS.alt, k=k)))


@app.get("/api/compare/person/{i}")
def compare_person(i: int):
    """One person's two lives since the split, the first fork in their road and the chain of causes behind it."""
    _need_alt()
    with WS.lock:
        if i < 0 or i >= min(WS.base.w.P.n, WS.alt.w.P.n):
            raise HTTPException(404, "no such person in both worlds")
        return jresp(B.person_divergence(WS.base, WS.alt, i))


@app.get("/api/compare/relationships")
def compare_relationships(k: int = 40):
    """Couples and friendships that exist in only one of the two worlds."""
    _need_alt()
    k = max(1, min(k, 200))
    return jresp(_cached(("relationships", k), lambda: B.compare_relationships(WS.base, WS.alt, k=k)))


@app.get("/api/compare/places")
def compare_places(kind: str = "complex", var: str = "loneliness"):
    _need_alt()
    if kind not in ("complex", "ward", "neighborhood", "school"):
        raise HTTPException(400, "kind must be complex|ward|neighborhood|school")
    if var not in WS.base.w.P.specs:
        raise HTTPException(400, f"unknown field {var}")
    return jresp(_cached(("places", kind, var), lambda: B.compare_places(WS.base, WS.alt, kind, var)))


@app.post("/api/fork/add")
def fork_add(body: dict = Body(...)):
    """Add more changes to the existing What-if world, starting today (the Original is untouched)."""
    _need_alt()
    from ..engine.interventions import expand
    with WS.lock:
        alt = WS.alt
        man = alt.systems["environment"].manager
        added = []
        for spec in body.get("interventions", []):
            for atom in expand(spec):
                atom["start_day"] = max(int(atom.get("start_day", 0)), alt.w.day)
                atom.setdefault("ramp_days", 0)
                atom.setdefault("duration_days", None)
                atom.setdefault("op", "set")
                man.add(atom)
                alt.interventions.append(atom)
                added.append(atom)
        WS.compare_cache = None
    return jresp({"ok": True, "added": len(added)})


# ----------------------------------------------------------------------------- natural-language What-ifs (LLM)
def _target(mode: str = "new"):
    from ..llm.compiler import target_world
    return target_world(WS, mode)


def _entity_index(mode: str = "new"):
    """Entity index over the world a plan will run in (the Original for a new What-if, the What-if when adding to it),
    rebuilt daily or when worlds change. Call with WS.lock held."""
    from ..llm.entities import EntityIndex
    sim = _target(mode)
    which = "alt" if sim is WS.alt else "base"
    tag = (WS.world_id, WS.fork_id, sim.w.day)
    cache = {k: v for k, v in (WS._index or {}).items() if v[0][:2] == tag[:2]}     # forget replaced worlds
    if cache.get(which, (None,))[0] != tag:
        cache[which] = (tag, EntityIndex(sim))
    WS._index = cache
    return cache[which][1]


def _local_only(request: Request):
    """The What-if compiler runs your own Claude/Codex login, so only pages served from this machine may drive it
    (the API's CORS is open for the static viewer; this keeps other websites from spending your plan)."""
    origin = request.headers.get("origin")
    if not origin or origin == "null":
        return
    from urllib.parse import urlsplit
    host = (urlsplit(origin).hostname or "").lower()
    own = (request.headers.get("host") or "").rsplit(":", 1)[0].strip("[]").lower()
    if host in ("localhost", "127.0.0.1", "::1") or (host == own and _is_ip(host)):     # a domain could be rebound
        return
    raise HTTPException(403, "What-if requests are only accepted from this computer")


def _is_ip(host: str) -> bool:
    import ipaddress
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        return False


def _server_url(request: Request) -> str:
    host, port = (request.scope.get("server") or ("127.0.0.1", 8000))[:2]
    return f"http://{'127.0.0.1' if host in ('0.0.0.0', '::', None) else host}:{port}"


@app.get("/api/entities/search")
def entities_search(q: str = "", kinds: str = "", limit: int = 12, mode: str = "new"):
    """Everything a What-if can point at: people, places, groups and model concepts, with exact refs and filters."""
    if WS.base is None:
        raise HTTPException(404, "no world")
    with WS.lock:
        ix = _entity_index(mode)
        return jresp(ix.search(q, [k for k in kinds.split(",") if k] or None, limit=max(1, min(limit, 40))))


@app.get("/api/entities/get")
def entities_get(ref: str, mode: str = "new"):
    if WS.base is None:
        raise HTTPException(404, "no world")
    with WS.lock:
        r = _entity_index(mode).get(ref)
    if r is None:
        raise HTTPException(404, f"no entity {ref}")
    return jresp(r)


@app.get("/api/whatif/llm/status")
def llm_status(refresh: bool = False):
    from ..llm import compiler
    return jresp(compiler.status(fresh=refresh))


@app.post("/api/whatif/llm/settings")
def llm_settings(request: Request, body: dict = Body(...)):
    _local_only(request)
    from ..llm import compiler
    return jresp(compiler.save_settings(body))


@app.post("/api/whatif/llm/test")
def llm_test(request: Request):
    """Ask the chosen model for a one-word reply: does the sign-in or API key really work? (Uses a tiny bit of usage.)"""
    _local_only(request)
    from ..llm import compiler
    return jresp(compiler.test_connection())


@app.get("/api/whatif/llm/models")
def llm_models(request: Request, url: str = ""):
    """Models a local server (LM Studio, Ollama) offers, for the settings dropdown."""
    _local_only(request)      # the server fetches this URL, so only this computer's pages may ask
    import re
    from ..llm import backends, compiler
    url = url or compiler.load_settings()["openai_url"]
    if not re.match(r"^https?://[\w.\-\[\]:]+(/[\w./-]*)?$", url):
        raise HTTPException(400, "not a server address")
    return jresp({"url": url, "models": backends.local_models(url)})


@app.post("/api/whatif/llm/load")
def llm_load(request: Request, body: dict = Body(...)):
    """Load a model into LM Studio with a big enough context window: {url?, model, context_length?, unload_others?}.
    Blocks until LM Studio has loaded it (seconds to a few minutes for big models)."""
    _local_only(request)
    import re
    from ..llm import backends, compiler
    s = compiler.load_settings()
    url = str(body.get("url") or s["openai_url"])
    if not re.match(r"^https?://[\w.\-\[\]:]+(/[\w./-]*)?$", url):
        raise HTTPException(400, "not a server address")
    model = str(body.get("model") or "")
    if not model or len(model) > 200:
        raise HTTPException(400, "pick a model")
    ctx = body.get("context_length") or 32768
    ctx = int(min(max(int(ctx) if isinstance(ctx, (int, float)) else 32768, 8192), 262144))
    return jresp(backends.load_local_model(url, model, ctx, bool(body.get("unload_others", True)), s.get("openai_key") or ""))


@app.post("/api/whatif/compile")
def whatif_compile(request: Request, body: dict = Body(...)):
    """Start turning a plain-language What-if into a plan: {text, mentions: [{ref,...}], history: [...], mode: new|add}."""
    _local_only(request)
    from ..llm import compiler
    if WS.base is None:
        raise HTTPException(409, "build a world first")
    text = str(body.get("text", "")).strip()
    if not text:
        raise HTTPException(400, "describe your What-if")
    job = compiler.start(WS, _entity_index, text[:4000], list(body.get("mentions") or [])[:20], list(body.get("history") or [])[-12:],
                         "add" if body.get("mode") == "add" else "new", _server_url(request))
    return jresp({"job": job.id})


@app.get("/api/whatif/compile/{jid}")
def whatif_compile_poll(jid: str):
    from ..llm import compiler
    job = compiler.JOBS.get(jid)
    if job is None:
        raise HTTPException(404, "no such job")
    return jresp(job.view())


@app.post("/api/whatif/compile/{jid}/cancel")
def whatif_compile_cancel(jid: str, request: Request):
    _local_only(request)
    from ..llm import compiler
    job = compiler.JOBS.get(jid)
    if job is not None:
        job.cancel.set()
    return {"ok": True}


@app.post("/api/whatif/tool/{name}")
def whatif_tool(name: str, request: Request, body: dict = Body(default={})):
    """The compiler's read-only tools (called by Claude Code through the MCP bridge, or by the local tool loop)."""
    _local_only(request)
    from ..llm import compiler
    if WS.base is None:
        raise HTTPException(409, "no world")
    job = compiler.JOBS.get(request.headers.get("x-ucsim-job", ""))
    mode = job.mode if job is not None else "new"
    with WS.lock:
        res = compiler.run_tool(WS, _entity_index(mode), name, body, mode)
    if job is not None:
        if name == "search_entities" and res.get("results"):
            top = res["results"][0]
            job.step("found", f"Found {top['label']} ({top['ref']})" + (f" · {top['n']} people" if top.get("n") else ""))
        elif name == "count_people" and "n" in res:
            job.step("found", f"{res['n']:,} people match: {res.get('who', '')}")
        elif name == "validate_plan":
            job.step("found", "Draft checks out" if res.get("ok") else f"Draft has {len(res.get('errors', []))} problem(s) to fix")
    return jresp(res)


@app.post("/api/whatif/validate")
def whatif_validate(request: Request, body: dict = Body(...)):
    """Re-check a (possibly edited) plan: {plan} → receipt."""
    _local_only(request)
    from ..llm.plan import plan_id, validate
    if WS.base is None:
        raise HTTPException(409, "no world")
    with WS.lock:
        mode = "add" if body.get("mode") == "add" else "new"
        v = validate(body.get("plan") or {}, _target(mode), _entity_index(mode))
    v["plan_id"] = plan_id(v["plan"])
    return jresp(v)


@app.post("/api/whatif/apply")
def whatif_apply(request: Request, body: dict = Body(...)):
    """Apply a plan: {plan, mode: new|add, include: [bool per change]} → splits the world (new) or adds to the What-if."""
    _local_only(request)
    from ..llm.plan import lower, plan_id, validate
    if WS.base is None:
        raise HTTPException(409, "no world")
    if WS.job.get("state") == "building":
        raise HTTPException(409, "a new world is being built; wait for it to finish")
    plan = body.get("plan") or (WS.plans.get(body.get("plan_id", "")) or {}).get("plan")
    if not plan:
        raise HTTPException(400, "no plan")
    if not isinstance(plan, dict):
        raise HTTPException(400, "the plan must be an object")
    src = WS.plans.get(body.get("plan_id") or "") or WS.plans.get(plan_id(plan)) or {}     # the request it came from
    include = body.get("include")
    if isinstance(include, list) and len(include) == len(plan.get("changes") or []):
        plan = {**plan, "changes": [c for c, keep in zip(plan["changes"], include) if keep]}
    with WS.lock:
        mode = "add" if body.get("mode") == "add" and WS.alt is not None else "new"
        v = validate(plan, _target(mode), _entity_index(mode))
        if not v["ok"]:
            raise HTTPException(409, "the plan still has problems: " + "; ".join(v["errors"][:4]))
        pid = plan_id(v["plan"])
        # mid-day (the morning phase already ran), changes start tomorrow so delays and durations count whole days
        today = WS.base.w.day + (1 if getattr(WS.base, "_phases_done", 0) else 0)
        atoms = lower(v["plan"], today, pid)
        if mode == "new":
            WS.alt = runner.fork(WS.base, atoms)
            WS.fork_id += 1
            WS._index = None
            WS.divergence = [runner.divergence(WS.base, WS.alt)]
        else:
            alt = WS.alt
            man = alt.systems["environment"].manager
            for a in atoms:
                a["start_day"] = max(int(a["start_day"]), alt.w.day + (1 if getattr(alt, "_phases_done", 0) else 0))
                man.add(a)
                alt.interventions.append(a)
        WS.compare_cache = None
        WS.plans[pid] = {**{k: src[k] for k in ("request", "mentions", "created") if k in src}, **WS.plans.get(pid, {}), "plan": v["plan"], "receipt": v["changes"], "applied": True,
                         "applied_day": today, "mode": mode, "atoms": [a["id"] for a in atoms]}
    return jresp({"ok": True, "plan_id": pid, "mode": mode, "changes": len(atoms), "fork_day": WS.alt.meta_fork_day if WS.alt is not None else None})


@app.get("/api/whatif/plans")
def whatif_plans():
    """Plans applied to the running What-if: their changes, who they reached, practice adoption curves, and how the
    LLM's predictions are holding up against the simulation."""
    from ..analysis.query import evaluate_filter
    with WS.lock:
        alt, base = WS.alt, WS.base
        if alt is None:
            return jresp([])
        live = {a.get("plan") for a in alt.interventions if a.get("plan")}
        report = {r["k"]: r for r in alt.whatif.report()}
        items = alt.whatif.items
        out = []
        for pid in live:
            rec = WS.plans.get(pid)
            if not rec:
                continue
            plan = rec["plan"]
            ks = [k for k, it in enumerate(items) if it.get("plan") == pid]
            reach = [{"label": items[k].get("label"), "kind": items[k].get("target_type"), "reached": report[k].get("reached"),
                      "practice": report[k].get("practice")} for k in ks]
            exps = []
            n = min(base.w.P.n, alt.w.P.n)
            for e in plan.get("expectations", []):
                row = dict(e)
                var = e.get("variable")
                if var and var in base.w.P.specs:
                    try:
                        mb = evaluate_filter(base.w, e.get("who"), sim=base)[:n] & alt.w.P["present"][:n].astype(bool)
                        if mb.sum() >= 5:
                            xb = base.w.P[var][:n][mb].astype(float)
                            xa = alt.w.P[var][:n][mb].astype(float)
                            d = float(np.nanmean(xa) - np.nanmean(xb))
                            sd = float(np.nanstd(np.r_[xa, xb])) or 1.0
                            eff = d / sd
                            row.update(base=float(np.nanmean(xb)), alt=float(np.nanmean(xa)), effect=eff, n=int(mb.sum()))
                            moved = abs(eff) >= 0.03
                            row["status"] = ("too early" if not moved else
                                             "as predicted" if (e["direction"] == "up") == (d > 0) and e["direction"] != "unclear" else
                                             "moved" if e["direction"] == "unclear" else "opposite")
                    except Exception:  # noqa: BLE001
                        pass
                exps.append(row)
            out.append({"plan_id": pid, "title": plan["title"], "request": rec.get("request"), "reply": plan.get("reply"),
                        "changes": rec.get("receipt"), "assumptions": plan.get("assumptions"), "not_modeled": plan.get("not_modeled"),
                        "expectations": exps, "reach": reach, "applied_day": rec.get("applied_day")})
        return jresp(out)


# ----------------------------------------------------------------------------- fields (the explorer)
@app.get("/api/fields/info")
def fields_info():
    """Which fields are recorded over time, and how often."""
    if WS.base is None:
        raise HTTPException(404, "no world")
    rec, H = WS.base.systems["recorder"], WS.base.systems["history"]
    return jresp({"weekly": rec.field_vars, "daily": rec.vars, "person_history": {"categorical": H.cat_vars, "numeric": H.num_vars},
                  "weekly_every": 7, "history_every": H.every, "groups": list(rec.GROUPS), "start_date": str(WS.base.cal.date(0))})


@app.get("/api/fields/summary")
def fields_summary(u: str = "base"):
    """The current value of every chartable field (for the field browser)."""
    sim = WS.sim(u)
    with WS.lock:
        return jresp(F.summary(sim, sim.systems["recorder"].field_vars))


@app.get("/api/fields/timeline")
def fields_timeline(var: str, group: str = "all"):
    """A field over time for a standard group, in each world that exists."""
    out = {"var": var, "group": group}
    for name, sim in (("base", WS.base), ("alt", WS.alt)):
        if sim is None:
            continue
        with WS.lock:
            t = F.timeline(sim, var, group)
        if t is not None:
            out[name] = t
    if "base" not in out:
        raise HTTPException(404, f"{var} is not recorded over time")
    out["fork_day"] = getattr(WS.alt, "meta_fork_day", None) if WS.alt is not None else None
    return jresp(out)


@app.get("/api/person/{i}/history")
def person_history(i: int):
    """One person's tracked states every two weeks, in each world."""
    out = {}
    for name, sim in (("base", WS.base), ("alt", WS.alt)):
        if sim is None or i >= sim.w.P.n:
            continue
        with WS.lock:
            out[name] = F.person_history(sim, i)
    if not out:
        raise HTTPException(404, "no such person")
    out["fork_day"] = getattr(WS.alt, "meta_fork_day", None) if WS.alt is not None else None
    return jresp(out)


@app.get("/api/pulse")
def pulse(u: str = "base"):
    """The world right now: what people are doing, the day's and week's events, headlines, what's moving, lives to follow."""
    sim = WS.sim(u)
    with WS.lock:
        out = F.pulse(sim, F.featured_people(sim))
        out["interventions"] = WS.alt.interventions if WS.alt is not None else []
        out["fork_day"] = getattr(WS.alt, "meta_fork_day", None) if WS.alt is not None else None
        out["divergence"] = WS.divergence[-1] if WS.divergence else None
        return jresp(out)


@app.get("/api/relationships")
def relationships(u: str = "base", status: str = "", limit: int = 60):
    """Couples (newest first) and the kinds of ties that make up the friendship network."""
    sim = WS.sim(u)
    with WS.lock:
        return jresp(F.relationships(sim, status, min(limit, 500)))


@app.get("/api/causal_graph")
def causal_graph():
    """Mechanism graph: variables → mechanisms → variables, with evidence levels (+ deltas if comparing)."""
    reg = WS.registry
    deltas = WS.compare_cache["mechanisms"] if WS.compare_cache else {}
    var_d = {k: v.get("delta_sd", v.get("delta")) for k, v in WS.compare_cache["variables"].items()} if WS.compare_cache else {}
    nodes, edges = {}, []
    for mid, m in reg.mechanisms.items():
        nodes[mid] = {"id": mid, "kind": "mechanism", "label": m.label, "evidence": m.evidence, "system": m.system,
                      "delta": deltas.get(mid)}
        tg = m.target if isinstance(m.target, list) else [m.target]
        for t in tg:
            if t in reg.variables:
                nodes.setdefault(t, {"id": t, "kind": "variable", "label": reg.variables[t].label,
                                     "domain": reg.variables[t].domain, "delta": var_d.get(t)})
                edges.append({"source": mid, "target": t})
        for s in m.sources:
            if s in reg.variables:
                nodes.setdefault(s, {"id": s, "kind": "variable", "label": reg.variables[s].label,
                                     "domain": reg.variables[s].domain, "delta": var_d.get(s)})
                edges.append({"source": s, "target": mid})
    for e in reg.events.values():
        for eff in e.effects:
            nodes.setdefault(f"event:{e.id}", {"id": f"event:{e.id}", "kind": "event", "label": e.label, "evidence": e.evidence})
            if eff["var"] in reg.variables:
                edges.append({"source": f"event:{e.id}", "target": eff["var"], "mag": eff["mag"], "half_life": eff["half_life"]})
    return jresp({"nodes": list(nodes.values()), "edges": edges})


# ----------------------------------------------------------------------------- places & institutions
@app.get("/api/places/complexes")
def complexes(var: str = "loneliness", u: str = "base", min_n: int = 3):
    sim = WS.sim(u)
    with WS.lock:
        P, w = sim.w.P, sim.w
        pres = P["present"] & (P["complex_id"] >= 0)
        cid = P["complex_id"][pres]
        x = P[var][pres].astype(float)
        n = np.bincount(cid, minlength=w.complexes.height)
        s = np.bincount(cid, weights=np.nan_to_num(x), minlength=w.complexes.height)
        cx = w.complexes
        out = []
        for k in np.where(n >= min_n)[0]:
            row = {"id": int(k), "name": cx["name"][int(k)], "lon": float(cx["lon"][int(k)]), "lat": float(cx["lat"][int(k)]),
                   "name": ward_name(w.wards, k), "n": int(n[k]), "mean": float(s[k] / n[k]), "kind": cx["kind"][int(k)],
                   "contracted": bool(cx["contracted"][int(k)])}
            C = w.meta.get("culture")
            if C is not None:
                row.update(social=round(float(C["cx_social"][k]), 3), observance=round(float(C["cx_relig"][k]), 3),
                           party=round(float(C["cx_party"][k]), 3))
            out.append(row)
        return jresp(out)


@app.get("/api/places/venues")
def venues():
    sim = WS.base
    if sim is None:
        raise HTTPException(404)
    v = sim.w.venues
    rows = v.select("venue_id", "name", "vtype", "lon", "lat").to_dicts()
    C = getattr(sim.w, "congregations", None) or {}
    for k, nm in enumerate(C.get("name", [])):
        rows.append({"venue_id": -1 - k, "name": f"{nm} ({C['affiliation'][k]})", "vtype": "congregation",
                     "lon": float(C["lon"][k]), "lat": float(C["lat"][k])})
    return jresp(rows)


@app.get("/api/places/wards")
def wards(var: str = "attend_rate", u: str = "base"):
    sim = WS.sim(u)
    with WS.lock:
        P, w = sim.w.P, sim.w
        pres = P["present"] & (P["ward_id"] >= 0)
        wid = P["ward_id"][pres]
        nw = len(w.wards["kind"])
        n = np.bincount(wid, minlength=nw)
        s = np.bincount(wid, weights=np.nan_to_num(P[var][pres].astype(float)), minlength=nw)
        return jresp([{"id": k, "kind": str(w.wards["kind"][k]), "lon": float(w.wards["lon"][k]), "lat": float(w.wards["lat"][k]),
                       "name": ward_name(w.wards, k), "n": int(n[k]), "mean": float(s[k] / max(n[k], 1))} for k in range(nw) if n[k] > 0])


INSTITUTION_VARS = ["age", "mood", "loneliness", "stress", "belonging", "faith_belief", "attend_rate", "n_friends",
                    "dates_30d", "financial_stress", "gpa", "rent"]


@app.get("/api/institution/{kind}/{iid}")
def institution(kind: str, iid: int, u: str = "base"):
    sim = WS.sim(u)
    with WS.lock:
        P, w = sim.w.P, sim.w
        if kind == "complex":
            mask = P["complex_id"] == iid
            name = w.complexes["name"][iid]
        elif kind == "ward":
            mask = P["ward_id"] == iid
            name = ward_name(w.wards, iid)
        elif kind == "employer":
            mask = P["employer_id"] == iid
            name = str(w.employers["name"][iid])
        elif kind == "school":
            mask = (P["school"] == iid) & P["enrolled"]
            name = ["none", "BYU", "UVU"][iid]
        elif kind == "unit":
            mask = P["unit_id"] == iid
            name = f"Housing unit #{iid}"
        else:
            raise HTTPException(400, "kind must be complex|ward|employer|school|unit")
        mask &= P["present"]
        ids = np.where(mask)[0]
        stats = {v: float(np.nanmean(P[v][ids].astype(float))) if len(ids) else None for v in INSTITUTION_VARS}
        comp = {}
        for c in ("sex", "rel_status", "activity", "role", "school", "mission_status"):
            cats = P.specs[c].categories
            cnt = np.bincount(P[c][ids], minlength=len(cats)) if len(ids) else np.zeros(len(cats))
            comp[c] = {cats[k]: int(cnt[k]) for k in range(len(cats)) if cnt[k]}
        # internal network density
        E = w.E
        lo, hi = E.endpoints()
        inside = np.isin(lo, ids) & np.isin(hi, ids)
        friends_inside = int((inside & (E["stage"] >= 3)).sum())
        log = sim.log
        recent = np.where(np.isin(log["a"], ids) & (log["day"] >= w.day - 60))[0]
        ev = np.bincount(log["type"][recent], minlength=len(sim.reg.event_names))
        top = [{"type": sim.reg.event_names[k], "label": sim.reg.events[sim.reg.event_names[k]].label, "count": int(ev[k])}
               for k in np.argsort(-ev)[:12] if ev[k] > 0]
        members = [{"id": int(i), "name": synthetic_name(P, int(i))} for i in ids[:300]]
        culture = None
        C = w.meta.get("culture")
        if C is not None:
            cul = sim.systems["culture"]
            if kind == "complex":
                culture = cul.complex_profile(iid)
            elif kind == "ward":
                culture = {"warmth": float(C["ward_warmth"][iid]), "activity": float(C["ward_activity"][iid]),
                           "warmth_vs_average": float(cul.ward_warmth_dev(np.array([iid]))[0])}
            elif kind == "unit" and iid < len(C["unit_social"]):
                culture = {"sociability_z": float(P["home_social_culture"][ids[0]]) if len(ids) else None,
                           "observance": float(C["unit_relig"][iid]), "cohesion": float(C["unit_cohesion"][iid])}
        return jresp({"kind": kind, "id": iid, "name": name, "n": len(ids), "stats": stats, "composition": comp,
                      "friend_ties_inside": friends_inside, "culture": culture,
                      "density": friends_inside / max(len(ids) * (len(ids) - 1) / 2, 1), "recent_events": top, "members": members})


@app.get("/api/network/sample")
def network_sample(u: str = "base", min_stage: int = 3, max_nodes: int = 1500, filter: str = "", tie: str = ""):
    """A sampled friendship graph for the network view (cohort-filterable; `tie` keeps one kind of tie,
    e.g. roommate, classmate, ward, clubmate, teammate, romantic)."""
    sim = WS.sim(u)
    with WS.lock:
        P, E = sim.w.P, sim.w.E
        mask = evaluate_filter(sim.w, json.loads(filter) if filter else None, sim)
        lo, hi = E.endpoints()
        m = mask[lo] & mask[hi]
        if tie == "romantic":
            m &= (E["flags"] & (Tie.ROMANTIC | Tie.SPOUSE)) > 0
        elif tie:
            bit = next((b for b, nm in Tie.NAMES.items() if nm == tie), 0)
            m &= ((E["flags"] & bit) > 0) & (E["stage"] >= min_stage)
        else:
            m &= E["stage"] >= min_stage
        idx = np.where(m)[0]
        nodes = np.unique(np.r_[lo[idx], hi[idx]])
        if len(nodes) > max_nodes:
            # snowball sample from a few seeds so local clusters (apartments, wards) stay intact,
            # then keep every tie among the sampled people (induced subgraph)
            rng = np.random.default_rng(0)
            a, b = np.r_[lo[idx], hi[idx]], np.r_[hi[idx], lo[idx]]
            order = np.argsort(a, kind="stable")
            a, b = a[order], b[order]
            starts = np.searchsorted(a, np.arange(P.n + 1))
            seen = np.zeros(P.n, bool)
            picked: list[int] = []
            for seed in rng.permutation(nodes):
                if len(picked) >= max_nodes:
                    break
                if seen[seed]:
                    continue
                queue, seen[seed] = [int(seed)], True
                budget = max(30, max_nodes // 8)
                while queue and budget > 0 and len(picked) < max_nodes:
                    v = queue.pop(0)
                    picked.append(v)
                    budget -= 1
                    nb = b[starts[v]:starts[v + 1]]
                    nb = nb[~seen[nb]]
                    seen[nb] = True
                    queue.extend(int(x) for x in rng.permutation(nb))
            nodes = np.array(sorted(picked), dtype=np.int64)
            keep = np.zeros(P.n, bool)
            keep[nodes] = True
            idx = idx[keep[lo[idx]] & keep[hi[idx]]]
        return jresp({"nodes": [{"id": int(i), "sex": int(P["sex"][i]), "activity": int(P["activity"][i]),
                                 "school": int(P["school"][i]), "rel": int(P["rel_status"][i]), "ward": int(P["ward_id"][i]),
                                 "complex": int(P["complex_id"][i]), "loneliness": float(P["loneliness"][i]),
                                 "age": float(P["age"][i])} for i in nodes],
                      "edges": [{"s": int(lo[e]), "t": int(hi[e]), "stage": int(E["stage"][e]), "c": float(E["closeness"][e]),
                                 "met": CTX[int(E["origin_ctx"][e])] if int(E["origin_ctx"][e]) < len(CTX) else "?"} for e in idx]})


@app.get("/api/relationship_origins")
def relationship_origins(u: str = "base", min_stage: int = 3, romantic: bool = False):
    """Where relationships originate: counts by meeting context and place coordinates."""
    sim = WS.sim(u)
    with WS.lock:
        E = sim.w.E
        from ..engine.state import Tie
        m = (E["stage"] >= min_stage)
        if romantic:
            m &= (E["flags"] & (Tie.ROMANTIC | Tie.SPOUSE | Tie.DATED)) > 0
        oc = E["origin_ctx"][m]
        cnt = np.bincount(oc, minlength=len(CTX))
        return jresp({CTX[k]: int(cnt[k]) for k in range(len(CTX)) if cnt[k]})


# ----------------------------------------------------------------------------- Monte Carlo & sweeps
@app.post("/api/montecarlo")
def montecarlo(body: dict = Body(...)):
    def job():
        try:
            WS.mc = {"state": "running"}
            scen = {"baseline": []}
            scen.update(body.get("scenarios", {}))
            res = runner.monte_carlo(scen, seeds=list(range(1, int(body.get("seeds", 6)) + 1)),
                                     days=int(body.get("days", 120)), scale=float(body.get("scale", 0.1)),
                                     workers=int(body.get("workers", 4)))
            res["state"] = "done"
            WS.mc = res
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            WS.mc = {"state": "error", "error": repr(e)}
    threading.Thread(target=job, daemon=True).start()
    return {"ok": True}


@app.get("/api/montecarlo")
def montecarlo_result():
    return jresp(WS.mc or {"state": "none"})


@app.post("/api/sweep")
def sweep(body: dict = Body(...)):
    def job():
        try:
            WS.sweep_result = {"state": "running"}
            res = runner.sweep(body["param"], [float(v) for v in body["values"]], seeds=list(range(1, int(body.get("seeds", 3)) + 1)),
                               days=int(body.get("days", 120)), scale=float(body.get("scale", 0.1)), workers=int(body.get("workers", 4)))
            res["state"] = "done"
            WS.sweep_result = res
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            WS.sweep_result = {"state": "error", "error": repr(e)}
    threading.Thread(target=job, daemon=True).start()
    return {"ok": True}


@app.get("/api/sweep")
def sweep_result():
    return jresp(WS.sweep_result or {"state": "none"})


@app.post("/api/uncertainty")
def uncertainty(body: dict = Body(...)):
    """Uncertainty ensemble for a What-if: parameter draws × seeds, paired runs, stochastic vs parametric variance."""
    from ..engine.uncertainty import ensemble

    def job():
        try:
            WS.unc = {"state": "running", "progress": 0, "total": 0}

            def prog(i, n):
                WS.unc.update(progress=i, total=n)
            scen = body.get("scenario") or [{"preset": body.get("preset", "rent_up_20")}]
            res = ensemble(scen, n_draws=int(body.get("draws", 6)), seeds=tuple(range(1, int(body.get("seeds", 3)) + 1)),
                           days=int(body.get("days", 90)), warmup=int(body.get("warmup", 21)), scale=float(body.get("scale", 0.05)),
                           levels=tuple(body.get("levels", ("hypothetical", "structural", "speculative", "extrapolated"))),
                           workers=int(body.get("workers", 4)), progress=prog)
            res["state"] = "done"
            WS.unc = res
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            WS.unc = {"state": "error", "error": repr(e)}
    threading.Thread(target=job, daemon=True).start()
    return {"ok": True}


@app.get("/api/uncertainty")
def uncertainty_result():
    return jresp(getattr(WS, "unc", None) or {"state": "none"})


@app.post("/api/save")
def save(body: dict = Body(default={})):
    out = []
    with WS.lock:
        for sim in (WS.base, WS.alt):
            if sim is not None:
                out.append(str(runner.save_run(sim, notes=body.get("notes", ""))))
    return {"saved": out}


@app.get("/api/runs")
def runs():
    rows = []
    if runner.RUNS.exists():
        for d in sorted(runner.RUNS.iterdir()):
            cfg = d / "config.json"
            if cfg.exists():
                rows.append(json.loads(cfg.read_text(encoding="utf-8")))
    return jresp(rows)


# ----------------------------------------------------------------------------- app updates
@app.get("/api/update/check")
def update_check(force: bool = False):
    """Is a newer release of the installed app on GitHub?"""
    from .. import updater
    return jresp(updater.check(force))


@app.get("/api/update/status")
def update_status():
    from .. import updater
    return jresp(dict(updater.STATE))


@app.post("/api/update/install")
def update_install(request: Request):
    """Download the newer installer, run it silently and quit; the new version starts by itself."""
    _local_only(request)
    from .. import updater
    from ..app import data_home
    return jresp(updater.start_install(data_home()))


# ----------------------------------------------------------------------------- feature routers
def _include_routers():
    """Every `ucsim/api/routes_*.py` module that defines `router` (a FastAPI APIRouter) is served. Handlers import what
    they need from this module lazily (`from .server import WS, jresp`), so feature modules never edit this file."""
    import importlib
    import pkgutil
    import sys
    # the package's __path__ (not its folder) so the frozen Windows app's importer can list bundled modules too
    for m in sorted(pkgutil.iter_modules(sys.modules[__package__].__path__), key=lambda m: m.name):
        if m.name.startswith("routes_"):
            mod = importlib.import_module(f"{__package__}.{m.name}")
            if getattr(mod, "router", None) is not None:
                app.include_router(mod.router)


_include_routers()


# ----------------------------------------------------------------------------- static
@app.get("/geo/{name}")
def geo(name: str):
    p = GEO_DIR / name
    if not p.exists():
        raise HTTPException(404)
    return FileResponse(p)


if WEB_DIST.exists():
    app.mount("/", StaticFiles(directory=WEB_DIST, html=True), name="web")


def main():
    ap = argparse.ArgumentParser(description="Serve the simulator and workstation. Worlds are normally created from the UI; "
                                             "pass --scale to build one at startup instead.")
    ap.add_argument("--scale", type=float, default=None, help="build a world of this scale at startup (0.3 ≈ 18k people)")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--warmup", type=int, default=0, help="with --scale: simulate this many days before serving")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--host", default="127.0.0.1")
    args = ap.parse_args()
    if args.scale is not None:
        print(f"Building world (scale {args.scale}, seed {args.seed}, warmup {args.warmup} days) …")
        WS.job = {"state": "building", "phase": "synthesizing", "progress": 0, "total": max(args.warmup, 1), "started": time.time()}
        WS.build(args.scale, args.seed, args.warmup)
    from ..app import free_port
    port = free_port(args.port, args.host)  # Windows may reserve the requested port; fall back to a free one
    print(f"Workstation: http://{args.host}:{port}")
    import uvicorn
    uvicorn.run(app, host=args.host, port=port, log_level="warning")


if __name__ == "__main__":
    main()
