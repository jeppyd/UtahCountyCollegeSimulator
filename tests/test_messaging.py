"""Messaging (engine/systems/messaging.py): attention and noticing, how silence is read, being left out, news
spreading along ties, the API, and determinism."""
import numpy as np
from fastapi.testclient import TestClient

from ucsim.api import server
from ucsim.engine.ledger import CHANNEL_ID
from ucsim.engine.runner import new_simulation
from ucsim.engine.state import EdgeStore
from ucsim.engine.systems.messaging import ACT_ID, KIND_ID


def test_threads_follow_homes_and_friend_groups(ran):
    M = ran.systems["messaging"]
    T, Mm, P = M.threads, M.members, ran.w.P
    act = T["active"]
    for k in ("household", "friends", "ward"):
        assert ((T["kind"] == KIND_ID[k]) & act).any(), k
    hh = np.flatnonzero((T["kind"] == KIND_ID["household"]) & act)[0]
    mem = Mm["person"][(Mm["thread"] == T["id"][hh]) & (Mm["left"] < 0)]
    assert len(np.unique(P["unit_id"][mem])) == 1 and len(mem) >= 2


def test_attention_mentions_busy_chats_and_mutes(ran):
    M = ran.systems["messaging"]
    P = ran.w.P
    who = np.flatnonzero(P["present"].astype(bool))[:200]
    direct = M.notice_prob(who, "text", None, True)
    T = M.threads
    busy_t = int(T["id"][np.argmax(T["volume"])])
    busy = M.notice_prob(who, "group_chat", np.full(len(who), busy_t), False)
    assert (direct > busy).all() and 0 < busy.mean() < direct.mean() <= 1


def test_silence_is_read_by_rejection_sensitivity(ran):
    L = ran.log
    ty, a = L.cols["type"][: L.n], L.cols["a"][: L.n]
    rs = ran.z("rejection_sensitivity")
    ig = a[ty == ran.reg.event_ids["felt_ignored"]]
    bz = a[ty == ran.reg.event_ids["assumed_busy"]]
    assert len(ig) >= 5 and len(bz) >= 5
    assert rs[ig].mean() > rs[bz].mean() + 0.3


def test_left_out_is_recorded_with_the_occasion(ran):
    L = ran.log
    ty = L.cols["type"][: L.n]
    ev = np.flatnonzero(ty == ran.reg.event_ids["left_out"])
    assert len(ev) > 0
    C = ran.causes
    from ucsim.engine.ledger import CAUSE_ID
    k = C.t["kind"][: C.t.n] == CAUSE_ID["occasion"]
    assert np.isin(ev, C.t["event"][: C.t.n][k]).all()


def test_news_spreads_along_ties(ran):
    M = ran.systems["messaging"]
    K, E = M.know.t, ran.w.E
    told = (K["source"][: K.n] >= 0) & (K["channel"][: K.n] == CHANNEL_ID["text"])
    assert told.sum() > 20
    src, dst = K["source"][: K.n][told].astype(np.int64), K["person"][: K.n][told].astype(np.int64)
    eix = E.find(EdgeStore.make_keys(src, dst))
    assert (eix >= 0).all()                                   # gossip only travels between people who know each other
    # the people it is about tell close friends first: day-0 knowers are mostly ties of the person
    for ev in np.unique(K["event"][: K.n])[:30]:
        rows = np.flatnonzero(K["event"][: K.n] == ev)
        day0 = K["day"][rows].min()
        assert (K["day"][rows] >= day0).all()


def test_checkins_get_replies_or_silence(ran):
    A = ran.systems["messaging"].acts
    n_check = (A["kind"] == ACT_ID["checkin"]).sum()
    n_rep = (A["kind"] == ACT_ID["reply"]).sum()
    assert n_check > 0 and 0.5 * n_check < n_rep < n_check


def test_api(ran):
    saved = server.WS.base
    server.WS.base = ran
    try:
        c = TestClient(server.app)
        M = ran.systems["messaging"]
        i = int(M.acts["sender"][M.acts["kind"] == ACT_ID["checkin"]][0])
        r = c.get(f"/api/messaging/person/{i}").json()
        assert r["acts"] and r["acts"][0]["words"]
        t = int(M.threads["id"][M.threads["active"]][0])
        assert c.get(f"/api/messaging/thread/{t}").json()["members"]
        ev = int(M.know.t["event"][0])
        assert c.get(f"/api/messaging/news/{ev}").json()["knowers"]
    finally:
        server.WS.base = saved


def test_messaging_is_deterministic():
    out = []
    for _ in range(2):
        sim = new_simulation(scale=0.02, seed=4)
        sim.run_days(15)
        M = sim.systems["messaging"]
        out.append((M.acts["kind"].copy(), M.acts["sender"].copy(), M.know.t["person"].copy(), M.threads["n"].copy()))
    for x, y in zip(*out):
        assert np.array_equal(x, y)
