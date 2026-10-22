"""Talking to the world (ucsim/llm/talk/): the wording checker (unit tests and the seeded-statement evaluation with
a floor), the fact builders, and Ask / Interview end to end through the API on a fake backend (no model is called)."""
import json
import time
import re
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient

from ucsim.api import server
from ucsim.llm.talk import facts as F
from ucsim.llm.talk import llm
from ucsim.llm.talk.check import Checker, numbers_in

CASES = json.loads((Path(__file__).parent / "data" / "talk_cases.json").read_text(encoding="utf-8"))
CATCH_FLOOR, FALSE_ALARM_CEIL = 0.9, 0.1


def _rates():
    claims = {c["id"]: c for c in CASES["claims"]}
    caught = alarms = n_false = n_true = 0
    for c in CASES["cases"]:
        ok = Checker(claims, mode=c["mode"], self_id=CASES["self_id"]).check(c)["ok"]
        if c["truth"]:
            n_true += 1
            alarms += not ok
        else:
            n_false += 1
            caught += not ok
    return caught / n_false, alarms / n_true, n_true, n_false


def test_checker_evaluation_floor():
    catch, alarm, n_true, n_false = _rates()
    assert n_true + n_false >= 60
    print(f"\nwording checker: catch rate {catch:.0%} of {n_false} false statements, false alarms {alarm:.0%} of {n_true} true ones")
    assert catch >= CATCH_FLOOR and alarm <= FALSE_ALARM_CEIL


def test_numbers_are_read_in_every_form():
    vals = sorted(n["value"] for n in numbers_in("About 40% of 1,204 students, twenty-three people, half of them, 3.5 hours"))
    assert vals == [0.5, 3.5, 23, 40, 1204]
    assert [n["hedged"] for n in numbers_in("about 40%")] == [True]


def test_causal_since_and_hidden_state():
    claims = {c["id"]: c for c in CASES["claims"]}
    ck = Checker(claims)
    assert ck.check({"text": "Since September, Emma Jensen has been lonely.", "claims": ["f1"]})["ok"]
    assert not ck.check({"text": "Since Emma Jensen is lonely, she stays home.", "claims": ["f1"]})["ok"]
    iv = Checker(claims, mode="interview", self_id=5)
    v = iv.check({"text": "Sophie is very stressed.", "claims": ["h1"]})
    assert not v["ok"] and "couldn't know" in v["reasons"][0]


def _fake(feature, stage, system, prompt, schema):
    facts = [json.loads(line) for line in prompt.split("ids)\n", 1)[-1].split("\n\n")[0].splitlines() if line.startswith("{")]
    if stage == "tools":
        return {"calls": [{"tool": "find_people", "args_json": json.dumps({"filter": {"and": [
            {"var": "school", "op": "eq", "value": "BYU"}, {"var": "loneliness", "op": "ge", "value": 0.5}]}, "what": "lonely BYU students"})},
            {"tool": "rank_places", "args_json": json.dumps({"kind": "complex", "var": "loneliness"})},
            {"tool": "no_such_tool", "args_json": "{}"}]}
    if feature == "ask":
        good = [c for c in facts if c["kind"] == "measurement"][-1]       # a place ranking (a clickable place)
        bad = "This is because of the weather." if stage == "answer" else "Exactly 99,999 people are lonely."
        return {"sentences": [{"text": good["text"], "claims": [good["id"]]}, {"text": bad, "claims": [good["id"]]}]}
    good = next(c for c in facts if c["kind"] == "perception")
    feel = next(c for c in facts if c["kind"] == "fact")
    return {"sentences": [{"text": good["text"], "claims": [good["id"]]},
                          {"text": "Some days I just want to end my life.", "claims": [feel["id"]]}]}


@pytest.fixture()
def client(ran, monkeypatch, tmp_path):
    monkeypatch.setattr(llm, "FAKE", _fake)
    monkeypatch.setattr(llm, "TALK_FILE", tmp_path / "talk.json")
    saved = (server.WS.base, server.WS.alt)
    server.WS.base, server.WS.alt = ran, None
    try:
        yield TestClient(server.app)
    finally:
        server.WS.base, server.WS.alt = saved


def _wait(c, jid):
    for _ in range(400):
        r = c.get(f"/api/talk/ask/{jid}").json()
        if r["state"] not in ("queued", "running"):
            return r
        time.sleep(0.05)
    raise AssertionError("job didn't finish")


