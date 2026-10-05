"""Natural-language What-ifs: the plan validator, the new intervention primitives, the compile job (with a stand-in
model, so no LLM is called), and the API."""
import copy
import time

import numpy as np
import pytest
from fastapi.testclient import TestClient

from ucsim.api import server
from ucsim.engine.runner import fork, new_simulation
from ucsim.llm import backends, compiler
from ucsim.llm.entities import EntityIndex
from ucsim.llm.plan import lower, plan_id, strict_schema, unstrict, validate


@pytest.fixture(scope="module")
def world():
    sim = new_simulation(scale=0.03, seed=11)
    sim.run_days(3)
    return sim


def _plan(*changes, **kw):
    return {"title": "Test", "reply": "", "changes": list(changes), "assumptions": [], "not_modeled": [], "expectations": [],
            "confidence": "medium", **kw}


def test_validator_accepts_real_levers_and_fixes_labels(world):
    ix = EntityIndex(world)
    v = validate(_plan(
        {"kind": "world", "label": "Alcohol", "why": "", "target": "alcohol_permitted", "op": "set", "value": True},
        {"kind": "nudge", "label": "Lonelier", "why": "", "target": "loneliness", "value": 0.05,
         "who": {"var": "school", "op": "eq", "value": "byu"}},           # lower-case label gets fixed
        {"kind": "param", "label": "Asks", "why": "", "target": "romance.ask.base", "op": "add", "value": 0.3},
    ), world, ix)
    assert v["ok"], v["errors"]
    assert v["plan"]["changes"][1]["who"]["value"] == "BYU"
    assert v["changes"][1]["n"] > 0 and "BYU" in v["changes"][1]["who"]


def test_validator_rejects_what_the_engine_cannot_do(world):
    v = validate(_plan(
        {"kind": "world", "label": "x", "why": "", "target": "beard_permitted", "op": "set", "value": True},      # invented key
        {"kind": "trait", "label": "x", "why": "", "target": "mood", "op": "add", "value": 0.1},                 # composed feeling
        {"kind": "trait", "label": "x", "why": "", "target": "rel_status", "op": "set", "value": 4},             # structural
        {"kind": "event", "label": "x", "why": "", "target": "wedding"},                                        # not injectable
        {"kind": "close", "label": "x", "why": "", "target": "venue_type:bar"},                                  # never visited
        {"kind": "param", "label": "x", "why": "", "target": "romance.ask.nonsense", "op": "set", "value": 1},
    ), world)
    assert not v["ok"] and len(v["errors"]) >= 6
    assert not v["plan"]["changes"]


def test_shock_valence_and_clipping(world):
    v = validate(_plan({"kind": "shock", "label": "Bad news", "why": "", "event_label": "Bad news", "story": "{a} heard bad news",
                        "motive": "connection", "valence": 0.9, "salience": 0.99,
                        "effects": [{"var": "mood", "mag": -0.6, "half_life_days": 10}]}), world)
    assert v["ok"]
    c = v["plan"]["changes"][0]
    assert c["effects"][0]["mag"] == -0.3 and c["salience"] == 0.85 and c["valence"] < 0    # sign follows the effects
    assert any("valence" in w for w in v["warnings"])


def test_strict_schema_round_trip():
    s = strict_schema()
    item = s["properties"]["changes"]["items"]
    assert "who_json" in item["properties"] and item["additionalProperties"] is False
    assert set(item["required"]) == set(item["properties"])
    back = unstrict({"title": "t", "changes": [{"kind": "nudge", "who_json": '{"var": "sex", "op": "eq", "value": "M"}', "share": None}]})
    assert back["changes"][0]["who"] == {"var": "sex", "op": "eq", "value": "M"} and "share" not in back["changes"][0]


def test_zero_strength_changes_leave_the_twin_identical(world):
    """Common random numbers: the new primitives draw nothing from shared streams, so a do-nothing plan changes nothing."""
    base = copy.deepcopy(world)
    v = validate(_plan(
        {"kind": "nudge", "label": "n", "why": "", "target": "stress", "value": 0.0},
        {"kind": "nudge", "label": "c", "why": "", "target": "choice:home", "value": 0.0},
        {"kind": "event", "label": "e", "why": "", "target": "family_crisis", "share": 0.0001, "who": {"ids": [0]}, "severity": 1.0},
    ), base)
    atoms = [a for a in lower(v["plan"], base.w.day, "t") if a["target_type"] != "event"]
    twin = fork(base, atoms)
    for _ in range(4):
        base.step_day()
        twin.step_day()
    for c in ("mood", "stress", "loneliness", "attend_rate", "dating_motivation"):
        assert np.array_equal(base.w.P[c], twin.w.P[c]), c


