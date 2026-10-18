"""Engine core: keyed RNG streams, calendar, event log, transient effects.

Random streams are keyed by (seed, stream name, day, block) and draw for *every
allocated agent*, so two paired universes that share a seed consume identical
random numbers for identical agents until their states diverge (common random
numbers).  This is what makes intervention comparisons low-noise.
"""
from __future__ import annotations

import datetime as dt
import hashlib
from dataclasses import dataclass

import numpy as np
from scipy.special import ndtri

from ..registry import Registry

# ----------------------------------------------------------------------------- RNG


def _h(s: str) -> int:
    return int.from_bytes(hashlib.blake2b(s.encode(), digest_size=8).digest(), "little")


class Streams:
    def __init__(self, seed: int):
        self.seed = int(seed)
        self._cache: dict[str, int] = {}

    def gen(self, name: str, day: int, block: int = 0) -> np.random.Generator:
        key = self._cache.get(name)
        if key is None:
            key = self._cache[name] = _h(name)
        return np.random.default_rng([self.seed, key & 0xFFFFFFFF, key >> 32, day + 100000, block])

    def uniform(self, name: str, day: int, n: int, block: int = 0) -> np.ndarray:
        return self.gen(name, day, block).random(n)

    def normal(self, name: str, day: int, n: int, block: int = 0) -> np.ndarray:
        return self.gen(name, day, block).standard_normal(n)


def splitmix64(x: np.ndarray) -> np.ndarray:
    x = (x.astype(np.uint64) + np.uint64(0x9E3779B97F4A7C15))
    x = (x ^ (x >> np.uint64(30))) * np.uint64(0xBF58476D1CE4E5B9)
    x = (x ^ (x >> np.uint64(27))) * np.uint64(0x94D049BB133111EB)
    return x ^ (x >> np.uint64(31))


def pair_normal(seed: int, a: np.ndarray, b: np.ndarray, salt: int, directed: bool = False) -> np.ndarray:
    """Deterministic standard-normal value per pair (symmetric unless directed)."""
    with np.errstate(over="ignore"):
        if directed:
            lo, hi = a.astype(np.uint64), b.astype(np.uint64)
        else:
            lo = np.minimum(a, b).astype(np.uint64)
            hi = np.maximum(a, b).astype(np.uint64)
        x = splitmix64(lo * np.uint64(1000003) + hi * np.uint64(7919) + np.uint64(seed * 31 + salt))
    u = (x >> np.uint64(11)).astype(np.float64) / float(1 << 53)
    return ndtri(np.clip(u, 1e-9, 1 - 1e-9))


# ----------------------------------------------------------------------------- calendar


