"""Columnar (entity-component) state stores.

Agents are integer ids; each registered person variable is one NumPy column.
`PersonTable` grows by doubling, so arrivals (freshmen, returning missionaries)
append without reallocating every time.  Internal engine-only columns live in
`internal` and are not exposed to the UI.
"""
from __future__ import annotations

import numpy as np

from ..registry import Registry, VarSpec


class PersonTable:
    def __init__(self, registry: Registry, capacity: int = 1024):
        self.reg = registry
        self.specs: dict[str, VarSpec] = {v.id: v for v in registry.person_vars()}
        self.n = 0
        self.cap = max(16, capacity)
        self.cols: dict[str, np.ndarray] = {
            k: np.full(self.cap, s.default_fill(), dtype=s.np_dtype) for k, s in self.specs.items()}
        self.internal: dict[str, np.ndarray] = {}
        self._internal_fill: dict[str, object] = {}
        self._cat_index = {k: {c: i for i, c in enumerate(s.categories)}
                           for k, s in self.specs.items() if s.dtype == "cat"}

    # ------------------------------------------------------------------ access
    def __getitem__(self, key: str) -> np.ndarray:
        if key in self.cols:
            return self.cols[key][: self.n]
        return self.internal[key][: self.n]

    def __setitem__(self, key: str, value):
        if key in self.cols:
            self.cols[key][: self.n] = value
        elif key in self.internal:
            self.internal[key][: self.n] = value
        else:
            raise KeyError(key)

    def __contains__(self, key):
        return key in self.cols or key in self.internal

    def add_internal(self, key: str, dtype=np.float32, fill=0, shape: tuple = ()):
        """An engine-only column; `shape` adds trailing dimensions (e.g. (7,) for one value per weekday)."""
        if key not in self.internal:
            self.internal[key] = np.full((self.cap, *shape), fill, dtype=dtype)
            self._internal_fill[key] = fill

    def code(self, var: str, label: str) -> int:
        return self._cat_index[var][label]

    def codes(self, var: str, labels) -> np.ndarray:
        idx = self._cat_index[var]
        return np.array([idx[l] for l in labels], dtype=np.uint8)

    def labels(self, var: str, codes=None) -> np.ndarray:
        cats = np.array(self.specs[var].categories, dtype=object)
        c = self[var] if codes is None else codes
        return cats[c]

    def is_(self, var: str, label: str) -> np.ndarray:
        return self[var] == self._cat_index[var][label]

    def isin(self, var: str, labels) -> np.ndarray:
        return np.isin(self[var], [self._cat_index[var][l] for l in labels])

    # ------------------------------------------------------------------ growth
    def allocate(self, k: int) -> np.ndarray:
        """Append k agents (default-filled); returns their ids."""
        if self.n + k > self.cap:
            new_cap = max(self.cap * 2, self.n + k + 16)
            for store in (self.cols, self.internal):
                for key, arr in store.items():
                    fill = self.specs[key].default_fill() if key in self.specs else self._internal_fill.get(key, 0)
                    grown = np.full((new_cap, *arr.shape[1:]), fill, dtype=arr.dtype)
                    grown[: self.cap] = arr
                    store[key] = grown
            self.cap = new_cap
        ids = np.arange(self.n, self.n + k)
        self.n += k
        return ids

    def snapshot(self, columns: list[str] | None = None) -> dict[str, np.ndarray]:
        cols = columns or list(self.cols)
        return {c: self[c].copy() for c in cols}


