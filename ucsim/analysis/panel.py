"""Longitudinal analysis: separating within-person change from between-person differences.

Cross-sectional correlations ("lonely people have fewer friends") cannot say which way influence runs.
Panel data can: does *a change* in X for a person predict *their* later change in Y, and vice versa? This
module runs the same estimators on simulated panels (the History snapshots, every two weeks) that one would
run on a real multi-wave survey, so the model is ready to be confronted with longitudinal evidence:

* **between-person** association: correlation of people's average X and average Y;
* **within-person cross-lagged effects** (the logic of the random-intercept cross-lagged panel model,
  Hamaker, Kuiper & Grasman 2015): center each person's series on their own mean, then regress
  Y(t+1) on X(t) controlling for Y(t), and the reverse, on standardized within-person deviations.

When real panel waves arrive, put them in the same shape (person × wave × variable) and call
``cross_lagged`` on them; ``compare`` lines simulated and observed coefficients up.
"""
from __future__ import annotations

import numpy as np

# pairs worth tracking in both directions (X, Y)
PAIRS = [("n_close_friends", "loneliness"), ("loneliness", "dates_30d"), ("attend_rate", "faith_belief"),
         ("stress", "dates_30d"), ("perceived_support", "loneliness"), ("loneliness", "expect_social"),
         ("financial_stress", "stress"), ("social_events_month", "loneliness")]


def panel(sim, variables: list[str], min_waves: int = 6, lag_days: int = 28) -> tuple[np.ndarray, dict[str, np.ndarray]]:
    """Waves spaced ~lag_days apart from the History snapshots; people present in every used wave."""
    hist = sim.systems["history"]
    snaps = hist.snaps
    if not snaps:
        return np.zeros(0, int), {}
    step = max(1, int(round(lag_days / hist.every)))
    use = snaps[::step]
    if len(use) < min_waves:
        use = snaps
    n0 = min(s["n"] for s in use)
    present = np.ones(n0, bool)
    for s in use:
        present &= s["present"][:n0]
    ids = np.where(present)[0]
    data = {}
    for v in variables:
        if not all(v in s for s in use):
            continue
        data[v] = np.stack([s[v][:n0][ids].astype(np.float64) for s in use])   # waves × people
    return ids, data


def _within(x: np.ndarray) -> np.ndarray:
    d = x - np.nanmean(x, axis=0, keepdims=True)
    sd = np.nanstd(d)
    return d / sd if sd > 0 else d


def cross_lagged(X: np.ndarray, Y: np.ndarray) -> dict:
    """Within-person standardized lagged effects X→Y and Y→X (each controlling the outcome's own lag), and the
    between-person correlation of person means. X, Y: waves × people."""
    out = {"waves": int(X.shape[0]), "people": int(X.shape[1])}
    mx, my = np.nanmean(X, axis=0), np.nanmean(Y, axis=0)
    ok = np.isfinite(mx) & np.isfinite(my)
    out["between_r"] = float(np.corrcoef(mx[ok], my[ok])[0, 1]) if ok.sum() > 10 and mx[ok].std() > 0 and my[ok].std() > 0 else float("nan")
    wx, wy = _within(X), _within(Y)

    def lagged(src, dst):
        a = src[:-1].ravel()
        y0 = dst[:-1].ravel()
        y1 = dst[1:].ravel()
        m = np.isfinite(a) & np.isfinite(y0) & np.isfinite(y1)
        if m.sum() < 30:
            return float("nan")
        A = np.c_[np.ones(m.sum()), a[m], y0[m]]
        beta, *_ = np.linalg.lstsq(A, y1[m], rcond=None)
        return float(beta[1])

    out["x_to_y"] = lagged(wx, wy)
    out["y_to_x"] = lagged(wy, wx)
    out["cross_sectional_r"] = float(np.nanmean([np.corrcoef(X[t], Y[t])[0, 1] for t in range(X.shape[0])
                                                 if np.nanstd(X[t]) > 0 and np.nanstd(Y[t]) > 0]))
    return out


def report(sim, pairs=PAIRS, lag_days: int = 28) -> list[dict]:
    vars_ = sorted({v for p in pairs for v in p})
    ids, data = panel(sim, vars_, lag_days=lag_days)
    rows = []
    for x, y in pairs:
        if x in data and y in data:
            r = cross_lagged(data[x], data[y])
            rows.append({"x": x, "y": y, **{k: (round(v, 3) if isinstance(v, float) and np.isfinite(v) else v) for k, v in r.items()}})
    return rows


def compare(simulated: list[dict], observed: list[dict]) -> list[dict]:
    """Line up simulated and observed coefficients for the same (x, y) pairs (observed from a real panel)."""
    obs = {(o["x"], o["y"]): o for o in observed}
    out = []
    for s in simulated:
        o = obs.get((s["x"], s["y"]))
        if o:
            out.append({"x": s["x"], "y": s["y"], **{f"sim_{k}": s.get(k) for k in ("between_r", "x_to_y", "y_to_x")},
                        **{f"obs_{k}": o.get(k) for k in ("between_r", "x_to_y", "y_to_x")}})
    return out
