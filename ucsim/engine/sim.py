"""Simulation orchestrator: multi-timescale, event-driven daily loop.

Timescales
----------
blocks (morning/afternoon/evening): activity choice → co-presence → encounters
daily   : romance decisions & dates, emotional states, sleep, illness, effects decay
weekly  : tie stages & closeness, faith & practice, norms diffusion, relationships, study
monthly : finances, jobs, housing market, fertility, missions, life-event hazards
term    : enrollment, sections, grades, graduation, lease turnover, cohort arrivals
"""
from __future__ import annotations

import time

import numpy as np

from .core import Calendar, Effects, EventLog, Streams
from .world import World

EMOTION_STATES = ["mood", "stress", "loneliness", "anxiety", "belonging", "self_esteem", "guilt", "fatigue",
                  "purpose", "financial_stress", "academic_pressure", "romantic_longing"]
BLOCKS = ["morning", "afternoon", "evening"]


class Simulation:
    def __init__(self, world: World, interventions: list | None = None, name: str = "baseline",
                 record: bool = True):
        from .systems import (academics, activity, economy, emotion, encounters, environment, faith, groups, housing,
                              history, lifecourse, mind, network, norms, recorder, romance)
        self.w = world
        self.name = name
        self.reg = world.reg
        self.p = world.params
        self.streams = Streams(world.seed)
        self.cal = Calendar(world.cfg, world.start_date)
        self.log = EventLog(world.reg)
        self.effects = Effects(EMOTION_STATES)
        self.interventions = list(interventions or [])
        self.timing: dict[str, float] = {}
        self.record = record
        self.systems = {
            "environment": environment.Environment(self),
            "lifecourse": lifecourse.LifeCourse(self),
            "academics": academics.Academics(self),
            "activity": activity.Activity(self),
            "groups": groups.Groups(self),
            "encounters": encounters.Encounters(self),
            "network": network.Network(self),
            "romance": romance.Romance(self),
            "emotion": emotion.Emotion(self),
            "faith": faith.Faith(self),
            "norms": norms.Norms(self),
            "mind": mind.Mind(self),
            "economy": economy.Economy(self),
            "housing": housing.Housing(self),
            "recorder": recorder.Recorder(self),
            "history": history.History(self),
        }
        self._zcache_day = -999
        self._zcache: dict[str, tuple[float, float]] = {}
        for name in ("environment", "housing", "activity", "groups", "network", "academics", "encounters", "economy",
                     "romance", "faith", "norms", "mind", "emotion", "lifecourse", "recorder"):
            sysobj = self.systems[name]
            if hasattr(sysobj, "init"):
                sysobj.init()
        self._ranged = [(k, v.range[0], v.range[1]) for k, v in self.w.P.specs.items()
                        if v.range and v.dtype in ("f4", "f8")]
        self.clamp()
        self.systems["history"].init()  # first snapshot = the world as built

    def clamp(self):
        """Invariant: every ranged float stays inside the registry's declared support."""
        P = self.w.P
        for k, lo, hi in self._ranged:
            col = P.cols[k][: P.n]
            np.clip(col, lo, hi, out=col)

    # ------------------------------------------------------------------ helpers used by systems
    @property
    def day(self) -> int:
        return self.w.day

    def u(self, name: str, block: int = 0) -> np.ndarray:
        """Per-agent uniform draws for this day (common random numbers across universes)."""
        return self.streams.uniform(name, self.w.day, self.w.P.n, block)

    def z(self, var: str) -> np.ndarray:
        """Population z-score of a person variable (moments cached weekly over present agents)."""
        P = self.w.P
        if self.w.day - self._zcache_day >= 7:
            self._zcache = {}
            self._zcache_day = self.w.day
        if var not in self._zcache:
            x = P[var].astype(np.float64)
            m = P["present"]
            xs = x[m & np.isfinite(x)]
            mu, sd = (float(xs.mean()), float(xs.std()) or 1.0) if len(xs) else (0.0, 1.0)
            self._zcache[var] = (mu, sd)
        mu, sd = self._zcache[var]
        x = P[var].astype(np.float64)
        return np.where(np.isfinite(x), (x - mu) / sd, 0.0)

    def emit(self, etype: str, a, b=None, value=None, cause=None, place=None, block: int = 0,
             mech: str | None = None, ev: dict | None = None, effects_for: str = "a") -> np.ndarray:
        """Log events and apply their registered emotional effects (with moderators)."""
        a = np.atleast_1d(np.asarray(a, dtype=np.int64))
        ids = self.log.emit(etype, self.w.day, a, b=b, value=value, cause=cause, place=place, block=block, mech=mech)
        spec = self.reg.events[etype]
        if spec.effects and len(a):
            targets = a if effects_for == "a" else np.atleast_1d(np.asarray(b, dtype=np.int64))
            self.apply_effects(etype, targets, ids, ev or {})
        return ids

    def apply_effects(self, etype: str, agents: np.ndarray, event_ids: np.ndarray, ev: dict):
        from .core import pair_normal
        spec = self.reg.events[etype]
        code = self.reg.event_ids[etype]
        for k, eff in enumerate(spec.effects):
            logm = np.zeros(len(agents))
            for mod, beta in (eff.get("mods") or {}).items():
                if mod.startswith("ev."):
                    val = np.asarray(ev.get(mod[3:], 0.0), dtype=float)
                    logm += beta * np.broadcast_to(val, (len(agents),))
                else:
                    logm += beta * self.z(mod)[agents]
            noise = pair_normal(self.w.seed, agents, np.full(len(agents), self.w.day * 131 + code * 7 + k), 991, True)
            mag = eff["mag"] * np.exp(np.clip(logm, -3, 3) + eff.get("sd", 0.3) * noise - 0.5 * eff.get("sd", 0.3) ** 2)
            self.effects.add(agents, eff["var"], mag, self.w.day + int(eff.get("delay", 0)),
                             np.full(len(agents), float(eff["half_life"])), event_ids)

    # ------------------------------------------------------------------ stepping
    # Phases of a day, keyed by the clock hour at which they run.
    PHASES = (("start", 6), ("block0", 8), ("block1", 13), ("block2", 18), ("end", 23))

    def _run(self, name, fn, *args):
        t0 = time.perf_counter()
        fn(*args)
        self.timing[name] = self.timing.get(name, 0.0) + time.perf_counter() - t0

    def _phase(self, phase: str):
        S = self.systems
        w = self.w
        if phase == "start":
            self._run("environment", S["environment"].daily)
            self._run("lifecourse", S["lifecourse"].daily)
            self._run("academics", S["academics"].daily)
            self._run("groups", S["groups"].daily)
            self._run("faith", S["faith"].daily)
            self._run("romance", S["romance"].plan_day)
        elif phase.startswith("block"):
            b = int(phase[-1])
            w.hour = (8, 13, 18)[b]
            self._run("activity", S["activity"].choose, b)
            self._run("encounters", S["encounters"].run, b)
            if b == 2:
                self._run("romance", S["romance"].evening)
        else:
            self._end_of_day()

    def _end_of_day(self):
        S = self.systems
        w = self.w
        d = w.day
        wd = self.cal.weekday(d)
        self._run("encounters", S["encounters"].friend_contact)
        self._run("romance", S["romance"].daily)
        self._run("mind", S["mind"].daily)
        self._run("emotion", S["emotion"].daily)
        self._run("norms", S["norms"].daily)
        if wd == 6:  # Sunday night: weekly systems
            self._run("network", S["network"].weekly)
            self._run("mind", S["mind"].weekly)
            self._run("faith", S["faith"].weekly)
            self._run("norms", S["norms"].weekly)
            self._run("romance", S["romance"].weekly)
            self._run("academics", S["academics"].weekly)
            self._run("emotion", S["emotion"].weekly)
        if self.cal.date(d + 1).day == 1:  # last day of month
            self._run("economy", S["economy"].monthly)
            self._run("housing", S["housing"].monthly)
            self._run("lifecourse", S["lifecourse"].monthly)
            self._run("emotion", S["emotion"].monthly)
        self._run("housing", S["housing"].daily)
        self._run("activity", S["activity"].night)
        self.clamp()
        if self.record:
            self._run("recorder", S["recorder"].daily)
        self._run("history", S["history"].daily)
        if d % 14 == 13:
            self.effects.prune(d)

    def step_day(self):
        """Run the remaining phases of the current day, then advance to the next morning."""
        done = getattr(self, "_phases_done", 0)
        for k in range(done, len(self.PHASES)):
            self._phase(self.PHASES[k][0])
        self._phases_done = 0
        self.w.day += 1
        self.w.hour = 6

    def advance_hours(self, hours: int):
        """Advance the clock hour by hour, running each phase when its hour is reached."""
        for _ in range(hours):
            done = getattr(self, "_phases_done", 0)
            nxt_hour = self.w.hour + 1
            if nxt_hour >= 24 + 6:
                self.step_day()
                continue
            while done < len(self.PHASES) and self.PHASES[done][1] <= nxt_hour:
                self._phase(self.PHASES[done][0])
                done += 1
            self._phases_done = done
            if done == len(self.PHASES) and nxt_hour >= 24:
                self._phases_done = 0
                self.w.day += 1
                self.w.hour = 6
            else:
                self.w.hour = nxt_hour

    def run_days(self, n: int, progress=None):
        for i in range(n):
            self.step_day()
            if progress:
                progress(i + 1, n)
        return self

    def run_until(self, day: int, progress=None):
        return self.run_days(max(0, day - self.w.day), progress)