def test_primitives_do_what_they_say(world):
    base = copy.deepcopy(world)
    P = base.w.P
    cx = int(np.bincount(P["complex_id"][(P["complex_id"] >= 0) & P["present"]]).argmax())
    res = np.where((P["complex_id"] == cx) & P["present"])[0]
    v = validate(_plan(
        {"kind": "close", "label": "fire", "why": "", "target": f"complex:{cx}"},
        {"kind": "shock", "label": "Lost home", "why": "", "event_label": "Lost their home", "story": "{a} lost their home",
         "motive": "security", "effects": [{"var": "stress", "mag": 0.12, "half_life_days": 21}],
         "who": {"var": "complex_id", "op": "eq", "value": cx}},
        {"kind": "practice", "label": "Beards", "why": "", "practice_label": "Wearing a beard", "seed_share": 0.05, "base": -3,
         "who": {"var": "sex", "op": "eq", "value": "M"}, "effects_while": [{"var": "self_esteem", "value": 0.02}]},
        {"kind": "nudge", "label": "lonely", "why": "", "target": "loneliness", "value": 0.06, "duration_days": 30},
    ), base)
    assert v["ok"], v["errors"]
    atoms = lower(v["plan"], base.w.day, plan_id(v["plan"]))
    assert [a["target_type"] for a in atoms][-1] == "close"          # closures go last on their day
    alt = fork(base, atoms)
    for _ in range(8):
        base.step_day()
        alt.step_day()
    A = alt.w.P
    assert not ((A["complex_id"][res] == cx) & A["present"][res]).any()          # everyone rehoused
    code = alt.reg.event_ids["whatif_shock"]
    hit = alt.log["a"][alt.log["type"] == code]
    assert set(res) <= set(hit.tolist())                                             # the residents got the shock first
    pres = A["present"].astype(bool)
    assert A["loneliness"][pres].mean() > base.w.P["loneliness"][pres].mean() + 0.03
    rep = [r for r in alt.whatif.report() if r.get("practice")]
    assert rep and rep[0]["practice"]["history"][0]["share"] > 0.02
    from ucsim.analysis.explain import event_record
    rec = event_record(alt, int(np.where(alt.log["type"] == code)[0][0]))
    assert rec["label"] == "Lost their home" and "{a}" in rec["story"]


def test_compile_job_with_a_stand_in_model_repairs_errors(world, monkeypatch, tmp_path):
    monkeypatch.setattr(compiler, "HOME", tmp_path)
    monkeypatch.setattr(compiler, "SETTINGS_FILE", tmp_path / "llm.json")
    calls = []

    def fake_claude(prompt, schema, pack, settings, on_step, cancel, mcp_config):
        calls.append(prompt)
        on_step("tool", "Looking up “Helaman”")
        bad = {"kind": "world", "label": "x", "why": "", "target": "not_a_key", "op": "set", "value": True}
        good = {"kind": "world", "label": "Alcohol permitted", "why": "the request", "target": "alcohol_permitted", "op": "set", "value": True}
        return {"plan": _plan(bad if len(calls) == 1 else good), "text": "", "error": None, "meta": {}}
    monkeypatch.setattr(backends, "run_claude", fake_claude)

    class WS:
        base, alt, plans = world, None, {}
        lock = server.FairLock()
    job = compiler.start(WS, lambda: EntityIndex(world), "alcohol is allowed", [], [], "new", "http://127.0.0.1:1")
    for _ in range(200):
        if job.state in ("done", "error"):
            break
        time.sleep(0.05)
    assert job.state == "done", job.error
    assert len(calls) == 2 and "previous answer had problems" in calls[1]       # one repair round
    assert job.result["ok"] and job.result["plan"]["changes"][0]["target"] == "alcohol_permitted"
    assert any(s["kind"] == "fix" for s in job.steps)


def test_api_entities_apply_and_plans(monkeypatch):
    saved = (server.WS.base, server.WS.alt, server.WS.divergence, server.WS.job)
    base = new_simulation(scale=0.03, seed=5)
    base.run_days(2)
    server.WS.base, server.WS.alt, server.WS.divergence, server.WS.job = base, None, [], {"state": "idle"}
    server.WS._index = None
    try:
        c = TestClient(server.app)
        hits = c.get("/api/entities/search", params={"q": "Helaman"}).json()
        assert hits and hits[0]["ref"] == "complex:587" and hits[0]["who"] == {"var": "complex_id", "op": "eq", "value": 587}
        plan = _plan({"kind": "world", "label": "Coffee", "why": "", "target": "coffee_permitted", "op": "set", "value": True},
                     expectations=[{"text": "More coffee", "variable": "coffee", "direction": "up"}])
        assert c.post("/api/whatif/validate", json={"plan": plan}).json()["ok"]
        r = c.post("/api/whatif/apply", json={"plan": plan, "mode": "new"}).json()
        assert r["ok"] and server.WS.alt is not None
        assert server.WS.alt.interventions[0]["plan"] == r["plan_id"]
        server.WS.base.step_day()
        server.WS.alt.step_day()
        plans = c.get("/api/whatif/plans").json()
        assert plans[0]["title"] == "Test" and plans[0]["expectations"][0]["text"] == "More coffee"
        bad = _plan({"kind": "world", "label": "x", "why": "", "target": "nope", "op": "set", "value": 1})
        assert c.post("/api/whatif/apply", json={"plan": bad, "mode": "new"}).status_code == 409
    finally:
        server.WS.base, server.WS.alt, server.WS.divergence, server.WS.job = saved
        server.WS._index = None
