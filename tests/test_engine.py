"""Engine core: state stores, random streams, time, invariants, emotion attribution, provenance."""
import copy

import numpy as np
import pytest

from ucsim.analysis.explain import event_chain, explain_state
from ucsim.engine.core import Streams, pair_normal
from ucsim.engine.state import EdgeStore, Tie
from ucsim.engine.systems.emotion import STATE_ORDER


# ---------------------------------------------------------------- primitives
def test_edge_store_upsert_find_remove():
    E = EdgeStore(capacity=8)
    a = np.array([5, 1, 9, 3])
    b = np.array([2, 7, 4, 3 + 1])
    keys = EdgeStore.make_keys(a, b)
    assert (keys == EdgeStore.make_keys(b, a)).all(), "keys must be undirected"
    idx = E.upsert(keys)
    assert E.n == 4 and (E.find(keys) == idx).all()
    assert (np.diff(E.key_array) > 0).all(), "keys stay sorted"
    again = E.upsert(keys[:2])
    assert E.n == 4 and (again == E.find(keys[:2])).all()
    E.upsert(EdgeStore.make_keys(np.arange(20, 40), np.arange(40, 60)))  # forces growth
    assert E.n == 24
    rm = np.zeros(E.n, bool)
    rm[E.find(keys[:1])] = True
    E.remove(rm)
    assert E.n == 23 and E.find(keys[:1])[0] < 0


def test_streams_are_deterministic_and_keyed():
    s1, s2 = Streams(42), Streams(42)
    assert np.array_equal(s1.uniform("x", 3, 10), s2.uniform("x", 3, 10))
    assert not np.array_equal(s1.uniform("x", 3, 10), s1.uniform("y", 3, 10))
    assert not np.array_equal(s1.uniform("x", 3, 10), s1.uniform("x", 4, 10))


def test_pair_chemistry_is_symmetric_and_standard_normal():
    rng = np.random.default_rng(0)
    a, b = rng.integers(0, 10_000, 20_000), rng.integers(0, 10_000, 20_000)
    z1, z2 = pair_normal(1, a, b, salt=3), pair_normal(1, b, a, salt=3)
    assert np.allclose(z1, z2)
    assert abs(z1.mean()) < 0.05 and abs(z1.std() - 1) < 0.05
    d1, d2 = pair_normal(1, a, b, salt=3, directed=True), pair_normal(1, b, a, salt=3, directed=True)
    assert not np.allclose(d1, d2), "directed spark differs by direction"


# ---------------------------------------------------------------- time
def test_clock_and_phases(fresh):
    sim = copy.deepcopy(fresh)
    d0 = sim.w.day
    sim.advance_hours(9)  # 6am → 3pm: block0 (8) and block1 (13) have run
    assert sim.w.day == d0 and sim.w.hour == 15
    sim.step_day()        # finishes the day
    assert sim.w.day == d0 + 1 and sim.w.hour == 6


def test_calendar_terms(fresh):
    cal = fresh.cal
    assert cal.date(0).isoformat() == fresh.w.cfg["start_date"]
    assert cal.term("BYU", 10) is not None  # late August/September is fall semester


# ---------------------------------------------------------------- invariants after running
def test_population_and_relationship_invariants(ran):
    P, E = ran.w.P, ran.w.E
    pid = P["partner_id"]
    partnered = P.isin("rel_status", ["talking", "dating", "engaged", "married"])
    # partners are mutual
    i = np.where(partnered & (pid >= 0))[0]
    assert (pid[pid[i]] == i).all()
    # singles have no partner
    assert (pid[P.is_("rel_status", "single") & P["present"].astype(bool)] < 0).all()
    # partner ties exist in the edge store and are flagged romantic/spouse
    idx = E.find(E.make_keys(i, pid[i]))
    assert (idx >= 0).all()
    assert ((E["flags"][idx] & (Tie.ROMANTIC | Tie.SPOUSE)) > 0).all()
    # edge keys are unique; the sorted index (binary search) is sorted and points at each key's row
    k = E.key_array
    assert len(np.unique(k)) == len(k)
    assert (np.diff(E._sorted) > 0).all() and (k[E._perm] == E._sorted).all()
    assert (E.find(k) == np.arange(len(k))).all()
    # no self-loops, endpoints in range
    lo, hi = E.endpoints()
    assert (lo < hi).all() and hi.max() < P.n


