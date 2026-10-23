"""Conversation layers (docs/workstreams/conversations.md): the social records, phones, dating apps, listening in,
perspectives, developing stories and model wording. The acceptance checks, numbered as in the spec:

 1 observation invariance   2 historical integrity   3 participant consistency   4 branch/reset/undo integrity
 5 differentiation          6 fidelity under bad model output   7 ordinary and positive life   8 live behavior
 9 dating integrity         10 scale (tests/test_speed_budget.py)   11 belief revision   12 commitments
 13 story-sifting integrity 14 behavioral depth (ablations)

No real model is ever called: llm.FAKE stands in."""
import copy
import json
import time

import numpy as np
import pytest
from fastapi.testclient import TestClient

from ucsim.analysis import dialogue as D
from ucsim.analysis import phone as PH
from ucsim.analysis import stories as ST
from ucsim.engine.ledger import CHANNEL_ID
from ucsim.engine.runner import fork, new_simulation
from ucsim.engine.systems import social as S
from ucsim.llm.talk import dialogue as TD
from ucsim.llm.talk import llm


def _soc(sim):
    return sim.systems["social"]


def _ev(sim, name):
    n = sim.log.n
    return np.flatnonzero(sim.log["type"][:n] == sim.reg.event_ids[name])


def _fingerprint(sim) -> dict:
    """Everything behavior could depend on: people, ties, events, decisions and the social records."""
    P, E = sim.w.P, sim.w.E
    soc = _soc(sim)
    out = {"log": sim.log.n, "dec": sim.decisions.n if hasattr(sim.decisions, "n") else len(sim.decisions.t.ids),
           "types": sim.log["type"][: sim.log.n].tobytes(), "ex": soc.ex.t.n, "beliefs": soc.beliefs.t.n,
           "concerns": soc.concerns.t.n, "app": soc.app.t.n, "edges": E.n}
    for c in ("mood", "loneliness", "stress", "partner_id"):
        if c in P:
            out[c] = np.asarray(P[c][: P.n]).tobytes()
    for c in ("closeness", "hurt"):
        out["E" + c] = np.asarray(E[c][: E.n]).tobytes()
    for c in ("act", "speaker", "to", "day"):
        out["X" + c] = soc.ex.t[c].tobytes()
    return out


def _pairs_with_texts(sim, k=5):
    X = _soc(sim).ex.t
    r = np.flatnonzero(X["channel"] == CHANNEL_ID["text"])
    seen, out = set(), []
    for q in r[::-1].tolist():
        a, b = int(X.cols["speaker"][q]), int(X.cols["to"][q])
        if b >= 0 and (min(a, b), max(a, b)) not in seen:
            seen.add((min(a, b), max(a, b)))
            out.append((a, b))
        if len(out) >= k:
            break
    return out


def _echo(feature, stage, system, prompt, schema):
    """A fake model that rewords every line with its draft (always passes)."""
    plan = [json.loads(x) for x in prompt.split("## Lines to write")[1].split("\n") if x.startswith("{")]
    return {"lines": [{"id": x["id"], "text": (x.get("draft") or "ok")} for x in plan]}


# ------------------------------------------------------------------------------------------------- 1 observation
def test_watching_and_wording_never_change_the_world(monkeypatch):
    monkeypatch.setattr(llm, "FAKE", _echo)
    a = new_simulation(scale=0.02, seed=5)
    b = new_simulation(scale=0.02, seed=5)
    for d in range(9):
        a.step_day()
        b.step_day()
        # look at everything in b, every day, and word some of it
        for i, j in _pairs_with_texts(b, 3):
            PH.inbox(b, i)
            specs = PH.dm_lines(b, i, j)
            TD.store((TD.lineage(b), D.content_key(specs), D.SCHEMA), {"lines": {}, "removed": 0})
            TD.apply(b, specs, (TD.lineage(b), D.content_key(specs), D.SCHEMA))
        c = PH.conversations(b, days=3)
        for g in c["conversations"][:3]:
            PH.perspective(b, g["exchanges"][0])
        ST.developing(b)
        for t in _soc(b).app.t.ids[:3].tolist():
            PH.app_lines(b, t)
    fa, fb = _fingerprint(a), _fingerprint(b)
    assert fa.keys() == fb.keys()
    for k in fa:
        assert fa[k] == fb[k], f"watching changed {k}"


