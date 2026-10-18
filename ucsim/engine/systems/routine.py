"""Routines: free time has a shape that repeats week to week.

People do not choose their Tuesday evening from scratch every week. Each person keeps a routine memory for
the 28 weekly slots (7 days × morning/afternoon/evening/late evening): the free-time option they habitually take there
and how automatic it has become. Doing the same thing in the same slot strengthens the habit (asymptotic
learning, Lally et al. 2010); doing something else weakens it, and a new routine replaces a faded one.
Habit strength adds to that option's utility (Wood & Neal 2007: habits cue behavior directly), so routines
persist through small changes in mood and circumstances but give way to large ones (a new home, a breakup,
a coping episode). This is the plan memory of activity-based models (MATSim agents keep and reuse plans
rather than re-planning every day) at the resolution this model runs.

Storage: two n × 28 arrays (option code and float16 strength) — about 3 bytes per slot per person.
"""
from __future__ import annotations

import numpy as np

from .. import clock

NONE = 255
SLOTS = clock.SLOTS_PER_WEEK


class Routine:
    def __init__(self, sim):
        self.sim = sim
        self.act = np.full((0, SLOTS), NONE, np.uint8)
        self.str = np.zeros((0, SLOTS), np.float16)

    def init(self):
        self._grow()

    def _grow(self):
        n = self.sim.w.P.cap
        if self.act.shape[0] < n:
            a = np.full((n, SLOTS), NONE, np.uint8)
            s = np.zeros((n, SLOTS), np.float16)
            a[: self.act.shape[0]] = self.act
            s[: self.str.shape[0]] = self.str
            self.act, self.str = a, s

    def bonus(self, idx: np.ndarray, wd: int, b: int) -> np.ndarray:
        """Utility bonus for each free-time option (8 columns): the habitual option in this slot."""
        self._grow()
        slot = int(clock.slot(wd, b))
        a = self.act[idx, slot]
        st = self.str[idx, slot].astype(np.float32)
        B = np.zeros((len(idx), 8))
        has = a != NONE
        B[np.where(has)[0], a[has]] = self.sim.p("routine.habit.weight") * st[has]
        return B

    def observe(self, b: int, wd: int, free: np.ndarray, choice: np.ndarray):
        """After the free-time choice: reinforce the routine if it was followed, erode it if not."""
        self._grow()
        idx = np.where(free & (choice[: len(free)] != NONE))[0]
        if len(idx) == 0:
            return
        slot = int(clock.slot(wd, b))
        alpha = self.sim.p("routine.habit.alpha")
        c = choice[idx]
        a = self.act[idx, slot]
        st = self.str[idx, slot].astype(np.float32)
        same = a == c
        st = np.where(same, st + alpha * (1 - st), st * (1 - 1.5 * alpha))
        switch = ~same & (st < 0.15)
        a = np.where(switch | (a == NONE), c, a)
        st = np.where(switch | (self.act[idx, slot] == NONE), alpha, st)
        self.act[idx, slot] = a
        self.str[idx, slot] = st.astype(np.float16)

    def weekly(self):
        P = self.sim.w.P
        n = P.n
        self._grow()
        P["routine_strength"] = self.str[:n].astype(np.float32).mean(axis=1)

    def for_agent(self, i: int) -> list[dict]:
        names = ["home", "campus", "gym", "eating out", "outdoors", "dancing", "visiting friends", "around the complex"]
        days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        out = []
        if i >= self.act.shape[0]:
            return out
        for s in range(SLOTS):
            a = int(self.act[i, s])
            if a != NONE:
                out.append({"day": days[s // clock.N_BLOCKS], "block": clock.BLOCK_NAMES[s % clock.N_BLOCKS], "activity": names[a],
                            "strength": round(float(self.str[i, s]), 3)})
        return out