class Calendar:
    def __init__(self, cfg: dict, start: dt.date):
        self.start = start
        self.cfg = cfg
        self.byu_terms = cfg["calendar"]["byu_terms"]
        self.uvu_terms = cfg["calendar"]["uvu_terms"]
        self.high_f = np.array(cfg["climate"]["high_f"], dtype=float)
        self.lease = cfg["calendar"]["lease_turnover"]

    def date(self, day: int) -> dt.date:
        return self.start + dt.timedelta(days=day)

    def weekday(self, day: int) -> int:  # Monday = 0
        return self.date(day).weekday()

    def _term(self, terms, d: dt.date):
        md = f"{d.month:02d}-{d.day:02d}"
        for t in terms:
            s, e = t["start"], t["end"]
            if s <= md <= e:
                return t["name"]
        return None

    def term(self, school: str, day: int):
        d = self.date(day)
        return self._term(self.byu_terms if school == "BYU" else self.uvu_terms, d)

    def term_start(self, school: str, day: int) -> str | None:
        d = self.date(day)
        md = f"{d.month:02d}-{d.day:02d}"
        for t in (self.byu_terms if school == "BYU" else self.uvu_terms):
            if t["start"] == md:
                return t["name"]
        return None

    def term_end(self, school: str, day: int) -> str | None:
        d = self.date(day)
        md = f"{d.month:02d}-{d.day:02d}"
        for t in (self.byu_terms if school == "BYU" else self.uvu_terms):
            if t["end"] == md:
                return t["name"]
        return None

    def term_progress(self, school: str, day: int) -> float:
        """0..1 position within the current term (NaN outside terms)."""
        d = self.date(day)
        md = f"{d.month:02d}-{d.day:02d}"
        for t in (self.byu_terms if school == "BYU" else self.uvu_terms):
            if t["start"] <= md <= t["end"]:
                s = dt.date(d.year, int(t["start"][:2]), int(t["start"][3:]))
                e = dt.date(d.year, int(t["end"][:2]), int(t["end"][3:]))
                return (d - s).days / max(1, (e - s).days)
        return float("nan")

    def season(self, day: int) -> str:
        """Plain-language place in the BYU year: 'Fall semester · week 5 of 17', 'Christmas break', 'Summer break'."""
        d = self.date(day)
        md = f"{d.month:02d}-{d.day:02d}"
        for t in self.byu_terms:
            if t["start"] <= md <= t["end"]:
                s = dt.date(d.year, int(t["start"][:2]), int(t["start"][3:]))
                e = dt.date(d.year, int(t["end"][:2]), int(t["end"][3:]))
                week, weeks = (d - s).days // 7 + 1, max(1, ((e - s).days + 6) // 7)
                kind = "semester" if t["name"] in ("Fall", "Winter") else "term"
                return f"{t['name']} {kind} · week {week} of {weeks}"
        if d.month == 12 or (d.month == 1 and d.day < 8):
            return "Christmas break"
        if d.month == 8:
            return "Late-summer break"
        return "Between terms"

    def is_lease_turnover(self, day: int) -> bool:
        d = self.date(day)
        return f"{d.month:02d}-{d.day:02d}" in self.lease

    def holiday(self, day: int) -> bool:
        d = self.date(day)
        md = (d.month, d.day)
        if md in ((12, 24), (12, 25), (1, 1), (7, 4), (7, 24), (11, 27), (11, 28)):
            return True
        # Thanksgiving (4th Thursday Nov) and day after
        if d.month == 11 and d.weekday() in (3, 4) and 22 <= d.day <= 29:
            return True
        return False

    def temp_f(self, day: int) -> float:
        d = self.date(day)
        m = d.month - 1
        frac = (d.day - 1) / 30.0
        return float(self.high_f[m] * (1 - frac) + self.high_f[(m + 1) % 12] * frac)

    def is_conference_weekend(self, day: int) -> bool:
        d = self.date(day)
        return d.month in (4, 10) and d.weekday() in (5, 6) and d.day <= 7


# ----------------------------------------------------------------------------- events


class EventLog:
    """Append-only columnar log of salient events with causal parent links."""

    COLS = {"day": np.int32, "block": np.int8, "type": np.int16, "a": np.int32, "b": np.int32, "place": np.int32,
            "value": np.float32, "cause": np.int64, "mech": np.int16, "decision": np.int64}

    def __init__(self, registry: Registry, capacity: int = 1 << 16):
        self.reg = registry
        self.n = 0
        self.cap = capacity
        self.cols = {c: np.zeros(capacity, dtype=t) for c, t in self.COLS.items()}
        self.cols["b"][:] = -1
        self.cols["place"][:] = -1
        self.cols["cause"][:] = -1
        self.cols["mech"][:] = -1
        self.cols["decision"][:] = -1
        self.type_id = registry.event_ids
        self.mech_ids = {m: i for i, m in enumerate(registry.mechanisms)}
        self.mech_names = list(registry.mechanisms)

    def emit(self, etype: str, day: int, a, b=None, value=None, cause=None, place=None, block: int = 0,
             mech: str | None = None, decision=None) -> np.ndarray:
        a = np.atleast_1d(np.asarray(a, dtype=np.int64))
        k = len(a)
        if k == 0:
            return np.empty(0, dtype=np.int64)
        if self.n + k > self.cap:
            new_cap = max(self.cap * 2, self.n + k + 1024)
            for c, arr in self.cols.items():
                g = np.zeros(new_cap, dtype=arr.dtype)
                if c in ("b", "place", "cause", "mech", "decision"):
                    g[:] = -1
                g[: self.cap] = arr
                self.cols[c] = g
            self.cap = new_cap
        s = slice(self.n, self.n + k)
        self.cols["day"][s] = day
        self.cols["block"][s] = block
        self.cols["type"][s] = self.type_id[etype]
        self.cols["a"][s] = a
        if b is not None:
            self.cols["b"][s] = np.broadcast_to(np.asarray(b), (k,))
        if value is not None:
            self.cols["value"][s] = np.broadcast_to(np.asarray(value, dtype=np.float32), (k,))
        if cause is not None:
            self.cols["cause"][s] = np.broadcast_to(np.asarray(cause, dtype=np.int64), (k,))
        if place is not None:
            self.cols["place"][s] = np.broadcast_to(np.asarray(place), (k,))
        if mech is not None:
            self.cols["mech"][s] = self.mech_ids[mech]
        if decision is not None:
            self.cols["decision"][s] = np.broadcast_to(np.asarray(decision, dtype=np.int64), (k,))
        ids = np.arange(self.n, self.n + k, dtype=np.int64)
        self.n += k
        return ids

    def __getitem__(self, c):
        return self.cols[c][: self.n]

    def for_agent(self, i: int) -> np.ndarray:
        return np.where((self["a"] == i) | (self["b"] == i))[0]

    def name(self, type_code: int) -> str:
        return self.reg.event_names[type_code]