class EdgeStore:
    """Sparse undirected relationship store keyed by (lo, hi) pairs.

    Keys are int64 (lo << 32 | hi) kept sorted; attribute columns are parallel arrays.
    Batched upserts use searchsorted, so a day's interactions are applied in one pass.
    """

    # bel_lh: what lo *believes* hi's attraction to lo is (and bel_hl the reverse) — perceived, not actual.
    # disclosure: how much each has let the other see (self-disclosure / intimacy); support: help given and
    # received in hard times; hurt: unrepaired injury (betrayal, conflict) that fades slowly with repair.
    FLOAT_COLS = ("liking", "closeness", "trust", "conflict", "att_lh", "att_hl", "hours", "hours_leisure",
                  "chemistry", "bel_lh", "bel_hl", "disclosure", "support", "hurt")
    INT_COLS = {"n_inter": np.int32, "first_day": np.int32, "last_day": np.int32, "stage": np.uint8,
                "flags": np.uint32, "origin_ctx": np.uint8, "origin_place": np.int32, "introducer": np.int32,
                "dates": np.int16, "shared": np.int16}

    def __init__(self, capacity: int = 1 << 16):
        self.n = 0
        self.cap = capacity
        self.keys = np.empty(0, dtype=np.int64)
        self.cols: dict[str, np.ndarray] = {}
        for c in self.FLOAT_COLS:
            self.cols[c] = np.zeros(capacity, dtype=np.float32)
        for c, dt in self.INT_COLS.items():
            self.cols[c] = np.zeros(capacity, dtype=dt)
        self.cols["introducer"][:] = -1
        self.cols["origin_place"][:] = -1
        self._keys_buf = np.zeros(capacity, dtype=np.int64)

    @staticmethod
    def make_keys(a: np.ndarray, b: np.ndarray) -> np.ndarray:
        lo = np.minimum(a, b).astype(np.int64)
        hi = np.maximum(a, b).astype(np.int64)
        return (lo << 32) | hi

    @staticmethod
    def split(keys: np.ndarray):
        return (keys >> 32).astype(np.int64), (keys & 0xFFFFFFFF).astype(np.int64)

    def __len__(self):
        return self.n

    def __getitem__(self, c):
        return self.cols[c][: self.n]

    def find(self, keys: np.ndarray) -> np.ndarray:
        """Index of each key, or -1."""
        if self.n == 0 or len(keys) == 0:
            return np.full(len(keys), -1, dtype=np.int64)
        k = self._keys_buf[: self.n]
        pos = np.searchsorted(k, keys)
        pos_c = np.minimum(pos, self.n - 1)
        hit = k[pos_c] == keys
        return np.where(hit, pos_c, -1)

    def upsert(self, keys: np.ndarray, init: dict | None = None) -> np.ndarray:
        """Ensure keys exist (inserting new ones with `init` values); return their indices."""
        keys = np.asarray(keys, dtype=np.int64)
        idx = self.find(keys)
        missing = idx < 0
        if missing.any():
            new_keys, first = np.unique(keys[missing], return_index=True)
            self._insert(new_keys, {c: (v[missing][first] if isinstance(v, np.ndarray) else v)
                                    for c, v in (init or {}).items()})
            idx = self.find(keys)
        return idx

    def _insert(self, new_keys: np.ndarray, init: dict):
        """Insert keys that must be unique and absent (callers go through upsert or filter first)."""
        m = len(new_keys)
        if self.n + m > self.cap:
            new_cap = max(self.cap * 2, self.n + m + 1024)
            for c, arr in self.cols.items():
                g = np.zeros(new_cap, dtype=arr.dtype)
                if c in ("introducer", "origin_place"):
                    g[:] = -1
                g[: self.cap] = arr
                self.cols[c] = g
            kb = np.zeros(new_cap, dtype=np.int64)
            kb[: self.cap] = self._keys_buf
            self._keys_buf = kb
            self.cap = new_cap
        # both runs are sorted, so merge in O(n): new key j lands at searchsorted(old, key_j) + j
        old = self._keys_buf[: self.n]
        total = self.n + m
        pos_new = np.searchsorted(old, new_keys) + np.arange(m)
        is_new = np.zeros(total, bool)
        is_new[pos_new] = True
        keys = np.empty(total, np.int64)
        keys[pos_new] = new_keys
        keys[~is_new] = old
        self._keys_buf[:total] = keys
        for c, arr in self.cols.items():
            vals = np.zeros(m, dtype=arr.dtype)
            if c in ("introducer", "origin_place"):
                vals[:] = -1
            if c in init:
                vals[:] = init[c]
            merged = np.empty(total, arr.dtype)
            merged[pos_new] = vals
            merged[~is_new] = arr[: self.n]
            arr[:total] = merged
        self.n = total

    def remove(self, mask_remove: np.ndarray):
        keep = ~mask_remove[: self.n]
        k = int(keep.sum())
        self._keys_buf[:k] = self._keys_buf[: self.n][keep]
        for c, arr in self.cols.items():
            arr[:k] = arr[: self.n][keep]
        self.n = k

    @property
    def key_array(self):
        return self._keys_buf[: self.n]

    def endpoints(self):
        return self.split(self.key_array)

    def attraction_from(self, idx: np.ndarray, src: np.ndarray) -> np.ndarray:
        """Directed attraction of `src` toward the other endpoint, for edge indices idx."""
        lo, _ = self.split(self._keys_buf[idx])
        return np.where(src == lo, self.cols["att_lh"][idx], self.cols["att_hl"][idx])

    def set_attraction_from(self, idx: np.ndarray, src: np.ndarray, val: np.ndarray):
        lo, _ = self.split(self._keys_buf[idx])
        is_lo = src == lo
        self.cols["att_lh"][idx[is_lo]] = val[is_lo]
        self.cols["att_hl"][idx[~is_lo]] = val[~is_lo]

    def belief_from(self, idx: np.ndarray, src: np.ndarray) -> np.ndarray:
        """What `src` believes the other endpoint's attraction toward `src` is."""
        lo, _ = self.split(self._keys_buf[idx])
        return np.where(src == lo, self.cols["bel_lh"][idx], self.cols["bel_hl"][idx])

    def set_belief_from(self, idx: np.ndarray, src: np.ndarray, val: np.ndarray):
        lo, _ = self.split(self._keys_buf[idx])
        is_lo = src == lo
        self.cols["bel_lh"][idx[is_lo]] = val[is_lo]
        self.cols["bel_hl"][idx[~is_lo]] = val[~is_lo]

    def csr(self, mask: np.ndarray | None, n_nodes: int, weight: str | None = None):
        """Symmetric CSR adjacency of the selected edges (indptr, neighbors, edge_idx)."""
        sel = np.arange(self.n) if mask is None else np.where(mask[: self.n])[0]
        lo, hi = self.split(self._keys_buf[sel])
        src = np.concatenate([lo, hi])
        dst = np.concatenate([hi, lo])
        eidx = np.concatenate([sel, sel])
        order = np.argsort(src, kind="stable")
        src, dst, eidx = src[order], dst[order], eidx[order]
        indptr = np.zeros(n_nodes + 1, dtype=np.int64)
        np.add.at(indptr, src + 1, 1)
        indptr = np.cumsum(indptr)
        return indptr, dst, eidx


