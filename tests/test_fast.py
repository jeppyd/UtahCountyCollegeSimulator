"""Compiled kernels (engine/fast.py) give exactly what the NumPy versions give; date types are picked as before."""
import numpy as np

from ucsim.engine import fast


def _graph(n=3000, m=12000, seed=0):
    rng = np.random.default_rng(seed)
    a, b = rng.integers(0, n, m), rng.integers(0, n, m)
    ok = a != b
    a, b = a[ok], b[ok]
    src, dst = np.r_[a, b], np.r_[b, a]
    wt = np.round(rng.random(len(a)), 2)              # coarse weights: many exact ties to break the same way
    wt = np.r_[wt, wt]
    o = np.argsort(src, kind="stable")
    return n, src[o], dst[o], wt[o]


def test_label_propagation_matches_numpy():
    n, src, dst, wt = _graph()
    lab0 = np.arange(n, dtype=np.int64)
    ref = fast._label_propagation_numpy(n, src, dst, wt, lab0, 6, 0.5)
    got = fast.label_propagation(n, src, dst, wt, lab0, iters=6, self_w=0.5)
    assert np.array_equal(ref, got)
    assert len(np.unique(got)) < n                     # it found groups


def test_date_type_matches_one_pair_at_a_time(ran):
    from ucsim.engine.systems.romance import DATE_TYPES
    R = ran.systems["romance"]
    P = ran.w.P
    a, b = np.arange(0, 60), np.arange(60, 120)
    got = R._date_type(a, b)
    rng = ran.streams.gen("date_type", ran.w.day)
    winter = ran.w.env["temp_f"] < 45
    ref = []
    for x, y in zip(a, b):                             # the previous implementation
        sc = []
        for t in DATE_TYPES:
            c = f"fd_{t}"
            v = (P[c][x] + P[c][y]) / 2 if c in P.cols else 2.5
            if winter and t in ("hike", "picnic", "stargazing", "pickleball"):
                v -= 1.5
            sc.append(v)
        sc = np.array(sc) + rng.gumbel(size=len(sc)) * 0.8
        ref.append(DATE_TYPES[int(np.argmax(sc))])
    assert got == ref