@dataclass
class _EffectBuf:
    agent: np.ndarray
    var: np.ndarray
    mag: np.ndarray
    start: np.ndarray
    hl: np.ndarray
    event: np.ndarray


class Effects:
    """Transient, decaying effects of events on composed states.

    Each effect: agent, state var, magnitude, start day (delay), half-life, source event.
    contribution(t) = mag * 0.5 ** ((t - start) / half_life) for t >= start.
    The magnitude is drawn from the event template and scaled by multiplicative moderators:
        mag = base * exp(Σ β_k * z_k) * lognormal(σ)
    """

    def __init__(self, var_names: list[str], capacity: int = 1 << 15):
        self.var_names = var_names
        self.vid = {v: i for i, v in enumerate(var_names)}
        self.n = 0
        self.cap = capacity
        self.agent = np.zeros(capacity, np.int32)
        self.var = np.zeros(capacity, np.int16)
        self.mag = np.zeros(capacity, np.float32)
        self.start = np.zeros(capacity, np.int32)
        self.hl = np.ones(capacity, np.float32)
        self.event = np.full(capacity, -1, np.int64)

    def add(self, agent, var: str, mag, start, hl, event):
        agent = np.atleast_1d(np.asarray(agent))
        k = len(agent)
        if k == 0:
            return
        if self.n + k > self.cap:
            new_cap = max(self.cap * 2, self.n + k + 1024)
            for name in ("agent", "var", "mag", "start", "hl", "event"):
                arr = getattr(self, name)
                g = np.zeros(new_cap, dtype=arr.dtype)
                g[: self.cap] = arr
                setattr(self, name, g)
            self.cap = new_cap
        s = slice(self.n, self.n + k)
        self.agent[s] = agent
        self.var[s] = self.vid[var]
        self.mag[s] = mag
        self.start[s] = start
        self.hl[s] = np.maximum(hl, 0.5)
        self.event[s] = event
        self.n += k

    def contributions(self, day: int):
        s = slice(0, self.n)
        age = day - self.start[s]
        active = age >= 0
        c = np.where(active, self.mag[s] * np.power(0.5, np.maximum(age, 0) / self.hl[s]), 0.0)
        return c

    def totals(self, day: int, n_agents: int) -> dict[str, np.ndarray]:
        c = self.contributions(day)
        out = {}
        for v, i in self.vid.items():
            m = self.var[: self.n] == i
            out[v] = np.bincount(self.agent[: self.n][m], weights=c[m], minlength=n_agents)
        return out

    def prune(self, day: int, eps: float = 0.004):
        c = self.contributions(day)
        future = self.start[: self.n] > day
        keep = (np.abs(c) >= eps) | future
        k = int(keep.sum())
        for name in ("agent", "var", "mag", "start", "hl", "event"):
            arr = getattr(self, name)
            arr[:k] = arr[: self.n][keep]
        self.n = k

    def for_agent(self, i: int, day: int):
        m = self.agent[: self.n] == i
        c = self.contributions(day)[m]
        return [{"var": self.var_names[v], "now": float(x), "mag": float(g), "start": int(s), "half_life": float(h),
                 "event": int(e)} for v, x, g, s, h, e in zip(self.var[: self.n][m], c, self.mag[: self.n][m],
                                                               self.start[: self.n][m], self.hl[: self.n][m],
                                                               self.event[: self.n][m])]
