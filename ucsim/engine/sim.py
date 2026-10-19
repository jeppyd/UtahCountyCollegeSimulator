"""Simulation orchestrator: multi-timescale, event-driven daily loop.

Timescales
----------
blocks (morning/afternoon/evening/late evening, engine/clock.py): activity choice → co-presence → encounters
daily   : occasions (hosting, invitations, attendance), romance decisions & dates, emotional states, sleep, illness
weekly  : tie stages & closeness, faith & practice, norms diffusion, relationships, study
monthly : finances, jobs, housing market, fertility, missions, life-event hazards
term    : enrollment, sections, grades, graduation, lease turnover, cohort arrivals
"""
from __future__ import annotations

import time

import numpy as np

from . import clock
from .core import Calendar, Effects, EventLog, Streams
from .ledger import CauseLinks, DecisionLog, OccasionBook
from .memory import MemoryStore
from .world import World

EMOTION_STATES = ["mood", "stress", "loneliness", "anxiety", "belonging", "self_esteem", "guilt", "fatigue",
                  "purpose", "financial_stress", "academic_pressure", "romantic_longing"]
BLOCKS = list(clock.BLOCK_NAMES)


class Simulation:
    def __init__(self, world: World, interventions: list | None = None, name: str = "baseline",
                 record: bool = True):
        from .systems import (academics, activity, economy, emotion, encounters, environment, faith, groups, housing,
                              history, intimacy, lifecourse, mind, coping, culture, network, norms, occasions, plans,
                              recorder, romance, routine)
        self.w = world
        self.name = name
        self.reg = world.reg
        self.p = world.params
        self.streams = Streams(world.seed)
        self.cal = Calendar(world.cfg, world.start_date)
        self.log = EventLog(world.reg)
        self.effects = Effects(EMOTION_STATES)
        self.memory = MemoryStore(world.reg)
        # ledgers (engine/ledger.py): why choices went the way they did, extra causes of events, occasions and scenes
        self.decisions = DecisionLog(world.reg.decisions)
        self.causes = CauseLinks()
        self.book = OccasionBook(world.reg.occasions)
        self.detail_days = 120     # full decision/invitation detail is kept this long; older rows thin to what matters
        from ..geo.travel import TravelModel
        self.travel = TravelModel(world)   # door-to-door minutes by walking, bike, car, UTA transit or a ride
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
            "intimacy": intimacy.Intimacy(self),
            "emotion": emotion.Emotion(self),
            "faith": faith.Faith(self),
            "norms": norms.Norms(self),
            "mind": mind.Mind(self),
            "coping": coping.Coping(self),
            "plans": plans.Plans(self),
            "routine": routine.Routine(self),
            "culture": culture.Culture(self),
            "economy": economy.Economy(self),
            "occasions": occasions.Occasions(self),
            "housing": housing.Housing(self),
            "recorder": recorder.Recorder(self),
            "history": history.History(self),
        }
        self._zcache_day = -999
        self._zcache: dict[str, tuple[float, float]] = {}
        for name in ("environment", "housing", "activity", "groups", "network", "academics", "encounters", "economy",
                     "romance", "intimacy", "faith", "norms", "mind", "coping", "plans", "routine", "emotion", "culture", "occasions",
                     "lifecourse", "recorder"):
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

    @property
    def whatif(self):
        """The intervention manager (the What-if's changes; empty in the Original)."""
        return self.systems["environment"].manager

    def nudge(self, channel: str):
        """Population-scoped persistent offset a What-if puts on a behavior or feeling channel (0.0 when none)."""
        env = self.systems.get("environment")
        return env.manager.bias(channel) if env is not None else 0.0

    def emit(self, etype: str, a, b=None, value=None, cause=None, place=None, block: int = 0,
             mech: str | None = None, ev: dict | None = None, effects_for: str = "a", effects: list | None = None,
             motive: str | None = None, valence: float | None = None, salience: float | None = None,
             scale: float = 1.0, salt: int = 991, decision=None, causes: list | None = None) -> np.ndarray:
        """Log events, appraise them, apply their registered emotional effects and lay down memories.

        What-if injections can override the template: `effects` (instance effects instead of the registered ones),
        `motive` (which concern appraisal reads), `valence`/`salience` (how the memory feels and how memorable it is),
        `scale` (a severity multiplier on every effect, 0.25–4) and `salt` (independent effect noise per injection).

        Provenance: `decision` (decision id(s) from `self.decisions.record`) says which choice produced the event;
        `causes` adds typed causes beyond the single `cause` parent: a list of (kind, refs, weight) with kind from
        ledger.CAUSE_KINDS ("occasion", "person", "tie", "calendar", "action", ...) and refs aligned with `a`."""
        a = np.atleast_1d(np.asarray(a, dtype=np.int64))
        ids = self.log.emit(etype, self.w.day, a, b=b, value=value, cause=cause, place=place, block=block, mech=mech,
                            decision=decision)
        if not len(a):
            return ids
        if decision is not None:
            self.decisions.link_event(decision, ids)
        for item in causes or ():
            kind, refs = item[0], item[1]
            self.causes.add(ids, kind, refs, item[2] if len(item) > 2 else 1.0)
        spec = self.reg.events[etype]
        targets = a if effects_for == "a" else np.atleast_1d(np.asarray(b, dtype=np.int64))
        relevance, coping = self.appraise(etype, targets, motive)
        effs = spec.effects if effects is None else effects
        if effs:
            self.apply_effects(etype, targets, ids, ev or {}, relevance, coping, effects=effs, scale=scale, salt=salt)
        quality = (ev or {}).get("quality")
        self.memory.encode(ids, targets, self.reg.event_ids[etype], b if effects_for == "a" else None, self.w.day,
                           quality=quality, relevance=relevance, valence=valence, salience=salience)
        return ids

    # the concern an event touches comes from its category unless the event names one
    _NEG_STATES = frozenset(("stress", "loneliness", "anxiety", "guilt", "fatigue", "financial_stress", "academic_pressure",
                             "romantic_longing"))

    def appraise(self, etype: str, agents: np.ndarray, motive: str | None = None):
        """Appraisal (Lazarus & Folkman 1984; Scherer 2001): how relevant the event is to what this person cares
        about, and how able they feel to cope. Returns per-agent multipliers (≈1 on average): relevance scales
        every effect; low coping potential amplifies harmful effects."""
        P = self.w.P
        k = len(agents)
        mind = self.systems.get("mind")
        motive = motive or self.memory.motive_of[self.reg.event_ids[etype]]
        if mind is None or not getattr(mind, "cares_mean", None) or motive is None:
            return np.ones(k, np.float32), np.ones(k, np.float32)
        p = self.p
        c = P[f"cares_{motive}"][agents]
        rel = np.clip((0.5 + c) / (0.5 + mind.cares_mean[motive]), 0.4, 1.8) ** p("appraisal.relevance.strength")
        cp = 0.5 * P["perceived_support"][agents] + 0.3 * P["self_esteem"][agents] + 0.2 * (1 - P["stress"][agents])
        cop = np.exp(-p("appraisal.coping_potential.strength") * (cp - 0.55))
        return rel.astype(np.float32), cop.astype(np.float32)

    def apply_effects(self, etype: str, agents: np.ndarray, event_ids: np.ndarray, ev: dict,
                      relevance: np.ndarray | None = None, coping: np.ndarray | None = None, effects: list | None = None,
                      scale: float = 1.0, salt: int = 991):
        from .core import pair_normal
        spec = self.reg.events[etype]
        code = self.reg.event_ids[etype]
        log_scale = float(np.log(np.clip(scale, 0.25, 4.0)))
        for k, eff in enumerate(spec.effects if effects is None else effects):
            logm = np.zeros(len(agents))
            for mod, beta in (eff.get("mods") or {}).items():
                if mod.startswith("ev."):
                    val = np.asarray(ev.get(mod[3:], 0.0), dtype=float)
                    logm += beta * np.broadcast_to(val, (len(agents),))
                else:
                    logm += beta * self.z(mod)[agents]
            noise = pair_normal(self.w.seed, agents, np.full(len(agents), self.w.day * 131 + code * 7 + k), salt, True)
            mag = eff["mag"] * np.exp(np.clip(logm, -3, 3) + log_scale + eff.get("sd", 0.3) * noise - 0.5 * eff.get("sd", 0.3) ** 2)
            if relevance is not None:
                harmful = (eff["var"] in self._NEG_STATES) == (eff["mag"] > 0)
                mag = mag * relevance * (coping if harmful and coping is not None else 1.0)
            self.effects.add(agents, eff["var"], mag, self.w.day + int(eff.get("delay", 0)),
                             np.full(len(agents), float(eff["half_life"])), event_ids)

    # ------------------------------------------------------------------ stepping
    # Phases of a day, keyed by the clock hour at which they run.
    PHASES = (("start", 6), *((f"block{b}", h) for b, h in enumerate(clock.BLOCK_HOUR)), ("end", 23))

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
            self._run("occasions", S["occasions"].plan_day)
        elif phase.startswith("block"):
            b = int(phase[5:])
            w.hour = clock.BLOCK_HOUR[b]
            self._run("activity", S["activity"].choose, b)
            self._run("encounters", S["encounters"].run, b)
            if b == clock.EVENING[-1]:      # the evening is over: dates and what happened at parties and dances
                self._run("romance", S["romance"].evening)
        else:
            self._end_of_day()

    def _end_of_day(self):
        S = self.systems
        w = self.w
        d = w.day
        wd = self.cal.weekday(d)
        self._run("encounters", S["encounters"].friend_contact)
        self._run("occasions", S["occasions"].end_of_day)
        self._run("romance", S["romance"].daily)
        self._run("mind", S["mind"].daily)
        self._run("coping", S["coping"].daily)
        self._run("plans", S["plans"].daily)
        self._run("emotion", S["emotion"].daily)
        self._run("norms", S["norms"].daily)
        if wd == 6:  # Sunday night: weekly systems
            self._run("network", S["network"].weekly)
            self._run("mind", S["mind"].weekly)
            self._run("culture", S["culture"].weekly)
            self._run("faith", S["faith"].weekly)
            self._run("norms", S["norms"].weekly)
            self._run("romance", S["romance"].weekly)
            self._run("intimacy", S["intimacy"].weekly)
            self._run("plans", S["plans"].weekly)
            self._run("routine", S["routine"].weekly)
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
        if wd == 6:
            self.thin_ledgers()

    def thin_ledgers(self):
        """Keep full detail for `detail_days`; older decisions and invitations survive only if they led to a salient
        event (salience ≥ 0.5), belong to an occasion where something happened, or were attended. Recording draws no
        random numbers, so thinning never changes the world."""
        cut = self.w.day - self.detail_days
        if cut <= 0:
            return
        from .ledger import thin_decisions
        sal = np.array([e.salience for e in self.reg.events.values()], np.float32)
        types = self.log["type"]
        keep_ev = lambda ev: sal[types[np.clip(ev, 0, self.log.n - 1)]] >= 0.5   # noqa: E731
        O = self.book.occ
        notable = O["id"][(O["day"] < cut) & ((O["n_new_ties"] > 0) | (O["n_conflicts"] > 0))]
        self.book.thin(cut, keep_occ=notable)
        self.systems["occasions"].thin()
        keep_dec = self.book.inv["decision"]
        thin_decisions(self.decisions, cut, keep_ev, keep_ids=keep_dec[keep_dec >= 0])

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
