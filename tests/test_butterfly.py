"""The game-facing reads: weekly field aggregates, the all-field comparison, diverged lives, relationships and
places that differ between worlds, one person's two lives, person history, and the world's pulse."""
import numpy as np
import pytest

from ucsim.analysis import butterfly as B
from ucsim.analysis import fields as F


def test_weekly_field_aggregates_cover_every_chartable_field(ran):
    rec = ran.systems["recorder"]
    Fd = rec.fields
    assert Fd["days"][0] == 0 and Fd["days"][-1] % 7 == 0 and len(Fd["days"]) >= 3
    assert len(rec.field_vars) > 150
    g = Fd["groups"]["all"]
    for v in rec.field_vars:
        assert len(g[v]) == len(Fd["days"])
    spec = ran.w.P.specs["rel_status"]
    assert abs(sum(g["rel_status"][-1]) - 1) < 1e-3 and len(g["rel_status"][-1]) == len(spec.categories)
    t = F.timeline(ran, "loneliness")
    assert len(t["mean"]) == len(t["days"]) and len(t["pct"][-1]) == 5 and "daily_mean" in t
    t = F.timeline(ran, "living", "BYU")
    assert set(t["shares"]) == set(ran.w.P.specs["living"].categories)


def test_compare_fields_ranks_numeric_and_categorical_together(paired):
    base, alt = paired
    c = B.compare_fields(base, alt)
    f = c["fields"]
    assert c["fork_day"] == 3 and len(c["spark_days"]) >= 1
    assert {"num", "cat", "bool"} <= {r["kind"] for r in f.values()}
    assert "rent_burden" in f and f["rent_burden"]["kind"] == "num"
    assert all(np.isfinite(r["effect"]) for r in f.values())
    assert all(0 <= r["changed_share"] <= 1 for r in f.values())
    # rent rose 20%: rent burden should move up in the what-if world
    assert f["rent_burden"]["delta"] > 0
    assert all(len(r["spark"]) == len(c["spark_days"]) for r in f.values())


def test_diverged_people_and_person_divergence(paired):
    base, alt = paired
    d = B.diverged_people(base, alt, k=10)
    assert d["with_any_diff"] > 0 and len(d["people"]) > 0
    top = d["people"][0]
    assert top["score"] >= d["people"][-1]["score"]
    assert top["headline_base"] and top["headline_alt"]
    p = B.person_divergence(base, alt, top["id"])
    assert p["id"] == top["id"] and p["fork_day"] == 3
    assert isinstance(p["life_base"], list) and isinstance(p["states"], list)
    for chain in (p["first_base"], p["first_alt"]):
        if chain:
            assert chain[0]["a"] == top["id"] and chain[0]["day"] >= 3


def test_compare_relationships_and_places(paired):
    base, alt = paired
    r = B.compare_relationships(base, alt, k=5)
    c = r["couples"]
    assert c["base"] > 0 and c["alt"] > 0
    assert c["base"] - c["only_base"] == c["alt"] - c["only_alt"]          # the shared couples
    assert r["friendships"]["base"] - r["friendships"]["only_base"] == r["friendships"]["alt"] - r["friendships"]["only_alt"]
    rows = B.compare_places(base, alt, "complex", "rent_burden")
    assert rows and all(r["n_base"] >= 3 or r["n_alt"] >= 3 for r in rows)
    assert abs(rows[0]["delta"] or 0) >= abs(rows[-1]["delta"] or 0)
    assert B.compare_places(base, alt, "school", "loneliness")
    with pytest.raises(ValueError):
        B.compare_places(base, alt, "planet", "loneliness")


def test_person_history_and_pulse(ran):
    P = ran.w.P
    i = int(np.where(P["present"])[0][0])
    h = F.person_history(ran, i)
    assert h["days"][-1] == ran.w.day and len(h["dates"]) == len(h["days"])
    assert all(len(v) == len(h["days"]) for v in h["nums"].values())
    assert h["cats"]["rel_status"][-1] in P.specs["rel_status"].categories
    p = F.pulse(ran, F.featured_people(ran))
    assert p["present"] == int(P["present"].sum())
    assert sum(r["n"] for r in p["doing"]) <= p["present"]
    assert p["week"] and p["headlines"]
    assert all(t["days"] > 0 for t in p["trends"])
    s = F.summary(ran, ["loneliness", "rel_status", "employed"])
    assert s["fields"]["loneliness"]["p25"] <= s["fields"]["loneliness"]["p75"]
    assert abs(sum(s["fields"]["rel_status"]["shares"].values()) - 1) < 1e-3


@pytest.fixture(scope="module")
def client(paired):
    from fastapi.testclient import TestClient
    from ucsim.api import server
    base, alt = paired
    server.WS.base, server.WS.alt = base, alt
    server.WS.divergence = []
    server.WS.compare_cache = None
    yield TestClient(server.app)
    server.WS.alt = None


def test_game_endpoints(client, paired):
    base, alt = paired
    assert client.get("/api/fields/info").json()["weekly_every"] == 7
    assert "loneliness" in client.get("/api/fields/summary").json()["fields"]
    t = client.get("/api/fields/timeline", params={"var": "mood"}).json()
    assert "base" in t and "alt" in t and t["fork_day"] == 3
    assert client.get("/api/fields/timeline", params={"var": "no_such_field"}).status_code == 404
    assert client.get("/api/compare/fields").json()["fields"]
    ppl = client.get("/api/compare/people", params={"k": 5}).json()["people"]
    assert client.get(f"/api/compare/person/{ppl[0]['id']}").json()["name"]
    assert client.get("/api/compare/relationships").json()["couples"]
    assert client.get("/api/compare/places", params={"kind": "ward", "var": "attend_rate"}).status_code == 200
    assert client.get("/api/compare/places", params={"kind": "planet"}).status_code == 400
    h = client.get(f"/api/person/{ppl[0]['id']}/history").json()
    assert "base" in h and "alt" in h
    r = client.get("/api/relationships", params={"limit": 5}).json()
    assert r["friendships"] > 0 and len(r["couples"]) <= 5 and sum(r["couples_by_status"].values()) > 0
    assert all(c["status"] == "married" for c in client.get("/api/relationships", params={"status": "married"}).json()["couples"])
    pu = client.get("/api/pulse").json()
    assert pu["fork_day"] == 3 and pu["interventions"]
    st = client.get("/api/status").json()
    assert st["last_event_id"] == base.log.n - 1
    ev = client.get("/api/events", params={"after_id": base.log.n - 5, "limit": 50}).json()
    assert ev["total"] == 4
    n0 = len(alt.systems["environment"].manager.items)
    assert client.post("/api/fork/add", json={"interventions": [{"preset": "coffee_permitted"}]}).json()["added"] >= 1
    assert len(alt.systems["environment"].manager.items) > n0
    assert all(it["start_day"] >= alt.w.day for it in alt.systems["environment"].manager.items[n0:])
