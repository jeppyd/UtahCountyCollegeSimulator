"""Cohort filtering, registry integrity, serialization, the HTTP API and the privacy boundary."""
import json
from pathlib import Path

import numpy as np
import polars as pl
import pytest

from ucsim.analysis.person import profile, synthetic_name
from ucsim.analysis.query import describe_filter, evaluate_filter
from ucsim.registry import EVIDENCE_LEVELS, get_registry

ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------- query DSL
def test_filter_basic_ops(ran):
    w, P = ran.w, ran.w.P
    f = evaluate_filter(w, {"var": "sex", "op": "eq", "value": "F"}, ran, include_absent=True)
    assert np.array_equal(f, P.is_("sex", "F"))
    g = evaluate_filter(w, {"and": [{"var": "sex", "op": "eq", "value": "F"}, {"var": "age", "op": "between", "value": [18, 22]}]}, ran, include_absent=True)
    assert np.array_equal(g, P.is_("sex", "F") & (P["age"] >= 18) & (P["age"] <= 22))
    h = evaluate_filter(w, {"not": {"var": "sex", "op": "eq", "value": "F"}}, ran, include_absent=True)
    assert np.array_equal(h, ~P.is_("sex", "F"))
    q = evaluate_filter(w, {"var": "loneliness", "op": "quantile_ge", "value": 0.8}, ran)
    present = P["present"].astype(bool)
    assert 0.15 < q.sum() / present.sum() < 0.25


def test_filter_default_excludes_absent(ran):
    P = ran.w.P
    m = evaluate_filter(ran.w, None, ran)
    assert m.sum() == P["present"].sum()


def test_filter_recent_event_and_household(ran):
    m = evaluate_filter(ran.w, {"recent_event": "new_friend", "days": 30}, ran)
    assert m.any()
    h = evaluate_filter(ran.w, {"household": {"var": "activity", "op": "eq", "value": "active"}, "share": ">=", "value": 0.5}, ran)
    assert h.any() and not h.all()


def test_describe_filter_is_readable(ran):
    s = describe_filter({"and": [{"var": "sex", "op": "eq", "value": "F"}, {"var": "age", "op": "lt", "value": 21}]})
    assert "and" in s.lower() or "," in s


# ---------------------------------------------------------------- registry
def test_registry_integrity():
    reg = get_registry()
    assert len(reg.variables) > 200 and len(reg.mechanisms) > 80 and len(reg.events) > 40
    for v in reg.variables.values():
        assert v.evidence in EVIDENCE_LEVELS, v.id
        if v.dtype == "cat":
            assert v.categories, v.id
    for m in reg.mechanisms.values():
        assert m.evidence in EVIDENCE_LEVELS, m.id
        targets = m.target if isinstance(m.target, list) else [m.target]
        for t in targets:
            assert t in reg.variables, (m.id, t)
        for p, spec in m.params.items():
            assert "value" in spec, (m.id, p)
            if spec.get("range"):
                lo, hi = spec["range"]
                assert lo <= spec["value"] <= hi, (m.id, p)
    for e in reg.events.values():
        for eff in e.effects:
            assert eff["var"] in reg.variables, (e.id, eff)
            assert eff.get("half_life", 1) > 0, (e.id, eff)


# ---------------------------------------------------------------- people & serialization
def test_profile_and_names(ran):
    P = ran.w.P
    i = int(np.where(P["present"])[0][3])
    pr = profile(ran, i)
    assert pr["id"] == i and pr["name"] == synthetic_name(P, i)
    json.dumps(pr, default=float)


def test_save_run_roundtrip(ran, tmp_path, monkeypatch):
    from ucsim.engine import runner
    monkeypatch.setattr(runner, "RUNS", tmp_path)
    out = runner.save_run(ran, run_id="t", snapshots=False)
    persons = pl.read_parquet(out / "persons.parquet")
    edges = pl.read_parquet(out / "edges.parquet")
    events = pl.read_parquet(out / "events.parquet")
    assert persons.height == ran.w.P.n
    assert edges.height == ran.w.E.n
    assert events.height > 0 and "cause" in events.columns
    cfg = json.loads((out / "config.json").read_text(encoding="utf-8"))
    assert cfg["seed"] == ran.w.seed


# ---------------------------------------------------------------- HTTP API
@pytest.fixture(scope="module")
def client(ran):
    from fastapi.testclient import TestClient
    from ucsim.api import server
    server.WS.set_base(ran) if hasattr(server.WS, "set_base") else setattr(server.WS, "base", ran)
    return TestClient(server.app)


def test_api_core_endpoints(client, ran):
    assert client.get("/api/registry").json()["variables"]
    st = client.get("/api/status").json()
    assert st["day"] == ran.w.day
    r = client.get("/api/columns", params={"vars": "loneliness,sex"})
    assert r.status_code == 200 and len(r.content) > ran.w.P.n * 4
    i = int(np.where(ran.w.P["present"])[0][0])
    pj = client.get(f"/api/person/{i}").json()
    assert pj["id"] == i
    assert client.get("/api/events", params={"limit": 5}).status_code == 200
    assert client.get("/api/timeseries", params={"vars": "loneliness"}).status_code == 200
    cnt = client.post("/api/cohort/count", json={"filter": {"var": "sex", "op": "eq", "value": "F"}})
    assert cnt.status_code == 200


# ---------------------------------------------------------------- privacy boundary
def test_committed_priors_contain_only_aggregates():
    pri = json.loads((ROOT / "ucsim" / "priors" / "survey_priors.json").read_text(encoding="utf-8"))
    text = json.dumps(pri)
    assert len(text) < 5_000_000
    # no respondent-level arrays: every list is short (CPT rows, quantile grids, correlation rows)
    def walk(x, path=""):
        if isinstance(x, list):
            assert len(x) <= 400, path
            for k, v in enumerate(x[:5]):
                walk(v, f"{path}[{k}]")
        elif isinstance(x, dict):
            for k, v in x.items():
                walk(v, f"{path}.{k}")
    walk(pri)


def test_raw_survey_files_are_gitignored():
    gi = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "data/raw/" in gi
