"""The What-if on a second core (api/parallel.py): stepping it in a worker process gives exactly the same worlds as
stepping both in one process; pages see a recent copy; a change mid-run takes the live What-if back."""
import copy
import hashlib

import numpy as np
import pytest

from ucsim.api import parallel
from ucsim.api.server import Workspace
from ucsim.engine import runner


def _digest(sim) -> str:
    h = hashlib.sha1()
    for c in ("mood", "loneliness", "rel_status", "unit_id", "n_friends", "attend_rate", "partner_id"):
        h.update(np.ascontiguousarray(sim.w.P[c]).tobytes())
    L = sim.log
    for c in ("type", "a", "b", "day"):
        h.update(L.cols[c][: L.n].tobytes())
    h.update(sim.w.E.key_array.tobytes())
    return h.hexdigest()


@pytest.fixture(scope="module")
def pair():
    base = runner.new_simulation(scale=0.02, seed=21)
    base.run_days(2)
    alt = runner.fork(base, [{"preset": "rent_up_20"}])
    return base, alt


def _ws(base, alt):
    ws = Workspace()
    ws.base, ws.alt = copy.deepcopy(base), copy.deepcopy(alt)
    ws.job = {"state": "running", "total": 8}
    return ws


def test_parallel_matches_serial(pair, monkeypatch):
    base, alt = pair
    monkeypatch.setenv("UCSIM_PARALLEL", "0")
    serial = _ws(base, alt)
    serial.step(days=8)
    monkeypatch.setenv("UCSIM_PARALLEL", "force")
    par = _ws(base, alt)
    try:
        par.step(days=8)
        assert par._par is not None and not par._par_on            # used the worker, and the What-if came back
        assert par.alt.w.day == serial.alt.w.day == par.base.w.day
        assert _digest(par.alt) == _digest(serial.alt)
        assert _digest(par.base) == _digest(serial.base)
        assert par.divergence                                       # measured when the What-if came back
    finally:
        if par._par is not None:
            par._par.close()


def test_take_alt_mid_run(pair, monkeypatch):
    base, alt = pair
    monkeypatch.setenv("UCSIM_PARALLEL", "1")
    ws = _ws(base, alt)
    try:
        ws._par_start()
        for _ in range(2):                                          # two days on the second core
            ws._par.step_async(ws.base.w.day + 1)
            ws.base.step_day()
            ws._par.wait()
        assert ws._par_on and ws.alt.w.day == base.w.day           # the pages' copy is from the hand-over
        live = ws.take_alt()
        assert not ws._par_on and live.w.day == ws.base.w.day       # the live What-if is back, up to date
        assert ws.alt is live and ws._par_cool == parallel.COOLDOWN_DAYS
    finally:
        ws._par.close()


def test_when_the_hand_over_pays_off(monkeypatch):
    monkeypatch.setenv("UCSIM_PARALLEL", "0")
    assert not parallel.enabled()
    monkeypatch.setenv("UCSIM_PARALLEL", "1")
    assert parallel.enabled()
    assert not parallel.worth_it(parallel.MIN_DAYS - 1, 2.0, 0.5)          # too short
    assert not parallel.worth_it(10, None, None) and parallel.worth_it(365, None, None)   # unmeasured: long runs only
    assert parallel.worth_it(7, 1.8, 1.0) and not parallel.worth_it(7, 1.8, 8.0)   # a fast vs a slow hand-over
