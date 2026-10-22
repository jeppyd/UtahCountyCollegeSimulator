"""Speed and logs: every simulated day is timed (overall and per system, both worlds), slow days say why, the logbook
keeps what happened, the debug bundle holds settings and timings but no people, and the per-computer estimate is
built from measured worlds."""
import io
import json
import time
import zipfile

import pytest
from fastapi.testclient import TestClient

from ucsim import telemetry
from ucsim.api import server
from ucsim.engine.runner import fork, new_simulation


@pytest.fixture()
def ws(tmp_path):
    saved = (server.WS.base, server.WS.alt, server.WS.divergence, server.WS.job, server.WS.last_job, telemetry.TELEMETRY.history_file)
    base = new_simulation(scale=0.02, seed=5)
    base.run_days(1)
    server.WS.base, server.WS.alt = base, fork(base, [{"preset": "rent_up_20"}])
    server.WS.divergence, server.WS.job, server.WS.last_job = [], {"state": "idle"}, None
    telemetry.TELEMETRY.new_world(0.02, 5, int(base.w.P.n), 1.0, 0)
    telemetry.TELEMETRY.history_file = tmp_path / "speed_history.json"
    yield server.WS
    server.WS.job["cancel"] = True
    for _ in range(200):
        if not server.WS.busy():
            break
        time.sleep(0.05)
    (server.WS.base, server.WS.alt, server.WS.divergence, server.WS.job, server.WS.last_job,
     telemetry.TELEMETRY.history_file) = saved


def run(ws, days):
    c = TestClient(server.app)
    assert c.post("/api/step", json={"days": days}).status_code == 200
    t0 = time.time()
    while ws.busy() and time.time() - t0 < 120:
        time.sleep(0.05)
    assert not ws.busy()
    return c


def test_each_day_is_timed_per_system_and_world(ws, monkeypatch):
    monkeypatch.setenv("UCSIM_PARALLEL", "0")
    c = run(ws, 3)
    p = c.get("/api/perf").json()
    days = p["days"]
    assert [d["day"] for d in days][-3:] == [1, 2, 3]
    d = days[-1]
    assert d["wall_s"] > 0 and d["base_s"] > 0 and d["alt_s"] and d["alt_s"] > 0
    assert d["base_s"] <= d["wall_s"] * 1.05 and "activity" in d["systems"] and "activity" in d["alt_systems"]
    assert p["summary"]["n"] >= 3 and p["summary"]["days_per_min"] > 0
    st = c.get("/api/status").json()
    assert st["perf"]["last_s"] == d["wall_s"] and len(st["perf"]["spark"]) >= 3


def test_periodic_work_is_named():
    sim = new_simulation(scale=0.02, seed=1)
    sundays = [d for d in range(14) if sim.cal.weekday(d) == 6]
    assert sundays and "weekly" in telemetry.periodic(sim, sundays[0])
    assert "weekly" not in telemetry.periodic(sim, sundays[0] + 1)
    month_end = next(d for d in range(40) if sim.cal.date(d + 1).day == 1)
    assert "monthly" in telemetry.periodic(sim, month_end)


def test_slow_day_explained():
    T = telemetry.Telemetry()
    base = {"systems": {"activity": 0.1, "messaging": 0.02}, "base_s": 0.12, "periodic": []}
    for k in range(10):
        T.days.append({**base, "day": k, "wall_s": 0.13})
    slow = {"day": 10, "systems": {"activity": 0.1, "messaging": 0.5}, "base_s": 0.6, "wall_s": 0.62, "periodic": ["weekly"]}
    T.days.append(slow)
    why = T.why_slow(slow)
    assert "Sunday night" in why and "texts and group chats" in why


def test_logs_and_bundle(ws):
    telemetry.LOG.info("hello from the test %s", 42)
    telemetry.LOG.error("a test error")
    c = TestClient(server.app)
    r = c.get("/api/logs", params={"since": -1}).json()
    msgs = [x["msg"] for x in r["lines"]]
    assert "hello from the test 42" in msgs and r["next"] >= 2
    errs = c.get("/api/logs", params={"level": "error"}).json()["lines"]
    assert errs and all(x["level"] in ("error", "critical") for x in errs)
    newer = c.get("/api/logs", params={"since": r["next"] - 1}).json()["lines"]
    assert all(x["id"] >= r["next"] for x in newer)
    z = zipfile.ZipFile(io.BytesIO(c.get("/api/debug-bundle").content))
    names = set(z.namelist())
    assert {"about.json", "speed_days.json", "log_recent.txt"} <= names
    about = json.loads(z.read("about.json"))
    assert about["world"]["scale"] == ws.base.w.scale and "hello from the test 42" in z.read("log_recent.txt").decode()
    assert not any(n.startswith(("data/", "people")) for n in names)


def test_estimate_from_measured_worlds(ws, monkeypatch):
    monkeypatch.setenv("UCSIM_PARALLEL", "0")
    ws.alt = None
    c = TestClient(server.app)
    assert c.get("/api/perf/estimate", params={"scale": 0.1}).json() == {"measured": False}
    run(ws, 6)
    e = c.get("/api/perf/estimate", params={"scale": 0.04}).json()
    assert e["measured"] and e["from_scale"] == 0.02 and e["early_s"] > 0
