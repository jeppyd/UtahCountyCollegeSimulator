"""Ledgers: decisions with factors, extra causes, occasions with invitations and attendance."""
import numpy as np
import pytest

from ucsim.engine.ledger import CONSTRAINT, CauseLinks, DecisionLog, OccasionBook, Table, thin_decisions
from ucsim.registry import get_registry


def test_table_stable_ids_survive_thinning():
    t = Table({"x": (np.int32, -1), "v": (np.float32, 0.0, (2,))}, capacity=4)
    ids = t.append(10, x=np.arange(10), v=np.ones((10, 2)))
    assert list(ids) == list(range(10)) and t.n == 10
    t.keep(t["x"] % 2 == 0)
    assert t.n == 5
    assert list(t.pos([0, 1, 2, 9])) == [0, -1, 1, -1]
    more = t.append(2, x=[100, 101])
    assert list(more) == [10, 11]
    assert t.get("x", [10, 4]).tolist() == [100, 4]
    assert t.row(11)["x"] == 101


def test_decision_top_factors_constraints_and_refs():
    reg = get_registry()
    log = DecisionLog(reg.decisions)
    k = 3
    ids = log.record("attend_occasion", 5, [1, 2, 3], ["yes", "no", "no"],
                     {"close_organizer": [2.0, 0.1, 0.3], "tired": [-0.2, -1.5, 0.0], "travel": [0.0, -0.3, -0.9]},
                     base=-1.0, prob=[0.7, 0.2, 0.3], occasion=[7, 7, 7], refs={"close_organizer": ("person", [10, 10, 10])},
                     constraints={"conflict": [False, False, True]})
    assert len(ids) == k
    d0 = log.get(int(ids[0]))
    assert d0["outcome"] == "yes" and d0["factors"][0]["factor"] == "close_organizer"
    assert d0["factors"][0]["ref"] == {"kind": "person", "id": 10}
    assert abs(d0["total"] - (-1.0 + 2.0 - 0.2)) < 1e-2
    d2 = log.get(int(ids[2]))
    assert d2["factors"][0]["factor"] == "conflict" and d2["factors"][0]["constraint"]
    assert abs(d2["factors"][0]["value"]) == pytest.approx(CONSTRAINT, rel=1e-3)
    assert len(log.for_agent(2)) == 1 and len(log.for_occasion(7)) == 3
    summ = log.factor_summary(ids)
    assert {r["factor"] for r in summ} >= {"close_organizer", "tired"}
    with pytest.raises(KeyError):
        log.record("no_such_kind", 0, [1], 0, {})


def test_causes_and_thinning_keep_salient():
    c = CauseLinks()
    c.add([5, 6, 7], "occasion", [3, -1, 3], 0.5)
    assert [r["ref"] for r in c.of(5)] == [3] and c.of(6) == []
    assert sorted(c.effects_of("occasion", 3).tolist()) == [5, 7]
    reg = get_registry()
    log = DecisionLog(reg.decisions)
    a = log.record("attend_occasion", 1, [1, 2], ["yes", "no"], {"tired": [0.1, -0.1]})
    b = log.record("attend_occasion", 50, [3], ["yes"], {"tired": [0.1]})
    log.link_event(a[:1], [99])
    dropped = thin_decisions(log, 10, keep_event_mask_fn=lambda ev: ev == 99)
    assert dropped == 1 and log.get(int(a[0])) and not log.get(int(a[1])) and log.get(int(b[0]))


def test_occasion_book_invites_responses_attendance_series():
    reg = get_registry()
    book = OccasionBook(reg.occasions)
    o = book.plan("dinner", day=3, start=18 * 60 + 30, dur=120, organizer=1, org_kind="household", org_id=40, label="Sunday dinner")
    oid = int(o[0])
    inv = book.invite(oid, [2, 3, 4], inviter=1, channel="text", day=2)
    book.seen(inv[:2], 2)
    book.respond(inv[:2], "yes", 2)
    book.respond(inv[2:], "no", 3)
    came = book.attend(oid, [2, 5], arrive=[18 * 60 + 40, 19 * 60])
    d = book.describe(oid)
    assert d["n_invited"] == 3 and d["n_yes"] == 2 and d["n_came"] == 2 and d["name"] == "Sunday dinner"
    assert sorted(book.attendees(oid).tolist()) == [2, 5]
    rows = {r["person"]: r for r in book.invitation_rows(book.invitations(oid))}
    assert rows[5]["walk_in"] and rows[2]["attended"] and rows[2]["seen_day"] == 2 and rows[4]["response"] == "no"
    assert len(came) == 2
    assert len(book.overlapping(3, 19 * 60, 20 * 60)) == 1 and len(book.overlapping(3, 21 * 60, 22 * 60)) == 0
    s = book.add_series("dinner", weekday=6, start=18 * 60, dur=90, first_day=6, organizer=1)
    assert list(book.due_series(13, 6)) == list(s) and len(book.due_series(14, 0)) == 0
    inst = book.instantiate(s, 13)
    assert book.describe(int(inst[0]))["series"] == int(s[0])


def test_ledgers_never_change_the_world():
    """Recording is passive: a run with ledgers yields the same people as before they were consulted."""
    from ucsim.engine.runner import new_simulation
    a = new_simulation(scale=0.03, seed=2).run_days(8)
    b = new_simulation(scale=0.03, seed=2).run_days(8)
    b.thin_ledgers()
    assert a.log.n == b.log.n
    assert np.array_equal(a.w.P["mood"], b.w.P["mood"])
