"""Episodic memory: compact, structured, inspectable.

Generative Agents (Park et al. 2023) keep a stream of observations, retrieve by recency × importance ×
relevance, and reflect. Here the same ideas run on structured data rather than text:

* **encoding** — every salient event a person experiences becomes a memory row pointing at the event log:
  who else was involved, how it felt (valence, from the event's registered emotional effects and its
  quality), and how important it was (salience × feeling × how much the person cares about the concern it
  touches — the appraisal's relevance).
* **forgetting** — strength decays as a power law of age (Wixted & Ebbesen 1991; ACT-R base-level
  learning); rehearsal (retrieval, rumination) strengthens it. Weak memories are pruned; core memories
  (very important ones) are kept for good.
* **retrieval** — recency × importance × relevance (same person, same concern). Simulation retrieval
  rehearses; reading a person's page in the UI does not (``rehearse=False``), so looking never changes
  the world.
* **use** — rumination keeps negative memories active (a named mood term); a person's memory tone feeds
  how they judge their life; lessons (plans.py / mind) cite the memories that taught them.

One row ≈ 23 bytes; with pruning a person keeps a few dozen memories, so 60k people fit in ~50 MB.
"""
from __future__ import annotations

import numpy as np

# how each composed state counts toward the felt valence of an event (positive = feels good)
VALENCE_W = {"mood": 1.0, "self_esteem": 0.8, "belonging": 0.8, "purpose": 0.6, "loneliness": -1.0, "stress": -0.8,
             "anxiety": -0.8, "guilt": -0.8, "financial_stress": -0.6, "academic_pressure": -0.5, "romantic_longing": -0.4,
             "fatigue": -0.3}
# the concern (mind.MOTIVES) each event category touches, for appraisal relevance; events may override with `motive:`
CATEGORY_MOTIVE = {"social": "connection", "romance": "partnership", "sexuality": "partnership", "academics": "achievement",
                   "work": "security", "housing": "security", "religion": "faith", "health": "health", "habits": "faith",
                   "family": "partnership"}