def test_probabilities_and_states_bounded(ran):
    P = ran.w.P
    for s in STATE_ORDER:
        x = P[s][: P.n]
        assert np.isfinite(x).all(), s
    for k in ("faith_belief", "attend_rate", "closeness"):
        if k in P:
            x = P[k]
            assert (x >= -1e-6).all() and (x <= 1 + 1e-6).all(), k
    E = ran.w.E
    c = E["closeness"]
    assert ((c >= 0) & (c <= 1)).all()


def test_simulation_produces_social_life(ran):
    P, E = ran.w.P, ran.w.E
    present = P["present"].astype(bool)
    assert P["n_friends"][present].mean() > 2
    assert (E["stage"] >= 3).sum() > P.n
    log = ran.log
    names = {ran.reg.event_names[t] for t in np.unique(log["type"][: log.n])}
    for must in ("new_friend", "first_date"):
        assert must in names, must


def test_emotion_decomposition_is_exact(ran):
    sim = copy.deepcopy(ran)
    sim.step_day()  # a fresh daily composition
    P = sim.w.P
    emo = sim.systems["emotion"]
    n = P.n
    for s in STATE_ORDER:
        total = sum(np.asarray(v, float) for v in emo.contrib[s].values()) + emo.transient[s][:n] + P.internal[f"ar_{s}"][:n]
        lo, hi = 0.0, 1.0
        inside = (total > lo + 1e-3) & (total < hi - 1e-3) & P["present"].astype(bool)
        if s in ("mood", "loneliness", "stress"):
            assert np.allclose(total[inside], P[s][inside], atol=2e-3), s


def test_explain_state_matches_value(ran):
    P = ran.w.P
    i = int(np.where(P["present"])[0][0])
    ex = explain_state(ran, i, "loneliness")
    assert ex["terms"] and all(t["mechanism"].startswith("loneliness.") for t in ex["terms"])
    approx = sum(t["value"] for t in ex["terms"]) + sum(e["value"] for e in ex["events"]) + ex["noise"]
    assert abs(np.clip(approx, 0, 1) - ex["value"]) < 0.06  # events below 0.002 are omitted from the view


def test_event_provenance_chains_point_backwards(ran):
    log = ran.log
    cause = log["cause"][: log.n]
    has = np.where(cause >= 0)[0]
    assert len(has) > 0, "some events must have causal parents"
    assert (cause[has] < has).all(), "a cause precedes its consequence"
    assert (log["day"][cause[has]] <= log["day"][has]).all()
    chain = event_chain(ran, int(has[-1]))
    assert len(chain) >= 2 and chain[0]["cause"] == chain[1]["id"]
    mech = log["mech"][: log.n]
    assert (mech >= 0).mean() > 0.5, "most events name the mechanism that produced them"


def test_reproducible_trajectories():
    from ucsim.engine.runner import new_simulation
    a = new_simulation(scale=0.02, seed=5)
    b = new_simulation(scale=0.02, seed=5)
    a.run_days(5)
    b.run_days(5)
    for k in ("mood", "loneliness", "rel_status", "unit_id", "n_friends"):
        assert np.array_equal(a.w.P[k], b.w.P[k]), k
    assert a.log.n == b.log.n
    assert np.array_equal(a.w.E.key_array, b.w.E.key_array)


@pytest.mark.parametrize("days", [1])
def test_population_grows_with_cohort_and_never_loses_rows(days, fresh):
    sim = copy.deepcopy(fresh)
    n0 = sim.w.P.n
    sim.run_days(days)
    assert sim.w.P.n >= n0
