"""Compiled kernels for the few loops NumPy can't express well, with pure-NumPy fallbacks that give identical results.

Numba is optional (`pip install numba`, or `pip install .[fast]`): when it is installed these kernels are compiled on
first use (and cached on disk where the package folder is writable); without it the NumPy versions run. Set
UCSIM_NUMBA=0 to force the NumPy versions. `tests/test_fast.py` checks both give the same answers.
"""
from __future__ import annotations

import os
import sys

import numpy as np

HAVE_NUMBA = False
if os.environ.get("UCSIM_NUMBA", "1").strip() not in ("0", "false", "off"):
    try:
        import numba
        HAVE_NUMBA = True
    except Exception:  # noqa: BLE001  (not installed, or a broken install: fall back to NumPy)
        HAVE_NUMBA = False


# ----------------------------------------------------------------------------- label propagation
def _label_propagation_numpy(n, src, dst, wt, lab, iters, self_w):
    lab = lab.copy()
    for _ in range(iters):
        s = np.r_[src, np.arange(n)]
        l_ = np.r_[lab[dst], lab]
        ww = np.r_[wt, np.full(n, self_w)]
        key, inv = np.unique(s * n + l_, return_inverse=True)
        tot = np.bincount(inv.ravel(), weights=ww)
        node, cand = key // n, key % n
        order = np.lexsort((cand, -tot, node))
        first = np.unique(node[order], return_index=True)[1]
        lab[node[order][first]] = cand[order][first]
    return lab


# compiled code is cached next to this file when it can be (not inside a packaged app, nor a read-only install)
_CACHE = not getattr(sys, "frozen", False) and os.access(os.path.dirname(os.path.abspath(__file__)), os.W_OK)

if HAVE_NUMBA:
    @numba.njit(cache=_CACHE, nogil=True)
    def _lp_kernel(n, start, dst, wt, lab, iters, self_w):  # pragma: no cover  (compiled)
        acc = np.zeros(n)
        mark = np.zeros(n, np.bool_)
        maxdeg = 0
        for u in range(n):
            maxdeg = max(maxdeg, start[u + 1] - start[u])
        touched = np.empty(maxdeg + 1, np.int64)
        cur = lab.copy()
        for _ in range(iters):
            new = cur.copy()
            for u in range(n):
                k = 0
                for e in range(start[u], start[u + 1]):        # neighbours in edge order, then the node itself:
                    lb = cur[dst[e]]                            # the same summation order as the NumPy version
                    if not mark[lb]:
                        mark[lb] = True
                        touched[k] = lb
                        k += 1
                    acc[lb] += wt[e]
                lb = cur[u]
                if not mark[lb]:
                    mark[lb] = True
                    touched[k] = lb
                    k += 1
                acc[lb] += self_w
                best, bw = -1, -np.inf
                for i in range(k):
                    lb = touched[i]
                    v = acc[lb]
                    if v > bw or (v == bw and lb < best):        # the heaviest label; ties to the smaller label
                        bw, best = v, lb
                    acc[lb] = 0.0
                    mark[lb] = False
                new[u] = best
            cur = new
        return cur


def label_propagation(n: int, src: np.ndarray, dst: np.ndarray, wt: np.ndarray, lab: np.ndarray, iters: int = 6,
                      self_w: float = 0.5) -> np.ndarray:
    """Synchronous weighted label propagation: each node takes the label with the most weight among its neighbours'
    labels and its own (weight self_w), ties to the smaller label. `src` must be sorted (edges grouped by node)."""
    src = np.asarray(src, np.int64)
    dst = np.asarray(dst, np.int64)
    wt = np.asarray(wt, np.float64)
    lab = np.asarray(lab, np.int64)
    if HAVE_NUMBA:
        start = np.zeros(n + 1, np.int64)
        np.cumsum(np.bincount(src, minlength=n), out=start[1:])
        return _lp_kernel(n, start, dst, wt, lab, iters, float(self_w))
    return _label_propagation_numpy(n, src, dst, wt, lab, iters, self_w)