# Tie-type bit flags
class Tie:
    ROOMMATE = 1 << 0
    CLASSMATE = 1 << 1
    COWORKER = 1 << 2
    WARD = 1 << 3
    FHE = 1 << 4
    FAMILY = 1 << 5
    DATED = 1 << 6
    ROMANTIC = 1 << 7
    EX = 1 << 8
    SPOUSE = 1 << 9
    KISSED = 1 << 10
    NCMO = 1 << 11
    SEXUAL = 1 << 12
    APP_MATCH = 1 << 13
    INTRODUCED = 1 << 14
    NEIGHBOR = 1 << 15
    PREEXISTING = 1 << 16
    CLUBMATE = 1 << 17
    TEAMMATE = 1 << 18
    INSTITUTE = 1 << 19
    CONGREGATION = 1 << 20

    NAMES = {1 << 0: "roommate", 1 << 1: "classmate", 1 << 2: "coworker", 1 << 3: "ward", 1 << 4: "fhe",
             1 << 5: "family", 1 << 6: "dated", 1 << 7: "romantic", 1 << 8: "ex", 1 << 9: "spouse",
             1 << 10: "kissed", 1 << 11: "ncmo", 1 << 12: "sexual", 1 << 13: "app_match", 1 << 14: "introduced",
             1 << 15: "neighbor", 1 << 16: "preexisting", 1 << 17: "clubmate", 1 << 18: "teammate",
             1 << 19: "institute", 1 << 20: "congregation"}

    @classmethod
    def decode(cls, flags: int) -> list[str]:
        return [n for b, n in cls.NAMES.items() if flags & b]


# Context types (where interactions happen)
CTX = ["unit", "complex", "class", "ward", "fhe", "work", "gym", "venue", "gathering", "campus", "app", "date",
       "family", "preexisting", "dance", "outdoors", "hangout", "online", "club", "team", "institute",
       "congregation", "occasion"]   # append only: codes are stored on edges (origin_ctx)
CTX_ID = {c: i for i, c in enumerate(CTX)}