def test_ask_end_to_end_with_fake_backend(client):
    r = _wait(client, client.post("/api/talk/ask", json={"question": "Where are lonely BYU students?"}).json()["job"])
    assert r["state"] == "done", r["error"]
    res = r["result"]
    assert len(res["sentences"]) == 1 and res["repaired"]
    assert res["removed"] and "isn't in the cited facts" in res["removed"][0]["reasons"][0]
    assert any(t.get("error") for t in res["tools_used"]) and sum("facts" in t for t in res["tools_used"]) == 2
    assert res["refs"] and res["refs"][0]["kind"] == "place" and res["sentences"][0]["refs"] == res["refs"]
    assert res["backend"] == "fake" and res["seconds"] >= 0
    assert any(s["kind"] == "fix" for s in r["steps"])


def test_interview_is_observational_and_safe(client, ran):
    P = ran.w.P
    i = int(np.flatnonzero(P["present"].astype(bool) & (P["age"] > 18))[0])
    before = (ran.memory["rehearsal"].copy(), P["mood"].copy(), ran.log.n, ran.decisions.t.n)
    r = _wait(client, client.post(f"/api/talk/interview/{i}", json={"question": "How are you doing?", "history": []}).json()["job"])
    assert r["state"] == "done", r["error"]
    res = r["result"]
    assert res["person"]["id"] == i and len(res["sentences"]) == 1
    assert any("safe messaging" in x for rm in res["removed"] for x in rm["reasons"])
    after = (ran.memory["rehearsal"], P["mood"], ran.log.n, ran.decisions.t.n)
    assert np.array_equal(before[0], after[0]) and np.array_equal(before[1], after[1]) and before[2:] == after[2:]
    assert isinstance(client.get(f"/api/talk/differs/{i}").json(), list)


def test_dossier_leaves_sensitive_fields_out(ran):
    P = ran.w.P
    i = int(np.flatnonzero(P["present"].astype(bool) & (P["partner_id"] >= 0))[0])
    sh = F.dossier(ran, i)
    for c in sh.claims.values():
        assert not (c.get("field") and F.is_sensitive(ran.reg, c["field"]))
        assert c["kind"] in ("fact", "perception", "belief", "cause")
        assert c["subject"]["id"] == i
    assert F.is_sensitive(ran.reg, "porn_use") and F.is_sensitive(ran.reg, "sex_drive")


def test_status_and_settings(client):
    s = client.get("/api/talk/status").json()
    assert set(s["using"]) == {"ask", "interview"} and s["recommended"] == {"ask": "claude", "interview": "openai"}
    got = client.post("/api/talk/settings", json={"interview_backend": "claude", "sensitive": True}).json()
    assert got["interview_backend"] == "claude" and got["sensitive"] is True
    assert client.post("/api/talk/settings", json={"ask_backend": "rm -rf"}).json()["ask_backend"] == "auto"
    assert client.post("/api/talk/ask", json={"question": "x"}, headers={"origin": "https://evil.example"}).status_code == 403


def test_narrated_scene_is_held_to_its_beats(ran, monkeypatch, tmp_path):
    """A story of a get-together: passages must cite real beats and name only people in the scene; a stranger is
    caught, repaired once, and dropped if it stays."""
    seen = []

    def fake(feature, stage, system, prompt, schema):
        assert feature == "narrate" and "## The beats" in prompt
        seen.append(stage)
        ids = re.findall(r'"id": "(b\d+)"', prompt)
        good = [{"text": f"Passage {k}.", "claims": [b]} for k, b in enumerate(ids)]
        return {"sentences": good + [{"text": "Then Zebulon walked in.", "claims": ["b999"]}]}
    monkeypatch.setattr(llm, "FAKE", fake)
    monkeypatch.setattr(llm, "TALK_FILE", tmp_path / "talk.json")
    saved = (server.WS.base, server.WS.alt)
    server.WS.base, server.WS.alt = ran, None
    try:
        c = TestClient(server.app)
        O = ran.book.occ
        oid = int(O["id"][np.flatnonzero(O["n_came"][: O.n] >= 3)[0]])
        r = _wait(c, c.post("/api/scene/narrate", json={"kind": "occasion", "id": oid}).json()["job"])
        assert r["state"] == "done", r["error"]
        res = r["result"]
        assert res["passages"] and all(p["beats"] for p in res["passages"])
        assert res["removed"] and "don't exist" in res["removed"][0]["reasons"][0]
        assert seen == ["answer", "repair"] and res["coverage"] >= 0.6
    finally:
        server.WS.base, server.WS.alt = saved