class MemoryStore:
    COLS = {"agent": np.int32, "event": np.int32, "day": np.int32, "etype": np.int16, "other": np.int32,
            "valence": np.float16, "importance": np.float16, "rehearsal": np.uint8}

    def __init__(self, registry, capacity: int = 1 << 15):
        self.reg = registry
        self.n = 0
        self.cap = capacity
        self.cols = {c: np.zeros(capacity, t) for c, t in self.COLS.items()}
        names = registry.event_names
        self.base_valence = np.zeros(len(names), np.float32)
        self.salience = np.zeros(len(names), np.float32)
        self.motive_of = []
        for k, nm in enumerate(names):
            spec = registry.events[nm]
            v = sum(VALENCE_W.get(e["var"], 0.0) * float(e["mag"]) for e in spec.effects)
            self.base_valence[k] = float(np.tanh(8.0 * v))
            self.salience[k] = spec.salience
            self.motive_of.append(getattr(spec, "motive", None) or CATEGORY_MOTIVE.get(spec.category))
        self.min_salience = 0.3

    # ------------------------------------------------------------------ encoding
    def encode(self, event_ids, agents, etype_code: int, others, day: int, quality=None, relevance=None):
        if self.salience[etype_code] < self.min_salience:
            return
        agents = np.atleast_1d(np.asarray(agents))
        k = len(agents)
        if k == 0:
            return
        if self.n + k > self.cap:
            new_cap = max(self.cap * 2, self.n + k + 1024)
            for c, arr in self.cols.items():
                g = np.zeros(new_cap, arr.dtype)
                g[: self.cap] = arr
                self.cols[c] = g
            self.cap = new_cap
        val = np.full(k, self.base_valence[etype_code], np.float32)
        if quality is not None:
            val = np.clip(val + 0.4 * np.tanh(np.broadcast_to(np.asarray(quality, np.float32), (k,))), -1, 1)
        rel = np.ones(k, np.float32) if relevance is None else np.broadcast_to(np.asarray(relevance, np.float32), (k,))
        imp = np.clip(self.salience[etype_code] * (0.6 + 0.4 * np.abs(val)) * rel, 0, 1)
        s = slice(self.n, self.n + k)
        self.cols["agent"][s] = agents
        self.cols["event"][s] = np.broadcast_to(np.asarray(event_ids), (k,))
        self.cols["day"][s] = day
        self.cols["etype"][s] = etype_code
        self.cols["other"][s] = -1 if others is None else np.broadcast_to(np.asarray(others), (k,))
        self.cols["valence"][s] = val
        self.cols["importance"][s] = imp
        self.cols["rehearsal"][s] = 0
        self.n += k

    def __getitem__(self, c):
        return self.cols[c][: self.n]

    # ------------------------------------------------------------------ strength and forgetting
    def strength(self, day: int, decay: float = 0.5, tau: float = 7.0) -> np.ndarray:
        age = np.maximum(day - self["day"], 0).astype(np.float32)
        imp = self["importance"].astype(np.float32)
        reh = self["rehearsal"].astype(np.float32)
        return imp * (1 + 0.5 * reh) * (1 + age / tau) ** (-decay)

    def prune(self, day: int, decay: float, floor: float = 0.07, per_agent: int = 40, core: float = 0.8):
        if self.n == 0:
            return
        st = self.strength(day, decay)
        imp = self["importance"].astype(np.float32)
        keep = (st >= floor) | (imp >= core)
        # cap per person: keep their strongest
        order = np.lexsort((-st, self["agent"]))
        ag = self["agent"][order]
        first = np.r_[0, np.flatnonzero(ag[1:] != ag[:-1]) + 1]
        rank = np.arange(len(order)) - np.repeat(first, np.diff(np.r_[first, len(order)]))
        cap_ok = np.zeros(self.n, bool)
        cap_ok[order] = rank < per_agent
        keep &= cap_ok | (imp >= core)
        k = int(keep.sum())
        for c, arr in self.cols.items():
            arr[:k] = arr[: self.n][keep]
        self.n = k

    # ------------------------------------------------------------------ queries
    def per_agent(self, n_agents: int, day: int, decay: float):
        """(count, tone, negative load) per agent: tone = strength-weighted mean valence; load = Σ strength of
        negative memories from the last 60 days."""
        if self.n == 0:
            z = np.zeros(n_agents)
            return z.astype(np.int16), z, z
        st = self.strength(day, decay)
        ag = self["agent"]
        val = self["valence"].astype(np.float32)
        cnt = np.bincount(ag, minlength=n_agents)
        num = np.bincount(ag, weights=st * val, minlength=n_agents)
        den = np.bincount(ag, weights=st, minlength=n_agents)
        tone = np.where(den > 0, num / np.maximum(den, 1e-9), 0.0)
        recent_neg = (val < -0.1) & (day - self["day"] <= 60)
        load = np.bincount(ag[recent_neg], weights=st[recent_neg] * -val[recent_neg], minlength=n_agents)
        return np.minimum(cnt, 32000).astype(np.int16), tone, load

    def recall(self, i: int, day: int, decay: float, k: int = 12, about: int | None = None, motive: str | None = None,
               rehearse: bool = False) -> list[int]:
        """Row indices of agent i's top-k memories by recency × importance × relevance."""
        rows = np.where(self["agent"] == i)[0]
        if len(rows) == 0:
            return []
        st = self.strength(day, decay)[rows]
        rel = np.ones(len(rows), np.float32)
        if about is not None:
            rel *= np.where(self["other"][rows] == about, 2.5, 1.0)
        if motive is not None:
            rel *= np.array([1.8 if self.motive_of[t] == motive else 1.0 for t in self["etype"][rows]], np.float32)
        top = rows[np.argsort(-(st * rel))[:k]]
        if rehearse:
            self.cols["rehearsal"][top] = np.minimum(self["rehearsal"][top].astype(int) + 1, 250).astype(np.uint8)
        return top.tolist()

    def rehearse_negative(self, agents: np.ndarray, day: int, decay: float, per: int = 2):
        """Rumination: each listed agent re-lives their strongest recent negative memories."""
        if self.n == 0 or len(agents) == 0:
            return
        mask = np.zeros(int(max(agents.max(), self["agent"].max())) + 1, bool)
        mask[agents] = True
        cand = np.where(mask[self["agent"]] & (self["valence"].astype(np.float32) < -0.1) & (day - self["day"] <= 90))[0]
        if len(cand) == 0:
            return
        st = self.strength(day, decay)[cand]
        order = np.lexsort((-st, self["agent"][cand]))
        ag = self["agent"][cand][order]
        first = np.r_[0, np.flatnonzero(ag[1:] != ag[:-1]) + 1]
        rank = np.arange(len(order)) - np.repeat(first, np.diff(np.r_[first, len(order)]))
        hit = cand[order[rank < per]]
        self.cols["rehearsal"][hit] = np.minimum(self["rehearsal"][hit].astype(int) + 1, 250).astype(np.uint8)
