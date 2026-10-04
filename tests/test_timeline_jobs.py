"""Running time while the pages read: a run must not lock pages out until it ends, two clicks must not start two
runs, a pause must stop it, and an error must stop it visibly."""
import threading
import time

import pytest
from fastapi.testclient import TestClient

from ucsim.api import server
from ucsim.engine.runner import fork, new_simulation


def test_fair_lock_serves_waiters_between_turns():
    lock = server.FairLock()
    order, stop = [], threading.Event()

    def runner():   # re-takes the lock immediately, like a run stepping day after day
        while not stop.is_set():
            with lock:
                order.append("day")
                time.sleep(0.01)

    t = threading.Thread(target=runner, daemon=True)
    t.start()
    time.sleep(0.03)
    t0 = time.time()
    with lock:
        waited = time.time() - t0
        with lock:   # re-entrant
            order.append("reader")
    stop.set()
    t.join(2)
    assert waited < 0.5 and "reader" in order


@pytest.fixture()
def ws():
    """A fresh workspace with a tiny paired world, restored afterwards."""
    saved = (server.WS.base, server.WS.alt, server.WS.divergence, server.WS.job, server.WS.last_job)
    base = new_simulation(scale=0.02, seed=5)
    base.run_days(2)
    server.WS.base, server.WS.alt = base, fork(base, [{"preset": "rent_up_20"}])
    server.WS.divergence, server.WS.job, server.WS.last_job = [], {"state": "idle"}, None
    yield server.WS
    server.WS.job["cancel"] = True
    for _ in range(200):
        if not server.WS.busy():
            break
        time.sleep(0.05)
    server.WS.base, server.WS.alt, server.WS.divergence, server.WS.job, server.WS.last_job = saved


def wait_idle(ws, limit=60):
    t0 = time.time()
    while ws.busy() and time.time() - t0 < limit:
        time.sleep(0.05)
    assert not ws.busy()


def test_pages_answer_while_both_worlds_run(ws):
    c = TestClient(server.app)
    assert c.post("/api/step", json={"days": 40, "pace": 0.05}).status_code == 200
    assert c.post("/api/step", json={"days": 5}).status_code == 409          # a second click can't start a second run
    time.sleep(0.2)
    t0 = time.time()
    r = c.get("/api/compare/fields")
    took = time.time() - t0
    s = c.get("/api/status").json()
    assert r.status_code == 200 and s["job"]["state"] == "running"
    assert took < 1.5 and s["job"]["progress"] < 40                             # answered mid-run, not after it
    assert c.post("/api/cancel").json()["ok"]
    wait_idle(ws)
    s = c.get("/api/status").json()
    assert s["job"]["state"] == "idle" and s["last_job"]["reason"] == "paused" and s["last_job"]["progress"] < 40


def test_a_run_that_breaks_stops_visibly(ws, monkeypatch):
    c = TestClient(server.app)
    day = ws.base.w.day

    def boom():
        raise ValueError("synthetic failure")
    monkeypatch.setattr(ws.alt, "step_day", boom)
    assert c.post("/api/step", json={"days": 3}).status_code == 200
    wait_idle(ws)
    s = c.get("/api/status").json()
    assert s["job"]["state"] == "error" and "What-if" in s["job"]["error"] and s["last_job"]["reason"] == "error"
    assert ws.base.w.day == day + 1
    monkeypatch.undo()
    # the workspace is usable again: a new run starts and the lock is free
    assert c.post("/api/step", json={"days": 1}).status_code == 200
    wait_idle(ws)
    assert ws.alt.w.day == ws.base.w.day == day + 2                              # the What-if caught up
    assert c.get("/api/compare/people?k=3").status_code == 200