# ------------------------------------------------------------------------------------------------- 2 history
def test_history_is_as_it_was_then(ran):
    soc = _soc(ran)
    X = soc.ex.t
    # beliefs shown "then" were formed by then
    for r in np.flatnonzero(X["to"] >= 0)[:: max(1, X.n // 60)].tolist():
        pv = PH.perspective(ran, int(X.ids[r]))
        for side in (pv["speaker"], pv["other"]):
            assert all(b["formed"] <= pv["day"] for b in side["beliefs"])
        # what came next is later
        assert all(n["id"] > pv["id"] for n in pv["after"]["next"])
    # a thread cut at a day shows nothing after it, and what it shows matches the full thread up to then
    for i, j in _pairs_with_texts(ran, 4):
        full = PH.dm_lines(ran, i, j)
        if not full:
            continue
        cut = full[len(full) // 2]["day"]
        part = PH.dm_lines(ran, i, j, until=cut)
        assert all(s["day"] <= cut for s in part)
        assert [D.lid(s) for s in part] == [D.lid(s) for s in full if s["day"] <= cut]
    # no exchange is dated in the future
    assert X.n and int(X["day"].max()) <= ran.w.day


# ------------------------------------------------------------------------------------------------- 3 participants
def test_both_phones_show_the_same_messages(ran):
    for i, j in _pairs_with_texts(ran, 6):
        x, y = PH.dm_lines(ran, i, j), PH.dm_lines(ran, j, i)
        assert [D.lid(s) for s in x] == [D.lid(s) for s in y]
        assert [D.fallback(ran, s) for s in x] == [D.fallback(ran, s) for s in y]
        # every line is between the two of them
        assert all(s["speaker"] in (i, j, None) and s["to"] in (i, j, None) for s in x if s.get("kind") != "stage")
        assert len({D.lid(s) for s in x}) == len(x)                    # no message twice


def test_group_chat_shows_only_what_a_member_saw(ran):
    M = ran.systems["messaging"]
    Mm = M.members
    left = np.flatnonzero(Mm["left"] >= 0)
    rows = left[:5].tolist() + np.flatnonzero(Mm["left"] < 0)[:5].tolist()
    for r in rows:
        v, t = int(Mm.cols["person"][r]), int(Mm.cols["thread"][r])
        lines, info = PH.group_lines(ran, v, t)
        spans = [(s["joined"], s["left"] if s["left"] is not None else 10 ** 9) for s in info["spans"]]
        for s in lines:
            if s.get("kind") == "stage":
                continue
            assert any(a <= s["day"] <= b for a, b in spans), "a message from when they weren't in the chat"


# ------------------------------------------------------------------------------------------------- 4 branches
def test_wording_cache_follows_content_and_world(ran, monkeypatch):
    monkeypatch.setattr(llm, "FAKE", _echo)
    base = copy.deepcopy(ran)
    i, j = _pairs_with_texts(base, 1)[0]
    specs = PH.dm_lines(base, i, j)
    key = (TD.lineage(base), D.content_key(specs), D.SCHEMA)
    TD.store(key, {"lines": {D.lid(s): "WORDED" for s in specs}, "removed": 0})
    assert TD.apply(base, specs, key)[1] == "model"
    # undo (a deep copy of the world as it was) keeps the lineage: the same content finds the same words
    back = copy.deepcopy(base)
    assert (TD.lineage(back), D.content_key(PH.dm_lines(back, i, j)), D.SCHEMA) == key
    # a What-if branch: the same history shares words; once its content differs, its key differs
    alt = fork(base, [{"preset": "rent_up_20"}])
    assert (TD.lineage(alt), D.content_key(PH.dm_lines(alt, i, j)), D.SCHEMA) == key
    changed = specs + [D.line(i, j, "checkin", "text", base.w.day + 1, 1, msg=10 ** 9)]
    assert D.content_key(changed) != key[1]
    # another world (even with the same seed) never sees these words
    other = new_simulation(scale=0.02, seed=int(ran.w.seed))
    assert TD.lineage(other) != TD.lineage(base)


# ------------------------------------------------------------------------------------------------- 5 differentiation
def test_people_text_differently(ran):
    P = ran.w.P
    ids = np.flatnonzero(P["present"].astype(bool))[:200]
    styles = [D.style(ran, int(i)) for i in ids]
    assert len({D.style_words(s) for s in styles}) >= 6
    # the same act from different people doesn't read the same
    texts = {D.fallback(ran, D.line(int(i), int(ids[0]), "decline_brief", "text", 3, 1, ex=int(i))) for i in ids[1:60]}
    assert len(texts) >= 8
    # and the same planned line is always worded the same way
    s = D.line(int(ids[1]), int(ids[2]), "accept", "text", 3, 1, ex=7)
    assert D.fallback(ran, s) == D.fallback(ran, copy.deepcopy(s))


# ------------------------------------------------------------------------------------------------- 6 fidelity
def _checker(ran):
    a, b = 1, 2
    na, nb = PH._name(ran, a).split()[0], PH._name(ran, b).split()[0]
    specs = [D.line(a, b, "decline_brief", "text", 5, 1, ex=1), D.line(b, a, "accept", "text", 5, 1, ex=2),
             D.line(a, b, "decline_explained", "text", 5, 1, {"reason": "work"}, ex=3),
             D.line(a, b, "small_talk", "in_person", 5, 1, {"topic": "class"}, ex=4)]
    return TD.DialogueChecker(specs, {a: na, b: nb}, {na, nb}), specs


@pytest.mark.parametrize("sid,text,why", [
    ("x1", "can't, I have work", "kept their reason"),
    ("x1", "yes I'll be there", "turns a no into a yes"),
    ("x2", "can't make it sorry", "turns a yes into a no"),
    ("x3", "can't, I have a midterm", "gives a reason"),
    ("x4", "my girlfriend says hi", "relationship"),
    ("x4", "honestly my anxiety has been bad", "condition"),
    ("x4", "see you saturday at the thing", "sets a time"),
    ("x4", "there were like 40 people there", "number"),
    ("x4", "I promise I'll come next time", "promise"),
    ("x4", "you always ignore me", "accusation"),
    ("x4", "want to come over later?", "invitation"),
    ("x4", "Brigham told me about it", "names someone"),
])
def test_checker_rejects_what_the_record_does_not_say(ran, sid, text, why):
    ck, _ = _checker(ran)
    reasons = ck.check_line(sid, text)
    assert any(why in r for r in reasons), reasons


def test_checker_accepts_faithful_lines(ran):
    ck, _ = _checker(ran)
    assert ck.check_line("x1", "can't, sorry!") == []
    assert ck.check_line("x2", "count me in!") == []
    assert ck.check_line("x3", "can't, I'm working, sorry") == []
    assert ck.check_line("x4", "how's that class going?") == []
    assert ck.check_line("x99", "hi") == ["isn't a planned line"]


def test_bad_model_output_falls_back_line_by_line(ran, monkeypatch, tmp_path):
    calls = []

    def bad(feature, stage, system, prompt, schema):
        calls.append(stage)
        plan = [json.loads(x) for x in prompt.split("## Lines to write")[1].split("\n") if x.startswith("{")]
        out = []
        for k, x in enumerate(plan):
            out.append({"id": x["id"], "text": "my girlfriend and I are engaged!!" if k % 2 == 0 else (x.get("draft") or "ok")})
        return {"lines": out}
    monkeypatch.setattr(llm, "FAKE", bad)
    monkeypatch.setattr(llm, "TALK_FILE", tmp_path / "talk.json")
    i, j = _pairs_with_texts(ran, 1)[0]
    specs = PH.dm_lines(ran, i, j)
    names = {p: PH._name(ran, p).split()[0] for p in (i, j)}
    for s in specs:
        s["_draft"] = D.fallback(ran, s)
    key = ("test-lineage", D.content_key(specs), D.SCHEMA)
    TD.request(key, "test", lambda: (specs, names, set(names.values()), {}), priority=0)
    assert TD.wait_idle(10)
    got = TD.cached(key)
    assert got is not None and calls == ["answer", "repair"]
    texts, src = TD.apply(ran, specs, key)
    assert src == "model"
    assert not any("engaged" in t for t in texts)                         # never shown
    real = [s for s in specs if s.get("kind") != "stage" and not s.get("absent")]
    assert got["removed"] == (len(real) + 1) // 2 and len(got["lines"]) == len(real) // 2


def test_queue_dedupes_and_cancels(monkeypatch, tmp_path):
    gate = []

    def slow(feature, stage, system, prompt, schema):
        while not gate:
            time.sleep(0.01)
        return _echo(feature, stage, system, prompt, schema)
    monkeypatch.setattr(llm, "FAKE", slow)
    monkeypatch.setattr(llm, "TALK_FILE", tmp_path / "talk.json")
    spec = [D.line(1, 2, "accept", "text", 1, 1, ex=1)]
    build = lambda: (spec, {1: "A", 2: "B"}, {"A", "B"}, {})     # noqa: E731
    k1, k2 = ("q", "1", 0), ("q", "2", 0)
    a = TD.request(k1, "one", build)
    assert TD.request(k1, "one again", build)["job"] == a["job"]          # deduplicated
    b = TD.request(k2, "two", build, priority=5)
    assert TD.cancel(job_id=b["job"])
    gate.append(1)
    assert TD.wait_idle(10)
    assert TD.cached(k1) is not None and TD.cached(k2) is None


# ------------------------------------------------------------------------------------------------- 7 ordinary life
def test_most_of_life_is_ordinary_and_warm(ran):
    X = _soc(ran).ex.t
    acts = X["act"]
    ordinary = np.isin(acts, [S.ACT[a] for a in ("small_talk", "warm_moment", "introduce", "reply", "support", "app_chat")])
    hard = np.isin(acts, [S.ACT[a] for a in ("tension", "no_reply", "withdraw", "avoid")])
    assert ordinary.sum() > 3 * hard.sum()
    assert (acts == S.ACT["support"]).any() and (acts == S.ACT["warm_moment"]).any()


# ------------------------------------------------------------------------------------------------- 8 live
def test_listening_appends_without_repeats_or_future(ran):
    c = PH.conversations(ran, days=5)
    assert c["conversations"]
    cut = c["conversations"][len(c["conversations"]) // 2]["exchanges"][0]
    newer = PH.conversations(ran, days=5, since_ex=cut)
    got = [x for g in newer["conversations"] for x in g["exchanges"]]
    assert got and min(got) > cut and len(got) == len(set(got))
    assert all(g["day"] <= ran.w.day for g in c["conversations"])
    # co-location alone is not a conversation: every line is a recorded exchange or a stage note
    assert all(s.get("ex") is not None or s.get("kind") == "stage" for g in c["conversations"] for s in g["lines"])


# ------------------------------------------------------------------------------------------------- 9 dating
def test_app_threads_lead_to_one_date_each(ran):
    soc = _soc(ran)
    T = soc.app.t
    assert T.n
    sets = _ev(ran, "app_date_set")
    pairs = [tuple(sorted((int(ran.log["a"][e]), int(ran.log["b"][e])))) for e in sets]
    assert len(pairs) == len(set(pairs)), "two dates set from the same app match"
    firsts = _ev(ran, "first_date")
    fp = [(int(ran.log["a"][e]), int(ran.log["b"][e])) for e in firsts]           # one event for each of the two
    assert len(fp) == len(set(fp)), "a first date twice"
    st = T["stage"]
    ds = np.flatnonzero(st == S.APP["date_set"])
    assert (T["date_day"][ds] >= T["matched"][ds]).all()
    # every app thread's messages are between its two people
    for r in range(min(T.n, 25)):
        lines, info = PH.app_lines(ran, int(T.ids[r]))
        who = {info["a"]["id"], info["b"]["id"]}
        assert all(s["speaker"] in who for s in lines)
    # a profile is self-presentation, not hidden state
    prof = PH.profile(ran, int(T["a"][0]))
    assert not any(k in prof for k in ("attraction", "mood", "loneliness", "sexuality", "religiosity"))


# ------------------------------------------------------------------------------------------------- 11 beliefs
def test_beliefs_are_revised_by_evidence(ran):
    B = _soc(ran).beliefs.t
    assert B.n
    rv = np.flatnonzero(B["revised_by"] >= 0)
    assert len(rv), "no belief was ever revised"
    X = _soc(ran).ex.t
    for r in rv[:30].tolist():
        assert not B.cols["active"][r] and B.cols["revised_day"][r] >= B.cols["formed"][r]
        p = X.pos([int(B.cols["revised_by"][r])])[0]
        if p >= 0:          # the revising exchange involves the two of them
            assert {int(X.cols["speaker"][p]), int(X.cols["to"][p])} == {int(B.cols["owner"][r]), int(B.cols["about"][r])}
    # at most one active belief per (owner, about, proposition), and the cap holds
    act = np.flatnonzero(B["active"])
    keys = (B["owner"][act].astype(np.int64) << 32) | (B["about"][act].astype(np.int64) << 3) | B["prop"][act]
    assert len(keys) == len(np.unique(keys))


# ------------------------------------------------------------------------------------------------- 12 commitments
def test_promises_are_kept_missed_or_renegotiated(ran):
    C = _soc(ran).concerns.t
    pr = np.flatnonzero(C["kind"] == S.CONCERN["promise"])
    assert len(pr)
    st = {S.STATUS[int(s)] for s in C["status"][pr]}
    assert st & {"fulfilled", "missed", "renegotiated", "open", "lapsed"}
    kept, broken = _ev(ran, "promise_kept"), _ev(ran, "promise_broken")
    assert len(kept) + len(broken) > 0
    done = pr[C["status"][pr] != S.CSTAT["open"]]
    assert (C["resolved_day"][done] >= C["opened"][done]).all()


# ------------------------------------------------------------------------------------------------- 13 stories
def test_developing_stories_are_read_only_linked_and_varied(ran):
    n0, x0 = ran.log.n, _soc(ran).ex.t.n
    r = ST.developing(ran, limit=12)
    assert ran.log.n == n0 and _soc(ran).ex.t.n == x0
    assert r["stories"] and "not representative" in r["note"]
    for s in r["stories"]:
        if "exchange" in s["links"]:
            assert _soc(ran).ex.t.pos([s["links"]["exchange"]])[0] >= 0
        if "concern" in s["links"]:
            assert _soc(ran).concerns.t.pos([s["links"]["concern"]])[0] >= 0
    per = {}
    for s in r["stories"]:
        for p in s["people"]:
            per[p] = per.get(p, 0) + 1
    assert max(per.values()) <= 2
    kinds = [s["kind"] for s in r["stories"]]
    assert len(set(kinds)) >= min(3, len(set(k for k, v in r["found"].items() if v)))


# ------------------------------------------------------------------------------------------------- 14 ablations
def _run(overrides, days=14):
    sim = new_simulation(scale=0.02, seed=3)
    for k, v in overrides.items():
        sim.p.set(k, v)
    sim.run_days(days)
    return sim


def test_mechanisms_matter():
    base = _run({})
    # nobody ever explains a no: no "busy" readings from explained declines, more misreadings
    mute = _run({"social.decline.base": -20.0, "social.decline.reason": 0.0})
    I0, I1 = base.book.inv, mute.book.inv
    said0 = int((I0["said"] == 1).sum())
    said1 = int((I1["said"] == 1).sum())
    assert said0 > 0 and said1 < said0 // 4
    # nobody checks in on a hurt: fewer clarifications
    shy = _run({"social.respond.clarify": -20.0, "social.raise.base": -20.0})
    assert len(_ev(shy, "clarified")) < max(1, len(_ev(base, "clarified")))


# ------------------------------------------------------------------------------------------------- API
@pytest.fixture()
def client(ran, monkeypatch, tmp_path):
    from ucsim.api import server
    monkeypatch.setattr(llm, "FAKE", _echo)
    monkeypatch.setattr(llm, "TALK_FILE", tmp_path / "talk.json")
    saved = (server.WS.base, server.WS.alt)
    server.WS.base, server.WS.alt = ran, None
    try:
        yield TestClient(server.app)
    finally:
        server.WS.base, server.WS.alt = saved


def test_phone_api_end_to_end(client, ran):
    i, j = _pairs_with_texts(ran, 1)[0]
    n0 = ran.log.n
    ib = client.get(f"/api/phone/inbox/{i}").json()
    assert any(c["id"] == j for c in ib["dms"]) and ib["note"]
    d = client.get(f"/api/phone/dm?a={i}&b={j}").json()
    assert d["lines"] and d["wording"]["source"] in ("structured", "model")
    r = client.post("/api/phone/realize", json={"kind": "dm", "a": i, "b": j}).json()
    assert TD.wait_idle(10)
    if r.get("job"):
        assert client.get(f"/api/phone/realize/{r['job']}").json()["state"] == "done"
    d2 = client.get(f"/api/phone/dm?a={j}&b={i}").json()
    assert d2["wording"]["source"] == "model" and [x["text"] for x in d2["lines"]] == [x["text"] for x in client.get(f"/api/phone/dm?a={i}&b={j}").json()["lines"]]
    L = client.get(f"/api/listen?people={i},{j}&days=10").json()
    assert "conversations" in L
    assert client.get("/api/stories").json()["stories"] is not None
    ex = d["lines"][-1]["ex"] or next((x["ex"] for x in d["lines"] if x["ex"] is not None), None)
    if ex is not None:
        pv = client.get(f"/api/phone/perspective/{ex}").json()
        assert pv["speaker"] and "model" in pv["note"]
    assert ran.log.n == n0
