"""Samplers that turn the committed aggregate priors into synthetic attributes.

* `CPT` – sequential conditional probability tables with back-off, plus a calibration
  tilt (multiplicative odds on chosen levels) to hit external targets.
* `NumCPT` – conditional quantile tables (inverse-CDF sampling).
* `Copula` – Gaussian-copula conditional sampler: given whatever block variables the
  agent already has (bridge variables), draw the rest from the conditional normal.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import numpy as np
from scipy.special import ndtr, ndtri

PRIORS = Path(__file__).resolve().parents[1] / "priors" / "survey_priors.json"


@lru_cache(maxsize=1)
def load_priors() -> dict:
    return json.loads(PRIORS.read_text())


class CPT:
    def __init__(self, spec: dict):
        self.levels = spec["levels"]
        self.given = spec["given"]
        self.table = {k: np.asarray(v, dtype=float) for k, v in spec["table"].items()}

    def probs(self, keys: list) -> np.ndarray:
        """Most specific available distribution for a tuple of conditioning values."""
        for depth in range(len(keys), -1, -1):
            k = "|".join(str(x) for x in keys[:depth])
            if k in self.table:
                return self.table[k]
        return self.table[""]

    def sample(self, rng: np.random.Generator, cond: dict[str, np.ndarray], n: int,
               tilt: dict | None = None) -> np.ndarray:
        """Vectorized by unique conditioning combination. Returns level *indices*."""
        out = np.empty(n, dtype=np.int64)
        if self.given:
            stacked = np.stack([np.asarray(cond[g]).astype(str) for g in self.given], axis=1)
            uniq, inv = np.unique(stacked, axis=0, return_inverse=True)
            inv = inv.ravel()
        else:
            uniq, inv = np.array([[]]), np.zeros(n, dtype=np.int64)
        for u in range(len(uniq)):
            idx = np.where(inv == u)[0]
            p = self.probs(list(uniq[u])).copy()
            if tilt:
                for lvl, mult in tilt.items():
                    p[self.levels.index(lvl)] *= mult
            p = p / p.sum()
            out[idx] = rng.choice(len(p), size=len(idx), p=p)
        return out


class NumCPT:
    def __init__(self, spec: dict):
        self.given = spec["given"]
        self.q = np.asarray(spec["qgrid"])
        self.table = {k: np.asarray(v, dtype=float) for k, v in spec["table"].items() if v}

    def sample(self, rng, cond: dict[str, np.ndarray], n: int) -> np.ndarray:
        out = np.empty(n)
        stacked = np.stack([np.asarray(cond[g]).astype(str) for g in self.given], axis=1)
        uniq, inv = np.unique(stacked, axis=0, return_inverse=True)
        inv = inv.ravel()
        for u in range(len(uniq)):
            idx = np.where(inv == u)[0]
            keys = list(uniq[u])
            vals = None
            for depth in range(len(keys), -1, -1):
                k = "|".join(keys[:depth])
                if k in self.table:
                    vals = self.table[k]
                    break
            uu = rng.uniform(self.q[0], self.q[-1], size=len(idx))
            out[idx] = np.interp(uu, self.q, vals)
        return out


class Copula:
    """Gaussian copula over one survey block with sex-specific marginals."""

    def __init__(self, block: dict):
        self.name = block["name"]
        self.vars = block["variables"]
        self.idx = {v: i for i, v in enumerate(self.vars)}
        self.R = np.asarray(block["corr"], dtype=float)
        self.marg = block["marginals"]
        self.qgrid = np.round(np.linspace(0.01, 0.99, 99), 4)

    # ---- marginal transforms
    def _cdf_bounds(self, var: str, sex: str, x: np.ndarray):
        """CDF interval [F(x-), F(x)] for observed values (vectorized)."""
        m = self.marg[var]
        spec = m[sex]
        if m["kind"] == "num":
            q = np.asarray(spec)
            lo = np.searchsorted(q, x, side="left") / (len(q) + 1)
            hi = np.searchsorted(q, x, side="right") / (len(q) + 1)
            lo = np.clip(lo, 0.0, 0.999)
            hi = np.clip(np.maximum(hi, lo + 1e-3), 0.001, 1.0)
            return lo, hi
        p = np.asarray(spec)
        cdf = np.concatenate([[0.0], np.cumsum(p)])
        xi = np.clip(np.round(x).astype(int), 0, len(p) - 1)
        return cdf[xi], cdf[xi + 1]

    def _inverse(self, var: str, sex: str, u: np.ndarray) -> np.ndarray:
        m = self.marg[var]
        spec = m[sex]
        if m["kind"] == "num":
            q = np.asarray(spec)
            grid = np.arange(1, len(q) + 1) / (len(q) + 1)
            return np.interp(u, grid, q)
        cdf = np.cumsum(np.asarray(spec))
        return np.minimum(np.searchsorted(cdf, u * cdf[-1], side="right"), len(cdf) - 1).astype(float)

    def sample(self, rng: np.random.Generator, sex: np.ndarray, known: dict[str, np.ndarray],
               want: list[str]) -> dict[str, np.ndarray]:
        """Draw `want` variables conditional on `known` (NaN entries treated as unknown per agent)."""
        n = len(sex)
        want = [w for w in want if w in self.idx]
        out = {w: np.full(n, np.nan) for w in want}
        kvars = [k for k in known if k in self.idx]
        sexes = np.where(np.asarray(sex) == "M", "M", "F")
        # latent z for known values, per agent (NaN = missing)
        zk = np.full((n, len(kvars)), np.nan)
        for j, k in enumerate(kvars):
            x = np.asarray(known[k], dtype=float)
            ok = np.isfinite(x)
            for s in ("M", "F"):
                sel = ok & (sexes == s)
                if not sel.any():
                    continue
                lo, hi = self._cdf_bounds(k, s, x[sel])
                u = rng.uniform(lo, hi)
                zk[sel, j] = ndtri(np.clip(u, 1e-4, 1 - 1e-4))
        # group agents by missingness pattern of known vars to share the conditional algebra
        pattern = np.isfinite(zk)
        keys, inv = np.unique(pattern, axis=0, return_inverse=True)
        inv = inv.ravel()
        wi = [self.idx[w] for w in want]
        for g in range(len(keys)):
            rows = np.where(inv == g)[0]
            kmask = keys[g]
            ki = [self.idx[kvars[j]] for j in range(len(kvars)) if kmask[j]]
            if ki:
                S_kk = self.R[np.ix_(ki, ki)]
                S_wk = self.R[np.ix_(wi, ki)]
                S_ww = self.R[np.ix_(wi, wi)]
                A = np.linalg.solve(S_kk + 1e-6 * np.eye(len(ki)), S_wk.T).T
                mu = zk[np.ix_(rows, np.where(kmask)[0])] @ A.T
                cov = S_ww - A @ S_wk.T
            else:
                mu = np.zeros((len(rows), len(wi)))
                cov = self.R[np.ix_(wi, wi)]
            cov = (cov + cov.T) / 2
            w_, v_ = np.linalg.eigh(cov)
            L = v_ * np.sqrt(np.clip(w_, 1e-8, None))
            z = mu + rng.standard_normal((len(rows), len(wi))) @ L.T
            u = ndtr(z)
            for c, w in enumerate(want):
                for s in ("M", "F"):
                    sel = sexes[rows] == s
                    if sel.any():
                        out[w][rows[sel]] = self._inverse(w, s, u[sel, c])
        return out


@lru_cache(maxsize=1)
def copulas() -> dict[str, Copula]:
    pri = load_priors()
    return {k: Copula(b) for k, b in pri["blocks"].items()}


@lru_cache(maxsize=1)
def skeleton() -> dict:
    pri = load_priors()["skeleton"]
    out = {}
    for k, v in pri.items():
        out[k] = NumCPT(v) if "qgrid" in v else CPT(v)
    return out
